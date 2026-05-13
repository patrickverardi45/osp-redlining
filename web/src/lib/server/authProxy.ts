// Server-only helper — do not import from client components.
// Proxies /auth/* calls from the Next.js server to the Render backend,
// eliminating cross-origin CORS issues for credentialed browser requests.
// Cookie Path is rewritten /auth → /api/auth so the browser sends
// the refresh cookie back on subsequent /api/auth/refresh requests.

import { NextRequest, NextResponse } from "next/server";

const BACKEND_BASE =
  process.env.API_BASE?.replace(/\/+$/, "") ||
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/+$/, "") ||
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, "") ||
  "http://127.0.0.1:8000";

export async function proxyAuthRoute(
  request: NextRequest,
  routeName: string,
): Promise<NextResponse> {
  const backendUrl = `${BACKEND_BASE}/auth/${routeName}`;

  try {
    const forwardHeaders = new Headers();

    const contentType = request.headers.get("content-type");
    if (contentType) forwardHeaders.set("content-type", contentType);

    const cookie = request.headers.get("cookie");
    if (cookie) forwardHeaders.set("cookie", cookie);

    const authorization = request.headers.get("authorization");
    if (authorization) forwardHeaders.set("authorization", authorization);

    const hasBody = request.method !== "GET" && request.method !== "HEAD";
    const body = hasBody ? await request.arrayBuffer() : undefined;

    const upstream = await fetch(backendUrl, {
      method: request.method,
      headers: forwardHeaders,
      body,
      cache: "no-store",
    });

    const responseHeaders = new Headers();

    const ct = upstream.headers.get("content-type");
    if (ct) responseHeaders.set("content-type", ct);

    // Rewrite the refresh cookie path so the browser stores it under
    // /api/auth and resends it on future /api/auth/refresh requests.
    const setCookie = upstream.headers.get("set-cookie");
    if (setCookie) {
      const rewritten = setCookie.replace(/\bPath=\/auth\b/gi, "Path=/api/auth");
      responseHeaders.set("set-cookie", rewritten);
    }

    // 204 No Content has no body.
    const responseBody = upstream.status === 204 ? null : await upstream.arrayBuffer();

    return new NextResponse(responseBody, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch (error) {
    return NextResponse.json(
      {
        detail: "Auth backend unreachable",
        error: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 502 },
    );
  }
}
