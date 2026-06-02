#!/usr/bin/env python3
"""Local-only debug server. Run with DEBUG=true in .env."""
import os, json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import urlopen, Request as URLRequest
from urllib.error import HTTPError
from pathlib import Path

if os.environ.get("DEBUG", "false").lower() != "true":
    print("DEBUG=true required to run debug server")
    raise SystemExit(1)

BACKEND = os.environ.get("BACKEND_URL", "http://localhost:8000")
INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "dev-secret")
_HTML_PATH = Path(__file__).parent / "index.html"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self._send(200, _HTML_PATH.read_bytes(), "text/html; charset=utf-8")
        elif self.path.startswith("/proxy/"):
            self._proxy("GET", self.path[7:], b"")
        else:
            self._send(404, b"Not Found")

    def do_POST(self):
        if self.path.startswith("/proxy/"):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            self._proxy("POST", self.path[7:], body)
        else:
            self._send(404, b"Not Found")

    def _proxy(self, method, path, body):
        url = f"{BACKEND}/{path.lstrip('/')}"
        req = URLRequest(url, data=body or None, method=method,
                         headers={"Content-Type": "application/json",
                                  "X-Internal-Token": INTERNAL_SECRET})
        try:
            with urlopen(req) as r:
                data = r.read()
            self._send(200, data, "application/json")
        except HTTPError as e:
            # Forward the real status + body so the UI shows FastAPI's error detail
            self._send(e.code, e.read(), "application/json")
        except Exception as e:
            self._send(502, json.dumps({"error": str(e)}).encode(), "application/json")

    def _send(self, code, body, ct="text/plain"):
        self.send_response(code)
        self.send_header("Content-Type", ct)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # suppress access log

if __name__ == "__main__":
    port = int(os.environ.get("DEBUG_PORT", 9000))
    print(f"Debug UI: http://localhost:{port}  (backend: {BACKEND})")
    HTTPServer(("", port), Handler).serve_forever()
