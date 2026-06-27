"""GitHub App auth + the three API surfaces we need: tokens, source, Checks."""
import io
import tarfile
import time
from pathlib import Path

import httpx
import jwt

from . import config

API = "https://api.github.com"


def app_jwt() -> str:
    """Short-lived JWT signed with the App private key (RS256)."""
    now = int(time.time())
    return jwt.encode(
        {"iat": now - 60, "exp": now + 9 * 60, "iss": config.GITHUB_APP_ID},
        config.GITHUB_APP_PRIVATE_KEY,
        algorithm="RS256",
    )


async def installation_token(installation_id: int, repo: str) -> str:
    """Mint a fresh installation token scoped to a single repo for this run."""
    name = repo.split("/")[-1]
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            f"{API}/app/installations/{installation_id}/access_tokens",
            headers={"Authorization": f"Bearer {app_jwt()}",
                     "Accept": "application/vnd.github+json"},
            json={"repositories": [name]},
        )
        r.raise_for_status()
        return r.json()["token"]


async def download_source(token: str, repo: str, sha: str, dest: Path) -> Path:
    """Fetch the tarball at an exact commit and extract it. Returns the repo root.

    Tarball over `git clone` on purpose: no git binary, no full history, just
    the tree at `sha`.
    """
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as c:
        r = await c.get(f"{API}/repos/{repo}/tarball/{sha}",
                        headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        with tarfile.open(fileobj=io.BytesIO(r.content), mode="r:gz") as tf:
            tf.extractall(dest)  # ponytail: trusted source (the customer's own repo)
    # GitHub wraps everything in a single top-level dir.
    return next(p for p in dest.iterdir() if p.is_dir())


async def create_check_run(token: str, repo: str, sha: str, name: str) -> int:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            f"{API}/repos/{repo}/check-runs",
            headers={"Authorization": f"Bearer {token}",
                     "Accept": "application/vnd.github+json"},
            json={"name": name, "head_sha": sha, "status": "in_progress"},
        )
        r.raise_for_status()
        return r.json()["id"]


async def complete_check_run(token: str, repo: str, check_id: int,
                             conclusion: str, title: str, summary: str) -> None:
    """conclusion: success | failure | cancelled | neutral ..."""
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.patch(
            f"{API}/repos/{repo}/check-runs/{check_id}",
            headers={"Authorization": f"Bearer {token}",
                     "Accept": "application/vnd.github+json"},
            json={"status": "completed", "conclusion": conclusion,
                  "output": {"title": title, "summary": summary}},
        )
        r.raise_for_status()
