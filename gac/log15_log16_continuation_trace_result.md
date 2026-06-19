# LOG15/LOG16 CROSS-SHEET CONTINUATION TRACE — RESULT (PROOF/READ-ONLY)

**Status:** proof only. No render, no engine commit, no flag, no fixture/census change, nothing placed.
Branch `feat/truelinev2` @ `b4b597d`. Traces the combined log15/log16 run to its true printed termini,
treating the unprinted 31+00 as an interior segmentation cut (per `gac/log16_fiber_proof_result.md`).
Evidence: `truelinev2/proof/run_log15_log16_continuation_trace.py` (read-only; output under gitignored
`data/outputs/log15_log16_continuation/`). Reuses shipped machinery verbatim — no new module/constant/flag.

> Headline: **the combined log15/log16 run is an INTERIOR segment of one long, continuously-spliced 2-1.25"
> 288ct fiber MAIN backbone — it has NO clean standalone terminus pair.** Its recorded endpoints are mostly
> unprinted interior cuts (log15 start 24+07 ≈ `MATCHLINE 24+11 SEE SHEET 5`; the 31+00 cut). The ONLY
> printed structure among the endpoints is log16's END (installer HH @ 39+79) — and the physical run
> **continues past it** through interim handholes to **SPLICE POINT 46 / NEXTLINK HH @ 45+33**, which is
> already the start of the RENDERED segments log48/log50 (→ flower-pot drops 5+07 / 5+14). This is a
> **data-model mismatch** (drilling-drive-segmented bore-logs vs structure-segmented plan), not a geometry
> gap. **Render eligibility: NO.** The unlock is an OWNER SEGMENTATION DECISION, not more tracing.

---

## LOG15_LOG16 CONTINUATION TRACE RESULT

- **Source chain (running-station frame; structure census projected onto the running ladder).** One
  continuous 2-1.25" fiber main, upstream→downstream:
  - sheet 6: `MATCHLINE STA 24+11/4+37/1+92 - SEE SHEET 5` (run enters from sheet 5) … `MATCHLINE 26+71 SEE
    SHEET 7`.
  - sheet 7: `SPLICE POINT 35 / NEXTLINK HH @ 28+73` (reset 28+73=0+00, on-axis perp≈5) → 191' →
    `MATCHLINE 1+93/30+64 SEE SHEET 8`.
  - sheet 8: reciprocal matchline → run continues 30+64 → 33+93 (past the unprinted **31+00**) →
    `MATCHLINE 33+93 SEE SHEET 9`. (AP-154/156/157 + flower-pot drops hang off it.)
  - sheet 9: the generic-`BORE` 2-1.25" 288ct fiber blob, interior reset 35+43=0+00, on-axis NEXTLINK @
    35+43 + 38+10 → `MATCHLINE 38+90/6+11 SEE SHEET 10`. (AP-155.)
  - sheet 10: on-axis 2-1.25" main (perp≈5 at y≈420): `installer HH @ 39+79` (log16 END) → interim NEXTLINK
    HH @ **40+38 → 43+36 → 44+08** → `installer HH @ 44+83` (= log49 start, 914,420) → **SPLICE POINT 46 /
    NEXTLINK HH @ 45+33** (941,353; = log49 end / log48 start). Then the frame resets (45+33=0+00) and the
    fiber continues as the RENDERED log48/log50 to flower-pot terminals (5+07 / 5+14).

