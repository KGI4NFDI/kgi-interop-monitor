from __future__ import annotations

import pytest

from kgi_interop_monitor import queries, registry

from .fake_endpoint import FakeEndpoints


@pytest.fixture(scope="module")
def snapshot():
    with FakeEndpoints() as fake:
        yield registry.read(fake.url("/registry/sparql")), fake


def test_reads_every_dataset(snapshot):
    snap, _ = snapshot
    assert snap.ok and len(snap.records) == 15


def test_endpoint_values_keep_their_raw_form_and_term_type(snapshot):
    snap, fake = snapshot
    prose = next(r for r in snap.records if r.id == "KGR9")
    assert [ev.raw for ev in prose.endpoint_values] == ["work in progress"]
    assert all(not ev.is_iri for r in snap.records for ev in r.endpoint_values)
    healthy = next(r for r in snap.records if r.id == "KGR1")
    assert healthy.endpoint_values[0].raw == fake.url("/healthy/sparql")
    assert healthy.landing_pages == ["https://healthy.example"]


def test_dump_only_and_empty_records(snapshot):
    snap, _ = snapshot
    dump = next(r for r in snap.records if r.id == "KGR10")
    nothing = next(r for r in snap.records if r.id == "KGR11")
    assert not dump.endpoint_values and dump.dumps_or_access == ["https://dumps.example/dump.nt"]
    assert not nothing.endpoint_values and not nothing.dumps_or_access


def test_literal_endpoint_values_are_one_registry_finding(snapshot):
    snap, _ = snapshot
    found = {f.id: f for f in registry.findings(snap)}
    assert found["R1"].outcome == "fail"
    assert found["R1"].details["literal"] == 13
    assert "rdfs:Resource" in found["R1"].summary


def test_unreachable_registry_is_an_error_not_an_empty_registry():
    snap = registry.read("http://no-such-host.invalid/sparql")
    assert not snap.ok and snap.records == [] and snap.error.startswith("transport")
    assert len(snap.attempts) == 3


def test_record_ids():
    assert registry.record_id("http://kgi.services.base4nfdi.de/entity/KGR28") == "KGR28"


def test_queries_are_shipped_as_files():
    assert "registry_records" in queries.names()
    assert "dcat:servesDataset" in queries.load("registry_records")


@pytest.mark.live
def test_live_registry_reads():
    snap = registry.read()
    assert snap.ok and len(snap.records) >= 30
    assert any(r.id == "KGR28" for r in snap.records)
