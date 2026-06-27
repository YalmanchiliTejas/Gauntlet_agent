"""One job, end to end, plus debounce of rapid pushes."""
import asyncio
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from . import build_resolver, github, microvm

CHECK_NAME = "gauntlet"


@dataclass
class Job:
    repo: str            # "owner/name"
    sha: str             # exact commit to run
    ref: str             # branch/PR ref, used as the debounce key
    installation_id: int


# ponytail: in-memory, single-process. One task per (repo, ref); a newer push
# for the same ref cancels the older run. Move to SQS + a dedup table if you
# ever run more than one worker.
_inflight: dict[tuple[str, str], asyncio.Task] = {}


def submit(job: Job) -> None:
    key = (job.repo, job.ref)
    old = _inflight.get(key)
    if old and not old.done():
        old.cancel()
    task = asyncio.create_task(_run(job))
    _inflight[key] = task
    task.add_done_callback(lambda t: _inflight.pop(key, None))


async def _run(job: Job) -> None:
    token = await github.installation_token(job.installation_id, job.repo)
    check_id = await github.create_check_run(token, job.repo, job.sha, CHECK_NAME)
    workdir = Path(tempfile.mkdtemp(prefix="gauntlet-"))
    microvm_id = None
    try:
        root = await github.download_source(token, job.repo, job.sha, workdir)
        dockerfile = build_resolver.resolve(root)
        key = microvm.upload_bundle(root, dockerfile)
        image_id = microvm.build_image(key, f"{job.repo.replace('/', '-')}-{job.sha[:7]}")
        microvm_id, endpoint = microvm.run(image_id)

        # ponytail: "running the codebase" = confirm the app came up at its
        # endpoint. Swap this for the real per-customer harness (run tests,
        # post logs) when you have one.
        async with httpx.AsyncClient(timeout=30) as c:
            resp = await c.get(endpoint)
        ok = resp.status_code < 500
        await github.complete_check_run(
            token, job.repo, check_id,
            "success" if ok else "failure",
            "MicroVM ran" if ok else "MicroVM unhealthy",
            f"Endpoint {endpoint} returned {resp.status_code}.",
        )
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
        # Don't persist source past the run.
        shutil.rmtree(workdir, ignore_errors=True)
