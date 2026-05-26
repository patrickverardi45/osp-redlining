"use client";

/**
 * PDF Plan Mode — Step 1 viewer + Step 2A plan-set index sidebar.
 *
 * Step 1 (read-only) renders an uploaded engineering PDF as a dedicated
 * plan-sheet canvas outside the Leaflet workspace.  Step 2A adds a
 * left-sidebar plan-set index that classifies each page (plan_sheet /
 * detail_sheet / cover_sheet / notes_sheet / unknown) and surfaces
 * detected stations, matchlines, route names, and construction
 * keywords as operator-reviewable suggestions.  No drawing, no trace
 * persistence, no station anchors, no redline generation, no export
 * yet — those land in Steps 2B-4.
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
 *   5. Step 2A: in parallel with the first page fetch, also call
 *      /api/engineering-plans/{plan_id}/index to load the classified
 *      plan-set index.  The sidebar renders one entry per page with a
 *      classification badge; clicking jumps the canvas to that page.
 *
 * Page count is discovered TWICE: by probe-by-fetch on the image
 * endpoint (Step 1 fallback) AND by the index endpoint's page_count
 * field (Step 2A authoritative).  The index value supersedes the
 * probe value when available.
 *
 * Tenant isolation: enforced backend-side by _require_tenant_owns_session
 * against the plan's session_id (which we send in every request).
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

// Step 2A — plan-set index response shape (mirrors backend
// schema pdf-plan-index-1 from app/core/pdf_plan_index.py).
type PageClassification =
  | "plan_sheet"
  | "detail_sheet"
  | "cover_sheet"
  | "notes_sheet"
  | "unknown";

type PlanIndexPage = {
  page_index: number;
  page_number: number;
  title_candidates: string[];
  route_names: string[];
  matchline_refs: string[];
  station_labels: string[];
  construction_keywords: string[];
  classification: PageClassification;
  redline_candidate: boolean;
  text_layer_available: boolean;
  raw_text_excerpt: string;
  page_load_error?: string;
};

type PlanIndexResponse = {
  schema_version: string;
  page_count: number;
  text_extraction_available: boolean;
  pages: PlanIndexPage[];
};

type IndexState =
  | { kind: "loading" }
  | { kind: "ok"; index: PlanIndexResponse }
  | { kind: "error"; message: string }
  | { kind: "disabled" };

// Visual palette for classification badges.  Colors are intentionally
// distinct + screen-reader-labeled.  No reliance on color alone for
// meaning (each badge has the short text label too).
const CLASSIFICATION_STYLE: Record<
  PageClassification,
  { label: string; bg: string; fg: string; border: string }
> = {
  plan_sheet: {
    label: "Plan",
    bg: "rgba(16, 185, 129, 0.14)",
    fg: "#047857",
    border: "rgba(16, 185, 129, 0.45)",
  },
  detail_sheet: {
    label: "Detail",
    bg: "rgba(245, 158, 11, 0.14)",
    fg: "#92400e",
    border: "rgba(245, 158, 11, 0.45)",
  },
  cover_sheet: {
    label: "Cover",
    bg: "rgba(59, 130, 246, 0.12)",
    fg: "#1d4ed8",
    border: "rgba(59, 130, 246, 0.40)",
  },
  notes_sheet: {
    label: "Notes",
    bg: "rgba(139, 92, 246, 0.12)",
    fg: "#5b21b6",
    border: "rgba(139, 92, 246, 0.40)",
  },
  unknown: {
    label: "?",
    bg: "rgba(100, 116, 139, 0.12)",
    fg: "#475569",
    border: "rgba(100, 116, 139, 0.40)",
  },
};

export default function PdfPlanCanvas({ projectId, planId }: PdfPlanCanvasProps) {
  const [metadata, setMetadata] = useState<MetadataState>({ kind: "loading" });
  const [pageIndex, setPageIndex] = useState<number>(0);
  const [pageState, setPageState] = useState<PageState>({ kind: "idle" });
  const [knownMinFailIndex, setKnownMinFailIndex] = useState<number | null>(null);
  const [renderedDimensions, setRenderedDimensions] = useState<
    { w: number; h: number } | null
  >(null);
  const [indexState, setIndexState] = useState<IndexState>({ kind: "loading" });

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
  // Step 2A — fetch plan-set classification index once metadata is ok.
  // -------------------------------------------------------------------------
  useEffect(() => {
    if (metadata.kind !== "ok") return;
    const plan = metadata.plan;
    let cancelled = false;
    void (async () => {
      setIndexState({ kind: "loading" });
      try {
        const url =
          `${RENDER_BASE}/api/engineering-plans/${encodeURIComponent(plan.plan_id)}` +
          `/index?session_id=${encodeURIComponent(plan.session_id)}`;
        const resp = await apiFetch(url, undefined, "pdf_plan_viewer_index");
        if (cancelled) return;
        if (resp.status === 404) {
          // Backend flag off (TRUELINE_PLAN_OVERLAY_IMAGE) — index unavailable.
          setIndexState({ kind: "disabled" });
          return;
        }
        if (!resp.ok) {
          setIndexState({
            kind: "error",
            message: `Plan-set index unavailable (HTTP ${resp.status}). Page navigation still works.`,
          });
          return;
        }
        const data = (await resp.json().catch(() => null)) as
          | (PlanIndexResponse & { success?: boolean })
          | null;
        if (cancelled) return;
        if (!data || !Array.isArray(data.pages)) {
          setIndexState({
            kind: "error",
            message:
              "Plan-set index response was empty or malformed. Page navigation still works.",
          });
          return;
        }
        setIndexState({
          kind: "ok",
          index: {
            schema_version: data.schema_version || "unknown",
            page_count: data.page_count || data.pages.length,
            text_extraction_available: Boolean(data.text_extraction_available),
            pages: data.pages,
          },
        });
      } catch (err) {
        if (cancelled) return;
        setIndexState({
          kind: "error",
          message:
            err instanceof Error
              ? err.message
              : "Unexpected error while loading the plan-set index.",
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [metadata]);

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
  const indexedPageCount =
    indexState.kind === "ok" ? indexState.index.page_count : null;
  const currentPageEntry =
    indexState.kind === "ok"
      ? indexState.index.pages.find((p) => p.page_index === pageIndex) ?? null
      : null;

  const prevDisabled =
    pageIndex <= 0 || pageState.kind === "loading" || !isMetadataReady;
  // Next disables when we've hit the page-image probe boundary OR when the
  // index tells us we're already on the last page.
  const atKnownMaxByProbe =
    knownMinFailIndex !== null && pageIndex + 1 >= knownMinFailIndex;
  const atKnownMaxByIndex =
    indexedPageCount !== null && pageIndex + 1 >= indexedPageCount;
  const nextDisabled =
    pageState.kind === "loading" ||
    !isMetadataReady ||
    atKnownMaxByProbe ||
    atKnownMaxByIndex;

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
            maxWidth: 1600,
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
                minWidth: 92,
                textAlign: "center",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              Page {pageIndex + 1}
              {indexedPageCount !== null ? ` / ${indexedPageCount}` : ""}
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

      {/* Step 2A — per-page metadata strip (under the top bar, above the canvas) */}
      {currentPageEntry && (
        <PageMetadataStrip page={currentPageEntry} />
      )}

      {/* Optional banner for boundary / error notices */}
      {(pageState.kind === "error" || (atKnownMaxByProbe && pageState.kind !== "loading")) && (
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
          <div style={{ maxWidth: 1600, margin: "0 auto" }}>
            {pageState.kind === "error"
              ? pageState.message
              : "End of PDF reached — no more pages after this one."}
          </div>
        </div>
      )}

      {/* Main content area — flex row with sidebar + canvas */}
      <div
        style={{
          flex: 1,
          display: "flex",
          minHeight: 0,
        }}
      >
        {/* Step 2A — plan-set index sidebar */}
        <PlanSetSidebar
          indexState={indexState}
          currentPageIndex={pageIndex}
          onJump={setPageIndex}
        />

        {/* Canvas area */}
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
      </div>

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
            maxWidth: 1600,
            margin: "0 auto",
            display: "flex",
            justifyContent: "space-between",
            gap: 16,
            flexWrap: "wrap",
          }}
        >
          <span>
            PDF Plan Viewer · Step 1 + Step 2A (read-only · classifications are
            suggestions, operator review required)
          </span>
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

