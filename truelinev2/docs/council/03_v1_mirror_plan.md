# 03 — V1 Mirror Plan (one job, one page)

**Author role:** Product Lead + Frontend UX Lead (council seat 03)
**Scope:** Web repo `C:/Nova/projects/trueline-web-experience` ONLY. No engine / renderer / fixture / backend-truth-path / origin-main / deploy changes are proposed in the do-now tier.
**Source inputs:** v1 audit + UX audit + closeout audit (council JSON), grounded against the live files cited below.
**Goal (what "works like v1" means):** a real user, with no one explaining where to click, can create/select a job → upload plan PDF + KMZ/KML + bore logs + photos → see route/map/project context → generate redline candidates → review OR correct → see a clean closeout review page → print/save/download closeout PDF + ZIP. Powered by the v2 engine, with no fake outputs.

---

## 0. The single most important finding (the blocker)

The v2 single-page workspace (`src/components/ProductWorkspace.tsx`) already mirrors v1 structurally — eight numbered sections stacked in fixed order, one action owner per section, honest AUTO/REVIEW copy, dev plumbing collapsed behind disclosures. **The product is structurally there.** The one thing that makes it "not work like v1" is **discoverability**: the only surface where a real user can create a project and upload files is `ProductWorkspace`, and it is reachable **only** by manually typing `/intake?workspace=1`. Every visible nav item and every demo card routes to the two-card guided demo chooser, which has no upload path (`src/components/ProductIntake.tsx:8-10`, `:242-293`; `src/components/shell/Sidebar.tsx:17-21`).

That single hidden front door fails the success bar ("no one explains where to click") on its own. **Fix the front door first; everything else is polish on an already-correct page.**

---

## 1. Target one-page job workspace structure

Keep the existing structure — it is correct. The canonical section order is already defined once in `src/lib/workspaceSections.ts:12-21` and consumed by both the body (`ProductWorkspace.tsx:315-319`) and the sidebar scroll-spy (`Sidebar.tsx:96-126`). **Do not refactor this; do not split it back into routes.**

Target sections, in order, each `<section id="ws-<key>">` with a same-page anchor (`sectionAnchorId`, `workspaceSections.ts:24-26`):

| # | Key | Label (customer-facing) | Owner action | Component |
|---|-----|------------------------|--------------|-----------|
| — | `summary` | **Overview** (job dashboard / header) | ONE derived "next action" (no owned mutation) | `JobHeaderBand`, `ProductWorkspace.tsx:353` |
| 2 | `uploads` | **Project files** | Upload | `ProductUploadPanel` + `UploadsCards`, `ProductWorkspace.tsx:161-174` |
| 3 | `map` | **Map / route** | (read-only) | `ProductRouteMap`, `ProductWorkspace.tsx:175-180` |
| 4 | `borelogs` | **Bore logs** | Review rows / confirm | `ProductReviewedBoreLogGate`, `ProductWorkspace.tsx:181-186` |
| 5 | `redlines` | **Redline** | **Generate** (sole owner) | `ProductWorkflowPanel`, `ProductWorkspace.tsx:187-199` |
| 6 | `review` | **Review & correct** | **Accept / Correct** (sole owner) | `ProductReviewCandidates` (with `hideGenerate`), `ProductWorkspace.tsx:200-212` |
| 7 | `closeout` | **Closeout review** | **Assemble** (sole owner) | `CloseoutReviewSection`, `ProductWorkspace.tsx:213-225` |
| 8 | `exports` | **Export & print** | **Download / Print** (sole owner) | `ExportsSection`, `ProductWorkspace.tsx:226-231` |

Section #1 (Overview) is the header band; its number is suppressed by design (it is the page header, not a workflow step). Keep it that way.

The same-page anchor / scroll-spy contract is the v1-equivalent "one page" navigation. **Preserve `WORKSPACE_SECTIONS` as the single source of truth for keys/labels/order.**

---

## 2. Per-component / per-route disposition (KEEP / CHANGE / REMOVE-or-HIDE)

