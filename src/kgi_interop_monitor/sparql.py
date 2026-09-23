"""SPARQL protocol requests and what a response turned out to be.

Three request forms (SPARQL 1.1 Protocol §2.1.1 to §2.1.3) and a verdict for
every response. The verdict never trusts the status code alone: a 200 whose
body is an error message is its own verdict (checklist B2), and so is a 200
that is a web page instead of a results document (checklist A3).
"""

from __future__ import annotations

import csv
import io
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from .transport import REFUSAL_STATUSES, Exchange, follow

FORMS = ("get", "post-form", "post-direct")
"""Protocol §2.1.1 query via GET, §2.1.2 URL-encoded POST, §2.1.3 direct POST."""

MEDIA = {
    "json": "application/sparql-results+json",
    "xml": "application/sparql-results+xml",
    "csv": "text/csv",
    "tsv": "text/tab-separated-values",
}
RDF_ACCEPT = "text/turtle, application/n-triples;q=0.9, application/rdf+xml;q=0.8"
RDF_MEDIA = {
    "text/turtle": "turtle",
    "application/x-turtle": "turtle",
    "application/n-triples": "nt",
    "text/plain": "nt",
    "application/rdf+xml": "xml",
    "application/ld+json": "json-ld",
    "application/n-quads": "nquads",
    "application/trig": "trig",
}
SRX = "{http://www.w3.org/2005/sparql-results#}"

# Verdicts
OK = "ok"
ERROR_BODY_2XX = "error-body-2xx"
NOT_SPARQL = "not-sparql"
REFUSED = "refused"
HTTP_ERROR = "http-error"
TRANSPORT = "transport"
REDIRECT_LOOP = "redirect-loop"


def build_request(url: str, query: str, form: str, accept: str) -> tuple[str, str, dict[str, str], bytes | None]:
    """Method, URL, headers and body for one request form.

    A URL fragment is never sent by HTTP clients, so it is dropped here
    explicitly; registry values sometimes carry a UI route after '#'.
    """
    url = urllib.parse.urldefrag(url)[0]
    headers = {"Accept": accept}
    if form == "get":
        sep = "&" if "?" in url else "?"
        return "GET", url + sep + urllib.parse.urlencode({"query": query}), headers, None
    if form == "post-form":
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        return "POST", url, headers, urllib.parse.urlencode({"query": query}).encode("ascii")
    if form == "post-direct":
        headers["Content-Type"] = "application/sparql-query"
        return "POST", url, headers, query.encode("utf-8")
    raise ValueError(f"unknown request form {form!r}")


@dataclass
class QueryResult:
    """A classified response to one query in one request form."""

    url: str
    form: str
    query: str
    hops: list[Exchange]
    verdict: str = TRANSPORT
    detail: str = ""
    vars: list[str] = field(default_factory=list)
    rows: list[dict[str, dict]] = field(default_factory=list)
    boolean: bool | None = None
    triples: int | None = None
    result_media_type: str = ""
    media_type_matches: bool | None = None

    @property
    def exchange(self) -> Exchange:
        return self.hops[-1]

    @property
    def ok(self) -> bool:
        return self.verdict == OK

    @property
    def redirected(self) -> bool:
        return len(self.hops) > 1

    @property
    def final_url(self) -> str:
        # For GET the final URL carries the query string; report the endpoint.
        return urllib.parse.urlsplit(self.exchange.url)._replace(query="", fragment="").geturl()

    @property
    def status(self) -> int | None:
        return self.exchange.status

    def value(self, var: str, row: int = 0) -> str | None:
        try:
            return self.rows[row][var]["value"]
        except (IndexError, KeyError):
            return None

    def int_value(self, var: str, row: int = 0) -> int | None:
        raw = self.value(var, row)
        if raw is None:
            return None
        try:
            return int(float(raw))
        except ValueError:
            return None

    def evidence_ids(self) -> list[str]:
        return [hop.id for hop in self.hops]

    def summary(self) -> dict:
        return {
            "form": self.form,
            "url": self.url,
            "verdict": self.verdict,
            "detail": self.detail,
            "status": self.status,
            "media_type": self.result_media_type or None,
            "redirected": self.redirected,
            "evidence": self.evidence_ids(),
            "ms": round(self.exchange.timings.total_ms, 1) if self.exchange.timings.total_ms else None,
        }


