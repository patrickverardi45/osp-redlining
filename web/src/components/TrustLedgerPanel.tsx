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

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
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
  // missing_proof is the dangerous "silent placement" class — red accent so
  // these rows stand out immediately among proven/abstained rows.
  missing_proof: "#ef4444",
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

// Operator-readable abstain reasons. The backend stores machine codes
// (stopped_at / abstain reason); we surface a plain-English version and keep the
// raw code in a tooltip. Never invents new meaning — just relabels known codes.
const ABSTAIN_REASON_LABEL: Record<string, string> = {
  not_placed: "Not placed",
  same_route_anchor_collision: "Same-route collision — another bore log owns this route window",
  abstained_location_evidence_mismatch:
    "Location evidence mismatch — notes street not in the print index",
  abstained_post_v2_collision: "Post-rescue collision — re-arbitrated; this group abstained",
  render_gate_blocked: "Render gate blocked",
};

function humanizeAbstainReason(raw: string | null | undefined): string {
  const s = String(raw ?? "").trim();
  if (!s) return "Not placed";
  if (ABSTAIN_REASON_LABEL[s]) return ABSTAIN_REASON_LABEL[s];
  if (s.startsWith("render_blocked:")) {
    const rest = s.slice("render_blocked:".length).trim();
    return `Render blocked${rest ? ` — ${rest}` : ""}`;
  }
  return titleCase(s);
}

function fmtFt(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return `${Math.round(n).toLocaleString()} ft`;
}

function fmtScore(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toFixed(3);
}

// Normalize a source_file for ?focus= row matching — mirrors ModernHeroMap's
// focusSourceKey so "bore_log4", "bore_log4.xlsx", and "uploads/bore_log4.XLSX"
// all resolve to the same key.
function sourceKey(value: string | null | undefined): string {
  const lowered = String(value ?? "").trim().toLowerCase();
  if (!lowered) return "";
  const base = lowered.split(/[\\/]/).pop() ?? lowered;
  return base.replace(/\.(xlsx|xls|csv)$/, "");
}

// Honest one-line review note for the copied summary — status-dependent, never
// claims field-correctness. PSG is mentioned only as a separate follow-up.
function reviewNote(r: TrustLedgerRow): string {
  const psgNote = r.psg_warning ? " PSG warning should be reviewed separately." : "";
  if (r.proof_status === "proven") {
    return `Placement has a complete evidence chain.${psgNote}`.trim();
  }
  if (r.proof_status === "missing_proof") {
    return `Placed but the proof chain is incomplete (silent placement); review the missing links.${psgNote}`.trim();
  }
  return `Not placed; proof was insufficient or conflicting.${psgNote}`.trim();
}

// Plain-text evidence summary for one row — for QA notes, office review, closeout
// discussion, or debugging. Honest language only; route-index and PSG kept as
// SEPARATE lines (never merged); no "correct"/"looks right" claims. Uses only the
// existing row payload.
function buildEvidenceSummary(r: TrustLedgerRow): string {
  const ri = r.route_index_evidence;
  const lines: string[] = [];

  lines.push(`Source file: ${r.source_file ?? "—"}`);

  const groupLabel =
    r.group_idx !== null && r.group_idx !== undefined
      ? `grp ${r.group_idx}`
      : r.group_id ?? null;
  if (groupLabel) lines.push(`Group: ${groupLabel}`);

  lines.push(`Proof status: ${PROOF_LABEL[r.proof_status]}`);

  if (r.selected_route_id) {
    const name = r.selected_route_name ? ` (${r.selected_route_name})` : "";
    const notRendered = r.render_allowed === false ? " [not rendered]" : "";
    lines.push(`Selected route: ${r.selected_route_id}${name}${notRendered}`);
  } else {
    lines.push("Selected route: none");
  }

  const allowed = ri.allowed_route_ids.length ? ri.allowed_route_ids.join(", ") : "none";
  const prints = ri.print_tokens.length ? ri.print_tokens.join(", ") : "none";
  lines.push(
    `Route-index: ${VERDICT_WORD[ri.verdict]} — allowed routes ${allowed}; prints ${prints}`,
  );

  if (r.psg_warning) {
    const act = r.psg_warning.actionability ? ` (${r.psg_warning.actionability})` : "";
    lines.push(`PSG warning: ${psgLabel(r.psg_warning.status)}${act}`);
  } else {
    lines.push("PSG warning: none");
  }

  lines.push(
    `Mapping: ${
      r.mapping_summary.mapping_present
        ? `anchored ${fmtFt(r.mapping_summary.anchored_start_ft)} – ${fmtFt(
            r.mapping_summary.anchored_end_ft,
          )}`
        : "no anchor mapping"
    }`,
  );

  lines.push(
    `Geometry: route ${fmtFt(r.geometry_summary.route_length_ft)}; stations ${fmtFt(
      r.geometry_summary.min_station_ft,
    )} – ${fmtFt(r.geometry_summary.max_station_ft)}`,
  );

  lines.push(`Candidate score: ${fmtScore(r.candidate_summary.selected_combined_score)}`);

  lines.push(
    `Abstain reason: ${
      r.proof_status === "abstained" ? humanizeAbstainReason(r.abstain_reason) : "none"
    }`,
  );

  lines.push(
    `Missing links: ${
      r.missing_links.length ? r.missing_links.map(humanizeMissingLink).join(", ") : "none"
    }`,
  );

  lines.push(`Review note: ${reviewNote(r)}`);

  return lines.join("\n");
}

