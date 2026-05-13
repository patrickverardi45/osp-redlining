import { NextRequest } from "next/server";
import { proxyAppRoute } from "@/lib/server/appProxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export function GET(request: NextRequest) {
  return proxyAppRoute(request, "/api/nova-overrides");
}

export function POST(request: NextRequest) {
  return proxyAppRoute(request, "/api/nova-overrides");
}
