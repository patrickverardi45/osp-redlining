import { NextRequest } from "next/server";
import { proxyAppRoute } from "@/lib/server/appProxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
// Same-origin proxy for the read-only Trust Ledger (KMZ Automatic Redline
// Placement, default-OFF behind TRUELINE_TRUST_LEDGER). The /trust-ledger panel
// calls apiFetch("/api/trust-ledger?session_id=…"); without this handler the
// next.config fallback rewrite forwards it to 127.0.0.1:8000, which has nothing
// listening on Vercel and returns a 404. maxDuration=60 mirrors
// /api/match-review-queue and /api/current-state — a Render cold start can
// exceed Vercel's default function timeout and otherwise surface as an HTML 502.
// GET-only: the backend route is @localhost_router.get and the panel is
// read-only. proxyAppRoute preserves the ?session_id query and forwards the
// Authorization header.
export const maxDuration = 60;

export function GET(request: NextRequest) {
  return proxyAppRoute(request, "/api/trust-ledger");
}
