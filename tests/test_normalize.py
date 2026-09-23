from __future__ import annotations

from kgi_interop_monitor.normalize import candidates, canonical, parse_value, title_key


def test_prose_packed_and_single_values():
    assert parse_value("work in progress").is_prose
    assert parse_value("not available anymore").is_prose
    packed = parse_value("https://orkg.org/triplestore; https://orkg.org/sparql")
    assert packed.is_packed and packed.urls == ["https://orkg.org/triplestore", "https://orkg.org/sparql"]
    single = parse_value("https://query.wikidata.org")
    assert single.is_single_url and not single.is_packed and not single.is_prose
    labelled = parse_value("SPARQL: https://example.org/sparql")
    assert labelled.has_extra_text


def test_canonical_folds_case_slash_port_and_fragment():
    assert canonical("https://database.factgrid.de/query/") == canonical("https://Database.FactGrid.de/query")
    assert canonical("https://query.semantic-kompakkt.de/") == canonical("https://query.semantic-kompakkt.de")
    assert canonical("https://x.org:443/sparql#frag") == "https://x.org/sparql"
    assert canonical("http://x.org:8890/sparql") == "http://x.org:8890/sparql"


def test_title_key():
    assert title_key("FactGrid") == title_key("FactGRID")
    assert title_key("Semantic Kompakkt") == title_key("semantic-kompakkt")


# The registered values below are real (registry, 2026-09-23). The expected
# endpoint is where the checklist's July census found the service answering.

def test_wikibase_ui_root_proposes_sparql_first():
    assert candidates("https://query.wikidata.org")[0:2] == ["https://query.wikidata.org/sparql",
                                                             "https://query.wikidata.org/"]


def test_mardi_ui_root():
    assert "https://query.portal.mardi4nfdi.de/sparql" in candidates("https://query.portal.mardi4nfdi.de")


def test_factgrid_query_ui():
    c = candidates("https://database.factgrid.de/query/")
    assert c[0] == "https://database.factgrid.de/sparql"


def test_dblp_host_root():
    assert candidates("https://sparql.dblp.org")[0] == "https://sparql.dblp.org/sparql"


def test_fuseki_ui_route_in_fragment():
    c = candidates("https://sparql.knowledgehub.nfdi4earth.de/#/dataset/knowledge-graph/query")
    assert c[:2] == ["https://sparql.knowledgehub.nfdi4earth.de/knowledge-graph/sparql",
                     "https://sparql.knowledgehub.nfdi4earth.de/knowledge-graph/query"]


def test_documentation_page():
    assert candidates("https://lod.b3kat.de/doc/sparql-endpoint")[0] == "https://lod.b3kat.de/doc/sparql"
    assert "https://lod.b3kat.de/sparql" in candidates("https://lod.b3kat.de/doc/sparql-endpoint")


def test_trailing_slash_variant_is_a_candidate():
    assert "https://query.semantic-kompakkt.de/" in candidates("https://query.semantic-kompakkt.de")


def test_never_proposes_the_registered_url_and_stays_bounded():
    for url in ("https://nfdi4culture.de/sparql", "http://example.org/a/b/query.html", "https://x.org/"):
        c = candidates(url)
        assert url not in c and len(c) <= 10 and len(c) == len(set(c))


def test_http_gets_an_https_candidate():
    assert "https://example.org/sparql" in candidates("http://example.org/sparql")


def test_not_a_url_has_no_candidates():
    assert candidates("work in progress") == []
