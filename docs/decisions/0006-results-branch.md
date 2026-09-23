# 0006 Results live on an orphan branch, one full report per day

Status: accepted, 2026-09-23. Retention is marked for review.

## Context

Scheduled runs produce data every six hours. Committing it to `main` would
bury the hand-written development history under about 120 bot commits a month,
and the development history is itself part of what this repository shows. A
full report with its evidence is about 1.5 MB (180 KB compressed), because
every judgement links to the request and response behind it.

## Decision

- Scheduled runs commit to an orphan branch `results`. `main` never receives
  data, and `results/` is in `.gitignore` there.
- The results directory holds `latest.json` (the full last report, overwritten
  every run so the page can show the evidence), `history.jsonl` (one compact
  line per run, about 4 KB, append-only) and `runs/YYYY/MM/*.json.gz` (the full
  report of the first run of each UTC day).
- The status page is built from that directory, so it can be rebuilt for any
  past state by checking out an older commit of the branch.
- Results are CC0-1.0, like the KGI registry data.

## Consequences

- Growth is about 5 MB a month (one compressed snapshot a day plus history
  lines and the rewritten `latest.json`).
- Evidence for runs other than the first of the day survives only as the
  compact line. A finding that matters should be cited from the daily snapshot
  or copied into the journal.

## Review

- Whether one full snapshot a day is enough, or whether flapping endpoints
  need every run in full for a while.
