# Source-Span Extractor (MVP) — read-only span identity from source files

> Modules: `truelinev2/harness/span_source.py` (discovery + text/table extraction) and
> `truelinev2/harness/span_extractor.py` (span-row contract + parser + bridge). Tests:
> `truelinev2/tests/test_span_extractor.py`. Feeds
> [`SOURCE_COMPLETENESS_REVIEW_READINESS.md`](SOURCE_COMPLETENESS_REVIEW_READINESS.md) — it does **not** draw.

## The product problem

Track B proved plan geometry alone is insufficient: the product needs **source-confirmed bore/span identity**
before it can draw a REVIEW redline. This layer is the automatic extraction of that identity from the customer's
own source files (bore logs / bore schedules / span tables), filling the `source_confirmed_span_count` the
readiness classifier's `SPAN_SOURCE` seam needs. Guardrail: **never invent a station, a row, an endpoint, a
coordinate, or a source relationship.** A span is confirmed only when a source file *explicitly* ties two
stations together as one bore.

## What counts as a source-confirmed span

Two stations tied as one bore by an explicit source relationship — one of:

- **Explicit start/end columns** in a table (`start`/`from`/`begin` + `end`/`to`/`finish`, name-free synonyms).
- **Labeled start/end rows** in a single-station-column table (a role column labeling one row start, one end).
- **Inline station-pair callout** in text: `a+bb TO c+dd` or a dash range (reusing the proven name-free
  `extract.callout_anchor.span_callouts`, which deliberately skips the named `STA a TO STA b` / `DIR BORE`
  dialect — so `select_dialect` is never weakened).

Bare station rulers, a single station, and two unrelated standalone station labels are **refused**. Footage is the
printed value when present, else the labeled `COMPUTED_FROM_STATIONS` difference of the two source stations. Every
station is parsed by the canonical `truelinev2.stations.parse_station` — no station parsing is reinvented.

**Known limit (inherited, by design):** the inline-callout grammar reused from `extract.callout_anchor` caps the
station prefix at 1–3 digits, so a 4+ digit *inline* callout (e.g. `1000+00 TO ...`, ≈19 mi — never seen in real
bore stationing) is conservatively **refused**, not mis-read. Table paths (explicit columns / labeled rows) use
the full canonical parser and handle any station length. Widening the shared inline grammar would touch a module
consumed by the cold-package gates and would require re-verifying the deterministic frontier — a separate, gated
change, out of scope here.

## Modular seams

1. **Source file discovery** — `span_source.discover_span_sources(folder)`: manifest-driven (BORE_LOG-kind
   uploads, so the PLAN pdf is never mistaken for a span source) + an extension fallback for loose table/text
   files.
2. **Text/table extraction** — `span_source.documents_from_{text,csv,xlsx,pdf,file}` → normalized
   `SourceDocument` (text lines and/or a `SourceTable`). CSV via stdlib `csv`; XLSX via lazy `openpyxl` (the repo
   convention); text-PDF via lazy `ingest.pdf.PlanPdf` text; markdown pipe tables supported.
3. **Span-row parser** — `span_extractor.extract_spans_from_documents(docs)`: explicit-columns / labeled-rows /
   inline-callout grammars → span rows, else an honest per-document refusal.
4. **Normalized span-row contract** — `SpanRow` (`span_id`, `source_file`, `source_page`, `source_kind`,
   `start_station`, `end_station`, `footage`, optional `start_structure`/`end_structure`, `status`/`confidence`,
   `citation`, optional `bbox`) + `SpanExtraction` (spans, refusals, `source_files_seen`,
   `source_confirmed_span_count`).
5. **Bridge** — `span_extractor.span_source_evidence_from_extraction(extraction)` → `SpanSourceEvidence`, feeding
   `ReviewReadinessEvidence.span`. Counts drive the classifier: `≥1 span` → `SPAN_SOURCE_FOUND`; a
   seen-but-unconfirmed source → `NO_SOURCE_CONFIRMED_SPAN`; no source file → `MISSING_BORE_SPAN_SOURCE`.

## Refusal vocabulary

`NO_SOURCE_SPAN_FILE` (no candidate file), `NO_TABLE_SPAN_COLUMNS`, `STATION_RULER_ONLY`,
`UNRELATED_STANDALONE_STATIONS`, `NO_STATION_SPAN_TEXT`, `UNREADABLE_SOURCE`. Distinguishing **"a source file
exists"** (`source_files_seen` non-empty) from **"a source-confirmed span exists"**
(`source_confirmed_span_count ≥ 1`) is the layer's core job.

## Guardrails

Read-only, harness-only. No AUTO, no REVIEW stroke, no renderer, no placement/status, no `_cap_review`, no
web/staging/backend runtime, no `origin/main`. Imports nothing from render/placement/api/store/contracts/web (a
test asserts this). Name-free; real project/customer names appear only as runtime data. No uploaded/private source
files or gitignored data artifacts are committed — all fixtures are generic and built in the test's tmp dir.

## How to run (read-only)

```
PYTHONPATH=. venv/Scripts/python.exe -m pytest truelinev2/tests/test_span_extractor.py -q
# harness-only diagnostic CLI over a source file or a package folder (writes nothing, draws nothing):
PYTHONPATH=. venv/Scripts/python.exe -m truelinev2.harness.span_extractor <file-or-folder>
```
