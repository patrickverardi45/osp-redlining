# GAC Demo Runbook — Brenham PH5 Redline Placement

**Targets (PRODUCTION):**
- Frontend: `https://osp-redlining.vercel.app`
- Backend: `https://osp-redlining-backend.onrender.com` (Render)
- Persistent disk: `/data` (uploads at `/data/uploads`)

**Goal of the demo:** show TrueLine placing trustworthy redlines on a real job (Brenham PH5), with per-log proof, and the one validated PDF-evidence correction (bore_log71/72). **Demo Brenham only.** Do not live-upload GAC's own files for auto-placement (see `gac_what_to_say.md` and the failure note in §5).

> **Golden rule:** if anything won't **upload / load / persist**, **check disk facts first** (`df -h /data`) before blaming code. Render `/data` has maxed before and caused upload/session/audit failures.

---

## 1. Pre-flight (the day before)

**Render env flags — confirm all ON / `1`:**

The 7 matching flags:
- [ ] `TRUELINE_ABSTAIN_ON_LOCATION_MISMATCH`
- [ ] `TRUELINE_AUTO_CANDIDATE_EXPANSION`
- [ ] `TRUELINE_ABSTAIN_ON_ROUTE_COLLISION`
- [ ] `TRUELINE_ROUTE_COLLISION_ALTERNATE_SEARCH`
- [ ] `TRUELINE_EXPANDED_CANDIDATE_MATRIX`
- [ ] `TRUELINE_LOCATION_MISMATCH_MATRIX_RESCUE`
- [ ] `TRUELINE_SAME_ROUTE_WINDOW_OWNERSHIP`

Sprint-1 proof + PDF proof-slice flags:
- [ ] `TRUELINE_MRQ_PLACEMENT_PROOF=1` — exposes the per-log placement-proof report on the `/api/match-review-queue` JSON (API-only; see §4 note).
- [ ] `TRUELINE_PDF_AP_ROUTE_SHADOW=1` — default-OFF; gated to the 4 proof-slice logs (71/72/39/4).
- [ ] `TRUELINE_PDF_AP_ROUTE_AUTHORITATIVE=1` — default-OFF; gated to the 4 proof-slice logs. **This is what places bore_log71/72 on route_477.**

**Environment + data:**
- [ ] `OSP_UPLOAD_DIR` set to the persistent mount (`/data/uploads`) — if unset, uploads are lost on redeploy.
- [ ] `df -h /data` shows clear headroom (see §2).
- [ ] Demo data on hand: Brenham **KMZ** + the **58 bore logs** + the **3 PH5 plan PDFs**.
- [ ] **Demo credentials ready:** email/password OR a pilot JWT for `/auth/token`. *(verify live)*
- [ ] A **known-good Brenham session loads** end-to-end (also your fallback — §6).

**Expected good result (memorize — this is your live sanity check):**
- **36 of 58 logs placed = 334 station points / 286 redline segments; 22 abstain.**
- **bore_log71 + bore_log72 render on route_477 (LAWNDALE).**
- **bore_log39 (CHERI LN) abstains** (not drawn).

---

## 2. Disk-space pre-flight (Render shell, READ-ONLY — just check, do NOT script cleanup)

```bash
df -h /data
du -sh /data/uploads
du -sh /data/uploads/* | sort -rh | head
ls -lh /data/uploads/session_store.db
ls -lh /data/uploads/*.jsonl
```

**Healthy:** `df -h /data` not near 100%; `session_store.db` present and non-zero; no single subdir runaway-large; `request_audit.jsonl` not crowding the disk.

**If `/data` is near full (operator-confirmed only — do NOT run reflexively):** rotate/archive large `*.jsonl` (e.g. `request_audit.jsonl`); clear **orphaned** `topology_cache` / `engineering_plans` for **dead sessions only**. **NEVER delete** `session_store.db`, `auth.db`, or any live upload.

---

## 3. The click path (fewest steps to redlines + proof)

All upload controls live on the project workspace, **"1. Upload"** section, **Workspace** tab.

