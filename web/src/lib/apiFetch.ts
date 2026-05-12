// web/src/lib/apiFetch.ts
// Token preference: real access token (in-memory) → pilot token (localStorage).
// On 401, attempts one silent refresh and retries once. Auth routes are not retried.

import { getAccessToken } from "@/lib/accessToken";
import { refresh } from "@/lib/authClient";
import { getPilotToken } from "@/lib/pilotToken";

function buildHeaders(init?: RequestInit): Headers {
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
  return headers;
}

async function _apiFetch(
  url: string,
  init?: RequestInit,
  didRetry: boolean = false,
): Promise<Response> {
  const resp = await fetch(url, { ...init, headers: buildHeaders(init) });

  if (resp.status === 401 && !didRetry && !url.includes("/auth/")) {
    const refreshed = await refresh();
    if (refreshed) {
      return _apiFetch(url, init, true);
    }
  }

  return resp;
}

export async function apiFetch(url: string, init?: RequestInit): Promise<Response> {
  return _apiFetch(url, init, false);
}
