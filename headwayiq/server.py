"""Lightweight local dashboard server for HeadwayIQ.

Standard-library http.server only (no Flask/FastAPI, no runtime dependency), so
the demo runs fully offline. It binds to localhost and is read-only: it serves a
static page plus two JSON endpoints that call the real recommendation engine.

    GET /                 -> dashboard page
    GET /api/scenarios    -> [{name, title, description}, ...]
    GET /api/recommend?scenario=NAME -> full engine payload

No authentication: this is a localhost-only, read-only demo that exposes only
deterministic computed recommendations (no secrets, no user data, no writes). Do
not bind it to a public interface without adding access control.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import scenarios

WEB = Path(__file__).resolve().parent / "web"


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body, ctype: str) -> None:
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            try:
                self._send(200, (WEB / "index.html").read_bytes(), "text/html; charset=utf-8")
            except FileNotFoundError:
                self._send(500, "index.html missing", "text/plain; charset=utf-8")
            return
        if u.path == "/api/scenarios":
            self._json(scenarios.list_scenarios())
            return
        if u.path == "/api/recommend":
            name = parse_qs(u.query).get("scenario", [""])[0]
            try:
                self._json(scenarios.run(name))
            except KeyError as exc:
                self._json({"error": str(exc)}, 400)
            return
        self._send(404, "not found", "text/plain; charset=utf-8")

    def log_message(self, *args) -> None:  # keep the console quiet
        pass


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"HeadwayIQ dashboard: http://{host}:{port}  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        srv.server_close()


if __name__ == "__main__":
    serve()
