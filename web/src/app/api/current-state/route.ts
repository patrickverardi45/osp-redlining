import { NextRequest } from "next/server";
import { proxyAppRoute } from "@/lib/server/appProxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
// /api/current-state is the workspace's mount-time data load. Vercel's
// default 10s function timeout is shorter than a Render free-tier cold
// start, which produced an HTML 502 ("<!DOCTYPE html>...<title>502</title>")
// that the workspace's fetchState safe-parse then surfaced as the visible
// "Current state load failed (502): …" red banner. 60s clears the cold start.
export const maxDuration = 60;

export function GET(request: NextRequest) {
  return proxyAppRoute(request, "/api/current-state");
}
