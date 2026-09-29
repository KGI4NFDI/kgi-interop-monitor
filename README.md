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
with an **empty endpoint table**, ready to be pointed at the SPARQL endpoints of the
[KGI4NFDI](https://base4nfdi.de/projects/kgi4nfdi) registry.

Everything on the page is nicescholia's own code. This repository supplies only the
endpoint list, which is currently empty.

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
and an empty table. `/docs`, the generated OpenAPI page, comes for free.

## There is no HTML

Not here, and none in nicescholia either. [NiceGUI](https://nicegui.io) builds the
page in Python and pushes every widget to the browser over a websocket. So
`curl` returns an almost empty shell, and a browser that cannot open the socket shows
"Connection lost. Trying to reconnect…" — that is the framework, not a fault.

nicescholia is pinned to git `main` in `pyproject.toml`. The PyPI release (0.0.4)
predates the endpoint monitor and builds its own endpoint list internally, so the
swap below would have no effect on it.

## Filling it in

Everything lives in one file,
[`src/kgi_interop_monitor/nicekgi.py`](src/kgi_interop_monitor/nicekgi.py). The one
place to fill out is `Endpoints.get_endpoints`: return one
`lodstorage.query.Endpoint` per registry record, keyed by a short id. Measuring the
Triples and Last Update columns needs two further methods on the same class, which
its docstring names.

## Tests

```bash
scripts/test
```

unittest, via `ngwidgets.webserver_test.WebserverTest` — the harness nicescholia
uses. It starts the webserver in-process, with no browser and no network, and
checks that the nicescholia pages are registered, that the version metadata is
right and that the endpoint list is still empty.

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
