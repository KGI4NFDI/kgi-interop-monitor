# kgi-interop-monitor

[![Github Actions Build](https://github.com/KGI4NFDI/kgi-interop-monitor/actions/workflows/build.yml/badge.svg)](https://github.com/KGI4NFDI/kgi-interop-monitor/actions/workflows/build.yml)
[![GitHub issues](https://img.shields.io/github/issues/KGI4NFDI/kgi-interop-monitor.svg)](https://github.com/KGI4NFDI/kgi-interop-monitor/issues)
[![GitHub closed issues](https://img.shields.io/github/issues-closed/KGI4NFDI/kgi-interop-monitor.svg)](https://github.com/KGI4NFDI/kgi-interop-monitor/issues/?q=is%3Aissue+is%3Aclosed)
[![API Docs](https://img.shields.io/badge/API-Documentation-blue)](https://KGI4NFDI.github.io/kgi-interop-monitor/)
[![License](https://img.shields.io/github/license/KGI4NFDI/kgi-interop-monitor.svg)](https://opensource.org/licenses/MIT)

A [nicescholia](https://github.com/WolfgangFahl/nicescholia) dashboard for the SPARQL
endpoints of the [KGI4NFDI](https://base4nfdi.de/projects/kgi4nfdi) registry, sorted by
NFDI consortium. The endpoints come from a snapshot of the registry in
[`knowledge_graphs.yaml`](src/kgi_interop_monitor/resources/knowledge_graphs.yaml)

**Refresh** measures each of them with a triple count query.

## Run locally

Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
scripts/install
kgi-interop-monitor -s            # http://localhost:9001
```

## Run with Docker

```bash
docker build -t kgi-interop-monitor .
docker run --rm -p 9001:9001 -v kgi-states:/home/kgi/.nicescholia kgi-interop-monitor
```

The volume keeps the measured states across restarts.

## Tests

```bash
scripts/test
```

## License

MIT
