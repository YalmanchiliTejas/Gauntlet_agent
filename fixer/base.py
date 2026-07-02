"""Common Finding shape + Coder protocol — the seam between detection and fixing.

Every source (the judge over traces, the inspect scanners/agent) normalizes to `Finding`,
so the fixer and the verification loop are source-agnostic. A `Coder` turns findings +
cross-file context into a patch; Codex is the default impl, but the protocol lets a
Claude-based patch agent swap in.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from codeindex import probe

AXES = ("security", "redundancy", "reliability", "simulation")


@dataclass
class Finding:
    axis: str                 # one of AXES
    title: str
    severity: str = "med"     # low | med | high
    detail: str = ""
    file: str | None = None
    line: int | None = None
    evidence: str = ""
    source: str = ""          # judge | semgrep | bandit | investigate | ...


def fingerprint(f: Finding) -> tuple[str, str | None, str]:
    """Identity of a finding across verification runs, so the loop gates convergence on
    the ORIGINAL findings instead of whatever a fresh (stochastic) judge run flags.
    Digits are collapsed so 'called 3x' and 'called 2x' are the same finding."""
    title = re.sub(r"\d+", "#", " ".join(f.title.lower().split()))[:80]
    return (f.axis, f.file, title)


def _axis_from_text(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ("redundant", "duplicate", "retry storm", "wasted", "inefficient")):
        return "redundancy"
    if any(w in t for w in ("vuln", "inject", "ssrf", "secret", "auth", "deserial", "sql", "xss", "traversal")):
        return "security"
    if any(w in t for w in ("fabricat", "mismatch", "failed", "dangling", "unhandled", "cleanup", "leak", "timeout")):
        return "reliability"
    return "reliability"


def from_judge(judge_result: dict, step_dicts: list[dict], index) -> list[Finding]:
    """Judge verdict (issues citing evidence_steps) -> Findings anchored to code via probe."""
    out: list[Finding] = []
    for iss in judge_result.get("issues", []):
        text = iss.get("issue", "")
        cand = probe.from_issue(index, iss, step_dicts) if step_dicts else {}
        sym = next((s for syms in cand.values() for s in syms), None)
        axis = "simulation" if judge_result.get("verdict") == "fail" and not cand else _axis_from_text(text)
        out.append(Finding(axis, text, iss.get("severity", "med"),
                           iss.get("recommendation", ""),
                           sym.file if sym else None, sym.line if sym else None,
                           source="judge"))
    return out


def summary(findings: list[Finding]) -> str:
    """Group findings by axis for a PR body / report (human-facing, terse)."""
    lines = []
    for axis in AXES:
        items = [f for f in findings if f.axis == axis]
        if not items:
            continue
        lines.append(f"### {axis} ({len(items)})")
        for f in items:
            loc = f" — `{f.file}:{f.line}`" if f.file else ""
            lines.append(f"- [{f.severity}] {f.title}{loc}")
    return "\n".join(lines) or "No findings."


def detail_summary(findings: list[Finding]) -> str:
    """Coder-facing summary: keeps the judge's recommendation (`detail`) and `evidence`,
    which `summary` drops. This is the highest-signal feedback the coder gets."""
    lines = []
    for f in findings:
        loc = f" — `{f.file}:{f.line}`" if f.file else ""
        lines.append(f"- [{f.severity}] {f.title}{loc}")
        if f.detail:
            lines.append(f"    fix: {f.detail}")
        if f.evidence:
            lines.append(f"    evidence: {f.evidence[:300]}")
    return "\n".join(lines) or "No findings."


class Coder(Protocol):
    """Produce a unified diff that addresses `findings`, grounded in `context`.
    `failures` carries the previous iteration's failing test/sim/scan output (empty on first)."""
    def propose(self, root: Path, findings: list[Finding], context: str, failures: str = "") -> str: ...


def _demo() -> None:
    import tempfile
    from codeindex import build
    d = Path(tempfile.mkdtemp())
    (d / "tools.py").write_text("class Hubspot:\n    def search(self, q): ...\n")
    idx = build(d)
    steps = [{"type": "tool_call", "tool": "hubspot.search", "id": "c1"},
             {"type": "tool_result", "id": "c1", "ok": True}]
    jr = {"verdict": "warn",
          "issues": [{"issue": "hubspot.search called 3x with identical args (redundant)",
                      "evidence_steps": [0], "severity": "low", "recommendation": "cache the result"}]}
    fs = from_judge(jr, steps, idx)
    assert fs[0].axis == "redundancy", fs
    assert fs[0].file == "tools.py", fs            # anchored to code via probe
    ds = detail_summary(fs)
    assert "fix: cache the result" in ds, ds       # recommendation survives to the coder
    assert "fix:" not in summary(fs)               # human summary still drops it
    same = Finding("redundancy", "hubspot.search called 2x with identical args (redundant)",
                   file="tools.py")
    assert fingerprint(fs[0]) == fingerprint(same)                   # counts differ, same finding
    assert fingerprint(fs[0]) != fingerprint(Finding("security", fs[0].title, file="tools.py"))
    s = summary(fs + [Finding("security", "hardcoded API key", "high", file="x.py", line=2)])
    assert "### security" in s and "### redundancy" in s, s
    print("ok")


if __name__ == "__main__":
    _demo()
