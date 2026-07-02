"""Agent-as-judge over an agent's trajectory: find issues, tell the coding agent what to fix.

The trace is the agent-under-test's trajectory (reasoning, tool calls, tool results) —
not the network log. It can be huge, so it's a *queryable object*, not a prompt blob.
A coordinator agent investigates it, pulling only the steps it needs:

  ingest.from_spans -> OTel/OpenInference spans -> trajectory (any instrumented harness)
  trace.load()      -> [Step] from the trajectory JSONL the harness emits
  analyze()         -> pure, deterministic candidate findings (seed for the agent)
  verify()          -> cross-check claims vs egress ground truth (fabricated actions)
  querytrace.*      -> search / get / window / stats + recurse (RLM-style sub-calls
                       on step ranges, for trajectories past the context window)
  agent.judge()     -> tool-using loop: investigate, verify steps, emit verdict +
                       issues with recommendations for the coding agent
"""

from .agent import judge  # noqa: F401  (public entry)
