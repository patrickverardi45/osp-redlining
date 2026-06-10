# M8.2i — reset-vs-continuous collision doctrine + human grading packet

**Status:** doctrine + human grading packet only. **No code, no behavior, no wiring.** This is a
markdown document; it changes no engine / `decide.py` / `run_match` / `transition_classifier`,
adds no tests, and references the already-shipped M8.2h read-only artifacts. Default remains
**23/58**, M8.2d **NOT_SAFE**, M8.2f **NEEDS_MORE_EVIDENCE**, M8.2g **all needs_manual_review**,
M8.2h **unchanged**. Frame translation stays **INACTIVE**. No activation.

## Why this packet exists

M8.2h refuted the M8.2g "different matchline" hypothesis: for all three unresolved transitions
the competing matchline equation **references the bore's crossing station and sits at the
crossing box**. So these are genuine **on-crossing reset-vs-continuous collisions** — two strong,
authored signals that imply *opposite* physical interpretations of the same crossing. No textual
or geometric rule can decide them safely; a human must grade them. This packet gives Patrick the
doctrine and a per-case grading card so the decision is fast, explicit, and recorded.

---

## Doctrine — the nine questions

### 1. What does an "exact continuous box match" prove?
That the authored callout boxes on the chained sheets, read in their **printed (raw) stationing**,
(a) sum to the bore's total footage and (b) align end-to-start within tolerance (footage/start/end
deltas ≈ 0). It proves the bore's footage and span are **consistently represented by a continuous
chain of authored boxes in raw-station space**. It does **NOT** prove the physical route is
continuous across the matchline — equal raw stations on two sheets can be the same point
(continuous) *or* two different points whose numbers coincide because of a frame reset.

### 2. What does an "on-crossing reset equation" prove?
That the plan **authored a matchline frame equation at the bore's crossing station** (the equation
references the crossing station and is drawn next to the crossing box). It proves the two sheets'
frames are declared **offset at that matchline** (e.g. log42 `s1 2+70 = s2 5+16`, offset 246 ft).
It does **NOT** prove that *this* bore resets there — a matchline can carry equations for the
corridor/other routes while a given bore runs straight across it.

### 3. When those conflict, why is auto-placement unsafe?
Because the two signals demand **opposite placements of the same downstream segment**:
- the exact box match says *continue at the same raw station* (continuous link);
- the on-crossing reset of `N` ft says *equal raw stations are NOT the same physical point* → the
  downstream segment must be **translated by N ft**.

Pick "reset" blindly and you **break every genuinely continuous run** (this is exactly the M8.2d
regression: 23→15, 8 placed logs lost). Pick "continuous" blindly and you **silently accept a real
reset as continuous**, mis-placing the downstream segment by the offset (a false placement). Either
fixed rule is wrong for some real cases, so **honest abstain is the only zero-false option** until a
per-case decision exists.

### 4. What visual/manual evidence decides the winner?
Open the plan at the crossing box (M8.2h crops) and read:
- **drawn route geometry:** does the bore/conduit line cross the matchline **unbroken** (continuous),
  or does the route **end/turn/reset** at the matchline?
- **station-pair fit:** does the equation's *other-frame* value reconcile **this bore's** downstream
  box? (Translate the downstream box by the offset — does it land on the authored box?)
- **structures at the crossing:** HH / flower pot / access / splice labels — do they terminate or
  carry the route through?
- **SEE-SHEET target:** does the equation's referenced sheet match the sheet the bore actually
  continues onto?

### 5. What evidence would confirm `continuous_station`?
The drawn route crosses the matchline **unbroken**, the downstream box's start equals the upstream
box's end **in the same frame** (boxes authored continuously), **and** the on-crossing equation
pertains to a **different route/conduit** at that matchline (its station pair does **not** reconcile
this bore). The equation exists but is not on this bore's path.

### 6. What evidence would confirm `reset_equation`?
Translating the downstream box through the equation's offset **lands on the authored continuation**
(the reset reconciles the bore), the drawn route **resets/cranks** at the matchline, and the raw
station equality was **coincidental**. I.e. the equation's station pair matches this bore's crossing.

### 7. What evidence requires abstain / manual review?
Illegible or ambiguous drawn geometry; an equation that could plausibly apply to this bore **or** a
parallel route; multiple matchlines/equations coinciding at the crossing; or the **two sides of one
equation disagreeing** (precision conflict, log57). When neither continuous nor reset is decisively
supported, **abstain**.

### 8. What may the future engine rule do — ONLY after proof?
Only after a per-case human grade (or a validated, evidence-based localization rule) may the engine:
**localize** a reset edge to a bore's *actual* crossing (match the equation's station pair to the
bore's box stations), then **translate** a confirmed-reset downstream segment through the safe edge,
and **keep the raw link** for a confirmed-continuous crossing. And only if it is:
- **flag-gated, default-OFF, reversible**, and
- proven by a full **M8.2d re-validation showing ZERO regression** of the 23 current placements and
  **zero new false placements**.

### 9. What must NEVER happen
- **Never blindly prefer reset equations** — it regresses continuous runs (the M8.2d failure).
- **Never blindly prefer exact box continuity** — it silently accepts a real reset and mis-places by
  the offset.
- **Never activate frame translation if it regresses any of the 23 default placements.**
- **Never force a green/auto result from ambiguous evidence** — abstain instead.
- (Corollaries) Never edit `decide.py` / default `run_match` / change placement behavior without a
  proven, zero-regression, flag-gated activation; never merge/deploy without that proof.

