const SESSION_STORAGE_KEY = "osp_session_id";

function canUseLocalStorage(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

export function getStoredSessionId(): string | null {
  if (!canUseLocalStorage()) return null;
  const value = window.localStorage.getItem(SESSION_STORAGE_KEY);
  const sessionId = value?.trim();
  return sessionId || null;
}

export function getOrCreateSessionId(): string | null {
  const existing = getStoredSessionId();
  if (existing) return existing;
  if (!canUseLocalStorage()) return null;

  const generated =
    typeof window.crypto?.randomUUID === "function"
      ? window.crypto.randomUUID().replace(/-/g, "")
      : `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`;
  window.localStorage.setItem(SESSION_STORAGE_KEY, generated);
  return generated;
}

export function saveSessionId(value: unknown): string | null {
  const sessionId = typeof value === "string" ? value.trim() : "";
  if (!sessionId || !canUseLocalStorage()) return null;
  window.localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
  return sessionId;
}

export function rememberSessionFromResponse(data: unknown): string | null {
  if (!data || typeof data !== "object") return null;
  return saveSessionId((data as { session_id?: unknown }).session_id);
}

export function appendSessionId(url: string): string {
  const sessionId = getOrCreateSessionId();
  if (!sessionId) return url;
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}session_id=${encodeURIComponent(sessionId)}`;
}

export function appendSessionIdToForm(form: FormData): void {
  const sessionId = getOrCreateSessionId();
  if (sessionId && !form.has("session_id")) {
    form.append("session_id", sessionId);
  }
}
