"""Ingress: GitHub webhook + Slack + UI. Verify, ack fast, hand off to runner.

GitHub needs a response in ~10s, so handlers only verify + parse + submit; the
actual run happens in a background asyncio task (see runner.submit).
"""
import hashlib
import hmac
import time

from fastapi import Depends, FastAPI, Header, HTTPException, Request

from . import config
from .store import store
from .workflows.api_models import WorkflowGeneratePayload, model_to_dict
from .workflows.generate import generate_workflows_json

app = FastAPI()


def _verify_github(body: bytes, signature: str | None) -> None:
    if not config.GITHUB_WEBHOOK_SECRET:
        raise HTTPException(500, "GITHUB_WEBHOOK_SECRET not set")
    expected = "sha256=" + hmac.new(
        config.GITHUB_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        raise HTTPException(401, "bad signature")


def _verify_slack(body: bytes, ts: str | None, sig: str | None) -> None:
    if not config.SLACK_SIGNING_SECRET:
        raise HTTPException(500, "SLACK_SIGNING_SECRET not set")
    if not ts or abs(time.time() - int(ts)) > 60 * 5:
        raise HTTPException(401, "stale timestamp")
    base = f"v0:{ts}:".encode() + body
    expected = "v0=" + hmac.new(
        config.SLACK_SIGNING_SECRET.encode(), base, hashlib.sha256).hexdigest()
    if not sig or not hmac.compare_digest(expected, sig):
        raise HTTPException(401, "bad signature")


def require_api_key(x_api_key: str | None = Header(None)) -> None:
    """Gate the read/trigger/generate endpoints. Blank key = open (dev)."""
    if config.GAUNTLET_API_KEY and not hmac.compare_digest(x_api_key or "", config.GAUNTLET_API_KEY):
        raise HTTPException(401, "bad api key")


_KEYED = [Depends(require_api_key)]  # attach to protected routes


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(""),
    x_hub_signature_256: str | None = Header(None),
):
    body = await request.body()
    _verify_github(body, x_hub_signature_256)
    p = await request.json()
    from . import runner

    if x_github_event == "push":
        if p.get("after", "").strip("0") == "":  # branch deleted
            return {"skipped": "branch deleted"}
        job = runner.Job(p["repository"]["full_name"], p["after"],
                         p["ref"], p["installation"]["id"])
    elif x_github_event == "pull_request":
        pr = p["pull_request"]
        # Manual opt-in: labeling a PR `gauntlet-fix` runs the find-and-fix loop.
        # ref carries the PR head branch so the fix PR can target it.
        if p["action"] == "labeled" and p.get("label", {}).get("name") == "gauntlet-fix":
            from . import fix  # thin shim re-exporting fixer.job (keeps gauntlet/ self-contained)

            fix.submit(runner.Job(p["repository"]["full_name"], pr["head"]["sha"],
                                  pr["head"]["ref"], p["installation"]["id"]))
            return {"queued": "fix"}
        if p["action"] not in ("opened", "synchronize", "reopened"):
            return {"skipped": p["action"]}
        job = runner.Job(p["repository"]["full_name"], pr["head"]["sha"],
                         f"pr/{pr['number']}", p["installation"]["id"])
    else:
        return {"skipped": x_github_event}

    runner.submit(job)
    return {"queued": True}


@app.post("/trigger", dependencies=_KEYED)
async def ui_trigger(payload: dict):
    """UI trigger. Body: {repo, sha, ref?, installation_id}."""
    from . import runner

    try:
        job = runner.Job(payload["repo"], payload["sha"],
                         payload.get("ref", payload["sha"]),
                         int(payload["installation_id"]))
    except (KeyError, ValueError, TypeError):
        raise HTTPException(400, "need repo, sha, installation_id")
    runner.submit(job)
    return {"queued": True}


@app.post("/workflows/generate", dependencies=_KEYED)
async def workflows_generate(payload: WorkflowGeneratePayload):
    """Generate validated workflow drafts from docs, repo context, and service twins."""
    payload_dict = model_to_dict(payload)
    if not (payload_dict["docs"] or payload_dict["services"] or payload_dict["mcp_tools"]):
        raise HTTPException(400, "provide docs, services, or MCP tools before generating workflows")
    try:
        result = generate_workflows_json(payload_dict)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(400, str(exc))
    try:  # best-effort persistence
        store().save_workflows(user_id=None, drafts=result.get("workflows") or [])
    except Exception:
        pass
    return result


# ---------- read API (backend: runs/traces, workflows, users) ----------


@app.get("/runs", dependencies=_KEYED)
async def list_runs(user_id: str | None = None, repo: str | None = None, limit: int = 50):
    return {"runs": store().list_runs(user_id=user_id, repo=repo, limit=limit)}


@app.get("/runs/{run_id}", dependencies=_KEYED)
async def get_run(run_id: str):
    run = store().get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return run


@app.get("/workflows", dependencies=_KEYED)
async def list_workflows(user_id: str | None = None, limit: int = 50):
    return {"workflows": store().list_workflows(user_id=user_id, limit=limit)}


@app.get("/workflows/{workflow_id}", dependencies=_KEYED)
async def get_workflow(workflow_id: str):
    wf = store().get_workflow(workflow_id)
    if not wf:
        raise HTTPException(404, "workflow not found")
    return wf


