"""Slack twin: Web API is RPC, not CRUD. chat.postMessage returns
{ok, channel, ts, message} at HTTP 200; conversations.history returns stored
messages. ts is Slack's epoch-with-microseconds id.
"""
import time

from twins.engine import Twin


class SlackTwin(Twin):
    def create(self, resource, body):           # resource == "chat.postMessage"
        ts = f"{time.time():.6f}"
        msg = {"type": "message", "text": body.get("text", ""),
               "ts": ts, "channel": body.get("channel")}
        self._put("messages", ts, msg)
        return {"ok": True, "channel": body.get("channel"), "ts": ts, "message": msg}, 200

    def list(self, resource):                    # resource == "conversations.history"
        return {"ok": True, "messages": self._all("messages")}, 200


def _demo():
    import sqlite3
    t = SlackTwin(sqlite3.connect(":memory:"))
    resp, st = t.create("chat.postMessage", {"channel": "C123", "text": "hello"})
    assert st == 200 and resp["ok"] and resp["message"]["text"] == "hello", resp
    hist, st = t.list("conversations.history")
    assert st == 200 and hist["messages"][0]["ts"] == resp["ts"], hist
    print("ok")


if __name__ == "__main__":
    _demo()