### A. Product workspace (the truth path) — KEEP, with targeted CHANGES

| File | Disposition | Why / what |
|------|-------------|-----------|
| `src/components/ProductWorkspace.tsx` | **KEEP + CHANGE** | The page is correct. Changes: relabel duplicate "Create project" buttons (§3.2), soften id placeholder, restore `?section=` deep-link, move stray raw codes behind diagnostics, add positive closeout checklist + photos + notes + sign-off affordance honesty. |
| `src/components/ProductUploadPanel.tsx` | **KEEP + CHANGE** | Human-label the PDF-category radios (§3.3); drop the raw `jobId` from the panel title or move to a muted sub-label. |
| `src/components/ProductReviewedBoreLogGate.tsx` | **KEEP + CHANGE** | Drop the `(uploadId)` suffix from the source select (`:181-183`); human-label the `SegmentRelation` dropdown (`:298-302`); replace `window.prompt` reject (`:122-126`) with the inline reason input pattern already used in `ProductReviewCandidates.tsx:449-460`; keep `grp-…`/enum rows inside the existing "Review tools & diagnostics" `<details>` (`:259-341`) — that disclosure already exists, just keep the leaks inside it. |
| `src/components/ProductSourceAnchorCapture.tsx` | **KEEP + CHANGE** | This is the correction lane a non-engineer customer actually touches, so its leaks are high-impact. Remove the editable "Anchor id" input (`:283-289`) and "Reviewed bore-log" input (`:209-216`) — both already auto-default (`defaultAnchorId()` `:41-44`, `reviewedBoreLogId='rbl-main'` `:49`), so just drop the fields and keep generating silently. Move the `status:` / `renderable:` / `provenance:` / `coordinate space:` mono lines (`:306-313`, `:349-357`) into a "Technical details" `<details>`. Keep the plan-PDF select but show the filename without mono framing. |
| `src/components/ProductReviewCandidates.tsx` | **KEEP + CHANGE** | Move the parenthetical raw codes `(PARTIAL_SPAN_COVERAGE_50_PCT)` (`:358-361`) and the `(NO_PER_BORE_TERMINI)` items (`:374-378`) into the existing diagnostics `<details>` (`:386-406`); keep the plain-English sentence in the headline. Keep the inline reject-reason input (`:449-460`) — it is the correct pattern; reuse it in the bore-log gate. **Do NOT touch** `PATH_COPY`/`confidenceTone`/"Why this is REVIEW, not AUTO" honesty logic (`:24-51`, `:74-86`, `:368-382`). |
| `src/components/ProductWorkflowPanel.tsx` | **KEEP** | Generate is its sole action; diagnostics already correctly collapsed (`:239-247`). Reference pattern for the disclosure style. |
| `src/components/ProductRouteMap.tsx` | **KEEP + CHANGE** | State the no-basemap caveat **once** (collapse the triple disclaimer at `:90-94`, `:161-164`, header comment into one concise line, e.g. "Route shape from your uploaded KMZ/KML. No street basemap yet."). Move the raw `bbox …` line (`:141-145`) into diagnostics. **Do NOT add fake tiles or street names** — keep the no-invented-geometry stance; this is copy volume only. |
| `src/components/ProductUploadInventory.tsx` | **KEEP** | Already correctly mounted only inside the "Technical details — stored file inventory" `<details>` (`ProductWorkspace.tsx:169-172`). This is the right home for raw upload ids. |
| `src/components/ProductRecognizedCorpusHandoff.tsx` | **KEEP + CHANGE** | Move the raw blocked-state codes shown as visible bullets (`:187-193`, e.g. `UPLOADED_CORPUS_NOT_RECOGNIZED — …`) behind a "Technical details" `<details>`; keep the plain-English explanation visible. This is the recognized-deterministic path's user-facing surface — **do not change its handoff logic**, copy only. |
| `src/lib/workspaceSections.ts` | **KEEP + CHANGE** | Either wire `coerceSection` (`:30-33`) so reload/deep-link honors `?section=`, or stop writing `?section=` in `workspaceHref` (`:36-41`). See §3.5 — the doc comment (`:3-4`) currently promises sync that is not implemented. |

