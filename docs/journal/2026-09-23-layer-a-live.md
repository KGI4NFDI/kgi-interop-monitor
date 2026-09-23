# 2026-09-23 Layer A, first live runs

Two runs of `kgi-interop-monitor run --layers A` from the development machine
(vantage `local/windows`), 22 to 23 seconds each, against the 35 records of the
live registry.

## Result of the second run (after the fixes below)

| | Now | Checklist (Jul/Aug) |
|---|---|---|
| Records | 35 | 34 |
| Working as registered | 10 | 10 |
| Working after repair | 21 | 18 |
| No access point (A1) | 3 | 3 |
| Prose in `dcat:endpointURL` (A5) | 2 (GND, DSKG) | 2 |
| Duplicate pairs (A6) | 2 (FactGrid, Semantic Kompakkt) | FactGrid, MatWerk |

Grades: A 10, A* 11, dump 3, none 11. Every A* would be A if its registry
record were fixed; that is the cheapest improvement available.

## What changed since July, record by record

Compared with `case_study/working_endpoints.json`:

| Record | July | Now | Why |
|---|---|---|---|
| GovData (KGR9) | none | `https://www.govdata.de/sparql` | registered URL is a "sparql-assistent" page; new candidate rule |
| B3Kat (KGR25) | none | `https://lod.b3kat.de/sparql` | registered URL is a documentation page; new candidate rule |
| Nomisma (KGR40) | none | `https://nomisma.org/query` | `/query` candidate added in this session |
| RADAR (KGR85) | none | works as registered | it was flapping in July (KPI draft K5) |
| GESIS KG (KGR80) | works as registered | HTTP 404 | went away |
| TweetsCov19 (KGR62) | works as registered | HTTP 503 | down at the time of the run |

The count of 34 in July was an instrument artefact: the census keyed records
by title, and two records are both called "Semantic Kompakkt". The registry
has 35 datasets and has had them since July. This is a third instance of the
checklist's lesson about instruments: identity by title silently merges
duplicates.

## Things the live run caught in the instrument

1. **Grade C without measuring B or C.** The grade treated a gating probe that
   had not run as cleared. Fixed in `2a6cf55`; a missing gate now holds the
   grade.
2. **Packed value, first part wins.** ORKG registers two URLs in one value.
   The first version stopped at the first part that answered. Right by luck
   this time. All parts are now tried.
3. **Fragment hid a UI route.** NFDI4Earth's value ends in
   `#/dataset/knowledge-graph/query`. It "worked as registered" only because
   HTTP clients drop fragments. Now an A7 warning.
4. **Missing candidate.** Nomisma answers on `/query`; added.

## Observations worth a human look

- **ORKG's C1 defect may be gone.** The checklist records the registered ORKG
  endpoint as an empty Virtuoso with 5,589 triples. `https://orkg.org/triplestore`
  answers `COUNT(*)` with 6,543,341 today. Layer C will confirm or refute it.
- **The fix for NFDI4BIOIMAGE has waited in the tracker since June.**
  kgi4nfdi_registry_data issue #23 (opened 2026-06-25, no comments) asks to
  change the endpoint to `https://kg.nfdi4bioimage.de/rdf/N4BIKG/query`. That
  URL returns HTTP 502 today, and the registered one serves a web page. So the
  record is wrong, and applying the requested fix would not make it work yet.
- **Five records serve a web page with no SPARQL service found nearby:** the two
  uni-mannheim `query.*` hosts (Aktienführer, MaschinenBauIndustrie),
  NFDI4BIOIMAGE, NFDI4Objects and (before `/query`) Nomisma. The uni-mannheim
  hosts look like QLever UIs whose API lives elsewhere; that needs asking, not
  guessing.
- **MatWerk's second record (KGR34)** points at a host that no longer resolves.
  A6 cannot tell it is a duplicate of KGR74 (different host, different title),
  as predicted during scoping.
- **Every proposal is a proposal.** For example `https://www.govdata.de/sparql`
  answers SPARQL, but whether it serves the graph the record describes is a
  layer C question and, in the end, a question for the operator.
