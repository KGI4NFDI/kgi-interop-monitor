# 0004 Politeness budget

Status: accepted, 2026-09-23. The thresholds are marked for review.

## Context

The monitored endpoints are production services run by partners, several of
them single virtual machines. Some are among the largest public graphs
(Wikidata, dblp). A monitor that runs every six hours must cost them close to
nothing and must never write.

## Decision

- **Read-only.** Only SELECT, ASK, CONSTRUCT and DESCRIBE are ever sent. No
  update tests, and no request methods other than GET and POST. A PUT to the
  wrong URL can overwrite a graph on a Graph Store Protocol endpoint.
- **Identify.** `User-Agent: kgi-interop-monitor/<version>
  (+https://github.com/danielviladrich)`.
- **One request at a time per host**, with a short pause between requests to the
  same host. Several registry records share a host (six at data.gesis.org), so
  this is enforced per host, not per record.
- **Bounded queries.** Exploratory queries carry a LIMIT. Counting uses
  `COUNT(*)`, which most engines answer from index statistics.
- **Size gate.** Queries that may need a scan (`COUNT(DISTINCT ?s)` for B3,
  counts per named graph for C1 and C2) only run when `COUNT(*)` reported at
  most 50 million triples. Above that the probe reports `unknown` with the
  reason "politeness budget" rather than guessing. (Review: the threshold.)
- **Timeouts** of 10 s to connect and 30 s to read by default, 20 s for the
  size-gated probes. A timeout is a result (`unknown`), never retried within
  the same run.

## Consequences

- B3 cannot reproduce the Wikidata observation from the checklist on a schedule.
  It can be run on demand with an explicit `--heavy` flag.
- The whole run stays in the order of a few hundred small requests.
