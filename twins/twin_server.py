"""HTTP front end for a twin. Thin: parse, validate, dispatch to the engine.

Behavior comes from a per-service plugin (twins/services/<service>.py) if one
exists, else the generic engine. Data is per-run: TWIN_DB + a scenario seed.

  TWIN_SERVICE=stripe TWIN_VERSION=2022-11-15 \
  TWIN_DB=/run/stripe.db TWIN_SEED=/run/scenario.json \
  TWIN_WEBHOOK_URL=https://app.under.test/webhooks/stripe \
  uvicorn twins.twin_server:app --port 9100
"""
import importlib
import json
import os
import sqlite3

import jsonschema
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from twins import engine, spec_registry

SERVICE = os.environ.get("TWIN_SERVICE", "widgets")
VERSION = os.environ.get("TWIN_VERSION", "v1")
spec = spec_registry.load(SERVICE, VERSION)
db = sqlite3.connect(os.environ.get("TWIN_DB", ":memory:"), check_same_thread=False)


def _load_twin() -> engine.Twin:
    """A service plugin if present, else generic CRUD."""
    webhook = os.environ.get("TWIN_WEBHOOK_URL")
    try:
        mod = importlib.import_module(f"twins.services.{SERVICE}")
    except ModuleNotFoundError:
        return engine.Twin(db, webhook)
    cls = next(c for c in vars(mod).values()
               if isinstance(c, type) and issubclass(c, engine.Twin) and c is not engine.Twin)
    return cls(db, webhook)


twin = _load_twin()


def _seed():
    # Platform defaults shipped with the spec, then the run's scenario on top.
    default = spec_registry.REGISTRY / SERVICE / VERSION / "seed.json"
    if default.is_file():
        twin.seed(json.loads(default.read_text()))
    scenario = os.environ.get("TWIN_SEED")
    if scenario and os.path.isfile(scenario):
        twin.seed(json.loads(open(scenario).read()))


_seed()
app = FastAPI()


def _validate(schema, instance):
    if schema is not None:
        jsonschema.validate(instance, {"components": spec.components, **schema})


@app.api_route("/{full:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def handle(full: str, request: Request):
    path = "/" + full
    op = spec.operation(request.method, path)
    if op is None:
        return JSONResponse({"error": "not in spec", "path": path}, 404)

    resource, rid = spec.target(path)   # template-derived; handles nested paths
    method = request.method

    body = None
    if method in ("POST", "PUT", "PATCH"):
        body = engine.parse_body(request.headers.get("content-type", ""), await request.body())
        try:
            _validate(spec.request_schema(op), body)
        except jsonschema.ValidationError as e:
            return JSONResponse({"error": "request schema violation", "detail": e.message}, 400)

    try:
        if method == "POST":
            payload, status = twin.create(resource, body)
        elif method == "GET" and rid is None:
            payload, status = twin.list(resource, dict(request.query_params))
        elif method == "GET":
            payload, status = twin.retrieve(resource, rid)
        elif method in ("PUT", "PATCH"):
            payload, status = twin.update(resource, rid, body, method == "PATCH")
        elif method == "DELETE":
            payload, status = twin.delete(resource, rid)
        else:
            return JSONResponse({"error": "unsupported method"}, 405)
    except engine.TwinError as e:
        return JSONResponse(e.payload, e.status)

    if status == 204:
        return Response(status_code=204)
    try:
        _validate(spec.response_schema(op, status), payload)
    except jsonschema.ValidationError as e:
        return JSONResponse({"error": "twin response violates schema", "detail": e.message}, 500)
    return JSONResponse(payload, status)
