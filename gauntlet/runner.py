"""One job, end to end, plus debounce of rapid pushes.

token -> checkout -> resolve plan -> boot sandbox egress (twins + default-deny
proxy) -> build & run MicroVM through the proxy -> poll the harness result ->
report via Checks -> terminate + teardown + delete source.
"""
import asyncio
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from judge import ingest
from judge import judge as run_judge
from judge.verify import load_egress
from sandbox.orchestrator import Sandbox

from . import build_resolver, config, github
from .store import read_trajectory, store


def _sandbox_backend():
    """Pick the sandbox that builds/runs the customer image. Docker when no
    MicroVM bucket is configured (or forced); MicroVMs otherwise."""
    use_docker = config.SANDBOX_BACKEND == "docker" or (
        config.SANDBOX_BACKEND != "microvm" and not config.MICROVM_S3_BUCKET)
    if use_docker:
        from . import docker_vm
        return docker_vm
    from . import microvm
    return microvm


microvm = _sandbox_backend()

CHECK_NAME = "gauntlet"
_TRAJECTORY_VM_PATH = "/gauntlet_trajectory.jsonl"  # where a native-JSONL agent may write


def _otel_env() -> dict:
    """Point the customer's (OTel-instrumented) agent at the in-VM harness trace sink,
    so we capture its trajectory with no change to their code."""
    return {"OTEL_TRACES_EXPORTER": "otlp",
            "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",  # JSON so the stdlib harness can parse it
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "http://127.0.0.1:8080/v1/traces",
            "OTEL_SERVICE_NAME": "agent-under-test",
            "TRAJECTORY_FILE": _TRAJECTORY_VM_PATH}


def _format_judge(v: dict) -> str:
    issues = v.get("issues") or []
    head = f"\n\n**Judge: {v.get('verdict', '?')}** — {len(issues)} issue(s)"
    if v.get("note"):
        head += f" _({v['note']})_"
    lines = [f"- [{i.get('severity', '?')}] {i.get('issue')}"
             + (f" → {i['recommendation']}" if i.get("recommendation") else "")
             for i in issues[:10]]
    return head + ("\n" + "\n".join(lines) if lines else "")


@dataclass
class Job:
    repo: str            # "owner/name"
    sha: str             # exact commit to run
    ref: str             # branch/PR ref, used as the debounce key
    installation_id: int
    # Workflow-run overrides (a /workflows/{id}/run job). When set, the declared
    # twins replace the repo's .gauntlet.json ones and the task prompt is baked
    # into the VM as GAUNTLET_TASK_PROMPT for the agent to read.
    task_prompt: str | None = None
    twins: dict | None = None      # {service: version}; None = use the repo's plan
    modes: dict | None = None      # {service: twin|live|record}
    workflow_id: str | None = None
    egress_default: str = "deny"   # deny (PR checks) | live (workflow runs: undeclared -> real)
    # When set, POST the outcome here on finish (the Fly backend delegates to us
    # and stores the result in its own DB via this callback).
    callback_url: str | None = None
    callback_secret: str | None = None


# ponytail: in-memory, single-process. One task per (repo, ref); a newer push
# for the same ref cancels the older run. Move to SQS + a dedup table for >1 worker.
_inflight: dict[tuple[str, str], asyncio.Task] = {}


def submit(job: Job) -> None:
    key = (job.repo, job.ref)
    old = _inflight.get(key)
    if old and not old.done():
        old.cancel()
    task = asyncio.create_task(_run(job))
    _inflight[key] = task
    task.add_done_callback(lambda t: _inflight.pop(key, None))


async def _poll_result(endpoint: str, token: str, timeout: float = 600) -> dict:
    """Poll the in-VM harness until the command finishes (or we give up).
    Every MicroVM request needs the auth token."""
    deadline = asyncio.get_event_loop().time() + timeout
    headers = {"X-aws-proxy-auth": token}
    async with httpx.AsyncClient(timeout=15) as c:
        while asyncio.get_event_loop().time() < deadline:
            try:
                r = await c.get(f"{endpoint.rstrip('/')}/result", headers=headers)
                data = r.json()
                if data.get("done"):
                    return data
            except httpx.HTTPError:
                pass
            await asyncio.sleep(2)
    return {"done": False, "exit_code": -1, "stderr": "timed out waiting for result"}


