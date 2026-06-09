# TrueLine v2 — M3 Checkpoint

**Date:** 2026-06-09
**Scope:** clean-room PDF-first product in `truelinev2/` only. Old `backend/` monolith and `web/` frontend are out of scope and unaffected.

---

## 1. Branch

`feat/truelinev2`

The same branch also carries one **web-only** commit (`1555b4b`, the closeout XSS fix) that is **not** part of the v2 product — see §2.

---

## 2. Commits

v2 product lineage (each commit is `truelinev2/`-only, zero old-app files):

| Milestone | SHA | Summary |
|---|---|---|
| M1 | `46c1ded` | `feat(truelinev2): add standalone Brenham PDF-first vertical` — convention-agnostic core + Brenham dialect; reproduces the old-engine Brenham answer with v2's own code. |
| M2 | `c2cdbfa` | `feat(truelinev2): add ODOT plan dialect (M2), legend-safe alignment-gated placement` — ODOT station-axis + point-note dialect; places a bore the old engine got 0 callouts on. |
| M3 | `c70f982` | `feat(truelinev2): ODOT CAD-layer drawn-extent placement (M3) + drift guards` — drawn directional-bore run isolated from the `E-PROPOSED-DB` CAD layer; extent match; 3 drift guards added. Supersedes the M2 point-note approach. |

Separate, **not a v2 change** (documented here only to avoid confusion):

| | SHA | Summary |
|---|---|---|
| XSS fix | `1555b4b` | `fix(web): HTML-escape closeout print packet fields` — **web-only**, touches solely `web/src/components/CloseoutPacket.tsx` (B-XSS-CLOSEOUT-1). Rides on `feat/truelinev2` because that was the checked-out branch; it does not belong to the v2 product and must not be described as v2 work. |

Nothing has been pushed.

---

## 3. Proof results

> Recorded at each milestone's ship. This session re-verified the **test suite live** (§4) but did **not** re-run the proof harnesses (they depend on locally-staged datasets; see §6/§7).

- **M1 Brenham — `-m truelinev2.proof.run_m1_brenham`:** `bore_log51` → `AUTO_SELECT`, sheet 8, `0+00 → 2+99`, **299′**. Footage grammar `STA A TO STA B` + `DIR. BORE (NNN')`. Real PNG served over HTTP, tenant-scoped + fail-closed. Reproduces the old engine's answer with v2's own pipeline.
- **M2 ODOT (point-note; superseded by M3):** 71′ bore → correct **REVIEW** at the real `VIA DIRECTIONAL BORE` note (~`19+60`, sheet 11); 118′/88′ abstained honestly; **0 false placements**.
- **M3 ODOT (CAD-layer drawn-extent) — `-m truelinev2.proof.run_m2_odot`** (the ODOT runner, updated in M3; there is no separate `run_m3`): all **3 Tulsa-31 bores place REVIEW** (118′/88′ improved up from abstain), each graded correct vs the redline PDF (redline marks `14+20` / `19+76 → 20+47` / `23+33`), **0 false placements**.
  - Mechanism: 72 CAD layers (OCGs); `get_drawings()` carries a `'layer'` key; the drawn directional-bore RUN lives on layer **`E-PROPOSED-DB`** (the obvious-named `P-PROPOSED DIRECTIONAL BORE` layer holds only the legend SAMPLE). Dialect selects bore-named layers by token pattern, keeps alignment-band segments (drops the legend sample), projects endpoints → stations, `match_mode="extent"`.
  - **Tiering today:** ODOT places **REVIEW only** — `AUTO` fires only on a *tight + unique* extent, which the current endpoint-projection does not yet achieve. ODOT AUTO is deferred (see §9).

**Standing invariant across all proofs: 0 false placements.**

---

## 4. Current tests

Verified live this session (repo root, `$env:PYTHONPATH="."`, `.\venv\Scripts\python.exe -m pytest truelinev2/tests -q`):

```
43 passed in 0.37s
```

Test files (`truelinev2/tests/`): `test_stations.py`, `test_brenham_dialect.py`, `test_match.py`, `test_isolation.py`, `test_sanitize.py`, `test_artifacts.py`, `test_borelog_brenham.py`, `test_station_axis.py`, `test_borelog_odot.py`, `test_legend.py`, `test_odot_match.py`, `test_odot_extent.py`, plus the three drift-guard files in §5.

