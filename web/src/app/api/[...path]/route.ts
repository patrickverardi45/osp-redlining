// Server-side catch-all that proxies all non-auth /api/* requests to the backend.
// Keeps browser calls same-origin — no NEXT_PUBLIC_ env vars needed in client bundles.
//
// Path mapping:
//   /api/jobs/**        → backend /jobs/**        (backend root, no /api/ prefix)
//   /api/exceptions/**  → backend /exceptions/**  (backend root, no /api/ prefix)
//   /api/<anything>     → backend /api/<anything>

import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const BACKEND_BASE =
  process.env.API_BASE?.replace(/\/+$/, "") ||
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/+$/, "") ||
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, "") ||
  "http://127.0.0.1:8000";

// These top-level paths live at the backend root, not under /api/.
const BACKEND_ROOT_SEGMENTS = new Set(["jobs", "exceptions"]);

async function proxyToBackend(
  request: NextRequest,
  pathSegments: string[],
): Promise<NextResponse> {
  try {
    const firstSegment = pathSegments[0] ?? "";
    const joinedPath = pathSegments.join("/");

    // Jobs and exceptions are at the backend root, not under /api/.
    const backendPath = BACKEND_ROOT_SEGMENTS.has(firstSegment)
      ? `/${joinedPath}`
      : `/api/${joinedPath}`;

    const incomingUrl = new URL(request.url);
    const search = incomingUrl.search; // e.g. "?session_id=abc"
    const backendUrl = `${BACKEND_BASE}${backendPath}${search}`;

    const forwardHeaders = new Headers();

    const contentType = request.headers.get("content-type");
    if (contentType) forwardHeaders.set("content-type", contentType);

    const authorization = request.headers.get("authorization");
    if (authorization) forwardHeaders.set("authorization", authorization);

    const cookie = request.headers.get("cookie");
    if (cookie) forwardHeaders.set("cookie", cookie);

    const hasBody = request.method !== "GET" && request.method !== "HEAD";
    const body = hasBody ? await request.arrayBuffer() : undefined;

    const upstream = await fetch(backendUrl, {
      method: request.method,
      headers: forwardHeaders,
      body,
      cache: "no-store",
    });

    const responseBody =
      upstream.status === 204 ? null : await upstream.arrayBuffer();

    const response = new NextResponse(responseBody, { status: upstream.status });

    const ct = upstream.headers.get("content-type");
    if (ct) response.headers.set("content-type", ct);

    const setCookie = upstream.headers.get("set-cookie");
    if (setCookie) response.headers.set("set-cookie", setCookie);

    return response;
  } catch (error) {
    return NextResponse.json(
      {
        detail: "Backend unreachable",
        error: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 502 },
    );
  }
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  return proxyToBackend(request, path);
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  return proxyToBackend(request, path);
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  return proxyToBackend(request, path);
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  return proxyToBackend(request, path);
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  return proxyToBackend(request, path);
}
