"""
Created on 2026-09-29

@author: danielviladrich
"""

from ngwidgets.webserver_test import WebserverTest

from kgi_interop_monitor.cmd import KgiCmd
from kgi_interop_monitor.nicekgi import KgiWebserver


class TestKgiWebserver(WebserverTest):
    """
    Test the nicekgi webserver
    """

    def setUp(self, debug=False, profile=True):
        WebserverTest.setUp(self, KgiWebserver, KgiCmd, debug=debug, profile=profile)

    def test_pages_are_registered(self):
        """
        test that the nicescholia chrome registered its pages

        The pages are not fetched here: NiceGUI builds them over a websocket
        and schedules background tasks on the server event loop, so a plain
        GET from the test client is not how a page is exercised.
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

    def test_endpoints_are_empty(self):
        """
        test the whole customization surface of this template

        get_endpoints is the one place to fill out; until it returns registry
        records the dashboard renders an empty table.
        """
        endpoints = self.ws.endpoints.get_endpoints()
        if self.debug:
            print(endpoints)
        self.assertEqual({}, endpoints)
