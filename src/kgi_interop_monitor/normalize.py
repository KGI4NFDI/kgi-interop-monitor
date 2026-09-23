"""What a registry endpoint value contains, and where the endpoint might be.

Two jobs, both pure functions without network access:

1. :func:`parse_value` reads a raw dcat:endpointURL value. It finds prose
   ("work in progress"), several URLs packed into one value ("a; b") and UI
   routes after a fragment (Fuseki's "#/dataset/<name>/query").
2. :func:`candidates` proposes URLs where the actual SPARQL endpoint may sit
   when the registered one does not answer (checklist A7). Registries store
   what a human copied from a browser: the query UI or the host root, not the
   protocol endpoint. Every candidate is a *proposal*; it can land on a
   different service on the same host, so a human confirms it before the
   registry is changed.
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field

URL_RE = re.compile(r"https?://[^\s;,<>\"'|]+", re.I)

UI_TAILS = ("query", "query.html", "sparql-ui", "yasgui", "snorql", "sparql-assistent", "sparql-endpoint", "ui", "#")
"""Last path segments that usually name a query web page, not the endpoint."""

MAX_CANDIDATES = 10


@dataclass
class ParsedValue:
    raw: str
    urls: list[str] = field(default_factory=list)

    @property
    def is_prose(self) -> bool:
        return not self.urls

    @property
    def is_packed(self) -> bool:
        return len(self.urls) > 1

    @property
    def is_single_url(self) -> bool:
        return len(self.urls) == 1 and self.urls[0] == self.raw.strip()

    @property
    def has_extra_text(self) -> bool:
        """One URL, but surrounded by other characters (quotes, a label, ...)."""
        return len(self.urls) == 1 and not self.is_single_url


def parse_value(raw: str) -> ParsedValue:
    urls = []
    for match in URL_RE.findall(raw or ""):
        url = match.rstrip(".)")
        if url not in urls:
            urls.append(url)
    return ParsedValue(raw=raw or "", urls=urls)


def canonical(url: str) -> str:
    """Comparison key: case-folded scheme and host, no default port, no
    fragment, no trailing slash. Used to spot duplicate records (A6)."""
    parts = urllib.parse.urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    port = parts.port
    if port and not ((parts.scheme == "http" and port == 80) or (parts.scheme == "https" and port == 443)):
        host = f"{host}:{port}"
    path = parts.path.rstrip("/")
    query = f"?{parts.query}" if parts.query else ""
    return f"{parts.scheme.lower()}://{host}{path}{query}"


def title_key(title: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", (title or "").casefold())


def candidates(url: str) -> list[str]:
    """Where else the SPARQL endpoint of ``url`` may be, most likely first."""
    parts = urllib.parse.urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return []
    root = f"{parts.scheme}://{parts.netloc}"
    path = parts.path.rstrip("/")
    out: list[str] = []

    def add(candidate: str) -> None:
        # A trailing-slash variant of the registered URL is a real candidate:
        # some servers answer on /sparql but not /sparql/, or the reverse.
        if candidate != url.strip() and candidate not in out:
            out.append(candidate)

    # A UI route after the fragment, as in Fuseki: "#/dataset/<name>/query".
    fuseki = re.match(r"/?dataset/([^/]+)/(query|sparql|info|edit|upload)", parts.fragment or "")
    if fuseki:
        add(f"{root}{path}/{fuseki.group(1)}/sparql")
        add(f"{root}{path}/{fuseki.group(1)}/query")
    if parts.fragment or parts.query:
        add(f"{root}{path or '/'}")

    segments = [s for s in path.split("/") if s]
    tail = segments[-1].lower() if segments else ""
    parent = "/" + "/".join(segments[:-1]) if segments else ""
    parent = parent.rstrip("/")

    if tail in UI_TAILS or tail.endswith(".html"):
        add(f"{root}{parent}/sparql")
        add(f"{root}{parent}")
    if tail != "sparql":
        add(f"{root}{path}/sparql")
    add(f"{root}{path}/" if path else f"{root}/")
    if path:
        add(f"{root}{path}")
    # Wikibase query services: UI at the host root or /query, endpoint at
    # /sparql, with the Blazegraph path as the historical alternative.
    if (parts.hostname or "").startswith("query.") or tail == "query":
        add(f"{root}/sparql")
        add(f"{root}/bigdata/namespace/wdq/sparql")
    add(f"{root}/sparql")
    # Fuseki-style services answer on /query (Nomisma does, next to a UI at
    # /sparql/). A query web page there just fails the check, cheaply.
    add(f"{root}/query")
    # QLever UI deployments serve the API under /api/.
    add(f"{root}/api/")
    if parts.scheme == "http":
        add(urllib.parse.urlunsplit(("https",) + tuple(parts[1:4]) + ("",)))
    return out[:MAX_CANDIDATES]
