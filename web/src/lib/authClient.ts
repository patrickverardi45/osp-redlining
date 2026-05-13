// Phase 1 real auth client.
// All /auth/* requests are proxied through Next.js (/api/auth/*) to avoid
// cross-origin CORS issues with credentialed fetches. Explicit proxy routes
// live at web/src/app/api/auth/{login,refresh,logout,me}/route.ts and
// forward to the real backend via web/src/lib/server/authProxy.ts.

import { clearAccessToken, getAccessToken, setAccessToken } from "@/lib/accessToken";

// Relative paths — always same-origin, no CORS, no env var needed here.
const AUTH_PREFIX = "/api/auth";

export interface AuthUser {
  id: string;
  email: string;
  display_name: string | null;
  company_id: string;
  company_slug: string;
  role: string;
}

export async function login(email: string, password: string): Promise<AuthUser> {
  const res = await fetch(`${AUTH_PREFIX}/login`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? "Login failed");
  }
  const data = await res.json();
  setAccessToken(data.access_token);
  return data.user as AuthUser;
}

// Returns true if a valid access token was obtained; false otherwise.
export async function refresh(): Promise<boolean> {
  try {
    const res = await fetch(`${AUTH_PREFIX}/refresh`, {
      method: "POST",
      credentials: "include",
    });
    if (!res.ok) return false;
    const data = await res.json();
    setAccessToken(data.access_token);
    return true;
  } catch {
    return false;
  }
}

export async function logout(): Promise<void> {
  clearAccessToken();
  await fetch(`${AUTH_PREFIX}/logout`, {
    method: "POST",
    credentials: "include",
  }).catch(() => {});
}

export async function me(): Promise<AuthUser | null> {
  const token = getAccessToken();
  if (!token) return null;
  try {
    const res = await fetch(`${AUTH_PREFIX}/me`, {
      credentials: "include",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return null;
    return (await res.json()) as AuthUser;
  } catch {
    return null;
  }
}
