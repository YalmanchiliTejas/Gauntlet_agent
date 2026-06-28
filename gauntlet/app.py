"""Ingress: GitHub webhook + Slack + UI. Verify, ack fast, hand off to runner.

GitHub needs a response in ~10s, so handlers only verify + parse + submit; the
actual run happens in a background asyncio task (see runner.submit).
"""
import hashlib
import hmac
import time

from fastapi import FastAPI, Header, HTTPException, Request

from . import config
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
        if p["action"] not in ("opened", "synchronize", "reopened"):
            return {"skipped": p["action"]}
        pr = p["pull_request"]
        job = runner.Job(p["repository"]["full_name"], pr["head"]["sha"],
                         f"pr/{pr['number']}", p["installation"]["id"])
    else:
        return {"skipped": x_github_event}

    runner.submit(job)
    return {"queued": True}


@app.post("/trigger")
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


@app.post("/workflows/generate")
async def workflows_generate(payload: WorkflowGeneratePayload):
    """Generate validated workflow drafts from docs, repo context, and service twins."""
    payload_dict = model_to_dict(payload)
    if not (payload_dict["docs"] or payload_dict["services"] or payload_dict["mcp_tools"]):
        raise HTTPException(400, "provide docs, services, or MCP tools before generating workflows")
    try:
        return generate_workflows_json(payload_dict)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(400, str(exc))


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
