// Session boundary verification tests.
// Validates the workspace state boundary contract from
// architecture/stabilization/workspace-state-boundary-v1.md
//
// Group 1 — Static enforcement (always run, no browser or auth required):
//   Grep web/src to assert the caller graph matches the contract.
//
// Group 2 — Ring buffer / browser (skip without QA_USER_EMAIL + QA_USER_PASSWORD + QA_PROJECT_URL):
//   Navigate the live app and inspect window.__truelineSessionLog.
//   QA_PROJECT_URL must point to a page that renders RedlineMap or DesignSetupPanel
//   (e.g. http://localhost:3000/projects/<id>/map).
//
// Group 3 — Mutation transitions (additionally require QA_ALLOW_MUTATION=true):
//   Trigger UI mutations and verify exactly one mutation-adopt entry is recorded.

import { test, expect, resolveCreds } from "../_support/harness";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const ALLOW_MUTATION = (process.env.QA_ALLOW_MUTATION ?? "").toLowerCase() === "true";
const MUTATION_SKIP = "QA_ALLOW_MUTATION!=true — set QA_ALLOW_MUTATION=true to enable";

// qa/tests/workflows → three levels up → TrueLine_Beta root
const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const SRC_ROOT = path.join(REPO_ROOT, "web", "src");
const SESSION_FILE = path.resolve(path.join(SRC_ROOT, "lib", "session.ts"));

// Project page URL that renders RedlineMap / DesignSetupPanel.
// Not in qa.config.json — must be supplied via env when running browser tests.
const PROJECT_URL = (process.env.QA_PROJECT_URL ?? "").trim();

type QaPageType = Parameters<Parameters<typeof test>[1]>[0]["qaPage"];

// ─── Static helpers ──────────────────────────────────────────────────────────

function findFilesMatching(dir: string, pattern: RegExp, excludePaths: string[] = []): string[] {
  const excluded = new Set(excludePaths.map((p) => path.resolve(p)));
  const hits: string[] = [];
  function walk(d: string) {
    for (const entry of fs.readdirSync(d, { withFileTypes: true })) {
      const full = path.join(d, entry.name);
      if (entry.isDirectory()) {
        walk(full);
      } else if (/\.(ts|tsx)$/.test(entry.name) && !excluded.has(path.resolve(full))) {
        try {
          if (pattern.test(fs.readFileSync(full, "utf8"))) hits.push(full);
        } catch {
          // skip unreadable
        }
      }
    }
  }
  walk(dir);
  return hits;
}

// ─── Browser helper ──────────────────────────────────────────────────────────

