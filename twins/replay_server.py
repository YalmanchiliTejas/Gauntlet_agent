"""Replay twin: serve responses recorded by the proxy's `record` mode
(fixtures/<service>.jsonl) for long-tail services that have no plugin or spec.

  REPLAY_FIXTURE=fixtures/somevendor.jsonl uvicorn twins.replay_server:app --port 9200

Stateless: matches (method, path) to the recorded response. Unmatched -> 404.
"""
import json
import os
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import Response


class Replay:
    def __init__(self, lines):
        self.table = {}
        for line in lines:
            if not line.strip():
                continue
            rec = json.loads(line)
            key = (rec["method"], urlparse(rec["url"]).path)
            self.table[key] = (rec["status"], rec.get("response", ""))

    def match(self, method, path):
        return self.table.get((method, path))


def _load() -> Replay:
    p = os.environ.get("REPLAY_FIXTURE")
    return Replay(open(p).read().splitlines()) if p and os.path.isfile(p) else Replay([])


replay = _load()
app = FastAPI()


@app.api_route("/{full:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def handle(full: str, request: Request):
    hit = replay.match(request.method, "/" + full)
    if hit is None:
        return Response('{"error": "no recording for this request"}', 404,
                        media_type="application/json")
    status, body = hit
    return Response(body, status, media_type="application/json")


def _demo():
    lines = [json.dumps({"method": "GET", "url": "https://api.x.com/v1/things",
                         "status": 200, "response": '[{"id": 1}]'})]
    r = Replay(lines)
    assert r.match("GET", "/v1/things") == (200, '[{"id": 1}]')
    assert r.match("POST", "/v1/things") is None
    print("ok")


if __name__ == "__main__":
    _demo()
