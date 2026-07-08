"""Orchestrate a find-and-fix run: collect findings → verify-loop → open a PR (or report).

Manual opt-in (the `gauntlet-fix` label). Runs entirely in an ephemeral copy of the source; the
verification loop re-runs the gauntlet (build+run+judge) + scanners each iteration via
`runner.run_and_judge`, and a PR is opened only when everything comes back clean.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import tempfile
from itertools import count
from pathlib import Path

log = logging.getLogger(__name__)

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

        # Discovery: seed from the run the user clicked "Fix" on when we have it (avoids a
        # fresh, stochastic judge pass); otherwise run+judge to find the findings.
        if (job.seed_verdict or {}).get("issues"):
            before_verdict = job.seed_verdict.get("verdict", "n/a")
            discovery_verdict = job.seed_verdict
            discovery_traj = list(job.seed_trajectory or [])
            findings = (from_judge(job.seed_verdict, job.seed_trajectory or [], build(root))
                        + codescan_static.scan(root))
        else:
            first = await run_and_judge(root, plan, f"{job.repo.replace('/', '-')}-fix{next(names)}-{job.sha[:7]}", workdir)
            before_verdict = first["verdict"].get("verdict", "n/a")
            discovery_verdict = first["verdict"]
            discovery_traj = ([s.raw for s in load_trajectory(first["trajectory"])]
                              if first["trajectory"] else [])
            findings = _findings_from(first["verdict"], first["trajectory"], root)
        findings += investigate(root, render(context_for(root, _seed_names(build(root), findings))),
                                _local_exec(root))
        if not findings:
            await github.complete_check_run(gh, job.repo, check_id, "success",
                                            "Nothing to fix", "No security/redundancy/reliability findings.")
            await _fire_fix_callback(job, "passed", verdict={"note": "Nothing to fix"})
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

        def save_fix(status: str, pr_url: str | None = None) -> None:
            _persist_fix(job, status=status, iterations=result.iterations,
                         before_verdict=before_verdict, verdict=discovery_verdict,
                         findings=findings, trajectory=discovery_traj,
                         patch=result.diff, pr_url=pr_url)

        if result.converged:
            after = snapshot(root)
            changed_files = sorted(rel for rel in set(before) | set(after) if before.get(rel) != after.get(rel))
            if not changed_files:
                await github.complete_check_run(gh, job.repo, check_id, "neutral",
                                                "No changes produced",
                                                "Verification passed without any code changes.")
                save_fix("converged_no_changes")
                await _fire_fix_callback(job, "passed",
                                         verdict={"note": "Converged with no code changes"})
                return
            branch = f"gauntlet/fix-{job.sha[:7]}"
            await github.create_branch(gh, job.repo, branch, job.sha)
            for rel in changed_files:
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
            save_fix("converged", pr_url=url)
            await _fire_fix_callback(job, "passed",
                                     verdict={"note": "Fix PR opened", "pr_url": url,
                                              "changed_files": changed_files, "diff": result.diff[:40_000]})
        else:
            await github.complete_check_run(gh, job.repo, check_id, "neutral",
                                            "Could not fully verify a fix", report(result, before_verdict))
            save_fix("not_converged")
            await _fire_fix_callback(job, "failed",
                                     error="Could not fully verify a fix (see the run's check on GitHub).")
    except Exception as e:
        await github.complete_check_run(gh, job.repo, check_id, "neutral",
                                        "Fix loop failed", f"```\n{e}\n```")
        await _fire_fix_callback(job, "error", error=str(e))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _persist_fix(job, *, status: str, iterations: int, before_verdict: str | None,
                 verdict: dict | None, findings: list, trajectory: list,
                 patch: str | None, pr_url: str | None = None) -> None:
    """Best-effort: record the fixed run's trace, judge findings, and Codex patch to Supabase.
    No-op when DATABASE_URL is unset; never breaks a fix run."""
    from dataclasses import asdict

    from gauntlet.store import store
    try:
        store().save_fix(
            workflow_id=getattr(job, "workflow_id", None), repo=job.repo, sha=job.sha,
            ref=job.ref, status=status, iterations=iterations, before_verdict=before_verdict,
            verdict=verdict, findings=[asdict(f) for f in findings],
            trajectory=trajectory, patch=patch, pr_url=pr_url)
    except Exception as exc:
        log.warning("save_fix failed workflow_id=%s: %s", getattr(job, "workflow_id", None), exc)


async def _fire_fix_callback(job, status: str, *, verdict: dict | None = None,
                             error: str | None = None) -> None:
    """Report the fix outcome to the delegating backend (Fly) so the UI's fix run resolves.
    Best-effort; no callback_url (label-triggered fix) = skip."""
    if not getattr(job, "callback_url", None):
        return
    import httpx
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            resp = await c.post(job.callback_url,
                                headers={"Authorization": f"Bearer {job.callback_secret or ''}"},
                                json={"status": status, "verdict": verdict, "error": error,
                                      "workflow_id": job.workflow_id})
            resp.raise_for_status()
    except Exception as exc:
        log.warning("fix callback failed workflow_id=%s: %s", getattr(job, "workflow_id", None), exc)
