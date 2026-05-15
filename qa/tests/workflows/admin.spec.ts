// Admin workflow tests.
// Test 1 (always): unauthenticated contract — GET /admin/users, /admin/companies → 401/403 JSON.
// Test 2 (mutation-gated): full lifecycle — login as owner/admin, create QA user,
//   assign to QA company, verify list, member isolation check, cleanup.
//   Cleanup targets only IDs returned by CREATE calls in this run — never scans lists.
//
// Safety guards hard-abort (throw) if naming convention is violated rather than skip.
// QA company: "QA-{timestamp}", QA user: "qa+{timestamp}@trueline-test.invalid"

import { test, expect, resolveCreds } from "../_support/harness";

const BACKEND_URL = process.env.QA_BACKEND_URL || "http://127.0.0.1:8000";
const ALLOW_MUTATION = (process.env.QA_ALLOW_MUTATION ?? "").toLowerCase() === "true";
const MUTATION_SKIP_REASON =
  "QA_ALLOW_MUTATION!=true — skipping authenticated admin lifecycle probe";

function assertQaCompany(name: string, id: string): void {
  if (!name.startsWith("QA-")) {
    throw new Error(
      `SAFETY ABORT: refusing to delete company "${name}" (id=${id}) — name must start with "QA-"`,
    );
  }
}

function assertQaUser(email: string, id: string): void {
  if (!/^qa\+\d+@trueline-test\.invalid$/.test(email)) {
    throw new Error(
      `SAFETY ABORT: refusing to delete user "${email}" (id=${id}) — email must match qa+{timestamp}@trueline-test.invalid`,
    );
  }
}

