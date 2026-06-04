// web/src/components/PdfFirstEvidencePanel.tsx
//
// Read-only render of the PDF-first engine evidence (Day-4f) attached to the
// /api/match-review-queue response under `pdf_first_evidence` (present only when the
// backend runs with TRUELINE_PDF_FIRST_ENGINE=1 + the stacked geometry/render flags).
// Shows the engine's authored bore-path overlay (pdf_path_trace, else pdf_redline) as
// a PAGE-SPACE image fetched through the gated artifact route, with a neutral review-
// grade badge and collapsed technical details. NO map drawing, NO station points, NO
// separate page. Overlay PNGs are fetched via apiFetch (Bearer auth) and shown as
// object URLs — the same authenticated-image pattern as ModernHeroMap's plan page.

"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/apiFetch";
import type {
  PdfFirstCard,
  PdfFirstEvidence,
  PdfFirstFailSafeCard,
} from "@/lib/types/matchReviewQueue";

const chip: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  padding: "1px 8px",
  borderRadius: 4,
  fontSize: 11,
  fontWeight: 600,
  background: "var(--tl-bg-raised, rgba(255,255,255,0.04))",
  border: "1px solid var(--tl-border)",
  color: "var(--tl-text-muted)",
};

function logLabel(card: { log_ids?: string[]; segment_id?: string | null }): string {
  if (card.log_ids && card.log_ids.length) return card.log_ids.join(", ");
  return card.segment_id ?? "—";
}

function Meta({ label, value }: { label: string; value: React.ReactNode }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <span style={{ fontSize: 12, color: "var(--tl-text-muted)" }}>
      <span style={{ opacity: 0.7 }}>{label}:</span> {value}
    </span>
  );
}

// Neutral, customer-safe wording (reused from the approved demo). Never surfaces raw
// engine statuses (BLOCKED / READY / route_id) in the headline — the truth lives in
// the collapsed technical details. Everything stays "review-grade", never final/READY.
function neutralBadge(card: PdfFirstCard): string | null {
  const geo = card.geo;
  if (!geo) return null;
  if (geo.geometry_status === "FRAME_WITH_DROP_TERMINAL_CANDIDATE")
    return "Fiber-drop evidence — review only";
  // Authored matchline / station-frame resolver wins (TRUELINE_MATCHLINE_FRAME_RESOLVER): a bore
  // the engine left FRAME_ONLY, lifted into one verified authored cross-sheet / single-sheet run.
  if (geo.geometry_status === "MATCHLINE_FRAME_RESOLVED")
    return "Review — authored matchline frame resolved";
  if (geo.geometry_status === "STATION_FRAME_RESOLVED")
    return "Review — authored station frame resolved";
  const ts = geo.pdf_path_trace?.trace_status ?? "";
  if (ts.includes("DASH_CHAINED") || ts === "PDF_PATH_TRACE_REVIEW")
    return "Review — parallel authored bore layers present";
  if (ts.startsWith("PDF_PATH_TRACE_")) return "Review — authored bore-path trace";
  if (geo.pdf_redline) return "Review — authored redline";
  return null;
}

// Prefer the bore-path trace overlay; fall back to the redline overlay (e.g. a drop-
// terminal candidate whose path trace is blocked). Returns a BASENAME or null.
function overlayName(card: PdfFirstCard): string | null {
  const geo = card.geo;
  if (!geo) return null;
  return geo.pdf_path_trace?.artifact_name ?? geo.pdf_redline?.artifact_name ?? null;
}

