// web/src/components/office/SessionListPanel.tsx
//
// Phase 4A: Session/Date columns + "Breadcrumbs" rename.
// Phase 4E: optional `highlightedSessionId` row highlight.
// Phase 4F: secondary "Reviewed" badge sourced from client-side review state.
// Phase 4G: local reviewer-note indicator.

"use client";

import { useState } from "react";
import type { Photo, Session } from "@/lib/api";
import {
  useSessionReview,
  useSessionReviewNote,
} from "@/lib/office/sessionReview";
import SessionPhotoGalleryModal, {
  sortPhotosByUploadedDesc,
  type SessionPhotoGallery,
} from "./SessionPhotoGalleryModal";

interface SessionListPanelProps {
  sessions: Session[];
  photos?: Photo[];
  highlightedSessionId?: string | null;
}

const SESSION_STATUS_CONFIG: Record<string, { label: string; className: string }> = {
  active: {
    label: "Active",
    className:
      "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700",
  },
  ended: {
    label: "Ended",
    className:
      "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600",
  },
  paused: {
    label: "Paused",
    className:
      "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-700",
  },
  syncing: {
    label: "Syncing",
    className:
      "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700",
  },
};

function SessionStatusBadge({ status }: { status: string }) {
  const config = SESSION_STATUS_CONFIG[status] ?? {
    label: status,
    className:
      "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-500",
  };
  return <span className={config.className}>{config.label}</span>;
}

function ReviewedBadge({ sessionId }: { sessionId: string }) {
  const { status } = useSessionReview(sessionId);
  if (status !== "reviewed") return null;
  return (
    <span
      className="ml-1.5 inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-50 text-green-700 border border-green-200"
      aria-label="Reviewed"
    >
      Reviewed
    </span>
  );
}

function NoteIndicator({ sessionId }: { sessionId: string }) {
  const { note } = useSessionReviewNote(sessionId);
  const trimmed = note.trim();
  if (!trimmed) return null;
  const preview = trimmed.length > 120 ? `${trimmed.slice(0, 117)}...` : trimmed;
  return (
    <span
      className="ml-1 inline-flex h-2 w-2 rounded-full bg-blue-500 align-middle"
      title={preview}
      aria-label={`Reviewer note: ${preview}`}
    />
  );
}

function formatTimestamp(ts: string | null): string {
  if (!ts) return "-";
  return new Date(ts).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
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

function shortenSessionId(rawId: string): string {
  if (!rawId) return "-";
  return rawId.length <= 8 ? rawId : rawId.slice(0, 8);
}

function calcDuration(start: string, end: string | null): string {
  if (!end) return "In progress";
  const diffMs = new Date(end).getTime() - new Date(start).getTime();
  if (diffMs < 0) return "-";
  const totalMin = Math.floor(diffMs / 60000);
  const hours = Math.floor(totalMin / 60);
  const mins = totalMin % 60;
  if (hours === 0) return `${mins}m`;
  return `${hours}h ${mins}m`;
}

export default function SessionListPanel({
  sessions,
  photos = [],
  highlightedSessionId,
}: SessionListPanelProps) {
  const [gallery, setGallery] = useState<SessionPhotoGallery | null>(null);

  return (
    <section>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-base font-semibold text-gray-800">
          Walk Sessions
          <span className="ml-2 text-gray-400 font-normal text-sm">
            ({sessions.length})
          </span>
        </h2>
      </div>

      {sessions.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50 py-10 text-center text-sm text-gray-400">
          No walk sessions yet
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200 shadow-sm">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Session
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Crew
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Date
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Started
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Ended
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Duration
                </th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Breadcrumbs
                </th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Stations
                </th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Photos
                </th>
                <th className="px-4 py-3 text-center text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  View
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-100">
              {sessions.map((session) => {
                const isHighlighted =
                  Boolean(highlightedSessionId) &&
                  session.id === highlightedSessionId;
                const sessionPhotos = photos.filter(
                  (p) =>
                    p.session_id != null && String(p.session_id) === session.id,
                );
                return (
                  <tr
                    key={session.id}
                    className={`transition-colors ${
                      isHighlighted
                        ? "bg-amber-50 hover:bg-amber-100 ring-1 ring-inset ring-amber-200"
                        : "hover:bg-gray-50"
                    }`}
                    aria-current={isHighlighted ? "true" : undefined}
                  >
                    <td className="px-4 py-3 font-mono text-xs text-gray-700 whitespace-nowrap">
                      {isHighlighted && (
                        <span
                          aria-hidden="true"
                          className="mr-1 inline-block h-1.5 w-1.5 rounded-full bg-amber-500 align-middle"
                        />
                      )}
                      {shortenSessionId(session.id)}
                      <NoteIndicator sessionId={session.id} />
                    </td>
                    <td className="px-4 py-3 font-medium text-gray-800">
                      {session.crew_name}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <SessionStatusBadge status={session.status} />
                      <ReviewedBadge sessionId={session.id} />
                    </td>
                    <td className="px-4 py-3 text-gray-700 whitespace-nowrap text-xs">
                      {formatDate(session.started_at)}
                    </td>
                    <td className="px-4 py-3 text-gray-500 whitespace-nowrap text-xs">
                      {formatTimestamp(session.started_at)}
                    </td>
                    <td className="px-4 py-3 text-gray-500 whitespace-nowrap text-xs">
                      {formatTimestamp(session.ended_at)}
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs whitespace-nowrap">
                      {calcDuration(session.started_at, session.ended_at)}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-700 tabular-nums">
                      {session.track_point_count?.toLocaleString?.() ?? 0}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-700 tabular-nums">
                      {session.station_count}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-700 tabular-nums">
                      {session.photo_count}
                    </td>
                    <td className="px-4 py-3 text-center">
                      {sessionPhotos.length > 0 ? (
                        <button
                          type="button"
                          onClick={() =>
                            setGallery({
                              kind: "list",
                              photos: sortPhotosByUploadedDesc(sessionPhotos),
                            })
                          }
                          className="text-blue-600 hover:underline text-xs font-medium"
                        >
                          {`View photos (${sessionPhotos.length})`}
                        </button>
                      ) : session.latest_photo_url ? (
                        <button
                          type="button"
                          onClick={() =>
                            setGallery({
                              kind: "fallback",
                              url: String(session.latest_photo_url),
                            })
                          }
                          className="text-blue-600 hover:underline text-xs font-medium"
                        >
                          View photo
                        </button>
                      ) : (
                        <span className="text-gray-300 text-xs">-</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <SessionPhotoGalleryModal
        gallery={gallery}
        onClose={() => setGallery(null)}
      />
    </section>
  );
}
