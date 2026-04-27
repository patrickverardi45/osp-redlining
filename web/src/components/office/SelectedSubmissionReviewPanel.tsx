// web/src/components/office/SelectedSubmissionReviewPanel.tsx
//
// Phase 4E - compact "Selected Submission Review" card.
// Phase 4F - live review badge + "Mark as Reviewed" toggle.
// Phase 4G - frontend-only reviewer notes.
"use client";

import { useEffect, useState } from "react";

import type { Session } from "@/lib/api";
import {
  SESSION_REVIEW_LABELS,
  useSessionReview,
  useSessionReviewNote,
} from "@/lib/office/sessionReview";

type SelectedSubmissionReviewPanelProps = {
  selectedSessionId: string;
  session: Session | null;
};

function shortenId(rawId: string): string {
  if (!rawId) return "-";
  return rawId.length <= 8 ? rawId : rawId.slice(0, 8);
}

function formatDate(ts: string | null | undefined): string {
  if (!ts) return "-";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatDateTime(ts: string | null | undefined): string {
  if (!ts) return "-";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

function safeCount(n: unknown): number {
  return typeof n === "number" && Number.isFinite(n) ? n : 0;
}

export default function SelectedSubmissionReviewPanel({
  selectedSessionId,
  session,
}: SelectedSubmissionReviewPanelProps) {
  const { status: reviewStatus, toggleReviewed } = useSessionReview(
    selectedSessionId,
  );
  const { note: savedNote, setNote } = useSessionReviewNote(selectedSessionId);
  const [noteDraft, setNoteDraft] = useState("");
  const [noteJustSaved, setNoteJustSaved] = useState(false);
  const isReviewed = reviewStatus === "reviewed";

  useEffect(() => {
    setNoteDraft(savedNote);
    setNoteJustSaved(false);
  }, [savedNote, selectedSessionId]);

  const saveReviewerNote = () => {
    setNote(noteDraft);
    setNoteJustSaved(true);
  };

  const clearReviewerNote = () => {
    setNoteDraft("");
    setNote("");
    setNoteJustSaved(true);
  };

  if (!session) {
    return (
      <section
        aria-label="Selected submission review"
        className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"
      >
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <div className="font-semibold">Selected Submission Review</div>
            <div className="mt-1 text-xs">
              Could not find session{" "}
              <span className="font-mono">
                {shortenId(selectedSessionId)}
              </span>{" "}
              on this job. The link may be out of date.
            </div>
          </div>
        </div>
      </section>
    );
  }

  const stations = safeCount(session.station_count);
  const photos = safeCount(session.photo_count);
  const breadcrumbs = safeCount(session.track_point_count);
  const crew = session.crew_name?.trim() || "-";

  const badgeClass = isReviewed
    ? "inline-flex items-center rounded-full border border-green-200 bg-green-50 px-2 py-0.5 text-xs font-medium text-green-800 whitespace-nowrap"
    : "inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800 whitespace-nowrap";

  const actionButtonClass = isReviewed
    ? "inline-flex items-center rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs font-semibold text-gray-700 hover:bg-gray-50 transition-colors"
    : "inline-flex items-center rounded-md border border-green-700 bg-green-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-green-800 transition-colors";

  return (
    <section
      aria-label="Selected submission review"
      className="rounded-lg border border-gray-200 bg-white shadow-sm overflow-hidden"
    >
      <div className="border-b border-gray-100 bg-gray-50 px-4 py-3 flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-base font-semibold text-gray-800">
            Selected Submission Review
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Came in from the Field Submissions Inbox. Review marks are saved
            on this device only.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={badgeClass}
            aria-label={`Status: ${SESSION_REVIEW_LABELS[reviewStatus]}`}
          >
            {SESSION_REVIEW_LABELS[reviewStatus]}
          </span>
          <button
            type="button"
            onClick={toggleReviewed}
            className={actionButtonClass}
            aria-pressed={isReviewed}
          >
            {isReviewed ? "Undo Review" : "Mark as Reviewed"}
          </button>
        </div>
      </div>

      <dl className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 divide-x divide-y sm:divide-y-0 divide-gray-100">
        <Cell label="Session" mono>
          {shortenId(session.id)}
        </Cell>
        <Cell label="Crew">{crew}</Cell>
        <Cell label="Date">
          <div className="text-gray-800">{formatDate(session.started_at)}</div>
          <div className="text-[11px] text-gray-400 mt-0.5">
            {formatDateTime(session.started_at)}
          </div>
        </Cell>
        <Cell label="Stations" align="right" mono>
          {stations.toLocaleString()}
        </Cell>
        <Cell label="Photos" align="right" mono>
          {photos.toLocaleString()}
        </Cell>
        <Cell label="Breadcrumbs" align="right" mono>
          {breadcrumbs.toLocaleString()}
        </Cell>
      </dl>

      <details
        className="border-t border-gray-100 bg-white"
        defaultOpen={Boolean(savedNote)}
      >
        <summary className="cursor-pointer select-none px-4 py-3 text-sm font-semibold text-gray-800 hover:bg-gray-50">
          Reviewer Notes
          {savedNote ? (
            <span className="ml-2 rounded-full bg-blue-50 px-2 py-0.5 text-[11px] font-medium text-blue-700 border border-blue-100">
              Saved on this device
            </span>
          ) : null}
        </summary>
        <div className="px-4 pb-4">
          <label htmlFor="session-review-note" className="sr-only">
            Reviewer Notes
          </label>
          <textarea
            id="session-review-note"
            value={noteDraft}
            onChange={(event) => {
              setNoteDraft(event.target.value.slice(0, 1000));
              setNoteJustSaved(false);
            }}
            maxLength={1000}
            rows={4}
            placeholder="Add reviewer notes for this session..."
            className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-800 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
          />
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
            <div className="text-xs text-gray-500">
              {noteDraft.length.toLocaleString()} / 1,000 characters
              {noteJustSaved ? (
                <span className="ml-2 font-medium text-green-700">
                  Saved on this device
                </span>
              ) : null}
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={clearReviewerNote}
                className="inline-flex items-center rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs font-semibold text-gray-700 hover:bg-gray-50 transition-colors"
              >
                Clear
              </button>
              <button
                type="button"
                onClick={saveReviewerNote}
                className="inline-flex items-center rounded-md border border-blue-700 bg-blue-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-800 transition-colors"
              >
                Save
              </button>
            </div>
          </div>
        </div>
      </details>
    </section>
  );
}

function Cell({
  label,
  children,
  align,
  mono,
}: {
  label: string;
  children: React.ReactNode;
  align?: "left" | "right";
  mono?: boolean;
}) {
  return (
    <div
      className={`px-4 py-3 ${
        align === "right" ? "text-right" : "text-left"
      }`}
    >
      <dt className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
        {label}
      </dt>
      <dd
        className={`mt-1 text-sm text-gray-800 ${
          mono ? "font-mono" : ""
        } ${align === "right" ? "tabular-nums" : ""}`}
      >
        {children}
      </dd>
    </div>
  );
}