1. **Login** — `https://osp-redlining.vercel.app/auth/login`, sign in (email/password). *Pilot-token fallback:* go to `/auth/token`, paste the JWT, **"Save pilot token"** → lands on `/projects`. *(verify live: credentials)*
2. **Open the Brenham project** — at `/projects`, click **"Open Project →"** on the Brenham card, or **"+ New Project"** → name it (e.g. "Brenham PH5") → **"Create & Open"** → lands on `/projects/<slug>`. *(verify live: the project list is per-browser localStorage; confirm a Brenham card exists on the demo machine, or create one.)*
3. **Upload KMZ** — click **"Upload KMZ Design"** (accepts `.kmz/.kml`) → posts to `/api/upload-design`. This mints the session and draws the KMZ design lines. *(KMZ must come first — the PDF upload is gated on an active session.)*
4. **Upload Field Data** — click **"Upload Field Data"** (accepts `.xlsx/.xls/.csv`, multiple), select the Brenham bore logs → posts to `/api/upload-structured-bore-files`. Backend matches routes + builds redlines.
   - **→ The "Project Map" redraws: red redline lines + yellow station dots, auto-zoomed. This is the headline visual.**
5. *(Footage proof)* switch to the **Closeout** tab → **"4. Reports"** → show **Drilled/as-built footage** + the **% complete** donut.
6. *(Engineering evidence — the PDF story)* expand **"Reference Plans / Closeout Evidence"** → **"Upload Engineering Plan PDFs"** → select the 3 PH5 PDFs (posts to `/api/upload-engineering-plans`). With the PDF-AP flags ON, this is what backs the bore_log71/72 → route_477 correction.
7. **Show placement proof** — open **`/match-review?projectId=<slug>`** (same browser/session). Each row shows source_file, selected route, and a **route-verdict badge: Consistent / Suspect / Not proven**. Click **"View on map →"** → returns to `/projects/<slug>?focus=<source_file>` with a **"Focused review"** banner and the map panned/emphasized on that log's redline.

---

## 4. What the viewer sees (and where the proof actually lives)

- **Map ("Project Map" / ModernHeroMap):** redline segments = **red polylines** (`#ef4444`); station points = **yellow dots** (`#facc15`); auto-fit to the data. There is **no pts/segs counter on the map** — confirm counts via the Closeout footage report and/or the API (§ verification).
- **In-app proof = the `/match-review` route-verdict badges** (Consistent / Suspect / Not proven) + the `?focus=` map emphasis.
- **HONEST NOTE — `placement_proof` is API-only.** The Sprint-1 `TRUELINE_MRQ_PLACEMENT_PROOF` report (per-log `evidence_source`, station_pts, segs, totals) is returned in the **`/api/match-review-queue?session_id=<sid>` JSON** but is **not rendered by any page yet**. If you want to show it, open that URL in a browser tab (authenticated) or curl it — do not promise an in-app panel that doesn't exist. *(verify live: `/match-review` has no default nav button from the workspace except "Trust Ledger"; reach it by URL.)*

---

## 5. Demo verification checklist (confirm these live before you call it good)

- [ ] After Field Data upload, **red redlines + yellow stations draw** and the map auto-zooms.
- [ ] Closeout footage report shows a non-zero **drilled/as-built footage**.
- [ ] `/match-review?projectId=<slug>` lists rows with **verdict badges** (some Consistent, some Not proven, some abstained) — i.e. it is **not** all-green; the abstains are visible.
- [ ] **bore_log72 → route_477** (the validated PDF correction) and **bore_log71 → route_477**; **bore_log39 abstains** (no redline).
- [ ] *(API spot-check, optional)* `GET /api/match-review-queue?session_id=<sid>` JSON `placement_proof.totals` reconciles to **station_pts=334, segs=286** for the full PH5 session (or matches whatever the loaded session contains).
- [ ] No "Failed to fetch" / no 502 `<!DOCTYPE html>` during uploads.

---

## 6. Failure-mode triage + abort

**Upload "Failed to fetch" OR "Current state load failed (502): `<!DOCTYPE html>`":**
1. **Check `df -h /data` first** (disk-full is the most common cause).
2. Confirm the backend is up (Render can cold-start).
3. B-WS-12 fingerprint: a bore-log upload that OOMs the backend (memory, not disk) → 502 → that exact `<!DOCTYPE html>` string. Structurally fixed (RI.4 ROWS_ONLY), but know the tell.

**Redlines don't draw:** confirm the 7 matching flags + proof-slice flags are still ON; confirm a rebuild ran after upload.

**Abort/fallback:** one clean live attempt. If upload/load stutters, **switch to a pre-loaded known-good Brenham session** (load, don't upload) and keep talking. Keep a **screen-recording of a clean run** as the ultimate fallback. Do not debug live in front of the room.

---

*Numbers in this runbook are from deterministic local replays this session (`scripts/pdf_ap_conflict_grader.py`, `scripts/trust_ledger_replay.py`). The decision to keep PDF-AP gated to bore_log71/72 is locked — see `gac_what_to_say.md` and the Sprint 2.5 grading evidence.*
