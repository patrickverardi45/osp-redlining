// Real demo-workflow test. Drives the production UI exactly the way a human
// runs a demo: log in through the form, open a project workspace, click the
// visible buttons, drop files into the visible file inputs, and watch for the
// red error banner that direct-endpoint tests never catch.
//
// Always runs when QA_ALLOW_MUTATION=true — no silent skips. Failures must
// surface the offending step, current URL, visible banner text, screenshot,
// failed network requests, and any non-JSON API response body.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect, resolveCreds, fixturePath, fixtureExists } from "../_support/harness";
import type { AttemptRecord } from "../_support/harness";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const ALLOW_MUTATION = (process.env.QA_ALLOW_MUTATION ?? "").toLowerCase() === "true";
const FRONTEND_URL = process.env.QA_FRONTEND_URL || "http://localhost:3000";
const PROJECT_ID = (process.env.QA_DEMO_PROJECT_ID || "ph-5").trim();
const RUN_DIR = process.env.QA_RUN_DIR || path.resolve(__dirname, "..", "..", "reports", "_adhoc");
const SHOT_DIR = path.join(RUN_DIR, "screenshots", "demo-walkthrough");
const REPORT_PATH = path.join(RUN_DIR, "demo-walkthrough.json");

fs.mkdirSync(SHOT_DIR, { recursive: true });

const RED_BANNER_MARKERS = [
  "Unexpected token",
  "is not valid JSON",
  "The page could not be found",
  "Internal Server Error",
  "Backend connection failed",
  "DNS_HOSTNAME_RESOLVED_PRIVATE",
  "Current state load failed",
];

type StepRecord = {
  index: number;
  name: string;
  status: "pass" | "fail" | "skipped";
  url: string;
  visibleBanner: string | null;
  consoleErrorCount: number;
  pageErrorCount: number;
  failedRequestCount: number;
  apiResponses: AttemptRecord[];
  screenshotPath: string | null;
  detail: string | null;
  startedAt: string;
  finishedAt: string;
};

