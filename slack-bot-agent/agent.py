"""A task-driven Slack agent — with planted inefficiencies for the judge/fixer to catch.

Reads its task from GAUNTLET_TASK_PROMPT (the workflow Gauntlet injects) and works it over
two Slack tools: read_history and post_message.

Two paths:
  * OPENAI_API_KEY set  -> a clean, grounded ReAct loop (the "good" agent).
  * no key (the default) -> a deliberately inefficient scripted run so the judge fires and
    the fixer loop has real code to repair. Planted smells:
        - reads the same history 3x                 -> redundant_call
        - reads a second channel it never uses      -> dangling / dead retrieval
        - reply ignores the fetched question         -> no grounding (off-topic answer)
        - blind-retries the post 3x                  -> retry_loop / redundant_call

All Slack calls hit the real host, so the sandbox egress proxy routes them to the `slack`
twin. The token is fake — the twin answers. Trajectory is native JSONL (judge/trace.py).
"""
from __future__ import annotations

import json
import os
import time

import requests

SLACK = "https://slack.com/api"
TOKEN = os.environ.get("SLACK_TOKEN", "xoxb-fake-for-twin")
CHANNEL = os.environ.get("SLACK_CHANNEL", "C_SUPPORT")
TASK = os.environ.get("GAUNTLET_TASK_PROMPT",
                      "Read the channel, then post a concise reply to the latest question.")
TRAJECTORY = os.environ.get("GAUNTLET_TRAJECTORY", "/gauntlet_trajectory.jsonl")
MAX_STEPS = 6

_traj = open(TRAJECTORY, "w")
_seq = 0


def _emit(obj: dict) -> None:
    _traj.write(json.dumps(obj) + "\n")
    _traj.flush()


def thought(text: str) -> None:
    _emit({"type": "thought", "text": text})


# --- Slack tools -----------------------------------------------------------------

def _slack(method: str, http: str, **args) -> dict:
    global _seq
    _seq += 1
    cid = f"c{_seq}"
    _emit({"type": "tool_call", "id": cid, "tool": f"slack.{method}", "args": args,
           "ts": time.time()})
    url = f"{SLACK}/{method}"
    if http == "GET":
        r = requests.get(url, params={"token": TOKEN, **args}, timeout=15)
    else:
        r = requests.post(url, data={"token": TOKEN, **args}, timeout=15)
    body = r.json() if r.content else {}
    _emit({"type": "tool_result", "id": cid, "ok": bool(body.get("ok")),
           "output": json.dumps(body)[:500], "end": time.time()})
    return body


def read_history(channel: str = CHANNEL, **_) -> list[str]:
    body = _slack("conversations.history", "GET", channel=channel, limit="20")
    return [m.get("text", "") for m in body.get("messages", [])]


def post_message(channel: str = CHANNEL, text: str = "") -> dict:
    return _slack("chat.postMessage", "POST", channel=channel, text=text, username="agent")


# --- The good path: grounded ReAct loop (only when a model is available) ----------

def _plan(task: str, observations: list[dict]) -> dict:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return {"tool": "finish", "args": {}}
    sys = ("You are a Slack agent. Tools: read_history(channel), post_message(channel, text), "
           "finish(). Reply with ONE JSON action {\"tool\":...,\"args\":{...}}. Ground every "
           "post_message in what read_history returned. Finish when done.")
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": "gpt-4o-mini", "response_format": {"type": "json_object"},
              "messages": [{"role": "system", "content": sys},
                           {"role": "user", "content": f"Task: {task}\nObservations: "
                                                        f"{json.dumps(observations)[:2000]}"}]},
        timeout=30)
    action = json.loads(r.json()["choices"][0]["message"]["content"])
    thought(f"LLM chose: {json.dumps(action)[:160]}")
    return action


def _run_grounded(task: str) -> str:
    observations: list[dict] = []
    for _ in range(MAX_STEPS):
        action = _plan(task, observations)
        tool, args = action.get("tool"), action.get("args", {})
        if tool == "finish":
            break
        if tool == "read_history":
            observations.append({"messages": read_history(**args)})
        elif tool == "post_message":
            post_message(**args)
            observations.append({"posted": True})
        else:
            break
    return "Posted a grounded reply." if any(o.get("posted") for o in observations) else "Nothing posted."


# --- The default path: deliberately inefficient scripted run ----------------------

def _run_inefficient(task: str) -> str:
    # SMELL (redundant_call): fetch the same history three times instead of once.
    messages: list[str] = []
    for _ in range(3):
        messages = read_history(CHANNEL)

    # SMELL (dead retrieval): pull another channel and never use it.
    read_history("C_RANDOM")

    question = next((m for m in reversed(messages) if m), "")
    thought(f"Latest message: {question!r}")

    # SMELL (no grounding): reply ignores `question` and `task` entirely.
    reply = "Our refund policy allows returns within 30 days. Let me know if that helps!"

    # SMELL (retry_loop): blind 3x re-post, no success check between attempts.
    for _ in range(3):
        post_message(CHANNEL, reply)
    return "Posted a canned reply (ungrounded)."


def main() -> None:
    thought(f"Task: {TASK}")
    summary = _run_grounded(TASK) if os.environ.get("OPENAI_API_KEY") else _run_inefficient(TASK)
    _emit({"type": "message", "role": "assistant", "text": summary})
    _traj.close()
    print(summary)


if __name__ == "__main__":
    main()
