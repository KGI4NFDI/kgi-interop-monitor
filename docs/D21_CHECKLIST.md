# Query-layer defect checklist for assessing KG interoperability

Consolidated 2026-08-09 from every measurement pass in this folder. Each row is a
defect observed on live NFDI infrastructure, with the probe that detects it.

Sources: `case_study/registry_census.py` + `.json` (34 KGs, 2026-07-16),
`case_study/size_census.py` (2026-07-25), `alignment_lab/sparql_verify*.py`
(2026-08-08), `alignment_lab/FINDINGS.md`.

The ordering matters. A defect at layer N makes every measurement at layer N+1
unreliable, so a checker that skips a layer silently under-reports the ones above
it. Ontology matching sits at layer D and is meaningless until A through C hold.

---

## Layer A: addressing. Is there a queryable URL at all?

Population: the 34 KGs in the KGI registry. 28 register a SPARQL endpoint.

| # | Defect | Probe | Observed |
|---|---|---|---|
| A1 | No access point of any kind | `dcat:endpointURL` absent on the `DataService`, no dump either | **3 / 34** |
| A2 | Dump or access API only, no SPARQL | access URL present, endpoint absent | **3 / 34** |
| A3 | Registered URL is not a SPARQL endpoint | POST a trivial `ASK {}`; expect SPARQL results JSON | **13 / 34** (`liveness: not-sparql`) |
| A4 | Registered URL is dead | connection error or non-2xx | **5 / 34** |
| A5 | Free text in a typed field | regex the `endpointURL` literal for prose | **2**: GND `"work in progress"`, DSKG `"not available anymore"` |
| A6 | Duplicate entries for one graph | group registry rows by host, compare after case-fold and trailing-slash strip | FactGrid `/query/` and FactGRID `/query`; MatWerk twice under different hosts |
| A7 | Endpoint resolvable only after normalisation | retry with `/sparql` appended, host root replaced, UI path stripped | **7 more** become reachable this way (MaRDI, dblp, FactGrid) |

Net: **10 answer as registered. 18 answer after normalisation.** The gap between
those two numbers is the WP2 job in one line.

**A7 is the one you named.** The registry stores what a human pasted from a
browser, which is the query UI (`/query/`) or the host root, not the protocol
endpoint (`/sparql`). Nothing validates that the stored string is the thing a
client should POST to.

---

## Layer B: protocol. It answers, but does it answer *you*?

| # | Defect | Probe | Observed |
|---|---|---|---|
| B1 | Rejects one POST dialect, accepts the other | send the same query both as `application/x-www-form-urlencoded` and as `Content-Type: application/sparql-query` | MatWerk Virtuoso rejects form-encoded with `SP030 Bad character '%'`, answers the raw dialect fine |
| B2 | **HTTP 200 carrying an error body** | never branch on status alone; require `results` in the parsed JSON | MatWerk returns 200 + `{"error": "Virtuoso 37000 Error SP030..."}` |
| B3 | Query-shape sensitivity, not size sensitivity | compare `COUNT(*)` against `COUNT(DISTINCT ?x)` on the same pattern | `COUNT(*)` returns in 100 to 600 ms on Wikidata's 948M type statements; `COUNT(DISTINCT)` times out |
| B4 | Federation declared but not routable | `SERVICE` with a bound endpoint, then with a variable endpoint | QLever (the KGI hub) rejects variable-endpoint `SERVICE`, so the catalogue can describe federation it cannot route |
| B5 | Server-side refusal unrelated to the query | check for 409 / 403 on a trivial query | GESIS endpoints return 409 |

**B2 is the nastiest**, because it is invisible to the obvious check. And it
caused a measurable false negative in our own instrument: `registry_census.json`
records **10** live endpoints, `working_endpoints.json` records **11**. The extra
one is MatWerk, which the census marked dead because its client used the dialect
Virtuoso rejects and then read a 200 as success with no results.

So the census under-reported layer A because it did not handle layer B. That is
the general hazard, observed on our own code.

---

## Layer C: content. It answers correctly, but with what?