// Authenticated image: fetch the gated PNG via apiFetch (Bearer header), render it as
// an object URL, and revoke on cleanup. Mirrors ModernHeroMap's plan-page-image flow
// (a raw <img src> can't carry the Authorization header, so we blob it).
function OverlayImage({
  sessionId,
  name,
  alt,
}: {
  sessionId: string;
  name: string;
  alt: string;
}) {
  const [src, setSrc] = useState<string | null>(null);
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");

  useEffect(() => {
    // No synchronous setState here — the component is keyed by sessionId:name at the
    // call site, so a change remounts with fresh "loading" state. State only updates
    // from the async fetch callbacks below.
    let cancelled = false;
    let objectUrl: string | null = null;
    const url =
      `/api/pdf-first-evidence/${encodeURIComponent(sessionId)}/artifact` +
      `?name=${encodeURIComponent(name)}`;
    apiFetch(url, undefined, "pdf_first_artifact")
      .then((r) => (r.ok ? r.blob() : null))
      .then((b) => {
        if (cancelled) return;
        if (!b) {
          setState("error");
          return;
        }
        objectUrl = URL.createObjectURL(b);
        setSrc(objectUrl);
        setState("ok");
      })
      .catch(() => {
        if (!cancelled) setState("error");
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [sessionId, name]);

  if (state === "error") {
    return (
      <div style={{ marginTop: 8, fontSize: 12, color: "var(--tl-text-muted)" }}>
        Overlay image unavailable.
      </div>
    );
  }
  if (state === "loading" || !src) {
    return (
      <div style={{ marginTop: 8, fontSize: 12, color: "var(--tl-text-muted)" }}>
        Loading overlay…
      </div>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element -- blob object URL; next/image not applicable
    <img
      src={src}
      alt={alt}
      loading="lazy"
      style={{
        maxWidth: "100%",
        marginTop: 8,
        borderRadius: 6,
        border: "1px solid var(--tl-border)",
      }}
    />
  );
}

function SegmentCard({ card, sessionId }: { card: PdfFirstCard; sessionId: string | null }) {
  const sr = card.station_range;
  const station = sr && (sr.start || sr.end) ? `${sr.start ?? "?"} → ${sr.end ?? "?"}` : null;
  const badge = neutralBadge(card);
  const overlay = overlayName(card);
  const geo = card.geo;
  // Cross-sheet seam-stitch (default-OFF backend flag): when the stitch resolved, the card
  // carries two per-sheet segment PNGs. Render them additively below the primary crop.
  // Absent / abstained (resolved !== true) -> empty -> nothing extra renders (no regression).
  const seam = geo?.cross_sheet_seam_stitch;
  const seamSegs = seam?.resolved ? (seam.segments ?? []).filter((s) => !!s.artifact_name) : [];
  return (
    <li
      style={{
        padding: "10px 12px",
        borderRadius: 8,
        border: "1px solid var(--tl-border)",
        borderLeft: `3px solid ${card.tier === "AUTO_SELECT" ? "#3f7a4b" : "#b8860b"}`,
        background: "var(--tl-bg-raised, rgba(255,255,255,0.02))",
      }}
    >
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <span style={{ fontFamily: "monospace", fontSize: 13, fontWeight: 600 }}>{logLabel(card)}</span>
        <span style={chip}>{badge ?? card.tier ?? "—"}</span>
      </div>
      <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginTop: 6 }}>
        <Meta label="Station" value={station} />
        <Meta label="Footage" value={card.footage != null ? `${card.footage}'` : null} />
        <Meta label="Print" value={card.print} />
        <Meta label="Sheets" value={card.sheets && card.sheets.length ? card.sheets.join(" / ") : null} />
        <Meta
          label="Structures"
          value={card.end_structures && card.end_structures.length ? card.end_structures.join(", ") : null}
        />
      </div>

      {overlay && sessionId ? (
        <OverlayImage
          key={`${sessionId}:${overlay}`}
          sessionId={sessionId}
          name={overlay}
          alt={`${logLabel(card)} bore-path overlay`}
        />
      ) : (
        <div style={{ marginTop: 6, fontSize: 11, color: "var(--tl-text-muted)" }}>
          No overlay image for this item.
        </div>
      )}

      {sessionId && seamSegs.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: "var(--tl-text)" }}>
            Cross-sheet redline (page-to-page) — {seamSegs.length} segment
            {seamSegs.length === 1 ? "" : "s"}
          </div>
          {seamSegs.map((seg) => (
            <div key={seg.artifact_name} style={{ marginTop: 6 }}>
              <div style={{ fontSize: 11, color: "var(--tl-text-muted)" }}>
                Cross-sheet redline segment — Sheet {seg.sheet ?? "?"}
              </div>
              <OverlayImage
                key={`${sessionId}:${seg.artifact_name}`}
                sessionId={sessionId}
                name={seg.artifact_name!}
                alt={`${logLabel(card)} cross-sheet seam segment — sheet ${seg.sheet ?? "?"}`}
              />
            </div>
          ))}
        </div>
      )}

      {card.caveat?.text && (
        <div style={{ marginTop: 6, fontSize: 12, color: "#d4a72c" }}>{card.caveat.text}</div>
      )}

      {geo && (
        <details style={{ marginTop: 8 }}>
          <summary style={{ cursor: "pointer", fontSize: 12, color: "var(--tl-text-muted)" }}>
            Technical details
          </summary>
          <div
            style={{
              fontSize: 12,
              color: "var(--tl-text-muted)",
              marginTop: 6,
              display: "flex",
              flexDirection: "column",
              gap: 3,
            }}
          >
            <Meta label="Engine status" value={geo.pdf_path_trace?.trace_status ?? null} />
            <Meta label="Geometry" value={geo.geometry_status ?? null} />
            <Meta label="Path basis" value={geo.pdf_path_trace?.path_basis ?? null} />
            {card.caveat?.code && <Meta label="Caveat code" value={card.caveat.code} />}
            <span>Review-grade — not promoted to final/READY.</span>
          </div>
        </details>
      )}
    </li>
  );
}

