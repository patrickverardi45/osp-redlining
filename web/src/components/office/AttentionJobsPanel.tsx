// web/src/components/office/AttentionJobsPanel.tsx

import Link from "next/link";
import type { Job } from "@/lib/api";

interface AttentionJobsPanelProps {
  jobs: Job[];
}

function isAttentionJob(job: Job): boolean {
  return (
    job.exception_count > 0 ||
    job.status === "qa_review" ||
    job.status === "closeout_ready"
  );
}

function attentionReason(job: Job): string {
  const reasons: string[] = [];
  if (job.exception_count > 0)
    reasons.push(`${job.exception_count} open exception${job.exception_count !== 1 ? "s" : ""}`);
  if (job.status === "qa_review") reasons.push("QA review pending");
  if (job.status === "closeout_ready") reasons.push("Ready to close out");
  return reasons.join(" · ");
}

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

export default function AttentionJobsPanel({ jobs }: AttentionJobsPanelProps) {
  const attentionJobs = jobs.filter(isAttentionJob);

  if (attentionJobs.length === 0) return null;

  return (
    <section>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          marginBottom: 12,
        }}
      >
        <h2 className="tl-h2">Needs Attention</h2>
        <span className="tl-pill tl-pill-danger">{attentionJobs.length}</span>
      </div>

      <div
        className="tl-table-wrap"
        style={{
          borderColor: "var(--tl-red-border)",
          background: "var(--tl-surface)",
        }}
      >
        <table className="tl-table">
          <thead>
            <tr>
              <th style={{ color: "#fca5a5" }}>Job</th>
              <th style={{ color: "#fca5a5" }}>Code</th>
              <th style={{ color: "#fca5a5" }}>Why</th>
              <th style={{ color: "#fca5a5" }}>Last Sync</th>
            </tr>
          </thead>
          <tbody>
            {attentionJobs.map((job) => (
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
                <td style={{ color: "var(--tl-text)" }}>
                  {attentionReason(job)}
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
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
