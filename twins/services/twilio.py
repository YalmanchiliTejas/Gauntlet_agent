"""Twilio twin: SMxxxx sids (no underscore), status, account_sid, and Twilio's
{messages:[…], page, page_size} list envelope. Real SDK sends form bodies.
"""
import uuid

from twins.engine import Twin


class TwilioTwin(Twin):
    def new_id(self, resource):
        return "SM" + uuid.uuid4().hex  # Twilio sid format: SM + 32 hex

    def on_create(self, resource, body):
        sid = self.new_id(resource)
        return {**body, "id": sid, "sid": sid, "status": "sent",
                "account_sid": "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}

    def wrap_list(self, resource, rows):
        return {"messages": rows, "page": 0, "page_size": len(rows)}


def _demo():
    import sqlite3
    t = TwilioTwin(sqlite3.connect(":memory:"))
    msg, st = t.create("Messages", {"To": "+15551112222", "From": "+15553334444", "Body": "hi"})
    assert st == 201 and msg["sid"].startswith("SM") and "_" not in msg["sid"], msg
    assert msg["status"] == "sent"
    lst = t.wrap_list("Messages", [msg])
    assert lst["messages"][0]["sid"] == msg["sid"] and lst["page_size"] == 1, lst
    print("ok")


if __name__ == "__main__":
    _demo()
