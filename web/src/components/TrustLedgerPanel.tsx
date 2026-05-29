// web/src/components/TrustLedgerPanel.tsx
//
// Read-only Trust Ledger panel (KMZ Automatic Redline Placement). Fetches
// /api/trust-ledger for the active workspace session and renders the per-group
// proof verdict: proven / abstained / missing_proof. Route-index evidence and
// the Plan Sheet Graph (PSG) warning are shown as SEPARATE badges and never
// merged — a row can be route-index "consistent" AND carry a PSG possible-
// packet-mismatch warning at the same time (e.g. the bore_log72 case).
//
// "Proven from evidence" means the placement is justified by the recorded
// evidence chain — it is NOT a field-correctness claim and never says a
// placement "looks right" or was "verified by eye".
//
// Read-only: no overrides, no mutations, no matching/scoring/render effect.
// Default-OFF on the backend (TRUELINE_TRUST_LEDGER); the disabled response is
// handled gracefully below.

"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/apiFetch";
import { peekSessionId } from "@/lib/session";
import type {
  ProofStatus,
  RouteIndexVerdict,
  TrustLedgerResponse,
  TrustLedgerRow,
} from "@/lib/types/trustLedger";

// ── Proof palette (de-facto dark proof tones reused from MatchReviewEvidence) ─
const PROOF_TONE: Record<ProofStatus, React.CSSProperties> = {
  proven: { background: "#0e2417", border: "1px solid #2f6b3a", color: "#86efac" },
  missing_proof: { background: "#2a2206", border: "1px solid #854d0e", color: "#fcd34d" },
  abstained: {
    background: "var(--tl-bg-raised, rgba(255,255,255,0.04))",
    border: "1px solid var(--tl-border)",
    color: "var(--tl-text-muted)",
  },
};
const PROOF_LABEL: Record<ProofStatus, string> = {
  proven: "Proven from evidence",
  missing_proof: "Missing proof",
  abstained: "Abstained",
};
const PROOF_ACCENT: Record<ProofStatus, string | null> = {
  proven: "#2f6b3a",
  missing_proof: "#b8860b",
  abstained: null,
};

const VERDICT_TONE: Record<RouteIndexVerdict, React.CSSProperties> = {
  consistent: { background: "#0e2417", border: "1px solid #2f6b3a", color: "#86efac" },
  suspect: { background: "#2a2206", border: "1px solid #854d0e", color: "#fcd34d" },
  not_proven: {
    background: "var(--tl-bg-raised, rgba(255,255,255,0.04))",
    border: "1px solid var(--tl-border)",
    color: "var(--tl-text-muted)",
  },
};
const VERDICT_WORD: Record<RouteIndexVerdict, string> = {
  consistent: "Consistent",
  suspect: "Suspect",
  not_proven: "Not proven",
};

const PSG_TONE: React.CSSProperties = {
  background: "#2a2206",
  border: "1px solid #854d0e",
  color: "#fcd34d",
};

const neutralChip: React.CSSProperties = {
  background: "var(--tl-bg-raised, rgba(255,255,255,0.04))",
  border: "1px solid var(--tl-border)",
  color: "var(--tl-text-muted)",
};

const MISSING_LINK_LABEL: Record<string, string> = {
  route_geometry_absent: "Route geometry absent",
  station_range_absent: "Station range absent",
  mapping_absent: "Anchor mapping absent",
  no_candidate_or_rescue_justification: "No candidate/rescue justification",
  route_index_suspect: "Route index suspect",
  route_index_not_proven: "Route index not proven",
};

const PSG_STATUS_LABEL: Record<string, string> = {
  external_packet_mismatch_possible: "Possible packet mismatch",
  station_print_disjoint: "Station / print disjoint",
  unknown: "Unknown",
};

