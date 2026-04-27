// web/src/lib/office/fieldSubmissionsInbox.ts
//
// Phase 4D — shared inbox data hook.
// Phase 4F — review-aware filtering.
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
// Phase 4F: the "Needs Review" filter now consults client-side review state
// (localStorage, via @/lib/office/sessionReview) and excludes any session
// that has been marked "reviewed". The "Today" and "This Week" filters are
// time-based and unchanged — sessions that have been reviewed will still
// show up there, just with no filtering effect from the review status.
//
// This module contains NO UI. All rendering happens in the consumers.

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { getJobs, getJobById } from "@/lib/api";
import type { Job, JobDetail, Session } from "@/lib/api";
import { getSessionReviewStatus } from "@/lib/office/sessionReview";

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

// Phase 4F: storage event prefix we care about. We listen for `storage` and
// the same-tab custom event so the inbox re-filters when a session is
// marked reviewed from elsewhere on the page.
const REVIEW_STORAGE_PREFIX = "osp_session_review:";
const REVIEW_SAME_TAB_EVENT = "osp:session-review-changed";

export function useFieldSubmissions(
  initialFilter: InboxFilter = "needs_review",
): FieldSubmissionsState {
  const [rows, setRows] = useState<InboxRow[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [partialFailures, setPartialFailures] = useState<number>(0);
  const [filter, setFilter] = useState<InboxFilter>(initialFilter);

  // Phase 4F: a tick counter that bumps whenever any session-review
  // localStorage entry changes. We don't need to know which session changed
  // — we just need the memos below to recompute their filter results.
  // Storing the version in state (rather than a ref) is what triggers the
  // re-render.
  const [reviewVersion, setReviewVersion] = useState<number>(0);

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

  // Phase 4F: subscribe to review-status changes so the inbox re-filters
  // when a session is marked reviewed (in this tab or another tab).
  useEffect(() => {
    if (typeof window === "undefined") return;

    const onStorage = (event: StorageEvent) => {
      if (!event.key) return;
      if (!event.key.startsWith(REVIEW_STORAGE_PREFIX)) return;
      setReviewVersion((v) => v + 1);
    };
    const onSameTab = () => {
      setReviewVersion((v) => v + 1);
    };

    window.addEventListener("storage", onStorage);
    window.addEventListener(REVIEW_SAME_TAB_EVENT, onSameTab as EventListener);
    return () => {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener(
        REVIEW_SAME_TAB_EVENT,
        onSameTab as EventListener,
      );
    };
  }, []);

  // Phase 4F: a row is "ready for review" if the underlying walk has ended
  // AND the reviewer has NOT yet marked it reviewed client-side. Time-based
  // filters intentionally do not check review state — they answer "what
  // walks happened today/this week", which is a different question.
  //
  // The reviewVersion dependency forces recomputation when a review status
  // flips elsewhere on the page (or in another tab).
  const eligibleRows = useMemo(
    () => rows.filter((row) => isCompleted(row.session)),
    [rows],
  );

  const needsReviewRows = useMemo(
    () =>
      eligibleRows.filter(
        (row) => getSessionReviewStatus(row.session.id) !== "reviewed",
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [eligibleRows, reviewVersion],
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
        return needsReviewRows;
    }
  }, [eligibleRows, needsReviewRows, filter]);

  const counts = useMemo<Record<InboxFilter, number>>(() => {
    return {
      // Phase 4F: the "Needs Review" chip count reflects the same exclusion
      // as the filter — once a reviewer marks a row reviewed it disappears
      // from the count too, so reviewers see the queue actually drain.
      needs_review: needsReviewRows.length,
      today: eligibleRows.filter((row) => isToday(row.session.started_at))
        .length,
      week: eligibleRows.filter((row) =>
        isWithinLastWeek(row.session.started_at),
      ).length,
    };
  }, [eligibleRows, needsReviewRows]);

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