// Plain-English translation of an internal fail-safe reason code for the customer view.
function friendlyReason(raw?: string | null): string | null {
  if (!raw) return null;
  if (raw.includes("GE_2_COEQUAL_OVERLAP")) return "Two or more overlapping candidates with equal evidence — engine placed nothing.";
  if (raw.includes("NO_TIEBREAKER") || raw.includes("GE_2_COEQUAL_CANDIDATES"))
    return "Several equally-supported candidates, no tiebreaker — engine placed nothing.";
  if (raw.includes("NO_AUTHORED_BOX_MATCH")) return "No authored bore-path callout matched this bore's station span.";
  if (raw.includes("no parseable stations") || raw.includes("ValueError"))
    return "Station data could not be read from the source spreadsheet.";
  return raw;
}

function FailSafeCard({ card }: { card: PdfFirstFailSafeCard }) {
  const n = card.candidates?.length ?? 0;
  return (
    <li
      style={{
        padding: "10px 12px",
        borderRadius: 8,
        border: "1px solid var(--tl-border)",
        borderLeft: "3px solid #7f1d1d",
        background: "var(--tl-bg-raised, rgba(255,255,255,0.02))",
      }}
    >
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <span style={{ fontFamily: "monospace", fontSize: 13, fontWeight: 600 }}>
          {card.log_ids && card.log_ids.length ? card.log_ids.join(", ") : "—"}
        </span>
        <span style={{ ...chip, color: "#fca5a5", borderColor: "#7f1d1d" }}>
          The engine placed nothing and drew nothing
        </span>
      </div>
      <div style={{ marginTop: 6 }}>
        <Meta label="Reason" value={friendlyReason(card.reason)} />
      </div>
      <div style={{ marginTop: 4, fontSize: 11, color: "var(--tl-text-muted)" }}>
        {n} candidate{n === 1 ? "" : "s"} shown for review only
      </div>
    </li>
  );
}

type CovGroup = "A" | "B" | "C" | "D" | "E";

const GROUP_META: { key: CovGroup; title: string }[] = [
  { key: "A", title: "Drawn PDF traces" },
  { key: "B", title: "Review / evidence overlays" },
  { key: "C", title: "Matchline / partial" },
  { key: "D", title: "Fail-safe / no draw" },
  { key: "E", title: "Needs review / more source data" },
];

