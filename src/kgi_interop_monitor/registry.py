"""Read the KGI registry and report what is wrong with the registry as a whole.

Per-record problems are checklist rows (A1, A2, A5, A6) and are judged by the
layer A probes. This module only reads the records and reports the defects
that belong to the registry itself, once, instead of once per record.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import queries
from .sparql import FORMS, QueryResult, run_query

KGI_HUB = "https://sparql.kgi.services.base4nfdi.de/api/"
XSD_STRING = "http://www.w3.org/2001/XMLSchema#string"


@dataclass
class EndpointValue:
    """One dcat:endpointURL value exactly as the registry stores it."""

    raw: str
    is_iri: bool
    datatype: str | None = None


@dataclass
class RegistryRecord:
    id: str
    iri: str
    title: str
    landing_pages: list[str] = field(default_factory=list)
    endpoint_values: list[EndpointValue] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    downloads: list[str] = field(default_factory=list)
    accesses: list[str] = field(default_factory=list)

    @property
    def dumps_or_access(self) -> list[str]:
        return sorted(set(self.downloads) | set(self.accesses))

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "iri": self.iri,
            "title": self.title,
            "landing_pages": self.landing_pages,
            "endpoint_values": [ev.__dict__ for ev in self.endpoint_values],
            "services": self.services,
            "downloads": self.downloads,
            "accesses": self.accesses,
        }


@dataclass
class Snapshot:
    endpoint: str
    fetched_at: str
    records: list[RegistryRecord]
    attempts: list[QueryResult]
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def record_id(iri: str) -> str:
    """KGR28 from http://kgi.services.base4nfdi.de/entity/KGR28."""
    tail = re.split(r"[/#]", iri.rstrip("/"))[-1]
    return tail or iri


def _value(row: dict, key: str) -> str | None:
    cell = row.get(key)
    return cell.get("value") if isinstance(cell, dict) else None


def parse_records(result: QueryResult) -> list[RegistryRecord]:
    by_iri: dict[str, RegistryRecord] = {}
    for row in result.rows:
        iri = _value(row, "dataset")
        if not iri:
            continue
        rec = by_iri.setdefault(iri, RegistryRecord(id=record_id(iri), iri=iri, title=""))
        title = _value(row, "title")
        if title and not rec.title:
            rec.title = title.strip()
        for key, target in (("landing", rec.landing_pages), ("service", rec.services),
                            ("download", rec.downloads), ("access", rec.accesses)):
            value = _value(row, key)
            if value and value not in target:
                target.append(value)
        raw = _value(row, "endpoint")
        if raw is not None and not any(ev.raw == raw for ev in rec.endpoint_values):
            endpoint_cell = row.get("endpoint", {})
            is_iri = endpoint_cell.get("type") == "uri"
            is_iri_flag = _value(row, "endpointIsIri")
            if is_iri_flag is not None:
                is_iri = is_iri_flag.lower() in ("true", "1")
            datatype = _value(row, "endpointDatatype") or endpoint_cell.get("datatype")
            if not is_iri and datatype is None:
                datatype = XSD_STRING  # a plain literal is an xsd:string in RDF 1.1
            rec.endpoint_values.append(EndpointValue(raw=raw, is_iri=is_iri, datatype=datatype))
    for rec in by_iri.values():
        rec.title = rec.title or rec.id
    return sorted(by_iri.values(), key=lambda r: (r.title.lower(), r.id))


def read(endpoint: str = KGI_HUB, **kwargs) -> Snapshot:
    """Fetch all registry records. Tries the request forms in turn, so a
    registry that rejects one form is still read (and the rejection kept)."""
    query = queries.load("registry_records")
    attempts: list[QueryResult] = []
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for form in ("post-form", "get", "post-direct"):
        result = run_query(endpoint, query, form, purpose="registry", **kwargs)
        attempts.append(result)
        if result.ok:
            return Snapshot(endpoint, fetched_at, parse_records(result), attempts)
    last = attempts[-1]
    return Snapshot(endpoint, fetched_at, [], attempts, error=f"{last.verdict}: {last.detail}")


@dataclass
class Finding:
    """A defect of the registry as a whole, reported once."""

    id: str
    title: str
    outcome: str
    summary: str
    details: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def findings(snapshot: Snapshot) -> list[Finding]:
    out: list[Finding] = []
    values = [ev for rec in snapshot.records for ev in rec.endpoint_values]
    literals = [ev for ev in values if not ev.is_iri]
    if values:
        out.append(Finding(
            id="R1",
            title="dcat:endpointURL values are literals",
            outcome="fail" if literals else "pass",
            summary=(f"{len(literals)} of {len(values)} dcat:endpointURL values are literals "
                     f"({', '.join(sorted({(ev.datatype or 'plain').rsplit('#', 1)[-1] for ev in literals}))}); "
                     "DCAT 3 gives the property the range rdfs:Resource, so an IRI is expected.")
            if literals else f"all {len(values)} dcat:endpointURL values are IRIs",
            details={"literal": len(literals), "iri": len(values) - len(literals),
                     "basis": "https://www.w3.org/TR/vocab-dcat-3/#Property:data_service_endpoint_url"},
        ))
    with_endpoint = [r for r in snapshot.records if r.endpoint_values]
    out.append(Finding(
        id="R0",
        title="registry population",
        outcome="info",
        summary=(f"{len(snapshot.records)} datasets; {len(with_endpoint)} with a dcat:endpointURL value; "
                 f"{sum(1 for r in snapshot.records if not r.endpoint_values and r.dumps_or_access)} with only a "
                 f"dump or access URL; {sum(1 for r in snapshot.records if not r.endpoint_values and not r.dumps_or_access)} "
                 "with no access point"),
        details={"datasets": len(snapshot.records), "with_endpoint_value": len(with_endpoint)},
    ))
    return out


__all__ = ["KGI_HUB", "EndpointValue", "RegistryRecord", "Snapshot", "Finding", "read", "findings", "parse_records", "FORMS"]
