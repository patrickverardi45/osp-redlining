// web/src/components/office/FieldSubmissionsInboxPanel.tsx
//
// Phase 4D — compact "Field Submissions Inbox" panel for the main
// Operator Workspace (rendered at /).
//
// Sits between the top status cards and the Upload section. Read-only.
// Reuses the same getJobs/getJobById fan-out as /jobs/inbox via the
// shared `useFieldSubmissions` hook so the two views stay in sync without
// either duplicating logic.
//
// Style matches the inline-style aesthetic of RedlineMap.tsx (no Tailwind,
// inline `style={}` blocks) so it sits naturally inside the workspace.

"use client";

import Link from "next/link";

import {
  FIELD_SUBMISSIONS_FILTER_LABELS,
  formatSessionDate,
  formatSessionDateTime,
  safeCount,
  shortenSessionId,
  useFieldSubmissions,
  type InboxFilter,
} from "@/lib/office/fieldSubmissionsInbox";

// Cap rows in the compact panel so it never grows past a reasonable height
// on the workspace screen. Power users can click "View all" to open the
// full /jobs/inbox view.
const COMPACT_ROW_LIMIT = 5;

const FILTER_KEYS: InboxFilter[] = ["needs_review", "today", "week"];

export default function FieldSubmissionsInboxPanel() {
  const {
    filteredRows,
    counts,
    loading,
    error,
    partialFailures,
    filter,
    setFilter,
    refresh,
  } = useFieldSubmissions("needs_review");

  const visibleRows = filteredRows.slice(0, COMPACT_ROW_LIMIT);
  const overflow = Math.max(0, filteredRows.length - visibleRows.length);

  return (
    <div
      style={{
        background: "#ffffff",
        border: "1px solid #dbe4ee",
        borderRadius: 20,
        overflow: "hidden",
        boxShadow: "0 10px 24px rgba(15, 23, 42, 0.04)",
      }}
    >
      {/* Header — same layout as the workspace's <Section> component, but
          inlined here so this panel is independent of that helper. */}
      <div
        style={{
          padding: 18,
          borderBottom: "1px solid #e8eef5",
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <div>
          <div style={{ fontSize: 18, fontWeight: 800, color: "#0f172a" }}>
            Field Submissions Inbox
          </div>
          <div
            style={{
              marginTop: 6,
              fontSize: 13,
              color: "#64748b",
              maxWidth: 720,
            }}
          >
            Walk sessions sent in from the field, ready for office review.
            Read-only — nothing here mutates job or session state.
          </div>
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <button
            type="button"
            onClick={refresh}
            disabled={loading}
            style={{
              padding: "6px 12px",
              fontSize: 12,
              fontWeight: 700,
              borderRadius: 10,
              border: "1px solid #cfd8e3",
              background: "#ffffff",
              color: "#0f172a",
              cursor: loading ? "not-allowed" : "pointer",
              opacity: loading ? 0.6 : 1,
            }}
          >
            {loading ? "Refreshing…" : "Refresh"}
          </button>
          <Link
            href="/jobs/inbox"
            style={{
              padding: "6px 12px",
              fontSize: 12,
              fontWeight: 700,
              borderRadius: 10,
              border: "1px solid #cfd8e3",
              background: "#ffffff",
              color: "#0f172a",
              textDecoration: "none",
            }}
          >
            View all →
          </Link>
        </div>
      </div>

      {/* Filter chips */}
      <div
        style={{
          padding: "12px 18px",
          borderBottom: "1px solid #eef2f7",
          display: "flex",
          flexWrap: "wrap",
          gap: 8,
          alignItems: "center",
        }}
      >
        {FILTER_KEYS.map((key) => {
          const active = filter === key;
          return (
            <button
              key={key}
              type="button"
              onClick={() => setFilter(key)}
              style={{
                padding: "6px 12px",
                borderRadius: 999,
                fontSize: 12,
                fontWeight: 700,
                border: active ? "1px solid #0f172a" : "1px solid #dbe4ee",
                background: active ? "#0f172a" : "#ffffff",
                color: active ? "#ffffff" : "#475569",
                cursor: "pointer",
              }}
            >
              {FIELD_SUBMISSIONS_FILTER_LABELS[key]}
              <span
                style={{
                  marginLeft: 6,
                  display: "inline-block",
                  padding: "1px 7px",
                  borderRadius: 999,
                  fontSize: 10,
                  fontWeight: 800,
                  background: active ? "rgba(255,255,255,0.18)" : "#f1f5f9",
                  color: active ? "#ffffff" : "#475569",
                }}
              >
                {counts[key]}
              </span>
            </button>
          );
        })}
      </div>

      {/* Body */}
      <div style={{ padding: 18 }}>
        {loading && (
          <div
            style={{
              padding: "16px 0",
              fontSize: 13,
              color: "#94a3b8",
              textAlign: "center",
            }}
          >
            Loading field submissions…
          </div>
        )}

        {!loading && error && (
          <div
            style={{
              border: "1px solid #fecaca",
              background: "#fef2f2",
              color: "#991b1b",
              borderRadius: 12,
              padding: "10px 12px",
              fontSize: 13,
            }}
          >
            <strong>Error:</strong> {error}
          </div>
        )}

        {!loading && !error && partialFailures > 0 && (
          <div
            style={{
              border: "1px solid #fcd34d",
              background: "#fffbeb",
              color: "#92400e",
              borderRadius: 12,
              padding: "8px 12px",
              fontSize: 12,
              marginBottom: 10,
            }}
          >
            {partialFailures === 1
              ? "1 job could not be loaded; its sessions are not shown."
              : `${partialFailures} jobs could not be loaded; their sessions are not shown.`}
          </div>
        )}

        {!loading && !error && filteredRows.length === 0 && (
          <div
            style={{
              border: "1px dashed #dbe4ee",
              borderRadius: 14,
              padding: "32px 16px",
              textAlign: "center",
              color: "#94a3b8",
              fontSize: 13,
              background: "#fbfdff",
            }}
          >
            No field submissions ready for review.
          </div>
        )}

        {!loading && !error && filteredRows.length > 0 && (
          <div style={{ overflowX: "auto" }}>
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: 13,
              }}
            >
              <thead>
                <tr>
                  <Th>Status</Th>
                  <Th>Job</Th>
                  <Th>Session</Th>
                  <Th>Crew</Th>
                  <Th>Date</Th>
                  <Th align="right">Stations</Th>
                  <Th align="right">Photos</Th>
                  <Th align="right">Breadcrumbs</Th>
                  <Th align="right" />
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((row) => {
                  const session = row.session;
                  return (
                    <tr key={`${row.jobId}:${session.id}`}>
                      <Td>
                        <span
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            padding: "2px 8px",
                            borderRadius: 999,
                            fontSize: 11,
                            fontWeight: 700,
                            background: "#fef3c7",
                            color: "#92400e",
                            border: "1px solid #fcd34d",
                            whiteSpace: "nowrap",
                          }}
                        >
                          Needs Review
                        </span>
                      </Td>
                      <Td>
                        <Link
                          href={`/jobs/${row.jobId}`}
                          style={{
                            color: "#0f172a",
                            fontWeight: 700,
                            textDecoration: "none",
                          }}
                        >
                          {row.jobLabel}
                        </Link>
                      </Td>
                      <Td>
                        <span
                          style={{
                            fontFamily:
                              "ui-monospace, SFMono-Regular, monospace",
                            fontSize: 12,
                            color: "#475569",
                          }}
                        >
                          {shortenSessionId(session.id)}
                        </span>
                      </Td>
                      <Td>
                        {session.crew_name?.trim() || (
                          <span style={{ color: "#94a3b8" }}>—</span>
                        )}
                      </Td>
                      <Td>
                        <div style={{ color: "#0f172a" }}>
                          {formatSessionDate(session.started_at)}
                        </div>
                        <div
                          style={{
                            fontSize: 11,
                            color: "#94a3b8",
                            marginTop: 2,
                          }}
                        >
                          {formatSessionDateTime(session.started_at)}
                        </div>
                      </Td>
                      <Td align="right" mono>
                        {safeCount(session.station_count).toLocaleString()}
                      </Td>
                      <Td align="right" mono>
                        {safeCount(session.photo_count).toLocaleString()}
                      </Td>
                      <Td align="right" mono>
                        {safeCount(session.track_point_count).toLocaleString()}
                      </Td>
                      <Td align="right">
                        <Link
                          href={`/jobs/${row.jobId}`}
                          style={{
                            fontSize: 12,
                            fontWeight: 700,
                            color: "#1d4ed8",
                            textDecoration: "none",
                            whiteSpace: "nowrap",
                          }}
                        >
                          View →
                        </Link>
                      </Td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            {overflow > 0 && (
              <div
                style={{
                  marginTop: 10,
                  fontSize: 12,
                  color: "#64748b",
                  textAlign: "right",
                }}
              >
                Showing {visibleRows.length} of {filteredRows.length}.{" "}
                <Link
                  href="/jobs/inbox"
                  style={{
                    color: "#1d4ed8",
                    fontWeight: 700,
                    textDecoration: "none",
                  }}
                >
                  View all →
                </Link>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Small inline cell helpers ────────────────────────────────────────────────
// Defined locally to avoid pulling another component into a tight panel; keeps
// styling consistent with the rest of the inline-style workspace.

function Th({
  children,
  align,
}: {
  children?: React.ReactNode;
  align?: "left" | "right";
}) {
  return (
    <th
      style={{
        textAlign: align === "right" ? "right" : "left",
        padding: "8px 10px",
        borderBottom: "1px solid #e2e8f0",
        fontSize: 11,
        fontWeight: 700,
        textTransform: "uppercase",
        letterSpacing: 0.04,
        color: "#64748b",
        whiteSpace: "nowrap",
      }}
    >
      {children}
    </th>
  );
}

function Td({
  children,
  align,
  mono,
}: {
  children?: React.ReactNode;
  align?: "left" | "right";
  mono?: boolean;
}) {
  return (
    <td
      style={{
        textAlign: align === "right" ? "right" : "left",
        padding: "10px 10px",
        borderBottom: "1px solid #eef2f7",
        verticalAlign: "top",
        color: "#0f172a",
        fontVariantNumeric: mono ? "tabular-nums" : undefined,
      }}
    >
      {children}
    </td>
  );
}
