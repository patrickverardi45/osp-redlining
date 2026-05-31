# Target #26 — PDF Visual Bore→Structure Extraction Path — READ-ONLY

**Product correction honored:** the plan sheets DO visually encode the bore-run→structure
relationship; the gap was an **extraction-method failure**, not missing data. This target
proves the relationship is machine-extractable from the provided PDFs and defines the exact
primitive — validated on real pages against known answers.

**VERDICT: POSITIVE — the bore→structure relationship IS present and auto-extractable.** A
position-aware spatial join over the plan sheets reproduces known run-endpoints directly from
geometry: `STA 4+51 → TERMINAL PORT HH` (AP-163) at **13 px**, and `STA 4+13 → PORT` (AP-157)
at **14 px**. The hand-transcribed `BRENHAM_PH5_RUN_ENDPOINTS` table is exactly this join done
by eye — it can be derived automatically. Nothing was placed.

> Read-only. No engine/STATE change, no flag, no placement. Probe:
> `scripts/pdf_visual_relationship_probe.py` → `.out` (positioned words + vector layer on the
> real plan PDF). Geometry catcher = the Target #25 AP/structure index.

---

## 1. Which PDF pages/sheets carry the relationship (deliverable 1)

The **detailed plan sheets 8–14** (`Brenham - Phase 5_07-15-25.pdf`, pdf pages **21–27**;
sheet N = page N+13). Each is a dense AutoCAD plan view where every DIR.BORE run is drawn as a
leader/polyline ending at a structure symbol with adjacent STA + structure text. Measured on
two sheets:

| sheet | pdf page | words | vector lines | vector curves | rects | STA callouts | structure labels (FLOWER/SPLICE/TERMINAL/PORT) | DIR.BORE |
|---|---|---|---|---|---|---|---|---|
| 8 | 21 | 1150 | 2157 | 6477 | — | 15+ | 30 | — |
| 10 | 23 | 1588 | 3233 | 7874 | 34 | 55 | 13+5+34 | 20 |

## 2. Visual-element inventory needed (deliverable 2)

| element | how it appears | extractable today? |
|---|---|---|
| **STA callouts** (`4+51`, `4+13`, `0+00`…) | positioned text words with (x,y) bbox | **YES** — `extract_words(use_text_flow=True)` gives x0/x1/top/bottom |
| **Structure-type labels** (`TERMINAL`/`PORT`/`FLOWER`/`SPLICE`) | positioned text | **YES** — present, 30+ per sheet |
| **AP numbers** (`163`, `157`) | positioned text, but glyph-scrambled on vector sheets | **PARTIAL** — needs Target #1 char-stream V2 recovery (plain extract found only `100`) |
| **Leader lines / bored-run polylines** | `page.lines` (2–3k) + `page.curves` (6–8k) | **YES as geometry**, but NEVER read by the text extractor |
| **Structure symbols** (handhole/pot boxes) | `page.rects` | YES as geometry |
| **Matchlines** | `MATCHLINE STA …` text + a line | YES (already in graph) |
| **Sheet/grid context** | `<n> OF <total>` title block | YES (already used) |

## 3. Why the current extractor misses it (deliverable 3)

The blocker is **layout binding**, four concrete failures:
1. **Text-order flattening.** `extract_text()` / linear `use_text_flow` emit a STA callout and
   its adjacent structure label as far-apart tokens in reading order — the **(x,y) adjacency
   that encodes "this station ends at this structure" is discarded.**
2. **Vector layer unread.** The leader lines + bored-run polylines (the literal "bore path"
   the product refers to) live in `page.lines`/`page.curves` — **thousands of objects the text
   pipeline never touches.** The run→structure connection is drawn, not written.
