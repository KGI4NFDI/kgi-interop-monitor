# 0001 Probe over raw `http.client`, not a SPARQL or HTTP library

Status: accepted, 2026-09-23

## Context

Layer B of the checklist is about what the server does on the wire. The
libraries a SPARQL client would normally use each change that picture:

- SPARQLWrapper picks one request form and turns HTTP errors into exceptions,
  so a 200 with an error body (B2) looks like success with no rows.
- requests and urllib follow redirects, and a 301 or 302 on a POST is replayed
  as a GET without the body. The query silently disappears.
- Both decode, decompress and normalise headers before the caller sees them.

The census that under-reported MatWerk failed exactly this way: it used one
dialect and trusted the status code.

## Decision

All probe traffic goes through a small client on the standard library's
`http.client`. It sends exactly the bytes a probe asks for, never follows a
redirect on its own, and returns an `Exchange` record with: request line and
headers, status, response headers, a capped body excerpt, the error class if
the connection failed, and timings (DNS, connect including TLS, time to first
byte, total). Redirects are followed by the caller, one hop at a time, and each
hop is recorded.

## Consequences

- Timings come from the same code path that sends the query, so latency KPIs are
  comparable across endpoints.
- No proxy support. GitHub runners do not need one; a local run behind a proxy
  would have to add it.
- The client is small enough to test against a local fake endpoint, which is
  how its failure classification gets tested.