---

## 5. Drift guards

Three structural guards keep v2 clean-room and the core convention-agnostic (all green inside the 43-test run):

1. **No old-app imports** — `proof/import_isolation.py` (standalone: `-m truelinev2.proof.import_isolation`) and `tests/test_import_isolation.py` (same check under pytest). Asserts **zero** imports of `app.*` / `main` / `redline_pdf_first` / `tl_core` / `backend`.
2. **No convention strings in core** — `tests/test_no_convention_leakage.py`. Asserts convention-specific vocabulary (e.g. `DIRECTIONAL BORE`, Brenham/ODOT grammar tokens) appears **only** in `extract/` dialects, never in the convention-agnostic core (`schema` / `match` / `render` / `store` / `api` / `normalize`).
3. **No global mutable state** — `tests/test_no_global_state.py`. Asserts no module-level mutable global state (every run is self-contained / reentrant).

---

## 6. ODOT dataset path

Defined in `truelinev2/proof/run_m2_odot.py`:

- **Source zip** (`TL2_ODOT_ZIP`, default): `C:\Users\Patrick\OneDrive\Attachments\Desktop\ODOT_TULSA_29 (11-11-25) (1).zip` — note the zip is *named* Tulsa 29 but supplies the **Tulsa 31** plan/redline/bores.
- **Extracted inputs dir:** `C:\Temp\truelinev2_m2\inputs` (auto-extracted from the zip if the files are absent).
- **Grading output:** `C:\Temp\truelinev2_m2\grading`
- **Report output:** `<repo>/data/outputs/truelinev2`
- **Plan PDF:** `ODOT_TULSA_31 (11-12-25) (1).pdf`
- **Redline PDF (grading ground truth):** `ODOT_TULSA_31_REDLINE_3-18-26.pdf`
- **Bore logs:** `3-21-26 TULSA 31 BORE LOG 118'.xlsx`, `… 71'.xlsx`, `… 88'.xlsx`

Only **Tulsa 31** is staged locally. Tulsa 29/30/32 and Creek 27 VeroFy logs are **not present locally** — this gates M4 statistical scale (§9).

Derived offset for ODOT = **0** (from matchline-token consensus in `extract/sheet_map.py`), not hardcoded.

---

## 7. Brenham dataset notes

Defined in `truelinev2/proof/run_m1_brenham.py`:

- **Bore log:** `C:\Users\Patrick\OneDrive\Attachments\Desktop\excel bore logs\bore_log51.xlsx`
- **Plan PDF:** `<repo>/data/uploads/Brenham_Tx/NEXTLINK - Brenham - Phase 5_07-15-25.pdf`
- **Report output:** `<repo>/data/outputs/truelinev2`

Notes:
- Convention = **flat-table xlsx** bore log + Brenham AutoCAD plan grammar (`STA A TO STA B` + `DIR. BORE (NNN')`).
- Plan pages are **rotation = 270** → raw `search_for` coords are mapped through `page.rotation_matrix` before `get_pixmap(clip=)` in `ingest/pdf.py` (otherwise crops land in the wrong place).
- Derived offset for Brenham = **13** (fixed), not hardcoded into the core.
- Brenham is PDF-first (its KMZ carries 0 station anchors); the plan-sheet station graph is the location truth.
- This is the M1 reference vertical — it proves v2 reproduces the *known* old-engine answer before generalizing to ODOT.

---

## 8. Current untracked working-tree state

`git status --short` before writing this checkpoint (the M1/M2/M3 commits and the web XSS fix are already in history; working tree has **no** modified tracked files):

```
?? .agents/
?? backend/tl_core/
?? gac/drop_lane_source_adjudication.md
?? gac/pdf_drill_path_frame_strategy.md
?? skills-lock.json
?? trueline-token-reduction-doctrine.md
?? wiki/RECOVERED_BASELINE_98d108a.md
```