test.describe("Admin workflow", () => {
  test("admin endpoints require auth (unauthenticated → 401/403 JSON)", async ({ qaSignal }) => {
    let backendUnreachable = false;

    for (const path of ["/admin/users", "/admin/companies"]) {
      const url = `${BACKEND_URL}${path}`;
      const started = Date.now();
      let res: Response | null = null;
      try {
        res = await fetch(url, { method: "GET" });
      } catch (err) {
        qaSignal.notes.push(`admin fetch failed (${path}): ${(err as Error).message}`);
        backendUnreachable = true;
        break;
      }

      const status = res.status;
      const contentType = res.headers.get("content-type") ?? "";
      const body = await res.text();
      const trimmed = body.trim().toLowerCase();
      const isHtml =
        trimmed.startsWith("<!doctype html") || trimmed.startsWith("<html") || trimmed.includes("<body");
      let isJson = false;
      try { JSON.parse(body); isJson = true; } catch { isJson = false; }

      qaSignal.attempts.push({
        label: `admin-unauth:${path}`,
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
      expect(() => JSON.parse(body), `${path} body must be JSON, got: ${body.slice(0, 200)}`).not.toThrow();
      expect(isHtml, `${path} response leaked HTML`).toBe(false);
    }

    test.skip(backendUnreachable, "Backend unreachable; admin contract not exercisable");
  });

  test("authenticated admin lifecycle: create QA user, assign, verify, member isolation, cleanup", async ({ qaSignal }) => {
    test.skip(!ALLOW_MUTATION, MUTATION_SKIP_REASON);
    const { email, password } = resolveCreds();
    expect(
      email && password,
      "QA_USER_EMAIL/QA_USER_PASSWORD must be set when QA_ALLOW_MUTATION=true",
    ).toBeTruthy();

    // Login to get access token.
    const loginStarted = Date.now();
    const loginRes = await fetch(`${BACKEND_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    qaSignal.attempts.push({
      label: "admin-login",
      url: `${BACKEND_URL}/auth/login`,
      method: "POST",
      status: loginRes.status,
      contentType: loginRes.headers.get("content-type"),
      isJson: true,
      isHtml: false,
      bodyPreview: null,
      durationMs: Date.now() - loginStarted,
      timestamp: new Date().toISOString(),
    });
    expect(loginRes.status, "login must succeed to run admin tests").toBe(200);
    const loginJson = await loginRes.json();
    const token: string = loginJson.access_token;
    expect(token, "access_token must be present in login response").toBeTruthy();

    const authHeaders = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
    const ts = Date.now();
    const qaCompanyName = `QA-${ts}`;
    const qaUserEmail = `qa+${ts}@trueline-test.invalid`;
    const qaUserPassword = `QaTest-${ts}`;

    let createdCompanyId: string | null = null;
    let createdCompanyName: string | null = null;
    let createdUserId: string | null = null;
    let createdUserEmail: string | null = null;

    try {
      // Step 1: Attempt to create QA company (owner only; graceful 403 if not owner).
      const createCompanyRes = await fetch(`${BACKEND_URL}/admin/companies`, {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify({ name: qaCompanyName }),
      });
      if (createCompanyRes.status === 403) {
        qaSignal.notes.push(
          "POST /admin/companies returned 403 — QA user is not a platform owner; company creation skipped",
        );
      } else {
        expect(createCompanyRes.status, "create company must return 201").toBe(201);
        const company = await createCompanyRes.json();
        createdCompanyId = company.id;
        createdCompanyName = company.name;
        assertQaCompany(createdCompanyName!, createdCompanyId!);
        qaSignal.notes.push(`created company: ${createdCompanyName} (id=${createdCompanyId})`);
      }

      // Step 2: Create QA user.
      const createUserRes = await fetch(`${BACKEND_URL}/admin/users`, {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify({ email: qaUserEmail, password: qaUserPassword, display_name: "QA Test User" }),
      });
      expect(createUserRes.status, "create user must return 201").toBe(201);
      const user = await createUserRes.json();
      createdUserId = user.id;
      createdUserEmail = user.email;
      assertQaUser(createdUserEmail!, createdUserId!);
      qaSignal.notes.push(`created user: ${createdUserEmail} (id=${createdUserId})`);

      // Step 3: Assign user to company (only if company was created).
      if (createdCompanyId) {
        const assignRes = await fetch(`${BACKEND_URL}/admin/users/${createdUserId}/assign`, {
          method: "POST",
          headers: authHeaders,
          body: JSON.stringify({ company_id: createdCompanyId, role: "member" }),
        });
        expect(assignRes.status, "assign user must succeed").toBeLessThan(300);
        const assign = await assignRes.json();
        qaSignal.notes.push(`assigned user to company: membership_id=${assign.membership_id}`);
      }

      // Step 4: Verify user appears in list.
      const usersRes = await fetch(`${BACKEND_URL}/admin/users`, {
        method: "GET",
        headers: authHeaders,
      });
      expect(usersRes.status, "GET /admin/users must return 200").toBe(200);
      const users: Array<{ id: string }> = await usersRes.json();
      const found = users.some((u) => u.id === createdUserId);
      expect(found, `created user id=${createdUserId} must appear in /admin/users`).toBe(true);
      qaSignal.notes.push("created user verified in user list");

      // Step 5: Member isolation — new QA user must not access admin endpoints.
      const memberLoginRes = await fetch(`${BACKEND_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: qaUserEmail, password: qaUserPassword }),
      });
      if (memberLoginRes.status === 200) {
        const memberToken: string = (await memberLoginRes.json()).access_token;
        const memberAdminRes = await fetch(`${BACKEND_URL}/admin/users`, {
          method: "GET",
          headers: { Authorization: `Bearer ${memberToken}` },
        });
        expect(
          memberAdminRes.status,
          "member-role user must receive 403 on GET /admin/users",
        ).toBe(403);
        qaSignal.notes.push("member isolation check passed: /admin/users returned 403 for member role");
      } else {
        qaSignal.notes.push(
          `member login returned ${memberLoginRes.status} — skipping isolation check (user may have no company assignment)`,
        );
      }
    } finally {
      // Cleanup: delete only what this run created (identified by IDs, not list scans).
      if (createdUserId && createdUserEmail) {
        assertQaUser(createdUserEmail, createdUserId);
        const delUserRes = await fetch(`${BACKEND_URL}/admin/users/${createdUserId}`, {
          method: "DELETE",
          headers: authHeaders,
        });
        qaSignal.notes.push(
          `cleanup: DELETE /admin/users/${createdUserId} → ${delUserRes.status}`,
        );
      }
      if (createdCompanyId && createdCompanyName) {
        assertQaCompany(createdCompanyName, createdCompanyId);
        const delCompanyRes = await fetch(`${BACKEND_URL}/admin/companies/${createdCompanyId}`, {
          method: "DELETE",
          headers: authHeaders,
        });
        qaSignal.notes.push(
          `cleanup: DELETE /admin/companies/${createdCompanyId} → ${delCompanyRes.status}`,
        );
      }
    }
  });
});
