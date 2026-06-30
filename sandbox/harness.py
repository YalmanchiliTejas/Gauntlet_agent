"""Runs INSIDE the sandbox VM. Executes the customer's command once, captures
stdout/stderr + exit code, and serves the result over HTTP so the runner can
poll it. Stdlib only — no deps to install in the image.

It also doubles as an OTLP/HTTP trace sink: the customer's agent is OTel-configured
(env baked by the runner) to export spans to http://127.0.0.1:8080/v1/traces. We
collect those so the runner can pull the agent's trajectory and judge it. A customer
who emits our native trajectory JSONL instead just writes it to $TRAJECTORY_FILE.

  HARNESS_CMD="pytest -q" PORT=8080 python harness.py

  GET  /health      -> {"ok": true}
  GET  /result      -> {"done": bool, "exit_code": int, "stdout": str, "stderr": str}
  GET  /trajectory  -> {"native": str|null, "otlp": [span-export-doc, ...]}
  POST /v1/traces   -> OTLP/HTTP ingest (http/json); body stored for /trajectory
"""
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

_CMD = os.environ.get("HARNESS_CMD", "true")
_CAP = 64 * 1024          # tail bytes of each stream we keep
_OTLP_CAP = 32 * 1024 * 1024  # max bytes of OTLP we retain (agent traces can be large)
result: dict = {"done": False}
_otlp: list = []
_otlp_bytes = 0
_lock = threading.Lock()


def _run() -> None:
    try:
        p = subprocess.run(_CMD, shell=True, capture_output=True, text=True)
        result.update(done=True, exit_code=p.returncode,
                      stdout=p.stdout[-_CAP:], stderr=p.stderr[-_CAP:])
    except Exception as e:  # never let the harness itself hang the poll
        result.update(done=True, exit_code=-1, stdout="", stderr=f"harness error: {e}")


def _trajectory() -> dict:
    native = None
    tf = os.environ.get("TRAJECTORY_FILE")
    if tf and os.path.isfile(tf):
        native = open(tf).read()
    with _lock:
        return {"native": native, "otlp": list(_otlp)}


class _Handler(BaseHTTPRequestHandler):
    def _send(self, body: bytes, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send(b'{"ok": true}')
        elif self.path == "/result":
            self._send(json.dumps(result).encode())
        elif self.path == "/trajectory":
            self._send(json.dumps(_trajectory()).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        global _otlp_bytes
        if self.path.startswith("/v1/traces"):
            n = int(self.headers.get("content-length", 0))
            body = self.rfile.read(n)
            try:
                doc = json.loads(body)
            except Exception:
                doc = None
            if doc is not None:
                with _lock:
                    if _otlp_bytes < _OTLP_CAP:  # ponytail: drop overflow, keep the head
                        _otlp.append(doc)
                        _otlp_bytes += n
            self._send(b'{"partialSuccess":{}}')  # OTLP/HTTP success envelope
        elif self.path.startswith("/exec"):
            # Generated-CLI channel: the review/fix agent runs tools in the VM. Behind the
            # MicroVM auth token (AWS-gated endpoint); the VM is already running untrusted code.
            n = int(self.headers.get("content-length", 0))
            try:
                cmd = json.loads(self.rfile.read(n)).get("cmd", "")
            except Exception:
                cmd = ""
            try:
                p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
                res = {"exit": p.returncode, "stdout": p.stdout[-_CAP:], "stderr": p.stderr[-_CAP:]}
            except Exception as e:
                res = {"exit": -1, "stdout": "", "stderr": f"exec error: {e}"}
            self._send(json.dumps(res).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):  # quiet
        pass


if __name__ == "__main__":
    threading.Thread(target=_run, daemon=True).start()
    HTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), _Handler).serve_forever()
