"""Bridge the index to its two consumers, on plain dicts (no judge import):

  - coder agent: judge finding / trajectory -> the tool names involved -> code locations.
  - workflow generation: a structured repo summary (interfaces the agent exposes).

Tool names are often dotted/underscored (`hubspot.search`, `send_email`); we resolve the
whole name, then fall back to its parts (last segment = the method, usually the symbol).
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from .index import Index, Symbol
from .query import find_symbol, grep


def _candidates(idx: Index, name: str, limit: int = 10) -> list[Symbol]:
    found = find_symbol(idx, name, limit)
    if found:
        return found
    out: list[Symbol] = []
    for part in [p for p in reversed(re.split(r"[._\-]", name)) if len(p) >= 2]:
        for s in find_symbol(idx, part, limit):
            if s not in out:
                out.append(s)
    return out[:limit]


def locate(idx: Index, names) -> dict[str, list[Symbol]]:
    """name -> candidate definitions. Empty list = not found in source (worth a grep)."""
    return {n: _candidates(idx, n) for n in dict.fromkeys(names)}


def names_from_steps(steps: list[dict]) -> list[str]:
    """Tool names referenced by trajectory steps (preserves order, de-duped)."""
    return list(dict.fromkeys(s["tool"] for s in steps
                              if s.get("type") == "tool_call" and s.get("tool")))


def from_trajectory(idx: Index, steps: list[dict]) -> dict[str, list[Symbol]]:
    return locate(idx, names_from_steps(steps))


def from_issue(idx: Index, issue: dict, steps: list[dict]) -> dict[str, list[Symbol]]:
    """A judge issue cites evidence_steps; resolve the tools at those steps to code."""
    cited = [steps[i] for i in issue.get("evidence_steps", []) if 0 <= i < len(steps)]
    return locate(idx, names_from_steps(cited))


def repo_context(idx: Index, max_symbols: int = 300) -> dict:
    """Structured summary for workflow generation: what the repo is and what it exposes."""
    langs = Counter(Path(f).suffix for f in idx.files if Path(f).suffix)
    return {
        "files": len(idx.files),
        "languages": dict(langs.most_common()),
        "symbols": [{"name": s.name, "kind": s.kind, "file": s.file, "line": s.line}
                    for s in idx.symbols[:max_symbols]],
        "symbol_count": len(idx.symbols),
    }


def _demo() -> None:
    import tempfile
    from .index import build
    d = Path(tempfile.mkdtemp())
    (d / "tools.py").write_text(
        "class Hubspot:\n    def search(self, q): ...\n\ndef send_email(to): ...\n")
    idx = build(d)
    steps = [
        {"type": "tool_call", "tool": "hubspot.search", "id": "c1"},
        {"type": "tool_result", "id": "c1", "ok": True},
        {"type": "tool_call", "tool": "send_email", "id": "c2"},
    ]
    loc = from_trajectory(idx, steps)
    assert any(s.name == "search" for s in loc["hubspot.search"]), loc      # dotted -> last part
    assert any(s.name == "send_email" for s in loc["send_email"]), loc
    issue = {"issue": "redundant", "evidence_steps": [0]}
    assert "hubspot.search" in from_issue(idx, issue, steps)
    ctx = repo_context(idx)
    assert ctx["files"] == 1 and ctx["languages"] == {".py": 1}
    assert any(s["name"] == "send_email" for s in ctx["symbols"])
    print("ok")


if __name__ == "__main__":
    _demo()
