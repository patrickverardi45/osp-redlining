// web/src/components/office/CloseoutContentSummaryPanel.tsx

import type { JobDetail } from "@/lib/api";

interface CloseoutContentSummaryPanelProps {
  job: JobDetail;
}

function formatDate(ts: string | null | undefined): string {
  if (!ts) return "—";
  return new Date(ts).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

function latestArtifactDate(
  artifacts: JobDetail["artifacts"]
): string | null {
  const completed = (artifacts ?? [])
    .filter((a) => a.generation_status === "complete" && a.created_at)
    .sort(
      (a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    );
  return completed[0]?.created_at ?? null;
}

interface ContentRowProps {
  label: string;
  value: string | number;
  subtext?: string;
  highlight?: boolean;
}

function ContentRow({ label, value, subtext, highlight }: ContentRowProps) {
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-gray-100 last:border-b-0">
      <span className="text-sm text-gray-600">{label}</span>
      <div className="text-right">
        <span
          className={`text-sm font-semibold tabular-nums ${
            highlight ? "text-red-600" : "text-gray-800"
          }`}
        >
          {value}
        </span>
        {subtext && (
          <div className="text-xs text-gray-400 mt-0.5">{subtext}</div>
        )}
      </div>
    </div>
  );
}

export default function CloseoutContentSummaryPanel({
  job,
}: CloseoutContentSummaryPanelProps) {
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
  const latestDate = latestArtifactDate(artifacts);

  const totalStations = stations.length;
  const totalPhotos = photos.length;

  // Aggregate from sessions as fallback if stations array absent
  const sessionStationTotal = sessions.reduce(
    (sum, s) => sum + (s.station_count ?? 0),
    0
  );
  const sessionPhotoTotal = sessions.reduce(
    (sum, s) => sum + (s.photo_count ?? 0),
    0
  );

  const displayedStations = totalStations > 0 ? totalStations : sessionStationTotal;
  const displayedPhotos = totalPhotos > 0 ? totalPhotos : sessionPhotoTotal;

  return (
    <section>
      <div className="mb-3">
        <h2 className="text-base font-semibold text-gray-800">
          Closeout Package Contents
        </h2>
        <p className="text-xs text-gray-400 mt-0.5">
          Summary of data that will be included in the generated closeout
          package.
        </p>
      </div>

      <div className="rounded-lg border border-gray-200 bg-white shadow-sm px-5 py-1">
        <ContentRow label="Routes" value={routes.length} />
        <ContentRow label="Walk Sessions" value={sessions.length} />
        <ContentRow
          label="Stations"
          value={displayedStations}
          subtext={
            totalStations === 0 && sessionStationTotal > 0
              ? "from session totals"
              : undefined
          }
        />
        <ContentRow
          label="Photos"
          value={displayedPhotos}
          subtext={
            totalPhotos === 0 && sessionPhotoTotal > 0
              ? "from session totals"
              : undefined
          }
        />
        <ContentRow
          label="Open Exceptions"
          value={openExceptions}
          highlight={openExceptions > 0}
        />
        <ContentRow
          label="Completed Artifacts"
          value={completedArtifacts}
          subtext={
            latestDate ? `Latest: ${formatDate(latestDate)}` : undefined
          }
        />
      </div>
    </section>
  );
}
