"""Default coder: drive the Codex CLI to edit the repo in place.

Codex (like CodeRabbit's "install a CLI, don't define a schema") edits files in the working
dir; the loop snapshots before/after for the authoritative diff, so `propose` just runs Codex
with a grounded fix prompt and returns its log. `run(cmd)->str` is injected (microVM `/exec`
or local subprocess), keeping this swappable for a Claude-based coder behind the Coder protocol.
"""
from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from findings import Finding, detail_summary


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

    def propose(self, root: Path, findings: list[Finding], context: str, failures: str = "") -> str:
        prompt = fix_prompt(findings, context, failures)
        argv = ["codex", "exec"] + (["-m", self.model] if self.model else []) + [prompt]
        if self.run is not None:
            return self.run("codex exec " + (f"-m {self.model} " if self.model else "") + shlex.quote(prompt))
        p = subprocess.run(argv, cwd=root, capture_output=True, text=True)
        return (p.stdout + p.stderr)[-8000:]
