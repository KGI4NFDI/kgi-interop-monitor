"""Raw HTTP exchanges with timings and classified failures.

Every probe request goes through :func:`exchange`. It sends exactly what it is
given, never follows a redirect on its own and never raises for a network or
HTTP problem: the problem is the measurement, so it comes back inside the
:class:`Exchange` record. See docs/decisions/0001-raw-http-client.md.
"""

from __future__ import annotations

import gzip
import http.client
import itertools
import socket
import ssl
import threading
import time
import urllib.parse
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import USER_AGENT

BODY_CAP = 4_000_000
"""Bytes read at most from one response. Probes never need more."""

EXCERPT_CHARS = 400
"""Characters of the body kept as evidence in reports."""

DEFAULT_CONNECT_TIMEOUT = 10.0
DEFAULT_READ_TIMEOUT = 30.0
MAX_REDIRECTS = 3

REFUSAL_STATUSES = frozenset({401, 403, 409, 429})
"""Statuses that mean 'alive but not answering you' (checklist B5)."""


def _ssl_context() -> ssl.SSLContext:
    # Never disable verification: an invalid certificate is a finding.
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:  # pragma: no cover - certifi is a declared dependency
        return ssl.create_default_context()


SSL_CONTEXT = _ssl_context()


@dataclass
class Timings:
    """Milliseconds per phase. ``connect_ms`` includes the TLS handshake."""

    dns_ms: float | None = None
    connect_ms: float | None = None
    ttfb_ms: float | None = None
    total_ms: float | None = None

    def as_dict(self) -> dict:
        return {k: (round(v, 1) if v is not None else None) for k, v in self.__dict__.items()}