Notes:
- **`backend/tl_core/`** is the **discarded `tl_core` wrapper experiment** (reuse-by-import), superseded by `truelinev2/`. It is **not** part of v2 — leave it alone; do not import from it or confuse it with the v2 product.
- The rest are unrelated untracked scratch/docs (`.agents/`, `gac/`, root scratch files, a recovered wiki baseline).
- Writing this checkpoint adds one new untracked file: `truelinev2/docs/checkpoints/m3-checkpoint.md`. It is **not staged**.

---

## 9. M4 options

The M4 decision (none started). Three candidate directions:

1. **ODOT AUTO via drawn-bore vector extent** *(unblocked — Tulsa 31 data in hand).* Trace the actual `E-PROPOSED-DB` run polyline (not just endpoint projection) to produce a tight, unique span so `match_mode="extent"` can fire **AUTO** on ODOT for the first time. Risk: AUTO is exactly where a false placement can sneak in (cf. the legend lesson) — every artifact must be visually graded.
2. **Statistical scale** *(blocked on data).* Run the existing M3 pipeline across ≥20 bores (Tulsa 29/30/32, Creek 27) and grade precision/recall vs each redline, holding the 0-false invariant. Needs the additional VeroFy logs staged locally — not present today.
3. **Minimal review UI** *(unblocked, lower proof-value).* A thin operator surface over the existing `review/payload.py` Match-Review payload + served PNG. Product scaffolding rather than generalization proof.

Also deferred (not M4-blocking): real JWT, persistence/perf hardening, additional dialects.

---

## 10. Exact recommended next step

**First action (no code, gates everything else): confirm with the operator whether the additional ODOT VeroFy logs — Tulsa 29 / 30 / 32 and Creek 27 — can be staged locally.**

- **If yes →** M4 = **statistical scale** (Option 2). Validate generalization breadth across ≥20 bores before adding AUTO complexity. This is the most aligned with the ALL-REDLINES / DO-NOT-WIDEN standard: prove the dialect holds on unseen ODOT packets while keeping 0 false placements.
- **If no →** M4 = **ODOT drawn-bore vector-extent tracing** (Option 1) on the Tulsa-31 data already in hand, to attempt the first ODOT AUTO without widening — each placement artifact **visually graded vs the redline** before it counts.

Do not start either branch until the data question is answered; the answer selects the branch.

---

## 11. Strict rules for the next session

1. **Clean-room is absolute.** `truelinev2/` imports only external infra (PyMuPDF, openpyxl, Pillow, pydantic, FastAPI/uvicorn, sqlite, pytest). **Zero** imports of `app.*` / `main` / `redline_pdf_first` / `tl_core` / `backend`. The old app is **spec-only**. Guards in §5 enforce this — keep them green.
2. **Old engine is frozen.** No architecture or new-feature investment in `backend/` unless a near-term pilot deadline explicitly forces it. The old engine stays as a Brenham-style fallback/demo.
3. **Convention stays in the seam.** Only `extract/` dialects may know about Brenham/ODOT specifics. The core (`schema`/`match`/`render`/`store`/`api`/`normalize`) must stay convention-agnostic — a new convention is a new dialect, not an engine fork. (Guard #2 fails the build otherwise.)
4. **0 false placements is the invariant.** Honest REVIEW/abstain beats a guess. Never widen to place a wrong redline.
5. **Always view + grade every placement artifact vs the redline.** The ODOT legend false-positive passed all automated checks and was caught **only** by visual grading. Automated green is necessary, not sufficient.
6. **Offsets are derived, never hardcoded into core** (Brenham = 13 fixed; ODOT = 0 from matchline consensus).
7. **Environment:** run from repo root with `$env:PYTHONPATH="."`; use the **repo-root venv** `.\venv\Scripts\python.exe` (3.11.9). `backend\venv` is a broken trap — do not use it.
8. **Keep commits `truelinev2/`-only.** Never mix `web/` / `backend/` / `wiki/` / `gac/` / `data/` changes into a v2 commit. (The `1555b4b` web XSS fix is the cautionary example of an unrelated change that merely shares this branch.)
9. **Do not touch `backend/tl_core/`** — discarded wrapper experiment, not part of v2.
10. **Production is untouched.** No Render/Vercel flag changes, no deploys, from v2 work. Nothing is pushed.
