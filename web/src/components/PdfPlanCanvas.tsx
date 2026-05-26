"use client";

/**
 * PDF Plan Mode — Step 1 viewer + Step 2A plan-set index +
 * Step 2B operator trace + station anchors.
 *
 * Step 1: read-only dedicated PDF page viewer outside the Leaflet workspace.
 * Step 2A: sidebar plan-set index classifying every page (plan_sheet,
 *   detail_sheet, cover_sheet, notes_sheet, unknown) with detected stations,
 *   matchlines, routes, and construction keywords.
 * Step 2B: SVG overlay over the rendered PDF page lets the operator:
 *   - "Begin Trace" -> click route vertices on the image
 *   - "End Trace"   -> finish the trace draft
 *   - "Save Trace"  -> persist via PUT /api/engineering-plans/{plan_id}/trace
 *   - "Clear Trace" -> DELETE the persisted trace
 *   - "Add Station Anchor" -> click on/near the trace, enter label like
 *                              "11+60", anchor snaps to the trace
 *   Trace + anchors stored in PDF-pixel coordinates, scoped to
 *   (plan_id, page_index, session_id), persisted server-side under
 *   {ENGINEERING_PLAN_ROOT}/{session_id}/traces/.
 *
 * Hard limits honored (per Step 2B goal directive):
 * - No bore-log -> trace mapping
 * - No computed redline segment drawing
 * - No PDF export
 * - No auth / KMZ / map-redline / billing / closeout / GIS / parser touch
 * - No AI/LLM runtime calls
 * - Station placement is operator-entered, NOT auto-detected
 *
 * Coordinate model: stored points are PDF-pixel coordinates at the
 * page's native render DPI (96 by default).  The SVG overlay uses
 * viewBox="0 0 naturalWidth naturalHeight" so it scales with the
 * displayed image automatically; click events are converted from
 * browser pixels to PDF pixels via the SVG's bounding rect.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/apiFetch";
import { appendSessionIdReadOnly } from "@/lib/session";
import type { EngineeringPlan } from "@/lib/types/backend";
import type {
  PageClassification,
  PdfPoint,
  PdfRouteTrace,
  PdfRouteTracePayload,
  PdfStationAnchor,
  PlanIndexPage,
  PlanIndexResponse,
} from "@/lib/types/pdfPlan";
import {
  formatStationFt,
  nearestPointOnPolyline,
  parseStationLabel,
} from "@/lib/pdfPlanMath";

const _RAW_API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "";
const RENDER_BASE = _RAW_API_BASE.replace(/\/+$/, "");

// Anchor snap radius in PDF pixels.  Beyond this distance the click is
// treated as an anchor on the trace at the nearest snapped point — we
// always snap, never place free-floating anchors, because the geometric
// meaning of a station value is "a position along the route".
const ANCHOR_SNAP_HINT_PX = 60;

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

type IndexState =
  | { kind: "loading" }
  | { kind: "ok"; index: PlanIndexResponse }
  | { kind: "error"; message: string }
  | { kind: "disabled" };

type EditMode = "idle" | "tracing" | "anchoring";

type TraceState =
  | { kind: "loading" }
  | { kind: "absent" } // no trace on disk for this page yet
  | { kind: "loaded"; trace: PdfRouteTrace }
  | { kind: "error"; message: string }
  | { kind: "disabled" };

type SaveState =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "saved"; at: string }
  | { kind: "error"; message: string };

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

  // Step 2B — operator trace + anchors
  const [traceState, setTraceState] = useState<TraceState>({ kind: "loading" });
  const [editMode, setEditMode] = useState<EditMode>("idle");
  const [draftPoints, setDraftPoints] = useState<PdfPoint[]>([]);
  const [draftAnchors, setDraftAnchors] = useState<PdfStationAnchor[]>([]);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState<boolean>(false);
  const [saveState, setSaveState] = useState<SaveState>({ kind: "idle" });

  const activeObjectUrlRef = useRef<string | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  // -------------------------------------------------------------------------
  // Plan metadata (once on mount)
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
  // Plan-set classification index (Step 2A)
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
  // PDF page image (per page)
  // -------------------------------------------------------------------------
  useEffect(() => {
    if (metadata.kind !== "ok") return;
    const plan = metadata.plan;
    const targetPageIndex = pageIndex;

    let cancelled = false;

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
  // Step 2B — load any saved trace for this (plan, page)
  // -------------------------------------------------------------------------
  useEffect(() => {
    if (metadata.kind !== "ok") return;
    const plan = metadata.plan;
    const targetPageIndex = pageIndex;
    let cancelled = false;

    void (async () => {
      // Reset draft state on page change.  Done inside the async IIFE so
      // the setStates are not synchronous-in-effect-body (eslint rule
      // react-hooks/set-state-in-effect).
      setEditMode("idle");
      setDraftPoints([]);
      setDraftAnchors([]);
      setHasUnsavedChanges(false);
      setSaveState({ kind: "idle" });
      setTraceState({ kind: "loading" });
      try {
        const url =
          `${RENDER_BASE}/api/engineering-plans/${encodeURIComponent(plan.plan_id)}` +
          `/trace?page_index=${encodeURIComponent(String(targetPageIndex))}` +
          `&session_id=${encodeURIComponent(plan.session_id)}`;
        const resp = await apiFetch(url, { cache: "no-store" }, "pdf_plan_trace_load");
        if (cancelled) return;
        if (resp.status === 404) {
          // 404 means either flag-off OR no trace yet; we distinguish by
          // checking the JSON body's error message conservatively.
          const data = (await resp.json().catch(() => null)) as
            | { error?: string }
            | null;
          const msg = (data?.error || "").toLowerCase();
          if (msg.includes("disabled")) {
            setTraceState({ kind: "disabled" });
          } else {
            setTraceState({ kind: "absent" });
          }
          return;
        }
        if (!resp.ok) {
          setTraceState({
            kind: "error",
            message: `Failed to load trace (HTTP ${resp.status}).`,
          });
          return;
        }
        const data = (await resp.json().catch(() => null)) as
          | { trace?: PdfRouteTrace }
          | null;
        if (cancelled) return;
        const t = data?.trace;
        if (!t || !Array.isArray(t.points)) {
          setTraceState({ kind: "absent" });
          return;
        }
        setTraceState({ kind: "loaded", trace: t });
        // Seed the draft from the saved trace so anchor-add etc. work
        // against the same vertex sequence.
        setDraftPoints(t.points.map((p) => [p[0], p[1]]));
        setDraftAnchors((t.anchors || []).map((a) => ({ ...a })));
      } catch (err) {
        if (cancelled) return;
        setTraceState({
          kind: "error",
          message:
            err instanceof Error
              ? err.message
              : "Unexpected error while loading trace.",
        });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [metadata, pageIndex]);

  // -------------------------------------------------------------------------
  // Unmount cleanup
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

  // -------------------------------------------------------------------------
  // Derived UI state
  // -------------------------------------------------------------------------
  const isMetadataReady = metadata.kind === "ok";
  const indexedPageCount =
    indexState.kind === "ok" ? indexState.index.page_count : null;
  const currentPageEntry =
    indexState.kind === "ok"
      ? indexState.index.pages.find((p) => p.page_index === pageIndex) ?? null
      : null;

  const prevDisabled =
    pageIndex <= 0 || pageState.kind === "loading" || !isMetadataReady;
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
  // Step 2B — trace + anchor handlers
  // -------------------------------------------------------------------------

  const beginTrace = useCallback(() => {
    // Begin a fresh trace; existing saved trace is shadowed until Save replaces it.
    setEditMode("tracing");
    setDraftPoints([]);
    setDraftAnchors([]);
    setHasUnsavedChanges(true);
    setSaveState({ kind: "idle" });
  }, []);

  const endTrace = useCallback(() => {
    setEditMode("idle");
  }, []);

  const beginAnchoring = useCallback(() => {
    if (draftPoints.length < 2) return;
    setEditMode("anchoring");
  }, [draftPoints.length]);

  const clearDraft = useCallback(() => {
    setEditMode("idle");
    setDraftPoints([]);
    setDraftAnchors([]);
    setHasUnsavedChanges(true);
  }, []);

  const removeLastDraftPoint = useCallback(() => {
    setDraftPoints((prev) => prev.slice(0, -1));
    setHasUnsavedChanges(true);
  }, []);

  const removeAnchor = useCallback((anchorId: string) => {
    setDraftAnchors((prev) => prev.filter((a) => a.anchor_id !== anchorId));
    setHasUnsavedChanges(true);
  }, []);

  const saveTrace = useCallback(async () => {
    if (metadata.kind !== "ok") return;
    if (draftPoints.length < 2) {
      setSaveState({
        kind: "error",
        message: "A trace needs at least 2 vertices before it can be saved.",
      });
      return;
    }
    if (!renderedDimensions) {
      setSaveState({
        kind: "error",
        message: "Page dimensions are not known yet — please wait for the image to finish loading.",
      });
      return;
    }
    const plan = metadata.plan;
    setSaveState({ kind: "saving" });
    try {
      const payload: PdfRouteTracePayload = {
        page_dpi: 96,
        page_size_px: [renderedDimensions.w, renderedDimensions.h],
        points: draftPoints,
        anchors: draftAnchors.map((a) => ({
          anchor_id: a.anchor_id,
          label: a.label,
          station_ft: a.station_ft,
          point: a.point,
          created_at: a.created_at,
        })),
      };
      const url =
        `${RENDER_BASE}/api/engineering-plans/${encodeURIComponent(plan.plan_id)}` +
        `/trace?page_index=${encodeURIComponent(String(pageIndex))}` +
        `&session_id=${encodeURIComponent(plan.session_id)}`;
      const resp = await apiFetch(
        url,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
        "pdf_plan_trace_save",
      );
      if (!resp.ok) {
        const body = (await resp.json().catch(() => null)) as
          | { error?: string }
          | null;
        const msg = body?.error || `Save failed (HTTP ${resp.status}).`;
        setSaveState({ kind: "error", message: msg });
        return;
      }
      const data = (await resp.json().catch(() => null)) as
        | { trace?: PdfRouteTrace }
        | null;
      const saved = data?.trace;
      if (!saved) {
        setSaveState({
          kind: "error",
          message: "Server accepted save but returned no trace body.",
        });
        return;
      }
      setTraceState({ kind: "loaded", trace: saved });
      setDraftPoints(saved.points.map((p) => [p[0], p[1]]));
      setDraftAnchors((saved.anchors || []).map((a) => ({ ...a })));
      setHasUnsavedChanges(false);
      setSaveState({ kind: "saved", at: saved.updated_at });
    } catch (err) {
      setSaveState({
        kind: "error",
        message:
          err instanceof Error ? err.message : "Unexpected error while saving trace.",
      });
    }
  }, [metadata, draftPoints, draftAnchors, renderedDimensions, pageIndex]);

  const deleteTrace = useCallback(async () => {
    if (metadata.kind !== "ok") return;
    const plan = metadata.plan;
    // Confirm UX-side via window.confirm — operator intent is destructive.
    if (
      typeof window !== "undefined" &&
      !window.confirm(
        "Delete the saved trace and all station anchors on this page? This cannot be undone.",
      )
    ) {
      return;
    }
    setSaveState({ kind: "saving" });
    try {
      const url =
        `${RENDER_BASE}/api/engineering-plans/${encodeURIComponent(plan.plan_id)}` +
        `/trace?page_index=${encodeURIComponent(String(pageIndex))}` +
        `&session_id=${encodeURIComponent(plan.session_id)}`;
      const resp = await apiFetch(
        url,
        { method: "DELETE" },
        "pdf_plan_trace_delete",
      );
      if (!resp.ok && resp.status !== 404) {
        const body = (await resp.json().catch(() => null)) as
          | { error?: string }
          | null;
        setSaveState({
          kind: "error",
          message: body?.error || `Delete failed (HTTP ${resp.status}).`,
        });
        return;
      }
      setTraceState({ kind: "absent" });
      setEditMode("idle");
      setDraftPoints([]);
      setDraftAnchors([]);
      setHasUnsavedChanges(false);
      setSaveState({ kind: "idle" });
    } catch (err) {
      setSaveState({
        kind: "error",
        message:
          err instanceof Error ? err.message : "Unexpected error while deleting trace.",
      });
    }
  }, [metadata, pageIndex]);

  // -------------------------------------------------------------------------
  // SVG click handling — convert browser pixels to PDF pixels via the
  // SVG's bounding rect.  Because the SVG uses viewBox = "0 0 W H" where
  // W/H are the image's natural pixel dimensions, the conversion is just
  // a simple ratio.
  // -------------------------------------------------------------------------
  const handleSvgClick = useCallback(
    (e: React.MouseEvent<SVGSVGElement>) => {
      const svg = svgRef.current;
      if (!svg || !renderedDimensions) return;
      const rect = svg.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return;
      const xFrac = (e.clientX - rect.left) / rect.width;
      const yFrac = (e.clientY - rect.top) / rect.height;
      const pdfX = Math.max(0, Math.min(renderedDimensions.w, xFrac * renderedDimensions.w));
      const pdfY = Math.max(0, Math.min(renderedDimensions.h, yFrac * renderedDimensions.h));

      if (editMode === "tracing") {
        setDraftPoints((prev) => [...prev, [pdfX, pdfY]]);
        setHasUnsavedChanges(true);
        return;
      }
      if (editMode === "anchoring") {
        if (draftPoints.length < 2) {
          setSaveState({
            kind: "error",
            message: "Trace must exist before adding station anchors.",
          });
          setEditMode("idle");
          return;
        }
        const snap = nearestPointOnPolyline([pdfX, pdfY], draftPoints);
        if (!snap) return;
        // Prompt for the station label.
        const labelInput = typeof window !== "undefined"
          ? window.prompt(
              "Enter station value for this anchor (examples: 11+60, STA 14+20, 2047):",
              "",
            )
          : null;
        if (!labelInput) {
          setEditMode("idle");
          return;
        }
        const station_ft = parseStationLabel(labelInput);
        if (station_ft === null) {
          setSaveState({
            kind: "error",
            message: `"${labelInput}" is not a valid station. Use formats like 11+60, STA 14+20, or raw feet 2047.`,
          });
          setEditMode("idle");
          return;
        }
        const newAnchor: PdfStationAnchor = {
          anchor_id: generateAnchorId(),
          station_ft,
          label: labelInput.trim().slice(0, 32),
          point: snap.point,
          created_at: new Date().toISOString(),
        };
        setDraftAnchors((prev) => [...prev, newAnchor]);
        setHasUnsavedChanges(true);
        setEditMode("idle");
        setSaveState({ kind: "idle" });
        return;
      }
      // editMode === "idle" -> click does nothing
    },
    [editMode, renderedDimensions, draftPoints],
  );

  // The SVG should only capture pointer events when in an edit mode that
  // requires clicks; otherwise let clicks pass through to the image (which
  // ignores them) so accidental clicks don't get interpreted as anything.
  const svgInteractive = editMode === "tracing" || editMode === "anchoring";

  const sortedAnchorsForRender = useMemo(() => {
    return [...draftAnchors].sort((a, b) => a.station_ft - b.station_ft);
  }, [draftAnchors]);

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
      {/* Top bar */}
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

      {/* Step 2A — per-page metadata strip */}
      {currentPageEntry && <PageMetadataStrip page={currentPageEntry} />}

      {/* Step 2B — trace toolbar */}
      {metadata.kind === "ok" && pageState.kind === "ready" && (
        <TraceToolbar
          editMode={editMode}
          traceState={traceState}
          draftPoints={draftPoints}
          draftAnchors={draftAnchors}
          hasUnsavedChanges={hasUnsavedChanges}
          saveState={saveState}
          onBeginTrace={beginTrace}
          onEndTrace={endTrace}
          onSave={saveTrace}
          onClear={clearDraft}
          onDeleteSaved={deleteTrace}
          onAddAnchor={beginAnchoring}
          onUndoLastPoint={removeLastDraftPoint}
        />
      )}

      {/* Optional banner for boundary / error notices */}
      {(pageState.kind === "error" ||
        (atKnownMaxByProbe && pageState.kind !== "loading")) && (
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

      {/* Main content area — sidebar + canvas */}
      <div
        style={{
          flex: 1,
          display: "flex",
          minHeight: 0,
        }}
      >
        <PlanSetSidebar
          indexState={indexState}
          currentPageIndex={pageIndex}
          onJump={setPageIndex}
        />

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
            <FullPageNotice
              title="Plan unavailable"
              titleColor="#dc2626"
              body={metadata.message}
              projectId={projectId}
            />
          )}

          {metadata.kind === "not_pdf" && (
            <FullPageNotice
              title="Not a PDF"
              body={`This plan is a ${metadata.plan.file_type || "non-PDF"} file. The PDF Plan Viewer only supports PDFs. Image plans can be viewed via the workspace overlay.`}
              projectId={projectId}
            />
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
            <CanvasWithOverlay
              objectUrl={pageState.objectUrl}
              imageAlt={`${metadata.plan.original_filename} — page ${pageIndex + 1}`}
              onImageLoad={(w, h) => setRenderedDimensions({ w, h })}
              renderedDimensions={renderedDimensions}
              draftPoints={draftPoints}
              draftAnchors={sortedAnchorsForRender}
              editMode={editMode}
              svgInteractive={svgInteractive}
              svgRef={svgRef}
              onSvgClick={handleSvgClick}
              onRemoveAnchor={removeAnchor}
            />
          )}
        </section>
      </div>

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
            PDF Plan Viewer · Step 1 + 2A + 2B (operator-traced; station
            placement is operator-entered, suggestion-grade classifications)
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
// Sub-components
// ───────────────────────────────────────────────────────────────────────────

