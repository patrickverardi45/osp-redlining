import { NextRequest } from "next/server";
import { proxyAppRoute } from "@/lib/server/appProxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export function GET(
  request: NextRequest,
  { params }: { params: Promise<{ photoId: string }> },
) {
  return params.then(({ photoId }) =>
    proxyAppRoute(request, `/api/station-photos/file/${encodeURIComponent(photoId)}`),
  );
}