async function loginAndLand(page: QaPageType): Promise<boolean> {
  const { email, password } = resolveCreds();
  if (!email || !password) return false;
  await page.goto("/auth/login", { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle");
  await page.locator("#email").fill(email);
  await page.locator("#password").fill(password);
  const navPromise = page
    .waitForURL(/\/projects/, { timeout: 20_000 })
    .then(() => true)
    .catch(() => false);
  await page.locator("button[type='submit']").click();
  return navPromise;
}

// ─── Group 1: Static enforcement ─────────────────────────────────────────────

test.describe("Session boundary — static enforcement", () => {
  test("rememberSessionFromResponse has zero call sites in app source", () => {
    const callers = findFilesMatching(SRC_ROOT, /rememberSessionFromResponse/, [SESSION_FILE]);
    expect(
      callers.map((f) => path.relative(REPO_ROOT, f)),
      `rememberSessionFromResponse found outside session.ts — migrate these callers:\n` +
        callers.map((f) => `  ${path.relative(REPO_ROOT, f)}`).join("\n"),
    ).toHaveLength(0);
  });

  test("acceptSessionFromMutation is only imported in expected write-path files", () => {
    const EXPECTED = new Set(
      [
        path.join("components", "RedlineMap.tsx"),
        path.join("components", "ModernHeroMap.tsx"),
        path.join("components", "office", "DesignSetupPanel.tsx"),
        path.join("app", "walk", "page.tsx"),
      ].map((rel) => path.resolve(path.join(SRC_ROOT, rel))),
    );

    // Match import statements only — comments that mention the name (e.g. guard notes)
    // must not be counted as callers.
    const callers = findFilesMatching(SRC_ROOT, /import\s+\{[^}]*acceptSessionFromMutation/, [SESSION_FILE]);
    const unexpected = callers.filter((f) => !EXPECTED.has(path.resolve(f)));

    expect(
      unexpected.map((f) => path.relative(REPO_ROOT, f)),
      `acceptSessionFromMutation imported outside expected write-path files:\n` +
        unexpected.map((f) => `  ${path.relative(REPO_ROOT, f)}`).join("\n"),
    ).toHaveLength(0);
  });

  test("read-path components import and use appendSessionIdReadOnly", () => {
    // After Task 2 of workspace-state-boundary-v1, read-path components must
    // use appendSessionIdReadOnly (never mints) rather than appendSessionId.
    // Positive check: each file must contain the read-only accessor.
    const READ_PATH_FILES = [
      path.join(SRC_ROOT, "components", "RedlineMap.tsx"),
      path.join(SRC_ROOT, "components", "ModernHeroMap.tsx"),
      path.join(SRC_ROOT, "components", "office", "DesignSetupPanel.tsx"),
    ];

    for (const file of READ_PATH_FILES) {
      const content = fs.readFileSync(file, "utf8");
      expect(
        content,
        `${path.relative(REPO_ROOT, file)}: must import/use appendSessionIdReadOnly — ` +
          `read paths must not mint a session as a side-effect`,
      ).toContain("appendSessionIdReadOnly");
    }
  });

  test("peekSessionId and appendSessionIdReadOnly are the read-path session accessors", () => {
    // Verify session.ts exports the boundary helpers so callers can import them.
    const sessionSrc = fs.readFileSync(SESSION_FILE, "utf8");
    expect(sessionSrc).toContain("export function peekSessionId");
    expect(sessionSrc).toContain("export function appendSessionIdReadOnly");
    expect(sessionSrc).toContain("export function acceptSessionFromMutation");
  });
});

// ─── Group 2: Ring buffer / browser ──────────────────────────────────────────
//
// These tests require:
//   QA_USER_EMAIL, QA_USER_PASSWORD  — to authenticate
//   QA_PROJECT_URL                   — URL of a page rendering RedlineMap or DesignSetupPanel
//   NODE_ENV=development              — so session.ts exposes window.__truelineSessionLog
//
// Each test navigates to QA_PROJECT_URL via a full page load, which re-initialises
// the module-scoped ring buffer to empty. Read API calls should add no entries.

test.describe("Session boundary — ring buffer (requires auth + QA_PROJECT_URL)", () => {
  test("ring buffer is exposed after project page load (dev build smoke)", async ({
    qaPage,
    qaSignal,
  }) => {
    const { email, password } = resolveCreds();
    test.skip(!email || !password, "credentials missing — set QA_USER_EMAIL and QA_USER_PASSWORD");
    test.skip(
      !PROJECT_URL,
      "QA_PROJECT_URL not set — point to a URL that renders RedlineMap or DesignSetupPanel",
    );

    const loggedIn = await loginAndLand(qaPage);
    test.skip(!loggedIn, "login did not succeed");

    await qaPage.goto(PROJECT_URL, { waitUntil: "networkidle" });

    const defined = await qaPage.evaluate(
      () => Array.isArray((window as { __truelineSessionLog?: unknown }).__truelineSessionLog),
    );
    qaSignal.notes.push(`window.__truelineSessionLog defined: ${defined}`);
    test.skip(!defined, "ring buffer not exposed — requires dev build (NODE_ENV=development)");

    expect(defined).toBe(true);
  });

  test("read paths leave ring buffer empty after page load", async ({ qaPage, qaSignal }) => {
    const { email, password } = resolveCreds();
    test.skip(!email || !password, "credentials missing");
    test.skip(!PROJECT_URL, "QA_PROJECT_URL not set");

    // Login and land on /projects.
    await qaPage.goto("/auth/login", { waitUntil: "domcontentloaded" });
    await qaPage.waitForLoadState("networkidle");
    await qaPage.locator("#email").fill(email);
    await qaPage.locator("#password").fill(password);
    const navPromise = qaPage
      .waitForURL(/\/projects/, { timeout: 20_000 })
      .then(() => true)
      .catch(() => false);
    await qaPage.locator("button[type='submit']").click();
    const loggedIn = await navPromise;
    test.skip(!loggedIn, "login did not succeed");

    // Plant a known session so read components can include it on their requests.
    // localStorage persists across same-origin page navigations.
    const PLANTED = "qa-rb-read-boundary-check";
    await qaPage.evaluate((sid) => {
      localStorage.setItem("osp_session_id", sid);
    }, PLANTED);

    // Full page load to PROJECT_URL re-initialises the ring buffer to empty.
    // Read components (RedlineMap fetchState, DesignSetupPanel fetchCurrentState)
    // call appendSessionIdReadOnly / peekSessionId — neither calls acceptSessionFromMutation.
    await qaPage.goto(PROJECT_URL, { waitUntil: "networkidle" });

    const ringDefined = await qaPage.evaluate(
      () => Array.isArray((window as { __truelineSessionLog?: unknown }).__truelineSessionLog),
    );
    qaSignal.notes.push(`ring buffer exposed: ${ringDefined}`);
    test.skip(!ringDefined, "ring buffer not exposed — requires dev build");

    type RingEntry = { op: string; prev: string | null; next: string | null };
    const log: RingEntry[] = await qaPage.evaluate(
      () => (window as { __truelineSessionLog?: RingEntry[] }).__truelineSessionLog ?? [],
    );

    const rotations = log.filter((e) => e.op === "rotation");
    const adoptions = log.filter((e) => e.op === "mutation-adopt");
    qaSignal.notes.push(
      `ring buffer after reads: ${log.length} total, ` +
        `${rotations.length} rotation, ${adoptions.length} mutation-adopt`,
    );

    expect(rotations, "read API calls must not rotate the session identity").toHaveLength(0);
    expect(adoptions, "read API calls must not emit mutation-adopt entries").toHaveLength(0);

    const stored = await qaPage.evaluate(() => localStorage.getItem("osp_session_id"));
    expect(stored, "reads must not overwrite the stored session id").toBe(PLANTED);
  });
});

// ─── Group 3: Mutation transitions ───────────────────────────────────────────
//
// These tests click UI controls that trigger write API calls and verify the
// ring buffer records the expected transition op. They require:
//   QA_USER_EMAIL, QA_USER_PASSWORD, QA_ALLOW_MUTATION=true, QA_PROJECT_URL
//   NODE_ENV=development (ring buffer must be exposed)
//
// A full page.goto() re-initialises the ring buffer, so no explicit clear is needed.

test.describe("Session boundary — mutation transitions (requires auth + ALLOW_MUTATION + QA_PROJECT_URL)", () => {
  test("reset mutation records at least one mutation-adopt entry with no rotation", async ({
    qaPage,
    qaSignal,
  }) => {
    test.skip(!ALLOW_MUTATION, MUTATION_SKIP);
    const { email, password } = resolveCreds();
    test.skip(!email || !password, "credentials missing");
    test.skip(!PROJECT_URL, "QA_PROJECT_URL not set");

    const loggedIn = await loginAndLand(qaPage);
    test.skip(!loggedIn, "login did not succeed");

    await qaPage.goto(PROJECT_URL, { waitUntil: "networkidle" });

    const ringDefined = await qaPage.evaluate(
      () => Array.isArray((window as { __truelineSessionLog?: unknown }).__truelineSessionLog),
    );
    test.skip(!ringDefined, "ring buffer not exposed — requires dev build");

    // Ring buffer is empty at this point (fresh page load, no mutations yet).
    // Locate and click the reset button to trigger a write-path call.
    const resetBtn = qaPage.getByRole("button", { name: /reset/i }).first();
    const resetVisible = await resetBtn.isVisible().catch(() => false);
    test.skip(!resetVisible, "reset button not visible on QA_PROJECT_URL — check the URL");

    await resetBtn.click();
    await qaPage.waitForLoadState("networkidle");

    type RingEntry = { op: string };
    const log: RingEntry[] = await qaPage.evaluate(
      () => (window as { __truelineSessionLog?: RingEntry[] }).__truelineSessionLog ?? [],
    );

    const rotations = log.filter((e) => e.op === "rotation");
    const adoptions = log.filter((e) => e.op === "mutation-adopt");
    qaSignal.notes.push(
      `ring buffer after reset: ${log.length} total, ` +
        `${adoptions.length} mutation-adopt, ${rotations.length} rotation`,
    );

    expect(
      adoptions.length,
      "reset must record at least one mutation-adopt in the ring buffer",
    ).toBeGreaterThanOrEqual(1);
    expect(
      rotations,
      "reset must not produce a rotation — server should echo back the same session id",
    ).toHaveLength(0);
  });

  test("design upload mutation records mutation-adopt with no rotation", async ({
    qaPage,
    qaSignal,
  }) => {
    test.skip(!ALLOW_MUTATION, MUTATION_SKIP);
    const { email, password } = resolveCreds();
    test.skip(!email || !password, "credentials missing");
    test.skip(!PROJECT_URL, "QA_PROJECT_URL not set");

    const loggedIn = await loginAndLand(qaPage);
    test.skip(!loggedIn, "login did not succeed");

    await qaPage.goto(PROJECT_URL, { waitUntil: "networkidle" });

    const ringDefined = await qaPage.evaluate(
      () => Array.isArray((window as { __truelineSessionLog?: unknown }).__truelineSessionLog),
    );
    test.skip(!ringDefined, "ring buffer not exposed — requires dev build");

    // Trigger a design upload via the file input. Use a minimal placeholder KMZ.
    const uploadInput = qaPage.locator('input[type="file"][accept*="kmz"]').first();
    const inputVisible = await uploadInput.isVisible().catch(() => false);
    test.skip(!inputVisible, "KMZ file input not found on QA_PROJECT_URL — check the URL");

    const minimalKmz = Buffer.from(
      "PK\x03\x04\x14\x00\x00\x00\x08\x00" + // ZIP local file header magic
        "\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00",
    );
    await uploadInput.setInputFiles({
      name: "qa-placeholder.kmz",
      mimeType: "application/vnd.google-earth.kmz",
      buffer: minimalKmz,
    });
    await qaPage.waitForLoadState("networkidle");

    type RingEntry = { op: string };
    const log: RingEntry[] = await qaPage.evaluate(
      () => (window as { __truelineSessionLog?: RingEntry[] }).__truelineSessionLog ?? [],
    );

    const rotations = log.filter((e) => e.op === "rotation");
    const adoptions = log.filter((e) => e.op === "mutation-adopt");
    qaSignal.notes.push(
      `ring buffer after design upload: ${log.length} total, ` +
        `${adoptions.length} mutation-adopt, ${rotations.length} rotation`,
    );

    // The backend may reject a placeholder KMZ but acceptSessionFromMutation is
    // still called with whatever the response contains — assert no rotation.
    expect(adoptions.length, "upload must record at least one mutation-adopt").toBeGreaterThanOrEqual(1);
    expect(rotations, "upload must not produce a session rotation").toHaveLength(0);
  });
});
