"""Stripe twin — the flagship. Faithful enough that the real `stripe` SDK can't
tell: cus_/pi_/ch_ ids, object/created/livemode fields, {object:list,…} list
envelopes, vendor error envelopes, card-decline simulation via test tokens, and
a signed payment_intent.succeeded webhook.
"""
import hashlib
import hmac
import json
import os
import time
import uuid

from twins.engine import Twin, TwinError

# Stripe's documented decline test tokens / payment methods.
_DECLINE = {"tok_chargeDeclined", "pm_card_chargeDeclined", "tok_visa_chargeDeclined"}


class StripeTwin(Twin):
    id_prefixes = {"customers": "cus", "payment_intents": "pi", "charges": "ch"}

    def on_create(self, resource, body):
        rec = {**body,
               "id": self.new_id(resource),
               "object": resource[:-1],          # customers -> customer
               "created": int(time.time()),
               "livemode": False}
        if resource == "payment_intents":
            pm = rec.get("payment_method") or rec.get("source")
            if pm in _DECLINE:
                raise TwinError(402, {"error": {
                    "type": "card_error", "code": "card_declined",
                    "decline_code": "generic_decline",
                    "message": "Your card was declined."}})
            rec["status"] = "succeeded" if rec.get("confirm") in (True, "true") \
                else "requires_confirmation"
        return rec

    def create(self, resource, body):
        rec, status = super().create(resource, body)
        if resource == "payment_intents" and rec.get("status") == "succeeded":
            self.emit("payment_intent.succeeded", rec)
        return rec, status

    def wrap_list(self, resource, rows):
        return {"object": "list", "url": f"/v1/{resource}",
                "has_more": False, "data": rows}

    def emit(self, event_type, obj):
        if not self.webhook_url:
            return
        import httpx
        event = {"id": f"evt_{uuid.uuid4().hex[:24]}", "object": "event",
                 "type": event_type, "created": int(time.time()),
                 "data": {"object": obj}}
        payload = json.dumps(event)
        ts = int(time.time())
        secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
        sig = hmac.new(secret.encode(), f"{ts}.{payload}".encode(), hashlib.sha256).hexdigest()
        httpx.post(self.webhook_url, content=payload, timeout=5,
                   headers={"Content-Type": "application/json",
                            "Stripe-Signature": f"t={ts},v1={sig}"})


def _demo():
    import sqlite3
    t = StripeTwin(sqlite3.connect(":memory:"))

    cus, _ = t.create("customers", {"email": "a@b.c"})
    assert cus["id"].startswith("cus_") and cus["object"] == "customer", cus

    pi, st = t.create("payment_intents", {"amount": 4200, "currency": "usd", "confirm": "true"})
    assert st == 201 and pi["id"].startswith("pi_") and pi["status"] == "succeeded", pi

    lst = t.wrap_list("payment_intents", [pi])
    assert lst["object"] == "list" and lst["data"][0]["id"] == pi["id"], lst

    try:
        t.create("payment_intents", {"amount": 100, "currency": "usd", "source": "tok_chargeDeclined"})
        assert False, "expected decline"
    except TwinError as e:
        assert e.status == 402 and e.payload["error"]["code"] == "card_declined"
    print("ok")


if __name__ == "__main__":
    _demo()
