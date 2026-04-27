// web/src/app/jobs/inbox/page.tsx
//
// Phase 4D: Field Submissions Inbox — full-page view.
//
// The actual inbox-data plumbing lives in the shared hook
// `useFieldSubmissions` (web/src/lib/office/fieldSubmissionsInbox.ts) so this
// page and the compact panel on the main Operator Workspace stay in sync
// without duplicating the getJobs / getJobById fan-out.
//
// This page does NOT mutate session state. It does not approve, reject, or
// otherwise change anything. It is a visibility-only view.
//
// Status mapping (Phase 4D):
//   - Any session whose `status` is "ended" is treated as "Needs Review".
//   - All other statuses (active, paused, syncing, anything else) are
//     considered in-progress and excluded from the inbox.
//
// Filters operate on `started_at`:
//   - "Needs Review" — every ended session, regardless of date
//   - "Today"        — ended sessions started today (local time)
//   - "This Week"    — ended sessions started within the last 7 days
//                      (rolling, inclusive of today)
"use client";

import Link from "next/link";

import {
  FIELD_SUBMISSIONS_FILTER_LABELS,
  formatSessionDate,
  formatSessionDateTime,
  safeCount,
  shortenSessionId,
  useFieldSubmissions,
  type InboxFilter,
} from "@/lib/office/fieldSubmissionsInbox";

const FILTER_KEYS: InboxFilter[] = ["needs_review", "today", "week"];

export default function FieldSubmissionsInboxPage() {
  const {
    filteredRows,
    counts,
    loading,
    error,
    partialFailures,
    filter,
    setFilter,
    refresh,
  } = useFieldSubmissions("needs_review");

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-6xl mx-auto px-6 py-10 space-y-6">
        {/* Breadcrumb / back link. The office app has no global sidebar, so
            we provide a simple way back to the jobs list. */}
        <nav className="text-sm text-gray-500">
          <Link href="/jobs" className="hover:text-blue-600 hover:underline">
            Jobs
          </Link>
          <span className="mx-2 text-gray-300">/</span>
          <span className="text-gray-800">Field Submissions Inbox</span>
        </nav>

        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            Field Submissions Inbox
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Walk sessions sent in from the field, ready for office review.
            Read-only — nothing here mutates job or session state.
          </p>
        </div>

        {/* Filter chips */}
        <div className="flex flex-wrap items-center gap-2">
          {FILTER_KEYS.map((key) => {
            const active = filter === key;
            return (
              <button
                key={key}
                type="button"
                onClick={() => setFilter(key)}
                className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                  active
                    ? "bg-gray-800 text-white border-gray-800"
                    : "bg-white text-gray-700 border-gray-200 hover:border-gray-400"
                }`}
              >
                {FIELD_SUBMISSIONS_FILTER_LABELS[key]}
                <span
                  className={`ml-2 inline-flex items-center justify-center rounded-full px-1.5 text-[10px] font-semibold ${
                    active
                      ? "bg-white/20 text-white"
                      : "bg-gray-100 text-gray-600"
                  }`}
                >
                  {counts[key]}
                </span>
              </button>
            );
          })}
          <div className="ml-auto">
            <button
              type="button"
              onClick={refresh}
              disabled={loading}
              className="px-3 py-1.5 rounded text-xs font-medium bg-white border border-gray-200 text-gray-700 hover:border-gray-400 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? "Refreshing…" : "Refresh"}
            </button>
          </div>
        </div>

        {/* Loading */}
        {loading && (
          <div className="text-sm text-gray-400 py-10 text-center">
            Loading field submissions…
          </div>
        )}

        {/* Hard error */}
        {!loading && error && (
          <div>
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              <span className="font-semibold">
                Error loading field submissions:
              </span>{" "}
              {error}
            </div>
            <button
              onClick={refresh}
              className="mt-3 px-3 py-1.5 rounded text-sm font-medium bg-gray-800 text-white hover:bg-gray-700 transition-colors"
            >
              Retry
            </button>
          </div>
        )}

        {/* Soft / partial failures — show inbox but warn that some jobs
            could not be loaded. */}
        {!loading && !error && partialFailures > 0 && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-800">
            {partialFailures === 1
              ? "1 job could not be loaded; its sessions are not shown."
              : `${partialFailures} jobs could not be loaded; their sessions are not shown.`}
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && filteredRows.length === 0 && (
          <div className="rounded-lg border border-dashed border-gray-200 bg-white py-16 text-center text-sm text-gray-400">
            No field submissions ready for review.
          </div>
        )}

        {/* Inbox rows */}
        {!loading && !error && filteredRows.length > 0 && (
          <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm">
            <table className="min-w-full divide-y divide-gray-200 text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                    Status
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                    Job
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                    Session
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                    Crew
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                    Date
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">
                    Stations
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">
                    Photos
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">
                    Breadcrumbs
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">
                    {""}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filteredRows.map((row) => {
                  const session = row.session;
                  return (
                    <tr
                      key={`${row.jobId}:${session.id}`}
                      className="hover:bg-gray-50 transition-colors"
                    >
                      <td className="px-4 py-3 whitespace-nowrap">
                        <span className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800">
                          Needs Review
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <Link
                          href={`/jobs/${row.jobId}?session=${encodeURIComponent(session.id)}`}
                          className="font-medium text-gray-900 hover:text-blue-600 hover:underline"
                        >
                          {row.jobLabel}
                        </Link>
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-gray-700 whitespace-nowrap">
                        {shortenSessionId(session.id)}
                      </td>
                      <td className="px-4 py-3 text-gray-700">
                        {session.crew_name?.trim() || (
                          <span className="text-gray-400">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <div className="text-gray-700">
                          {formatSessionDate(session.started_at)}
                        </div>
                        <div className="text-[11px] text-gray-400">
                          {formatSessionDateTime(session.started_at)}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums text-gray-700">
                        {safeCount(session.station_count).toLocaleString()}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums text-gray-700">
                        {safeCount(session.photo_count).toLocaleString()}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums text-gray-700">
                        {safeCount(
                          session.track_point_count,
                        ).toLocaleString()}
                      </td>
                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        <Link
                          href={`/jobs/${row.jobId}?session=${encodeURIComponent(session.id)}`}
                          className="text-xs font-medium text-blue-600 hover:underline"
                        >
                          View Session →
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
