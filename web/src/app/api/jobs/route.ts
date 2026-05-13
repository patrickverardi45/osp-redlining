import { NextRequest } from "next/server";
import { proxyAppRoute } from "@/lib/server/appProxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// /jobs lives at the backend root — no /api/ prefix.
export function GET(request: NextRequest) {
  return proxyAppRoute(request, "/jobs");
}
