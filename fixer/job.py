"""Orchestrate a find-and-fix run: collect findings → verify-loop → open a PR (or report).

Manual opt-in (the `gauntlet-fix` label). Runs entirely in an ephemeral copy of the source; the
verification loop re-runs the gauntlet (build+run+judge) + scanners each iteration via
`runner.run_and_judge`, and a PR is opened only when everything comes back clean.
"""
from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
from itertools import count
from pathlib import Path

from codeindex import build
from codeindex.context import context_for, render
from codescan import static as codescan_static
from codescan.investigate import investigate
from gauntlet import build_resolver, github
from gauntlet.runner import Job, run_and_judge
from judge.trace import load as load_trajectory

from findings import Finding, detail_summary, fingerprint, from_judge, summary
from .codex import CodexCoder
from .loop import fix_loop, snapshot
from .output import pr_body, report

CHECK_NAME = "gauntlet-fix"
_SEVERE = {"high", "med"}
_inflight: dict[tuple[str, str], asyncio.Task] = {}


def submit(job: Job) -> None:
    key = (job.repo, job.ref)
    old = _inflight.get(key)
    if old and not old.done():
        old.cancel()
    task = asyncio.create_task(_run(job))
    _inflight[key] = task
    task.add_done_callback(lambda t: _inflight.pop(key, None))


def _local_exec(root: Path):
    def run(cmd: str) -> str:
        p = subprocess.run(cmd, shell=True, cwd=root, capture_output=True, text=True, timeout=120)
        return (p.stdout + p.stderr)[-8000:]
    return run


def _seed_names(idx, findings: list[Finding]) -> list[str]:
    files = {f.file for f in findings if f.file}
    return [s.name for s in idx.symbols if s.file in files][:30]


def _findings_from(verdict: dict, trajectory: Path | None, root: Path) -> list[Finding]:
    idx = build(root)
    steps = [s.raw for s in load_trajectory(trajectory)] if trajectory else []
    return from_judge(verdict, steps, idx) + codescan_static.scan(root)


def _failures_text(result: dict, verdict: dict, remaining: list[Finding]) -> str:
    return (f"tests exit={result.get('exit_code')}\n"
            f"sim verdict={verdict.get('verdict')}\n"
            f"{(result.get('stderr') or '')[-2000:]}\n"
            f"remaining:\n{detail_summary(remaining)}")


async def _run(job: Job) -> None:
    gh = await github.installation_token(job.installation_id, job.repo)
    check_id = await github.create_check_run(gh, job.repo, job.sha, CHECK_NAME)
    workdir = Path(tempfile.mkdtemp(prefix="gauntlet-fix-"))
    try:
        root = await github.download_source(gh, job.repo, job.sha, workdir)
        plan = build_resolver.resolve(root)
        names = count()

        # Initial pass: gauntlet+judge + scanners + (optional) agentic investigation -> findings.
        first = await run_and_judge(root, plan, f"{job.repo.replace('/', '-')}-fix{next(names)}-{job.sha[:7]}", workdir)
        before_verdict = first["verdict"].get("verdict", "n/a")
        findings = _findings_from(first["verdict"], first["trajectory"], root)
        findings += investigate(root, render(context_for(root, _seed_names(build(root), findings))),
                                _local_exec(root))
        if not findings:
            await github.complete_check_run(gh, job.repo, check_id, "success",
                                            "Nothing to fix", "No security/redundancy/reliability findings.")
            return

        coder = CodexCoder()  # default; runs codex in the workdir
        ctx_fn = lambda r, f: render(context_for(r, _seed_names(build(r), f)))

        # Convergence gates on the ORIGINAL findings by identity; issues a fresh judge run
        # newly flags are reported on the PR, not chased (the judge is stochastic).
        orig_fps = {fingerprint(f) for f in findings}
        new_seen: dict[tuple, Finding] = {}

        async def verify(r: Path):
            # Cheap gate first: static scan is seconds, a gauntlet run is a VM build+boot.
            # ponytail: scan-only cheap gate; add a local test run if scans pass too easily.
            cheap = [f for f in codescan_static.scan(r)
                     if f.severity in _SEVERE and fingerprint(f) in orig_fps]
            if cheap:
                return False, f"static scan still failing:\n{detail_summary(cheap)}", cheap
            out = await run_and_judge(r, plan, f"{job.repo.replace('/', '-')}-fix{next(names)}-{job.sha[:7]}", workdir)
            cur = [f for f in _findings_from(out["verdict"], out["trajectory"], r) if f.severity in _SEVERE]
            rem = [f for f in cur if fingerprint(f) in orig_fps]
            new_seen.update((fingerprint(f), f) for f in cur if fingerprint(f) not in orig_fps)
            # "warn" from judge noise doesn't block; a "fail" verdict (regression) still does.
            ok = (out["result"].get("exit_code") == 0
                  and out["verdict"].get("verdict") != "fail" and not rem)
            return ok, ("" if ok else _failures_text(out["result"], out["verdict"], rem)), rem

        before = snapshot(root)
        result = await fix_loop(root, findings, coder, verify, context_fn=ctx_fn)

        if result.converged:
            branch = f"gauntlet/fix-{job.sha[:7]}"
            await github.create_branch(gh, job.repo, branch, job.sha)
            after = snapshot(root)
            for rel in sorted(set(before) | set(after)):
                if before.get(rel) != after.get(rel):
                    await github.put_file(gh, job.repo, branch, rel,
                                          after[rel].encode(), "gauntlet: automated fix")
            fixed = [f for f in findings if f.severity in _SEVERE]  # what verification gated on
            body = pr_body(result, fixed, before_verdict, "pass")
            if new_seen:
                body += ("\n\n## Observed during fixing (new, not blocking — review)\n"
                         + summary(list(new_seen.values())))
            url = await github.open_pr(gh, job.repo, branch, job.ref,
                                       "Gauntlet automated fix", body)
            await github.complete_check_run(gh, job.repo, check_id, "success",
                                            "Fix PR opened", f"Verified fix opened: {url}")
        else:
            await github.complete_check_run(gh, job.repo, check_id, "neutral",
                                            "Could not fully verify a fix", report(result, before_verdict))
    except Exception as e:
        await github.complete_check_run(gh, job.repo, check_id, "neutral",
                                        "Fix loop failed", f"```\n{e}\n```")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
