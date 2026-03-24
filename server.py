#!/usr/bin/env python3
"""Combined server: landing page at /, course notes at /course, btc-greeks at /btc"""

import http.server
import urllib.request
import os

PORT = int(os.environ.get("PORT", 8080))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

INDEX_HTML  = os.path.join(BASE_DIR, "index.html")
COURSE_HTML = os.path.join(BASE_DIR, "6-lesson", "index.html")
BTC_HTML    = os.path.join(BASE_DIR, "4-option", "index.html")

DERIBIT_BASE = "https://www.deribit.com"
BYBIT_BASE   = "https://api.bybit.com"
CONVEX_BASE  = "https://small-bulldog-987.convex.cloud"


class CombinedHandler(http.server.BaseHTTPRequestHandler):

    # ── Static pages ─────────────────────────────────────────────────────────

    def do_GET(self):
        if self.path.startswith("/proxy/bybit/"):
            self._proxy_get(BYBIT_BASE + self.path[len("/proxy/bybit"):],
                            extra_headers={"X-Referer": "bybit-skill"})

        elif self.path.startswith("/proxy/deribit/"):
            self._proxy_get(DERIBIT_BASE + self.path[len("/proxy/deribit"):])

        elif self.path in ("/btc", "/btc/"):
            self._serve_file(BTC_HTML)

        elif self.path in ("/course", "/course/"):
            self._serve_file(COURSE_HTML)

        else:
            self._serve_file(INDEX_HTML)

    # ── Proxy POST (Convex) ───────────────────────────────────────────────────

    def do_POST(self):
        if self.path.startswith("/proxy/convex/"):
            target = CONVEX_BASE + "/" + self.path[len("/proxy/convex/"):]
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            self._proxy_post(target, body)
        else:
            self.send_error(404)

    # ── CORS preflight ────────────────────────────────────────────────────────

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _serve_file(self, path):
        try:
            with open(path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self.send_error(404, f"File not found: {path}")

    def _proxy_get(self, url, extra_headers=None):
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            if extra_headers:
                headers.update(extra_headers)
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(str(e).encode())

    def _proxy_post(self, url, body):
        try:
            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(str(e).encode())

    def log_message(self, fmt, *args):
        print(fmt % args)


print(f"Serving on port {PORT}")
print(f"  /        → {INDEX_HTML}")
print(f"  /course  → {COURSE_HTML}")
print(f"  /btc     → {BTC_HTML}")
http.server.HTTPServer(("", PORT), CombinedHandler).serve_forever()
