# 00 — FieldRoute (TrueLine v2) Master Plan

**Author:** Technical Lead (final synthesis + tradeoff authority)
**Date:** 2026-06-27
**Branch:** `feat/truelinev2` (backend HEAD `9ee706a`); web repo `trueline-web-experience` (separate, mock-free product mode)
**Reconciles:** `01_council_report.md`, `02_public_web_research_corpus.md`, `03_v1_mirror_plan.md`, `04_engine_behavior_spec.md`, `05_owner_smoke_script.md`
**Status of this document:** the single source of truth for sequencing and tradeoffs. Where the council members disagreed, this plan makes the call and says why. Where a static audit predicted something, this plan marks it as a *prediction* and routes it to the live Part-A checklist at the end.

---

## 1. Mission (one paragraph) and success definition

**Mission.** Make FieldRoute work like the v1 monolith — one job, one page, upload → redlines → review/correct → closeout → print/save/export — powered by the *safer* v2 engine, with zero fake outputs. The v2 engine and backend are already honest and solid (the deterministic 50/58 frontier is provably isolated, confidence is earned, the export gate is unified, the closeout backend is more honest than v1). The product fails only at the **seams a real user touches**: there is no front door to the upload workspace, an uploaded bore log secretly requires manual re-entry before the engine will run, and the guided demo dead-ends before closeout. The work is therefore overwhelmingly **frontend + ops glue plus a small set of honesty fixes in the generic (Lane B) adapter and gitignored artifacts** — not engine surgery.

**Success definition (the bar everything is graded against).** A first-time user — Patrick, Hector, or a customer — given only the running app URL and *no verbal instructions*, can: (1) create/select a job; (2) upload plan PDF + KMZ/KML + bore logs + photos; (3) see route/map/project context; (4) generate redline candidates; (5) review OR correct a placement; (6) land on one clean closeout review page; (7) print/save/download the closeout PDF + ZIP. **"HTTP 200 is not proof."** A step passes only when a real human reaches the expected result without being told where to click, and no output is faked (no fake AUTO/FINAL, no fake confidence, no fake map geometry/street names, no invented coordinates, no fake billing dollars, no hidden uncertainty).

---

## 2. Reconciliation — conflicts resolved, side quests killed

The five council members are **strongly aligned** on the diagnosis. The single recurring theme across the Council Report (A1), the V1 Mirror Plan (§0), and the Owner Smoke Script (Flow 4 step 1) is the same: **the upload workspace has no front door.** I treat that agreement as high-confidence. The conflicts that remain are about *tiering* and *honesty mechanism*, resolved below.

### 2.1 Final tradeoff calls

