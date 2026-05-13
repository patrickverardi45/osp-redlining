import { NextRequest } from "next/server";
import { proxyAppRoute } from "@/lib/server/appProxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> },
) {
  // Drain the route param so Next.js doesn't warn about unused dynamic segment.
  // Forward to the long-stable backend path /api/closeout/lock — the handler
  // `api_closeout_lock` exposes both /api/jobs/{job_id}/lock-closeout AND
  // /api/closeout/lock; the latter has been deployed on Render for longer and
  // is the safer target. job_id is optional on the backend and is read from
  // the JSON body's session_id, not from the URL.
  await params;
  return proxyAppRoute(request, `/api/closeout/lock`);
}
