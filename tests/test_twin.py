"""Twin behaves like a real stateful API: seeded, multi-step, schema-checked.

Run: python -m pytest tests/test_twin.py
"""
import pytest
from starlette.testclient import TestClient

from twins import twin_server


@pytest.fixture
def client():
    # `with` fires startup -> seed loads.
    with TestClient(twin_server.app) as c:
        yield c


def test_seed_loaded(client):
    ids = [w["id"] for w in client.get("/widgets").json()]
    assert "seed-1" in ids


def test_post_then_get_roundtrip(client):
    r = client.post("/widgets", json={"name": "alpha", "count": 2})
    assert r.status_code == 201
    wid = r.json()["id"]
    got = client.get(f"/widgets/{wid}")
    assert got.status_code == 200
    assert got.json()["name"] == "alpha"


def test_missing_required_field_rejected(client):
    assert client.post("/widgets", json={"count": 1}).status_code == 400  # no name


def test_extra_field_rejected(client):
    # WidgetInput has additionalProperties:false
    assert client.post("/widgets", json={"name": "x", "bogus": 1}).status_code == 400


def test_undeclared_endpoint_404(client):
    assert client.get("/nope").status_code == 404


def test_delete_then_gone(client):
    wid = client.post("/widgets", json={"name": "temp"}).json()["id"]
    assert client.delete(f"/widgets/{wid}").status_code == 204
    assert client.get(f"/widgets/{wid}").status_code == 404
