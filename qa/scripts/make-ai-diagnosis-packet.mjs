#!/usr/bin/env node
// Synthesizes diagnosis-packet.json and diagnosis-packet.md from the
// outputs of check-api-contracts.mjs and Playwright. The packet is the
// thing the user pastes into ChatGPT/Nova in another session.

import fs from "node:fs";
import path from "node:path";
import {
  loadConfig,
  ensureRunDir,
  writeJson,
  readJsonSafe,
  nextStepHint,
  suspectOwner,
  clipBody,
} from "./lib/run-context.mjs";

const config = loadConfig();
const runDir = ensureRunDir();
const apiPath = path.join(runDir, "api-contracts.json");
const smokePath = path.join(runDir, "playwright-smoke.json");
const workflowsPath = path.join(runDir, "playwright-workflows.json");
const combinedPwPath = path.join(runDir, "playwright-results.json");
const signalsDir = path.join(runDir, "test-signals");
const outJsonPath = path.join(runDir, "diagnosis-packet.json");
const outMdPath = path.join(runDir, "diagnosis-packet.md");

const apiReport = readJsonSafe(apiPath, null);
const smokeReport = readJsonSafe(smokePath, null);
const workflowsReport = readJsonSafe(workflowsPath, null);
const combinedReport = readJsonSafe(combinedPwPath, null);
const testSignals = loadTestSignals(signalsDir);

function loadTestSignals(dir) {
  if (!fs.existsSync(dir)) return [];
  const out = [];
  for (const name of fs.readdirSync(dir)) {
    if (!name.endsWith(".json")) continue;
    const parsed = readJsonSafe(path.join(dir, name), null);
    if (parsed) out.push(parsed);
  }
  return out;
}

function flattenPwResults(report) {
  if (!report) return [];
  const tests = [];
  const walk = (suite, parents = []) => {
    if (!suite) return;
    const title = suite.title ?? suite.name ?? "";
    const newParents = title ? [...parents, title] : parents;
    for (const spec of suite.specs ?? []) {
      for (const t of spec.tests ?? []) {
        for (const result of t.results ?? []) {
          tests.push({
            title: spec.title,
            fullTitle: [...newParents, spec.title].join(" › "),
            file: spec.file ?? suite.file ?? null,
            status: result.status,
            error: result.error ?? null,
            errors: result.errors ?? [],
            duration: result.duration ?? null,
            attachments: result.attachments ?? [],
            stdout: (result.stdout ?? []).map((s) => s.text ?? s).join(""),
            stderr: (result.stderr ?? []).map((s) => s.text ?? s).join(""),
          });
        }
      }
    }
    for (const child of suite.suites ?? []) {
      walk(child, newParents);
    }
  };
  for (const root of report.suites ?? []) walk(root);
  return tests;
}

const pwTests = [
  ...flattenPwResults(smokeReport),
  ...flattenPwResults(workflowsReport),
  ...flattenPwResults(combinedReport),
];

// Confirmed failures = API contract failures + non-passing PW tests.
const confirmedFailures = [];

if (apiReport?.results) {
  for (const r of apiReport.results) {
    if (r.pass || r.skipped) continue;
    confirmedFailures.push({
      source: "api-contract",
      id: r.id,
      title: `${r.method} ${r.path}`,
      category: r.failure?.category ?? "unknown",
      suspectedOwner: r.failure?.suspectedOwner ?? suspectOwner({ failedUrl: r.url }),
      evidence: {
        failedUrl: r.url,
        method: r.method,
        responseStatus: r.response.status,
        responseContentType: r.response.contentType,
        responseIsJson: r.response.isJson,
        responseIsHtml: r.response.isHtml,
        responseBodyPreview: r.response.bodyPreview,
        networkError: r.networkError,
        expected: r.failure?.expected ?? null,
        notes: r.notes,
      },
      nextStep: r.failure?.nextStep ?? nextStepHint(r.failure ?? {}),
      fixPrompt: buildFixPrompt({
        source: "api-contract",
        title: `${r.method} ${r.path}`,
        category: r.failure?.category,
        evidence: r,
      }),
    });
  }
}