### B. Navigation shell — CHANGE (this is where the blocker lives)

| File | Disposition | Why / what |
|------|-------------|-----------|
| `src/components/shell/Sidebar.tsx` | **CHANGE** | `NAV` (`:17-21`) is Home / Showcase / Intake only. **Add a visible "New project / Upload" item linking to `/intake?workspace=1`** (the real front door). **Rename "Intake" → "Guided demos"** so the label matches the chooser it opens (`:20` label vs `intake/page.tsx:15` title "Demo workflows" vs `ProductIntake.tsx:245` "Choose a demo workflow"). Keep the in-workspace section nav (`:85-127`) exactly as is — it is the correct same-page anchor rail. |
| `src/app/intake/page.tsx` | **KEEP** (copy already honest) | Title "Demo workflows" (`:15`) is fine once the sidebar label matches it; sub-copy already points off-path to the workspace. |

### C. Front doors (Home + the workspace's own back-link) — CHANGE

| File | Disposition | Why / what |
|------|-------------|-----------|
| `src/app/page.tsx` | **CHANGE** | `DEMO_CARDS` (`:22-44`) are three demo entries with no upload front door. **Add a fourth card "Start a new project — upload your files" → `/intake?workspace=1`**, honestly labeled as the operator/upload workspace. This is the single change that makes the v1 core flow reachable from the landing page. |
| `src/components/ProductIntake.tsx` | **CHANGE** | The "Guided demo workflows" link inside the workspace (`ProductWorkspace.tsx:246-248`) points **back** to the chooser, which is correct as a secondary link — keep it. The blocking issue is the **absence of a forward link into `?workspace=1`** anywhere else; that is fixed in Sidebar + Home above. Optionally add one honestly-labeled "Operator / upload workspace" card to the chooser (`:242-293`) so the demo page itself offers the door. Do not remove the typed-URL gate logic; just stop it being the *only* door. |

### D. Dead / legacy components — REMOVE

| File | Disposition | Why / what |
|------|-------------|-----------|
| `src/components/ProductArtifactGallery.tsx` | **REMOVE** | Exported (`:43`) but imported by no page/component (grep-confirmed). Reads a single `NEXT_PUBLIC_TL2_JOB_ID` job (`liveV2Product.ts:44`) — the pre-workspace single-job model the per-job workspace replaced. |
| `src/components/ProductJobStatusStrip.tsx` | **REMOVE** | Exported (`:32`), imported nowhere. Surfaces a **Billing** field with `billingFinalTotal/currency` (`:71-75`) that contradicts the workspace's "no dollar amounts shown" stance (`ProductWorkspace.tsx:676`). Deleting it prevents a future contributor re-mounting a billing-dollars/single-job panel that violates the no-fake-billing rule. |
| `NEXT_PUBLIC_TL2_JOB_ID` config path (`liveV2Product.ts:44`) | **REMOVE if no other consumer** | Only the two dead components above use it (grep shows the read site at `liveV2Product.ts:44` and nothing else). Remove the helper once the two files are gone, after a final grep confirms zero remaining references. Lower priority than the deletions; do it in the same PR to avoid a dangling config. |

### E. Stale parallel dashboard routes (the "where is closeout" trap) — HIDE-from-nav now, REMOVE/GATE later

| File | Disposition | Why / what |
|------|-------------|-----------|
| `src/app/closeout/page.tsx` | **HIDE / GATE** | Contract-first **mock** dashboard: `api.closeout.readiness(FLAGSHIP_PROJECT_ID)`, self-labeled "mock data" (`:39`), header CTA → `/packet` "Export packet" (`:42-46`). This is NOT the product closeout (which lives only in `ProductWorkspace §7/§8`). Already absent from the `NAV` array (`Sidebar.tsx:17-21`), so it is reachable only by URL today — that is the right posture. **Action:** confirm it stays out of all product nav and badge it unmistakably "Demo / mock — not your job's closeout" if it is kept for the showcase. Do not delete in the do-now tier (it is the original dashboard; deletion is higher-risk and out of the v1-mirror critical path). |
| `src/app/packet/page.tsx` | **HIDE / GATE** | Mock packet builder over `api.closeout.packet(projectId)` for hardcoded `demo-project-001/003` (`:10`, `:13-21`). Same treatment as `/closeout`: keep out of product nav, badge as mock if retained. |