| # | Question the council split on | Final call (Technical Lead) | Why |
|---|---|---|---|
| T1 | Is the front door the #1 priority, or is staging reliability? | **Staging reliability is "step 0" (must be green to test at all), but it is a 2-line config guard, not a project.** The front door is the #1 *product* fix. Do the staging guard (S7) and the front door (A1) in the **same first pass** — neither blocks the other. | The demo can't run if staging is down (Council §f.1), but S7 is one fail-loud check + a precheck line. The front door is the gate to *every* other validation. Both are cheap and safe-now; sequence them together. |
| T2 | Bore-log OCR/extraction (A2): build it now, or label-and-defer? | **DEFER the extractor; ship the honesty + UX framing now.** Make the manual gate unmistakable (de-bury the group step W3, fix the `engineReady===null` loop W2, label the upload "stored, not auto-read"). Real OCR/xlsx extraction is owner-approval, **after** the workflow is proven end-to-end. | This is the biggest "works like v1" gap, but building an extractor before the workflow is walkable is polishing an unreachable feature. The honest framing makes the manual path *completable today* (Smoke Flow 4 proves it). Faking extracted rows is forbidden. |
| T3 | Generic Lane B HIGH (C2/G2): hard-cap at MEDIUM, require corroboration, or relabel? | **Hard-cap Lane B at MEDIUM, gated behind a regression test (G7).** Option (a) from both the Council Report and Engine Spec. | Verified live: `_confidence:391-397` awards HIGH at `conf>=0.72` and only demotes on a strict predicate a contrived clean plan *can* satisfy. Lane B is an *inference with no annotation evidence that the run IS the bore* — it must never claim HIGH to a customer. A cap is the smallest, most honest, least-ambiguous change; the test locks it. Requiring "corroboration before HIGH" is more code and more magic constants (G6) for a band that should not exist in an inference lane anyway. |
| T4 | Named-REVIEW vs generic-LOW confidence asymmetry (C3/G3): emit a band for named REVIEW, or suppress the generic band in the UI? | **UI-suppress the generic band where it invites a misleading comparison (safe-now), and document the asymmetry.** Emitting a qualitative band for named REVIEW is engine-adjacent and owner-approval — defer it. | The dishonest *effect* (a weaker generic LOW reading as "more analyzed" than a stronger named drawn-extent REVIEW) is fixed entirely on the read side with no engine touch. The engine-side symmetry fix is a nicety, not a blocker. |
| T5 | Approve/Lock/Close sign-off (D2): wire it now, or honestly label "deferred"? | **Honestly label it now ("Sign-off requires sign-in — coming with accounts"); do NOT dead-end silently. Wiring the real Approve action is owner-approval.** | The backend supports it (`closeout_review.py:364-436`), but the gate takes `actor_role`/`authorized_roles` and the product's auth (P5) is explicitly PAUSED. Wiring a role-gated action with no real identity is half-fake. The honest dead-end-killer (a clear "coming with accounts" message + a complete READY_FOR_APPROVAL state) ships now; the real action lands with auth. This keeps the no-fake rule intact. |
| T6 | Field photos in closeout (D1): add a photo section, or remove PHOTO from the summary? | **Remove PHOTO from the closeout summary now (stop promising evidence we omit); add the real photo-evidence block later (owner-approval, with the deliverable-section change).** | The review currently lists "Photos ✓/✗" but no photo ever reaches the on-screen review or PDF — that is a hidden-omission honesty violation. Removing the promise is a safe-now frontend fix; adding a real embedded-thumbnail section to `closeout_pdf.py` is a new deliverable section (owner call) and is sequenced after the core workflow. |
| T7 | Legacy `/closeout` + `/packet` mock routes (D5): hide or delete? | **HIDE/badge as mock now (confirm out of product nav); deletion is a separate owner decision, not in the do-now tier.** | They are already out of `NAV` (verified `Sidebar.tsx:17-21`). The cheap regression-free win is guaranteeing they never appear in product nav and badging them. Deleting the original contract-first dashboard is higher-risk and outside the v1-mirror critical path. |

### 2.2 Side quests KILLED (do not do these now)

- **"We need more real-world examples / a second corpus before we can proceed."** KILLED. The evidence base is already in hand: the public web research corpus (`02_…`, 21 fetched sources, 17 patterns), the v1 corpora (`v1-*.png` + the legacy app), and the v2 ODOT corpus. G6 (constants validated on one corpus) is a *provisional-marker + regression-test* task, **not** a research blocker. A second corpus improves *calibration confidence*; it does not gate shipping the honest LOW the engine already produces. Mark the constants provisional, lock the behavior with a test (G7), move on.
- **Polishing UI before the workflow is proven end-to-end.** KILLED as a priority inversion. The mandated order is: **test the workflow (Part A live smoke) → fix what blocks it → then polish.** UI simplification (Council §f.6: id-input removal, enum labels, codes-behind-diagnostics) is real and safe-now, but it is **Tier 6**, after the front door, the discoverability/loop fixes, and the placement-honesty fixes that the smoke script actually trips on.
- **Always-on Windows-Service staging (S2).** KILLED for now. The logon-bound, self-healing supervisor (verified auto-heal in ~4s) is acceptable for the owner-demo cadence. A SYSTEM-principal service is a larger, higher-risk ops change — separate owner-approved task, not in this plan's do-now tier.
- **Tiled basemap / street labels / geotagged photos / billing dollars (Council §f.7).** KILLED as do-now. All are honesty-bound "last" items; none are on the "works like v1" critical path and each risks a no-fake violation if rushed. Defer wholesale.
- **Building the synthetic test-plan generator (corpus §4) as a deliverable.** DEFERRED. The G7 regression test (lock the ODOT bores at LOW + no-real-plan-HIGH) is in-scope and small; the full R1–R10 synthetic generator is a nice-to-have that can feed the REVIEW/test lane later. Do the targeted regression test, not the generator framework.

