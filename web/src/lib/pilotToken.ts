// web/src/lib/pilotToken.ts

export const PILOT_TOKEN_STORAGE_KEY = "trueline_pilot_token";

function canUseLocalStorage(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

export function getPilotToken(): string | null {
  if (!canUseLocalStorage()) return null;
  const value = window.localStorage.getItem(PILOT_TOKEN_STORAGE_KEY);
  return value?.trim() || null;
}

export function savePilotToken(token: string): void {
  if (!canUseLocalStorage()) return;
  window.localStorage.setItem(PILOT_TOKEN_STORAGE_KEY, token.trim());
}

export function clearPilotToken(): void {
  if (!canUseLocalStorage()) return;
  window.localStorage.removeItem(PILOT_TOKEN_STORAGE_KEY);
}

export function looksLikeJwt(token: string): boolean {
  const parts = token.trim().split(".");
  return parts.length === 3 && parts.every((p) => p.length > 0);
}

export function isTokenExpired(token: string): boolean {
  if (typeof window === "undefined") return false;
  try {
    const payload = token.trim().split(".")[1];
    if (!payload) return false;
    const padded = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padLen = (4 - (padded.length % 4)) % 4;
    const decoded = atob(padded + "=".repeat(padLen));
    const claims = JSON.parse(decoded) as Record<string, unknown>;
    const exp = claims["exp"];
    if (typeof exp !== "number") return false;
    return Date.now() / 1000 >= exp;
  } catch {
    return false;
  }
}
