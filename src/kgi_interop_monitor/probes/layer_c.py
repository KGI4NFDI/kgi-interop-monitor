"""Layer C, content: it answers correctly, but with what?

Runs on the working endpoint. C1 and C2 read a census of the named graphs
(with counts below the politeness gate, names only above it). C3 counts
footprints of materialised inference. C4 and C5 compare what is served with
the curated reference releases in references.json.

Judgements that need a human are marked as warnings rather than failures:
a union default graph over several release graphs may be intended, and a
graph name is only a hint of what the graph holds.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .. import queries, references
from ..model import Outcome, ProbeResult, blocked, not_applicable
from ..sparql import TRANSPORT, QueryResult, run_query
from .layer_a import Working
from .layer_b import SIZE_GATE

C_TIMEOUT = 20.0
EMPTY_ENOUGH = 10_000
"""Below this many data triples, a store that is mostly engine graphs is empty."""
MODULE_TOLERANCE = 0.05
"""Relative difference in labelled classes tolerated before C5 fails (review)."""

SYSTEM_GRAPHS = [
    (re.compile(r"openlinksw\.com/schemas/"), "Virtuoso"),
    (re.compile(r"^https?://localhost:8890/"), "Virtuoso"),
    (re.compile(r"^urn:activitystreams-owl:map$"), "Virtuoso"),
    (re.compile(r"^urn:core:services:sparql$"), "Virtuoso"),
    (re.compile(r"^http://www\.w3\.org/ns/ldp#?$"), "Virtuoso"),
    (re.compile(r"^http://www\.w3\.org/2002/07/owl#?$"), "Virtuoso"),
    (re.compile(r"^urn:x-arq:"), "Jena"),
]
"""Graphs an engine creates for itself. Evidence: ORKG's July census (top
graphs localhost:8890/DAV/ and virtrdf#) and the Virtuoso default install."""

DEFAULT_GRAPH_ALIASES = [re.compile(r"^http://qlever\.cs\.uni-freiburg\.de/builtin-functions/default-graph$")]
"""Names under which an engine lists its default graph; data, not system."""

WORKING_GRAPH = re.compile(
    r"(test|tmp|temp|draft|scratch|sandbox|backup|private|personal|playground|staging|inferen|debug|experiment)",
    re.I)
"""Graph-name hints of work in progress (review: a personal graph named after
its owner, like MatWerk's /joerg, is invisible to this list)."""


@dataclass
class Census:
    graphs: list[tuple[str, int | None]] = field(default_factory=list)
    with_counts: bool = False
    result: QueryResult | None = None
    error: str | None = None

    def kind(self, graph: str) -> str:
        if any(p.search(graph) for p in DEFAULT_GRAPH_ALIASES):
            return "default-alias"
        if any(p.search(graph) for p, _ in SYSTEM_GRAPHS):
            return "system"
        return "data"

    def data_graphs(self) -> list[tuple[str, int | None]]:
        return [(g, n) for g, n in self.graphs if self.kind(g) == "data"]

    def system_graphs(self) -> list[tuple[str, int | None]]:
        return [(g, n) for g, n in self.graphs if self.kind(g) == "system"]


@dataclass
class CLayer:
    results: dict[str, ProbeResult]
    attempts: list[QueryResult] = field(default_factory=list)
    kpis: dict = field(default_factory=dict)


def not_measurable(dump_only: bool) -> CLayer:
    make = (lambda pid: not_applicable(pid, "no SPARQL endpoint registered (dump or access URL only)")) if dump_only \
        else (lambda pid: blocked(pid, "no working SPARQL URL (see layer A)"))
    return CLayer({pid: make(pid) for pid in ("C1", "C2", "C3", "C4", "C5")})


def _q(working: Working, name: str, purpose: str, **kwargs) -> QueryResult:
    kw = dict(kwargs, read_timeout=min(kwargs.get("read_timeout", C_TIMEOUT), C_TIMEOUT))
    return run_query(working.url, queries.load(name), working.form, purpose=purpose, **kw)