function FullPageNotice({
  title,
  titleColor,
  body,
  projectId,
}: {
  title: string;
  titleColor?: string;
  body: string;
  projectId: string;
}) {
  return (
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
          color: titleColor || "var(--tl-text)",
          fontSize: 15,
        }}
      >
        {title}
      </div>
      <div style={{ color: "var(--tl-text-muted)" }}>{body}</div>
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
  );
}

function CanvasWithOverlay({
  objectUrl,
  imageAlt,
  onImageLoad,
  renderedDimensions,
  draftPoints,
  draftAnchors,
  editMode,
  svgInteractive,
  svgRef,
  onSvgClick,
  onRemoveAnchor,
}: {
  objectUrl: string;
  imageAlt: string;
  onImageLoad: (w: number, h: number) => void;
  renderedDimensions: { w: number; h: number } | null;
  draftPoints: PdfPoint[];
  draftAnchors: PdfStationAnchor[];
  editMode: EditMode;
  svgInteractive: boolean;
  svgRef: React.RefObject<SVGSVGElement | null>;
  onSvgClick: (e: React.MouseEvent<SVGSVGElement>) => void;
  onRemoveAnchor: (anchorId: string) => void;
}) {
  const pathD = useMemo(() => buildPolylinePath(draftPoints), [draftPoints]);
  const cursorStyle =
    editMode === "tracing"
      ? "crosshair"
      : editMode === "anchoring"
      ? "copy"
      : "default";

  return (
    <div
      style={{
        position: "relative",
        display: "inline-block",
        background: "#ffffff",
        boxShadow: "0 4px 16px rgba(15, 23, 42, 0.14)",
        borderRadius: 4,
        maxWidth: "100%",
        lineHeight: 0,
      }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={objectUrl}
        alt={imageAlt}
        onLoad={(e) => {
          const img = e.currentTarget;
          onImageLoad(img.naturalWidth, img.naturalHeight);
        }}
        style={{
          display: "block",
          maxWidth: "100%",
          height: "auto",
        }}
      />
      {renderedDimensions && (
        <svg
          ref={svgRef}
          viewBox={`0 0 ${renderedDimensions.w} ${renderedDimensions.h}`}
          preserveAspectRatio="none"
          onClick={svgInteractive ? onSvgClick : undefined}
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
            pointerEvents: svgInteractive ? "auto" : "none",
            cursor: cursorStyle,
          }}
        >
          {/* Trace polyline */}
          {pathD && (
            <path
              d={pathD}
              fill="none"
              stroke="#1d4ed8"
              strokeWidth={Math.max(2, renderedDimensions.w / 480)}
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity={editMode === "tracing" ? 0.75 : 0.9}
            />
          )}
          {/* Vertex dots */}
          {draftPoints.map((pt, i) => (
            <circle
              key={`vertex-${i}`}
              cx={pt[0]}
              cy={pt[1]}
              r={Math.max(4, renderedDimensions.w / 320)}
              fill="#ffffff"
              stroke="#1d4ed8"
              strokeWidth={Math.max(1.5, renderedDimensions.w / 720)}
            />
          ))}
          {/* Station anchors — vertical marker line + label box */}
          {draftAnchors.map((a) => {
            const r = Math.max(6, renderedDimensions.w / 240);
            return (
              <g
                key={`anchor-${a.anchor_id}`}
                pointerEvents={svgInteractive ? "none" : "auto"}
                style={{ cursor: svgInteractive ? "inherit" : "pointer" }}
                onClick={(ev) => {
                  ev.stopPropagation();
                  if (svgInteractive) return;
                  if (
                    typeof window !== "undefined" &&
                    window.confirm(
                      `Remove station anchor "${a.label}" (${formatStationFt(a.station_ft)} ft)?`,
                    )
                  ) {
                    onRemoveAnchor(a.anchor_id);
                  }
                }}
              >
                <circle
                  cx={a.point[0]}
                  cy={a.point[1]}
                  r={r}
                  fill="#dc2626"
                  stroke="#ffffff"
                  strokeWidth={Math.max(1.5, renderedDimensions.w / 720)}
                />
                <text
                  x={a.point[0] + r + 6}
                  y={a.point[1] + r / 2}
                  fill="#7f1d1d"
                  fontSize={Math.max(11, renderedDimensions.w / 96)}
                  fontWeight={700}
                  fontFamily="ui-sans-serif, system-ui, sans-serif"
                  style={{
                    paintOrder: "stroke",
                    stroke: "#ffffff",
                    strokeWidth: Math.max(2, renderedDimensions.w / 480),
                    strokeLinejoin: "round",
                  }}
                >
                  {a.label}
                </text>
              </g>
            );
          })}
        </svg>
      )}
    </div>
  );
}

