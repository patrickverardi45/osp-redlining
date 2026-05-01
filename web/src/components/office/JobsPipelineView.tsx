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
    <tr>
      <td>
        <Link
          href={`/jobs/${job.id}`}
          className="tl-link"
          style={{ fontWeight: 600, fontSize: 13 }}
        >
          {job.job_name}
        </Link>
      </td>
      <td
        style={{
          color: "var(--tl-text-muted)",
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          fontSize: 12,
          whiteSpace: "nowrap",
        }}
      >
        {job.job_code}
      </td>
      <td
        style={{
          textAlign: "center",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {job.route_count}
      </td>
      <td
        style={{
          textAlign: "center",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {job.session_count}
      </td>
      <td
        style={{
          textAlign: "center",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        <span
          style={{
            color:
              job.exception_count > 0 ? "#fca5a5" : "var(--tl-text-faint)",
            fontWeight: job.exception_count > 0 ? 700 : 500,
          }}
        >
          {job.exception_count}
        </span>
      </td>
      <td
        style={{
          color: "var(--tl-text-faint)",
          fontSize: 12,
          whiteSpace: "nowrap",
        }}
      >
        {formatDate(job.last_sync_at)}
      </td>
      <td>
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
    <div className="tl-card" style={{ overflow: "hidden" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "12px 16px",
          background: "var(--tl-bg-grid)",
          borderBottom: "1px solid var(--tl-border)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <StatusBadge status={stage.key} />
          <span style={{ color: "var(--tl-text-faint)", fontSize: 12 }}>
            {stage.description}
          </span>
        </div>
        <span
          style={{
            color: "var(--tl-text-muted)",
            fontSize: 12,
            fontWeight: 700,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {jobs.length} job{jobs.length !== 1 ? "s" : ""}
        </span>
      </div>

      {jobs.length === 0 ? (
        <div
          style={{
            padding: "16px",
            textAlign: "center",
            color: "var(--tl-text-faint)",
            fontSize: 13,
          }}
        >
          No jobs in this stage.
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table className="tl-table">
            <thead>
              <tr>
                <th>Job</th>
                <th>Code</th>
                <th style={{ textAlign: "center" }}>Routes</th>
                <th style={{ textAlign: "center" }}>Sessions</th>
                <th style={{ textAlign: "center" }}>Exceptions</th>
                <th>Last Sync</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
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
    <div style={{ display: "grid", gap: 14 }}>
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
