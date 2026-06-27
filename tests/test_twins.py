"""Permanent coverage for every twin clone — vendor-specific shapes, id formats,
envelopes, and failure modes, through the real HTTP + schema-validation path.

Run: python -m pytest tests/test_twins.py
"""
import os
import sys

from starlette.testclient import TestClient


def make_client(service: str, version: str) -> TestClient:
    """Fresh in-memory twin for `service` (re-imports the module per service)."""
    os.environ["TWIN_SERVICE"] = service
    os.environ["TWIN_VERSION"] = version
    os.environ.pop("TWIN_DB", None)        # :memory:
    os.environ.pop("TWIN_WEBHOOK_URL", None)
    sys.modules.pop("twins.twin_server", None)
    import twins.twin_server as ts
    return TestClient(ts.app)


def test_stripe():
    c = make_client("stripe", "2022-11-15")
    cus = c.post("/customers", data={"email": "a@b.c"})           # form, like the SDK
    assert cus.status_code == 201 and cus.json()["id"].startswith("cus_")
    assert cus.json()["object"] == "customer"
    pi = c.post("/payment_intents", data={"amount": "4200", "currency": "usd", "confirm": "true"})
    assert pi.json()["id"].startswith("pi_") and pi.json()["status"] == "succeeded"
    dec = c.post("/payment_intents", data={"amount": "1", "currency": "usd", "source": "tok_chargeDeclined"})
    assert dec.status_code == 402 and dec.json()["error"]["code"] == "card_declined"
    lst = c.get("/customers").json()
    assert lst["object"] == "list" and any(x["id"] == "cus_seed" for x in lst["data"])
    assert c.get("/not_a_resource").status_code == 404   # undeclared -> 404


def test_twilio():
    c = make_client("twilio", "2010-04-01")
    m = c.post("/Messages", data={"To": "+15551112222", "From": "+15553334444", "Body": "hi"})
    assert m.status_code == 201 and m.json()["sid"].startswith("SM") and "_" not in m.json()["sid"]
    assert m.json()["status"] == "sent"
    lst = c.get("/Messages").json()
    assert set(lst) >= {"messages", "page", "page_size"}
    assert c.post("/Messages", data={"To": "+1"}).status_code == 400   # missing Body/From


def test_slack():
    c = make_client("slack", "v1")
    r = c.post("/chat.postMessage", data={"channel": "C1", "text": "yo"})
    assert r.status_code == 200 and r.json()["ok"] and r.json()["message"]["text"] == "yo"
    hist = c.get("/conversations.history").json()
    assert hist["ok"] and hist["messages"][0]["ts"] == r.json()["ts"]


def test_gmail():
    c = make_client("gmail", "v1")
    s = c.post("/gmail/v1/users/me/messages/send", json={"raw": "aGk="})
    assert s.status_code == 200 and s.json()["labelIds"] == ["SENT"]
    assert s.json()["threadId"] == s.json()["id"]
    lst = c.get("/gmail/v1/users/me/messages").json()
    ids = {m["id"] for m in lst["messages"]}
    assert s.json()["id"] in ids and "seedmsg00000001" in ids


def test_google_calendar():
    c = make_client("google_calendar", "v3")
    ev = c.post("/calendar/v3/calendars/primary/events",
                json={"summary": "Sync", "start": {"dateTime": "2026-07-01T10:00:00Z"},
                      "end": {"dateTime": "2026-07-01T10:30:00Z"}})
    assert ev.status_code == 200 and ev.json()["status"] == "confirmed"
    assert ev.json()["kind"] == "calendar#event" and ev.json()["htmlLink"]
    assert c.get("/calendar/v3/calendars/primary/events").json()["kind"] == "calendar#events"


def test_excel():
    c = make_client("excel", "v1")
    r0 = c.post("/v1.0/workbook/tables/Table1/rows", json={"values": [["a", "b", 1]]})
    r1 = c.post("/v1.0/workbook/tables/Table1/rows", json={"values": [["c", "d", 2]]})
    assert r0.json()["index"] == 0 and r1.json()["index"] == 1     # sequential
    assert c.get("/v1.0/workbook/tables/Table1/rows").json()["value"][0]["values"] == [["a", "b", 1]]
    assert c.get("/v1.0/workbook/worksheets").json()["value"][0]["name"] == "Sheet1"


def test_hubspot():
    c = make_client("hubspot", "v3")
    r = c.post("/crm/v3/objects/contacts", json={"properties": {"email": "a@b.c"}})
    assert r.status_code == 201 and r.json()["id"].isdigit() and r.json()["archived"] is False
    rid = r.json()["id"]
    assert c.get(f"/crm/v3/objects/contacts/{rid}").json()["properties"]["email"] == "a@b.c"
    assert c.get("/crm/v3/objects/contacts").json()["total"] >= 2   # seed + new


def test_resend_generic():
    c = make_client("resend", "v1")
    e = c.post("/emails", json={"from": "a@b.c", "to": "d@e.f", "subject": "hi"})
    assert e.status_code == 201
    assert c.get(f"/emails/{e.json()['id']}").json()["subject"] == "hi"
    assert c.post("/emails", json={"from": "a@b.c"}).status_code == 400   # missing to/subject
