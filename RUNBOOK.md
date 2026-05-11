# TrueLine operations runbook

## Step 0B — uploads backup and restore

This runbook covers **only** the directory resolved as `UPLOADS_DIR` in production (`OSP_UPLOAD_DIR`, typically `/data/uploads` on Render with a persistent disk at `/data`).

It does **not** cover:

- **`backend/data/operational_logs/`** — the current deployed backend does not ship snap-review JSONL at that path; nothing to back up there until code and disk layout exist.
- **SQLite** — not deployed yet; session/job state is still in-memory in the running process.
- **Raw KMZ blobs** — uploads are parsed in memory; rehydration after full loss still requires re-uploading KMZ from the operator.

### Verified Render layout (reference)

- `OSP_UPLOAD_DIR=/data/uploads`
- `/data` is a Render persistent disk
- Under `/data/uploads` expect at least: `engineering_plans/`, `nova_overrides/`, `project_route_context/`, `reviewer_exceptions/`, `station_photos/`, `walk_submissions/`

---

## How to run a backup

### On Render (shell)

From the service root where `scripts/` exists (same layout as this repo):

```bash
chmod +x scripts/backup_uploads.sh
./scripts/backup_uploads.sh
```

If `OSP_UPLOAD_DIR` is already set in the environment (Render dashboard), the script uses it. Otherwise it uses `/data/uploads` when that directory exists.

Optional overrides:

```bash
OSP_UPLOAD_DIR=/data/uploads BACKUP_OUTPUT_DIR=/data/backups ./scripts/backup_uploads.sh
```

**Expected output (example):**

```
SOURCE=/data/uploads
OUTFILE=/data/backups/truline-uploads-20260511T153045Z-a1b2c3d.tar.gz
GIT_SHA=a1b2c3d
OK verified archive entries=42
/data/backups/truline-uploads-20260511T153045Z-a1b2c3d.tar.gz
```

Exit code `0` means the tarball was written and `tar -tzf` succeeded. Any non-zero exit means backup failed (do not treat the archive as good).

### Local / dev (fallback)

With no `/data/uploads`, the script uses `<repo>/backend/uploads` if that directory exists:

```bash
./scripts/backup_uploads.sh
```

Archives default to `<repo>/backups/` (created automatically). Add `backups/` to deployment ignore lists if you sync the repo to a server; it is gitignored here.

---

## How to restore a backup

**Warning:** restore overwrites the live uploads tree. Stop traffic or scale the web service to zero before restore to avoid half-written JSON indexes.

### 1. Stop the app

On Render: scale the service to **0** instances, or use maintenance mode if you use a proxy in front.

### 2. Preserve current state (safety)

```bash
TS=$(date -u +%Y%m%dT%H%M%SZ)
sudo mv /data/uploads "/data/uploads.pres.${TS}" || mv /data/uploads "/data/uploads.pres.${TS}"
```

(Use `sudo` only if your shell user requires it; Render shell is often already root or the deploy user.)

### 3. Extract the tarball

Archives are built with **`-C <parent> uploads`** (or `backend/uploads` on dev), so members look like `uploads/...`.

**Render (`/data` disk):**

```bash
tar -xzf /data/backups/truline-uploads-<TIMESTAMP>-<GITSHA>.tar.gz -C /data
ls -la /data/uploads
```

**Local dev:**

```bash
tar -xzf backups/truline-uploads-<TIMESTAMP>-<GITSHA>.tar.gz -C "$(git rev-parse --show-toplevel)/backend"
ls -la backend/uploads
```

### 4. Permissions

Ensure the process user can read/write `/data/uploads` (same ownership as before the restore). On Render, redeploying sometimes resets nothing if the disk is unchanged—verify `ls -la`.

### 5. Start the app

Scale back to **1** instance. Smoke-test: open a job, confirm photos load and walk submissions appear.

### 6. If restore was wrong

```bash
rm -rf /data/uploads
mv "/data/uploads.pres.<TS>" /data/uploads
```

---

## Post-restore verification

Run on the **restored** disk (paths under `/data/uploads` on Render):

| Check | Command / action |
|--------|------------------|
| **Station photos** | `test -f /data/uploads/station_photos/index.json && jq . /data/uploads/station_photos/index.json \| head` (or `python -m json.tool`) — expect `"photos"` array |
| **Walk submissions** | `test -f /data/uploads/walk_submissions/index.json` — list `walk_submissions/*.json` |
| **Engineering plans** | `test -f /data/uploads/engineering_plans/index.json` — `ls engineering_plans/` |
| **Reviewer exceptions** | `test -f /data/uploads/reviewer_exceptions/index.json` |
| **Nova overrides** | `test -f /data/uploads/nova_overrides/index.json` |
| **Project route context** | `ls /data/uploads/project_route_context/` — JSON per project |

