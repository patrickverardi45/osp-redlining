// web/src/components/MatchReviewQueuePanel.tsx
//
// Read-only Match Review Queue panel. Fetches /api/match-review-queue for the
// active workspace session and renders a compact list of review rows. The
// Plan Sheet Graph precision-evidence badge renders only on rows that carry it
// (backend-gated). Read-only: no overrides, no mutations, no route behavior.

"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/apiFetch";
import { peekSessionId } from "@/lib/session";
import PlanSheetGraphEvidenceBadge from "@/components/PlanSheetGraphEvidenceBadge";
import type {
  MatchReviewQueueResponse,
  MatchReviewRow,
} from "@/lib/types/matchReviewQueue";

const lowTone: React.CSSProperties = {
  background: "var(--tl-bg-raised, rgba(255,255,255,0.04))",
  border: "1px solid var(--tl-border)",
  color: "var(--tl-text-muted)",
};
const PRIORITY_TONE: Record<string, React.CSSProperties> = {
  high: { background: "#2a1212", border: "1px solid #7f1d1d", color: "#fca5a5" },
  medium: { background: "#1f1a06", border: "1px solid #854d0e", color: "#fcd34d" },
  low: lowTone,
};

export default function MatchReviewQueuePanel({
  sessionId,
}: {
  sessionId?: string | null;
}) {
  const [data, setData] = useState<MatchReviewQueueResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [sid, setSid] = useState<string | null>(sessionId ?? null);

  useEffect(() => {
    const next = (sessionId ?? "").trim();
    setSid(next ? next : peekSessionId());
  }, [sessionId]);

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
          <p className="tl-subtle" style={{ margin: "0 0 12px", fontSize: 13 }}>
            {data?.row_count ?? 0} rows &middot; {withEvidence} with plan-sheet evidence
            {withEvidence === 0 &&
              " · the plan-sheet evidence field is backend-gated (TRUELINE_MRQ_PLAN_SHEET_GRAPH_EVIDENCE); enable it to populate"}
          </p>

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
                const tone = PRIORITY_TONE[r.priority] ?? lowTone;
                return (
                  <li
                    key={`${r.source_file ?? "row"}-${r.group_id ?? i}`}
                    style={{
                      padding: "10px 12px",
                      borderRadius: 8,
                      border: "1px solid var(--tl-border)",
                      background: "var(--tl-bg-raised, rgba(255,255,255,0.02))",
                    }}
                  >
                    <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                      <span style={{ fontFamily: "monospace", fontSize: 13, fontWeight: 600 }}>
                        {r.source_file ?? "—"}
                      </span>
                      <span
                        style={{
                          padding: "1px 8px",
                          borderRadius: 4,
                          fontSize: 11,
                          fontWeight: 600,
                          ...tone,
                        }}
                      >
                        {r.priority}
                      </span>
                      <span style={{ fontSize: 12, color: "var(--tl-text-muted)" }}>{r.status}</span>
                      {r.selected_route_id && (
                        <span style={{ fontSize: 12, color: "var(--tl-text-muted)", marginLeft: "auto" }}>
                          → {r.selected_route_id}
                          {r.render_allowed === false ? " (not rendered)" : ""}
                        </span>
                      )}
                    </div>
                    <PlanSheetGraphEvidenceBadge evidence={r.plan_sheet_graph_evidence} />
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
