import { NextRequest } from "next/server";
import { proxyAuthRoute } from "@/lib/server/authProxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export function GET(request: NextRequest) {
  return proxyAuthRoute(request, "me");
}
