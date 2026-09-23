"""Layer C against the fake endpoints, with a stub release source so no test
depends on GitHub."""

from __future__ import annotations

import pytest

from kgi_interop_monitor.references import Reference
from kgi_interop_monitor.runner import RunConfig, run

from .fake_endpoint import FakeEndpoints

REFS = [
    Reference("MWO-like", "example/mwo", ("http://purls.example/mwo",), "http://purls.example/mwo/MWO_",
              "https://example.invalid/{tag}/mwo.ttl"),
    Reference("NFDIcore", "example/nfdicore", ("https://nfdi.fiz-karlsruhe.de/ontology",),
              "https://nfdi.fiz-karlsruhe.de/ontology/NFDI_", "https://example.invalid/{tag}/nfdicore.ttl"),
]


class StubReleases:
    def latest_tag(self, ref):
        return {"example/mwo": ("v3.0.2", "stub"), "example/nfdicore": ("v3.0.5", "stub")}[ref.repo]

    def release_class_count(self, ref, tag):
        return {"example/nfdicore": (8, "stub release with 8 labelled classes")}.get(ref.repo, (0, "stub"))


@pytest.fixture(scope="module")
def report():
    with FakeEndpoints() as fake:
        config = RunConfig(registry_endpoint=fake.url("/registry/sparql"), hub_endpoint=fake.url("/hub/sparql"),
                           control_url=fake.url("/healthy/sparql?query=ASK%7B%7D"), layers="ABC",
                           connect_timeout=2, read_timeout=5, references=REFS, release_source=StubReleases())
        yield run(config)


def kg(report, rid):
    return next(k for k in report["kgs"] if k["id"] == rid)


def outcomes(report, rid):
    return {pid: r["outcome"] for pid, r in kg(report, rid)["results"].items()}


def test_healthy_reaches_grade_c(report):
    o = outcomes(report, "KGR1")
    assert o["C1"] == "pass" and o["C3"] == "pass"
    assert {o["C2"], o["C4"], o["C5"]} == {"n/a"}
    assert kg(report, "KGR1")["grade"] == "C"


def test_empty_store_is_c1(report):
    k = kg(report, "KGR7")
    assert k["results"]["C1"]["outcome"] == "fail" and k["grade"] == "B"


def test_messy_store_fails_c2_to_c5(report):
    k = kg(report, "KGR8")
    o = outcomes(report, "KGR8")
    assert o["C1"] == "pass"
    assert o["C2"] == "fail" and "scratch-test" in k["results"]["C2"]["summary"]
    assert o["C3"] == "fail" and k["results"]["C3"]["details"]["nothing_subsumptions"] == 3
    assert o["C4"] == "fail" and "3.0.1 served, v3.0.2 released" in k["results"]["C4"]["summary"]
    assert o["C5"] == "fail" and "10 labelled classes here, 8 in v3.0.5" in k["results"]["C5"]["summary"]
    assert k["grade"] == "B"


def test_c_is_measured_through_the_working_url(report):
    c1 = kg(report, "KGR4")["results"]["C1"]
    assert c1["measured_on"]["via"] == "normalised"


def test_blocked_and_not_applicable(report):
    assert outcomes(report, "KGR6")["C1"] == "blocked"
    assert outcomes(report, "KGR10")["C1"] == "n/a"


def test_graph_kpis(report):
    kpis = kg(report, "KGR8")["kpis"]
    assert kpis["named_graphs"] == 3
    assert {g["kind"] for g in kpis["top_graphs"]} == {"data"}


def test_c5_compares_with_the_release_of_the_served_version():
    """MatWerk serves MWO 3.0.1 with 44 labelled classes: equal to v3.0.1, far
    from v3.0.2. That is version lag (C4), not a module (C5)."""
    from kgi_interop_monitor.probes import layer_c
    from kgi_interop_monitor.probes.layer_a import Working

    class Counts:
        def latest_tag(self, ref):
            return ("v3.0.2", "stub")

        def release_class_count(self, ref, tag):
            return ({"v3.0.1": 10, "v3.0.2": 94}[tag], f"stub {tag}")

    ref = Reference("NFDIcore", "example/nfdicore", ("https://nfdi.fiz-karlsruhe.de/ontology",),
                    "https://nfdi.fiz-karlsruhe.de/ontology/NFDI_", "x/{tag}")
    with FakeEndpoints() as fake:
        w = Working(fake.url("/messy/sparql"), "get", "registered", None)
        matched, _ = layer_c.c5(w, [ref], Counts(), {"NFDIcore": "3.0.1"})
        latest, _ = layer_c.c5(w, [ref], Counts(), {})
    assert matched.outcome.value == "pass" and matched.details["comparisons"][0]["release_tag"] == "v3.0.1"
    assert latest.outcome.value == "fail"


def test_triples_mode_store_has_no_named_graphs_to_mix():
    from kgi_interop_monitor.probes.layer_c import Census, c2

    assert c2(100, Census(triples_mode=True)).outcome.value == "n/a"
