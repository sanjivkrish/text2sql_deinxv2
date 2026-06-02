#!/usr/bin/env python3
"""Local-only debug server. Run with DEBUG=true in .env."""
import os, json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import urlopen, Request as URLRequest
from urllib.parse import urlparse, parse_qs

if os.environ.get("DEBUG", "false").lower() != "true":
    print("DEBUG=true required to run debug server")
    raise SystemExit(1)

BACKEND = os.environ.get("BACKEND_URL", "http://localhost:8000")
INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "dev-secret")

HTML = """<!DOCTYPE html>
<html><head><title>Text-to-SQL v2 Debug</title>
<style>body{font-family:monospace;padding:20px;max-width:900px}
textarea,input,select{width:100%;box-sizing:border-box;margin:4px 0}
button{margin:4px;padding:8px 16px}.panel{background:#f4f4f4;padding:12px;margin:8px 0;border-radius:4px}
details summary{cursor:pointer;font-weight:bold}pre{overflow:auto;max-height:300px}
.err{color:red}.ok{color:green}</style></head>
<body><h2>Text-to-SQL v2 — Debug UI</h2>
<label>Query:<textarea id="q" rows="3" placeholder="e.g. how many students are in each class"></textarea></label>
<label>School ID (UUID):<input id="sid" value="test-school-uuid"/></label>
<label>Limit:<input id="lim" type="number" value="50"/></label>
<button onclick="run('plan')">Plan Only</button>
<button onclick="run('query')">Full Query</button>
<button onclick="run('health')">Health Check</button>
<div id="out"></div>
<script>
async function run(mode) {
  const q = document.getElementById('q').value.trim();
  const sid = document.getElementById('sid').value.trim();
  const lim = parseInt(document.getElementById('lim').value) || 50;
  const out = document.getElementById('out');
  out.innerHTML = 'Loading...';
  const body = mode === 'health' ? null : JSON.stringify({query:q, school_id:sid, limit:lim});
  const url = mode === 'health' ? '/proxy/health' : (mode === 'plan' ? '/proxy/query/plan' : '/proxy/query');
  const method = mode === 'health' ? 'GET' : 'POST';
  const resp = await fetch(url, {method, headers:{'Content-Type':'application/json'}, body});
  const data = await resp.json();
  let html = '';
  if (data.summary) html += `<div class="panel"><b>Summary</b><p>${data.summary}</p></div>`;
  if (data.token_usage) html += `<div class="panel"><b>Token Cost</b><pre>${JSON.stringify(data.token_usage,null,2)}</pre></div>`;
  if (data.warnings?.length) html += `<div class="panel err"><b>Warnings</b><ul>${data.warnings.map(w=>`<li>${w}</li>`).join('')}</ul></div>`;
  if (data.query_plan || data.intent) html += `<details class="panel"><summary>Pipeline Trace</summary><pre>${JSON.stringify(data,null,2)}</pre></details>`;
  if (!html) html = `<div class="panel"><pre>${JSON.stringify(data,null,2)}</pre></div>`;
  out.innerHTML = html;
}
</script></body></html>"""

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self._send(200, HTML.encode(), "text/html")
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
        except Exception as e:
            self._send(500, json.dumps({"error": str(e)}).encode(), "application/json")

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
