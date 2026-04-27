// web/src/lib/office/fieldSubmissionsInbox.ts
//
// Phase 4D — shared inbox data hook.
//
// Powers both:
//   - /jobs/inbox (full page)
//   - the compact "Field Submissions Inbox" panel on the main Operator
//     Workspace at /
//
// There is no global /sessions endpoint on the backend yet. To build a
// cross-job inbox we call getJobs() once and getJobById() per job in
// parallel. Per-job failures are tracked separately so a single broken job
// does not blank the whole inbox.
//
// This module contains NO UI. All rendering happens in the consumers.

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { getJobs, getJobById } from "@/lib/api";
import type { Job, JobDetail, Session } from "@/lib/api";

// ─── Public types ─────────────────────────────────────────────────────────────

export type InboxFilter = "needs_review" | "today" | "week";

export type InboxRow = {
  jobId: string;
  jobLabel: string;
  jobCode: string;
  session: Session;
};

export type FieldSubmissionsState = {
  rows: InboxRow[];
  filteredRows: InboxRow[];
  counts: Record<InboxFilter, number>;
  loading: boolean;
  error: string | null;
  partialFailures: number;
  filter: InboxFilter;
  setFilter: (filter: InboxFilter) => void;
  refresh: () => void;
};

// ─── Helpers (pure) ───────────────────────────────────────────────────────────

export function shortenSessionId(rawId: string): string {
  if (!rawId) return "—";
  return rawId.length <= 8 ? rawId : rawId.slice(0, 8);
}

export function formatSessionDate(ts: string | null | undefined): string {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function formatSessionDateTime(ts: string | null | undefined): string {
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

export function safeCount(n: unknown): number {
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

// "This Week" = session started_at within the last 7 days (rolling, inclusive
// of today). ms-threshold so behavior is unambiguous and locale-independent.
const WEEK_MS = 7 * 24 * 60 * 60 * 1000;

function isWithinLastWeek(ts: string): boolean {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return false;
  const now = Date.now();
  const t = d.getTime();
  return t >= now - WEEK_MS && t <= now;
}

// Phase 4D: only ended sessions are "ready for review".
export function isCompleted(session: Session): boolean {
  return String(session.status || "").toLowerCase() === "ended";
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useFieldSubmissions(
  initialFilter: InboxFilter = "needs_review",
): FieldSubmissionsState {
  const [rows, setRows] = useState<InboxRow[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [partialFailures, setPartialFailures] = useState<number>(0);
  const [filter, setFilter] = useState<InboxFilter>(initialFilter);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    setPartialFailures(0);
    try {
      const jobs = await getJobs();
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
    void refresh();
  }, [refresh]);

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

  const counts = useMemo<Record<InboxFilter, number>>(() => {
    return {
      needs_review: eligibleRows.length,
      today: eligibleRows.filter((row) => isToday(row.session.started_at))
        .length,
      week: eligibleRows.filter((row) =>
        isWithinLastWeek(row.session.started_at),
      ).length,
    };
  }, [eligibleRows]);

  return {
    rows,
    filteredRows,
    counts,
    loading,
    error,
    partialFailures,
    filter,
    setFilter,
    refresh,
  };
}

// Filter label table — exposed so consumers render consistent chip labels.
export const FIELD_SUBMISSIONS_FILTER_LABELS: Record<InboxFilter, string> = {
  needs_review: "Needs Review",
  today: "Today",
  week: "This Week",
};
