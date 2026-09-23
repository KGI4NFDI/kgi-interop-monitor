# 2026-09-23 History, status page and CI

## What was built

- `history.py`: `latest.json`, one compact line per run in `history.jsonl`,
  one full snapshot per UTC day (ADR 0006), KPIs over a window
  (availability, latency median and 95th percentile, flaps) and failing
  checks per layer per run.
- `page/`: one self-contained HTML file. Ladder, registry and hub findings,
  the check matrix, a drawer with the evidence behind every cell, failed
  checks over time.
- `.github/workflows/`: tests on every push (Python 3.10 and 3.12, green on
  the first push), the monitor every six hours, committing to the orphan
  `results` branch.

## Design decisions on the page

- Colour encodes outcome, and every outcome also has a glyph, so colour
  never carries meaning alone. Only failures are solid; passes and warnings
  are tints, so what needs attention stands out in a 36 by 17 grid.
- The grade chips use one blue ramp, validated as an ordinal ramp with the
  dataviz validator. The first light ramp failed the light-end contrast
  check (1.5:1 against the surface) and was re-stepped to start at a darker
  blue (2.06:1). The three series of the trend chart are the first three
  slots of the validated categorical palette; the aqua series is below 3:1
  on the light surface, so it carries a direct end label and the chart has
  a table view.
- The ladder shows "would clear it if the registry record were fixed" as a
  pale extension of each bar. That gap is the argument for fixing registry
  records first: it is the cheapest improvement on offer.

## What went wrong

1. **Nothing rendered on the first build.** The evidence excerpts include
   HTML error pages. A `<!--` followed by `<script` inside the data's script
   element switches the HTML parser into its double-escaped state, where
   `</script>` no longer closes the element, so the page script was read as
   part of the JSON. Escaping `</` (the usual advice) is not enough. Every
   `<`, `>` and `&` in the data is now a `\u` escape, and `test_page.py`
   pins the exact case.
2. **The drawer ignored `hidden`.** Its own `display: flex` beat the user
   agent rule. A `[hidden] { display: none !important }` rule fixes it for
   the standalone page (the artifact host adds the same rule).
3. **The browser pane cannot open local files.** The page is served over
   `http.server` on localhost for the one look it gets before publishing.
4. **The page scrolled sideways** below about 1,250 px: the matrix's
   min-content width blew out the wrapper's auto grid column. Found with the
   look before publishing; the column is `minmax(0, 1fr)` now.
5. **The drawer's scroll area was cut off** by 62 px: `height: 100%` plus
   padding without `border-box`.
6. **The first publish was refused**: the file held 60 raw U+FFFD characters.
   They were data, not damage (evidence of responses that were not UTF-8, such
   as the UTF-16 protocol test), and are now written as `�` escapes.

## Where the page is

The status page built from the first three runs is published as a private
claude.ai page (https://claude.ai/artifact/5WQvwk84uk4b4wZXbv2y1S). Every
scheduled run also rebuilds `site/index.html` on the `results` branch and
keeps it as a workflow artifact for 30 days.