def take_census(working: Working, triples: int | None, heavy: bool, **kwargs) -> Census:
    small = triples is not None and (triples <= SIZE_GATE or heavy)
    r = _q(working, "c_graph_counts" if small else "c_graph_list", "C census", **kwargs)
    if not r.ok:
        return Census(result=r, error=r.detail)
    graphs = []
    for row in r.rows:
        g = row.get("g", {}).get("value")
        if g is None:
            continue
        graphs.append((g, int(float(row["n"]["value"])) if small and "n" in row else None))
    return Census(graphs=graphs, with_counts=small, result=r)


def c1(triples: int | None, census: Census, count_evidence: list[str]) -> ProbeResult:
    ev = count_evidence + (census.result.evidence_ids() if census.result else [])
    if triples is None:
        return ProbeResult("C1", Outcome.UNKNOWN, "COUNT(*) did not answer (see B3), so population is unknown",
                           evidence=ev)
    details = {"triples": triples, "named_graphs": len(census.graphs),
               "system_graphs": [g for g, _ in census.system_graphs()]}
    if triples == 0:
        return ProbeResult("C1", Outcome.FAIL, "live but empty: COUNT(*) is 0", details=details, evidence=ev)
    if census.with_counts and census.graphs:
        data = sum(n or 0 for g, n in census.graphs if census.kind(g) != "system")
        system = sum(n or 0 for _, n in census.system_graphs())
        details.update(data_triples=data, system_triples=system)
        share = system / (data + system) if data + system else 0
        if data == 0 or (share >= 0.5 and data < EMPTY_ENOUGH):
            return ProbeResult("C1", Outcome.FAIL,
                               f"live but unpopulated: {system:,} of {data + system:,} triples are the engine's own graphs",
                               details=details, evidence=ev)
    note = "" if census.graphs or census.error is None else " (graph census not available)"
    return ProbeResult("C1", Outcome.PASS, f"{triples:,} triples in the default graph, "
                       f"{len(census.data_graphs())} data graphs{note}", details=details, evidence=ev)


def c2(triples: int | None, census: Census) -> ProbeResult:
    ev = census.result.evidence_ids() if census.result else []
    if census.error is not None:
        if census.result is not None and census.result.verdict == TRANSPORT:
            return ProbeResult("C2", Outcome.UNKNOWN, f"graph census did not answer: {census.error}", evidence=ev)
        return ProbeResult("C2", Outcome.UNKNOWN, f"graph census failed: {census.error}", evidence=ev)
    data = census.data_graphs()
    if len(data) <= 1:
        return not_applicable("C2", "at most one data graph, so there is nothing to mix")
    working = [g for g, _ in data if WORKING_GRAPH.search(g.split("://", 1)[-1].split("/", 1)[-1])]
    details = {"data_graphs": [{"graph": g, "triples": n} for g, n in data], "working_like": working}
    if not census.with_counts:
        if working:
            return ProbeResult("C2", Outcome.WARN, f"working-like graphs present ({', '.join(working)}); whether the "
                               "default graph includes them was not checked (size gate)", details=details, evidence=ev)
        return ProbeResult("C2", Outcome.PASS, f"{len(data)} data graphs, none named like work in progress "
                           "(union not checked, size gate)", details=details, evidence=ev)
    named_total = sum(n or 0 for _, n in census.graphs)
    union = triples is not None and triples > 0 and abs(triples - named_total) <= 0.01 * triples
    details.update(union=union, named_total=named_total, default_total=triples)
    if union and working:
        return ProbeResult("C2", Outcome.FAIL, f"the default graph is the union of {len(census.graphs)} graphs and "
                           f"includes work in progress: {', '.join(working)}", details=details, evidence=ev)
    if union:
        return ProbeResult("C2", Outcome.WARN, f"the default graph is the union of {len(data)} data graphs; a query "
                           "without GRAPH reads all of them (check that all are releases)", details=details, evidence=ev)
    return ProbeResult("C2", Outcome.PASS, "the default graph is not the union of the named graphs",
                       details=details, evidence=ev)


