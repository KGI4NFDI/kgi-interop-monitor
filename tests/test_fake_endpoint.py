"""The fake endpoint must itself behave as documented, or every probe test
built on it proves nothing."""

from __future__ import annotations

import pytest

from kgi_interop_monitor import sparql
from kgi_interop_monitor.sparql import FORMS, MEDIA, run_query

from .fake_endpoint import FakeEndpoints


@pytest.fixture(scope="module")
def fake():
    with FakeEndpoints(slow_seconds=1.0) as f:
        yield f


@pytest.mark.parametrize("form", FORMS)
def test_healthy_answers_every_form(fake, form):
    r = run_query(fake.url("/healthy/sparql"), "SELECT * WHERE { ?s ?p ?o } LIMIT 1", form)
    assert r.ok and len(r.rows) == 1


@pytest.mark.parametrize("fmt", ["json", "xml", "csv", "tsv"])
def test_healthy_negotiates_formats(fake, fmt):
    r = run_query(fake.url("/healthy/sparql"), "SELECT ?s WHERE { ?s ?p ?o } LIMIT 2", "get", accept=MEDIA[fmt])
    assert r.ok and r.result_media_type == MEDIA[fmt] and len(r.rows) == 2


def test_healthy_rejects_bad_syntax_with_400(fake):
    r = run_query(fake.url("/healthy/sparql"), "SELECT ?s WHERE { ?s ?p ?o ", "get")
    assert r.status == 400


def test_virtuoso_like_mimics_matwerk(fake):
    form = run_query(fake.url("/virtuoso/sparql"), "ASK {}", "post-form")
    direct = run_query(fake.url("/virtuoso/sparql"), "ASK {}", "post-direct")
    bad = run_query(fake.url("/virtuoso/sparql"), "SELECT ?s WHERE {", "get")
    assert form.verdict == sparql.ERROR_BODY_2XX and direct.ok
    assert bad.verdict == sparql.ERROR_BODY_2XX


def test_ui_is_not_sparql_and_wikibase_has_a_real_endpoint_next_to_it(fake):
    assert run_query(fake.url("/ui/"), "ASK {}", "get").verdict == sparql.NOT_SPARQL
    assert run_query(fake.url("/wikibase/query/"), "ASK {}", "get").verdict == sparql.NOT_SPARQL
    assert run_query(fake.url("/wikibase/sparql"), "ASK {}", "get").ok


def test_refuse_gone_moved(fake):
    assert run_query(fake.url("/refuse/sparql"), "ASK {}", "get").verdict == sparql.REFUSED
    assert run_query(fake.url("/gone/sparql"), "ASK {}", "get").verdict == sparql.HTTP_ERROR
    moved = run_query(fake.url("/moved/sparql"), "ASK {}", "post-form")
    assert moved.ok and moved.redirected


def test_messy_default_graph_is_the_union_of_its_named_graphs(fake):
    total = run_query(fake.url("/messy/sparql"), "SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }", "get")
    per_graph = run_query(fake.url("/messy/sparql"),
                          "SELECT ?g (COUNT(*) AS ?n) WHERE { GRAPH ?g { ?s ?p ?o } } GROUP BY ?g", "get")
    assert total.ok and per_graph.ok
    assert total.int_value("n") == sum(int(row["n"]["value"]) for row in per_graph.rows)


def test_hub_routes_bound_service_and_rejects_variable_service(fake):
    bound = run_query(fake.url("/hub/sparql"),
                      f"SELECT * WHERE {{ SERVICE <{fake.url('/healthy/sparql')}> {{ ?s ?p ?o }} }}", "get")
    variable = run_query(fake.url("/hub/sparql"),
                         f"SELECT * WHERE {{ VALUES ?e {{ <{fake.url('/healthy/sparql')}> }} SERVICE ?e {{ ?s ?p ?o }} }}", "get")
    assert bound.ok and len(bound.rows) == 1
    assert variable.status == 400


def test_registry_describes_the_endpoints(fake):
    r = run_query(fake.url("/registry/sparql"),
                  "PREFIX dcat: <http://www.w3.org/ns/dcat#> SELECT (COUNT(*) AS ?n) WHERE { ?d a dcat:Dataset }", "get")
    assert r.int_value("n") == 15
