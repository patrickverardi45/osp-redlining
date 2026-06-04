// check-proxy-coverage.mjs
//
// Focused guard for the transport boundary (fix/pdf-first-nonupload-proxy-cleanup):
// the PDF-first REVIEW/DISPLAY path must reach the backend SAME-ORIGIN (through the Vercel
// proxy routes) and must NOT build direct-to-Render URLs. The ONLY sanctioned direct-to-Render
// call is the large multipart engineering-plan UPLOAD in RedlineMap.tsx, whose POST body can
// exceed Vercel's ~4.5 MB serverless request-body ceiling (GET responses are not bound by it).
//
// Run: npm --prefix web run check:proxy-coverage
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..", "src");

// A direct-to-Render URL is built from NEXT_PUBLIC_API_BASE(_URL) (a.k.a. RENDER_BASE).
const DIRECT_RENDER = /NEXT_PUBLIC_API_BASE(_URL)?|RENDER_BASE|onrender\.com/;

// PDF-first review/display components — MUST be same-origin only (no direct-to-Render).
const REVIEW_DISPLAY = [
  "components/PdfFirstEvidencePanel.tsx",
  "components/MatchReviewQueuePanel.tsx",
  "components/ModernHeroMap.tsx",
];

// The single sanctioned direct-to-Render caller (large multipart upload only).
const SANCTIONED_DIRECT = "components/RedlineMap.tsx";

let failed = false;

function read(rel) {
  try {
    return readFileSync(join(SRC, rel), "utf8");
  } catch {
    console.error(`[proxy-coverage] FAIL ${rel} not found (path drift?)`);
    failed = true;
    return "";
  }
}

for (const rel of REVIEW_DISPLAY) {
  const txt = read(rel);
  if (DIRECT_RENDER.test(txt)) {
    console.error(`[proxy-coverage] FAIL ${rel} builds a direct-to-Render URL; the PDF-first review/display path must be same-origin.`);
    failed = true;
  } else {
    console.log(`[proxy-coverage] OK   ${rel} same-origin only.`);
  }
}

// Positive assertion: the sanctioned direct upload is still present and intentional.
const redline = read(SANCTIONED_DIRECT);
if (DIRECT_RENDER.test(redline) && /upload-engineering-plans/.test(redline)) {
  console.log(`[proxy-coverage] OK   ${SANCTIONED_DIRECT} retains the sanctioned direct-to-Render upload (large multipart body).`);
} else {
  console.error(`[proxy-coverage] FAIL ${SANCTIONED_DIRECT} no longer has the sanctioned direct upload — upload transport changed unexpectedly.`);
  failed = true;
}

if (failed) {
  console.error("[proxy-coverage] FAILED");
  process.exit(1);
}
console.log("[proxy-coverage] PASSED");