def c3(working: Working, census: Census, **kwargs) -> tuple[ProbeResult, list[QueryResult]]:
    nothing = _q(working, "c_nothing", "C3 owl:Nothing", **kwargs)
    reflexive = _q(working, "c_reflexive", "C3 reflexive", **kwargs)
    ev = nothing.evidence_ids() + reflexive.evidence_ids()
    n_nothing = nothing.int_value("n") if nothing.ok else None
    n_reflexive = reflexive.int_value("n") if reflexive.ok else None
    inferred = [g for g, _ in census.data_graphs() if re.search(r"inferen", g, re.I)]
    details = {"nothing_subsumptions": n_nothing, "reflexive_subclass": n_reflexive, "inference_graphs": inferred}
    if n_nothing:
        return ProbeResult("C3", Outcome.FAIL, f"{n_nothing:,} owl:Nothing rdfs:subClassOf statements: reasoner "
                           "output mixed with assertions", details=details, evidence=ev), [nothing, reflexive]
    if n_nothing is None or n_reflexive is None:
        failed = nothing if n_nothing is None else reflexive
        return ProbeResult("C3", Outcome.UNKNOWN, f"could not count: {failed.detail}", details=details,
                           evidence=ev), [nothing, reflexive]
    if n_reflexive or inferred:
        parts = []
        if n_reflexive:
            parts.append(f"{n_reflexive:,} reflexive rdfs:subClassOf statements")
        if inferred:
            parts.append(f"graphs named like inferences: {', '.join(inferred)}")
        return ProbeResult("C3", Outcome.WARN, "; ".join(parts), details=details, evidence=ev), [nothing, reflexive]
    return ProbeResult("C3", Outcome.PASS, "no owl:Nothing subsumptions, no reflexive subclass axioms",
                       details=details, evidence=ev), [nothing, reflexive]


def c4(working: Working, refs: list[references.Reference], source: references.ReleaseSource,
       **kwargs) -> tuple[ProbeResult, list[QueryResult], list[dict]]:
    r = _q(working, "c_ontologies", "C4 ontologies", **kwargs)
    if not r.ok:
        return ProbeResult("C4", Outcome.UNKNOWN, f"could not list ontologies: {r.detail}",
                           evidence=r.evidence_ids()), [r], []
    served = [{"ontology": row.get("ontology", {}).get("value"),
               "versionIRI": row.get("versionIRI", {}).get("value"),
               "versionInfo": row.get("versionInfo", {}).get("value")} for row in r.rows]
    if not served:
        return not_applicable("C4", "no owl:Ontology is served"), [r], served
    checks, lagging, unknown = [], [], []
    for ref in refs:
        mine = [s for s in served if s["ontology"] and ref.matches(s["ontology"])]
        if not mine:
            continue
        tag, note = source.latest_tag(ref)
        latest = references.version_tuple(tag)
        for s in mine:
            version = references.version_tuple(s["versionIRI"]) or references.version_tuple(s["versionInfo"])
            check = {"reference": ref.name, "served": references.version_text(version), "latest": tag, "source": note}
            checks.append(check)
            if latest is None or version is None:
                unknown.append(check)
            elif version < latest:
                lagging.append(check)
    details = {"served": served, "checks": checks}
    if not checks:
        names = ", ".join(sorted({s["ontology"] for s in served if s["ontology"]})[:5])
        return ProbeResult("C4", Outcome.NA, f"serves {len(served)} ontologies, none with a known reference release "
                           f"({names})", details=details, evidence=r.evidence_ids()), [r], served
    if lagging:
        text = "; ".join(f"{c['reference']} {c['served']} served, {c['latest']} released" for c in lagging)
        return ProbeResult("C4", Outcome.FAIL, f"behind the release: {text}", details=details,
                           evidence=r.evidence_ids()), [r], served
    if unknown:
        return ProbeResult("C4", Outcome.UNKNOWN, "version not comparable: " + "; ".join(
            f"{c['reference']} served {c['served']}, latest {c['latest']} ({c['source']})" for c in unknown),
            details=details, evidence=r.evidence_ids()), [r], served
    text = "; ".join(f"{c['reference']} {c['served']}" for c in checks)
    return ProbeResult("C4", Outcome.PASS, f"serves the latest release: {text}", details=details,
                       evidence=r.evidence_ids()), [r], served


