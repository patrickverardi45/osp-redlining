// web/src/lib/office/sessionReview.ts
//
// Phase 4F — frontend-only session review status.
//
// State lives entirely in the browser via localStorage. There is NO backend
// call, NO API contract change, and NO mutation of the Session interface
// in @/lib/api. When the eventual backend gains a real review-status field,
// the same hook can be swapped to read/write through the API while every
// consumer keeps the same call shape.
//
// Storage layout:
//   key:   osp_session_review:{sessionId}
//   value: "needs_review" | "reviewed"
//
// "needs_review" is the implicit default when no key is present, so we
// never write that value — we just delete the key on reset. This keeps
// localStorage tidy and avoids re-emitting writes for the default state.
//
// The hook also subscribes to the `storage` event so two open tabs stay
// in sync within the same browser. SSR safety: every localStorage access
// is guarded behind a typeof window check, and the hook returns the
// default until the first mount-effect runs.
"use client";

import { useCallback, useEffect, useState } from "react";

// ─── Public types ─────────────────────────────────────────────────────────────

export type SessionReviewStatus = "needs_review" | "reviewed";

const STORAGE_PREFIX = "osp_session_review:";

// Custom event name for same-tab updates. The native `storage` event only
// fires across tabs; same-tab subscribers need a separate signal so a
// "Mark Reviewed" click in the SelectedSubmissionReviewPanel propagates to
// the SessionListPanel and inbox panels rendered alongside it.
const SAME_TAB_EVENT = "osp:session-review-changed";

// ─── Pure read/write functions ────────────────────────────────────────────────

function storageKey(sessionId: string): string {
  return `${STORAGE_PREFIX}${sessionId}`;
}

function isValidStatus(value: unknown): value is SessionReviewStatus {
  return value === "needs_review" || value === "reviewed";
}

export function getSessionReviewStatus(
  sessionId: string,
): SessionReviewStatus {
  if (!sessionId) return "needs_review";
  if (typeof window === "undefined") return "needs_review";
  try {
    const raw = window.localStorage.getItem(storageKey(sessionId));
    if (!raw) return "needs_review";
    return isValidStatus(raw) ? raw : "needs_review";
  } catch {
    // localStorage can throw in private browsing or when quota exceeded.
    // Failing closed to "needs_review" is safe — the worst case is the
    // reviewer marks something twice.
    return "needs_review";
  }
}

export function setSessionReviewStatus(
  sessionId: string,
  status: SessionReviewStatus,
): void {
  if (!sessionId) return;
  if (typeof window === "undefined") return;
  try {
    if (status === "needs_review") {
      // Default state — delete the key rather than write the default.
      window.localStorage.removeItem(storageKey(sessionId));
    } else {
      window.localStorage.setItem(storageKey(sessionId), status);
    }
  } catch {
    // Same rationale as the read path — silently no-op if storage is
    // unavailable. Visible side effect for the user: their click appears
    // to do nothing, which is acceptable in private browsing.
    return;
  }
  // Notify same-tab subscribers. Cross-tab subscribers receive the native
  // `storage` event automatically and don't need this dispatch.
  try {
    window.dispatchEvent(
      new CustomEvent<SessionReviewChangePayload>(SAME_TAB_EVENT, {
        detail: { sessionId, status },
      }),
    );
  } catch {
    /* ignore */
  }
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

type SessionReviewChangePayload = {
  sessionId: string;
  status: SessionReviewStatus;
};

/**
 * useSessionReview
 *
 * Returns the current review status for a session id, plus a setter that
 * persists to localStorage and notifies other subscribers in the same tab
 * (and other tabs via the native `storage` event).
 *
 * `sessionId` may be null/empty during initial render — the hook returns
 * "needs_review" in that case and the setter is a no-op.
 */
export function useSessionReview(sessionId: string | null | undefined): {
  status: SessionReviewStatus;
  setStatus: (next: SessionReviewStatus) => void;
  toggleReviewed: () => void;
} {
  // Server / first-render: always start at the default. We hydrate to the
  // real localStorage value inside useEffect so we never produce a server
  // vs. client mismatch.
  const [status, setStatusState] = useState<SessionReviewStatus>("needs_review");

  useEffect(() => {
    if (!sessionId) {
      setStatusState("needs_review");
      return;
    }
    setStatusState(getSessionReviewStatus(sessionId));

    // Cross-tab listener.
    const onStorage = (event: StorageEvent) => {
      if (!event.key) return;
      if (event.key !== storageKey(sessionId)) return;
      // event.newValue is null when the key was removed (i.e. status reset).
      const next = isValidStatus(event.newValue)
        ? event.newValue
        : "needs_review";
      setStatusState(next);
    };

    // Same-tab listener. Custom event so multiple components in the same
    // page see updates without forcing a page-level state lift.
    const onSameTab = (event: Event) => {
      const detail = (event as CustomEvent<SessionReviewChangePayload>).detail;
      if (!detail || detail.sessionId !== sessionId) return;
      setStatusState(detail.status);
    };

    window.addEventListener("storage", onStorage);
    window.addEventListener(SAME_TAB_EVENT, onSameTab as EventListener);

    return () => {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener(SAME_TAB_EVENT, onSameTab as EventListener);
    };
  }, [sessionId]);

  const setStatus = useCallback(
    (next: SessionReviewStatus) => {
      if (!sessionId) return;
      setSessionReviewStatus(sessionId, next);
      // Update local state immediately so the calling component sees the
      // change on the same render cycle. The same-tab event will arrive
      // next tick and be a no-op (state already matches).
      setStatusState(next);
    },
    [sessionId],
  );

  const toggleReviewed = useCallback(() => {
    if (!sessionId) return;
    const current = getSessionReviewStatus(sessionId);
    const next: SessionReviewStatus =
      current === "reviewed" ? "needs_review" : "reviewed";
    setSessionReviewStatus(sessionId, next);
    setStatusState(next);
  }, [sessionId]);

  return { status, setStatus, toggleReviewed };
}

// ─── Display helpers ──────────────────────────────────────────────────────────

export const SESSION_REVIEW_LABELS: Record<SessionReviewStatus, string> = {
  needs_review: "Needs Review",
  reviewed: "Reviewed",
};
