"""Replay a response captured from a live endpoint.

Fixtures in tests/fixtures/live/ are real responses, captured on the date in
their file name with the capture code in the commit that added them. Replaying
them keeps the tests honest about what endpoints actually send, without
touching the network.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "live"

SKIP_HEADERS = {"content-length", "transfer-encoding", "connection", "content-encoding", "date"}


def load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def replay_handler(fixture: dict) -> type[BaseHTTPRequestHandler]:
    response = fixture["response"]
    body = response["body"].encode("utf-8")

    class Replay(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def version_string(self):
            return response["headers"].get("server", "")

        def _answer(self):
            length = int(self.headers.get("Content-Length", 0) or 0)
            if length:
                self.rfile.read(length)
            self.send_response(response["status"])
            for key, value in response["headers"].items():
                if key not in SKIP_HEADERS and key != "server":
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = _answer
        do_POST = _answer

    return Replay
