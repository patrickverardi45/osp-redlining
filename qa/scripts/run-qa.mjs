#!/usr/bin/env node
// Orchestrator: runs API contract checks, Playwright smoke + workflow tests,
// then synthesizes the AI diagnosis packet and HTML report. Each phase writes
// into the same timestamped reports/<run-id>/ folder so the user can ship the
// whole folder to ChatGPT/Nova in one paste.

import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { ensureRunDir, loadConfig, writeJson, readJsonSafe } from "./lib/run-context.mjs";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const QA_ROOT = path.resolve(__dirname, "..");

const runDir = ensureRunDir();
process.env.QA_RUN_DIR = runDir;
const config = loadConfig();

console.log("\n=================================================================");
console.log("  TrueLine QA harness");
console.log("=================================================================");
console.log(`  Frontend : ${config.resolved.frontendUrl || "(unset)"}`);
console.log(`  Backend  : ${config.resolved.backendUrl || "(unset)"}`);
console.log(`  Creds    : ${config.resolved.credentials.email ? "configured" : "missing"}`);
console.log(`  Target   : ${config.resolved.targetIsProduction ? "PRODUCTION (deployed)" : "local"}`);
console.log(`  Mutating : ${config.resolved.allowMutation ? "ALLOWED (QA_ALLOW_MUTATION=true)" : "blocked (read-only + login only)"}`);
console.log(`  Run dir  : ${runDir}`);
console.log("=================================================================\n");

if (config.resolved.targetIsProduction && config.resolved.allowMutation) {
  console.log("!  WARNING: pointing at production AND QA_ALLOW_MUTATION=true.");
  console.log("!  Upload/state-mutating tests WILL hit the live backend if fixtures exist.");
  console.log("");
}

// --- helpers --------------------------------------------------------------

function runStep(label, command, args, opts = {}) {
  return new Promise((resolve) => {
    const startedAt = new Date().toISOString();
    console.log(`▶  ${label}`);
    const child = spawn(command, args, {
      cwd: QA_ROOT,
      env: { ...process.env, QA_RUN_DIR: runDir },
      stdio: "inherit",
      shell: process.platform === "win32",
      ...opts,
    });
    child.on("close", (code) => {
      const finishedAt = new Date().toISOString();
      resolve({
        label,
        command: `${command} ${args.join(" ")}`,
        exitCode: code,
        startedAt,
        finishedAt,
      });
    });
    child.on("error", (err) => {
      const finishedAt = new Date().toISOString();
      resolve({
        label,
        command: `${command} ${args.join(" ")}`,
        exitCode: -1,
        spawnError: err.message,
        startedAt,
        finishedAt,
      });
    });
  });
}

function detectPlaywrightInstalled() {
  const moduleDir = path.join(QA_ROOT, "node_modules", "@playwright", "test");
  return fs.existsSync(moduleDir);
}

function preflight() {
  const notes = [];
  if (!detectPlaywrightInstalled()) {
    notes.push(
      "Playwright is not installed. Run `npm install` inside qa/ before re-running. " +
      "API contract checks will still execute; Playwright steps will report a skipped reason.",
    );
  }
  if (!config.resolved.frontendUrl) {
    notes.push("No frontend URL configured. Set QA_FRONTEND_URL or edit qa/config/qa.config.json.");
  }
  if (!config.resolved.backendUrl) {
    notes.push("No backend URL configured. Set QA_BACKEND_URL or edit qa/config/qa.config.json.");
  }
  if (!config.resolved.credentials.email || !config.resolved.credentials.password) {
    notes.push(
      "QA_USER_EMAIL / QA_USER_PASSWORD not set — authenticated workflow tests will skip.",
    );
  }
  return notes;
}

// --- run ------------------------------------------------------------------

const startedAt = new Date().toISOString();
const preflightNotes = preflight();
preflightNotes.forEach((n) => console.log(`!  ${n}`));
if (preflightNotes.length) console.log("");

const steps = [];

steps.push(
  await runStep("api contracts", "node", ["scripts/check-api-contracts.mjs"]),
);

if (detectPlaywrightInstalled()) {
  steps.push(
    await runStep(
      "playwright smoke",
      "npx",
      ["playwright", "test", "trueline-smoke.spec.ts"],
      {
        env: {
          ...process.env,
          QA_RUN_DIR: runDir,
          QA_PLAYWRIGHT_JSON: "playwright-smoke.json",
        },
      },
    ),
  );

  steps.push(
    await runStep(
      "playwright workflows",
      "npx",
      ["playwright", "test", "workflows"],
      {
        env: {
          ...process.env,
          QA_RUN_DIR: runDir,
          QA_PLAYWRIGHT_JSON: "playwright-workflows.json",
        },
      },
    ),
  );
} else {
  console.log("!  Skipping Playwright phases — @playwright/test not installed.\n");
  steps.push({
    label: "playwright smoke",
    command: "skipped",
    exitCode: null,
    skippedReason: "@playwright/test not installed in qa/",
    startedAt: new Date().toISOString(),
    finishedAt: new Date().toISOString(),
  });
  steps.push({
    label: "playwright workflows",
    command: "skipped",
    exitCode: null,
    skippedReason: "@playwright/test not installed in qa/",
    startedAt: new Date().toISOString(),
    finishedAt: new Date().toISOString(),
  });
}

steps.push(
  await runStep("ai diagnosis packet", "node", ["scripts/make-ai-diagnosis-packet.mjs"]),
);
steps.push(
  await runStep("html report", "node", ["scripts/build-html-report.mjs"]),
);

const finishedAt = new Date().toISOString();

// --- summary --------------------------------------------------------------

const apiResults = readJsonSafe(path.join(runDir, "api-contracts.json"), null);
const diagnosis = readJsonSafe(path.join(runDir, "diagnosis-packet.json"), null);

const summary = {
  type: "qa-run-summary",
  runId: path.basename(runDir),
  startedAt,
  finishedAt,
  environment: {
    frontendUrl: config.resolved.frontendUrl,
    backendUrl: config.resolved.backendUrl,
    credentialsConfigured: Boolean(
      config.resolved.credentials.email && config.resolved.credentials.password,
    ),
    targetIsProduction: config.resolved.targetIsProduction,
    allowMutation: config.resolved.allowMutation,
  },
  preflightNotes,
  steps,
  totals: {
    api: apiResults?.totals ?? null,
    diagnosisFailureCount: diagnosis?.confirmedFailures?.length ?? 0,
  },
  artifactsRelative: {
    apiContracts: "api-contracts.json",
    playwrightSmoke: "playwright-smoke.json",
    playwrightWorkflows: "playwright-workflows.json",
    playwrightResultsCombined: "playwright-results.json",
    diagnosisPacketJson: "diagnosis-packet.json",
    diagnosisPacketMd: "diagnosis-packet.md",
    htmlReport: "report.html",
    testSignalsDir: "test-signals",
  },
};

writeJson(path.join(runDir, "summary.json"), summary);

console.log("\n=================================================================");
console.log("  Run complete");
console.log("=================================================================");
console.log(`  Reports : ${runDir}`);
console.log(`  HTML    : ${path.join(runDir, "report.html")}`);
console.log(`  AI pack : ${path.join(runDir, "diagnosis-packet.md")}`);
console.log("");
console.log("  Next:");
console.log("    1. Open report.html in a browser for the human view.");
console.log("    2. Paste diagnosis-packet.md into ChatGPT/Nova for triage.");
console.log("    3. Hand the generated fix-prompt blocks to Sonnet/Cursor.");
console.log("=================================================================\n");
