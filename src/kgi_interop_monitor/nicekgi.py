"""
Webserver definition - nicescholia dashboard for the SPARQL endpoints of the
KGI4NFDI registry.

Created on 2026-09-29

@author: danielviladrich
"""

import html
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lodstorage.query import Endpoint, Query
from lodstorage.sparql import SPARQL
from ngwidgets.input_webserver import InputWebserver, InputWebSolution, WebserverConfig
from nicegui import Client, run, ui
from nscholia.endpoint_dashboard import EndpointDashboard
from nscholia.endpoints import Endpoints as ScholiaEndpoints
from nscholia.endpoints import UpdateStateCache

import kgi_interop_monitor
from kgi_interop_monitor.kgs import KnowledgeGraph, KnowledgeGraphs
from kgi_interop_monitor.registration import RegistrationForm


def build_date(default: str) -> str:
    """
    the date the image build passes in as KGI_BUILT_AT - the commit date on
    main, the start of the build for a manual run

    Args:
        default: the date to show outside an image

    Returns:
        the date as YYYY-MM-DD
    """
    built_at = os.environ.get("KGI_BUILT_AT", "")
    date = built_at[:10] or default
    return date


@dataclass
class Version:
    """
    Version handling for nicekgi
    """

    # the page title and the name in the menu banner of every page
    name = "KGI Monitor (Beta)"
    version = kgi_interop_monitor.__version__
    date = "2026-09-29"
    # the About page shows it as "updated"
    updated = build_date("2026-09-29")
    description = "nicescholia dashboard for the KGI4NFDI registry endpoints"
    authors = ""
    doc_url = "https://github.com/KGI4NFDI/kgi-interop-monitor"
    chat_url = "https://github.com/KGI4NFDI/kgi-interop-monitor/discussions"
    cm_url = "https://github.com/KGI4NFDI/kgi-interop-monitor"
    license = "MIT"

    longDescription = f"""{name} version {version}
{description}

  Created by {authors} on {date} last updated {updated}"""


# sent with every query: who is asking and where to find out more
USER_AGENT = f"kgi-interop-monitor/{Version.version} (+{Version.cm_url})"
# the registry refers to consortia, institutions and contacts by Wikidata item
WIKIDATA_ENTITY = "http://www.wikidata.org/entity/"
WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"


