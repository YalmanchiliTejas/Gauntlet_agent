"""Default coder: drive the Codex CLI to edit the repo in place.

Codex (like CodeRabbit's "install a CLI, don't define a schema") edits files in the working
dir; the loop snapshots before/after for the authoritative diff, so `propose` just runs Codex
with a grounded fix prompt and returns its log. `run(cmd)->str` is injected (microVM `/exec`
or local subprocess), keeping this swappable for a Claude-based coder behind the Coder protocol.
"""
from __future__ import annotations

import logging
import os
import shlex
import subprocess
from pathlib import Path

from findings import Finding, detail_summary

log = logging.getLogger(__name__)

_authed = False


def _ensure_codex_auth() -> None:
    """`codex exec` ignores the OPENAI_API_KEY env var for auth (it defaults to ChatGPT-style
    auth and 401s) — it needs an explicit login that writes ~/.codex/auth.json. Feed the key
    via stdin, not argv, so it never shows up in `ps`. Runs once per process."""
    global _authed
    if _authed:
        return
    _authed = True
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        log.warning("OPENAI_API_KEY not set — codex will 401")
        return
    r = subprocess.run(["codex", "login", "--api-key"], input=key + "\n",
                       capture_output=True, text=True)
    if r.returncode != 0:
        log.warning("codex login failed (%s): %s", r.returncode, (r.stdout + r.stderr)[-500:])


def fix_prompt(findings: list[Finding], context: str, failures: str = "") -> str:
    """The grounded fix prompt (CodeRabbit-style): findings + cross-file context + constraints
    + the previous iteration's concrete failures. Uses `detail_summary` so the judge's
    recommendation and evidence reach the coder, not just the title/location."""
    p = ["Fix the issues below in this repository. Make the SMALLEST change that resolves each.",
         "Do not break the callers/importers shown in the context. Keep existing behavior otherwise.",
         "", "## Issues", detail_summary(findings), "", "## Cross-file context", context]
    if failures:
        p += ["", "## Previous attempt still failing — address this output", failures[:6000]]
    return "\n".join(p)


class CodexCoder:
    def __init__(self, run=None, model: str | None = None):
        self.run = run            # run(cmd:str)->str in the repo (sandbox/local); None = local subprocess
        self.model = model

    # --dangerously-bypass-approvals-and-sandbox: headless, no TTY, OS sandbox may be absent.
    # --skip-git-repo-check: the fixer workdir is an extracted tarball, not a git repo; without
    #   this codex exec exits 1.
    _FLAGS = ["--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check"]

    def propose(self, root: Path, findings: list[Finding], context: str, failures: str = "") -> str:
        prompt = fix_prompt(findings, context, failures)
        mflag = ["-m", self.model] if self.model else []
        argv = ["codex", "exec", *self._FLAGS, *mflag, prompt]
        if self.run is not None:
            return self.run(f"codex exec {' '.join(self._FLAGS)} "
                            + (f"-m {self.model} " if self.model else "") + shlex.quote(prompt))
        _ensure_codex_auth()
        p = subprocess.run(argv, cwd=root, capture_output=True, text=True)
        out = (p.stdout + p.stderr)
        if p.returncode != 0:
            log.warning("codex exec exited %s\n%s", p.returncode, out[-3000:])
        return out[-8000:]