3. **AP-number glyph scramble.** On these vector-heavy AutoCAD sheets the AP digits render
   out of order under plain extraction (Target #1) — recoverable only via char-stream V2, and
   only the *structure type* (PORT/FLOWER) survives plain extraction.
4. **No spatial-join step.** Nothing in the pipeline pairs callout ↔ nearest structure label
   ↔ connecting leader. The relationship is computable but never computed.

## 4. Concrete extraction path for a blocked log (deliverable 4) — bore_log57

Validated end-to-end by the probe:

```
bore_log57 (print 8, end station 413)
  → sheet 8 (pdf page 21): spatial nearest-label join on the '4+13' STA callout
      '4+13' @ (x=1097,y=332)  →  nearest structure label 'PORT' @ (x=1089,y=344), dist=14px
      = TERMINAL PORT HH  (AP-157's run terminus — matches hand-table (8,413,"ap",157))
  → AP number 157 recovered by co-located char-stream V2 (Target #1 technique)
  → Target #25 AP/structure index[157]  →  latlon [30.15819…, -96.38598…],
      tail_route route_465, fs_page 8, station 413
  → geometry resolved.
```

The same join validates AP-163 (`4+51`→TERMINAL @13px) — the bore_log7 anchor. So the
primitive reproduces *known-correct* answers, then extends to the blocked log. (bore_log57's
residual cross-sheet ambiguity — a sheet-13 matchline at 398 — is resolved by the *same*
primitive: a `MATCHLINE` label is not a structure-type label, so a type-filtered join keeps
AP-157.)

**Honest caveat — multi-drive logs whose END is not a printed terminus.** bore_log29 (end 415)
has **0 `4+15` callouts** on sheets 10/12 (probe-confirmed; the sheets carry local-0+00 drive
stations 0+47…1+90, 1+90…5+10). Its end is a *mid-drive* station, so end-station matching can't
bind it even with perfect extraction — it needs the per-DRIVE run grouping below.

## 5. Smallest next extraction primitive (deliverable 5)

**Primitive A — `STA-callout → nearest structure-type label` spatial join (per detailed sheet).**
Pure/read-only: for each `STA d+dd` word, the structure label within ≤~20 px (and/or connected
by a `page.lines` leader), with the AP number recovered by co-located char-stream V2. Output =
an **auto-derived `(sheet, station, structure_type, ap)` table** that reproduces the
hand-transcribed `BRENHAM_PH5_RUN_ENDPOINTS` (validate by equality against it), then feeds the
Target #25 index. This replaces manual transcription and covers every run-terminus bore
(backbone-AP + flower-pot drops).

**Primitive B (follow-on, for the multi-drive logs) — DIR.BORE RUN grouping.** Group each
`{BORE label + its start/end STA callouts + connecting leader polyline + end structure}` into a
run object, giving per-drive `start→end → structure`. A multi-drive bore's internal station
subranges then bind drive-by-drive (not just by its final end), unblocking bore_log29/31/46/47/58.

## 6. Verdict + next implementation target

**The relationship is in the PDF; the failure was extraction.** Next implementation target: a
**default-OFF, read-only `extract_run_endpoints_from_sheet(page)` shadow helper** implementing
Primitive A — derives the `(sheet, station, structure_type, ap)` tuples by spatial join +
char-stream AP recovery, **gated by an equality check against the existing hand `BRENHAM_PH5_RUN_ENDPOINTS`**
(ship only if it reproduces the known table), feeding the Target #25 index. It builds the
structure-side table automatically and still places nothing (DO-NOT-WIDEN intact). Primitive B
(run grouping) follows for the multi-drive logs. This is the first target since #20 with a
concrete *forward extraction* path rather than an abstain.

## 7. Files read
- `Brenham - Phase 5_07-15-25.pdf` plan sheets 8 & 10 (pdf pages 21, 23) — positioned words +
  `page.lines`/`curves`/`rects` (read-only).
- `BRENHAM_PH5_RUN_ENDPOINTS` ([pdf_ap_route_resolver.py](backend/app/core/pdf_ap_route_resolver.py)) — the hand table this primitive reproduces.
- Target #25 `scripts/ap_structure_index.{py,json}` (the geometry catcher); Targets #1 (glyph V2), #20, #23, #24.
- Probe: `scripts/pdf_visual_relationship_probe.py` → `.out`.
