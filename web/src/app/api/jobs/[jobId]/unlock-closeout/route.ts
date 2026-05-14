import { NextRequest } from "next/server";
import { proxyAppRoute } from "@/lib/server/appProxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> },
) {
  // See lock-closeout/route.ts — forward to the stable /api/closeout/unlock
  // backend path. Same handler `api_closeout_unlock`, same payload, just an
  // older and definitely-deployed decorator.
  await params;
  return proxyAppRoute(request, `/api/closeout/unlock`);
}
