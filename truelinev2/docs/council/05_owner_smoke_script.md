# FieldRoute — Owner Smoke Script

**Audience:** Patrick (owner), running behind Cloudflare Access. No prior context needed.
**Goal:** prove a real user can take a project from upload → redline → review/correct → closeout → print/save/download, powered by the real v2 engine, with no fake outputs **and no "demo" language anywhere customer-facing.**
**Rule of the day:** *HTTP 200 is not proof.* A step "passes" only if you reach the EXPECTED result **without anyone explaining where to click**. Anything you have to puzzle over, work around, or be told about = a **RED FLAG** (write it down — it is a finding, not a pass).

This script is **read-only against the running product**. It exercises the UI a customer would use. `<BASE>` = `https://staging.fieldroute.io` (staging) or `http://localhost:3100` (a local browser smoke).

> **Naming note:** the projects below are the seeded example projects. They appear in the **Projects** list by their product names (e.g. "Recognized project — automatic redline"). The raw store IDs (`recognized-log9`, `demo-general-upload`, …) appear only in the URL and under **Diagnostics / Technical details** — never as a visible card, title, or button. That is by design.

---

## 0. Front door + nav (no "demo" anywhere)

1. Open `<BASE>/`.
   - **EXPECT:** a clean FieldRoute landing — hero "Automatic OSP redline handoff", cards **"Start a new project"** and **"Finished redline gallery"**, and a "How FieldRoute works" explainer.
   - The left sidebar nav is exactly **Home · New project · Projects**. The top bar reads **FieldRoute · Access-gated**.
   - **RED FLAG:** the word **"Demo"/"Demos"/"Demo workflows"/"demonstration"/"Staging demo"** appears anywhere on screen. (There should be none.)

2. Click **New project** (or **Projects**) in the sidebar.
   - **EXPECT:** the **Projects** workspace — a **Project** list with product-named projects ("Recognized project — automatic redline", "Uploaded project — clean placement", "Uploaded project — ambiguous (correct it)", "Uploaded project — REVIEW acceptance", "Uploaded project — cross-sheet REVIEW", "Finished redline showcase") plus a "Create project" box.
   - **RED FLAG:** any project card/button shows a raw id like `demo-general-upload`, or says "demo".

---

## Flow 1 — Recognized project, end-to-end (the "it just works" project)

Open **Projects** → click **"Recognized project — automatic redline"**.

| # | Click | EXPECT |
|---|-------|--------|
| 1 | (project opens) | Header **"Recognized project — automatic redline"** (no raw id shown). Status strip: Files / Redline / Closeout. |
| 2 | Scroll to **3 · Map / route**. | A route renders from the uploaded KMZ, or an honest "no GIS route" note. No invented coordinates or street names. |
| 3 | Scroll to **5 · Redline** → **Generate redline**. | **"Redline placed automatically"** + red-stroke redline PNG(s) + **"Continue to closeout ↓"**. <br>**RED FLAG:** "Automatic redline is not configured" / `RECOGNIZED_CORPUS_REGISTRY_NOT_CONFIGURED` (registry env missing). |
| 4 | **6 · Review & correct**. | "No review needed — the redline was placed automatically." |
| 5 | **7 · Closeout review** → **Assemble closeout package**. | Badge **"Assembled — ready for approval"**; Project summary, Uploaded files, **Final review checklist** (all ✓), Redline evidence (red PNG), Bore-log rows, Quantities (Billing **not shown — quantities only**). |
| 6 | **8 · Export & print** → **Download closeout PDF**. | A real PDF downloads (filename like `closeout_packet_recognized-project-automatic-redline.pdf`) with the embedded **red** redline + itemized quantities. |
| 7 | **Download data package (.zip)**. | A real zip downloads. |
| 8 | **Print / save the on-screen review** (the secondary link). | Browser print dialog shows **only** the closeout review (sidebar + other sections hidden). |

---

## Flow 2 — Uploaded project, clean placement (accept & close out)

Open **"Uploaded project — clean placement"**.

| # | Click | EXPECT |
|---|-------|--------|
| 1 | **4 · Bore logs** | Green **"Bore log reviewed & ready"**. |
| 2 | **5 · Redline** → **Generate redline**. | **"Redline candidate placed — review it"** + a dashed red REVIEW PNG. |
| 3 | **6 · Review & correct**. | "Engine REVIEW redline candidate", **"Medium confidence · 70%"** (honest — an inferred placement is **never** shown as High), plus "Why this is REVIEW, not AUTO". <br>**RED FLAG:** a **High** confidence badge (the inference lane is capped at Medium). |
| 4 | **Accept engine redline**. | "Accepted (human-accepted REVIEW)". |
| 5 | **7 · Closeout review** → **Assemble closeout package**. | "Assembled — ready for approval"; redline summary "Accepted REVIEW redline". <br>**RED FLAG:** a stale "still needs to be accepted" message lingering after you accepted. |
| 6 | **8 · Export & print** → download PDF + ZIP. | Both download with embedded red evidence. |

---

