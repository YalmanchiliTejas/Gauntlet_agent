"""Boot the per-run egress world: the twins a run declares + the proxy, with a
default-deny routing table. Returns the proxy address and CA path the sandbox
must use; teardown stops everything and deletes per-run state.

This is the seam: it's what forces all sandbox egress through the proxy so
declared vendors hit twins and everything else is denied.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# The real domain each service answers as (what the customer's SDK will call).
DOMAINS = {
    "stripe": "api.stripe.com",
    "twilio": "api.twilio.com",
    "slack": "slack.com",
    "hubspot": "api.hubapi.com",
    "resend": "api.resend.com",
    "github": "api.github.com",
    "gmail": "gmail.googleapis.com",
    "google_calendar": "www.googleapis.com",
    "excel": "graph.microsoft.com",
}


def build_routing(services: dict, modes: dict | None = None, ports: dict | None = None) -> dict:
    """Pure: declared services -> per-domain routing table. Undeclared = absent
    (the proxy default-denies anything not in the table).

    services: {name: version}   modes: {name: twin|live|record}   ports: {name: port}
    """
    modes, ports = modes or {}, ports or {}
    table = {}
    for svc in services:
        domain = DOMAINS[svc]
        mode = modes.get(svc, "twin")
        if mode == "twin":
            table[domain] = {"mode": "twin", "service": svc,
                             "twin": f"127.0.0.1:{ports[svc]}"}
        else:
            table[domain] = {"mode": mode, "service": svc}
    return table


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Sandbox:
    def __init__(self, services: dict, modes: dict | None = None, webhook_url: str | None = None,
                 egress_default: str = "deny"):
        self.services = services            # {name: version}
        self.modes = modes or {}
        self.webhook_url = webhook_url
        self.egress_default = egress_default  # deny | live (passthrough undeclared)
        self.procs: list[subprocess.Popen] = []
        self.dir = Path(tempfile.mkdtemp(prefix="sandbox-"))
        self.proxy_url = ""
        self.ca = self.dir / "mitm" / "mitmproxy-ca-cert.pem"
        self.egress_log = self.dir / "egress.jsonl"  # ground truth for the judge's verifier

    def start(self) -> "Sandbox":
        ports = {}
        for svc, ver in self.services.items():
            if self.modes.get(svc, "twin") != "twin":
                continue
            ports[svc] = _free_port()
            env = {**os.environ, "TWIN_SERVICE": svc, "TWIN_VERSION": ver,
                   "TWIN_DB": str(self.dir / f"{svc}.db")}
            if self.webhook_url:
                env["TWIN_WEBHOOK_URL"] = self.webhook_url
            self.procs.append(subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "twins.twin_server:app",
                 "--port", str(ports[svc])], env=env))

        routing = self.dir / "routing.json"
        routing.write_text(json.dumps(build_routing(self.services, self.modes, ports)))

        proxy_port = _free_port()
        # ponytail: requires mitmproxy installed (pip install -e .). mitmdump
        # generates its CA into confdir on first run; the sandbox trusts self.ca.
        self.procs.append(subprocess.Popen(
            ["mitmdump", "-s", "proxy/addon.py", "--listen-port", str(proxy_port),
             "--set", f"confdir={self.dir / 'mitm'}",
             # lazy: deny undeclared domains cleanly (don't dial upstream first)
             "--set", "connection_strategy=lazy"],
            env={**os.environ, "ROUTING_TABLE": str(routing),
                 "FIXTURES_DIR": str(self.dir / "fixtures"),
                 "EGRESS_LOG": str(self.egress_log),
                 "EGRESS_DEFAULT": self.egress_default}))
        self.proxy_url = f"http://127.0.0.1:{proxy_port}"

        # Wait for the proxy port + the generated CA so the sandbox can trust it.
        deadline = time.time() + 30
        while time.time() < deadline and not self.ca.is_file():
            time.sleep(0.2)
        return self

    def env_for_sandbox(self) -> dict:
        """Inject into the VM so ALL egress goes through the proxy + trusts its CA.

        The CA path is the in-VM location where the image places it (the runner
        passes the CA bytes to microvm.upload_bundle), not the host path.
        """
        ca = "/gauntlet_ca.pem"  # matches microvm._CA_VM_PATH
        return {"HTTP_PROXY": self.proxy_url, "HTTPS_PROXY": self.proxy_url,
                "REQUESTS_CA_BUNDLE": ca, "SSL_CERT_FILE": ca,
                "NODE_EXTRA_CA_CERTS": ca, "CURL_CA_BUNDLE": ca}

    def teardown(self) -> None:
        for p in self.procs:
            p.terminate()
        for p in self.procs:
            try:
                p.wait(timeout=5)
            except Exception:
                p.kill()
        shutil.rmtree(self.dir, ignore_errors=True)


def _demo():
    # Pure routing: declared -> mapped, undeclared -> absent (proxy will deny).
    t = build_routing({"stripe": "2022-11-15", "slack": "v1"},
                      modes={"slack": "record"}, ports={"stripe": 9100})
    assert t["api.stripe.com"] == {"mode": "twin", "service": "stripe", "twin": "127.0.0.1:9100"}
    assert t["slack.com"] == {"mode": "record", "service": "slack"}
    assert "api.twilio.com" not in t  # undeclared => default-deny
    print("ok")


if __name__ == "__main__":
    _demo()
