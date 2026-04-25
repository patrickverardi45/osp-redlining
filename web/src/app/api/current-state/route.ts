import { NextResponse } from "next/server";

const BACKEND_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/+$/, "") ||
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, "") ||
  "http://127.0.0.1:8000";

export async function GET(request: Request) {
  try {
    const incomingUrl = new URL(request.url);
    const sessionId = incomingUrl.searchParams.get("session_id");
    const backendUrl = new URL(`${BACKEND_BASE}/api/current-state`);
    if (sessionId) {
      backendUrl.searchParams.set("session_id", sessionId);
    }

    const response = await fetch(backendUrl.toString(), {
      method: "GET",
      cache: "no-store",
    });

    const text = await response.text();

    return new NextResponse(text, {
      status: response.status,
      headers: {
        "content-type": response.headers.get("content-type") || "application/json",
        "cache-control": "no-store",
      },
    });
  } catch (error) {
    return NextResponse.json(
      {
        error: "Office backend unreachable",
        detail: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 502 }
    );
  }
}