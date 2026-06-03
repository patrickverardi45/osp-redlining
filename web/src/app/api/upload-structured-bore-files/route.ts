import { NextRequest } from "next/server";
import { proxyAppRoute } from "@/lib/server/appProxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
// Bore upload triggers _rebuild_field_data_outputs (ROWS_ONLY) over every row;
// the full multi-log set needs more than Vercel's ~10s function default, or the
// proxy 504s (HTML) before Render finishes. Mirrors upload-engineering-plans /
// current-state, which already set 60 for the same reason. (Render's own worker
// timeout must likewise exceed the rebuild — see deploy notes.)
export const maxDuration = 60;

export function POST(request: NextRequest) {
  return proxyAppRoute(request, "/api/upload-structured-bore-files");
}
