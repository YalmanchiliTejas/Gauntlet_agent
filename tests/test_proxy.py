"""The proxy's routing decision — especially default-deny, the core safety
property. Pure function, no mitmproxy needed.

Run: python -m pytest tests/test_proxy.py
"""
from proxy.addon import decide

TABLE = {
    "api.widgets.com": {"mode": "twin", "service": "widgets", "twin": "127.0.0.1:9100"},
    "api.vendor.com": {"mode": "record", "service": "vendor"},
    "api.internal.com": {"mode": "live"},
}


def test_undeclared_domain_is_denied():
    assert decide("evil.example.com", TABLE)["action"] == "deny"


def test_empty_table_denies_everything():
    assert decide("api.widgets.com", {})["action"] == "deny"


def test_twin_rewrites_to_local_server():
    d = decide("api.widgets.com", TABLE)
    assert d == {"action": "twin", "host": "127.0.0.1", "port": 9100,
                 "mode": "twin", "service": "widgets"}


def test_record_forwards_and_marks_recording():
    d = decide("api.vendor.com", TABLE)
    assert d["action"] == "forward" and d["mode"] == "record"


def test_live_forwards_untouched():
    d = decide("api.internal.com", TABLE)
    assert d["action"] == "forward" and d["mode"] == "live"


def test_unknown_mode_is_denied():
    # A declared domain with a bogus mode must NOT fall through to allow.
    assert decide("x.com", {"x.com": {"mode": "bogus"}})["action"] == "deny"
