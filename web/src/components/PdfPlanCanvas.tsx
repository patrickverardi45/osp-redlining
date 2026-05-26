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
  BoreLogRow,
  PageClassification,
  PdfPoint,
  PdfRouteTrace,
  PdfRouteTracePayload,
  PdfSegmentsEnvelope,
  PdfStationAnchor,
  PdfStationSegment,
  PdfStationSegmentPayload,
  PlanIndexPage,
  PlanIndexResponse,
} from "@/lib/types/pdfPlan";
import {
  anchorsWithCumulativeDistance,
  cumulativePolylineLengths,
  extractPolylineSubpath,
  formatStationFt,
  nearestPointOnPolyline,
  parseStationLabel,
  stationFtToPolylineDistance,
} from "@/lib/pdfPlanMath";
import {
  importBoreLogExcelBatch,
  type ImportFileOutcome,
} from "@/lib/pdfPlanBoreLogImport";

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

// Step 3A — manual station segments
type SegmentsState =
  | { kind: "loading" }
  | { kind: "ok"; envelope: PdfSegmentsEnvelope }
  | { kind: "error"; message: string }
  | { kind: "disabled" };

type SegmentOpState =
  | { kind: "idle" }
  | { kind: "saving" }
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

  // Step 3A — manual station segments
  const [segmentsState, setSegmentsState] = useState<SegmentsState>({ kind: "loading" });
  const [segmentOpState, setSegmentOpState] = useState<SegmentOpState>({ kind: "idle" });
  const [segmentDraftOpen, setSegmentDraftOpen] = useState<boolean>(false);
  const [segmentDraft, setSegmentDraft] = useState<{
    label: string;
    start: string;
    end: string;
    notes: string;
  }>({ label: "", start: "", end: "", notes: "" });

  // Step 3B — bore-log-style rows (operator scratch space; persisted to
  // localStorage so they survive reloads but are NOT shared across
  // browsers/devices.  The PERSISTENT record of work is the generated
  // segment server-side; rows are the source from which segments are
  // generated.)
  const [boreLogRows, setBoreLogRows] = useState<BoreLogRow[]>([]);
  const [generateOpState, setGenerateOpState] = useState<{
    kind: "idle" | "running";
    message?: string;
    tone?: "info" | "success" | "warn" | "error";
  }>({ kind: "idle" });
  const [rowDraftOpen, setRowDraftOpen] = useState<boolean>(false);
  const [rowDraft, setRowDraft] = useState<{
    label: string;
    start: string;
    end: string;
    depth: string;
    boc: string;
    crew: string;
    date: string;
    notes: string;
  }>({
    label: "",
    start: "",
    end: "",
    depth: "",
    boc: "",
    crew: "",
    date: "",
    notes: "",
  });

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
  // Step 3A — load saved manual segments for this (plan, page)
  // -------------------------------------------------------------------------
  useEffect(() => {
    if (metadata.kind !== "ok") return;
    const plan = metadata.plan;
    const targetPageIndex = pageIndex;
    let cancelled = false;

    void (async () => {
      // Reset draft dialog on page change.
      setSegmentDraftOpen(false);
      setSegmentDraft({ label: "", start: "", end: "", notes: "" });
      setSegmentOpState({ kind: "idle" });
      setSegmentsState({ kind: "loading" });
      try {
        const url =
          `${RENDER_BASE}/api/engineering-plans/${encodeURIComponent(plan.plan_id)}` +
          `/segments?page_index=${encodeURIComponent(String(targetPageIndex))}` +
          `&session_id=${encodeURIComponent(plan.session_id)}`;
        const resp = await apiFetch(url, { cache: "no-store" }, "pdf_plan_segments_load");
        if (cancelled) return;
        if (resp.status === 404) {
          // Same heuristic as trace load: distinguish flag-off vs absent.
          const data = (await resp.json().catch(() => null)) as
            | { error?: string }
            | null;
          const msg = (data?.error || "").toLowerCase();
          if (msg.includes("disabled")) {
            setSegmentsState({ kind: "disabled" });
          } else {
            // No envelope at all is unusual (GET always returns 200 with
            // empty envelope) but treat as empty for safety.
            setSegmentsState({
              kind: "ok",
              envelope: emptySegmentsEnvelope(plan.plan_id, plan.session_id, targetPageIndex),
            });
          }
          return;
        }
        if (!resp.ok) {
          setSegmentsState({
            kind: "error",
            message: `Failed to load segments (HTTP ${resp.status}).`,
          });
          return;
        }
        const data = (await resp.json().catch(() => null)) as
          | { envelope?: PdfSegmentsEnvelope }
          | null;
        if (cancelled) return;
        const env = data?.envelope;
        if (!env || !Array.isArray(env.segments)) {
          setSegmentsState({
            kind: "ok",
            envelope: emptySegmentsEnvelope(plan.plan_id, plan.session_id, targetPageIndex),
          });
          return;
        }
        setSegmentsState({ kind: "ok", envelope: env });
      } catch (err) {
        if (cancelled) return;
        setSegmentsState({
          kind: "error",
          message:
            err instanceof Error
              ? err.message
              : "Unexpected error while loading segments.",
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [metadata, pageIndex]);

  // -------------------------------------------------------------------------
  // Step 3B — hydrate / persist bore-log-style rows in localStorage
  // -------------------------------------------------------------------------
  useEffect(() => {
    // Reset + hydrate on (plan, page) change.  Setters are placed inside
    // an async IIFE so they execute after the synchronous effect body
    // completes (avoids react-hooks/set-state-in-effect lint).
    void (async () => {
      setGenerateOpState({ kind: "idle" });
      setRowDraftOpen(false);
      setRowDraft({
        label: "",
        start: "",
        end: "",
        depth: "",
        boc: "",
        crew: "",
        date: "",
        notes: "",
      });
      if (metadata.kind !== "ok" || typeof window === "undefined") {
        setBoreLogRows([]);
        return;
      }
      const key = boreLogRowsStorageKey(metadata.plan.plan_id, pageIndex);
      try {
        const raw = window.localStorage.getItem(key);
        if (!raw) {
          setBoreLogRows([]);
          return;
        }
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          setBoreLogRows(parsed as BoreLogRow[]);
        } else {
          setBoreLogRows([]);
        }
      } catch {
        setBoreLogRows([]);
      }
    })();
  }, [metadata, pageIndex]);

  // Persist bore-log rows to localStorage whenever they change.
  useEffect(() => {
    if (metadata.kind !== "ok" || typeof window === "undefined") return;
    const key = boreLogRowsStorageKey(metadata.plan.plan_id, pageIndex);
    try {
      if (boreLogRows.length === 0) {
        window.localStorage.removeItem(key);
      } else {
        window.localStorage.setItem(key, JSON.stringify(boreLogRows));
      }
    } catch {
      /* localStorage full / disabled — silently degrade; the generated
         segments are the authoritative record server-side. */
    }
  }, [metadata, pageIndex, boreLogRows]);

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
  // Step 3A — segment rendering: precompute cumulative lengths + anchor-to-
  // distance map once per (trace, anchors) update; segment subpaths derive
  // from these.  All math lives in pdfPlanMath; this just wires it up.
  // -------------------------------------------------------------------------
  const segmentGeometry = useMemo(() => {
    if (traceState.kind !== "loaded") return null;
    const t = traceState.trace;
    if (!t.points || t.points.length < 2) return null;
    const cumLengths = cumulativePolylineLengths(t.points);
    const totalLength = cumLengths[cumLengths.length - 1];
    const sortedAnchors = anchorsWithCumulativeDistance(
      t.anchors || [],
      t.points,
      cumLengths,
    );
    return { points: t.points, cumLengths, totalLength, sortedAnchors };
  }, [traceState]);

  const renderableSegments = useMemo(() => {
    if (segmentsState.kind !== "ok") return [];
    if (!segmentGeometry) return [];
    if (segmentGeometry.sortedAnchors.length < 2) return [];
    const out: Array<{
      segment: PdfStationSegment;
      subpath: PdfPoint[];
      midpoint: PdfPoint | null;
      computable: boolean;
    }> = [];
    for (const seg of segmentsState.envelope.segments) {
      const startDist = stationFtToPolylineDistance(
        seg.start_station_ft,
        segmentGeometry.sortedAnchors,
        segmentGeometry.totalLength,
      );
      const endDist = stationFtToPolylineDistance(
        seg.end_station_ft,
        segmentGeometry.sortedAnchors,
        segmentGeometry.totalLength,
      );
      if (startDist === null || endDist === null) {
        out.push({ segment: seg, subpath: [], midpoint: null, computable: false });
        continue;
      }
      const subpath = extractPolylineSubpath(
        segmentGeometry.points,
        segmentGeometry.cumLengths,
        startDist,
        endDist,
      );
      const midDist = (startDist + endDist) / 2;
      const midSubpath = extractPolylineSubpath(
        segmentGeometry.points,
        segmentGeometry.cumLengths,
        midDist,
        midDist,
      );
      const midpoint = midSubpath.length > 0 ? midSubpath[0] : null;
      out.push({ segment: seg, subpath, midpoint, computable: true });
    }
    return out;
  }, [segmentsState, segmentGeometry]);

  const segmentsRenderable = segmentGeometry !== null && segmentGeometry.sortedAnchors.length >= 2;
  const segmentsRequireAnchors =
    traceState.kind === "loaded" &&
    (!segmentGeometry || segmentGeometry.sortedAnchors.length < 2);

  // -------------------------------------------------------------------------
  // Step 3A — segment add / delete handlers
  // -------------------------------------------------------------------------

  const openAddSegment = useCallback(() => {
    setSegmentDraft({ label: "", start: "", end: "", notes: "" });
    setSegmentDraftOpen(true);
    setSegmentOpState({ kind: "idle" });
  }, []);

  const closeAddSegment = useCallback(() => {
    setSegmentDraftOpen(false);
  }, []);

  const submitSegment = useCallback(async () => {
    if (metadata.kind !== "ok") return;
    const plan = metadata.plan;
    const labelTrim = segmentDraft.label.trim();
    const startTrim = segmentDraft.start.trim();
    const endTrim = segmentDraft.end.trim();
    if (!labelTrim) {
      setSegmentOpState({ kind: "error", message: "Label is required." });
      return;
    }
    const startFt = parseStationLabel(startTrim);
    const endFt = parseStationLabel(endTrim);
    if (startFt === null) {
      setSegmentOpState({
        kind: "error",
        message: `Start station "${startTrim}" is not a valid station (use 11+60, STA 14+20, or raw feet 2047).`,
      });
      return;
    }
    if (endFt === null) {
      setSegmentOpState({
        kind: "error",
        message: `End station "${endTrim}" is not a valid station.`,
      });
      return;
    }
    setSegmentOpState({ kind: "saving" });
    try {
      const payload: PdfStationSegmentPayload = {
        label: labelTrim,
        start_station_ft: startFt,
        end_station_ft: endFt,
        start_label: startTrim,
        end_label: endTrim,
        notes: segmentDraft.notes.trim() || undefined,
      };
      const url =
        `${RENDER_BASE}/api/engineering-plans/${encodeURIComponent(plan.plan_id)}` +
        `/segments?page_index=${encodeURIComponent(String(pageIndex))}` +
        `&session_id=${encodeURIComponent(plan.session_id)}`;
      const resp = await apiFetch(
        url,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
        "pdf_plan_segment_add",
      );
      if (!resp.ok) {
        const body = (await resp.json().catch(() => null)) as
          | { error?: string }
          | null;
        setSegmentOpState({
          kind: "error",
          message: body?.error || `Add segment failed (HTTP ${resp.status}).`,
        });
        return;
      }
      const data = (await resp.json().catch(() => null)) as
        | { envelope?: PdfSegmentsEnvelope }
        | null;
      const env = data?.envelope;
      if (env) {
        setSegmentsState({ kind: "ok", envelope: env });
      }
      setSegmentOpState({ kind: "idle" });
      setSegmentDraftOpen(false);
      setSegmentDraft({ label: "", start: "", end: "", notes: "" });
    } catch (err) {
      setSegmentOpState({
        kind: "error",
        message:
          err instanceof Error ? err.message : "Unexpected error while adding segment.",
      });
    }
  }, [metadata, segmentDraft, pageIndex]);

  // -------------------------------------------------------------------------
  // Step 3B — bore-log row handlers (add/edit/delete) + Generate Segments
  // -------------------------------------------------------------------------

  const openAddRow = useCallback(() => {
    setRowDraft({
      label: "",
      start: "",
      end: "",
      depth: "",
      boc: "",
      crew: "",
      date: "",
      notes: "",
    });
    setRowDraftOpen(true);
    setGenerateOpState({ kind: "idle" });
  }, []);

  const closeAddRow = useCallback(() => {
    setRowDraftOpen(false);
  }, []);

  const submitRow = useCallback(() => {
    const labelTrim = rowDraft.label.trim();
    const startTrim = rowDraft.start.trim();
    const endTrim = rowDraft.end.trim();
    if (!labelTrim) {
      setGenerateOpState({
        kind: "idle",
        message: "Row label is required.",
        tone: "error",
      });
      return;
    }
    const startFt = parseStationLabel(startTrim);
    const endFt = parseStationLabel(endTrim);
    if (startFt === null) {
      setGenerateOpState({
        kind: "idle",
        message: `Start station "${startTrim}" is not a valid station (use 11+60, STA 14+20, or raw feet).`,
        tone: "error",
      });
      return;
    }
    if (endFt === null) {
      setGenerateOpState({
        kind: "idle",
        message: `End station "${endTrim}" is not a valid station.`,
        tone: "error",
      });
      return;
    }
    const newRow: BoreLogRow = {
      row_id: generateAnchorId(),
      label: labelTrim,
      start_label: startTrim,
      end_label: endTrim,
      depth: rowDraft.depth.trim() || undefined,
      boc: rowDraft.boc.trim() || undefined,
      crew: rowDraft.crew.trim() || undefined,
      date: rowDraft.date.trim() || undefined,
      notes: rowDraft.notes.trim() || undefined,
      created_at: new Date().toISOString(),
    };
    setBoreLogRows((prev) => [...prev, newRow]);
    setRowDraftOpen(false);
    setRowDraft({
      label: "",
      start: "",
      end: "",
      depth: "",
      boc: "",
      crew: "",
      date: "",
      notes: "",
    });
    setGenerateOpState({
      kind: "idle",
      message: `Row "${labelTrim}" added. Click Generate Segments to render it on the PDF.`,
      tone: "info",
    });
  }, [rowDraft]);

  const deleteRow = useCallback((rowId: string) => {
    setBoreLogRows((prev) => prev.filter((r) => r.row_id !== rowId));
    setGenerateOpState({ kind: "idle" });
  }, []);

  // Step 3C — Excel bore-log import.  Frontend-only: parses each .xlsx in
  // the browser, aggregates to one Step 3B row per workbook, and appends
  // to the current page's row list.  Backend unchanged — the existing
  // Generate Segments handler will POST these rows like any other.
  const handleImportExcel = useCallback(async (files: FileList | File[]) => {
    const fileArr = Array.from(files);
    if (fileArr.length === 0) return;
    setGenerateOpState({
      kind: "running",
      message: `Importing ${fileArr.length} file${fileArr.length === 1 ? "" : "s"}…`,
      tone: "info",
    });
    let outcomes: ImportFileOutcome[];
    try {
      outcomes = await importBoreLogExcelBatch(fileArr);
    } catch (err) {
      setGenerateOpState({
        kind: "idle",
        message: `Excel import failed: ${err instanceof Error ? err.message : String(err)}`,
        tone: "error",
      });
      return;
    }
    const newRows: BoreLogRow[] = [];
    const skipped: Array<{ filename: string; reason: string }> = [];
    const errored: Array<{ filename: string; reason: string }> = [];
    const nowIso = new Date().toISOString();
    for (const out of outcomes) {
      if (out.kind === "ok") {
        newRows.push({
          row_id: generateAnchorId(),
          created_at: nowIso,
          ...out.row_spec,
        });
      } else if (out.kind === "skipped") {
        skipped.push({ filename: out.filename, reason: out.reason });
      } else {
        errored.push({ filename: out.filename, reason: out.reason });
      }
    }
    if (newRows.length > 0) {
      setBoreLogRows((prev) => [...prev, ...newRows]);
    }
    const parts: string[] = [];
    parts.push(
      `Imported ${newRows.length} row${newRows.length === 1 ? "" : "s"} from ${fileArr.length} file${fileArr.length === 1 ? "" : "s"}.`,
    );
    if (skipped.length > 0) {
      parts.push(
        `${skipped.length} skipped: ${skipped
          .slice(0, 3)
          .map((s) => `${s.filename} (${s.reason})`)
          .join("; ")}${skipped.length > 3 ? "; …" : ""}`,
      );
    }
    if (errored.length > 0) {
      parts.push(
        `${errored.length} failed: ${errored
          .slice(0, 3)
          .map((e) => `${e.filename} (${e.reason})`)
          .join("; ")}${errored.length > 3 ? "; …" : ""}`,
      );
    }
    if (newRows.length > 0) {
      parts.push("Click Generate Segments to render them as redlines.");
    }
    setGenerateOpState({
      kind: "idle",
      message: parts.join(" "),
      tone:
        errored.length > 0
          ? "error"
          : skipped.length > 0
          ? "warn"
          : newRows.length > 0
          ? "success"
          : "info",
    });
  }, []);

  const clearAllRows = useCallback(() => {
    if (boreLogRows.length === 0) return;
    if (
      typeof window !== "undefined" &&
      !window.confirm(
        `Clear all ${boreLogRows.length} bore-log row(s)? This does NOT delete any segments already generated from them.`,
      )
    ) {
      return;
    }
    setBoreLogRows([]);
    setGenerateOpState({ kind: "idle" });
  }, [boreLogRows.length]);

  const generateSegmentsFromRows = useCallback(async () => {
    if (metadata.kind !== "ok") return;
    if (boreLogRows.length === 0) {
      setGenerateOpState({
        kind: "idle",
        message: "No rows to generate from. Add at least one bore-log row first.",
        tone: "warn",
      });
      return;
    }
    if (!segmentsRenderable) {
      setGenerateOpState({
        kind: "idle",
        message: "Save a trace + at least 2 station anchors before generating segments.",
        tone: "warn",
      });
      return;
    }
    const plan = metadata.plan;
    setGenerateOpState({ kind: "running" });

    // Build a set of currently-saved segments to detect duplicates
    // server-side rejects (label + start + end identical) so we can
    // report which rows were already present.
    const generated: BoreLogRow[] = [];
    const duplicates: BoreLogRow[] = [];
    const errors: Array<{ row: BoreLogRow; message: string }> = [];
    let latestEnvelope: PdfSegmentsEnvelope | null = null;

    for (const row of boreLogRows) {
      const startFt = parseStationLabel(row.start_label);
      const endFt = parseStationLabel(row.end_label);
      if (startFt === null || endFt === null) {
        errors.push({
          row,
          message: `Unparseable station on row "${row.label}".`,
        });
        continue;
      }
      const sourceMetadata: Record<string, string> = {};
      // Step 3C — start with import metadata (filename, print, point_readings, etc.)
      // so subsequent per-field row values override matching keys.  This lets the
      // operator edit the row inline after import and have those edits win on the
      // generated segment.
      if (row.import_metadata) {
        Object.assign(sourceMetadata, row.import_metadata);
      }
      if (row.depth) sourceMetadata.depth = row.depth;
      if (row.boc) sourceMetadata.boc = row.boc;
      if (row.crew) sourceMetadata.crew = row.crew;
      if (row.date) sourceMetadata.date = row.date;
      sourceMetadata.row_id = row.row_id;
      const payload: PdfStationSegmentPayload = {
        label: row.label,
        start_station_ft: startFt,
        end_station_ft: endFt,
        start_label: row.start_label,
        end_label: row.end_label,
        notes: row.notes,
        source: "bore_log_row",
        source_metadata: sourceMetadata,
      };
      try {
        const url =
          `${RENDER_BASE}/api/engineering-plans/${encodeURIComponent(plan.plan_id)}` +
          `/segments?page_index=${encodeURIComponent(String(pageIndex))}` +
          `&session_id=${encodeURIComponent(plan.session_id)}`;
        const resp = await apiFetch(
          url,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          },
          "pdf_plan_segment_generate_from_row",
        );
        if (resp.ok) {
          const data = (await resp.json().catch(() => null)) as
            | { envelope?: PdfSegmentsEnvelope }
            | null;
          if (data?.envelope) {
            latestEnvelope = data.envelope;
            const matched = data.envelope.segments.find(
              (s) =>
                s.label === row.label &&
                Math.abs(s.start_station_ft - startFt) < 1e-6 &&
                Math.abs(s.end_station_ft - endFt) < 1e-6,
            );
            generated.push({
              ...row,
              last_generated_segment_id: matched?.segment_id,
              last_generated_at: new Date().toISOString(),
            });
          } else {
            generated.push(row);
          }
        } else {
          const body = (await resp.json().catch(() => null)) as
            | { error?: string }
            | null;
          const errMsg = body?.error || `HTTP ${resp.status}`;
          if (errMsg.toLowerCase().includes("already exists")) {
            duplicates.push(row);
          } else {
            errors.push({ row, message: errMsg });
          }
        }
      } catch (err) {
        errors.push({
          row,
          message: err instanceof Error ? err.message : "Unexpected error",
        });
      }
    }

    // Update row records with last_generated_segment_id stamps.
    if (generated.length > 0) {
      const generatedIds = new Set(generated.map((g) => g.row_id));
      setBoreLogRows((prev) =>
        prev.map((r) => {
          const g = generated.find((x) => x.row_id === r.row_id);
          return generatedIds.has(r.row_id) && g
            ? {
                ...r,
                last_generated_segment_id: g.last_generated_segment_id,
                last_generated_at: g.last_generated_at,
              }
            : r;
        }),
      );
    }
    if (latestEnvelope) {
      setSegmentsState({ kind: "ok", envelope: latestEnvelope });
    }

    const parts: string[] = [];
    parts.push(
      `Generated ${generated.length} PDF redline segment${generated.length === 1 ? "" : "s"} from bore-log-style row${generated.length === 1 ? "" : "s"}.`,
    );
    if (duplicates.length > 0) {
      parts.push(
        `${duplicates.length} row${duplicates.length === 1 ? " was" : "s were"} skipped because an identical segment (same label + start + end) already exists.`,
      );
    }
    if (errors.length > 0) {
      parts.push(
        `${errors.length} row${errors.length === 1 ? "" : "s"} could not be generated: ${errors
          .slice(0, 3)
          .map((e) => `"${e.row.label}" (${e.message})`)
          .join("; ")}`,
      );
    }
    setGenerateOpState({
      kind: "idle",
      message: parts.join(" "),
      tone:
        errors.length > 0
          ? "error"
          : duplicates.length > 0
          ? "warn"
          : generated.length > 0
          ? "success"
          : "info",
    });
  }, [metadata, boreLogRows, segmentsRenderable, pageIndex]);

  const deleteSegmentById = useCallback(
    async (segmentId: string) => {
      if (metadata.kind !== "ok") return;
      const plan = metadata.plan;
      if (
        typeof window !== "undefined" &&
        !window.confirm("Delete this manual station segment? This cannot be undone.")
      ) {
        return;
      }
      setSegmentOpState({ kind: "saving" });
      try {
        const url =
          `${RENDER_BASE}/api/engineering-plans/${encodeURIComponent(plan.plan_id)}` +
          `/segments/${encodeURIComponent(segmentId)}` +
          `?page_index=${encodeURIComponent(String(pageIndex))}` +
          `&session_id=${encodeURIComponent(plan.session_id)}`;
        const resp = await apiFetch(url, { method: "DELETE" }, "pdf_plan_segment_delete");
        if (!resp.ok) {
          const body = (await resp.json().catch(() => null)) as
            | { error?: string }
            | null;
          setSegmentOpState({
            kind: "error",
            message: body?.error || `Delete segment failed (HTTP ${resp.status}).`,
          });
          return;
        }
        const data = (await resp.json().catch(() => null)) as
          | { envelope?: PdfSegmentsEnvelope }
          | null;
        const env = data?.envelope;
        if (env) {
          setSegmentsState({ kind: "ok", envelope: env });
        }
        setSegmentOpState({ kind: "idle" });
      } catch (err) {
        setSegmentOpState({
          kind: "error",
          message:
            err instanceof Error
              ? err.message
              : "Unexpected error while deleting segment.",
        });
      }
    },
    [metadata, pageIndex],
  );

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

      {/* Step 3B — bore-log-style rows panel (drives segment generation) */}
      {metadata.kind === "ok" && pageState.kind === "ready" && (
        <BoreLogRowsPanel
          rows={boreLogRows}
          rowDraftOpen={rowDraftOpen}
          rowDraft={rowDraft}
          generateOpState={generateOpState}
          segmentsRenderable={segmentsRenderable}
          traceState={traceState}
          onOpenAddRow={openAddRow}
          onCloseAddRow={closeAddRow}
          onRowDraftChange={setRowDraft}
          onSubmitRow={submitRow}
          onDeleteRow={deleteRow}
          onClearAll={clearAllRows}
          onGenerate={generateSegmentsFromRows}
          onImportFiles={handleImportExcel}
        />
      )}

      {/* Step 3A — manual station segments panel */}
      {metadata.kind === "ok" && pageState.kind === "ready" && (
        <SegmentsPanel
          segmentsState={segmentsState}
          segmentOpState={segmentOpState}
          traceState={traceState}
          segmentsRenderable={segmentsRenderable}
          segmentsRequireAnchors={segmentsRequireAnchors}
          renderable={renderableSegments}
          draftOpen={segmentDraftOpen}
          draft={segmentDraft}
          onDraftChange={setSegmentDraft}
          onOpenAdd={openAddSegment}
          onCloseAdd={closeAddSegment}
          onSubmit={submitSegment}
          onDelete={deleteSegmentById}
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
              renderableSegments={renderableSegments}
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
            PDF Plan Viewer · Steps 1 + 2A + 2B + 3A.1 (operator-traced; station
            anchors calibrate the trace; manual segments draw redline ranges;
            suggestion-grade page classifications)
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
  renderableSegments,
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
  renderableSegments: Array<{
    segment: PdfStationSegment;
    subpath: PdfPoint[];
    midpoint: PdfPoint | null;
    computable: boolean;
  }>;
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
          {/* Trace polyline — muted underlay when segments are present so
               the segment overlay reads as the dominant redline.  Stays
               brighter during active tracing so the operator can see what
               they're drawing. */}
          {pathD && (
            <path
              d={pathD}
              fill="none"
              stroke="#1d4ed8"
              strokeWidth={
                editMode === "tracing"
                  ? Math.max(2.5, renderedDimensions.w / 380)
                  : Math.max(1.5, renderedDimensions.w / 540)
              }
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity={
                editMode === "tracing"
                  ? 0.85
                  : renderableSegments.some((s) => s.computable && s.subpath.length >= 2)
                  ? 0.45
                  : 0.85
              }
              strokeDasharray={
                editMode === "tracing"
                  ? undefined
                  : renderableSegments.some((s) => s.computable && s.subpath.length >= 2)
                  ? `${Math.max(6, renderedDimensions.w / 200)} ${Math.max(4, renderedDimensions.w / 320)}`
                  : undefined
              }
            />
          )}
          {/* Vertex dots */}
          {draftPoints.map((pt, i) => (
            <circle
              key={`vertex-${i}`}
              cx={pt[0]}
              cy={pt[1]}
              r={Math.max(3, renderedDimensions.w / 360)}
              fill="#ffffff"
              stroke="#1d4ed8"
              strokeWidth={Math.max(1.2, renderedDimensions.w / 800)}
              opacity={
                editMode === "tracing"
                  ? 1
                  : renderableSegments.some((s) => s.computable && s.subpath.length >= 2)
                  ? 0.55
                  : 1
              }
            />
          ))}
          {/* Step 3A.1 — manual station segments rendered as bold red
               overlays on top of the (now muted) operator trace.  Three
               layers per segment for contractor-redline legibility on
               busy plan sheets:
                 1. wide white halo (knocks out the busy background)
                 2. bold red core stroke (the actual redline)
                 3. red round endcaps at start + end (clear bounds)
               Labels are drawn perpendicular-offset from the segment
               midpoint with a thin red leader line, so the geometry
               itself stays visible underneath the label.  Label box
               sizes are based on actual character count for readability
               at any page width. */}
          {renderableSegments.map(({ segment, subpath, midpoint, computable }) => {
            if (!computable || subpath.length < 2) return null;
            const segPath = buildPolylinePath(subpath);
            // Bolder core stroke — scales with page width but with a
            // firmer floor so even at small zooms the redline reads.
            const coreStroke = Math.max(8, renderedDimensions.w / 130);
            // Halo wider than core so it always shows around the edges.
            const haloStroke = coreStroke + Math.max(5, renderedDimensions.w / 240);
            // Endcap radius — slightly larger than half the core stroke
            // so the cap visually clamps the segment ends.
            const endcapR = coreStroke * 0.62;

            // Perpendicular offset for the label based on the chord
            // direction (subpath start -> end).  Falls back to "above"
            // when the chord is too short to derive a stable normal.
            const start = subpath[0];
            const end = subpath[subpath.length - 1];
            const chordDx = end[0] - start[0];
            const chordDy = end[1] - start[1];
            const chordLen = Math.sqrt(chordDx * chordDx + chordDy * chordDy);
            let nx = 0;
            let ny = -1;
            if (chordLen > 1e-3) {
              // Perpendicular to chord; default to the side with smaller
              // y (toward the top of the page) so labels stack predictably.
              const rawNx = -chordDy / chordLen;
              const rawNy = chordDx / chordLen;
              if (rawNy <= 0) {
                nx = rawNx;
                ny = rawNy;
              } else {
                nx = -rawNx;
                ny = -rawNy;
              }
            }
            const labelOffset = Math.max(34, renderedDimensions.w / 48);

            // Label box sizing — proportional to character count + page
            // width.  Conservative width estimate for monospace-like
            // proportional fonts.
            const labelText = segment.label;
            const fontPx = Math.max(11, renderedDimensions.w / 110);
            const charPx = fontPx * 0.58;
            const padX = fontPx * 0.7;
            const padY = fontPx * 0.32;
            const boxW = labelText.length * charPx + padX * 2;
            const boxH = fontPx + padY * 2;
            const labelMidX = midpoint ? midpoint[0] + nx * labelOffset : 0;
            const labelMidY = midpoint ? midpoint[1] + ny * labelOffset : 0;

            return (
              <g key={`seg-${segment.segment_id}`}>
                {/* (1) white halo */}
                <path
                  d={segPath}
                  fill="none"
                  stroke="#ffffff"
                  strokeWidth={haloStroke}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  opacity={0.85}
                />
                {/* (2) bold red core */}
                <path
                  d={segPath}
                  fill="none"
                  stroke="#dc2626"
                  strokeWidth={coreStroke}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  opacity={0.96}
                />
                {/* (3) red endcaps at the start + end of the segment */}
                <circle
                  cx={start[0]}
                  cy={start[1]}
                  r={endcapR}
                  fill="#b91c1c"
                  stroke="#ffffff"
                  strokeWidth={Math.max(1.5, renderedDimensions.w / 720)}
                  opacity={0.98}
                />
                <circle
                  cx={end[0]}
                  cy={end[1]}
                  r={endcapR}
                  fill="#b91c1c"
                  stroke="#ffffff"
                  strokeWidth={Math.max(1.5, renderedDimensions.w / 720)}
                  opacity={0.98}
                />
                {midpoint && (
                  <g pointerEvents="none">
                    {/* leader line from segment midpoint to label centre */}
                    <line
                      x1={midpoint[0]}
                      y1={midpoint[1]}
                      x2={labelMidX}
                      y2={labelMidY}
                      stroke="#b91c1c"
                      strokeWidth={Math.max(1, renderedDimensions.w / 700)}
                      strokeDasharray={`${Math.max(2, renderedDimensions.w / 720)} ${Math.max(2, renderedDimensions.w / 720)}`}
                      opacity={0.7}
                    />
                    {/* label pill */}
                    <rect
                      x={labelMidX - boxW / 2}
                      y={labelMidY - boxH / 2}
                      width={boxW}
                      height={boxH}
                      rx={Math.max(3, fontPx * 0.3)}
                      ry={Math.max(3, fontPx * 0.3)}
                      fill="#ffffff"
                      stroke="#b91c1c"
                      strokeWidth={Math.max(1.2, renderedDimensions.w / 720)}
                      opacity={0.96}
                    />
                    <text
                      x={labelMidX}
                      y={labelMidY + fontPx * 0.34}
                      textAnchor="middle"
                      fill="#b91c1c"
                      fontSize={fontPx}
                      fontWeight={700}
                      fontFamily="ui-sans-serif, system-ui, sans-serif"
                    >
                      {labelText}
                    </text>
                  </g>
                )}
              </g>
            );
          })}
          {/* Station anchors — small diamond markers + station label.
               Visually subdued vs. segment redlines (Step 3A.1): smaller
               size, dark-amber color (distinct from segment red), label
               offset above the diamond.  Clear visual hierarchy:
                 - bold red lines  = redline segments (operator output)
                 - amber diamonds  = station anchors (calibration points)
                 - blue trace      = operator-drawn route (calibration spine)
               This keeps "what is the redline" unambiguous on a busy
               plan sheet. */}
          {draftAnchors.map((a) => {
            // Diamond size — half the previous circle, more compact.
            const r = Math.max(4, renderedDimensions.w / 360);
            const fontPx = Math.max(10, renderedDimensions.w / 130);
            // Diamond points (rotated square)
            const diamond = [
              `${a.point[0]},${a.point[1] - r}`,
              `${a.point[0] + r},${a.point[1]}`,
              `${a.point[0]},${a.point[1] + r}`,
              `${a.point[0] - r},${a.point[1]}`,
            ].join(" ");
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
                <polygon
                  points={diamond}
                  fill="#b45309"
                  stroke="#ffffff"
                  strokeWidth={Math.max(1, renderedDimensions.w / 800)}
                />
                <text
                  x={a.point[0]}
                  y={a.point[1] - r - Math.max(4, fontPx * 0.3)}
                  textAnchor="middle"
                  fill="#92400e"
                  fontSize={fontPx}
                  fontWeight={600}
                  fontFamily="ui-sans-serif, system-ui, sans-serif"
                  style={{
                    paintOrder: "stroke",
                    stroke: "#ffffff",
                    strokeWidth: Math.max(2, renderedDimensions.w / 540),
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
      {/* Step 3A.1 — help line explaining anchors vs segments visually. */}
      <div
        style={{
          maxWidth: 1600,
          margin: "4px auto 0",
          fontSize: 11,
          color: "var(--tl-text-faint)",
          lineHeight: 1.45,
          fontStyle: "italic",
        }}
      >
        <span style={{ color: "#1d4ed8", fontWeight: 600, fontStyle: "normal" }}>
          Trace
        </span>
        {" "}is the blue route you draw on the plan sheet.{" "}
        <span style={{ color: "#b45309", fontWeight: 600, fontStyle: "normal" }}>
          Station anchors
        </span>
        {" "}are amber diamonds you place on the trace at known station values
        (e.g. 16+79, 19+54) — they calibrate the trace&rsquo;s station scale.
        Add at least 2 anchors before defining segments.
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

function boreLogRowsStorageKey(planId: string, pageIndex: number): string {
  return `pdf_plan_bore_rows:${planId}:p${pageIndex}`;
}

function emptySegmentsEnvelope(
  planId: string,
  sessionId: string,
  pageIndex: number,
): PdfSegmentsEnvelope {
  const now = new Date().toISOString();
  return {
    schema_version: "pdf-plan-segments-1",
    plan_id: planId,
    session_id: sessionId,
    page_index: pageIndex,
    trace_id: null,
    segments: [],
    created_at: now,
    updated_at: now,
  };
}

// ───────────────────────────────────────────────────────────────────────────
// Step 3A — manual station segments panel
// ───────────────────────────────────────────────────────────────────────────

function SegmentsPanel({
  segmentsState,
  segmentOpState,
  traceState,
  segmentsRenderable,
  segmentsRequireAnchors,
  renderable,
  draftOpen,
  draft,
  onDraftChange,
  onOpenAdd,
  onCloseAdd,
  onSubmit,
  onDelete,
}: {
  segmentsState: SegmentsState;
  segmentOpState: SegmentOpState;
  traceState: TraceState;
  segmentsRenderable: boolean;
  segmentsRequireAnchors: boolean;
  renderable: Array<{
    segment: PdfStationSegment;
    subpath: PdfPoint[];
    midpoint: PdfPoint | null;
    computable: boolean;
  }>;
  draftOpen: boolean;
  draft: { label: string; start: string; end: string; notes: string };
  onDraftChange: (
    d: { label: string; start: string; end: string; notes: string },
  ) => void;
  onOpenAdd: () => void;
  onCloseAdd: () => void;
  onSubmit: () => void;
  onDelete: (segmentId: string) => void;
}) {
  const traceLoaded = traceState.kind === "loaded";
  const segmentsCount =
    segmentsState.kind === "ok" ? segmentsState.envelope.segments.length : 0;
  const disabled =
    segmentsState.kind === "disabled" || segmentsState.kind === "loading";
  const addDisabled =
    disabled || !traceLoaded || !segmentsRenderable || segmentOpState.kind === "saving";

  const headerMessage = (() => {
    if (segmentsState.kind === "loading") return "Loading segments…";
    if (segmentsState.kind === "disabled")
      return "Manual segments are disabled on the backend.";
    if (segmentsState.kind === "error") return segmentsState.message;
    if (!traceLoaded)
      return "Save a trace + at least 2 station anchors to enable manual segments.";
    if (segmentsRequireAnchors)
      return "Add at least 2 station anchors via the trace toolbar to enable manual segments.";
    if (segmentsCount === 0)
      return "No manual segments yet. Click + Add Segment to map a station range to the trace.";
    return `${segmentsCount} manual segment${segmentsCount === 1 ? "" : "s"} on this page (draft — manual entries until bore-log import).`;
  })();
  const headerTone: "info" | "warn" | "error" = (() => {
    if (segmentsState.kind === "error") return "error";
    if (
      segmentsState.kind === "disabled" ||
      !traceLoaded ||
      segmentsRequireAnchors
    )
      return "warn";
    return "info";
  })();
  const headerColor =
    headerTone === "error"
      ? "#dc2626"
      : headerTone === "warn"
      ? "#92400e"
      : "var(--tl-text-muted)";

  return (
    <div
      style={{
        padding: "8px 22px",
        borderBottom: "1px solid var(--tl-border)",
        background: "var(--tl-surface)",
      }}
    >
      <div
        style={{
          maxWidth: 1600,
          margin: "0 auto",
          display: "flex",
          flexDirection: "column",
          gap: 8,
          fontSize: 12,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            flexWrap: "wrap",
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
            Station Segments
          </span>
          <span
            style={{
              fontSize: 10,
              padding: "2px 6px",
              background: "rgba(220, 38, 38, 0.10)",
              color: "#b91c1c",
              border: "1px solid rgba(220, 38, 38, 0.30)",
              borderRadius: 4,
              fontWeight: 700,
              letterSpacing: "0.04em",
              textTransform: "uppercase",
            }}
          >
            Manual / Draft
          </span>
          <ToolbarButton
            onClick={onOpenAdd}
            disabled={addDisabled}
            variant="primary"
            title="Enter start/end stations to draw a draft segment along the saved trace"
          >
            + Add Segment
          </ToolbarButton>
          <span
            role="status"
            style={{
              color: headerColor,
              fontWeight: 500,
              fontSize: 12,
              flex: 1,
              minWidth: 240,
              textAlign: "right",
            }}
          >
            {headerMessage}
          </span>
        </div>

        {/* Step 3A.1 — help line explaining segments. */}
        <div
          style={{
            fontSize: 11,
            color: "var(--tl-text-faint)",
            lineHeight: 1.45,
            fontStyle: "italic",
          }}
        >
          <span style={{ color: "#b91c1c", fontWeight: 600, fontStyle: "normal" }}>
            Station segments
          </span>
          {" "}mark redline ranges along the calibrated trace. Example: with
          anchors at 16+79 and 19+54 on the trace, add a segment{" "}
          <span style={{ fontWeight: 600, fontStyle: "normal" }}>
            &ldquo;Bore 1&rdquo; from 16+79 to 19+54
          </span>
          {" "}— it will render as a bold red line covering exactly that 275 ft
          of the trace. Segment list below is the source of truth; the on-PDF
          drawing is the visual derivative.
        </div>

        {draftOpen && (
          <SegmentDraftForm
            draft={draft}
            onChange={onDraftChange}
            onSubmit={onSubmit}
            onCancel={onCloseAdd}
            opState={segmentOpState}
          />
        )}

        {segmentsState.kind === "ok" && segmentsCount > 0 && (
          <ol
            style={{
              listStyle: "none",
              padding: 0,
              margin: 0,
              display: "grid",
              gap: 4,
              borderTop: "1px solid var(--tl-border)",
              paddingTop: 8,
            }}
          >
            {segmentsState.envelope.segments.map((seg) => {
              const computed = renderable.find(
                (r) => r.segment.segment_id === seg.segment_id,
              );
              const isComputable = computed?.computable ?? segmentsRenderable;
              return (
                <li key={seg.segment_id}>
                  <SegmentListEntry
                    segment={seg}
                    computable={isComputable}
                    onDelete={onDelete}
                  />
                </li>
              );
            })}
          </ol>
        )}

        {segmentOpState.kind === "error" && !draftOpen && (
          <div
            style={{
              fontSize: 11,
              color: "#dc2626",
              background: "rgba(220, 38, 38, 0.06)",
              border: "1px solid rgba(220, 38, 38, 0.25)",
              borderRadius: 6,
              padding: "6px 10px",
            }}
          >
            {segmentOpState.message}
          </div>
        )}
      </div>
    </div>
  );
}

function SegmentDraftForm({
  draft,
  onChange,
  onSubmit,
  onCancel,
  opState,
}: {
  draft: { label: string; start: string; end: string; notes: string };
  onChange: (
    d: { label: string; start: string; end: string; notes: string },
  ) => void;
  onSubmit: () => void;
  onCancel: () => void;
  opState: SegmentOpState;
}) {
  const submitting = opState.kind === "saving";
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!submitting) onSubmit();
      }}
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr 1fr 2fr auto auto",
        gap: 6,
        alignItems: "end",
        padding: "8px",
        border: "1px solid rgba(29, 78, 216, 0.30)",
        borderRadius: 8,
        background: "rgba(29, 78, 216, 0.04)",
      }}
    >
      <SegmentField
        label="Label"
        value={draft.label}
        placeholder="e.g. Bore 1"
        onChange={(v) => onChange({ ...draft, label: v })}
        autoFocus
        disabled={submitting}
      />
      <SegmentField
        label="Start station"
        value={draft.start}
        placeholder="11+60"
        onChange={(v) => onChange({ ...draft, start: v })}
        disabled={submitting}
      />
      <SegmentField
        label="End station"
        value={draft.end}
        placeholder="14+20"
        onChange={(v) => onChange({ ...draft, end: v })}
        disabled={submitting}
      />
      <SegmentField
        label="Notes (optional)"
        value={draft.notes}
        placeholder="Crew, date, scope, …"
        onChange={(v) => onChange({ ...draft, notes: v })}
        disabled={submitting}
      />
      <ToolbarButton
        onClick={onSubmit}
        disabled={submitting}
        variant="primary"
      >
        {submitting ? "Saving…" : "Save Segment"}
      </ToolbarButton>
      <ToolbarButton onClick={onCancel} disabled={submitting} variant="ghost">
        Cancel
      </ToolbarButton>
      {opState.kind === "error" && (
        <div
          style={{
            gridColumn: "1 / -1",
            fontSize: 11,
            color: "#dc2626",
          }}
        >
          {opState.message}
        </div>
      )}
    </form>
  );
}

function SegmentField({
  label,
  value,
  placeholder,
  onChange,
  autoFocus,
  disabled,
}: {
  label: string;
  value: string;
  placeholder?: string;
  onChange: (value: string) => void;
  autoFocus?: boolean;
  disabled?: boolean;
}) {
  return (
    <label
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 2,
        fontSize: 11,
        color: "var(--tl-text-muted)",
        fontWeight: 600,
      }}
    >
      {label}
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoFocus={autoFocus}
        disabled={disabled}
        style={{
          padding: "5px 8px",
          fontSize: 12,
          borderRadius: 6,
          border: "1px solid #cbd5e1",
          background: disabled ? "#f1f5f9" : "#ffffff",
          color: "var(--tl-text)",
          fontFamily: "inherit",
        }}
      />
    </label>
  );
}

// ───────────────────────────────────────────────────────────────────────────
// Step 3B — bore-log-style rows panel
// ───────────────────────────────────────────────────────────────────────────

function BoreLogRowsPanel({
  rows,
  rowDraftOpen,
  rowDraft,
  generateOpState,
  segmentsRenderable,
  traceState,
  onOpenAddRow,
  onCloseAddRow,
  onRowDraftChange,
  onSubmitRow,
  onDeleteRow,
  onClearAll,
  onGenerate,
  onImportFiles,
}: {
  rows: BoreLogRow[];
  rowDraftOpen: boolean;
  rowDraft: {
    label: string;
    start: string;
    end: string;
    depth: string;
    boc: string;
    crew: string;
    date: string;
    notes: string;
  };
  generateOpState: {
    kind: "idle" | "running";
    message?: string;
    tone?: "info" | "success" | "warn" | "error";
  };
  segmentsRenderable: boolean;
  traceState: TraceState;
  onOpenAddRow: () => void;
  onCloseAddRow: () => void;
  onRowDraftChange: (d: {
    label: string;
    start: string;
    end: string;
    depth: string;
    boc: string;
    crew: string;
    date: string;
    notes: string;
  }) => void;
  onSubmitRow: () => void;
  onDeleteRow: (rowId: string) => void;
  onClearAll: () => void;
  onGenerate: () => void;
  /** Step 3C — fires when the operator picks one or more .xlsx files. */
  onImportFiles: (files: FileList | File[]) => void;
}) {
  const importInputRef = useRef<HTMLInputElement>(null);
  const onImportClick = useCallback(() => {
    importInputRef.current?.click();
  }, []);
  const onImportChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (files && files.length > 0) {
        onImportFiles(files);
      }
      // Reset so re-picking the same file fires onChange again.
      if (importInputRef.current) {
        importInputRef.current.value = "";
      }
    },
    [onImportFiles],
  );
  const traceLoaded = traceState.kind === "loaded";
  const generateDisabled =
    rows.length === 0 ||
    !traceLoaded ||
    !segmentsRenderable ||
    generateOpState.kind === "running";

  const statusColor =
    generateOpState.tone === "error"
      ? "#dc2626"
      : generateOpState.tone === "warn"
      ? "#92400e"
      : generateOpState.tone === "success"
      ? "#047857"
      : "var(--tl-text-muted)";

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
          flexDirection: "column",
          gap: 8,
          fontSize: 12,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            flexWrap: "wrap",
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
            Bore Log Rows
          </span>
          <span
            style={{
              fontSize: 10,
              padding: "2px 6px",
              background: "rgba(180, 83, 9, 0.10)",
              color: "#92400e",
              border: "1px solid rgba(180, 83, 9, 0.30)",
              borderRadius: 4,
              fontWeight: 700,
              letterSpacing: "0.04em",
              textTransform: "uppercase",
            }}
          >
            Segment Source · Local Draft
          </span>
          <ToolbarButton
            onClick={onOpenAddRow}
            disabled={rowDraftOpen}
            variant="default"
            title="Add one bore-log-style row (label, start/end stations, optional depth/BOC/crew/date/notes)"
          >
            + Add Row
          </ToolbarButton>
          <ToolbarButton
            onClick={onImportClick}
            disabled={generateOpState.kind === "running"}
            variant="default"
            title="Step 3C — Pick one or more .xlsx bore-log files. Each workbook becomes one row (label = filename stem, start/end = first/last station, depth/BOC = max numeric, crew/date/print preserved). Parses in browser only; no upload."
          >
            Import from Excel
          </ToolbarButton>
          <input
            ref={importInputRef}
            type="file"
            accept=".xlsx"
            multiple
            onChange={onImportChange}
            style={{ display: "none" }}
            aria-hidden="true"
          />
          <ToolbarButton
            onClick={onGenerate}
            disabled={generateDisabled}
            variant="primary"
            title="POST one segment per row to /api/.../segments with source=bore_log_row. Reuses Step 3A storage + rendering."
          >
            {generateOpState.kind === "running"
              ? "Generating…"
              : `Generate Segments${rows.length > 0 ? ` (${rows.length})` : ""}`}
          </ToolbarButton>
          <ToolbarButton
            onClick={onClearAll}
            disabled={rows.length === 0 || generateOpState.kind === "running"}
            variant="ghost"
            title="Clear all rows (does NOT delete any segments already generated from them)"
          >
            Clear Rows
          </ToolbarButton>
          <span
            role="status"
            style={{
              marginLeft: "auto",
              color: statusColor,
              fontWeight: 500,
              fontSize: 12,
              maxWidth: 640,
              textAlign: "right",
              lineHeight: 1.4,
            }}
          >
            {generateOpState.message ||
              (rows.length === 0
                ? "No rows yet. + Add Row to enter bore-log-style data."
                : `${rows.length} row${rows.length === 1 ? "" : "s"} drafted. Click Generate Segments to render as redlines.`)}
          </span>
        </div>

        <div
          style={{
            fontSize: 11,
            color: "var(--tl-text-faint)",
            lineHeight: 1.45,
            fontStyle: "italic",
          }}
        >
          <span style={{ color: "#92400e", fontWeight: 600, fontStyle: "normal" }}>
            Bore-log-style rows
          </span>
          {" "}are structured operator input (label, station range, optional
          depth/BOC/crew/date/notes) that get converted into PDF redline
          segments via the same Step 3A engine. Add rows manually via{" "}
          <strong>+ Add Row</strong>, or bulk-import from .xlsx bore-log
          files via <strong>Import from Excel</strong> (one workbook = one
          row; first/last station become start/end; max depth/BOC preserved
          in metadata along with all point readings). Rows are local browser
          drafts (this page only); generated segments are the persistent
          record server-side.
        </div>

        {rowDraftOpen && (
          <BoreLogRowDraftForm
            draft={rowDraft}
            onChange={onRowDraftChange}
            onSubmit={onSubmitRow}
            onCancel={onCloseAddRow}
          />
        )}

        {rows.length > 0 && (
          <ol
            style={{
              listStyle: "none",
              padding: 0,
              margin: 0,
              display: "grid",
              gap: 4,
              borderTop: "1px solid var(--tl-border)",
              paddingTop: 8,
            }}
          >
            {rows.map((row) => (
              <li key={row.row_id}>
                <BoreLogRowEntry row={row} onDelete={onDeleteRow} />
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}

function BoreLogRowDraftForm({
  draft,
  onChange,
  onSubmit,
  onCancel,
}: {
  draft: {
    label: string;
    start: string;
    end: string;
    depth: string;
    boc: string;
    crew: string;
    date: string;
    notes: string;
  };
  onChange: (d: typeof draft) => void;
  onSubmit: () => void;
  onCancel: () => void;
}) {
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
      style={{
        display: "grid",
        gridTemplateColumns: "1.4fr 1fr 1fr 0.8fr 0.8fr 1fr 1fr 2fr auto auto",
        gap: 6,
        alignItems: "end",
        padding: "8px",
        border: "1px solid rgba(180, 83, 9, 0.30)",
        borderRadius: 8,
        background: "rgba(180, 83, 9, 0.04)",
      }}
    >
      <SegmentField
        label="Label / Bore"
        value={draft.label}
        placeholder="Bore 1"
        onChange={(v) => onChange({ ...draft, label: v })}
        autoFocus
      />
      <SegmentField
        label="Start sta."
        value={draft.start}
        placeholder="16+79"
        onChange={(v) => onChange({ ...draft, start: v })}
      />
      <SegmentField
        label="End sta."
        value={draft.end}
        placeholder="19+54"
        onChange={(v) => onChange({ ...draft, end: v })}
      />
      <SegmentField
        label="Depth"
        value={draft.depth}
        placeholder="6.0"
        onChange={(v) => onChange({ ...draft, depth: v })}
      />
      <SegmentField
        label="BOC"
        value={draft.boc}
        placeholder="8.0"
        onChange={(v) => onChange({ ...draft, boc: v })}
      />
      <SegmentField
        label="Crew"
        value={draft.crew}
        placeholder="Smith"
        onChange={(v) => onChange({ ...draft, crew: v })}
      />
      <SegmentField
        label="Date"
        value={draft.date}
        placeholder="2026-05-26"
        onChange={(v) => onChange({ ...draft, date: v })}
      />
      <SegmentField
        label="Notes (optional)"
        value={draft.notes}
        placeholder="…"
        onChange={(v) => onChange({ ...draft, notes: v })}
      />
      <ToolbarButton onClick={onSubmit} variant="primary">
        Save Row
      </ToolbarButton>
      <ToolbarButton onClick={onCancel} variant="ghost">
        Cancel
      </ToolbarButton>
    </form>
  );
}

function BoreLogRowEntry({
  row,
  onDelete,
}: {
  row: BoreLogRow;
  onDelete: (rowId: string) => void;
}) {
  const detailParts: string[] = [];
  if (row.depth) detailParts.push(`depth ${row.depth}`);
  if (row.boc) detailParts.push(`BOC ${row.boc}`);
  if (row.crew) detailParts.push(`crew ${row.crew}`);
  if (row.date) detailParts.push(row.date);
  const detailLine = detailParts.join(" · ");
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "auto 1fr auto auto auto",
        gap: 8,
        alignItems: "center",
        padding: "6px 8px",
        background: row.last_generated_segment_id
          ? "rgba(4, 120, 87, 0.04)"
          : "rgba(180, 83, 9, 0.04)",
        border: `1px solid ${
          row.last_generated_segment_id
            ? "rgba(4, 120, 87, 0.20)"
            : "rgba(180, 83, 9, 0.20)"
        }`,
        borderRadius: 6,
        fontSize: 12,
      }}
    >
      <span
        title={
          row.last_generated_segment_id
            ? "Generated as a segment"
            : "Pending — click Generate Segments to render"
        }
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: row.last_generated_segment_id ? "#059669" : "#b45309",
        }}
      />
      <div style={{ display: "flex", flexDirection: "column", gap: 1, minWidth: 0 }}>
        <span style={{ fontWeight: 700, color: "var(--tl-text)" }}>
          {row.label}
        </span>
        {(detailLine || row.notes) && (
          <span
            style={{
              fontSize: 11,
              color: "var(--tl-text-muted)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
            title={`${detailLine}${detailLine && row.notes ? " · " : ""}${row.notes || ""}`}
          >
            {detailLine && <span style={{ color: "#92400e" }}>{detailLine}</span>}
            {detailLine && row.notes && " · "}
            {row.notes}
          </span>
        )}
      </div>
      <span
        style={{
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          color: "var(--tl-text)",
          whiteSpace: "nowrap",
        }}
      >
        {row.start_label} → {row.end_label}
      </span>
      <span
        style={{
          fontSize: 10,
          padding: "2px 6px",
          borderRadius: 4,
          background: row.last_generated_segment_id
            ? "rgba(4, 120, 87, 0.12)"
            : "rgba(100, 116, 139, 0.10)",
          color: row.last_generated_segment_id ? "#047857" : "#475569",
          border: `1px solid ${
            row.last_generated_segment_id
              ? "rgba(4, 120, 87, 0.35)"
              : "rgba(100, 116, 139, 0.30)"
          }`,
          fontWeight: 700,
          letterSpacing: "0.04em",
          textTransform: "uppercase",
          whiteSpace: "nowrap",
        }}
      >
        {row.last_generated_segment_id ? "Generated" : "Pending"}
      </span>
      <ToolbarButton
        onClick={() => onDelete(row.row_id)}
        variant="danger-ghost"
        title="Delete this row (does NOT delete any segment previously generated from it)"
      >
        Delete Row
      </ToolbarButton>
    </div>
  );
}

function SegmentListEntry({
  segment,
  computable,
  onDelete,
}: {
  segment: PdfStationSegment;
  computable: boolean;
  onDelete: (segmentId: string) => void;
}) {
  const lengthFt = segment.end_station_ft - segment.start_station_ft;
  const lengthAbs = Math.abs(lengthFt);
  // Step 3B — source badge. Older segments have no source; treat as manual.
  const source = segment.source || "manual";
  const isBoreLogRow = source === "bore_log_row";
  const sourceMetadata = segment.source_metadata || {};
  const metadataParts: string[] = [];
  if (sourceMetadata.depth) metadataParts.push(`depth ${sourceMetadata.depth}`);
  if (sourceMetadata.boc) metadataParts.push(`BOC ${sourceMetadata.boc}`);
  if (sourceMetadata.crew) metadataParts.push(`crew ${sourceMetadata.crew}`);
  if (sourceMetadata.date) metadataParts.push(sourceMetadata.date);
  const metadataLine = metadataParts.join(" · ");
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "auto auto 1fr auto auto auto",
        gap: 8,
        alignItems: "center",
        padding: "6px 8px",
        background: "rgba(15, 23, 42, 0.02)",
        border: "1px solid var(--tl-border)",
        borderRadius: 6,
        fontSize: 12,
      }}
    >
      <span
        title={isBoreLogRow ? "Generated from a bore-log-style row" : "Manual segment"}
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: computable ? "#dc2626" : "#cbd5e1",
        }}
      />
      <span
        title={
          isBoreLogRow
            ? "This segment was generated from a structured bore-log-style row (Step 3B)."
            : "This segment was entered manually (Step 3A)."
        }
        style={{
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: "0.04em",
          textTransform: "uppercase",
          padding: "2px 6px",
          borderRadius: 4,
          background: isBoreLogRow ? "rgba(180, 83, 9, 0.10)" : "rgba(100, 116, 139, 0.10)",
          color: isBoreLogRow ? "#92400e" : "#475569",
          border: `1px solid ${isBoreLogRow ? "rgba(180, 83, 9, 0.35)" : "rgba(100, 116, 139, 0.30)"}`,
          whiteSpace: "nowrap",
        }}
      >
        {isBoreLogRow ? "Bore-Log Row" : "Manual"}
      </span>
      <div style={{ display: "flex", flexDirection: "column", gap: 1, minWidth: 0 }}>
        <span style={{ fontWeight: 700, color: "var(--tl-text)" }}>
          {segment.label}
        </span>
        {(segment.notes || metadataLine) && (
          <span
            style={{
              fontSize: 11,
              color: "var(--tl-text-muted)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
            title={segment.notes || metadataLine}
          >
            {metadataLine && <span style={{ color: "#92400e" }}>{metadataLine}</span>}
            {metadataLine && segment.notes && " · "}
            {segment.notes}
          </span>
        )}
      </div>
      <span
        style={{
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          color: "var(--tl-text)",
          whiteSpace: "nowrap",
        }}
      >
        {segment.start_label} → {segment.end_label}
      </span>
      <span
        style={{
          fontSize: 11,
          color: "var(--tl-text-muted)",
          whiteSpace: "nowrap",
        }}
      >
        {lengthAbs.toFixed(0)} ft
        {!computable && (
          <span
            title="Cannot render on the trace — need at least 2 station anchors."
            style={{ color: "#92400e", marginLeft: 6 }}
          >
            (no anchors)
          </span>
        )}
      </span>
      <ToolbarButton
        onClick={() => onDelete(segment.segment_id)}
        variant="danger-ghost"
        title="Delete this manual segment"
      >
        Delete
      </ToolbarButton>
    </div>
  );
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
