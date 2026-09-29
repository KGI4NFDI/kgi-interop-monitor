"""
Created on 2026-09-29

@author: danielviladrich
"""

from basemkit.basetest import Basetest

from kgi_interop_monitor.kgs import KnowledgeGraphs


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

    def test_prose_is_no_url(self):
        """
        test that a prose endpoint value is recognized as such
        """
        kg = KnowledgeGraphs.of_yaml().kgs["KGR19"]
        self.assertEqual("work in progress", kg.endpoint)
        self.assertFalse(kg.endpoint_is_url)
