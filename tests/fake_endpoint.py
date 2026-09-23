"""A local SPARQL server with switchable defects, plus a fake registry.

Each path prefix behaves like one kind of endpoint found in the KGI registry.
Queries are evaluated for real by rdflib, so probes see realistic answers, and
the defects are layered on top at the HTTP level. This is the seeded-defect
idea from the parked instrument/ design study: every checklist row gets an
endpoint that is known to have that defect, and one that is known not to.

| prefix           | behaves like                                           |
|------------------|--------------------------------------------------------|
| /healthy/sparql  | a clean endpoint, all three request forms, 4 formats   |
| /virtuoso/sparql | 200 + error body on form POST and on syntax errors     |
| /ui/             | a query web page, never SPARQL (A3)                    |
| /wikibase/query/ | UI at /query/, endpoint at /wikibase/sparql (A7)       |
| /refuse/sparql   | HTTP 409 for everything (B5)                           |
| /gone/sparql     | HTTP 404 (A4)                                          |
| /slow/sparql     | answers after a delay                                  |
| /moved/sparql    | 301 to /healthy/sparql                                 |
| /empty/sparql    | a clean endpoint over an empty store (C1)              |
| /messy/sparql    | union default graph with a scratch graph, owl:Nothing  |
|                  | subsumptions and an old ontology version (C2, C3, C4)  |
| /hub/sparql      | a federation hub: bound SERVICE works, SERVICE ?var is |
|                  | rejected like QLever does (B4)                         |
| /registry/sparql | a DCAT registry describing all of the above            |
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from rdflib import Dataset, Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCAT, DCTERMS, OWL, RDF, RDFS

EX = Namespace("http://example.org/")
NFDI = Namespace("https://nfdi.fiz-karlsruhe.de/ontology/")

MEDIA_FOR = {
    "json": "application/sparql-results+json",
    "xml": "application/sparql-results+xml",
    "csv": "text/csv",
    "tsv": "text/tab-separated-values",
}


def healthy_data() -> Dataset:
    ds = Dataset()
    g = ds.default_graph
    for i in range(20):
        g.add((EX[f"thing{i}"], RDF.type, EX.Thing))
        g.add((EX[f"thing{i}"], RDFS.label, Literal(f"thing {i}")))
    return ds


def messy_data() -> Dataset:
    """Union default graph: release graph, scratch graph, inference graph."""
    ds = Dataset(default_union=True)
    release = ds.graph(URIRef("https://kg.example/graph/mwo/3.0.1"))
    release.add((URIRef("http://purls.example/mwo"), RDF.type, OWL.Ontology))
    release.add((URIRef("http://purls.example/mwo"), OWL.versionIRI, URIRef("http://purls.example/mwo/3.0.1")))
    for i in range(10):
        cls = NFDI[f"NFDI_{i:07d}"]
        release.add((cls, RDF.type, OWL.Class))
        release.add((cls, RDFS.label, Literal(f"class {i}")))
    scratch = ds.graph(URIRef("https://kg.example/graph/scratch-test"))
    for i in range(3):
        scratch.add((OWL.Nothing, RDFS.subClassOf, NFDI[f"NFDI_{i:07d}"]))
    inferred = ds.graph(URIRef("https://kg.example/graph/spreadsheets_inferences"))
    inferred.add((NFDI["NFDI_0000001"], RDFS.subClassOf, NFDI["NFDI_0000001"]))
    return ds


def registry_data(base: str) -> Graph:
    """A small DCAT registry pointing at the fake endpoints."""
    g = Graph()
    kgr = Namespace("http://kgi.example/entity/")

    def record(ident, title, endpoint=None, download=None, landing=None):
        ds = kgr[ident]
        g.add((ds, RDF.type, DCAT.Dataset))
        g.add((ds, DCTERMS.title, Literal(title)))
        if landing:
            g.add((ds, DCAT.landingPage, URIRef(landing)))
        if endpoint is not None:
            svc = kgr[f"{ident}_service"]
            g.add((svc, RDF.type, DCAT.DataService))
            g.add((svc, DCAT.servesDataset, ds))
            g.add((svc, DCAT.endpointURL, Literal(endpoint)))  # a literal, as in the real registry
        if download:
            dist = kgr[f"{ident}_dist"]
            g.add((ds, DCAT.distribution, dist))
            g.add((dist, DCAT.downloadURL, URIRef(download)))

    record("KGR1", "Healthy KG", f"{base}/healthy/sparql", landing="https://healthy.example")
    record("KGR2", "Virtuoso KG", f"{base}/virtuoso/sparql")
    record("KGR3", "UI Only KG", f"{base}/ui/")
    record("KGR4", "Wikibase KG", f"{base}/wikibase/query/")
    record("KGR5", "Refusing KG", f"{base}/refuse/sparql")
    record("KGR6", "Gone KG", f"{base}/gone/sparql")
    record("KGR7", "Empty KG", f"{base}/empty/sparql")
    record("KGR8", "Messy KG", f"{base}/messy/sparql")
    record("KGR9", "Prose KG", "work in progress", download="https://dumps.example/prose.nt")
    record("KGR10", "Dump Only KG", None, download="https://dumps.example/dump.nt")
    record("KGR11", "Nothing KG", None)
    record("KGR12", "Healthy KG", f"{base}/healthy/sparql/", landing="https://healthy.example")
    record("KGR13", "Moved KG", f"{base}/moved/sparql")
    return g


class FakeEndpoints:
    """Start with ``with FakeEndpoints() as fake: fake.url('/healthy/sparql')``."""

    def __init__(self, slow_seconds: float = 2.0) -> None:
        self.slow_seconds = slow_seconds
        self.stores = {
            "healthy": healthy_data(),
            "virtuoso": healthy_data(),
            "empty": Dataset(),
            "messy": messy_data(),
            "slow": healthy_data(),
            "wikibase": healthy_data(),
        }
        self.requests: list[tuple[str, str]] = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.server.daemon_threads = True
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        registry = Dataset()
        registry.default_graph += registry_data(self.base)
        self.stores["registry"] = registry
        self.stores["hub"] = registry

    def url(self, path: str) -> str:
        return self.base + path

    def __enter__(self) -> "FakeEndpoints":
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc) -> None:
        self.server.shutdown()
        self.server.server_close()

    # ------------------------------------------------------------------ http

    def _handler(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def version_string(self):
                return "Virtuoso/07.20.3237 (Linux) x86_64" if self.path.startswith("/virtuoso") else "FakeSPARQL/1.0"

            def reply(self, status, body, content_type="text/plain; charset=utf-8", headers=None):
                data = body.encode("utf-8") if isinstance(body, str) else body
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                self.route("GET")

            def do_POST(self):
                self.route("POST")

            def do_PUT(self):
                self.reply(405, "method not allowed")

            def route(self, method):
                parts = urllib.parse.urlsplit(self.path)
                length = int(self.headers.get("Content-Length", 0) or 0)
                body = self.rfile.read(length) if length else b""
                fake.requests.append((method, self.path))
                path = parts.path
                if path.startswith("/ui/") or path.startswith("/wikibase/query"):
                    return self.reply(200, "<!DOCTYPE html><html><body>Query UI</body></html>", "text/html")
                if path.startswith("/refuse/"):
                    return self.reply(409, "Conflict")
                if path.startswith("/gone/"):
                    return self.reply(404, "Not Found")
                if path.startswith("/moved/"):
                    return self.reply(301, "", headers={"Location": "/healthy/sparql"})
                store_name = path.strip("/").split("/")[0]
                if path.startswith("/wikibase/sparql"):
                    store_name = "wikibase"
                if store_name not in fake.stores or not (path.endswith("/sparql") or path.endswith("/sparql/")):
                    return self.reply(404, "Unknown path")
                if store_name == "slow":
                    time.sleep(fake.slow_seconds)

                query, error = self.extract_query(method, parts.query, body)
                if error:
                    return self.reply(400, error)
                if query is None:
                    return self.reply(400, "no query")
                if store_name == "virtuoso" and method == "POST" and self.headers.get("Content-Type", "").startswith(
                        "application/x-www-form-urlencoded"):
                    return self.reply(200, json.dumps({"error": "Virtuoso 37000 Error SP030: SPARQL compiler, line 0: "
                                                                "Bad character '%' (0x25) in SPARQL expression at '%'"}),
                                      "application/sparql-results+json")
                if store_name == "hub":
                    return self.hub(query)
                self.evaluate(fake.stores[store_name], query, virtuoso=store_name == "virtuoso")

            def extract_query(self, method, query_string, body):
                params = urllib.parse.parse_qs(query_string)
                ctype = self.headers.get("Content-Type", "")
                if method == "GET":
                    queries = params.get("query", [])
                    if len(queries) > 1:
                        return None, "more than one query string"
                    return (queries[0] if queries else None), None
                if ctype.startswith("application/x-www-form-urlencoded"):
                    queries = urllib.parse.parse_qs(body.decode("ascii", "replace")).get("query", [])
                    if len(queries) != 1:
                        return None, "expected exactly one query parameter"
                    return queries[0], None
                if ctype.startswith("application/sparql-query"):
                    if "charset" in ctype.lower() and "utf-8" not in ctype.lower():
                        return None, "only UTF-8 is accepted"
                    try:
                        return body.decode("utf-8"), None
                    except UnicodeDecodeError:
                        return None, "body is not UTF-8"
                return None, f"unsupported content type {ctype or '(none)'}"

            def evaluate(self, store, query, virtuoso=False):
                try:
                    result = store.query(query)
                except Exception as exc:  # rdflib parse or evaluation error
                    if virtuoso:
                        return self.reply(200, json.dumps({"error": f"Virtuoso 37000 Error SP030: {exc}"}),
                                          "application/sparql-results+json")
                    return self.reply(400, f"Parse error: {exc}")
                accept = self.headers.get("Accept", "")
                if result.type in ("CONSTRUCT", "DESCRIBE"):
                    return self.reply(200, result.serialize(format="turtle"), "text/turtle")
                fmt = "json"
                for name, media in MEDIA_FOR.items():
                    if media in accept:
                        fmt = name
                        break
                if fmt in ("csv", "tsv") and result.type == "ASK":
                    fmt = "json"
                data = result.serialize(format="txt" if fmt == "tsv" else fmt)
                if fmt == "tsv":
                    data = self.tsv(result)
                return self.reply(200, data, MEDIA_FOR[fmt])

            def tsv(self, result):
                vars_ = [str(v) for v in result.vars]
                lines = ["\t".join("?" + v for v in vars_)]
                for row in result:
                    lines.append("\t".join(term.n3() if term is not None else "" for term in row))
                return ("\n".join(lines) + "\n").encode("utf-8")

            def hub(self, query):
                if re.search(r"SERVICE\s+(SILENT\s+)?\?", query, re.I):
                    return self.reply(400, json.dumps({"exception": "SERVICE with a variable endpoint is not supported"}),
                                      "application/json")
                match = re.search(r"SERVICE\s+(?:SILENT\s+)?<([^>]+)>", query, re.I)
                if not match:
                    return self.evaluate(fake.stores["hub"], query)
                from kgi_interop_monitor.sparql import run_query

                remote = run_query(match.group(1), "SELECT * WHERE { ?s ?p ?o } LIMIT 1", "get", pacer=None)
                if not remote.ok:
                    return self.reply(500, json.dumps({"exception": f"SERVICE request failed: {remote.detail}"}),
                                      "application/json")
                payload = {"head": {"vars": remote.vars}, "results": {"bindings": remote.rows}}
                return self.reply(200, json.dumps(payload), MEDIA_FOR["json"])

        return Handler