If `index.json` is missing or invalid JSON, treat restore as incomplete.

---

## Render-specific notes

- **Disk:** Backups written to `/data/backups` stay on the **same** persistent disk as `/data/uploads`. If the disk is lost, both uploads and backups are lost—mirror tarballs off-box (e.g. `aws s3 cp`) for real disaster recovery; that is outside this minimal script.
- **Cron:** Render can run a cron job or scheduled shell that invokes `scripts/backup_uploads.sh`; ensure the job’s working directory includes the repo root (or call with absolute path to the script).
- **No SQLite yet:** restarting the service still drops in-memory session state (`STATE` / `_SESSIONS`). Backup only protects **filesystem evidence** under `UPLOADS_DIR`.

---

## In-memory session warning (current production)

Until SQLite (or equivalent) session persistence ships:

- Operators may need to **re-upload KMZ** and re-run bore/redline steps after a long restart or deploy, even when `/data/uploads` is intact.
- This runbook **does not** change that behavior; it only protects what is already on disk under `UPLOADS_DIR`.

---

## Private Beta Operations

Purpose: operational guidance for the private-beta security gate. Keep changes minimal and internal-only.

1) Current branch
- `security/private-beta-gate`

2) Local startup commands
- Backend (PowerShell):

	```powershell
	cd C:\Nova\projects\TrueLine\TrueLine_Beta\backend
	.\venv\Scripts\Activate.ps1
	python -m uvicorn main:app --reload
	```

- Frontend:

	```powershell
	cd C:\Nova\projects\TrueLine\TrueLine_Beta\web
	npm run dev
	```

3) Required env vars
- Backend:
	- `TRUELINE_OBS_TOKEN` (observability token)
	- `TRUELINE_ALLOWED_ORIGINS` (CSV list, fallback to `[*]`)
	- `TRUELINE_API_TOKEN` (placeholder/future)
	- `OSP_UPLOAD_DIR` (optional override for uploads)
- Frontend:
	- `NEXT_PUBLIC_API_BASE`

4) Protected endpoints (observability)
- `/api/debug/*` (requires observability token if `TRUELINE_OBS_TOKEN` set)
- `/api/observability/*` (requires observability token if set)

5) Session persistence
- SQLite DB: `uploads/session_store.db`
	- Persists `_SESSIONS` snapshots and survives backend restart
	- Do not delete without backup

6) Request audit
- Audit file: `uploads/request_audit.jsonl`
- Endpoint: `GET /api/observability/request-audit`
- Token required (observability middleware)
- Logs (one JSON object per line): timestamp, request_id, path, method, session_id (query), status_code, duration_ms
- Does NOT log request bodies, headers, auth tokens, or uploaded contents

7) Session observability endpoints (examples)
- List recent sessions (metadata only):

	```powershell
	$hdr = @{ Authorization = "Bearer local-test-token" }
	Invoke-RestMethod -Uri "http://localhost:8000/api/observability/sessions?limit=50" -Headers $hdr
	```

- Label a session:

	```powershell
	$body = @{ session_id = 'abc123'; company_id = 'ACME'; workspace_label = 'ACME-net' } | ConvertTo-Json
	Invoke-RestMethod -Uri "http://localhost:8000/api/observability/session-label" -Method Post -Body $body -Headers $hdr -ContentType 'application/json'
	```

8) Backup checklist (minimal)
- Stop backend if possible (scale to 0 or stop service)
- Copy `uploads/` directory to dated backup folder
- Copy `uploads/session_store.db` and `uploads/request_audit.jsonl` explicitly
- Keep a dated backup folder: `backups/truline-<YYYYMMDDTHHMMSS>-<gitsha>/`

9) Beta operating rules
- Only internal users operate the system in private beta
- No public signups or external onboarding
- Label every customer session with `company_id`/`workspace_label`
- Never share the observability token
- Keep each company/project in separate sessions
- Verify `session_id` before uploading real customer data

10) Incident procedure (high-level)
- Wrong customer data uploaded: stop ingestion, snapshot uploads, contact owner, restore from backup if needed
- Backend restart: verify `session_store.db` present; check `/api/observability/sessions` for recovered sessions
- Missing session: check `uploads/session_store.db` and `uploads/` indexes; restore backup if needed
- Failed upload: inspect upload logs, verify disk space and permissions
- Suspected data leakage: rotate `TRUELINE_OBS_TOKEN`, audit `request_audit.jsonl`, and escalate to security

11) Pre-deploy checklist
- `git status` clean
- `python -m py_compile backend\main.py`
- `npm run build` from `web`
- Verify Vercel / deployment root is `web` and Render env vars set

12) Rollback note
- Use `git log` and redeploy previous known-good commit if needed

Keep this section concise and internal; do not expose observability tokens or audit files publicly.