### 2.3 One audit prediction corrected (verified, not guessed)

The QA-matrix prediction that "Print/Save leaks the whole page (no `@media print` scoping)" is **false against the live code**: `globals.css:43-60` scopes `@media print` to `#closeout-print` and hides diagnostics (independently confirmed by the Council Report and the V1 Mirror Plan). It is **not** carried as a finding. The Owner Smoke Script still lists it as a RED FLAG to *check* at Flow 1 step 8 — that is correct as a live verification, but the static expectation is that it passes. Print demotion (D4) is still worth doing (the on-screen review is thinner than the PDF), but it is a CTA-prominence fix, not a scoping bug.

---

## 3. The prioritized, sequenced implementation roadmap

**Risk tiers:** **safe-now** = frontend-only, gitignored artifacts, docs, tests, or ops config — no engine/renderer/fixture/coordinate/backend-truth-path/`origin-main`/deploy touch. **owner-approval** = engine-adjacent (Lane B adapter), new deliverable section, backend record/contract-adjacent, or an ops change with blast radius. **forbidden** = listed in §4; never in a do-now tier.

**Sequencing rule (mandated):** Tier 0 and Tier 1 make the workflow *runnable and reachable*. Tier 2 runs the **live Part-A smoke** (§5) — **do not proceed to polish until the smoke has been run and its findings reconciled**. Tiers 3–7 fix what the smoke trips on, in honesty-first order, ending with pure polish.

---

### Tier 0 — Staging is green (step 0; must hold before any live test)

| Step | Scope | Exact files | Risk | Proof |
|---|---|---|---|---|
| 0.1 | Make `TL2_RECOGNIZED_CORPUS_REGISTRY` a fail-loud precondition at backend start + add to the owner precheck (guards the recognized-deterministic path and `completed-redline-showcase` against silent "not configured"). | `truelinev2/api/product_pipeline_routes.py:931-932, :1104` (read site); `staging-supervisor.ps1` (env set — add a fail-loud assert); owner precheck in `05_owner_smoke_script.md §0` | safe-now (ops/config) | Backend refuses to start (or logs a loud error) if the env is unset; Smoke Flow 1 step 3 / Flow 7 step 2 show real red redlines, never `RECOGNIZED_CORPUS_REGISTRY_NOT_CONFIGURED`. |
| 0.2 | Fix `seed_showcase.py` stale `PLAN_SRC` → a durable source (the recognized Brenham plan used by `seed_recognized_log9.py`). | `seed_showcase.py:27` | safe-now (gitignored seed script) | Re-seeding `completed-redline-showcase` on a clean machine returns 0, not 2 (MISSING source). |
| 0.3 | (Owner action, elevated shell) Add the At-Logon trigger via `register-staging-task.ps1`; keep the Startup VBS as belt-and-suspenders. | `register-staging-task.ps1:29-45` | owner-approval (elevated shell; pure ops) | The registered task shows an At-Logon trigger in addition to the 5-min repetition; instant recovery no longer rests solely on the un-versioned VBS. |
| — | DEFER: lower heal latency / update cloudflared (S3/S6); always-on Windows Service (S2). | — | n/a | Not now. Low priority / separate owner task. |

---

### Tier 1 — The front door + the loop-breakers (make the v1 flow reachable)

This is the heart of "works like v1." All frontend-only.