function TraceToolbar({
  editMode,
  traceState,
  draftPoints,
  draftAnchors,
  hasUnsavedChanges,
  saveState,
  onBeginTrace,
  onEndTrace,
  onSave,
  onClear,
  onDeleteSaved,
  onAddAnchor,
  onUndoLastPoint,
}: {
  editMode: EditMode;
  traceState: TraceState;
  draftPoints: PdfPoint[];
  draftAnchors: PdfStationAnchor[];
  hasUnsavedChanges: boolean;
  saveState: SaveState;
  onBeginTrace: () => void;
  onEndTrace: () => void;
  onSave: () => void;
  onClear: () => void;
  onDeleteSaved: () => void;
  onAddAnchor: () => void;
  onUndoLastPoint: () => void;
}) {
  const tracingActive = editMode === "tracing";
  const anchoringActive = editMode === "anchoring";
  const hasDraft = draftPoints.length >= 2;
  const savedExists = traceState.kind === "loaded";

  const statusText = (() => {
    if (saveState.kind === "saving") return "Saving…";
    if (saveState.kind === "error") return saveState.message;
    if (saveState.kind === "saved") return "Saved.";
    if (tracingActive) return `Tracing — clicked ${draftPoints.length} point${draftPoints.length === 1 ? "" : "s"}. Click "End Trace" when done.`;
    if (anchoringActive) return "Click on or near the trace to place a station anchor.";
    if (hasUnsavedChanges && hasDraft) return "Unsaved changes — click Save Trace to persist.";
    if (savedExists) return `Saved trace · ${draftPoints.length} vertices · ${draftAnchors.length} anchor${draftAnchors.length === 1 ? "" : "s"}.`;
    if (traceState.kind === "absent") return "No trace yet. Click Begin Trace to start.";
    if (traceState.kind === "loading") return "Loading trace…";
    if (traceState.kind === "disabled") return "Trace persistence is disabled on the backend.";
    if (traceState.kind === "error") return traceState.message;
    return "";
  })();
  const statusTone: "info" | "error" | "warn" | "success" = (() => {
    if (saveState.kind === "error") return "error";
    if (saveState.kind === "saved") return "success";
    if (traceState.kind === "error") return "error";
    if (traceState.kind === "disabled") return "warn";
    if (hasUnsavedChanges && hasDraft) return "warn";
    return "info";
  })();
  const statusColor =
    statusTone === "error"
      ? "#dc2626"
      : statusTone === "warn"
      ? "#92400e"
      : statusTone === "success"
      ? "#047857"
      : "var(--tl-text-muted)";

  const traceDisabled = traceState.kind === "disabled" || traceState.kind === "loading";
  const saveDisabled =
    !hasDraft || !hasUnsavedChanges || saveState.kind === "saving" || traceDisabled;
  const clearDisabled = draftPoints.length === 0 || saveState.kind === "saving";
  const deleteDisabled = !savedExists || saveState.kind === "saving";
  const anchorDisabled = !hasDraft || tracingActive || traceDisabled;

  return (
    <div
      style={{
        padding: "8px 22px",
        borderBottom: "1px solid var(--tl-border)",
        background: "var(--tl-bg-grid)",
      }}
    >
      <div
        style={{
          maxWidth: 1600,
          margin: "0 auto",
          display: "flex",
          alignItems: "center",
          gap: 8,
          flexWrap: "wrap",
          fontSize: 12,
        }}
      >
        <span
          style={{
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: "0.04em",
            textTransform: "uppercase",
            color: "var(--tl-text)",
          }}
        >
          Route Trace
        </span>

        <ToolbarButton
          onClick={onBeginTrace}
          disabled={tracingActive || traceDisabled}
          variant={tracingActive ? "active" : "default"}
        >
          Begin Trace
        </ToolbarButton>
        <ToolbarButton
          onClick={onEndTrace}
          disabled={!tracingActive}
        >
          End Trace
        </ToolbarButton>
        <ToolbarButton
          onClick={onUndoLastPoint}
          disabled={!tracingActive || draftPoints.length === 0}
          title="Remove the last vertex you clicked"
        >
          Undo Point
        </ToolbarButton>
        <ToolbarButton
          onClick={onSave}
          disabled={saveDisabled}
          variant="primary"
        >
          Save Trace
        </ToolbarButton>
        <ToolbarButton
          onClick={onClear}
          disabled={clearDisabled}
          variant="ghost"
          title="Clear the in-memory draft (doesn't delete the saved trace until you Save)"
        >
          Clear Draft
        </ToolbarButton>

        <span
          style={{
            margin: "0 4px",
            color: "var(--tl-text-faint)",
            opacity: 0.6,
          }}
        >
          |
        </span>

        <ToolbarButton
          onClick={onAddAnchor}
          disabled={anchorDisabled}
          variant={anchoringActive ? "active" : "default"}
        >
          + Station Anchor
        </ToolbarButton>
        <ToolbarButton
          onClick={onDeleteSaved}
          disabled={deleteDisabled}
          variant="danger-ghost"
          title="Delete the saved trace + all its anchors from the server"
        >
          Delete Saved
        </ToolbarButton>

        <span
          role="status"
          style={{
            marginLeft: "auto",
            color: statusColor,
            fontWeight: 500,
            fontSize: 12,
            maxWidth: 520,
            textAlign: "right",
            lineHeight: 1.4,
          }}
        >
          {statusText}
        </span>
      </div>
    </div>
  );
}

