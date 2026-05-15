// Export probe — captures the real production response for plausible export
// / download endpoints so the diagnosis packet records what shape they
// return. This is read-only (GET) and runs unauthenticated against the
// backend; no app or backend code is touched.
//
// Run regardless of QA_ALLOW_MUTATION; GETs are not mutations. Captures
// URL, method, status, content-type, and first 500 chars of body for each
// probe, then asserts only the always-true "should not be 5xx and should
// be either JSON or a real file body, never an HTML error page".

import { test, expect } from "../_support/harness";

const BACKEND_URL = process.env.QA_BACKEND_URL || "http://127.0.0.1:8000";

const EXPORT_CANDIDATES: { path: string; note: string }[] = [
  { path: "/download-csv", note: "downloads.py router (not currently mounted in main.py)" },
  { path: "/api/download-csv", note: "namespaced variant" },
  { path: "/api/export/closeout-package", note: "speculative closeout package export" },
];

test.describe("Export / download probe", () => {
  for (const candidate of EXPORT_CANDIDATES) {
    test(`probe ${candidate.path}`, async ({ qaSignal }) => {
      const url = `${BACKEND_URL}${candidate.path}`;
      const started = Date.now();
      let res: Response | null = null;
      let networkError: string | null = null;
      try {
        res = await fetch(url, { method: "GET" });
      } catch (err) {
        networkError = (err as Error).message;
      }
      const durationMs = Date.now() - started;

      if (!res) {
        qaSignal.attempts.push({
          label: `export-probe:${candidate.path}`,
          url,
          method: "GET",
          status: null,
          contentType: null,
          isJson: false,
          isHtml: false,
          bodyPreview: `network error: ${networkError}`,
          durationMs,
          timestamp: new Date().toISOString(),
        });
        // Do not fail the harness on network glitches against the probe set —
        // they are diagnostic, not assertions. The captured attempt is the
        // useful artifact.
        return;
      }

      const status = res.status;
      const contentType = res.headers.get("content-type") ?? "";
      const body = await res.text();
      const trimmed = body.trim().toLowerCase();
      const isHtml =
        trimmed.startsWith("<!doctype html") ||
        trimmed.startsWith("<html") ||
        trimmed.includes("<head");
      let isJson = false;
      try {
        if (body) {
          JSON.parse(body);
          isJson = true;
        }
      } catch {
        isJson = false;
      }
      qaSignal.attempts.push({
        label: `export-probe:${candidate.path}`,
        url,
        method: "GET",
        status,
        contentType,
        isJson,
        isHtml,
        bodyPreview: body.length > 500 ? body.slice(0, 500) + `…[+${body.length - 500} bytes]` : body,
        durationMs,
        timestamp: new Date().toISOString(),
      });
      qaSignal.notes.push(`${candidate.note}`);

      // The probe documents the response; we only assert "no HTML 5xx".
      // A 404 with informative JSON is acceptable; a 500 leaking HTML is not.
      expect(status, `export probe returned 5xx: ${status}`).toBeLessThan(500);
      if (status >= 400) {
        expect(
          isHtml,
          `export probe at ${candidate.path} returned an HTML body with status ${status}: ${body.slice(0, 200)}`,
        ).toBe(false);
      }
    });
  }

  test("engineering KMZ payload endpoint requires auth (unauthenticated → 401/403 JSON)", async ({ qaSignal }) => {
    const url = `${BACKEND_URL}/api/engineering-kmz-payload`;
    const started = Date.now();
    let response: Response | null = null;
    try {
      response = await fetch(url, { method: "GET" });
    } catch (err) {
      qaSignal.notes.push(`engineering-kmz fetch failed: ${(err as Error).message}`);
    }
    test.skip(!response, "Backend unreachable; engineering-kmz-payload contract not exercisable");

    const status = response!.status;
    const contentType = response!.headers.get("content-type") ?? "";
    const body = await response!.text();
    const trimmed = body.trim().toLowerCase();
    const isHtml =
      trimmed.startsWith("<!doctype html") || trimmed.startsWith("<html") || trimmed.includes("<body");
    let isJson = false;
    try { JSON.parse(body); isJson = true; } catch { isJson = false; }

    qaSignal.attempts.push({
      label: "engineering-kmz-unauth",
      url,
      method: "GET",
      status,
      contentType,
      isJson,
      isHtml,
      bodyPreview: body.length > 500 ? body.slice(0, 500) + `…[+${body.length - 500} bytes]` : body,
      durationMs: Date.now() - started,
      timestamp: new Date().toISOString(),
    });

    expect([401, 403]).toContain(status);
    expect(contentType.toLowerCase()).toContain("application/json");
    expect(() => JSON.parse(body), `engineering-kmz body must be JSON, got: ${body.slice(0, 200)}`).not.toThrow();
    expect(isHtml, "engineering-kmz response leaked HTML").toBe(false);
  });
});