async def _fetch_trajectory(endpoint: str, vm_token: str, workdir: Path,
                            egress_log: Path | None = None) -> Path | None:
    """Trajectory for the judge, best source first:
       1. native JSONL the agent wrote, 2. OTel spans it exported,
       3. fallback: synthesize from the proxy egress log (uninstrumented agent)."""
    path = workdir / "trajectory.jsonl"
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(f"{endpoint.rstrip('/')}/trajectory", headers={"X-aws-proxy-auth": vm_token})
            traj = r.json()
        if traj.get("native"):
            path.write_text(traj["native"])
        else:
            steps = ingest.from_otlp_docs(traj.get("otlp") or [])
            path.write_text("".join(json.dumps(s) + "\n" for s in steps))
    except Exception:
        path.write_text("")
    if path.stat().st_size:
        return path
    # No spans and no native file -> fall back to the network record.
    events = load_egress(egress_log) if egress_log else []
    if events:
        path.write_text("".join(json.dumps(s) + "\n" for s in ingest.from_egress(events)))
        return path
    return None


async def run_and_trace(root: Path, plan, name: str, workdir: Path,
                        extra_env: dict | None = None, egress_default: str = "deny") -> dict:
    """Build+run the CUSTOMER agent in the sandbox, capture result + trajectory, teardown.
    Returns {"result", "trajectory": Path|None, "egress_log": Path|None, "services": list}.
    This is all the droplet does — NO judge. The judge + fixer loop run on Fly, which calls
    this over the `/sandbox/exec` endpoint and judges the returned trajectory locally.
    `extra_env` bakes extra vars into the image (e.g. GAUNTLET_TASK_PROMPT for a workflow run).
    `egress_default` = deny (default) | live (undeclared domains passthrough to the real host)."""
    sandbox = None
    microvm_id = None
    try:
        env, ca_pem = _otel_env(), None  # always capture the agent trajectory
        if extra_env:
            env.update(extra_env)
        if plan.twins or egress_default != "deny":
            sandbox = Sandbox(plan.twins, plan.modes, egress_default=egress_default).start()
            env.update(sandbox.env_for_sandbox())
            ca_pem = Path(sandbox.ca).read_bytes()  # bake the proxy CA into the image
        key = microvm.upload_bundle(root, plan.dockerfile, ca_pem=ca_pem, env=env)
        image_id = microvm.build_image(key, name)
        microvm_id, endpoint, vm_token = microvm.run(image_id)
        result = await _poll_result(endpoint, vm_token)
        tpath = await _fetch_trajectory(endpoint, vm_token, workdir,
                                        sandbox.egress_log if sandbox else None)
        # Copy the egress log into the workdir so it outlives sandbox teardown — the Fly-side
        # judge needs it alongside the trajectory.
        epath = None
        if sandbox and Path(sandbox.egress_log).exists():
            epath = workdir / "egress.jsonl"
            epath.write_bytes(Path(sandbox.egress_log).read_bytes())
        return {"result": result, "trajectory": tpath, "egress_log": epath,
                "services": sorted(plan.twins) if plan.twins else []}
    finally:
        if microvm_id:
            microvm.terminate(microvm_id)
        if sandbox:
            sandbox.teardown()


async def run_and_judge(root: Path, plan, name: str, workdir: Path,
                        extra_env: dict | None = None, egress_default: str = "deny") -> dict:
    """run_and_trace + judge in one call. Retained for the droplet's STANDALONE mode; the
    Fly integration instead calls run_and_trace (via /sandbox/exec) and judges on Fly.
    Returns {"result", "verdict" (dict), "trajectory": Path|None}."""
    out = await run_and_trace(root, plan, name, workdir,
                              extra_env=extra_env, egress_default=egress_default)
    tpath = out["trajectory"]
    verdict = (run_judge(str(tpath),
                         egress_log=str(out["egress_log"]) if out["egress_log"] else None,
                         services=set(out["services"]))
               if tpath else {"verdict": "n/a", "issues": [], "note": "no trajectory captured"})
    return {"result": out["result"], "verdict": verdict, "trajectory": tpath}


