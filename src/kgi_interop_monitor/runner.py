"""One monitoring run: control probe, registry, every record through the ladder.

The control probe comes first. If the monitor itself has no network, every
endpoint would look dead; that must be reported as an instrument failure, not
as thirty outages (the tier 0 idea from kgi4nfdi_learning).
"""

from __future__ import annotations

import os
import platform
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import __version__, registry
from .model import SPECS, Outcome, ProbeResult, grade
from .probes import layer_a
from .registry import RegistryRecord
from .sparql import QueryResult
from .transport import exchange

CONTROL_URL = "https://www.w3.org/"


@dataclass
class RunConfig:
    registry_endpoint: str = registry.KGI_HUB
    hub_endpoint: str = registry.KGI_HUB
    control_url: str = CONTROL_URL
    only: set[str] | None = None
    layers: str = "ABC"
    max_workers: int = 6
    heavy: bool = False
    connect_timeout: float = 10.0
    read_timeout: float = 30.0

    def request_kwargs(self) -> dict:
        return {"connect_timeout": self.connect_timeout, "read_timeout": self.read_timeout}


@dataclass
class KgReport:
    record: RegistryRecord
    results: dict[str, ProbeResult] = field(default_factory=dict)
    working: layer_a.Working | None = None
    dump_only: bool = False
    kpis: dict = field(default_factory=dict)
    queries: list[QueryResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    seconds: float = 0.0

    def add(self, *results: ProbeResult) -> None:
        for result in results:
            self.results[result.probe] = result

    def as_dict(self) -> dict:
        has_working = self.working is not None
        seen, exchanges = set(), []
        for q in self.queries:
            for hop in q.hops:
                if hop.id not in seen:
                    seen.add(hop.id)
                    exchanges.append(hop.evidence())
        ordered = {pid: self.results[pid].as_dict() for pid in SPECS if pid in self.results}
        return {
            "id": self.record.id,
            "iri": self.record.iri,
            "title": self.record.title,
            "registered": [ev.raw for ev in self.record.endpoint_values],
            "landing_pages": self.record.landing_pages,
            "working": self.working.as_dict() if self.working else None,
            "grade": grade(self.results, has_working, self.dump_only),
            "grade_if_registry_fixed": grade(self.results, has_working, self.dump_only, assume_registry_fixed=True),
            "results": ordered,
            "kpis": self.kpis,
            "notes": self.notes,
            "seconds": round(self.seconds, 1),
            "exchanges": exchanges,
        }


def assess_record(record: RegistryRecord, config: RunConfig) -> KgReport:
    started = time.monotonic()
    report = KgReport(record)
    kwargs = config.request_kwargs()
    a = layer_a.assess(record, **kwargs)
    report.add(*a.results.values())
    report.working, report.dump_only = a.working, a.dump_only
    report.queries.extend(a.attempts)
    report.seconds = time.monotonic() - started
    return report


def vantage() -> str:
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return f"github-actions/{os.environ.get('RUNNER_OS', 'unknown').lower()}"
    return os.environ.get("KGI_MONITOR_VANTAGE", f"local/{platform.system().lower()}")


def run(config: RunConfig) -> dict:
    started = datetime.now(timezone.utc)
    clock = time.monotonic()
    report: dict = {
        "run_id": started.strftime("%Y-%m-%dT%H%MZ"),
        "started_at": started.isoformat(timespec="seconds"),
        "monitor": {"version": __version__, "vantage": vantage(), "layers": config.layers, "heavy": config.heavy},
        "registry_endpoint": config.registry_endpoint,
        "hub_endpoint": config.hub_endpoint,
        "status": "ok",
        "registry_findings": [],
        "hub": {},
        "kgs": [],
    }

    control = exchange("GET", config.control_url, purpose="control", **config.request_kwargs())
    report["control"] = control.evidence()
    if not control.ok_transport:
        report["status"] = "instrument-unhealthy"
        report["status_detail"] = (f"control probe {config.control_url} failed ({control.error_class}); "
                                   "no endpoint was judged, because every one would look dead")
        return _finish(report, clock)

    snapshot = registry.read(config.registry_endpoint, **config.request_kwargs())
    report["registry"] = {
        "fetched_at": snapshot.fetched_at,
        "records": len(snapshot.records),
        "attempts": [a.summary() for a in snapshot.attempts],
    }
    if not snapshot.ok:
        report["status"] = "registry-unavailable"
        report["status_detail"] = f"the registry did not answer: {snapshot.error}"
        return _finish(report, clock)
    report["registry_findings"] = [f.as_dict() for f in registry.findings(snapshot)]

    records = [r for r in snapshot.records if not config.only or r.id in config.only]
    with ThreadPoolExecutor(max_workers=config.max_workers) as pool:
        kg_reports = list(pool.map(lambda rec: assess_record(rec, config), records))

    a6 = layer_a.duplicates(records, {r.record.id: r.working for r in kg_reports})
    for kg in kg_reports:
        kg.add(a6[kg.record.id])
    report["kgs"] = [kg.as_dict() for kg in kg_reports]
    return _finish(report, clock)


def _finish(report: dict, clock: float) -> dict:
    report["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    report["seconds"] = round(time.monotonic() - clock, 1)
    report["summary"] = summarise(report)
    return report


def summarise(report: dict) -> dict:
    kgs = report.get("kgs", [])
    grades: dict[str, int] = {}
    for kg in kgs:
        grades[kg["grade"]] = grades.get(kg["grade"], 0) + 1
    per_probe: dict[str, dict[str, int]] = {}
    for kg in kgs:
        for pid, res in kg["results"].items():
            bucket = per_probe.setdefault(pid, {})
            bucket[res["outcome"]] = bucket.get(res["outcome"], 0) + 1
    return {
        "kgs": len(kgs),
        "grades": grades,
        "working_as_registered": sum(1 for kg in kgs if kg["working"] and kg["working"]["via"] == "registered"),
        "working_after_repair": sum(1 for kg in kgs if kg["working"]),
        "probes": per_probe,
        "failures": sum(1 for kg in kgs for r in kg["results"].values() if r["outcome"] == Outcome.FAIL.value),
    }
