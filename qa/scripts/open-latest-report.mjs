#!/usr/bin/env node
// Convenience: open the most recent run's report.html in the OS default app.
import path from "node:path";
import fs from "node:fs";
import { spawn } from "node:child_process";
import { latestRunDir } from "./lib/run-context.mjs";

const dir = latestRunDir();
if (!dir) {
  console.error("No QA runs found in qa/reports/. Run `npm run qa:all` first.");
  process.exit(1);
}
const html = path.join(dir, "report.html");
if (!fs.existsSync(html)) {
  console.error(`Latest run is missing report.html: ${html}`);
  process.exit(1);
}
console.log(`Opening ${html}`);
const opener =
  process.platform === "win32" ? "start" : process.platform === "darwin" ? "open" : "xdg-open";
const child = spawn(opener, [html], { shell: true, stdio: "inherit", detached: true });
child.unref();
