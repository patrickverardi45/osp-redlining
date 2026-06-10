# M8.2j — reset-vs-continuous collision: human grading ledger

**Status:** evidence-intake ledger ONLY. **No engine / `decide.py` / `run_match` / classifier
change; no behavior; no activation.** This records Patrick's human grades for the three M8.2h
on-crossing reset-vs-continuous collisions so they exist as evidence *before* any future engine
rule. Default remains **23/58**, M8.2d **NOT_SAFE**, M8.2f **NEEDS_MORE_EVIDENCE**, M8.2g/M8.2h
**unchanged**. Doctrine: [m8-2i-reset-vs-continuous-collision-doctrine.md](../milestones/m8-2i-reset-vs-continuous-collision-doctrine.md).

> ⚠️ **DO NOT use any grade here for auto-placement** until a future flag-gated rule passes an
> M8.2d re-validation proving **ZERO regression** of the 23 default placements and **zero new
> false placements**. A recorded grade is human evidence, not an engine decision.

## How to use this ledger
1. Open the crop(s) for a target (regenerate with
   `$env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_transition_visual_targets`
   — crops land under the gitignored `data/outputs/m8_2h_crops/`).
2. Answer the **exact human question** for that target.
3. Record the grade in **`m8-2j-reset-collision-human-grades.json`** (the machine-checked source of
   truth): set `grade` + fill `reviewer`, `date`, `rationale`, `confidence`. Mirror it in the card
   below if you like. **A grade without all four provenance fields is INVALID.**
4. Validate completeness (read-only, never touches placement):
   `$env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_reset_collision_grade_report`

**Allowed grades:** `continuous_station_confirmed` · `reset_equation_confirmed` ·
`precision_conflict_manual_review` · `still_unknown_manual_review` · `abstain_required`
(default `ungraded`).

---

## Target 1 — log42 [sheets 1, 2]
- **crossing station:** `2+70`
- **competing equation:** `STA 2+70/5+16` (offset 246 ft, HIGH, on s1)
- **crops:** `data/outputs/m8_2h_crops/bore_log42__crossing_s1.png` · `__start_s2.png` · `__end_s1.png`
- **exact human question:** *On sheet 1 at STA 2+70, does the bore/conduit line run continuously across the matchline, or does the `2+70/5+16` equation apply to THIS bore (is its real continuation s2 5+16, not s2 2+70)?*
- **evidence summary:** exact continuous box match (270'+17'=287', deltas 0); a HIGH on-crossing matchline equation (offset 246 ft) referencing `2+70`, ~136 units from the s1 crossing box.

| field | value |
|---|---|
| grade | `ungraded` |
| reviewer | _(unfilled)_ |
| date | _(unfilled)_ |
| rationale | _(unfilled)_ |
| confidence | _(unfilled)_ |

## Target 2 — log57 [sheets 8, 10, 13]
- **crossing station:** `3+98`
- **competing equations:** `STA 3+98/3+08` (90 ft) and `STA 3+93/3+08` (85 ft) — both HIGH, share `3+08`, 5 ft apart
- **crops:** `data/outputs/m8_2h_crops/bore_log57__crossing_s8.png` · `__start_s10.png` · `__end_s8.png`
- **exact human question:** *Are `3+98/3+08` vs `3+93/3+08` ONE matchline (which value is correct), and does that single reset apply to THIS bore, or does the bore run continuously across s13→s8?*
- **evidence summary:** exact continuous box match (413', deltas 0); two HIGH equations sharing `3+08`, disagreeing 5 ft → one matchline read slightly apart (precision spread over the 2 ft tolerance), reset ~85–90 ft.

| field | value |
|---|---|
| grade | `ungraded` |
| reviewer | _(unfilled)_ |
| date | _(unfilled)_ |
| rationale | _(unfilled)_ |
| confidence | _(unfilled)_ |

## Target 3 — log65 [sheets 9, 10]
- **crossing station:** `6+11`
- **competing equation:** `STA 38+90/6+11` (offset 3279 ft, HIGH on s9 / MEDIUM on s10)
- **crops:** `data/outputs/m8_2h_crops/bore_log65__crossing_s9.png` · `__start_s10.png` · `__end_s9.png`
- **exact human question:** *At STA 6+11, does this 199 ft VACANT segment continue straight onto s9, or does the `38+90/6+11` reset apply to it (its real continuation being s-other 38+90)? Confirm against the parent run (log65 is a run/segment child).*
- **evidence summary:** exact continuous box match (160'+39'=199', deltas 0); a HIGH/MEDIUM on-crossing equation (offset 3279 ft) referencing `6+11`, ~130 units from the s10 crossing box; offset geometrically possible (sheets reach 4533 ft) but extreme for a 199 ft segment.

| field | value |
|---|---|
| grade | `ungraded` |
| reviewer | _(unfilled)_ |
| date | _(unfilled)_ |
| rationale | _(unfilled)_ |
| confidence | _(unfilled)_ |

---

## Current state
All three targets are **`ungraded`** → the validation report verdict is **`HUMAN_GRADING_REQUIRED`**.
No target is "resolved"; nothing here is product-ready or wired into placement. Grades become useful
only as labeled fixtures for a future, separately-proven, flag-gated rule.
