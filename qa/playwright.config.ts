import { defineConfig, devices } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const configPath = path.resolve(__dirname, "config", "qa.config.json");
const cfg = JSON.parse(fs.readFileSync(configPath, "utf8"));

const frontendUrl =
  process.env.QA_FRONTEND_URL ||
  cfg.env?.frontendUrl?.default ||
  "http://localhost:3000";

const runDir = process.env.QA_RUN_DIR || path.resolve(__dirname, "reports", "_adhoc");
const jsonName = process.env.QA_PLAYWRIGHT_JSON || "playwright-results.json";
fs.mkdirSync(runDir, { recursive: true });
fs.mkdirSync(path.join(runDir, "screenshots"), { recursive: true });
fs.mkdirSync(path.join(runDir, "videos"), { recursive: true });
fs.mkdirSync(path.join(runDir, "traces"), { recursive: true });

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: cfg.timeouts?.playwrightTestMs ?? 60000,
  expect: { timeout: cfg.timeouts?.playwrightActionMs ?? 15000 },
  reporter: [
    ["list"],
    ["json", { outputFile: path.join(runDir, jsonName) }],
  ],
  outputDir: path.join(runDir, "_pw_artifacts"),
  use: {
    baseURL: frontendUrl,
    actionTimeout: cfg.timeouts?.playwrightActionMs ?? 15000,
    navigationTimeout: cfg.timeouts?.playwrightNavigationMs ?? 30000,
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    trace: "retain-on-failure",
    ignoreHTTPSErrors: true,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
