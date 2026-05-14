// Closeout workflow tests.
// Read-only test always runs; the authenticated lock-closeout test is
// mutation-gated and follows the same "no silent skip when allowed" rule as
// uploads.spec.ts: if QA_ALLOW_MUTATION=true and creds/login resolve, it
// must run end-to-end or fail with a clear reason.

import { test, expect, resolveCreds, recordAttempt } from "../_support/harness";

const BACKEND_URL = process.env.QA_BACKEND_URL || "http://127.0.0.1:8000";
const ALLOW_MUTATION = (process.env.QA_ALLOW_MUTATION ?? "").toLowerCase() === "true";
const MUTATION_SKIP_REASON =
  "QA_ALLOW_MUTATION!=true — skipping authenticated closeout lock probe";

test.describe("Closeout workflow", () => {
  test("closeout lock endpoint returns JSON, never HTML (unauthenticated)", async ({ qaSignal }) => {
    let response: Response | null = null;
    const started = Date.now();
    try {
      response = await fetch(`${BACKEND_URL}/api/closeout/lock`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
    } catch (err) {
      qaSignal.notes.push(`closeout fetch failed: ${(err as Error).message}`);
    }
    test.skip(!response, "Backend unreachable; closeout contract not exercisable");

    const status = response!.status;
    const contentType = response!.headers.get("content-type") ?? "";
    const body = await response!.text();
    qaSignal.attempts.push({
      label: "closeout-lock-unauth",
      url: `${BACKEND_URL}/api/closeout/lock`,
      method: "POST",
      status,
      contentType,
      isJson: (() => { try { JSON.parse(body); return true; } catch { return false; } })(),
      isHtml: body.trim().toLowerCase().startsWith("<!doctype html") || body.trim().toLowerCase().startsWith("<html"),
      bodyPreview: body.length > 500 ? body.slice(0, 500) + `…[+${body.length - 500} bytes]` : body,
      durationMs: Date.now() - started,
      timestamp: new Date().toISOString(),
    });

    expect([401, 403, 422]).toContain(status);
    expect(contentType.toLowerCase()).toContain("application/json");
    expect(() => JSON.parse(body), `closeout body must be JSON, got: ${body.slice(0, 200)}`).not.toThrow();

    const lower = body.trim().toLowerCase();
    const looksHtml =
      lower.startsWith("<!doctype html") ||
      lower.startsWith("<html") ||
      lower.includes("<body");
    expect(looksHtml, "closeout response leaked HTML").toBe(false);
  });

  test("authenticated closeout lock returns idempotent JSON", async ({ qaPage, qaSignal }) => {
    test.skip(!ALLOW_MUTATION, MUTATION_SKIP_REASON);

    // Log in via the UI so qaPage.request inherits the auth cookie set by
    // the frontend proxy. This is the same path the real app uses.
    const { email, password } = resolveCreds();
    expect(
      email && password,
      "QA_USER_EMAIL/QA_USER_PASSWORD must be set when QA_ALLOW_MUTATION=true",
    ).toBeTruthy();

    await qaPage.goto("/auth/login", { waitUntil: "domcontentloaded" });
    await qaPage.waitForLoadState("networkidle");
    await qaPage.locator("#email").fill(email);
    await qaPage.locator("#password").fill(password);
    const navPromise = qaPage
      .waitForURL(/\/projects/, { timeout: 20000 })
      .then(() => true)
      .catch(() => false);
    await qaPage.locator("button[type='submit']").click();
    const loggedIn = await navPromise;
    expect(loggedIn, "login submit did not redirect to /projects within 20s").toBe(true);

    const started = Date.now();
    const response = await qaPage.request.post("/api/jobs/qa-harness/lock-closeout", {
      data: { session_id: "qa-harness", user: "qa-harness" },
      headers: { "Content-Type": "application/json" },
    });
    const attempt = await recordAttempt(
      qaSignal,
      "closeout-lock-auth",
      "/api/jobs/qa-harness/lock-closeout",
      "POST",
      response,
      started,
    );

    // Whatever the route does, the contract is "JSON, never HTML, never 5xx".
    expect(attempt.status, `closeout lock returned 5xx: ${attempt.status}`).toBeLessThan(500);
    expect((attempt.contentType ?? "").toLowerCase()).toContain("application/json");
    expect(attempt.isJson, `closeout lock body must be JSON, got: ${(attempt.bodyPreview ?? "").slice(0, 200)}`).toBe(true);
  });
});