for (const t of pwTests) {
  if (t.status === "passed" || t.status === "skipped" || t.status === "interrupted") continue;
  const matchedSignal = testSignals.find(
    (s) => s.testTitle === t.title || s.testFile === t.file,
  );
  const category = inferPwCategory(t, matchedSignal);
  const errMsg = t.error?.message || t.errors?.[0]?.message || "Playwright test failed";
  confirmedFailures.push({
    source: "playwright",
    id: t.fullTitle,
    title: t.fullTitle,
    category,
    suspectedOwner: suspectOwner({
      failedUrl:
        matchedSignal?.attempts?.find((a) => (a.status ?? 0) >= 400 || a.isHtml)?.url ??
        matchedSignal?.failedNetwork?.[0]?.url ??
        "",
    }),
    evidence: {
      file: t.file,
      status: t.status,
      durationMs: t.duration,
      errorMessage: clipBody(errMsg, 2000),
      errorStack: clipBody(t.error?.stack ?? "", 4000),
      stderr: clipBody(t.stderr, 2000),
      consoleErrors: matchedSignal?.consoleErrors ?? [],
      pageErrors: matchedSignal?.pageErrors ?? [],
      failedNetwork: matchedSignal?.failedNetwork ?? [],
      attempts: matchedSignal?.attempts ?? [],
      notes: matchedSignal?.notes ?? [],
      attachments: (t.attachments ?? []).map((a) => ({
        name: a.name,
        contentType: a.contentType,
        path: a.path,
      })),
    },
    nextStep: nextStepHint({ category }),
    fixPrompt: buildFixPrompt({
      source: "playwright",
      title: t.fullTitle,
      category,
      evidence: { ...t, signal: matchedSignal },
    }),
  });
}

function inferPwCategory(t, signal) {
  const msg = (t.error?.message || "").toLowerCase();
  if (signal?.attempts?.some((a) => a.isHtml)) return "html-instead-of-json";
  if (signal?.attempts?.some((a) => (a.status ?? 0) >= 500)) return "server-error-5xx";
  if (signal?.attempts?.some((a) => (a.status ?? 0) >= 400 && !a.isJson)) return "non-json-content-type";
  if (signal?.failedNetwork?.some((n) => n.responseIsHtml)) return "html-instead-of-json";
  if (signal?.failedNetwork?.some((n) => (n.status ?? 0) >= 500)) return "server-error-5xx";
  if (signal?.pageErrors?.length) return "page-load-failed";
  if (signal?.consoleErrors?.length) return "console-error";
  if (msg.includes("net::err") || msg.includes("econnrefused")) return "page-load-failed";
  if (msg.includes("timeout") || msg.includes("waiting for")) return "wrong-status";
  return "playwright-assertion-failed";
}

function buildFixPrompt({ source, title, category, evidence }) {
  const guardrails = config.guardrails?.doNotTouch ?? [];
  const guardrailBlock = guardrails.length
    ? `\nDO NOT TOUCH:\n` + guardrails.map((g) => `  - ${g}`).join("\n")
    : "";
  const evidencePreview =
    source === "api-contract"
      ? `\nEvidence (API contract):\n` +
        `  URL: ${evidence.url}\n` +
        `  Method: ${evidence.method}\n` +
        `  Response status: ${evidence.response?.status}\n` +
        `  Response content-type: ${evidence.response?.contentType}\n` +
        `  Response is JSON: ${evidence.response?.isJson}\n` +
        `  Response is HTML: ${evidence.response?.isHtml}\n` +
        `  Body preview: ${(evidence.response?.bodyPreview ?? "").slice(0, 500).replace(/\n/g, " ")}\n`
      : `\nEvidence (Playwright):\n` +
        `  Error: ${(evidence.error?.message ?? "").slice(0, 400)}\n` +
        `  Console errors: ${(evidence.signal?.consoleErrors ?? []).length}\n` +
        `  Page errors: ${(evidence.signal?.pageErrors ?? []).length}\n` +
        `  Failed network: ${(evidence.signal?.failedNetwork ?? []).length}\n`;

  return (
    `Fix only the confirmed failure below. Do not refactor. Do not add features. ` +
    `Preserve current behavior of all unrelated code paths. Provide full-file ` +
    `replacements only — never partial diffs. After changes, run the QA harness ` +
    `with \`npm run qa:all\` from qa/ and confirm this specific failure is gone.\n` +
    `\nConfirmed failure: ${title}` +
    `\nCategory: ${category}` +
    `\n${evidencePreview}` +
    `${guardrailBlock}\n`
  );
}

