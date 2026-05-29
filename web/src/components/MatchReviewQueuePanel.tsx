// web/src/components/MatchReviewQueuePanel.tsx
//
// Read-only Match Review Queue panel. Fetches /api/match-review-queue for the
// active workspace session and renders a compact list of review rows. The
// Plan Sheet Graph precision-evidence badge renders only on rows that carry it
// (backend-gated). Read-only: no overrides, no mutations, no route behavior.

"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/apiFetch";
import { peekSessionId } from "@/lib/session";
import PlanSheetGraphEvidenceBadge from "@/components/PlanSheetGraphEvidenceBadge";
import type {
  MatchReviewQueueResponse,
  MatchReviewRow,
} from "@/lib/types/matchReviewQueue";

// Priority is sorting / context metadata, not an alarm. Render it as a quiet
// neutral chip with a small ordering dot — warning tone is reserved for the
// Plan Sheet Evidence badge so the rows that actually need review stand out.
const neutralChip: React.CSSProperties = {
  background: "var(--tl-bg-raised, rgba(255,255,255,0.04))",
  border: "1px solid var(--tl-border)",
  color: "var(--tl-text-muted)",
};
const PRIORITY_DOT: Record<string, string> = {
  high: "#d4a72c",
  medium: "#7a7f87",
  low: "#4b5563",
};

// Friendly labels for the raw pipeline status enum — operators never see
// snake_case. Unknown values fall back to Title Case.
const STATUS_LABEL: Record<string, string> = {
  placed_with_low_confidence: "Placed, low confidence",
  rescued_v4: "Auto-recovered",
  abstained: "Not placed",
  ambiguous: "Ambiguous",
  collision_resolved: "Conflict resolved",
  placed: "Placed",
  unknown: "Unknown",
};

