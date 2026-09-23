# 0003 SPARQL 1.1 compliance is a separate axis from the layer grade

Status: accepted, 2026-09-23

## Context

The checklist layers are ordered checks of whether a client that knows only the
registry can get trustworthy answers. It is tempting to read "reached layer B"
as "speaks SPARQL 1.1". That reading is wrong in both directions:

- Some probes are stricter than the spec. Variable-endpoint `SERVICE` (B4) is in
  the informative section 4 of SPARQL 1.1 Federated Query. B3 is about
  performance. Layer C is about the data, not the engine.
- Passing A to C says nothing about most of the query language: property paths,
  aggregate edge cases, OPTIONAL semantics, functions, datatypes.

## Decision

- Each probe states its normative basis: a W3C MUST or SHOULD with section
  reference, a DCAT modelling rule, or "fitness for use" when no spec requires
  it. The status page shows it.
- A separate protocol conformance score runs the 13 read-only, data-independent
  tests of the W3C SPARQL 1.1 Protocol test suite, with dataset parameters
  removed. It is shown as `n/13`, next to the layer grade and never merged
  into it.
- Query-language compliance is out of scope for remote monitoring. It needs the
  W3C test data loaded into a store, which is a job for a local engine lab (for
  example pyomnigraph), keyed by the engine fingerprint.

## Consequences

The page can answer "is this endpoint usable" and "does it follow the protocol"
separately. Neither is presented as the other.
