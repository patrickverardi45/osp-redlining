// web/src/components/office/ExceptionSummaryPanel.tsx
"use client";

import { useState, useCallback } from "react";
import type { Exception } from "@/lib/api";
import { updateExceptionStatus } from "@/lib/api";

// ─── Props ────────────────────────────────────────────────────────────────────

interface ExceptionSummaryPanelProps {
  exceptions: Exception[];
  onMutated: () => void; // called after successful status change so parent can refresh
}

// ─── Badge configs ────────────────────────────────────────────────────────────

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

const STATUS_CONFIG: Record<string, { label: string; className: string }> = {
  open: {
    label: "Open",
    className:
      "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-red-50 text-red-600 border border-red-200",
  },
  resolved: {
    label: "Resolved",
    className:
      "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-50 text-green-600 border border-green-200",
  },
  dismissed: {
    label: "Dismissed",
    className:
      "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-500",
  },
};

// ─── Sub-components ───────────────────────────────────────────────────────────

function SeverityBadge({ severity }: { severity: string }) {
  const config = SEVERITY_CONFIG[severity] ?? {
    label: severity,
    className:
      "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-500",
  };
  return <span className={config.className}>{config.label}</span>;
}

function StatusBadge({ status }: { status: string }) {
  const config = STATUS_CONFIG[status] ?? {
    label: status,
    className:
      "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-500",
  };
  return <span className={config.className}>{config.label}</span>;
}

function formatType(raw: string): string {
  return raw.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// ─── Filter bar ───────────────────────────────────────────────────────────────

type StatusFilter = "all" | "open" | "resolved" | "dismissed";
type SeverityFilter = "all" | "low" | "medium" | "high";

function FilterBar({
  statusFilter,
  severityFilter,
  onStatusChange,
  onSeverityChange,
}: {
  statusFilter: StatusFilter;
  severityFilter: SeverityFilter;
  onStatusChange: (v: StatusFilter) => void;
  onSeverityChange: (v: SeverityFilter) => void;
}) {
  const statusOpts: StatusFilter[] = ["all", "open", "resolved", "dismissed"];
  const severityOpts: SeverityFilter[] = ["all", "low", "medium", "high"];

  const base =
    "px-2.5 py-1 rounded text-xs font-medium border transition-colors";
  const active = "bg-gray-800 text-white border-gray-800";
  const inactive =
    "bg-white text-gray-600 border-gray-200 hover:border-gray-400";

  return (
    <div className="flex flex-wrap gap-3 items-center">
      <div className="flex items-center gap-1">
        <span className="text-xs text-gray-400 mr-1">Status:</span>
        {statusOpts.map((s) => (
          <button
            key={s}
            onClick={() => onStatusChange(s)}
            className={`${base} ${statusFilter === s ? active : inactive}`}
          >
            {s === "all" ? "All" : s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}
      </div>
      <div className="flex items-center gap-1">
        <span className="text-xs text-gray-400 mr-1">Severity:</span>
        {severityOpts.map((s) => (
          <button
            key={s}
            onClick={() => onSeverityChange(s)}
            className={`${base} ${severityFilter === s ? active : inactive}`}
          >
            {s === "all" ? "All" : s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function ExceptionSummaryPanel({
  exceptions,
  onMutated,
}: ExceptionSummaryPanelProps) {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>("all");
  const [loadingIds, setLoadingIds] = useState<Set<string>>(new Set());
  const [errorIds, setErrorIds] = useState<Map<string, string>>(new Map());

  const safeExceptions = exceptions ?? [];
  const openCount = safeExceptions.filter((e) => e.status === "open").length;

  const filtered = safeExceptions.filter((ex) => {
    const statusOk = statusFilter === "all" || ex.status === statusFilter;
    const severityOk = severityFilter === "all" || ex.severity === severityFilter;
    return statusOk && severityOk;
  });

  const handleAction = useCallback(
    async (id: string, newStatus: "resolved" | "dismissed") => {
      setLoadingIds((prev) => new Set(prev).add(id));
      setErrorIds((prev) => {
        const next = new Map(prev);
        next.delete(id);
        return next;
      });
      try {
        await updateExceptionStatus(id, newStatus);
        onMutated();
      } catch (err: unknown) {
        const msg =
          err instanceof Error ? err.message : "Failed to update exception.";
        setErrorIds((prev) => new Map(prev).set(id, msg));
      } finally {
        setLoadingIds((prev) => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
      }
    },
    [onMutated]
  );

  return (
    <section>
      {/* Header */}
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <h2 className="text-base font-semibold text-gray-800">
          Exceptions
          <span className="ml-2 text-gray-400 font-normal text-sm">
            ({safeExceptions.length})
          </span>
          {openCount > 0 && (
            <span className="ml-2 inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-red-100 text-red-700">
              {openCount} open
            </span>
          )}
        </h2>
      </div>

      {/* Filters — only show when there's data */}
      {safeExceptions.length > 0 && (
        <div className="mb-3">
          <FilterBar
            statusFilter={statusFilter}
            severityFilter={severityFilter}
            onStatusChange={setStatusFilter}
            onSeverityChange={setSeverityFilter}
          />
        </div>
      )}

      {/* Empty state — no exceptions at all */}
      {safeExceptions.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50 py-10 text-center text-sm text-gray-400">
          No exceptions logged for this job.
        </div>
      ) : filtered.length === 0 ? (
        // Empty state — filters exclude everything
        <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50 py-6 text-center text-sm text-gray-400">
          No exceptions match the current filters.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200 shadow-sm">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Type
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Severity
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Description
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-100">
              {filtered.map((ex) => {
                const isLoading = loadingIds.has(ex.id);
                const rowError = errorIds.get(ex.id);

                return (
                  <tr
                    key={ex.id}
                    className={`transition-colors ${
                      ex.status === "open"
                        ? "bg-red-50/30 hover:bg-red-50/60"
                        : "hover:bg-gray-50"
                    }`}
                  >
                    <td className="px-4 py-3 font-medium text-gray-800 whitespace-nowrap">
                      {formatType(ex.exception_type)}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <SeverityBadge severity={ex.severity} />
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <StatusBadge status={ex.status} />
                    </td>
                    <td className="px-4 py-3 text-gray-600 max-w-xs">
                      <div>{ex.description}</div>
                      {rowError && (
                        <div className="mt-1 text-xs text-red-600 font-medium">
                          ⚠ {rowError}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      {ex.status === "open" ? (
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => handleAction(ex.id, "resolved")}
                            disabled={isLoading}
                            className="px-2.5 py-1 rounded text-xs font-medium bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                          >
                            {isLoading ? "Saving…" : "Resolve"}
                          </button>
                          <button
                            onClick={() => handleAction(ex.id, "dismissed")}
                            disabled={isLoading}
                            className="px-2.5 py-1 rounded text-xs font-medium bg-gray-200 text-gray-700 hover:bg-gray-300 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                          >
                            {isLoading ? "Saving…" : "Dismiss"}
                          </button>
                        </div>
                      ) : (
                        <span className="text-xs text-gray-400">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
