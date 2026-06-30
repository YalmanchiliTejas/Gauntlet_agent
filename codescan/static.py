"""Run security/reliability scanners and normalize their output to `Finding`.

Each tool is a (binary, argv, parser) triple. We run only the tools actually installed
(or whatever the caller injects), via an injectable `run(cmd) -> (rc, stdout)` so this works
locally now and over the microVM `/exec` later. Parsers are pure and unit-tested on sample JSON.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from fixer.base import Finding, _axis_from_text

_SEMGREP_SEV = {"ERROR": "high", "WARNING": "med", "INFO": "low"}
_BANDIT_SEV = {"HIGH": "high", "MEDIUM": "med", "LOW": "low"}


def _parse_semgrep(out: str) -> list[Finding]:
    data = json.loads(out or "{}")
    res = []
    for r in data.get("results", []):
        check = r.get("check_id", "semgrep")
        msg = (r.get("extra", {}) or {}).get("message", check)
        res.append(Finding(
            axis=_axis_from_text(check + " " + msg),
            title=check,
            severity=_SEMGREP_SEV.get((r.get("extra", {}) or {}).get("severity", "WARNING"), "med"),
            detail=msg, file=r.get("path"), line=(r.get("start", {}) or {}).get("line"),
            source="semgrep"))
    return res


def _parse_bandit(out: str) -> list[Finding]:
    data = json.loads(out or "{}")
    res = []
    for r in data.get("results", []):
        res.append(Finding(
            axis="security", title=r.get("test_id", "bandit"),
            severity=_BANDIT_SEV.get(r.get("issue_severity", "MEDIUM"), "med"),
            detail=r.get("issue_text", ""), file=r.get("filename"),
            line=r.get("line_number"), source="bandit"))
    return res


@dataclass(frozen=True)
class Tool:
    bin: str
    cmd: list[str]
    parse: Callable[[str], list[Finding]]


TOOLS = [
    Tool("semgrep", ["semgrep", "--config", "auto", "--json", "--quiet", "."], _parse_semgrep),
    Tool("bandit", ["bandit", "-r", ".", "-f", "json", "-q"], _parse_bandit),
    # ponytail: add gitleaks / pip-audit / npm audit as (bin, cmd, parser) triples when needed.
]


def _local_run(root: Path) -> Callable[[list[str]], tuple[int, str]]:
    def run(cmd):
        p = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
        return p.returncode, p.stdout
    return run


def scan(root, run: Callable | None = None, tools: list[Tool] | None = None) -> list[Finding]:
    """Run available scanners (or injected ones) and merge their findings."""
    run = run or _local_run(Path(root))
    if tools is None:
        tools = [t for t in TOOLS if shutil.which(t.bin)]
    findings: list[Finding] = []
    for t in tools:
        try:
            _, out = run(t.cmd)
            findings += t.parse(out)
        except Exception:
            continue  # a broken/absent tool must not sink the whole scan
    return findings


def _demo() -> None:
    semgrep_out = json.dumps({"results": [
        {"check_id": "python.lang.security.audit.dangerous-system-call",
         "path": "app.py", "start": {"line": 12},
         "extra": {"severity": "ERROR", "message": "possible command injection"}}]})
    bandit_out = json.dumps({"results": [
        {"test_id": "B105", "filename": "cfg.py", "line_number": 3,
         "issue_severity": "HIGH", "issue_text": "hardcoded password"}]})
    sf = _parse_semgrep(semgrep_out)
    assert sf[0].axis == "security" and sf[0].severity == "high" and sf[0].line == 12, sf
    bf = _parse_bandit(bandit_out)
    assert bf[0].severity == "high" and bf[0].file == "cfg.py", bf
    # orchestration with injected tool + stub run (no real binaries needed)
    fake = Tool("semgrep", ["semgrep"], _parse_semgrep)
    got = scan(".", run=lambda cmd: (0, semgrep_out), tools=[fake])
    assert len(got) == 1 and got[0].source == "semgrep", got
    print("ok")


if __name__ == "__main__":
    _demo()
