#!/usr/bin/env node
// Builds a self-contained, human-readable HTML report from the run artifacts.
// Output: <runDir>/report.html

import fs from "node:fs";
import path from "node:path";
import { ensureRunDir, readJsonSafe } from "./lib/run-context.mjs";

const runDir = ensureRunDir();
const apiReport = readJsonSafe(path.join(runDir, "api-contracts.json"), null);
const diagnosis = readJsonSafe(path.join(runDir, "diagnosis-packet.json"), null);
const summary = readJsonSafe(path.join(runDir, "summary.json"), null);

const passed = apiReport?.totals?.passed ?? 0;
const failed =
  (apiReport?.totals?.failed ?? 0) +
  ((diagnosis?.confirmedFailures ?? []).filter((f) => f.source === "playwright").length);
const skipped = apiReport?.totals?.skipped ?? 0;

const overallGreen = failed === 0;

function esc(s) {
  if (s == null) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function statusPill(ok) {
  if (ok) {
    return `<span class="pill pill-pass">PASS</span>`;
  }
  return `<span class="pill pill-fail">FAIL</span>`;
}

const apiRows = (apiReport?.results ?? [])
  .map((r) => {
    const ok = r.pass;
    const skip = r.skipped;
    const pill = skip
      ? `<span class="pill pill-skip">SKIP</span>`
      : statusPill(ok);
    return `
    <tr class="${skip ? "skip" : ok ? "pass" : "fail"}">
      <td>${pill}</td>
      <td><code>${esc(r.method)}</code></td>
      <td><code>${esc(r.target)}</code></td>
      <td><code>${esc(r.path)}</code></td>
      <td>${r.response?.status ?? "—"}</td>
      <td>${esc(r.response?.contentType ?? "—")}</td>
      <td>${esc(r.failure?.category ?? (skip ? "skipped" : ""))}</td>
    </tr>`;
  })
  .join("");

const failureCards = (diagnosis?.confirmedFailures ?? [])
  .map((f, idx) => {
    const evidenceJson = esc(JSON.stringify(f.evidence, null, 2));
    return `
  <article class="card">
    <header>
      <span class="pill pill-fail">FAIL #${idx + 1}</span>
      <h3>${esc(f.title)}</h3>
    </header>
    <dl>
      <dt>Source</dt><dd><code>${esc(f.source)}</code></dd>
      <dt>Category</dt><dd><code>${esc(f.category)}</code></dd>
      <dt>Suspected owner</dt><dd><code>${esc(f.suspectedOwner)}</code></dd>
      <dt>Next step</dt><dd>${esc(f.nextStep)}</dd>
    </dl>
    <details>
      <summary>Raw evidence</summary>
      <pre>${evidenceJson}</pre>
    </details>
    <details open>
      <summary>Cursor / Sonnet fix prompt</summary>
      <pre class="fix-prompt">${esc(f.fixPrompt)}</pre>
    </details>
  </article>`;
  })
  .join("");

const screenshotFiles = (() => {
  const dir = path.join(runDir, "screenshots");
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir).filter((n) => /\.(png|jpg|jpeg|webp)$/i.test(n));
})();

const artifactsTmp = path.join(runDir, "_pw_artifacts");
const pwScreenshots = (() => {
  if (!fs.existsSync(artifactsTmp)) return [];
  const found = [];
  for (const entry of fs.readdirSync(artifactsTmp)) {
    const full = path.join(artifactsTmp, entry);
    if (!fs.statSync(full).isDirectory()) continue;
    for (const file of fs.readdirSync(full)) {
      if (/\.(png|jpg|jpeg|webp)$/i.test(file)) {
        found.push(path.join("_pw_artifacts", entry, file));
      }
    }
  }
  return found;
})();

const allScreenshots = [
  ...screenshotFiles.map((f) => path.join("screenshots", f)),
  ...pwScreenshots,
];

const rootCauseHint =
  diagnosis?.confirmedFailures?.[0]?.nextStep ??
  (overallGreen
    ? "All checks pass. If a bug is still reported in the wild, reproduce it under the QA harness so it is captured."
    : "Inspect the first confirmed failure card below.");

const guardrailItems = (diagnosis?.guardrails?.doNotTouch ?? [])
  .map((g) => `<li>${esc(g)}</li>`)
  .join("");

const firstFixPrompt = diagnosis?.confirmedFailures?.[0]?.fixPrompt ?? "";

