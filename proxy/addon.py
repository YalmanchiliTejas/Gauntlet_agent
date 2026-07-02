"""The egress proxy: the single chokepoint for all sandbox outbound traffic.

Switching twin/live/record happens HERE, at the network layer — not in the
agent's code — because third-party SDKs can't be trusted to honor a custom
base URL. The sandbox is configured with HTTPS_PROXY=this and our CA trusted,
so we see every request by domain.

  twin   -> rewrite to a local twin server
  live   -> forward to the real endpoint untouched
  record -> forward to the real endpoint AND log traffic to grow twin fixtures
  (anything not listed) -> deny. Default-deny is THE safety property.

Run:  mitmdump -s proxy/addon.py --listen-port 8080

The routing decision (`decide`) is a pure function with no mitmproxy
dependency, so the default-deny guarantee is unit-testable on its own.
"""
import json
import os
import time
from pathlib import Path


def load_table(path: str) -> dict:
    return json.loads(Path(path).read_text())


def decide(host: str, table: dict, default: str = "deny") -> dict:
    """Pure routing decision for a destination host.

    `default` is what happens to a host not in the table:
      deny (safety default, PR-check runs) | live (passthrough to the real
      endpoint, for workflow runs where the agent must reach services it isn't
      twinning — its LLM API, its own backend, etc.)."""
    route = table.get(host)
    if route is None:
        if default == "live":
            return {"action": "forward", "mode": "live", "service": host}
        return {"action": "deny", "reason": "domain not declared"}
    mode = route.get("mode")
    service = route.get("service", host)
    if mode == "twin":
        h, _, p = route["twin"].partition(":")
        return {"action": "twin", "host": h, "port": int(p or 80),
                "mode": "twin", "service": service}
    if mode in ("live", "record"):
        return {"action": "forward", "mode": mode, "service": service}
    return {"action": "deny", "reason": f"unknown mode {mode!r}"}


class Egress:
    def __init__(self):
        self._table = None
        self._default = os.environ.get("EGRESS_DEFAULT", "deny")

    @property
    def table(self) -> dict:
        if self._table is None:  # lazy so importing this module needs no file/deps
            self._table = load_table(os.environ.get("ROUTING_TABLE", "proxy/routing.json"))
        return self._table

    def request(self, flow) -> None:
        from mitmproxy import http
        d = decide(flow.request.pretty_host, self.table, self._default)
        flow.metadata["service"] = d.get("service", flow.request.pretty_host)
        if d["action"] == "deny":
            flow.metadata["egress_mode"] = "deny"
            flow.response = http.Response.make(403, f"egress denied: {d['reason']}\n".encode())
            return
        flow.metadata["egress_mode"] = d["mode"]
        if d["action"] == "twin":
            flow.request.scheme = "http"
            flow.request.host = d["host"]
            flow.request.port = d["port"]
        # forward: leave the request untouched, mitmproxy sends it to the real host

    def response(self, flow) -> None:
        self._egress_log(flow)
        if flow.metadata.get("egress_mode") != "record":
            return
        # Log real traffic so we can grow / correct this service's twin fixtures.
        service = flow.metadata["service"]
        fixtures = Path(os.environ.get("FIXTURES_DIR", "fixtures"))
        fixtures.mkdir(parents=True, exist_ok=True)
        line = {
            "ts": time.time(),
            "method": flow.request.method,
            "url": flow.request.pretty_url,
            "status": flow.response.status_code,
            "request": flow.request.get_text(strict=False),
            "response": flow.response.get_text(strict=False),
        }
        with (fixtures / f"{service}.jsonl").open("a") as f:
            f.write(json.dumps(line) + "\n")

    def _egress_log(self, flow) -> None:
        """Ground truth for the judge's verifier: every egress attempt (any mode, incl.
        denied). Lets the judge catch a tool_result that claims an action no call backs."""
        path = os.environ.get("EGRESS_LOG")
        if not path:
            return
        line = {
            "ts": flow.request.timestamp_start or time.time(),
            "service": flow.metadata.get("service"),
            "mode": flow.metadata.get("egress_mode"),
            "method": flow.request.method,
            "url": flow.request.pretty_url,
            "status": flow.response.status_code if flow.response else None,
            # W3C trace context: carries the span id of the tool call that made this
            # request, so the judge can join egress->tool exactly (no name guessing).
            "traceparent": flow.request.headers.get("traceparent"),
        }
        with open(path, "a") as f:
            f.write(json.dumps(line) + "\n")


addons = [Egress()]
