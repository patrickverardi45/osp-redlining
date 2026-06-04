import { NextRequest } from "next/server";
import { proxyAppRoute } from "@/lib/server/appProxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
// Same-origin proxy for the gated PDF-first evidence artifact (overlay PNG) route.
// PdfFirstEvidencePanel fetches
//   apiFetch("/api/pdf-first-evidence/{session_id}/artifact?name=<basename>")
// and renders the blob as an <img>. Without this handler the next.config fallback
// rewrite forwards to 127.0.0.1:8000, which has nothing listening on Vercel and 404s.
// GET-only (the backend route is @localhost_router.get; read-only). proxyAppRoute
// preserves the ?name query, forwards the Authorization header, and streams the
// image/png body through unchanged.
export const maxDuration = 60;

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ session_id: string }> },
) {
  const { session_id } = await params;
  return proxyAppRoute(
    request,
    `/api/pdf-first-evidence/${encodeURIComponent(session_id)}/artifact`,
  );
}