test.describe("Production demo workflow (UI only)", () => {
  test("walk through login → project → uploads → closeout", async ({ qaPage, qaSignal }) => {
    test.skip(!ALLOW_MUTATION, "QA_ALLOW_MUTATION!=true — demo walkthrough requires explicit opt-in");
    test.setTimeout(180_000);

    const { email, password } = resolveCreds();
    expect(email && password, "QA_USER_EMAIL/QA_USER_PASSWORD required when QA_ALLOW_MUTATION=true").toBeTruthy();

    const steps: StepRecord[] = [];
    let stepCounter = 0;
    let firstFailure: StepRecord | null = null;

    // Per-step capture index: snapshot attempts.length before, then after,
    // so each step records only the API calls fired during that step.
    let attemptCursor = 0;

    async function detectBanner(): Promise<string | null> {
      try {
        const text = await qaPage.locator("body").innerText({ timeout: 3000 });
        for (const marker of RED_BANNER_MARKERS) {
          if (text.includes(marker)) {
            const idx = text.indexOf(marker);
            const start = Math.max(0, idx - 60);
            const end = Math.min(text.length, idx + 200);
            return text.slice(start, end).replace(/\s+/g, " ").trim();
          }
        }
      } catch {
        return null;
      }
      return null;
    }

    async function snapshot(name: string): Promise<string> {
      const safeName = name.replace(/[^a-z0-9_-]+/gi, "_").slice(0, 80);
      const file = path.join(SHOT_DIR, `${String(stepCounter).padStart(2, "0")}_${safeName}.png`);
      try {
        await qaPage.screenshot({ path: file, fullPage: true });
      } catch {
        return "";
      }
      return path.relative(RUN_DIR, file);
    }

    async function step(name: string, body: () => Promise<void>): Promise<void> {
      stepCounter += 1;
      const startedAt = new Date().toISOString();
      const consoleBefore = qaSignal.consoleErrors.length;
      const pageBefore = qaSignal.pageErrors.length;
      const failedBefore = qaSignal.failedNetwork.length;
      let detail: string | null = null;
      let status: StepRecord["status"] = "pass";
      try {
        await body();
      } catch (err) {
        status = "fail";
        detail = err instanceof Error ? err.message : String(err);
      }
      const url = qaPage.url();
      const banner = await detectBanner();
      const screenshotPath = await snapshot(name);
      const apiResponses = qaSignal.attempts.slice(attemptCursor);
      attemptCursor = qaSignal.attempts.length;

      // Any visible red-banner marker is itself a failure — surface it even if
      // the body() block didn't throw.
      if (status === "pass" && banner) {
        status = "fail";
        detail = `visible red-banner marker: ${banner.slice(0, 200)}`;
      }
      // Any captured non-JSON API response is a failure for this workflow.
      const nonJsonApi = apiResponses.find(
        (a) =>
          a.url.includes("/api/") &&
          a.status !== null &&
          (a.isHtml || (a.contentType ? !a.contentType.toLowerCase().includes("application/json") : false)),
      );
      if (status === "pass" && nonJsonApi) {
        status = "fail";
        detail = `non-JSON API response on ${nonJsonApi.method} ${nonJsonApi.url} (status=${nonJsonApi.status}, ct=${nonJsonApi.contentType})`;
      }

      const record: StepRecord = {
        index: stepCounter,
        name,
        status,
        url,
        visibleBanner: banner,
        consoleErrorCount: qaSignal.consoleErrors.length - consoleBefore,
        pageErrorCount: qaSignal.pageErrors.length - pageBefore,
        failedRequestCount: qaSignal.failedNetwork.length - failedBefore,
        apiResponses,
        screenshotPath: screenshotPath || null,
        detail,
        startedAt,
        finishedAt: new Date().toISOString(),
      };
      steps.push(record);
      if (status === "fail" && !firstFailure) {
        firstFailure = record;
      }
    }

    // Capture every /api/* response through the page so we can attribute it
    // to a step. The harness's failedNetwork only records errors and HTML;
    // we want every API call, success or fail.
    qaPage.on("response", async (res) => {
      const url = res.url();
      if (!url.includes("/api/")) return;
      let bodyText = "";
      try {
        bodyText = await res.text();
      } catch {
        bodyText = "";
      }
      const ct = res.headers()["content-type"] ?? null;
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
      qaSignal.attempts.push({
        label: "ui-capture",
        url,
        method: res.request().method(),
        status: res.status(),
        contentType: ct,
        isJson,
        isHtml,
        bodyPreview: bodyText.length > 500 ? bodyText.slice(0, 500) + `…[+${bodyText.length - 500} bytes]` : bodyText,
        durationMs: null,
        timestamp: new Date().toISOString(),
      });
    });

    // --- Step 1 — go to login page -----------------------------------------
    await step("01_open_login_page", async () => {
      const resp = await qaPage.goto("/auth/login", { waitUntil: "domcontentloaded" });
      expect(resp, "login page should respond").not.toBeNull();
      await qaPage.waitForLoadState("networkidle");
      await expect(qaPage.locator("#email")).toBeVisible({ timeout: 10_000 });
      await expect(qaPage.locator("#password")).toBeVisible({ timeout: 10_000 });
    });

    // --- Step 2 — submit login form ----------------------------------------
    // 60s wait tolerates a Render free-tier cold start on /auth/login. A real
    // user just waits — the harness has to be as patient. The user-visible
    // failure we're reproducing is on the workspace page (step #5+), not on
    // the login round-trip.
    await step("02_submit_login", async () => {
      await qaPage.locator("#email").fill(email);
      await qaPage.locator("#password").fill(password);
      const navPromise = qaPage
        .waitForURL(/\/projects/, { timeout: 60_000 })
        .then(() => true)
        .catch(() => false);
      await qaPage.locator("button[type='submit']").click();
      const navigated = await navPromise;
      expect(
        navigated,
        `login submit did not navigate to /projects within 60s — current URL: ${qaPage.url()}`,
      ).toBe(true);
    });

    // --- Step 3 — projects list visible ------------------------------------
    await step("03_projects_list_visible", async () => {
      await qaPage.waitForLoadState("networkidle").catch(() => {});
      await expect(qaPage).toHaveURL(/\/projects/);
    });

    // --- Step 4 — open workspace for PROJECT_ID ----------------------------
    // Critical-path check: the workspace's mount-time GET /api/current-state
    // must return application/json. If Vercel's function times out waiting
    // for a Render cold start, it serves an HTML 502 page that the
    // workspace's fetchState safe-parse then renders as the red banner the
    // user reported. We explicitly wait for that request here so the test
    // fails the same way the user's browser does.
    await step(`04_open_workspace_${PROJECT_ID}`, async () => {
      const currentStatePromise = qaPage
        .waitForResponse(
          (r) =>
            r.url().includes("/api/current-state") &&
            r.request().method() === "GET",
          { timeout: 65_000 },
        )
        .catch(() => null);
      const resp = await qaPage.goto(`/projects/${encodeURIComponent(PROJECT_ID)}`, {
        waitUntil: "domcontentloaded",
      });
      expect(resp, `workspace navigation should respond`).not.toBeNull();
      const status = resp!.status();
      expect(
        status,
        `workspace /projects/${PROJECT_ID} returned ${status}`,
      ).toBeLessThan(400);
      const currentStateRes = await currentStatePromise;
      expect(
        currentStateRes,
        "expected the workspace to fire GET /api/current-state on mount",
      ).not.toBeNull();
      const csStatus = currentStateRes!.status();
      const csCt = currentStateRes!.headers()["content-type"] ?? "";
      const csBody = await currentStateRes!.text();
      const csSnippet = csBody.slice(0, 200);
      expect(
        csCt.toLowerCase(),
        `/api/current-state returned non-JSON content-type "${csCt}" (status ${csStatus}). Body[:200]: ${csSnippet}`,
      ).toContain("application/json");
      expect(
        csStatus,
        `/api/current-state returned ${csStatus}; body[:200]: ${csSnippet}`,
      ).toBeLessThan(500);
      await qaPage.waitForLoadState("networkidle").catch(() => {});
    });

    // --- Step 5 — workspace fully rendered, no red banner ------------------
    await step("05_workspace_initial_render", async () => {
      await expect(
        qaPage.locator("text=Workflow Controls"),
        "expected 'Workflow Controls' heading to render",
      ).toBeVisible({ timeout: 15_000 });
      // Give async state-loading effects time to settle.
      await qaPage.waitForTimeout(2000);
    });

    // --- Step 6 — click Refresh State --------------------------------------
    await step("06_click_refresh_state", async () => {
      const refreshBtn = qaPage.locator("button", { hasText: "Refresh State" }).first();
      await expect(
        refreshBtn,
        "expected a 'Refresh State' button to be visible on the workspace",
      ).toBeVisible({ timeout: 10_000 });
      await refreshBtn.click();
      await qaPage.waitForTimeout(2000);
    });

    // --- Step 7 — upload KMZ via the visible Upload KMZ Design control -----
    await step("07_upload_kmz_design", async () => {
      expect(
        fixtureExists("fixtures/sample-design.kmz"),
        "fixture qa/fixtures/sample-design.kmz must exist",
      ).toBe(true);
      const fp = fixturePath("fixtures/sample-design.kmz");
      // Find the label that contains the text, then the file input inside it.
      const kmzInput = qaPage.locator(
        "label:has-text('Upload KMZ Design') input[type='file']",
      );
      await expect(
        kmzInput,
        "expected an Upload KMZ Design file input on the workspace",
      ).toHaveCount(1, { timeout: 10_000 });
      await kmzInput.setInputFiles(fp);
      await qaPage.waitForTimeout(4000);
    });

    // --- Step 8 — upload engineering plan via the visible UI ---------------
    await step("08_upload_engineering_plan", async () => {
      expect(
        fixtureExists("fixtures/sample-engineering-plan.pdf"),
        "fixture qa/fixtures/sample-engineering-plan.pdf must exist",
      ).toBe(true);
      const fp = fixturePath("fixtures/sample-engineering-plan.pdf");
      const planInput = qaPage.locator(
        "label:has-text('Upload Engineering Plans') input[type='file']",
      );
      await expect(
        planInput,
        "expected an Upload Engineering Plans file input on the workspace",
      ).toHaveCount(1, { timeout: 10_000 });
      await planInput.setInputFiles(fp);
      await qaPage.waitForTimeout(5000);
    });

    // --- Step 9 — station photo upload via the visible UI (best-effort) ----
    await step("09_station_photo_upload_via_ui", async () => {
      expect(
        fixtureExists("fixtures/sample-station-photo.jpg"),
        "fixture qa/fixtures/sample-station-photo.jpg must exist",
      ).toBe(true);
      // Station photo upload is only available after a station is selected on
      // the map. Without a real KMZ + field data, no station is selectable.
      // Probe for a visible station-photo file input; if absent, fail with
      // the exact missing-selector message per requirements.
      const photoInput = qaPage.locator(
        "input[type='file'][accept*='image']",
      );
      const count = await photoInput.count();
      if (count === 0) {
        throw new Error(
          "no station-photo file input found in the visible DOM. " +
            "Station selection in the workspace map is required to expose " +
            "the photo upload control — a real demo requires a loaded KMZ + " +
            "field data + selected station before this UI control appears.",
        );
      }
      const first = photoInput.first();
      const visible = await first.isVisible().catch(() => false);
      if (!visible) {
        throw new Error(
          "station-photo file input found in DOM but not visible. " +
            "Selector: input[type='file'][accept*='image']",
        );
      }
      await first.setInputFiles(fixturePath("fixtures/sample-station-photo.jpg"));
      await qaPage.waitForTimeout(3000);
    });

    // --- Step 10 — switch to Closeout tab ----------------------------------
    await step("10_switch_to_closeout_tab", async () => {
      const closeoutTab = qaPage.locator("button[role='tab']", { hasText: "Closeout" }).first();
      await expect(
        closeoutTab,
        "expected a Closeout tab button on the workspace",
      ).toBeVisible({ timeout: 10_000 });
      await closeoutTab.click();
      await qaPage.waitForTimeout(2000);
    });

    // --- Step 11 — lock closeout via visible UI ----------------------------
    await step("11_lock_closeout_via_ui", async () => {
      const lockBtn = qaPage.locator("button", { hasText: "Lock Closeout" }).first();
      const count = await lockBtn.count();
      if (count === 0) {
        throw new Error(
          "no 'Lock Closeout' button visible. The button only appears when " +
            "billing is approved and closeout is unlocked — a real demo " +
            "requires that prerequisite state.",
        );
      }
      const disabled = await lockBtn.isDisabled().catch(() => false);
      if (disabled) {
        throw new Error("'Lock Closeout' button is disabled — billing-approved prerequisite not met.");
      }
      await lockBtn.click();
      await qaPage.waitForTimeout(3000);
    });

    // --- Finalize: write report file ---------------------------------------
    const report = {
      type: "demo-walkthrough",
      generatedAt: new Date().toISOString(),
      frontendUrl: FRONTEND_URL,
      projectId: PROJECT_ID,
      runDir: RUN_DIR,
      totalSteps: steps.length,
      passed: steps.filter((s) => s.status === "pass").length,
      failed: steps.filter((s) => s.status === "fail").length,
      skipped: steps.filter((s) => s.status === "skipped").length,
      firstFailure,
      steps,
    };
    fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2), "utf8");
    qaSignal.notes.push(`demo-walkthrough report: ${path.relative(RUN_DIR, REPORT_PATH)}`);

    // The Playwright test fails if ANY step failed. Surface the first failure
    // as the test's error message so the diagnosis packet picks it up.
    expect(
      firstFailure,
      firstFailure
        ? `demo step #${firstFailure.index} "${firstFailure.name}" failed: ${firstFailure.detail ?? "(no detail)"} — see ${path.relative(RUN_DIR, REPORT_PATH)}`
        : "all demo steps passed",
    ).toBeNull();
  });
});
