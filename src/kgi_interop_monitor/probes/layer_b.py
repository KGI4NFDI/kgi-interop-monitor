"""Layer B, protocol: it answers, but does it answer you?

Runs on the working endpoint that layer A settled. B1 sends the same bounded
SELECT in all three request forms. B2 looks for errors disguised as 2xx in
everything sent so far and sends one malformed query on purpose. B3 compares
two query shapes behind the politeness size gate. B4 asks the KGI hub to
reach the endpoint through SERVICE. B5 looks for refusals of trivial queries.

The same pass collects the endpoint KPIs: latency (three ASK samples in the
working form), result formats, the W3C protocol subset score, the engine
fingerprint and the TLS certificate expiry.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from .. import fingerprint, protocol, queries
from ..model import Outcome, ProbeResult, blocked, not_applicable
from ..sparql import ERROR_BODY_2XX, FORMS, MEDIA, NOT_SPARQL, REFUSED, TRANSPORT, QueryResult, run_query
from ..transport import Exchange
from .layer_a import Working

SIZE_GATE = 50_000_000
"""Triples above which scan-prone probes need --heavy (ADR 0004, review)."""
B3_TIMEOUT = 20.0
SLOW_COUNT_MS = 5000
"""A COUNT(*) slower than this is not answered from index statistics."""
LATENCY_SAMPLES = 3


@dataclass
class BLayer:
    results: dict[str, ProbeResult]
    attempts: list[QueryResult] = field(default_factory=list)
    exchanges: list[Exchange] = field(default_factory=list)
    kpis: dict = field(default_factory=dict)
    triples: int | None = None


def _ev(results: list[QueryResult]) -> list[str]:
    return [x for r in results for x in r.evidence_ids()]


def _median(values: list[float]) -> float | None:
    values = [v for v in values if v is not None]
    return round(statistics.median(values), 1) if values else None


def not_measurable(a_attempts: list[QueryResult], dump_only: bool) -> BLayer:
    """No working endpoint: B1 to B4 cannot run. B5 can still be judged from
    what layer A saw, because a refusal is visible without a working URL."""
    results: dict[str, ProbeResult] = {}
    if dump_only:
        for pid in ("B1", "B2", "B3", "B4", "B5"):
            results[pid] = not_applicable(pid, "no SPARQL endpoint registered (dump or access URL only)")
        return BLayer(results, kpis={"available": False, "error_class": "no-sparql"})
    for pid in ("B1", "B2", "B3", "B4"):
        results[pid] = blocked(pid, "no working SPARQL URL (see layer A)")
    refused = [r for r in a_attempts if r.verdict == REFUSED]
    if refused:
        statuses = sorted({r.status for r in refused})
        results["B5"] = ProbeResult("B5", Outcome.FAIL,
                                    f"a trivial query is refused with HTTP {', '.join(map(str, statuses))}",
                                    details={"forms": sorted({r.form for r in refused})}, evidence=_ev(refused))
    else:
        results["B5"] = blocked("B5", "no working SPARQL URL (see layer A)")
    return BLayer(results, kpis={"available": False, "error_class": error_class(a_attempts)})


def error_class(attempts: list[QueryResult]) -> str | None:
    """Why the registered URL gave no results, as one short label for the
    page: not-sparql, a transport class such as dns or tls-expired, or
    http-<status>."""
    first = next((r for r in attempts if not r.ok), None)
    if first is None:
        return None
    if first.verdict == NOT_SPARQL:
        return "not-sparql"
    if first.exchange.error_class:
        return first.exchange.error_class
    if first.status:
        return f"http-{first.status}"
    return first.verdict


def b1(url: str, **kwargs) -> tuple[ProbeResult, list[QueryResult]]:
    select = queries.load("b_select")
    matrix = [run_query(url, select, form, purpose=f"B1 {form}", **kwargs) for form in FORMS]
    ok = [r.form for r in matrix if r.ok]
    forms = {r.form: r.summary() for r in matrix}
    if len(ok) == len(FORMS):
        return ProbeResult("B1", Outcome.PASS, "GET, URL-encoded POST and direct POST all return results",
                           details={"forms": forms}, evidence=_ev(matrix)), matrix
    rejected = [r for r in matrix if not r.ok]
    text = "; ".join(f"{r.form}: {r.detail}" for r in rejected)
    return ProbeResult("B1", Outcome.FAIL, f"{len(rejected)} of {len(FORMS)} request forms fail: {text}",
                       details={"forms": forms, "accepted": ok}, evidence=_ev(matrix)), matrix


def result_formats(url: str, form: str, b1_matrix: list[QueryResult], **kwargs) -> tuple[list[str], list[QueryResult]]:
    select = queries.load("b_select")
    formats, sent = [], []
    json_result = next((r for r in b1_matrix if r.form == form), None)
    if json_result and json_result.ok and json_result.result_media_type == MEDIA["json"]:
        formats.append("json")
    for name in ("xml", "csv", "tsv"):
        r = run_query(url, select, form, accept=MEDIA[name], purpose=f"B formats {name}", **kwargs)
        sent.append(r)
        if r.ok and r.result_media_type == MEDIA[name]:
            formats.append(name)
    return formats, sent


def b2(url: str, form: str, seen: list[QueryResult], **kwargs) -> tuple[ProbeResult, QueryResult]:
    bad = run_query(url, queries.load("b_malformed"), form, purpose=f"B2 {form}", **kwargs)
    disguised = [r for r in seen + [bad] if r.verdict == ERROR_BODY_2XX]
    details = {"malformed_query": bad.summary()}
    if disguised:
        where = "; ".join(f"{r.form} {r.exchange.purpose.split()[0]}: {r.detail}" for r in disguised[:3])
        return ProbeResult("B2", Outcome.FAIL, f"errors come back as HTTP 2xx: {where}", details=details,
                           evidence=_ev(disguised)), bad
    if bad.ok:
        return ProbeResult("B2", Outcome.FAIL, "a malformed query was answered as if it were valid",
                           details=details, evidence=bad.evidence_ids()), bad
    if bad.verdict == TRANSPORT:
        return ProbeResult("B2", Outcome.UNKNOWN, f"the malformed query got no answer: {bad.detail}",
                           details=details, evidence=bad.evidence_ids()), bad
    if bad.status and 400 <= bad.status < 500:
        return ProbeResult("B2", Outcome.PASS, f"errors use error statuses (syntax error: HTTP {bad.status})",
                           details=details, evidence=bad.evidence_ids()), bad
    return ProbeResult("B2", Outcome.WARN, f"a syntax error got HTTP {bad.status}; §2.1.7 asks for 400",
                       details=details, evidence=bad.evidence_ids()), bad


def b3(url: str, form: str, heavy: bool, **kwargs) -> tuple[ProbeResult, list[QueryResult], int | None]:
    count = run_query(url, queries.load("b_count_all"), form, purpose="B3 count(*)", **kwargs)
    n = count.int_value("n") if count.ok else None
    t1 = count.exchange.timings.total_ms
    if n is None:
        return ProbeResult("B3", Outcome.UNKNOWN, f"COUNT(*) did not answer: {count.detail or 'no number'}",
                           evidence=count.evidence_ids()), [count], None
    if n > SIZE_GATE and not heavy:
        return ProbeResult("B3", Outcome.UNKNOWN,
                           f"not run: {n:,} triples is above the {SIZE_GATE:,} politeness gate (use --heavy)",
                           details={"triples": n, "count_ms": round(t1, 1)}, evidence=count.evidence_ids()), [count], n
    kw = dict(kwargs, read_timeout=min(kwargs.get("read_timeout", B3_TIMEOUT), B3_TIMEOUT))
    distinct = run_query(url, queries.load("b_count_distinct"), form, purpose="B3 count(distinct)", **kw)
    t2 = distinct.exchange.timings.total_ms
    details = {"triples": n, "count_ms": round(t1, 1), "count_distinct_ms": round(t2, 1) if t2 else None}
    ev = count.evidence_ids() + distinct.evidence_ids()
    if not distinct.ok:
        if t1 >= SLOW_COUNT_MS:
            # COUNT(*) is already slow, so this is an overall-speed problem,
            # not the shape sensitivity the checklist row is about.
            return ProbeResult("B3", Outcome.WARN,
                               f"slow on both shapes: COUNT(*) takes {t1 / 1000:.1f} s and COUNT(DISTINCT ?s) fails "
                               f"({distinct.detail})", details=details, evidence=ev), [count, distinct], n
        return ProbeResult("B3", Outcome.FAIL,
                           f"COUNT(*) answers in {t1:.0f} ms, COUNT(DISTINCT ?s) on the same pattern fails: {distinct.detail}",
                           details=details, evidence=ev), [count, distinct], n
    details["distinct_subjects"] = distinct.int_value("n")
    ratio = (t2 / t1) if t1 else None
    details["ratio"] = round(ratio, 1) if ratio else None
    if ratio and ratio > 10 and t2 > 5000:
        return ProbeResult("B3", Outcome.WARN, f"COUNT(DISTINCT ?s) is {ratio:.0f} times slower ({t2 / 1000:.1f} s)",
                           details=details, evidence=ev), [count, distinct], n
    return ProbeResult("B3", Outcome.PASS, f"both shapes answer ({t1:.0f} ms and {t2:.0f} ms)",
                       details=details, evidence=ev), [count, distinct], n


def b4(url: str, hub: str | None, is_hub: bool, **kwargs) -> tuple[ProbeResult, list[QueryResult]]:
    if is_hub or not hub:
        return not_applicable("B4", "this is the hub itself" if is_hub else "no hub configured"), []
    query = queries.render("b_service_bound", endpoint=url)
    r = run_query(hub, query, "get", purpose="B4 hub", **kwargs)
    details = {"hub": hub, "result": r.summary()}
    if r.ok and r.rows:
        return ProbeResult("B4", Outcome.PASS, "the KGI hub reaches it through SERVICE", details=details,
                           evidence=r.evidence_ids()), [r]
    if r.ok:
        return ProbeResult("B4", Outcome.WARN, "the hub's SERVICE call came back empty", details=details,
                           evidence=r.evidence_ids()), [r]
    if r.verdict == TRANSPORT:
        return ProbeResult("B4", Outcome.UNKNOWN, f"the hub did not answer: {r.detail}", details=details,
                           evidence=r.evidence_ids()), [r]
    return ProbeResult("B4", Outcome.FAIL, f"the hub cannot reach it: {r.detail}", details=details,
                       evidence=r.evidence_ids()), [r]


def b5(matrix: list[QueryResult]) -> ProbeResult:
    refused = [r for r in matrix if r.verdict == REFUSED]
    if refused:
        statuses = sorted({r.status for r in refused})
        answered = [r.form for r in matrix if r.ok]
        scope = (f"only in {', '.join(r.form for r in refused)}, while {', '.join(answered)} answer: "
                 "a block on one request form, which also breaks clients that use it (see B1, B4)"
                 if answered else "in every request form")
        return ProbeResult("B5", Outcome.FAIL,
                           f"trivial queries refused with HTTP {', '.join(map(str, statuses))} {scope}",
                           details={"refused": [r.form for r in refused], "answered": answered},
                           evidence=_ev(refused))
    return ProbeResult("B5", Outcome.PASS, "trivial queries are answered, not refused")


def latency(url: str, form: str, **kwargs) -> tuple[dict, list[QueryResult]]:
    ask = queries.load("a_ask")
    samples = [run_query(url, ask, form, purpose="latency", **kwargs) for _ in range(LATENCY_SAMPLES)]
    ok = [s for s in samples if s.ok]
    t = [s.exchange.timings for s in ok]
    return {
        "latency_ms": _median([x.total_ms for x in t]),
        "ttfb_ms": _median([x.ttfb_ms for x in t]),
        "connect_ms": _median([x.connect_ms for x in t]),
        "latency_samples_ms": [round(x.total_ms, 1) for x in t],
        "latency_failures": len(samples) - len(ok),
    }, samples


def tls_days_left(exchanges: list[Exchange]) -> tuple[str | None, int | None]:
    not_after = next((x.tls_not_after for x in exchanges if x.tls_not_after), None)
    if not not_after:
        return None, None
    days = (date.fromisoformat(not_after) - datetime.now(timezone.utc).date()).days
    return not_after, days


def assess(working: Working, a_attempts: list[QueryResult], *, hub: str | None, heavy: bool = False,
           is_hub: bool = False, **kwargs) -> BLayer:
    url, form = working.url, working.form
    results: dict[str, ProbeResult] = {}
    attempts: list[QueryResult] = []

    results["B1"], matrix = b1(url, **kwargs)
    attempts += matrix
    formats, sent = result_formats(url, form, matrix, **kwargs)
    attempts += sent
    on_working = [r for r in a_attempts if r.url.rstrip("/") == url.rstrip("/") or r.final_url.rstrip("/") == url.rstrip("/")]
    results["B2"], bad = b2(url, form, on_working + attempts, **kwargs)
    attempts.append(bad)
    lat, samples = latency(url, form, **kwargs)
    attempts += samples
    results["B3"], counted, triples = b3(url, form, heavy, **kwargs)
    attempts += counted
    results["B4"], routed = b4(url, hub, is_hub, **kwargs)
    attempts += routed
    results["B5"] = b5(matrix)

    suite = protocol.run_suite(url, **kwargs)
    suite_exchanges = suite.pop("_exchanges")
    all_exchanges = [h for r in a_attempts + attempts if not r.exchange.purpose.startswith("B4") for h in r.hops]
    all_exchanges += suite_exchanges
    not_after, days = tls_days_left(all_exchanges)
    kpis = {
        "available": True,
        **lat,
        "formats": formats,
        "protocol": {"passed": suite["passed"], "total": suite["total"],
                     "failed": [t["id"] for t in suite["tests"] if not t["passed"]], "tests": suite["tests"]},
        "engine": fingerprint.identify(all_exchanges),
        "tls_not_after": not_after,
        "tls_days_left": days,
        "triples": triples,
        "measured_via": working.as_dict(),
    }
    for r in results.values():
        if r.outcome not in (Outcome.NA, Outcome.BLOCKED):
            r.measured_on = working.as_dict()
    return BLayer(results, attempts, suite_exchanges, kpis, triples)