---

## Human grading packet

Source of truth for coordinates/crops: M8.2h report `data/outputs/transition_visual_targets.{md,json}`
and crops `data/outputs/m8_2h_crops/` (both **gitignored**; regenerate with
`$env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_transition_visual_targets`).
All three default placements are `AUTO_SELECT` `EXACT_BOX_FOOTAGE_AND_ENDPOINTS` (deltas 0) and go
`ABSTAIN` under the naive frame opt-in. Coordinates are PDF display space `[x0,y0,x1,y1]`.

Allowed grade (pick exactly one per card):
`continuous_station_confirmed` · `reset_equation_confirmed` · `precision_conflict_manual_review` ·
`still_unknown_manual_review` · `abstain_required`

### Grading card — log42 [sheets 1, 2]
- **sheets/pages:** s2 and s1 (span 0+00→2+87, 287 ft).
- **crossing station:** `2+70` (s2 box ends 0+00→2+70 @ `[905,465,960,470]`; s1 box 2+70→2+87 @ `[82,516,137,521]`).
- **competing equation:** `STA 2+70 / 5+16` (offset **246 ft**, HIGH confidence, on s1) — references the crossing `2+70`, ~136 units from the s1 crossing box.
- **why it conflicts:** boxes sum exactly to 287 ft continuously (deltas 0), but a 246 ft reset at `2+70` means s1's `2+70` is physically s2's `5+16` — raw continuity and the reset disagree.
- **crops:** `data/outputs/m8_2h_crops/bore_log42__crossing_s1.png` (+ `__start_s2.png`, `__end_s1.png`).
- **the exact human question:** *On sheet 1 at STA 2+70, does the bore/conduit line run continuously across the matchline, or does the `2+70/5+16` equation apply to THIS bore (i.e., is its real continuation s2 5+16, not s2 2+70)?*
- **grade:** ☐ continuous_station_confirmed ☐ reset_equation_confirmed ☐ precision_conflict_manual_review ☐ still_unknown_manual_review ☐ abstain_required

### Grading card — log57 [sheets 8, 10, 13]
- **sheets/pages:** chain s10 → s13 → s8 (span 0+00→4+13, 413 ft); disputed crossing s13→s8.
- **crossing station:** `3+98` (s13 box …→3+98 @ `[284,312,339,317]`; s8 box 3+98→4+13 @ `[1027,386,1082,391]`).
- **competing equations:** `STA 3+98 / 3+08` (offset 90 ft) **and** `STA 3+93 / 3+08` (offset 85 ft) — both HIGH, **share the `3+08` side**, disagree by **5 ft** (one matchline read slightly apart, just over the 2 ft conflict tolerance).
- **why it conflicts:** the boxes sum exactly to 413 ft continuously, but the s8↔s13 matchline carries a reset (~85–90 ft); the two readings of that one matchline also disagree by 5 ft (a precision conflict, not two semantic resets).
- **crops:** `data/outputs/m8_2h_crops/bore_log57__crossing_s8.png` (+ `__start_s10.png`, `__end_s8.png`).
- **the exact human question:** *Is `3+98/3+08` vs `3+93/3+08` ONE matchline (which value is correct), and does that single reset apply to THIS bore, or does the bore run continuously across s13→s8?*
- **grade:** ☐ continuous_station_confirmed ☐ reset_equation_confirmed ☐ precision_conflict_manual_review ☐ still_unknown_manual_review ☐ abstain_required

### Grading card — log65 [sheets 9, 10]
- **sheets/pages:** s10 → s9 (span 4+51→6+50, 199 ft; a VACANT HDPE segment).
- **crossing station:** `6+11` (s10 box 4+51→6+11 @ `[110,280,165,285]`; s9 box 6+11→6+50 @ `[975,295,1030,300]`).
- **competing equation:** `STA 38+90 / 6+11` (offset **3279 ft**, HIGH on s9 / MEDIUM on s10) — references the crossing `6+11`, ~130 units from the s10 crossing box.
- **why it conflicts:** boxes sum exactly to 199 ft continuously, yet a 3279 ft reset sits at `6+11`; the offset is geometrically possible (sheets reach 4533 ft) but extreme for a 199 ft segment — likely a corridor reset that may not be this bore's.
- **crops:** `data/outputs/m8_2h_crops/bore_log65__crossing_s9.png` (+ `__start_s10.png`, `__end_s9.png`).
- **the exact human question:** *At STA 6+11, does this 199 ft VACANT segment continue straight onto s9, or does the `38+90/6+11` reset apply to it (its real continuation being s-other 38+90)?* This bore is also a known run/segment child — confirm against the parent run.
- **grade:** ☐ continuous_station_confirmed ☐ reset_equation_confirmed ☐ precision_conflict_manual_review ☐ still_unknown_manual_review ☐ abstain_required

---

## What happens after grading
- Each `continuous_station_confirmed` / `reset_equation_confirmed` becomes a labeled fixture for a
  **future, flag-gated** localization rule — which may ship **only** after an M8.2d re-validation
  proves zero regression of the 23 defaults and zero new false placements.
- Each `precision_conflict_manual_review` / `still_unknown_manual_review` / `abstain_required` stays
  ABSTAIN; the engine keeps its honest abstain (no change today).
- log11 remains separately blocked on missing anchor/box/footage evidence.
- **Nothing in this packet changes behavior.** It is decision support only.
