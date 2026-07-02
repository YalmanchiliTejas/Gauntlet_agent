"""Verification layer: cross-check trajectory claims against egress ground truth.

The trajectory is self-reported — the agent can claim a tool succeeded when nothing
happened, or report success while the call 403'd. The egress log (proxy/addon.py) is
what really left the box. The hard part is linking a tool call to the egress it caused;
we do it by EVIDENCE, strongest first, so we don't guess from tool names:

  1. traceparent join  — egress carries the W3C span id of the tool that made it.
  2. temporal window    — egress ts falls within a tool span's [ts, end].
  3. name/explicit map  — last-resort, only to classify a tool as external.

Pure and deterministic; the judge agent reasons over the findings via the verify tool.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .analyze import Finding
from .trace import Step

_EXTERNAL_TYPES = {"extension", "external", "external_api", "http", "api"}


def load_egress(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.is_file():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def _span_of(traceparent) -> str | None:
    # W3C: "00-<trace-id>-<span-id>-<flags>"
    parts = (traceparent or "").split("-")
    return parts[2] if len(parts) >= 3 else None


def _attribute(calls: list[tuple[int, Step]], egress: list[dict]) -> dict[int, list[dict]]:
    """egress event -> owning tool_call index, by span-id join then time window."""
    by_span = {s.span_id: i for i, s in calls if s.span_id}
    owners: dict[int, list[dict]] = {}
    for e in egress:
        owner = by_span.get(_span_of(e.get("traceparent")))
        if owner is None:
            ts = float(e.get("ts") or 0)
            owner = next((i for i, s in calls if s.ts and s.ts <= ts <= (s.end or s.ts)), None)
        if owner is not None:
            owners.setdefault(owner, []).append(e)
    return owners


def _is_external(s: Step, services: set[str], tool_service: dict | None) -> bool:
    if s.tool_type.lower() in _EXTERNAL_TYPES:
        return True
    if tool_service and s.tool in tool_service:
        return True
    toks = set(re.split(r"[^a-z0-9]+", (s.tool or "").lower()))
    return any(svc.lower() in toks for svc in services)


def _failed_egress(e: dict) -> bool:
    return e.get("mode") == "deny" or (e.get("status") or 0) >= 400


def verify(steps: list[Step], egress: list[dict], services: set[str] | None = None,
           tool_service: dict | None = None) -> list[Finding]:
    services = services or set()
    calls = [(i, s) for i, s in enumerate(steps) if s.is_call]
    results = {s.call_id: s for s in steps if s.type == "tool_result"}
    owners = _attribute(calls, egress)
    findings: list[Finding] = []

    for i, s in calls:
        res = results.get(s.call_id)
        if res is None or res.failed:
            continue  # only claims of SUCCESS can be contradicted by the egress
        hits = owners.get(i, [])
        if hits and all(_failed_egress(e) for e in hits):
            findings.append(Finding(
                "result_mismatch",
                f"{s.tool} reported success but its egress call(s) failed/were denied "
                f"({', '.join(str(e.get('status') or e.get('mode')) for e in hits)})",
                count=len(hits), steps=[i]))
        elif not hits and _is_external(s, services, tool_service):
            findings.append(Finding(
                "fabricated_action",
                f"{s.tool} reported success but NO egress is attributable to it — "
                f"the external action likely never happened",
                steps=[i]))

    # Egress failures that belong to no tool call: something failed the agent isn't tracking.
    attributed = {id(e) for es in owners.values() for e in es}
    orphan_fail = [e for e in egress if _failed_egress(e) and id(e) not in attributed]
    if orphan_fail:
        findings.append(Finding(
            "untracked_failure",
            f"{len(orphan_fail)} egress call(s) failed/denied with no owning tool call "
            f"(services: {sorted({e.get('service') for e in orphan_fail})})",
            count=len(orphan_fail)))

    return findings


def _demo() -> None:
    from .trace import Step as S
    steps = [
        # exact join: email.send span "aaa", reports ok, but its egress 403'd -> mismatch
        S({"type": "tool_call", "id": "aaa", "tool": "email.send", "ts": 10, "end": 11,
           "tool_type": "extension", "args": {"to": "x"}}),
        S({"type": "tool_result", "id": "aaa", "ok": True, "output": "sent"}),
        # external tool reports ok, no egress at all -> fabricated
        S({"type": "tool_call", "id": "bbb", "tool": "stripe.refund", "ts": 20, "end": 21,
           "tool_type": "extension", "args": {"id": "ch_1"}}),
        S({"type": "tool_result", "id": "bbb", "ok": True, "output": "refunded"}),
    ]
    egress = [
        {"ts": 10.5, "service": "gmail", "status": 403, "mode": "twin",
         "traceparent": "00-trace-aaa-01"},                       # joins to span aaa, failed
        {"ts": 99, "service": "slack", "status": 500, "mode": "twin"},  # orphan failure
    ]
    fs = verify(steps, egress, services={"gmail", "stripe", "slack"})
    kinds = {f.kind for f in fs}
    assert "result_mismatch" in kinds, fs
    assert "fabricated_action" in kinds, fs
    assert "untracked_failure" in kinds, fs
    mm = next(f for f in fs if f.kind == "result_mismatch")
    assert mm.steps == [0], mm   # joined by traceparent, not by name
    # temporal fallback: same data, no traceparent -> still attributes by [ts,end]
    egress[0].pop("traceparent")
    assert any(f.kind == "result_mismatch" for f in verify(steps, egress, services={"gmail", "stripe", "slack"}))
    print("ok")


if __name__ == "__main__":
    _demo()