function ToolbarButton({
  onClick,
  disabled,
  variant = "default",
  title,
  children,
}: {
  onClick: () => void;
  disabled?: boolean;
  variant?: "default" | "active" | "primary" | "ghost" | "danger-ghost";
  title?: string;
  children: React.ReactNode;
}) {
  const baseStyle: React.CSSProperties = {
    padding: "4px 10px",
    fontSize: 12,
    borderRadius: 6,
    cursor: disabled ? "not-allowed" : "pointer",
    fontWeight: 600,
    opacity: disabled ? 0.4 : 1,
    border: "1px solid",
    background: "transparent",
    color: "inherit",
    whiteSpace: "nowrap",
    transition: "background 120ms ease, color 120ms ease",
  };
  let extra: React.CSSProperties = {};
  if (variant === "primary") {
    extra = {
      background: disabled ? "#cbd5e1" : "#1d4ed8",
      borderColor: disabled ? "#cbd5e1" : "#1d4ed8",
      color: "#ffffff",
    };
  } else if (variant === "active") {
    extra = {
      background: "rgba(29, 78, 216, 0.10)",
      borderColor: "rgba(29, 78, 216, 0.45)",
      color: "#1d4ed8",
    };
  } else if (variant === "ghost") {
    extra = {
      borderColor: "transparent",
      color: "var(--tl-text-muted)",
    };
  } else if (variant === "danger-ghost") {
    extra = {
      borderColor: "rgba(220, 38, 38, 0.30)",
      color: "#dc2626",
    };
  } else {
    extra = {
      borderColor: "rgba(15, 23, 42, 0.18)",
      color: "var(--tl-text)",
    };
  }
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      style={{ ...baseStyle, ...extra }}
    >
      {children}
    </button>
  );
}