// ── CSV / JSON export (client-side, read-only) ─────────────────────────────
// Column values reuse the same honest helpers as the on-screen rows; route-index
// and PSG are SEPARATE columns (never merged). No "correct"/"looks right" text.
function csvNum(n: number | null | undefined): string {
  return n === null || n === undefined || Number.isNaN(n) ? "" : String(n);
}

function csvBool(b: boolean | null | undefined): string {
  return b === null || b === undefined ? "" : String(b);
}

function csvCell(value: string): string {
  return /[",\r\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

const CSV_COLUMNS: ReadonlyArray<{ key: string; get: (r: TrustLedgerRow) => string }> = [
  { key: "source_file", get: (r) => r.source_file ?? "" },
  { key: "group_id", get: (r) => r.group_id ?? "" },
  {
    key: "group_idx",
    get: (r) => (r.group_idx === null || r.group_idx === undefined ? "" : String(r.group_idx)),
  },
  { key: "proof_status", get: (r) => PROOF_LABEL[r.proof_status] },
  { key: "evidence_chain_complete", get: (r) => csvBool(r.evidence_chain_complete) },
  { key: "selected_route_id", get: (r) => r.selected_route_id ?? "" },
  { key: "selected_route_name", get: (r) => r.selected_route_name ?? "" },
  { key: "render_allowed", get: (r) => csvBool(r.render_allowed) },
  { key: "route_index_verdict", get: (r) => VERDICT_WORD[r.route_index_evidence.verdict] },
  { key: "allowed_route_ids", get: (r) => r.route_index_evidence.allowed_route_ids.join("; ") },
  { key: "print_tokens", get: (r) => r.route_index_evidence.print_tokens.join("; ") },
  { key: "psg_warning_status", get: (r) => (r.psg_warning ? psgLabel(r.psg_warning.status) : "none") },
  { key: "psg_actionability", get: (r) => r.psg_warning?.actionability ?? "" },
  { key: "candidate_score", get: (r) => csvNum(r.candidate_summary.selected_combined_score) },
  {
    key: "candidate_justification",
    get: (r) =>
      r.candidate_summary.selected_in_rankings
        ? "in_rankings"
        : r.candidate_summary.has_rescue_reason
          ? "rescue"
          : "none",
  },
  { key: "mapping_mode", get: (r) => r.mapping_summary.mode ?? "" },
  { key: "mapping_anchored_start_ft", get: (r) => csvNum(r.mapping_summary.anchored_start_ft) },
  { key: "mapping_anchored_end_ft", get: (r) => csvNum(r.mapping_summary.anchored_end_ft) },
  { key: "mapping_anchor_offset_ft", get: (r) => csvNum(r.mapping_summary.anchor_offset_ft) },
  { key: "route_length_ft", get: (r) => csvNum(r.geometry_summary.route_length_ft) },
  { key: "route_in_catalog", get: (r) => csvBool(r.geometry_summary.route_in_catalog) },
  { key: "min_station_ft", get: (r) => csvNum(r.geometry_summary.min_station_ft) },
  { key: "max_station_ft", get: (r) => csvNum(r.geometry_summary.max_station_ft) },
  {
    key: "abstain_reason",
    get: (r) => (r.proof_status === "abstained" ? humanizeAbstainReason(r.abstain_reason) : "none"),
  },
  {
    key: "missing_links",
    get: (r) =>
      r.missing_links.length ? r.missing_links.map(humanizeMissingLink).join("; ") : "none",
  },
  { key: "review_note", get: (r) => reviewNote(r) },
];

function buildLedgerCsv(rows: TrustLedgerRow[]): string {
  const header = CSV_COLUMNS.map((c) => csvCell(c.key)).join(",");
  const body = rows.map((r) => CSV_COLUMNS.map((c) => csvCell(c.get(r))).join(","));
  return [header, ...body].join("\r\n");
}

// UTF-8 BOM so spreadsheet apps (Excel) render unicode (em-dashes) correctly.
const CSV_BOM = String.fromCharCode(0xfeff);

function downloadTextFile(filename: string, mime: string, content: string): void {
  try {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch {
    // best-effort: no-op if the browser blocks the download
  }
}

// ── Triage filters ───────────────────────────────────────────────────────
// Read-only client-side narrowing. Buckets use ONLY existing row fields; a
// chip's count always equals its filtered rows (computed from the same source).
type FilterKey =
  | "all"
  | "proven"
  | "abstained"
  | "missing_proof"
  | "psg_warning"
  | "map_review";

// Base filters always shown. "map_review" is appended at render time ONLY when a
// projectId is present (otherwise no row can deep-link to the map).
const FILTER_ORDER: FilterKey[] = ["all", "proven", "abstained", "missing_proof", "psg_warning"];

const FILTER_LABELS: Record<FilterKey, string> = {
  all: "All",
  proven: "Proven",
  abstained: "Abstained",
  missing_proof: "Missing proof",
  psg_warning: "PSG warnings",
  map_review: "Map review",
};

// A row can be reviewed on the map iff it was placed (not abstained) and we know
// the projectId + source_file needed to build the focus deep-link. Mirrors the
// per-row "View on map" gate exactly, so the chip count equals the visible links.
function rowHasMapReview(r: TrustLedgerRow, projectId?: string | null): boolean {
  return r.proof_status !== "abstained" && Boolean(projectId) && Boolean(r.source_file);
}

function rowMatchesFilter(
  r: TrustLedgerRow,
  key: FilterKey,
  projectId?: string | null,
): boolean {
  if (key === "all") return true;
  if (key === "psg_warning") return Boolean(r.psg_warning);
  if (key === "map_review") return rowHasMapReview(r, projectId);
  return r.proof_status === key;
}

function computeFilterCounts(
  rows: TrustLedgerRow[],
  projectId?: string | null,
): Record<FilterKey, number> {
  const counts: Record<FilterKey, number> = {
    all: rows.length,
    proven: 0,
    abstained: 0,
    missing_proof: 0,
    psg_warning: 0,
    map_review: 0,
  };
  for (const r of rows) {
    if (r.proof_status === "proven") counts.proven += 1;
    else if (r.proof_status === "abstained") counts.abstained += 1;
    else if (r.proof_status === "missing_proof") counts.missing_proof += 1;
    if (r.psg_warning) counts.psg_warning += 1;
    if (rowHasMapReview(r, projectId)) counts.map_review += 1;
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

function LegendItem({ dot, term, def }: { dot: string; term: string; def: string }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "baseline", gap: 6, maxWidth: 380 }}>
      <span
        aria-hidden="true"
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: dot,
          flexShrink: 0,
          alignSelf: "center",
        }}
      />
      <span>
        <strong style={{ color: "var(--tl-text)" }}>{term}</strong> — {def}
      </span>
    </span>
  );
}

