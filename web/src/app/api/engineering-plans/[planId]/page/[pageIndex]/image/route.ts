import { NextRequest } from "next/server";
import { proxyAppRoute } from "@/lib/server/appProxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
// Same-origin proxy for the engineering-plan page IMAGE (GET — no request body, so it is
// NOT bound by Vercel's ~4.5 MB serverless request-body ceiling that forces the large
// multipart upload-engineering-plans to stay direct-to-Render). Keeps the PDF-first
// review/display plan overlay same-origin, so that path needs no CORS allowlisted origin.
// proxyAppRoute preserves ?dpi=&session_id=, forwards Authorization, passes image/png through.
export const maxDuration = 60;

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ planId: string; pageIndex: string }> },
) {
  const { planId, pageIndex } = await params;
  return proxyAppRoute(
    request,
    `/api/engineering-plans/${encodeURIComponent(planId)}/page/${encodeURIComponent(pageIndex)}/image`,
  );
}
