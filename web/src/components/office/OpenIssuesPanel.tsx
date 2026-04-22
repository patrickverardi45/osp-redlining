// web/src/components/office/OpenIssuesPanel.tsx

import type { Exception } from "@/lib/api";

interface OpenIssuesPanelProps {
  exceptions: Exception[];
}

const SEVERITY_CONFIG: Record<string, { label: string; className: string }> = {
  low: {
    label: "Low",
    className:
      "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600",
  },
  medium: {
    label: "Medium",
    className:
      "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-700",
  },
  high: {
    label: "High",
    className:
      "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-700",
  },
  critical: {
    label: "Critical",
    className:
      "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700",
  },
};

function SeverityBadge({ severity }: { severity: string }) {
  const config = SEVERITY_CONFIG[severity] ?? {
    label: severity,
    className:
      "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-500",
  };
  return <span className={config.className}>{config.label}</span>;
}

function formatType(raw: string): string {
  return raw.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function OpenIssuesPanel({ exceptions }: OpenIssuesPanelProps) {
  const openExceptions = (exceptions ?? []).filter(
    (e) => e.status === "open"
  );

  return (
    <section>
      <div className="mb-3">
        <h2 className="text-base font-semibold text-gray-800">
          Open Issues
          {openExceptions.length > 0 && (
            <span className="ml-2 inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-red-100 text-red-700">
              {openExceptions.length} blocking
            </span>
          )}
        </h2>
        <p className="text-xs text-gray-400 mt-0.5">
          Open exceptions that must be resolved or dismissed before closeout.
        </p>
      </div>

      {openExceptions.length === 0 ? (
        <div className="rounded-lg border border-dashed border-green-200 bg-green-50/40 py-8 text-center text-sm text-green-700 font-medium">
          ✓ No open exceptions blocking closeout.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-red-200 shadow-sm">
          <table className="min-w-full divide-y divide-red-100 text-sm">
            <thead className="bg-red-50">
              <tr>
                <th className="px-4 py-2.5 text-left text-xs font-semibold text-red-700 uppercase tracking-wider">
                  Type
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold text-red-700 uppercase tracking-wider">
                  Severity
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold text-red-700 uppercase tracking-wider">
                  Description
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-red-100">
              {openExceptions.map((ex) => (
                <tr
                  key={ex.id}
                  className="bg-red-50/20 hover:bg-red-50/50 transition-colors"
                >
                  <td className="px-4 py-2.5 font-medium text-gray-800 whitespace-nowrap">
                    {formatType(ex.exception_type)}
                  </td>
                  <td className="px-4 py-2.5 whitespace-nowrap">
                    <SeverityBadge severity={ex.severity} />
                  </td>
                  <td className="px-4 py-2.5 text-gray-600 max-w-md">
                    {ex.description}
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