| Step | Scope | Exact files | Risk | Proof |
|---|---|---|---|---|
| 1.1 | **Add a visible front door to the upload workspace.** Add a sidebar nav item "New project" → `/intake?workspace=1`; add a Home card "Start a new project — upload your files" → `/intake?workspace=1`; rename sidebar "Intake" → "Guided demos" so the label matches the chooser it opens. | `web shell/Sidebar.tsx:17-21` (NAV); `web app/page.tsx:22-44` (DEMO_CARDS); `web app/intake/page.tsx:15` (title already "Demo workflows") | safe-now | A first-time user finds and clicks a visible "New project / upload" entry — no typed URL. (Smoke Flow 4 step 1 RED FLAG resolves.) |
| 1.2 | **Route the guided demo into closeout/export** — add a "Continue to closeout →" link from the guided card into `?workspace=1&job=<same job>`, so the guided path no longer dead-ends at Accept. | `web ProductIntake.tsx:228-237` | safe-now | Smoke Flow 7 step 1: the guided demo can reach Assemble/Download, not end at Accept. |
| 1.3 | **Fix the `engineReady===null` primary-action loop** — treat `engineReady !== true` (null or false) as "not ready" so Overview points to the bore-log gate before Generate, instead of prematurely saying "Generate the redline." | `web ProductWorkspace.tsx:387-395, :369` | safe-now | A just-uploaded bore log no longer sends the user to Generate → abstain → loop. |
| 1.4 | **De-bury the bore-log segment-group confirm step** — surface "create a group to finish" as a primary prompted action while the readiness badge is amber, not hidden inside the "Review tools & diagnostics" `<details>`. | `web ProductReviewedBoreLogGate.tsx:259-310` | safe-now | Smoke Flow 4 step 10: the user reaches `engine_ready: true` without being told to open a collapsed section. |
| 1.5 | **Disambiguate the two "Create project" buttons** — tenant button (`onCreateProject`, shown when `!projectExists`) → "Set up workspace"; per-job button (`onCreate → onCreateJob`) → keep "Create project"; placeholder → "project name". Pick ONE customer word (project). | `web ProductWorkspace.tsx:255-260, :288-293, :294-299` | safe-now | Smoke Flow 4 steps 2–3: no two identically-labeled buttons; a first-timer is not stuck on the disabled one. |
| 1.6 | **Label the upload "stored, not auto-read"** and human-label the PDF-category radios ("Plan PDF" / "Bore log"); per-file kind (or warn on two PDFs under one kind) to defuse the mis-filing trap. | `web ProductUploadPanel.tsx:31-54, :65-67, :75-84`; `web productWrites.ts:75-83` (`inferUploadKind`) | safe-now (frontend); backend mis-file heuristic is owner-approval and deferred | Smoke Flow 4 step 5: a bore-log PDF is not silently filed as a second plan; the user knows re-entry is expected. |

---

### Tier 2 — RUN THE LIVE PART-A SMOKE (gate: do not polish past here until done)

| Step | Scope | Exact files | Risk | Proof |
|---|---|---|---|---|
| 2.1 | **Owner (or operator) runs all 7 flows of `05_owner_smoke_script.md` against the running stack** (staging or local), filling the red-flag log. Reconcile every RED FLAG against the predictions in this plan: confirmed → it stays a finding; refuted → strike it. | `truelinev2/docs/council/05_owner_smoke_script.md`; this plan §5 | safe-now (read-only against the product) | A completed red-flag log + a checked owner sign-off list (Flows 1–7). This is the empirical truth that supersedes every static prediction. |

> **This is the mandated gate.** The static audits are *predictions*; §5 lists what the live run must confirm or refute. Tiers 3–7 below are scoped from those predictions — adjust them to what the live run actually shows.

---

### Tier 3 — Placement correctness + honest confidence (kill the banked dishonesty)

> Engine note: the deterministic 50/58 frontier is provably isolated (generic dialect never in `_DIALECTS`; fires only after named dialects decline — verified). **None of these touch the deterministic path.** Severity is about *honesty of what the user is shown*.

