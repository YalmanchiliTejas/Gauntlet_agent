"""Generated-CLI investigation agent — finds what the linters miss.

Borrowed from CodeRabbit: the model investigates by writing shell commands (grep, ast-grep,
semgrep -e, cat) run in the sandbox, instead of bespoke tool schemas. Seeded with the cross-file
context bundle. Bounded steps; output normalizes to `Finding`. `run(cmd)->str` is injected
(local subprocess now, microVM `/exec` later); no LLM key -> returns [] (static-only).
"""
from __future__ import annotations

import json
from typing import Callable

from judge._llm import _extract_json_object, _send_prompt
from judge.agent import _OBS_CAP, _has_creds, _send_retry
from judge.redact import redact_str

from findings import Finding

_SYSTEM = """You are a security + reliability auditor of an AI agent's codebase. Investigate by
issuing shell commands (grep, ast-grep, semgrep -e '<pattern>', cat, sed -n) — the repo is the
working directory. Hunt for: security (injection, SSRF, unsafe deserialization, authz gaps,
hardcoded/leaked secrets, path traversal) AND reliability (unhandled errors, missing retry/backoff
on flaky calls, leaked resources/sessions, missing input validation). Confirm each issue by reading
the actual code before reporting it.

Cross-file context to start from:
{context}

Reply with JSON only, one action per turn:
  {{"tool": "exec", "args": {{"cmd": "<shell>"}}}}
  {{"finish": {{"findings": [
     {{"axis": "security|reliability", "title": "...", "severity": "low|med|high",
       "file": "path", "line": 0, "evidence": "what proves it"}} ]}}}}
Finish only after you have read the code backing each finding."""


def investigate(root, context_text: str, run: Callable[[str], str],
                sender: Callable | None = None, max_steps: int = 10) -> list[Finding]:
    if sender is None and not _has_creds():
        return []  # no LLM -> rely on static scanners only
    send = sender or _send_prompt
    transcript = [_SYSTEM.format(context=context_text)]
    for _ in range(max_steps):
        try:
            action = _extract_json_object(_send_retry(send, "\n\n".join(transcript)))
        except Exception as e:
            transcript.append(f"Observation: unusable reply ({e}). Emit one JSON action.")
            continue
        if "finish" in action:
            out = []
            for f in action["finish"].get("findings", []):
                out.append(Finding(
                    axis="security" if f.get("axis") == "security" else "reliability",
                    title=f.get("title", "issue"), severity=f.get("severity", "med"),
                    detail=f.get("evidence", ""), file=f.get("file"), line=f.get("line"),
                    evidence=f.get("evidence", ""), source="investigate"))
            return out
        if "tool" in action and action["tool"] == "exec":
            cmd = action.get("args", {}).get("cmd", "")
            try:
                obs = redact_str(run(cmd))            # mask secrets before they hit the model
            except Exception as e:
                obs = f"error: {e}"
            transcript.append(f"$ {cmd}\n{obs[:_OBS_CAP]}")
        else:
            transcript.append("Observation: emit a single exec or finish object.")
    return []


def _demo() -> None:
    # Scripted: grep -> finish with one finding. Stub run returns canned output. No network.
    replies = iter([
        '{"tool": "exec", "args": {"cmd": "grep -rn API_KEY ."}}',
        '{"finish": {"findings": [{"axis": "security", "title": "hardcoded API key",'
        ' "severity": "high", "file": "cfg.py", "line": 2, "evidence": "API_KEY = \\"sk-...\\""}]}}',
    ])
    out = investigate(".", "context: cfg.py defines settings",
                      run=lambda cmd: 'cfg.py:2:API_KEY = "sk-live-redactme0123456789"',
                      sender=lambda _p: next(replies))
    assert len(out) == 1 and out[0].axis == "security" and out[0].file == "cfg.py", out
    print("ok")


if __name__ == "__main__":
    _demo()
