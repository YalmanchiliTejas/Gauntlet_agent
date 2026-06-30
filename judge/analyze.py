"""Deterministic pass over the agent trajectory: count what an LLM shouldn't.

Redundant tool calls, failed calls, retry loops, dangling calls — these are exact
properties of the trajectory. Compute them here for free; the judge agent reasons
over the result to tell the coding agent what to optimize.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .trace import Step


@dataclass
class Finding:
    kind: str          # redundant_call | failed_call | retry_loop | dangling_call
    detail: str
    count: int = 1
    steps: list[int] = field(default_factory=list)   # trajectory indices as evidence


def analyze(steps: list[Step]) -> list[Finding]:
    findings: list[Finding] = []
    calls = [(i, s) for i, s in enumerate(steps) if s.is_call]

    # Redundant tool calls: same tool + identical args invoked more than once.
    by_key: dict[str, list[int]] = {}
    for i, s in calls:
        by_key.setdefault(s.args_key, []).append(i)
    for key, idxs in by_key.items():
        if len(idxs) > 1:
            tool = steps[idxs[0]].tool
            findings.append(Finding(
                "redundant_call",
                f"{tool} called {len(idxs)}x with identical args — cache or reuse the result",
                count=len(idxs), steps=idxs))

    # Failed calls: a result that errored. Attribute back to its call when id matches.
    result_idx = {s.call_id: i for i, s in enumerate(steps) if s.type == "tool_result"}
    for i, s in enumerate(steps):
        if s.failed:
            findings.append(Finding(
                "failed_call",
                f"tool result errored: {(s.error or s.output)[:200]}",
                steps=[i]))

    # Retry loop: the same tool failing repeatedly (blind retries).
    failed_tools = Counter()
    for i, s in enumerate(steps):
        if s.failed:
            # find the tool name from the matching call id, else nearest preceding call
            call = next((c for ci, c in reversed(calls) if c.call_id == s.call_id or ci < i), None)
            if call:
                failed_tools[call.tool] += 1
    for tool, n in failed_tools.items():
        if n >= 3:
            findings.append(Finding("retry_loop", f"{tool} failed {n}x — likely a blind retry loop", count=n))

    # Dangling call: a tool_call with no matching result (agent hung / lost the turn).
    for i, s in calls:
        if s.call_id is not None and s.call_id not in result_idx:
            findings.append(Finding("dangling_call", f"{s.tool} call has no result (id={s.call_id})", steps=[i]))

    return findings


def summary(steps: list[Step], findings: list[Finding]) -> dict:
    return {
        "total_steps": len(steps),
        "tool_calls": sum(1 for s in steps if s.is_call),
        "failed_calls": sum(1 for s in steps if s.failed),
        "redundant_calls": sum(f.count - 1 for f in findings if f.kind == "redundant_call"),
        "findings": [vars(f) for f in findings],
    }


def _demo() -> None:
    from .trace import Step as S
    steps = [
        S({"type": "thought", "text": "look up acme"}),
        S({"type": "tool_call", "id": "c1", "tool": "hubspot.search", "args": {"q": "acme"}}),
        S({"type": "tool_result", "id": "c1", "ok": True, "output": "{}"}),
        S({"type": "tool_call", "id": "c2", "tool": "hubspot.search", "args": {"q": "acme"}}),  # redundant
        S({"type": "tool_result", "id": "c2", "ok": True, "output": "{}"}),
        S({"type": "tool_call", "id": "c3", "tool": "email.send", "args": {"to": "x"}}),
        S({"type": "tool_result", "id": "c3", "ok": False, "error": "401"}),                    # failed
        S({"type": "tool_call", "id": "c4", "tool": "email.send", "args": {"to": "y"}}),         # dangling (no result)
    ]
    kinds = Counter(f.kind for f in analyze(steps))
    assert kinds["redundant_call"] == 1, kinds
    assert kinds["failed_call"] == 1, kinds
    assert kinds["dangling_call"] == 1, kinds
    assert summary(steps, analyze(steps))["redundant_calls"] == 1
    print("ok")


if __name__ == "__main__":
    _demo()
