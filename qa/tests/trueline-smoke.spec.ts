// Smoke test: the absolute minimum we expect the app to do without crashing.
// Lands on the home page, then visits the login page, capturing console and
// network errors via the qaPage fixture.

import { test, expect } from "./_support/harness";

test.describe("TrueLine smoke", () => {
  test("home page renders without console errors", async ({ qaPage, qaSignal }) => {
    const response = await qaPage.goto("/", { waitUntil: "domcontentloaded" });
    expect(response, "GET / should produce a response").not.toBeNull();
    const status = response!.status();
    // 200 (landing) or a redirect to /auth/login is acceptable.
    expect([200, 301, 302, 303, 307, 308]).toContain(status);
    qaSignal.notes.push(`home status=${status}`);
  });

  test("login page renders and form is interactable", async ({ qaPage, qaSignal }) => {
    const response = await qaPage.goto("/auth/login", { waitUntil: "domcontentloaded" });
    expect(response?.status(), "login should render 200").toBe(200);

    const email = qaPage.locator("#email");
    const password = qaPage.locator("#password");
    await expect(email).toBeVisible();
    await expect(password).toBeVisible();
    qaSignal.notes.push("login form fields visible");
  });
});
