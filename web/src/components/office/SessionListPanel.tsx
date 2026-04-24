import type { Session } from "@/lib/api";

interface SessionListPanelProps {
  sessions: Session[];
}

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "https://walkv1-backend.onrender.com"
).replace(/\/+$/, "");

function resolvePhotoUrl(photoUrl: string): string {
  if (/^https?:\/\//i.test(photoUrl)) {
    try {
      const parsed = new URL(photoUrl);
      const isLocalhostHost =
        parsed.hostname === "localhost" ||
        parsed.hostname === "127.0.0.1" ||
        parsed.hostname === "0.0.0.0";
      if (isLocalhostHost) {
        const normalizedPath = `${parsed.pathname}${parsed.search}${parsed.hash}`;
        return API_BASE_URL ? `${API_BASE_URL}${normalizedPath}` : normalizedPath;
      }
      return photoUrl;
    } catch {
      return photoUrl;
    }
  }
  const normalizedPath = photoUrl.startsWith("/") ? photoUrl : `/${photoUrl}`;
  return API_BASE_URL ? `${API_BASE_URL}${normalizedPath}` : normalizedPath;
}

const SESSION_STATUS_CONFIG: Record<string, { label: string; className: string }> = {
  active: {
    label: "Active",
    className:
      "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700",
  },
  ended: {
    label: "Ended",
    className:
      "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600",
  },
  paused: {
    label: "Paused",
    className:
      "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-700",
  },
  syncing: {
    label: "Syncing",
    className:
      "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700",
  },
};

function SessionStatusBadge({ status }: { status: string }) {
  const config = SESSION_STATUS_CONFIG[status] ?? {
    label: status,
    className:
      "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-500",
  };
  return <span className={config.className}>{config.label}</span>;
}

function formatTimestamp(ts: string | null): string {
  if (!ts) return "—";
  return new Date(ts).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

function calcDuration(start: string, end: string | null): string {
  if (!end) return "In progress";
  const diffMs = new Date(end).getTime() - new Date(start).getTime();
  if (diffMs < 0) return "—";
  const totalMin = Math.floor(diffMs / 60000);
  const hours = Math.floor(totalMin / 60);
  const mins = totalMin % 60;
  if (hours === 0) return `${mins}m`;
  return `${hours}h ${mins}m`;
}

export default function SessionListPanel({ sessions }: SessionListPanelProps) {
  return (
    <section>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-base font-semibold text-gray-800">
          Walk Sessions
          <span className="ml-2 text-gray-400 font-normal text-sm">
            ({sessions.length})
          </span>
        </h2>
      </div>

      {sessions.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50 py-10 text-center text-sm text-gray-400">
          No walk sessions recorded for this job.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200 shadow-sm">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Crew
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Started
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Ended
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Duration
                </th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Stations
                </th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Photos
                </th>
                <th className="px-4 py-3 text-center text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  View
                </th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Track Pts
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-100">
              {sessions.map((session) => (
                <tr key={session.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 font-medium text-gray-800">
                    {session.crew_name}
                  </td>
                  <td className="px-4 py-3">
                    <SessionStatusBadge status={session.status} />
                  </td>
                  <td className="px-4 py-3 text-gray-500 whitespace-nowrap text-xs">
                    {formatTimestamp(session.started_at)}
                  </td>
                  <td className="px-4 py-3 text-gray-500 whitespace-nowrap text-xs">
                    {formatTimestamp(session.ended_at)}
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs whitespace-nowrap">
                    {calcDuration(session.started_at, session.ended_at)}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-700 tabular-nums">
                    {session.station_count}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-700 tabular-nums">
                    {session.photo_count}
                  </td>

                  {/* 🔥 NEW: VIEW PHOTO */}
                  <td className="px-4 py-3 text-center">
                    {session.latest_photo_url ? (
                      <a
                        href={resolvePhotoUrl(session.latest_photo_url)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-600 hover:underline text-xs font-medium"
                      >
                        View Photo
                      </a>
                    ) : (
                      <span className="text-gray-300 text-xs">—</span>
                    )}
                  </td>

                  <td className="px-4 py-3 text-right text-gray-700 tabular-nums">
                    {session.track_point_count?.toLocaleString?.() ?? 0}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}