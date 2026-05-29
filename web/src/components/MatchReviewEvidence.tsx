// web/src/components/MatchReviewEvidence.tsx
//
// Read-only "PDF route evidence" block for a Match Review Queue row. Surfaces
// the deterministic PDF print-index dimension already returned in the row's
// `evidence_summary` and computes an expected-vs-actual route verdict:
//
//   expected route set = evidence_summary.allowed_route_ids
//                        (from the Brenham print/sheet index — the
//                         authoritative placement guide for these prints)
//   actual route       = row.selected_route_id
//   verdict            = consistent | suspect | not_proven
//
// This is ROUTE-ID / print-index evidence ONLY. It is NOT a pixel-level PDF
// proof and NOT a subjective "looks right" judgement — the map is the visual
// confirmation surface, this is the deterministic route-set comparison. Pure
// presentational: never mutates state, never calls an API, never affects
// matching / scoring / selection / rendering.

"use client";

import type { MatchReviewEvidenceSummary } from "@/lib/types/matchReviewQueue";

type VerdictKind = "consistent" | "suspect" | "not_proven";

interface Verdict {
  kind: VerdictKind;
  word: string;
  detail: string;
}

// Deterministic index-agreement verdict. Pure — same inputs, same output.
// No guessing: when the PDF print-index route set is absent, or there is no
// selected route, the verdict is explicitly "not proven".
function indexAgreementVerdict(
  selectedRouteId: string | null,
  allowedRouteIds?: string[],
): Verdict {
  const allowed = (allowedRouteIds ?? []).filter(
    (r) => typeof r === "string" && r.trim(),
  );
  if (allowed.length === 0) {
    return {
      kind: "not_proven",
      word: "Not proven",
      detail: "no PDF print-index route set available.",
    };
  }
  const selected = (selectedRouteId ?? "").trim();
  if (!selected) {
    return { kind: "not_proven", word: "Not proven", detail: "no selected route." };
  }
  if (allowed.includes(selected)) {
    return {
      kind: "consistent",
      word: "Consistent",
      detail: "selected route is in the PDF-derived expected route set.",
    };
  }
  return {
    kind: "suspect",
    word: "Suspect",
    detail: "selected route is outside the PDF-derived expected route set.",
  };
}

// Reuses the PlanSheetGraphEvidenceBadge tone language: amber for attention,
// neutral for inconclusive, plus a calm green for the reassuring case.
const VERDICT_TONE: Record<VerdictKind, React.CSSProperties> = {
  consistent: { background: "#0e2417", border: "1px solid #2f6b3a", color: "#86efac" },
  suspect: { background: "#2a2206", border: "1px solid #854d0e", color: "#fcd34d" },
  not_proven: {
    background: "var(--tl-bg-raised, rgba(255,255,255,0.04))",
    border: "1px solid var(--tl-border)",
    color: "var(--tl-text-muted)",
  },
};

function joinOrDash(values?: string[]): string {
  const out = (values ?? []).filter((v) => typeof v === "string" && v.trim());
  return out.length ? out.join(", ") : "—";
}

export default function MatchReviewEvidence({
  evidence,
  selectedRouteId,
  selectedRouteName,
}: {
  evidence: MatchReviewEvidenceSummary;
  selectedRouteId: string | null;
  selectedRouteName: string | null;
}) {
  const prints = evidence.print_tokens ?? [];
  const allowed = evidence.allowed_route_ids ?? [];
  const streetHints = evidence.street_hints ?? [];
  const notesStreets = evidence.notes_streets ?? [];
  const mismatch = Boolean(evidence.location_evidence_mismatch);
  const verdict = indexAgreementVerdict(selectedRouteId, allowed);

  const actual = (selectedRouteId ?? "").trim();
  const sourceTitle = evidence.print_sheet_index_source
    ? `Expected route set source: ${evidence.print_sheet_index_source}`
    : undefined;
  const hasStreetLine = streetHints.length > 0 || notesStreets.length > 0 || mismatch;

  return (
    <div style={{ marginTop: 8, maxWidth: 560, display: "flex", flexDirection: "column", gap: 4 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
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
            ...VERDICT_TONE[verdict.kind],
          }}
        >
          <span style={{ textTransform: "uppercase", letterSpacing: "0.04em", opacity: 0.85 }}>
            PDF route check
          </span>
          <span aria-hidden="true" style={{ opacity: 0.5 }}>
            &middot;
          </span>
          <span>{verdict.word}</span>
        </span>
        <span style={{ fontSize: 11, color: "var(--tl-text-muted)" }}>{verdict.detail}</span>
      </div>

      <div style={{ fontSize: 12, color: "var(--tl-text-muted)", lineHeight: 1.6 }}>
        <span>Prints </span>
        <code style={{ color: "var(--tl-text)" }}>{joinOrDash(prints)}</code>
        <span> · Expected </span>
        <code style={{ color: "var(--tl-text)" }} title={sourceTitle}>
          {joinOrDash(allowed)}
        </code>
        <span> · Actual </span>
        <code style={{ color: "var(--tl-text)" }}>
          {actual || "—"}
          {actual && selectedRouteName ? ` (${selectedRouteName})` : ""}
        </code>
      </div>

      {hasStreetLine && (
        <div style={{ fontSize: 11, color: "var(--tl-text-muted)" }}>
          {streetHints.length > 0 && (
            <>
              <span>Streets </span>
              <span style={{ color: "var(--tl-text)" }}>{joinOrDash(streetHints)}</span>
            </>
          )}
          {notesStreets.length > 0 && (
            <>
              {streetHints.length > 0 && <span> · </span>}
              <span>Notes </span>
              <span style={{ color: "var(--tl-text)" }}>{joinOrDash(notesStreets)}</span>
            </>
          )}
          {mismatch && (
            <>
              {(streetHints.length > 0 || notesStreets.length > 0) && <span> · </span>}
              <span style={{ color: "#fcd34d" }}>location evidence mismatch</span>
            </>
          )}
        </div>
      )}
    </div>
  );
}
