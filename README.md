# Results of kgi-interop-monitor

Data branch. The code lives on `main`; scheduled runs commit here, so the
development history on `main` stays readable (see
`docs/decisions/0006-results-branch.md` on `main`).

| Path | What it is |
|---|---|
| `results/latest.json` | Full report of the last run, with the HTTP evidence behind every result |
| `results/history.jsonl` | One compact line per run: grade and one letter per checklist row for every record, plus latency, availability and W3C score |
| `results/runs/YYYY/MM/*.json.gz` | Full report of the first run of each UTC day |
| `site/index.html` | The status page, self-contained; open it in a browser |

Letters in `history.jsonl`, in checklist order A1..C5: P pass, W warn,
F fail, U unknown, B blocked (not measured because a lower layer failed),
N not applicable.

Each commit message names the run and its grade counts. Runs whose control
probe failed are recorded with status `instrument-unhealthy` and judge no
endpoint.

Results are released under CC0 1.0 (`LICENSE`), like the KGI registry data.
