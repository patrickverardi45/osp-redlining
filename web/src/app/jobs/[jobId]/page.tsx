// web/src/app/jobs/[jobId]/page.tsx
// Client component — re-fetches after mutations (status change, exception resolve, report generation).
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
        <h2 className="tl-h2" style={{ marginBottom: 12 }}>
          Map Review
        </h2>
        <div
          className="tl-card"
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--tl-text-faint)",
            fontSize: 13,
            height: 540,
          }}
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

  const selectedSession = useMemo<Session | null>(() => {
    if (!selectedSessionId || !job) return null;
    return (
      (job.sessions ?? []).find((s) => s.id === selectedSessionId) ?? null
    );
  }, [selectedSessionId, job]);

  // ── Loading ────────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="tl-page">
        <div className="tl-page-inner">
          <nav style={{ fontSize: 13, color: "var(--tl-text-muted)", marginBottom: 22 }}>
            <Link href="/jobs" className="tl-link">
              Jobs
            </Link>
            <span style={{ margin: "0 8px", color: "var(--tl-text-faint)" }}>/</span>
            <span style={{ color: "var(--tl-text-faint)" }}>Loading…</span>
          </nav>
          <div className="tl-card tl-card-padded" style={{ textAlign: "center" }}>
            <span className="tl-subtle">Loading job data…</span>
          </div>
        </div>
      </div>
    );
  }

  // ── Error ──────────────────────────────────────────────────────────────────
  if (error) {
    return (
      <div className="tl-page">
        <div className="tl-page-inner">
          <nav style={{ fontSize: 13, color: "var(--tl-text-muted)", marginBottom: 22 }}>
            <Link href="/jobs" className="tl-link">
              Jobs
            </Link>
            <span style={{ margin: "0 8px", color: "var(--tl-text-faint)" }}>/</span>
            <span style={{ color: "var(--tl-text)" }}>Error</span>
          </nav>
          <div
            className="tl-card tl-card-padded"
            style={{
              borderColor: "var(--tl-red-border)",
              background: "var(--tl-surface)",
              color: "#fee2e2",
            }}
          >
            <span style={{ fontWeight: 700 }}>Error loading job:</span> {error}
          </div>
          <button
            onClick={fetchJob}
            className="tl-btn tl-btn-primary"
            style={{ marginTop: 16 }}
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
    <div className="tl-page">
      <div className="tl-page-inner" style={{ display: "grid", gap: 32 }}>
        {/* Job Header */}
        <JobHeader job={job} />

        {/* Workflow Actions */}
        <WorkflowActionsPanel
          jobId={job.id}
          currentStatus={job.status}
          onMutated={fetchJob}
        />

        <hr className="tl-divider" />

        <DesignSetupPanel onMutated={fetchJob} />

        <hr className="tl-divider" />

        <RouteListPanel routes={job.routes ?? []} />

        <SessionListPanel
          sessions={job.sessions ?? []}
          photos={job.photos ?? []}
          highlightedSessionId={selectedSessionId}
        />

        <ExceptionSummaryPanel
          exceptions={job.exceptions ?? []}
          onMutated={fetchJob}
        />

        <hr className="tl-divider" />

        {selectedSessionId && (
          <SelectedSubmissionReviewPanel
            selectedSessionId={selectedSessionId}
            session={selectedSession}
          />
        )}

        <OfficeMapReviewPanel
          job={job}
          selectedSessionId={selectedSessionId}
        />

        <hr className="tl-divider" />

        <ReportActionsPanel jobId={job.id} onGenerated={fetchJob} />
        <ArtifactsPanel artifacts={job.artifacts ?? []} />

        {/* ── Closeout Review ──────────────────────────────────────────────── */}
        <hr className="tl-divider" />

        <div>
          <div className="tl-eyebrow">Closeout</div>
          <h2 className="tl-h1" style={{ fontSize: 22, margin: "8px 0 4px" }}>
            Closeout Review
          </h2>
          <p className="tl-subtle" style={{ margin: 0 }}>
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
