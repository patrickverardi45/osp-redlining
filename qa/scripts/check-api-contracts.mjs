#!/usr/bin/env node
// API contract checker. Hits each route in qa.config.json and verifies:
//   - reachability
//   - HTTP status is in the allow-list
//   - content-type matches expectation (json|html|text|…)
//   - body actually parses as JSON when JSON is required
//   - response is not a stray "HTML 404 page" from the wrong server
// Output: <runDir>/api-contracts.json
//
// Exit code is 0 even when contract checks fail — the orchestrator decides the
// overall run status. We never want this script's non-zero exit to mask a
// downstream Playwright run.

import fs from "node:fs";
import path from "node:path";
import {
  loadConfig,
  ensureRunDir,
  writeJson,
  clipBody,
  categorizeContentType,
  looksLikeJson,
  looksLikeHtml,
  suspectOwner,
  nextStepHint,
} from "./lib/run-context.mjs";

const config = loadConfig();
const runDir = ensureRunDir();
const resultsPath = path.join(runDir, "api-contracts.json");
const timeoutMs = config.timeouts?.apiCheckMs ?? 15000;

const targetBase = (target) =>
  target === "frontend" ? config.resolved.frontendUrl : config.resolved.backendUrl;

function buildHeaders(contract) {
  const headers = { Accept: "application/json, text/plain;q=0.5, */*;q=0.1" };
  if (contract.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (contract.auth === "pilot" && config.resolved.credentials.pilotToken) {
    headers["Authorization"] = `Bearer ${config.resolved.credentials.pilotToken}`;
  }
  if (contract.auth === "obs" && config.resolved.credentials.obsToken) {
    headers["Authorization"] = `Bearer ${config.resolved.credentials.obsToken}`;
  }
  return headers;
}

function classifyFailure({ contract, status, contentType, bodyText, networkError }) {
  if (networkError) {
    return contract.target === "backend" ? "backend-unreachable" : "frontend-unreachable";
  }
  if (status >= 500) return "server-error-5xx";

  const ctCategory = categorizeContentType(contentType);
  const expectCt = contract.expect?.contentType;
  const jsonRequired = contract.expect?.jsonRequired === true;

  // If we expected JSON but got HTML, that's the canonical TrueLine bug.
  if (jsonRequired && (ctCategory === "html" || looksLikeHtml(bodyText))) {
    return "html-instead-of-json";
  }
  if (jsonRequired && !looksLikeJson(bodyText)) {
    return "non-json-content-type";
  }
  if (expectCt && expectCt !== ctCategory && expectCt !== "any") {
    return "non-json-content-type";
  }

  const allowedStatuses = contract.expect?.status ?? [];
  if (allowedStatuses.length && !allowedStatuses.includes(status)) {
    return "wrong-status";
  }
  return null;
}

async function runOne(contract) {
  const url = `${targetBase(contract.target)}${contract.path}`;
  const started = Date.now();
  const result = {
    id: contract.id,
    target: contract.target,
    method: contract.method,
    path: contract.path,
    url,
    tags: contract.tags ?? [],
    notes: contract.notes ?? null,
    pass: false,
    skipped: false,
    durationMs: 0,
    request: {
      headers: null,
      bodyPreview: contract.body !== undefined ? clipBody(JSON.stringify(contract.body), 500) : null,
    },
    response: {
      status: null,
      contentType: null,
      contentTypeCategory: null,
      isJson: null,
      isHtml: null,
      bodyPreview: null,
      headers: null,
    },
    networkError: null,
    failure: null,
  };

  if (!targetBase(contract.target)) {
    result.skipped = true;
    result.failure = {
      category: "config-missing",
      message: `No URL configured for target=${contract.target}`,
      nextStep: "Set QA_FRONTEND_URL / QA_BACKEND_URL or update qa/config/qa.config.json.",
    };
    return result;
  }

  const headers = buildHeaders(contract);
  result.request.headers = headers;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const init = {
      method: contract.method,
      headers,
      signal: controller.signal,
      redirect: "manual",
    };
    if (contract.body !== undefined) {
      init.body = JSON.stringify(contract.body);
    }
    const response = await fetch(url, init);
    const contentType = response.headers.get("content-type");
    const bodyText = await response.text();

    result.response.status = response.status;
    result.response.contentType = contentType;
    result.response.contentTypeCategory = categorizeContentType(contentType);
    result.response.isJson = looksLikeJson(bodyText);
    result.response.isHtml = looksLikeHtml(bodyText);
    result.response.bodyPreview = clipBody(bodyText, 4000);
    result.response.headers = Object.fromEntries(response.headers.entries());
    result.durationMs = Date.now() - started;

    const failCategory = classifyFailure({
      contract,
      status: response.status,
      contentType,
      bodyText,
    });

    if (!failCategory) {
      result.pass = true;
    } else {
      const failure = {
        category: failCategory,
        message: `Contract ${contract.id} failed: ${failCategory}`,
        failedUrl: url,
        method: contract.method,
        responseStatus: response.status,
        responseContentType: contentType,
        responseIsJson: result.response.isJson,
        responseIsHtml: result.response.isHtml,
        responseBodyPreview: result.response.bodyPreview,
        expected: contract.expect,
        suspectedOwner: suspectOwner({ failedUrl: url }),
      };
      failure.nextStep = nextStepHint(failure);
      result.failure = failure;
    }
  } catch (error) {
    result.durationMs = Date.now() - started;
    result.networkError = {
      name: error.name,
      message: error.message,
      cause: error.cause?.code ?? error.cause?.message ?? null,
    };
    const failure = {
      category: contract.target === "backend" ? "backend-unreachable" : "frontend-unreachable",
      message: `Network error contacting ${url}: ${error.message}`,
      failedUrl: url,
      method: contract.method,
      suspectedOwner: suspectOwner({ failedUrl: url }),
    };
    failure.nextStep = nextStepHint(failure);
    result.failure = failure;
  } finally {
    clearTimeout(timer);
  }

  return result;
}

