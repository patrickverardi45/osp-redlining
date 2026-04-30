const SESSION_STORAGE_KEY = "osp_session_id";

function canUseLocalStorage(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function sessionStorageKey(projectId?: string): string {
  const scopedProjectId = projectId?.trim();
  return scopedProjectId ? `${SESSION_STORAGE_KEY}:${scopedProjectId}` : SESSION_STORAGE_KEY;
}

export function getStoredSessionId(projectId?: string): string | null {
  if (!canUseLocalStorage()) return null;
  const value = window.localStorage.getItem(sessionStorageKey(projectId));
  const sessionId = value?.trim();
  return sessionId || null;
}

export function getSessionId(projectId?: string): string | null {
  return getStoredSessionId(projectId);
}

export function getOrCreateSessionId(projectId?: string): string | null {
  const existing = getStoredSessionId(projectId);
  if (existing) return existing;
  if (!canUseLocalStorage()) return null;

  const generated =
    typeof window.crypto?.randomUUID === "function"
      ? window.crypto.randomUUID().replace(/-/g, "")
      : `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`;
  window.localStorage.setItem(sessionStorageKey(projectId), generated);
  return generated;
}

export function saveSessionId(value: unknown, projectId?: string): string | null {
  const sessionId = typeof value === "string" ? value.trim() : "";
  if (!sessionId || !canUseLocalStorage()) return null;
  window.localStorage.setItem(sessionStorageKey(projectId), sessionId);
  return sessionId;
}

export function rememberSessionFromResponse(data: unknown, projectId?: string): string | null {
  if (!data || typeof data !== "object") return null;
  return saveSessionId((data as { session_id?: unknown }).session_id, projectId);
}

export function appendSessionId(url: string, projectId?: string): string {
  const sessionId = getOrCreateSessionId(projectId);
  if (!sessionId) return url;
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}session_id=${encodeURIComponent(sessionId)}`;
}

export function appendSessionIdToForm(form: FormData, projectId?: string): void {
  const sessionId = getOrCreateSessionId(projectId);
  if (sessionId && !form.has("session_id")) {
    form.append("session_id", sessionId);
  }
}
