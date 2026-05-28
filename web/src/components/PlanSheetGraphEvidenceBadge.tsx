// web/src/components/PlanSheetGraphEvidenceBadge.tsx
//
// Read-only badge for a Match Review Queue row's `plan_sheet_graph_evidence`.
// Renders NOTHING when the field is absent or carries an unrecognized status
// (the backend already excludes the noisy within_corridor / multi_corridor_span
// statuses). Pure presentational — never mutates anything, never calls an API.

"use client";

import { useState } from "react";
import type { PlanSheetGraphEvidence } from "@/lib/types/matchReviewQueue";

const STATUS_LABEL: Record<string, string> = {
  station_print_disjoint: "Station / sheet mismatch",
  external_packet_mismatch_possible: "Possible packet mismatch",
  unknown: "Missing print evidence",
};

// Operator-readable, plain-English explanation per status.
const STATUS_EXPLANATION: Record<string, string> = {
  station_print_disjoint: "Station range does not fit the PDF plan-sheet corridor.",
  external_packet_mismatch_possible:
    "Bore log street/notes may not match the PDF sheet/street evidence.",
  unknown: "Missing or unreadable print/sheet evidence.",
};

const warnTone: React.CSSProperties = {
  background: "#2a2206",
  border: "1px solid #854d0e",
  color: "#fcd34d",
};
const infoTone: React.CSSProperties = {
  background: "var(--tl-bg-raised, rgba(255,255,255,0.04))",
  border: "1px solid var(--tl-border)",
  color: "var(--tl-text-muted)",
};

export default function PlanSheetGraphEvidenceBadge({
  evidence,
}: {
  evidence?: PlanSheetGraphEvidence | null;
}) {
  const [open, setOpen] = useState(false);

  if (!evidence || !evidence.status) return null;
  const label = STATUS_LABEL[evidence.status];
  if (!label) return null; // defensive: only render known/actionable statuses

  const isHigh = evidence.actionability === "high";
  const tone = isHigh ? warnTone : infoTone;
  const explanation = STATUS_EXPLANATION[evidence.status] ?? "";

  const detail: Array<[string, string]> = [];
  if (evidence.prints?.length) detail.push(["Prints", evidence.prints.join(", ")]);
  if (evidence.sheets?.length) detail.push(["Sheets", evidence.sheets.join(", ")]);
  if (evidence.station_range)
    detail.push([
      "Station range",
      `${evidence.station_range[0]}–${evidence.station_range[1]} ft`,
    ]);
  if (evidence.corridors?.length)
    detail.push([
      "Corridors",
      evidence.corridors.map((c) => `[${c.join(",")}]`).join(" · "),
    ]);
  if (evidence.index_streets?.length)
    detail.push(["Index streets", evidence.index_streets.join(", ")]);
  if (evidence.notes_streets?.length)
    detail.push(["Notes streets", evidence.notes_streets.join(", ")]);

  const reasons = evidence.reasons ?? [];
  const hasDetail = detail.length > 0 || reasons.length > 0;

  return (
    <div style={{ marginTop: 6 }}>
      <div
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 8,
          padding: "3px 9px",
          borderRadius: 6,
          fontSize: 11,
          fontWeight: 600,
          ...tone,
        }}
      >
        <span style={{ textTransform: "uppercase", letterSpacing: "0.04em", opacity: 0.85 }}>
          Plan Sheet Evidence
        </span>
        <span aria-hidden="true" style={{ opacity: 0.5 }}>
          &middot;
        </span>
        <span>{label}</span>
        <span
          style={{ padding: "0 6px", borderRadius: 4, fontSize: 10, background: "rgba(0,0,0,0.25)" }}
          title={isHigh ? "High actionability" : "Data-quality note"}
        >
          {isHigh ? "High" : "Data quality"}
        </span>
        {hasDetail && (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              color: "inherit",
              font: "inherit",
              padding: 0,
              opacity: 0.8,
              textDecoration: "underline",
            }}
          >
            {open ? "hide" : "details"}
          </button>
        )}
      </div>

      {explanation && (
        <div style={{ fontSize: 11, color: "var(--tl-text-muted)", margin: "4px 0 0", maxWidth: 560 }}>
          {explanation}
        </div>
      )}

      {open && hasDetail && (
        <div
          style={{
            marginTop: 6,
            padding: "8px 10px",
            borderRadius: 6,
            border: "1px solid var(--tl-border)",
            background: "var(--tl-bg-raised, rgba(255,255,255,0.03))",
            fontSize: 11,
            color: "var(--tl-text)",
            display: "flex",
            flexDirection: "column",
            gap: 6,
            maxWidth: 560,
          }}
        >
          {detail.map(([k, v]) => (
            <div key={k} style={{ display: "flex", gap: 8 }}>
              <span style={{ color: "var(--tl-text-muted)", minWidth: 96 }}>{k}</span>
              <span style={{ fontFamily: "monospace", wordBreak: "break-word" }}>{v}</span>
            </div>
          ))}
          {reasons.length > 0 && (
            <div style={{ display: "flex", gap: 8 }}>
              <span style={{ color: "var(--tl-text-muted)", minWidth: 96 }}>Reasons</span>
              <ul style={{ margin: 0, paddingLeft: 16, display: "flex", flexDirection: "column", gap: 2 }}>
                {reasons.map((r, i) => (
                  <li key={`${i}-${r.slice(0, 16)}`} style={{ fontFamily: "monospace", wordBreak: "break-word" }}>
                    {r}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