const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>TrueLine QA Report — ${esc(summary?.runId ?? path.basename(runDir))}</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
  :root { color-scheme: light dark; --pass: #1b8a3a; --fail: #c0392b; --skip: #8a8a8a; --bg: #f7f7fb; --card: #ffffff; --text: #111; --muted: #555; --accent: #1f6feb; }
  @media (prefers-color-scheme: dark) { :root { --bg: #0b0f17; --card: #141924; --text: #e6ecf5; --muted: #7a8fa6; } }
  body { font-family: ui-sans-serif, system-ui, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 1.5rem; line-height: 1.45; }
  h1, h2, h3 { letter-spacing: -0.01em; }
  h1 { margin-top: 0; }
  .banner { padding: 1rem 1.25rem; border-radius: 12px; margin-bottom: 1.5rem; font-weight: 600; }
  .banner.green { background: #1b8a3a; color: white; }
  .banner.red { background: #c0392b; color: white; }
  .grid { display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); margin-bottom: 1.5rem; }
  .stat { background: var(--card); padding: 1rem; border-radius: 12px; border: 1px solid rgba(127, 127, 127, 0.2); }
  .stat .label { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em; color: var(--muted); }
  .stat .value { font-size: 1.75rem; font-weight: 700; margin-top: 0.25rem; }
  table { width: 100%; border-collapse: collapse; background: var(--card); border-radius: 12px; overflow: hidden; }
  th, td { text-align: left; padding: 0.6rem 0.75rem; border-bottom: 1px solid rgba(127, 127, 127, 0.15); font-size: 0.9rem; }
  th { background: rgba(127, 127, 127, 0.08); font-weight: 600; }
  tr.pass td { color: var(--text); }
  tr.fail td { background: rgba(192, 57, 43, 0.06); }
  tr.skip td { color: var(--muted); }
  .pill { display: inline-block; padding: 0.15rem 0.55rem; border-radius: 999px; font-size: 0.75rem; font-weight: 700; letter-spacing: 0.05em; }
  .pill-pass { background: var(--pass); color: white; }
  .pill-fail { background: var(--fail); color: white; }
  .pill-skip { background: var(--skip); color: white; }
  .card { background: var(--card); border: 1px solid rgba(127, 127, 127, 0.2); border-radius: 12px; padding: 1rem 1.25rem; margin-bottom: 1rem; }
  .card header { display: flex; gap: 0.75rem; align-items: center; margin-bottom: 0.5rem; }
  .card header h3 { margin: 0; font-size: 1.05rem; }
  dl { display: grid; grid-template-columns: max-content 1fr; gap: 0.25rem 1rem; margin: 0.5rem 0; font-size: 0.9rem; }
  dt { color: var(--muted); }
  pre { background: rgba(127, 127, 127, 0.08); padding: 0.75rem; border-radius: 8px; overflow-x: auto; font-size: 0.8rem; white-space: pre-wrap; word-break: break-word; }
  pre.fix-prompt { background: rgba(31, 111, 235, 0.08); border-left: 3px solid var(--accent); }
  details { margin-top: 0.5rem; }
  summary { cursor: pointer; font-size: 0.85rem; color: var(--muted); }
  .screenshots { display: grid; gap: 0.5rem; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); }
  .screenshots a { display: block; border: 1px solid rgba(127, 127, 127, 0.2); border-radius: 8px; overflow: hidden; }
  .screenshots img { width: 100%; height: 120px; object-fit: cover; display: block; }
  section { margin-bottom: 2rem; }
  .meta { color: var(--muted); font-size: 0.8rem; }
  ul.do-not-touch li { margin-bottom: 0.15rem; }
</style>
</head>
<body>
  <h1>TrueLine QA Report</h1>
  <p class="meta">
    Run <code>${esc(summary?.runId ?? path.basename(runDir))}</code>
    · Frontend <code>${esc(diagnosis?.environment?.frontendUrl ?? "(unset)")}</code>
    · Backend <code>${esc(diagnosis?.environment?.backendUrl ?? "(unset)")}</code>
    · Credentials ${diagnosis?.environment?.credentialsConfigured ? "configured" : "missing"}
  </p>

  <div class="banner ${overallGreen ? "green" : "red"}">
    ${overallGreen
      ? "All confirmed checks passed."
      : `${diagnosis?.confirmedFailures?.length ?? 0} confirmed failures.`}
  </div>

  <div class="grid">
    <div class="stat"><div class="label">API passed</div><div class="value">${passed}</div></div>
    <div class="stat"><div class="label">API failed</div><div class="value">${apiReport?.totals?.failed ?? 0}</div></div>
    <div class="stat"><div class="label">API skipped</div><div class="value">${skipped}</div></div>
    <div class="stat"><div class="label">Confirmed failures</div><div class="value">${diagnosis?.confirmedFailures?.length ?? 0}</div></div>
  </div>

  <section>
    <h2>Most likely root cause</h2>
    <p>${esc(rootCauseHint)}</p>
  </section>

  <section>
    <h2>API contract results</h2>
    <table>
      <thead>
        <tr><th>Status</th><th>Method</th><th>Target</th><th>Path</th><th>HTTP</th><th>Content-Type</th><th>Category</th></tr>
      </thead>
      <tbody>${apiRows || `<tr><td colspan="7">No API contract results.</td></tr>`}</tbody>
    </table>
  </section>

  <section>
    <h2>Confirmed failures</h2>
    ${failureCards || `<p class="meta">None. Either everything passed or no Playwright artifacts were produced.</p>`}
  </section>

  ${allScreenshots.length
    ? `<section><h2>Screenshots</h2><div class="screenshots">${allScreenshots
        .map((s) => `<a href="${esc(s)}" target="_blank"><img src="${esc(s)}" loading="lazy" alt="${esc(s)}" /></a>`)
        .join("")}</div></section>`
    : ""}

  <section>
    <h2>Do not touch (guardrails)</h2>
    <ul class="do-not-touch">${guardrailItems || `<li class="meta">No guardrails defined.</li>`}</ul>
  </section>

  ${firstFixPrompt ? `<section>
    <h2>First Cursor/Sonnet fix prompt</h2>
    <pre class="fix-prompt">${esc(firstFixPrompt)}</pre>
  </section>` : ""}

  <section>
    <h2>How to use this report</h2>
    <ol>
      <li>If everything is green, no action.</li>
      <li>For each red failure card, paste the <strong>Cursor/Sonnet fix prompt</strong> into your tool of choice.</li>
      <li>Run <code>npm run qa:all</code> from <code>qa/</code> again after applying fixes.</li>
      <li>For deeper triage, paste <code>diagnosis-packet.md</code> into ChatGPT/Nova.</li>
    </ol>
  </section>
</body>
</html>
`;

fs.writeFileSync(path.join(runDir, "report.html"), html, "utf8");
console.log(`Wrote ${path.relative(process.cwd(), path.join(runDir, "report.html"))}`);
