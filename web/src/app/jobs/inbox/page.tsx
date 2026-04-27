// web/src/app/jobs/inbox/page.tsx
//
// Phase 4D: Field Submissions Inbox.
//
// Office-only view that aggregates walk sessions across every job in the
// shop into a single "inbox" of field submissions waiting to be reviewed.
//
// Data plumbing notes (read this before changing anything):
//   - There is no global /sessions endpoint. We build the inbox by calling
//     getJobs() once and then getJobById() per job in parallel. This is a
//     fan-out, not a fake — every row corresponds to a real session
//     returned by the backend.
//   - This page does NOT mutate session state. It does not approve, reject,
//     or otherwise change anything. It is a visibility-only view.
//   - Phase 4D is intentionally read-only: the only action is an optional
//     "View Session" link that scrolls the existing job detail page to the
//     SessionListPanel. No new buttons, no approval workflow.
//
// Status mapping for this phase:
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

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { getJobs, getJobById } from "@/lib/api";
import type { Job, JobDetail, Session } from "@/lib/api";

// ─── Inbox row shape ──────────────────────────────────────────────────────────
// We flatten (job, session) pairs into one row per session so the table can
// render without nested loops. Only the fields the inbox actually shows are
// kept here; everything else stays on the underlying Session.

type InboxRow = {
  jobId: string;
  jobLabel: string;
  jobCode: string;
  session: Session;
};

type InboxFilter = "needs_review" | "today" | "week";

const FILTER_LABELS: Record<InboxFilter, string> = {
  needs_review: "Needs Review",
  today: "Today",
  week: "This Week",
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function shortenSessionId(rawId: string): string {
  if (!rawId) return "—";
  return rawId.length <= 8 ? rawId : rawId.slice(0, 8);
}

function formatSessionDate(ts: string | null | undefined): string {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatSessionDateTime(ts: string | null | undefined): string {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "—";
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

function jobLabelFor(job: Job): string {
  if (job.job_code && job.job_name) return `${job.job_code} — ${job.job_name}`;
  return job.job_name || job.job_code || job.id;
}

// "Today" = session started_at falls on today's local calendar date.
function isToday(ts: string): boolean {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return false;
  const now = new Date();
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  );
}

// "This Week" = session started_at within the last 7 days (rolling,
// inclusive of today). We use a ms threshold rather than ISO weeks so the
// behavior is unambiguous and locale-independent.
const WEEK_MS = 7 * 24 * 60 * 60 * 1000;

function isWithinLastWeek(ts: string): boolean {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return false;
  const now = Date.now();
  const t = d.getTime();
  return t >= now - WEEK_MS && t <= now;
}

// Phase 4D status rule. Only "ended" sessions are in the inbox.
function isCompleted(session: Session): boolean {
  return String(session.status || "").toLowerCase() === "ended";
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function FieldSubmissionsInboxPage() {
  const [rows, setRows] = useState<InboxRow[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  // Track per-job fetch failures separately so a single broken job detail
  // does not blank the whole inbox. We surface the count in a small notice.
  const [partialFailures, setPartialFailures] = useState<number>(0);
  const [filter, setFilter] = useState<InboxFilter>("needs_review");

  const fetchInbox = useCallback(async () => {
    setLoading(true);
    setError(null);
    setPartialFailures(0);
    try {
      const jobs = await getJobs();
      // Fan out: one getJobById call per job. Settled (not all-or-nothing)
      // so a single broken job doesn't kill the inbox.
      const results = await Promise.allSettled(
        jobs.map((job) => getJobById(job.id)),
      );

      let failures = 0;
      const flattened: InboxRow[] = [];
      results.forEach((result, idx) => {
        const job = jobs[idx];
        if (result.status !== "fulfilled") {
          failures += 1;
          return;
        }
        const detail: JobDetail = result.value;
        const sessions = Array.isArray(detail.sessions) ? detail.sessions : [];
        for (const session of sessions) {
          flattened.push({
            jobId: job.id,
            jobLabel: jobLabelFor(job),
            jobCode: job.job_code || job.id,
            session,
          });
        }
      });

      // Sort newest-first so the most recently submitted walk surfaces at
      // the top of the inbox.
      flattened.sort((a, b) => {
        const ta = new Date(a.session.started_at).getTime() || 0;
        const tb = new Date(b.session.started_at).getTime() || 0;
        return tb - ta;
      });

      setRows(flattened);
      setPartialFailures(failures);
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "An unexpected error occurred while loading field submissions.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchInbox();
  }, [fetchInbox]);

  // Only ended sessions are eligible for the inbox at all. Date filters
  // narrow further but never include in-progress sessions.
  const eligibleRows = useMemo(
    () => rows.filter((row) => isCompleted(row.session)),
    [rows],
  );

  const filteredRows = useMemo(() => {
    switch (filter) {
      case "today":
        return eligibleRows.filter((row) => isToday(row.session.started_at));
      case "week":
        return eligibleRows.filter((row) =>
          isWithinLastWeek(row.session.started_at),
        );
      case "needs_review":
      default:
        return eligibleRows;
    }
  }, [eligibleRows, filter]);

  // Filter chip counts so the user can see at a glance how much is in each
  // bucket without flipping through them.
  const counts = useMemo(() => {
    return {
      needs_review: eligibleRows.length,
      today: eligibleRows.filter((row) => isToday(row.session.started_at))
        .length,
      week: eligibleRows.filter((row) =>
        isWithinLastWeek(row.session.started_at),
      ).length,
    } as Record<InboxFilter, number>;
  }, [eligibleRows]);

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
          {(Object.keys(FILTER_LABELS) as InboxFilter[]).map((key) => {
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
                {FILTER_LABELS[key]}
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
              onClick={fetchInbox}
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
              onClick={fetchInbox}
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
                    {/* Optional "View Session" column. Reuses the existing
                        job detail route — no new action endpoint. */}
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
                          href={`/jobs/${row.jobId}`}
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
                          href={`/jobs/${row.jobId}`}
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
