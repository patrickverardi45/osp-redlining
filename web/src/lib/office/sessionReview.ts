// web/src/lib/office/sessionReview.ts
//
// Phase 4F - frontend-only session review status.
// Phase 4G - frontend-only reviewer notes.
//
// State lives entirely in the browser via localStorage. There is NO backend
// call, NO API contract change, and NO mutation of the Session interface
// in @/lib/api. When the eventual backend gains real review fields, these
// hooks can be swapped to read/write through the API while consumers keep
// the same call shape.
//
// Storage layout:
//   key:   osp_session_review:{sessionId}
//   value: "needs_review" | "reviewed"
//
//   key:   osp_session_review_note:{sessionId}
//   value: reviewer note text, capped at NOTE_MAX_LENGTH
//
// "needs_review" is the implicit default when no status key is present, so
// we never write that value - we just delete the key on reset. Empty notes
// also delete their key. This keeps localStorage tidy and avoids re-emitting
// writes for default/empty state.
//
// Hooks subscribe to the `storage` event so two open tabs stay in sync within
// the same browser. SSR safety: every localStorage access is guarded behind a
// typeof window check, and hooks return defaults until the first mount-effect
// runs.
"use client";

import { useCallback, useEffect, useState } from "react";

export type SessionReviewStatus = "needs_review" | "reviewed";

const STORAGE_PREFIX = "osp_session_review:";
const NOTE_STORAGE_PREFIX = "osp_session_review_note:";
const NOTE_MAX_LENGTH = 1000;

const SAME_TAB_EVENT = "osp:session-review-changed";
const SAME_TAB_NOTE_EVENT = "osp:session-review-note-changed";

function storageKey(sessionId: string): string {
  return `${STORAGE_PREFIX}${sessionId}`;
}

function noteStorageKey(sessionId: string): string {
  return `${NOTE_STORAGE_PREFIX}${sessionId}`;
}

function isValidStatus(value: unknown): value is SessionReviewStatus {
  return value === "needs_review" || value === "reviewed";
}

function normalizeReviewNote(text: string): string {
  return text.slice(0, NOTE_MAX_LENGTH);
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
      window.localStorage.removeItem(storageKey(sessionId));
    } else {
      window.localStorage.setItem(storageKey(sessionId), status);
    }
  } catch {
    return;
  }
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

export function getSessionReviewNote(sessionId: string): string {
  if (!sessionId) return "";
  if (typeof window === "undefined") return "";
  try {
    const raw = window.localStorage.getItem(noteStorageKey(sessionId));
    return raw ? normalizeReviewNote(raw) : "";
  } catch {
    return "";
  }
}

export function setSessionReviewNote(sessionId: string, text: string): void {
  if (!sessionId) return;
  if (typeof window === "undefined") return;
  const note = normalizeReviewNote(text);
  try {
    if (note.trim().length === 0) {
      window.localStorage.removeItem(noteStorageKey(sessionId));
    } else {
      window.localStorage.setItem(noteStorageKey(sessionId), note);
    }
  } catch {
    return;
  }
  try {
    window.dispatchEvent(
      new CustomEvent<SessionReviewNoteChangePayload>(SAME_TAB_NOTE_EVENT, {
        detail: { sessionId, note: note.trim().length === 0 ? "" : note },
      }),
    );
  } catch {
    /* ignore */
  }
}

type SessionReviewChangePayload = {
  sessionId: string;
  status: SessionReviewStatus;
};

type SessionReviewNoteChangePayload = {
  sessionId: string;
  note: string;
};

export function useSessionReview(sessionId: string | null | undefined): {
  status: SessionReviewStatus;
  setStatus: (next: SessionReviewStatus) => void;
  toggleReviewed: () => void;
} {
  const [status, setStatusState] = useState<SessionReviewStatus>("needs_review");

  useEffect(() => {
    if (!sessionId) {
      setStatusState("needs_review");
      return;
    }
    setStatusState(getSessionReviewStatus(sessionId));

    const onStorage = (event: StorageEvent) => {
      if (!event.key) return;
      if (event.key !== storageKey(sessionId)) return;
      const next = isValidStatus(event.newValue)
        ? event.newValue
        : "needs_review";
      setStatusState(next);
    };

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

export function useSessionReviewNote(sessionId: string | null | undefined): {
  note: string;
  setNote: (next: string) => void;
} {
  const [note, setNoteState] = useState<string>("");

  useEffect(() => {
    if (!sessionId) {
      setNoteState("");
      return;
    }
    setNoteState(getSessionReviewNote(sessionId));

    const onStorage = (event: StorageEvent) => {
      if (!event.key) return;
      if (event.key !== noteStorageKey(sessionId)) return;
      setNoteState(event.newValue ? normalizeReviewNote(event.newValue) : "");
    };

    const onSameTab = (event: Event) => {
      const detail = (event as CustomEvent<SessionReviewNoteChangePayload>)
        .detail;
      if (!detail || detail.sessionId !== sessionId) return;
      setNoteState(normalizeReviewNote(detail.note));
    };

    window.addEventListener("storage", onStorage);
    window.addEventListener(SAME_TAB_NOTE_EVENT, onSameTab as EventListener);

    return () => {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener(
        SAME_TAB_NOTE_EVENT,
        onSameTab as EventListener,
      );
    };
  }, [sessionId]);

  const setNote = useCallback(
    (next: string) => {
      if (!sessionId) return;
      const normalized = normalizeReviewNote(next);
      setSessionReviewNote(sessionId, normalized);
      setNoteState(normalized.trim().length === 0 ? "" : normalized);
    },
    [sessionId],
  );

  return { note, setNote };
}

export const SESSION_REVIEW_LABELS: Record<SessionReviewStatus, string> = {
  needs_review: "Needs Review",
  reviewed: "Reviewed",
};