def error_signature(text: str) -> str:
    """A short, human-readable reason pulled out of an error body."""
    text = text.strip()
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if isinstance(data, dict):
            for key in ("exception", "error", "message", "detail", "reason"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return " ".join(value.split())[:240]
                if isinstance(value, dict) and value.get("message"):
                    return " ".join(str(value["message"]).split())[:240]
    if "<" in text[:200] and ">" in text[:400]:
        text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
        text = re.sub(r"<[^>]+>", " ", text)
    lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    for line in lines:
        if re.search(r"error|exception|invalid|parse|syntax|bad", line, re.I):
            return line[:240]
    return (lines[0] if lines else "")[:240]


def _looks_like_html(text: str) -> bool:
    head = text.lstrip()[:512].lower()
    return head.startswith("<!doctype html") or head.startswith("<html") or "<body" in head


def _json_error(text: str) -> bool:
    """True when the body is a JSON object that reports an error."""
    try:
        data = json.loads(text)
    except ValueError:
        return False
    return isinstance(data, dict) and any(k in data for k in ("error", "exception", "message"))


def _parse_json(text: str, result: QueryResult) -> str:
    try:
        data = json.loads(text)
    except ValueError:
        return NOT_SPARQL
    if isinstance(data, dict) and isinstance(data.get("head"), dict):
        if isinstance(data.get("boolean"), bool):
            result.boolean = data["boolean"]
            return OK
        bindings = (data.get("results") or {}).get("bindings") if isinstance(data.get("results"), dict) else None
        if isinstance(bindings, list):
            result.vars = list(data["head"].get("vars") or [])
            result.rows = [b for b in bindings if isinstance(b, dict)]
            return OK
    if isinstance(data, dict) and any(k in data for k in ("error", "exception", "message")):
        return ERROR_BODY_2XX
    return NOT_SPARQL


def _parse_xml(text: str, result: QueryResult) -> str:
    try:
        root = ET.fromstring(text.encode("utf-8") if isinstance(text, str) else text)
    except ET.ParseError:
        return NOT_SPARQL
    if root.tag != f"{SRX}sparql":
        return NOT_SPARQL
    boolean = root.find(f"{SRX}boolean")
    if boolean is not None:
        result.boolean = (boolean.text or "").strip() == "true"
        return OK
    head = root.find(f"{SRX}head")
    result.vars = [v.get("name") for v in head.findall(f"{SRX}variable")] if head is not None else []
    results = root.find(f"{SRX}results")
    if results is None:
        return NOT_SPARQL
    for res in results.findall(f"{SRX}result"):
        row = {}
        for binding in res.findall(f"{SRX}binding"):
            term = next(iter(binding), None)
            if term is None:
                continue
            kind = term.tag.replace(SRX, "")
            row[binding.get("name")] = {"type": "uri" if kind == "uri" else kind, "value": term.text or ""}
        result.rows.append(row)
    return OK


def _parse_delimited(text: str, result: QueryResult, delimiter: str) -> str:
    lines = text.splitlines()
    if not lines or not lines[0].strip():
        return NOT_SPARQL
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    header = next(reader)
    result.vars = [h.strip().lstrip("?$") for h in header]
    for record in reader:
        if not record:
            continue
        result.rows.append({v: {"type": "unknown", "value": val} for v, val in zip(result.vars, record) if val != ""})
    return OK


def _parse_rdf(body: bytes, fmt: str, result: QueryResult) -> str:
    from rdflib import Graph

    graph = Graph()
    try:
        graph.parse(data=body, format=fmt)
    except Exception:  # rdflib raises many parser-specific types
        return NOT_SPARQL
    result.triples = len(graph)
    return OK


def classify(result: QueryResult, expect: str = "results") -> QueryResult:
    """Fill in the verdict for a finished request.

    ``expect`` is ``results`` (SELECT or ASK) or ``graph`` (CONSTRUCT or
    DESCRIBE).
    """
    x = result.exchange
    if len(result.hops) > 1 and x.status in (301, 302, 303, 307, 308):
        result.verdict, result.detail = REDIRECT_LOOP, f"still redirecting after {len(result.hops) - 1} hops"
        return result
    if not x.ok_transport:
        result.verdict, result.detail = TRANSPORT, f"{x.error_class}: {x.error_detail}"
        return result
    text = x.text()
    if x.status in REFUSAL_STATUSES:
        result.verdict, result.detail = REFUSED, f"HTTP {x.status}: {error_signature(text)}".strip(": ")
        return result
    if not 200 <= x.status < 300:
        result.verdict, result.detail = HTTP_ERROR, f"HTTP {x.status}: {error_signature(text)}".strip(": ")
        return result

    media = x.media_type
    result.result_media_type = media
    if expect == "graph":
        fmt = RDF_MEDIA.get(media)
        result.verdict = _parse_rdf(x.body, fmt, result) if fmt else NOT_SPARQL
        result.media_type_matches = result.verdict == OK
        if result.verdict != OK:
            if _json_error(text):
                result.verdict = ERROR_BODY_2XX
                result.detail = f"HTTP {x.status} with error body: {error_signature(text)}"
            else:
                result.detail = f"2xx but not an RDF graph ({media or 'no content type'})"
        return result

    # SELECT / ASK: parse by declared media type first, then by sniffing,
    # because a correct document under a wrong content type is still usable
    # but is itself a protocol deviation (§2.1.6).
    declared = {MEDIA["json"]: "json", "application/json": "json", MEDIA["xml"]: "xml",
                "application/xml": "xml", "text/xml": "xml", MEDIA["csv"]: "csv", MEDIA["tsv"]: "tsv"}.get(media)
    sniffed = "json" if text.lstrip().startswith("{") else "xml" if text.lstrip().startswith("<?xml") or "<sparql" in text[:300] else None
    kind = declared or sniffed
    if kind == "json":
        verdict = _parse_json(text, result)
    elif kind == "xml":
        verdict = _parse_xml(text, result)
    elif kind == "csv":
        verdict = _parse_delimited(text, result, ",")
    elif kind == "tsv":
        verdict = _parse_delimited(text, result, "\t")
    else:
        verdict = NOT_SPARQL
    result.verdict = verdict
    result.media_type_matches = verdict == OK and media in MEDIA.values()
    if verdict == ERROR_BODY_2XX:
        result.detail = f"HTTP {x.status} with error body: {error_signature(text)}"
    elif verdict == NOT_SPARQL:
        what = "an HTML page" if _looks_like_html(text) else f"{media or 'no content type'}"
        result.detail = f"HTTP {x.status} but {what}, not a SPARQL results document"
    return result


def run_query(
    url: str,
    query: str,
    form: str = "post-form",
    *,
    accept: str = MEDIA["json"],
    expect: str = "results",
    purpose: str = "",
    **kwargs,
) -> QueryResult:
    """Send one query in one request form, follow redirects, classify."""
    method, request_url, headers, body = build_request(url, query, form, accept)
    hops = follow(method, request_url, headers=headers, body=body, purpose=purpose, **kwargs)
    return classify(QueryResult(url=url, form=form, query=query, hops=hops), expect)


def first_ok(results: list[QueryResult]) -> QueryResult | None:
    return next((r for r in results if r.ok), None)
