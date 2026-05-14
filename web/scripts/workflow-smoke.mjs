#!/usr/bin/env node
/**
 * workflow-smoke.mjs — Read-only smoke test of deployed TrueLine workflow endpoints.
 *
 * Logs in, stores the access token, then probes every critical API route and
 * writes a JSON + HTML report to web/smoke-reports/.
 *
 * Usage:
 *   SMOKE_BASE_URL=https://osp-redlining.vercel.app \
 *   SMOKE_EMAIL=user@example.com \
 *   SMOKE_PASSWORD=secret \
 *   node scripts/workflow-smoke.mjs
 *
 * Optional:
 *   SMOKE_PROJECT_ID=<uuid>   appended as ?project_id=... to state/photo routes
 */

import { mkdirSync, writeFileSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const WEB_ROOT   = join(__dirname, "..");
const REPORT_DIR = join(WEB_ROOT, "smoke-reports");

// ── Config ──────────────────────────────────────────────────────────────────

const BASE_URL   = (process.env.SMOKE_BASE_URL || "https://osp-redlining.vercel.app").replace(/\/+$/, "");
const EMAIL      = process.env.SMOKE_EMAIL;
const PASSWORD   = process.env.SMOKE_PASSWORD;
const PROJECT_ID = process.env.SMOKE_PROJECT_ID || null;

if (!EMAIL || !PASSWORD) {
  console.error("ERROR: SMOKE_EMAIL and SMOKE_PASSWORD are required.");
  console.error("Usage: SMOKE_EMAIL=user@example.com SMOKE_PASSWORD=secret npm run smoke:workflow");
  process.exit(2);
}

// ── Auth state ───────────────────────────────────────────────────────────────

let accessToken  = null;
const cookieJar  = new Map(); // name → value

function parseCookies(raw) {
  if (!raw) return;
  const headers = Array.isArray(raw) ? raw : [raw];
  for (const h of headers) {
    const [pair] = h.split(";");
    const eq = pair.indexOf("=");
    if (eq < 0) continue;
    cookieJar.set(pair.slice(0, eq).trim(), pair.slice(eq + 1).trim());
  }
}

function cookieHeader() {
  return [...cookieJar.entries()].map(([k, v]) => `${k}=${v}`).join("; ");
}

// ── Classification ───────────────────────────────────────────────────────────
//
// OK            — 2xx + JSON body
// AUTH_FAIL     — 401 or 403
// MISSING_PROXY — HTML body (Vercel served its own 404/error page; no route.ts)
// BACKEND_500   — 5xx forwarded from backend
// NON_JSON      — non-HTML non-JSON body on a non-2xx status
// NOT_FOUND     — 404 + JSON (proxy exists, backend has no data for current state)
// UNKNOWN       — anything else

function classify(status, isJson, contentType) {
  const ct = (contentType || "").toLowerCase();
  if (status === 401 || status === 403) return "AUTH_FAIL";
  if (ct.includes("text/html") || ct.includes("application/xhtml")) return "MISSING_PROXY";
  if (status === 404 && !isJson) return "MISSING_PROXY";
  if (status === 404)            return "NOT_FOUND";
  if ((status === 500 || status === 502 || status === 503 || status === 504) && !isJson) return "NON_JSON";
  if (status === 500 || status === 502 || status === 503 || status === 504)              return "BACKEND_500";
  if (status >= 200 && status < 300 && isJson)  return "OK";
  if (status >= 200 && status < 300 && !isJson) return "NON_JSON";
  return "UNKNOWN";
}

// ── Probe ────────────────────────────────────────────────────────────────────

async function probe({ label, method = "GET", path, extraHeaders = {}, body = undefined, critical = true }) {
  const url = `${BASE_URL}${path}`;

  const headers = { ...extraHeaders };
  if (accessToken)          headers["Authorization"] = `Bearer ${accessToken}`;
  const ck = cookieHeader();
  if (ck)                   headers["Cookie"] = ck;

  let status = 0, statusText = "NETWORK_ERROR", contentType = "(none)";
  let setCookieRaw = null, responseText = "";
  let isJson = false, parsed = null;
  const t0 = Date.now();

  try {
    const res = await fetch(url, { method, headers, body });
    status      = res.status;
    statusText  = res.statusText;
    contentType = res.headers.get("content-type") || "(none)";
    setCookieRaw = res.headers.get("set-cookie");
    responseText = await res.text();
    if (setCookieRaw) parseCookies(setCookieRaw);
  } catch (err) {
    responseText = err.message;
  }

  try   { parsed = JSON.parse(responseText); isJson = true; }
  catch { isJson = false; }

  const durationMs     = Date.now() - t0;
  const classification = classify(status, isJson, contentType);
  const bodyPreview    = responseText.substring(0, 500);

  return { label, method, url, path, critical, status, statusText, contentType, isJson, parsed, bodyPreview, classification, durationMs };
}

// ── Console output ───────────────────────────────────────────────────────────

const STATUS_ICONS = { OK: "✓", NOT_FOUND: "~", AUTH_FAIL: "✗", MISSING_PROXY: "✗", BACKEND_500: "✗", NON_JSON: "✗", UNKNOWN: "?" };

function printResult(r) {
  const icon    = STATUS_ICONS[r.classification] ?? "?";
  const nc      = r.critical ? "" : " [non-critical]";
  const detail  = r.isJson ? (r.parsed?.detail || r.parsed?.error || r.parsed?.message || "") : "";
  console.log(`\n  ${icon} ${r.classification}${nc}  ${r.method} ${r.path}  →  ${r.status} ${r.statusText}  (${r.durationMs}ms)`);
  console.log(`    Content-Type : ${r.contentType}`);
  console.log(`    JSON valid   : ${r.isJson ? "yes" : "no"}`);
  if (detail)   console.log(`    Detail       : ${detail}`);
  console.log(`    Body (500ch) : ${r.bodyPreview}`);
}

// ── HTML report ───────────────────────────────────────────────────────────────

function esc(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

const COLORS = {
  OK: "#1a9e5c", NOT_FOUND: "#7f8c8d",
  AUTH_FAIL: "#c0392b", MISSING_PROXY: "#c0392b",
  BACKEND_500: "#c0392b", NON_JSON: "#e67e22", UNKNOWN: "#7f8c8d",
};

function buildHtml(results, meta) {
  const criticalFails = results.filter(r => r.critical && CRITICAL_FAIL_CLASSES.has(r.classification));

  const rows = results.map(r => `
    <tr>
      <td style="color:${COLORS[r.classification] ?? "#555"};font-weight:bold">${esc(r.classification)}</td>
      <td><code>${esc(r.method)}</code></td>
      <td><code>${esc(r.path)}</code></td>
      <td>${esc(r.status)}</td>
      <td style="color:${r.isJson ? "#1a9e5c" : "#c0392b"}">${r.isJson ? "yes" : "no"}</td>
      <td>${esc(r.durationMs)}ms</td>
      <td style="font-size:11px;max-width:380px;word-break:break-all">${esc(r.bodyPreview)}</td>
    </tr>`).join("");

  const failBox = criticalFails.length > 0
    ? `<div class="fail-box"><h3>Critical Failures (${criticalFails.length})</h3>
       ${criticalFails.map(r => `<code>${esc(r.classification)} — ${esc(r.method)} ${esc(r.path)} — HTTP ${r.status}</code>`).join("")}
       </div>`
    : `<div class="ok-box">All critical routes passed.</div>`;

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>TrueLine Workflow Smoke</title>
<style>
  body{font-family:system-ui,sans-serif;margin:2rem;background:#f5f5f5;color:#2c3e50}
  h1{margin:0 0 .5rem}
  .meta{color:#555;font-size:13px;margin-bottom:1rem}
  table{border-collapse:collapse;width:100%;background:#fff;border-radius:6px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.1)}
  th{background:#2c3e50;color:#fff;text-align:left;padding:8px 12px;font-size:13px}
  td{padding:7px 12px;border-bottom:1px solid #eee;font-size:12px;vertical-align:top}
  tr:last-child td{border-bottom:none}
  .fail-box{background:#fdf0f0;border:1px solid #e74c3c;border-radius:6px;padding:1rem;margin-bottom:1.5rem}
  .fail-box h3{margin:0 0 .5rem;color:#c0392b}
  .fail-box code{display:block;font-size:12px;color:#555;margin:2px 0}
  .ok-box{background:#eafaf1;border:1px solid #1a9e5c;border-radius:6px;padding:1rem;margin-bottom:1.5rem;color:#1a9e5c;font-weight:bold}
</style>
</head>
<body>
<h1>TrueLine Workflow Smoke Report</h1>
<div class="meta">
  <strong>Run at:</strong> ${esc(meta.runAt)} &nbsp;|&nbsp;
  <strong>Base URL:</strong> ${esc(meta.baseUrl)} &nbsp;|&nbsp;
  <strong>Email:</strong> ${esc(meta.email)} &nbsp;|&nbsp;
  <strong>Login:</strong> ${esc(meta.loginStatus)} &nbsp;|&nbsp;
  <strong>Project ID:</strong> ${esc(meta.projectId ?? "(none)")}
</div>
${failBox}
<table>
  <thead>
    <tr><th>Classification</th><th>Method</th><th>Path</th><th>Status</th><th>JSON</th><th>Time</th><th>Body Preview</th></tr>
  </thead>
  <tbody>${rows}</tbody>
</table>
</body>
</html>`;
}

// ── Critical-fail class set ───────────────────────────────────────────────────

const CRITICAL_FAIL_CLASSES = new Set(["AUTH_FAIL", "MISSING_PROXY", "BACKEND_500", "NON_JSON"]);

// ── Main ──────────────────────────────────────────────────────────────────────

const runAt = new Date().toISOString();
const results = [];
let loginStatus = "not_attempted";

console.log("\n╔══════════════════════════════════════════════════════════════════╗");
console.log(  "║          TrueLine Workflow Smoke Report                         ║");
console.log(  "╚══════════════════════════════════════════════════════════════════╝");
console.log(` Base URL  : ${BASE_URL}`);
console.log(` Email     : ${EMAIL}`);
console.log(` Project ID: ${PROJECT_ID ?? "(none — using session default)"}`);

// ── 1. Login ─────────────────────────────────────────────────────────────────

console.log("\n── 1. Login ──────────────────────────────────────────────────────");

const loginResult = await probe({
  label:        "POST /api/auth/login",
  method:       "POST",
  path:         "/api/auth/login",
  extraHeaders: { "Content-Type": "application/json" },
  body:         JSON.stringify({ email: EMAIL, password: PASSWORD }),
  critical:     true,
});
printResult(loginResult);
results.push(loginResult);

if (loginResult.isJson && loginResult.parsed?.access_token) {
  accessToken = loginResult.parsed.access_token;
  loginStatus = "ok";
  console.log(`\n  → Access token stored (${accessToken.substring(0, 20)}...)`);
  if (cookieJar.size > 0) {
    console.log(`  → Cookies captured: ${[...cookieJar.keys()].join(", ")}`);
  }
} else {
  loginStatus = `failed_${loginResult.status}`;
  console.log("\n  ⚠  Login failed — subsequent requests will be unauthenticated.");
}

// ── 2. Auth/me ────────────────────────────────────────────────────────────────

console.log("\n── 2. Auth check ────────────────────────────────────────────────");

const meResult = await probe({ label: "GET /api/auth/me", method: "GET", path: "/api/auth/me", critical: true });
printResult(meResult);
results.push(meResult);

// ── 3. Workflow routes ────────────────────────────────────────────────────────

console.log("\n── 3. Workflow routes ───────────────────────────────────────────");

const qs = PROJECT_ID ? `?project_id=${encodeURIComponent(PROJECT_ID)}` : "";

const workflowRoutes = [
  // name                                  critical   note
  { path: `/api/current-state${qs}`,        critical: true  },
  { path: `/api/engineering-plans${qs}`,    critical: true  }, // GET list; separate from upload-engineering-plans
  { path: `/api/station-photos${qs}`,       critical: true  },
  { path: `/api/engineered-segments${qs}`,  critical: true  },
  { path: `/api/walk/route-context${qs}`,   critical: true  },
  { path: `/api/nova-overrides${qs}`,       critical: true  },
];

for (const route of workflowRoutes) {
  const r = await probe({ label: `GET ${route.path}`, method: "GET", ...route });
  printResult(r);
  results.push(r);
}

// ── 4. Save reports ───────────────────────────────────────────────────────────

console.log("\n── 4. Saving reports ────────────────────────────────────────────");

mkdirSync(REPORT_DIR, { recursive: true });

const meta = { runAt, baseUrl: BASE_URL, email: EMAIL, loginStatus, projectId: PROJECT_ID };

const jsonPayload = {
  meta,
  results: results.map(({ parsed: _parsed, ...r }) => r), // drop full parsed object; bodyPreview is enough
};

const jsonPath = join(REPORT_DIR, "workflow-smoke-latest.json");
const htmlPath = join(REPORT_DIR, "workflow-smoke-latest.html");

writeFileSync(jsonPath, JSON.stringify(jsonPayload, null, 2));
writeFileSync(htmlPath, buildHtml(results, meta));

console.log("  Saved: smoke-reports/workflow-smoke-latest.json");
console.log("  Saved: smoke-reports/workflow-smoke-latest.html");

// ── 5. Summary ────────────────────────────────────────────────────────────────

const criticalFails = results.filter(r => r.critical && CRITICAL_FAIL_CLASSES.has(r.classification));
const HR = "═".repeat(68);

console.log(`\n${HR}`);
console.log(" SUMMARY");
console.log(HR);

for (const r of results) {
  const nc   = r.critical ? "         " : " [nc]    ";
  const icon = STATUS_ICONS[r.classification] ?? "?";
  console.log(` ${icon}  ${r.classification.padEnd(14)} ${nc} ${r.method.padEnd(5)} ${r.path}  →  HTTP ${r.status}`);
}

console.log("");

if (criticalFails.length === 0) {
  console.log(" All critical routes passed.");
  console.log(`\n${"─".repeat(68)}\n Exit 0`);
  process.exit(0);
}

console.log(` ${criticalFails.length} critical failure(s):`);
for (const r of criticalFails) {
  console.log(`   [${r.classification}]  ${r.method} ${r.path}  →  HTTP ${r.status}`);
}
console.log(`\n${"─".repeat(68)}\n Exit 1`);
process.exit(1);
