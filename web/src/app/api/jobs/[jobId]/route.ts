import { NextRequest } from "next/server";
import { proxyAppRoute } from "@/lib/server/appProxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// /jobs/{job_id} lives at the backend root — no /api/ prefix.
// Without this file Vercel's edge served a text/plain 404 (the
// "Unexpected token 'T', 'The page c'..." error banner) when
// useFieldSubmissions called getJobById on workspace mount.
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> },
) {
  const { jobId } = await params;
  return proxyAppRoute(request, `/jobs/${encodeURIComponent(jobId)}`);
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> },
) {
  const { jobId } = await params;
  return proxyAppRoute(request, `/jobs/${encodeURIComponent(jobId)}`);
}
