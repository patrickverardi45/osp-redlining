// web/src/components/office/JobStatusActionButtons.tsx
// Shared component — used in both /jobs pipeline rows AND /jobs/[jobId] detail page.
// Renders forward/back status action buttons for a single job.
"use client";

import { useState } from "react";
import {
  updateJobStatus,
  getNextStatus,
  getPrevStatus,
  isKnownStatus,
  ADVANCE_ACTION_LABELS,
  STATUS_LABELS,
  CONFIRM_REQUIRED_TRANSITIONS,
} from "@/lib/api";
import type { JobStatus } from "@/lib/api";

interface JobStatusActionButtonsProps {
  jobId: string;
  currentStatus: string;
  onMutated: () => void;   // called after successful status change
  compact?: boolean;       // true = tighter layout for list rows
}

export default function JobStatusActionButtons({
  jobId,
  currentStatus,
  onMutated,
  compact = false,
}: JobStatusActionButtonsProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Unknown status — show warning, no actions
  if (!isKnownStatus(currentStatus)) {
    return (
      <span className="text-xs text-gray-400 italic">
        Unknown status — no actions available
      </span>
    );
  }

  const status = currentStatus as JobStatus;
  const nextStatus = getNextStatus(status);
  const prevStatus = getPrevStatus(status);

  // No transitions possible from either end
  if (!nextStatus && !prevStatus) {
    return null;
  }

  const handleTransition = async (targetStatus: JobStatus, direction: "forward" | "back") => {
    // Confirm for sensitive forward transitions
    if (
      direction === "forward" &&
      CONFIRM_REQUIRED_TRANSITIONS.has(status)
    ) {
      const nextLabel = STATUS_LABELS[targetStatus];
      const ok = window.confirm(
        `Move this job to "${nextLabel}"?\n\nThis action will change the job status and cannot be undone without a further status change.`
      );
      if (!ok) return;
    }

    setLoading(true);
    setError(null);
    try {
      await updateJobStatus(jobId, targetStatus);
      onMutated();
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Failed to update job status."
      );
    } finally {
      setLoading(false);
    }
  };

  const advanceLabel = nextStatus ? (ADVANCE_ACTION_LABELS[status] ?? `Move to ${STATUS_LABELS[nextStatus]}`) : null;
  const backLabel = prevStatus ? `Move Back to ${STATUS_LABELS[prevStatus]}` : null;

  if (compact) {
    // ── Compact layout for pipeline/table rows ────────────────────────────
    return (
      <div className="flex flex-col gap-1 min-w-[160px]">
        {advanceLabel && nextStatus && (
          <button
            onClick={() => handleTransition(nextStatus, "forward")}
            disabled={loading}
            className="px-2.5 py-1 rounded text-xs font-semibold bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
          >
            {loading ? "Saving…" : advanceLabel}
          </button>
        )}
        {backLabel && prevStatus && (
          <button
            onClick={() => handleTransition(prevStatus, "back")}
            disabled={loading}
            className="px-2.5 py-1 rounded text-xs font-medium bg-gray-100 text-gray-600 hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
          >
            {loading ? "Saving…" : backLabel}
          </button>
        )}
        {error && (
          <span className="text-xs text-red-600 font-medium mt-0.5">
            ⚠ {error}
          </span>
        )}
      </div>
    );
  }

  // ── Full layout for detail page WorkflowActionsPanel ─────────────────────
  return (
    <div className="flex flex-wrap items-center gap-3">
      {advanceLabel && nextStatus && (
        <button
          onClick={() => handleTransition(nextStatus, "forward")}
          disabled={loading}
          className="px-4 py-2 rounded text-sm font-semibold bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? "Saving…" : advanceLabel}
        </button>
      )}
      {backLabel && prevStatus && (
        <button
          onClick={() => handleTransition(prevStatus, "back")}
          disabled={loading}
          className="px-4 py-2 rounded text-sm font-medium bg-gray-200 text-gray-700 hover:bg-gray-300 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? "Saving…" : backLabel}
        </button>
      )}
      {error && (
        <span className="text-sm text-red-600 font-medium">⚠ {error}</span>
      )}
    </div>
  );
}
