"""Slack twin: Web API is RPC, not CRUD.

Fidelity target — the real slack_sdk WebClient must not be able to tell this from
production:
  * chat.postMessage      POST /api/chat.postMessage      -> {ok, channel, ts, message}
  * conversations.history GET  /api/conversations.history -> {ok, messages, has_more}
Slack signals logical failures as HTTP 200 with {"ok": false, "error": <code>}
(NOT 4xx), so we mirror that instead of raising TwinError. `ts` is Slack's
epoch-with-microseconds message id; history is returned newest-first.
"""
import time

from twins.engine import Twin

_DEFAULT_LIMIT = 100  # Slack's default page size for conversations.history


def _err(code: str):
    return {"ok": False, "error": code}, 200


class SlackTwin(Twin):
    def create(self, resource, body):           # resource == "chat.postMessage"
        body = body or {}
        channel = body.get("channel")
        if not channel:
            return _err("channel_not_found")
        # Slack requires text unless blocks/attachments carry the content.
        if not body.get("text") and not body.get("blocks") and not body.get("attachments"):
            return _err("no_text")

        ts = f"{time.time():.6f}"
        # Stored record keeps `channel` so history can scope to it; the message object
        # Slack returns does not echo a top-level channel inside `message`.
        stored = {"type": "message", "text": body.get("text", ""), "ts": ts, "channel": channel}
        if body.get("username"):
            stored["username"] = body["username"]
        self._put("messages", ts, stored)
        msg = {k: v for k, v in stored.items() if k != "channel"}
        return {"ok": True, "channel": channel, "ts": ts, "message": msg}, 200

    def list(self, resource, params=None):       # resource == "conversations.history"
        params = params or {}
        channel = params.get("channel")
        if not channel:
            return _err("channel_not_found")

        try:
            limit = int(params.get("limit", _DEFAULT_LIMIT))
        except (TypeError, ValueError):
            return _err("invalid_limit")
        limit = max(1, min(limit, 1000))  # Slack clamps to [1, 1000]

        # Scope to the requested channel, newest-first (Slack orders by descending ts).
        scoped = sorted((m for m in self._all("messages") if m.get("channel") == channel),
                        key=lambda m: float(m["ts"]), reverse=True)
        page = [{k: v for k, v in m.items() if k != "channel"} for m in scoped[:limit]]
        # ponytail: no cursor pagination (next_cursor) — add if a scenario needs >1 page.
        return {"ok": True, "messages": page, "has_more": len(scoped) > limit}, 200


def _demo():
    import sqlite3
    t = SlackTwin(sqlite3.connect(":memory:"))

    # post -> read back, scoped to the same channel
    resp, st = t.create("chat.postMessage", {"channel": "C_SUPPORT", "text": "hello"})
    assert st == 200 and resp["ok"] and resp["message"]["text"] == "hello", resp
    assert "channel" not in resp["message"], resp                      # channel is top-level only
    hist, st = t.list("conversations.history", {"channel": "C_SUPPORT"})
    assert st == 200 and hist["ok"] and hist["messages"][0]["ts"] == resp["ts"], hist

    # channel scoping: a message posted to another channel is not returned
    t.create("chat.postMessage", {"channel": "C_OTHER", "text": "elsewhere"})
    only, _ = t.list("conversations.history", {"channel": "C_SUPPORT"})
    assert [m["text"] for m in only["messages"]] == ["hello"], only

    # newest-first + limit + has_more
    t.create("chat.postMessage", {"channel": "C_SUPPORT", "text": "second"})
    page, _ = t.list("conversations.history", {"channel": "C_SUPPORT", "limit": "1"})
    assert page["messages"][0]["text"] == "second" and page["has_more"] is True, page

    # Slack-style logical errors, all HTTP 200 with ok:false
    assert t.list("conversations.history", {})[0] == {"ok": False, "error": "channel_not_found"}
    assert t.create("chat.postMessage", {"channel": "C1"})[0]["error"] == "no_text"
    assert t.create("chat.postMessage", {"text": "hi"})[0]["error"] == "channel_not_found"
    print("ok")


if __name__ == "__main__":
    _demo()
