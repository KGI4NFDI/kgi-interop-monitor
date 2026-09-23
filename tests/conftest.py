from __future__ import annotations

import socket
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from kgi_interop_monitor import transport


@contextmanager
def serve(handler: type[BaseHTTPRequestHandler]):
    """Run a threaded HTTP server on a free localhost port for one test."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def free_port() -> int:
    """A port that nothing listens on (bound, read, released)."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(autouse=True)
def no_pacing(monkeypatch):
    """Tests talk to localhost only; pacing would just slow them down."""
    monkeypatch.setattr(transport.PACER, "min_interval", 0.0)
