"""Harness-agnostic trajectory capture: OpenTelemetry spans -> our Step JSONL.

The portable way to get an agent's trajectory out of ANY harness is OpenTelemetry.
Both live conventions are OTel spans, differing only in attribute names:
  - OTel GenAI semconv  (gen_ai.*, operation "execute_tool")
  - OpenInference       (openinference.span.kind = TOOL/LLM/AGENT, tool.*, input/output.value)
Framework instrumentors (LangChain, LlamaIndex, OpenAI/Anthropic SDK, CrewAI, MCP, ...)
emit one of these; a custom harness either auto-instruments or writes our JSONL directly.

Point an OTLP file exporter at the run, then:  python -m judge.ingest spans.json > trajectory.jsonl

A TOOL/execute_tool span folds call+result into one span, so it becomes TWO steps
(tool_call + tool_result) linked by the span id. LLM/agent spans become a message
step so the judge keeps the reasoning.
"""
from __future__ import annotations

import json
import sys


def _attrs(span: dict) -> dict:
    """Flatten attributes whether they're a plain dict or OTLP's [{key,value:{...}}] list."""
    a = span.get("attributes", {})
    if isinstance(a, dict):
        return a
    out = {}
    for item in a:  # OTLP form
        v = item.get("value", {})
        out[item.get("key")] = next(iter(v.values()), None) if isinstance(v, dict) else v
    return out


def _spans(doc) -> list[dict]:
    """Accept a bare list, {"spans": [...]}, or OTLP {"resourceSpans":[{"scopeSpans":[{"spans"}]}]}."""
    if isinstance(doc, list):
        return doc
    if "spans" in doc:
        return doc["spans"]
    out = []
    for rs in doc.get("resourceSpans", []):
        for ss in rs.get("scopeSpans", rs.get("instrumentationLibrarySpans", [])):
            out.extend(ss.get("spans", []))
    return out


def _is_tool(kind: str, op: str) -> bool:
    return kind.upper() == "TOOL" or op == "execute_tool"


def _is_llm(kind: str, op: str) -> bool:
    return kind.upper() in ("LLM", "AGENT", "CHAIN") or op in ("chat", "text_completion", "generate_content")


def _maybe_json(v):
    if isinstance(v, (dict, list)):
        return v
    if isinstance(v, str):
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


def _failed(span: dict) -> bool:
    status = span.get("status", {})
    code = status.get("code") if isinstance(status, dict) else status
    return str(code).upper() in ("ERROR", "STATUS_CODE_ERROR", "2")


def _sec(v) -> float:
    """Normalize a timestamp to epoch seconds (OTel uses unix nanoseconds)."""
    v = float(v or 0)
    return v / 1e9 if v > 1e12 else v


def _start(span: dict):
    return span.get("startTimeUnixNano") or span.get("start_time") or span.get("startTime") or 0


def _end(span: dict):
    return span.get("endTimeUnixNano") or span.get("end_time") or span.get("endTime") or _start(span)


def from_egress(events: list[dict]) -> list[dict]:
    """Fallback trajectory for an UNINSTRUMENTED agent: synthesize tool_call/result steps
    from the proxy's egress log. The network calls the agent made are its external actions,
    so redundancy / failure / denied-egress detection still works without any OTel spans.
    (No reasoning/thoughts — those only exist with real instrumentation.)"""
    steps: list[dict] = []
    for i, e in enumerate(events):
        cid = f"e{i}"
        ts = e.get("ts", 0)
        steps.append({"type": "tool_call", "id": cid, "ts": ts,
                      "tool": e.get("service") or "http",
                      "args": {"method": e.get("method"), "url": e.get("url")}})
        status = e.get("status")
        denied = e.get("mode") == "deny" or status == 403
        ok = status is not None and status < 400 and not denied
        res = {"type": "tool_result", "id": cid, "ts": ts, "ok": ok}
        res["output" if ok else "error"] = (f"HTTP {status}" + (" (egress denied)" if denied else ""))
        steps.append(res)
    return steps


def from_otlp_docs(docs: list) -> list[dict]:
    """Merge many OTLP export docs (one per agent POST to /v1/traces) into a trajectory."""
    merged = {"resourceSpans": []}
    for d in docs:
        if isinstance(d, dict) and "resourceSpans" in d:
            merged["resourceSpans"].extend(d["resourceSpans"])
        else:  # {"spans":[...]} or a bare list
            merged["resourceSpans"].append({"scopeSpans": [{"spans": _spans(d)}]})
    return from_spans(merged)


