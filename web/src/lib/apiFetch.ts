// web/src/lib/apiFetch.ts

import { getPilotToken } from "@/lib/pilotToken";

export async function apiFetch(url: string, init?: RequestInit): Promise<Response> {
  const token = getPilotToken();
  if (!token) {
    return fetch(url, init);
  }
  const existingHeaders = new Headers(init?.headers);
  existingHeaders.set("Authorization", `Bearer ${token}`);
  const nextInit: RequestInit = { ...init, headers: existingHeaders };
  return fetch(url, nextInit);
}
