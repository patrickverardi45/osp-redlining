/**
 * Workspace Session Module — TrueLine OSP
 *
 * Three permitted caller tiers. Do not mix them:
 *
 * READ callers (fetchState, fetchCurrentState, fetchStationPhotos, exports):
 *   Use peekSessionId to read the stored id without minting a new session.
 *   Use appendSessionIdReadOnly to append it to a URL — returns the URL unchanged
 *   if no session is stored. Never pass a read response to acceptSessionFromMutation.
 *
 * WRITE callers (handleReset, upload handlers, route confirmation):
 *   Use appendSessionId or appendSessionIdToForm to attach the session to the request.
 *   Call acceptSessionFromMutation(data, projectId) once after the response to record
 *   the session transition and update localStorage.
 *
 * TELEMETRY / DIAGNOSTIC callers (submitBugNote, pipeline diagnostics):
 *   Must NOT adopt data.session_id. These paths observe state; they do not own it.
 *   Use appendSessionIdReadOnly on request URLs; discard any session_id in the response.
 *
 * DEPRECATED:
 *   rememberSessionFromResponse — zero legitimate callers in app code. Do not use it.
 */
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

/**
 * @deprecated Use {@link acceptSessionFromMutation} instead.
 * This function does not emit transition logs and cannot distinguish
 * read-path calls from authorised mutation callers.
 */
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

// ─── Workspace Session Boundary V1 ──────────────────────────────────────────
// Read/write separation and observability helpers.
// Audit: architecture/stabilization/workspace-state-boundary-v1.md

type SessionTransitionOp = "mutation-adopt" | "rotation" | "noop";

interface SessionTransition {
  ts: number;
  op: SessionTransitionOp;
  projectId: string | null;
  prev: string | null;
  next: string | null;
}

declare global {
  interface Window {
    __truelineSessionLog?: SessionTransition[];
    __truelineSessionLogClear?: () => void;
  }
}

const _sessionTransitionLog: SessionTransition[] = [];
const _SESSION_LOG_CAP = 50;

function _pushTransition(entry: SessionTransition): void {
  _sessionTransitionLog.push(entry);
  if (_sessionTransitionLog.length > _SESSION_LOG_CAP) {
    _sessionTransitionLog.shift();
  }
}

// Expose ring buffer in development builds only.
// Next.js statically replaces process.env.NODE_ENV, so this block is
// tree-shaken from production bundles.
if (typeof window !== "undefined" && process.env.NODE_ENV !== "production") {
  window.__truelineSessionLog = _sessionTransitionLog;
  window.__truelineSessionLogClear = () => {
    _sessionTransitionLog.length = 0;
  };
}

/**
 * Read-only alias for {@link getStoredSessionId}.
 * Never mints a session. Use on any path that only reads workspace state:
 * /api/current-state, /api/station-photos GET, exports.
 */
export function peekSessionId(projectId?: string): string | null {
  return getStoredSessionId(projectId);
}

/**
 * Same as {@link appendSessionId} but never mints a session.
 * If no session is stored the URL is returned unchanged.
 * Use on read paths so a cold-tab GET cannot create a session as a side-effect.
 */
export function appendSessionIdReadOnly(url: string, projectId?: string): string {
  const sessionId = getStoredSessionId(projectId);
  if (!sessionId) return url;
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}session_id=${encodeURIComponent(sessionId)}`;
}

/**
 * Authorised session adoption point for workspace mutators.
 *
 * Wraps the {@link rememberSessionFromResponse} behaviour and adds:
 * - a structured transition log entry on every call
 * - a console.debug on rotation (development builds only)
 *
 * Permitted callers: handleReset and upload handlers.
 * Forbidden on read paths — use {@link peekSessionId} + {@link appendSessionIdReadOnly}.
 *
 * Op codes:
 *   "noop"          – response had no valid session_id; nothing written.
 *   "mutation-adopt"– session confirmed or first adoption (prev → same or null → next).
 *   "rotation"      – server returned a different id than what was stored (prev → different next).
 *
 * @returns the session id now stored in localStorage, or null if the
 *          response contained no valid session_id.
 */
export function acceptSessionFromMutation(data: unknown, projectId?: string): string | null {
  if (!data || typeof data !== "object") return null;
  const prev = getStoredSessionId(projectId);
  const next = saveSessionId((data as { session_id?: unknown }).session_id, projectId);
  const op: SessionTransitionOp =
    next === null ? "noop" :
    prev !== null && prev !== next ? "rotation" :
    "mutation-adopt";
  _pushTransition({ ts: Date.now(), op, projectId: projectId ?? null, prev, next });
  if (op === "rotation" && process.env.NODE_ENV !== "production") {
    console.debug("[workspace-session] rotation", { prev, next, projectId });
  }
  return next;
}
