// web/src/components/office/ReportActionsPanel.tsx
"use client";

import { useState } from "react";
import {
  generateQaSummary,
  generateRedlineReport,
  generateCloseoutReport,
} from "@/lib/api";

// ─── Types ────────────────────────────────────────────────────────────────────

interface ReportActionsPanelProps {
  jobId: string;
  onGenerated: () => void; // called after any successful generation so parent can refresh
}

type ReportKey = "qa" | "redline" | "closeout";

interface ReportConfig {
  key: ReportKey;
  label: string;
  description: string;
  fn: (jobId: string) => Promise<unknown>;
}

const REPORTS: ReportConfig[] = [
  {
    key: "qa",
    label: "Generate QA Summary",
    description: "Station-level quality assurance summary with depth and BOC data.",
    fn: generateQaSummary,
  },
  {
    key: "redline",
    label: "Generate Redline Package",
    description: "Design vs. walk comparison with deviation highlights.",
    fn: generateRedlineReport,
  },
  {
    key: "closeout",
    label: "Generate Closeout Package",
    description: "Final as-built documentation package for this job.",
    fn: generateCloseoutReport,
  },
];

// ─── Component ────────────────────────────────────────────────────────────────

export default function ReportActionsPanel({
  jobId,
  onGenerated,
}: ReportActionsPanelProps) {
  const [loadingKeys, setLoadingKeys] = useState<Set<ReportKey>>(new Set());
  const [errors, setErrors] = useState<Partial<Record<ReportKey, string>>>({});
  const [queued, setQueued] = useState<Partial<Record<ReportKey, boolean>>>({});

  const handleGenerate = async (report: ReportConfig) => {
    setLoadingKeys((prev) => new Set(prev).add(report.key));
    setErrors((prev) => {
      const next = { ...prev };
      delete next[report.key];
      return next;
    });
    setQueued((prev) => {
      const next = { ...prev };
      delete next[report.key];
      return next;
    });

    try {
      await report.fn(jobId);
      setQueued((prev) => ({ ...prev, [report.key]: true }));
      onGenerated();
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : "Report generation failed.";
      setErrors((prev) => ({ ...prev, [report.key]: msg }));
    } finally {
      setLoadingKeys((prev) => {
        const next = new Set(prev);
        next.delete(report.key);
        return next;
      });
    }
  };

  return (
    <section>
      <div className="mb-3">
        <h2 className="text-base font-semibold text-gray-800">Report Actions</h2>
        <p className="text-xs text-gray-400 mt-0.5">
          Generate artifacts from current job data. Results appear in the
          Generated Artifacts panel below.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {REPORTS.map((report) => {
          const isLoading = loadingKeys.has(report.key);
          const error = errors[report.key];
          const wasQueued = queued[report.key];

          return (
            <div
              key={report.key}
              className="rounded-lg border border-gray-200 bg-white shadow-sm p-4 flex flex-col gap-3"
            >
              <div>
                <div className="text-sm font-semibold text-gray-800">
                  {report.label}
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  {report.description}
                </div>
              </div>

              {error && (
                <div className="text-xs text-red-600 font-medium">
                  ⚠ {error}
                </div>
              )}

              {wasQueued && !isLoading && !error && (
                <div className="text-xs text-green-600 font-medium">
                  ✓ Queued — check artifacts below.
                </div>
              )}

              <button
                onClick={() => handleGenerate(report)}
                disabled={isLoading}
                className="mt-auto px-3 py-1.5 rounded text-xs font-semibold bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {isLoading ? "Queuing…" : report.label}
              </button>
            </div>
          );
        })}
      </div>
    </section>
  );
}
