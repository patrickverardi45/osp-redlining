# Terminus fixture authoring guide (no Excel required)

A *terminus fixture* is one real bore plus what you expect the terminus extractor to find at its **start** and
**end**. You can author one with **plain notes + screenshots** — no Excel, no code.

## What the extractor decides (so you know what to write down)

For each endpoint it answers: **is the endpoint proven by printed/source evidence, or only known from the
bore-log row?**

- **source-bound** → a printed structure note `STA <station> <structure>` (or, later, a printed run callout /
  bilateral matchline equation) sits at the endpoint station. The endpoint is printed-proven.
- **not source-bound** → only the bore-log row gives the station value; no printed endpoint proof was found.
  The extractor reports the station value **and a named blocker** (e.g. `NO_PRINTED_START_STRUCTURE`).

The extractor **never** invents an endpoint or relabels a bore-log value as "printed". A correct
"not source-bound + blocker" is the honest, expected answer for many real bores today.

## Directory layout

```
<your-fixtures-root>/<your-bore-id>/
  uploads/
    project_plan.pdf          # the plan PDF (any real plan; a bore-log file too)
    bore_log.<xlsx|csv|pdf>   # the bore-log — ANY accepted kind, not only Excel
  expected_termini.json       # what you expect (hand-edit this text file)
  fixture.md                  # OPTIONAL: your notes + screenshots (human-readable; not parsed)
```

## `expected_termini.json` (hand-editable)

```json
{
  "fixture_id": "my-real-bore-01",
  "description": "Plain-English description of this bore and where its endpoints are.",
  "uploads": [
    {"kind": "PLAN_PDF", "filename": "project_plan.pdf"},
    {"kind": "BORE_LOG", "filename": "bore_log.xlsx"}
  ],
  "expected": {
    "start": {"source_bound": true,  "source_type": "PRINTED_STRUCTURE_LABEL", "blocker": null},
    "end":   {"source_bound": false, "source_type": "BORE_LOG_ROW", "blocker": "NO_PRINTED_END_STRUCTURE"}
  }
}
```

- `source_type` ∈ `PRINTED_STRUCTURE_LABEL` · `PRINTED_STA_CALLOUT` · `MATCHLINE_BOUNDARY_STATION` ·
  `BORE_LOG_ROW` · `KMZ_ROUTE_VERTEX` · `INFERRED_FROM_GEOMETRY` · `ABSENT`.
- `blocker` (when not source-bound) ∈ `NO_PRINTED_START_STRUCTURE` · `NO_PRINTED_END_STRUCTURE` ·
  `AMBIGUOUS_START_STRUCTURE` · `AMBIGUOUS_END_STRUCTURE` · `NO_BORE_LOG_STATION`.

## `fixture.md` (optional; your notes + screenshots)

Just write what you see. Example:

```markdown
# my-real-bore-01

Bore log says start 11+75, end 13+25, sheet 7.

## START (11+75)  — EXPECT: printed structure label
Screenshot: ![start](shots/start_hh_sheet7.png)
Notes: the plan prints "STA 11+75 INSTALLER HH" right at the entry. Source-backed.

## END (13+25)  — EXPECT: not printed (bore-log value only)
Screenshot: ![end](shots/end_sheet7.png)
Notes: I do NOT see a printed structure note at the end — only the drawn line. So I expect
       source_bound=false with blocker NO_PRINTED_END_STRUCTURE.
```

Screenshots live in any subfolder you like; `fixture.md` is for humans and is never parsed by the tests — so
there is no schema to satisfy and nothing to break.

## Rules (so a fixture stays honest)

- Use **real screenshots / plain notes** of what the plan actually prints. Do not write a `source_bound: true`
  you cannot point to in a screenshot.
- Do **not** use the recognized/work corpus or anyone's active work corpus as a fixture.
- Do **not** invent coordinates, depths, or structure labels. If you can't find printed proof, the honest
  expectation is `source_bound: false` + the matching blocker.
