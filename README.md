# kgi-interop-monitor

A monitor for the query layer of the knowledge graphs registered in the
[KGI4NFDI](https://base4nfdi.de/projects/kgi4nfdi) registry. It reads the
registry from the KGI hub, sends every registered SPARQL endpoint the probes of
the D2.1 defect checklist ([`docs/D21_CHECKLIST.md`](docs/D21_CHECKLIST.md)) in
layer order, and keeps the results as a time series so that defects can be
watched as they get fixed.

Status: private test build. Layers A (addressing), B (protocol) and C
(content) are implemented; layer D (vocabulary) is not.

## What it answers

For each of the 35 registry records, and for the KGI hub itself:

| Layer | Question | Checks |
|---|---|---|
| A, addressing | Is there a URL a machine can query? | A1 to A7: access point at all, dump only, not SPARQL, dead, prose in the field, duplicates, works only after normalisation |
| B, protocol | Does it answer an ordinary client? | B1 to B5: all three request forms, errors as errors (not 200), query-shape sensitivity, reachable from the hub through SERVICE, refusals |
| C, content | Can what it serves be trusted? | C1 to C5: populated, no working graphs in the default graph, no materialised inference, current release, the whole ontology rather than a module |

Every result is one of six outcomes: pass, warn, fail, unknown, blocked (not
measured because a lower layer failed) and n/a. The grade is the highest layer
whose gating checks all clear, strictly in order (`none` < `dump` < `A*` < `A`
< `B` < `C`), and each record also carries the grade it would have if its
registry record were fixed. Separately, every endpoint gets a score on the 13
read-only tests of the W3C SPARQL 1.1 Protocol suite, because reaching a layer
does not mean SPARQL 1.1 conformance
([ADR 0003](docs/decisions/0003-compliance-is-a-separate-axis.md)).

Every judgement links to the HTTP requests and responses it was based on.

## Quick start

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]" &&  source ./.venv/bin/activate
kgi-interop-monitor run                 # full ladder against the live registry, about 7 minutes
kgi-interop-monitor page                # results/ -> site/index.html
pytest                                  # offline tests against a local fake endpoint
```

Useful options: `run --only KGR28,KGR74` for single records, `--layers A` for
a quick addressing pass, `--heavy` to also run scan-prone probes on large
stores, `--results DIR` for another results directory.

## Where the results are

Scheduled runs (GitHub Actions, every six hours) commit to the orphan branch
`results`, never to `main`:

- `results/latest.json`: the full last report, with evidence
- `results/history.jsonl`: one compact line per run
- `results/runs/YYYY/MM/*.json.gz`: the full report of the first run of each day
- `site/index.html`: the status page, self-contained

## How it is built

- Raw `http.client`, no SPARQL library, so redirects, dialects and
  errors-with-status-200 stay visible ([ADR 0001](docs/decisions/0001-raw-http-client.md)).
- Dialects are measured, then negotiated for the higher layers, and every
  workaround is reported ([ADR 0002](docs/decisions/0002-dialect-strategy.md)).
- Read-only and paced: one request at a time per host, bounded queries, a
  50 million triple gate for scan-prone probes, no update or PUT requests
  ([ADR 0004](docs/decisions/0004-politeness-budget.md)).
- The probe queries are plain `.rq` files in `src/kgi_interop_monitor/queries/`.
  They are the D2.1 benchmark queries and can be run by hand.
- The reference releases behind C4 and C5 are a curated table,
  `src/kgi_interop_monitor/references.json`.

## Reading the history of this repository

The development history is part of the result. `docs/journal/` has one entry
per session with what was observed live and what went wrong in the
instrument; `docs/decisions/` has the design decisions, with the ones that
need a human marked for review. Each checklist row has its GitHub issue, and
each layer was built on its own branch and merged without squashing.

## Needs a human decision

- The thresholds: the 50 million triple gate, the 5 % tolerance in C5, the
  graph-name hints in C2.
- The reference table: which served ontology counts as a version of which
  release.
- A2 as a warning rather than a failure (SPARQL is optional under the KGI
  D3.1 guidelines, but the checklist lists A2 as a defect).
- Every URL that A7 proposes before anyone changes a registry record.

## Licensing

Mirrors the KGI4NFDI repositories:

| What | License | KGI4NFDI precedent |
|---|---|---|
| Code | MIT (`LICENSE`) | kgi4nfdi-website, data-preparation-scripts |
| Measurement results | CC0-1.0 (`LICENSES/CC0-1.0.txt`) | kgi4nfdi_registry_data |
| Documentation | CC-BY-4.0 (`LICENSES/CC-BY-4.0.md`) | Guidelines |