**Rationale for HIDE-not-REMOVE here:** the council hard rules forbid touching the backend truth path and warn that "other routes are mostly NOT the product truth path; treat with suspicion." These routes are already de-advertised (not in `NAV`). The cheap, safe, regression-free win is to guarantee they never appear in product navigation and never collide with the one real closeout. Full removal of the original dashboard is a separate decision the owner should make deliberately, not a side effect of the v1-mirror change.

---

## 3. Exact edits to make the app understandable

### 3.1 Front door (BLOCKER — do first)
- `Sidebar.tsx:17-21` — add `{ href: '/intake?workspace=1', label: 'New project', icon: Upload }` to `NAV`; rename existing `{ href: '/intake', label: 'Intake' }` → `label: 'Guided demos'` (icon can stay `Upload` or switch to a demo/play icon).
- `app/page.tsx:22-44` — add a `DEMO_CARDS` entry: `href: '/intake?workspace=1'`, title "Start a new project", body "Upload your plan PDF, bore logs, KMZ/KML route, and photos, then generate and review the redline — your real job, end to end.", cta "Create a project and upload files".
- Result: at least two visible, honestly-labeled paths to `?workspace=1`. No more secret URL.

### 3.2 Duplicated "Create project" buttons (`ProductWorkspace.tsx`)
- Button at `:255-260` (tenant-level, shown when `!projectExists`, calls `onCreateProject`) → relabel **"Set up workspace"** (or "Initialize").
- Button at `:294-299` (per-job, calls `onCreate → onCreateJob`) → keep label **"Create project"**.
- Input at `:288-293` placeholder → **"project name"** (drop "id (a-z 0-9 _ -)" framing from the primary surface).
- Pick ONE customer word — **"project"** — and map it consistently to the job concept in copy. Never show two identically-labeled buttons at once.

### 3.3 Raw enum / id leaks in customer-facing forms
- `ProductUploadPanel.tsx:75-84` — render the radio labels as **"Plan PDF"** / **"Bore log"** (the `cat` value stays `PLAN_PDF`/`BORE_LOG` internally; only the visible `<span>` text changes).
- `ProductUploadPanel.tsx:65-67` — drop the raw `jobId` mono from the heading, or demote it to a muted sub-label.
- `ProductReviewedBoreLogGate.tsx:181-183` — show `{u.filename}` only; drop `({u.uploadId})`.
- `ProductReviewedBoreLogGate.tsx:298-302` — option labels **"Separate bores"** / **"Segments of one run"** (values unchanged).
- `ProductSourceAnchorCapture.tsx:209-216, 283-289` — remove both the "Reviewed bore-log" and "Anchor id" inputs (auto-defaults already exist); submit silently with the generated ids.
- Keep every raw token available **only** inside the existing `<details>` disclosures.

### 3.4 Engineer-speak in primary copy → move behind diagnostics
- `ProductReviewCandidates.tsx:358-361, 374-378` — strip the parenthetical raw codes from the main body; keep plain English; surface the codes inside the existing diagnostics `<details>` (`:386-406`).
- `ProductSourceAnchorCapture.tsx:306-313, 349-357` — move `status/renderable/provenance/coordinate space` lines into a "Technical details" `<details>`.
- `ProductRecognizedCorpusHandoff.tsx:187-193` — move raw blocked-state codes behind a "Technical details" `<details>`.
- `ProductRouteMap.tsx:90-94, 141-145, 161-164` — one concise no-basemap caveat; raw `bbox` into diagnostics.