function titleCase(value: string): string {
  return value
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function humanizeMissingLink(s: string): string {
  return MISSING_LINK_LABEL[s] ?? titleCase(s);
}

function psgLabel(status: string | null | undefined): string {
  if (!status) return "Plan sheet warning";
  return PSG_STATUS_LABEL[status] ?? titleCase(status);
}

function fmtFt(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return `${Math.round(n).toLocaleString()} ft`;
}

function fmtScore(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toFixed(3);
}

// ── Triage filters ───────────────────────────────────────────────────────
// Read-only client-side narrowing. Buckets use ONLY existing row fields; a
// chip's count always equals its filtered rows (computed from the same source).
type FilterKey = "all" | "proven" | "abstained" | "missing_proof" | "psg_warning";

const FILTER_ORDER: FilterKey[] = ["all", "proven", "abstained", "missing_proof", "psg_warning"];

const FILTER_LABELS: Record<FilterKey, string> = {
  all: "All",
  proven: "Proven",
  abstained: "Abstained",
  missing_proof: "Missing proof",
  psg_warning: "PSG warnings",
};

function rowMatchesFilter(r: TrustLedgerRow, key: FilterKey): boolean {
  if (key === "all") return true;
  if (key === "psg_warning") return Boolean(r.psg_warning);
  return r.proof_status === key;
}

function computeFilterCounts(rows: TrustLedgerRow[]): Record<FilterKey, number> {
  const counts: Record<FilterKey, number> = {
    all: rows.length,
    proven: 0,
    abstained: 0,
    missing_proof: 0,
    psg_warning: 0,
  };
  for (const r of rows) {
    if (r.proof_status === "proven") counts.proven += 1;
    else if (r.proof_status === "abstained") counts.abstained += 1;
    else if (r.proof_status === "missing_proof") counts.missing_proof += 1;
    if (r.psg_warning) counts.psg_warning += 1;
  }
  return counts;
}

// ── Small presentational helpers ───────────────────────────────────────────
function Badge({
  label,
  word,
  tone,
}: {
  label: string;
  word: string;
  tone: React.CSSProperties;
}) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "2px 8px",
        borderRadius: 6,
        fontSize: 11,
        fontWeight: 600,
        whiteSpace: "nowrap",
        ...tone,
      }}
    >
      <span style={{ textTransform: "uppercase", letterSpacing: "0.04em", opacity: 0.85 }}>
        {label}
      </span>
      <span aria-hidden="true" style={{ opacity: 0.5 }}>
        &middot;
      </span>
      <span>{word}</span>
    </span>
  );
}

function StatPill({
  label,
  value,
  valueColor,
}: {
  label: string;
  value: number;
  valueColor?: string;
}) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "baseline",
        gap: 6,
        padding: "4px 10px",
        borderRadius: 8,
        ...neutralChip,
      }}
    >
      <span style={{ fontSize: 12 }}>{label}</span>
      <strong style={{ fontSize: 15, color: valueColor ?? "var(--tl-text)" }}>{value}</strong>
    </span>
  );
}

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ fontSize: 12, color: "var(--tl-text-muted)" }}>
      <span style={{ opacity: 0.7 }}>{label} </span>
      {children}
    </div>
  );
}

