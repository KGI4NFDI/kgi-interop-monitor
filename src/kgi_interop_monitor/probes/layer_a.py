"""Layer A, addressing: is there a queryable URL at all?

A1, A2 and A5 read the registry record only. A3 and A4 ask the registered URL
``ASK {}`` in all three request forms. A7 looks for the real endpoint when the
registered URL does not answer. A6 compares records with each other and is
computed once all records have been assessed (see :func:`duplicates`).

The layer also settles the *working endpoint*: the URL and request form that
layers B and C measure through. When it had to be found by following a
redirect, splitting a packed value or normalising the URL, that is reported
under A7 and the higher layers record it (ADR 0002).
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass, field

from .. import queries
from ..model import Outcome, ProbeResult, not_applicable
from ..normalize import ParsedValue, candidates, canonical, parse_value, title_key
from ..registry import RegistryRecord
from ..sparql import FORMS, HTTP_ERROR, NOT_SPARQL, ERROR_BODY_2XX, OK, REDIRECT_LOOP, REFUSED, TRANSPORT, QueryResult, run_query

DEAD_STATUSES = frozenset({404, 410}) | frozenset(range(500, 600))
HOST_LEVEL_ERRORS = frozenset({"dns", "refused", "reset", "network", "timeout-connect",
                               "tls", "tls-expired", "tls-hostname", "tls-untrusted"})
PREFERRED_FORMS = ("get", "post-form", "post-direct")


@dataclass
class Working:
    """The URL and request form the higher layers measure through."""

    url: str
    form: str
    via: str  # registered | redirect | split | normalised
    ask: QueryResult

    def as_dict(self) -> dict:
        return {"url": self.url, "form": self.form, "via": self.via}


@dataclass
class ALayer:
    results: dict[str, ProbeResult]
    working: Working | None
    attempts: list[QueryResult] = field(default_factory=list)
    dump_only: bool = False


def ask_matrix(url: str, purpose: str, **kwargs) -> list[QueryResult]:
    ask = queries.load("a_ask")
    return [run_query(url, ask, form, purpose=f"{purpose} {form}", **kwargs) for form in FORMS]


def _is_dead(result: QueryResult) -> bool:
    return (result.verdict in (TRANSPORT, REDIRECT_LOOP)
            or (result.verdict == HTTP_ERROR and result.status in DEAD_STATUSES))


def matrix_state(results: list[QueryResult]) -> str:
    """sparql | not-sparql | refused | dead, for the answers of one URL."""
    if any(r.ok for r in results):
        return "sparql"
    if all(_is_dead(r) for r in results):
        return "dead"
    if any(r.verdict == REFUSED for r in results) and not any(
            r.verdict in (NOT_SPARQL, ERROR_BODY_2XX) for r in results):
        return "refused"
    return "not-sparql"


def pick_working(results: list[QueryResult]) -> QueryResult | None:
    by_form = {r.form: r for r in results if r.ok}
    return next((by_form[f] for f in PREFERRED_FORMS if f in by_form), None)


def _evidence(results: list[QueryResult]) -> list[str]:
    return [x for r in results for x in r.evidence_ids()]


def _parsed(record: RegistryRecord) -> list[ParsedValue]:
    return [parse_value(ev.raw) for ev in record.endpoint_values]


def _urls(parsed: list[ParsedValue]) -> list[str]:
    out: list[str] = []
    for p in parsed:
        out.extend(u for u in p.urls if u not in out)
    return out


# ------------------------------------------------------------ record checks

def a1(record: RegistryRecord, parsed: list[ParsedValue]) -> ProbeResult:
    urls, dumps = _urls(parsed), record.dumps_or_access
    if urls or dumps:
        ways = []
        if urls:
            ways.append(f"{len(urls)} endpoint URL{'s' if len(urls) > 1 else ''}")
        if dumps:
            ways.append(f"{len(dumps)} dump or access URL{'s' if len(dumps) > 1 else ''}")
        return ProbeResult("A1", Outcome.PASS, "has " + " and ".join(ways))
    reason = ("the only endpoint value is prose: " + ", ".join(repr(p.raw) for p in parsed)) if parsed else \
        "no dcat:endpointURL, dcat:downloadURL or dcat:accessURL"
    return ProbeResult("A1", Outcome.FAIL, f"no access point: {reason}")


def a2(record: RegistryRecord, parsed: list[ParsedValue]) -> ProbeResult:
    if _urls(parsed):
        return ProbeResult("A2", Outcome.PASS, "a SPARQL endpoint is registered")
    if record.dumps_or_access:
        return ProbeResult("A2", Outcome.WARN,
                           "dump or access URL only, no SPARQL endpoint (optional under the KGI D3.1 guidelines)",
                           details={"dumps_or_access": record.dumps_or_access})
    return not_applicable("A2", "no access point at all (see A1)")


def a5(record: RegistryRecord, parsed: list[ParsedValue]) -> ProbeResult:
    if not parsed:
        return not_applicable("A5", "no dcat:endpointURL value")
    prose = [p.raw for p in parsed if p.is_prose]
    if prose:
        return ProbeResult("A5", Outcome.FAIL, "free text instead of a URL: " + ", ".join(repr(v) for v in prose),
                           details={"values": [p.raw for p in parsed]})
    packed = [p.raw for p in parsed if p.is_packed]
    if packed:
        return ProbeResult("A5", Outcome.WARN,
                           f"several URLs packed into one value: {packed[0]!r}; DCAT allows one dcat:endpointURL "
                           "statement per URL", details={"values": [p.raw for p in parsed]})
    extra = [p.raw for p in parsed if p.has_extra_text]
    if extra:
        return ProbeResult("A5", Outcome.WARN, f"URL with surrounding text: {extra[0]!r}")
    if len(parsed) > 1:
        return ProbeResult("A5", Outcome.PASS, f"{len(parsed)} well-formed URL values")
    return ProbeResult("A5", Outcome.PASS, "a single well-formed URL")


# ------------------------------------------------------------ network checks

def _a3_a4(state: str, results: list[QueryResult]) -> tuple[ProbeResult, ProbeResult]:
    ev = _evidence(results)
    forms = {r.form: r.summary() for r in results}
    if state == "dead":
        first = results[0]
        a4 = ProbeResult("A4", Outcome.FAIL, f"dead: {first.detail}", details={"forms": forms}, evidence=ev)
        return ProbeResult("A3", Outcome.BLOCKED, "the URL does not answer (see A4)"), a4
    status = next((r.status for r in results if r.status), None)
    a4 = ProbeResult("A4", Outcome.PASS, f"the server answers (HTTP {status})", details={"forms": forms}, evidence=ev)
    if state == "sparql":
        n = sum(r.ok for r in results)
        return ProbeResult("A3", Outcome.PASS, f"answered ASK {{}} in {n} of {len(results)} request forms",
                           details={"forms": forms}, evidence=ev), a4
    if state == "refused":
        return ProbeResult("A3", Outcome.UNKNOWN, "the server refuses before it can be identified as SPARQL (see B5)",
                           details={"forms": forms}, evidence=ev), a4
    bad = next((r for r in results if r.verdict in (NOT_SPARQL, ERROR_BODY_2XX)), results[0])
    return ProbeResult("A3", Outcome.FAIL, f"not a SPARQL endpoint: {bad.detail}", details={"forms": forms},
                       evidence=ev), a4


def search_candidates(urls: list[str], **kwargs) -> tuple[Working | None, list[dict], list[QueryResult]]:
    """Try the normalisation candidates of each URL, cheapest form first."""
    tried: list[dict] = []
    sent: list[QueryResult] = []
    dead_hosts: set[str] = set()
    ask = queries.load("a_ask")
    for url in urls:
        for candidate in candidates(url):
            host = candidate.split("/")[2].lower()
            if host in dead_hosts:
                continue
            for form in PREFERRED_FORMS:
                result = run_query(candidate, ask, form, purpose=f"A7 {form}", **kwargs)
                sent.append(result)
                tried.append({"url": candidate, "form": form, "verdict": result.verdict, "detail": result.detail})
                if result.ok:
                    return Working(result.final_url if result.redirected else candidate, form, "normalised",
                                   result), tried, sent
                if result.verdict == TRANSPORT and result.exchange.error_class in HOST_LEVEL_ERRORS:
                    dead_hosts.add(host)
                    break
                # Only a rejection of the request form is worth another form
                # on the same URL; a web page or a 404 is not.
                if not (result.verdict == HTTP_ERROR and result.status in (400, 405, 406, 415)):
                    break
    return None, tried, sent


def assess(record: RegistryRecord, **kwargs) -> ALayer:
    parsed = _parsed(record)
    results = {"A1": a1(record, parsed), "A2": a2(record, parsed), "A5": a5(record, parsed)}
    urls = _urls(parsed)
    attempts: list[QueryResult] = []
    dump_only = not urls and bool(record.dumps_or_access)

    if not urls:
        reason = "no endpoint URL registered" + (" (dump or access URL only, see A2)" if dump_only else "")
        for pid in ("A3", "A4", "A7"):
            results[pid] = not_applicable(pid, reason)
        return ALayer(results, None, attempts, dump_only)

    # A3 / A4 on what is registered. A packed value is tried part by part,
    # all parts, because the first one that answers is not necessarily the
    # one that holds the data.
    working: Working | None = None
    states: list[str] = []
    per_url: list[list[QueryResult]] = []
    packed = len(urls) > 1 or any(p.is_packed for p in parsed)
    for url in urls:
        matrix = ask_matrix(url, "A3/A4", **kwargs)
        attempts.extend(matrix)
        per_url.append(matrix)
        states.append(matrix_state(matrix))
        best = pick_working(matrix)
        if best and working is None:
            via = "split" if packed else ("redirect" if best.redirected else "registered")
            target = best.final_url if best.redirected else urllib.parse.urldefrag(url)[0]
            working = Working(target, best.form, via, best)
        if not packed:
            break
    order = ("sparql", "not-sparql", "refused", "dead")
    best_index = min(range(len(states)), key=lambda i: order.index(states[i]))
    a3, a4 = _a3_a4(states[best_index], per_url[best_index])
    results["A3"], results["A4"] = a3, a4
    fragment = urllib.parse.urldefrag(urls[0])[1] if not packed else ""

    # A7: does the value work as stored?
    if working and working.via == "registered" and fragment:
        results["A7"] = ProbeResult(
            "A7", Outcome.WARN,
            f"works only because HTTP drops the fragment '#{fragment}'; the value carries a UI route, "
            f"register {working.url} instead", details={"proposal": working.url})
    elif working and working.via == "registered":
        results["A7"] = ProbeResult("A7", Outcome.PASS, "works as registered")
    elif working and working.via == "redirect":
        results["A7"] = ProbeResult(
            "A7", Outcome.WARN,
            f"works only after a redirect to {working.url}; clients that replay a redirected POST as GET lose the query",
            details={"proposal": working.url, "hops": [h.url for h in working.ask.hops]},
            evidence=working.ask.evidence_ids())
    elif working and working.via == "split":
        parts = [{"url": u, "state": st} for u, st in zip(urls, states)]
        results["A7"] = ProbeResult("A7", Outcome.FAIL,
                                    f"works only after splitting the value; {working.url} answers "
                                    f"({sum(st == 'sparql' for st in states)} of {len(urls)} parts are SPARQL)",
                                    details={"proposal": working.url, "parts": parts},
                                    evidence=working.ask.evidence_ids())
    else:
        host_down = all(r.verdict == TRANSPORT and r.exchange.error_class in HOST_LEVEL_ERRORS
                        for matrix in per_url for r in matrix)
        if host_down:
            results["A7"] = not_applicable("A7", "the host itself is unreachable, so no normalisation can help")
        else:
            found, tried, sent = search_candidates(urls, **kwargs)
            attempts.extend(sent)
            if found:
                working = found
                results["A7"] = ProbeResult(
                    "A7", Outcome.FAIL, f"not usable as registered; {found.url} answers SPARQL (proposal, needs a human check)",
                    details={"proposal": found.url, "tried": tried}, evidence=_evidence(sent))
            else:
                results["A7"] = ProbeResult("A7", Outcome.NA, f"none of {len({t['url'] for t in tried})} normalised "
                                            "URLs answered SPARQL either", details={"tried": tried},
                                            evidence=_evidence(sent))
    return ALayer(results, working, attempts, dump_only)


# ------------------------------------------------------------ across records

def duplicates(records: list[RegistryRecord], working: dict[str, Working | None]) -> dict[str, ProbeResult]:
    """A6: records that share an endpoint, a title, a landing page or the
    endpoint they resolve to. Known blind spot: one graph registered under
    two hosts with two titles (MatWerk) shares none of these keys."""
    keys: dict[tuple[str, str], set[str]] = {}

    def index(kind: str, value: str, rid: str) -> None:
        if value:
            keys.setdefault((kind, value), set()).add(rid)

    for rec in records:
        for p in _parsed(rec):
            for url in p.urls:
                index("same registered endpoint", canonical(url), rec.id)
        index("same title", title_key(rec.title), rec.id)
        for page in rec.landing_pages:
            index("same landing page", canonical(page), rec.id)
        w = working.get(rec.id)
        if w:
            index("same working endpoint", canonical(w.url), rec.id)

    out: dict[str, ProbeResult] = {}
    for rec in records:
        others: dict[str, list[str]] = {}
        for (kind, _value), ids in keys.items():
            if rec.id in ids and len(ids) > 1:
                for other in sorted(ids - {rec.id}):
                    others.setdefault(other, [])
                    if kind not in others[other]:
                        others[other].append(kind)
        if others:
            text = "; ".join(f"{o} ({', '.join(k)})" for o, k in others.items())
            out[rec.id] = ProbeResult("A6", Outcome.WARN, f"possible duplicate of {text}", details={"others": others})
        else:
            out[rec.id] = ProbeResult("A6", Outcome.PASS, "no other record shares its endpoint, title or landing page")
    return out
