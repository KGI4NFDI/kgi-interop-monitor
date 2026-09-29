# kgi-interop-monitor

[![Github Actions Build](https://github.com/KGI4NFDI/kgi-interop-monitor/actions/workflows/build.yml/badge.svg)](https://github.com/KGI4NFDI/kgi-interop-monitor/actions/workflows/build.yml)
[![GitHub issues](https://img.shields.io/github/issues/KGI4NFDI/kgi-interop-monitor.svg)](https://github.com/KGI4NFDI/kgi-interop-monitor/issues)
[![GitHub closed issues](https://img.shields.io/github/issues-closed/KGI4NFDI/kgi-interop-monitor.svg)](https://github.com/KGI4NFDI/kgi-interop-monitor/issues/?q=is%3Aissue+is%3Aclosed)
[![API Docs](https://img.shields.io/badge/API-Documentation-blue)](https://KGI4NFDI.github.io/kgi-interop-monitor/)
[![License](https://img.shields.io/github/license/KGI4NFDI/kgi-interop-monitor.svg)](https://opensource.org/licenses/MIT)

A minimal [nicescholia](https://github.com/WolfgangFahl/nicescholia) template: it
reproduces the dashboard at
[nicescholia.wikidata.dbis.rwth-aachen.de](https://nicescholia.wikidata.dbis.rwth-aachen.de/)
— header, menu, footer, the endpoint grid with its columns and its 🟢🟡🔴 legend —
for the SPARQL endpoints of the
[KGI4NFDI](https://base4nfdi.de/projects/kgi4nfdi) registry, sorted by NFDI
consortium.

Everything on the page is nicescholia's own code. This repository supplies only the
endpoint list.

## Run it

Python 3.11 or newer (ngwidgets requires it).

```bash
python -m venv .venv
source .venv/bin/activate
scripts/install
kgi-interop-monitor -s            # serve on http://localhost:9001
```

`--port N` to serve elsewhere, `--host` to listen beyond localhost, `-h` for the rest.
Without the console script: `python -m kgi_interop_monitor.cmd -s`.

You should see the **Endpoint Monitor** heading, a Refresh button, the colour legend
and one row per registered endpoint, sorted by consortium. **Refresh** sends every
endpoint nicescholia's triple count query. `/docs`, the generated OpenAPI page, comes for free.

## There is no HTML

Not here, and none in nicescholia either. [NiceGUI](https://nicegui.io) builds the
page in Python and pushes every widget to the browser over a websocket. So
`curl` returns an almost empty shell, and a browser that cannot open the socket shows
"Connection lost. Trying to reconnect…" — that is the framework, not a fault.

nicescholia is pinned to git `main` in `pyproject.toml`. The PyPI release (0.0.4)
predates the endpoint monitor and builds its own endpoint list internally, so the
endpoint list below would have no effect on it.

## The endpoint list

The knowledge graphs are a snapshot of the registry in one config file,
[`src/kgi_interop_monitor/resources/knowledge_graphs.yaml`](src/kgi_interop_monitor/resources/knowledge_graphs.yaml):
one record per registry id with the name, the NFDI consortium, the website and the
endpoint value exactly as the registry stores it. The file header says where and
when it was taken.

- The records come from the registry's own SPARQL endpoint, the KGI hub at
  `https://sparql.kgi.services.base4nfdi.de/api/`.
- The registry has no consortium property. The consortium is the dataset's
  `dcterms:creator` where Wikidata types that creator as an *accepted NFDI
  consortium*.
- The rows are sorted alphabetically by consortium, which puts each
  consortium's knowledge graphs together; those without one come last. The
  Consortium column is nicescholia's own Group column made visible: nicescholia
  groups its rows on that column, but row grouping needs AG Grid Enterprise,
  which NiceGUI does not ship.
- Only endpoint values that are URLs get a row. Missing and prose values
  ("work in progress") are kept in the file but not shown.

`Endpoints` in [`nicekgi.py`](src/kgi_interop_monitor/nicekgi.py) extends
nicescholia's own, so the Triples and Last Update columns are measured with
nicescholia's queries; it only replaces the endpoint list.

## Tests

```bash
scripts/test
```

unittest, via `ngwidgets.webserver_test.WebserverTest` — the harness nicescholia
uses. It starts the webserver in-process, with no browser and no network, and
checks that the nicescholia pages are registered, that the version metadata is
right, that the config file loads and that the registry endpoints are listed with
their consortium, sorted by it.

`scripts/blackisort` formats the sources and `scripts/doc` builds the API
documentation. See [AGENTS.md](AGENTS.md) for the conventions this project
follows.

## Licensing

| What | License |
|---|---|
| Code | MIT (`LICENSE`) |
| Measurement results | CC0-1.0 (`LICENSES/CC0-1.0.txt`) |
| Documentation | CC-BY-4.0 (`LICENSES/CC-BY-4.0.md`) |

Mirrors the KGI4NFDI repositories.
