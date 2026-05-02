// web/src/components/office/JobHeader.tsx

import Link from "next/link";
import type { JobDetail } from "@/lib/api";

interface JobHeaderProps {
  job: JobDetail;
}

const STATUS_PILL: Record<string, { label: string; tone: string }> = {
  pending: { label: "Pending", tone: "tl-pill" },
  in_progress: { label: "In Progress", tone: "tl-pill tl-pill-info" },
  complete: { label: "Complete", tone: "tl-pill tl-pill-success" },
  on_hold: { label: "On Hold", tone: "tl-pill tl-pill-warn" },
  qa_review: { label: "QA Review", tone: "tl-pill tl-pill-warn" },
  closeout_ready: { label: "Closeout Ready", tone: "tl-pill tl-pill-accent" },
};

function StatusBadge({ status }: { status: string }) {
  const config = STATUS_PILL[status] ?? {
    label: status
      .replace(/_/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase()),
    tone: "tl-pill",
  };
  return <span className={config.tone}>{config.label}</span>;
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
  const valueColor =
    highlight && value > 0 ? "#fca5a5" : "var(--tl-text)";
  return (
    <div
      className="tl-card tl-card-padded"
      style={{ minWidth: 120, textAlign: "center" }}
    >
      <div
        className="tl-metric-value tl-metric-value-lg"
        style={{ color: valueColor, marginTop: 0, fontSize: 30 }}
      >
        {value}
      </div>
      <div className="tl-metric-label" style={{ marginTop: 6 }}>
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
    <div style={{ display: "grid", gap: 20 }}>
      {/* Breadcrumb */}
      <nav style={{ fontSize: 13, color: "var(--tl-text-muted)" }}>
        <Link href="/jobs" className="tl-link">
          Jobs
        </Link>
        <span style={{ margin: "0 8px", color: "var(--tl-text-faint)" }}>/</span>
        <span style={{ color: "var(--tl-text)", fontWeight: 600 }}>
          {job.job_code}
        </span>
      </nav>

      {/* Title row */}
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 16,
          flexWrap: "wrap",
        }}
      >
        <div>
          <div className="tl-eyebrow">Job</div>
          <h1 className="tl-h1" style={{ margin: "8px 0 4px", fontSize: 26 }}>
            {job.job_name}
          </h1>
          <p
            style={{
              margin: 0,
              color: "var(--tl-text-muted)",
              fontFamily:
                "ui-monospace, SFMono-Regular, Menlo, monospace",
              fontSize: 12,
            }}
          >
            {job.job_code}
          </p>
          <p
            style={{
              margin: "6px 0 0",
              color: "var(--tl-text-faint)",
              fontSize: 12,
            }}
          >
            {formatLastSync(job.last_sync_at)}
          </p>
        </div>
        <div style={{ paddingTop: 4 }}>
          <StatusBadge status={job.status} />
        </div>
      </div>

      {/* Stat cards */}
      <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
        <StatCard label="Routes" value={job.route_count} />
        <StatCard label="Sessions" value={job.session_count} />
        <StatCard label="Exceptions" value={job.exception_count} highlight />
      </div>
    </div>
  );
}
