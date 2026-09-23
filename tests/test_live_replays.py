"""Replays of responses captured live on 2026-09-23 (tests/fixtures/live)."""

from __future__ import annotations

from kgi_interop_monitor import sparql
from kgi_interop_monitor.sparql import run_query

from .conftest import serve
from .replay import load, replay_handler


def test_matwerk_form_post_is_http_200_with_an_error_body():
    """Checklist B1 and B2, still true on 2026-09-23."""
    with serve(replay_handler(load("2026-09-23-matwerk-select-post-form"))) as base:
        r = run_query(base + "/sparql", "SELECT * WHERE { ?s ?p ?o } LIMIT 1", "post-form")
    assert r.status == 200
    assert r.verdict == sparql.ERROR_BODY_2XX
    assert "SP030" in r.detail


def test_matwerk_direct_post_answers():
    with serve(replay_handler(load("2026-09-23-matwerk-select-post-direct"))) as base:
        r = run_query(base + "/sparql", "SELECT * WHERE { ?s ?p ?o } LIMIT 1", "post-direct")
    assert r.ok and len(r.rows) == 1


def test_wikidata_as_registered_is_a_web_page():
    """Checklist A3: the registered URL is the query UI."""
    with serve(replay_handler(load("2026-09-23-wikidata-ui-root-ask-get"))) as base:
        r = run_query(base, "ASK {}", "get")
    assert r.verdict == sparql.NOT_SPARQL


def test_qlever_syntax_error_is_a_proper_400():
    with serve(replay_handler(load("2026-09-23-qlever-hub-syntax-error"))) as base:
        r = run_query(base + "/api/", "SELECT ?s WHERE { ?s ?p ?o ", "get")
    assert r.verdict == sparql.HTTP_ERROR and r.status == 400
    assert "Invalid SPARQL query" in r.detail
