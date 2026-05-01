// web/src/components/office/JobsTable.tsx
"use client";

import Link from "next/link";
import type { Job } from "@/lib/api";
import { STATUS_BADGE_CLASSES } from "@/lib/statusConfig";
import JobStatusActionButtons from "@/components/office/JobStatusActionButtons";

interface JobsTableProps {
  jobs: Job[];
  onRefresh: () => void;
}

function StatusBadge({ status }: { status: string }) {
  const colorClass =
    STATUS_BADGE_CLASSES[status] ?? "bg-gray-100 text-gray-600";
  const label = status
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${colorClass}`}
    >
      {label}
    </span>
  );
}

function formatDate(ts: string | null): string {
  if (!ts) return "—";
  return new Date(ts).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

export default function JobsTable({ jobs, onRefresh }: JobsTableProps) {
  if (jobs.length === 0) {
    return (
      <div
        className="tl-card tl-card-padded"
        style={{ textAlign: "center", padding: "48px 18px" }}
      >
        <span className="tl-subtle">No jobs found.</span>
      </div>
    );
  }

  return (
    <div className="tl-table-wrap" style={{ overflowX: "auto" }}>
      <table className="tl-table">
        <thead>
          <tr>
            <th>Job</th>
            <th>Code</th>
            <th>Status</th>
            <th style={{ textAlign: "center" }}>Routes</th>
            <th style={{ textAlign: "center" }}>Sessions</th>
            <th style={{ textAlign: "center" }}>Exceptions</th>
            <th>Last Sync</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.id}>
              <td>
                <Link
                  href={`/jobs/${job.id}`}
                  className="tl-link"
                  style={{ fontWeight: 600 }}
                >
                  {job.job_name}
                </Link>
              </td>
              <td
                style={{
                  color: "var(--tl-text-muted)",
                  fontFamily:
                    "ui-monospace, SFMono-Regular, Menlo, monospace",
                  fontSize: 12,
                }}
              >
                {job.job_code}
              </td>
              <td>
                <StatusBadge status={job.status} />
              </td>
              <td
                style={{
                  textAlign: "center",
                  fontVariantNumeric: "tabular-nums",
                  fontWeight: 600,
                }}
              >
                {job.route_count}
              </td>
              <td
                style={{
                  textAlign: "center",
                  fontVariantNumeric: "tabular-nums",
                  fontWeight: 600,
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
                      job.exception_count > 0
                        ? "#fca5a5"
                        : "var(--tl-text-faint)",
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
          ))}
        </tbody>
      </table>
    </div>
  );
}