async function main() {
  const startedAt = new Date().toISOString();
  const results = [];
  for (const contract of config.apiContracts) {
    process.stdout.write(`  api: ${contract.method.padEnd(6)} ${contract.target.padEnd(9)} ${contract.path} … `);
    const result = await runOne(contract);
    results.push(result);
    if (result.skipped) {
      process.stdout.write("SKIPPED\n");
    } else if (result.pass) {
      process.stdout.write(`OK (${result.response.status})\n`);
    } else {
      process.stdout.write(`FAIL (${result.failure?.category ?? "unknown"})\n`);
    }
  }

  const passed = results.filter((r) => r.pass).length;
  const failed = results.filter((r) => !r.pass && !r.skipped).length;
  const skipped = results.filter((r) => r.skipped).length;

  const payload = {
    type: "api-contracts",
    startedAt,
    finishedAt: new Date().toISOString(),
    environment: {
      frontendUrl: config.resolved.frontendUrl,
      backendUrl: config.resolved.backendUrl,
      credentialsConfigured: Boolean(
        config.resolved.credentials.email && config.resolved.credentials.password,
      ),
      pilotTokenConfigured: Boolean(config.resolved.credentials.pilotToken),
    },
    totals: { total: results.length, passed, failed, skipped },
    results,
  };

  writeJson(resultsPath, payload);
  console.log(`\nAPI contracts: ${passed} passed, ${failed} failed, ${skipped} skipped`);
  console.log(`Wrote ${path.relative(process.cwd(), resultsPath)}`);
}

main().catch((err) => {
  console.error("check-api-contracts.mjs crashed:", err);
  // Still write a minimal artifact so the orchestrator can report it.
  try {
    writeJson(resultsPath, {
      type: "api-contracts",
      crashed: true,
      error: { name: err.name, message: err.message, stack: err.stack },
    });
  } catch {
    /* ignore */
  }
  process.exit(0);
});
