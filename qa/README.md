# TrueLine QA Agent System

Internal, single-command QA harness for TrueLine. Designed to be run from a
developer laptop, produce machine- and AI-readable reports, and dispatch
narrow fix prompts to Sonnet / Cursor — **never** to encourage refactors of
unrelated code.

## What it does

1. **API contract checker** — hits the routes in `config/qa.config.json`
   and verifies status codes, content-types, and JSON-ness. Detects the
   "HTML where JSON was expected" regression that has been biting us.
2. **Playwright smoke + workflow tests** — drives a real browser through
   the login → projects → uploads → closeout path. Captures console errors,
   page errors, failed network requests, screenshots, video, and traces.
3. **AI diagnosis packet** — synthesizes a structured JSON + Markdown
   document. Each confirmed failure carries: failed URL, response shape,
   suspected owner, next diagnostic step, and a ready-to-paste **Cursor /
   Sonnet fix prompt** scoped to only that failure.
4. **HTML report** — green/red banner, API contract table, failure cards,
   screenshots, guardrails, and the first fix prompt — all in one self-
   contained file.

## Directory layout

```
qa/
├── README.md                         ← this file
├── package.json                      ← Playwright + scripts
├── playwright.config.ts              ← reporter + run dir config
├── .gitignore
├── config/
│   └── qa.config.json                ← URLs, endpoints, expectations
├── fixtures/
│   └── README.md                     ← drop placeholder upload files here
├── prompts/
│   ├── fix-confirmed-failure.md      ← Cursor/Sonnet prompt template
│   └── ai-diagnosis-reader.md        ← ChatGPT/Nova reader prompt
├── reports/
│   └── <yyyy-mm-ddThhmmss>/          ← one folder per run, full artifacts
│       ├── summary.json
│       ├── api-contracts.json
│       ├── playwright-smoke.json
│       ├── playwright-workflows.json
│       ├── diagnosis-packet.json
│       ├── diagnosis-packet.md
│       ├── report.html
│       ├── screenshots/  videos/  traces/
│       └── test-signals/             ← per-test console/network capture
├── scripts/
│   ├── run-qa.mjs                    ← orchestrator (entry point)
│   ├── check-api-contracts.mjs
│   ├── make-ai-diagnosis-packet.mjs
│   ├── build-html-report.mjs
│   ├── open-latest-report.mjs
│   └── lib/run-context.mjs
└── tests/
    ├── _support/harness.ts           ← shared fixtures + error capture
    ├── trueline-smoke.spec.ts
    └── workflows/
        ├── auth.spec.ts
        ├── project-workflow.spec.ts
        ├── uploads.spec.ts
        └── closeout.spec.ts
```

## Install (Windows PowerShell)

From the repo root:

```powershell
cd qa
npm install
npm run qa:install-browsers   # one-time: downloads Chromium for Playwright
```

If you skip `qa:install-browsers`, the Playwright phases fail at runtime
with a clear "Chromium not installed" message but the API contract phase
still runs and produces a report.

## Start the app locally

The QA harness expects the frontend and backend to already be running.
Open two PowerShell windows:

**Backend (port 8000):**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Frontend (port 3000):**

```powershell
cd web
npm install
npm run dev
```

## Configure (optional)

By default the harness targets `http://localhost:3000` and
`http://127.0.0.1:8000` without credentials. Authenticated workflow tests
skip gracefully when credentials are absent — that is by design.

To exercise authenticated flows, set these before running:

```powershell
$env:QA_FRONTEND_URL  = "http://localhost:3000"
$env:QA_BACKEND_URL   = "http://127.0.0.1:8000"
$env:QA_USER_EMAIL    = "you@example.com"
$env:QA_USER_PASSWORD = "your-password"
# Optional, only if you have them:
$env:QA_PILOT_TOKEN   = "..."
$env:QA_OBS_TOKEN     = "..."
```

### Running against production

