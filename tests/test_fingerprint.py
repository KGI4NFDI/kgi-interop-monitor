"""Engine signatures against responses captured live on 2026-09-23."""

from __future__ import annotations

from kgi_interop_monitor.fingerprint import identify
from kgi_interop_monitor.transport import Exchange

from .replay import load


def from_fixture(name: str) -> Exchange:
    f = load(name)
    return Exchange(id=name, method=f["request"]["method"], url=f["request"]["url"], request_headers={},
                    request_body=None, status=f["response"]["status"],
                    response_headers={k.lower(): v for k, v in f["response"]["headers"].items()},
                    body=f["response"]["body"].encode("utf-8"))


def test_qlever_hub():
    fp = identify([from_fixture("2026-09-23-qlever-hub-syntax-error")])
    assert fp["engine"] == "QLever" and fp["source"] == "body"


def test_matwerk_virtuoso():
    fp = identify([from_fixture("2026-09-23-matwerk-syntax-error")])
    assert fp["engine"] == "Virtuoso"


def test_wikidata_blazegraph():
    fp = identify([from_fixture("2026-09-23-wikidata-sparql-syntax-error")])
    assert fp["engine"] == "Blazegraph"


def test_header_beats_body():
    x = Exchange(id="x", method="GET", url="https://e/sparql", request_headers={}, request_body=None, status=400,
                 response_headers={"server": "Virtuoso/07.20.3237 (Linux) x86_64"}, body=b"Invalid SPARQL query: ")
    fp = identify([x])
    assert fp["engine"] == "Virtuoso" and fp["version"] == "07.20.3237" and fp["also_matched"] == ["QLever"]


def test_unknown_stays_unknown():
    x = Exchange(id="x", method="GET", url="https://e/sparql", request_headers={}, request_body=None, status=400,
                 response_headers={"server": "nginx"}, body=b"bad request")
    fp = identify([x])
    assert fp["engine"] is None and fp["server_headers"] == ["nginx"]


def test_data_that_looks_like_an_error_code_is_not_a_signature():
    x = Exchange(id="x", method="GET", url="https://e/sparql", request_headers={}, request_body=None, status=200,
                 response_headers={}, body=b'{"head":{"vars":["o"]},"results":{"bindings":[{"o":{"type":"literal","value":"Virtuoso 37000 Error SP030"}}]}}')
    assert identify([x])["engine"] is None
