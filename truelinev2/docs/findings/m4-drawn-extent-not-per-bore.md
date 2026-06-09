# M4 finding — the drawn directional bore has no per-bore extent (REVIEW is the ceiling)

**Date:** 2026-06-09
**Status:** negative result, banked. No placement moved. 0-false preserved.
**Scope:** `truelinev2/` only. Read-only probe; no production / old-engine touch; nothing deployed.

## Question
M4 (chosen path: "ODOT AUTO extent") asked: can we trace the real `E-PROPOSED-DB`
drawn run so `match_mode="extent"` fires its first ODOT **AUTO** on the Tulsa-31
data already in hand — i.e. a tight, unique drawn span matching one bore log?

## Method
A read-only probe (written **outside** the repo, nothing committed) reused the
shipped v2 modules + the proof's input staging to compare, per Tulsa-31 bore:
today's rect-bbox extents (`vector_segments`) vs **true** per-path geometry
(`get_drawings()['items']`), each projected onto the station axis, against the
bore span and the shipped `auto_tol = 25 ft`.

## Evidence
1. **rect bbox == true item geometry in every case** → swapping `vector_segments`
   rect for `items` polylines buys **zero** tightness. The change M4 proposed does
   not move the needle.
2. `E-PROPOSED-DB` draws the directional bore as a **continuous dashed alignment
   line**: every drawn run ≈ **40 ft dash / ~9 ft gap**, identical across sheets
   10 / 11 / 12 and all three bores — a CAD linetype, not bore boundaries.
3. The dashed line overshoots each VeroFy log's sub-span; no single run is tight + unique:

   | Bore | Span (ft) | Drawn dashes (ft) | Tight single-run candidates |
   |---|---|---|---|
   | 118′ | `[1420,1538]` | `1386 → 1566` (overshoots both ends) | **0** |
   | 88′  | `[2333,2421]` | `2328 → 2474` (overshoots end) | **0** |
   | 71′  | `[1976,2047]` | dash `[1984,2024]` within 25 ft of both ends | **1 — coincidence** |

   The 71′ "hit" is dash-phase luck: `[1984,2024]` covers only the first 40 ft of
   the 71 ft span, and a continuation dash `[2033,2073]` runs 26 ft past the end →
   not unique, union not tight.

## Conclusion
The plan draws **one continuous designed directional bore**; each VeroFy log is a
*sub-span* of it, and the plan does not encode where one log ends and the next
begins. So a deterministic **per-bore drawn extent does not exist** in Tulsa-31.
**REVIEW is the correct ceiling** for ODOT extent; forcing AUTO would tune to a
rendering artifact and risk a false placement — violating the 0-false invariant.

Not categorically impossible: a future packet whose bore log spans a *whole* drawn
run would have real termini and could AUTO. Tulsa-31 does not provide it.

## Banked changes (no placement moved; all 3 bores still REVIEW)
- `match/overlap.py` — extent REVIEW reason tightened
  `DRAWN_BORE_COVERS_SPAN` → `DRAWN_EXTENT_COVERS_SPAN_NOT_TIGHT`, plus a
  convention-neutral caveat `DRAWN_EXTENT_EXCEEDS_BORE_SPAN` when the covering
  geometry overshoots the span. (The no-convention-leakage guard stays green —
  the core names no convention.)
- `extract/odot.py` — the dialect docstring records this finding (the convention home).
- `tests/test_odot_extent.py` — `test_continuous_run_covers_span_reviews` asserts the
  new reason + caveat.
- This doc.

## Named target (per the abstention doctrine)
"ODOT extent → AUTO" remains a **named target**, unlocked only by either:
(a) a packet whose bore log spans a whole drawn run (real termini), or
(b) a different deterministic per-bore anchor (e.g. entry/exit pit symbols, or
bracketing "VIA DIRECTIONAL BORE" note pairs that delimit one log's run).
Until then ODOT places REVIEW, honestly — abstention from AUTO is an interim
safety state, not a manual fallback.
