"""The agent trajectory + loader. One Step per trajectory entry.

A trace is the agent-under-test's own trajectory: reasoning, tool calls (name +
args), and tool results — NOT the network log. Schema is intentionally tolerant
(extra keys ignored) so it ingests whatever the harness emits, one JSON object
per line:

  {"type": "thought",     "text": "I should look up the contact first"}
  {"type": "tool_call",   "id": "c1", "tool": "hubspot.search", "args": {"q": "acme"}}
  {"type": "tool_result", "id": "c1", "ok": true, "output": "{...}"}
  {"type": "message",     "role": "assistant", "text": "Done."}
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Step:
    raw: dict  # the original entry; accessors below pull typed fields tolerantly

    @property
    def type(self) -> str:
        return self.raw.get("type", "")

    @property
    def tool(self) -> str | None:
        return self.raw.get("tool")

    @property
    def args(self) -> dict:
        return self.raw.get("args") or {}

    @property
    def call_id(self):
        return self.raw.get("id")

    @property
    def span_id(self):
        return self.raw.get("id")  # OTel span id; egress traceparent joins on this

    @property
    def ts(self) -> float:
        return float(self.raw.get("ts") or 0)

    @property
    def end(self) -> float:
        return float(self.raw.get("end") or self.raw.get("ts") or 0)

    @property
    def tool_type(self) -> str:
        return str(self.raw.get("tool_type") or "")

    @property
    def text(self) -> str:
        return self.raw.get("text") or ""

    @property
    def output(self) -> str:
        return str(self.raw.get("output") or "")

    @property
    def error(self) -> str:
        return str(self.raw.get("error") or "")

    @property
    def is_call(self) -> bool:
        return self.type == "tool_call"

    @property
    def failed(self) -> bool:
        """A result that errored. `ok: false`, or an `error` field, or no ok given but error text."""
        if self.type != "tool_result":
            return False
        if "ok" in self.raw:
            return not self.raw["ok"]
        return bool(self.error)

    @property
    def args_key(self) -> str:
        """Canonical (tool, args) identity for dedup — order-independent."""
        return json.dumps([self.tool, self.args], sort_keys=True)


def load(path: str | Path) -> list[Step]:
    """Read the trajectory JSONL. Missing/empty -> no steps (not an error)."""
    p = Path(path)
    if not p.is_file():
        return []
    return [Step(json.loads(line)) for line in p.read_text().splitlines() if line.strip()]