export default function TrustLedgerPanel({
  sessionId,
  projectId,
}: {
  sessionId?: string | null;
  // Optional project slug; when provided, the panel binds to the same
  // project-scoped workspace session (osp_session_id:<projectId>) the live map
  // uses. Read-only: peekSessionId never mints a session.
  projectId?: string | null;
}) {
  const [data, setData] = useState<TrustLedgerResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [sid, setSid] = useState<string | null>(sessionId ?? null);
  const [filter, setFilter] = useState<FilterKey>("all");

  useEffect(() => {
    const next = (sessionId ?? "").trim();
    // Explicit ?session_id= wins; else fall back to the project-scoped session.
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
      const url = `/api/trust-ledger?session_id=${encodeURIComponent(sid)}`;
      const res = await apiFetch(url, undefined, "trust_ledger");
      if (!res.ok) {
        setError(`Trust ledger request failed (${res.status}).`);
        setData(null);
        return;
      }
      const json = (await res.json()) as TrustLedgerResponse;
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

  const isDisabled = Boolean(data && data.success === false && data.enabled === false);
  const rows: TrustLedgerRow[] = data?.rows ?? [];
  const counts = data?.counts ?? { proven: 0, abstained: 0, missing_proof: 0 };
  const rowCount = data?.row_count ?? rows.length;
  const silentCount = data?.silent_placement_count ?? counts.missing_proof;
  const psgCount = data?.psg_warning_count ?? rows.filter((r) => r.psg_warning).length;
  const coverage = data?.coverage_sanity_summary ?? null;
  const filterCounts = computeFilterCounts(rows);
  const filteredRows = rows.filter((r) => rowMatchesFilter(r, filter));
  const enabledWithData = Boolean(data && data.enabled !== false && !isDisabled);

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
          Trust ledger
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

      {sid && error && (
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

      {sid && !error && isDisabled && (
        <div
          style={{
            padding: "12px 14px",
            borderRadius: 8,
            background: "var(--tl-bg-raised, rgba(255,255,255,0.04))",
            border: "1px solid var(--tl-border)",
            color: "var(--tl-text-muted)",
            fontSize: 13,
          }}
        >
          <strong style={{ color: "var(--tl-text)" }}>Trust Ledger is disabled.</strong> Enable{" "}
          <code>TRUELINE_TRUST_LEDGER=1</code> on the backend and rebuild the session, then refresh.
          {data?.detail && <div style={{ marginTop: 6, opacity: 0.8 }}>{data.detail}</div>}
        </div>
      )}

      {sid && !error && !isDisabled && loading && !data && (
        <p className="tl-subtle" style={{ margin: 0 }}>
          Loading…
        </p>
      )}

      {sid && !error && enabledWithData && (
        <>
          {/* Counts summary — proof verdicts + the silent-placement + PSG counts. */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
            <StatPill label="Proven" value={counts.proven} valueColor="#86efac" />
            <StatPill label="Abstained" value={counts.abstained} />
            <StatPill
              label="Missing proof"
              value={counts.missing_proof}
              valueColor={counts.missing_proof > 0 ? "#fcd34d" : undefined}
            />
            <StatPill
              label="Silent placements"
              value={silentCount}
              valueColor={silentCount > 0 ? "#fcd34d" : undefined}
            />
            <StatPill
              label="PSG warnings"
              value={psgCount}
              valueColor={psgCount > 0 ? "#fcd34d" : undefined}
            />
            <StatPill label="Rows" value={rowCount} />
          </div>

          <p className="tl-subtle" style={{ margin: "0 0 12px", fontSize: 13 }}>
            <strong style={{ color: "var(--tl-text)" }}>
              &ldquo;Proven from evidence&rdquo; means the placement is justified by the recorded
              evidence chain
            </strong>{" "}
            — route geometry, station range, anchor mapping, and a candidate or rescue
            justification. It is not a field-correctness claim. &ldquo;Missing proof&rdquo; rows
            were placed but the chain is incomplete (the silent-placement class), surfaced honestly.
          </p>

          {coverage && (
            <p className="tl-subtle" style={{ margin: "0 0 12px", fontSize: 12 }}>
              Coverage sanity: placed {coverage.placed_group_count ?? "—"} · abstained{" "}
              {coverage.abstained_group_count ?? "—"} · total {coverage.total_groups ?? "—"} ·
              same-route collisions {coverage.same_route_anchor_collision_count ?? "—"} · window
              decisions {coverage.same_route_window_decision_count ?? "—"}
              {coverage.schema_version ? ` · ${coverage.schema_version}` : ""}
            </p>
          )}

          {rows.length > 0 && (
            <div
              role="tablist"
              aria-label="Filter trust ledger rows"
              style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}
            >
              {FILTER_ORDER.map((key) => {
                const active = filter === key;
                return (
                  <button
                    key={key}
                    type="button"
                    role="tab"
                    aria-selected={active}
                    onClick={() => setFilter(key)}
                    className="tl-btn tl-btn-ghost"
                    style={{
                      fontSize: 12,
                      padding: "3px 10px",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 6,
                      ...(active
                        ? {
                            background: "var(--tl-bg-raised, rgba(255,255,255,0.10))",
                            border: "1px solid var(--tl-text-muted, #64748b)",
                            color: "var(--tl-text, #e2e8f0)",
                          }
                        : null),
                    }}
                  >
                    {FILTER_LABELS[key]}
                    <span
                      aria-hidden="true"
                      style={{
                        fontSize: 10,
                        fontWeight: 600,
                        opacity: 0.75,
                        padding: "0 5px",
                        borderRadius: 999,
                        background: active
                          ? "rgba(0,0,0,0.22)"
                          : "var(--tl-bg-raised, rgba(255,255,255,0.06))",
                      }}
                    >
                      {filterCounts[key]}
                    </span>
                  </button>
                );
              })}
            </div>
          )}

          {rows.length === 0 ? (
            <p className="tl-subtle" style={{ margin: 0 }}>
              No trust-ledger rows for this session. Rebuild the session on a backend with the trust
              ledger enabled, then refresh.
            </p>
          ) : filteredRows.length === 0 ? (
            <p className="tl-subtle" style={{ margin: 0 }}>
              No rows match the {FILTER_LABELS[filter]} filter.
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
              {filteredRows.map((r, i) => {
                const accent = PROOF_ACCENT[r.proof_status];
                const ri = r.route_index_evidence;
                const cand = r.candidate_summary;
                const mapping = r.mapping_summary;
                const geom = r.geometry_summary;
                const groupLabel =
                  r.group_idx !== null && r.group_idx !== undefined
                    ? `grp ${r.group_idx}`
                    : r.group_id ?? "grp —";
                return (
                  <li
                    key={`${r.source_file ?? "row"}-${r.group_id ?? r.group_idx ?? i}`}
                    style={{
                      padding: "10px 12px",
                      borderRadius: 8,
                      border: "1px solid var(--tl-border)",
                      borderLeft: accent
                        ? `3px solid ${accent}`
                        : "1px solid var(--tl-border)",
                      background: "var(--tl-bg-raised, rgba(255,255,255,0.02))",
                    }}
                  >
                    {/* Header line: file · group · proof status · selected route */}
                    <div
                      style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}
                    >
                      <span style={{ fontFamily: "monospace", fontSize: 13, fontWeight: 600 }}>
                        {r.source_file ?? "—"}
                      </span>
                      <span
                        title={r.group_id ? `group_id: ${r.group_id}` : undefined}
                        style={{
                          padding: "1px 8px",
                          borderRadius: 4,
                          fontSize: 11,
                          fontWeight: 500,
                          ...neutralChip,
                        }}
                      >
                        {groupLabel}
                      </span>
                      <Badge
                        label="Proof"
                        word={PROOF_LABEL[r.proof_status]}
                        tone={PROOF_TONE[r.proof_status]}
                      />
                      {r.selected_route_id ? (
                        <span
                          style={{
                            fontSize: 12,
                            color: "var(--tl-text-muted)",
                            marginLeft: "auto",
                          }}
                        >
                          → {r.selected_route_id}
                          {r.selected_route_name ? ` (${r.selected_route_name})` : ""}
                          {r.render_allowed === false ? " · not rendered" : ""}
                        </span>
                      ) : (
                        <span
                          style={{
                            fontSize: 12,
                            color: "var(--tl-text-muted)",
                            marginLeft: "auto",
                          }}
                        >
                          no route selected
                        </span>
                      )}
                    </div>

                    {/* Separate evidence badges: route-index AND (orthogonal) PSG */}
                    <div
                      style={{
                        display: "flex",
                        gap: 8,
                        alignItems: "center",
                        flexWrap: "wrap",
                        marginTop: 8,
                      }}
                    >
                      <Badge
                        label="Route index"
                        word={VERDICT_WORD[ri.verdict]}
                        tone={VERDICT_TONE[ri.verdict]}
                      />
                      {r.psg_warning && (
                        <Badge
                          label="Plan sheet"
                          word={psgLabel(r.psg_warning.status)}
                          tone={PSG_TONE}
                        />
                      )}
                      {r.psg_warning?.actionability && (
                        <span style={{ fontSize: 11, color: "var(--tl-text-muted)" }}>
                          {titleCase(r.psg_warning.actionability)}
                        </span>
                      )}
                    </div>

                    {/* Evidence chain detail */}
                    <div
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        gap: 3,
                        marginTop: 8,
                      }}
                    >
                      <Detail label="Evidence chain:">
                        {r.proof_status === "abstained"
                          ? "not applicable (not placed)"
                          : r.evidence_chain_complete
                            ? "complete"
                            : "incomplete"}
                      </Detail>

                      {r.proof_status === "abstained" && (
                        <Detail label="Abstain reason:">
                          <code style={{ fontSize: 11 }}>{r.abstain_reason ?? "not_placed"}</code>
                        </Detail>
                      )}

                      {r.missing_links.length > 0 && (
                        <div
                          style={{
                            display: "flex",
                            gap: 6,
                            flexWrap: "wrap",
                            alignItems: "center",
                          }}
                        >
                          <span style={{ fontSize: 12, color: "var(--tl-text-muted)", opacity: 0.7 }}>
                            Missing:
                          </span>
                          {r.missing_links.map((m) => (
                            <span
                              key={m}
                              style={{
                                padding: "1px 7px",
                                borderRadius: 4,
                                fontSize: 11,
                                ...PSG_TONE,
                              }}
                            >
                              {humanizeMissingLink(m)}
                            </span>
                          ))}
                        </div>
                      )}

                      <Detail label="Route-index:">
                        selected {ri.selected_route_id ?? "—"} · allowed [
                        {ri.allowed_route_ids.length ? ri.allowed_route_ids.join(", ") : "none"}] ·
                        prints [{ri.print_tokens.length ? ri.print_tokens.join(", ") : "none"}]
                      </Detail>

                      <Detail label="Candidate:">
                        score {fmtScore(cand.selected_combined_score)} ·{" "}
                        {cand.selected_in_rankings
                          ? "in rankings"
                          : cand.has_rescue_reason
                            ? "rescue justification"
                            : "no ranking / rescue"}
                        {cand.top.length > 0 && (
                          <>
                            {" "}
                            · top:{" "}
                            {cand.top
                              .map((t) => `${t.route_id ?? "—"} (${fmtScore(t.score)})`)
                              .join(", ")}
                          </>
                        )}
                      </Detail>

                      <Detail label="Mapping:">
                        {mapping.mode ?? "—"} ·{" "}
                        {mapping.mapping_present
                          ? `${fmtFt(mapping.anchored_start_ft)} – ${fmtFt(mapping.anchored_end_ft)}`
                          : "no anchor mapping"}
                      </Detail>

                      <Detail label="Geometry:">
                        route {fmtFt(geom.route_length_ft)}
                        {geom.route_in_catalog === true
                          ? " (in catalog)"
                          : geom.route_in_catalog === false
                            ? " (not in catalog)"
                            : ""}{" "}
                        · stations {fmtFt(geom.min_station_ft)} – {fmtFt(geom.max_station_ft)}
                      </Detail>

                      {r.selected_anchor_reasons.length > 0 && (
                        <Detail label="Anchors:">{r.selected_anchor_reasons.join(", ")}</Detail>
                      )}
                    </div>
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
