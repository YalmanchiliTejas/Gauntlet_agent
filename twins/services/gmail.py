"""Gmail twin: users.messages. send returns {id, threadId, labelIds} at HTTP 200;
list returns the light {messages:[{id,threadId}], resultSizeEstimate} shape.
The {userId} path segment is ignored (single-tenant twin).
"""
import uuid

from twins.engine import Twin


class GmailTwin(Twin):
    def new_id(self, resource):
        return uuid.uuid4().hex[:16]

    def create(self, resource, body):
        # POST .../messages/send  -> always store under "messages", return 200.
        rec = {"id": self.new_id("messages"), "labelIds": ["SENT"]}
        rec["threadId"] = rec["id"]
        self._put("messages", rec["id"], rec)
        return rec, 200

    def wrap_list(self, resource, rows):
        return {"messages": [{"id": r["id"], "threadId": r.get("threadId", r["id"])} for r in rows],
                "resultSizeEstimate": len(rows)}


def _demo():
    import sqlite3
    t = GmailTwin(sqlite3.connect(":memory:"))
    sent, st = t.create("send", {"raw": "base64..."})
    assert st == 200 and sent["labelIds"] == ["SENT"] and sent["threadId"] == sent["id"], sent
    got, st = t.retrieve("messages", sent["id"])
    assert got["id"] == sent["id"]
    lst = t.wrap_list("messages", [sent])
    assert lst["messages"][0]["id"] == sent["id"] and lst["resultSizeEstimate"] == 1, lst
    print("ok")


if __name__ == "__main__":
    _demo()