| Step | Scope | Exact files | Risk | Proof |
|---|---|---|---|---|
| 3.1 | **Regenerate or delete the stale HIGH 0.73 proof artifacts.** Verified live: `generic_adapter_probe/report.json` records `"placement confidence HIGH (0.73)"` for the 71' bore — banked dishonesty that contradicts the honest LOW the current code produces. Also `seed_general_upload_local_smoke` / `general_upload_e2e`. Update any START_HERE/doc asserting old HIGH/MEDIUM. | `data/outputs/truelinev2/generic_adapter_probe/report.json:14-18, :31-34` (verified `HIGH (0.73)`) | safe-now (gitignored data/output, NOT engine; do NOT touch the frontier) | The checked-in proof reflects current honest LOW output; no reader believes the generic lane earns HIGH on a real plan. |
| 3.2 | **Hard-cap Lane B (generic INFERENCE) at MEDIUM, gated behind the G7 regression test.** Verified live: `_confidence:391-397` lets a contrived clean single-run plan reach `band=HIGH` (conf capped 0.85). Cap to MEDIUM regardless of signals. | `truelinev2/contracts/uploaded_corpus_engine_handoff.py:391-397`; `_GENERIC_HIGH_COVER:189` | owner-approval (Lane B adapter, NOT the 50/58 path; test-gated) | A synthesized clean-single-bore plan can no longer show HIGH; the regression test (3.4) asserts no real-plan bore reaches HIGH. The deterministic ODOT/Brenham renders stay byte-identical. |
| 3.3 | **Correct the generic-lane docstrings; wire or remove `_cap_review`.** Verified live: `:415-417` still claims the generic dialect "runs through the SAME `run_match` + `decide_by_extent`," but the live path calls `_place_generic` and constructs REVIEW directly. `_cap_review` (`:168-178`) is test-only. (AUTO-impossibility is real; the stated mechanism is inaccurate.) | `truelinev2/extract/generic_geometry.py:12-16`; `uploaded_corpus_engine_handoff.py:415-418, :320-324, _cap_review:168-178` | safe-now (doc/cleanup; no behavior change) | Docstrings describe the actual `_place_generic` path; `_cap_review` is either wired as a belt-and-suspenders guard or removed. No frontier change. |
| 3.4 | **Add the regression test** asserting all 3 ODOT bores stay LOW + `CORRECTION_RECOMMENDED` and **no real-plan bore reaches HIGH** (also closes 3.2's test gate). Mark the magic constants `# PROVISIONAL — validated on one corpus`. | new test under `truelinev2/tests` / proof harness; constants at `uploaded_corpus_engine_handoff.py:187-191, :235, :349, :365-389` | safe-now (test-only; provisional comment is a no-op) | Test passes on HEAD and fails if a future weight change re-inflates confidence. Synthetic fixtures (if any) feed only the REVIEW/test lane, never AUTO/FINAL, never the 50/58 fixtures. |
| 3.5 | **UI-suppress the generic confidence band** where it would invite a misleading comparison against a (band-less) named-dialect REVIEW; document the asymmetry. | `web ProductReviewCandidates.tsx` (band display); ref `uploaded_corpus_engine_handoff.py:634-635` | safe-now (UI). Emitting a qualitative band for named REVIEW is owner-approval and DEFERRED. | A generic LOW no longer reads as "more analyzed" than a named drawn-extent REVIEW. |
| — | DEFER (owner-approval, deliberate product decisions): partial-leg `PARTIAL_CROSS_SHEET_REVIEW` LOW for cross-matchline bores (C4/G4); surface "winner among N near-tied runs" in warnings (C5). | — | owner-approval | Not now. Honest abstain/keep is acceptable today. |

---

### Tier 4 — Correction flow completeness

| Step | Scope | Exact files | Risk | Proof |
|---|---|---|---|---|
| 4.1 | **Make "anchor created but not rendered → still blocked" obvious** — a SUPERSEDED record (and thus a released export gate) only happens after Render, not after Create source anchor. Add clear copy. | `web ProductSourceAnchorCapture.tsx:127-142`; ref `review_acceptance.py:56-60` | safe-now (frontend copy) | Smoke Flow 3 trap: a user who Creates an anchor but doesn't Render sees *why* Assemble is still blocked. |
| 4.2 | **Handle the validated-but-not-renderable anchor** — today `renderable:false` shows blocker codes with no recovery hint. Add a plain-English next step. | `web ProductSourceAnchorCapture.tsx:293-341` | safe-now (frontend) | Smoke Flow 3 step 5 RED FLAG resolves: a `renderable:false` result tells the user what to do. |
| — | Extending a correction path to non-LOW / named-dialect REVIEW (today only Reject → hard-blocks closeout) is frontend-led but **gate semantics need owner confirmation** — DEFER until the smoke shows it's a real blocker. | `web ProductReviewCandidates.tsx:255-258, :469`; `product_workflow.py:216-218` | owner-approval | Confirm against the live smoke first. |

---

### Tier 5 — Closeout review / print / save like v1

| Step | Scope | Exact files | Risk | Proof |
|---|---|---|---|---|
| 5.1 | **Honestly label sign-off** — replace the "approve/lock are deferred" dead-end with "Sign-off requires sign-in — coming with accounts" and a complete `READY_FOR_APPROVAL` state. Do NOT wire a role-gated Approve action while product auth is PAUSED. | `web ProductWorkspace.tsx:707`; backend ready at `closeout_review.py:364-436` | safe-now (frontend copy). Wiring the real Approve action is owner-approval, lands with auth. | The workflow no longer dead-ends silently one step before v1's "Approved for Billing"; the message is honest, not a permanently-disabled feel. |
| 5.2 | **Remove PHOTO from the closeout summary** (stop promising photo evidence the deliverable omits). | `web ProductWorkspace.tsx:76 (PHOTO accepted), :620-628 (listed in review)` | safe-now (frontend) | The on-screen review no longer shows "Photos ✓/✗" for evidence that never appears. |
| 5.3 | **Demote browser Print to a secondary text link; make "Download closeout PDF" the primary CTA.** (Print scoping is already correct — `globals.css:43-60` — so this is prominence only.) | `web ProductWorkspace.tsx:763-789, :678-681` | safe-now (frontend) | The official PDF (with itemized quantities) is the obvious deliverable; the thinner on-screen print is clearly secondary. |
| 5.4 | **Confirm legacy `/closeout` + `/packet` mock routes stay out of product nav; badge as mock if retained.** | `web app/closeout/page.tsx:39`; `web app/packet/page.tsx:10`; `web shell/Sidebar.tsx:17-21` (already not in NAV) | safe-now (frontend) | Clicking "Closeout" anywhere in product nav never lands on the fake readiness ring / mock packet. |
| 5.5 | **Add a positive completeness checklist to the clean-job review** — server-derived ✓ rows (redline placed, review accepted/recognized, bore-log engine-ready, package assembled, KMZ status, billing status) from data already fetched. Every row a real server value — no fabricated ✓. | `web ProductWorkspace.tsx:691-703` (currently gated on warnings/blockers) | safe-now (frontend) | A happy-path job shows an affirmative readiness checklist like v1, all backed by real status. |
| — | DEFER (owner-approval, new deliverable/record/backend): embedded field-photo section in `closeout_pdf.py` + review (D1, with no fake geotag); operator-notes field server-persisted + rendered (D3); "Generated &lt;date&gt;" + optional route summary in the PDF (D6, mind byte-determinism). | `closeout_pdf.py`; closeout/export record | owner-approval | Sequenced after the core workflow is proven; each is a deliverable-content change. |

---

### Tier 6 — UI simplification (hide dev plumbing the customer never types) — AFTER the workflow is proven

| Step | Scope | Exact files | Risk | Proof |
|---|---|---|---|---|
| 6.1 | Drop/auto-generate raw anchor id + reviewed-bore-log id inputs (auto-defaults already exist); drop the `(uploadId)` suffix; human-label `SegmentRelation` enums ("Separate bores" / "Segments of one run"). | `web ProductSourceAnchorCapture.tsx:209-216, :283-289`; `web ProductReviewedBoreLogGate.tsx:181-183, :298-302` | safe-now (frontend) | The correction lane a non-engineer touches has no raw ids/enums in primary copy; behavior unchanged. |
| 6.2 | Move parenthetical raw codes / status / provenance / coordinate-space / bbox into the existing "Technical details" disclosures; keep plain English in the headline. | `web ProductReviewCandidates.tsx:358-361, :374-378`; `web ProductRecognizedCorpusHandoff.tsx:187-193`; `web ProductSourceAnchorCapture.tsx:306-313, :349-357`; `web ProductRouteMap.tsx:90-94, :141-145, :161-164` | safe-now (frontend; no fake tiles/streets) | Raw codes live only inside disclosures; the map states its no-basemap caveat once. |
| 6.3 | Replace the `window.prompt()` reject-reason with the inline-reason input pattern already used in `ProductReviewCandidates.tsx:449-460`. | `web ProductReviewedBoreLogGate.tsx:122-126` | safe-now (frontend) | Rejection capture is consistent and in-app; no native modal. |
| 6.4 | **Delete the two dead components** `ProductArtifactGallery.tsx` and `ProductJobStatusStrip.tsx` (the latter leaks a Billing dollars field), then remove `NEXT_PUBLIC_TL2_JOB_ID` once a final grep confirms zero references. | `web ProductArtifactGallery.tsx:43`; `web ProductJobStatusStrip.tsx:32, :71-75`; `web liveV2Product.ts:44` | safe-now (frontend; zero runtime references) | No future contributor can re-mount a billing-dollars/single-job panel that violates the no-fake-billing stance. |
| 6.5 | **Resolve `?section=` deep-link** — either honor it on mount (`coerceSection` + `scrollToSection`, recommended, v1-faithful) or stop writing it. The doc comment currently lies. | `web workspaceSections.ts:30-33 (unused coerceSection), :36-41 (workspaceHref)`; `web ProductWorkspace.tsx:101-104` | safe-now (frontend) | Reload/share of `…&section=closeout` lands at the section, or the URL stops promising what it doesn't do. |
| 6.6 | **Persist/rehydrate the last path verdict/blockers across reload** so an ABSTAIN reason isn't lost on refresh. | `web ProductWorkflowPanel.tsx:96-132` | safe-now (frontend) | Smoke Flow 6: the abstain reason survives a reload (or is honestly re-derivable). |

---

### Tier 7 — Optional / honesty-bound extras (LAST; only on owner request)

| Step | Scope | Risk |
|---|---|---|
| 7.1 | Embedded field-photo thumbnails in PDF + review (no fake geotag). | owner-approval |
| 7.2 | Real bore-log extraction (OCR/xlsx parse) so uploads feed the engine — **never fake rows** (the T2 deferral). | owner-approval (engine-adjacent new extractor) |
| 7.3 | Tiled basemap / street labels for the route map — **never invent coordinates/street names**. | owner-approval (external tiles) |
| 7.4 | Surface billing dollars **only** when server cost rules are configured — **never fake dollars**. | owner-approval |
| 7.5 | Wire the real role-gated Approve/Lock/Close action — lands **with** external auth (P5). | owner-approval |
| 7.6 | Always-on Windows-Service staging (S2); lower heal latency (S3); update cloudflared (S6). | owner-approval (ops) |

---

## 4. What must NOT be touched (regression guardrails + hard no-fake rules)

**Forbidden areas — never in a do-now tier, never as a side effect:**

- **The deterministic 50/58 drawn-redline frontier.** No engine-code change may move it. The generic (Lane B) adapter is the *only* engine-adjacent area any step above touches, and it is provably isolated (`GenericGeometryDialect` is never in `_DIALECTS`; fires only after the named path declines). The recognized ODOT/Brenham renders must stay byte-identical.
- **The renderer**, the **fixtures / anchors / coordinates** (every drawn vertex derives from a real run endpoint or an axis projection; extrapolation is flagged and capped — no invented coordinates).
- **The backend truth path** and **`origin/main`** (`068a279`, untouched).
- **Deploy.** No deploy change in any do-now tier; staging steps are config/ops guards only.

**Hard "no fake X" rules (any current violation is a finding; never introduce one):**

- No fake **AUTO** and no fake **FINAL** — uncertain placements are REVIEW/ABSTAIN, never silently AUTO. (Lane B caps `< 0.86`, builds REVIEW directly, provenance `OWNER_CONFIRMED_HUMAN_ADJUSTABLE`.)
- No fake **confidence** — a band is earned evidence, not a polish layer. (This is exactly why Tier 3 kills the HIGH-on-clean-plan path and the stale HIGH 0.73 artifact.)
- No fake **map geometry / street names / coordinates** — KMZ corroborates *length* and supplies map *context* only; the map overlay stays honestly BLOCKED until a real WGS84 redline exists.
- No fake **billing dollars** — quantities only unless real server cost rules are configured; delete the dead Billing-leak component (6.4).
- No **hidden uncertainty** — ABSTAIN names the specific missing evidence element + the next artifact; a banked human grade (SUPERSEDED) is never overridden; the unified export gate blocks a pending/rejected REVIEW.

**Must-not-break flows (verify in the live smoke):** recognized-deterministic path; clean uploaded project; ambiguous correction flow; ZIP/PDF exports. **Preserve:** the single-page stacked-section workspace + `WORKSPACE_SECTIONS` order; `PATH_COPY`/`confidenceTone`/"Why this is REVIEW, not AUTO"; the `onChanged`/`flowVersion` refresh bus; one server-authoritative closeout status + unified export gate; sha256-verified embedded evidence; the correct `#closeout-print` print scoping.

---

## 5. What the live Part-A audit must confirm or refute

The static audits are **predictions** grounded in the code on disk; the running staging build may diverge. Run `05_owner_smoke_script.md` (all 7 flows) and confirm/refute each:

- [ ] **Front door (A1):** is the upload workspace reachable only by typing `/intake?workspace=1` on the *running* build? (Confirmed in source; confirm the deployed build matches.)
- [ ] **Bore-log not auto-read (A2):** does a fresh blank job require manual station re-entry to reach `engine_ready: true`, with `extraction_status` permanently `queued`? (Confirmed in source `upload_pipeline.py:128`; confirm the user-visible behavior in Flow 4.)
- [ ] **Guided demo dead-ends (A3):** do the `/intake` guided cards stop at Accept with no closeout/export? (Flow 7.)
- [ ] **Recognized path env (S7):** does `recognized-log9` / `completed-redline-showcase` actually place real red redlines, or show `RECOGNIZED_CORPUS_REGISTRY_NOT_CONFIGURED`? (Flow 1 step 3, Flow 7 step 2.) — the single highest-stakes config dependency.
- [ ] **Clean job confidence (Flow 2):** does `demo-general-upload` grade as the script expects, and is it seeded clean (green "reviewed & ready" pill)? Note: per Tier 3.2 the honest ceiling is now MEDIUM, not HIGH — **if Flow 2 shows HIGH, that is the rigged-demo path and a finding, not a pass.** (This refines the smoke script's "expect High confidence" line.)
- [ ] **Ambiguous correction (Flow 3):** does `demo-general-upload-ambiguous` grade LOW (unlocking the correction panel), does the plan raster load for click-capture, does Create-anchor-without-Render correctly leave Assemble BLOCKED, and does Render → SUPERSEDED → Assemble → corrected stroke in PDF/ZIP work?
- [ ] **Ambiguous job id:** confirm the seeded id is `demo-general-upload-ambiguous` (the script flags a possible `job-ambiguous` / `general-demo` tenant mismatch) — a one-word swap if wrong.
- [ ] **Export gate (Flow 5):** is Assemble BLOCKED (`REVIEW_NOT_ACCEPTED`) and are downloads disabled before acceptance, then released after? (A downloadable file from an un-accepted redline is a serious RED FLAG.)
- [ ] **Reload resilience (Flow 6):** do job selection + accepted/assembled state survive a refresh (file-backed store)? Losing verdict *text* is an expected low-sev gap; losing job selection or accepted state is a real bug.
- [ ] **Print scoping (Flow 1 step 8):** confirm the print preview shows only `#closeout-print`, **not** the whole workspace — the plan predicts this PASSES (correcting the stale qaMatrix claim). If it leaks, the prediction was wrong.
- [ ] **No-fake invariants (every flow):** all drawn strokes red; no invented coordinates/street names/billing dollars; uncertain = flagged for review, never silent AUTO; KMZ honestly BLOCKED (pixel-only); blocked actions show plain-English reasons, not stack traces.

Anything the live run **refutes** strikes the corresponding finding/step above. Anything it **confirms** stays — and the Tier-1/3/5 fixes are scoped to exactly these.
