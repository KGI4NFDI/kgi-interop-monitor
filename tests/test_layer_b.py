"""Layer B against the fake endpoints."""

from __future__ import annotations

import pytest

from kgi_interop_monitor.probes import layer_b
from kgi_interop_monitor.runner import RunConfig, run

from .fake_endpoint import FakeEndpoints


@pytest.fixture(scope="module")
def report():
    with FakeEndpoints() as fake:
        config = RunConfig(registry_endpoint=fake.url("/registry/sparql"), hub_endpoint=fake.url("/hub/sparql"),
                           control_url=fake.url("/healthy/sparql?query=ASK%7B%7D"), layers="AB",
                           connect_timeout=2, read_timeout=5)
        yield run(config)


def kg(report, rid):
    return next(k for k in report["kgs"] if k["id"] == rid)


def outcomes(report, rid):
    return {pid: r["outcome"] for pid, r in kg(report, rid)["results"].items()}


def test_healthy_clears_layer_b(report):
    o = outcomes(report, "KGR1")
    assert [o[p] for p in ("B1", "B2", "B3", "B4", "B5")] == ["pass"] * 5
    assert kg(report, "KGR1")["grade"] == "B"


def test_virtuoso_like_fails_b1_and_b2_like_matwerk(report):
    k = kg(report, "KGR2")
    assert k["results"]["B1"]["outcome"] == "fail" and "post-form" in k["results"]["B1"]["summary"]
    assert k["results"]["B2"]["outcome"] == "fail" and "SP030" in k["results"]["B2"]["summary"]
    assert k["grade"] == "A"


def test_kpis_for_a_working_endpoint(report):
    kpis = kg(report, "KGR1")["kpis"]
    assert kpis["available"] and kpis["latency_ms"] > 0 and len(kpis["latency_samples_ms"]) == 3
    assert set(kpis["formats"]) == {"json", "xml", "csv", "tsv"}
    assert kpis["protocol"]["passed"] == 13 and kpis["triples"] == 40


def test_engine_fingerprint_from_the_server_header(report):
    assert kg(report, "KGR2")["kpis"]["engine"]["engine"] == "Virtuoso"


def test_measured_through_the_normalised_url_and_says_so(report):
    b1 = kg(report, "KGR4")["results"]["B1"]
    assert b1["measured_on"]["via"] == "normalised" and b1["measured_on"]["url"].endswith("/wikibase/sparql")


def test_refusal_without_working_url_is_b5_and_the_rest_is_blocked(report):
    o = outcomes(report, "KGR5")
    assert o["B5"] == "fail" and o["B1"] == "blocked" and o["B4"] == "blocked"


def test_dump_only_is_not_applicable_not_blocked(report):
    o = outcomes(report, "KGR10")
    assert {o[p] for p in ("B1", "B2", "B3", "B4", "B5")} == {"n/a"}


def test_dead_endpoint_has_an_error_class(report):
    assert kg(report, "KGR6")["kpis"] == {"available": False, "error_class": "http-404"}


def test_hub_row_and_variable_service_finding(report):
    assert kg(report, "HUB")["results"]["B4"]["outcome"] == "n/a"
    h1 = report["hub_findings"][0]
    assert h1["id"] == "H1" and h1["outcome"] == "fail" and "informative" in h1["details"]["basis"]


def test_size_gate(monkeypatch):
    monkeypatch.setattr(layer_b, "SIZE_GATE", 10)
    with FakeEndpoints() as fake:
        result, _, n = layer_b.b3(fake.url("/healthy/sparql"), "get", heavy=False)
        heavy, _, _ = layer_b.b3(fake.url("/healthy/sparql"), "get", heavy=True)
    assert result.outcome.value == "unknown" and "politeness" in result.summary and n == 40
    assert heavy.outcome.value == "pass"
