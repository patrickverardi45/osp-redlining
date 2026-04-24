// web/src/app/jobs/page.tsx
"use client";

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
  const base =
    "px-3 py-1.5 text-xs font-semibold rounded border transition-colors";
  const active = "bg-gray-800 text-white border-gray-800";
  const inactive =
    "bg-white text-gray-600 border-gray-200 hover:border-gray-400";

  return (
    <div className="flex items-center gap-1">
      <button
        onClick={() => onChange("pipeline")}
        className={`${base} ${mode === "pipeline" ? active : inactive}`}
      >
        Pipeline View
      </button>
      <button
        onClick={() => onChange("all")}
        className={`${base} ${mode === "all" ? active : inactive}`}
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
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-6xl mx-auto px-6 py-10 space-y-8">

        {/* Page header */}
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Jobs</h1>
            <p className="text-sm text-gray-500 mt-1">
              OSP Redlining + Walk Verification — Office Dashboard
            </p>
          </div>
          {!loading && !error && (
            <ViewToggle mode={viewMode} onChange={setViewMode} />
          )}
        </div>

        {/* Loading */}
        {loading && (
          <div className="text-sm text-gray-400 py-10 text-center">
            Loading jobs…
          </div>
        )}

        {/* Error */}
        {!loading && error && (
          <div>
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              <span className="font-semibold">Error loading jobs:</span> {error}
            </div>
            <button
              onClick={fetchJobs}
              className="mt-3 px-3 py-1.5 rounded text-sm font-medium bg-gray-800 text-white hover:bg-gray-700 transition-colors"
            >
              Retry
            </button>
          </div>
        )}

        {/* Dashboard content */}
        {!loading && !error && (
          <>
            {/* Summary cards */}
            <JobsSummaryCards jobs={jobs} />

            {/* Attention panel — only shown when there are attention jobs */}
            <AttentionJobsPanel jobs={jobs} />

            {/* View divider */}
            <hr className="border-gray-200" />

            {/* Pipeline or flat view */}
            {viewMode === "pipeline" ? (
              <JobsPipelineView jobs={jobs} onRefresh={fetchJobs} />
            ) : (
              <>
                <JobsTable jobs={jobs} onRefresh={fetchJobs} />
                {jobs.length > 0 && (
                  <p className="text-xs text-gray-400 text-right">
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
