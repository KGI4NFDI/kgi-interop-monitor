from __future__ import annotations

import urllib.parse

import pytest

from kgi_interop_monitor import sparql
from kgi_interop_monitor.sparql import QueryResult, build_request, classify, error_signature
from kgi_interop_monitor.transport import Exchange



def fake_result(status=200, body=b"", content_type="application/sparql-results+json", error=None):
    x = Exchange(id="x", method="GET", url="http://e/sparql", request_headers={}, request_body=None,
                 status=None if error else status, body=body,
                 response_headers={"content-type": content_type} if content_type else {},
                 error_class=error)
    return QueryResult(url="http://e/sparql", form="get", query="ASK {}", hops=[x])


# ----------------------------------------------------------------- requests

def test_get_form_puts_the_query_in_the_url():
    method, url, headers, body = build_request("http://e/sparql", "ASK {}", "get", "application/sparql-results+json")
    assert method == "GET" and body is None
    assert urllib.parse.parse_qs(urllib.parse.urlsplit(url).query) == {"query": ["ASK {}"]}


def test_get_form_keeps_existing_query_parameters():
    _, url, _, _ = build_request("http://e/sparql?default-graph-uri=g", "ASK {}", "get", "x")
    assert "default-graph-uri=g&query=" in url


def test_post_forms_set_the_two_protocol_media_types():
    _, _, h1, b1 = build_request("http://e/s", "ASK {}", "post-form", "x")
    _, _, h2, b2 = build_request("http://e/s", "ASK {}", "post-direct", "x")
    assert h1["Content-Type"] == "application/x-www-form-urlencoded" and b1 == b"query=ASK+%7B%7D"
    assert h2["Content-Type"] == "application/sparql-query" and b2 == b"ASK {}"


def test_fragment_is_dropped():
    _, url, _, _ = build_request("https://sparql.example/#/dataset/kg/query", "ASK {}", "post-form", "x")
    assert url == "https://sparql.example/"


# ------------------------------------------------------------- result forms

def test_json_select():
    body = b'{"head":{"vars":["n"]},"results":{"bindings":[{"n":{"type":"literal","value":"403"}}]}}'
    r = classify(fake_result(body=body))
    assert r.ok and r.vars == ["n"] and r.int_value("n") == 403 and r.media_type_matches


def test_json_ask():
    r = classify(fake_result(body=b'{"head":{},"boolean":true}'))
    assert r.ok and r.boolean is True


def test_xml_select_and_ask():
    select = b"""<?xml version="1.0"?><sparql xmlns="http://www.w3.org/2005/sparql-results#">
      <head><variable name="s"/></head><results><result><binding name="s"><uri>http://x/a</uri></binding></result></results></sparql>"""
    ask = b"""<?xml version="1.0"?><sparql xmlns="http://www.w3.org/2005/sparql-results#"><head/><boolean>true</boolean></sparql>"""
    r1 = classify(fake_result(body=select, content_type="application/sparql-results+xml"))
    r2 = classify(fake_result(body=ask, content_type="application/sparql-results+xml"))
    assert r1.ok and r1.value("s") == "http://x/a"
    assert r2.ok and r2.boolean is True


def test_csv_and_tsv():
    r1 = classify(fake_result(body=b"s,n\r\nhttp://x/a,5\r\n", content_type="text/csv"))
    r2 = classify(fake_result(body=b"?s\t?n\n<http://x/a>\t5\n", content_type="text/tab-separated-values"))
    assert r1.ok and r1.vars == ["s", "n"] and r1.int_value("n") == 5
    assert r2.ok and r2.vars == ["s", "n"]


def test_rdf_graph():
    r = classify(fake_result(body=b"<http://x/s> <http://x/p> 1 .", content_type="text/turtle"), expect="graph")
    assert r.ok and r.triples == 1


def test_results_under_a_wrong_content_type_are_usable_but_flagged():
    r = classify(fake_result(body=b'{"head":{},"boolean":true}', content_type="text/plain"))
    assert r.ok and r.media_type_matches is False


def test_html_page_is_not_sparql():
    r = classify(fake_result(body=b"<!DOCTYPE html><html><body>Query UI</body></html>", content_type="text/html"))
    assert r.verdict == sparql.NOT_SPARQL and "HTML page" in r.detail


@pytest.mark.parametrize("status,verdict", [(409, sparql.REFUSED), (403, sparql.REFUSED), (404, sparql.HTTP_ERROR), (502, sparql.HTTP_ERROR)])
def test_status_classes(status, verdict):
    assert classify(fake_result(status=status, body=b"nope", content_type="text/plain")).verdict == verdict


def test_transport_failure():
    r = classify(fake_result(error="dns"))
    assert r.verdict == sparql.TRANSPORT and r.detail.startswith("dns")


def test_error_signature_from_json_html_and_stack_trace():
    assert error_signature('{"exception": "Invalid SPARQL query: missing }"}') == "Invalid SPARQL query: missing }"
    assert error_signature("<html><body><h1>Error 500</h1><p>boom</p></body></html>") == "Error 500 boom"
    trace = "java.util.concurrent.ExecutionException: org.openrdf.query.MalformedQueryException: Encountered x\n\tat a.b"
    assert error_signature(trace).startswith("java.util.concurrent.ExecutionException")
