from __future__ import annotations

import gzip
import time
from http.server import BaseHTTPRequestHandler

from kgi_interop_monitor import USER_AGENT
from kgi_interop_monitor.transport import exchange, follow

from .conftest import free_port, serve


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep test output quiet
        pass

    def version_string(self):
        return "Toy/1.0"

    def _reply(self, status, body=b"", headers=None):
        self.send_response(status)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/ok":
            self._reply(200, b"hello", {"Content-Type": "text/plain; charset=utf-8"})
        elif self.path == "/echo-agent":
            self._reply(200, self.headers.get("User-Agent", "").encode())
        elif self.path == "/moved":
            self._reply(301, b"", {"Location": "/ok"})
        elif self.path == "/loop":
            self._reply(302, b"", {"Location": "/loop"})
        elif self.path == "/gzip":
            self._reply(200, gzip.compress(b"compressed"), {"Content-Encoding": "gzip"})
        elif self.path == "/slow":
            time.sleep(1.5)
            self._reply(200, b"late")
        else:
            self._reply(404, b"no such path")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(length)
        if self.path == "/moved":
            self._reply(307, b"", {"Location": "/echo-post"})
        else:
            self._reply(200, b"got:" + data, {"X-Content-Type-Seen": self.headers.get("Content-Type", "none")})


def test_success_records_status_headers_body_and_timings():
    with serve(Handler) as base:
        x = exchange("GET", base + "/ok")
    assert x.ok_transport and x.status == 200
    assert x.text() == "hello"
    assert x.response_headers["server"] == "Toy/1.0"
    assert x.media_type == "text/plain"
    assert x.timings.connect_ms is not None and x.timings.ttfb_ms is not None
    assert x.timings.total_ms >= x.timings.ttfb_ms


def test_identifies_itself():
    with serve(Handler) as base:
        x = exchange("GET", base + "/echo-agent")
    assert x.text() == USER_AGENT


def test_http_errors_are_results_not_exceptions():
    with serve(Handler) as base:
        x = exchange("GET", base + "/missing")
    assert x.status == 404 and x.error_class is None


def test_redirects_are_not_followed_implicitly():
    with serve(Handler) as base:
        x = exchange("GET", base + "/moved")
    assert x.status == 301 and x.response_headers["location"] == "/ok"


def test_follow_keeps_every_hop():
    with serve(Handler) as base:
        hops = follow("GET", base + "/moved")
    assert [h.status for h in hops] == [301, 200]
    assert hops[-1].text() == "hello"


def test_follow_keeps_method_and_body():
    with serve(Handler) as base:
        hops = follow("POST", base + "/moved", body=b"query=ASK", headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert [h.status for h in hops] == [307, 200]
    assert hops[-1].text() == "got:query=ASK"


def test_follow_stops_on_a_loop():
    with serve(Handler) as base:
        hops = follow("GET", base + "/loop", max_redirects=3)
    assert len(hops) == 4 and all(h.status == 302 for h in hops)


def test_body_without_content_type_is_sent_as_is():
    # Needed for the W3C negative tests that omit the media type on purpose.
    with serve(Handler) as base:
        x = exchange("POST", base + "/echo-post", body=b"ASK {}")
    assert x.response_headers["x-content-type-seen"] == "none"


def test_gzip_body_is_decoded():
    with serve(Handler) as base:
        x = exchange("GET", base + "/gzip")
    assert x.body == b"compressed"


def test_refused_connection_is_classified():
    x = exchange("GET", f"http://127.0.0.1:{free_port()}/sparql")
    assert x.status is None and x.error_class == "refused"


def test_unresolvable_host_is_classified():
    x = exchange("GET", "http://no-such-host.invalid/sparql")
    assert x.error_class == "dns"


def test_read_timeout_is_classified():
    with serve(Handler) as base:
        x = exchange("GET", base + "/slow", read_timeout=0.3)
    assert x.error_class == "timeout-read"


def test_prose_is_not_a_url():
    x = exchange("GET", "work in progress")
    assert x.error_class == "invalid-url"


def test_evidence_is_serialisable_and_hides_the_user_agent():
    import json

    with serve(Handler) as base:
        x = exchange("GET", base + "/ok", purpose="test")
    ev = x.evidence()
    json.dumps(ev)
    assert "User-Agent" not in ev["request"]["headers"]
    assert ev["response"]["body_excerpt"] == "hello"
    assert ev["purpose"] == "test"
