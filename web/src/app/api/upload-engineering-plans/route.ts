import { NextRequest } from "next/server";
import { proxyAppRoute } from "@/lib/server/appProxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 60; // engineering plans triggers a second rebuild pass; needs more than the 10s default

export function POST(request: NextRequest) {
  return proxyAppRoute(request, "/api/upload-engineering-plans");
}
