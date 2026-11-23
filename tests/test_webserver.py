"""
Created on 2026-09-29

@author: danielviladrich
"""

import asyncio
import os
import re
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError

from fastapi.testclient import TestClient
from lodstorage.sparql import SPARQL
from ngwidgets.webserver_test import WebserverTest
from nicegui import Client, app, core, ui
from nicegui.page import page

from kgi_interop_monitor import nicekgi
from kgi_interop_monitor.cmd import KgiCmd
from kgi_interop_monitor.kgs import KnowledgeGraph
from kgi_interop_monitor.nicekgi import (
    USER_AGENT,
    KgiEndpointDashboard,
    KgiSolution,
    KgiWebserver,
)
from kgi_interop_monitor.registration import RegistrationForm


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
        for path in ["/", "/endpoints", "/federation", "/settings", "/about"]:
            self.assertIn(path, paths)

    def test_version(self):
        """
        test the version metadata the footer and the About page read
        """
        version = self.ws.config.version
        if self.debug:
            print(version.longDescription)
        self.assertEqual("KGI Monitor (Beta)", version.name)
        self.assertEqual("kgi-monitor", self.ws.config.short_name)
        self.assertTrue(version.version)

    def test_build_date(self):
        """
        test that the updated date is the date the image build passes in, and
        the given default outside an image
        """
        with patch.dict(os.environ, {"KGI_BUILT_AT": "2026-10-29T11:46:39Z"}):
            self.assertEqual("2026-10-29", nicekgi.build_date("2026-09-29"))
        with patch.dict(os.environ, {"KGI_BUILT_AT": ""}):
            self.assertEqual("2026-09-29", nicekgi.build_date("2026-09-29"))

    def test_logo(self):
        """
        test that the KGI4NFDI logo of the menu banner ships with the package
        """
        logo = Path(nicekgi.__file__).parent / "resources" / "kgi4nfdi_logo.png"
        self.assertEqual(b"PNG", logo.read_bytes()[1:4])

    def wait_for_server(self):
        """
        wait until the server thread has started once: the run configuration
        and the /favicon.ico route stay for the later tests of this process
        """
        deadline = time.time() + 10
        started = False
        while not started and time.time() < deadline:
            started = any(
                getattr(route, "path", None) == "/favicon.ico" for route in app.routes
            )
            time.sleep(0.05)
        self.assertTrue(started)

    def render(self, path: str) -> str:
        """
        get a page on an event loop of its own: ngwidgets' test server stops
        after the first test and closes NiceGUI's loop

        Args:
            path: the path of the page

        Returns:
            the HTML of the page
        """
        self.wait_for_server()

        async def on_own_loop(scope, receive, send):
            core.loop = asyncio.get_running_loop()
            await self.ws.app(scope, receive, send)

        with patch.object(core, "loop", core.loop):
            response = TestClient(on_own_loop).get(path)
        self.assertEqual(200, response.status_code)
        html = response.text
        return html

    def test_favicon(self):
        """
        test that a served page links the favicon and that its URL serves the
        KGI icon
        """
        html = self.render("/about")
        link = re.search(r'<link href="([^"]+)" rel="shortcut icon"', html)
        self.assertEqual("/favicon.ico", link.group(1))
        icon = KgiWebserver.RESOURCES / "kgi4nfdi_icon.png"
        self.assertEqual(icon.read_bytes(), self.get_response(link.group(1)).content)

    def test_logo_survives_deleted_client(self):
        """
        test that the logo URL of the menu banner still serves the logo after
        a client that showed it was deleted
        """
        self.wait_for_server()
        with Client(page(""), request=None) as client:
            KgiSolution(self.ws, client).setup_menu()
        images = [e for e in client.elements.values() if isinstance(e, ui.image)]
        url = images[0].props["src"]
        self.assertTrue(url.endswith("kgi4nfdi_logo.png"), url)
        # what NiceGUI calls on each element of a deleted client
        images[0]._handle_delete()
        logo = KgiWebserver.RESOURCES / "kgi4nfdi_logo.png"
        self.assertEqual(logo.read_bytes(), self.get_response(url).content)

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

    def test_mark_repaired(self):
        """
        test that only a rerouted row gets the wrench, with both URLs in its
        tooltip, and that the URL column stays wide enough to show it
        """
        kgs = {
            "KGR1": KnowledgeGraph(
                name="rerouted",
                endpoint="https://a.example.org/query",
                endpoint_url="https://a.example.org/sparql",
            ),
            "KGR2": KnowledgeGraph(
                name="registered", endpoint="https://b.example.org/sparql"
            ),
        }
        column_defs = [{"field": "link", "width": 70}]
        dashboard = SimpleNamespace(
            endpoints_provider=SimpleNamespace(kgs=SimpleNamespace(kgs=kgs)),
            grid=SimpleNamespace(
                ag_grid=SimpleNamespace(options={"columnDefs": column_defs})
            ),
        )
        rows = [
            {"endpoint_key": "KGR1", "link": "<a>Link</a>"},
            {"endpoint_key": "KGR2", "link": "<a>Link</a>"},
        ]
        KgiEndpointDashboard.mark_repaired(dashboard, rows)
        self.assertIn("🔧", rows[0]["link"])
        self.assertIn("registered: https://a.example.org/query", rows[0]["link"])
        self.assertIn("probed: https://a.example.org/sparql", rows[0]["link"])
        self.assertEqual("<a>Link</a>", rows[1]["link"])
        self.assertEqual(80, column_defs[0]["minWidth"])

    def test_registry_rows_flag_probed_endpoint(self):
        """
        test that the registered endpoint stays and gets the warning sign with
        the probed URL in its tooltip - only on the endpoint row
        """
        properties = {"name": "Name", "endpoint": "SPARQL endpoint"}
        registered = {"name": ["KG"], "endpoint": ["https://a.example.org/query"]}
        rows = KgiSolution.registry_rows(
            "KGR1", registered, {}, properties, "https://a.example.org/sparql"
        )
        by_property = {row["property"]: row for row in rows[1:]}
        endpoint = by_property["SPARQL endpoint"]["registered"]
        self.assertIn("https://a.example.org/query", endpoint)
        self.assertIn("⚠️", endpoint)
        self.assertIn("probes https://a.example.org/sparql instead", endpoint)
        self.assertNotIn("⚠️", by_property["Name"]["registered"])
        unflagged = KgiSolution.registry_rows("KGR1", registered, {}, properties)
        self.assertFalse(any("⚠️" in row["registered"] for row in unflagged))

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
        self.assertEqual(len(endpoints), self.ws.endpoints.checked_sources)
        for source, row in matrix.items():
            self.assertEqual(len(endpoints), len(row))
            self.assertEqual({None}, set(row.values()))

    def test_check_federation_source_down(self):
        """
        test that a source that fails the plain query is asked nothing else
        """
        with patch.object(SPARQL, "queryAsListOfDicts", side_effect=OSError("down")):
            matrix = self.ws.endpoints.check_federation()
        for source, row in matrix.items():
            self.assertEqual({source: "OSError: down"}, row)

    def test_get_registry_metadata(self):
        """
        test the registration form fields of the live registry: every
        knowledge graph has a name and only the fields of the form
        """
        metadata = self.ws.endpoints.get_registry_metadata()
        if self.debug:
            print(f"{len(metadata)} knowledge graphs")
        self.assertTrue(len(metadata) > 0)
        for key, fields in metadata.items():
            self.assertRegex(key, r"^KGR\d+$")
            self.assertTrue(fields.get("name"), key)
            self.assertLessEqual(set(fields), set(self.ws.endpoints.REGISTRY_FIELDS))
        culture = metadata["KGR7"]
        self.assertEqual(["Culture Knowledge Graph"], culture["name"])
        self.assertEqual(["https://nfdi4culture.de/sparql"], culture["endpoint"])

    def test_registry_id_fails_loudly(self):
        """
        test that a registry record without a KGR<number> id stops the
        registry query with an error that names the record - no query sent
        """
        rows = [
            {
                "kg": "http://kgi.services.base4nfdi.de/entity/KGR7",
                "field": "name",
                "value": "a",
            },
            {
                "kg": "http://kgi.services.base4nfdi.de/entity/X1",
                "field": "name",
                "value": "b",
            },
        ]
        with patch.object(SPARQL, "queryAsListOfDicts", return_value=rows):
            with self.assertRaisesRegex(ValueError, "entity/X1 has no KGR<number> id"):
                self.ws.endpoints.get_registry_metadata()

    def test_get_wikidata_labels(self):
        """
        test that the Wikidata items among the metadata values get their
        English label and nothing else is sent to Wikidata
        """
        metadata = {
            "KGR7": {
                "name": ["Culture Knowledge Graph"],
                "consortium": ["http://www.wikidata.org/entity/Q98276929"],
            }
        }
        labels = self.ws.endpoints.get_wikidata_labels(metadata)
        if self.debug:
            print(labels)
        self.assertEqual(
            {"http://www.wikidata.org/entity/Q98276929": "NFDI4Culture"}, labels
        )
        self.assertEqual({}, self.ws.endpoints.get_wikidata_labels({}))

    def test_registry_cell(self):
        """
        test that Wikidata items show their label, URLs are links with the URL
        as title and prose is shown as registered
        """
        item = "http://www.wikidata.org/entity/Q98276929"
        labels = {item: "NFDI4Culture"}
        url = "https://nfdi4culture.de/sparql"
        for value, expected in [
            (item, f'<a href="{item}" target="_blank" title="{item}">NFDI4Culture</a>'),
            (
                "http://www.wikidata.org/entity/Q1",
                '<a href="http://www.wikidata.org/entity/Q1" target="_blank"'
                ' title="http://www.wikidata.org/entity/Q1">Q1</a>',
            ),
            (url, f'<a href="{url}" target="_blank" title="{url}">{url}</a>'),
            ("work in progress", "work in progress"),
            ("https://a.org; https://b.org", "https://a.org; https://b.org"),
            ("<b>", "&lt;b&gt;"),
        ]:
            self.assertEqual(expected, KgiSolution.registry_cell(value, labels))

    def test_registry_rows(self):
        """
        test the rows of one knowledge graph: a header with its id, its name
        and the issue link under Action, then one row per property with the
        registered values - missing labelled - and no action
        """
        properties = {"name": "Name", "endpoint": "SPARQL endpoint", "api": "API"}
        registered = {"name": ["ORKG"], "endpoint": ["https://a.org; https://b.org"]}
        rows = KgiSolution.registry_rows("KGR43", registered, {}, properties)
        if self.debug:
            for row in rows:
                print(row)
        header = rows[0]
        self.assertEqual("kg", header["kind"])
        self.assertEqual(
            '<span class="kgi-toggle"></span><b>KGR43</b>', header["property"]
        )
        self.assertEqual("<b>ORKG</b>", header["registered"])
        self.assertTrue(header["action"].startswith('<b>(<a class="kgi-issue"'))
        self.assertIn(RegistrationForm.NEW_ISSUE_URL, header["action"])
        self.assertIn(">Open GitHub update issue</a>)</b>", header["action"])
        by_property = {row["property"]: row for row in rows[1:]}
        self.assertEqual(list(properties.values()), list(by_property))
        self.assertEqual("ORKG", by_property["Name"]["registered"])
        self.assertEqual(
            "https://a.org; https://b.org",
            by_property["SPARQL endpoint"]["registered"],
        )
        self.assertEqual("<i>missing</i>", by_property["API"]["registered"])
        for row in rows[1:]:
            self.assertEqual("", row["action"])

    def test_user_agent(self):
        """
        test that the queries of the home page name this project, not
        nicescholia
        """
        self.assertTrue(USER_AGENT.startswith("kgi-interop-monitor/"))
        endpoints = self.ws.endpoints
        endpoint = list(endpoints.get_endpoints().values())[0]
        query = endpoints.triple_count_query_for_endpoint(endpoint)
        with patch("kgi_interop_monitor.nicekgi.SPARQL") as sparql:
            endpoints.runQuery(query)
        sparql.assert_called_once_with(endpoint.endpoint, agent=USER_AGENT)

    def test_post_then_get(self):
        """
        test that a query the server refuses by POST is sent once more by
        GET, and that any other HTTP error is not retried
        """
        endpoints = self.ws.endpoints
        endpoint = list(endpoints.get_endpoints().values())[0]
        query = endpoints.triple_count_query_for_endpoint(endpoint)
        for code, expected in [
            (403, ["POST", "GET"]),
            (405, ["POST", "GET"]),
            (502, ["POST"]),
        ]:
            methods = []

            def answer(sparql, *_args, **_kwargs):
                methods.append(sparql.method)
                if sparql.method == "POST":
                    raise HTTPError(endpoint.endpoint, code, "refused", None, None)
                return [{"tripleCount": 1}]

            with (
                self.subTest(code=code),
                patch.object(
                    SPARQL, "queryAsListOfDicts", autospec=True, side_effect=answer
                ),
            ):
                if code == 502:
                    with self.assertRaises(HTTPError):
                        endpoints.runQuery(query)
                else:
                    self.assertEqual([{"tripleCount": 1}], endpoints.runQuery(query))
                self.assertEqual(expected, methods)
