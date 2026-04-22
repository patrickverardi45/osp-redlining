// web/src/components/office/ArtifactsPanel.tsx

import type { Artifact } from "@/lib/api";

// ─── Props ────────────────────────────────────────────────────────────────────

interface ArtifactsPanelProps {
  artifacts: Artifact[];
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const GENERATION_STATUS_CONFIG: Record<
  string,
  { label: string; className: string }
> = {
  queued: {
    label: "Queued",
    className:
      "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-700",
  },
  working: {
    label: "Working…",
    className:
      "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700",
  },
  complete: {
    label: "Complete",
    className:
      "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700",
  },
  failed: {
    label: "Failed",
    className:
      "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700",
  },
};

function GenerationStatusBadge({ status }: { status: string }) {
  const config = GENERATION_STATUS_CONFIG[status] ?? {
    label: status,
    className:
      "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-500",
  };
  return <span className={config.className}>{config.label}</span>;
}

function formatArtifactType(raw: string): string {
  return raw.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatDate(ts: string): string {
  return new Date(ts).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function ArtifactsPanel({ artifacts }: ArtifactsPanelProps) {
  const safeArtifacts = artifacts ?? [];

  return (
    <section>
      <div className="mb-3">
        <h2 className="text-base font-semibold text-gray-800">
          Generated Artifacts
          <span className="ml-2 text-gray-400 font-normal text-sm">
            ({safeArtifacts.length})
          </span>
        </h2>
      </div>

      {safeArtifacts.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50 py-10 text-center text-sm text-gray-400">
          No artifacts generated yet. Use Report Actions above to generate
          documents.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200 shadow-sm">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Type
                </th>
                <th className="px-4 py-3 text-center text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Version
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Created
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Download
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-100">
              {safeArtifacts.map((artifact) => (
                <tr key={artifact.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 font-medium text-gray-800 whitespace-nowrap">
                    {formatArtifactType(artifact.artifact_type)}
                  </td>
                  <td className="px-4 py-3 text-center text-gray-600 tabular-nums">
                    v{artifact.version_number}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <GenerationStatusBadge
                      status={artifact.generation_status}
                    />
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs whitespace-nowrap">
                    {formatDate(artifact.created_at)}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    {artifact.file_url && artifact.generation_status === "complete" ? (
                      <a
                        href={artifact.file_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs font-medium text-blue-600 hover:text-blue-800 hover:underline"
                      >
                        Download ↗
                      </a>
                    ) : (
                      <span className="text-xs text-gray-400">—</span>
                    )}
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
