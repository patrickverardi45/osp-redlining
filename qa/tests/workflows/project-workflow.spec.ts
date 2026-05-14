// Project dashboard / workspace workflow.
// Without authenticated credentials the test logs in via the UI; if creds are
// missing it tests the unauthenticated redirect/landing behavior so we still
// catch HTML-instead-of-JSON regressions on /api/current-state.

import { test, expect, resolveCreds } from "../_support/harness";

test.describe("Project workflow", () => {
  test("projects route is reachable", async ({ qaPage, qaSignal }) => {
    const { email, password } = resolveCreds();
    if (email && password) {
      await qaPage.goto("/auth/login", { waitUntil: "domcontentloaded" });
      await qaPage.locator("#email").fill(email);
      await qaPage.locator("#password").fill(password);
      const navPromise = qaPage.waitForURL(/\/projects/, { timeout: 20000 }).catch(() => null);
      await qaPage.locator("button[type='submit']").click();
      const ok = await navPromise;
      if (!ok) {
        qaSignal.notes.push("login submit did not redirect; continuing with direct nav");
      }
    }

    const response = await qaPage.goto("/projects", { waitUntil: "domcontentloaded" });
    expect(response, "GET /projects should respond").not.toBeNull();
    const status = response!.status();
    // Authenticated → 200. Unauthenticated → 200 with client redirect or 3xx
    // depending on the Next.js auth gate. Anything 4xx/5xx is a failure.
    expect(status, `unexpected status on /projects: ${status}`).toBeLessThan(400);
    qaSignal.notes.push(`/projects status=${status}`);
  });

  test("/api/current-state never returns HTML", async ({ qaPage, qaSignal }) => {
    // Hit the proxy directly through the page context so we replicate the
    // browser's same-origin call surface.
    const response = await qaPage.request.get("/api/current-state");
    const status = response.status();
    const contentType = response.headers()["content-type"] ?? "";
    const body = await response.text();
    qaSignal.notes.push(`current-state status=${status} ct=${contentType}`);

    // Status may be 401 (unauthenticated) or 200 (authenticated). The body
    // must always parse as JSON — we never want an HTML 404 leaking through.
    expect(contentType.toLowerCase()).toContain("application/json");
    expect(() => JSON.parse(body), `current-state body must be JSON, got: ${body.slice(0, 200)}`).not.toThrow();
  });
});
