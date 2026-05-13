// Server-only helper — do not import from client components.
// Proxies /api/* calls from the Next.js server to the Render backend,
// keeping browser calls same-origin and avoiding CORS issues.

import { NextRequest, NextResponse } from "next/server";

const BACKEND_BASE =
  process.env.API_BASE?.replace(/\/+$/, "") ||
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/+$/, "") ||
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, "") ||
  "http://127.0.0.1:8000";

/**
 * Proxy a Next.js request to the backend at the given path.
 *
 * @param request   - Incoming NextRequest
 * @param backendPath - Backend-relative path, e.g. "/api/current-state" or "/jobs"
 */
export async function proxyAppRoute(
  request: NextRequest,
  backendPath: string,
): Promise<NextResponse> {
  try {
    const incomingUrl = new URL(request.url);
    const search = incomingUrl.search; // preserves ?session_id=... and all other params
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

    // 204 No Content has no body.
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
