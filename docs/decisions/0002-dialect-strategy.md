# 0002 Dialects: measure, then negotiate, never mask

Status: accepted, 2026-09-23

## Context

Endpoints in the registry run QLever, Virtuoso, Blazegraph (Wikibase), Jena,
Oxigraph and others. They disagree on which request forms they accept, which
result formats they return, how they report errors and which query shapes they
can answer in time. A monitor has two ways to get this wrong: adapt silently
and hide the defect, or refuse to adapt and report a false negative one layer
higher, as the census did for MatWerk.

## Decision

1. **Measure.** Every endpoint gets the same request matrix: GET, URL-encoded
   POST and direct POST, and for the working form the four result media types.
   The matrix is the evidence for layer B.
2. **Negotiate.** Probes in layers C (and later D) run on the first request form
   that returned a valid results document, and every result records which form
   and URL it was measured through.
3. **Never mask.** A workaround is always reported. If a probe needed a fallback
   query shape, that is itself a B3 finding. If the URL needed normalising, that
   is an A7 finding.
4. **Portable SPARQL only.** Probe queries use SPARQL 1.1 core, no engine
   extensions, no engine-specific hints. They live as `.rq` files so they can be
   read and reused as the D2.1 benchmark queries.
5. **Fingerprint to explain, not to steer.** The engine is inferred from the
   `Server` header, the error body returned for a malformed query, and URL
   shape. The fingerprint is shown next to results to explain them. It never
   changes what a probe sends. Engine-specific knowledge that is needed anyway
   (for example which named graphs are engine-internal) sits in one declarative
   table with the evidence it came from.

## Consequences

- A layer-B defect does not cascade into a false layer-C result.
- The fingerprint table will be incomplete at first. An unknown engine is shown
  as unknown, not guessed.