export default function TrustLedgerPanel({
  sessionId,
  projectId,
  focusedRow,
}: {
  sessionId?: string | null;
  // Optional project slug; when provided, the panel binds to the same
  // project-scoped workspace session (osp_session_id:<projectId>) the live map
  // uses. Read-only: peekSessionId never mints a session.
  projectId?: string | null;
  // Optional ?focus=<source_file> carried back from focused map review. When set,
  // the panel scrolls to + highlights the matching row(s). Read-only.
  focusedRow?: string | null;
}) {
  const [data, setData] = useState<TrustLedgerResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [sid, setSid] = useState<string | null>(sessionId ?? null);
  const [filter, setFilter] = useState<FilterKey>("all");
  const ulRef = useRef<HTMLUListElement | null>(null);
  // Per-row "Copy evidence summary" feedback: { id, ok } for the row just acted on.
  const [copyState, setCopyState] = useState<{ id: string; ok: boolean } | null>(null);

  const handleCopySummary = useCallback(async (rowId: string, row: TrustLedgerRow) => {
    const text = buildEvidenceSummary(row);
    let ok = false;
    try {
      if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        ok = true;
      }
    } catch {
      ok = false;
    }
    setCopyState({ id: rowId, ok });
    window.setTimeout(() => {
      setCopyState((cur) => (cur && cur.id === rowId ? null : cur));
    }, 1800);
  }, []);

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
  const filterCounts = computeFilterCounts(rows, projectId);
  const filteredRows = rows.filter((r) => rowMatchesFilter(r, filter, projectId));
  const enabledWithData = Boolean(data && data.enabled !== false && !isDisabled);
  // Danger = a route was placed without a complete proof chain. PSG warnings are
  // a SEPARATE (orthogonal) signal and do NOT flip the strip to danger.
  const hasDanger = counts.missing_proof > 0 || silentCount > 0;
  // "Map review" chip only when projectId is known (else no row can deep-link).
  const filterOrder: FilterKey[] = projectId ? [...FILTER_ORDER, "map_review"] : FILTER_ORDER;

  // ── Return-to-row focus (carried back from focused map review) ─────────────
  // Read-only: scroll to + highlight the row(s) whose source_file matches the
  // ?focus= param the map focus banner appended. A bore log with multiple groups
  // yields multiple rows for one source_file; all are highlighted.
  const focusedKey = sourceKey(focusedRow);
  const hasRowFocus = focusedKey.length > 0;
  const focusRowExists =
    hasRowFocus && rows.some((r) => sourceKey(r.source_file) === focusedKey);
  const focusRowVisible =
    hasRowFocus && filteredRows.some((r) => sourceKey(r.source_file) === focusedKey);
  // "Clear row focus" drops ?focus=, preserving projectId + session_id when present.
  const clearCtx = new URLSearchParams();
  if (projectId) clearCtx.set("projectId", projectId);
  if (sessionId) clearCtx.set("session_id", sessionId);
  const clearRowFocusHref = clearCtx.toString()
    ? `/trust-ledger?${clearCtx.toString()}`
    : "/trust-ledger";

  useEffect(() => {
    if (!focusedKey || !focusRowVisible) return;
    const el = ulRef.current?.querySelector('[data-tl-focus-row="1"]');
    if (el && typeof el.scrollIntoView === "function") {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [focusedKey, focusRowVisible]);

  // Client-side export of the CURRENT filtered rows (read-only). Whatever the
  // active filter shows is what exports; the toolbar labels the count + filter.
  const exportBaseName = `trust-ledger_${filter}_${(sid ?? "session").slice(0, 12)}`;
  const handleExportCsv = () => {
    if (filteredRows.length === 0) return;
    // UTF-8 BOM so Excel renders em-dashes / unicode correctly.
    downloadTextFile(
      `${exportBaseName}.csv`,
      "text/csv;charset=utf-8",
      CSV_BOM + buildLedgerCsv(filteredRows),
    );
  };
  const handleExportJson = () => {
    if (filteredRows.length === 0) return;
    const payload = {
      schema_version: data?.schema_version ?? "trust-ledger-1",
      session_id: sid,
      exported_filter: filter,
      row_count: filteredRows.length,
      counts: data?.counts ?? null,
      rows: filteredRows,
    };
    downloadTextFile(
      `${exportBaseName}.json`,
      "application/json",
      JSON.stringify(payload, null, 2),
    );
  };

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
          {/* Returned-from-map-review banner — shown only when a ?focus= row is
              carried back. Scrolls to + highlights the matching row below. */}
          {hasRowFocus && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                flexWrap: "wrap",
                padding: "8px 12px",
                borderRadius: 8,
                marginBottom: 12,
                background: "var(--tl-bg-raised, rgba(255,255,255,0.04))",
                border: "1px dashed var(--tl-text-muted, #64748b)",
                fontSize: 12,
                color: "var(--tl-text-muted)",
              }}
            >
              <span className="tl-pill tl-pill-info">Returned from map review</span>
              <span>
                Focused row:{" "}
                <span
                  style={{
                    fontFamily: "monospace",
                    color: "var(--tl-text)",
                    fontWeight: 600,
                  }}
                >
                  {focusedRow}
                </span>
              </span>
              {!focusRowExists && (
                <span style={{ color: "#fca5a5" }}>
                  not found in this session&rsquo;s ledger
                </span>
              )}
              {focusRowExists && !focusRowVisible && (
                <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                  <span>hidden by the {FILTER_LABELS[filter]} filter</span>
                  <button
                    type="button"
                    className="tl-btn tl-btn-ghost"
                    style={{ fontSize: 11, padding: "1px 8px" }}
                    onClick={() => setFilter("all")}
                  >
                    Show all
                  </button>
                </span>
              )}
              <Link
                href={clearRowFocusHref}
                className="tl-link"
                style={{ fontSize: 12, marginLeft: "auto", whiteSpace: "nowrap" }}
              >
                Clear row focus
              </Link>
            </div>
          )}

          {/* Review status strip — the at-a-glance verdict. Green when every
               placement carries a complete proof chain; red when any placement
               is missing proof (the silent-placement danger class). */}
          <div
            role="status"
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              flexWrap: "wrap",
              padding: "10px 14px",
              borderRadius: 8,
              marginBottom: 12,
              ...(hasDanger
                ? { background: "#2a1212", border: "1px solid #7f1d1d", color: "#fca5a5" }
                : { background: "#0e2417", border: "1px solid #2f6b3a", color: "#86efac" }),
            }}
          >
            <span
              aria-hidden="true"
              style={{
                width: 9,
                height: 9,
                borderRadius: "50%",
                background: hasDanger ? "#ef4444" : "#22c55e",
                flexShrink: 0,
              }}
            />
            <strong style={{ fontSize: 13 }}>
              {hasDanger
                ? `Review needed — ${counts.missing_proof} placement${
                    counts.missing_proof === 1 ? "" : "s"
                  } with missing proof`
                : "No silent placements — every placement carries a complete proof chain"}
            </strong>
            <span style={{ fontSize: 12, opacity: 0.85 }}>
              {counts.proven} proven · {counts.abstained} abstained · {rowCount} rows
              {psgCount > 0
                ? ` · ${psgCount} PSG warning${psgCount === 1 ? "" : "s"} to review`
                : ""}
            </span>
          </div>

          {/* Counts summary — proof verdicts + the silent-placement + PSG counts.
               Missing proof uses red (not amber) — it is the dangerous silent-
               placement class, not a mere warning. */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
            <StatPill label="Proven" value={counts.proven} valueColor="#86efac" />
            <StatPill label="Abstained" value={counts.abstained} />
            <StatPill
              label="Missing proof"
              value={counts.missing_proof}
              valueColor={counts.missing_proof > 0 ? "#fca5a5" : undefined}
            />
            <StatPill
              label="Silent placements"
              value={silentCount}
              valueColor={silentCount > 0 ? "#fca5a5" : undefined}
            />
            <StatPill
              label="PSG warnings"
              value={psgCount}
              valueColor={psgCount > 0 ? "#fcd34d" : undefined}
            />
            <StatPill label="Rows" value={rowCount} />
          </div>

          {/* Legend — honest definition of each proof status. */}
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: 14,
              marginBottom: 10,
              fontSize: 12,
              color: "var(--tl-text-muted)",
            }}
          >
            <LegendItem
              dot="#86efac"
              term="Proven from evidence"
              def="placed with a complete proof chain (route geometry, station range, anchor mapping, candidate/rescue, route-index consistent)"
            />
            <LegendItem
              dot="var(--tl-text-muted)"
              term="Abstained"
              def="not placed — proof was insufficient or conflicting"
            />
            <LegendItem
              dot="#ef4444"
              term="Missing proof"
              def="placed but the proof chain is incomplete (silent placement)"
            />
          </div>
          <p className="tl-subtle" style={{ margin: "0 0 12px", fontSize: 12 }}>
            Route-index evidence and the PSG (plan-sheet) warning are separate signals — a row can be
            route-index consistent and still carry a PSG warning. &ldquo;Proven&rdquo; is an evidence
            claim, not a field-correctness claim.
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
              {filterOrder.map((key) => {
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

          {rows.length > 0 && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                flexWrap: "wrap",
                marginBottom: 12,
              }}
            >
              <span style={{ fontSize: 12, color: "var(--tl-text-muted)" }}>
                Export {filteredRows.length} {filteredRows.length === 1 ? "row" : "rows"} (
                {FILTER_LABELS[filter]}):
              </span>
              <button
                type="button"
                className="tl-btn tl-btn-ghost"
                style={{ fontSize: 12, padding: "2px 10px" }}
                onClick={handleExportCsv}
                disabled={filteredRows.length === 0}
              >
                Export CSV
              </button>
              <button
                type="button"
                className="tl-btn tl-btn-ghost"
                style={{ fontSize: 12, padding: "2px 10px" }}
                onClick={handleExportJson}
                disabled={filteredRows.length === 0}
              >
                Export JSON
              </button>
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
                const isRowFocused =
                  hasRowFocus && sourceKey(r.source_file) === focusedKey;
                const rowId = `${r.source_file ?? "row"}-${r.group_id ?? r.group_idx ?? i}`;
                return (
                  <li
                    key={`${r.source_file ?? "row"}-${r.group_id ?? r.group_idx ?? i}`}
                    data-tl-focus-row={isRowFocused ? "1" : undefined}
                    style={{
                      padding: "10px 12px",
                      borderRadius: 8,
                      border: isRowFocused
                        ? "1px solid #f5d020"
                        : "1px solid var(--tl-border)",
                      borderLeft: accent
                        ? `3px solid ${accent}`
                        : "1px solid var(--tl-border)",
                      background: isRowFocused
                        ? "rgba(245,208,32,0.08)"
                        : "var(--tl-bg-raised, rgba(255,255,255,0.02))",
                      boxShadow: isRowFocused
                        ? "0 0 0 2px rgba(245,208,32,0.35)"
                        : undefined,
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
                          <span title={r.abstain_reason ?? "not_placed"}>
                            {humanizeAbstainReason(r.abstain_reason)}
                          </span>
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

                    {/* Row action bar — "View on map" deep-link (placed rows
                        only; abstained rows have no rendered geometry, so the link
                        is omitted) + a "Copy evidence summary" action on every row. */}
                    <div
                      style={{
                        marginTop: 10,
                        display: "flex",
                        gap: 8,
                        alignItems: "center",
                        flexWrap: "wrap",
                      }}
                    >
                      {r.proof_status !== "abstained" && projectId && r.source_file && (
                        <Link
                          href={`/projects/${projectId}?focus=${encodeURIComponent(r.source_file)}`}
                          prefetch={false}
                          className="tl-btn tl-btn-ghost"
                          style={{ fontSize: 12, padding: "2px 10px" }}
                        >
                          View on map →
                        </Link>
                      )}
                      <button
                        type="button"
                        className="tl-btn tl-btn-ghost"
                        style={{ fontSize: 12, padding: "2px 10px" }}
                        onClick={() => void handleCopySummary(rowId, r)}
                        title="Copy a plain-text evidence summary for QA / office review"
                      >
                        {copyState?.id === rowId
                          ? copyState.ok
                            ? "Copied"
                            : "Copy failed"
                          : "Copy evidence summary"}
                      </button>
                      {r.proof_status === "missing_proof" && (
                        <span style={{ fontSize: 11, color: "#fca5a5" }}>
                          Placed but proof chain incomplete — review geometry
                        </span>
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
