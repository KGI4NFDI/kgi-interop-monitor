"""
Created on 2026-11-23

@author: danielviladrich
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

from basemkit.basetest import Basetest

from kgi_interop_monitor.endpoint_urls import (
    candidates,
    find_endpoint_url,
    update,
    write_endpoint_urls,
)
from kgi_interop_monitor.kgs import KnowledgeGraph, KnowledgeGraphs

UI_URL = "https://db.example.org/query"
SPARQL_URL = "https://db.example.org/sparql"


class TestEndpointUrls(Basetest):
    """
    Test finding the SPARQL protocol URL, with stubbed responses
    """

    @staticmethod
    def answering(*urls: str):
        """
        patch the ASK probe so that only the given URLs answer

        Args:
            urls: the URLs that answer

        Returns:
            the patcher
        """
        patcher = patch(
            "kgi_interop_monitor.endpoint_urls.answers_ask",
            side_effect=lambda url, timeout=15.0: url in urls,
        )
        return patcher

    def test_candidates(self):
        """
        test the proposals for a query page and for a Fuseki route
        """
        self.assertEqual(SPARQL_URL, candidates(UI_URL)[0])
        fuseki = "https://db.example.org/#/dataset/kg/query"
        self.assertEqual("https://db.example.org/kg/sparql", candidates(fuseki)[0])
        self.assertEqual([], candidates("work in progress"))

    def test_failing_endpoint_with_answering_candidate(self):
        """
        test that a failing registered endpoint gets the candidate that answers
        """
        with self.answering(SPARQL_URL):
            endpoint_url, _reason = find_endpoint_url(UI_URL)
        self.assertEqual(SPARQL_URL, endpoint_url)

    def test_packed_value(self):
        """
        test that each URL of a value holding several is tried
        """
        value = "https://db.example.org/triplestore; https://db.example.org/other"
        with self.answering("https://db.example.org/triplestore"):
            endpoint_url, _reason = find_endpoint_url(value)
        self.assertEqual("https://db.example.org/triplestore", endpoint_url)

    def test_removed_once_registered_answers(self):
        """
        test that endpoint_url goes as soon as the registered value answers
        """
        kg = KnowledgeGraph(name="kg", endpoint=UI_URL, endpoint_url=SPARQL_URL)
        kgs = KnowledgeGraphs(kgs={"KGR1": kg})
        with self.answering(UI_URL, SPARQL_URL):
            update(kgs)
        self.assertIsNone(kg.endpoint_url)

    def test_kept_while_nothing_answers(self):
        """
        test that a host that is down does not lose its endpoint_url
        """
        kg = KnowledgeGraph(name="kg", endpoint=UI_URL, endpoint_url=SPARQL_URL)
        kgs = KnowledgeGraphs(kgs={"KGR1": kg})
        with self.answering():
            update(kgs)
        self.assertEqual(SPARQL_URL, kg.endpoint_url)

    def test_none_without_answer(self):
        """
        test that no endpoint_url is invented when nothing answers
        """
        kg = KnowledgeGraph(name="kg", endpoint=UI_URL)
        kgs = KnowledgeGraphs(kgs={"KGR1": kg})
        with self.answering():
            update(kgs)
        self.assertIsNone(kg.endpoint_url)

    def test_prose_is_skipped(self):
        """
        test that a prose endpoint value is not probed
        """
        kg = KnowledgeGraph(name="kg", endpoint="work in progress")
        kgs = KnowledgeGraphs(kgs={"KGR1": kg})
        with self.answering() as probe:
            changes = update(kgs)
        probe.assert_not_called()
        self.assertEqual({}, changes)

    def test_write_round_trip(self):
        """
        test that writing adds and removes only the endpoint_url lines
        """
        text = (
            "source: https://example.org/\n"
            "kgs:\n"
            "  KGR1:\n"
            "    name: first\n"
            f"    endpoint: {UI_URL}\n"
            "    website: https://example.org\n"
            "  KGR2:\n"
            "    name: second\n"
            "    endpoint: https://other.example.org/sparql\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "kgs.yaml"
            path.write_bytes(text.encode("utf-8"))
            kgs = KnowledgeGraphs.of_yaml(str(path))
            kgs.kgs["KGR1"].endpoint_url = SPARQL_URL
            write_endpoint_urls(str(path), kgs)
            reread = KnowledgeGraphs.of_yaml(str(path))
            self.assertEqual(SPARQL_URL, reread.kgs["KGR1"].endpoint_url)
            self.assertEqual("https://example.org", reread.kgs["KGR1"].website)
            self.assertIsNone(reread.kgs["KGR2"].endpoint_url)
            reread.kgs["KGR1"].endpoint_url = None
            write_endpoint_urls(str(path), reread)
            self.assertEqual(text.encode("utf-8"), path.read_bytes())
