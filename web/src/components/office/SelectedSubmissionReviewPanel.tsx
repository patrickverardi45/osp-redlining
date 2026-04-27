// web/src/components/office/SelectedSubmissionReviewPanel.tsx
//
// Phase 4E — compact "Selected Submission Review" card.
//
// Renders above the Map Review panel on /jobs/[jobId] when a `session`
// query parameter resolves to one of the job's sessions. Read-only: shows
// the headline facts about the chosen submission so reviewers know exactly
// which walk they're looking at when they came in via the inbox.
//
// The session-not-found case is rendered as a yellow notice rather than a
// hard error — the reviewer landed here on purpose, and a stale link
// (session deleted, wrong id, etc.) shouldn't break the rest of the page.
"use client";

import type { Session } from "@/lib/api";

type SelectedSubmissionReviewPanelProps = {
  selectedSessionId: string;
  session: Session | null;
};

function shortenId(rawId: string): string {
  if (!rawId) return "—";
  return rawId.length <= 8 ? rawId : rawId.slice(0, 8);
}

function formatDate(ts: string | null | undefined): string {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatDateTime(ts: string | null | undefined): string {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

function safeCount(n: unknown): number {
  return typeof n === "number" && Number.isFinite(n) ? n : 0;
}

export default function SelectedSubmissionReviewPanel({
  selectedSessionId,
  session,
}: SelectedSubmissionReviewPanelProps) {
  // Stale link / session not on this job. Show a soft notice and bail.
  if (!session) {
    return (
      <section
        aria-label="Selected submission review"
        className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"
      >
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <div className="font-semibold">Selected Submission Review</div>
            <div className="mt-1 text-xs">
              Could not find session{" "}
              <span className="font-mono">
                {shortenId(selectedSessionId)}
              </span>{" "}
              on this job. The link may be out of date.
            </div>
          </div>
        </div>
      </section>
    );
  }

  const stations = safeCount(session.station_count);
  const photos = safeCount(session.photo_count);
  const breadcrumbs = safeCount(session.track_point_count);
  const crew = session.crew_name?.trim() || "—";

  return (
    <section
      aria-label="Selected submission review"
      className="rounded-lg border border-gray-200 bg-white shadow-sm overflow-hidden"
    >
      <div className="border-b border-gray-100 bg-gray-50 px-4 py-3 flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-base font-semibold text-gray-800">
            Selected Submission Review
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Came in from the Field Submissions Inbox. Read-only.
          </p>
        </div>
        <span
          className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800 whitespace-nowrap"
          aria-label="Status: Needs Review"
        >
          Needs Review
        </span>
      </div>

      <dl className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 divide-x divide-y sm:divide-y-0 divide-gray-100">
        <Cell label="Session" mono>
          {shortenId(session.id)}
        </Cell>
        <Cell label="Crew">{crew}</Cell>
        <Cell label="Date">
          <div className="text-gray-800">{formatDate(session.started_at)}</div>
          <div className="text-[11px] text-gray-400 mt-0.5">
            {formatDateTime(session.started_at)}
          </div>
        </Cell>
        <Cell label="Stations" align="right" mono>
          {stations.toLocaleString()}
        </Cell>
        <Cell label="Photos" align="right" mono>
          {photos.toLocaleString()}
        </Cell>
        <Cell label="Breadcrumbs" align="right" mono>
          {breadcrumbs.toLocaleString()}
        </Cell>
      </dl>
    </section>
  );
}

function Cell({
  label,
  children,
  align,
  mono,
}: {
  label: string;
  children: React.ReactNode;
  align?: "left" | "right";
  mono?: boolean;
}) {
  return (
    <div
      className={`px-4 py-3 ${
        align === "right" ? "text-right" : "text-left"
      }`}
    >
      <dt className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
        {label}
      </dt>
      <dd
        className={`mt-1 text-sm text-gray-800 ${
          mono ? "font-mono" : ""
        } ${align === "right" ? "tabular-nums" : ""}`}
      >
        {children}
      </dd>
    </div>
  );
}
