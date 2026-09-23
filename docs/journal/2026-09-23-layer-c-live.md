# 2026-09-23 Layer C, first live runs

Full run `2026-09-23T0050Z` (layers A to C, 426 s), then a targeted re-run of
MatWerk, Culture KG, SoftwareKG and Wikidata after the fixes in `02560d6`
(see below).

## The checklist's MatWerk findings, reproduced for the right reason

| Row | Checklist (Aug) | Monitor (today) |
|---|---|---|
| C2 | default graph mixes a personal graph `matwerk/joerg` | fail: the default graph is the union of 16 graphs and includes `spreadsheets_inferences` |
| C3 | 165 `owl:Nothing rdfs:subClassOf` rows in one subsumption query | fail: 301 `owl:Nothing rdfs:subClassOf` statements in the store |
| C4 | serves MWO 3.0.1, GitHub releases 3.0.2 | fail: MWO 3.0.1 served, v3.0.2 released |
| C5 | 184 labelled `NFDI_*` against the release's 167 | fail: NFDIcore 184 labelled classes here, 167 in v3.0.5 |

C2 fails through a different graph than the checklist names. The keyword list
catches `spreadsheets_inferences` but cannot see that `joerg` is a person's
working graph. That blind spot was predicted and is still there; a human
reading the graph list in the drill-down sees it.

## Other findings

- **Culture KG (QLever)** serves NFDIcore **3.0.2** while 3.0.5 is released
  (C4), and holds **171** labelled `NFDI_` classes against **149** in the 3.0.2
  release (C5). Hypothesis, not checked: the extra classes are CTO's terms
  minted into the NFDIcore namespace, which is checklist row D1 (26 such
  classes in August). Layer D will have to confirm it.
- **SoftwareKG** has one `owl:Nothing rdfs:subClassOf` statement (C3 fail) and a
  default graph that is the union of five data graphs (C2 warning, for a human
  to judge).
- **data.europa.eu**: 111 reflexive `rdfs:subClassOf` statements (C3 warning);
  194 named graphs, none named like work in progress.
- **ORKG's C1 defect is gone.** The checklist records an empty Virtuoso with
  5,589 triples; today it holds 6,543,341 triples in real data graphs.
- **TweetsKB** answered layer A and B, then returned "502 Proxy Error" to every
  layer C query in the same run: unknown, not fail.

Grades after the run: C for NFDI4Earth, RADAR and data.europa.eu (and the KGI
hub), B for Culture KG, and several records at A* whose grade would be C if
their registry record were fixed (GovData, dblp, ORKG, Wikidata).

## Instrument lessons

1. **C5 counted version lag twice.** It compared MatWerk's MWO (44 labelled
   classes) with the latest release (94) and called it a module. MWO v3.0.1
   has exactly 44. MatWerk serves a complete old version, which is C4's
   finding. C5 now compares with the release of the served version.
2. **The ontology IRI changed in a patch release.** MWO v3.0.1 declares
   `.../mwo/mwo.owl`, v3.0.2 declares `.../mwo`. Matching served ontologies to
   releases by IRI therefore needs curated aliases; that is what
   `references.json` is for, and why it is marked for review.
3. **A definite "no" was reported as "don't know".** Blazegraph in triples mode
   answers any GRAPH pattern with `QuadsOperationInTriplesModeException`. That
   means "no named graphs", so C2 is n/a, not unknown, and Wikidata's
   grade-if-fixed rises from B to C.
4. **An invented expectation in a test.** A live test asserted "more than 100"
   MWO classes; nobody had counted. The release has 94.