### 3.5 `?section=` deep-link state (`workspaceSections.ts` + `ProductWorkspace.tsx`)
Pick ONE (do not leave the URL lying):
- **(a) Honor it** — on mount, read `searchParams.get('section')` → `coerceSection` (`workspaceSections.ts:30-33`, currently zero call sites) and `scrollToSection` after the job detail loads (`ProductWorkspace.tsx:101-104`). Restores v1-style deep-linkability.
- **(b) Stop writing it** — drop `params.set('section', …)` from `workspaceHref` (`:39`). Removes the false promise the doc comment makes (`:3-4`).
- Recommendation: **(a)** — it is the more v1-faithful behavior and the parse helper already exists.

### 3.6 `window.prompt` reject → inline input
- `ProductReviewedBoreLogGate.tsx:122-126` — replace `window.prompt('Reason for rejecting this row?')` with the inline required-reason input pattern already proven in `ProductReviewCandidates.tsx:449-460`. Removes the unstyled native modal and makes rejection capture consistent in-app.

---

## 4. Closeout completeness (v1 had these; v2 dropped them) — frontend-only, no contract change

These are the parts where v2 currently feels *worse* than v1. All are addressable on the read side using data the backend already returns.

1. **Field-photo evidence (v1 §4) is accepted but never shown.** `PHOTO` is an accepted upload kind (`ProductWorkspace.tsx:76`) and the closeout review even lists "Photos" with a check/X icon (`:620-628`), implying it is in the package — but no photo ever reaches the on-screen review or the PDF. **Fix:** either render a photo-evidence block in `CloseoutReviewSection` sourced from the job's `PHOTO` uploads (same trusted-upload read pattern as redline artifacts), **or** remove `PHOTO` from the closeout `UPLOAD_KINDS` loop so the review does not promise evidence it omits. Do not fake any geotag/coordinate. (PDF embedding is a backend `closeout_pdf.py` task — flag it but keep it out of this web-only do-now tier.)
2. **Operator notes (v1 §7) absent.** No place for a closer/PM to record a human note. **Fix (web side):** add an optional free-text notes field in `CloseoutReviewSection` that persists server-side on the existing closeout/export record; render it in the on-screen review. Must be clearly human-authored and must not influence the server gate. (Backend persistence + PDF render is a contract-adjacent task — coordinate with the backend seat; do the UI capture once persistence exists.)
3. **No sign-off in the UI though the backend has it.** `ProductWorkspace.tsx:707` says "approve/lock are deferred", yet `closeout_review.py` implements `lock/unlock/approve/reject/reopen/close` with audit. **Fix:** decide with the owner — (a) wire an explicit Approve/Lock action gated on the deployment's `authorized_roles` (no contract change needed), advancing `READY_FOR_APPROVAL → LOCKED/APPROVED` and unlocking FINAL packet/billing; or (b) if approval is genuinely gated on external auth, say so honestly ("Sign-off requires sign-in — coming with accounts") instead of a permanently-disabled-feeling dead end. **Do not** silently leave the workflow dead-ending one step before v1's "Approved for Billing".
4. **Positive completeness checklist (v1 final-review checklist).** The on-screen "Notes" panel renders only when warnings/blockers exist (`:691-703`), so a clean happy-path job shows no readiness affirmation beyond the green pill. **Fix:** add a positive, server-derived checklist (redline placed ✓, review accepted/recognized ✓, bore-log engine-ready ✓, package assembled ✓, KMZ status, billing status) from data already fetched (`fetchCloseoutStatus` + `fetchExportStatus`). Every row backed by a real server value — no fabricated ✓.
5. **Demote the weaker print path.** `ExportsSection` (`:763-789`) shows "Print / Save this review" first and equally prominent to "Download closeout PDF", but the on-screen review omits itemized quantities/disclaimer (`:678-681`), so Print yields a thinner artifact. **Fix:** make "Download closeout PDF" the primary CTA; demote browser Print to a small secondary "Print this review" text link. Keep the already-honest helper copy (`:783-789`). Do not enrich the printed view with fakes.