- **Start terminus.** **NOT source-clear within scope.** log15's recorded start 24+07 coincides with
  `MATCHLINE 24+11 - SEE SHEET 5` → the backbone continues upstream onto sheet 5+. The nearest on-axis
  splice is `SPLICE 35 NEXTLINK HH @ 28+73` (interior to log15). The true head-end is further upstream
  (sheet 5 and earlier — unmeasured; out of this trace's scope).

- **Interior segmentation points (NOT endpoints).** **31+00** (unprinted ruler-cut, log15 end == log16
  start; nearest structure 209 pt). Also the matchline cuts 30+64, 33+93, 38+90 and the interior resets
  28+73 (SPLICE 35) and 35+43. None is a run terminus; the conduit is continuous through every one.

- **Matchlines crossed.** 24+11 (→ s5), 26+71 (s6↔s7), 30+64 (s7↔s8), 33+93 (s8↔s9), 38+90 (s9↔s10).
  Five sheet boundaries; the run is continuous across all of them.

- **Sheet-9 BORE blob role.** The MIDDLE leg only (33+93 → 38+90) of the cross-sheet run; the 2-1.25"
  288ct fiber main is drawn on the generic-`BORE` layer just on this dense sheet (the sprawl wall). NOT a
  standalone run — endpoints are on sheets 8 and 10.

- **39+79 role.** A **printed installer HH** (binds uniquely, 188,422) — log16's recorded END and a genuine
  structure (13"X24"X24" HH, 2-1.25" HDPE). BUT it is an **interim handhole on a continuing main**: printed
  `40+00` + `169'` and three more on-axis NEXTLINK HHs (40+38/43+36/44+08) lie downstream of it. So 39+79
  is a valid drive-segment end, NOT a backbone terminus.

- **Downstream continuation after 39+79.** Continuous on-axis 2-1.25" main: 39+79 → 40+38 → 43+36 → 44+08 →
  44+83 (log49 start) → **45+33 SPLICE 46** → (reset) → log48/log50 → flower pots 5+07 / 5+14 (ALREADY
  RENDERED). The geometric BASE_CONDUIT flood from 39+79 sprawls (122 segs / 1478 endpoints, furthest dash
  ~46+81) — confirming continuity, useless for a unique terminus (expected sprawl).

- **Candidate true terminus (downstream).** The next **printed splice** structure is `SPLICE 46 / NEXTLINK
  HH @ 45+33` — but it is already the boundary of the rendered log48/log50. The eventual physical termini
  are the flower-pot drops (5+07/5+14, rendered). NO terminus uniquely belongs to log16: it is interior.

- **Unique candidate:** **NO.** The run has no unique standalone terminus pair. Printed anchors on the
  segment — SPLICE 35 (28+73), installer HH (39+79), SPLICE 46 (45+33) — do not pair to match either
  bore-log's recorded span (28+73→39+79 = 1106'; 28+73→45+33 = 1660'; neither = log15's 693' nor log16's
  879'), because the bore-log spans are DRILLING-DRIVE boundaries that fall at unprinted interior points.

- **Closure.** Not achievable to a unique structure pair. log16's 879' would close only if the start were
  positioned by footage 879' back from 39+79 along the cross-sheet alignment — but that start (31+00) is an
  unprinted interior point, so the stroke's START would be a **ruler-cut on a through-alignment**, which the
  station-corridor `end_is_drawn_terminus` law REJECTS (the drop/overtrace false positive, mirrored to the
  start).

- **Rejection gates.** `ENDPOINT_IDENTITY` (start UNPRINTED) for log16; `END_IS_NOT_A_DRAWN_TERMINUS` /
  ruler-cut-on-through-alignment for any footage-positioned interior start; upstream `MISSING_SOURCE`
  (24+07 continues to sheet 5+). DO-NOT-WIDEN forbids anchoring a redline to an interior footage point on a
  continuous spliced main.

- **Render eligibility:** **NO.** Neither log15, log16, nor the combined run is renderable as a clean
  structure-to-structure redline within the traced sheets.

- **If no render — exact missing source.** An **OWNER SEGMENTATION DECISION**, because this is a data-model
  mismatch, not a geometry gap. The bore-logs are drilling drives; the plan segments by structure. Options
  for the owner:
  1. **Re-segment to printed structures** — render the splice-to-splice / splice-to-HH backbone (e.g.
     SPLICE 35 @ 28+73 → installer HH @ 39+79, or → SPLICE 46 @ 45+33). Clean anchors, but the stroke spans
     multiple bore-logs and overlaps the rendered log48/log50 at the downstream splice — a re-mapping of
     bore-log → redline the owner must authorize.
  2. **Authorize footage-positioned drive boundaries** — accept log16 drawn from its 31+00 start positioned
     879' back from the 39+79 HH along the cross-sheet alignment (and log15 likewise). This requires owner
     sign-off that an interior, non-structure drive-junction may anchor a stroke (it currently trips the
     ruler-cut rejection gate). High DO-NOT-WIDEN risk; not auto-safe.
  3. **Provide the upstream head-end** — the sheet-5+ terminus identity so the *combined* backbone can be
     bounded upstream; the downstream still resolves into the rendered log48/log50.

- **Contact sheet needed:** **YES** — generated (see Files): the owner needs to see the one printed end
  (39+79), the continuing main + SPLICE 46, and the unprinted 31+00 / sheet-5 upstream cut to choose a
  segmentation option. This is the stop point.

- **Files changed.** None tracked. New untracked scratch: `truelinev2/proof/run_log15_log16_continuation_trace.py`,
  `truelinev2/proof/run_log15_log16_continuation_contact.py` (contact sheet), this packet, and gitignored
  JSON/PNG under `data/outputs/log15_log16_continuation/`.

- **Commit.** **NONE.** **Push.** **NONE.**

- **Recommendation.**
  1. **Stop at the contact sheet** and get the owner segmentation decision (option 1 / 2 / 3 above) — the
     terminus is not source-determinable without it; more tracing will not change that.
  2. **Bank the resolved facts:** log15's owner-named continuation (`33+93 → SEE SHEET 9`) is fully traced —
     it runs through the sheet-9 fiber blob to the sheet-10 installer HH @ 39+79 and continues to SPLICE 46.
     log16's END (39+79) is confirmed a printed installer HH. The remaining gap is purely segmentation, not
     geometry.
  3. **Recommended owner option = #1 (re-segment to printed structures)** — it is the only DO-NOT-WIDEN-safe
     path (both anchors printed). It requires owner authorization to re-map the drilling-drive bore-logs
     (log15/log16) onto structure-bounded strokes and to accept the overlap handling at SPLICE 46 with the
     rendered log48/log50. Hold rendering until that authorization.

---

## Guardrails honored
Read-only. No render, no stroke/card/PNG-as-redline, no AUTO. No BORE→BASE_CONDUIT, no MAX_DASH_GAP /
budget / tolerance change, no corpus mutation, no census rebaseline, no flag, no deploy, no `origin/main`,
no backend/web/runtime touch, no unrelated-file cleanup, no junction_bridge build, 31+00 never treated as
an endpoint. Reversible (untracked probes + this packet; gitignored JSON/PNG).
