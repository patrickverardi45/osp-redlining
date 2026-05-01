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
  const colorMap: Record<NonNullable<CardProps["highlight"]>, string> = {
    blue: "#7dd3fc",
    yellow: "#fde047",
    orange: "#fcd34d",
    red: "#fca5a5",
  };
  const valueColor = highlight ? colorMap[highlight] : "var(--tl-text)";

  return (
    <div
      className="tl-card tl-card-padded"
      style={{ flex: 1, minWidth: 140 }}
    >
      <div
        className="tl-metric-value tl-metric-value-lg"
        style={{ color: valueColor, marginTop: 0 }}
      >
        {value}
      </div>
      <div className="tl-metric-label" style={{ marginTop: 6 }}>
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
    <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
      <SummaryCard label="Total Jobs" value={total} />
      <SummaryCard label="In Progress" value={inProgress} highlight="blue" />
      <SummaryCard label="QA Review" value={qaReview} highlight="yellow" />
      <SummaryCard
        label="Closeout Ready"
        value={closeoutReady}
        highlight="orange"
      />
      <SummaryCard label="Needs Attention" value={attention} highlight="red" />
    </div>
  );
}
