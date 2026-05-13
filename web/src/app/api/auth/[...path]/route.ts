import { NextRequest, NextResponse } from "next/server";

// Server-side proxy for all /auth/* calls.
// Eliminates cross-origin CORS issues: browser speaks to Vercel (same-origin),
// Next.js forwards to the Render backend server-side.
// Cookie path is rewritten from /auth → /api/auth so the browser stores the
// refresh cookie with a path that matches future /api/auth/refresh requests.

const BACKEND_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/+$/, "") ||
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, "") ||
  "http://127.0.0.1:8000";

type Params = { path: string[] };

async function handler(
  request: NextRequest,
  context: { params: Promise<Params> },
): Promise<NextResponse> {
  const { path } = await context.params;
  const backendUrl = `${BACKEND_BASE}/auth/${path.join("/")}`;

  try {
    const forwardHeaders = new Headers();

    const contentType = request.headers.get("content-type");
    if (contentType) forwardHeaders.set("content-type", contentType);

    // Forward the refresh cookie and any auth bearer token from the browser.
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

    // Forward the refresh cookie, rewriting its Path from /auth → /api/auth.
    // The backend sets Path=/auth; our proxy sits at /api/auth/*, so without
    // this rewrite the browser would never send the cookie back to us.
    const setCookie = upstream.headers.get("set-cookie");
    if (setCookie) {
      const rewritten = setCookie.replace(/\bPath=\/auth\b/gi, "Path=/api/auth");
      responseHeaders.set("set-cookie", rewritten);
    }

    // 204 No Content responses have no body.
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

export const GET = handler;
export const POST = handler;
export const DELETE = handler;
