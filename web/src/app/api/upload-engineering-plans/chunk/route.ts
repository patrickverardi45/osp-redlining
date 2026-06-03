import { NextRequest } from "next/server";
import { proxyAppRoute } from "@/lib/server/appProxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
// LP.1 — same-origin proxy for chunked large-plan upload. Each chunk is small
// (browser slices at ~3.5 MB, under Vercel's ~4.5 MB serverless body ceiling) so
// no chunk hits the body limit and, being same-origin, none triggers a CORS
// preflight. The final chunk reassembles + registers on the backend (no redline
// rebuild), so 60s is ample headroom over the slowest finalize.
export const maxDuration = 60;

export function POST(request: NextRequest) {
  return proxyAppRoute(request, "/api/upload-engineering-plans/chunk");
}
