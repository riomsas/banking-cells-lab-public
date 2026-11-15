# Copyright 2026 Consulting RIOM S.A.S.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Local HTTP API for a strictly synthetic lab. Bind to loopback only."""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from .platform import DomainError, Laboratory
from .cells import SERVICE_DOMAINS


STATIC_RESOURCES = {
    "/": ("web/index.html", "text/html; charset=utf-8"),
    "/app.css": ("web/app.css", "text/css; charset=utf-8"),
    "/app.js": ("web/app.js", "text/javascript; charset=utf-8"),
    "/favicon.svg": ("web/assets/favicon.svg", "image/svg+xml"),
}


def handler_factory(lab):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, data, content_type="application/json; charset=utf-8"):
            body = json.dumps(data).encode("utf-8") if isinstance(data, (dict, list)) else data
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _dispatch(self):
            path = urlsplit(self.path).path
            params = parse_qs(urlsplit(self.path).query)
            if self.command == "GET" and path in STATIC_RESOURCES:
                rel_path, mime = STATIC_RESOURCES[path]
                self._send(200, (Path(__file__).parent / rel_path).read_bytes(), mime)
            elif self.command == "GET" and path == "/api/health":
                self._send(200, {"status": "ok", "synthetic": True})
            elif self.command == "GET" and path == "/api/domains":
                self._send(200, sorted(SERVICE_DOMAINS))
            elif self.command == "GET" and path == "/api/cells":
                self._send(200, lab.cells())
            elif self.command == "GET" and path.startswith("/api/cells/"):
                self._send(200, lab._cell(path.removeprefix("/api/cells/")))
            elif self.command == "GET" and path == "/api/analytics":
                self._send(200, lab.analytics())
            elif self.command == "GET" and path == "/api/simulations":
                self._send(200, lab.simulations())
            elif self.command == "GET" and path == "/api/metrics":
                self._send(200, lab.metrics())
            elif self.command == "GET" and path == "/api/events":
                self._send(200, lab.events(int(params.get("limit", ["100"])[0])))
            elif self.command == "POST" and path.startswith("/api/") :
                raw_length = self.headers.get("Content-Length", "")
                if not raw_length.isdecimal() or not 0 <= int(raw_length) <= 16384:
                    raise DomainError("INVALID_BODY_SIZE", 413)
                if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
                    raise DomainError("JSON_REQUIRED", 415)
                try:
                    payload = json.loads(self.rfile.read(int(raw_length)))
                except (ValueError, UnicodeError):
                    raise DomainError("INVALID_JSON", 400) from None
                if not isinstance(payload, dict):
                    raise DomainError("INVALID_JSON_OBJECT", 400)
                if path == "/api/cells":
                    self._send(201, lab.create_cell(payload))
                elif path.endswith("/transition") and path.startswith("/api/cells/"):
                    cell_id = path[len("/api/cells/"):-len("/transition")].strip("/")
                    self._send(200, lab.transition(cell_id, payload.get("state"), payload.get("reason")))
                elif path.endswith("/capacity") and path.startswith("/api/cells/"):
                    cell_id = path[len("/api/cells/"):-len("/capacity")].strip("/")
                    self._send(200, lab.set_capacity(cell_id, payload.get("capacity"), payload.get("priority")))
                elif path == "/api/routing":
                    self._send(201, lab.route(payload))
                elif path.startswith("/api/requests/") and path.endswith("/complete"):
                    request_id = path[len("/api/requests/"):-len("/complete")].strip("/")
                    self._send(200, lab.complete(request_id))
                elif path == "/api/simulations":
                    self._send(200, lab.simulate(payload))
                else:
                    self._send(404, {"error": "NOT_FOUND"})
            else:
                self._send(404, {"error": "NOT_FOUND"})

        def do_GET(self):
            self._handle()

        def do_POST(self):
            self._handle()

        def _handle(self):
            try:
                self._dispatch()
            except DomainError as ex:
                self._send(ex.status, {"error": ex.code})
            except (ValueError, TypeError):
                self._send(400, {"error": "INVALID_INPUT"})
            except Exception:
                self._send(500, {"error": "INTERNAL_ERROR"})

        def log_message(self, fmt, *args):
            # Avoid logging query strings or synthetic request bodies.
            pass

    return Handler


def serve():
    database = os.environ.get("RIOM_LAB_DB", ":memory:")
    if database != ":memory:":
        path = Path(database).expanduser().resolve()
        if path.is_relative_to(Path(__file__).resolve().parent.parent):
            raise RuntimeError("Operational database must be outside the source repository")
        path.parent.mkdir(parents=True, exist_ok=True)
    lab = Laboratory(database)
    server = HTTPServer(("127.0.0.1", int(os.environ.get("RIOM_LAB_PORT", "8765"))), handler_factory(lab))
    try:
        print("Synthetic lab: http://127.0.0.1:" + str(server.server_port), flush=True)
        server.serve_forever()
    finally:
        server.server_close()
        lab.close()


if __name__ == "__main__":
    serve()
