"""The read-only part of the W3C SPARQL 1.1 Protocol test suite.

The suite (w3c/rdf-tests, sparql/sparql11/protocol/manifest.ttl) has 34
tests. 14 are update tests and 6 need their own test datasets loaded; neither
may be sent to a production endpoint. One more, ``bad_query_method``, sends a
PUT, which on a Graph Store Protocol endpoint can overwrite a graph, so it is
left out too. The remaining 13 run here, adapted in one way: the
``default-graph-uri`` parameter pointing at an external test document is
removed, because some engines dereference it. The score is reported as
``n/13`` next to the layer grade, never folded into it (ADR 0003).

Requests are built byte for byte from the manifest, including the ones that
omit Accept or Content-Type on purpose, and sent without following
redirects: the manifest accepts 3xx as success for the positive tests.
"""

from __future__ import annotations

from dataclasses import dataclass

from .sparql import RDF_MEDIA, _parse_json, _parse_xml, QueryResult
from .transport import Exchange, exchange

MANIFEST = "https://github.com/w3c/rdf-tests/blob/main/sparql/sparql11/protocol/manifest.ttl"

TABULAR = {"application/sparql-results+xml", "application/sparql-results+json", "text/csv",
           "text/tab-separated-values"}
BOOLEAN = {"application/sparql-results+xml", "application/sparql-results+json"}
RDF = {"application/rdf+xml", "text/turtle", "application/n-triples", "text/plain", "application/xhtml+xml"}


@dataclass(frozen=True)
class ProtocolTest:
    id: str
    name: str
    method: str
    query_string: str | None
    body: bytes | None
    content_type: str | None
    expect: str  # boolean-true | tabular | boolean | rdf | 4xx


TESTS: list[ProtocolTest] = [
    ProtocolTest("query_get", "query via GET", "GET", "query=ASK%20%7B%7D", None, None, "boolean-true"),
    ProtocolTest("query_post_form", "query via URL-encoded POST", "POST", None, b"query=ASK%20%7B%7D",
                 "application/x-www-form-urlencoded", "boolean-true"),
    ProtocolTest("query_post_direct", "query via POST directly", "POST", None, b"ASK {}",
                 "application/sparql-query", "boolean-true"),
    ProtocolTest("query_content_type_select", "SELECT answers in XML, JSON, CSV or TSV", "POST", None,
                 b"SELECT (1 AS ?value) {}", "application/sparql-query", "tabular"),
    ProtocolTest("query_content_type_ask", "ASK answers in XML or JSON", "POST", None, b"ASK {}",
                 "application/sparql-query", "boolean"),
    ProtocolTest("query_content_type_describe", "DESCRIBE answers in an RDF syntax", "POST", None,
                 b"DESCRIBE <http://example.org/>", "application/sparql-query", "rdf"),
    ProtocolTest("query_content_type_construct", "CONSTRUCT answers in an RDF syntax", "POST", None,
                 b"CONSTRUCT { <s> <p> 1 } WHERE {}", "application/sparql-query", "rdf"),
    ProtocolTest("bad_multiple_queries", "two query parameters are rejected", "GET",
                 "query=ASK%20%7B%7D&query=SELECT%20%2A%20%7B%7D", None, None, "4xx"),
    ProtocolTest("bad_query_wrong_media_type", "POST with text/plain is rejected", "POST", None, b"ASK {}",
                 "text/plain", "4xx"),
    ProtocolTest("bad_query_missing_form_type", "URL-encoded body without its media type is rejected", "POST",
                 None, b"query=ASK%20%7B%7D", None, "4xx"),
    ProtocolTest("bad_query_missing_direct_type", "query body without a media type is rejected", "POST", None,
                 b"ASK {}", None, "4xx"),
    ProtocolTest("bad_query_non_utf8", "direct POST in UTF-16 is rejected", "POST", None,
                 "ASK {}".encode("utf-16"), "application/sparql-query; charset=UTF-16", "4xx"),
    ProtocolTest("bad_query_syntax", "a syntax error gets a 4xx", "GET", "query=ASK%20%7B", None, None, "4xx"),
]


def _judge(test: ProtocolTest, x: Exchange) -> tuple[bool, str]:
    if not x.ok_transport:
        return False, f"{x.error_class}: {x.error_detail}"
    status, media = x.status, x.media_type
    if test.expect == "4xx":
        if 400 <= status < 500:
            return True, f"HTTP {status}"
        return False, f"expected a 4xx, got HTTP {status}"
    if not (200 <= status < 400):
        return False, f"expected 2xx or 3xx, got HTTP {status}"
    if 300 <= status < 400:
        return True, f"HTTP {status} (redirect, accepted by the manifest)"
    no_accept = " (the manifest sends no Accept header, so this is the server's default format)"
    if test.expect == "tabular":
        ok = media in TABULAR
        return ok, f"HTTP {status}, {media or 'no content type'}" + ("" if ok else no_accept)
    if test.expect == "rdf":
        ok = media in RDF
        return ok, f"HTTP {status}, {media or 'no content type'}" + ("" if ok else no_accept)
    if test.expect in ("boolean", "boolean-true"):
        if media not in BOOLEAN:
            return False, f"HTTP {status}, {media or 'no content type'} is not a boolean results format" + no_accept
        holder = QueryResult(url=x.url, form="", query="", hops=[x])
        parsed = _parse_json(x.text(), holder) if media.endswith("json") else _parse_xml(x.text(), holder)
        if holder.boolean is None:
            return False, f"HTTP {status}, no boolean in the body ({parsed})"
        if test.expect == "boolean-true" and holder.boolean is not True:
            return False, "ASK {} must be true"
        return True, f"HTTP {status}, {media}, boolean {str(holder.boolean).lower()}"
    raise ValueError(test.expect)


def run_suite(url: str, **kwargs) -> dict:
    results, exchanges = [], []
    for test in TESTS:
        target = url
        if test.query_string:
            target = url + ("&" if "?" in url else "?") + test.query_string
        headers = {"Content-Type": test.content_type} if test.content_type else {}
        x = exchange(test.method, target, headers=headers, body=test.body, purpose=f"P {test.id}", **kwargs)
        exchanges.append(x)
        passed, detail = _judge(test, x)
        results.append({"id": test.id, "name": test.name, "passed": passed, "detail": detail, "evidence": [x.id]})
    return {
        "passed": sum(r["passed"] for r in results),
        "total": len(TESTS),
        "tests": results,
        "source": MANIFEST,
        "adaptation": "default-graph-uri removed; update, dataset and PUT tests excluded",
        "_exchanges": exchanges,
    }