def c5(working: Working, refs: list[references.Reference], source: references.ReleaseSource,
       **kwargs) -> tuple[ProbeResult, list[QueryResult]]:
    sent, comparisons = [], []
    for ref in refs:
        kw = dict(kwargs, read_timeout=min(kwargs.get("read_timeout", C_TIMEOUT), C_TIMEOUT))
        r = run_query(working.url, queries.render("c_labelled_classes", namespace=ref.class_prefix), working.form,
                      purpose=f"C5 {ref.name}", **kw)
        sent.append(r)
        if not r.ok:
            comparisons.append({"reference": ref.name, "error": r.detail})
            continue
        at_endpoint = r.int_value("n") or 0
        if at_endpoint == 0:
            continue
        tag, note = source.latest_tag(ref)
        released, where = source.release_class_count(ref, tag) if tag else (None, note)
        comparisons.append({"reference": ref.name, "prefix": ref.class_prefix, "endpoint": at_endpoint,
                            "release": released, "release_tag": tag, "release_source": where})
    ev = [x for r in sent for x in r.evidence_ids()]
    details = {"comparisons": comparisons}
    errors = [c for c in comparisons if "error" in c]
    compared = [c for c in comparisons if c.get("release") is not None]
    if not comparisons:
        return not_applicable("C5", "holds no classes of a reference ontology"), sent
    off = []
    for c in compared:
        diff = c["endpoint"] - c["release"]
        c["difference"] = diff
        if c["release"] and abs(diff) / c["release"] > MODULE_TOLERANCE:
            off.append(c)
    if off:
        text = "; ".join(f"{c['reference']}: {c['endpoint']} labelled classes here, {c['release']} in {c['release_tag']}"
                         for c in off)
        return ProbeResult("C5", Outcome.FAIL, f"not the released ontology: {text}", details=details, evidence=ev), sent
    if errors or len(compared) < len([c for c in comparisons if "error" not in c]):
        return ProbeResult("C5", Outcome.UNKNOWN, "could not compare every reference: " + "; ".join(
            c.get("error") or f"{c['reference']}: {c['release_source']}" for c in comparisons if c not in compared),
            details=details, evidence=ev), sent
    text = "; ".join(f"{c['reference']} {c['endpoint']} vs {c['release']}" for c in compared)
    outcome = Outcome.PASS if all(c["difference"] == 0 for c in compared) else Outcome.WARN
    return ProbeResult("C5", outcome, f"labelled classes match the release within {MODULE_TOLERANCE:.0%}: {text}",
                       details=details, evidence=ev), sent


def assess(working: Working, triples: int | None, count_evidence: list[str], *, heavy: bool = False,
           refs: list[references.Reference] | None = None, source: references.ReleaseSource | None = None,
           **kwargs) -> CLayer:
    refs = references.load() if refs is None else refs
    source = source or references.ReleaseSource()
    census = take_census(working, triples, heavy, **kwargs)
    attempts = [census.result] if census.result else []
    results = {"C1": c1(triples, census, count_evidence), "C2": c2(triples, census)}
    results["C3"], sent = c3(working, census, **kwargs)
    attempts += sent
    results["C4"], sent, served = c4(working, refs, source, **kwargs)
    attempts += sent
    results["C5"], sent = c5(working, refs, source, **kwargs)
    attempts += sent
    for r in results.values():
        if r.outcome not in (Outcome.NA, Outcome.BLOCKED):
            r.measured_on = working.as_dict()
    kpis = {
        "named_graphs": len(census.graphs),
        "top_graphs": [{"graph": g, "triples": n, "kind": census.kind(g)} for g, n in census.graphs[:12]],
        "ontologies_served": served[:20],
    }
    return CLayer(results, attempts, kpis)
