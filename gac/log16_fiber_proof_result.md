# Gate 1 — LOG16 FIBER PROOF SLICE RESULT (PROOF/READ-ONLY)

**Status:** proof only. No render, no engine commit, no flag, no fixture/census change, nothing placed.
Branch `feat/truelinev2` @ `b4b597d`. Answers the Gate-1 proof question for log16: *can the existing
corridor machinery + the proposed junction-bridge gates produce a unique, source-backed verdict for
log16?* Evidence is source-measured by two new read-only probes (below); both reuse the shipped machinery
verbatim — no new module, no new constant, no flag, no budget/tolerance raise.

> Headline: **NO — and the blocker is upstream of the corridor.** log16's START (31+00) is an UNPRINTED
> ruler-cut on a through-alignment (nearest structure 209 pt ≈ 145 ft away; zero structure within 90 pt),
> the SAME interior cut as log15's owner-decided end. log16's run is **cross-sheet (8→9→10)**, and the
> generic-`BORE` fiber blob is **only the middle leg (sheet 9)** — the two endpoints do not even sit on
> the blob sheet. So the single-sheet fiber-corridor + junction-bridge design is **structurally
> inapplicable**, and the identity gate (`ENDPOINT_IDENTITY` / `MISSING_SOURCE`) fails before any corridor
> is trusted. **log16 is the downstream continuation of log15 on the E/W PORT TERMINAL TAIL backbone**, not
> an independent fiber bore — re-triage it OUT of the fiber lane, INTO the log15 cross-sheet-continuation
> lane.

---

## Probes (read-only, untracked, gitignored outputs)
- `truelinev2/proof/run_log16_fiber_proof_slice.py` — runs the design-packet §4 bounded-corridor algorithm
  as a MEASUREMENT (endpoint binds → ladder/scale → generic-`BORE` ∪ BASE corridor → length corridor →
  walk → bridge analysis → typed verdict). Output: `data/outputs/log16_fiber_proof_slice/…json`.
- `truelinev2/proof/run_log16_endpoint_context.py` — verifies the endpoint result is a true source fact
  (raw structure/reset/matchline context at each endpoint on every sheet), not a binder artifact.

---

## LOG16 FIBER PROOF RESULT

- **Source data.** `bore_log16`: span **879'**, sta **31+00 → 39+79** (running ft 3100→3979; NOT a local
  reset frame), `sheet_refs = [8, 9, 10]`, `print_raw = "8,9,10"`. Generic-`BORE` (outside BASE_CONDUIT):
  sheet 8 = **0**, sheet 9 = **159 segs / 1 comp / ~3128' / bbox w584×h354 (the BLOB)**, sheet 10 = **0**.
  So the only generic-`BORE` is the **sheet-9 middle leg**; sheets 8 and 10 carry BASE_CONDUIT only
  (41 / 122 segs).

- **Endpoint identities.**
  - **END 39+79 = UNIQUE.** Binds `installer_hh` at **(188.1, 422.2) on sheet 10** (5.6 pt from the ladder
    position of running 3979; printed `STA 39+79` + `13"X24"X24"` HH box + `2-1.25" HDPE`). A real printed
    structure — but the backbone **continues past it** (printed `40+00`, `169'` to the next segment), so it
    is an interior HH, not a hard terminus.
  - **START 31+00 = UNPRINTED.** Zero binds across `nextlink_hh / installer_hh / terminal_port_hh /
    flower_pot` × sheets 8/9/10 × both label forms (`31+00`, `31+00=0+00`). Projected onto sheet 8's ladder
    (running 3100 → (648.8, 550.8)), the **nearest NEXTLINK is 209 pt away and the nearest FLOWER POT 210
    pt** — nothing within 90 pt. Sheet 8 carries **no reset callouts**. 31+00 sits between the printed
    matchlines `STA 1+93/30+64 - SEE SHEET 7` and `STA 33+93 - SEE SHEET 9` → it is a **ruler-cut on the
    continuous backbone**, identical to log15's owner-decided 31+00.