// Classify a segment card into one honest coverage group from the engine's OWN fields
// (mirrors the offline coverage harness). Fail-safe cards are group D by construction.
// "Drawn" stays review-grade evidence — never a final/READY claim.
function segmentGroup(card: PdfFirstCard): CovGroup {
  const geo = card.geo;
  if (!geo) return "E";
  if (geo.geometry_status === "FRAME_WITH_DROP_TERMINAL_CANDIDATE") return "B"; // fiber-drop evidence
  if (geo.pdf_path_trace?.artifact_name) return geo.frame?.multi_sheet ? "C" : "A";
  if (geo.pdf_redline?.artifact_name) return "B";
  return "E"; // placement metadata but nothing drawable
}

export default function PdfFirstEvidencePanel({
  evidence,
  sessionId,
}: {
  evidence: PdfFirstEvidence;
  sessionId?: string | null;
}) {
  const placements = evidence.placements ?? [];
  const reviews = evidence.review_items ?? [];
  const failSafe = evidence.fail_safe ?? [];
  const total = placements.length + reviews.length + failSafe.length;
  const sid = sessionId ?? null;

  // Group every card A-E. Nothing hidden — empty groups are omitted, counts are shown.
  const grouped: Record<CovGroup, React.ReactNode[]> = { A: [], B: [], C: [], D: [], E: [] };
  [...placements, ...reviews].forEach((card, i) => {
    grouped[segmentGroup(card)].push(
      <SegmentCard key={`s-${i}-${card.segment_id ?? card.log_ids?.join(",") ?? i}`} card={card} sessionId={sid} />,
    );
  });
  failSafe.forEach((card, i) => {
    grouped.D.push(<FailSafeCard key={`f-${i}`} card={card} />);
  });

  return (
    <div
      style={{
        marginBottom: 16,
        padding: 14,
        borderRadius: 10,
        border: "1px solid var(--tl-border)",
        borderLeft: "3px solid #3f7a4b",
        background: "var(--tl-bg-raised, rgba(255,255,255,0.03))",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 12,
          flexWrap: "wrap",
          marginBottom: 8,
        }}
      >
        <h2 className="tl-h2" style={{ margin: 0 }}>
          PDF-first evidence
        </h2>
        <span style={{ fontSize: 12, color: "var(--tl-text-muted)" }}>
          {total} bore log{total === 1 ? "" : "s"} accounted for
        </span>
      </div>
      <p className="tl-subtle" style={{ margin: "0 0 12px", fontSize: 12 }}>
        Authored bore-path evidence traced from the PDF&apos;s CAD bore layers, in the plan&apos;s own
        (page-space) coordinates{evidence.source?.input ? ` · source: ${evidence.source.input}` : ""}. Read-only ·
        review-grade · grouped by outcome — none hidden.
        {evidence.status && evidence.status !== "OK" ? ` · status: ${evidence.status}` : ""}
      </p>

      {total === 0 ? (
        <p className="tl-subtle" style={{ margin: 0 }}>
          No PDF-first evidence for this session.
        </p>
      ) : (
        GROUP_META.map(({ key, title }) => {
          const items = grouped[key];
          if (!items.length) return null;
          return (
            <details key={key} open={key === "A" || key === "B" || key === "C"} style={{ marginTop: 10 }}>
              <summary style={{ cursor: "pointer", fontSize: 13, fontWeight: 600, color: "var(--tl-text)" }}>
                Group {key} — {title}
                <span
                  style={{
                    fontSize: 11,
                    background: "var(--tl-bg-raised, rgba(255,255,255,0.10))",
                    borderRadius: 10,
                    padding: "0 8px",
                    marginLeft: 6,
                  }}
                >
                  {items.length}
                </span>
              </summary>
              <ul
                style={{
                  listStyle: "none",
                  margin: "8px 0 0",
                  padding: 0,
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                }}
              >
                {items}
              </ul>
            </details>
          );
        })
      )}

      {(evidence.warnings?.length ?? 0) > 0 && (
        <p className="tl-subtle" style={{ margin: "10px 0 0", fontSize: 11, color: "var(--tl-text-muted)" }}>
          {evidence.warnings!.length} warning(s)
        </p>
      )}
    </div>
  );
}
