// web/src/components/office/JobsSummaryCards.tsx

import type { Job } from "@/lib/api";

interface JobsSummaryCardsProps {
  jobs: Job[];
}

function isAttentionJob(job: Job): boolean {
  return (
    job.exception_count > 0 ||
    job.status === "qa_review" ||
    job.status === "closeout_ready"
  );
}

interface CardProps {
  label: string;
  value: number;
  highlight?: "blue" | "yellow" | "orange" | "red";
}

function SummaryCard({ label, value, highlight }: CardProps) {
  const colorMap = {
    blue: "text-blue-700",
    yellow: "text-yellow-700",
    orange: "text-orange-600",
    red: "text-red-600",
  };
  const valueClass = highlight ? colorMap[highlight] : "text-gray-800";

  return (
    <div className="bg-white border border-gray-200 rounded-lg px-5 py-4 shadow-sm flex-1 min-w-[120px]">
      <div className={`text-2xl font-bold tabular-nums ${valueClass}`}>
        {value}
      </div>
      <div className="text-xs text-gray-500 mt-1 font-medium uppercase tracking-wide">
        {label}
      </div>
    </div>
  );
}

export default function JobsSummaryCards({ jobs }: JobsSummaryCardsProps) {
  const total = jobs.length;
  const inProgress = jobs.filter((j) => j.status === "in_progress").length;
  const qaReview = jobs.filter((j) => j.status === "qa_review").length;
  const closeoutReady = jobs.filter((j) => j.status === "closeout_ready").length;
  const attention = jobs.filter(isAttentionJob).length;

  return (
    <div className="flex flex-wrap gap-3">
      <SummaryCard label="Total Jobs" value={total} />
      <SummaryCard label="In Progress" value={inProgress} highlight="blue" />
      <SummaryCard label="QA Review" value={qaReview} highlight="yellow" />
      <SummaryCard label="Closeout Ready" value={closeoutReady} highlight="orange" />
      <SummaryCard label="Needs Attention" value={attention} highlight="red" />
    </div>
  );
}
