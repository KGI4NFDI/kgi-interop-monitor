"""
Webserver definition - nicescholia dashboard for the SPARQL endpoints of the
KGI4NFDI registry.

Created on 2026-09-29

@author: danielviladrich
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from lodstorage.query import Endpoint
from ngwidgets.input_webserver import InputWebserver, InputWebSolution, WebserverConfig
from nscholia.endpoint_dashboard import EndpointDashboard
from nscholia.endpoints import Endpoints as ScholiaEndpoints
from nscholia.endpoints import UpdateStateCache

import kgi_interop_monitor
from kgi_interop_monitor.kgs import KnowledgeGraph, KnowledgeGraphs


@dataclass
class Version:
    """
    Version handling for nicekgi
    """

    name = "nicekgi"
    version = kgi_interop_monitor.__version__
    date = "2026-09-29"
    updated = "2026-09-29"
    description = "nicescholia dashboard for the KGI4NFDI registry endpoints"
    authors = ""
    doc_url = "https://github.com/KGI4NFDI/kgi-interop-monitor"
    chat_url = "https://github.com/KGI4NFDI/kgi-interop-monitor/discussions"
    cm_url = "https://github.com/KGI4NFDI/kgi-interop-monitor"
    license = "MIT"

    longDescription = f"""{name} version {version}
{description}

  Created by {authors} on {date} last updated {updated}"""


class Endpoints(ScholiaEndpoints):
    """
    the KGI4NFDI registry endpoints; nicescholia's Endpoints supplies the
    queries the dashboard measures with
    """

    # consortium shown for the knowledge graphs whose registry record names none
    NO_CONSORTIUM = "(no consortium in the registry)"

    def __init__(self, yaml_path: Optional[str] = None):
        """
        constructor

        Args:
            yaml_path: the knowledge graph config file, the shipped one when None
        """
        super().__init__()
        self.kgs = KnowledgeGraphs.of_yaml(yaml_path)

    @staticmethod
    def sort_key(item: Tuple[str, KnowledgeGraph]) -> Tuple[bool, str, str, str]:
        """
        alphabetically by consortium, then by name - knowledge graphs without a
        consortium last

        Args:
            item: the registry id and the knowledge graph

        Returns:
            the sort key
        """
        key, kg = item
        sort_key = (
            not kg.consortium,
            (kg.consortium or "").casefold(),
            kg.name.casefold(),
            key,
        )
        return sort_key

    def get_endpoints(self) -> Dict[str, Endpoint]:
        """
        list the registered SPARQL endpoints, sorted by consortium

        Registry records whose endpoint value is missing or prose ("work in
        progress") get no row.

        Returns:
            mapping of registry id to Endpoint, sorted by consortium
        """
        endpoints = {}
        for key, kg in sorted(self.kgs.kgs.items(), key=self.sort_key):
            if not kg.endpoint_is_url:
                continue
            endpoint = Endpoint(
                name=kg.name, lang="sparql", endpoint=kg.endpoint, website=kg.website
            )
            # the Consortium column shows this non-field attribute
            endpoint.group = kg.consortium or self.NO_CONSORTIUM
            endpoints[key] = endpoint
        return endpoints


class KgiEndpointDashboard(EndpointDashboard):
    """
    nicescholia's endpoint dashboard with a Consortium column

    Row grouping needs AG Grid Enterprise, which NiceGUI does not ship, so the
    group is shown as a column and the rows are sorted by it.
    """

    @staticmethod
    def show_consortium(column_defs: List[dict]) -> List[dict]:
        """
        turn nicescholia's hidden Group column into a visible Consortium column

        Args:
            column_defs: the AG Grid column definitions, changed in place

        Returns:
            the column definitions
        """
        for column_def in column_defs:
            if column_def.get("field") == "group":
                column_def.pop("rowGroup", None)
                column_def.update(
                    {
                        "headerName": "Consortium",
                        "hide": False,
                        "sortable": True,
                        "filter": True,
                    }
                )
        return column_defs

    def setup_ui(self):
        """
        render nicescholia's dashboard and show the Consortium column
        """
        super().setup_ui()
        self.show_consortium(self.grid.ag_grid.options["columnDefs"])
        self.grid.update()


class KgiWebserver(InputWebserver):
    """
    The main webserver class
    """

    @classmethod
    def get_config(cls) -> WebserverConfig:
        config = WebserverConfig(
            short_name="nicekgi",
            timeout=6.0,
            copy_right="(c) 2026 Daniel Viladrich",
            version=Version(),
            default_port=9001,
        )
        server_config = WebserverConfig.get(config)
        server_config.solution_class = KgiSolution
        return server_config

    def __init__(self):
        super().__init__(config=KgiWebserver.get_config())
        self.endpoints = Endpoints()
        # measured states, cached on disk between runs
        self.update_state_cache = UpdateStateCache()


class KgiSolution(InputWebSolution):
    """
    Handling specific page requests for a client session.
    """

    async def home(self):
        """
        The main page content
        """

        def show():
            self.endpoint_dashboard = KgiEndpointDashboard(self)
            self.endpoint_dashboard.setup_ui()

        await self.setup_content_div(show)
