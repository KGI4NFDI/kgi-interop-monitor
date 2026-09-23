# 2026-09-23 Layer B, first live run

Run `2026-09-23T0040Z`, layers A and B, 180 seconds from `local/windows`,
35 registry records plus the KGI hub. B3 and B5 were refined after this run
(commit `2e0ee87`); the numbers below are from the run itself.

## Working endpoints at a glance

| Record | Engine | Latency (median ASK, ms) | W3C subset | Triples (COUNT(*)) |
|---|---|---|---|---|
| ClaimsKG | Virtuoso | 100 | 2/13 | 7,720,673 |
| Culture KG | QLever | 117 | 13/13 | 148,670,197 |
| GovData | unknown | 92 | 13/13 | 18,071,168 |
| dblp | QLever | 105 | 13/13 | 1,593,835,256 |
| FactGrid (two records) | Blazegraph | 90, 113 | 11/13 | 150,436,316 |
| **KGI hub** | QLever | 88 | 11/13 | 403 |
| B3Kat | unknown | 144 | 13/13 | COUNT(*) did not answer |
| MaRDI | Blazegraph | 82 | 11/13 | 868,969,832 |
| MatWerk (KGR74) | Virtuoso | 152 | 0/13 | 319,033 |
| NFDI4Earth | Virtuoso | 55 | 5/13 | 50,020,266 |
| Nomisma | unknown | 391 | 6/13 | 14,455,716 |
| ORKG | Virtuoso | 83 | 5/13 | 6,543,341 |
| Question Features Sample | Virtuoso | 100 | 2/13 | 373,221 |
| RADAR | Virtuoso | 98 | 5/13 | 539,262 |
| Semantic Kompakkt (two records) | Blazegraph | 99, 93 | 11/13 | 61,754 |
| SoftwareKG | Virtuoso | 98 | 2/13 | 4,004,821 |
| SoMeSci | Virtuoso | 100 | 2/13 | 405,601 |
| data.europa.eu | Virtuoso | 57 | 8/13 | 1,260,827,001 |
| TweetsKB | Virtuoso | 100 | 0/13 | 2,292,801,662 |
| Wikidata | Blazegraph | 85 | 11/13 | 8,978,930,753 |

Engines: 10 Virtuoso, 5 Blazegraph, 3 QLever, 3 not identified.

## Findings

**The checklist's B-layer defects are all still there, and B4 now has a
mechanism.**

- **H1 (hub, variable SERVICE):** QLever answers `SERVICE ?endpoint` with
  HTTP 400 "Variable endpoint in SERVICE is currently not supported by QLever".
  Confirms checklist B4. Federated Query §4 is informative, so this is a
  capability gap of the hub, not non-compliance.
- **B1 breaks B4 at GESIS.** ClaimsKG, Question Features Sample, SoftwareKG
  and SoMeSci answer GET and form POST but refuse *direct* POST with HTTP 409.
  The KGI hub's bound `SERVICE` call to the same endpoints fails with "SERVICE
  responded with HTTP status code: 409". So QLever federates through direct
  POST, and a block on one request form at the endpoint is exactly what makes
  it unreachable from the hub. TweetsKB, on the same host, gives 502 Proxy Error
  on direct POST, with the same consequence. This explains the checklist's
  "GESIS endpoints return 409" (B5): it is not a blanket refusal but a refusal
  of one request form.
- **MatWerk still answers form POST with 200 plus a Virtuoso `SP030` error**
  (B1, B2), exactly as in the checklist. It also scores 0/13 on the W3C subset.
  Without an Accept header (the manifest sends none) Virtuoso answers in HTML,
  and it answers malformed requests with 200 or a 303 redirect instead of a 4xx.
  Every Virtuoso endpoint in the registry scores 0 to 8 of 13 for the same
  reasons. A client that always sends Accept avoids the first problem, but not
  the second.
- **Nomisma** answers only GET; both POST forms get HTTP 403 from "Orbeon
  Forms", a web framework in front of the store. So the hub cannot reach it
  either (403 through SERVICE).
- **The KGI hub itself scores 11/13.** It rejects `DESCRIBE <http://example.org/>`
  with 400 and answers `CONSTRUCT { <s> <p> 1 } WHERE {}` (relative IRIs, as
  the manifest writes it) with 500.

## Instrument lessons from this run

1. **A B3 "fail" was really slowness.** Nomisma's COUNT(*) takes 10 s, so a
   timed-out COUNT(DISTINCT) there is not the index-versus-scan effect the
   checklist row is about. Now a warning when COUNT(*) itself is slow.
2. **The size gate is a cliff.** NFDI4Earth has 50,020,266 triples, 20,266
   above the 50M gate, so its B3 is `unknown` while a store 1% smaller would
   be measured. The threshold was always marked for review (ADR 0004); a
   cliff this close makes the point.
3. **A score needs its reason next to it.** "0/13" for MatWerk reads like a
   dead endpoint. The failing tests now carry the reason (no Accept header,
   so HTML is the server's default).
4. **Committed with a failing test once** (`c95984a`). The test run was piped
   into `tail`, which hid pytest's exit status. Commits are gated on the real
   exit status since.
