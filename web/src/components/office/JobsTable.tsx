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
      <div className="text-center py-16 text-gray-400 text-sm">
        No jobs found.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200 shadow-sm">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-3 text-left font-semibold text-gray-600 uppercase tracking-wider text-xs">
              Job
            </th>
            <th className="px-4 py-3 text-left font-semibold text-gray-600 uppercase tracking-wider text-xs">
              Code
            </th>
            <th className="px-4 py-3 text-left font-semibold text-gray-600 uppercase tracking-wider text-xs">
              Status
            </th>
            <th className="px-4 py-3 text-center font-semibold text-gray-600 uppercase tracking-wider text-xs">
              Routes
            </th>
            <th className="px-4 py-3 text-center font-semibold text-gray-600 uppercase tracking-wider text-xs">
              Sessions
            </th>
            <th className="px-4 py-3 text-center font-semibold text-gray-600 uppercase tracking-wider text-xs">
              Exceptions
            </th>
            <th className="px-4 py-3 text-left font-semibold text-gray-600 uppercase tracking-wider text-xs">
              Last Sync
            </th>
            <th className="px-4 py-3 text-left font-semibold text-gray-600 uppercase tracking-wider text-xs">
              Actions
            </th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-100">
          {jobs.map((job) => (
            <tr
              key={job.id}
              className="hover:bg-gray-50 transition-colors align-top"
            >
              <td className="px-4 py-3">
                <Link
                  href={`/jobs/${job.id}`}
                  className="font-medium text-blue-600 hover:text-blue-800 hover:underline"
                >
                  {job.job_name}
                </Link>
              </td>
              <td className="px-4 py-3 text-gray-500 font-mono text-xs">
                {job.job_code}
              </td>
              <td className="px-4 py-3">
                <StatusBadge status={job.status} />
              </td>
              <td className="px-4 py-3 text-center text-gray-700 font-medium tabular-nums">
                {job.route_count}
              </td>
              <td className="px-4 py-3 text-center text-gray-700 font-medium tabular-nums">
                {job.session_count}
              </td>
              <td className="px-4 py-3 text-center tabular-nums">
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
              <td className="px-4 py-3 text-gray-400 text-xs whitespace-nowrap">
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
          ))}
        </tbody>
      </table>
    </div>
  );
}
