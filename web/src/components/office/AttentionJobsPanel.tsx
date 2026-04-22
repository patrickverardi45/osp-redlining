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
      <div className="flex items-center gap-2 mb-3">
        <h2 className="text-base font-semibold text-gray-800">
          Needs Attention
        </h2>
        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-red-100 text-red-700">
          {attentionJobs.length}
        </span>
      </div>

      <div className="rounded-lg border border-red-200 bg-red-50/30 overflow-hidden shadow-sm">
        <table className="min-w-full divide-y divide-red-100 text-sm">
          <thead className="bg-red-50">
            <tr>
              <th className="px-4 py-2.5 text-left text-xs font-semibold text-red-700 uppercase tracking-wider">
                Job
              </th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold text-red-700 uppercase tracking-wider">
                Code
              </th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold text-red-700 uppercase tracking-wider">
                Why
              </th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold text-red-700 uppercase tracking-wider">
                Last Sync
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-red-100 bg-white">
            {attentionJobs.map((job) => (
              <tr key={job.id} className="hover:bg-red-50/50 transition-colors">
                <td className="px-4 py-2.5">
                  <Link
                    href={`/jobs/${job.id}`}
                    className="font-medium text-blue-600 hover:text-blue-800 hover:underline"
                  >
                    {job.job_name}
                  </Link>
                </td>
                <td className="px-4 py-2.5 text-gray-500 font-mono text-xs">
                  {job.job_code}
                </td>
                <td className="px-4 py-2.5 text-sm text-gray-700">
                  {attentionReason(job)}
                </td>
                <td className="px-4 py-2.5 text-xs text-gray-400 whitespace-nowrap">
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
