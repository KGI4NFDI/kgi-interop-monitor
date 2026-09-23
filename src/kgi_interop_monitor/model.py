"""Outcomes, probe definitions and the grade.

The outcome vocabulary and the grade rule are explained in
docs/decisions/0005-outcomes-and-grade.md. The probe catalogue below is the
single place where each checklist row is defined for the code, the report and
the status page.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Outcome(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    UNKNOWN = "unknown"
    BLOCKED = "blocked"
    NA = "n/a"


EARL = {
    Outcome.PASS: "earl:passed",
    Outcome.WARN: "earl:passed",
    Outcome.FAIL: "earl:failed",
    Outcome.UNKNOWN: "earl:cantTell",
    Outcome.BLOCKED: "earl:untested",
    Outcome.NA: "earl:inapplicable",
}
"""How outcomes map to the W3C Evaluation and Report Language."""

CLEARS = frozenset({Outcome.PASS, Outcome.WARN, Outcome.NA})
"""Outcomes that let a gating probe count as cleared."""


@dataclass(frozen=True)
class ProbeSpec:
    id: str
    layer: str
    title: str
    question: str
    gating: bool
    basis: str
    basis_url: str | None
    owner: str


PROTOCOL = "https://www.w3.org/TR/sparql11-protocol/"
FEDERATED = "https://www.w3.org/TR/sparql11-federated-query/"
DCAT3 = "https://www.w3.org/TR/vocab-dcat-3/"

SPECS: dict[str, ProbeSpec] = {s.id: s for s in [
    ProbeSpec("A1", "A", "No access point of any kind",
              "Does the record offer any way in: an endpoint value, a dump or an access URL?",
              True, "DCAT 3: dcat:endpointURL on the dcat:DataService, dcat:downloadURL / dcat:accessURL",
              DCAT3, "registry maintainers"),
    ProbeSpec("A2", "A", "Dump or access API only, no SPARQL",
              "Is a dump or access URL the only way in?",
              False, "KGI D3.1 guidelines: a SPARQL endpoint is optional", None, "KG operator"),
    ProbeSpec("A3", "A", "Registered URL is not a SPARQL endpoint",
              "Does the registered URL return a SPARQL results document for ASK {}?",
              True, "SPARQL 1.1 Protocol §2.1 (query operation)", PROTOCOL + "#query-operation", "registry maintainers"),
    ProbeSpec("A4", "A", "Registered URL is dead",
              "Does the registered URL answer at the HTTP level at all?",
              True, "fitness for use", None, "KG operator"),
    ProbeSpec("A5", "A", "Free text in a typed field",
              "Is the dcat:endpointURL value a single URL rather than prose or a list?",
              True, "DCAT 3: dcat:endpointURL has range rdfs:Resource",
              DCAT3 + "#Property:data_service_endpoint_url", "registry maintainers"),
    ProbeSpec("A6", "A", "Duplicate entries for one graph",
              "Does another record describe the same endpoint, title or landing page?",
              False, "fitness for use", None, "registry maintainers"),
    ProbeSpec("A7", "A", "Endpoint resolvable only after normalisation",
              "Does the registered URL work as stored, without redirects or rewriting?",
              True, "fitness for use", None, "registry maintainers"),
    ProbeSpec("B1", "B", "Rejects one request form, accepts another",
              "Do GET, URL-encoded POST and direct POST all return results?",
              True, "SPARQL 1.1 Protocol §2.1.1 to §2.1.3; W3C tests query_get, query_post_form, query_post_direct",
              PROTOCOL + "#query-operation", "KG operator"),
    ProbeSpec("B2", "B", "HTTP 200 carrying an error body",
              "Are errors reported with an error status, never as 2xx?",
              True, "SPARQL 1.1 Protocol §2.1.6 and §2.1.7", PROTOCOL + "#query-success", "KG operator"),
    ProbeSpec("B3", "B", "Query-shape sensitivity",
              "Does COUNT(DISTINCT ?s) answer where COUNT(*) does, in comparable time?",
              False, "fitness for use (performance); not a SPARQL requirement", None, "KG operator"),
    ProbeSpec("B4", "B", "Federation declared but not routable",
              "Can the KGI hub reach this endpoint through SERVICE?",
              False, "SPARQL 1.1 Federated Query §3; SERVICE with a variable is informative (§4)",
              FEDERATED, "hub operators (KGI)"),
    ProbeSpec("B5", "B", "Server-side refusal unrelated to the query",
              "Is a trivial query answered rather than refused (401, 403, 409, 429)?",
              True, "fitness for use", None, "KG operator"),
    ProbeSpec("C1", "C", "Live but unpopulated",
              "Does the endpoint serve data, beyond the engine's own graphs?",
              True, "fitness for use", None, "KG operator"),
    ProbeSpec("C2", "C", "Default graph is a union including working graphs",
              "Does a query without GRAPH read only published data?",
              True, "fitness for use", None, "KG operator"),
    ProbeSpec("C3", "C", "Materialised inference mixed with assertion",
              "Are there owl:Nothing subsumptions or reflexive axioms in the data?",
              True, "OWL 2: owl:Nothing is the empty class", "https://www.w3.org/TR/owl2-syntax/#Classes", "KG operator"),
    ProbeSpec("C4", "C", "Endpoint version lags the release",
              "Does the served ontology version match the latest published release?",
              True, "fitness for use", None, "KG operator"),
    ProbeSpec("C5", "C", "Endpoint serves a module, not the ontology",
              "Does the endpoint hold the same labelled classes as the release file?",
              True, "fitness for use", None, "KG operator"),
]}

LAYERS = ("A", "B", "C")
GATES = {layer: [s.id for s in SPECS.values() if s.layer == layer and s.gating] for layer in LAYERS}

GRADE_ORDER = ["none", "dump", "A*", "A", "B", "C"]


@dataclass
class ProbeResult:
    probe: str
    outcome: Outcome
    summary: str
    details: dict = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    measured_on: dict | None = None
    instrument_error: bool = False

    def as_dict(self) -> dict:
        out = {
            "probe": self.probe,
            "outcome": self.outcome.value,
            "summary": self.summary,
            "details": self.details,
            "evidence": self.evidence,
        }
        if self.measured_on:
            out["measured_on"] = self.measured_on
        if self.instrument_error:
            out["instrument_error"] = True
        return out


def blocked(probe: str, reason: str) -> ProbeResult:
    return ProbeResult(probe, Outcome.BLOCKED, reason)


def not_applicable(probe: str, reason: str) -> ProbeResult:
    return ProbeResult(probe, Outcome.NA, reason)


def grade(results: dict[str, ProbeResult], has_working_url: bool, dump_only: bool = False,
          assume_registry_fixed: bool = False) -> str:
    """Highest layer whose gating probes all clear, strictly in order.

    ``A*`` means a working SPARQL URL exists but the registry record is not
    usable as stored (normalisation, redirect, packed or prose value). With
    ``assume_registry_fixed`` the A-layer registry defects are forgiven, which
    answers "what grade would this KG have if only its record were fixed?".
    """
    if not has_working_url:
        return "dump" if dump_only else "none"

    def clears(layer: str) -> bool:
        return all(results[p].outcome in CLEARS for p in GATES[layer] if p in results)

    level = "A" if (assume_registry_fixed or clears("A")) else "A*"
    if level == "A*":
        return level
    if not clears("B"):
        return level
    if not clears("C"):
        return "B"
    return "C"
