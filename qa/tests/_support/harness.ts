// Shared Playwright fixtures: error capture + per-test artifact emission.
// Each test that uses `qaPage` gets an extended Page wrapped with listeners
// for console errors, page errors, and failed network requests. The collected
// signal is emitted alongside the standard Playwright JSON report so the
// diagnosis packet can stitch it back to the test name.

import { test as base, expect } from "@playwright/test";
import type { Page, Request, Response, ConsoleMessage } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const RUN_DIR = process.env.QA_RUN_DIR || path.resolve(__dirname, "..", "..", "reports", "_adhoc");
const SIGNALS_DIR = path.join(RUN_DIR, "test-signals");
fs.mkdirSync(SIGNALS_DIR, { recursive: true });

export type CapturedConsoleEntry = {
  type: string;
  text: string;
  location?: { url: string; lineNumber: number; columnNumber: number } | null;
  timestamp: string;
};

export type CapturedNetworkEntry = {
  url: string;
  method: string;
  status: number | null;
  contentType: string | null;
  failure: string | null;
  durationMs: number | null;
  responseBodyPreview: string | null;
  responseIsHtml: boolean | null;
  responseIsJson: boolean | null;
  timestamp: string;
};

export type CapturedPageError = {
  message: string;
  stack: string | null;
  timestamp: string;
};

export type AttemptRecord = {
  label: string;
  url: string;
  method: string;
  status: number | null;
  contentType: string | null;
  isJson: boolean | null;
  isHtml: boolean | null;
  bodyPreview: string | null;
  durationMs: number | null;
  timestamp: string;
};

export type TestSignal = {
  testTitle: string;
  testFile: string;
  startedAt: string;
  finishedAt: string | null;
  consoleErrors: CapturedConsoleEntry[];
  pageErrors: CapturedPageError[];
  failedNetwork: CapturedNetworkEntry[];
  attempts: AttemptRecord[];
  notes: string[];
};

function clip(s: string, max = 4000): string {
  if (s == null) return "";
  if (s.length <= max) return s;
  return s.slice(0, max) + `\n…[truncated ${s.length - max} bytes]`;
}

function safeTitleSlug(title: string): string {
  return title
    .replace(/[^a-z0-9_\-]/gi, "_")
    .replace(/_+/g, "_")
    .slice(0, 120);
}

type QaFixtures = {
  qaPage: Page;
  qaSignal: TestSignal;
};

export const test = base.extend<QaFixtures>({
  qaSignal: async ({}, use, testInfo) => {
    const signal: TestSignal = {
      testTitle: testInfo.title,
      testFile: testInfo.file,
      startedAt: new Date().toISOString(),
      finishedAt: null,
      consoleErrors: [],
      pageErrors: [],
      failedNetwork: [],
      attempts: [],
      notes: [],
    };
    await use(signal);
    signal.finishedAt = new Date().toISOString();
    const slug = `${safeTitleSlug(testInfo.titlePath.join("__"))}.json`;
    fs.writeFileSync(path.join(SIGNALS_DIR, slug), JSON.stringify(signal, null, 2), "utf8");
  },
  qaPage: async ({ page, qaSignal }, use) => {
    const pendingRequests = new Map<Request, number>();

    const onConsole = (msg: ConsoleMessage) => {
      if (msg.type() !== "error" && msg.type() !== "warning") return;
      // Only treat errors as failure signals — warnings are notes.
      const entry: CapturedConsoleEntry = {
        type: msg.type(),
        text: clip(msg.text(), 2000),
        location: msg.location() ? { ...msg.location() } : null,
        timestamp: new Date().toISOString(),
      };
      if (msg.type() === "error") {
        qaSignal.consoleErrors.push(entry);
      } else {
        qaSignal.notes.push(`console.warning: ${entry.text}`);
      }
    };

    const onPageError = (err: Error) => {
      qaSignal.pageErrors.push({
        message: clip(err.message, 2000),
        stack: err.stack ? clip(err.stack, 4000) : null,
        timestamp: new Date().toISOString(),
      });
    };

    const onRequest = (req: Request) => {
      pendingRequests.set(req, Date.now());
    };

    const onRequestFailed = (req: Request) => {
      const started = pendingRequests.get(req);
      pendingRequests.delete(req);
      qaSignal.failedNetwork.push({
        url: req.url(),
        method: req.method(),
        status: null,
        contentType: null,
        failure: req.failure()?.errorText ?? "request failed",
        durationMs: started ? Date.now() - started : null,
        responseBodyPreview: null,
        responseIsHtml: null,
        responseIsJson: null,
        timestamp: new Date().toISOString(),
      });
    };

    const onResponse = async (res: Response) => {
      const req = res.request();
      const started = pendingRequests.get(req);
      pendingRequests.delete(req);
      const status = res.status();
      // Capture only "interesting" responses to keep signal noise low.
      const url = res.url();
      const isApiCall = url.includes("/api/") || url.includes("/auth/");
      const isError = status >= 400;
      if (!isApiCall && !isError) return;

      const contentType = res.headers()["content-type"] ?? null;
      let bodyPreview: string | null = null;
      let isHtml = false;
      let isJson = false;
      try {
        const text = await res.text();
        bodyPreview = clip(text, 2000);
        const trimmed = text.trim().toLowerCase();
        isHtml =
          trimmed.startsWith("<!doctype html") ||
          trimmed.startsWith("<html") ||
          trimmed.includes("<head") ||
          trimmed.includes("<body");
        try {
          JSON.parse(text);
          isJson = true;
        } catch {
          isJson = false;
        }
      } catch {
        // Some responses cannot be read after navigation; ignore.
      }

      if (isError || (isApiCall && isHtml)) {
        qaSignal.failedNetwork.push({
          url,
          method: req.method(),
          status,
          contentType,
          failure: isError
            ? `HTTP ${status}`
            : isHtml
            ? "API returned HTML"
            : null,
          durationMs: started ? Date.now() - started : null,
          responseBodyPreview: bodyPreview,
          responseIsHtml: isHtml,
          responseIsJson: isJson,
          timestamp: new Date().toISOString(),
        });
      }
    };

    page.on("console", onConsole);
    page.on("pageerror", onPageError);
    page.on("request", onRequest);
    page.on("requestfailed", onRequestFailed);
    page.on("response", onResponse);

    await use(page);

    page.off("console", onConsole);
    page.off("pageerror", onPageError);
    page.off("request", onRequest);
    page.off("requestfailed", onRequestFailed);
    page.off("response", onResponse);
  },
});

