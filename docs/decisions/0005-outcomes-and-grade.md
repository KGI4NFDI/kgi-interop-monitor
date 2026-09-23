# 0005 Six outcomes and a strict grade

Status: accepted, 2026-09-23. The treatment of A2 and of warnings is marked for review.

## Context

The checklist's central lesson is that a checker which skips a layer
under-reports the layers above it. A red cell must therefore say *why* it is
red: because the probe found the defect, because the probe could not be run,
or because the question does not apply. Collapsing those three is how the
first census reported false negatives.

## Decision

Six outcomes, mapped to the W3C Evaluation and Report Language so results can
be exported as EARL later:

| Outcome | Meaning | EARL |
|---|---|---|
| pass | the defect is absent | passed |
| warn | the defect is absent but something needs a human look, or a registry-side workaround was needed | passed |
| fail | the defect is present | failed |
| unknown | the probe ran and could not decide (timeout, politeness budget, instrument error) | cantTell |
| blocked | not run, because a lower layer failed (for example no working URL) | untested |
| n/a | the question does not apply (for example no ontology served, for C4) | inapplicable |

Some rows are *gating*: a layer is cleared only when all its gating rows are
pass, warn or n/a. Non-gating rows (A2, A6, B3, B4) are reported but never
hold the grade back. B4 is a property of the hub, and B3 is about performance.

The grade is strict and ordered: `none` < `dump` < `A*` < `A` < `B` < `C`.

- `none`: no working SPARQL URL and nothing else to offer.
- `dump`: no SPARQL, but a dump or access URL (A2). Layers B and C are n/a
  here, not blocked, because the KGI D3.1 guidelines make SPARQL optional.
- `A*`: a working SPARQL URL exists, but only after following a redirect,
  splitting a packed value or normalising the URL.
- `A`, `B`, `C`: all gating rows of that layer and every layer below clear.

Because the grade is strict, a KG stuck at `A*` hides how good its endpoint
is. So every report also carries `grade_if_registry_fixed`, the grade with the
A-layer registry defects forgiven. The gap between the two is the value of
fixing registry records, which is the quickest improvement on offer.

Higher layers are still *measured* when a lower layer is only degraded (for
example B1 fails but one request form works): they run through the working
form and record it (ADR 0002). They are blocked only when there is nothing to
measure through.

## Review

- A2 as warn plus n/a above it follows D3.1. The checklist lists A2 as a
  defect. If KGI decides SPARQL is required for registered KGs, A2 becomes a
  fail and `dump` sinks below `A*`.
- A warn clears a gate. That keeps review items (such as a union default graph
  over two release graphs) from sinking a KG, at the price of letting a real
  problem through until someone reads the warning.
