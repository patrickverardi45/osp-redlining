# 06 — Live Part-A Audit Findings (ground truth)

**Author:** Driven live by the agent (not predicted) — isolated local stack.
**Date:** 2026-06-27
**Method:** A fully **isolated** audit stack so the owner's pristine staging demo was never touched:
- Copied the staging product store (41 MB) → `data/outputs/truelinev2/council_audit/product_store`.
- 2nd backend `uvicorn …:8200` against the copy (shared read-only recognized-corpus registry).
- Local-base web `next dev` on `:3100` (`NEXT_PUBLIC_TL2_PRODUCT_API=1`, `_API_BASE=http://127.0.0.1:8200`, `_TENANT=staging-smoke`).
- The live supervisor-managed staging (`:8100` backend / `:3000` web / cloudflared) was left untouched.
**Rule honored:** *HTTP 200 is not proof* — I looked at the rendered stroke and drove the real click-paths. 0 console errors across every flow.

---

## What PASSED (the product's core actually works)

| Flow | Result |
|------|--------|
| **1 · Recognized deterministic** (`recognized-log9`) | Generate → **"Redline placed automatically"** with 2 real engine PNGs; **visual proof** captured (a real red dashed bore stroke + station dots on the plan sheet — `flow1-recognized-log9-stroke.png`). Closeout review renders in full; **Assemble → real `%PDF` packet (6.08 MB) + real `PK` ZIP (1.86 MB)** pulled from the backend. Billing honest ("not shown — quantities only"). |
| **3 · Ambiguous → correct → supersede** (`demo-general-upload-ambiguous`) | Honest **LOW 45%** (`MULTIPLE_PLAUSIBLE_RUNS_2`, `COMPETING_RUNS_NEAR_SCORE`). Correction panel appears; **plan raster loads** (1584×1224); marked a 3-point bore route; **Create source anchor → VALIDATED, renderable:true**; **trap verified** (Assemble *before* Render stays BLOCKED); **Render → SUPERSEDED** ("Corrected — human-confirmed placement saved"); **Assemble → "Human-corrected REVIEW redline"**, downloads enabled. Full correction loop works. |
| **5 · Export gate** (`demo-general-upload`) | Assemble before acceptance is **BLOCKED** ("still needs to be accepted… in the Review section"); all 3 downloads **disabled**; released only after Accept. No deliverable from an un-accepted redline. |
| **6 · Reload resilience** | After a full reload of an assembled job: job still selected, Overview "Redline: placed · corrected", closeout "Assembled — ready for approval", downloads still enabled. File-backed store + URL re-selection survive refresh. |
| **No-fake invariants** | Every drawn stroke red; route map shows real WGS84 geometry + an honest "street names are not invented" note; billing quantities-only; KMZ honestly pixel-only. Holding. |

---

## CONFIRMED findings (live)

| ID | Sev | Confirmed behavior |
|----|-----|--------------------|
| **A1** front door | blocker | Sidebar nav = Home / Redline Showcase / Intake only; the upload workspace is reachable **only** by typing `?workspace=1`. No in-app entry. |
| **C2** confidence overstatement | high | `demo-general-upload` (generic INFERENCE lane) shows **"High confidence · 85%"** while the *same card* states *"Why this is REVIEW, not AUTO: the engine has no source-tight per-bore evidence"* (`NO_PER_BORE_TERMINI`). Claiming HIGH while admitting no source-tight evidence is the rigged-demo overstatement. The Tier 3.2 MEDIUM cap is justified. (Contrast: the ambiguous job honestly grades LOW — so the asymmetry is about the *demo plan*, not calibration.) |
| **A3** guided dead-end | high | The guided `/intake?job=…` view has Generate/Accept but **no Assemble / closeout / download** — closeout lives only in the workspace. |
| **NEW · stale assemble error** | medium | After **Accept** in Review, the Closeout Assemble button still showed a **stale "still needs to be accepted… Go to Review"** error (left over from a prior blocked attempt). Clicking Assemble again succeeded — so accept *did* propagate server-side; the client error simply never cleared. A user who accepted would believe they are still blocked. (State-sync gap not explicitly in the council report; related to the W2/W7 class.) |

## Source-confirmed (not driven live; trusting the Technical Lead's verified source + observed gate behavior)

- **A2** (blocker) — uploaded bore log is never auto-read (`upload_pipeline.py:128` extraction permanently `queued`; `engine_ready` needs manually re-typed + confirmed + grouped rows). The curated jobs are pre-seeded engine-ready; a blank job requires manual re-entry. Confirmed in source; full blank-job Flow 4 not driven.
- **W3** (high) buried group-confirm step; **W4** (high) twin "Create project" buttons on a fresh tenant (only one shows once the tenant project exists, as observed).

## Refuted / not reproduced

- **S7 "recognized not configured"** did **NOT** reproduce — the recognized path placed real redlines (registry present). The fail-loud start guard remains good defensive practice, not an active outage.
- **Print scoping** — not driven (print dialog), but `globals.css:43-60` scopes `@media print` to `#closeout-print` in source (the council already corrected the stale qaMatrix claim). Not carried as a bug; Tier 5.3 is a CTA-prominence fix only.

---

## Net read

The master plan's headline holds **empirically**: the engine + backend are honest and the end-to-end happy paths (recognized, clean-accept, ambiguous-correct, export-gate, reload) genuinely work. The real gaps a user hits are exactly the seams the council named — **no front door (A1), bore-log manual re-entry (A2), guided dead-end (A3)** — plus two honesty items I confirmed live: **HIGH-85% on the inference lane (C2)** and the **stale assemble-error after Accept**. None require touching the deterministic 50/58 frontier; the only engine-adjacent fix is the Lane B confidence cap.
