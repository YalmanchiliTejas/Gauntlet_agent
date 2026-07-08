"""Twin engine: generic stateful behavior + hooks a per-service module overrides.

The base `Twin` is plain CRUD over SQLite. A service plugin (e.g. StripeTwin)
subclasses it to add fidelity: real id prefixes (cus_…), server-set fields
(object/created/livemode/status), list & error envelopes, webhook events, and
failure simulation. The real vendor SDK should not be able to tell the
difference — that's the bar.

State is per run (a fresh SQLite db) and resets between runs by using a new db.
"""
import json
import sqlite3
import uuid
from urllib.parse import parse_qsl


class TwinError(Exception):
    """Raised to return a vendor-shaped error envelope with a status code."""
    def __init__(self, status: int, payload: dict):
        super().__init__(str(payload))
        self.status = status
        self.payload = payload


def _coerce(v: str):
    # Form values are strings; SDKs send amount=4200, active=true. Best-effort.
    if v in ("true", "false"):
        return v == "true"
    if v.lstrip("-").isdigit():
        return int(v)
    return v


def _unflatten(pairs) -> dict:
    """Stripe-style brackets: metadata[k]=v -> {"metadata": {"k": v}}."""
    out: dict = {}
    for key, val in pairs:
        if "[" in key and key.endswith("]"):
            head, _, rest = key.partition("[")
            out.setdefault(head, {})[rest[:-1]] = _coerce(val)
        else:
            out[key] = _coerce(val)
    return out


def parse_body(content_type: str, raw: bytes) -> dict:
    """Accept JSON or form-encoded — real SDKs (Stripe, Twilio) send form."""
    if not raw:
        return {}
    ct = (content_type or "").split(";")[0].strip()
    if ct == "application/x-www-form-urlencoded":
        return _unflatten(parse_qsl(raw.decode()))
    return json.loads(raw)  # default + application/json


class Twin:
    id_prefixes: dict[str, str] = {}  # resource -> id prefix, e.g. {"customers": "cus"}

    def __init__(self, db: sqlite3.Connection, webhook_url: str | None = None):
        self.db = db
        self.webhook_url = webhook_url
        db.execute("CREATE TABLE IF NOT EXISTS records "
                   "(resource TEXT, id TEXT, body TEXT, PRIMARY KEY(resource, id))")
        db.commit()

    # ---- hooks services override for fidelity ----
    def new_id(self, resource: str) -> str:
        prefix = self.id_prefixes.get(resource)
        raw = uuid.uuid4().hex[:24]
        return f"{prefix}_{raw}" if prefix else raw

    def on_create(self, resource: str, body: dict) -> dict:
        """Build the stored record incl. server-set fields. Override per service."""
        return {**body, "id": self.new_id(resource)}

    def wrap_list(self, resource: str, rows: list) -> object:
        """Shape a collection response (Stripe wraps in {object:list,data:…})."""
        return rows

    def emit(self, event_type: str, obj: dict) -> None:
        """Fire a webhook to the app under test, if one is configured."""
        if not self.webhook_url:
            return
        import httpx
        httpx.post(self.webhook_url,
                   json={"type": event_type, "data": {"object": obj}}, timeout=5)

    # ---- storage ----
    def _put(self, resource, rid, rec):
        self.db.execute("INSERT OR REPLACE INTO records VALUES (?,?,?)",
                        (resource, rid, json.dumps(rec)))
        self.db.commit()

    def _get(self, resource, rid):
        r = self.db.execute("SELECT body FROM records WHERE resource=? AND id=?",
                            (resource, rid)).fetchone()
        return json.loads(r[0]) if r else None

    def _all(self, resource):
        # ORDER BY rowid = stable insertion order. Without it SQLite returns rows in
        # (resource, id) index order, and random ids make list order nondeterministic.
        return [json.loads(b) for (b,) in
                self.db.execute("SELECT body FROM records WHERE resource=? ORDER BY rowid", (resource,))]

    # ---- operations: (payload, status) ----
    def create(self, resource, body):
        rec = self.on_create(resource, body)
        self._put(resource, rec["id"], rec)
        return rec, 201

    def retrieve(self, resource, rid):
        rec = self._get(resource, rid)
        if rec is None:
            raise TwinError(404, {"error": {"type": "invalid_request_error",
                                            "message": f"no such {resource[:-1]}: {rid}"}})
        return rec, 200

    def list(self, resource, params: dict | None = None):
        return self.wrap_list(resource, self._all(resource)), 200

    def update(self, resource, rid, body, patch: bool):
        base = self._get(resource, rid) or {"id": rid}
        rec = {**base, **body, "id": rid} if patch else {**body, "id": rid}
        self._put(resource, rid, rec)
        return rec, 200

    def delete(self, resource, rid):
        self.db.execute("DELETE FROM records WHERE resource=? AND id=?", (resource, rid))
        self.db.commit()
        return None, 204

    def seed(self, records: dict):
        """records: {resource: [ {...}, ... ]}. Later layers win (scenarios)."""
        for resource, rows in records.items():
            for row in rows:
                rid = str(row.get("id") or self.new_id(resource))
                self._put(resource, rid, {**row, "id": rid})


def _demo():
    class FakeStripe(Twin):
        id_prefixes = {"customers": "cus"}

        def on_create(self, resource, body):
            return {**body, "id": self.new_id(resource), "object": "customer",
                    "created": 1700000000, "livemode": False}

    t = FakeStripe(sqlite3.connect(":memory:"))
    rec, st = t.create("customers", {"email": "a@b.c"})
    assert st == 201 and rec["id"].startswith("cus_") and rec["object"] == "customer", rec
    assert t.retrieve("customers", rec["id"])[0]["email"] == "a@b.c"
    try:
        t.retrieve("customers", "cus_nope")
        assert False, "expected 404"
    except TwinError as e:
        assert e.status == 404

    body = parse_body("application/x-www-form-urlencoded",
                      b"amount=4200&currency=usd&metadata[order]=42")
    assert body == {"amount": 4200, "currency": "usd", "metadata": {"order": 42}}, body
    print("ok")


if __name__ == "__main__":
    _demo()
