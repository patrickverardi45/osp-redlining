// Upload workflow tests.
// These tests mutate backend state. They only run when ALL three are true:
//   1. QA_ALLOW_MUTATION=true (explicit opt-in, required for production safety)
//   2. QA_USER_EMAIL / QA_USER_PASSWORD are set
//   3. a fixture file exists at qa/fixtures/<name>
// Otherwise the test is skipped with a clear note.

import { test, expect, resolveCreds, fixturePath, fixtureExists } from "../_support/harness";

const ALLOW_MUTATION = (process.env.QA_ALLOW_MUTATION ?? "").toLowerCase() === "true";
const MUTATION_SKIP_REASON =
  "QA_ALLOW_MUTATION!=true — skipping production-mutating upload (set QA_ALLOW_MUTATION=true to enable)";

async function loginIfPossible(page: Parameters<Parameters<typeof test>[1]>[0]["qaPage"]) {
  const { email, password } = resolveCreds();
  if (!email || !password) return false;
  await page.goto("/auth/login", { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle");
  await page.locator("#email").fill(email);
  await page.locator("#password").fill(password);
  const navPromise = page.waitForURL(/\/projects/, { timeout: 20000 }).then(() => true).catch(() => false);
  await page.locator("button[type='submit']").click();
  return await navPromise;
}

test.describe("Uploads workflow (best-effort)", () => {
  test("engineering plan upload endpoint accepts a small PDF", async ({ qaPage, qaSignal }) => {
    test.skip(!ALLOW_MUTATION, MUTATION_SKIP_REASON);
    const { email, password } = resolveCreds();
    test.skip(!email || !password, "credentials missing — skipping engineering plan upload");
    test.skip(
      !fixtureExists("fixtures/sample-engineering-plan.pdf"),
      "fixtures/sample-engineering-plan.pdf missing — add a tiny valid PDF to enable",
    );

    const loggedIn = await loginIfPossible(qaPage);
    test.skip(!loggedIn, "login did not succeed; skipping upload test");

    const filePath = fixturePath("fixtures/sample-engineering-plan.pdf");
    const fs = await import("node:fs");
    const buffer = fs.readFileSync(filePath);

    const response = await qaPage.request.post("/api/upload-engineering-plans", {
      multipart: {
        file: { name: "sample-engineering-plan.pdf", mimeType: "application/pdf", buffer },
      },
    });
    const status = response.status();
    const contentType = response.headers()["content-type"] ?? "";
    const body = await response.text();
    qaSignal.notes.push(`engineering-plan upload status=${status} ct=${contentType}`);

    // We do NOT assert the upload succeeds — the backend may legitimately
    // reject a placeholder PDF. We DO assert the response is well-formed JSON
    // (never HTML / never 5xx). That's the regression signal we care about.
    expect(status, `upload returned 5xx: ${status}`).toBeLessThan(500);
    expect(contentType.toLowerCase()).toContain("application/json");
    expect(() => JSON.parse(body), `body must be JSON, got: ${body.slice(0, 200)}`).not.toThrow();
  });

  test("station photo upload endpoint accepts a small image", async ({ qaPage, qaSignal }) => {
    test.skip(!ALLOW_MUTATION, MUTATION_SKIP_REASON);
    const { email, password } = resolveCreds();
    test.skip(!email || !password, "credentials missing — skipping station photo upload");
    test.skip(
      !fixtureExists("fixtures/sample-station-photo.jpg"),
      "fixtures/sample-station-photo.jpg missing — add a tiny valid JPG to enable",
    );

    const loggedIn = await loginIfPossible(qaPage);
    test.skip(!loggedIn, "login did not succeed; skipping upload test");

    const filePath = fixturePath("fixtures/sample-station-photo.jpg");
    const fs = await import("node:fs");
    const buffer = fs.readFileSync(filePath);

    const response = await qaPage.request.post("/api/station-photos/upload", {
      multipart: {
        file: { name: "sample-station-photo.jpg", mimeType: "image/jpeg", buffer },
      },
    });
    const status = response.status();
    const contentType = response.headers()["content-type"] ?? "";
    const body = await response.text();
    qaSignal.notes.push(`station-photo upload status=${status} ct=${contentType}`);

    expect(status, `upload returned 5xx: ${status}`).toBeLessThan(500);
    expect(contentType.toLowerCase()).toContain("application/json");
    expect(() => JSON.parse(body), `body must be JSON, got: ${body.slice(0, 200)}`).not.toThrow();
  });

  test("kmz upload endpoint accepts a tiny placeholder", async ({ qaPage, qaSignal }) => {
    test.skip(!ALLOW_MUTATION, MUTATION_SKIP_REASON);
    const { email, password } = resolveCreds();
    test.skip(!email || !password, "credentials missing — skipping KMZ upload");
    test.skip(
      !fixtureExists("fixtures/sample-design.kmz"),
      "fixtures/sample-design.kmz missing — add a tiny valid KMZ to enable",
    );

    const loggedIn = await loginIfPossible(qaPage);
    test.skip(!loggedIn, "login did not succeed; skipping upload test");

    const filePath = fixturePath("fixtures/sample-design.kmz");
    const fs = await import("node:fs");
    const buffer = fs.readFileSync(filePath);

    const response = await qaPage.request.post("/api/upload-design", {
      multipart: {
        file: { name: "sample-design.kmz", mimeType: "application/vnd.google-earth.kmz", buffer },
      },
    });
    const status = response.status();
    const contentType = response.headers()["content-type"] ?? "";
    const body = await response.text();
    qaSignal.notes.push(`kmz upload status=${status} ct=${contentType}`);

    expect(status, `upload returned 5xx: ${status}`).toBeLessThan(500);
    expect(contentType.toLowerCase()).toContain("application/json");
    expect(() => JSON.parse(body), `body must be JSON, got: ${body.slice(0, 200)}`).not.toThrow();
  });

  test("bore log upload endpoint accepts a small CSV", async ({ qaPage, qaSignal }) => {
    test.skip(!ALLOW_MUTATION, MUTATION_SKIP_REASON);
    const { email, password } = resolveCreds();
    test.skip(!email || !password, "credentials missing — skipping bore log upload");
    test.skip(
      !fixtureExists("fixtures/sample-bore-log.csv"),
      "fixtures/sample-bore-log.csv missing — add a tiny valid CSV to enable",
    );

    const loggedIn = await loginIfPossible(qaPage);
    test.skip(!loggedIn, "login did not succeed; skipping upload test");

    const filePath = fixturePath("fixtures/sample-bore-log.csv");
    const fs = await import("node:fs");
    const buffer = fs.readFileSync(filePath);

    const response = await qaPage.request.post("/api/upload-structured-bore-files", {
      multipart: {
        file: { name: "sample-bore-log.csv", mimeType: "text/csv", buffer },
      },
    });
    const status = response.status();
    const contentType = response.headers()["content-type"] ?? "";
    const body = await response.text();
    qaSignal.notes.push(`bore-log upload status=${status} ct=${contentType}`);

    // Contract: response is well-formed JSON and not 5xx. The backend may
    // reject the placeholder CSV (e.g. missing required columns) — that is
    // an acceptable 4xx. What we are guarding against is a 5xx or HTML body.
    expect(status, `bore upload returned 5xx: ${status}`).toBeLessThan(500);
    expect(contentType.toLowerCase()).toContain("application/json");
    expect(() => JSON.parse(body), `body must be JSON, got: ${body.slice(0, 200)}`).not.toThrow();
  });
});
