// web/src/components/office/SessionListPanel.tsx
//
// Phase 4A: Session/Date columns + "Breadcrumbs" rename.
// Phase 4E: optional `highlightedSessionId` row highlight.
// Phase 4F: secondary "Reviewed" badge sourced from client-side review state.

"use client";

import type { Session } from "@/lib/api";
import {
  useSessionReview,
} from "@/lib/office/sessionReview";

interface SessionListPanelProps {
  sessions: Session[];
  // Phase 4E: when set, the matching row is highlighted so reviewers who
  // arrive via the Field Submissions Inbox can see at a glance which
  // session their `?session=` query param refers to. Optional — the panel
  // works exactly as before when not supplied.
  highlightedSessionId?: string | null;
}

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "https://walkv1-backend.onrender.com"
).replace(/\/+$/, "");

function resolvePhotoUrl(photoUrl: string): string {
  if (/^https?:\/\//i.test(photoUrl)) {
    try {
      const parsed = new URL(photoUrl);
      const isLocalhostHost =
        parsed.hostname === "localhost" ||
        parsed.hostname === "127.0.0.1" ||
        parsed.hostname === "0.0.0.0";
      if (isLocalhostHost) {
        const normalizedPath = `${parsed.pathname}${parsed.search}${parsed.hash}`;
        return API_BASE_URL ? `${API_BASE_URL}${normalizedPath}` : normalizedPath;
      }
      return photoUrl;
    } catch {
      return photoUrl;
    }
  }
  const normalizedPath = photoUrl.startsWith("/") ? photoUrl : `/${photoUrl}`;
  return API_BASE_URL ? `${API_BASE_URL}${normalizedPath}` : normalizedPath;
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

// Phase 4F: secondary review badge. Only renders when the session has been
// marked "reviewed" client-side; default ("needs_review") is intentionally
// silent here so the row doesn't gain visual noise for the common case.
// The badge sits next to the existing status badge — it does not replace it.
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

function formatTimestamp(ts: string | null): string {
  if (!ts) return "—";
  return new Date(ts).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

// Phase 4A: calendar-only date for the new "Date" column. Reads started_at
// off the existing Session type — no new fetch.
function formatDate(ts: string | null | undefined): string {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

// Phase 4A: shortened session id for the new "Session" column. Most ids are
// UUID-ish; surface the leading 8 chars so the column stays narrow.
function shortenSessionId(rawId: string): string {
  if (!rawId) return "—";
  return rawId.length <= 8 ? rawId : rawId.slice(0, 8);
}

function calcDuration(start: string, end: string | null): string {
  if (!end) return "In progress";
  const diffMs = new Date(end).getTime() - new Date(start).getTime();
  if (diffMs < 0) return "—";
  const totalMin = Math.floor(diffMs / 60000);
  const hours = Math.floor(totalMin / 60);
  const mins = totalMin % 60;
  if (hours === 0) return `${mins}m`;
  return `${hours}h ${mins}m`;
}

export default function SessionListPanel({
  sessions,
  highlightedSessionId,
}: SessionListPanelProps) {
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
                {/* Phase 4A: Session (shortened id) */}
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Session
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Crew
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Status
                </th>
                {/* Phase 4A: Date column (started_at, date only) */}
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
                {/* Phase 4A: Breadcrumbs (track_point_count) — renamed from
                    "Track Pts" so the field is named consistently with the
                    mobile /walk UI. */}
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
                  {/* Phase 4A: Session (shortened id) */}
                  <td className="px-4 py-3 font-mono text-xs text-gray-700 whitespace-nowrap">
                    {isHighlighted && (
                      <span
                        aria-hidden="true"
                        className="mr-1 inline-block h-1.5 w-1.5 rounded-full bg-amber-500 align-middle"
                      />
                    )}
                    {shortenSessionId(session.id)}
                  </td>
                  <td className="px-4 py-3 font-medium text-gray-800">
                    {session.crew_name}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <SessionStatusBadge status={session.status} />
                    {/* Phase 4F: secondary review badge. Only appears for
                        sessions that have been marked reviewed client-side. */}
                    <ReviewedBadge sessionId={session.id} />
                  </td>
                  {/* Phase 4A: Date column */}
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
                  {/* Phase 4A: Breadcrumbs (track_point_count) */}
                  <td className="px-4 py-3 text-right text-gray-700 tabular-nums">
                    {session.track_point_count?.toLocaleString?.() ?? 0}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-700 tabular-nums">
                    {session.station_count}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-700 tabular-nums">
                    {session.photo_count}
                  </td>

                  {/* 🔥 NEW: VIEW PHOTO */}
                  <td className="px-4 py-3 text-center">
                    {session.latest_photo_url ? (
                      <a
                        href={resolvePhotoUrl(session.latest_photo_url)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-600 hover:underline text-xs font-medium"
                      >
                        View Photo
                      </a>
                    ) : (
                      <span className="text-gray-300 text-xs">—</span>
                    )}
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