// ───────────────────────────────────────────────────────────────────────────
// Plan-set sidebar — one entry per page with classification badge.
// ───────────────────────────────────────────────────────────────────────────

function PlanSetSidebar({
  indexState,
  currentPageIndex,
  onJump,
}: {
  indexState: IndexState;
  currentPageIndex: number;
  onJump: (pageIndex: number) => void;
}) {
  const baseStyle: React.CSSProperties = {
    width: 280,
    flexShrink: 0,
    borderRight: "1px solid var(--tl-border)",
    background: "var(--tl-bg-grid)",
    overflow: "auto",
    display: "flex",
    flexDirection: "column",
  };

  return (
    <aside style={baseStyle} aria-label="Plan set page index">
      <div
        style={{
          padding: "10px 14px",
          borderBottom: "1px solid var(--tl-border)",
          fontSize: 11,
          fontWeight: 700,
          color: "var(--tl-text)",
          letterSpacing: "0.04em",
          textTransform: "uppercase",
        }}
      >
        Plan Set Index
      </div>

      {indexState.kind === "loading" && (
        <div
          style={{
            padding: 16,
            fontSize: 12,
            color: "var(--tl-text-muted)",
          }}
        >
          Classifying pages…
        </div>
      )}

      {indexState.kind === "disabled" && (
        <div
          style={{
            padding: 16,
            fontSize: 12,
            color: "var(--tl-text-muted)",
            lineHeight: 1.5,
          }}
        >
          Plan-set indexing is currently disabled on the backend. Page
          navigation still works — use Prev / Next above.
        </div>
      )}

      {indexState.kind === "error" && (
        <div
          style={{
            padding: 16,
            fontSize: 12,
            color: "#92400e",
            background: "rgba(245, 158, 11, 0.08)",
            lineHeight: 1.5,
          }}
        >
          {indexState.message}
        </div>
      )}

      {indexState.kind === "ok" && (
        <>
          {!indexState.index.text_extraction_available && (
            <div
              style={{
                padding: "10px 14px",
                margin: "8px",
                background: "rgba(245, 158, 11, 0.08)",
                border: "1px solid rgba(245, 158, 11, 0.30)",
                borderRadius: 6,
                fontSize: 11,
                color: "#92400e",
                lineHeight: 1.5,
              }}
            >
              No PDF text layer detected on any page. Classifications may be
              empty — this PDF likely needs OCR to be searchable (deferred to a
              future step).
            </div>
          )}
          <ol
            style={{
              listStyle: "none",
              padding: 0,
              margin: 0,
              borderTop: "1px solid var(--tl-border)",
            }}
          >
            {indexState.index.pages.map((page) => (
              <li key={page.page_index}>
                <PlanSetSidebarEntry
                  page={page}
                  isCurrent={page.page_index === currentPageIndex}
                  onJump={onJump}
                />
              </li>
            ))}
          </ol>
        </>
      )}
    </aside>
  );
}