async def _run(job: Job) -> None:
    gh_token = await github.installation_token(job.installation_id, job.repo)
    check_id = await github.create_check_run(gh_token, job.repo, job.sha, CHECK_NAME)
    workdir = Path(tempfile.mkdtemp(prefix="gauntlet-"))
    run_id = _persist_run_start(job)
    try:
        root = await github.download_source(gh_token, job.repo, job.sha, workdir)
        plan = build_resolver.resolve(root)
        if job.twins is not None:  # workflow run: its declared twins replace the repo's
            plan.twins, plan.modes = job.twins, job.modes or {}
        extra_env = {"GAUNTLET_TASK_PROMPT": job.task_prompt} if job.task_prompt else None
        out = await run_and_judge(root, plan, f"{job.repo.replace('/', '-')}-{job.sha[:7]}", workdir,
                                  extra_env=extra_env, egress_default=job.egress_default)
        result = out["result"]
        ok = result.get("exit_code") == 0
        summary = (f"`{plan.run}` exited {result.get('exit_code')}\n\n"
                   f"```\n{(result.get('stdout') or '')[-3000:]}\n"
                   f"{(result.get('stderr') or '')[-1000:]}\n```"
                   f"{_format_judge(out['verdict'])}")
        _persist_run_finish(run_id, "passed" if ok else "failed",
                            exit_code=result.get("exit_code"), verdict=out["verdict"],
                            trajectory=out.get("trajectory"))
        await _fire_callback(job, "passed" if ok else "failed",
                             exit_code=result.get("exit_code"), verdict=out["verdict"])
        await github.complete_check_run(gh_token, job.repo, check_id,
                                        "success" if ok else "failure",
                                        "Passed" if ok else "Failed", summary)
    except asyncio.CancelledError:
        _persist_run_finish(run_id, "canceled", error="Superseded by a newer push.")
        await _fire_callback(job, "canceled", error="Superseded by a newer push.")
        await github.complete_check_run(gh_token, job.repo, check_id, "cancelled",
                                        "Superseded", "A newer push cancelled this run.")
        raise
    except Exception as e:  # report, don't swallow
        _persist_run_finish(run_id, "error", error=str(e))
        await _fire_callback(job, "error", error=str(e))
        await github.complete_check_run(gh_token, job.repo, check_id, "failure",
                                        "Run failed", f"```\n{e}\n```")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)  # don't persist source


async def _fire_callback(job: Job, status: str, *, exit_code: int | None = None,
                         verdict: dict | None = None, error: str | None = None) -> None:
    """Report the outcome to the delegating backend (Fly). Best-effort — a failed
    callback must never fail the run. Trajectory is omitted (can be large); the
    verdict carries the judge summary the UI needs."""
    if not job.callback_url:
        return
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            await c.post(job.callback_url,
                         headers={"Authorization": f"Bearer {job.callback_secret or ''}"},
                         json={"status": status, "exit_code": exit_code,
                               "verdict": verdict, "error": error,
                               "workflow_id": job.workflow_id})
    except Exception:
        pass


# Persistence is best-effort: a database hiccup must never fail a run.
def _persist_run_start(job: Job) -> str | None:
    try:
        s = store()
        user = s.upsert_user(github_installation_id=job.installation_id)
        return s.create_run(user_id=user["id"] if user else None,
                            repo=job.repo, sha=job.sha, ref=job.ref,
                            workflow_id=job.workflow_id)
    except Exception:
        return None


def _persist_run_finish(run_id, status, *, exit_code=None, verdict=None,
                        trajectory=None, error=None) -> None:
    try:
        store().finish_run(run_id=run_id, status=status, exit_code=exit_code,
                           verdict=verdict,
                           trajectory=read_trajectory(trajectory) if trajectory else None,
                           error=error)
    except Exception:
        pass