To point the harness at the deployed environment instead of localhost, set
the URL env vars to the Vercel and Render hosts. **Leave
`QA_ALLOW_MUTATION` unset** — that keeps the run to login + read-only
checks against the live tenant:

```powershell
$env:QA_FRONTEND_URL  = "https://osp-redlining.vercel.app"
$env:QA_BACKEND_URL   = "https://osp-redlining-backend.onrender.com"
$env:QA_USER_EMAIL    = "<your prod user>"
$env:QA_USER_PASSWORD = "<your prod password>"
npm run qa:all
```

The orchestrator banner prints `Target: PRODUCTION (deployed)` when the
URLs are not loopback. The `summary.json` and `diagnosis-packet.json`
record the same fact so a triage agent can tell production vs local apart.

### Mutating production (opt-in only)

Upload and other state-mutating workflow tests are **gated** behind
`QA_ALLOW_MUTATION=true` in addition to the existing fixture + credential
gates. This protects the live backend from accidental writes. Set it only
when you intend to upload to a real tenant:

```powershell
$env:QA_ALLOW_MUTATION = "true"
```

When `QA_ALLOW_MUTATION` is unset, false, or anything other than the
exact string `"true"`, the upload tests skip with a clear reason. Login
and read-only API contract checks always run — those are considered safe
against production.

## Run

One command runs the entire harness:

```powershell
cd qa
npm run qa:all
```

This executes, in order:

1. `qa:api`        — API contract checks
2. `qa:smoke`      — Playwright smoke spec
3. `qa:workflow`   — Playwright workflow specs
4. `qa:diagnose`   — synthesize AI diagnosis packet
5. `qa:report`     — render `report.html`

Each phase can also be run individually:

```powershell
npm run qa:api
npm run qa:smoke
npm run qa:workflow
npm run qa:diagnose
npm run qa:report
```

When phases are run individually, they create a fresh timestamped run dir
unless `QA_RUN_DIR` is set. The orchestrator (`qa:all`) sets that env var
once so every phase writes into the same folder.

## Read the report

After a run completes, the console prints the run directory. Open the
HTML report:

```powershell
npm run qa:open-latest
```

For ChatGPT / Nova triage, paste `diagnosis-packet.md` from the run
directory into a chat session along with `prompts/ai-diagnosis-reader.md`.

For Sonnet / Cursor fixes, copy the **Cursor / Sonnet fix prompt** block
from the top-priority failure card and paste it directly.

## Graceful degradation

The harness is built to always produce a useful report, even when the
environment is partly broken:

- Backend down → API contract checker marks each backend route as
  `backend-unreachable` with a clear next step.
- Frontend down → Playwright records page load errors; API contracts
  pointed at the frontend still produce structured output.
- No credentials → authenticated tests skip with `credentials-missing`.
- No fixture files → upload tests skip with `fixture-missing`.
- `QA_ALLOW_MUTATION` unset → upload tests skip with `QA_ALLOW_MUTATION!=true`.
- Playwright not installed → API contract phase still runs; orchestrator
  records "playwright not installed" in the summary.

Skipped tests are never silent — they always land in the diagnosis packet
with the reason.

## What this harness will not do

- It will not refactor unrelated app logic.
- It will not modify KMZ parsing/rendering or topology sidecar code.
- It will not mutate production data; all upload tests only assert that
  the **response contract** holds, never that the file was committed.
- It will not emit fix prompts for symptoms that were not reproduced by
  this run. The diagnosis packet is grounded in evidence.

## Troubleshooting

- "Chromium executable doesn't exist" → run `npm run qa:install-browsers`.
- "ECONNREFUSED on backend" → confirm `uvicorn` is listening on port 8000
  and `QA_BACKEND_URL` matches.
- Login tests skip with "credentials missing" → set `QA_USER_EMAIL` and
  `QA_USER_PASSWORD` for that PowerShell session.
- Upload tests skip with "fixture missing" → drop a tiny placeholder file
  at the path named in the skip message (see `fixtures/README.md`).
