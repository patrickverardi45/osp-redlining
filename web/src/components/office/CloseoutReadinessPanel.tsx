// web/src/components/office/CloseoutReadinessPanel.tsx

import type { JobDetail } from "@/lib/api";

interface CloseoutReadinessPanelProps {
  job: JobDetail;
}

// ─── Readiness logic ──────────────────────────────────────────────────────────

type ReadinessLevel = "ready" | "needs_review" | "not_ready";

interface ReadinessResult {
  level: ReadinessLevel;
  label: string;
  reason: string;
}

function evaluateReadiness(job: JobDetail): ReadinessResult {
  const routes = job.routes ?? [];
  const sessions = job.sessions ?? [];
  const stations = job.stations ?? [];
  const exceptions = job.exceptions ?? [];

  const openExceptions = exceptions.filter((e) => e.status === "open").length;

  // NOT READY — hard blockers
  if (routes.length === 0) {
    return {
      level: "not_ready",
      label: "Not Ready",
      reason: "No routes are assigned to this job.",
    };
  }
  if (sessions.length === 0) {
    return {
      level: "not_ready",
      label: "Not Ready",
      reason: "No walk sessions have been recorded.",
    };
  }
  if (stations.length === 0) {
    return {
      level: "not_ready",
      label: "Not Ready",
      reason: "No station data has been collected.",
    };
  }

  // NEEDS REVIEW — soft blockers
  if (openExceptions > 0) {
    return {
      level: "needs_review",
      label: "Needs Review",
      reason: `${openExceptions} open exception${openExceptions !== 1 ? "s" : ""} must be resolved or dismissed before closeout.`,
    };
  }
  if (sessions.length > 0 && stations.length === 0) {
    return {
      level: "needs_review",
      label: "Needs Review",
      reason: "Walk sessions exist but no station data has been collected.",
    };
  }
  if (routes.length > 0 && sessions.length === 0) {
    return {
      level: "needs_review",
      label: "Needs Review",
      reason: "Routes are assigned but no walk sessions have been completed.",
    };
  }

  // READY
  return {
    level: "ready",
    label: "Ready for Closeout",
    reason: "All required data is present and no open exceptions are blocking export.",
  };
}

// ─── Readiness badge ──────────────────────────────────────────────────────────

const READINESS_STYLES: Record<
  ReadinessLevel,
  { badge: string; border: string; bg: string; icon: string }
> = {
  ready: {
    badge: "bg-green-100 text-green-800 border border-green-200",
    border: "border-green-200",
    bg: "bg-green-50/30",
    icon: "✓",
  },
  needs_review: {
    badge: "bg-yellow-100 text-yellow-800 border border-yellow-200",
    border: "border-yellow-200",
    bg: "bg-yellow-50/30",
    icon: "⚠",
  },
  not_ready: {
    badge: "bg-red-100 text-red-800 border border-red-200",
    border: "border-red-200",
    bg: "bg-red-50/20",
    icon: "✕",
  },
};

// ─── Stat item ────────────────────────────────────────────────────────────────

function StatItem({
  label,
  value,
  warn,
}: {
  label: string;
  value: number;
  warn?: boolean;
}) {
  return (
    <div className="flex flex-col items-center px-4 py-3 border-r border-gray-200 last:border-r-0">
      <span
        className={`text-xl font-bold tabular-nums ${
          warn && value > 0 ? "text-red-600" : "text-gray-800"
        }`}
      >
        {value}
      </span>
      <span className="text-xs text-gray-500 mt-0.5 font-medium uppercase tracking-wide text-center">
        {label}
      </span>
    </div>
  );
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function CloseoutReadinessPanel({
  job,
}: CloseoutReadinessPanelProps) {
  const routes = job.routes ?? [];
  const sessions = job.sessions ?? [];
  const stations = job.stations ?? [];
  const photos = job.photos ?? [];
  const exceptions = job.exceptions ?? [];
  const artifacts = job.artifacts ?? [];

  const openExceptions = exceptions.filter((e) => e.status === "open").length;
  const completedArtifacts = artifacts.filter(
    (a) => a.generation_status === "complete"
  ).length;

  const { level, label, reason } = evaluateReadiness(job);
  const style = READINESS_STYLES[level];

  return (
    <section>
      <div className="mb-3">
        <h2 className="text-base font-semibold text-gray-800">
          Closeout Readiness
        </h2>
      </div>

      <div
        className={`rounded-lg border ${style.border} ${style.bg} overflow-hidden shadow-sm`}
      >
        {/* Readiness status bar */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-gray-200">
          <span
            className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-semibold ${style.badge}`}
          >
            <span>{style.icon}</span>
            {label}
          </span>
          <span className="text-sm text-gray-600">{reason}</span>
        </div>

        {/* Stat strip */}
        <div className="flex flex-wrap divide-x divide-gray-200 bg-white">
          <StatItem label="Routes" value={routes.length} />
          <StatItem label="Sessions" value={sessions.length} />
          <StatItem label="Stations" value={stations.length} />
          <StatItem label="Photos" value={photos.length} />
          <StatItem
            label="Open Exceptions"
            value={openExceptions}
            warn={true}
          />
          <StatItem label="Artifacts" value={completedArtifacts} />
        </div>
      </div>
    </section>
  );
}