function PlanSetSidebarEntry({
  page,
  isCurrent,
  onJump,
}: {
  page: PlanIndexPage;
  isCurrent: boolean;
  onJump: (pageIndex: number) => void;
}) {
  const style = CLASSIFICATION_STYLE[page.classification];
  const title =
    page.title_candidates.find((t) => t.length >= 3 && t.length <= 60) ||
    (page.classification === "unknown"
      ? page.text_layer_available
        ? "Unclassified"
        : "Scanned (no text layer)"
      : "");
  const stationCount = page.station_labels.length;
  const matchlineCount = page.matchline_refs.length;
  const routeText = page.route_names.slice(0, 2).join(" · ");

  return (
    <button
      type="button"
      onClick={() => onJump(page.page_index)}
      aria-current={isCurrent ? "page" : undefined}
      title={`Jump to page ${page.page_number}`}
      style={{
        display: "block",
        width: "100%",
        textAlign: "left",
        padding: "10px 14px",
        background: isCurrent ? "rgba(37, 99, 235, 0.10)" : "transparent",
        borderTop: "none",
        borderRight: "none",
        borderLeft: isCurrent
          ? "3px solid #2563eb"
          : "3px solid transparent",
        borderBottom: "1px solid var(--tl-border)",
        cursor: "pointer",
        color: "var(--tl-text)",
        fontFamily: "inherit",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginBottom: 4,
        }}
      >
        <span
          style={{
            fontSize: 10,
            fontWeight: 700,
            padding: "2px 6px",
            background: style.bg,
            color: style.fg,
            border: `1px solid ${style.border}`,
            borderRadius: 4,
            textTransform: "uppercase",
            letterSpacing: "0.04em",
            minWidth: 38,
            textAlign: "center",
          }}
        >
          {style.label}
        </span>
        <span style={{ fontSize: 13, fontWeight: 600 }}>
          Page {page.page_number}
        </span>
        {page.redline_candidate && (
          <span
            title="Likely candidate for redline tracing"
            aria-label="Redline candidate"
            style={{
              fontSize: 10,
              padding: "2px 5px",
              background: "rgba(220, 38, 38, 0.12)",
              color: "#b91c1c",
              border: "1px solid rgba(220, 38, 38, 0.35)",
              borderRadius: 4,
              fontWeight: 700,
              letterSpacing: "0.04em",
            }}
          >
            ●
          </span>
        )}
      </div>
      {title && (
        <div
          style={{
            fontSize: 11,
            color: "var(--tl-text-muted)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            marginBottom: 2,
          }}
        >
          {title}
        </div>
      )}
      {(stationCount > 0 || matchlineCount > 0 || routeText) && (
        <div
          style={{
            fontSize: 10,
            color: "var(--tl-text-faint)",
            display: "flex",
            gap: 8,
            flexWrap: "wrap",
            marginTop: 2,
          }}
        >
          {routeText && <span>{routeText}</span>}
          {stationCount > 0 && (
            <span>
              {stationCount} sta{stationCount === 1 ? "" : "s"}
            </span>
          )}
          {matchlineCount > 0 && (
            <span>
              {matchlineCount} ML
            </span>
          )}
        </div>
      )}
    </button>
  );
}

