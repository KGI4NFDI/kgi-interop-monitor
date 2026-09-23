from __future__ import annotations

import pytest

from kgi_interop_monitor import references
from kgi_interop_monitor.references import count_labelled_classes, version_tuple

TTL = b"""@prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
<https://nfdi.fiz-karlsruhe.de/ontology/NFDI_1> a owl:Class ; rdfs:label "one" .
<https://nfdi.fiz-karlsruhe.de/ontology/NFDI_2> a owl:Class .
<http://other.example/X> a owl:Class ; rdfs:label "other" ."""


def test_versions_from_iris_and_tags():
    assert version_tuple("https://nfdi.fiz-karlsruhe.de/ontology/3.0.5") == (3, 0, 5)
    assert version_tuple("v3.0.2") == (3, 0, 2)
    assert version_tuple("http://purls.helmholtz-metadaten.de/mwo/3.0.1") < version_tuple("v3.0.2")
    assert version_tuple("no version") is None


def test_counts_only_labelled_classes_in_the_prefix():
    assert count_labelled_classes(TTL, "https://nfdi.fiz-karlsruhe.de/ontology/NFDI_") == 1


def test_reference_table_is_well_formed():
    refs = references.load()
    assert {r.name for r in refs} >= {"NFDIcore", "MWO"}
    assert all("{tag}" in r.release_file for r in refs)
    nfdicore = next(r for r in refs if r.name == "NFDIcore")
    assert nfdicore.matches("https://nfdi.fiz-karlsruhe.de/ontology") and not nfdicore.matches("https://nfdi.fiz-karlsruhe.de/ontology/extension")


@pytest.mark.live
def test_live_release_lookup():
    source = references.ReleaseSource()
    mwo = next(r for r in references.load() if r.name == "MWO")
    tag, _ = source.latest_tag(mwo)
    count, where = source.release_class_count(mwo, tag)
    # MWO v3.0.2 has 94 labelled MWO_ classes (counted from the release file)
    assert version_tuple(tag) >= (3, 0, 2) and count and count >= 90, where
