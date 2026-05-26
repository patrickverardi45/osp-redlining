"use client";

import type { CSSProperties } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  acceptSessionFromMutation,
  appendSessionId,
  appendSessionIdReadOnly,
  appendSessionIdToForm,
} from "@/lib/session";
import { apiFetch } from "@/lib/apiFetch";
import type { BridgedGpsPhoto } from "@/components/RedlineMap";
import { getJobById, type JobDetail, type Photo, type Session, type Station } from "@/lib/api";
import type {
  BackendState,
  KmzLineFeature,
  KmzPolygonFeature,
  KmzRenderPayloadResponse,
  RedlineSegment,
  SemanticKmz,
  StationPhoto,
  StationPoint,
} from "@/lib/types/backend";
import { formatDisplayDate } from "@/lib/format/text";

const API_BASE = "";

const EMPTY_DEFAULT_CENTER: [number, number] = [39.8283, -98.5795];
const EMPTY_DEFAULT_ZOOM = 4;

type LeafletNS = typeof import("leaflet");
type BaseStyle = "standard" | "satellite";

/** VO.2b — read-only PDF page-image overlay state injected by RedlineMap via
 *  React.cloneElement at the operationalMap render site.  When absent or
 *  `visible=false`, no overlay is rendered.  When `visible=true && planId
 *  !== null`, ModernHeroMap fetches the PNG from
 *    GET /api/engineering-plans/{plan_id}/page/{page_index}/image?dpi=<48-300>
 *  via apiFetch (Bearer auth; 401 → silent refresh + retry) and renders it on
 *  the `pdfOverlayPane` (z=150, below all operational layers).  Default OFF
 *  every session.  Backend 404 (TRUELINE_PLAN_OVERLAY_IMAGE off) and 500
 *  (page out of range) fail silently — no overlay rendered; operator self-
 *  corrects via Prev/Next page controls in the parent UI.
 *
 *  Authoritative design: wiki/sprints/visual-overlay/vo-2b-frontend-pdf-image-overlay-plan.md
 */
export type EngineeringPlanOverlayState = {
  visible: boolean;
  planId: string | null;
  pageIndex: number;
  /** Opacity ∈ [0, 0.8]; values outside this range are clamped at render time. */
  opacity: number;
  /** DPI passed to the backend page-image endpoint; valid range [48, 300]. */
  dpi: number;
};

type ModernHeroMapProps = {
  projectId?: string;
  /** Mirrors the selection of the field-submissions inbox owned by RedlineMap.
   *  When both IDs are set, this map renders the selected submission's stations
   *  as a distinct overlay. Null means "no selection". */
  selectedFieldSessionId?: string | null;
  selectedFieldJobId?: string | null;
  /** Bumped by the parent (e.g. after a successful KMZ upload in RedlineMap)
   *  to signal that /api/current-state should be refetched. The value itself
   *  is only used as an effect-dependency cache-buster — its magnitude is
   *  meaningless. Optional; defaults to 0. */
  refreshVersion?: number;
  bridgedGpsPhotos?: BridgedGpsPhoto[];
  /** Already-hydrated semantic KMZ data from the parent's current-state response.
   *  When provided, pre-fetches the render payload without requiring the user to
   *  toggle the KMZ context layer on first. */
  kmzSemantic?: SemanticKmz | null;
  /** VO.2b — PDF page-image overlay state (see type doc above). */
  engineeringPlanOverlay?: EngineeringPlanOverlayState;
};

function cleanCoords(coords: number[][] | undefined | null): Array<[number, number]> {
  if (!Array.isArray(coords)) return [];
  const out: Array<[number, number]> = [];
  for (const pt of coords) {
    if (!Array.isArray(pt) || pt.length < 2) continue;
    const lat = Number(pt[0]);
    const lon = Number(pt[1]);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
    out.push([lat, lon]);
  }
  return out;
}

