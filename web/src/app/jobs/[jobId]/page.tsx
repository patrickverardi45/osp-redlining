// web/src/app/jobs/[jobId]/page.tsx
// Client component — re-fetches after mutations (status change, exception resolve, report generation).
//
// Phase 4E additions:
//   - Reads optional `?session=<id>` query parameter so the Field
//     Submissions Inbox can hand off a specific submission for review.
//   - Renders a Selected Submission Review panel above Map Review when
//     a session is selected.
//   - Highlights the selected row in the Walk Sessions table.
//   - Passes the selected id through to the Map Review panel so the
//     matching walk track can be emphasized.
//
// Hard rules respected:
//   - read-only, no redlines generated, no approve / reject actions
//   - no backend changes
//   - no fake data — the selected session must come from job.sessions[]
"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import dynamic from "next/dynamic";

import { getJobById } from "@/lib/api";
import type { JobDetail, Session } from "@/lib/api";

// ─── Existing panels ──────────────────────────────────────────────────────────
import JobHeader from "@/components/office/JobHeader";
import DesignSetupPanel from "@/components/office/DesignSetupPanel";
import RouteListPanel from "@/components/office/RouteListPanel";
import SessionListPanel from "@/components/office/SessionListPanel";
import SelectedSubmissionReviewPanel from "@/components/office/SelectedSubmissionReviewPanel";
import ExceptionSummaryPanel from "@/components/office/ExceptionSummaryPanel";
import ReportActionsPanel from "@/components/office/ReportActionsPanel";
import ArtifactsPanel from "@/components/office/ArtifactsPanel";

// ─── Closeout review panels ───────────────────────────────────────────────────
import CloseoutReadinessPanel from "@/components/office/CloseoutReadinessPanel";
import CloseoutContentSummaryPanel from "@/components/office/CloseoutContentSummaryPanel";
import SessionCoveragePanel from "@/components/office/SessionCoveragePanel";
import OpenIssuesPanel from "@/components/office/OpenIssuesPanel";

// ─── Workflow actions ─────────────────────────────────────────────────────────
import WorkflowActionsPanel from "@/components/office/WorkflowActionsPanel";

// ─── Map — Leaflet, client-only ───────────────────────────────────────────────
const OfficeMapReviewPanel = dynamic(
  () => import("@/components/office/OfficeMapReviewPanel"),
  {
    ssr: false,
    loading: () => (
      <section>
        <h2 className="text-base font-semibold text-gray-800 mb-3">
          Map Review
        </h2>
        <div
          className="rounded-lg border border-gray-200 bg-gray-50 flex items-center justify-center text-sm text-gray-400"
          style={{ height: "540px" }}
        >
          Loading map…
        </div>
      </section>
    ),
  }
);

// ─── Component ────────────────────────────────────────────────────────────────

export default function JobDetailPage() {
  const params = useParams();
  const jobId = params.jobId as string;

  // Phase 4E: pick up the optional `session` query parameter. Empty / missing
  // means "no specific session selected" — the page renders exactly as it
  // did before. We trim and coalesce to null so downstream components have a
  // single clean shape to work with.
  const searchParams = useSearchParams();
  const rawSelectedSessionId = searchParams?.get("session") ?? "";
  const selectedSessionId = rawSelectedSessionId.trim() || null;

  const [job, setJob] = useState<JobDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchJob = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getJobById(jobId);
      setJob(data);
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "An unexpected error occurred while loading the job."
      );
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    fetchJob();
  }, [fetchJob]);

  // Phase 4E: resolve the selected id against the loaded sessions. Done here
  // (rather than inside the review panel) so we can pass either the real
  // Session record or `null` (meaning "selected, but not on this job — stale
  // link") to the panel without re-walking the array there.
  const selectedSession = useMemo<Session | null>(() => {
    if (!selectedSessionId || !job) return null;
    return (
      (job.sessions ?? []).find((s) => s.id === selectedSessionId) ?? null
    );
  }, [selectedSessionId, job]);

  // ── Loading ────────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50">
        <div className="max-w-5xl mx-auto px-6 py-10">
          <nav className="text-sm text-gray-500 mb-6">
            <Link href="/jobs" className="hover:text-blue-600 hover:underline">
              Jobs
            </Link>
            <span className="mx-2 text-gray-300">/</span>
            <span className="text-gray-400">Loading…</span>
          </nav>
          <div className="text-sm text-gray-400">Loading job data…</div>
        </div>
      </div>
    );
  }

  // ── Error ──────────────────────────────────────────────────────────────────
  if (error) {
    return (
      <div className="min-h-screen bg-gray-50">
        <div className="max-w-5xl mx-auto px-6 py-10">
          <nav className="text-sm text-gray-500 mb-6">
            <Link href="/jobs" className="hover:text-blue-600 hover:underline">
              Jobs
            </Link>
            <span className="mx-2 text-gray-300">/</span>
            <span className="text-gray-800">Error</span>
          </nav>
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <span className="font-semibold">Error loading job:</span> {error}
          </div>
          <button
            onClick={fetchJob}
            className="mt-4 px-3 py-1.5 rounded text-sm font-medium bg-gray-800 text-white hover:bg-gray-700 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!job) return null;

  // ── Detail view ────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-5xl mx-auto px-6 py-10 space-y-10">

        {/* Job Header */}
        <JobHeader job={job} />

        {/* ── Workflow Actions — near top so office staff sees status first ── */}
        <WorkflowActionsPanel
          jobId={job.id}
          currentStatus={job.status}
          onMutated={fetchJob}
        />

        <hr className="border-gray-200" />

        {/* Design / KMZ setup */}
        <DesignSetupPanel onMutated={fetchJob} />

        <hr className="border-gray-200" />

        {/* Routes */}
        <RouteListPanel routes={job.routes ?? []} />

        {/* Walk Sessions — Phase 4E: highlight the inbox-selected session */}
        <SessionListPanel
          sessions={job.sessions ?? []}
          highlightedSessionId={selectedSessionId}
        />

        {/* Exceptions — interactive, refreshes job on mutation */}
        <ExceptionSummaryPanel
          exceptions={job.exceptions ?? []}
          onMutated={fetchJob}
        />

        <hr className="border-gray-200" />

        {/* Phase 4E: Selected Submission Review — only when a `session`
            query param is present. Sits directly above the map so the
            reviewer's eye flows from "what was submitted" to "what does
            it look like on the map". */}
        {selectedSessionId && (
          <SelectedSubmissionReviewPanel
            selectedSessionId={selectedSessionId}
            session={selectedSession}
          />
        )}

        {/* Map — Leaflet, client-only. Phase 4E: passes the selected
            session id so the matching walk track is emphasized. */}
        <OfficeMapReviewPanel
          job={job}
          selectedSessionId={selectedSessionId}
        />

        <hr className="border-gray-200" />

        {/* Report generation + artifact list */}
        <ReportActionsPanel jobId={job.id} onGenerated={fetchJob} />
        <ArtifactsPanel artifacts={job.artifacts ?? []} />

        {/* ── Closeout Review ──────────────────────────────────────────────── */}
        <hr className="border-gray-200" />

        <div>
          <h2 className="text-lg font-bold text-gray-900 mb-1">
            Closeout Review
          </h2>
          <p className="text-sm text-gray-500">
            Pre-export readiness check and package summary for this job.
          </p>
        </div>

        <CloseoutReadinessPanel job={job} />
        <CloseoutContentSummaryPanel job={job} />
        <SessionCoveragePanel sessions={job.sessions ?? []} />
        <OpenIssuesPanel exceptions={job.exceptions ?? []} />

      </div>
    </div>
  );
}