class Endpoints(ScholiaEndpoints):
    """
    the KGI4NFDI registry endpoints; nicescholia's Endpoints supplies the
    queries the dashboard measures with
    """

    # consortium shown for the knowledge graphs whose registry record names none
    NO_CONSORTIUM = "(no consortium in the registry)"
    # the id of a registry record: KGR and its number
    REGISTRY_ID = re.compile(r"KGR\d+")
    # the fields of the registration form as resources/queries/registry.rq
    # names them, with their column header
    REGISTRY_FIELDS = {
        "name": "Name",
        "endpoint": "SPARQL endpoint",
        "website": "Website",
        "description": "Description",
        "consortium": "Consortium",
        "institution": "Institution",
        "contact": "Contact point",
        # license, subjects and KG software: form fields the registry does not
        # store - only suggestions
        "license": "License",
        "subjects": "Subjects",
        "kg_software": "KG software",
        "ontologies": "Ontologies",
        "api": "API",
        "dumps": "Dumps",
    }

    def __init__(self, yaml_path: Optional[str] = None):
        """
        constructor

        Args:
            yaml_path: the knowledge graph config file, the shipped one when None
        """
        super().__init__()
        self.kgs = KnowledgeGraphs.of_yaml(yaml_path)
        # sources done in the running federation check, None when none runs
        self.checked_sources: Optional[int] = None

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

    @classmethod
    def query(cls, name: str) -> str:
        """
        the SPARQL query of the given name

        Args:
            name: the file name in resources/queries, without .rq

        Returns:
            the query text
        """
        path = Path(__file__).parent / "resources" / "queries" / f"{name}.rq"
        query = path.read_text()
        return query

    def runQuery(self, query: Query) -> Optional[List[Dict[str, Any]]]:
        """
        nicescholia's runQuery, sent with the user agent of this project

        Args:
            query: the query to run

        Returns:
            the query result as list of dicts
        """
        endpoint = SPARQL(query.endpoint, agent=USER_AGENT)
        if query.params.has_params:
            query.apply_default_params()
        qlod = endpoint.queryAsListOfDicts(
            query.query, param_dict=query.params.params_dict
        )
        return qlod

    def check_federation(self) -> Dict[str, Dict[str, Optional[str]]]:
        """
        send the federated test query for every ordered pair of endpoints

        Each source is asked the plain query first; when that fails, its
        federated queries are not sent.

        Returns:
            by registry id of the source, then of the target: None when the
            source could call the target, else the error - under its own id
            the outcome of the plain query
        """
        endpoints = self.get_endpoints()
        plain_query = self.query("plain")
        federation_query = self.query("federation")
        self.checked_sources = 0
        matrix = {}
        for source, source_ep in endpoints.items():
            sparql = SPARQL(source_ep.endpoint, agent=USER_AGENT)
            sparql.sparql.setTimeout(20)
            matrix[source] = {}
            for target in [source] + [key for key in endpoints if key != source]:
                query = plain_query
                if target != source:
                    target_url = endpoints[target].endpoint
                    query = federation_query.replace("TARGET", target_url)
                try:
                    qlod = sparql.queryAsListOfDicts(query)
                    error = None if qlod else "empty result"
                except Exception as ex:
                    error = f"{type(ex).__name__}: {ex}"
                matrix[source][target] = error
                if error and target == source:
                    break
            self.checked_sources += 1
        return matrix

    def get_registry_metadata(self) -> Dict[str, Dict[str, List[str]]]:
        """
        query the live registry for the registration form fields of every
        registered knowledge graph

        Returns:
            by registry id, sorted by its number: the values of each field
            that has any

        Raises:
            ValueError: if a record's id is not KGR and a number - the page
                sorts and links the records by it
        """
        sparql = SPARQL(self.kgs.source, agent=USER_AGENT)
        qlod = sparql.queryAsListOfDicts(self.query("registry"))
        metadata = {}
        for record in qlod:
            key = record["kg"].rsplit("/", 1)[-1]
            if not self.REGISTRY_ID.fullmatch(key):
                raise ValueError(
                    f"registry record {record['kg']} has no KGR<number> id"
                )
            values = metadata.setdefault(key, {}).setdefault(record["field"], [])
            values.append(str(record["value"]))
        for fields in metadata.values():
            for values in fields.values():
                values.sort()
        metadata = dict(
            sorted(metadata.items(), key=lambda item: int(item[0][len("KGR") :]))
        )
        return metadata

    def get_wikidata_labels(
        self, metadata: Dict[str, Dict[str, List[str]]]
    ) -> Dict[str, str]:
        """
        ask Wikidata for the English labels of the Wikidata items among the
        registry metadata values

        Args:
            metadata: the registry metadata as get_registry_metadata returns it

        Returns:
            mapping of item IRI to English label - items without one are missing
        """
        items = sorted(
            {
                value
                for fields in metadata.values()
                for values in fields.values()
                for value in values
                if value.startswith(WIKIDATA_ENTITY)
            }
        )
        labels = {}
        if items:
            query = self.query("labels").replace(
                "ITEMS", " ".join(f"<{item}>" for item in items)
            )
            sparql = SPARQL(WIKIDATA_ENDPOINT, agent=USER_AGENT)
            for record in sparql.queryAsListOfDicts(query):
                labels[str(record["item"])] = str(record["label"])
        return labels


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
        render nicescholia's dashboard, mark it as beta and show the Consortium
        column - and start the check right away when there are no current
        measurements, instead of waiting for a click on Refresh
        """
        super().setup_ui()
        for element in ui.context.client.elements.values():
            if getattr(element, "text", None) == "Endpoint Monitor":
                element.text = "Endpoint Monitor (Beta)"
        self.show_consortium(self.grid.ag_grid.options["columnDefs"])
        self.grid.update()
        # never measured, or longer ago than nicescholia's daily refresh
        if self.update_state_cache.is_stale:
            ui.timer(0.1, self.check_all, once=True)


class KgiWebserver(InputWebserver):
    """
    The main webserver class
    """

    @classmethod
    def get_config(cls) -> WebserverConfig:
        config = WebserverConfig(
            short_name="kgi-monitor",
            timeout=6.0,
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
        # the last federation check, kept in memory only
        self.federation = {}

        @ui.page("/endpoints")
        async def endpoints(client: Client):
            return await self.page(client, KgiSolution.endpoints)

        @ui.page("/federation")
        async def federation(client: Client):
            return await self.page(client, KgiSolution.federation)


class KgiSolution(InputWebSolution):
    """
    Handling specific page requests for a client session.
    """

    # menu buttons of the ngwidgets default menu that are not shown
    HIDDEN_BUTTONS = ("settings", "github", "help")
    # menu buttons of the ngwidgets default menu shown under another name - the
    # home page is the registry metadata matrix
    RENAMED_BUTTONS = {"chat": "feedback", "home": "metadata"}
    # the height of the footer banner in px
    FOOTER_HEIGHT = 22
    # menu buttons of the ngwidgets default menu shown with another icon
    BUTTON_ICONS = {"home": "table_chart"}
    # ngwidgets' log panel under the page content - a page may switch it off
    with_log = True
    # the intro of the registry page, one line each: what it is for, what to do
    REGISTRY_INTRO = (
        "Is the registry metadata of your knowledge graph up to date?",
        "1. Unfold your knowledge graph and review its metadata.",
        "2. Open its GitHub update issue - it comes filled with the registered values.",
        "3. Correct or complete the values in the issue before you submit it.",
    )
    # background of the header row of a knowledge graph
    HEADER_COLOR = "#e8eaf6"
    # the space in px above the registry table: menu, intro and buttons
    TABLE_TOP = 250
    # folding by knowledge graph: the keys of the folded ones live in the
    # browser, so folding needs no round trip and keeps the scroll position
    # - until the first fold there is no set and every knowledge graph is
    # folded, so the page opens folded without waiting for the browser
    FOLD_FILTER = (
        "node => node.data.kind === 'kg'"
        " || (window.kgiCollapsed ? !window.kgiCollapsed.has(node.data.key) : false)"
    )
    FOLD_ROW_CLASS = (
        "params => params.data.kind !== 'kg' ? '' : 'kgi-kg'"
        " + (!window.kgiCollapsed || window.kgiCollapsed.has(params.data.key)"
        " ? ' kgi-collapsed' : '')"
    )
    # a click on a header row, but not on its link, folds or unfolds it
    FOLD_CLICK = (
        "params => {"
        " if (params.data.kind !== 'kg' || params.event.target.closest('a')) return;"
        " if (!window.kgiCollapsed) {"
        " window.kgiCollapsed = new Set();"
        " params.api.forEachNode(node => node.data.kind === 'kg'"
        " && window.kgiCollapsed.add(node.data.key)); }"
        " const collapsed = window.kgiCollapsed;"
        " const key = params.data.key;"
        " collapsed.has(key) ? collapsed.delete(key) : collapsed.add(key);"
        " params.api.onFilterChanged();"
        " params.api.redrawRows({rowNodes: [params.node]}); }"
    )
    # the registry table: small text, tight rows, links on one line, a fold
    # marker on the header rows
    REGISTRY_CSS = r"""
