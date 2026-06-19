# Re-triage — log49 / log15 / log57 OUT of the fiber-backbone lane (READ-ONLY)

**Status:** classification only. No render, no engine commit, no flag, no fixture/census change, nothing
placed. Branch `feat/truelinev2` @ `2de1f18`. Triggered by the Gate-1 fiber design sprint, which found
these three have **zero generic-`BORE` run** on any referenced sheet, so they were wrongly parked in the
fiber-backbone bucket.

## Verdict
All three are **NOT fiber** and **NONE is renderable now**. Each is blocked on **END IDENTITY**, not on
the generic-`BORE` sprawl/disconnect the fiber tracer addresses. Re-file them out of the fiber lane.

## Evidence triangulated (three independent sources agree)
1. **Layer survey** (`run_fiber_lane_survey_probe.py`): generic-`BORE` = 0 segs on every referenced sheet
   of all three; the run rides BASE_CONDUIT classes (BORE - PORT / VACANT PIPE / LATERAL) + BORE - PATH.
2. **v2 truth table** (`data/outputs/final_engine_truth_table.json`, census-frozen): the authoritative v2
   stroke_status per bore.
3. **Legacy adjudications** (gac targets #23/#33/#34/#38, route480, drill_frame_bucket_review): consistent
   END-side findings, esp. for log57.

## Per-log

| log | sheets | span | generic-BORE | v2 stroke_status | actual lane | renderable | blocker |
|---|---|---|---|---|---|---|---|
| **log49** | 10 | 44' (44+89→45+33) | absent | `END_IDENTITY_UNPRINTED` (UNIQUE_BUT_CAVEATED) | end-identity / owner-confirm (source-gap) | **NO** | end-structure identity not printed → owner SOURCE_REVIEW or KMZ/geo |
| **log15** | 6,7,8 | 693' (24+07→31+00) | absent | `END_IDENTITY_UNPRINTED` (STATION_AXIS_INTERVAL_PATH) | end-identity / owner-confirm (source-gap) | **NO** | same end-identity gap; route is the opt-in station-axis-interval solver, end positioned not identified |
| **log57** | 8,10,13 | 413' (0+00→4+13) | absent | `PICK_CARD_WITH_END_ANCHOR` (AUTO_EXACT_MATCH box) | multi-drive pick-card / source-gap (`.FS`) | **NO** | multi-drive/multi-corridor: END 413→AP-157 (sh8) is geometry-ready BUT bore spans 2 corridors ({3..9} vs {10,12,13,14}); "print mapping uncertain" (split from bore_log24). Unblock = `.FS` drive-decomposition (proven absent) or owner corridor pick. Forcing AP-157 = wrong redline a corridor away (DO-NOT-WIDEN). |

## Existing primitives can't render any of them
- **Drop-terminus-symbol / cross-sheet-drop-terminus** need a flower-pot SYMBOL end — none of these ends
  at a flower pot (log49/15 ends unprinted; log57 ends at the AP-157 terminal).
- **Cross-sheet route-assembly (SEE-SHEET)** explicitly refuses the multi-corridor parallel-run case
  (log57) without an end-continuity / drive discriminator; log49/15 ends are not printed callout termini.
- **Drop lane (flower-pot KMZ identity)** is log5/30/48/50/65 — not these.
- So no shipped primitive yields a source-safe, unique, closing redline for any of the three.

## Net effect on the lanes
- **Fiber-backbone milestone shrinks** from the START_HERE list of 7 → the 4 true generic-`BORE` members
  (log42, log16 blobs; log3, log4 strips). See `gac/fiber_backbone_design_sprint.md`.
- **log49 + log15 → end-identity / owner-confirm lane** (same family as the review-candidate reasoning
  lane). Owner end-structure confirmation (or KMZ/geo) is the unlock. `run_remaining_endpoint_review.py`
  already builds the log49 owner contact sheet (read-only, no red).
- **log57 → multi-drive source-gap lane** (with log29/31/46/47/58). Unlock = the `.FS`
  Fiber-Schematic / drive-decomposition sheet (proven absent from all delivered Brenham PDFs) or an owner
  corridor/drive statement. Not a geometry problem.

## log49 render attempt (2026-06-18) — BLOCKED, not source-safe

Owner confirmed the IDENTITY (start = printed `STA 44+83 INSTALLER HH`; end = `STA 45+33=0+00 NEXTLINK HH`;
route printed `44+83->45+33` 50'; accept the ~6' recorded-vs-printed drift). Read-only verification via the
sweep's own binders showed the COORDINATE is not uniquely extractable, so the render gate ("only if unique/
source-safe and distinct from log48/log50") is not met:

- **END binds** cleanly: `nextlink_hh @ 45+33` -> (941.0, 353.3) STRUCTURE_POSITION_BOUND.
- **START does NOT bind** by any existing primitive:
  - `resolve_structure_position("44+83", installer_hh)` -> `LABEL_WORD_NOT_UNIQUE` ("44+83" prints 3x, all
    run-callout text at y~445-490, not at the symbol).
  - `_bind_hh_symbol_near_label("44+83")` -> `None` (ambiguous nearby HH symbols).
  - end-anchored chain-reach uniqueness -> the chain from the END is the **7877' shared sheet-10 network**
    (contains siblings log48/log50) and reaches **TWO** NEXTLINK termini at the bore span:
    (914.6,420.2)@49.9' and (861.3,354.2)@55.5' -> AMBIGUOUS.
- **Span/parent gate**: log49 is a split child of parent **bore_log20** (siblings log48, log50; the exact
  mixup family). `child_owns_route` compares the drawn span to log49's recorded `entry_span` 44'
  (`adj_corrected_span` unset); drawn ~50' = 13.4-13.6% > the 10% gate -> would fail even if a start were picked.

**Verdict: BLOCKED (not source-safe).** Forcing a pick between the two ~50' termini would be a nearest/
arbitrary guess in the bore_log20 split family -> wrong-redline risk DO-NOT-WIDEN forbids. The owner's
IDENTITY confirmation is accepted, but the start COORDINATE is not uniquely extractable from the plan.

**Exact unlock (named):** an owner pick between the two candidate start symbols — (914.6,420.2) vs
(861.3,354.2) — i.e. a coordinate-level disambiguation (or a KMZ/geo anchor), PLUS recording the owner's
44'->50' span correction as `adj_corrected_span` in the parent-source model so `child_owns_route` accepts
it. Until both exist, log49 stays a caveated review (PLACED_REVIEW), never an auto/forced render.

**OWNER PICK (2026-06-18):** owner chose **Candidate A = (914.6, 420.2)** (route 49.9' to the 45+33 end;
the NEXTLINK symbol nearest the printed `STA 44+83 INSTALLER HH` callout) via
`run_log49_start_pick_contact.py`. Coordinate ambiguity resolved.

**DETERMINISM CHECK (2026-06-18) — START IS DETERMINISTIC.** `resolve_structure_position(label_text="44+83",
structure_class="installer_hh", context_texts=("INSTALLER","HH"))` -> `STRUCTURE_POSITION_BOUND` at
(914.6,420.2) == A. Exactly ONE of the three `44+83` tokens sits in an `INSTALLER HH - TEXT` label box
(936,453,987,468) carrying `['13"X24"X24"','44+83','@','HH','INSTALLER','STA']`; its single leader resolves
to A; class-fill = installer_hh red. The other two `44+83` tokens are run-callout text (no INSTALLER HH box).
**Candidate B is rejected by SOURCE** (not at that leader tip; no INSTALLER HH callout points to it). END
binds (`nextlink_hh @ 45+33` -> 941.0,353.3); route source-backed, 4 verts, drawn **49.9'** = closes the
printed `DIR. BORE (50')` callout (0.1%). So the bind is NOT a coordinate pick — it is the standard
word->box->leader->symbol->fill chain, owner-confirmed only as to identity (class word INSTALLER).

**REMAINING BLOCKER — parent-source span gate.** `child_owns_route(49.9, [10])` -> REJECT: "candidate span
50ft does not close its own recorded span 44+89->45+33 (~44ft, tol 10%)" (13.4% > 10%). The drawn route
matches the PRINTED 50' callout (source); the bore-log's 44' is the OCR-drift the owner accepted.
Distinctness from siblings is fine (`span_collision: []`; 49.9' is nowhere near log48's 507' / log50's 514').
The ONLY deterministic fix is the parent model's `adj_corrected_span = "44+83->45+33"` (source-confirmed by
the printed callout; accepted because log49 has no span-colliding sibling) -- a `parent_source_model.json`
edit.

**RENDERED (2026-06-18, commit `b4b597d`, pushed -> `origin/feat/truelinev2`). FRONTIER 44 -> 45.** Owner
authorized the deterministic render + the parent-model span correction. NEW gated opt-in
`start_label_context` hook (the START analogue of `end_hh_symbol_bind`) binds the installer HH via the
INSTALLER HH callout context+leader -> Candidate A (914.6,420.2); B rejected by source. END = 45+33 NEXTLINK
HH. `adj_corrected_span="44+83->45+33"` set on log49's parent-model entry (source-confirmed by the printed
50' callout; not corpus/census). Drawn 49.9' closes 50'; parent gate passes; DISTINCT from log48 (507') /
log50 (514'). All 54 prior sweep renders byte-identical (md5 vs HEAD); +1 new PNG. Callout gated e2e 24
passed; v2 suite 1376 passed, 2 skipped; census FROZEN. Three files: sweep + test + parent model.

## log15 end decision (2026-06-18) — OWNER CHOSE B (continuation); NOT renderable at 31+00

Contact sheet `run_log15_end_decision_contact.py` (read-only, no red, not committed) surfaced the source:
- sheet 7: `STA 28+73=0+00 NEXTLINK HH / SPLICE POINT 35` -> `DIR. BORE (191') 28+73->30+64` ->
  `MATCHLINE STA 1+93/30+64 - SEE SHEET 8`.
- sheet 8: reciprocal `... SEE SHEET 7`, then the run CONTINUES `STA 30+64 -> 33+93`, then
  `MATCHLINE STA 33+93 - SEE SHEET 9`. The recorded `31+00` sits mid-run with NO terminus structure within
  90 pt (it is the `E/W PORT TERMINAL TAIL` backbone with AP-154/156/157 + flower pots).

**Owner chose B: log15 CONTINUES across the 30+64 matchline; 31+00 is NOT the terminus** (an interior
ruler-point). Choice A (real end at 31+00) is refuted by source (no structure; conduit runs through).

**RECLASSIFIED: log15 = cross-sheet CONTINUATION (terminus on sheet 9+, UNIDENTIFIED), not a 31+00 end.**
Not source-safe to render: drawing at 31+00 would be the ruler-cut-on-a-through-alignment false positive.
**Blocker / next step:** trace the `33+93 -> SEE SHEET 9` continuation to the TRUE terminus on sheet 9+ and
identify it (structure / matchline / dead-end). This overlaps the cross-sheet / PORT TERMINAL TAIL backbone
lane; it is a separate investigation, owner-authorized. No render; state unchanged (`b4b597d`, frontier 45).

## Guardrails honored
Read-only. No BORE→BASE_CONDUIT, no MAX_DASH_GAP change, no corpus mutation, no census rebaseline, no
flag, no deploy, no `origin/main`, no forced ambiguous redline, no log16 slice. Reversible (one untracked
doc + the survey probe).