function PlanSetSidebar({
  indexState,
  currentPageIndex,
  onJump,
}: {
  indexState: IndexState;
  currentPageIndex: number;
  onJump: (pageIndex: number) => void;
}) {
  return (
    <aside
      style={{
        width: 280,
        flexShrink: 0,
        borderRight: "1px solid var(--tl-border)",
        background: "var(--tl-bg-grid)",
        overflow: "auto",
        display: "flex",
        flexDirection: "column",
      }}
      aria-label="Plan set page index"
    >
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
        <div style={{ padding: 16, fontSize: 12, color: "var(--tl-text-muted)" }}>
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
            <span>{matchlineCount} ML</span>
          )}
        </div>
      )}
    </button>
  );
}

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

// ───────────────────────────────────────────────────────────────────────────
// Small helpers
// ───────────────────────────────────────────────────────────────────────────

function buildPolylinePath(points: PdfPoint[]): string {
  if (!points || points.length === 0) return "";
  const parts: string[] = [];
  for (let i = 0; i < points.length; i++) {
    const cmd = i === 0 ? "M" : "L";
    parts.push(`${cmd}${points[i][0].toFixed(2)},${points[i][1].toFixed(2)}`);
  }
  return parts.join(" ");
}

function generateAnchorId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID().replace(/-/g, "").slice(0, 24);
  }
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`.slice(0, 24);
}

// Suppress an "unused import" warning if ANCHOR_SNAP_HINT_PX is only
// referenced from docs — keep the constant exported in case Step 3 wants
// it.  No-op suppression that doesn't ship runtime cost.
void ANCHOR_SNAP_HINT_PX;
