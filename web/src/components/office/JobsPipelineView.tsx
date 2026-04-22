// web/src/components/office/JobsPipelineView.tsx
"use client";

import Link from "next/link";
import type { Job } from "@/lib/api";
import { STATUS_BADGE_CLASSES } from "@/lib/statusConfig";
import JobStatusActionButtons from "@/components/office/JobStatusActionButtons";

interface JobsPipelineViewProps {
  jobs: Job[];
  onRefresh: () => void;
}

// ─── Pipeline stages ──────────────────────────────────────────────────────────

interface PipelineStage {
  key: string;
  label: string;
  description: string;
}

const PIPELINE_STAGES: PipelineStage[] = [
  { key: "draft", label: "Draft", description: "Job created, not yet assigned to field" },
  { key: "ready_for_field", label: "Ready for Field", description: "Approved and ready for walk crews" },
  { key: "in_progress", label: "In Progress", description: "Active walk sessions underway" },
  { key: "field_complete", label: "Field Complete", description: "All walks done, pending QA" },
  { key: "qa_review", label: "QA Review", description: "Data under office review" },
  { key: "redlines_ready", label: "Redlines Ready", description: "Redline package generated" },
  { key: "closeout_ready", label: "Closeout Ready", description: "Final package ready to send" },
  { key: "billed", label: "Billed", description: "Closeout delivered and billed" },
];

// ─── Status badge ─────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const colorClass =
    STATUS_BADGE_CLASSES[status] ?? "bg-gray-100 text-gray-600";
  const label = status
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${colorClass}`}
    >
      {label}
    </span>
  );
}

// ─── Date helper ──────────────────────────────────────────────────────────────

function formatDate(ts: string | null): string {
  if (!ts) return "—";
  return new Date(ts).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

// ─── Job row ──────────────────────────────────────────────────────────────────

function JobRow({
  job,
  onRefresh,
}: {
  job: Job;
  onRefresh: () => void;
}) {
  return (
    <tr className="hover:bg-gray-50 transition-colors align-top">
      <td className="px-4 py-3">
        <Link
          href={`/jobs/${job.id}`}
          className="font-medium text-blue-600 hover:text-blue-800 hover:underline text-sm"
        >
          {job.job_name}
        </Link>
      </td>
      <td className="px-4 py-3 text-gray-500 font-mono text-xs whitespace-nowrap">
        {job.job_code}
      </td>
      <td className="px-4 py-3 text-center text-gray-700 text-sm tabular-nums">
        {job.route_count}
      </td>
      <td className="px-4 py-3 text-center text-gray-700 text-sm tabular-nums">
        {job.session_count}
      </td>
      <td className="px-4 py-3 text-center text-sm tabular-nums">
        <span
          className={
            job.exception_count > 0
              ? "font-semibold text-red-600"
              : "text-gray-400"
          }
        >
          {job.exception_count}
        </span>
      </td>
      <td className="px-4 py-3 text-xs text-gray-400 whitespace-nowrap">
        {formatDate(job.last_sync_at)}
      </td>
      <td className="px-4 py-3">
        <JobStatusActionButtons
          jobId={job.id}
          currentStatus={job.status}
          onMutated={onRefresh}
          compact={true}
        />
      </td>
    </tr>
  );
}

// ─── Stage group ──────────────────────────────────────────────────────────────

function StageGroup({
  stage,
  jobs,
  onRefresh,
}: {
  stage: PipelineStage;
  jobs: Job[];
  onRefresh: () => void;
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white shadow-sm overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-b border-gray-200">
        <div className="flex items-center gap-2">
          <StatusBadge status={stage.key} />
          <span className="text-xs text-gray-400">{stage.description}</span>
        </div>
        <span className="text-xs font-semibold text-gray-500 tabular-nums">
          {jobs.length} job{jobs.length !== 1 ? "s" : ""}
        </span>
      </div>

      {jobs.length === 0 ? (
        <div className="px-4 py-4 text-sm text-gray-400 text-center">
          No jobs in this stage.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-100 text-sm">
            <thead>
              <tr className="bg-gray-50/50">
                <th className="px-4 py-2 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  Job
                </th>
                <th className="px-4 py-2 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  Code
                </th>
                <th className="px-4 py-2 text-center text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  Routes
                </th>
                <th className="px-4 py-2 text-center text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  Sessions
                </th>
                <th className="px-4 py-2 text-center text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  Exceptions
                </th>
                <th className="px-4 py-2 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  Last Sync
                </th>
                <th className="px-4 py-2 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {jobs.map((job) => (
                <JobRow key={job.id} job={job} onRefresh={onRefresh} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function JobsPipelineView({
  jobs,
  onRefresh,
}: JobsPipelineViewProps) {
  const knownKeys = new Set(PIPELINE_STAGES.map((s) => s.key));
  const grouped: Record<string, Job[]> = {};
  for (const stage of PIPELINE_STAGES) grouped[stage.key] = [];
  const otherJobs: Job[] = [];

  for (const job of jobs) {
    if (knownKeys.has(job.status)) {
      grouped[job.status].push(job);
    } else {
      otherJobs.push(job);
    }
  }

  return (
    <div className="space-y-4">
      {PIPELINE_STAGES.map((stage) => (
        <StageGroup
          key={stage.key}
          stage={stage}
          jobs={grouped[stage.key]}
          onRefresh={onRefresh}
        />
      ))}
      {otherJobs.length > 0 && (
        <StageGroup
          stage={{
            key: "other",
            label: "Other",
            description: "Jobs with unrecognised status",
          }}
          jobs={otherJobs}
          onRefresh={onRefresh}
        />
      )}
    </div>
  );
}
