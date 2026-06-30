"""The trajectory as a queryable object — the heart of agent-as-judge.

A long run can be thousands of steps. Instead of stuffing them into the judge's
context (truncation loses the smoking gun), we expose tools so the judge pulls
only the steps it needs: list-with-filters cheaply, then fetch full args/output
for the few that matter. Each tool returns compact text the model reads back.
"""
from __future__ import annotations

import json

from .analyze import analyze, summary
from .redact import redact, redact_str
from .trace import Step


def _one_line(i: int, s: Step) -> str:
    if s.type == "tool_call":
        return f"[{i}] call {s.tool}({json.dumps(redact(s.args))[:120]})"
    if s.type == "tool_result":
        tag = "ERR" if s.failed else "ok"
        return f"[{i}] result {tag}: {redact_str(s.error or s.output)[:120]}"
    return f"[{i}] {s.type}: {redact_str(s.text)[:120]}"


def search(steps, type=None, tool=None, failed=None, contains=None, limit=50) -> str:
    """List matching steps, one line each (truncated). Filters AND together.
    `failed=True` -> only errored results; `tool` matches tool_call/tool_result name."""
    hits = []
    for i, s in enumerate(steps):
        if type and s.type != type:
            continue
        if tool and s.tool != tool:
            continue
        if failed is not None and s.failed != failed:
            continue
        if contains and contains not in (s.text + s.output + s.error + json.dumps(s.args)):
            continue
        hits.append(_one_line(i, s))
    head = f"{len(hits)} match(es)" + (f", showing first {limit}" if len(hits) > limit else "")
    return head + "\n" + "\n".join(hits[:limit])


def get(steps, index: int) -> str:
    """Full step incl. args / output / error — the selective evidence pull (secrets masked)."""
    if not 0 <= index < len(steps):
        return f"error: index {index} out of range (0..{len(steps)-1})"
    return json.dumps(redact(steps[index].raw), indent=2)


def window(steps, index: int, n: int = 3) -> str:
    """The n steps before/after index — local context around a step."""
    lo, hi = max(0, index - n), min(len(steps), index + n + 1)
    return "\n".join(_one_line(i, steps[i]) for i in range(lo, hi))


def listing(steps, start: int, end: int, limit: int = 200) -> str:
    """Global-indexed one-liners for a step range — the compact view a sub-call reasons over.
    Failed results carry their error inline; that's where root cause usually is."""
    lo, hi = max(0, start), min(len(steps), end + 1)
    lines = [_one_line(i, steps[i]) for i in range(lo, hi)]
    head = f"steps {lo}..{hi-1} ({hi-lo} total)" + (f", showing first {limit}" if hi - lo > limit else "")
    return head + "\n" + "\n".join(lines[:limit])


def stats(steps) -> str:
    """Run summary + the deterministic findings, as the agent's starting point."""
    return json.dumps(summary(steps, analyze(steps)), indent=2)


_RECURSE_PROMPT = """You are a sub-judge inspecting ONE slice of a larger agent trajectory.
Read only the steps below and answer the parent's question concisely. Cite step
indices (they are global). If nothing in this slice is notable, say so.

Question: {question}

{listing}"""


def recurse(steps, sender, start: int, end: int, question: str, _depth: int = 0, _max_depth: int = 2) -> str:
    """RLM-style recursive self-call: judge a step range as its own environment.

    If the slice is still too big to show inline, split in half and recurse, then
    combine — so a trajectory far past the context window is handled divide-and-conquer.
    """
    lo, hi = max(0, start), min(len(steps), end + 1)
    if hi - lo > 200 and _depth < _max_depth:
        mid = (lo + hi) // 2  # ponytail: even halving; let the model choose splits if it matters
        left = recurse(steps, sender, lo, mid - 1, question, _depth + 1, _max_depth)
        right = recurse(steps, sender, mid, hi - 1, question, _depth + 1, _max_depth)
        return f"[steps {lo}..{mid-1}] {left}\n[steps {mid}..{hi-1}] {right}"
    return sender(_RECURSE_PROMPT.format(question=question, listing=listing(steps, lo, hi - 1)))


# name -> callable(steps, **args) -> str. `recurse` needs the sender, so agent.py routes it.
TOOLS = {"search": search, "get": get, "window": window, "stats": stats}

TOOL_DOCS = """\
- stats(): run summary + deterministic candidate findings. Call this first.
- search(type?, tool?, failed?, contains?, limit?): list matching steps, truncated.
    type is thought/message/tool_call/tool_result; failed=true -> only errored results.
- get(index): full step for one entry, including args / output / error.
- window(index, n?): the n steps before and after a step (local context).
- recurse(start, end, question): when a step RANGE is too large to read inline, hand it to
    a sub-judge that reads only that slice and answers your question. Use it to divide a long
    trajectory into regions and conquer each; fold the answers into your verdict."""


def dispatch(steps, name: str, args: dict) -> str:
    fn = TOOLS.get(name)
    if fn is None:
        return f"error: unknown tool {name!r}. Available: {', '.join(TOOLS)}"
    try:
        return fn(steps, **(args or {}))
    except TypeError as e:
        return f"error: bad args for {name}: {e}"


def _demo() -> None:
    from .trace import Step as S
    steps = [
        S({"type": "tool_call", "id": "c1", "tool": "hubspot.search", "args": {"q": "acme"}}),
        S({"type": "tool_result", "id": "c1", "ok": False, "error": "boom"}),
        S({"type": "message", "role": "assistant", "text": "done"}),
    ]
    assert "1 match" in search(steps, failed=True)
    assert "2 match" in search(steps, tool="hubspot.search") or "1 match" in search(steps, tool="hubspot.search")
    assert '"error": "boom"' in get(steps, 1)
    assert "out of range" in get(steps, 9)
    assert "[0]" in window(steps, 1, 1) and "[2]" in window(steps, 1, 1)
    assert "boom" in dispatch(steps, "get", {"index": 1})
    assert "unknown tool" in dispatch(steps, "nope", {})
    seen = {}

    def sub(p):
        seen["p"] = p
        return "step 1 failed"

    out = recurse(steps, sub, 0, 2, "any failures?")
    assert out == "step 1 failed" and "steps 0..2" in seen["p"], (out, seen)
    print("ok")


if __name__ == "__main__":
    _demo()
