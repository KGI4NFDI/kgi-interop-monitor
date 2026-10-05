"""
Created on 2026-09-29

@author: danielviladrich
"""

from unittest.mock import patch

from lodstorage.sparql import SPARQL
from ngwidgets.webserver_test import WebserverTest

from kgi_interop_monitor.cmd import KgiCmd
from kgi_interop_monitor.nicekgi import KgiEndpointDashboard, KgiWebserver


class TestKgiWebserver(WebserverTest):
    """
    Test the nicekgi webserver
    """

    def setUp(self, debug=False, profile=True):
        WebserverTest.setUp(self, KgiWebserver, KgiCmd, debug=debug, profile=profile)

    def test_pages_are_registered(self):
        """
        test that the nicescholia chrome registered its pages
        """
        paths = [getattr(route, "path", None) for route in self.ws.app.routes]
        if self.debug:
            print(paths)
        for path in ["/", "/settings", "/about"]:
            self.assertIn(path, paths)

    def test_version(self):
        """
        test the version metadata the footer and the About page read
        """
        version = self.ws.config.version
        if self.debug:
            print(version.longDescription)
        self.assertEqual("nicekgi", version.name)
        self.assertTrue(version.version)

    def test_endpoints(self):
        """
        test that the registry endpoints are listed with their consortium

        Only endpoint values that are URLs get a row.
        """
        endpoints = self.ws.endpoints.get_endpoints()
        if self.debug:
            print(f"{len(endpoints)} endpoints")
        self.assertTrue(len(endpoints) > 0)
        for key, endpoint in endpoints.items():
            self.assertTrue(endpoint.endpoint.startswith("http"), key)
            self.assertTrue(endpoint.group, key)
        self.assertEqual("NFDI4Culture", endpoints["KGR7"].group)
        self.assertNotIn("KGR19", endpoints)

    def test_sorted_by_consortium(self):
        """
        test that the rows are sorted alphabetically by consortium, the
        knowledge graphs without one last
        """
        endpoints = self.ws.endpoints.get_endpoints()
        no_consortium = self.ws.endpoints.NO_CONSORTIUM
        groups = [endpoint.group for endpoint in endpoints.values()]
        named = [group for group in groups if group != no_consortium]
        if self.debug:
            print(groups)
        self.assertEqual(sorted(named, key=str.casefold), named)
        self.assertEqual(named, groups[: len(named)])
        self.assertIn(no_consortium, groups)

    def test_consortium_column(self):
        """
        test that nicescholia's hidden Group column becomes a Consortium column
        """
        column_defs = [
            {"headerName": "Group", "field": "group", "rowGroup": True, "hide": True},
            {"headerName": "Service", "field": "name"},
        ]
        KgiEndpointDashboard.show_consortium(column_defs)
        consortium = column_defs[0]
        self.assertEqual("Consortium", consortium["headerName"])
        self.assertFalse(consortium["hide"])
        self.assertNotIn("rowGroup", consortium)
        self.assertEqual("name", column_defs[1]["field"])

    def test_check_federation(self):
        """
        test that every ordered pair of endpoints is asked - no endpoint is
        queried here
        """
        endpoints = self.ws.endpoints.get_endpoints()
        with patch.object(
            SPARQL, "queryAsListOfDicts", return_value=[{"ok": 1}]
        ) as ask:
            matrix = self.ws.endpoints.check_federation()
        self.assertIn(
            "SERVICE <https://nfdi4culture.de/sparql>", str(ask.call_args_list)
        )
        self.assertEqual(list(endpoints), list(matrix))
        for source, row in matrix.items():
            self.assertEqual(len(endpoints) - 1, len(row))
            self.assertNotIn(source, row)
            self.assertEqual({None}, set(row.values()))
