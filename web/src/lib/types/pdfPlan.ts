/**
 * PDF Plan Mode — shared frontend types.
 *
 * Mirrors backend schemas:
 *   - pdf-plan-index-1   (backend/app/core/pdf_plan_index.py)
 *   - pdf-plan-trace-1   (backend/app/core/pdf_plan_trace_store.py)
 *
 * Coordinates throughout are PDF-pixel coordinates at the rendered page's
 * native DPI (96 by default).  They are NOT lat/lon and do NOT depend on
 * the browser's rendered image size.
 */

// ───────────────────────────────────────────────────────────────────────────
// Step 2A — plan-set page index
// ───────────────────────────────────────────────────────────────────────────

export type PageClassification =
  | "plan_sheet"
  | "detail_sheet"
  | "cover_sheet"
  | "notes_sheet"
  | "unknown";

export type PlanIndexPage = {
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

export type PlanIndexResponse = {
  schema_version: string;
  page_count: number;
  text_extraction_available: boolean;
  pages: PlanIndexPage[];
};

// ───────────────────────────────────────────────────────────────────────────
// Step 2B — operator-traced route + station anchors
// ───────────────────────────────────────────────────────────────────────────

export type PdfPoint = [number, number]; // [x, y] in PDF-pixel coordinates

export type PdfStationAnchor = {
  anchor_id: string;
  station_ft: number;
  label: string;
  point: PdfPoint;
  created_at: string;
};

export type PdfRouteTrace = {
  schema_version: string; // "pdf-plan-trace-1"
  trace_id: string;
  plan_id: string;
  session_id: string;
  page_index: number;
  page_dpi: number;
  page_size_px: [number, number]; // [W, H]
  points: PdfPoint[];
  anchors: PdfStationAnchor[];
  created_at: string;
  updated_at: string;
};

/** Payload shape the client PUTs to /api/engineering-plans/{plan_id}/trace.
 *  Server normalizes + assigns the trace_id deterministically. */
export type PdfRouteTracePayload = {
  page_dpi: number;
  page_size_px: [number, number];
  points: PdfPoint[];
  anchors?: Array<{
    label: string;
    point: PdfPoint;
    station_ft?: number;
    anchor_id?: string;
    created_at?: string;
  }>;
};
