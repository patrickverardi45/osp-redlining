// web/src/components/office/WorkflowActionsPanel.tsx
// Sits near the top of /jobs/[jobId] to give office users clear workflow controls.
"use client";

import {
  isKnownStatus,
  STATUS_LABELS,
  STATUS_ORDER,
  getNextStatus,
  getPrevStatus,
} from "@/lib/api";
import type { JobStatus } from "@/lib/api";
import JobStatusActionButtons from "@/components/office/JobStatusActionButtons";

interface WorkflowActionsPanelProps {
  jobId: string;
  currentStatus: string;
  onMutated: () => void;
}

const STATUS_BADGE: Record<JobStatus, string> = {
  draft: "bg-gray-100 text-gray-700",
  ready_for_field: "bg-indigo-100 text-indigo-700",
  in_progress: "bg-blue-100 text-blue-700",
  field_complete: "bg-cyan-100 text-cyan-700",
  qa_review: "bg-yellow-100 text-yellow-700",
  redlines_ready: "bg-purple-100 text-purple-700",
  closeout_ready: "bg-orange-100 text-orange-700",
  billed: "bg-green-100 text-green-700",
};

function StatusPill({ status }: { status: string }) {
  const label = isKnownStatus(status)
    ? STATUS_LABELS[status]
    : status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  const colorClass = isKnownStatus(status)
    ? STATUS_BADGE[status]
    : "bg-gray-100 text-gray-600";
  return (
    <span
      className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-semibold ${colorClass}`}
    >
      {label}
    </span>
  );
}

// Simple step-progress track showing current position in pipeline
function PipelineTrack({ currentStatus }: { currentStatus: string }) {
  const idx = isKnownStatus(currentStatus)
    ? STATUS_ORDER.indexOf(currentStatus as JobStatus)
    : -1;

  return (
    <div className="flex items-center gap-0 flex-wrap">
      {STATUS_ORDER.map((s, i) => {
        const isActive = i === idx;
        const isPast = i < idx;
        const isLast = i === STATUS_ORDER.length - 1;

        return (
          <div key={s} className="flex items-center">
            <div
              className={`px-2.5 py-0.5 text-xs font-medium rounded-full whitespace-nowrap
                ${isActive ? "bg-blue-600 text-white" : ""}
                ${isPast ? "bg-gray-200 text-gray-500" : ""}
                ${!isActive && !isPast ? "bg-gray-100 text-gray-400" : ""}
              `}
            >
              {STATUS_LABELS[s]}
            </div>
            {!isLast && (
              <span
                className={`mx-1 text-xs ${
                  i < idx ? "text-gray-400" : "text-gray-200"
                }`}
              >
                →
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function WorkflowActionsPanel({
  jobId,
  currentStatus,
  onMutated,
}: WorkflowActionsPanelProps) {
  const known = isKnownStatus(currentStatus);
  const next = known ? getNextStatus(currentStatus as JobStatus) : null;
  const prev = known ? getPrevStatus(currentStatus as JobStatus) : null;
  const hasActions = known && (next !== null || prev !== null);

  return (
    <section className="rounded-lg border border-gray-200 bg-white shadow-sm overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 bg-gray-50 border-b border-gray-200">
        <h2 className="text-base font-semibold text-gray-800">
          Workflow Status
        </h2>
        <StatusPill status={currentStatus} />
      </div>

      {/* Pipeline track */}
      <div className="px-5 py-3 border-b border-gray-100">
        <PipelineTrack currentStatus={currentStatus} />
      </div>

      {/* Action buttons */}
      <div className="px-5 py-4">
        {hasActions ? (
          <div>
            <p className="text-xs text-gray-500 mb-3">
              Advance this job to the next workflow stage, or move it back if needed.
            </p>
            <JobStatusActionButtons
              jobId={jobId}
              currentStatus={currentStatus}
              onMutated={onMutated}
              compact={false}
            />
          </div>
        ) : !known ? (
          <p className="text-sm text-gray-400 italic">
            This job has an unrecognised status — no workflow actions are available.
          </p>
        ) : (
          <p className="text-sm text-gray-500">
            This job is at the final workflow stage.
          </p>
        )}
      </div>
    </section>
  );
}