| # | Defect | Probe | Observed |
|---|---|---|---|
| C1 | Live but unpopulated | `SELECT (COUNT(*) AS ?n) WHERE {?s ?p ?o}` plus a named-graph listing | ORKG's registered endpoint is an empty Virtuoso: 5,589 triples, top graphs are Virtuoso's own `localhost:8890/DAV/` and `virtrdf#` |
| C2 | Default graph is a union including working graphs | `SELECT ?g (COUNT(*)) WHERE { GRAPH ?g {?s ?p ?o} } GROUP BY ?g`, then re-run the real query scoped to the release graph | MatWerk's default graph returns 181 subsumption rows; **165 are `owl:Nothing rdfs:subClassOf ...`** from a personal graph `matwerk/joerg`. Scoped to `matwerk/mwo/3.0.1`: 11 clean rows. **91% noise.** |
| C3 | Materialised inference mixed with assertion | look for `owl:Nothing` subsumptions and reflexive/tautological triples | as C2; also an 80,602-triple `spreadsheets_inferences` graph |
| C4 | Endpoint version lags the release | compare `owl:versionIRI` at the endpoint against the published tag | store serves **MWO 3.0.1**, GitHub releases **3.0.2**; all seven `agent role` edges missing live |
| C5 | Endpoint serves a module, not the ontology | count labelled classes in the namespace, compare to the release | serves `nfdicore-extension` (3,964 triples), not full NFDIcore; reports 184 labelled `NFDI_*` against the release's 167 |

---

## Layer D: vocabulary and semantics. Only meaningful once A to C hold.

| # | Defect | Probe | Observed |
|---|---|---|---|
| D1 | Minting into someone else's namespace | list subjects in the hub namespace declared by a module but absent from the hub release | CTO declares **26 axiomatised classes** under `nfdi.fiz-karlsruhe.de/ontology/` that are not in NFDIcore 3.0.5 |
| D2 | Dangling references | hub URIs appearing only as a bare `owl:Class` with no label and no axioms | NFDI4DS carries **10** |
| D3 | Alignment targets a deprecated term | join proposed targets against `owl:deprecated true` | CTO's **only** subsumption into the hub points at `NFDI_0000015`, which is deprecated |
| D4 | Structure hidden in blank nodes | resolve `owl:intersectionOf` members before counting parents | **29** hub classes are parented only through a restriction; a named-superclass scan calls 54 classes unanchored where the true number is 10 |
| D5 | Refinement-migration drift | after any hub class splits, re-check every downstream `IAO_0100001` against its own label and definition | `MWO_0001056` "obsolete **reference** dataset" points at `experimental dataset`; 1203 used twice, 1204 never. See `alignment_lab/RECORD_DEFECT_MWO_0001056.md` |
| D6 | Textual merge instead of `owl:imports` | check for `owl:imports`; count inlined hub declarations | none of MWO, CTO, NFDI4DS, MemO declares `owl:imports`; each inlines 162 to 167 hub class declarations |
| D7 | Alignments absent from the artifact you queried | check whether mappings live in a separate module | NFDIcore's schema.org mapping is in `mappings/schema.owl`, **not** in the release TTL. Querying `nfdicore.ttl` for alignments correctly returns nothing |

---

## Two lessons about the instrument, not the data

**Cross-validation is worthless when both paths share an assumption.** The first
census reported **0** registered endpoints. `dcat:endpointURL` lives on a
`dcat:DataService` linked by `dcat:servesDataset`, not on the dataset or its
distribution. The census looked in the wrong place, then "confirmed" the result a
second way that looked in the same wrong place. True answer: 28 of 34.

**A checker that skips a layer under-reports the layers above it.** B2 cost our
own census one live endpoint (10 reported, 11 actual). Any KPI built on a single
client implementation inherits that client's blind spots.

---

## Prior art, for the "is this a known problem" question

VoID had a `void:sparqlEndpoint` property in 2011, and a LOD-cloud census found
only about **14%** of 562 public endpoints ever populated a VoID description. The
resolvability gap here is a variant of the same endemic registry-metadata failure,
not an NFDI scandal. At 28/34 registered, KGI is already well above that
baseline. The remaining work is resolvability and content trust, which is layers
A through C above, not population.
