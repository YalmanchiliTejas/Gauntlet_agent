"""One job, end to end, plus debounce of rapid pushes.

token -> checkout -> resolve plan -> boot sandbox egress (twins + default-deny
proxy) -> build & run MicroVM through the proxy -> poll the harness result ->
report via Checks -> terminate + teardown + delete source.
"""
import asyncio
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from sandbox.orchestrator import Sandbox

from . import build_resolver, github, microvm

CHECK_NAME = "gauntlet"


@dataclass
class Job:
    repo: str            # "owner/name"
    sha: str             # exact commit to run
    ref: str             # branch/PR ref, used as the debounce key
    installation_id: int


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


async def _poll_result(endpoint: str, timeout: float = 600) -> dict:
    """Poll the in-VM harness until the command finishes (or we give up)."""
    deadline = asyncio.get_event_loop().time() + timeout
    async with httpx.AsyncClient(timeout=15) as c:
        while asyncio.get_event_loop().time() < deadline:
            try:
                r = await c.get(f"{endpoint.rstrip('/')}/result")
                data = r.json()
                if data.get("done"):
                    return data
            except httpx.HTTPError:
                pass
            await asyncio.sleep(2)
    return {"done": False, "exit_code": -1, "stderr": "timed out waiting for result"}


async def _run(job: Job) -> None:
    token = await github.installation_token(job.installation_id, job.repo)
    check_id = await github.create_check_run(token, job.repo, job.sha, CHECK_NAME)
    workdir = Path(tempfile.mkdtemp(prefix="gauntlet-"))
    sandbox = None
    microvm_id = None
    try:
        root = await github.download_source(token, job.repo, job.sha, workdir)
        plan = build_resolver.resolve(root)

        # Boot the egress world this run declared; default-deny everything else.
        env = {}
        if plan.twins:
            sandbox = Sandbox(plan.twins, plan.modes).start()
            env = sandbox.env_for_sandbox()

        key = microvm.upload_bundle(root, plan.dockerfile)
        image_id = microvm.build_image(key, f"{job.repo.replace('/', '-')}-{job.sha[:7]}")
        microvm_id, endpoint = microvm.run(image_id, env=env)

        result = await _poll_result(endpoint)
        ok = result.get("exit_code") == 0
        summary = (f"`{plan.run}` exited {result.get('exit_code')}\n\n"
                   f"```\n{(result.get('stdout') or '')[-3000:]}\n"
                   f"{(result.get('stderr') or '')[-1000:]}\n```")
        await github.complete_check_run(token, job.repo, check_id,
                                        "success" if ok else "failure",
                                        "Passed" if ok else "Failed", summary)
    except asyncio.CancelledError:
        await github.complete_check_run(token, job.repo, check_id, "cancelled",
                                        "Superseded", "A newer push cancelled this run.")
        raise
    except Exception as e:  # report, don't swallow
        await github.complete_check_run(token, job.repo, check_id, "failure",
                                        "Run failed", f"```\n{e}\n```")
    finally:
        if microvm_id:
            microvm.terminate(microvm_id)
        if sandbox:
            sandbox.teardown()
        shutil.rmtree(workdir, ignore_errors=True)  # don't persist source