.kgi-registry {
  --ag-font-size: 12px;
  --ag-header-height: 26px;
  --ag-cell-horizontal-padding: 6px;
}
.kgi-registry .ag-cell {
  line-height: 16px;
  padding-top: 3px;
  padding-bottom: 3px;
}
.kgi-registry .ag-cell a {
  white-space: nowrap;
}
.kgi-registry .kgi-issue {
  text-decoration: underline;
}
.kgi-registry .kgi-kg {
  cursor: pointer;
}
.kgi-registry .kgi-toggle::before {
  content: "\25BE\00a0";
}
.kgi-registry .kgi-collapsed .kgi-toggle::before {
  content: "\25B8\00a0";
}
"""

    def link_button(
        self, name: str, target: str, icon_name: str, new_tab: bool = True
    ) -> Optional[ui.link]:
        """
        ngwidgets' menu button, hidden or renamed for the reduced menu

        Args:
            name: the name to be displayed on the button
            target: the target URL opened when the button is clicked
            icon_name: the name of the icon to be displayed on the button
            new_tab: if True open the link in a new tab

        Returns:
            the link holding the button, None when the button is hidden
        """
        link_btn = None
        if name not in self.HIDDEN_BUTTONS:
            icon_name = self.BUTTON_ICONS.get(name, icon_name)
            name = self.RENAMED_BUTTONS.get(name, name)
            link_btn = super().link_button(name, target, icon_name, new_tab=new_tab)
        return link_btn

    def setup_menu(self, detailed: Optional[bool] = None):
        """
        ngwidgets' menu banner, with the tool's name and the KGI4NFDI logo at
        its right - the banner is on every page

        Args:
            detailed: if True add github, chat and help links
        """
        super().setup_menu(detailed)
        logo = Path(__file__).parent / "resources" / "kgi4nfdi_logo.png"
        kgi4nfdi_url = "https://base4nfdi.de/projects/kgi4nfdi"
        # name and logo stay together, at the right also when the menu wraps
        with self.header.classes("items-center"):
            with ui.row().classes("ml-auto items-center no-wrap"):
                ui.label(self.config.version.name).classes("text-h6")
                with ui.link(target=kgi4nfdi_url, new_tab=True):
                    ui.image(logo).props("fit=contain").style(
                        "height: 36px; width: 148px"
                    )

    def configure_menu(self):
        """
        add the endpoint dashboard and the federation matrix to the menu - the
        registry metadata matrix is the home page
        """
        self.link_button("endpoints", "/endpoints", "lan", new_tab=False)
        self.link_button("federation", "/federation", "grid_on", new_tab=False)

    async def setup_footer(self, *args, **kwargs):
        """
        the footer: a link to nicescholia - and ngwidgets' log panel above
        it, unless the page switched it off
        """
        kwargs.setdefault("with_log", self.with_log)
        await super().setup_footer(*args, **kwargs)
        self.footer.clear()
        # a thin banner, so it covers little of the page behind it
        self.footer.style(f"padding: 2px 16px; height: {self.FOOTER_HEIGHT}px")
        with self.footer:
            ui.link(
                "Powered by nicescholia", "https://github.com/WolfgangFahl/nicescholia"
            ).style("color: #fff; font-size: 12px; line-height: 18px")

    async def home(self):
        """
        The home page: the registry metadata matrix
        """
        await self.registry()

    async def endpoints(self):
        """
        The endpoint dashboard: nicescholia's monitor of the registered SPARQL
        endpoints
        """

        def show():
            self.endpoint_dashboard = KgiEndpointDashboard(self)
            self.endpoint_dashboard.setup_ui()

        await self.setup_content_div(show)

    async def federation(self):
        """
        The federation matrix: can the endpoint of the row call the endpoint
        of the column via SERVICE?
        """

        def show():
            provider = self.webserver.endpoints
            endpoints = provider.get_endpoints()
            column_defs = [{"headerName": "Source", "field": "name", "pinned": "left"}]
            for key in endpoints:
                column_defs.append({"headerName": key, "field": key, "width": 70})

            def show_matrix():
                rows = []
                for source, errors in self.webserver.federation.items():
                    row = {"key": source, "name": f"{source} {endpoints[source].name}"}
                    for target, error in errors.items():
                        # the source itself does not answer / cannot call target
                        failed = "🔴" if target == source else "🟡"
                        row[target] = failed if error else "🟢"
                        row[f"{target}_error"] = error
                    rows.append(row)
                grid.options["rowData"] = rows
                grid.update()

            async def refresh():
                if provider.checked_sources is not None:
                    return
                provider.checked_sources = 0
                try:
                    self.webserver.federation = await run.io_bound(
                        provider.check_federation
                    )
                finally:
                    provider.checked_sources = None

            def show_progress():
                checked = provider.checked_sources
                if checked is not None:
                    detail.content = (
                        f"Checking federation ... {checked} of {len(endpoints)} sources"
                    )
                elif detail.content.startswith("Checking"):
                    detail.content = hint
                    show_matrix()

            def show_detail(event):
                source, target = event.args["data"]["key"], event.args["colId"]
                if target not in endpoints:
                    return
                source_ep, target_ep = endpoints[source], endpoints[target]
                query = Endpoints.query("plain")
                if target != source:
                    query = Endpoints.query("federation")
                    query = query.replace("TARGET", target_ep.endpoint)
                error = event.args["data"].get(f"{target}_error")
                detail.content = (
                    f"source: {source} {source_ep.name} {source_ep.endpoint}\n"
                    f"target: {target} {target_ep.name} {target_ep.endpoint}\n"
                    f"{query}\n{error or 'ok'}"
                )

            # titled like nicescholia's Endpoint Monitor
            with ui.row().classes("w-full items-center mb-4"):
                ui.label("Federation Monitor (Beta)").classes("text-2xl font-bold")
                ui.button("Refresh", icon="refresh", on_click=refresh)
            hint = "click a cell for its query and error"
            detail = ui.code(hint, language="text")
            options = {"columnDefs": column_defs, "rowData": []}
            grid = ui.aggrid(options, auto_size_columns=False).classes("h-screen")
            grid.on("cellClicked", show_detail)
            show_matrix()
            ui.timer(1.0, show_progress)

        await self.setup_content_div(show)

    @staticmethod
    def registry_cell(value: str, labels: Dict[str, str]) -> str:
        """
        one registry metadata value as HTML: Wikidata items by their label and
        URLs as links, anything else as registered

        Args:
            value: the value as the registry stores it
            labels: the English labels of the Wikidata items

        Returns:
            the HTML of the value
        """
        text = html.escape(value)
        # links stay on one line - the title holds the URL a narrow cell cuts
        if value.startswith(WIKIDATA_ENTITY):
            label = labels.get(value, value.removeprefix(WIKIDATA_ENTITY))
            text = (
                f'<a href="{text}" target="_blank" title="{text}">'
                f"{html.escape(label)}</a>"
            )
        elif value.startswith(("http://", "https://")) and " " not in value:
            text = f'<a href="{text}" target="_blank" title="{text}">{text}</a>'
        return text

    @classmethod
    def property_row(
        cls, key: str, header: str, values: List[str], labels: Dict[str, str]
    ) -> Dict[str, str]:
        """
        the row of one property of a knowledge graph: its registered values,
        labelled missing when there are none

        Args:
            key: the registry id
            header: the name of the property
            values: the registered values
            labels: the English labels of the Wikidata items

        Returns:
            the row
        """
        registered = "<br>".join(cls.registry_cell(value, labels) for value in values)
        row = {
            "kind": "property",
            "key": key,
            "property": header,
            "registered": registered or "<i>missing</i>",
            "action": "",
        }
        return row

    @classmethod
    def registry_rows(
        cls,
        key: str,
        fields: Dict[str, List[str]],
        labels: Dict[str, str],
        properties: Dict[str, str],
    ) -> List[Dict[str, str]]:
        """
        the rows of one knowledge graph: a header with its id, its name under
        Registered and the issue link under Action, then one row per property

        Args:
            key: the registry id
            fields: the registered values per field
            labels: the English labels of the Wikidata items
            properties: the fields to show, with their names

        Returns:
            the rows
        """
        name = (fields.get("name") or [""])[0]
        title = f'<span class="kgi-toggle"></span><b>{html.escape(key)}</b>'
        rows = [
            {
                "kind": "kg",
                "key": key,
                "property": title,
                "registered": f"<b>{html.escape(name)}</b>",
                "action": cls.form_link(key, fields, labels),
            }
        ]
        for field, header in properties.items():
            rows.append(cls.property_row(key, header, fields.get(field, []), labels))
        return rows

    @staticmethod
    def form_link(
        key: str, fields: Dict[str, List[str]], labels: Dict[str, str]
    ) -> str:
        """
        the link that opens the registry's data contribution form, filled
        with the registered values, as a new issue on GitHub

        Args:
            key: the registry id
            fields: the registered values per field
            labels: the English labels of the Wikidata items

        Returns:
            the HTML of the link
        """
        url = html.escape(RegistrationForm(key, fields, labels).url(), quote=True)
        hint = (
            "a new GitHub issue with the registered values - sent only if you submit it"
        )
        link = (
            f'<b>(<a class="kgi-issue" href="{url}" target="_blank" title="{hint}">'
            "Open GitHub update issue</a>)</b>"
        )
        return link

    async def registry(self):
        """
        The registry metadata: for every registered knowledge graph a header
        row and one row per field of the registration form, queried live from
        the registry, with the link to update it - without the log panel, the
        status next to the buttons shows the errors
        """
        self.with_log = False

        def show():
            provider = self.webserver.endpoints
            column_defs = [
                {
                    "headerName": "Property",
                    "field": "property",
                    "width": 130,
                },
                # wide enough for the issue link on one line
                {"headerName": "Registered", "field": "registered", "flex": 1},
                {"headerName": "Action", "field": "action", "width": 200},
            ]

            async def refresh():
                status.text = "Querying the registry ..."
                try:
                    metadata = await run.io_bound(provider.get_registry_metadata)
                    labels = await run.io_bound(provider.get_wikidata_labels, metadata)
                except Exception as ex:
                    status.text = (
                        f"Querying the registry failed: {type(ex).__name__}: {ex}"
                    )
                    return
                rows = []
                for key, fields in metadata.items():
                    rows.extend(
                        self.registry_rows(
                            key, fields, labels, provider.REGISTRY_FIELDS
                        )
                    )
                grid.options["rowData"] = rows
                grid.update()
                status.text = f"{len(metadata)} knowledge graphs registered"

            def fold(collapse: bool):
                keys = []
                if collapse:
                    rows = grid.options["rowData"]
                    keys = [row["key"] for row in rows if row["kind"] == "kg"]
                ui.run_javascript(f"window.kgiCollapsed = new Set({json.dumps(keys)})")
                grid.run_grid_method("onFilterChanged")
                grid.run_grid_method("redrawRows")

            with ui.column().classes("w-full gap-3 pb-3"):
                # titled like nicescholia's Endpoint Monitor
                with ui.row().classes("items-center"):
                    ui.label("Metadata Monitor (Beta)").classes("text-2xl font-bold")
                    ui.button("Refresh", icon="refresh", on_click=refresh)
                    ui.button(
                        "Collapse all", icon="unfold_less", on_click=lambda: fold(True)
                    )
                    ui.button(
                        "Expand all", icon="unfold_more", on_click=lambda: fold(False)
                    )
                    status = ui.label()
                with ui.column().classes("gap-0"):
                    for line in self.REGISTRY_INTRO:
                        ui.label(line)
            ui.add_css(self.REGISTRY_CSS)
            options = {
                "columnDefs": column_defs,
                # the rows of a knowledge graph stay together - no sorting
                "defaultColDef": {"wrapText": True, "autoHeight": True},
                ":getRowStyle": "params => params.data.kind === 'kg' ? "
                f"{{background: '{self.HEADER_COLOR}'}} : null",
                # a header row folds the rows of its knowledge graph
                ":isExternalFilterPresent": "() => true",
                ":doesExternalFilterPass": self.FOLD_FILTER,
                ":getRowClass": self.FOLD_ROW_CLASS,
                ":onCellClicked": self.FOLD_CLICK,
                "rowData": [],
            }
            grid = ui.aggrid(
                options,
                html_columns=list(range(len(column_defs))),
                auto_size_columns=False,
            ).classes("kgi-registry")
            # fit the window above the footer, so the scrollbar stays in view
            space = self.TABLE_TOP + self.FOOTER_HEIGHT
            grid.style(f"height: calc(100vh - {space}px)")
            ui.timer(0.1, refresh, once=True)

        await self.setup_content_div(show)