- **Fiber / generic-`BORE` geometry.** Sheet 9 = **one** connected component (159 segs, ~3128'); the whole
  sheet's fiber net is a single blob (the SPRAWL wall). The start-bind symbol does **not** host into it
  (`host=None`) — because the start is unprinted and the start region is on sheet 8, not sheet 9.

- **Station / callout ladder (sheet 9).** Coherent scale **1.44 pt/ft**; 5 clean ticks → **2 rows**
  (3400→3500, 3600→3800). The rows cover only the **middle** of the run; **neither endpoint** (3100, 3979)
  is on the sheet-9 ladder (start projects on sheet 8, end on sheet 10). Sheet 9 also carries an interior
  reset `35+43=0+00` and matchlines `33+93 - SEE SHEET 8` + `38+90/6+11 - SEE SHEET 10`.

- **Candidate bounded corridor.** **NOT ATTEMPTED / inapplicable.** The corridor requires two
  identity-anchored endpoints on the lane sheet; log16 has only one printed endpoint (the END, on sheet
  10), the START is unprinted, and the blob is on a third sheet (9). A single-sheet corridor cannot be
  anchored by log16's endpoints.

- **Junction-bridge needed.** **MOOT / not exercised.** The design-packet junction-bridge addresses a
  *within-sheet* generic-`BORE`↔BASE_CONDUIT tap gap (log42's 65 pt). log16's discontinuities are the
  **cross-sheet matchline crossings** (33+93 between sheets 8↔9, 38+90 between 9↔10) — handled by
  cross-sheet route-assembly, not the junction-bridge. log16 never reaches the bridge question.

- **Bridge gate result.** N/A (bridge not reached). Recorded for completeness: log16 would fail the
  *identity-anchor* precondition (no printed start) before any of the five bridge gates apply.

- **Unique candidate:** **NO.** Typed verdict `MISSING_SOURCE_ENDPOINT_IDENTITY` (START 31+00 UNPRINTED;
  END UNIQUE). Not ambiguous, not an overtrace, not a rejected bridge — **missing source** at the start.

- **Closure.** Not computable (no start anchor). The printed run does continue cross-sheet 8→9→10; the
  combined log15+log16 backbone is the continuity, not a sheet-9 self-contained arc.

- **Rejection gates triggered.** `ENDPOINT_IDENTITY` (start = UNPRINTED) → identity gate fails first.
  Downstream gates (`LADDER_SCALE_NOT_COHERENT`, corridor, walk, frame-ownership, terminus, bridge) are
  **not reached** — correctly, since an unanchored corridor must never be trusted.

- **Safe future render path.** None for log16 *in isolation*. log16 = the **downstream continuation of
  log15** on the same E/W PORT TERMINAL TAIL backbone; they share the unprinted 31+00 cut and the 33+93
  matchline. The only safe unlock is the **log15 continuation lane**: identify the backbone's TRUE printed
  termini (upstream: log15's `28+73 NEXTLINK HH / SPLICE 35` region; downstream: trace past the 39+79
  installer HH / `40+00` to the real end) and render the **combined** run between real structures — the
  31+00 split is a bore-log segmentation artifact that the plan does not draw, so it can never be a stroke
  endpoint. (Owner source identifying 31+00 would not help — there is nothing there to bind.)

- **Required implementation slice.** **NONE built, none recommended for the fiber lane.** The proposed
  `truelinev2/extract/junction_bridge.py` was deliberately **NOT written** — the proof shows log16 does not
  exercise it. The genuinely-needed primitive for log16 is the **cross-sheet-continuation terminus
  identifier** (the log15 blocker: trace `33+93 → SEE SHEET 9 → SEE SHEET 10 → …` to the true downstream
  terminus), NOT a fiber corridor and NOT a junction-bridge.

- **Tests needed.** None (no engine change). If the cross-sheet-continuation lane is later built, its tests
  belong to that lane, not the fiber lane.

- **Commit.** **NONE.** Read-only proof: two new untracked probes + this packet + gitignored JSON outputs.
  No tracked engine/fixture/render/census file touched; `b4b597d` unchanged; frontier 45/58 unchanged.

- **Push.** **NONE.**

- **Recommendation.**
  1. **Re-triage log16 OUT of the fiber lane**, INTO the **log15 cross-sheet-continuation lane** — they are
     two halves of one continuous backbone split at the unprinted 31+00 cut. The fiber milestone shrinks
     from 4 → **3** true generic-`BORE` members (log42 blob; log3/log4 strips).
  2. **Do NOT build the junction-bridge for log16** — it is the wrong tool; log16 never reaches the bridge.
  3. **The fiber lane still lacks a clean single-sheet PROOF case.** log42 is owner-contested; log16 is
     cross-sheet with an unprinted start; log3/log4 are thin strips dominated by cross-sheet assembly. A
     new fiber proof target must have **both endpoints printed AND on the same generic-`BORE` blob sheet** —
     a named follow-up survey (none of the surveyed 7 satisfies it as-is).
  4. **Bank the side benefit:** this proof *traced* log15's owner-named continuation (`33+93 → SEE SHEET 9`)
     through the sheet-9 fiber blob to the sheet-10 installer HH at 39+79 (= log16's end) and showed the run
     continues past it — concrete progress on the log15 blocker, to be finished in that lane.

---

## Guardrails honored
Read-only. No render, no stroke/card/PNG/AUTO. No BORE→BASE_CONDUIT (the generic layer was added ONLY to
the proof's local lane set; BRENHAM_CONDUIT_LAYERS untouched). No MAX_DASH_GAP / budget / tolerance change.
No corpus mutation, no census rebaseline, no flag, no deploy, no `origin/main`, no backend/web/runtime
touch, no unrelated-file cleanup. Reversible (two untracked probes + this packet; gitignored JSON).
