// web/src/lib/apiFetch.ts
// Token preference: real access token (in-memory) → pilot token (localStorage).
// On 401, attempts one silent refresh and retries once. Auth routes are not retried.
// Attaches X-TL-Request-ID per call for backend log correlation. Logs failures to
// console.warn — never logs tokens, passwords, cookies, or file contents.

import { getAccessToken } from "@/lib/accessToken";
import { refresh } from "@/lib/authClient";
import { getPilotToken } from "@/lib/pilotToken";

function buildHeaders(init?: RequestInit, clientReqId?: string): Headers {
  const headers = new Headers(init?.headers);
  const accessToken = getAccessToken();
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  } else {
    const pilotToken = getPilotToken();
    if (pilotToken) {
      headers.set("Authorization", `Bearer ${pilotToken}`);
    }
  }
  if (clientReqId) {
    headers.set("x-tl-request-id", clientReqId);
  }
  return headers;
}

async function _apiFetch(
  url: string,
  init?: RequestInit,
  didRetry: boolean = false,
  clientReqId: string = "",
  action?: string,
): Promise<Response> {
  const resp = await fetch(url, { ...init, headers: buildHeaders(init, clientReqId) });

  if (resp.status === 401 && !didRetry && !url.includes("/auth/")) {
    const refreshed = await refresh();
    if (refreshed) {
      return _apiFetch(url, init, true, clientReqId, action);
    }
  }

  if (!resp.ok) {
    // Fire-and-forget: log failure context without blocking caller or consuming body.
    void resp
      .clone()
      .text()
      .catch(() => "")
      .then((body) => {
        console.warn("[apiFetch]", {
          t: "apiFetch_error",
          clientReqId,
          action: action ?? null,
          url,
          method: ((init?.method as string) ?? "GET").toUpperCase(),
          status: resp.status,
          bodyPreview: body.slice(0, 200).trim(),
          ts: new Date().toISOString(),
        });
      })
      .catch(() => {});
  }

  return resp;
}

export async function apiFetch(
  url: string,
  init?: RequestInit,
  action?: string,
): Promise<Response> {
  const clientReqId =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return _apiFetch(url, init, false, clientReqId, action);
}