import pathlib

from sandbox.orchestrator import DOMAINS  # services we ship a twin for

_REGISTRY = pathlib.Path(__file__).resolve().parent.parent / "twins" / "registry"


def _resolve_twins(twins: dict | None) -> dict | None:
    """Keep only services with a shipped twin, filling a missing version from the
    registry (latest). None/empty passes through unchanged."""
    if not twins:
        return twins
    out: dict = {}
    for name, ver in twins.items():
        if name not in DOMAINS:
            continue
        if not ver:
            d = _REGISTRY / name
            vers = sorted(p.name for p in d.iterdir() if p.is_dir()) if d.is_dir() else []
            ver = vers[-1] if vers else None
        if ver:
            out[name] = ver
    return out


@app.post("/sandbox/run")
async def sandbox_run(payload: dict, x_sandbox_secret: str | None = Header(None)):
    """Execute a workflow run delegated from the product backend (Fly): run the
    customer's repo in the VM with the given twins, bake the task prompt in as
    GAUNTLET_TASK_PROMPT, and POST the outcome to callback_url on finish.

    Body: {repo, sha, installation_id, ref?, task_prompt?, twins?, modes?,
           workflow_id?, callback_url?, callback_secret?}.
    twins/modes are already resolved to {service: version} / {service: mode} by
    the caller (only services with a shipped twin registry entry)."""
    if config.SANDBOX_INBOUND_SECRET and not hmac.compare_digest(
            x_sandbox_secret or "", config.SANDBOX_INBOUND_SECRET):
        raise HTTPException(401, "bad sandbox secret")
    from . import runner

    twins = _resolve_twins(payload.get("twins"))
    try:
        job = runner.Job(
            repo=payload["repo"], sha=payload["sha"],
            ref=payload.get("ref", payload["sha"]),
            installation_id=int(payload["installation_id"]),
            task_prompt=payload.get("task_prompt"),
            twins=twins,
            modes=payload.get("modes") or {},
            workflow_id=payload.get("workflow_id"),
            egress_default=payload.get("egress_default", "live"),
            callback_url=payload.get("callback_url"),
            callback_secret=payload.get("callback_secret"))
    except (KeyError, ValueError, TypeError):
        raise HTTPException(400, "need repo, sha, installation_id")
    runner.submit(job)
    return {"queued": True, "workflow_id": payload.get("workflow_id")}


@app.post("/sandbox/exec")
async def sandbox_exec(payload: dict, x_sandbox_secret: str | None = Header(None)):
    """Run+trace ONLY (no judge). Fly's fixer loop / judge live on Fly and call this with
    an uploaded source bundle (the possibly-uncommitted working copy), then judge the
    returned trajectory locally.

    Body: {bundle_b64, name?, twins?, modes?, env?, egress_default?}.
    Returns: {result, trajectory: str|null, egress_log: str|null, services: [str]}.
    ponytail: bundle is base64 JSON — fine for small repos; switch to multipart/object-store
    if bundles get large."""
    import base64
    import io
    import tempfile
    import zipfile
    from pathlib import Path

    if config.SANDBOX_INBOUND_SECRET and not hmac.compare_digest(
            x_sandbox_secret or "", config.SANDBOX_INBOUND_SECRET):
        raise HTTPException(401, "bad sandbox secret")
    try:
        raw = base64.b64decode(payload["bundle_b64"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(400, "need bundle_b64 (base64 zip of the source)")

    from . import build_resolver, runner

    workdir = Path(tempfile.mkdtemp(prefix="gauntlet-exec-"))
    root = workdir / "src"
    root.mkdir()
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            z.extractall(root)  # ponytail: trusted caller (Fly), auth'd by the shared secret
        plan = build_resolver.resolve(root)
        if payload.get("twins") is not None:  # let the caller override declared twins
            plan.twins = _resolve_twins(payload.get("twins")) or {}
            plan.modes = payload.get("modes") or {}
        extra_env = payload.get("env") or None
        out = await runner.run_and_trace(
            root, plan, payload.get("name", "fly-exec"), workdir,
            extra_env=extra_env, egress_default=payload.get("egress_default", "live"))
        tpath, epath = out["trajectory"], out["egress_log"]
        return {"result": out["result"],
                "trajectory": tpath.read_text() if tpath else None,
                "egress_log": epath.read_text() if epath else None,
                "services": out["services"]}
    finally:
        import shutil
        shutil.rmtree(workdir, ignore_errors=True)


@app.post("/slack/command")
async def slack_command(
    request: Request,
    x_slack_request_timestamp: str | None = Header(None),
    x_slack_signature: str | None = Header(None),
):
    """Slack slash command: `/gauntlet owner/repo sha installation_id`."""
    body = await request.body()
    _verify_slack(body, x_slack_request_timestamp, x_slack_signature)
    form = dict(p.split("=", 1) for p in body.decode().split("&") if "=" in p)
    from urllib.parse import unquote_plus
    parts = unquote_plus(form.get("text", "")).split()
    if len(parts) != 3:
        return {"text": "usage: /gauntlet owner/repo <sha> <installation_id>"}
    repo, sha, inst = parts
    from . import runner

    runner.submit(runner.Job(repo, sha, sha, int(inst)))
    return {"text": f"Queued run for {repo}@{sha[:7]}."}
