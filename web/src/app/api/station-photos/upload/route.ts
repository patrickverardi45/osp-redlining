import { NextRequest } from "next/server";
import { proxyAppRoute } from "@/lib/server/appProxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 60; // image uploads can stream multiple files; matches upload-engineering-plans

export function POST(request: NextRequest) {
  return proxyAppRoute(request, "/api/station-photos/upload");
}
