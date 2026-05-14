import { NextRequest } from "next/server";
import { proxyAppRoute } from "@/lib/server/appProxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ photoId: string }> },
) {
  const { photoId } = await params;
  return proxyAppRoute(request, `/api/station-photos/file/${encodeURIComponent(photoId)}`);
}