const packet = {
  type: "diagnosis-packet",
  generatedAt: new Date().toISOString(),
  runId: path.basename(runDir),
  environment: {
    frontendUrl: config.resolved.frontendUrl,
    backendUrl: config.resolved.backendUrl,
    credentialsConfigured: Boolean(
      config.resolved.credentials.email && config.resolved.credentials.password,
    ),
  },
  totals: {
    apiContracts: apiReport?.totals ?? null,
    playwrightTests: pwTests.length,
    confirmedFailures: confirmedFailures.length,
  },
  confirmedFailures,
  guardrails: config.guardrails,
  readerInstructions:
    "This is an AI-readable diagnosis packet. The 'confirmedFailures' list contains every failure that the QA harness was able to reproduce. For each failure, the 'fixPrompt' field is a ready-to-paste prompt for Sonnet/Cursor. Do not propose fixes for symptoms not represented here.",
};

writeJson(outJsonPath, packet);
fs.writeFileSync(outMdPath, renderMarkdown(packet), "utf8");
console.log(`Wrote ${path.relative(process.cwd(), outJsonPath)}`);
console.log(`Wrote ${path.relative(process.cwd(), outMdPath)}`);

function renderMarkdown(p) {
  const lines = [];
  lines.push(`# TrueLine QA Diagnosis Packet`);
  lines.push("");
  lines.push(`**Run:** \`${p.runId}\``);
  lines.push(`**Generated:** ${p.generatedAt}`);
  lines.push(`**Frontend:** ${p.environment.frontendUrl || "(unset)"}`);
  lines.push(`**Backend:** ${p.environment.backendUrl || "(unset)"}`);
  lines.push(`**Creds configured:** ${p.environment.credentialsConfigured ? "yes" : "no"}`);
  lines.push("");
  lines.push("## Summary");
  lines.push("");
  if (p.totals.apiContracts) {
    lines.push(
      `- API contract checks: ${p.totals.apiContracts.passed}/${p.totals.apiContracts.total} passed, ` +
        `${p.totals.apiContracts.failed} failed, ${p.totals.apiContracts.skipped} skipped`,
    );
  } else {
    lines.push(`- API contract checks: not run`);
  }
  lines.push(`- Playwright tests recorded: ${p.totals.playwrightTests}`);
  lines.push(`- Confirmed failures: **${p.totals.confirmedFailures}**`);
  lines.push("");

  if (p.confirmedFailures.length === 0) {
    lines.push("> No confirmed failures in this run. If you still observe a bug,");
    lines.push("> reproduce it under the QA harness so it is captured.");
    lines.push("");
  } else {
    lines.push("## Confirmed Failures");
    lines.push("");
    p.confirmedFailures.forEach((f, idx) => {
      lines.push(`### ${idx + 1}. ${f.title}`);
      lines.push("");
      lines.push(`- **Source:** ${f.source}`);
      lines.push(`- **Category:** \`${f.category}\``);
      lines.push(`- **Suspected owner:** \`${f.suspectedOwner}\``);
      lines.push(`- **Next diagnostic step:** ${f.nextStep}`);
      lines.push("");
      lines.push("**Evidence (raw):**");
      lines.push("");
      lines.push("```json");
      lines.push(JSON.stringify(f.evidence, null, 2));
      lines.push("```");
      lines.push("");
      lines.push("**Cursor / Sonnet fix prompt:**");
      lines.push("");
      lines.push("```");
      lines.push(f.fixPrompt.trim());
      lines.push("```");
      lines.push("");
    });
  }

  lines.push("## Guardrails (do not modify)");
  lines.push("");
  for (const g of p.guardrails?.doNotTouch ?? []) {
    lines.push(`- ${g}`);
  }
  lines.push("");
  lines.push("## How to read this packet");
  lines.push("");
  lines.push(p.readerInstructions);
  lines.push("");

  return lines.join("\n");
}
