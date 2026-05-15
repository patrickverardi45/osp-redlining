// Project lifecycle browser test.
// Exercises the full create → archive → restore → delete flow for a QA project
// within a single browser session. Projects are localStorage-backed; this test
// verifies the dashboard UI contract without touching backend state.
//
// Mutation-gated because it writes to localStorage and navigates through the app.
// Requires owner or admin credentials (Archive/Restore/Delete buttons are role-gated).
//
// Safety guard: assertQaProject throws (not skips) if project name does not match
// "QA Project " prefix — prevents accidental deletion of real projects.

import { test, expect, resolveCreds } from "../_support/harness";

const ALLOW_MUTATION = (process.env.QA_ALLOW_MUTATION ?? "").toLowerCase() === "true";
const MUTATION_SKIP_REASON =
  "QA_ALLOW_MUTATION!=true — skipping project lifecycle browser test";

function assertQaProject(name: string): void {
  if (!name.startsWith("QA Project ")) {
    throw new Error(
      `SAFETY ABORT: refusing to delete project "${name}" — name must start with "QA Project "`,
    );
  }
}

test.describe("Project lifecycle (browser)", () => {
  test("create → archive → restore → delete a QA project", async ({ qaPage, qaSignal }) => {
    test.skip(!ALLOW_MUTATION, MUTATION_SKIP_REASON);
    const { email, password } = resolveCreds();
    test.skip(!email || !password, "credentials missing — project lifecycle test requires login");

    // Login via UI.
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
    test.skip(!loggedIn, "login did not succeed — skipping project lifecycle test");

    // Navigate explicitly to the projects dashboard.
    await qaPage.goto("/projects", { waitUntil: "domcontentloaded" });
    await qaPage.waitForLoadState("networkidle");
    qaSignal.notes.push("on /projects dashboard");

    const ts = Date.now();
    const projectName = `QA Project ${ts}`;
    assertQaProject(projectName); // sanity-check naming convention before creating

    // --- Create ---
    await qaPage.getByRole("button", { name: /\+ new project/i }).click();
    await qaPage.locator("#new-project-name").fill(projectName);
    // "Create & Open" navigates to the project workspace. Wait for navigation then come back.
    const workspaceNavPromise = qaPage
      .waitForURL(/\/projects\/.+/, { timeout: 15000 })
      .then(() => true)
      .catch(() => false);
    await qaPage.locator("#new-project-form button[type='submit']").click();
    const navigatedToWorkspace = await workspaceNavPromise;
    if (!navigatedToWorkspace) {
      qaSignal.notes.push("warning: Create & Open did not navigate to workspace");
    }
    qaSignal.notes.push(`created project: ${projectName}`);

    // Return to the projects dashboard.
    await qaPage.goto("/projects", { waitUntil: "domcontentloaded" });
    await qaPage.waitForLoadState("networkidle");

    // Project card must be visible.
    const projectCard = qaPage.locator("article").filter({ hasText: projectName });
    await expect(projectCard, `project card for "${projectName}" must be visible`).toBeVisible({
      timeout: 10000,
    });
    qaSignal.notes.push("project card visible on dashboard");

    // Verify Archive button is present (requires owner/admin role).
    const archiveBtn = projectCard.getByRole("button", { name: "Archive" });
    await expect(
      archiveBtn,
      'Archive button not visible — QA user may not have owner/admin role (canManageProjects=false)',
    ).toBeVisible({ timeout: 5000 });

    // --- Archive ---
    await archiveBtn.click();
    // Card should disappear from the visible list (archived projects are hidden by default).
    await expect(projectCard).not.toBeVisible({ timeout: 5000 });
    qaSignal.notes.push("project archived — card hidden from main list");

    // "Show Archived" button appears when any project is archived.
    const showArchivedBtn = qaPage.getByRole("button", { name: "Show Archived" });
    await expect(showArchivedBtn, '"Show Archived" button must appear after archiving').toBeVisible({
      timeout: 5000,
    });
    await showArchivedBtn.click();
    // Archived card reappears with "Archived" badge.
    await expect(projectCard).toBeVisible({ timeout: 5000 });
    qaSignal.notes.push("archived card visible after Show Archived");

    // --- Restore ---
    const restoreBtn = projectCard.getByRole("button", { name: "Restore" });
    await expect(restoreBtn, "Restore button must be visible on archived card").toBeVisible({
      timeout: 5000,
    });
    await restoreBtn.click();
    // After restore, the card is no longer archived and remains visible.
    await expect(projectCard).toBeVisible({ timeout: 5000 });
    qaSignal.notes.push("project restored — card visible in main list");

    // --- Delete ---
    assertQaProject(projectName); // guard before destructive action
    const deleteBtn = projectCard.getByRole("button", { name: "Delete" });
    await expect(deleteBtn, "Delete button must be visible on restored card").toBeVisible({
      timeout: 5000,
    });
    await deleteBtn.click();

    // Confirmation dialog: "Yes, delete" button.
    const confirmBtn = projectCard.getByRole("button", { name: "Yes, delete" });
    await expect(confirmBtn, '"Yes, delete" confirmation button must appear').toBeVisible({
      timeout: 5000,
    });
    await confirmBtn.click();

    // Card must disappear after deletion.
    await expect(projectCard).not.toBeVisible({ timeout: 5000 });
    qaSignal.notes.push(`deleted project: ${projectName}`);
  });
});
