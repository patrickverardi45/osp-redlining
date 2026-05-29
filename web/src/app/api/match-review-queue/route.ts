import { NextRequest } from "next/server";
import { proxyAppRoute } from "@/lib/server/appProxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
// Same-origin proxy for the read-only Match Review Queue (Slice B + C1 + Plan
// Sheet Graph evidence). The /match-review panel calls
// apiFetch("/api/match-review-queue?session_id=…"); without this handler the
// next.config fallback rewrite forwards it to 127.0.0.1:8000, which has nothing
// listening on Vercel and returns a 404. maxDuration=60 mirrors
// /api/current-state — a Render cold start can exceed Vercel's default 10s
// function timeout and otherwise surface as an HTML 502. GET-only: the backend
// route is @localhost_router.get and the panel never mutates. proxyAppRoute
// preserves the ?session_id query and forwards the Authorization header.
export const maxDuration = 60;

export function GET(request: NextRequest) {
  return proxyAppRoute(request, "/api/match-review-queue");
}