// Phase 2F — mute a KMZ hex color ~55% toward slate-gray so KMZ context never
// competes with operational redlines. Pure, never throws.
function muteKmzColorMHM(hex: string | null | undefined): string {
  const fallback = "#7c8da6";
  if (!hex || !/^#[0-9a-fA-F]{6}$/.test(hex)) return fallback;
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `#${Math.round(r*0.55+148*0.45).toString(16).padStart(2,"0")}${Math.round(g*0.55+163*0.45).toString(16).padStart(2,"0")}${Math.round(b*0.55+184*0.45).toString(16).padStart(2,"0")}`;
}

// Phase 2G — derive structural subtype from folder_path and name so markers
// can be styled distinctly without backend changes. Pure function, never throws.
type KmzPointSubtype = "splice_hh"|"terminal_port_hh"|"installer_hh"|"flower_pot"|"house"|"generic_structure";
function getKmzPointSubtype(
  name: string|null|undefined,
  folderPath: string[]|null|undefined,
): KmzPointSubtype {
  const sig = [
    ...(Array.isArray(folderPath) ? folderPath : []),
    name ?? "",
  ].join(" / ").toLowerCase();
  if (sig.includes("splice hh") || sig.includes("splice loc")) return "splice_hh";
  if (sig.includes("terminal port"))                             return "terminal_port_hh";
  if (sig.includes("installer hh") || sig.includes("installer")) return "installer_hh";
  if (sig.includes("flower pot") || sig.includes("flowerpot"))   return "flower_pot";
  if (sig.includes("house"))                                     return "house";
  return "generic_structure";
}
// Marker style per subtype. All are deliberately muted/small so they don't
// compete with operational redlines or station markers.
// Phase 2J: subtype visual hierarchy — splice_hh most prominent, house most subdued.
const KMZ_POINT_STYLES: Record<KmzPointSubtype, { fillColor:string; color:string; radius:number; fillOpacity:number; weight:number }> = {
  splice_hh:        { fillColor:"#c2344a", color:"rgba(15,23,42,0.85)", radius:5.5, fillOpacity:0.82, weight:1.4 },
  terminal_port_hh: { fillColor:"#2f7fbc", color:"rgba(15,23,42,0.80)", radius:5.0, fillOpacity:0.75, weight:1.2 },
  installer_hh:     { fillColor:"#c27a1a", color:"rgba(15,23,42,0.75)", radius:4.5, fillOpacity:0.68, weight:1.1 },
  flower_pot:       { fillColor:"#3a9455", color:"rgba(15,23,42,0.70)", radius:4.0, fillOpacity:0.60, weight:1.0 },
  house:            { fillColor:"#5a6374", color:"rgba(15,23,42,0.55)", radius:2.6, fillOpacity:0.38, weight:0.7 },
  generic_structure:{ fillColor:"#6e7e96", color:"rgba(15,23,42,0.55)", radius:2.8, fillOpacity:0.42, weight:0.8 },
};

// ─── Phase 2I: SVG engineering glyph system ─────────────────────────────────
// Inline SVG glyphs (24x24 viewBox) for recognizable telecom node symbols.
// Colors are applied per-subtype at render time via fill substitution.

type KmzGlyphKind = "triangle" | "square" | "diamond" | "house" | "flower" | "circle";

/** Build a 24×24 inline SVG string with the given fill color (14px rendered). */
function _kmzSvg(path: string, fillColor: string, fillOpacity = 0.72): string {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="14" height="14"><path d="${path}" fill="${fillColor}" fill-opacity="${fillOpacity}" stroke="rgba(15,23,42,0.75)" stroke-width="1"/></svg>`;
}

const _KMZ_GLYPH_PATHS: Record<KmzGlyphKind, string> = {
  // Upward-pointing triangle — Terminal Port Handhole
  triangle: "M12 3 L21 21 L3 21 Z",
  // Filled square — Installer HH / Splice HH
  square: "M3 3 H21 V21 H3 Z",
  // Rotated square (diamond) — Reel / slack
  diamond: "M12 2 L22 12 L12 22 L2 12 Z",
  // Simple house silhouette — House drop
  house: "M12 2 L22 10 V22 H15 V14 H9 V22 H2 V10 Z",
  // 5-petal flower — Flower Pot
  flower: "M12 12 m-5-5 a5 5 0 1 1 10 0 a5 5 0 1 1-10 0 M12 7 a4 4 0 1 0 0.001 0 M7 12 a4 4 0 1 0 0.001 0 M17 12 a4 4 0 1 0 0.001 0 M12 17 a4 4 0 1 0 0.001 0 M12 12 m-3-3 a4 4 0 1 1 6 6 a4 4 0 1 1-6-6 M12 9 a3 3 0 1 0 0.001 0",
  // Filled circle — generic / splice (fallback)
  circle: "M12 4 a8 8 0 1 1 0 0.001 Z",
};

/** Build a complete inline SVG string for the given glyph and fill color. */
function buildKmzGlyphSvg(glyph: KmzGlyphKind, fillColor: string): string {
  return _kmzSvg(_KMZ_GLYPH_PATHS[glyph], fillColor);
}

/**
 * Inspect `icon_href` (from KML IconStyle) for well-known telecom icon filename hints.
 * Returns a glyph kind when a match is found, or null to fall back to circleMarker.
 */
function getKmzGlyphFromIconHref(icon_href: string | undefined | null): KmzGlyphKind | null {
  if (!icon_href) return null;
  const lc = icon_href.toLowerCase();
  if (lc.includes("triangle")) return "triangle";
  if (lc.includes("square"))   return "square";
  if (lc.includes("diamond"))  return "diamond";
  if (lc.includes("house"))    return "house";
  if (lc.includes("flower") || lc.includes("star")) return "flower";
  return null;
}

// ─── Phase 2K: engineering attribute extraction + inspection helpers ─────────

/** Human-readable label for each KMZ point subtype (popup header). */
const KMZ_SUBTYPE_LABELS: Record<KmzPointSubtype, string> = {
  splice_hh:        "Splice Handhole",
  terminal_port_hh: "Terminal Port Handhole",
  installer_hh:     "Installer Handhole",
  flower_pot:       "Flower Pot",
  house:            "House",
  generic_structure:"Generic Structure",
};

/**
 * Telecom field priority order.
 * Known fields appear first in the Engineering Attributes panel; remainder are alphabetical.
 */
const ENGINEERING_FIELD_PRIORITY: string[] = [
  "AP Number", "Node Type", "HH Size", "Flower Pot Size",
  "Terminal Length", "Splitter Count", "SCID", "Splice Location",
  "Cable ID", "Fiber Size", "Terminal ID", "Address", "Notes",
];

/**
 * Parse Google Earth description HTML and extract structured key/value rows
 * from `<table><tr><td>` patterns. Pure, never throws, max 48 rows.
 */
function extractEngineeringAttributes(
  descriptionRaw: string,
): Array<{ key: string; value: string }> {
  if (!descriptionRaw || typeof document === "undefined") return [];
  try {
    const parser = new DOMParser();
    const doc = parser.parseFromString(descriptionRaw, "text/html");
    const result: Array<{ key: string; value: string }> = [];
    const trs = Array.from(doc.querySelectorAll("tr"));
    for (const tr of trs) {
      const cells = Array.from(tr.querySelectorAll("td, th"));
      if (cells.length < 2) continue;
      const normalize = (el: Element) =>
        (el.textContent ?? "").replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim();
      const key = normalize(cells[0]);
      const val = normalize(cells[1]);
      if (!key || !val) continue;
      if (key.length > 120 || val.length > 300) continue;
      result.push({ key, value: val });
      if (result.length >= 48) break;
    }
    return result;
  } catch {
    return [];
  }
}

/** Sort extracted engineering rows: known priority fields first, then alphabetical. */
function sortEngineeringAttributes(
  rows: Array<{ key: string; value: string }>,
): Array<{ key: string; value: string }> {
  const priorityOf = (key: string): number => {
    const lc = key.toLowerCase();
    const idx = ENGINEERING_FIELD_PRIORITY.findIndex(p => p.toLowerCase() === lc);
    return idx === -1 ? ENGINEERING_FIELD_PRIORITY.length : idx;
  };
  return [...rows].sort((a, b) => {
    const da = priorityOf(a.key);
    const db = priorityOf(b.key);
    if (da !== db) return da - db;
    return a.key.localeCompare(b.key);
  });
}

// ─── Footage-based KMZ placement helpers ────────────────────────────────────
// Local copies of RedlineMap's geometry helpers so ModernHeroMap can interpolate
// selected field stations along the KMZ design path the same way RedlineMap
// does. Kept verbatim in semantics; do not edit in isolation — keep in sync
// with RedlineMap if the algorithm there ever changes.

const EARTH_RADIUS_FT = 6371000 * 3.28084;

function segmentLengthFtHaversine(a: number[], b: number[]): number {
  const lat1 = (a[0] * Math.PI) / 180;
  const lat2 = (b[0] * Math.PI) / 180;
  const dLat = ((b[0] - a[0]) * Math.PI) / 180;
  const dLon = ((b[1] - a[1]) * Math.PI) / 180;
  const h =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
  return 2 * EARTH_RADIUS_FT * Math.asin(Math.min(1, Math.sqrt(Math.max(0, h))));
}

function totalKmzPolylinesLengthFt(polylines: number[][][]): number {
  let total = 0;
  for (const line of polylines) {
    for (let i = 0; i < line.length - 1; i++) {
      total += segmentLengthFtHaversine(line[i], line[i + 1]);
    }
  }
  return total;
}

/** Prefer API mapped_station_ft when numeric; else chainage from station_number (e.g. 00+46 → 46). */
function fieldStationFtFromRow(st: {
  station_number: string;
  mapped_station_ft?: unknown;
}): number {
  const m = st.mapped_station_ft;
  if (typeof m === "number" && Number.isFinite(m)) {
    return m;
  }
  const [major, minor] = String(st.station_number).split("+");
  const v = parseInt(major ?? "0", 10) * 100 + parseInt(minor ?? "0", 10);
  return Number.isFinite(v) ? v : NaN;
}

/** Point at distanceFt along concatenated polylines (0 = start of first polyline). */
function latLonAlongPolylinesByDistanceFt(
  polylines: number[][][],
  distanceFt: number,
  totalFt: number,
): { lat: number; lon: number } | null {
  if (polylines.length === 0 || totalFt <= 0 || !Number.isFinite(distanceFt)) return null;
  const target = Math.max(0, Math.min(distanceFt, totalFt));
  let remaining = target;
  for (const line of polylines) {
    for (let i = 0; i < line.length - 1; i++) {
      const a = line[i];
      const b = line[i + 1];
      const segFt = segmentLengthFtHaversine(a, b);
      if (segFt < 1e-9) continue;
      if (remaining <= segFt + 1e-9) {
        const t = Math.max(0, Math.min(1, remaining / segFt));
        return { lat: a[0] + t * (b[0] - a[0]), lon: a[1] + t * (b[1] - a[1]) };
      }
      remaining -= segFt;
    }
  }
  const lastLine = polylines[polylines.length - 1];
  const end = lastLine[lastLine.length - 1];
  return { lat: end[0], lon: end[1] };
}

/**
 * Returns [lat, lon] points along the concatenated KMZ design polylines
 * between startFt and endFt (haversine ft), inclusive. Used to render the
 * field-submission connector as the actual curved KMZ sub-polyline rather
 * than straight chords between projected stations. Verbatim parity with
 * RedlineMap.kmzSubpathCoordsByDistanceRangeFt; do not edit in isolation.
 */
function kmzSubpathCoordsByDistanceRangeFt(
  polylines: number[][][],
  startFt: number,
  endFt: number,
): number[][] {
  const out: number[][] = [];
  if (!polylines.length || !Number.isFinite(startFt) || !Number.isFinite(endFt)) {
    return [];
  }
  const totalFt = totalKmzPolylinesLengthFt(polylines);
  if (totalFt <= 0) return [];
  let s = Math.max(0, Math.min(startFt, totalFt));
  let e = Math.max(0, Math.min(endFt, totalFt));
  if (s > e) {
    const tmp = s;
    s = e;
    e = tmp;
  }
  if (e - s < 1e-9) return [];
  const addPt = (lat: number, lon: number) => {
    const last = out[out.length - 1];
    if (last && Math.abs(last[0] - lat) < 1e-14 && Math.abs(last[1] - lon) < 1e-14) {
      return;
    }
    out.push([lat, lon]);
  };
  let cum = 0;
  for (const line of polylines) {
    for (let i = 0; i < line.length - 1; i++) {
      const Va = line[i];
      const Vb = line[i + 1];
      const L = segmentLengthFtHaversine(Va, Vb);
      if (L < 1e-9) continue;
      const segStart = cum;
      const segEnd = cum + L;
      if (e <= segStart) return out;
      if (s >= segEnd) {
        cum = segEnd;
        continue;
      }
      const d0 = Math.max(s - segStart, 0);
      const d1 = Math.min(e - segStart, L);
      const t0 = Math.max(0, Math.min(1, d0 / L));
      const t1 = Math.max(0, Math.min(1, d1 / L));
      const lat0 = Va[0] + t0 * (Vb[0] - Va[0]);
      const lon0 = Va[1] + t0 * (Vb[1] - Va[1]);
      const lat1 = Va[0] + t1 * (Vb[0] - Va[0]);
      const lon1 = Va[1] + t1 * (Vb[1] - Va[1]);
      addPt(lat0, lon0);
      if (t1 - t0 > 1e-12) addPt(lat1, lon1);
      cum = segEnd;
      if (cum >= e - 1e-9) return out;
    }
  }
  return out;
}

// ─── Visual-only snap-to-KMZ helpers (verbatim parity with RedlineMap) ────
// Used to render normal station markers on the nearest point of the KMZ
// design polylines so the visual shape matches RedlineMap. Does NOT mutate
// stored GPS coordinates — the inspector still reads raw lat/lon from the
// untouched StationPoint source. Keep semantics in sync with RedlineMap.

function nearestPointOnLatLonSegment(
  lat: number,
  lon: number,
  a: number[],
  b: number[],
): { lat: number; lon: number } {
  const alat = a[0];
  const alon = a[1];
  const blat = b[0];
  const blon = b[1];
  const dlat = blat - alat;
  const dlon = blon - alon;
  const len2 = dlat * dlat + dlon * dlon;
  if (len2 < 1e-20) return { lat: alat, lon: alon };
  let t = ((lat - alat) * dlat + (lon - alon) * dlon) / len2;
  t = Math.max(0, Math.min(1, t));
  return { lat: alat + t * dlat, lon: alon + t * dlon };
}

function snapLatLonToKmzPolylines(
  lat: number,
  lon: number,
  polylines: number[][][],
): { lat: number; lon: number } {
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || polylines.length === 0) {
    return { lat, lon };
  }
  let bestLat = lat;
  let bestLon = lon;
  let bestD = Infinity;
  for (const line of polylines) {
    for (let i = 0; i < line.length - 1; i++) {
      const p = nearestPointOnLatLonSegment(lat, lon, line[i], line[i + 1]);
      const d = (p.lat - lat) * (p.lat - lat) + (p.lon - lon) * (p.lon - lon);
      if (d < bestD) {
        bestD = d;
        bestLat = p.lat;
        bestLon = p.lon;
      }
    }
  }
  return { lat: bestLat, lon: bestLon };
}

function lineColor(feature: KmzLineFeature): string {
  const raw = String(feature.stroke ?? feature.color ?? "").trim();
  return raw || "#0f172a";
}

function lineWidth(feature: KmzLineFeature): number {
  const raw = Number(feature.stroke_width ?? feature.width ?? 2.5);
  if (!Number.isFinite(raw)) return 2.5;
  return Math.max(1, Math.min(raw, 8));
}

function polygonStroke(feature: KmzPolygonFeature): string {
  const raw = String(feature.stroke ?? feature.stroke_color ?? "").trim();
  return raw || "#334155";
}

function polygonFill(feature: KmzPolygonFeature): string {
  const raw = String(feature.fill ?? feature.fill_color ?? "").trim();
  return raw || "#64748b";
}

function polygonOpacity(feature: KmzPolygonFeature): number {
  const raw = Number(feature.fill_opacity ?? 0.16);
  if (!Number.isFinite(raw)) return 0.16;
  return Math.max(0.04, Math.min(raw, 0.5));
}

// ─── Station identity helpers (verbatim parity with RedlineMap) ──────────
// The backend keys station-photo records by a stable composite identity
// derived from the station's route, source file, label, and snapped/raw GPS.
// Reproduce the legacy formatting exactly so photos uploaded from either map
// are addressable from the other.

function stationIdentityPart(value: unknown, digits?: number): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "";
    return digits !== undefined ? value.toFixed(digits) : String(value);
  }
  return String(value).trim();
}

function buildStationIdentity(
  routeName: string | null | undefined,
  point: StationPoint | null | undefined,
): string {
  if (!point) return "";
  return [
    stationIdentityPart(routeName),
    stationIdentityPart(point.source_file),
    stationIdentityPart(point.station),
    stationIdentityPart(point.mapped_station_ft, 3),
    stationIdentityPart(point.lat, 8),
    stationIdentityPart(point.lon, 8),
  ].join("|");
}

function buildStationSummary(
  routeName: string | null | undefined,
  point: StationPoint | null | undefined,
): string {
  if (!point) return "--";
  const station = String(point.station ?? "").trim() || "--";
  const source = String(point.source_file ?? "").trim() || "--";
  const route = String(routeName ?? "").trim() || "--";
  return `${station} • ${route} • ${source}`;
}

export default function ModernHeroMap({
  projectId,
  selectedFieldSessionId = null,
  selectedFieldJobId = null,
  refreshVersion = 0,
  bridgedGpsPhotos = [],
  kmzSemantic,
  engineeringPlanOverlay,
}: ModernHeroMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<ReturnType<LeafletNS["map"]> | null>(null);
  const leafletRef = useRef<LeafletNS | null>(null);
  const standardTilesRef = useRef<ReturnType<LeafletNS["tileLayer"]> | null>(null);
  const satelliteTilesRef = useRef<ReturnType<LeafletNS["tileLayer"]> | null>(null);
  const kmzLinesRef = useRef<Array<ReturnType<LeafletNS["polyline"]>>>([]);
  const kmzPolygonsRef = useRef<Array<ReturnType<LeafletNS["polygon"]>>>([]);
  const redlineLayersRef = useRef<Array<ReturnType<LeafletNS["polyline"]>>>([]);
  const stationLayersRef = useRef<Array<ReturnType<LeafletNS["circleMarker"]>>>([]);
  const photoLayersRef = useRef<Array<ReturnType<LeafletNS["circleMarker"]>>>([]);
  const fieldStationLayersRef = useRef<Array<ReturnType<LeafletNS["circleMarker"]>>>([]);
  const fieldConnectorLayerRef = useRef<ReturnType<LeafletNS["polyline"]> | null>(null);
  // Raw GPS evidence trail for the selected field session. Visually secondary
  // to the violet snapped/interpolated route. Coords are NEVER added to
  // allPoints — the trail must not influence fitBounds.
  const fieldTrailLayerRef = useRef<ReturnType<LeafletNS["polyline"]> | null>(null);
  const fieldPhotoLayersRef = useRef<Array<ReturnType<LeafletNS["circleMarker"]>>>([]);
  const bridgedGpsPhotoLayersRef = useRef<Array<ReturnType<LeafletNS["circleMarker"]>>>([]);
  // Phase 2F — KMZ context render payload layers. Separate from the simplified
  // kmz_reference layers. Stored in independent refs so they can be rebuilt
  // without touching operational geometry.
  const kmzCtxPolygonLayersRef = useRef<Array<ReturnType<LeafletNS["polygon"]>>>([]);
  const kmzCtxLineLayersRef = useRef<Array<ReturnType<LeafletNS["polyline"]>>>([]);
  const kmzCtxPointLayersRef = useRef<Array<ReturnType<LeafletNS["circleMarker"]>>>([]);
  // Phase 2J: layers that have permanent tooltips, separated for zoom-aware toggling.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const kmzPtPermLabelLayersRef = useRef<Array<any>>([]);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const kmzLinePermLabelLayersRef = useRef<Array<any>>([]);
  // Parallel arrays of evidence-layer ids, one per layer in stationLayersRef /
  // redlineLayersRef. Index-aligned with the layer arrays. A null entry means
  // "no evidence layer" — those layers are never filtered by hiddenLayers.
  const stationLayerIdsRef = useRef<Array<string | null>>([]);
  const redlineLayerIdsRef = useRef<Array<string | null>>([]);

  const [baseStyle, setBaseStyle] = useState<BaseStyle>("satellite");
  const [state, setState] = useState<BackendState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mapZoom, setMapZoom] = useState<number>(13);
  const [selectedFieldJobDetail, setSelectedFieldJobDetail] = useState<JobDetail | null>(
    null,
  );
  const [showStations, setShowStations] = useState<boolean>(false);
  const [showFieldSubmission, setShowFieldSubmission] = useState<boolean>(true);
  const [showFieldPhotos, setShowFieldPhotos] = useState<boolean>(true);
  // GPS evidence trail visibility. Default off so the trail (noisy raw GPS) is
  // an opt-in evidence layer, not part of the operational view. Mirrors
  // RedlineMap's showFieldGpsEvidenceTrail behavior.
  const [showFieldGpsTrail, setShowFieldGpsTrail] = useState<boolean>(false);
  const [selectedStationIndex, setSelectedStationIndex] = useState<number | null>(null);
  const [selectedFieldStationIdx, setSelectedFieldStationIdx] = useState<number | null>(null);
  // Hover indices — purely cosmetic. Drive a separate restyle effect; never
  // touched by the geometry render-effect, so hovering can't move the camera
  // or rebuild any Leaflet layer.
  const [hoverStationIndex, setHoverStationIndex] = useState<number | null>(null);
  const [hoverFieldStationIdx, setHoverFieldStationIdx] = useState<number | null>(null);
  const [selectedFieldPhotoIdx, setSelectedFieldPhotoIdx] = useState<number | null>(null);
  const [selectedPhotoPointIdx, setSelectedPhotoPointIdx] = useState<number | null>(null);
  const [selectedBridgedPhotoIdx, setSelectedBridgedPhotoIdx] = useState<number | null>(null);
  // Photo placement save state. Drag is direct on each photo's marker; on
  // pointerup we save the new Displayed Position. Original Geotag is never
  // mutated. No "Move Mode" — the markers are always grabbable when the
  // session isn't closeout-locked.
  const [photoMoveSaving, setPhotoMoveSaving] = useState(false);
  const [photoMoveError, setPhotoMoveError] = useState<string | null>(null);
  // Client-only Displayed Position overrides for bridged geotagged photos
  // (source_type "client_geotagged_temp"). Keyed by photo id. Lives only in
  // the modern map's render — does NOT round-trip to RedlineMap and does NOT
  // persist across refresh, since these photos themselves are ephemeral
  // (they reset when RedlineMap remounts and the File handles are dropped).
  // Original Geotag (lat/lon on the BridgedGpsPhoto) is never mutated; we
  // only attach displayLat/displayLon overrides here.
  const [bridgedPhotoOverrides, setBridgedPhotoOverrides] = useState<
    Record<string, { lat: number; lon: number }>
  >({});
  // Station photo workflow. Mirrors RedlineMap: when a station is selected we
  // fetch its attached photos via /api/station-photos using the composite
  // station_identity key, and we POST new attachments via
  // /api/station-photos/upload. State is owned at the map root so the
  // inspector panel can stay declarative.
  const [stationPhotos, setStationPhotos] = useState<StationPhoto[]>([]);
  const [stationPhotosLoading, setStationPhotosLoading] = useState(false);
  const [stationPhotoBusy, setStationPhotoBusy] = useState(false);
  const [stationPhotoError, setStationPhotoError] = useState<string | null>(null);

  // Evidence-layer visibility. Set of evidence_layer_id strings that are
  // currently hidden. Empty = all visible. Mirrors RedlineMap's behavior:
  // hiding a layer suppresses both its station markers and its redline
  // segments without re-fitting the map.
  const [hiddenLayers, setHiddenLayers] = useState<Set<string>>(new Set());
  // Phase 2F — KMZ engineering context layer state. Local only. No backend writes.
  const [layerKmzContext, setLayerKmzContext] = useState(false);
  const [kmzRenderPayload, setKmzRenderPayload] = useState<KmzRenderPayloadResponse | null>(null);
  const [kmzHiddenFolders, setKmzHiddenFolders] = useState<Set<string>>(new Set());
  type SelectedKmzCtxFeature = {
    feature_id: string; feature_type: "point"|"line"|"polygon";
    name?: string; classification?: string; folder_path?: string[];
    description?: string; extended_data?: Record<string,string>;
    chainage_ft?: number|null; sequence_number?: string|null;
    sequence_kind?: string|null; lifecycle?: {label:string;confidence:string;reason:string}|null;
    // Phase 2I — balloon fidelity
    description_raw?: string; style_url?: string; icon_href?: string;
    // Phase 2K — subtype for human-readable header
    subtype?: KmzPointSubtype;
  };
  const [selectedKmzCtxFeature, setSelectedKmzCtxFeature] = useState<SelectedKmzCtxFeature|null>(null);
  // Mirror into a ref so the geometry render-effect can read latest visibility
  // without depending on it (toggling visibility must not re-trigger
  // fitBounds).
  const hiddenLayersRef = useRef(hiddenLayers);
  useEffect(() => {
    hiddenLayersRef.current = hiddenLayers;
  }, [hiddenLayers]);

  // Mirror toggle state into refs so the geometry render-effect can read the
  // latest values without depending on them. This keeps initial fitBounds
  // behavior intact: toggling visibility doesn't re-trigger the geometry
  // render and therefore doesn't re-fit the map.
  const showStationsRef = useRef(showStations);
  useEffect(() => {
    showStationsRef.current = showStations;
  }, [showStations]);
  const showFieldSubmissionRef = useRef(showFieldSubmission);
  useEffect(() => {
    showFieldSubmissionRef.current = showFieldSubmission;
  }, [showFieldSubmission]);
  const showFieldPhotosRef = useRef(showFieldPhotos);
  useEffect(() => {
    showFieldPhotosRef.current = showFieldPhotos;
  }, [showFieldPhotos]);
  const showFieldGpsTrailRef = useRef(showFieldGpsTrail);
  useEffect(() => {
    showFieldGpsTrailRef.current = showFieldGpsTrail;
  }, [showFieldGpsTrail]);

  const STATION_LABEL_MIN_ZOOM = 16;

  const kmzLines = useMemo(
    () =>
      (state?.kmz_reference?.line_features ?? [])
        .map((f) => ({ ...f, coords: cleanCoords(f.coords) }))
        .filter((f) => f.coords.length >= 2),
    [state],
  );

  const kmzPolygons = useMemo(
    () =>
      (state?.kmz_reference?.polygon_features ?? [])
        .map((f) => ({ ...f, coords: cleanCoords(f.coords) }))
        .filter((f) => f.coords.length >= 3),
    [state],
  );

  const redlineSegments = useMemo(
    () =>
      (state?.redline_segments ?? [])
        .map((segment: RedlineSegment) => ({
          ...segment,
          coords: cleanCoords(segment.coords),
        }))
        .filter((segment) => segment.coords.length >= 2),
    [state],
  );

  // Concatenation of cleaned KMZ polyline geometry. Used as the snap target
  // for normal station markers (visual-only) and as the interpolation path
  // for footage-based field-station placement. Declared above stationPoints
  // so the station memo can read it without a forward reference.
  const kmzSnapPolylines = useMemo<number[][][]>(
    () => kmzLines.map((l) => l.coords as unknown as number[][]),
    [kmzLines],
  );

  // Snap target for normal station placement. Combines the operational
  // redline polylines with the KMZ design polylines so stations land on the
  // nearest visible path — preferring redlines when they are nearer (which is
  // the operational truth) and falling back to KMZ when no redline exists in
  // the area yet. KMZ design lines remain unchanged for everything else
  // (field submission interpolation, connector subpath, evidence trail).
  const stationSnapPolylines = useMemo<number[][][]>(() => {
    const out: number[][][] = [];
    for (const seg of redlineSegments) {
      const coords = seg.coords;
      if (Array.isArray(coords) && coords.length >= 2) {
        out.push(coords as unknown as number[][]);
      }
    }
    for (const line of kmzLines) {
      const coords = line.coords;
      if (Array.isArray(coords) && coords.length >= 2) {
        out.push(coords as unknown as number[][]);
      }
    }
    return out;
  }, [redlineSegments, kmzLines]);

  // Source file → evidence_layer_id mapping derived from bore_log_summary.
  // Used to gate station markers (whose source_file lives on the StationPoint)
  // and redline segments (whose source_file lives on the segment) by their
  // owning evidence layer. Mirrors the legacy map's mapping.
  const sourceFileToLayerId = useMemo(() => {
    const map = new Map<string, string>();
    for (const entry of state?.bore_log_summary ?? []) {
      const src = String(entry.source_file ?? "").trim();
      if (src && entry.evidence_layer_id) {
        map.set(src, entry.evidence_layer_id);
      }
    }
    return map;
  }, [state?.bore_log_summary]);

  // Normal station rows. Each row carries:
  //   - lat/lon — RAW backend GPS, preserved untouched. The inspector reads
  //     these (via `source`) so the display field set is unaffected by snap.
  //   - displayLat/displayLon — what the marker actually renders at. Snapped
  //     to the nearest point on the KMZ design polylines for visual parity
  //     with RedlineMap. When KMZ geometry isn't available, this falls back
  //     to raw lat/lon.
  //   - source — original StationPoint, untouched.
  const stationPoints = useMemo(() => {
    const raw = (state?.station_points ?? []) as StationPoint[];
    const out: Array<{
      lat: number;
      lon: number;
      displayLat: number;
      displayLon: number;
      label: string;
      source: StationPoint;
    }> = [];
    for (const sp of raw) {
      const lat = Number(sp?.lat);
      const lon = Number(sp?.lon);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
      const labelRaw =
        (typeof sp.station === "string" && sp.station.trim()) ||
        (typeof sp.business_id === "string" && sp.business_id.trim()) ||
        (Number.isFinite(Number(sp.station_ft)) ? String(sp.station_ft) : "");
      // Snap to redlines + KMZ union so stations sit on the operational
      // path. snapLatLonToKmzPolylines just picks the nearest point on any
      // polyline in the pool, so feeding it both populations is safe.
      const snapped =
        stationSnapPolylines.length > 0
          ? snapLatLonToKmzPolylines(lat, lon, stationSnapPolylines)
          : { lat, lon };
      out.push({
        lat,
        lon,
        displayLat: snapped.lat,
        displayLon: snapped.lon,
        label: labelRaw || "",
        source: sp,
      });
    }
    return out;
  }, [state, stationSnapPolylines]);

  // Bridged geotagged photos with any in-session Displayed Position override
  // applied. Renders use displayLat/displayLon when set; lat/lon (Original
  // Geotag) stays untouched on every entry. Overrides keyed by photo id.
  const effectiveBridgedPhotos = useMemo(() => {
    if (!Array.isArray(bridgedGpsPhotos) || bridgedGpsPhotos.length === 0) {
      return [] as BridgedGpsPhoto[];
    }
    return bridgedGpsPhotos.map((photo) => {
      const override = bridgedPhotoOverrides[photo.id];
      if (override) {
        return {
          ...photo,
          displayLat: override.lat,
          displayLon: override.lon,
        };
      }
      return photo;
    });
  }, [bridgedGpsPhotos, bridgedPhotoOverrides]);

  // Prune overrides for photos that have disappeared from bridgedGpsPhotos
  // (e.g., RedlineMap cleared its gpsPhotos). Keeps the override map from
  // growing across upload/clear cycles.
  useEffect(() => {
    setBridgedPhotoOverrides((prev) => {
      const ids = new Set(bridgedGpsPhotos.map((p) => p.id));
      let changed = false;
      const next: Record<string, { lat: number; lon: number }> = {};
      for (const key of Object.keys(prev)) {
        if (ids.has(key)) {
          next[key] = prev[key];
        } else {
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [bridgedGpsPhotos]);

  // Geotagged photo points. Read tolerantly from a few likely-named arrays on
  // `state` so this layer activates the moment the backend surfaces photo
  // coordinates in /api/current-state. Accepts either {lat,lon} or
  // {latitude,longitude}. Invalid coords are silently skipped.
  const photoPoints = useMemo(() => {
    const stateRec = state as Record<string, unknown> | null;
    const candidates: unknown[] = [
      stateRec?.photo_points,
      stateRec?.geotagged_photos,
      stateRec?.photos,
    ];
    const arr =
      (candidates.find((c) => Array.isArray(c) && (c as unknown[]).length > 0) as
        | Array<Record<string, unknown>>
        | undefined) ?? [];
    const out: Array<{
      lat: number;
      lon: number;
      displayLat: number;
      displayLon: number;
      label: string;
      source: Record<string, unknown>;
    }> = [];
    for (const p of arr) {
      if (!p || typeof p !== "object") continue;
      const rec = p as Record<string, unknown>;
      const latRaw = rec.lat ?? rec.latitude;
      const lonRaw = rec.lon ?? rec.longitude;
      const originalLatRaw = rec.original_lat ?? latRaw;
      const originalLonRaw = rec.original_lon ?? lonRaw;
      const adjustedLatRaw = rec.adjusted_lat;
      const adjustedLonRaw = rec.adjusted_lon;
      const lat = Number(originalLatRaw);
      const lon = Number(originalLonRaw);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
      const adjustedLat = Number(adjustedLatRaw);
      const adjustedLon = Number(adjustedLonRaw);
      const hasAdjusted = Number.isFinite(adjustedLat) && Number.isFinite(adjustedLon);
      const displayLat = hasAdjusted ? adjustedLat : lat;
      const displayLon = hasAdjusted ? adjustedLon : lon;
      const orig = (p as { original_filename?: unknown }).original_filename;
      const fn = (p as { filename?: unknown }).filename;
      const nm = (p as { name?: unknown }).name;
      const label =
        (typeof orig === "string" && orig.trim()) ||
        (typeof fn === "string" && fn.trim()) ||
        (typeof nm === "string" && nm.trim()) ||
        "Photo";
      out.push({ lat, lon, displayLat, displayLon, label, source: p });
    }
    return out;
  }, [state]);

  // Filtered overlay: only stations belonging to the currently selected field
  // submission session. Each row carries:
  //   - rawLat/rawLon — raw GPS as returned by the API (NaN when missing)
  //   - displayLat/displayLon — KMZ-projected coords when footage + KMZ are
  //     valid; otherwise raw GPS as a fallback
  //   - stationFt — footage along the KMZ path (mapped_station_ft preferred,
  //     else parsed from station_number)
  //   - label — station_number for the on-marker tag
  // Rows are sorted by stationFt (finite first, ascending) so the connector
  // polyline runs in station order rather than API order.
  const fieldStations = useMemo(() => {
    if (!selectedFieldSessionId || !selectedFieldJobDetail) return [];
    const sid = selectedFieldSessionId.trim();
    const totalKmzFt = totalKmzPolylinesLengthFt(kmzSnapPolylines);

    type Row = {
      rawLat: number;
      rawLon: number;
      displayLat: number;
      displayLon: number;
      stationFt: number;
      label: string;
      source: Station;
    };
    const rows: Row[] = [];

    for (const st of selectedFieldJobDetail.stations ?? []) {
      if (String(st.session_id ?? "") !== sid) continue;

      const rawLat = Number(st.latitude);
      const rawLon = Number(st.longitude);
      const hasRaw = Number.isFinite(rawLat) && Number.isFinite(rawLon);

      const stationFt = fieldStationFtFromRow({
        station_number: String(st.station_number ?? ""),
        mapped_station_ft: (st as { mapped_station_ft?: unknown }).mapped_station_ft,
      });

      let displayLat: number | null = null;
      let displayLon: number | null = null;

      if (
        Number.isFinite(stationFt) &&
        totalKmzFt > 0 &&
        kmzSnapPolylines.length > 0
      ) {
        const onLine = latLonAlongPolylinesByDistanceFt(
          kmzSnapPolylines,
          stationFt,
          totalKmzFt,
        );
        if (onLine && Number.isFinite(onLine.lat) && Number.isFinite(onLine.lon)) {
          displayLat = onLine.lat;
          displayLon = onLine.lon;
        }
      }

      if (displayLat === null || displayLon === null) {
        if (!hasRaw) continue;
        displayLat = rawLat;
        displayLon = rawLon;
      }

      rows.push({
        rawLat: hasRaw ? rawLat : NaN,
        rawLon: hasRaw ? rawLon : NaN,
        displayLat,
        displayLon,
        stationFt,
        label: String(st.station_number ?? "").trim(),
        source: st,
      });
    }

    rows.sort((a, b) => {
      const aFin = Number.isFinite(a.stationFt);
      const bFin = Number.isFinite(b.stationFt);
      if (aFin && bFin) return a.stationFt - b.stationFt;
      if (aFin) return -1;
      if (bFin) return 1;
      return 0;
    });

    return rows;
  }, [selectedFieldJobDetail, selectedFieldSessionId, kmzSnapPolylines]);

  // Photos belonging to the currently selected field submission. Pulled from
  // the JobDetail already fetched for the field-station overlay; no extra
  // network. Filtered strictly by session_id and finite coords.
  const fieldPhotos = useMemo(() => {
    if (!selectedFieldSessionId || !selectedFieldJobDetail) return [];
    const sid = selectedFieldSessionId.trim();
    const out: Array<{ lat: number; lon: number; label: string; source: Photo }> = [];
    for (const ph of selectedFieldJobDetail.photos ?? []) {
      if (String(ph.session_id ?? "") !== sid) continue;
      const lat = Number(ph.latitude);
      const lon = Number(ph.longitude);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
      const stationLabel =
        typeof ph.station_label === "string" ? ph.station_label.trim() : "";
      const label = stationLabel ? `Photo · ${stationLabel}` : "Photo";
      out.push({ lat, lon, label, source: ph });
    }
    return out;
  }, [selectedFieldJobDetail, selectedFieldSessionId]);

  // Session object for the currently selected field submission — used by the
  // field station card to show crew_name, started_at, and photo_count.
  const selectedFieldSession = useMemo<Session | null>(() => {
    if (!selectedFieldSessionId || !selectedFieldJobDetail) return null;
    const sid = selectedFieldSessionId.trim();
    return selectedFieldJobDetail.sessions?.find((s) => s.id === sid) ?? null;
  }, [selectedFieldJobDetail, selectedFieldSessionId]);

  // Raw GPS evidence trail for the currently selected field session. Sourced
  // from session.track_geometry.coordinates which is GeoJSON-shaped
  // ([lon, lat] tuples); we swap to Leaflet's [lat, lon] order. Filters out
  // any non-finite or malformed pairs. Never mutates the original geometry.
  // IMPORTANT: these coords are intentionally NOT added to allPoints — the
  // trail must never influence fitBounds.
  const fieldTrailCoords = useMemo<Array<[number, number]>>(() => {
    const raw = selectedFieldSession?.track_geometry?.coordinates;
    if (!Array.isArray(raw)) return [];
    const out: Array<[number, number]> = [];
    for (const pt of raw) {
      if (!Array.isArray(pt) || pt.length < 2) continue;
      const lon = Number(pt[0]);
      const lat = Number(pt[1]);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
      out.push([lat, lon]);
    }
    return out;
  }, [selectedFieldSession]);

  // Fetch the selected field job's detail. Mirrors RedlineMap's pattern but
  // owned independently here so the two maps don't share state. No-op when
  // either id is missing.
  useEffect(() => {
    if (!selectedFieldJobId || !selectedFieldSessionId) {
      setSelectedFieldJobDetail(null);
      return;
    }
    let cancelled = false;
    void getJobById(selectedFieldJobId, projectId)
      .then((detail) => {
        if (!cancelled) setSelectedFieldJobDetail(detail);
      })
      .catch(() => {
        if (!cancelled) setSelectedFieldJobDetail(null);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedFieldJobId, selectedFieldSessionId, projectId]);

  useEffect(() => {
    let cancelled = false;
    async function loadState(): Promise<void> {
      setLoading(true);
      setError(null);
      try {
        const res = await apiFetch(appendSessionId(`${API_BASE}/api/current-state`, projectId), {
          cache: "no-store",
        });
        const data = (await res.json()) as BackendState;
        if (!res.ok || data.success === false) {
          throw new Error(data.error || "Unable to load current state.");
        }
        if (!cancelled) setState(data);
      } catch (e) {
        if (!cancelled && state === null) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void loadState();
    return () => {
      cancelled = true;
    };
  }, [projectId, refreshVersion]);

  useEffect(() => {
    let cancelled = false;
    const node = containerRef.current;
    if (!node) return;

    void (async () => {
      try {
        const mod = await import("leaflet");
        if (cancelled) return;
        const L: LeafletNS =
          (mod as unknown as { default?: LeafletNS }).default ??
          (mod as unknown as LeafletNS);

        const map = L.map(node, {
          center: EMPTY_DEFAULT_CENTER,
          zoom: EMPTY_DEFAULT_ZOOM,
          maxZoom: 22,
          zoomControl: true,
          attributionControl: true,
          scrollWheelZoom: true,
        });

        const standard = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 22,
          maxNativeZoom: 19,
          attribution: "&copy; OpenStreetMap contributors",
        });
        const satellite = L.tileLayer(
          "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
          {
            maxZoom: 22,
            maxNativeZoom: 19,
            attribution: "Tiles &copy; Esri",
          },
        );

        leafletRef.current = L;
        mapRef.current = map;
        standardTilesRef.current = standard;
        satelliteTilesRef.current = satellite;

        // VO.2b — create the PDF overlay pane once when the map is initialized.
        // z=150 places the overlay strictly BELOW every existing operational pane
        // (kmzContextPolygonPane=200 etc., overlayPane~400) so redlines / stations /
        // photos remain visually dominant.  pointerEvents:none lets clicks pass
        // through to the operational layer so it stays interactive.
        const PDF_OVERLAY_PANE = "pdfOverlayPane";
        if (!map.getPane(PDF_OVERLAY_PANE)) {
          const pdfPane = map.createPane(PDF_OVERLAY_PANE);
          pdfPane.style.zIndex = "150";
          pdfPane.style.pointerEvents = "none";
        }

        satellite.addTo(map);
        map.invalidateSize();
        if (!cancelled) setMapZoom(map.getZoom());
        map.on("zoomend", () => {
          setMapZoom(map.getZoom());
        });
        // Background click clears all floating panels. Marker click handlers
        // stop propagation so they don't trigger this simultaneously.
        map.on("click", () => {
          setSelectedStationIndex(null);
          setSelectedFieldStationIdx(null);
          setSelectedFieldPhotoIdx(null);
          setSelectedPhotoPointIdx(null);
          setSelectedBridgedPhotoIdx(null);
          setSelectedKmzCtxFeature(null);
        });
      } catch {
        if (!cancelled) setError("Leaflet map failed to initialize.");
      }
    })();

    return () => {
      cancelled = true;
      try {
        mapRef.current?.remove();
      } catch {
        // noop
      }
      mapRef.current = null;
      leafletRef.current = null;
      standardTilesRef.current = null;
      satelliteTilesRef.current = null;
      kmzLinesRef.current = [];
      kmzPolygonsRef.current = [];
      redlineLayersRef.current = [];
      stationLayersRef.current = [];
      photoLayersRef.current = [];
      fieldStationLayersRef.current = [];
      fieldConnectorLayerRef.current = null;
      fieldTrailLayerRef.current = null;
      fieldPhotoLayersRef.current = [];
      bridgedGpsPhotoLayersRef.current = [];
      kmzCtxPolygonLayersRef.current = [];
      kmzCtxLineLayersRef.current = [];
      kmzCtxPointLayersRef.current = [];
      kmzPtPermLabelLayersRef.current = [];
      kmzLinePermLabelLayersRef.current = [];
    };
  }, []);

  // VO.2b — refs for the PDF page-image overlay lifecycle.  Stored on refs
  // (not state) so opacity updates can sync onto the existing overlay without
  // triggering a re-fetch.
  const pdfOverlayRef = useRef<ReturnType<LeafletNS["imageOverlay"]> | null>(null);
  const pdfObjectUrlRef = useRef<string | null>(null);
  const pdfOverlayOpacityRef = useRef<number>(0.45);

  // VO.2b — keep the overlay opacity in sync without re-fetching the image.
  // The PNG is cached server-side per (plan_id, page_index, dpi) so re-fetches
  // are cheap, but the slider should feel instant; ref-based sync avoids the
  // network round-trip entirely.
  useEffect(() => {
    const opacity = Math.min(0.8, Math.max(0, engineeringPlanOverlay?.opacity ?? 0.45));
    pdfOverlayOpacityRef.current = opacity;
    const overlay = pdfOverlayRef.current;
    if (overlay && typeof overlay.setOpacity === "function") {
      try { overlay.setOpacity(opacity); } catch { /* noop */ }
    }
  }, [engineeringPlanOverlay?.opacity]);

  // VO.2b — PDF page-image overlay lifecycle.  Pure read; never mutates STATE.
  // Fetches via apiFetch (Bearer auth, 401 → silent refresh + retry).  Renders
  // only when overlay state is `visible && planId !== null` AND a non-empty
  // fit-to-route bounding box can be computed from kmzSnapPolylines.
  // Backend 404 (TRUELINE_PLAN_OVERLAY_IMAGE off) and 500 (page out of range)
  // fail silently → no overlay rendered; operator self-corrects via Prev/Next.
  useEffect(() => {
    // Tear down any previous overlay before deciding whether to mount a new one.
    const prevOverlay = pdfOverlayRef.current;
    const prevObjectUrl = pdfObjectUrlRef.current;
    pdfOverlayRef.current = null;
    pdfObjectUrlRef.current = null;
    if (prevOverlay) { try { prevOverlay.remove(); } catch { /* noop */ } }
    if (prevObjectUrl) { try { URL.revokeObjectURL(prevObjectUrl); } catch { /* noop */ } }

    const L = leafletRef.current;
    const map = mapRef.current;
    if (!L || !map) return;
    if (!engineeringPlanOverlay) return;
    if (!engineeringPlanOverlay.visible) return;
    if (!engineeringPlanOverlay.planId) return;

    const PDF_OVERLAY_PANE = "pdfOverlayPane";
    if (!map.getPane(PDF_OVERLAY_PANE)) return; // pane should exist post-init; bail safe

    // Fit-to-active-route bounds when KMZ geometry is available; otherwise
    // fall back to the current map viewport so reference / standalone PDFs
    // (ODOT etc.) render without requiring KMZ, bore-logs, redlines, or any
    // active route geometry. Preserves byte-identical KMZ-bounds behavior on
    // sessions that already have operational geometry; only the previously
    // dead-end no-geometry branch changes.
    let minLat = Infinity, maxLat = -Infinity, minLng = Infinity, maxLng = -Infinity;
    let anyPoint = false;
    for (const poly of kmzSnapPolylines) {
      for (const pt of poly) {
        const lat = pt[0];
        const lng = pt[1];
        if (!Number.isFinite(lat) || !Number.isFinite(lng)) continue;
        if (lat < minLat) minLat = lat;
        if (lat > maxLat) maxLat = lat;
        if (lng < minLng) minLng = lng;
        if (lng > maxLng) maxLng = lng;
        anyPoint = true;
      }
    }
    let bounds: [[number, number], [number, number]];
    if (anyPoint) {
      bounds = [
        [minLat, minLng],
        [maxLat, maxLng],
      ];
    } else {
      const mb = map.getBounds();
      bounds = [
        [mb.getSouth(), mb.getWest()],
        [mb.getNorth(), mb.getEast()],
      ];
    }

    // Construct the page-image URL.  Direct-to-Render via NEXT_PUBLIC_API_BASE
    // when defined (mirrors the upload flow at RedlineMap.handleEngineeringPlansUpload);
    // falls back to same-origin when the env is unset (dev/local without proxy).
    const RENDER_BASE = (
      process.env.NEXT_PUBLIC_API_BASE ||
      process.env.NEXT_PUBLIC_API_BASE_URL ||
      ""
    ).replace(/\/+$/, "");
    const baseUrl = RENDER_BASE || API_BASE;
    const planId = engineeringPlanOverlay.planId;
    const pageIndex = Math.max(0, Math.floor(engineeringPlanOverlay.pageIndex));
    const dpi = Math.min(300, Math.max(48, Math.floor(engineeringPlanOverlay.dpi || 96)));

    let cancelled = false;
    void (async () => {
      try {
        const url =
          `${baseUrl}/api/engineering-plans/${encodeURIComponent(planId)}` +
          `/page/${encodeURIComponent(String(pageIndex))}/image?dpi=${dpi}`;
        const resp = await apiFetch(url, undefined, "vo2b_load_plan_page");
        if (cancelled) return;
        if (!resp.ok) return; // 404 / 500 / 400 → no overlay; silent (UI shows prior state)
        const blob = await resp.blob();
        if (cancelled) return;
        const objectUrl = URL.createObjectURL(blob);
        const overlay = L.imageOverlay(objectUrl, bounds, {
          pane: PDF_OVERLAY_PANE,
          opacity: pdfOverlayOpacityRef.current,
          interactive: false,
        });
        overlay.addTo(map);
        if (cancelled) {
          try { overlay.remove(); } catch { /* noop */ }
          try { URL.revokeObjectURL(objectUrl); } catch { /* noop */ }
          return;
        }
        pdfOverlayRef.current = overlay;
        pdfObjectUrlRef.current = objectUrl;
      } catch {
        // Pure best-effort.  Never throw out of an effect.
      }
    })();

    return () => {
      cancelled = true;
      const ov = pdfOverlayRef.current;
      const ou = pdfObjectUrlRef.current;
      pdfOverlayRef.current = null;
      pdfObjectUrlRef.current = null;
      if (ov) { try { ov.remove(); } catch { /* noop */ } }
      if (ou) { try { URL.revokeObjectURL(ou); } catch { /* noop */ } }
    };
  }, [
    engineeringPlanOverlay?.visible,
    engineeringPlanOverlay?.planId,
    engineeringPlanOverlay?.pageIndex,
    engineeringPlanOverlay?.dpi,
    kmzSnapPolylines,
  ]);

  // Phase 2F — Fetch KMZ render payload when context toggle turns ON.
  // Silent failure. No STATE writes. Read-only.
  useEffect(() => {
    if (!kmzSemantic) return;
    let cancelled = false;
    void (async () => {
      try {
        const res = await apiFetch(appendSessionId(`${API_BASE}/api/observability/kmz-render-payload`, projectId), { cache: "no-store" });
        if (!res.ok) return;
        const data = (await res.json()) as KmzRenderPayloadResponse;
        if (!cancelled) setKmzRenderPayload(data);
      } catch { /* silent */ }
    })();
    return () => { cancelled = true; };
  }, [kmzSemantic, projectId]);

  // Phase 2F — Render KMZ context layers on the Leaflet map.
  // Separate from the operational geometry effect so it never touches redlines/stations.
  // KMZ context layers are added to a low-z pane so operational redlines stay dominant.
  useEffect(() => {
    const L = leafletRef.current;
    const map = mapRef.current;
    // Clean up existing KMZ context layers.
    for (const ly of kmzCtxPolygonLayersRef.current) { try { ly.remove(); } catch { /* noop */ } }
    for (const ly of kmzCtxLineLayersRef.current) { try { ly.remove(); } catch { /* noop */ } }
    for (const ly of kmzCtxPointLayersRef.current) { try { ly.remove(); } catch { /* noop */ } }
    kmzCtxPolygonLayersRef.current = [];
    kmzCtxLineLayersRef.current = [];
    kmzCtxPointLayersRef.current = [];
    kmzPtPermLabelLayersRef.current = [];
    kmzLinePermLabelLayersRef.current = [];
    if (!L || !map || !layerKmzContext || !kmzRenderPayload) return;

    // Phase 2H.1 — Updated pane z-index hierarchy:
    //   KMZ ctx polygons (200) < KMZ ctx lines (210) < kmz_reference design lines (280)
    //   < KMZ ctx point markers (320) < overlayPane redlines/stations (~400)
    // This ensures structure markers are always visible above design route lines.
    const POLY_PANE = "kmzContextPolygonPane";
    const LINE_PANE = "kmzContextLinePane";
    const PT_PANE   = "kmzContextPointPane";
    if (!map.getPane(POLY_PANE)) { const p = map.createPane(POLY_PANE); p.style.zIndex = "200"; }
    if (!map.getPane(LINE_PANE)) { const p = map.createPane(LINE_PANE); p.style.zIndex = "210"; }
    if (!map.getPane(PT_PANE))   { const p = map.createPane(PT_PANE);   p.style.zIndex = "320"; }

    const _lineClasses = new Set(["cable","cable_route","backbone","lateral","drop","duct","route_segment"]);
    const _labelClasses = new Set(["Backbone","Underground Cable","Terminal Tail","Vacant Pipe"]);

    // 1. Polygons — lowest KMZ pane
    for (const poly of (kmzRenderPayload.polygons ?? [])) {
      const fk = (poly.folder_path ?? []).join(" / ");
      if (kmzHiddenFolders.has(fk)) continue;
      const coords: [number,number][] = (poly.outer ?? [])
        .filter(p => Array.isArray(p) && p.length>=2 && Number.isFinite(p[0]) && Number.isFinite(p[1]))
        .map(p => [p[0],p[1]]);
      if (coords.length < 3) continue;
      const fc = muteKmzColorMHM(poly.fill_color);
      const layer = L.polygon(coords, { pane: POLY_PANE, color: fc, weight: 0.9, opacity: 0.35, fillColor: fc, fillOpacity: 0.10, interactive: true });
      if (poly.name) layer.bindTooltip(poly.name.slice(0,24), { permanent: false, direction: "center", className: "tl-station-label" });
      layer.on("click", (e) => {
        L.DomEvent.stopPropagation(e);
        setSelectedKmzCtxFeature({ feature_id: poly.feature_id, feature_type: "polygon", name: poly.name, classification: poly.classification, folder_path: poly.folder_path, description: poly.description, extended_data: poly.extended_data, chainage_ft: poly.chainage_ft, sequence_number: poly.sequence_number, sequence_kind: poly.sequence_kind, lifecycle: poly.lifecycle, description_raw: poly.description_raw, style_url: poly.style_url, icon_href: poly.icon_href });
      });
      layer.addTo(map);
      kmzCtxPolygonLayersRef.current.push(layer);
    }

    // 2. Lines — middle KMZ pane (above polygons, below points)
    for (const line of (kmzRenderPayload.lines ?? [])) {
      const fk = (line.folder_path ?? []).join(" / ");
      if (kmzHiddenFolders.has(fk)) continue;
      const coords: [number,number][] = (line.coords ?? [])
        .filter(p => Array.isArray(p) && p.length>=2 && Number.isFinite(p[0]) && Number.isFinite(p[1]))
        .map(p => [p[0],p[1]]);
      if (coords.length < 2) continue;
      const lc = muteKmzColorMHM(line.color);
      const layer = L.polyline(coords, { pane: LINE_PANE, color: lc, weight: 1.2, opacity: 0.42, interactive: true });
      // Phase 2J: label-eligible lines use permanent tooltips (zoom-gated separately).
      const showLabel = line.name && line.name !== "House Drop" && _lineClasses.has(line.classification) && _labelClasses.has(line.name);
      if (showLabel && line.name) {
        layer.bindTooltip(line.name.slice(0, 20), { permanent: true, direction: "center", className: "tl-station-label" });
        kmzLinePermLabelLayersRef.current.push(layer);
      }
      layer.on("click", (e) => {
        L.DomEvent.stopPropagation(e);
        setSelectedKmzCtxFeature({ feature_id: line.feature_id, feature_type: "line", name: line.name, classification: line.classification, folder_path: line.folder_path, description: line.description, extended_data: line.extended_data, chainage_ft: line.chainage_ft, sequence_number: line.sequence_number, sequence_kind: line.sequence_kind, lifecycle: line.lifecycle, description_raw: line.description_raw, style_url: line.style_url, icon_href: line.icon_href });
      });
      layer.addTo(map);
      kmzCtxLineLayersRef.current.push(layer);
    }

    // 3. Points — top KMZ pane (above lines and polygons) with reliable hit area (Phase 2G/2H)
    for (const pt of (kmzRenderPayload.points ?? [])) {
      const fk = (pt.folder_path ?? []).join(" / ");
      if (kmzHiddenFolders.has(fk)) continue;
      if (!Array.isArray(pt.coord) || pt.coord.length < 2) continue;
      const [ptLat, ptLon] = pt.coord;
      if (!Number.isFinite(ptLat) || !Number.isFinite(ptLon)) continue;
      const subtype = getKmzPointSubtype(pt.name, pt.folder_path);
      const sty = KMZ_POINT_STYLES[subtype];
      const tooltipText = pt.name ? pt.name.slice(0, 24) : KMZ_SUBTYPE_LABELS[subtype];
      // Phase 2J: persistent annotation for named engineering structures only.
      const _usePermLabel = subtype === "splice_hh" || subtype === "terminal_port_hh" ||
                            subtype === "installer_hh" || subtype === "flower_pot";
      // Phase 2K: enlarge hit area for high-priority structures.
      const _isHighPriority = subtype === "splice_hh" || subtype === "terminal_port_hh" ||
                              subtype === "installer_hh" || subtype === "flower_pot";
      const _clickPayload = {
        feature_id: pt.feature_id, feature_type: "point" as const,
        name: pt.name, classification: pt.classification,
        folder_path: pt.folder_path, description: pt.description,
        extended_data: pt.extended_data, chainage_ft: pt.chainage_ft,
        sequence_number: pt.sequence_number, sequence_kind: pt.sequence_kind,
        lifecycle: pt.lifecycle,
        description_raw: pt.description_raw, style_url: pt.style_url, icon_href: pt.icon_href,
        subtype, // Phase 2K: pass subtype through for popup header
      };

      // Phase 2K unified two-layer pattern:
      //   Layer 1 — transparent hit circle (always circleMarker, handles tooltip + click)
      //   Layer 2 — visual glyph (either divIcon L.marker or circleMarker, non-interactive)
      // This guarantees reliable clicks regardless of visual representation.
      const hitMarker = L.circleMarker([ptLat, ptLon], {
        pane: PT_PANE,
        radius: _isHighPriority ? 10 : 8,
        fillColor: "transparent", fillOpacity: 0,
        color: "transparent", weight: 0,
        interactive: true, bubblingMouseEvents: false,
      });
      hitMarker.bindTooltip(tooltipText, { permanent: _usePermLabel, direction: "top", offset: _usePermLabel ? [0,-8] : undefined, className: "tl-station-label" });
      if (_usePermLabel) kmzPtPermLabelLayersRef.current.push(hitMarker);
      hitMarker.on("click", (e) => { L.DomEvent.stopPropagation(e); setSelectedKmzCtxFeature(_clickPayload); });

      // Visual layer — non-interactive.
      const glyphKind = getKmzGlyphFromIconHref(pt.icon_href);
      if (glyphKind) {
        const svgHtml = buildKmzGlyphSvg(glyphKind, sty.fillColor);
        const divIco = L.divIcon({ html: svgHtml, className: "tl-kmz-glyph", iconSize: [14, 14], iconAnchor: [7, 7] });
        const visualMarker = L.marker([ptLat, ptLon], { pane: PT_PANE, icon: divIco, interactive: false, bubblingMouseEvents: false });
        visualMarker.addTo(map);
        kmzCtxPointLayersRef.current.push(visualMarker as unknown as ReturnType<LeafletNS["circleMarker"]>);
      } else {
        const visualMarker = L.circleMarker([ptLat, ptLon], {
          pane: PT_PANE,
          radius: sty.radius, color: sty.color, weight: sty.weight,
          fillColor: sty.fillColor, fillOpacity: sty.fillOpacity,
          interactive: false, bubblingMouseEvents: false,
        });
        visualMarker.addTo(map);
        kmzCtxPointLayersRef.current.push(visualMarker);
      }
      // Hit marker added last — sits on top in DOM within the same pane, receives events first.
      hitMarker.addTo(map);
      kmzCtxPointLayersRef.current.push(hitMarker);
    }
    // Phase 2J: apply initial zoom visibility so labels don't show at low zoom on first load.
    const _initZoom = map.getZoom();
    const _initShowPtLabel   = _initZoom >= 17;
    const _initShowLineLabel = _initZoom >= 18;
    for (const ly of kmzPtPermLabelLayersRef.current) {
      try { if (_initShowPtLabel) ly.openTooltip(); else ly.closeTooltip(); } catch { /* noop */ }
    }
    for (const ly of kmzLinePermLabelLayersRef.current) {
      try { if (_initShowLineLabel) ly.openTooltip(); else ly.closeTooltip(); } catch { /* noop */ }
    }

    // Belt-and-suspenders: bring visual glyph markers to front of their SVG pane
    // after all KMZ context layers are added, ensuring correct intra-pane DOM order.
    for (const ly of kmzCtxPointLayersRef.current) {
      try { (ly as { bringToFront?: () => void }).bringToFront?.(); } catch { /* noop */ }
    }
  }, [layerKmzContext, kmzRenderPayload, kmzHiddenFolders]);

  // Phase 2J — Zoom-aware KMZ label decluttering.
  // Permanent point labels (splice, terminal, installer, flower) appear at zoom >= 17.
  // Permanent line labels (Backbone, Underground Cable etc.) appear at zoom >= 18.
  // Only labels are toggled — geometry is never hidden.
  useEffect(() => {
    const KMZ_PT_LABEL_MIN_ZOOM   = 17;
    const KMZ_LINE_LABEL_MIN_ZOOM = 18;
    const showPt   = mapZoom >= KMZ_PT_LABEL_MIN_ZOOM;
    const showLine = mapZoom >= KMZ_LINE_LABEL_MIN_ZOOM;
    for (const ly of kmzPtPermLabelLayersRef.current) {
      try { if (showPt) ly.openTooltip(); else ly.closeTooltip(); } catch { /* noop */ }
    }
    for (const ly of kmzLinePermLabelLayersRef.current) {
      try { if (showLine) ly.openTooltip(); else ly.closeTooltip(); } catch { /* noop */ }
    }
  }, [mapZoom]);

  useEffect(() => {
    const map = mapRef.current;
    const standard = standardTilesRef.current;
    const satellite = satelliteTilesRef.current;
    if (!map || !standard || !satellite) return;
    if (baseStyle === "standard") {
      if (!map.hasLayer(standard)) standard.addTo(map);
      if (map.hasLayer(satellite)) map.removeLayer(satellite);
      return;
    }
    if (!map.hasLayer(satellite)) satellite.addTo(map);
    if (map.hasLayer(standard)) map.removeLayer(standard);
  }, [baseStyle]);

  useEffect(() => {
    const L = leafletRef.current;
    const map = mapRef.current;
    if (!L || !map) return;

    for (const layer of kmzLinesRef.current) {
      try {
        layer.remove();
      } catch {
        // noop
      }
    }
    for (const layer of kmzPolygonsRef.current) {
      try {
        layer.remove();
      } catch {
        // noop
      }
    }
    for (const layer of redlineLayersRef.current) {
      try {
        layer.remove();
      } catch {
        // noop
      }
    }
    for (const layer of stationLayersRef.current) {
      try {
        layer.remove();
      } catch {
        // noop
      }
    }
    for (const layer of photoLayersRef.current) {
      try {
        layer.remove();
      } catch {
        // noop
      }
    }
    for (const layer of fieldStationLayersRef.current) {
      try {
        layer.remove();
      } catch {
        // noop
      }
    }
    if (fieldConnectorLayerRef.current) {
      try {
        fieldConnectorLayerRef.current.remove();
      } catch {
        // noop
      }
    }
    if (fieldTrailLayerRef.current) {
      try {
        fieldTrailLayerRef.current.remove();
      } catch {
        // noop
      }
    }
    for (const layer of fieldPhotoLayersRef.current) {
      try {
        layer.remove();
      } catch {
        // noop
      }
    }
    kmzLinesRef.current = [];
    kmzPolygonsRef.current = [];
    redlineLayersRef.current = [];
    redlineLayerIdsRef.current = [];
    stationLayersRef.current = [];
    stationLayerIdsRef.current = [];
    photoLayersRef.current = [];
    fieldStationLayersRef.current = [];
    fieldConnectorLayerRef.current = null;
    fieldTrailLayerRef.current = null;
    fieldPhotoLayersRef.current = [];
    // Bridged client-side geotagged photo layers are NOT touched here. They
    // are owned by the dedicated bridged-photo effect to avoid coupling drag
    // overrides to the main geometry rebuild (which would refit the map).

    const allPoints: Array<[number, number]> = [];

    for (const feature of kmzPolygons) {
      const coords = feature.coords ?? [];
      if (coords.length < 3) continue;
      const layer = L.polygon(coords, {
        color: polygonStroke(feature),
        weight: 1.5,
        fillColor: polygonFill(feature),
        fillOpacity: polygonOpacity(feature),
      });
      layer.addTo(map);
      kmzPolygonsRef.current.push(layer);
      allPoints.push(...coords);
    }

    // Phase 2H.1 — Move kmz_reference design route lines to a dedicated pane at z-index 280
    // so that KMZ context point markers (kmzContextPointPane at 320) visually sit above them,
    // while operational redlines remain dominant on overlayPane (~400).
    const KMZ_REF_LINE_PANE = "kmzRefDesignPane";
    if (!map.getPane(KMZ_REF_LINE_PANE)) {
      const p = map.createPane(KMZ_REF_LINE_PANE);
      p.style.zIndex = "280";
    }

    for (const feature of kmzLines) {
      const coords = feature.coords ?? [];
      if (coords.length < 2) continue;
      const layer = L.polyline(coords, {
        pane: KMZ_REF_LINE_PANE,
        color: lineColor(feature),
        weight: lineWidth(feature),
        opacity: 0.92,
      });
      layer.addTo(map);
      kmzLinesRef.current.push(layer);
      allPoints.push(...coords);
    }

    // Redline output layer (dominant visual), drawn after KMZ so it stays on top.
    // Each segment's owning evidence_layer_id is captured into the parallel
    // redlineLayerIdsRef so toggling that layer can hide/show this segment
    // without re-running the geometry effect.
    for (const segment of redlineSegments) {
      const coords = segment.coords ?? [];
      if (coords.length < 2) continue;
      const layer = L.polyline(coords, {
        color: "#ef4444",
        weight: 5.25,
        opacity: 0.96,
      });
      const directId = (segment as { evidence_layer_id?: unknown }).evidence_layer_id;
      const evidenceLayerId =
        (typeof directId === "string" && directId.trim()) ||
        sourceFileToLayerId.get(String(segment.source_file ?? "").trim()) ||
        null;
      const isHidden = !!evidenceLayerId && hiddenLayersRef.current.has(evidenceLayerId);
      if (!isHidden) layer.addTo(map);
      redlineLayersRef.current.push(layer);
      redlineLayerIdsRef.current.push(evidenceLayerId);
    }

    // Station points: drawn after redlines so they sit above, but kept visually
    // restrained so redlines remain dominant. Markers render at displayLat /
    // displayLon (snapped to KMZ when available); raw GPS is preserved on the
    // source object for the inspector.
    for (let stIdx = 0; stIdx < stationPoints.length; stIdx++) {
      const sp = stationPoints[stIdx];
      const evidenceLayerId =
        sourceFileToLayerId.get(String(sp.source.source_file ?? "").trim()) || null;
      const isHidden =
        !!evidenceLayerId && hiddenLayersRef.current.has(evidenceLayerId);
      const marker = L.circleMarker([sp.displayLat, sp.displayLon], {
        radius: 4.8,
        color: "#0f172a",
        weight: 1,
        fillColor: "#facc15",
        fillOpacity: 0.95,
      });
      if (showStationsRef.current && !isHidden) marker.addTo(map);
      if (sp.label) {
        try {
          marker.bindTooltip(sp.label, {
            permanent: true,
            direction: "top",
            offset: [0, -2],
            className: "tl-station-label",
            opacity: 1,
          });
        } catch {
          // noop
        }
      }
      // Capture stIdx in a per-iteration closure for click selection. Stop
      // propagation so the map's background-click clear handler doesn't
      // immediately fire and unselect. Selecting a normal station also closes
      // any open field station card so the two panels don't overlap.
      const capturedIdx = stIdx;
      marker.on("click", (evt) => {
        L.DomEvent.stopPropagation(evt);
        setSelectedPhotoPointIdx(null);
        setSelectedFieldStationIdx(null);
        setSelectedFieldPhotoIdx(null);
        setSelectedBridgedPhotoIdx(null);
        setSelectedStationIndex(capturedIdx);
      });
      marker.on("mouseover", () => {
        setHoverStationIndex(capturedIdx);
      });
      marker.on("mouseout", () => {
        setHoverStationIndex((current) =>
          current === capturedIdx ? null : current,
        );
      });
      stationLayersRef.current.push(marker);
      stationLayerIdsRef.current.push(evidenceLayerId);
      allPoints.push([sp.displayLat, sp.displayLon]);
    }

    // Geotagged photos: cyan markers, drawn last so they sit above stations.
    // Each one is directly draggable via native pointer events on its SVG
    // element — no Move-Mode toggle. Click without drag still opens the photo
    // card. radius bumped to 7 so the hit target is comfortable for mouse
    // and touch. Coords are intentionally NOT added to allPoints — a stray
    // photo GPS (or a drag) must never reshape fitBounds.
    for (let phIdx = 0; phIdx < photoPoints.length; phIdx++) {
      const ph = photoPoints[phIdx];
      const photoId = String((ph.source as { id?: unknown }).id ?? "");
      const marker = L.circleMarker([ph.displayLat, ph.displayLon], {
        radius: 7,
        color: "#0c4a6e",
        weight: 1.5,
        fillColor: "#38bdf8",
        fillOpacity: 0.92,
      });
      marker.addTo(map);
      try {
        marker.bindTooltip(ph.label || "Photo", {
          direction: "top",
          offset: [0, -2],
          sticky: true,
          opacity: 0.95,
          className: "tl-photo-label",
        });
      } catch {
        // noop
      }
      const capturedPhIdx = phIdx;

      // Click-vs-drag disambiguation. wasDragged becomes true once the
      // pointer moves past a small threshold after pointerdown; clicks that
      // never moved still open the inspector card. Stored in this closure so
      // each photo manages its own state.
      let dragging = false;
      let activePointerId: number | null = null;
      let downClientX = 0;
      let downClientY = 0;
      let movedPastThreshold = false;
      const DRAG_THRESHOLD_PX = 3;

      marker.on("click", (evt) => {
        if (movedPastThreshold) {
          // Click that follows a real drag — swallow it so the photo card
          // doesn't get re-selected (which would also reset the drag UX).
          movedPastThreshold = false;
          L.DomEvent.stopPropagation(evt);
          return;
        }
        L.DomEvent.stopPropagation(evt);
        setSelectedStationIndex(null);
        setSelectedFieldStationIdx(null);
        setSelectedFieldPhotoIdx(null);
        setSelectedBridgedPhotoIdx(null);
        setSelectedPhotoPointIdx(capturedPhIdx);
      });

      photoLayersRef.current.push(marker);

      // Direct pointer-capture drag on the marker's SVG element. Mirrors the
      // legacy RedlineMap photo drag (RedlineMap.tsx onPointerDown/Move/Up
      // on the photo group), substituting Leaflet's containerPointToLatLng
      // for the legacy screenToWorld + worldPointToLatLon. No Move-Mode.
      const elNode = (
        marker as unknown as { getElement?: () => Element | null }
      ).getElement?.() as HTMLElement | SVGElement | null;
      if (!photoId || !elNode) continue;
      const pointerEl = elNode as unknown as {
        addEventListener: HTMLElement["addEventListener"];
        removeEventListener: HTMLElement["removeEventListener"];
        setPointerCapture?: (id: number) => void;
        releasePointerCapture?: (id: number) => void;
        style: CSSStyleDeclaration;
      };
      pointerEl.style.cursor = "grab";
      pointerEl.style.touchAction = "none";

      const disableMapInteractions = () => {
        try { map.dragging.disable(); } catch { /* noop */ }
        try { (map as { scrollWheelZoom?: { disable: () => void } }).scrollWheelZoom?.disable(); } catch { /* noop */ }
        try { (map as { touchZoom?: { disable: () => void } }).touchZoom?.disable(); } catch { /* noop */ }
        try { (map as { boxZoom?: { disable: () => void } }).boxZoom?.disable(); } catch { /* noop */ }
        try { (map as { doubleClickZoom?: { disable: () => void } }).doubleClickZoom?.disable(); } catch { /* noop */ }
      };
      const enableMapInteractions = () => {
        try { map.dragging.enable(); } catch { /* noop */ }
        try { (map as { scrollWheelZoom?: { enable: () => void } }).scrollWheelZoom?.enable(); } catch { /* noop */ }
        try { (map as { touchZoom?: { enable: () => void } }).touchZoom?.enable(); } catch { /* noop */ }
        try { (map as { boxZoom?: { enable: () => void } }).boxZoom?.enable(); } catch { /* noop */ }
        try { (map as { doubleClickZoom?: { enable: () => void } }).doubleClickZoom?.enable(); } catch { /* noop */ }
      };

      const onPointerDown = (e: PointerEvent) => {
        if (e.button !== undefined && e.button !== 0) return;
        // Closeout-locked sessions: drag is a no-op. Card click still works.
        if (closeoutLockedRef.current) return;
        e.preventDefault();
        e.stopPropagation();
        dragging = true;
        activePointerId = e.pointerId;
        downClientX = e.clientX;
        downClientY = e.clientY;
        movedPastThreshold = false;
        try { pointerEl.setPointerCapture?.(e.pointerId); } catch { /* noop */ }
        photoDragActiveRef.current = true;
        disableMapInteractions();
        pointerEl.style.cursor = "grabbing";
      };

      const onPointerMove = (e: PointerEvent) => {
        if (!dragging) return;
        if (activePointerId !== null && e.pointerId !== activePointerId) return;
        e.preventDefault();
        e.stopPropagation();
        const dx = e.clientX - downClientX;
        const dy = e.clientY - downClientY;
        if (!movedPastThreshold) {
          if (Math.abs(dx) < DRAG_THRESHOLD_PX && Math.abs(dy) < DRAG_THRESHOLD_PX) return;
          movedPastThreshold = true;
        }
        const container = map.getContainer();
        const rect = container.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const ll = map.containerPointToLatLng(L.point(x, y));
        marker.setLatLng(ll);
      };

      const finishDrag = (e: PointerEvent | null) => {
        if (!dragging) return;
        dragging = false;
        if (e) {
          e.preventDefault();
          e.stopPropagation();
        }
        try {
          if (activePointerId !== null) pointerEl.releasePointerCapture?.(activePointerId);
        } catch {
          // noop
        }
        activePointerId = null;
        enableMapInteractions();
        pointerEl.style.cursor = "grab";
        photoDragActiveRef.current = false;
        if (movedPastThreshold) {
          const ll = marker.getLatLng();
          const save = savePhotoAdjustmentRef.current;
          if (save) void save(photoId, ll.lat, ll.lng);
        }
      };

      const onPointerUp = (e: PointerEvent) => finishDrag(e);
      const onPointerCancel = (e: PointerEvent) => finishDrag(e);

      pointerEl.addEventListener("pointerdown", onPointerDown as EventListener);
      pointerEl.addEventListener("pointermove", onPointerMove as EventListener);
      pointerEl.addEventListener("pointerup", onPointerUp as EventListener);
      pointerEl.addEventListener("pointercancel", onPointerCancel as EventListener);
    }

    // Raw GPS evidence trail for the selected field session. Drawn BEFORE
    // the violet snapped/interpolated route so the snapped path stays visually
    // dominant. Light slate, dashed, semi-transparent — looks like noisy GPS
    // evidence rather than primary geometry. Coords are intentionally NOT
    // added to allPoints; the trail never influences fitBounds.
    if (fieldTrailCoords.length >= 2) {
      const trail = L.polyline(fieldTrailCoords, {
        color: "#94a3b8",
        weight: 2,
        opacity: 0.45,
        dashArray: "4 6",
        lineCap: "round",
        lineJoin: "round",
        interactive: false,
      });
      if (showFieldGpsTrailRef.current) trail.addTo(map);
      fieldTrailLayerRef.current = trail;
    }

    // Selected field-submission overlay: violet ring markers + a thin dashed
    // connector. Connector geometry follows the KMZ design subpath between
    // the min and max station footage so it traces the curved design path
    // rather than cutting straight chords between projected stations —
    // verbatim parity with RedlineMap's fieldStationPath behavior. Falls
    // back to straight lines through projected coords when footage is not
    // finite or KMZ geometry is unavailable. Drawn last so it sits above all
    // other layers as the focused selection. Coords are intentionally NOT
    // added to allPoints — fitBounds stays anchored to design+redline+station
    // geometry per spec.
    if (fieldStations.length >= 2) {
      const finiteFts = fieldStations
        .map((s) => s.stationFt)
        .filter((ft): ft is number => Number.isFinite(ft));
      let path: Array<[number, number]> | null = null;
      if (finiteFts.length >= 2 && kmzSnapPolylines.length > 0) {
        const startFt = Math.min(...finiteFts);
        const endFt = Math.max(...finiteFts);
        const subCoords = kmzSubpathCoordsByDistanceRangeFt(
          kmzSnapPolylines,
          startFt,
          endFt,
        );
        if (subCoords.length >= 2) {
          path = subCoords.map((c) => [c[0], c[1]] as [number, number]);
        }
      }
      if (!path) {
        path = fieldStations.map(
          (s) => [s.displayLat, s.displayLon] as [number, number],
        );
      }
      const connector = L.polyline(path, {
        color: "#a855f7",
        weight: 2.5,
        opacity: 0.6,
        dashArray: "4 4",
      });
      if (showFieldSubmissionRef.current) connector.addTo(map);
      fieldConnectorLayerRef.current = connector;
    }
    for (let fsIdx = 0; fsIdx < fieldStations.length; fsIdx++) {
      const fs = fieldStations[fsIdx];
      const marker = L.circleMarker([fs.displayLat, fs.displayLon], {
        radius: 5.8,
        color: "#7c3aed",
        weight: 2.5,
        fillColor: "#a855f7",
        fillOpacity: 0.18,
      });
      if (showFieldSubmissionRef.current) marker.addTo(map);
      if (fs.label) {
        try {
          marker.bindTooltip(fs.label, {
            permanent: true,
            direction: "top",
            offset: [0, -2],
            className: "tl-field-station-label",
            opacity: 1,
          });
        } catch {
          // noop
        }
      }
      // Capture fsIdx so the card knows which row to display. Selecting a field
      // station also closes any open normal-station inspector.
      const capturedFsIdx = fsIdx;
      marker.on("click", (evt) => {
        L.DomEvent.stopPropagation(evt);
        setSelectedStationIndex(null);
        setSelectedPhotoPointIdx(null);
        setSelectedFieldPhotoIdx(null);
        setSelectedBridgedPhotoIdx(null);
        // Click-toggle parity with legacy: clicking the same field station
        // again clears the selection.
        setSelectedFieldStationIdx((cur) =>
          cur === capturedFsIdx ? null : capturedFsIdx,
        );
      });
      marker.on("mouseover", () => {
        setHoverFieldStationIdx(capturedFsIdx);
      });
      marker.on("mouseout", () => {
        setHoverFieldStationIdx((current) =>
          current === capturedFsIdx ? null : current,
        );
      });
      fieldStationLayersRef.current.push(marker);
    }

    // Selected field-submission photos: bright cyan markers, drawn last so
    // they sit above the violet overlay. Source is the already-fetched
    // JobDetail; coords are intentionally NOT added to allPoints — fitBounds
    // stays anchored to design+redline+station geometry per spec.
    for (let fpIdx = 0; fpIdx < fieldPhotos.length; fpIdx++) {
      const fp = fieldPhotos[fpIdx];
      const marker = L.circleMarker([fp.lat, fp.lon], {
        radius: 4.7,
        color: "#155e75",
        weight: 1.25,
        fillColor: "#22d3ee",
        fillOpacity: 0.92,
      });
      if (showFieldPhotosRef.current) marker.addTo(map);
      try {
        marker.bindTooltip(fp.label, {
          direction: "top",
          offset: [0, -2],
          sticky: true,
          opacity: 0.95,
          className: "tl-field-photo-label",
        });
      } catch {
        // noop
      }
      // Stop propagation so background-click handler doesn't immediately clear
      // the selection. Selecting a photo closes any other open panel.
      const capturedFpIdx = fpIdx;
      marker.on("click", (evt) => {
        L.DomEvent.stopPropagation(evt);
        setSelectedStationIndex(null);
        setSelectedPhotoPointIdx(null);
        setSelectedFieldStationIdx(null);
        setSelectedBridgedPhotoIdx(null);
        setSelectedFieldPhotoIdx(capturedFpIdx);
      });
      fieldPhotoLayersRef.current.push(marker);
    }

    // NOTE: bridged client-side geotagged photos are NOT created here.
    // They are managed by a dedicated effect below so that drag overrides
    // never trigger this geometry rebuild (which would call fitBounds and
    // tear down every other layer).

    if (allPoints.length >= 2) {
      const bounds = L.latLngBounds(allPoints);
      if (bounds.isValid()) {
        map.fitBounds(bounds, { padding: [24, 24], maxZoom: 19 });
      }
    } else if (allPoints.length === 0) {
      // Workspace is empty/cleared: reset to a neutral overview so we don't
      // keep the previous project's camera position.
      map.setView(EMPTY_DEFAULT_CENTER, EMPTY_DEFAULT_ZOOM);
    }
  }, [
    kmzLines,
    kmzPolygons,
    redlineSegments,
    stationPoints,
    photoPoints,
    fieldStations,
    fieldPhotos,
    sourceFileToLayerId,
    fieldTrailCoords,
  ]);

  // Bridged client-side geotagged photos (source_type "client_geotagged_temp")
  // are managed in a dedicated effect, NOT in the main geometry effect.
  // This is intentional: dropping a dragged bridged photo updates an in-
  // session override map → effectiveBridgedPhotos changes → without this
  // split, the main geometry effect would re-run on every drop, tear down
  // every other layer, and call fitBounds. Decoupling here keeps drop a
  // pure, layer-local update with NO fitBounds / no setView / no flash
  // through KMZ/redline/station/field/photo layers.
  useEffect(() => {
    const map = mapRef.current;
    const L = leafletRef.current;
    if (!map || !L) return;

    // Tear down previous bridged markers only.
    for (const layer of bridgedGpsPhotoLayersRef.current) {
      try {
        layer.remove();
      } catch {
        // noop
      }
    }
    bridgedGpsPhotoLayersRef.current = [];

    for (let bgpIdx = 0; bgpIdx < effectiveBridgedPhotos.length; bgpIdx++) {
      const bgp = effectiveBridgedPhotos[bgpIdx];
      const origLat = Number(bgp.lat);
      const origLon = Number(bgp.lon);
      if (!Number.isFinite(origLat) || !Number.isFinite(origLon)) continue;
      const dispLat =
        typeof bgp.displayLat === "number" && Number.isFinite(bgp.displayLat)
          ? bgp.displayLat
          : origLat;
      const dispLon =
        typeof bgp.displayLon === "number" && Number.isFinite(bgp.displayLon)
          ? bgp.displayLon
          : origLon;
      const marker = L.circleMarker([dispLat, dispLon], {
        radius: 7,
        color: "#0c4a6e",
        weight: 1.5,
        fillColor: "#38bdf8",
        fillOpacity: 0.92,
      });
      marker.addTo(map);
      try {
        marker.bindTooltip(bgp.filename || "Photo", {
          direction: "top",
          offset: [0, -2],
          sticky: true,
          opacity: 0.95,
          className: "tl-photo-label",
        });
      } catch {
        // noop
      }
      const capturedBgpIdx = bgpIdx;
      const photoId = bgp.id;

      let dragging = false;
      let activePointerId: number | null = null;
      let downClientX = 0;
      let downClientY = 0;
      let movedPastThreshold = false;
      const DRAG_THRESHOLD_PX = 3;

      marker.on("click", (evt) => {
        if (movedPastThreshold) {
          movedPastThreshold = false;
          L.DomEvent.stopPropagation(evt);
          return;
        }
        L.DomEvent.stopPropagation(evt);
        setSelectedStationIndex(null);
        setSelectedFieldStationIdx(null);
        setSelectedFieldPhotoIdx(null);
        setSelectedPhotoPointIdx(null);
        setSelectedBridgedPhotoIdx(capturedBgpIdx);
      });

      bridgedGpsPhotoLayersRef.current.push(marker);

      const elNode = (
        marker as unknown as { getElement?: () => Element | null }
      ).getElement?.() as HTMLElement | SVGElement | null;
      if (!photoId || !elNode) continue;
      const pointerEl = elNode as unknown as {
        addEventListener: HTMLElement["addEventListener"];
        removeEventListener: HTMLElement["removeEventListener"];
        setPointerCapture?: (id: number) => void;
        releasePointerCapture?: (id: number) => void;
        style: CSSStyleDeclaration;
      };
      pointerEl.style.cursor = "grab";
      pointerEl.style.touchAction = "none";

      const disableMapInteractions = () => {
        try { map.dragging.disable(); } catch { /* noop */ }
        try { (map as { scrollWheelZoom?: { disable: () => void } }).scrollWheelZoom?.disable(); } catch { /* noop */ }
        try { (map as { touchZoom?: { disable: () => void } }).touchZoom?.disable(); } catch { /* noop */ }
        try { (map as { boxZoom?: { disable: () => void } }).boxZoom?.disable(); } catch { /* noop */ }
        try { (map as { doubleClickZoom?: { disable: () => void } }).doubleClickZoom?.disable(); } catch { /* noop */ }
      };
      const enableMapInteractions = () => {
        try { map.dragging.enable(); } catch { /* noop */ }
        try { (map as { scrollWheelZoom?: { enable: () => void } }).scrollWheelZoom?.enable(); } catch { /* noop */ }
        try { (map as { touchZoom?: { enable: () => void } }).touchZoom?.enable(); } catch { /* noop */ }
        try { (map as { boxZoom?: { enable: () => void } }).boxZoom?.enable(); } catch { /* noop */ }
        try { (map as { doubleClickZoom?: { enable: () => void } }).doubleClickZoom?.enable(); } catch { /* noop */ }
      };

      const onPointerDown = (e: PointerEvent) => {
        if (e.button !== undefined && e.button !== 0) return;
        if (closeoutLockedRef.current) return;
        e.preventDefault();
        e.stopPropagation();
        dragging = true;
        activePointerId = e.pointerId;
        downClientX = e.clientX;
        downClientY = e.clientY;
        movedPastThreshold = false;
        try { pointerEl.setPointerCapture?.(e.pointerId); } catch { /* noop */ }
        photoDragActiveRef.current = true;
        disableMapInteractions();
        pointerEl.style.cursor = "grabbing";
      };

      const onPointerMove = (e: PointerEvent) => {
        if (!dragging) return;
        if (activePointerId !== null && e.pointerId !== activePointerId) return;
        e.preventDefault();
        e.stopPropagation();
        const dx = e.clientX - downClientX;
        const dy = e.clientY - downClientY;
        if (!movedPastThreshold) {
          if (Math.abs(dx) < DRAG_THRESHOLD_PX && Math.abs(dy) < DRAG_THRESHOLD_PX) return;
          movedPastThreshold = true;
        }
        const container = map.getContainer();
        const rect = container.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const ll = map.containerPointToLatLng(L.point(x, y));
        marker.setLatLng(ll);
      };

      const finishDrag = (e: PointerEvent | null) => {
        if (!dragging) return;
        dragging = false;
        if (e) {
          e.preventDefault();
          e.stopPropagation();
        }
        try {
          if (activePointerId !== null) pointerEl.releasePointerCapture?.(activePointerId);
        } catch {
          // noop
        }
        activePointerId = null;
        enableMapInteractions();
        pointerEl.style.cursor = "grab";
        photoDragActiveRef.current = false;
        if (movedPastThreshold) {
          const ll = marker.getLatLng();
          // In-session override write — mutates only the override map. The
          // bridged photo's lat/lon (Original Geotag) is never touched.
          // Because this effect (not the main geometry effect) is the only
          // one watching effectiveBridgedPhotos, the resulting state change
          // re-runs only this effect. fitBounds is never called.
          setBridgedPhotoOverrides((prev) => ({
            ...prev,
            [photoId]: { lat: ll.lat, lon: ll.lng },
          }));
        }
      };

      const onPointerUp = (e: PointerEvent) => finishDrag(e);
      const onPointerCancel = (e: PointerEvent) => finishDrag(e);

      pointerEl.addEventListener("pointerdown", onPointerDown as EventListener);
      pointerEl.addEventListener("pointermove", onPointerMove as EventListener);
      pointerEl.addEventListener("pointerup", onPointerUp as EventListener);
      pointerEl.addEventListener("pointercancel", onPointerCancel as EventListener);
    }
  }, [effectiveBridgedPhotos]);

  // Toggle effects: add/remove already-drawn layers from the map without
  // touching geometry. Bypasses the geometry render-effect, so toggling does
  // not re-fit the map.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const layers = stationLayersRef.current;
    const ids = stationLayerIdsRef.current;
    for (let i = 0; i < layers.length; i++) {
      const id = ids[i];
      const visible = showStations && (!id || !hiddenLayers.has(id));
      const layer = layers[i];
      if (visible) {
        if (!map.hasLayer(layer)) layer.addTo(map);
      } else if (map.hasLayer(layer)) {
        map.removeLayer(layer);
      }
    }
  }, [showStations, hiddenLayers]);

  // Evidence-layer visibility for redlines. Add/remove existing polylines
  // based on hiddenLayers without touching geometry, mirroring the station
  // toggle pattern above.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const layers = redlineLayersRef.current;
    const ids = redlineLayerIdsRef.current;
    for (let i = 0; i < layers.length; i++) {
      const id = ids[i];
      const visible = !id || !hiddenLayers.has(id);
      const layer = layers[i];
      if (visible) {
        if (!map.hasLayer(layer)) layer.addTo(map);
      } else if (map.hasLayer(layer)) {
        map.removeLayer(layer);
      }
    }
  }, [hiddenLayers]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    for (const layer of fieldStationLayersRef.current) {
      if (showFieldSubmission) {
        if (!map.hasLayer(layer)) layer.addTo(map);
      } else if (map.hasLayer(layer)) {
        map.removeLayer(layer);
      }
    }
    const connector = fieldConnectorLayerRef.current;
    if (connector) {
      if (showFieldSubmission) {
        if (!map.hasLayer(connector)) connector.addTo(map);
      } else if (map.hasLayer(connector)) {
        map.removeLayer(connector);
      }
    }
  }, [showFieldSubmission]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    for (const layer of fieldPhotoLayersRef.current) {
      if (showFieldPhotos) {
        if (!map.hasLayer(layer)) layer.addTo(map);
      } else if (map.hasLayer(layer)) {
        map.removeLayer(layer);
      }
    }
  }, [showFieldPhotos]);

  // GPS evidence trail visibility. Pure imperative add/remove on the existing
  // polyline ref — never re-runs the geometry effect, so toggling can't move
  // the camera or rebuild any other layer.
  useEffect(() => {
    const map = mapRef.current;
    const trail = fieldTrailLayerRef.current;
    if (!map || !trail) return;
    if (showFieldGpsTrail) {
      if (!map.hasLayer(trail)) trail.addTo(map);
    } else if (map.hasLayer(trail)) {
      map.removeLayer(trail);
    }
  }, [showFieldGpsTrail]);

  // If the underlying station_points array shrinks past the selected index
  // (e.g., backend update mid-session), drop the selection rather than
  // pointing at a stale row.
  useEffect(() => {
    if (selectedStationIndex !== null && selectedStationIndex >= stationPoints.length) {
      setSelectedStationIndex(null);
    }
  }, [stationPoints, selectedStationIndex]);

  useEffect(() => {
    if (selectedFieldStationIdx !== null && selectedFieldStationIdx >= fieldStations.length) {
      setSelectedFieldStationIdx(null);
    }
  }, [fieldStations, selectedFieldStationIdx]);

  // ── Photo Move-Mode plumbing ──────────────────────────────────────────
  // Closeout-lock signal mirrors the upload's server-side gate. When the
  // closeout is locked we render Move/Reset as disabled with a message; the
  // backend would also 403 the request.
  const closeoutLocked = useMemo(() => {
    return Boolean(state?.closeout_lock?.is_locked || state?.closeout_locked);
  }, [state?.closeout_lock?.is_locked, state?.closeout_locked]);

  // Patch a single photo_points entry inside `state` so the photoPoints memo
  // recomputes and the underlying circleMarker moves to the new display
  // position immediately. Original Geotag (lat/lon) is never touched here —
  // we only ever mutate adjusted_lat / adjusted_lon / adjusted_at /
  // is_adjusted, which is exactly what the backend returns.
  const patchPhotoPoint = useCallback(
    (
      photoId: string,
      patch: {
        adjusted_lat: number | null;
        adjusted_lon: number | null;
        adjusted_at: string | null;
        is_adjusted: boolean;
      },
    ) => {
      setState((prev) => {
        if (!prev || !Array.isArray(prev.photo_points)) return prev;
        const next = prev.photo_points.map((p) => {
          if (String(p.id ?? "") !== photoId) return p;
          return {
            ...p,
            adjusted_lat: patch.adjusted_lat,
            adjusted_lon: patch.adjusted_lon,
            adjusted_at: patch.adjusted_at,
            is_adjusted: patch.is_adjusted,
          };
        });
        return { ...prev, photo_points: next };
      });
    },
    [],
  );

  const savePhotoAdjustment = useCallback(
    async (
      photoId: string,
      adjustedLat: number | null,
      adjustedLon: number | null,
    ) => {
      if (!photoId) return;
      setPhotoMoveSaving(true);
      setPhotoMoveError(null);
      try {
        const url = appendSessionId(
          `${API_BASE}/api/station-photos/${encodeURIComponent(photoId)}/adjust`,
          projectId,
        );
        const res = await apiFetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            adjusted_lat: adjustedLat,
            adjusted_lon: adjustedLon,
          }),
        });
        const data = (await res.json().catch(() => ({}))) as {
          success?: boolean;
          error?: string;
          photo?: {
            adjusted_lat?: number | null;
            adjusted_lon?: number | null;
            adjusted_at?: string | null;
            is_adjusted?: boolean;
          };
        };
        acceptSessionFromMutation(data, projectId);
        if (!res.ok || data.success === false) {
          throw new Error(data.error || "Unable to save displayed position.");
        }
        const photo = data.photo ?? {};
        patchPhotoPoint(photoId, {
          adjusted_lat:
            typeof photo.adjusted_lat === "number" ? photo.adjusted_lat : null,
          adjusted_lon:
            typeof photo.adjusted_lon === "number" ? photo.adjusted_lon : null,
          adjusted_at:
            typeof photo.adjusted_at === "string" ? photo.adjusted_at : null,
          is_adjusted: Boolean(photo.is_adjusted),
        });
      } catch (e) {
        setPhotoMoveError(
          e instanceof Error ? e.message : "Unable to save displayed position.",
        );
      } finally {
        setPhotoMoveSaving(false);
      }
    },
    [projectId, patchPhotoPoint],
  );

  const resetPhotoToOriginal = useCallback(
    async (photoId: string) => {
      if (closeoutLocked || !photoId) return;
      await savePhotoAdjustment(photoId, null, null);
    },
    [closeoutLocked, savePhotoAdjustment],
  );

  // Ref-mirrors so the per-photo drag handlers attached inside the geometry
  // render-effect can read latest values without taking these as dependencies
  // (which would re-fit the map on every photoMoveSaving toggle / closeout
  // toggle / save-callback identity change).
  const savePhotoAdjustmentRef = useRef(savePhotoAdjustment);
  useEffect(() => {
    savePhotoAdjustmentRef.current = savePhotoAdjustment;
  }, [savePhotoAdjustment]);
  const closeoutLockedRef = useRef(closeoutLocked);
  useEffect(() => {
    closeoutLockedRef.current = closeoutLocked;
  }, [closeoutLocked]);
  // Tracks whether ANY photo marker is mid-drag, so the photoPoints stale-id
  // guard / inspector close handlers don't tear the marker out underfoot.
  const photoDragActiveRef = useRef(false);


  // Hover stale-index guards. Hover layers are rebuilt by the geometry effect
  // when stationPoints / fieldStations change; clear any hover index that no
  // longer corresponds to a real layer.
  useEffect(() => {
    if (hoverStationIndex !== null && hoverStationIndex >= stationPoints.length) {
      setHoverStationIndex(null);
    }
  }, [stationPoints, hoverStationIndex]);

  useEffect(() => {
    if (hoverFieldStationIdx !== null && hoverFieldStationIdx >= fieldStations.length) {
      setHoverFieldStationIdx(null);
    }
  }, [fieldStations, hoverFieldStationIdx]);

  // Hover label visibility: when a station or field station is hovered, force
  // its label visible even when the map is below the normal label zoom
  // threshold. Implemented by toggling a "--force" class on the tooltip's
  // DOM element so existing zoom-gated CSS still hides every other label.
  // Pure DOM class mutation: no map ref calls, no fitBounds, no marker
  // recreation, no geometry rebuild.
  useEffect(() => {
    const stationLayers = stationLayersRef.current;
    for (let i = 0; i < stationLayers.length; i++) {
      const tip = stationLayers[i].getTooltip?.();
      const el = tip?.getElement?.() as HTMLElement | undefined;
      if (!el) continue;
      el.classList.toggle("tl-station-label--force", i === hoverStationIndex);
    }
  }, [hoverStationIndex, stationPoints]);

  useEffect(() => {
    const fsLayers = fieldStationLayersRef.current;
    for (let i = 0; i < fsLayers.length; i++) {
      const tip = fsLayers[i].getTooltip?.();
      const el = tip?.getElement?.() as HTMLElement | undefined;
      if (!el) continue;
      el.classList.toggle(
        "tl-field-station-label--force",
        i === hoverFieldStationIdx,
      );
    }
  }, [hoverFieldStationIdx, fieldStations]);

  useEffect(() => {
    if (selectedFieldPhotoIdx !== null && selectedFieldPhotoIdx >= fieldPhotos.length) {
      setSelectedFieldPhotoIdx(null);
    }
  }, [fieldPhotos, selectedFieldPhotoIdx]);

  useEffect(() => {
    if (selectedPhotoPointIdx !== null && selectedPhotoPointIdx >= photoPoints.length) {
      setSelectedPhotoPointIdx(null);
    }
  }, [photoPoints, selectedPhotoPointIdx]);

  useEffect(() => {
    if (selectedBridgedPhotoIdx !== null && selectedBridgedPhotoIdx >= effectiveBridgedPhotos.length) {
      setSelectedBridgedPhotoIdx(null);
    }
  }, [effectiveBridgedPhotos, selectedBridgedPhotoIdx]);

  // ── Station inspector — photo workflow plumbing ────────────────────────
  // The composite station_identity key is what the backend uses to attach
  // photos to a station. Construct it the same way RedlineMap does so photos
  // are addressable from either map.
  const routeName = useMemo(
    () => state?.selected_route_name || state?.route_name || "",
    [state?.selected_route_name, state?.route_name],
  );

  const selectedStation = useMemo(() => {
    if (selectedStationIndex === null) return null;
    return stationPoints[selectedStationIndex] ?? null;
  }, [selectedStationIndex, stationPoints]);

  const selectedStationIdentity = useMemo(
    () => buildStationIdentity(routeName, selectedStation?.source ?? null),
    [routeName, selectedStation],
  );

  const selectedStationSummary = useMemo(
    () => buildStationSummary(routeName, selectedStation?.source ?? null),
    [routeName, selectedStation],
  );

  const fetchStationPhotos = useCallback(
    async (identity: string) => {
      if (!identity) {
        setStationPhotos([]);
        return;
      }
      setStationPhotosLoading(true);
      setStationPhotoError(null);
      try {
        const res = await apiFetch(
          appendSessionIdReadOnly(
            `${API_BASE}/api/station-photos?station_identity=${encodeURIComponent(identity)}`,
            projectId,
          ),
          { cache: "no-store" },
        );
        const data = await res.json();
        if (!res.ok || data.success === false) {
          throw new Error(data.error || "Unable to load station photos.");
        }
        setStationPhotos(Array.isArray(data.photos) ? data.photos : []);
      } catch (e) {
        setStationPhotos([]);
        setStationPhotoError(
          e instanceof Error ? e.message : "Unable to load station photos.",
        );
      } finally {
        setStationPhotosLoading(false);
      }
    },
    [projectId],
  );

  const handleStationPhotoUpload = useCallback(
    async (files: FileList | null) => {
      if (!files || !files.length || !selectedStation || !selectedStationIdentity) {
        return;
      }
      const sp = selectedStation.source;
      setStationPhotoBusy(true);
      setStationPhotoError(null);
      try {
        const form = new FormData();
        form.append("station_identity", selectedStationIdentity);
        form.append("station_summary", selectedStationSummary);
        form.append("route_name", routeName);
        form.append("source_file", String(sp.source_file ?? ""));
        form.append("station_label", String(sp.station ?? ""));
        form.append(
          "mapped_station_ft",
          stationIdentityPart(sp.mapped_station_ft, 3),
        );
        form.append("lat", stationIdentityPart(sp.lat, 8));
        form.append("lon", stationIdentityPart(sp.lon, 8));
        Array.from(files).forEach((file) => form.append("files", file));
        appendSessionIdToForm(form, projectId);

        const res = await apiFetch(`${API_BASE}/api/station-photos/upload`, {
          method: "POST",
          body: form,
        });
        const data = await res.json();
        acceptSessionFromMutation(data, projectId);
        if (!res.ok || data.success === false) {
          throw new Error(data.error || "Station photo upload failed.");
        }
        await fetchStationPhotos(selectedStationIdentity);
      } catch (e) {
        setStationPhotoError(
          e instanceof Error ? e.message : "Station photo upload failed.",
        );
      } finally {
        setStationPhotoBusy(false);
      }
    },
    [
      projectId,
      selectedStation,
      selectedStationIdentity,
      selectedStationSummary,
      routeName,
      fetchStationPhotos,
    ],
  );

  // Refetch photos whenever the selected station identity changes. Clearing
  // the selection drops the photo list to keep the inspector empty-state
  // consistent with the legacy map.
  useEffect(() => {
    if (!selectedStation || !selectedStationIdentity) {
      setStationPhotos([]);
      setStationPhotoError(null);
      return;
    }
    void fetchStationPhotos(selectedStationIdentity);
  }, [selectedStation, selectedStationIdentity, fetchStationPhotos]);

  // Selected/hover station highlight: walk the (post-render) station layers
  // and restyle. Selected wins over hover; hover bumps radius and stroke
  // subtly so the operator gets feedback without losing focus on the active
  // selection. Declared after the geometry render-effect so it runs after
  // fresh markers are pushed into stationLayersRef. Never touches geometry
  // and never calls fitBounds.
  useEffect(() => {
    const layers = stationLayersRef.current;
    for (let i = 0; i < layers.length; i++) {
      const isSelected = i === selectedStationIndex;
      const isHovered = !isSelected && i === hoverStationIndex;
      try {
        layers[i].setStyle({
          radius: isSelected ? 6.8 : isHovered ? 5.8 : 4.8,
          weight: isSelected ? 2 : isHovered ? 1.5 : 1,
          color: isSelected ? "#f59e0b" : isHovered ? "#b45309" : "#0f172a",
          fillColor: "#facc15",
          fillOpacity: isSelected ? 0.95 : isHovered ? 1 : 0.95,
        });
      } catch {
        // noop
      }
    }
  }, [selectedStationIndex, hoverStationIndex, stationPoints]);

  // Selected/hover field station highlight: same restyle pattern as normal
  // stations. Selected wins over hover. Runs after the geometry render-effect
  // populates fieldStationLayersRef.
  useEffect(() => {
    const layers = fieldStationLayersRef.current;
    for (let i = 0; i < layers.length; i++) {
      const isSelected = i === selectedFieldStationIdx;
      const isHovered = !isSelected && i === hoverFieldStationIdx;
      try {
        layers[i].setStyle({
          radius: isSelected ? 7 : isHovered ? 6.3 : 5.8,
          weight: isSelected ? 3 : isHovered ? 2.8 : 2.5,
          color: isSelected ? "#facc15" : "#7c3aed",
          fillColor: "#a855f7",
          fillOpacity: isSelected ? 0.45 : isHovered ? 0.3 : 0.18,
        });
      } catch {
        // noop
      }
    }
  }, [selectedFieldStationIdx, hoverFieldStationIdx, fieldStations]);

  // Manual fit handlers. Each builds a points list from a single layer family
  // and calls fitBounds with the same padding/maxZoom contract as the initial
  // fit. No-op when there isn't enough geometry.
  const fitToPoints = useCallback((points: Array<[number, number]>) => {
    const map = mapRef.current;
    const L = leafletRef.current;
    if (!map || !L || points.length === 0) return;
    if (points.length === 1) {
      map.setView(points[0], 18);
      return;
    }
    const bounds = L.latLngBounds(points);
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [24, 24], maxZoom: 19 });
    }
  }, []);

  const handleFitAll = useCallback(() => {
    const points: Array<[number, number]> = [];
    for (const f of kmzPolygons) for (const p of f.coords) points.push(p);
    for (const f of kmzLines) for (const p of f.coords) points.push(p);
    for (const seg of redlineSegments) for (const p of seg.coords) points.push(p);
    for (const sp of stationPoints) points.push([sp.displayLat, sp.displayLon]);
    fitToPoints(points);
  }, [kmzPolygons, kmzLines, redlineSegments, stationPoints, fitToPoints]);

  const handleFitStations = useCallback(() => {
    fitToPoints(
      stationPoints.map((s) => [s.displayLat, s.displayLon] as [number, number]),
    );
  }, [stationPoints, fitToPoints]);

  const handleFitFieldSubmission = useCallback(() => {
    fitToPoints(
      fieldStations.map((s) => [s.displayLat, s.displayLon] as [number, number]),
    );
  }, [fieldStations, fitToPoints]);

  const hasRenderableGeometry =
    kmzLines.length > 0 ||
    kmzPolygons.length > 0 ||
    redlineSegments.length > 0 ||
    stationPoints.length > 0 ||
    photoPoints.length > 0 ||
    fieldStations.length > 0 ||
    fieldPhotos.length > 0;

  return (
    <section
      className="tl-card"
      style={{
        overflow: "hidden",
        padding: 0,
        background: "var(--tl-surface)",
        marginBottom: 14,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 10,
          flexWrap: "wrap",
          padding: "12px 14px",
          borderBottom: "1px solid var(--tl-border)",
        }}
      >
        <div>
          <h2 style={{ margin: 0, fontSize: 16, lineHeight: 1.3, color: "var(--tl-text)" }}>
            Project Map
          </h2>
          <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--tl-text-muted)" }}>
            Design, redlines, stations, photos, and field verification on one operational map.
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button
            type="button"
            className="tl-btn tl-btn-ghost"
            style={{ fontSize: 12, padding: "6px 10px", opacity: baseStyle === "standard" ? 1 : 0.85 }}
            onClick={() => setBaseStyle("standard")}
          >
            Standard
          </button>
          <button
            type="button"
            className="tl-btn tl-btn-ghost"
            style={{ fontSize: 12, padding: "6px 10px", opacity: baseStyle === "satellite" ? 1 : 0.85 }}
            onClick={() => setBaseStyle("satellite")}
          >
            Satellite
          </button>
        </div>
      </div>

      <div style={{ position: "relative", height: 560, background: "#0b1220" }}>
        <style>{`
          .tl-modern-hero-map .leaflet-tooltip.tl-station-label {
            background: rgba(15, 23, 42, 0.78);
            color: #fff;
            border: none;
            border-radius: 3px;
            padding: 1px 5px;
            font-size: 10px;
            font-weight: 600;
            line-height: 1.25;
            letter-spacing: 0.01em;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.25);
            white-space: nowrap;
            pointer-events: none;
          }
          .tl-modern-hero-map .leaflet-tooltip.tl-station-label::before,
          .tl-modern-hero-map .leaflet-tooltip-top.tl-station-label::before,
          .tl-modern-hero-map .leaflet-tooltip-bottom.tl-station-label::before,
          .tl-modern-hero-map .leaflet-tooltip-left.tl-station-label::before,
          .tl-modern-hero-map .leaflet-tooltip-right.tl-station-label::before {
            display: none;
          }
          .tl-modern-hero-map[data-show-labels="false"] .leaflet-tooltip.tl-station-label {
            display: none;
          }
          .tl-modern-hero-map[data-show-labels="false"] .leaflet-tooltip.tl-station-label.tl-station-label--force {
            display: block;
          }
          .tl-modern-hero-map .leaflet-tooltip.tl-photo-label {
            background: rgba(8, 47, 73, 0.85);
            color: #e0f2fe;
            border: none;
            border-radius: 3px;
            padding: 2px 6px;
            font-size: 10px;
            font-weight: 600;
            line-height: 1.25;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
            white-space: nowrap;
            pointer-events: none;
          }
          .tl-modern-hero-map .leaflet-tooltip.tl-photo-label::before,
          .tl-modern-hero-map .leaflet-tooltip-top.tl-photo-label::before,
          .tl-modern-hero-map .leaflet-tooltip-bottom.tl-photo-label::before,
          .tl-modern-hero-map .leaflet-tooltip-left.tl-photo-label::before,
          .tl-modern-hero-map .leaflet-tooltip-right.tl-photo-label::before {
            display: none;
          }
          .tl-modern-hero-map .leaflet-tooltip.tl-field-station-label {
            background: rgba(76, 29, 149, 0.85);
            color: #ede9fe;
            border: none;
            border-radius: 3px;
            padding: 1px 5px;
            font-size: 10px;
            font-weight: 700;
            line-height: 1.25;
            letter-spacing: 0.01em;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
            white-space: nowrap;
            pointer-events: none;
          }
          .tl-modern-hero-map .leaflet-tooltip.tl-field-station-label::before,
          .tl-modern-hero-map .leaflet-tooltip-top.tl-field-station-label::before,
          .tl-modern-hero-map .leaflet-tooltip-bottom.tl-field-station-label::before,
          .tl-modern-hero-map .leaflet-tooltip-left.tl-field-station-label::before,
          .tl-modern-hero-map .leaflet-tooltip-right.tl-field-station-label::before {
            display: none;
          }
          .tl-modern-hero-map[data-show-labels="false"] .leaflet-tooltip.tl-field-station-label {
            display: none;
          }
          .tl-modern-hero-map[data-show-labels="false"] .leaflet-tooltip.tl-field-station-label.tl-field-station-label--force {
            display: block;
          }
          .tl-modern-hero-map .leaflet-tooltip.tl-field-photo-label {
            background: rgba(8, 51, 68, 0.88);
            color: #cffafe;
            border: none;
            border-radius: 3px;
            padding: 2px 6px;
            font-size: 10px;
            font-weight: 600;
            line-height: 1.25;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
            white-space: nowrap;
            pointer-events: none;
          }
          .tl-modern-hero-map .leaflet-tooltip.tl-field-photo-label::before,
          .tl-modern-hero-map .leaflet-tooltip-top.tl-field-photo-label::before,
          .tl-modern-hero-map .leaflet-tooltip-bottom.tl-field-photo-label::before,
          .tl-modern-hero-map .leaflet-tooltip-left.tl-field-photo-label::before,
          .tl-modern-hero-map .leaflet-tooltip-right.tl-field-photo-label::before {
            display: none;
          }
          .tl-modern-hero-map-controls {
            position: absolute;
            top: 10px;
            right: 10px;
            z-index: 600;
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            justify-content: flex-end;
            max-width: calc(100% - 20px);
            pointer-events: none;
          }
          .tl-modern-hero-map-controls > button {
            pointer-events: auto;
            background: rgba(15, 23, 42, 0.85);
            color: #f1f5f9;
            border: 1px solid rgba(148, 163, 184, 0.4);
            border-radius: 999px;
            padding: 4px 10px;
            font-size: 11px;
            font-weight: 600;
            line-height: 1.4;
            cursor: pointer;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.25);
            transition: background 120ms ease, opacity 120ms ease;
          }
          .tl-modern-hero-map-controls > button:hover:not(:disabled) {
            background: rgba(15, 23, 42, 0.95);
          }
          .tl-modern-hero-map-controls > button:disabled {
            opacity: 0.4;
            cursor: not-allowed;
          }
          .tl-modern-hero-map-controls > button[data-active="false"]:not(:disabled) {
            opacity: 0.6;
          }
          .tl-modern-hero-map-inspector {
            position: absolute;
            top: 56px;
            right: 10px;
            z-index: 600;
            width: 280px;
            max-width: calc(100% - 20px);
            max-height: calc(100% - 76px);
            background: rgba(15, 23, 42, 0.92);
            color: #e2e8f0;
            border: 1px solid rgba(148, 163, 184, 0.3);
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35);
            overflow: hidden;
            display: flex;
            flex-direction: column;
          }
          .tl-modern-hero-map-inspector__head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 8px 10px;
            border-bottom: 1px solid rgba(148, 163, 184, 0.25);
            background: rgba(15, 23, 42, 0.55);
            flex: 0 0 auto;
          }
          .tl-modern-hero-map-inspector__title {
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            color: #cbd5e1;
          }
          .tl-modern-hero-map-inspector__close {
            background: transparent;
            border: none;
            color: #cbd5e1;
            font-size: 16px;
            line-height: 1;
            padding: 2px 8px;
            border-radius: 4px;
            cursor: pointer;
          }
          .tl-modern-hero-map-inspector__close:hover {
            background: rgba(148, 163, 184, 0.15);
            color: #fff;
          }
          .tl-modern-hero-map-inspector__body {
            padding: 6px 10px 10px;
            overflow-y: auto;
            flex: 1 1 auto;
          }
          .tl-modern-hero-map-inspector__row {
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            gap: 10px;
            padding: 4px 0;
            border-bottom: 1px solid rgba(148, 163, 184, 0.12);
          }
          .tl-modern-hero-map-inspector__row:last-child {
            border-bottom: none;
          }
          .tl-modern-hero-map-inspector__label {
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            color: #94a3b8;
            flex: 0 0 auto;
          }
          .tl-modern-hero-map-inspector__value {
            font-size: 12px;
            font-weight: 500;
            color: #f1f5f9;
            text-align: right;
            word-break: break-word;
            flex: 1 1 auto;
          }
          .tl-modern-hero-map-inspector__value--empty {
            color: #64748b;
          }
          .tl-modern-hero-map-inspector__photos {
            margin-top: 10px;
            padding-top: 10px;
            border-top: 1px solid rgba(148, 163, 184, 0.18);
            display: flex;
            flex-direction: column;
            gap: 8px;
          }
          .tl-modern-hero-map-inspector__photos-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            color: #94a3b8;
          }
          .tl-modern-hero-map-inspector__photos-count {
            font-variant-numeric: tabular-nums;
            font-size: 10px;
            font-weight: 700;
            color: #cbd5e1;
            background: rgba(148, 163, 184, 0.18);
            padding: 1px 7px;
            border-radius: 999px;
          }
          .tl-modern-hero-map-inspector__photos-status,
          .tl-modern-hero-map-inspector__photos-empty {
            font-size: 11px;
            color: #94a3b8;
            font-style: italic;
          }
          .tl-modern-hero-map-inspector__photos-error {
            font-size: 11px;
            font-weight: 600;
            color: #fca5a5;
            background: rgba(127, 29, 29, 0.4);
            border: 1px solid rgba(248, 113, 113, 0.45);
            border-radius: 6px;
            padding: 5px 8px;
          }
          .tl-modern-hero-map-inspector__photos-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 6px;
          }
          .tl-modern-hero-map-inspector__photo {
            display: flex;
            flex-direction: column;
            border: 1px solid rgba(148, 163, 184, 0.22);
            border-radius: 6px;
            overflow: hidden;
            text-decoration: none;
            color: #e2e8f0;
            background: rgba(15, 23, 42, 0.6);
            transition: border-color 120ms ease, transform 120ms ease;
          }
          .tl-modern-hero-map-inspector__photo:hover {
            border-color: rgba(148, 163, 184, 0.55);
          }
          .tl-modern-hero-map-inspector__photo-thumb {
            display: block;
            width: 100%;
            height: 64px;
            background-color: #0f172a;
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
          }
          .tl-modern-hero-map-inspector__photo-name {
            font-size: 10px;
            font-weight: 600;
            color: #e2e8f0;
            padding: 4px 6px;
            line-height: 1.3;
            word-break: break-all;
            overflow: hidden;
            text-overflow: ellipsis;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
          }
          .tl-modern-hero-map-inspector__upload {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            padding: 6px 10px;
            border-radius: 6px;
            border: 1px solid rgba(148, 163, 184, 0.4);
            background: rgba(30, 41, 59, 0.85);
            color: #f1f5f9;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.02em;
            cursor: pointer;
            transition: background 120ms ease, opacity 120ms ease;
          }
          .tl-modern-hero-map-inspector__upload:hover {
            background: rgba(30, 41, 59, 0.95);
          }
          .tl-modern-hero-map-inspector__upload input[type="file"] {
            display: none;
          }
          .tl-modern-hero-map-inspector__upload--disabled {
            cursor: not-allowed;
            opacity: 0.55;
          }
          .leaflet-marker-icon.tl-modern-hero-map-drag-pin,
          .tl-modern-hero-map-drag-pin {
            position: absolute;
            display: block;
            width: 44px !important;
            height: 44px !important;
            cursor: grab;
            background: transparent;
            border: none;
          }
          .leaflet-marker-icon.tl-modern-hero-map-drag-pin:active,
          .tl-modern-hero-map-drag-pin:active,
          .leaflet-marker-draggable.tl-modern-hero-map-drag-pin:active {
            cursor: grabbing;
          }
          .tl-modern-hero-map-drag-pin__halo {
            position: absolute;
            inset: -10px;
            border-radius: 50%;
            background: rgba(56, 189, 248, 0.18);
            border: 1px solid rgba(56, 189, 248, 0.35);
            pointer-events: none;
          }
          .tl-modern-hero-map-drag-pin__pulse {
            position: absolute;
            inset: -2px;
            border-radius: 50%;
            border: 2px solid rgba(56, 189, 248, 0.65);
            pointer-events: none;
            animation: tl-modern-hero-map-drag-pulse 1.6s ease-out infinite;
          }
          @keyframes tl-modern-hero-map-drag-pulse {
            0%   { transform: scale(0.85); opacity: 0.85; }
            70%  { transform: scale(1.25); opacity: 0;    }
            100% { transform: scale(1.25); opacity: 0;    }
          }
          .tl-modern-hero-map-drag-pin__core {
            position: absolute;
            inset: 6px;
            border-radius: 50%;
            background: radial-gradient(circle at 35% 30%, #7dd3fc 0%, #38bdf8 55%, #0284c7 100%);
            border: 3px solid #0c4a6e;
            box-shadow:
              0 2px 8px rgba(0, 0, 0, 0.55),
              inset 0 1px 0 rgba(255, 255, 255, 0.4);
            display: flex;
            align-items: center;
            justify-content: center;
            pointer-events: auto;
          }
          .tl-modern-hero-map-drag-pin__crosshair {
            display: block;
            width: 14px;
            height: 14px;
            background:
              linear-gradient(#ffffff, #ffffff) center / 2px 100% no-repeat,
              linear-gradient(#ffffff, #ffffff) center / 100% 2px no-repeat;
            opacity: 0.95;
            pointer-events: none;
          }
          .tl-modern-hero-map-inspector__summary {
            font-size: 10px;
            font-weight: 600;
            color: #94a3b8;
            border-top: 1px dashed rgba(148, 163, 184, 0.18);
            padding-top: 6px;
            line-height: 1.4;
            word-break: break-word;
          }
        `}</style>
        <div
          ref={containerRef}
          className="tl-modern-hero-map"
          data-show-labels={mapZoom >= STATION_LABEL_MIN_ZOOM ? "true" : "false"}
          style={{ position: "absolute", inset: 0 }}
        />
        <div className="tl-modern-hero-map-controls" role="toolbar" aria-label="Map controls">
          <button
            type="button"
            onClick={() => setShowStations((v) => !v)}
            data-active={showStations ? "true" : "false"}
            disabled={stationPoints.length === 0}
            title="Toggle station markers"
          >
            {showStations ? "Hide Stations" : "Show Stations"}
          </button>
        </div>

        {/* Phase 2F — Folder filter panel. Only when KMZ context ON and payload loaded. */}
        {layerKmzContext && kmzRenderPayload && (() => {
          const _allFeats = [...(kmzRenderPayload.points??[]), ...(kmzRenderPayload.lines??[]), ...(kmzRenderPayload.polygons??[])];
          const _folderMap = new Map<string,{short:string;full:string;count:number}>();
          for (const f of _allFeats) {
            const fp = Array.isArray(f.folder_path) ? f.folder_path : [];
            const key = fp.join(" / ");
            if (!key) continue;
            const ex = _folderMap.get(key);
            if (ex) { ex.count++; }
            else { _folderMap.set(key,{short:fp[fp.length-1]??key,full:key,count:1}); }
          }
          if (_folderMap.size === 0) return null;
          const _rows = Array.from(_folderMap.entries()).sort((a,b)=>a[0].localeCompare(b[0]));
          const _hasDrops = _rows.some(([k])=>k.includes("House Drop"));
          return (
            <div style={{ position:"absolute", top:46, right:10, zIndex:600, background:"rgba(2,8,23,0.9)", border:"1px solid rgba(251,191,36,0.28)", borderRadius:8, padding:"6px 10px", fontSize:10, color:"#e2e8f0", fontFamily:"ui-sans-serif,system-ui,sans-serif", maxHeight:180, overflowY:"auto", minWidth:200, pointerEvents:"all" }}>
              <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:4 }}>
                <span style={{ fontWeight:700, fontSize:10, color:"rgba(251,191,36,0.85)", letterSpacing:"0.04em", textTransform:"uppercase" }}>KMZ Layers</span>
                <div style={{ display:"flex", gap:5 }}>
                  {_hasDrops && (
                    <button type="button" style={{ background:"none", border:"1px solid rgba(148,163,184,0.28)", borderRadius:4, cursor:"pointer", color:"rgba(148,163,184,0.72)", fontSize:9, padding:"1px 5px" }}
                      onClick={()=>setKmzHiddenFolders(prev=>{ const n=new Set(prev); for(const[k] of _rows) if(k.includes("House Drop")) n.add(k); return n; })}>
                      Hide drops
                    </button>
                  )}
                  <button type="button" style={{ background:"none", border:"1px solid rgba(148,163,184,0.28)", borderRadius:4, cursor:"pointer", color:"rgba(148,163,184,0.72)", fontSize:9, padding:"1px 5px" }}
                    onClick={()=>setKmzHiddenFolders(new Set())}>
                    Show all
                  </button>
                </div>
              </div>
              {_rows.map(([key,meta])=>{
                const _vis = !kmzHiddenFolders.has(key);
                return (
                  <label key={key} title={meta.full} style={{ display:"flex", alignItems:"center", gap:5, cursor:"pointer", userSelect:"none", padding:"1px 0", color:_vis?"#cbd5e1":"rgba(148,163,184,0.38)" }}>
                    <input type="checkbox" checked={_vis} style={{ accentColor:"rgba(251,191,36,0.9)", cursor:"pointer" }}
                      onChange={e=>setKmzHiddenFolders(prev=>{ const n=new Set(prev); if(e.target.checked) n.delete(key); else n.add(key); return n; })} />
                    <span style={{ flex:1, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{meta.short}</span>
                    <span style={{ color:"rgba(148,163,184,0.45)", fontSize:9, flexShrink:0 }}>{meta.count}</span>
                  </label>
                );
              })}
            </div>
          );
        })()}

        {/* Phase 2K — KMZ engineering inspection popup */}
        {selectedKmzCtxFeature && (() => {
          const f = selectedKmzCtxFeature;

          // Engineering attribute extraction (Phase 2K Part A+B)
          const _engAttrs = sortEngineeringAttributes(
            extractEngineeringAttributes(f.description_raw ?? "")
          );

          // Shared micro-components for compact two-column rows
          const _lbl = (label: string) => (
            <span style={{ color:"rgba(148,163,184,0.52)", fontSize:10, minWidth:78, flexShrink:0, paddingTop:1, lineHeight:1.4 }}>{label}</span>
          );
          const _val = (v: React.ReactNode, bold = false) => (
            <span style={{ color: bold ? "#f1f5f9" : "#cbd5e1", fontWeight: bold ? 600 : 400, wordBreak:"break-word", flex:1, lineHeight:1.4 }}>{v}</span>
          );
          const _row = (label: string, value: React.ReactNode, bold = false) => (
            <div style={{ display:"flex", gap:8, alignItems:"baseline", minHeight:16 }}>
              {_lbl(label)}{_val(value, bold)}
            </div>
          );
          const _divider = (label?: string) => (
            <div style={{ display:"flex", alignItems:"center", gap:6, margin:"5px 0 3px" }}>
              <div style={{ borderTop:"1px solid rgba(148,163,184,0.12)", flex:1 }} />
              {label && <span style={{ color:"rgba(148,163,184,0.42)", fontSize:9, textTransform:"uppercase", letterSpacing:"0.06em", flexShrink:0 }}>{label}</span>}
              {label && <div style={{ borderTop:"1px solid rgba(148,163,184,0.12)", flex:1 }} />}
            </div>
          );

          // Subtype label for header (Part E)
          const _subtypeLabel = f.subtype ? KMZ_SUBTYPE_LABELS[f.subtype] : null;
          const _headerSub = _subtypeLabel
            ? _subtypeLabel
            : `${f.feature_type}${f.classification ? ` · ${f.classification}` : ""}`;

          return (
            <div style={{ position:"absolute", top: layerKmzContext&&kmzRenderPayload ? 250 : 56, right:10, zIndex:700, width:316, maxWidth:"calc(100% - 20px)", background:"rgba(3,9,25,0.96)", border:"1px solid rgba(148,163,184,0.20)", borderRadius:10, boxShadow:"0 6px 32px rgba(0,0,0,0.82)", fontFamily:"ui-sans-serif,system-ui,sans-serif", fontSize:11, color:"#e2e8f0", pointerEvents:"all", userSelect:"text", overflow:"hidden" }}>

              {/* Header — KMZ Feature + subtype (Part E) */}
              <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", padding:"6px 12px 5px", borderBottom:"1px solid rgba(148,163,184,0.13)", background:"rgba(15,23,42,0.60)" }}>
                <div style={{ display:"flex", flexDirection:"column", gap:1 }}>
                  <span style={{ fontWeight:700, fontSize:10, color:"rgba(251,191,36,0.88)", letterSpacing:"0.05em", textTransform:"uppercase", lineHeight:1.2 }}>KMZ Feature</span>
                  <span style={{ fontSize:10, color:"rgba(148,163,184,0.68)", lineHeight:1.3, fontStyle: _subtypeLabel ? "normal" : "italic" }}>
                    {_headerSub}
                  </span>
                </div>
                <button type="button" onClick={()=>setSelectedKmzCtxFeature(null)} style={{ background:"none", border:"none", cursor:"pointer", color:"rgba(148,163,184,0.55)", fontSize:16, lineHeight:1, padding:"2px 4px", borderRadius:4 }} title="Close" aria-label="Close KMZ feature info">×</button>
              </div>

              {/* Scrollable body */}
              <div style={{ padding:"7px 12px 9px", display:"flex", flexDirection:"column", gap:3, maxHeight:540, overflowY:"auto" }}>

                {/* 1. Core metadata */}
                {f.name && _row("Name", f.name, true)}
                {Array.isArray(f.folder_path) && f.folder_path.length > 0 && _row("Folder", f.folder_path.join(" / "))}
                {f.description && _row("Notes", f.description.length > 160 ? f.description.slice(0,160)+"…" : f.description)}
                {f.chainage_ft != null && _row("Chainage", `${f.chainage_ft} ft`)}
                {(f.sequence_number || f.sequence_kind) && _row("Sequence", [f.sequence_number, f.sequence_kind].filter(Boolean).join(" · "))}
                {f.lifecycle && _row("Lifecycle", (
                  <span>
                    <span style={{ color:"#fbbf24", fontWeight:600 }}>{f.lifecycle.label}</span>
                    {f.lifecycle.confidence && <span style={{ color:"rgba(148,163,184,0.48)", fontSize:10 }}> ({f.lifecycle.confidence})</span>}
                  </span>
                ))}

                {/* 2. Engineering Attributes — extracted from description_raw (Part C) */}
                {_engAttrs.length > 0 && (
                  <>
                    {_divider("Engineering Attributes")}
                    {_engAttrs.map(({ key, value }) => (
                      <div key={key} style={{ display:"flex", gap:8, alignItems:"baseline" }}>
                        <span style={{ color:"rgba(148,163,184,0.58)", fontSize:10, minWidth:78, flexShrink:0, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{key}</span>
                        <span style={{ color:"#dde5f0", wordBreak:"break-word", fontSize:10, flex:1, fontWeight: ENGINEERING_FIELD_PRIORITY.some(p=>p.toLowerCase()===key.toLowerCase()) ? 500 : 400 }}>{value}</span>
                      </div>
                    ))}
                  </>
                )}

                {/* 3. Extended data (KMZ ExtendedData tags) */}
                {f.extended_data && Object.keys(f.extended_data).length > 0 && (
                  <>
                    {_divider("KMZ ExtendedData")}
                    {Object.entries(f.extended_data).slice(0, 32).map(([k, v]) => (
                      <div key={k} style={{ display:"flex", gap:8, alignItems:"baseline" }}>
                        <span style={{ color:"rgba(148,163,184,0.52)", fontSize:10, minWidth:78, flexShrink:0, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{k}</span>
                        <span style={{ color:"#c8d4e6", wordBreak:"break-word", fontSize:10, flex:1 }}>{String(v)}</span>
                      </div>
                    ))}
                  </>
                )}

                {/* 4. Original Google Earth balloon (Phase 2I — preserved) */}
                {f.description_raw && f.description_raw.trim() && (
                  <>
                    {_divider("Original Balloon")}
                    <details>
                      <summary style={{ cursor:"pointer", color:"rgba(148,163,184,0.58)", fontSize:10, userSelect:"none", outline:"none", paddingBottom:3 }}>Show original balloon</summary>
                      <iframe
                        sandbox=""
                        srcDoc={f.description_raw}
                        style={{ width:"100%", maxHeight:220, height:220, border:"1px solid rgba(148,163,184,0.18)", borderRadius:5, background:"#0b1220", marginTop:4, display:"block", overflow:"hidden" }}
                        title="KMZ original balloon"
                      />
                    </details>
                  </>
                )}

                {/* 5. Icon source hint */}
                {f.icon_href && (
                  <div style={{ marginTop:3, color:"rgba(148,163,184,0.30)", fontSize:9, wordBreak:"break-all" }}>
                    Icon: {f.icon_href}
                  </div>
                )}
              </div>
            </div>
          );
        })()}

        {selectedStationIndex !== null && stationPoints[selectedStationIndex] && (
          <StationInspectorPanel
            station={stationPoints[selectedStationIndex].source}
            identity={selectedStationIdentity}
            summary={selectedStationSummary}
            photos={stationPhotos}
            photosLoading={stationPhotosLoading}
            uploadBusy={stationPhotoBusy}
            errorMessage={stationPhotoError}
            apiBase={API_BASE}
            onUpload={handleStationPhotoUpload}
            onClose={() => setSelectedStationIndex(null)}
          />
        )}
        {selectedFieldStationIdx !== null && fieldStations[selectedFieldStationIdx] && (
          <FieldStationCardPanel
            fieldStation={fieldStations[selectedFieldStationIdx]}
            selectedFieldSession={selectedFieldSession}
            onClose={() => setSelectedFieldStationIdx(null)}
          />
        )}
        {selectedFieldPhotoIdx !== null && fieldPhotos[selectedFieldPhotoIdx] && (
          <FieldPhotoCardPanel
            photo={fieldPhotos[selectedFieldPhotoIdx].source}
            onClose={() => setSelectedFieldPhotoIdx(null)}
          />
        )}
        {selectedPhotoPointIdx !== null && photoPoints[selectedPhotoPointIdx] && (() => {
          const sel = photoPoints[selectedPhotoPointIdx];
          const photoId = String(
            (sel.source as { id?: unknown }).id ?? "",
          );
          return (
            <GlobalPhotoPointCardPanel
              photoPoint={sel}
              photoId={photoId}
              isSaving={photoMoveSaving}
              errorMessage={photoMoveError}
              closeoutLocked={closeoutLocked}
              onResetToOriginal={() => void resetPhotoToOriginal(photoId)}
              onClose={() => setSelectedPhotoPointIdx(null)}
            />
          );
        })()}
        {selectedBridgedPhotoIdx !== null && effectiveBridgedPhotos[selectedBridgedPhotoIdx] && (() => {
          const sel = effectiveBridgedPhotos[selectedBridgedPhotoIdx];
          const hasOverride = Boolean(bridgedPhotoOverrides[sel.id]);
          return (
            <BridgedPhotoCardPanel
              photo={sel}
              isAdjusted={hasOverride}
              closeoutLocked={closeoutLocked}
              onResetToOriginal={() => {
                setBridgedPhotoOverrides((prev) => {
                  if (!(sel.id in prev)) return prev;
                  const next = { ...prev };
                  delete next[sel.id];
                  return next;
                });
              }}
              onClose={() => setSelectedBridgedPhotoIdx(null)}
            />
          );
        })()}
        {(loading || error || !hasRenderableGeometry) && (
          <div
            style={{
              position: "absolute",
              inset: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              pointerEvents: "none",
              padding: 16,
            }}
          >
            <div
              style={{
                background: "rgba(255,255,255,0.9)",
                color: "#334155",
                border: "1px solid #cbd5e1",
                borderRadius: 8,
                padding: "8px 12px",
                fontSize: 12,
                fontWeight: 600,
              }}
            >
              {loading
                ? "Loading map preview..."
                : error
                ? `Preview unavailable: ${error}`
                : "No KMZ or redline geometry available yet."}
            </div>
          </div>
        )}
      </div>
      {(state?.bore_log_summary?.length ?? 0) > 0 && (
        <EvidenceLayersPanel
          entries={state!.bore_log_summary!}
          hiddenLayers={hiddenLayers}
          setHiddenLayers={setHiddenLayers}
        />
      )}
    </section>
  );
}

// ─── Evidence Layers panel ────────────────────────────────────────────────
// Compact list of source files (one row per bore_log_summary entry) with a
// checkbox per row controlling its visibility on the map. Mirrors the legacy
// map's evidence-layer toggle. Toggling never re-fits the map: the parent
// applies visibility imperatively against already-rendered Leaflet layers.
function EvidenceLayersPanel({
  entries,
  hiddenLayers,
  setHiddenLayers,
}: {
  entries: NonNullable<BackendState["bore_log_summary"]>;
  hiddenLayers: Set<string>;
  setHiddenLayers: (next: Set<string>) => void;
}) {
  const ids = entries
    .map((e) => e.evidence_layer_id)
    .filter((id): id is string => Boolean(id));
  const allHidden = ids.length > 0 && ids.every((id) => hiddenLayers.has(id));
  const allVisible = ids.every((id) => !hiddenLayers.has(id));

  const toggleOne = (id: string | undefined) => {
    if (!id) return;
    const next = new Set(hiddenLayers);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setHiddenLayers(next);
  };
  const showAll = () => setHiddenLayers(new Set());
  const hideAll = () => setHiddenLayers(new Set(ids));

  return (
    <div
      style={{
        borderTop: "1px solid var(--tl-border)",
        background: "var(--tl-bg-grid)",
        padding: "10px 14px",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 10,
          marginBottom: 8,
          flexWrap: "wrap",
        }}
      >
        <div>
          <div
            style={{
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              color: "var(--tl-text-muted)",
            }}
          >
            Evidence Layers
          </div>
          <div
            style={{
              fontSize: 11,
              color: "var(--tl-text-faint)",
              marginTop: 2,
            }}
          >
            Hide redlines and stations by source file. Other map layers are
            unaffected.
          </div>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <button
            type="button"
            onClick={showAll}
            disabled={allVisible}
            style={evidenceMiniBtnStyle(allVisible)}
            title="Show all evidence layers"
          >
            All
          </button>
          <button
            type="button"
            onClick={hideAll}
            disabled={allHidden || ids.length === 0}
            style={evidenceMiniBtnStyle(allHidden || ids.length === 0)}
            title="Hide all evidence layers"
          >
            None
          </button>
        </div>
      </div>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 6,
        }}
      >
        {entries.map((entry, idx) => {
          const id = entry.evidence_layer_id;
          const checked = !id || !hiddenLayers.has(id);
          const label = (entry.source_file || "(unnamed)").split(/[\\/]/).pop();
          return (
            <label
              key={id || `evidence-${idx}`}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                padding: "4px 10px",
                borderRadius: 999,
                border: "1px solid var(--tl-border)",
                background: checked ? "var(--tl-surface)" : "transparent",
                fontSize: 11,
                fontWeight: 600,
                color: checked
                  ? "var(--tl-text)"
                  : "var(--tl-text-muted)",
                cursor: id ? "pointer" : "not-allowed",
                opacity: id ? 1 : 0.5,
                maxWidth: "100%",
              }}
              title={entry.source_file || ""}
            >
              <input
                type="checkbox"
                checked={checked}
                onChange={() => toggleOne(id)}
                disabled={!id}
                style={{ margin: 0 }}
              />
              <span
                style={{
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                  maxWidth: 240,
                }}
              >
                {label}
              </span>
              {typeof entry.row_count === "number" && (
                <span
                  style={{
                    fontWeight: 500,
                    color: "var(--tl-text-faint)",
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {entry.row_count}
                </span>
              )}
            </label>
          );
        })}
      </div>
    </div>
  );
}

function evidenceMiniBtnStyle(disabled: boolean): CSSProperties {
  return {
    fontSize: 11,
    fontWeight: 600,
    padding: "3px 10px",
    borderRadius: 999,
    border: "1px solid var(--tl-border)",
    background: "var(--tl-surface)",
    color: "var(--tl-text)",
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.45 : 1,
  };
}

// ─── Station inspector panel ───────────────────────────────────────────────
// Compact right-side overlay shown when a normal station marker is clicked.
// Read-only view; mirrors the field set RedlineMap surfaces for normal
// stations. Empty values render as a muted em-dash.

function fmtNumber(value: unknown, digits?: number): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return "";
  return digits != null ? n.toFixed(digits) : String(n);
}

function fmtString(value: unknown): string {
  if (typeof value !== "string") return "";
  const trimmed = value.trim();
  return trimmed;
}

// ─── Authenticated photo card ─────────────────────────────────────────────────
// Station photo file routes require Authorization — browser-native image/href
// requests cannot supply it. Fetches via apiFetch and renders a blob: URL.
function StationPhotoCard({ photo }: { photo: StationPhoto }) {
  const [blobSrc, setBlobSrc] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;
    apiFetch(photo.relative_url)
      .then((r) => (r.ok ? r.blob() : null))
      .then((b) => {
        if (active && b) {
          objectUrl = URL.createObjectURL(b);
          setBlobSrc(objectUrl);
        }
      })
      .catch(() => {});
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [photo.relative_url]);

  function handleOpen() {
    apiFetch(photo.relative_url)
      .then((r) => (r.ok ? r.blob() : null))
      .then((b) => { if (b) window.open(URL.createObjectURL(b)); })
      .catch(() => {});
  }

  return (
    <button
      type="button"
      className="tl-modern-hero-map-inspector__photo"
      title={photo.original_filename}
      onClick={handleOpen}
      style={{ background: "none", border: "none", padding: 0, cursor: "pointer", textAlign: "left", width: "100%", display: "block", font: "inherit" }}
    >
      <span
        className="tl-modern-hero-map-inspector__photo-thumb"
        style={{ backgroundImage: blobSrc ? `url(${blobSrc})` : undefined }}
        aria-label={photo.original_filename}
      />
      <span className="tl-modern-hero-map-inspector__photo-name">
        {photo.original_filename}
      </span>
    </button>
  );
}

function StationInspectorPanel({
  station,
  identity,
  summary,
  photos,
  photosLoading,
  uploadBusy,
  errorMessage,
  apiBase,
  onUpload,
  onClose,
}: {
  station: StationPoint;
  identity: string;
  summary: string;
  photos: StationPhoto[];
  photosLoading: boolean;
  uploadBusy: boolean;
  errorMessage: string | null;
  apiBase: string;
  onUpload: (files: FileList | null) => void;
  onClose: () => void;
}) {
  const dateValue = (() => {
    const raw = fmtString(station.date);
    if (!raw) return "";
    const formatted = formatDisplayDate(raw);
    return formatted && formatted !== "--" ? formatted : raw;
  })();

  const rows: Array<{ label: string; value: string }> = [
    { label: "Station", value: fmtString(station.station) },
    { label: "Business ID", value: fmtString(station.business_id ?? undefined) },
    { label: "Mapped FT", value: fmtNumber(station.mapped_station_ft, 3) },
    {
      label: "Depth FT",
      value: fmtNumber(station.depth_ft ?? undefined, 2),
    },
    {
      label: "BOC FT",
      value: fmtNumber(station.boc_ft ?? undefined, 2),
    },
    { label: "Date", value: dateValue },
    { label: "Crew", value: fmtString(station.crew) },
    { label: "Print", value: fmtString(station.print) },
    { label: "Source", value: fmtString(station.source_file) },
    { label: "Notes", value: fmtString(station.notes) },
    { label: "Lat", value: fmtNumber(station.lat, 6) },
    { label: "Lon", value: fmtNumber(station.lon, 6) },
  ];

  const photoCount = photos.length;
  const uploadDisabled = uploadBusy || !identity;

  return (
    <aside className="tl-modern-hero-map-inspector" aria-label="Station inspector">
      <div className="tl-modern-hero-map-inspector__head">
        <div>
          <div className="tl-modern-hero-map-inspector__title">Station Inspector</div>
          {fmtString(station.station) && (
            <div
              style={{
                fontSize: 13,
                fontWeight: 700,
                color: "#f8fafc",
                marginTop: 2,
                lineHeight: 1.25,
                wordBreak: "break-word",
              }}
            >
              {fmtString(station.station)}
            </div>
          )}
        </div>
        <button
          type="button"
          className="tl-modern-hero-map-inspector__close"
          onClick={onClose}
          aria-label="Close station inspector"
        >
          ×
        </button>
      </div>
      <div className="tl-modern-hero-map-inspector__body">
        {rows.map((row) => (
          <div className="tl-modern-hero-map-inspector__row" key={row.label}>
            <div className="tl-modern-hero-map-inspector__label">{row.label}</div>
            <div
              className={
                row.value
                  ? "tl-modern-hero-map-inspector__value"
                  : "tl-modern-hero-map-inspector__value tl-modern-hero-map-inspector__value--empty"
              }
            >
              {row.value || "—"}
            </div>
          </div>
        ))}

        <div className="tl-modern-hero-map-inspector__photos">
          <div className="tl-modern-hero-map-inspector__photos-head">
            <span>Photos</span>
            <span className="tl-modern-hero-map-inspector__photos-count">
              {photoCount}
            </span>
          </div>
          {photosLoading ? (
            <div className="tl-modern-hero-map-inspector__photos-status">
              Loading photos…
            </div>
          ) : photoCount > 0 ? (
            <div className="tl-modern-hero-map-inspector__photos-grid">
              {photos.map((photo) => (
                <StationPhotoCard key={photo.photo_id} photo={photo} />
              ))}
            </div>
          ) : (
            <div className="tl-modern-hero-map-inspector__photos-empty">
              No photos attached.
            </div>
          )}

          <label
            className={
              uploadDisabled
                ? "tl-modern-hero-map-inspector__upload tl-modern-hero-map-inspector__upload--disabled"
                : "tl-modern-hero-map-inspector__upload"
            }
            title={
              identity
                ? "Attach photos to this station"
                : "No station identity available — cannot upload"
            }
          >
            <input
              type="file"
              accept="image/*"
              multiple
              disabled={uploadDisabled}
              onChange={(e) => {
                onUpload(e.target.files);
                e.currentTarget.value = "";
              }}
            />
            {uploadBusy ? "Uploading…" : "Upload Station Photos"}
          </label>

          {errorMessage && (
            <div className="tl-modern-hero-map-inspector__photos-error">
              {errorMessage}
            </div>
          )}

          {summary && summary !== "--" && (
            <div className="tl-modern-hero-map-inspector__summary" title={identity}>
              {summary}
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}

// ─── Field station card panel ─────────────────────────────────────────────────
// Floating overlay shown when a violet field-submission station marker is
// clicked. Reuses the same inspector CSS classes as StationInspectorPanel but
// with a violet accent on the header to visually distinguish the two panels.
// Shows per-station depth/BOC and session-level crew/date/photo_count.

function FieldStationCardPanel({
  fieldStation,
  selectedFieldSession,
  onClose,
}: {
  fieldStation: { stationFt: number; label: string; source: Station };
  selectedFieldSession: Session | null;
  onClose: () => void;
}) {
  const rows: Array<{ label: string; value: string }> = [
    {
      label: "Station FT",
      value: Number.isFinite(fieldStation.stationFt) ? String(fieldStation.stationFt) : "",
    },
    { label: "Depth FT", value: fmtNumber(fieldStation.source.depth_ft, 2) },
    { label: "BOC FT", value: fmtNumber(fieldStation.source.boc_ft, 2) },
    { label: "Crew", value: fmtString(selectedFieldSession?.crew_name) },
    {
      label: "Date",
      value: selectedFieldSession?.started_at
        ? new Date(selectedFieldSession.started_at).toLocaleString()
        : "",
    },
    {
      label: "Photos",
      value:
        typeof selectedFieldSession?.photo_count === "number"
          ? String(selectedFieldSession.photo_count)
          : "",
    },
    { label: "Session", value: fmtString(fieldStation.source.session_id) },
  ];

  return (
    <aside className="tl-modern-hero-map-inspector" aria-label="Field station card">
      <div className="tl-modern-hero-map-inspector__head">
        <div>
          <div
            className="tl-modern-hero-map-inspector__title"
            style={{ color: "#c4b5fd" }}
          >
            Field Station
          </div>
          {fieldStation.label && (
            <div style={{ fontSize: 13, fontWeight: 700, color: "#ede9fe", marginTop: 2 }}>
              {fieldStation.label}
            </div>
          )}
        </div>
        <button
          type="button"
          className="tl-modern-hero-map-inspector__close"
          onClick={onClose}
          aria-label="Close field station card"
        >
          ×
        </button>
      </div>
      <div className="tl-modern-hero-map-inspector__body">
        {rows.map((row) => (
          <div className="tl-modern-hero-map-inspector__row" key={row.label}>
            <div className="tl-modern-hero-map-inspector__label">{row.label}</div>
            <div
              className={
                row.value
                  ? "tl-modern-hero-map-inspector__value"
                  : "tl-modern-hero-map-inspector__value tl-modern-hero-map-inspector__value--empty"
              }
            >
              {row.value || "—"}
            </div>
          </div>
        ))}
      </div>
    </aside>
  );
}

// ─── Field photo card panel ───────────────────────────────────────────────────
// Floating overlay shown when a cyan field-submission photo marker is clicked.
// Shows metadata fields and a thumbnail when thumbnail_url is available.

function FieldPhotoCardPanel({
  photo,
  onClose,
}: {
  photo: Photo;
  onClose: () => void;
}) {
  const [blobSrc, setBlobSrc] = useState<string | null>(null);
  useEffect(() => {
    if (!photo.thumbnail_url) return;
    let active = true;
    let objectUrl: string | null = null;
    apiFetch(photo.thumbnail_url)
      .then((r) => (r.ok ? r.blob() : null))
      .then((b) => {
        if (active && b) {
          objectUrl = URL.createObjectURL(b);
          setBlobSrc(objectUrl);
        }
      })
      .catch(() => {});
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [photo.thumbnail_url]);

  const rows: Array<{ label: string; value: string }> = [
    { label: "Station", value: fmtString(photo.station_label) },
    { label: "Lat", value: fmtNumber(photo.latitude, 6) },
    { label: "Lon", value: fmtNumber(photo.longitude, 6) },
    {
      label: "Uploaded",
      value: photo.uploaded_at
        ? new Date(photo.uploaded_at).toLocaleString()
        : "",
    },
    { label: "Note", value: fmtString(photo.note) },
    { label: "Session", value: fmtString(photo.session_id) },
  ];

  return (
    <aside className="tl-modern-hero-map-inspector" aria-label="Field photo card">
      <div className="tl-modern-hero-map-inspector__head">
        <div className="tl-modern-hero-map-inspector__title" style={{ color: "#67e8f9" }}>
          Field Photo
        </div>
        <button
          type="button"
          className="tl-modern-hero-map-inspector__close"
          onClick={onClose}
          aria-label="Close field photo card"
        >
          ×
        </button>
      </div>
      <div className="tl-modern-hero-map-inspector__body">
        {blobSrc ? (
          <img
            src={blobSrc}
            alt="Photo thumbnail"
            style={{
              width: "100%",
              borderRadius: 4,
              marginBottom: 8,
              objectFit: "cover",
              maxHeight: 140,
              display: "block",
            }}
          />
        ) : (
          <div
            style={{
              fontSize: 11,
              color: "#64748b",
              padding: "6px 0 8px",
              fontStyle: "italic",
            }}
          >
            No thumbnail available
          </div>
        )}
        {rows.map((row) => (
          <div className="tl-modern-hero-map-inspector__row" key={row.label}>
            <div className="tl-modern-hero-map-inspector__label">{row.label}</div>
            <div
              className={
                row.value
                  ? "tl-modern-hero-map-inspector__value"
                  : "tl-modern-hero-map-inspector__value tl-modern-hero-map-inspector__value--empty"
              }
            >
              {row.value || "—"}
            </div>
          </div>
        ))}
      </div>
    </aside>
  );
}

function BridgedPhotoCardPanel({
  photo,
  isAdjusted,
  closeoutLocked,
  onResetToOriginal,
  onClose,
}: {
  photo: BridgedGpsPhoto;
  isAdjusted: boolean;
  closeoutLocked: boolean;
  onResetToOriginal: () => void;
  onClose: () => void;
}) {
  const origLat = typeof photo.lat === "number" && Number.isFinite(photo.lat) ? photo.lat : null;
  const origLon = typeof photo.lon === "number" && Number.isFinite(photo.lon) ? photo.lon : null;
  const dispLat =
    typeof photo.displayLat === "number" && Number.isFinite(photo.displayLat)
      ? photo.displayLat
      : origLat;
  const dispLon =
    typeof photo.displayLon === "number" && Number.isFinite(photo.displayLon)
      ? photo.displayLon
      : origLon;
  const originalGps =
    origLat !== null && origLon !== null
      ? `${origLat.toFixed(6)}, ${origLon.toFixed(6)}`
      : "";
  const displayGps =
    dispLat !== null && dispLon !== null
      ? `${dispLat.toFixed(6)}, ${dispLon.toFixed(6)}`
      : "";
  const rows: Array<{ label: string; value: string }> = [
    { label: "Source Type", value: "client_geotagged_temp" },
    { label: "Filename", value: photo.filename },
    { label: "Displayed Position", value: displayGps },
    { label: "Original Geotag", value: originalGps },
  ];

  return (
    <aside className="tl-modern-hero-map-inspector" aria-label="Geotagged photo card">
      <div className="tl-modern-hero-map-inspector__head">
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div className="tl-modern-hero-map-inspector__title" style={{ color: "#67e8f9" }}>
            Geotagged Photo
          </div>
          {isAdjusted ? (
            <span
              style={{
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: 0.2,
                color: "#cffafe",
                border: "1px solid rgba(103, 232, 249, 0.45)",
                background: "rgba(8, 145, 178, 0.22)",
                borderRadius: 999,
                padding: "1px 7px",
                textTransform: "uppercase",
              }}
            >
              Adjusted
            </span>
          ) : null}
        </div>
        <button
          type="button"
          className="tl-modern-hero-map-inspector__close"
          onClick={onClose}
          aria-label="Close geotagged photo card"
        >
          ×
        </button>
      </div>
      <div className="tl-modern-hero-map-inspector__body">
        {photo.previewUrl ? (
          <img
            src={photo.previewUrl}
            alt="Photo preview"
            style={{
              width: "100%",
              borderRadius: 4,
              marginBottom: 8,
              objectFit: "cover",
              maxHeight: 140,
              display: "block",
            }}
          />
        ) : (
          <div
            style={{
              fontSize: 11,
              color: "#64748b",
              padding: "6px 0 8px",
              fontStyle: "italic",
            }}
          >
            No preview available
          </div>
        )}
        {rows.map((row) => (
          <div className="tl-modern-hero-map-inspector__row" key={row.label}>
            <div className="tl-modern-hero-map-inspector__label">{row.label}</div>
            <div
              className={
                row.value
                  ? "tl-modern-hero-map-inspector__value"
                  : "tl-modern-hero-map-inspector__value tl-modern-hero-map-inspector__value--empty"
              }
            >
              {row.value || "—"}
            </div>
          </div>
        ))}

        <div className="tl-modern-hero-map-inspector__photos">
          <div className="tl-modern-hero-map-inspector__photos-head">
            <span>Displayed Position</span>
            <span className="tl-modern-hero-map-inspector__photos-count">
              {isAdjusted ? "Office-corrected" : "= Original"}
            </span>
          </div>
          {closeoutLocked ? (
            <div className="tl-modern-hero-map-inspector__photos-status">
              Closeout is locked — placement is read-only.
            </div>
          ) : (
            <div className="tl-modern-hero-map-inspector__photos-status">
              Click and drag the photo marker on the map to move it. Original
              Geotag stays preserved as evidence. (In-session only — refresh
              clears these placements.)
            </div>
          )}
          {!closeoutLocked && isAdjusted ? (
            <div
              style={{
                display: "flex",
                gap: 6,
                flexWrap: "wrap",
                alignItems: "center",
              }}
            >
              <button
                type="button"
                onClick={onResetToOriginal}
                className="tl-modern-hero-map-inspector__upload"
                style={{
                  background: "rgba(30, 41, 59, 0.85)",
                  border: "1px solid rgba(248, 113, 113, 0.45)",
                }}
                title="Discard displayed position and revert to immutable Original Geotag"
              >
                Reset to Original Geotag
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </aside>
  );
}

function GlobalPhotoPointCardPanel({
  photoPoint,
  photoId,
  isSaving,
  errorMessage,
  closeoutLocked,
  onResetToOriginal,
  onClose,
}: {
  photoPoint: {
    lat: number;
    lon: number;
    displayLat: number;
    displayLon: number;
    label: string;
    source: Record<string, unknown>;
  };
  photoId: string;
  isSaving: boolean;
  errorMessage: string | null;
  closeoutLocked: boolean;
  onResetToOriginal: () => void;
  onClose: () => void;
}) {
  const src = photoPoint.source;
  const sourceType =
    (typeof src.source_type === "string" && src.source_type.trim()) || "station_photo";
  const station =
    (typeof src.station_label === "string" && src.station_label.trim()) ||
    (typeof src.station === "string" && src.station.trim()) ||
    "";
  const filename =
    (typeof src.original_filename === "string" && src.original_filename.trim()) ||
    (typeof src.filename === "string" && src.filename.trim()) ||
    (typeof src.name === "string" && src.name.trim()) ||
    photoPoint.label;
  const uploaded =
    typeof src.uploaded_at === "string" && src.uploaded_at.trim()
      ? new Date(src.uploaded_at).toLocaleString()
      : "";
  const note = typeof src.note === "string" ? src.note.trim() : "";
  const session = typeof src.session_id === "string" ? src.session_id.trim() : "";
  const originalLatRaw = src.original_lat;
  const originalLonRaw = src.original_lon;
  const originalLat = Number(originalLatRaw);
  const originalLon = Number(originalLonRaw);
  const hasOriginal = Number.isFinite(originalLat) && Number.isFinite(originalLon);
  const isAdjusted = Boolean(src.is_adjusted);
  const displayGps = `${photoPoint.displayLat.toFixed(6)}, ${photoPoint.displayLon.toFixed(6)}`;
  const originalGps = hasOriginal
    ? `${originalLat.toFixed(6)}, ${originalLon.toFixed(6)}`
    : `${photoPoint.lat.toFixed(6)}, ${photoPoint.lon.toFixed(6)}`;
  const thumbnailUrl =
    (typeof src.thumbnail_url === "string" && src.thumbnail_url.trim()) ||
    (typeof src.relative_url === "string" && src.relative_url.trim()) ||
    "";

  const rows: Array<{ label: string; value: string }> = [
    { label: "Source Type", value: sourceType },
    { label: "Displayed Position", value: displayGps },
    { label: "Original Geotag", value: originalGps },
    { label: "Station", value: station },
    { label: "Filename", value: filename },
    { label: "Uploaded", value: uploaded },
    { label: "Note", value: note },
    { label: "Session", value: session },
  ];

  const movePanel = (
    <div className="tl-modern-hero-map-inspector__photos">
      <div className="tl-modern-hero-map-inspector__photos-head">
        <span>Displayed Position</span>
        <span className="tl-modern-hero-map-inspector__photos-count">
          {isAdjusted ? "Office-corrected" : "= Original"}
        </span>
      </div>

      {closeoutLocked ? (
        <div className="tl-modern-hero-map-inspector__photos-status">
          Closeout is locked — placement is read-only.
        </div>
      ) : (
        <div className="tl-modern-hero-map-inspector__photos-status">
          {isSaving
            ? "Saving displayed position…"
            : "Click and drag the photo marker on the map to move it. Original Geotag stays preserved as evidence."}
        </div>
      )}

      {!closeoutLocked && photoId && isAdjusted ? (
        <div
          style={{
            display: "flex",
            gap: 6,
            flexWrap: "wrap",
            alignItems: "center",
          }}
        >
          <button
            type="button"
            onClick={onResetToOriginal}
            disabled={isSaving}
            className="tl-modern-hero-map-inspector__upload"
            style={{
              background: "rgba(30, 41, 59, 0.85)",
              border: "1px solid rgba(248, 113, 113, 0.45)",
            }}
            title="Discard displayed position and revert to immutable Original Geotag"
          >
            Reset to Original Geotag
          </button>
        </div>
      ) : null}

      {errorMessage ? (
        <div className="tl-modern-hero-map-inspector__photos-error">
          {errorMessage}
        </div>
      ) : null}
    </div>
  );

  return (
    <aside className="tl-modern-hero-map-inspector" aria-label="Photo evidence card">
      <div className="tl-modern-hero-map-inspector__head">
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div className="tl-modern-hero-map-inspector__title" style={{ color: "#67e8f9" }}>
            Photo Evidence
          </div>
          {isAdjusted ? (
            <span
              style={{
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: 0.2,
                color: "#cffafe",
                border: "1px solid rgba(103, 232, 249, 0.45)",
                background: "rgba(8, 145, 178, 0.22)",
                borderRadius: 999,
                padding: "1px 7px",
                textTransform: "uppercase",
              }}
            >
              Adjusted
            </span>
          ) : null}
        </div>
        <button
          type="button"
          className="tl-modern-hero-map-inspector__close"
          onClick={onClose}
          aria-label="Close photo evidence card"
        >
          ×
        </button>
      </div>
      <div className="tl-modern-hero-map-inspector__body">
        {thumbnailUrl ? (
          <img
            src={thumbnailUrl}
            alt="Photo thumbnail"
            style={{
              width: "100%",
              borderRadius: 4,
              marginBottom: 8,
              objectFit: "cover",
              maxHeight: 140,
              display: "block",
            }}
          />
        ) : (
          <div
            style={{
              fontSize: 11,
              color: "#64748b",
              padding: "6px 0 8px",
              fontStyle: "italic",
            }}
          >
            No thumbnail available
          </div>
        )}
        {rows.map((row) => (
          <div className="tl-modern-hero-map-inspector__row" key={row.label}>
            <div className="tl-modern-hero-map-inspector__label">{row.label}</div>
            <div
              className={
                row.value
                  ? "tl-modern-hero-map-inspector__value"
                  : "tl-modern-hero-map-inspector__value tl-modern-hero-map-inspector__value--empty"
              }
            >
              {row.value || "—"}
            </div>
          </div>
        ))}
        {movePanel}
      </div>
    </aside>
  );
}
