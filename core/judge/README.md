# judge — agent-as-judge over agent trajectories

Reads the **agent-under-test's trajectory** — its reasoning, tool calls (name +
args), and tool results — flags what to optimize (redundant calls, failures, retry
loops, dangling calls, inefficiency, correctness/security issues), and reports
recommendations the **coding agent** can act on, each citing the steps that prove it.

Design follows agent-as-judge (Judgment Labs): a long-horizon trajectory is turned
into a **queryable object** and a coordinator agent investigates it, instead of
stuffing the whole trace into one LLM-as-judge prompt (which truncates away the
evidence that matters).

## The trace = the agent trajectory
Not the network log. One JSON object per line (schema is tolerant — extra keys ok):
```
{"type": "thought",     "text": "look up the contact first"}
{"type": "tool_call",   "id": "c1", "tool": "hubspot.search", "args": {"q": "acme"}}
{"type": "tool_result", "id": "c1", "ok": true, "output": "{...}"}
{"type": "message",     "role": "assistant", "text": "done"}
```
### Capturing it from any harness — OpenTelemetry
The portable, harness-agnostic source is OpenTelemetry. Both live conventions are OTel
spans: **OTel GenAI semconv** (`gen_ai.*`, operation `execute_tool`) and **OpenInference**
(`openinference.span.kind` = TOOL/LLM/AGENT). Framework instrumentors (LangChain,
LlamaIndex, OpenAI/Anthropic SDK, CrewAI, MCP, …) emit one of these; a custom harness
either auto-instruments or emits a few manual spans. Point an OTLP file exporter at the
run, then:
```
python -m judge.ingest spans.json > trajectory.jsonl   # ingest.from_spans handles both specs
```
A custom harness with no instrumentation can also just write the JSONL above directly.
The judge only consumes the trajectory — it does not produce it.

## Pipeline
```
ingest.py      OTel/OpenInference spans -> trajectory JSONL (any instrumented harness)
trace.py       parse trajectory JSONL -> [Step]
analyze.py     PURE rules -> candidate Findings (no LLM): redundant calls, failed
               calls, retry loops, dangling calls. Exact counts, computed for free.
verify.py      cross-check claims vs egress ground truth -> result_mismatch /
               fabricated_action / untracked_failure. The agent self-reports; the
               egress log is what really left the box.
querytrace.py  the trajectory as a queryable object: search / get / window / stats.
               Lists stay compact; full args/output pulled only via get(index).
agent.py       the COORDINATOR: a ReAct JSON tool-loop. Seeds with stats() + verify(),
               searches + pulls the steps behind each suspicion, finishes with a
               verdict whose issues carry a recommendation + evidence_steps.
```

### Verification (the egress ground truth)
`proxy/addon.py` writes every egress attempt (any mode, incl. denied 403s) to
`EGRESS_LOG`, including the request's `traceparent`; `sandbox/orchestrator.py` exposes
it as `sandbox.egress_log`. `verify()` links each egress call to the tool that caused it
by **evidence, not name** — strongest first:

1. **traceparent join** — OTel-instrumented HTTP clients inject the W3C `traceparent`,
   which carries the *span id of the tool call*. We join egress→tool exactly; the
   service is read off the egress, no guessing.
2. **temporal window** — no propagation? attribute egress whose `ts` falls in a tool
   span's `[ts, end]`.
3. **`gen_ai.tool.type`** (from the span) tells us a tool calls external APIs, so we
   know which calls *should* egress without a name map.

Findings:
- **result_mismatch** — tool reported success but its egress call(s) failed/were denied.
- **fabricated_action** — an external tool reported success but no egress is attributable
  to it; the action never happened.
- **untracked_failure** — egress failed with no owning tool call (the agent isn't tracking it).

Pass `egress_log=` and `services=` to `judge()`. ponytail: name-token / `tool_service=`
is now only a *last-resort* classifier for whether a tool is external, used when neither
`gen_ai.tool.type` nor a span/time link is available — not the correlation mechanism.
Why split: counting duplicates/failures with an LLM is slow, costly, and
non-reproducible — rules do it exactly. The agent does only what rules can't:
investigate, judge severity, and say what to change.

## Long trajectories (thousands of steps) — recursion
1. **Deterministic first.** `analyze()` collapses the whole trajectory into exact
   findings with no LLM and no context limit. Most signal never needs a model.
2. **`recurse(start, end, question)`** (RLM-style, after Recursive Language Models).
   When a step *range* is too big to read inline, the coordinator hands it to a
   sub-judge over only that slice; if the slice is still too big, `recurse` halves
   it and combines — divide-and-conquer past the context window. The coordinator
   drives the decomposition; we don't hard-code partitions. ponytail: even halving
   + depth cap 2; let the model pick splits / deepen the cap when real traces need it.

## Use
```python
from judge import judge
result = judge("trajectory.jsonl",
               egress_log=sandbox.egress_log, services={"gmail", "hubspot"})
# {"verdict": "pass|warn|fail",
#  "issues": [{"issue","evidence_steps","severity","recommendation"}], "steps": N}
```
LLM creds reuse the planner's env (`GEMINI_API_KEY` / `OPENAI_API_KEY` / …).
Self-checks (scripted, no network): `python -m judge.{analyze,ingest,querytrace,verify,agent}`.

## Skipped (add when needed)
- **Worker / fork sub-agents** (split search across a huge trajectory, compare across
  prior runs): the article's full multi-agent layer. One trajectory fits one
  coordinator today; add when the `steps` budget runs out on real traces.
- **Feeding recommendations back to the coding agent** (PR comment / patch): `judge`
  returns structured issues; wire into the run report when that loop exists.
