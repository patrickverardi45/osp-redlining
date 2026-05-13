import { NextRequest } from "next/server";
import { proxyAuthRoute } from "@/lib/server/authProxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
// Same Render cold-start consideration as /api/current-state: the default
// 10s Vercel function timeout is shorter than a Render free-tier cold start,
// so the first login after idle could be cut off mid-request.
export const maxDuration = 60;

export function POST(request: NextRequest) {
  return proxyAuthRoute(request, "login");
}
