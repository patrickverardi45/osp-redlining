// web/src/app/jobs/inbox/page.tsx
//
// Phase 4D: Field Submissions Inbox — full-page view.
//
// The actual inbox-data plumbing lives in the shared hook
// `useFieldSubmissions` (web/src/lib/office/fieldSubmissionsInbox.ts) so this
// page and the compact panel on the main Operator Workspace stay in sync
// without duplicating the getJobs / getJobById fan-out.
//
// This page does NOT mutate session state. It does not approve, reject, or
// otherwise change anything. It is a visibility-only view.
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

const FILTER_KEYS: InboxFilter[] = ["needs_review", "today", "week"];

export default function FieldSubmissionsInboxPage() {
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

  return (
    <div className="tl-page">
      <div className="tl-page-inner-wide" style={{ display: "grid", gap: 22 }}>
        {/* Breadcrumb */}
        <nav
          style={{ fontSize: 13, color: "var(--tl-text-muted)" }}
        >
          <Link href="/jobs" className="tl-link">
            Jobs
          </Link>
          <span style={{ margin: "0 8px", color: "var(--tl-text-faint)" }}>
            /
          </span>
          <span style={{ color: "var(--tl-text)" }}>
            Field Submissions Inbox
          </span>
        </nav>

        <div>
          <div className="tl-eyebrow">TrueLine · Field</div>
          <h1 className="tl-h1" style={{ margin: "8px 0 6px" }}>
            Field Submissions Inbox
          </h1>
          <p className="tl-subtle" style={{ margin: 0 }}>
            Walk sessions sent in from the field, ready for office review.
            Read-only — nothing here mutates job or session state.
          </p>
        </div>

        {/* Filter chips */}
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            alignItems: "center",
            gap: 8,
          }}
        >
          {FILTER_KEYS.map((key) => {
            const active = filter === key;
            return (
              <button
                key={key}
                type="button"
                onClick={() => setFilter(key)}
                className={
                  active ? "tl-btn tl-btn-toggle-active" : "tl-btn tl-btn-ghost"
                }
                style={{
                  borderRadius: 999,
                  fontSize: 12,
                  padding: "6px 12px",
                }}
              >
                {FIELD_SUBMISSIONS_FILTER_LABELS[key]}
                <span
                  style={{
                    marginLeft: 8,
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    borderRadius: 999,
                    padding: "0 6px",
                    fontSize: 10,
                    fontWeight: 700,
                    background: active
                      ? "rgba(11,15,23,0.25)"
                      : "var(--tl-bg-grid)",
                    color: active
                      ? "var(--tl-accent-ink)"
                      : "var(--tl-text-muted)",
                    border: active
                      ? "1px solid rgba(11,15,23,0.25)"
                      : "1px solid var(--tl-border)",
                  }}
                >
                  {counts[key]}
                </span>
              </button>
            );
          })}
          <div style={{ marginLeft: "auto" }}>
            <button
              type="button"
              onClick={refresh}
              disabled={loading}
              className="tl-btn tl-btn-ghost"
              style={{
                fontSize: 12,
                padding: "6px 12px",
                opacity: loading ? 0.6 : 1,
                cursor: loading ? "not-allowed" : "pointer",
              }}
            >
              {loading ? "Refreshing…" : "Refresh"}
            </button>
          </div>
        </div>

        {/* Loading */}
        {loading && (
          <div
            className="tl-card tl-card-padded"
            style={{ textAlign: "center" }}
          >
            <span className="tl-subtle">Loading field submissions…</span>
          </div>
        )}

        {/* Hard error */}
        {!loading && error && (
          <div>
            <div
              className="tl-card tl-card-padded"
              style={{
                borderColor: "var(--tl-red-border)",
                background: "var(--tl-surface)",
                color: "#fee2e2",
              }}
            >
              <span style={{ fontWeight: 700 }}>
                Error loading field submissions:
              </span>{" "}
              {error}
            </div>
            <button
              onClick={refresh}
              className="tl-btn tl-btn-primary"
              style={{ marginTop: 12 }}
            >
              Retry
            </button>
          </div>
        )}

        {/* Soft / partial failures */}
        {!loading && !error && partialFailures > 0 && (
          <div
            className="tl-card"
            style={{
              padding: "10px 14px",
              borderColor: "var(--tl-amber-border)",
              background: "var(--tl-surface)",
              color: "#fde68a",
              fontSize: 12,
            }}
          >
            {partialFailures === 1
              ? "1 job could not be loaded; its sessions are not shown."
              : `${partialFailures} jobs could not be loaded; their sessions are not shown.`}
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && filteredRows.length === 0 && (
          <div
            className="tl-card"
            style={{
              border: "1px dashed var(--tl-border-strong)",
              padding: "56px 18px",
              textAlign: "center",
              color: "var(--tl-text-faint)",
              fontSize: 13,
            }}
          >
            No field submissions ready for review.
          </div>
        )}

        {/* Inbox rows */}
        {!loading && !error && filteredRows.length > 0 && (
          <div className="tl-table-wrap" style={{ overflowX: "auto" }}>
            <table className="tl-table">
              <thead>
                <tr>
                  <th>Status</th>
                  <th>Job</th>
                  <th>Session</th>
                  <th>Crew</th>
                  <th>Date</th>
                  <th style={{ textAlign: "right" }}>Stations</th>
                  <th style={{ textAlign: "right" }}>Photos</th>
                  <th style={{ textAlign: "right" }}>Breadcrumbs</th>
                  <th style={{ textAlign: "right" }}></th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((row) => {
                  const session = row.session;
                  return (
                    <tr key={`${row.jobId}:${session.id}`}>
                      <td style={{ whiteSpace: "nowrap" }}>
                        <span className="tl-pill tl-pill-warn">
                          Needs Review
                        </span>
                      </td>
                      <td>
                        <Link
                          href={`/jobs/${row.jobId}?session=${encodeURIComponent(session.id)}`}
                          className="tl-link"
                          style={{ fontWeight: 600 }}
                        >
                          {row.jobLabel}
                        </Link>
                      </td>
                      <td
                        style={{
                          fontFamily:
                            "ui-monospace, SFMono-Regular, Menlo, monospace",
                          fontSize: 12,
                          whiteSpace: "nowrap",
                          color: "var(--tl-text-muted)",
                        }}
                      >
                        {shortenSessionId(session.id)}
                      </td>
                      <td>
                        {session.crew_name?.trim() || (
                          <span style={{ color: "var(--tl-text-faint)" }}>
                            —
                          </span>
                        )}
                      </td>
                      <td style={{ whiteSpace: "nowrap" }}>
                        <div style={{ color: "var(--tl-text)" }}>
                          {formatSessionDate(session.started_at)}
                        </div>
                        <div
                          style={{
                            fontSize: 11,
                            color: "var(--tl-text-faint)",
                          }}
                        >
                          {formatSessionDateTime(session.started_at)}
                        </div>
                      </td>
                      <td
                        style={{
                          textAlign: "right",
                          fontVariantNumeric: "tabular-nums",
                        }}
                      >
                        {safeCount(session.station_count).toLocaleString()}
                      </td>
                      <td
                        style={{
                          textAlign: "right",
                          fontVariantNumeric: "tabular-nums",
                        }}
                      >
                        {safeCount(session.photo_count).toLocaleString()}
                      </td>
                      <td
                        style={{
                          textAlign: "right",
                          fontVariantNumeric: "tabular-nums",
                        }}
                      >
                        {safeCount(
                          session.track_point_count,
                        ).toLocaleString()}
                      </td>
                      <td
                        style={{ textAlign: "right", whiteSpace: "nowrap" }}
                      >
                        <Link
                          href={`/jobs/${row.jobId}?session=${encodeURIComponent(session.id)}`}
                          className="tl-link"
                          style={{ fontSize: 12, fontWeight: 600 }}
                        >
                          View Session →
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
