"""
Webserver definition - a minimal nicescholia template with an empty endpoint
table, ready to be pointed at the KGI4NFDI registry.

The page is nicescholia's own: header, menu, footer, the endpoint grid with its
columns and its colour legend, all imported from nscholia. Only the endpoint
list is ours, and it is empty - see Endpoints.get_endpoints below.

Created on 2026-09-29

@author: danielviladrich
"""

from dataclasses import dataclass
from typing import Any, Dict

from ngwidgets.input_webserver import InputWebserver, InputWebSolution, WebserverConfig
from nscholia.endpoint_dashboard import EndpointDashboard
from nscholia.endpoints import UpdateStateCache

import kgi_interop_monitor


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
    # authorship undecided - see the scoping discussion
    authors = ""
    doc_url = "https://github.com/KGI4NFDI/kgi-interop-monitor"
    chat_url = "https://github.com/KGI4NFDI/kgi-interop-monitor/discussions"
    cm_url = "https://github.com/KGI4NFDI/kgi-interop-monitor"
    license = "MIT"

    longDescription = f"""{name} version {version}
{description}

  Created by {authors} on {date} last updated {updated}"""


class Endpoints:
    """
    endpoints access - the whole customization surface of this template

    nscholia.endpoints.Endpoints reads snapquery's bundled samples; this one
    lists nothing, so the dashboard renders an empty table.
    """

    def get_endpoints(self) -> Dict[str, Any]:
        """
        list all endpoints

        TODO fill out: one lodstorage.query.Endpoint per KGI registry record,
        keyed by a short id

            Endpoint(name="MatWerk", lang="sparql", method="POST",
                     endpoint="https://.../sparql", website="https://...")

        The dashboard also reads a non-field group attribute for the grouping
        column, so set endpoint.group after construction. Filling the Triples
        and Last Update columns needs update_state_query_for_endpoint and
        runQuery here as well - neither is called while this returns nothing.

        Returns:
            mapping of endpoint key to Endpoint - empty for now
        """
        endpoints = {}
        return endpoints


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
        # triple counts measured with real queries, cached on disk between runs
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
            # Instantiate the View Component
            self.endpoint_dashboard = EndpointDashboard(self)
            self.endpoint_dashboard.setup_ui()

        await self.setup_content_div(show)
