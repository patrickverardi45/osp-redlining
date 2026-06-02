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
        {card.surface && <span style={{ fontSize: 11, color: "var(--tl-text-muted)" }}>{card.surface}</span>}
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

      {card.caveat?.code && (
        <div style={{ marginTop: 6, fontSize: 12, color: "#d4a72c" }}>
          {card.caveat.code}
          {card.caveat.text ? ` — ${card.caveat.text}` : ""}
        </div>
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
            <span>Review-grade — not promoted to final/READY.</span>
          </div>
        </details>
      )}
    </li>
  );
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
        <Meta label="Reason" value={card.reason} />
      </div>
      <div style={{ marginTop: 4, fontSize: 11, color: "var(--tl-text-muted)" }}>
        {n} candidate{n === 1 ? "" : "s"} shown for review only
      </div>
    </li>
  );
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
  const c = evidence.counts_by_surface ?? {};
  const total = placements.length + reviews.length + failSafe.length;
  const sid = sessionId ?? null;

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
          {c.placements ?? placements.length} placed · {c.review_items ?? reviews.length} review ·{" "}
          {c.fail_safe ?? failSafe.length} fail-safe
        </span>
      </div>
      <p className="tl-subtle" style={{ margin: "0 0 12px", fontSize: 12 }}>
        Authored bore-path redline traced from the PDF&apos;s CAD bore layers, drawn in the plan&apos;s own
        (page-space) coordinates
        {evidence.source?.input ? ` · source: ${evidence.source.input}` : ""}. Read-only · review-grade.
        {evidence.status && evidence.status !== "OK" ? ` · status: ${evidence.status}` : ""}
      </p>

      {total === 0 ? (
        <p className="tl-subtle" style={{ margin: 0 }}>
          No PDF-first evidence for this session.
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
          {placements.map((card, i) => (
            <SegmentCard key={`p-${i}`} card={card} sessionId={sid} />
          ))}
          {reviews.map((card, i) => (
            <SegmentCard key={`r-${i}`} card={card} sessionId={sid} />
          ))}
          {failSafe.map((card, i) => (
            <FailSafeCard key={`f-${i}`} card={card} />
          ))}
        </ul>
      )}

      {(evidence.warnings?.length ?? 0) > 0 && (
        <p className="tl-subtle" style={{ margin: "10px 0 0", fontSize: 11, color: "var(--tl-text-muted)" }}>
          {evidence.warnings!.length} warning(s)
        </p>
      )}
    </div>
  );
}
