#!/usr/bin/env python3
"""Combined server: /, /course, /btc, /interview"""

import http.server
import urllib.request
import os, importlib.util

PORT = int(os.environ.get("PORT", 8080))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

INDEX_HTML     = os.path.join(BASE_DIR, "index.html")
COURSE_HTML    = os.path.join(BASE_DIR, "6-lesson", "index.html")
BTC_HTML       = os.path.join(BASE_DIR, "4-option", "index.html")
INTERVIEW_HTML = os.path.join(BASE_DIR, "7-interview", "youtube-analyzer.html")

# ── Load interview proxy module ───────────────────────────────────────────────
_itv_mod = None
def _itv():
    global _itv_mod
    if _itv_mod is None:
        spec = importlib.util.spec_from_file_location(
            "interview_proxy",
            os.path.join(BASE_DIR, "7-interview", "proxy_server.py")
        )
        _itv_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_itv_mod)
        _itv_mod.init_db()
    return _itv_mod

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

        elif self.path in ("/interview", "/interview/"):
            self._serve_file(INTERVIEW_HTML)

        elif self.path.startswith("/interview/"):
            self._handle_interview(self.path[len("/interview"):])

        else:
            self._serve_file(INDEX_HTML)

    # ── Proxy POST (Convex) ───────────────────────────────────────────────────

    def do_POST(self):
        if self.path.startswith("/proxy/convex/"):
            target = CONVEX_BASE + "/" + self.path[len("/proxy/convex/"):]
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            self._proxy_post(target, body)
        elif self.path == "/api/ai":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            self._handle_ai(body)
        elif self.path.startswith("/interview/push-audio"):
            from urllib.parse import urlparse as _up, parse_qs as _pqs
            params = _pqs(_up(self.path).query)
            shim = _itv().Handler.__new__(_itv().Handler)
            shim.wfile, shim.headers = self.wfile, self.headers
            shim.send_response, shim.send_header, shim.end_headers = \
                self.send_response, self.send_header, self.end_headers
            shim.rfile = self.rfile
            shim.path  = self.path.replace("/interview", "", 1)
            shim.do_POST()

        elif self.path == "/interview/push":
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            shim   = _itv().Handler.__new__(_itv().Handler)
            shim.wfile, shim.headers = self.wfile, self.headers
            shim.send_response, shim.send_header, shim.end_headers = \
                self.send_response, self.send_header, self.end_headers
            # Reuse do_POST logic by calling it with body already read
            import json as _json
            try:
                data   = _json.loads(body)
                videos = data.get("videos", [])
                mod    = _itv()
                count  = 0
                for v in videos:
                    if v.get("id") and v.get("cues"):
                        mod.db_save(v["id"], v.get("url",""), v.get("title", v["id"]), v["cues"])
                        count += 1
                shim._json(200, {"synced": count})
            except Exception as e:
                shim._json(500, {"error": str(e)})
        else:
            self.send_error(404)

    # ── CORS preflight ────────────────────────────────────────────────────────

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ── Interview (YouTube Analyzer) ─────────────────────────────────────────

    def _handle_interview(self, subpath):
        """Delegate to interview proxy module by creating a shim Handler."""
        try:
            mod = _itv()
        except Exception as e:
            self._json_err(500, f"Interview module failed to load: {e}")
            return

        from urllib.parse import urlparse, parse_qs

        # Build a shim that looks like mod.Handler but uses our wfile/headers
        shim = mod.Handler.__new__(mod.Handler)
        shim.wfile   = self.wfile
        shim.headers = self.headers
        shim.send_response  = self.send_response
        shim.send_header    = self.send_header
        shim.end_headers    = self.end_headers

        parsed = urlparse(subpath)
        params = parse_qs(parsed.query)
        p = parsed.path

        if p == "/health":
            self._json_ok({"status": "ok"})
        elif p == "/transcript":
            shim._handle_transcript(params)
        elif p == "/history":
            shim._handle_history()
        elif p == "/delete":
            shim._handle_delete(params)
        elif p == "/audio":
            shim._handle_audio(params)
        elif p == "/tts":
            shim._handle_tts(params)
        else:
            self._json_err(404, "Not found")

    def _json_ok(self, obj):
        import json
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _json_err(self, code, msg):
        import json
        body = json.dumps({"error": msg}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

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

    def _handle_ai(self, body):
        import json
        import anthropic
        try:
            data = json.loads(body)
            highlight = data.get("highlight", "")
            question  = data.get("question", "")
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            client = anthropic.Anthropic(api_key=api_key)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            system = (
                "You are an expert AI educator specializing in the Anthropic Claude ecosystem, "
                "agent frameworks, MCP, and AI engineering. Answer questions clearly and concisely, "
                "referencing the highlighted text as context. Use concrete examples where helpful."
            )
            user_msg = f'The user highlighted this text:\n\n"{highlight}"\n\nQuestion: {question}'
            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": user_msg}]
            ) as stream:
                for text in stream.text_stream:
                    self.wfile.write(
                        f'data: {json.dumps({"text": text})}\n\n'.encode()
                    )
                    self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except Exception as e:
            self.wfile.write(
                f'data: {json.dumps({"text": f"Error: {e}"})}\n\ndata: [DONE]\n\n'.encode()
            )
            self.wfile.flush()

    def log_message(self, fmt, *args):
        print(fmt % args)


print(f"Serving on port {PORT}")
print(f"  /        → {INDEX_HTML}")
print(f"  /course  → {COURSE_HTML}")
print(f"  /btc     → {BTC_HTML}")
http.server.HTTPServer(("", PORT), CombinedHandler).serve_forever()
