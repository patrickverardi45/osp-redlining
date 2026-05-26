"use client";

/**
 * PDF Plan Mode — Step 1 viewer (read-only).
 *
 * Renders an uploaded engineering PDF as a dedicated plan-sheet canvas
 * outside the Leaflet workspace.  No drawing, no trace persistence, no
 * station anchors, no redline generation, no export — those land in
 * Steps 2-4.  This viewer exists to prove the routing + auth + PNG
 * fetch chain works in isolation from ModernHeroMap.
 *
 * Data flow:
 *   1. Mount: read session_id via appendSessionIdReadOnly (existing helper);
 *      fetch /api/engineering-plans, filter by planId.
 *   2. Once the matched plan is in state: fetch the page-image PNG via
 *      the existing VO.2a endpoint, scoped to the plan's OWN session_id
 *      (VO.2b R4 self-healing pattern — survives localStorage rotation).
 *   3. apiFetch -> resp.blob() -> URL.createObjectURL -> <img src=...>.
 *      Mirrors the VO.2b R8 pattern but without Leaflet panes; renders
 *      as a plain DOM <img> inside a scrollable container.
 *   4. Revoke prior blob URL before each new page fetch and on unmount.
 *
 * Page count is discovered by probe-by-fetch: out-of-range pages return
 * non-2xx and disable Next thereafter.  Matches VO.2b R8's page-discovery
 * approach so we add no new backend metadata endpoint in Step 1.
 *
 * Tenant isolation: enforced backend-side by _require_tenant_owns_session
 * against the plan's session_id (which we send in every image request).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/apiFetch";
import { appendSessionIdReadOnly } from "@/lib/session";
import type { EngineeringPlan } from "@/lib/types/backend";

const _RAW_API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "";
const RENDER_BASE = _RAW_API_BASE.replace(/\/+$/, "");

type PdfPlanCanvasProps = {
  projectId: string;
  planId: string;
};

type MetadataState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ok"; plan: EngineeringPlan }
  | { kind: "not_pdf"; plan: EngineeringPlan };

type PageState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; objectUrl: string }
  | { kind: "error"; status: number | null; message: string };

export default function PdfPlanCanvas({ projectId, planId }: PdfPlanCanvasProps) {
  const [metadata, setMetadata] = useState<MetadataState>({ kind: "loading" });
  const [pageIndex, setPageIndex] = useState<number>(0);
  const [pageState, setPageState] = useState<PageState>({ kind: "idle" });
  const [knownMinFailIndex, setKnownMinFailIndex] = useState<number | null>(null);
  const [renderedDimensions, setRenderedDimensions] = useState<{ w: number; h: number } | null>(null);

  // Holds the currently-mounted blob URL so we can revoke it across page
  // transitions + on unmount without depending on render order.
  const activeObjectUrlRef = useRef<string | null>(null);

  // -------------------------------------------------------------------------
  // Load plan metadata once on mount.
  // -------------------------------------------------------------------------
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setMetadata({ kind: "loading" });
      try {
        const url = appendSessionIdReadOnly(
          `${RENDER_BASE}/api/engineering-plans`,
          projectId,
        );
        const resp = await apiFetch(
          url,
          { cache: "no-store" },
          "pdf_plan_viewer_metadata",
        );
        if (cancelled) return;
        if (!resp.ok) {
          setMetadata({
            kind: "error",
            message: `Failed to load engineering plans (HTTP ${resp.status}). Try reloading or returning to the workspace.`,
          });
          return;
        }
        const data = (await resp.json().catch(() => ({}))) as {
          engineering_plans?: EngineeringPlan[];
        };
        const plans = Array.isArray(data.engineering_plans) ? data.engineering_plans : [];
        const matched = plans.find((p) => p.plan_id === planId) ?? null;
        if (cancelled) return;
        if (!matched) {
          setMetadata({
            kind: "error",
            message:
              "This plan was not found in the current project session. It may have been removed, archived, or uploaded under a different session.",
          });
          return;
        }
        if (matched.file_type !== "application/pdf") {
          setMetadata({ kind: "not_pdf", plan: matched });
          return;
        }
        setMetadata({ kind: "ok", plan: matched });
      } catch (err) {
        if (cancelled) return;
        setMetadata({
          kind: "error",
          message:
            err instanceof Error
              ? err.message
              : "Unexpected error while loading the plan record.",
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId, planId]);

  // -------------------------------------------------------------------------
  // Fetch + render the current page image whenever the plan or page changes.
  // -------------------------------------------------------------------------
  useEffect(() => {
    if (metadata.kind !== "ok") return;
    const plan = metadata.plan;
    const targetPageIndex = pageIndex;

    let cancelled = false;

    // Revoke the prior blob URL before kicking off the new fetch. Ref
    // mutation only — no setState in the synchronous effect body.
    if (activeObjectUrlRef.current) {
      try {
        URL.revokeObjectURL(activeObjectUrlRef.current);
      } catch {
        /* noop */
      }
      activeObjectUrlRef.current = null;
    }

    void (async () => {
      setPageState({ kind: "loading" });
      try {
        const url =
          `${RENDER_BASE}/api/engineering-plans/${encodeURIComponent(plan.plan_id)}` +
          `/page/${encodeURIComponent(String(targetPageIndex))}/image?dpi=96` +
          `&session_id=${encodeURIComponent(plan.session_id)}`;
        const resp = await apiFetch(url, undefined, "pdf_plan_viewer_page");
        if (cancelled) return;
        if (!resp.ok) {
          const isOutOfRange = resp.status === 404 || resp.status === 500;
          setPageState({
            kind: "error",
            status: resp.status,
            message: isOutOfRange
              ? `Page ${targetPageIndex + 1} is past the end of this PDF, or could not be rendered.`
              : `Failed to render page ${targetPageIndex + 1} (HTTP ${resp.status}).`,
          });
          // Record the failure boundary so Next becomes disabled past this
          // page.  Functional setState avoids stale-closure on knownMinFailIndex
          // and keeps this effect's deps lean (no need to list it).
          if (isOutOfRange && targetPageIndex > 0) {
            setKnownMinFailIndex((prev) =>
              prev === null || targetPageIndex < prev ? targetPageIndex : prev,
            );
          }
          return;
        }
        const blob = await resp.blob();
        if (cancelled) return;
        const objectUrl = URL.createObjectURL(blob);
        activeObjectUrlRef.current = objectUrl;
        setPageState({ kind: "ready", objectUrl });
      } catch (err) {
        if (cancelled) return;
        setPageState({
          kind: "error",
          status: null,
          message:
            err instanceof Error
              ? err.message
              : "Unexpected error while rendering the page.",
        });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [metadata, pageIndex]);

  // -------------------------------------------------------------------------
  // Unmount: revoke any in-flight blob URL.
  // -------------------------------------------------------------------------
  useEffect(() => {
    return () => {
      if (activeObjectUrlRef.current) {
        try {
          URL.revokeObjectURL(activeObjectUrlRef.current);
        } catch {
          /* noop */
        }
        activeObjectUrlRef.current = null;
      }
    };
  }, []);

  // Derived UI state ---------------------------------------------------------
  const isMetadataReady = metadata.kind === "ok";
  const prevDisabled =
    pageIndex <= 0 || pageState.kind === "loading" || !isMetadataReady;
  const atKnownMax =
    knownMinFailIndex !== null && pageIndex + 1 >= knownMinFailIndex;
  const nextDisabled =
    pageState.kind === "loading" || !isMetadataReady || atKnownMax;

  const onPrev = useCallback(() => {
    setPageIndex((p) => Math.max(0, p - 1));
  }, []);
  const onNext = useCallback(() => {
    setPageIndex((p) => p + 1);
  }, []);

  const planFilename = (() => {
    if (metadata.kind === "ok" || metadata.kind === "not_pdf") {
      return metadata.plan.original_filename;
    }
    return metadata.kind === "loading" ? "Loading plan..." : "Plan unavailable";
  })();

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  return (
    <main
      className="tl-page"
      style={{
        display: "flex",
        flexDirection: "column",
        minHeight: "100vh",
      }}
    >
      {/* Top bar: Back link, title, page controls */}
      <header
        className="tl-topbar"
        style={{
          padding: "12px 22px",
          borderBottom: "1px solid var(--tl-border)",
        }}
      >
        <div
          style={{
            maxWidth: 1400,
            margin: "0 auto",
            width: "100%",
            display: "grid",
            gridTemplateColumns: "auto 1fr auto",
            alignItems: "center",
            gap: 16,
          }}
        >
          <Link
            href={`/projects/${projectId}`}
            className="tl-link"
            style={{
              fontSize: 13,
              fontWeight: 600,
              whiteSpace: "nowrap",
            }}
          >
            ← Back to Workspace
          </Link>

          <div style={{ minWidth: 0, textAlign: "center", padding: "0 12px" }}>
            <div className="tl-eyebrow" style={{ fontSize: 11 }}>
              PDF Plan Viewer
            </div>
            <div
              style={{
                fontSize: 14,
                marginTop: 2,
                fontWeight: 600,
                color: "var(--tl-text)",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
              title={planFilename}
            >
              {planFilename}
            </div>
          </div>

          <nav
            aria-label="Page navigation"
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              whiteSpace: "nowrap",
            }}
          >
            <button
              type="button"
              onClick={onPrev}
              disabled={prevDisabled}
              className="tl-btn tl-btn-ghost"
              style={{
                padding: "5px 12px",
                fontSize: 13,
                opacity: prevDisabled ? 0.4 : 1,
                cursor: prevDisabled ? "not-allowed" : "pointer",
                minWidth: 64,
              }}
            >
              ‹ Prev
            </button>
            <span
              style={{
                fontSize: 13,
                fontWeight: 600,
                color: "var(--tl-text)",
                minWidth: 72,
                textAlign: "center",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              Page {pageIndex + 1}
            </span>
            <button
              type="button"
              onClick={onNext}
              disabled={nextDisabled}
              className="tl-btn tl-btn-ghost"
              style={{
                padding: "5px 12px",
                fontSize: 13,
                opacity: nextDisabled ? 0.4 : 1,
                cursor: nextDisabled ? "not-allowed" : "pointer",
                minWidth: 64,
              }}
            >
              Next ›
            </button>
          </nav>
        </div>
      </header>

      {/* Optional banner for boundary / error notices */}
      {(pageState.kind === "error" || (atKnownMax && pageState.kind !== "loading")) && (
        <div
          role="status"
          style={{
            padding: "8px 22px",
            background:
              pageState.kind === "error"
                ? "rgba(220, 38, 38, 0.06)"
                : "rgba(245, 158, 11, 0.06)",
            borderBottom: "1px solid var(--tl-border)",
            fontSize: 12,
            color: pageState.kind === "error" ? "#dc2626" : "#92400e",
          }}
        >
          <div style={{ maxWidth: 1400, margin: "0 auto" }}>
            {pageState.kind === "error"
              ? pageState.message
              : "End of PDF reached — no more pages after this one."}
          </div>
        </div>
      )}

      {/* Main canvas region */}
      <section
        style={{
          flex: 1,
          overflow: "auto",
          background: "#e2e8f0",
          padding: "24px",
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "center",
        }}
      >
        {metadata.kind === "loading" && (
          <div
            style={{
              padding: 40,
              color: "var(--tl-text-muted)",
              fontSize: 14,
            }}
          >
            Loading plan metadata...
          </div>
        )}

        {metadata.kind === "error" && (
          <div
            className="tl-card"
            style={{
              maxWidth: 480,
              padding: 24,
              background: "var(--tl-surface)",
              border: "1px solid var(--tl-border)",
              borderRadius: 12,
              textAlign: "center",
              color: "var(--tl-text)",
              fontSize: 14,
              lineHeight: 1.55,
              marginTop: 40,
            }}
          >
            <div
              style={{
                fontWeight: 700,
                marginBottom: 8,
                color: "#dc2626",
                fontSize: 15,
              }}
            >
              Plan unavailable
            </div>
            <div style={{ color: "var(--tl-text-muted)" }}>{metadata.message}</div>
            <Link
              href={`/projects/${projectId}`}
              className="tl-link"
              style={{
                display: "inline-block",
                marginTop: 16,
                fontSize: 13,
                fontWeight: 600,
              }}
            >
              ← Back to Workspace
            </Link>
          </div>
        )}

        {metadata.kind === "not_pdf" && (
          <div
            className="tl-card"
            style={{
              maxWidth: 480,
              padding: 24,
              background: "var(--tl-surface)",
              border: "1px solid var(--tl-border)",
              borderRadius: 12,
              textAlign: "center",
              color: "var(--tl-text)",
              fontSize: 14,
              lineHeight: 1.55,
              marginTop: 40,
            }}
          >
            <div
              style={{
                fontWeight: 700,
                marginBottom: 8,
                fontSize: 15,
              }}
            >
              Not a PDF
            </div>
            <div style={{ color: "var(--tl-text-muted)" }}>
              This plan is a {metadata.plan.file_type || "non-PDF"} file. The PDF
              Plan Viewer only supports PDFs. Image plans can be viewed via the
              workspace overlay.
            </div>
            <Link
              href={`/projects/${projectId}`}
              className="tl-link"
              style={{
                display: "inline-block",
                marginTop: 16,
                fontSize: 13,
                fontWeight: 600,
              }}
            >
              ← Back to Workspace
            </Link>
          </div>
        )}

        {metadata.kind === "ok" && pageState.kind === "loading" && (
          <div
            style={{
              padding: 40,
              color: "var(--tl-text-muted)",
              fontSize: 14,
              display: "flex",
              alignItems: "center",
              gap: 12,
            }}
          >
            <span
              aria-hidden="true"
              style={{
                width: 16,
                height: 16,
                border: "2px solid #cbd5e1",
                borderTopColor: "#475569",
                borderRadius: "50%",
                display: "inline-block",
                animation: "pdf-plan-spin 0.8s linear infinite",
              }}
            />
            Rendering page {pageIndex + 1}…
            <style>{`
              @keyframes pdf-plan-spin {
                from { transform: rotate(0deg); }
                to   { transform: rotate(360deg); }
              }
            `}</style>
          </div>
        )}

        {metadata.kind === "ok" && pageState.kind === "ready" && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={pageState.objectUrl}
            alt={`${metadata.plan.original_filename} — page ${pageIndex + 1}`}
            onLoad={(e) => {
              const img = e.currentTarget;
              setRenderedDimensions({
                w: img.naturalWidth,
                h: img.naturalHeight,
              });
            }}
            style={{
              maxWidth: "100%",
              height: "auto",
              background: "#ffffff",
              boxShadow: "0 4px 16px rgba(15, 23, 42, 0.14)",
              borderRadius: 4,
            }}
          />
        )}
      </section>

      {/* Footer status strip */}
      <footer
        style={{
          borderTop: "1px solid var(--tl-border)",
          background: "var(--tl-bg-grid)",
          padding: "8px 22px",
          fontSize: 11,
          color: "var(--tl-text-faint)",
        }}
      >
        <div
          style={{
            maxWidth: 1400,
            margin: "0 auto",
            display: "flex",
            justifyContent: "space-between",
            gap: 16,
            flexWrap: "wrap",
          }}
        >
          <span>PDF Plan Viewer · Step 1 (read-only)</span>
          {metadata.kind === "ok" && (
            <span
              style={{
                fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
              }}
            >
              {metadata.plan.plan_id}
              {" · "}
              {pageState.kind === "loading"
                ? "loading"
                : pageState.kind === "ready"
                ? "ready"
                : pageState.kind === "error"
                ? "error"
                : "idle"}
              {renderedDimensions
                ? ` · ${renderedDimensions.w}×${renderedDimensions.h}px @96dpi`
                : ""}
            </span>
          )}
        </div>
      </footer>
    </main>
  );
}