export { expect };

export function loadQaConfig() {
  const configPath = path.resolve(__dirname, "..", "..", "config", "qa.config.json");
  return JSON.parse(fs.readFileSync(configPath, "utf8"));
}

export function resolveCreds() {
  return {
    email: (process.env.QA_USER_EMAIL ?? "").trim(),
    password: (process.env.QA_USER_PASSWORD ?? "").trim(),
  };
}

export function fixturePath(rel: string): string {
  return path.resolve(__dirname, "..", "..", rel);
}

export function fixtureExists(rel: string): boolean {
  try {
    return fs.statSync(fixturePath(rel)).isFile();
  } catch {
    return false;
  }
}

// Capture a single request/response attempt into the test signal so the
// diagnosis packet and HTML report carry full evidence (URL, method, status,
// content-type, first 500 chars of body). The harness only auto-captures
// failures via the page listener; uploads go through page.request and need
// this explicit hook.
export async function recordAttempt(
  signal: TestSignal,
  label: string,
  url: string,
  method: string,
  responseOrError:
    | { status(): number; headers(): Record<string, string>; text(): Promise<string> }
    | { error: Error },
  startedAtMs: number,
): Promise<AttemptRecord> {
  const durationMs = Date.now() - startedAtMs;
  if ("error" in responseOrError) {
    const record: AttemptRecord = {
      label,
      url,
      method,
      status: null,
      contentType: null,
      isJson: false,
      isHtml: false,
      bodyPreview: `network error: ${responseOrError.error.message}`,
      durationMs,
      timestamp: new Date().toISOString(),
    };
    signal.attempts.push(record);
    return record;
  }
  const res = responseOrError;
  const status = res.status();
  const headers = res.headers();
  const contentType = (headers["content-type"] ?? null) as string | null;
  let bodyText = "";
  try {
    bodyText = await res.text();
  } catch {
    bodyText = "";
  }
  const trimmed = bodyText.trim().toLowerCase();
  const isHtml =
    trimmed.startsWith("<!doctype html") ||
    trimmed.startsWith("<html") ||
    trimmed.includes("<head") ||
    trimmed.includes("<body");
  let isJson = false;
  try {
    if (bodyText) {
      JSON.parse(bodyText);
      isJson = true;
    }
  } catch {
    isJson = false;
  }
  const record: AttemptRecord = {
    label,
    url,
    method,
    status,
    contentType,
    isJson,
    isHtml,
    bodyPreview: bodyText.length > 500 ? bodyText.slice(0, 500) + `…[+${bodyText.length - 500} bytes]` : bodyText,
    durationMs,
    timestamp: new Date().toISOString(),
  };
  signal.attempts.push(record);
  return record;
}
