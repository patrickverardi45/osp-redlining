// Auth workflow tests. The "expected unauthenticated 401 JSON" contract is
// already exercised in qa:api; here we test browser-level behavior:
// the login form should never render a "page not found" string from the
// proxy, and a bad-password login should surface a JSON error message.

import { test, expect, resolveCreds } from "../_support/harness";

test.describe("Auth workflow", () => {
  test("login page does not show 404/HTML proxy error markers", async ({ qaPage, qaSignal }) => {
    await qaPage.goto("/auth/login", { waitUntil: "domcontentloaded" });
    const bodyText = (await qaPage.locator("body").innerText()).toLowerCase();
    // These strings are the canonical markers of the "Unexpected token T /
    // The page could not be found is not valid JSON" pain point.
    for (const marker of ["the page could not be found", "404", "internal server error"]) {
      expect(
        bodyText.includes(marker),
        `Login page contained forbidden marker: "${marker}"`,
      ).toBe(false);
    }
    qaSignal.notes.push("login page free of HTML error markers");
  });

  test("bad credentials produce a JSON error from /api/auth/login", async ({ qaPage, qaSignal }) => {
    await qaPage.goto("/auth/login", { waitUntil: "domcontentloaded" });
    await qaPage.waitForLoadState("networkidle");
    // networkidle fires when the network is quiet but hydrateRoot() is async — React may not
    // have attached event listeners yet. Wait for the __reactFiber marker on the email input,
    // which is only set after React completes hydration on that DOM node.
    await qaPage.waitForFunction(
      () => {
        const el = document.getElementById("email");
        return el != null && Object.keys(el).some((k) => k.startsWith("__reactFiber"));
      },
      { timeout: 10000 },
    );

    const responsePromise = qaPage.waitForResponse(
      (r) => r.url().includes("/api/auth/login") && r.request().method() === "POST",
      { timeout: 15000 },
    );

    await qaPage.locator("#email").fill("qa-harness@invalid.example");
    await qaPage.locator("#password").fill("definitely-wrong");
    await qaPage.locator("button[type='submit']").click();

    const response = await responsePromise;
    const status = response.status();
    const contentType = response.headers()["content-type"] ?? "";
    const body = await response.text();

    qaSignal.notes.push(
      `bad-login -> status=${status} content-type=${contentType} bodyLen=${body.length}`,
    );

    // Status must be a clean auth/validation error, never 200 / 5xx.
    expect([400, 401, 403, 422]).toContain(status);
    // Content-type must be JSON, not HTML.
    expect(contentType.toLowerCase()).toContain("application/json");
    expect(() => JSON.parse(body), `Body must be valid JSON, got: ${body.slice(0, 200)}`).not.toThrow();
  });

  test("authenticated login redirects to /projects when creds provided", async ({ qaPage, qaSignal }) => {
    const { email, password } = resolveCreds();
    test.skip(!email || !password, "QA_USER_EMAIL / QA_USER_PASSWORD not set — skipping login test");

    await qaPage.goto("/auth/login", { waitUntil: "domcontentloaded" });
    await qaPage.locator("#email").fill(email);
    await qaPage.locator("#password").fill(password);

    const navPromise = qaPage.waitForURL(/\/projects/, { timeout: 20000 }).catch(() => null);
    await qaPage.locator("button[type='submit']").click();
    const navResult = await navPromise;

    if (!navResult) {
      // Surface the on-screen error rather than a generic timeout.
      const error = await qaPage.locator("body").innerText();
      qaSignal.notes.push(`login did not navigate; body snippet=${error.slice(0, 300)}`);
    }
    expect(navResult, "expected redirect to /projects after login").not.toBeNull();
  });
});
