#!/usr/bin/env python3
"""Local dev server with CORS proxy for Deribit API calls. Uses local SQLite instead of Convex."""

import http.server
import urllib.request
import urllib.parse
import os, json, threading
import db

PORT = int(os.environ.get("PORT", 8080))
DERIBIT_BASE = "https://www.deribit.com"
BYBIT_BASE   = "https://api.bybit.com"

class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/proxy/bybit/"):
            target = BYBIT_BASE + self.path[len("/proxy/bybit"):]
            try:
                req = urllib.request.Request(target, headers={"User-Agent": "Mozilla/5.0", "X-Referer": "bybit-skill"})
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
        elif self.path.startswith("/proxy/deribit/"):
            # Strip /proxy/deribit prefix and forward to Deribit
            target = DERIBIT_BASE + self.path[len("/proxy/deribit"):]
            try:
                req = urllib.request.Request(target, headers={"User-Agent": "Mozilla/5.0"})
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
        else:
            super().do_GET()

    def do_POST(self):
        if self.path.startswith("/proxy/convex/api/"):
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            path = body.get("path", "")
            args = body.get("args", {})
            try:
                if path == "candles:getAll":
                    value = db.get_all()
                elif path == "candles:append":
                    db.append(args["name"], args["newTicks"], args["newCloses"])
                    value = None
                else:
                    raise ValueError(f"Unknown path: {path}")
                resp = json.dumps({"status": "success", "value": value}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                self.send_response(500)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "errorMessage": str(e)}).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, fmt, *args):
        print(fmt % args)

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Start fetcher in background thread
import fetcher
t = threading.Thread(target=fetcher.main, daemon=True)
t.start()

print(f"Serving on http://localhost:{PORT}")
http.server.HTTPServer(("", PORT), ProxyHandler).serve_forever()
