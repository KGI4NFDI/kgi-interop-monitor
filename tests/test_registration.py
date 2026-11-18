"""
Created on 2026-10-26

@author: danielviladrich
"""

from urllib.parse import parse_qs, urlsplit

import yaml
from basemkit.basetest import Basetest

from kgi_interop_monitor.registration import RegistrationForm


class TestRegistrationForm(Basetest):
    """
    Test the data contribution form filled with the registered values
    """

    def setUp(self, debug=False, profile=True):
        Basetest.setUp(self, debug=debug, profile=profile)
        self.memory = "http://www.wikidata.org/entity/Q98231721"
        self.fields = {
            "name": ["FactGrid"],
            "consortium": [self.memory],
            "contact": ["http://www.wikidata.org/entity/Q1"],
            "endpoint": ["https://database.factgrid.de/sparql"],
            "dumps": ["https://a.org/1.ttl", "https://a.org/2.ttl"],
        }
        labels = {self.memory: "NFDI4Memory"}
        self.form = RegistrationForm("KGR16", self.fields, labels)

    def test_yaml_block(self):
        """
        test that the YAML has every field of the template, bare QIDs with
        their label as comment, and text never null
        """
        yaml_block = self.form.yaml_block()
        if self.debug:
            print(yaml_block)
        self.assertIn("- Q98231721  # NFDI4Memory", yaml_block)
        data = yaml.safe_load(yaml_block)
        labels = [label for label, _field, _kind in RegistrationForm.FIELDS]
        self.assertEqual(labels, list(data))
        self.assertEqual("FactGrid", data["Name of the KG*"])
        self.assertEqual("", data["Description"])
        self.assertEqual("", data["KG URL"])
        self.assertEqual(["Q98231721"], data["Related NFDI consortium"])
        self.assertEqual(["Q1"], data["Contact point*"])
        self.assertEqual([], data["License(s)*"])
        self.assertEqual(
            ["https://database.factgrid.de/sparql"], data["URLs for SPARQL endpoint*"]
        )
        self.assertEqual("", data["URL for (REST) API"])
        self.assertEqual(
            "https://a.org/1.ttl, https://a.org/2.ttl", data["URL for dump files"]
        )

    def test_readable_text(self):
        """
        test that non-ASCII characters stay readable in the issue - not
        escaped as \\u00fc - and still load as the same text
        """
        fields = {
            "name": ["Aktienführer Knowledge Graph"],
            "dumps": ["https://a.org/Bühne.ttl"],
        }
        yaml_block = RegistrationForm("KGR1", fields, {}).yaml_block()
        self.assertIn('Name of the KG*: "Aktienführer Knowledge Graph"', yaml_block)
        self.assertNotIn("\\u00", yaml_block)
        data = yaml.safe_load(yaml_block)
        self.assertEqual("Aktienführer Knowledge Graph", data["Name of the KG*"])
        self.assertEqual("https://a.org/Bühne.ttl", data["URL for dump files"])

    def test_body_and_url(self):
        """
        test that the issue names the record it updates and the link opens a
        new issue with title and body
        """
        body = self.form.body()
        self.assertIn("```yaml\nName of the KG*:", body)
        self.assertIn("Note to admin: This updates the existing registry", body)
        self.assertIn("http://kgi.services.base4nfdi.de/entity/KGR16", body)
        url = self.form.url()
        self.assertTrue(url.startswith(RegistrationForm.NEW_ISSUE_URL + "?"))
        query = parse_qs(urlsplit(url).query)
        # the template brings the labels and assignees - not the link
        self.assertEqual([RegistrationForm.TEMPLATE], query["template"])
        self.assertNotIn("labels", query)
        self.assertNotIn("assignees", query)
        self.assertEqual(
            ["[KGI registry entry] Update KGR16: FactGrid"], query["title"]
        )
        self.assertEqual([body], query["body"])