**Keep exactly as-is (closeout strengths — do not regress):** one server-authoritative status; the unified `export_gate` (409 + same REVIEW-acceptance code across ZIP/PDF/assembly); no fake billing dollars; honest KMZ `BLOCKED[UNSUPPORTED_PIXEL_ONLY]`; sha256-verified evidence; deterministic ZIP bundle; the `#closeout-print` + `@media print` review-before-print flow; the REVIEW-required banner.

---

## 5. What stays UNTOUCHED (regression guardrails)

These must not change in any do-now edit. Any change here is a higher-risk, separately-called-out tier.

- **Engine / renderer / fixtures / anchors / coordinates / backend truth path / `origin/main` / deploy.** Nothing in §1–§4 touches these; every edit is frontend-only.
- **Deterministic frontier 50/58 drawn redlines** — no edit here can move it (no engine code is touched).
- **The four flows that must not break:**
  - **Recognized-deterministic path** — `ProductRecognizedCorpusHandoff` logic and the recognized handoff in `ProductIntake.tsx:230-231`; only its raw-code *copy* moves behind diagnostics.
  - **Clean uploaded project** — the upload → generate → review → assemble → export happy path in `ProductWorkspace`; structure and section order unchanged.
  - **Ambiguous correction flow** — `ProductReviewCandidates` accept/reject + `ProductSourceAnchorCapture` render lane; only id-input removal + copy-relocation, no behavior change to candidate state transitions or the render call.
  - **ZIP / PDF exports** — `ExportsSection` download handlers (`:744-755`) and the `triggerDownload` helper (`:90-99`) are untouched; only button prominence/labels change.
- **Honesty contracts** — `PATH_COPY`, `confidenceTone`, "Why this is REVIEW, not AUTO", "no dollar amounts shown", "no street names / no invented geometry", the REVIEW-required banner. Copy may move location (inline → disclosure) but its meaning must not soften and no fake AUTO/FINAL/confidence/billing/coords may be introduced.
- **The single source of truth for sections** — `WORKSPACE_SECTIONS` in `workspaceSections.ts`. Add/honor `?section=` parsing, but do not reorder or rename keys (labels are already customer-readable).
- **The `onChanged`/`flowVersion` refresh bus** (`ProductWorkspace.tsx:129-134`) — preserve; it is what keeps the one page reactive after an in-page action.

---

## 6. Suggested sequencing (lowest risk → highest)

1. **Front door** (§3.1) — Sidebar nav item + Home card → `/intake?workspace=1`; rename "Intake" → "Guided demos". *Unblocks the entire v1 flow; pure additive copy/links.*
2. **Delete dead components** (§2.D) — `ProductArtifactGallery`, `ProductJobStatusStrip`, then `NEXT_PUBLIC_TL2_JOB_ID`. *Removes a billing-dollars/single-job re-mount hazard; zero runtime references.*
3. **Form-leak cleanup** (§3.2–§3.4, §3.6) — labels, id-input removal, codes behind diagnostics, inline reject. *Frontend-only, no state-machine change.*
4. **`?section=` deep-link** (§3.5, option a). *Low-risk; restores v1 deep-linkability.*
5. **Confirm legacy `/closeout` + `/packet` stay out of product nav** (§2.E). *Verification + optional mock badge.*
6. **Closeout completeness** (§4) — positive checklist + photo decision + notes capture + sign-off decision + Print demotion. *Coordinate items needing backend persistence/PDF with the backend seat; ship the web-only parts first.*

---

## 7. Acceptance bar (how to know it mirrors v1)

A first-time user, given only the running app URL and no verbal instructions, can:
1. Find and click a visible "New project / upload" entry (no secret URL).
2. Create one project, upload plan PDF + bore log (+ optional KMZ + photos), and see them confirmed.
3. See the route on the map and the bore-log rows.
4. Generate the redline, then accept or correct it — with honest REVIEW (never fake AUTO).
5. Land on one clean closeout review page that shows everything the package contains (including photos, or honestly omits them).
6. Download the closeout PDF (primary) and the ZIP, or print/save the review.

"HTTP 200 is not proof." The bar is a real human completing 1–6 without anyone explaining where to click — which today fails only at step 1.
