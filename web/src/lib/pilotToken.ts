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
