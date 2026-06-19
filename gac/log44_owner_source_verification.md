# log44 — Owner Source-Verification Packet

**Target:** log44 (= `bore_log17` Segment B) — the last *close* source-gated bore on the frontier (48/58).
**Status:** NOT rendered. One owner answer either unlocks a render or names the missing source.
**Visual packet:** `data/outputs/log44_owner_source_verification_packet/log44_owner_source_verification_contact.png` (+ per-panel PNGs + JSON sidecar). Helper-color overlays only — **no red TrueLine stroke drawn**.
**Builder (read-only):** `truelinev2/proof/run_log44_owner_source_verification_packet.py`

---

## The blocker (source-location conflict across 3 sheets)

The corpus records log44 as **print 18, `0+00 → 3+25` (325')**, but **sheet 18 has no matching run**
(engine-confirmed: `run_log17_family_abstain_probe` G6 → chain `0+00→3+25` = `CALLOUT_CHAIN_NONE`,
`ends_at_3+25 = 0`). The continued-31 adjudication trace points instead to a **sheet-13 Woodson Ln drop**
fed by a **sheet-10 high-station chain**. We need the owner to confirm which is real.

## Evidence (three panels)

| Panel | Sheet | What it shows |
|---|---|---|
| 1. Corpus claim | 18 | The only `0+00` runs are 3 short **E/W PORT TERMINAL TAIL** drops → AP-145 (~165'), AP-147 (~110'), AP-146 (~130'). **No `3+25`, no `3+23`, no Woodson, no 325' run.** |
| 2. Candidate | 13 | **AP-158 TERMINAL 8 PORT HH @ STA `2+45`** → **FLOWER POT @ STA `3+23`**, 1404 Woodson Ln. Both stations printed + unique. Local drop = **78'** (not 325'). |
| 3. Chain context | 10 | High-station chain **`39+79 → 43+36`** on the sheet-10 mainline; `43+36` = the adjudication-proposed upstream **cross-sheet point** that would feed the Woodson run. (The `43+36`↔sheet-13 join is **not** engine-found — owner-gated.) |

> Why 325' ≠ 78': the corpus 325' may be the **full** sheet-10-chain + sheet-13 run, or a mis-record.
> That is exactly why the START (Q2) must be owner-confirmed.

## Exact owner questions

- **Q1.** Is log44 actually the **sheet-13 Woodson Ln run** (AP-158 TERMINAL 8 PORT HH → FLOWER POT), not the corpus print-18 entry?
- **Q2.** What is the correct **START** — the sheet-10 `43+36` chain point (cross-sheet), the AP-158 terminal HH (local STA `2+45`), or a local `0+00`?
- **Q3.** Is the **END** the STA `3+23` FLOWER POT on 1404 Woodson Ln?

## Expected engine action per answer

| Answer | Engine action |
|---|---|
| **A1** — start = AP-158 terminal HH (`2+45`), end = `3+23` FLOWER POT | Render the **local sheet-13 drop** AP-158 TERMINAL 8 PORT HH → `3+23` FLOWER POT (~78'). End binds by printed AP-158 / flower-pot identity — the clean single-sheet case (**renders like log42's AP-105 terminal**). Safe once owner confirms identity; source supplies coordinates. |
| **A2** — start = sheet-10 `43+36` chain point | Assemble the **cross-sheet route** sheet10 (…→`43+36`) + SEE-SHEET → sheet13 Woodson (`2+45`→`3+23`). Render **only if** (a) the `43+36`↔sheet-13 matchline join is **source-printed** (no invented coords) **and** (b) the assembled route is **non-overlapping** with drawn bores. If the join is not printed → stays abstained pending the matchline source. |
| **A3** — corpus print 18 is correct | No 325' / `3+25` run exists on sheet 18 (engine-confirmed). Owner must point to the **actual sheet-18 run/source** (which structure, which `0+00`, the true end). Until supplied, log44 stays `END_IDENTITY_UNPRINTED` ABSTAIN — the current correct, zero-false state. |

## Posture
Render attempted: **no**. Red stroke drawn: **no** (helper colors only; the red "TrueLine" mark on the
sheet-10 crop is a source-PDF watermark, not a drawn redline). Census **frozen**; corpus / census / fixtures
**unmutated**; `origin/main` **untouched**; deploy **none**. All artifacts are untracked / gitignored.
