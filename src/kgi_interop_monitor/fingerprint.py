"""Which engine is behind an endpoint, inferred from what it sends back.

Used to *explain* results, never to change what a probe sends (ADR 0002).
Each signature names the evidence it came from, so the table can be checked
and extended. An endpoint that matches nothing is reported as unknown rather
than guessed.

Sources, strongest first: the ``Server`` header, the body of an error
response (the malformed query from B2 is the best trigger), then URL shape.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .transport import Exchange


@dataclass(frozen=True)
class Signature:
    engine: str
    source: str  # header | body | url
    pattern: re.Pattern
    evidence: str


def _sig(engine: str, source: str, pattern: str, evidence: str) -> Signature:
    return Signature(engine, source, re.compile(pattern, re.I | re.S), evidence)


SIGNATURES: list[Signature] = [
    # Server header
    _sig("Virtuoso", "header", r"Virtuoso/(?P<version>[\w.\-]+)", "Server header of OpenLink Virtuoso"),
    _sig("Apache Jena Fuseki", "header", r"(?:Apache Jena )?Fuseki(?: \(?(?P<version>[\d.]+))?", "Server header of Fuseki"),
    _sig("Oxigraph", "header", r"Oxigraph(?:/(?P<version>[\w.\-]+))?", "Server header of Oxigraph"),
    _sig("GraphDB", "header", r"GraphDB", "Server header of Ontotext GraphDB"),
    _sig("AllegroGraph", "header", r"AllegroServe", "AllegroGraph's HTTP server"),
    _sig("Stardog", "header", r"Stardog", "Server header of Stardog"),
    _sig("Blazegraph", "header", r"blazegraph|bigdata", "Server header of Blazegraph"),
    # Error bodies (captured examples in tests/fixtures/live)
    _sig("Virtuoso", "body", r"Virtuoso \d+ Error|\bSP0\d\d\b|\bSQ\d{3}\b",
         "Virtuoso error codes, e.g. 'Virtuoso 37000 Error SP030' (MatWerk, 2026-09-23)"),
    _sig("QLever", "body", r"Invalid SPARQL query: ", "QLever parse error in a JSON 'exception' (KGI hub, 2026-09-23)"),
    _sig("Blazegraph", "body", r"com\.bigdata\.|org\.openrdf\.",
         "Blazegraph / Sesame 2 stack trace (Wikidata Query Service, 2026-09-23)"),
    _sig("RDF4J or GraphDB", "body", r"org\.eclipse\.rdf4j|MALFORMED QUERY", "Eclipse RDF4J parser error"),
    _sig("Apache Jena Fuseki", "body", r"org\.apache\.jena|Error 400: (?:Parse|Lexical) error", "Jena ARQ parse error"),
    _sig("Stardog", "body", r"com\.complexible\.stardog", "Stardog stack trace"),
    # URL shape
    _sig("Blazegraph", "url", r"/bigdata/(?:namespace/[^/]+/)?sparql", "Blazegraph REST path"),
    _sig("RDF4J or GraphDB", "url", r"/repositories/[^/?#]+", "RDF4J repository path"),
]

RANK = {"header": 0, "body": 1, "url": 2}


def _error_like(x: Exchange) -> bool:
    """Only error responses are read for signatures: a successful result can
    contain any text as data, including another engine's error code."""
    if not x.body:
        return False
    if x.status is not None and x.status >= 400:
        return True
    head = x.body[:200].lstrip()
    return x.purpose.startswith("B2") or head.startswith(b'{"error"') or head.startswith(b'{"exception"')


def identify(exchanges: list[Exchange]) -> dict:
    """Best guess over all exchanges of one endpoint."""
    hits: list[tuple[int, Signature, str | None, str]] = []
    for x in exchanges:
        server = x.response_headers.get("server", "")
        for sig in SIGNATURES:
            if sig.source == "header" and server:
                m = sig.pattern.search(server)
            elif sig.source == "body" and _error_like(x):
                m = sig.pattern.search(x.text()[:20000])
            elif sig.source == "url":
                m = sig.pattern.search(x.url)
            else:
                m = None
            if m:
                version = m.groupdict().get("version") if m.groupdict() else None
                where = f"Server: {server}" if sig.source == "header" else x.id
                hits.append((RANK[sig.source], sig, version, where))
    if not hits:
        servers = sorted({x.response_headers.get("server") for x in exchanges if x.response_headers.get("server")})
        return {"engine": None, "version": None, "source": None, "evidence": None, "server_headers": servers}
    hits.sort(key=lambda h: h[0])
    rank, sig, version, where = hits[0]
    engines = sorted({h[1].engine for h in hits})
    return {
        "engine": sig.engine,
        "version": version,
        "source": sig.source,
        "evidence": f"{sig.evidence} ({where})",
        "also_matched": [e for e in engines if e != sig.engine],
    }