// ───────────────────────────────────────────────────────────────────────────
// Per-page metadata strip — shows current page's extracted signals.
// ───────────────────────────────────────────────────────────────────────────

function PageMetadataStrip({ page }: { page: PlanIndexPage }) {
  const style = CLASSIFICATION_STYLE[page.classification];
  const hasAnySignals =
    page.route_names.length > 0 ||
    page.station_labels.length > 0 ||
    page.matchline_refs.length > 0 ||
    page.construction_keywords.length > 0;

  return (
    <div
      style={{
        borderBottom: "1px solid var(--tl-border)",
        background: "var(--tl-surface)",
        padding: "8px 22px",
      }}
    >
      <div
        style={{
          maxWidth: 1600,
          margin: "0 auto",
          display: "flex",
          alignItems: "center",
          flexWrap: "wrap",
          gap: 8,
          fontSize: 12,
          color: "var(--tl-text)",
        }}
      >
        <span
          style={{
            fontSize: 10,
            fontWeight: 700,
            padding: "2px 8px",
            background: style.bg,
            color: style.fg,
            border: `1px solid ${style.border}`,
            borderRadius: 4,
            textTransform: "uppercase",
            letterSpacing: "0.05em",
          }}
        >
          {style.label}
        </span>
        {page.redline_candidate && (
          <span
            style={{
              fontSize: 10,
              fontWeight: 700,
              padding: "2px 8px",
              background: "rgba(220, 38, 38, 0.10)",
              color: "#b91c1c",
              border: "1px solid rgba(220, 38, 38, 0.30)",
              borderRadius: 4,
              textTransform: "uppercase",
              letterSpacing: "0.05em",
            }}
          >
            Redline Candidate
          </span>
        )}
        {!hasAnySignals && page.text_layer_available && (
          <span style={{ color: "var(--tl-text-muted)", fontStyle: "italic" }}>
            No route / station / construction signals detected.
          </span>
        )}
        {!page.text_layer_available && (
          <span style={{ color: "#92400e", fontStyle: "italic" }}>
            No PDF text layer on this page (likely a scan — OCR not yet
            implemented).
          </span>
        )}
        {page.route_names.length > 0 && (
          <MetadataChipGroup label="Route" items={page.route_names} />
        )}
        {page.matchline_refs.length > 0 && (
          <MetadataChipGroup
            label="Matchline"
            items={page.matchline_refs}
            maxShown={2}
          />
        )}
        {page.station_labels.length > 0 && (
          <MetadataChipGroup
            label="Stations"
            items={page.station_labels}
            maxShown={6}
          />
        )}
        {page.construction_keywords.length > 0 && (
          <MetadataChipGroup
            label="Keywords"
            items={page.construction_keywords}
            maxShown={5}
          />
        )}
      </div>
    </div>
  );
}

function MetadataChipGroup({
  label,
  items,
  maxShown = 4,
}: {
  label: string;
  items: string[];
  maxShown?: number;
}) {
  const shown = items.slice(0, maxShown);
  const overflow = items.length - shown.length;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        flexWrap: "wrap",
      }}
    >
      <span style={{ color: "var(--tl-text-muted)", fontWeight: 600 }}>
        {label}:
      </span>
      {shown.map((item, i) => (
        <span
          key={`${label}-${i}-${item.slice(0, 16)}`}
          style={{
            fontSize: 11,
            padding: "1px 6px",
            background: "rgba(15, 23, 42, 0.04)",
            border: "1px solid rgba(15, 23, 42, 0.08)",
            borderRadius: 4,
            color: "var(--tl-text)",
            whiteSpace: "nowrap",
            maxWidth: 240,
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
          title={item}
        >
          {item}
        </span>
      ))}
      {overflow > 0 && (
        <span style={{ color: "var(--tl-text-faint)" }}>+{overflow}</span>
      )}
    </span>
  );
}
