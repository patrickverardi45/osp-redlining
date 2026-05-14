// Shared run-context helpers. Resolves the QA config + timestamped reports
// directory. All scripts read/write the same run when QA_RUN_DIR is set.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export const QA_ROOT = path.resolve(__dirname, "..", "..");
export const REPORTS_ROOT = path.join(QA_ROOT, "reports");
export const CONFIG_PATH = path.join(QA_ROOT, "config", "qa.config.json");

export function loadConfig() {
  const raw = fs.readFileSync(CONFIG_PATH, "utf8");
  const cfg = JSON.parse(raw);
  cfg.resolved = resolveEnvBlock(cfg.env);
  return cfg;
}

function resolveEnvBlock(envBlock) {
  const pick = (entry) => {
    if (!entry) return "";
    const fromEnv = entry.envVar ? process.env[entry.envVar] : undefined;
    return (fromEnv ?? entry.default ?? "").trim();
  };
  return {
    frontendUrl: stripTrailingSlash(pick(envBlock.frontendUrl)),
    backendUrl: stripTrailingSlash(pick(envBlock.backendUrl)),
    credentials: {
      email: pick(envBlock.credentials?.email),
      password: pick(envBlock.credentials?.password),
      pilotToken: pick(envBlock.credentials?.pilotToken),
      obsToken: pick(envBlock.credentials?.obsToken),
    },
    allowMutation: pick(envBlock.allowMutation).toLowerCase() === "true",
    targetIsProduction: isProductionUrl(pick(envBlock.frontendUrl)) || isProductionUrl(pick(envBlock.backendUrl)),
  };
}

function isProductionUrl(url) {
  if (!url) return false;
  const u = url.toLowerCase();
  if (u.includes("localhost") || u.includes("127.0.0.1") || u.includes("0.0.0.0")) return false;
  return u.startsWith("http://") || u.startsWith("https://");
}

function stripTrailingSlash(s) {
  return (s || "").replace(/\/+$/, "");
}

export function timestampSlug(date = new Date()) {
  // ISO-ish, filesystem-safe, sortable. Example: 2026-05-13T143527
  const pad = (n) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`
  );
}

export function ensureRunDir() {
  // Respect orchestrator-supplied dir so all phases write to the same folder.
  if (process.env.QA_RUN_DIR) {
    const dir = process.env.QA_RUN_DIR;
    fs.mkdirSync(dir, { recursive: true });
    fs.mkdirSync(path.join(dir, "screenshots"), { recursive: true });
    fs.mkdirSync(path.join(dir, "videos"), { recursive: true });
    fs.mkdirSync(path.join(dir, "traces"), { recursive: true });
    return dir;
  }
  fs.mkdirSync(REPORTS_ROOT, { recursive: true });
  const dir = path.join(REPORTS_ROOT, timestampSlug());
  fs.mkdirSync(dir, { recursive: true });
  fs.mkdirSync(path.join(dir, "screenshots"), { recursive: true });
  fs.mkdirSync(path.join(dir, "videos"), { recursive: true });
  fs.mkdirSync(path.join(dir, "traces"), { recursive: true });
  process.env.QA_RUN_DIR = dir;
  return dir;
}

export function writeJson(filePath, value) {
  fs.writeFileSync(filePath, JSON.stringify(value, null, 2), "utf8");
}

export function readJsonSafe(filePath, fallback = null) {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch {
    return fallback;
  }
}

export function latestRunDir() {
  if (!fs.existsSync(REPORTS_ROOT)) return null;
  const candidates = fs
    .readdirSync(REPORTS_ROOT)
    .filter((name) => /^\d{4}-\d{2}-\d{2}T\d{6}$/.test(name))
    .map((name) => ({ name, full: path.join(REPORTS_ROOT, name) }))
    .filter((e) => fs.statSync(e.full).isDirectory())
    .sort((a, b) => (a.name < b.name ? 1 : -1));
  return candidates[0]?.full ?? null;
}

export function clipBody(text, maxLen = 4000) {
  if (text == null) return "";
  const s = typeof text === "string" ? text : String(text);
  if (s.length <= maxLen) return s;
  return s.slice(0, maxLen) + `\n…[truncated ${s.length - maxLen} bytes]`;
}

export function categorizeContentType(contentType) {
  const ct = (contentType || "").toLowerCase();
  if (ct.includes("application/json")) return "json";
  if (ct.includes("text/html")) return "html";
  if (ct.includes("text/plain")) return "text";
  if (ct.includes("application/xml") || ct.includes("text/xml")) return "xml";
  if (ct === "") return "unknown";
  return "other";
}

export function looksLikeJson(body) {
  if (!body) return false;
  const trimmed = body.trim();
  if (!trimmed) return false;
  if (!(trimmed.startsWith("{") || trimmed.startsWith("["))) return false;
  try {
    JSON.parse(trimmed);
    return true;
  } catch {
    return false;
  }
}

export function looksLikeHtml(body) {
  if (!body) return false;
  const trimmed = body.trim().toLowerCase();
  return (
    trimmed.startsWith("<!doctype html") ||
    trimmed.startsWith("<html") ||
    trimmed.includes("<head") ||
    trimmed.includes("<body")
  );
}

export function nextStepHint(failure) {
  switch (failure.category) {
    case "html-instead-of-json":
      return "Frontend likely returned a 404/500 HTML page where a Next.js API route was expected. Verify the route file exists, exports the right HTTP verb, and that the proxy helper does not throw before responding with JSON.";
    case "backend-unreachable":
      return "Backend is not reachable from the orchestrator. Confirm uvicorn is running on QA_BACKEND_URL and that no firewall is blocking the loopback port.";
    case "frontend-unreachable":
      return "Frontend is not reachable from the orchestrator. Confirm `next dev` is running on QA_FRONTEND_URL (default http://localhost:3000) and no other process is bound to that port.";
    case "wrong-status":
      return "Endpoint reachable but returned an unexpected status. Inspect server logs for traceback; check the route's auth dependency and request schema validation.";
    case "non-json-content-type":
      return "Endpoint returned a 2xx/4xx but the content-type is not JSON. Either the route is misconfigured or an upstream proxy is rewriting the response.";
    case "server-error-5xx":
      return "Backend raised an unhandled exception. Check the request_audit middleware log (backend/uploads/request_audit.jsonl) and the FastAPI traceback in the uvicorn console.";
    case "console-error":
      return "Frontend logged a runtime error. Open DevTools console at the failing page and trace the originating component.";
    case "page-load-failed":
      return "Playwright could not reach the page. Confirm the frontend dev server is up and that the route exists.";
    case "fixture-missing":
      return "Test skipped because a fixture file is missing. Drop a small valid file at the path in qa/fixtures/ to enable this workflow.";
    case "credentials-missing":
      return "Test skipped because login credentials were not provided. Set QA_USER_EMAIL / QA_USER_PASSWORD before re-running.";
    default:
      return "Inspect the captured request, response, and console logs for the failing test.";
  }
}

export function suspectOwner(failure) {
  const p = (failure.failedUrl || failure.path || "").toLowerCase();
  if (p.includes("/auth/")) return "auth";
  if (p.includes("upload-engineering")) return "upload:engineering";
  if (p.includes("station-photos")) return "upload:station-photos";
  if (p.includes("kmz") || p.includes("upload-design")) return "upload:kmz";
  if (p.includes("closeout")) return "closeout";
  if (p.includes("report") || p.includes("export")) return "export";
  if (p.includes("current-state") || p.includes("/api/")) return "backend";
  if (p.startsWith("http") && !p.includes("/api/")) return "frontend-route";
  return "unknown";
}