@dataclass
class Exchange:
    """One HTTP request and whatever came back, including nothing."""

    id: str
    method: str
    url: str
    request_headers: dict[str, str]
    request_body: bytes | None
    purpose: str = ""
    started_at: str = ""
    status: int | None = None
    reason: str = ""
    response_headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    body_truncated: bool = False
    error_class: str | None = None
    error_detail: str = ""
    timings: Timings = field(default_factory=Timings)
    tls_not_after: str | None = None

    @property
    def ok_transport(self) -> bool:
        """True when an HTTP response was received at all."""
        return self.error_class is None and self.status is not None

    @property
    def content_type(self) -> str:
        return self.response_headers.get("content-type", "")

    @property
    def media_type(self) -> str:
        return self.content_type.split(";", 1)[0].strip().lower()

    def text(self) -> str:
        charset = "utf-8"
        for part in self.content_type.split(";")[1:]:
            key, _, value = part.partition("=")
            if key.strip().lower() == "charset" and value.strip():
                charset = value.strip().strip('"')
        try:
            return self.body.decode(charset, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")

    def excerpt(self, limit: int = EXCERPT_CHARS) -> str:
        return " ".join(self.text()[: limit * 2].split())[:limit]

    def evidence(self) -> dict:
        """JSON-serialisable record without the full body."""
        body = self.request_body or b""
        return {
            "id": self.id,
            "purpose": self.purpose,
            "started_at": self.started_at,
            "request": {
                "method": self.method,
                "url": self.url,
                "headers": {k: v for k, v in self.request_headers.items() if k.lower() != "user-agent"},
                "body": body[:EXCERPT_CHARS].decode("utf-8", errors="replace") if body else None,
            },
            "response": {
                "status": self.status,
                "reason": self.reason,
                "content_type": self.content_type or None,
                "server": self.response_headers.get("server"),
                "location": self.response_headers.get("location"),
                "body_excerpt": self.excerpt() if self.body else None,
                "body_bytes": len(self.body),
                "body_truncated": self.body_truncated,
            },
            "error": {"class": self.error_class, "detail": self.error_detail} if self.error_class else None,
            "timings": self.timings.as_dict(),
            "tls_not_after": self.tls_not_after,
        }


_ids = itertools.count(1)
_ids_lock = threading.Lock()


def _next_id() -> str:
    with _ids_lock:
        return f"x{next(_ids):05d}"


class HostPacer:
    """At most one request in flight per host, with a pause between requests.

    Several registry records share a host (six sit on data.gesis.org), so
    politeness has to be enforced per host, not per record
    (docs/decisions/0004-politeness-budget.md).
    """

    def __init__(self, min_interval: float = 0.25) -> None:
        self.min_interval = min_interval
        self._locks: dict[str, threading.Lock] = {}
        self._last: dict[str, float] = {}
        self._guard = threading.Lock()

    def _lock_for(self, host: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(host, threading.Lock())

    def __call__(self, host: str) -> "_Slot":
        return _Slot(self, host)


class _Slot:
    def __init__(self, pacer: HostPacer, host: str) -> None:
        self.pacer, self.host = pacer, host
        self.lock = pacer._lock_for(host)

    def __enter__(self) -> None:
        self.lock.acquire()
        wait = self.pacer._last.get(self.host, 0.0) + self.pacer.min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)

    def __exit__(self, *exc) -> None:
        self.pacer._last[self.host] = time.monotonic()
        self.lock.release()


PACER = HostPacer()


def _classify_ssl(exc: ssl.SSLError) -> tuple[str, str]:
    if isinstance(exc, ssl.SSLCertVerificationError):
        message = (exc.verify_message or str(exc)).lower()
        if "expired" in message:
            return "tls-expired", exc.verify_message or str(exc)
        if "hostname" in message or "ip address mismatch" in message:
            return "tls-hostname", exc.verify_message or str(exc)
        return "tls-untrusted", exc.verify_message or str(exc)
    return "tls", str(exc)


def _classify_os_error(exc: BaseException, phase: str) -> tuple[str, str]:
    if isinstance(exc, ssl.SSLError):
        return _classify_ssl(exc)
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return f"timeout-{phase}", f"no answer within the {phase} timeout"
    if isinstance(exc, ConnectionRefusedError):
        return "refused", "connection refused, nothing listens on that port"
    if isinstance(exc, ConnectionResetError):
        return "reset", "connection reset by the server"
    if isinstance(exc, (http.client.RemoteDisconnected, http.client.BadStatusLine)):
        return "protocol", f"{type(exc).__name__}: {exc}"
    if isinstance(exc, http.client.HTTPException):
        return "protocol", f"{type(exc).__name__}: {exc}"
    return "network", f"{type(exc).__name__}: {exc}"


def _decode_body(data: bytes, headers: dict[str, str]) -> bytes:
    encoding = headers.get("content-encoding", "").lower()
    try:
        if encoding == "gzip":
            return gzip.decompress(data)
        if encoding == "deflate":
            return zlib.decompress(data)
    except (OSError, zlib.error):
        return data
    return data


def exchange(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    purpose: str = "",
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
    read_timeout: float = DEFAULT_READ_TIMEOUT,
    pacer: HostPacer | None = PACER,
) -> Exchange:
    """Send one request and return what happened. Never raises for I/O."""
    request_headers = {"User-Agent": USER_AGENT}
    request_headers.update(headers or {})
    record = Exchange(
        id=_next_id(),
        method=method,
        url=url,
        request_headers=request_headers,
        request_body=body,
        purpose=purpose,
        started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )

    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        record.error_class, record.error_detail = "invalid-url", f"not an absolute http(s) URL: {url!r}"
        return record
    host = parts.hostname
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        record.error_class, record.error_detail = "invalid-url", f"bad port in {url!r}"
        return record
    target = urllib.parse.urlunsplit(("", "", parts.path or "/", parts.query, ""))

    slot = pacer(host) if pacer else _NullSlot()
    with slot:
        started = time.perf_counter()
        try:
            socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            record.error_class, record.error_detail = "dns", f"hostname does not resolve: {exc}"
            record.timings.total_ms = (time.perf_counter() - started) * 1000
            return record
        except OSError as exc:  # pragma: no cover - rare resolver failures
            record.error_class, record.error_detail = "dns", str(exc)
            return record
        record.timings.dns_ms = (time.perf_counter() - started) * 1000

        if parts.scheme == "https":
            conn: http.client.HTTPConnection = http.client.HTTPSConnection(
                host, port, timeout=connect_timeout, context=SSL_CONTEXT
            )
        else:
            conn = http.client.HTTPConnection(host, port, timeout=connect_timeout)
        try:
            t_connect = time.perf_counter()
            try:
                conn.connect()
            except (OSError, http.client.HTTPException) as exc:
                record.error_class, record.error_detail = _classify_os_error(exc, "connect")
                return record
            record.timings.connect_ms = (time.perf_counter() - t_connect) * 1000
            if isinstance(conn.sock, ssl.SSLSocket):
                try:
                    cert = conn.sock.getpeercert()
                    if cert and cert.get("notAfter"):
                        record.tls_not_after = datetime.fromtimestamp(
                            ssl.cert_time_to_seconds(cert["notAfter"]), tz=timezone.utc
                        ).date().isoformat()
                except (ValueError, OSError):
                    pass
            conn.sock.settimeout(read_timeout)

            t_request = time.perf_counter()
            try:
                conn.request(method, target, body=body, headers=request_headers)
                response = conn.getresponse()
                record.timings.ttfb_ms = (time.perf_counter() - t_request) * 1000
                record.status, record.reason = response.status, response.reason
                merged: dict[str, str] = {}
                for key, value in response.getheaders():
                    key = key.lower()
                    merged[key] = f"{merged[key]}, {value}" if key in merged else value
                record.response_headers = merged
                chunks, size = [], 0
                while size <= BODY_CAP:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                record.body_truncated = size > BODY_CAP
                record.body = _decode_body(b"".join(chunks)[:BODY_CAP], merged)
            except (OSError, http.client.HTTPException) as exc:
                record.error_class, record.error_detail = _classify_os_error(exc, "read")
                if record.status is not None and record.error_class.startswith("timeout"):
                    record.error_detail = "headers arrived, body did not finish within the read timeout"
        finally:
            conn.close()
            record.timings.total_ms = (time.perf_counter() - started) * 1000
    return record


class _NullSlot:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *exc) -> None:
        return None


def follow(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    purpose: str = "",
    max_redirects: int = MAX_REDIRECTS,
    **kwargs,
) -> list[Exchange]:
    """Send a request and follow redirects one hop at a time.

    Every hop keeps the method and body, including after a 303. That is what a
    careful SPARQL client has to do, because the classic behaviour of turning a
    redirected POST into a GET throws the query away. The caller gets every hop,
    so a redirect is always visible as a finding.
    """
    hops = [exchange(method, url, headers=headers, body=body, purpose=purpose, **kwargs)]
    while (
        len(hops) <= max_redirects
        and hops[-1].status in (301, 302, 303, 307, 308)
        and hops[-1].response_headers.get("location")
    ):
        next_url = urllib.parse.urljoin(hops[-1].url, hops[-1].response_headers["location"])
        hops.append(exchange(method, next_url, headers=headers, body=body, purpose=purpose, **kwargs))
    return hops
