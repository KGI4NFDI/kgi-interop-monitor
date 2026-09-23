"""Layer A against the fake registry: every record has a known answer."""

from __future__ import annotations

import pytest

from kgi_interop_monitor.runner import RunConfig, run

from .conftest import free_port
from .fake_endpoint import FakeEndpoints


@pytest.fixture(scope="module")
def report():
    with FakeEndpoints() as fake:
        config = RunConfig(registry_endpoint=fake.url("/registry/sparql"), hub_endpoint=fake.url("/hub/sparql"),
                           control_url=fake.url("/healthy/sparql?query=ASK%7B%7D"), layers="A",
                           connect_timeout=2, read_timeout=5)
        out = run(config)
        out["_base"] = fake.base
        yield out


def kg(report, rid):
    return next(k for k in report["kgs"] if k["id"] == rid)


def outcomes(report, rid):
    return {pid: r["outcome"] for pid, r in kg(report, rid)["results"].items()}


def test_run_is_ok_and_covers_every_record(report):
    assert report["status"] == "ok"
    assert len([k for k in report["kgs"] if k["kind"] == "record"]) == 15
    assert report["summary"]["kgs"] == 15


def test_healthy_clears_layer_a(report):
    o = outcomes(report, "KGR1")
    assert {o[p] for p in ("A1", "A3", "A4", "A5", "A7")} == {"pass"}
    assert kg(report, "KGR1")["working"]["via"] == "registered"


def test_ui_only_is_a3_fail_and_nothing_to_normalise(report):
    o = outcomes(report, "KGR3")
    assert o["A3"] == "fail" and o["A4"] == "pass" and o["A7"] == "n/a"
    assert kg(report, "KGR3")["working"] is None and kg(report, "KGR3")["grade"] == "none"


def test_wikibase_ui_is_repaired_by_normalisation(report):
    k = kg(report, "KGR4")
    assert outcomes(report, "KGR4")["A7"] == "fail"
    assert k["working"] == {"url": report["_base"] + "/wikibase/sparql", "form": "get", "via": "normalised"}
    assert k["results"]["A7"]["details"]["proposal"] == report["_base"] + "/wikibase/sparql"
    assert k["grade"] == "A*"


def test_refusal_is_not_death(report):
    o = outcomes(report, "KGR5")
    assert o["A4"] == "pass" and o["A3"] == "unknown"


def test_gone_is_dead_and_a3_is_blocked(report):
    o = outcomes(report, "KGR6")
    assert o["A4"] == "fail" and o["A3"] == "blocked"


def test_prose_value(report):
    o = outcomes(report, "KGR9")
    assert o["A5"] == "fail" and o["A2"] == "warn" and o["A1"] == "pass"
    assert kg(report, "KGR9")["grade"] == "dump"


def test_dump_only_and_nothing(report):
    assert outcomes(report, "KGR10")["A2"] == "warn" and kg(report, "KGR10")["grade"] == "dump"
    assert outcomes(report, "KGR11")["A1"] == "fail" and kg(report, "KGR11")["grade"] == "none"


def test_redirect_is_a_warning_not_a_failure(report):
    k = kg(report, "KGR13")
    assert k["results"]["A7"]["outcome"] == "warn"
    assert k["working"]["via"] == "redirect" and k["working"]["url"].endswith("/healthy/sparql")


def test_duplicates_are_found_by_slash_title_landing_page_and_working_url(report):
    others = kg(report, "KGR1")["results"]["A6"]["details"]["others"]
    assert set(others["KGR12"]) >= {"same registered endpoint", "same title", "same landing page"}
    assert "same working endpoint" in others["KGR13"]
    assert outcomes(report, "KGR8")["A6"] == "pass"
    assert "same registered endpoint" in kg(report, "KGR7")["results"]["A6"]["details"]["others"]["KGR14"]


def test_every_network_result_carries_evidence(report):
    k = kg(report, "KGR3")
    ids = {x["id"] for x in k["exchanges"]}
    assert k["results"]["A3"]["evidence"] and set(k["results"]["A3"]["evidence"]) <= ids


def test_dead_network_is_an_instrument_failure_not_thirty_outages():
    out = run(RunConfig(control_url=f"http://127.0.0.1:{free_port()}/", registry_endpoint="http://unused.invalid/"))
    assert out["status"] == "instrument-unhealthy" and out["kgs"] == []


def test_unreachable_registry_is_reported_as_such():
    with FakeEndpoints() as fake:
        out = run(RunConfig(control_url=fake.url("/healthy/sparql?query=ASK%7B%7D"),
                            registry_endpoint=fake.url("/gone/sparql"), layers="A"))
    assert out["status"] == "registry-unavailable"


def test_packed_value_tries_every_part(report):
    k = kg(report, "KGR14")
    a7 = k["results"]["A7"]
    assert a7["outcome"] == "fail" and k["working"]["via"] == "split"
    assert k["working"]["url"].endswith("/empty/sparql")
    assert [part["state"] for part in a7["details"]["parts"]] == ["not-sparql", "sparql"]
    assert k["results"]["A5"]["outcome"] == "warn"


def test_ui_fragment_is_a_warning_and_is_dropped_from_the_working_url(report):
    k = kg(report, "KGR15")
    assert k["results"]["A7"]["outcome"] == "warn"
    assert "#" not in k["working"]["url"] and k["working"]["url"].endswith("/virtuoso/sparql")


def test_the_hub_is_monitored_as_its_own_row(report):
    hub = kg(report, "HUB")
    assert hub["kind"] == "hub" and hub["working"]["via"] == "registered"
    assert hub["results"]["A6"]["outcome"] == "n/a"
