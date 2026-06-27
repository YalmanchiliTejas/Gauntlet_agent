"""Runs INSIDE the sandbox VM. Executes the customer's command once, captures
stdout/stderr + exit code, and serves the result over HTTP so the runner can
poll it. Stdlib only — no deps to install in the image.

  HARNESS_CMD="pytest -q" PORT=8080 python harness.py

  GET /health  -> {"ok": true}
  GET /result  -> {"done": bool, "exit_code": int, "stdout": str, "stderr": str}
"""
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

_CMD = os.environ.get("HARNESS_CMD", "true")
_CAP = 64 * 1024  # tail bytes of each stream we keep
result: dict = {"done": False}


def _run() -> None:
    try:
        p = subprocess.run(_CMD, shell=True, capture_output=True, text=True)
        result.update(done=True, exit_code=p.returncode,
                      stdout=p.stdout[-_CAP:], stderr=p.stderr[-_CAP:])
    except Exception as e:  # never let the harness itself hang the poll
        result.update(done=True, exit_code=-1, stdout="", stderr=f"harness error: {e}")


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body = b'{"ok": true}'
        elif self.path == "/result":
            body = json.dumps(result).encode()
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # quiet
        pass


if __name__ == "__main__":
    threading.Thread(target=_run, daemon=True).start()
    HTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), _Handler).serve_forever()