def from_spans(doc) -> list[dict]:
    """OTel/OpenInference spans -> ordered list of trajectory step dicts."""
    steps: list[dict] = []
    for sp in sorted(_spans(doc), key=_start):
        a = _attrs(sp)
        kind = str(a.get("openinference.span.kind", ""))
        op = str(a.get("gen_ai.operation.name", ""))
        sid = sp.get("spanId") or sp.get("span_id") or sp.get("context", {}).get("span_id") or sp.get("name")
        ts, end = _sec(_start(sp)), _sec(_end(sp))
        if _is_tool(kind, op):
            tool = a.get("gen_ai.tool.name") or a.get("tool.name") or sp.get("name")
            args = _maybe_json(a.get("gen_ai.tool.call.arguments") or a.get("tool.parameters") or a.get("input.value") or {})
            out = a.get("gen_ai.tool.call.result") or a.get("tool.result") or a.get("output.value") or ""
            # gen_ai.tool.type marks tools that call external APIs -> lets the verifier know
            # which calls SHOULD egress, instead of guessing from the name.
            ttype = a.get("gen_ai.tool.type") or a.get("tool.type")
            steps.append({"type": "tool_call", "id": sid, "tool": tool, "ts": ts, "end": end,
                          **({"tool_type": ttype} if ttype else {}),
                          "args": args if isinstance(args, dict) else {"input": args}})
            steps.append({"type": "tool_result", "id": sid, "ts": ts, "end": end, "ok": not _failed(sp),
                          **({"error": str(out)} if _failed(sp) else {"output": str(out)})})
        elif _is_llm(kind, op):
            text = a.get("output.value") or a.get("gen_ai.completion") or a.get("llm.output_messages") or ""
            steps.append({"type": "message", "role": "assistant", "text": str(text)[:4000]})
    return steps


def _demo() -> None:
    doc = {"spans": [
        {"name": "agent", "spanId": "s0", "start_time": 1,
         "attributes": {"openinference.span.kind": "LLM", "output.value": "I'll search hubspot"}},
        {"name": "hubspot.search", "spanId": "s1", "start_time": 2,
         "attributes": {"openinference.span.kind": "TOOL", "tool.name": "hubspot.search",
                        "tool.parameters": '{"q": "acme"}', "output.value": "{}"}},
        # OTel GenAI style, errored tool
        {"name": "send", "spanId": "s2", "startTimeUnixNano": 3, "status": {"code": "ERROR"},
         "attributes": [{"key": "gen_ai.operation.name", "value": {"stringValue": "execute_tool"}},
                        {"key": "gen_ai.tool.name", "value": {"stringValue": "email.send"}},
                        {"key": "gen_ai.tool.call.arguments", "value": {"stringValue": "{\"to\":\"x\"}"}},
                        {"key": "gen_ai.tool.call.result", "value": {"stringValue": "401"}}]},
    ]}
    steps = from_spans(doc)
    types = [s["type"] for s in steps]
    assert types == ["message", "tool_call", "tool_result", "tool_call", "tool_result"], types
    assert steps[1]["tool"] == "hubspot.search" and steps[1]["args"] == {"q": "acme"}, steps[1]
    assert steps[4]["ok"] is False and steps[4]["error"] == "401", steps[4]
    # multiple export docs merge into one trajectory
    merged = from_otlp_docs([doc, {"resourceSpans": []}])
    assert [s["type"] for s in merged] == [s["type"] for s in steps], merged
    # egress fallback: uninstrumented agent -> trajectory from the proxy log
    eg = from_egress([
        {"ts": 1, "service": "hubspot", "method": "GET", "url": "https://api.hubapi.com/x", "status": 200},
        {"ts": 2, "service": "twilio", "method": "POST", "url": "https://api.twilio.com/y", "status": 403, "mode": "deny"},
    ])
    assert [s["type"] for s in eg] == ["tool_call", "tool_result", "tool_call", "tool_result"], eg
    assert eg[1]["ok"] is True and eg[3]["ok"] is False and "denied" in eg[3]["error"], eg
    print("ok")


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] != "_demo":
        doc = json.loads(open(sys.argv[1]).read())
        for step in from_spans(doc):
            print(json.dumps(step))
    else:
        _demo()
