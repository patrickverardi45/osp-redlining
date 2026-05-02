// web/src/app/jobs/page.tsx
"use client";

import Link from "next/link";
import { useState, useEffect, useCallback } from "react";
import { getJobs } from "@/lib/api";
import type { Job } from "@/lib/api";

import JobsSummaryCards from "@/components/office/JobsSummaryCards";
import AttentionJobsPanel from "@/components/office/AttentionJobsPanel";
import JobsPipelineView from "@/components/office/JobsPipelineView";
import JobsTable from "@/components/office/JobsTable";

// ─── View mode toggle ─────────────────────────────────────────────────────────

type ViewMode = "pipeline" | "all";

function ViewToggle({
  mode,
  onChange,
}: {
  mode: ViewMode;
  onChange: (m: ViewMode) => void;
}) {
  return (
    <div style={{ display: "inline-flex", gap: 6 }}>
      <button
        onClick={() => onChange("pipeline")}
        className={
          mode === "pipeline"
            ? "tl-btn tl-btn-toggle-active"
            : "tl-btn tl-btn-ghost"
        }
        style={{ fontSize: 12, padding: "6px 12px" }}
      >
        Pipeline View
      </button>
      <button
        onClick={() => onChange("all")}
        className={
          mode === "all" ? "tl-btn tl-btn-toggle-active" : "tl-btn tl-btn-ghost"
        }
        style={{ fontSize: 12, padding: "6px 12px" }}
      >
        All Jobs
      </button>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("pipeline");

  const fetchJobs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getJobs();
      setJobs(data);
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "An unexpected error occurred while loading jobs."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  return (
    <div className="tl-page">
      <div className="tl-page-inner-wide" style={{ display: "grid", gap: 28 }}>
        {/* Page header */}
        <div className="tl-section-head">
          <div>
            <div className="tl-eyebrow">Office</div>
            <h1 className="tl-h1" style={{ margin: "8px 0 6px" }}>
              Jobs
            </h1>
            <p className="tl-subtle" style={{ margin: 0 }}>
              OSP Redlining + Walk Verification — Office Dashboard
            </p>
          </div>
          {!loading && !error && (
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <Link
                href="/jobs/inbox"
                className="tl-btn tl-btn-ghost"
                style={{ fontSize: 12, padding: "6px 12px" }}
              >
                Field Submissions Inbox
              </Link>
              <ViewToggle mode={viewMode} onChange={setViewMode} />
            </div>
          )}
        </div>

        {/* Loading */}
        {loading && (
          <div className="tl-card tl-card-padded" style={{ textAlign: "center" }}>
            <span className="tl-subtle">Loading jobs…</span>
          </div>
        )}

        {/* Error */}
        {!loading && error && (
          <div>
            <div
              className="tl-card tl-card-padded"
              style={{
                borderColor: "var(--tl-red-border)",
                background: "var(--tl-surface)",
                color: "#fee2e2",
              }}
            >
              <span style={{ fontWeight: 700 }}>Error loading jobs:</span> {error}
            </div>
            <button
              onClick={fetchJobs}
              className="tl-btn tl-btn-primary"
              style={{ marginTop: 12 }}
            >
              Retry
            </button>
          </div>
        )}

        {/* Dashboard content */}
        {!loading && !error && (
          <>
            <JobsSummaryCards jobs={jobs} />
            <AttentionJobsPanel jobs={jobs} />

            <hr className="tl-divider" />

            {viewMode === "pipeline" ? (
              <JobsPipelineView jobs={jobs} onRefresh={fetchJobs} />
            ) : (
              <>
                <JobsTable jobs={jobs} onRefresh={fetchJobs} />
                {jobs.length > 0 && (
                  <p
                    className="tl-subtle"
                    style={{ textAlign: "right", fontSize: 12, margin: 0 }}
                  >
                    {jobs.length} job{jobs.length !== 1 ? "s" : ""} total
                  </p>
                )}
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