## Flow 3 — Uploaded project, ambiguous → correct it → supersede → assemble

Open **"Uploaded project — ambiguous (correct it)"**.

| # | Click | EXPECT |
|---|-------|--------|
| 1 | **5 · Redline** → **Generate redline**. | A dashed red REVIEW candidate. |
| 2 | **6 · Review & correct**. | **"Low confidence — verify"** badge + warnings (multiple plausible runs) + an amber **"Correct redline placement"** panel with the plan image. <br>**RED FLAG:** the badge is not Low (then the correction panel won't appear). |
| 3 | On the plan image, click the bore start, any bends, then the end (≥ 2 clicks). | "N point(s) marked" updates; a marker at each click. <br>**RED FLAG:** "failed to load plan pages" / no image. |
| 4 | **Create source anchor**. | A result with **`renderable: true`**. |
| 5 | **TRAP — do this:** jump to **7 · Closeout** and click **Assemble** *before* rendering. | **BLOCKED** — creating the anchor alone does not supersede; you must Render first. (If it assembles here, that is a serious RED FLAG.) |
| 6 | Back to **6 · Review** → **Render dashed redline from this validated anchor**. | `render: SUCCEEDED`; the card flips to **"Corrected — human-confirmed placement saved"** (SUPERSEDED). |
| 7 | **7 · Closeout** → **Assemble closeout package**. | "Assembled"; redline summary **"Human-corrected REVIEW redline"** — no page reload needed. |
| 8 | **8 · Export & print** → download PDF + ZIP. | Both download with the **corrected** red stroke embedded. |

---

## Flow 4 — Brand-new project from scratch (first-time-user test)

| # | Click | EXPECT |
|---|-------|--------|
| 1 | Sidebar **New project**. | The Projects workspace (reached from the nav — no typed URL). |
| 2 | In the **Project** box, type a name (e.g. `north-loop`) and click **Create project**. | The project is created and selected; the eight numbered sections appear. <br>**RED FLAG:** two identically-labeled "Create project" buttons / a disabled button with no feedback. (First-time setup uses a separate **"Set up workspace"** button.) |
| 3 | **2 · Project files** → set the PDF radio to **Plan PDF**, choose a plan PDF. | "Uploaded 1 file(s)"; the Plan PDF card turns green. |
| 4 | **Separately**, set the radio to **Bore log**, choose the bore-log file. | The Bore log card turns green. The panel states the bore log is **stored, not auto-read** — you confirm its stations next. <br>**RED FLAG:** picking a plan + bore-log PDF *together* is blocked with a clear message (good). |
| 5 | **4 · Bore logs** → **Create reviewed bore-log** → type real start/end stations → **Add reviewed row** → **Confirm** → create + confirm a segment group (the step is prompted while the badge is amber). | Pill flips to green **"Bore log reviewed & ready"**. <br>**RED FLAG:** the group step is hidden with no prompt. |
| 6 | **5 · Redline** → **Generate redline**. | Either a REVIEW candidate (continue as Flow 2/3) or an honest **"Could not place a redline"** with the specific missing evidence (both are acceptable — never a fake). |

---

## Flow 5 — Export gate honesty (must BLOCK — a *good* outcome)

Open **"Uploaded project — clean placement"** (fresh) → **Generate** a REVIEW candidate → **do NOT accept** → jump to **7 · Closeout** → **Assemble**.
- **EXPECT:** BLOCKED with "still needs to be accepted (or corrected) in the Review section" + a "Go to Review" link; the **8 · Export** download buttons are disabled. After you Accept and Assemble, downloads enable. (A downloadable file from an un-accepted redline is a serious RED FLAG.)

---

## Flow 6 — Reload resilience

During Flow 2/3, press browser **Reload** on the project URL after each major step.
- **EXPECT:** the project stays selected; uploaded/accepted/assembled state survives the refresh. (Losing a verdict's *explanatory text* on reload is a known low-severity gap; losing the project selection or the accepted/assembled state would be a real bug.)

---

## Owner sign-off (tick all)

- [ ] **No "demo" language anywhere customer-facing** (landing, sidebar, Projects, project workspace, closeout review, export buttons, downloaded filenames). Raw store ids appear only under Diagnostics / Technical details.
- [ ] Flow 1: recognized project → automatic red redline → assemble → real PDF + ZIP.
- [ ] Flow 2: clean uploaded project → **Medium** confidence (never High) → accept → assemble → download.
- [ ] Flow 3: ambiguous → Low → corrected on the plan → superseded → assemble → download (Assemble blocked before Render).
- [ ] Flow 4: new project from scratch reaches a redline (recording the manual bore-log re-entry as expected).
- [ ] Flow 5: export gate blocks before acceptance, releases after.
- [ ] Flow 6: project + accepted/assembled state survive a reload.

**No-fake checks (every flow):** every drawn stroke is red; no invented coordinates/street names/billing dollars; an uncertain placement is flagged for review, never silent AUTO, never High on the inference lane; KMZ honestly blocked (pixel-only); blocked actions show plain-English reasons.