function titleCase(value: string): string {
  return value
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function friendlyStatus(status: string): string {
  if (!status) return "—";
  return STATUS_LABEL[status] ?? titleCase(status);
}

export default function MatchReviewQueuePanel({
  sessionId,
  projectId,
}: {
  sessionId?: string | null;
  // When provided (via /match-review?projectId=<slug>), each row with a
  // source_file gets a read-only "View on map" deep-link. Omitted entirely when
  // absent — never inferred. Read-only: no effect on fetch/order/scoring.
  projectId?: string | null;
}) {
  const [data, setData] = useState<MatchReviewQueueResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [sid, setSid] = useState<string | null>(sessionId ?? null);

  useEffect(() => {
    const next = (sessionId ?? "").trim();
    // Fallback to the PROJECT-SCOPED session (osp_session_id:<projectId>) so
    // /match-review?projectId=<slug> binds to the same workspace session the
    // live map uses — ModernHeroMap loads /api/current-state via
    // appendSessionId(url, projectId). Explicit ?session_id= still wins (next).
    // projectId absent → peekSessionId(undefined) reads the global key (prior
    // behavior). Read-only: peekSessionId never mints a session.
    setSid(next ? next : peekSessionId(projectId ?? undefined));
  }, [sessionId, projectId]);

  const load = useCallback(async () => {
    if (!sid) {
      setData(null);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const url = `/api/match-review-queue?session_id=${encodeURIComponent(sid)}`;
      const res = await apiFetch(url, undefined, "match_review_queue");
      if (!res.ok) {
        setError(`Match review queue request failed (${res.status}).`);
        setData(null);
        return;
      }
      const json = (await res.json()) as MatchReviewQueueResponse;
      setData(json);
    } catch {
      setError("Network error — could not reach the server.");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [sid]);

  useEffect(() => {
    void load();
  }, [load]);

  const rows: MatchReviewRow[] = data?.rows ?? [];
  const withEvidence = rows.filter((r) => r.plan_sheet_graph_evidence).length;
  const rowCount = data?.row_count ?? rows.length;
  const otherCount = Math.max(0, rowCount - withEvidence);

  return (
    <section className="tl-card tl-card-padded">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 12,
          flexWrap: "wrap",
          marginBottom: 14,
        }}
      >
        <h2 className="tl-h2" style={{ margin: 0 }}>
          Review queue
        </h2>
        <button
          className="tl-btn tl-btn-ghost"
          style={{ fontSize: 12, padding: "4px 12px" }}
          onClick={() => void load()}
          disabled={loading || !sid}
        >
          {loading ? "Loading…" : "Refresh"}
        </button>
      </div>

      {!sid && (
        <p className="tl-subtle" style={{ margin: 0 }}>
          No active workspace session found. Open a workspace session, or append{" "}
          <code>?session_id=…</code> to this URL.
        </p>
      )}

      {error && (
        <div
          style={{
            padding: "10px 14px",
            borderRadius: 8,
            background: "#2a1212",
            border: "1px solid #7f1d1d",
            color: "#fca5a5",
            fontSize: 13,
          }}
        >
          {error}
        </div>
      )}

      {sid && !error && (
        <>
          {withEvidence > 0 ? (
            <p className="tl-subtle" style={{ margin: "0 0 12px", fontSize: 13 }}>
              <strong style={{ color: "var(--tl-text)" }}>
                {withEvidence} row{withEvidence === 1 ? "" : "s"} {withEvidence === 1 ? "has" : "have"}{" "}
                plan-sheet evidence to review.
              </strong>{" "}
              The other {otherCount} {otherCount === 1 ? "row is" : "rows are"} routing outcomes shown for
              context, not errors.
            </p>
          ) : (
            <p className="tl-subtle" style={{ margin: "0 0 12px", fontSize: 13 }}>
              No plan-sheet evidence is currently attached to this session. The {rowCount}{" "}
              {rowCount === 1 ? "row" : "rows"} below are routing outcomes shown for context, not errors.
            </p>
          )}

          {rows.length === 0 ? (
            <p className="tl-subtle" style={{ margin: 0 }}>
              Queue is empty for this session.
            </p>
          ) : (
            <ul
              style={{
                listStyle: "none",
                margin: 0,
                padding: 0,
                display: "flex",
                flexDirection: "column",
                gap: 8,
              }}
            >
              {rows.map((r, i) => {
                const ev = r.plan_sheet_graph_evidence;
                const accent = ev ? (ev.actionability === "high" ? "#b8860b" : "#6b7280") : null;
                return (
                  <li
                    key={`${r.source_file ?? "row"}-${r.group_id ?? i}`}
                    style={{
                      padding: "10px 12px",
                      borderRadius: 8,
                      border: "1px solid var(--tl-border)",
                      borderLeft: accent ? `3px solid ${accent}` : "1px solid var(--tl-border)",
                      background: "var(--tl-bg-raised, rgba(255,255,255,0.02))",
                    }}
                  >
                    <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                      <span style={{ fontFamily: "monospace", fontSize: 13, fontWeight: 600 }}>
                        {r.source_file ?? "—"}
                      </span>
                      <span
                        title={`Priority: ${titleCase(r.priority)}`}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 6,
                          padding: "1px 8px",
                          borderRadius: 4,
                          fontSize: 11,
                          fontWeight: 500,
                          ...neutralChip,
                        }}
                      >
                        <span
                          aria-hidden="true"
                          style={{
                            width: 6,
                            height: 6,
                            borderRadius: "50%",
                            background: PRIORITY_DOT[r.priority] ?? "#4b5563",
                          }}
                        />
                        {titleCase(r.priority)}
                      </span>
                      <span style={{ fontSize: 12, color: "var(--tl-text-muted)" }}>
                        {friendlyStatus(r.status)}
                      </span>
                      {r.selected_route_id && (
                        <span style={{ fontSize: 12, color: "var(--tl-text-muted)", marginLeft: "auto" }}>
                          → {r.selected_route_id}
                          {r.render_allowed === false ? " (not rendered)" : ""}
                        </span>
                      )}
                    </div>
                    <PlanSheetGraphEvidenceBadge evidence={ev} />
                    {projectId && r.source_file && (
                      <div style={{ marginTop: 8 }}>
                        <Link
                          href={`/projects/${projectId}?focus=${encodeURIComponent(r.source_file)}`}
                          prefetch={false}
                          className="tl-btn tl-btn-ghost"
                          style={{ fontSize: 12, padding: "2px 10px" }}
                        >
                          View on map →
                        </Link>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
