// web/src/components/office/JobHeader.tsx

import Link from "next/link";
import type { JobDetail } from "@/lib/api";

interface JobHeaderProps {
  job: JobDetail;
}

const STATUS_CONFIG: Record<string, { label: string; className: string }> = {
  pending: {
    label: "Pending",
    className:
      "inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-gray-100 text-gray-700",
  },
  in_progress: {
    label: "In Progress",
    className:
      "inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-blue-100 text-blue-700",
  },
  complete: {
    label: "Complete",
    className:
      "inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-green-100 text-green-700",
  },
  on_hold: {
    label: "On Hold",
    className:
      "inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-yellow-100 text-yellow-700",
  },
};

function StatusBadge({ status }: { status: string }) {
  const config = STATUS_CONFIG[status] ?? {
    label: status,
    className:
      "inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-gray-100 text-gray-600",
  };
  return <span className={config.className}>{config.label}</span>;
}

function StatCard({
  label,
  value,
  highlight,
}: {
  label: string;
  value: number;
  highlight?: boolean;
}) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg px-6 py-4 shadow-sm text-center min-w-[100px]">
      <div
        className={`text-3xl font-bold ${
          highlight && value > 0 ? "text-red-600" : "text-gray-800"
        }`}
      >
        {value}
      </div>
      <div className="text-xs text-gray-500 mt-1 uppercase tracking-wide font-medium">
        {label}
      </div>
    </div>
  );
}

function formatLastSync(ts: string | null): string {
  if (!ts) return "Never synced";
  return (
    "Last sync: " +
    new Date(ts).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    })
  );
}

export default function JobHeader({ job }: JobHeaderProps) {
  return (
    <div className="space-y-5">
      {/* Breadcrumb */}
      <nav className="text-sm text-gray-500">
        <Link href="/jobs" className="hover:text-blue-600 hover:underline">
          Jobs
        </Link>
        <span className="mx-2 text-gray-300">/</span>
        <span className="text-gray-800 font-medium">{job.job_code}</span>
      </nav>

      {/* Title row */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{job.job_name}</h1>
          <p className="text-sm text-gray-400 font-mono mt-0.5">{job.job_code}</p>
          <p className="text-xs text-gray-400 mt-1">{formatLastSync(job.last_sync_at)}</p>
        </div>
        <div className="pt-1">
          <StatusBadge status={job.status} />
        </div>
      </div>

      {/* Stat cards */}
      <div className="flex gap-4 flex-wrap">
        <StatCard label="Routes" value={job.route_count} />
        <StatCard label="Sessions" value={job.session_count} />
        <StatCard label="Exceptions" value={job.exception_count} highlight />
      </div>
    </div>
  );
}
