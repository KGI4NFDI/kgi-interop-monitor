"""
Created on 2026-09-29

@author: danielviladrich
"""

from basemkit.basetest import Basetest

from kgi_interop_monitor.kgs import KnowledgeGraph, KnowledgeGraphs
from kgi_interop_monitor.nicekgi import Endpoints


class TestKnowledgeGraphs(Basetest):
    """
    Test the knowledge graph config file
    """

    def test_config(self):
        """
        test that the shipped registry snapshot loads and is complete
        """
        kgs = KnowledgeGraphs.of_yaml()
        if self.debug:
            print(f"{len(kgs.kgs)} knowledge graphs from {kgs.source}")
        self.assertTrue(kgs.source.startswith("https://"))
        self.assertTrue(kgs.fetched)
        self.assertTrue(len(kgs.kgs) > 0)
        for key, kg in kgs.kgs.items():
            self.assertTrue(key.startswith("KGR"), key)
            self.assertTrue(kg.name, key)

    def test_culture_knowledge_graph(self):
        """
        test one known record: name, consortium and endpoint
        """
        kg = KnowledgeGraphs.of_yaml().kgs["KGR7"]
        self.assertEqual("Culture Knowledge Graph", kg.name)
        self.assertEqual("NFDI4Culture", kg.consortium)
        self.assertEqual("https://nfdi4culture.de/sparql", kg.endpoint)
        self.assertTrue(kg.endpoint_is_url)

    def test_utf8(self):
        """
        test that non-ASCII names read as they are, whatever the platform
        encoding - not as AktienfÃ¼hrer
        """
        kg = KnowledgeGraphs.of_yaml().kgs["KGR1"]
        self.assertEqual("Aktienführer Knowledge Graph", kg.name)

    def test_prose_is_no_url(self):
        """
        test that a prose endpoint value is recognized as such
        """
        kg = KnowledgeGraphs.of_yaml().kgs["KGR19"]
        self.assertEqual("work in progress", kg.endpoint)
        self.assertFalse(kg.endpoint_is_url)

    def test_shipped_endpoint_urls(self):
        """
        test that every shipped endpoint_url is a URL replacing a registered
        URL value
        """
        for key, kg in KnowledgeGraphs.of_yaml().kgs.items():
            if kg.endpoint_url:
                self.assertTrue(kg.endpoint_url.startswith("http"), key)
                self.assertTrue(kg.endpoint_is_url, key)
                self.assertNotEqual(kg.endpoint, kg.endpoint_url, key)

    def test_get_endpoints_probes_endpoint_url(self):
        """
        test that the monitor probes endpoint_url where it is set and the
        registered endpoint otherwise
        """
        provider = Endpoints()
        provider.kgs.kgs = {
            "KGR1": KnowledgeGraph(
                name="rerouted",
                endpoint="https://a.example.org/query",
                endpoint_url="https://a.example.org/sparql",
            ),
            "KGR2": KnowledgeGraph(
                name="registered", endpoint="https://b.example.org/sparql"
            ),
        }
        endpoints = provider.get_endpoints()
        self.assertEqual("https://a.example.org/sparql", endpoints["KGR1"].endpoint)
        self.assertEqual("https://b.example.org/sparql", endpoints["KGR2"].endpoint)

    def test_probed_instead(self):
        """
        test that the registered value is flagged only while the registry
        still holds the value the endpoint_url replaces
        """
        provider = Endpoints()
        provider.kgs.kgs = {
            "KGR1": KnowledgeGraph(
                name="rerouted",
                endpoint="https://a.example.org/query",
                endpoint_url="https://a.example.org/sparql",
            )
        }
        same = {"endpoint": ["https://a.example.org/query"]}
        fixed = {"endpoint": ["https://a.example.org/sparql"]}
        self.assertEqual(
            "https://a.example.org/sparql", provider.probed_instead("KGR1", same)
        )
        self.assertIsNone(provider.probed_instead("KGR1", fixed))
        self.assertIsNone(provider.probed_instead("KGR99", same))
