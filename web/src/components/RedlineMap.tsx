"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  CandidateRanking,
  VerificationInfo,
  StationPoint,
  RedlineSegment,
  GroupMatch,
  KmzLineFeature,
  KmzPolygonFeature,
  BackendState,
  StationPhoto,
  ExceptionCost,
  NoteTone,
  Bounds,
  ScreenPoint,
  Viewport,
} from "@/lib/types/backend";
import {
  PROJECTION_BASE_WIDTH,
  MAP_HEIGHT,
  MIN_ZOOM,
  MAX_ZOOM,
  FIT_PADDING,
  WHEEL_IN,
  WHEEL_OUT,
  BUTTON_IN,
  BUTTON_OUT,
  LOW_ZOOM_LABEL_THRESHOLD,
  MID_ZOOM_LABEL_THRESHOLD,
} from "@/lib/map/constants";
import MobileWalkContainer from "@/components/MobileWalkContainer";
import { clamp, formatNumber, cleanDisplayText, formatDisplayDate } from "@/lib/format/text";
import { toMoney } from "@/lib/format/money";
import { extractGps } from "@/lib/photos/exif";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/+$/, "") ||
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, "") ||
  "http://127.0.0.1:8000";

function stationIdentityPart(value: unknown, digits?: number): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "";
    return digits !== undefined ? value.toFixed(digits) : String(value);
  }
  const raw = String(value).trim();
  return raw;
}

function buildStationIdentity(routeName: string | null | undefined, point: StationPoint | null | undefined): string {
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

function buildStationSummary(routeName: string | null | undefined, point: StationPoint | null | undefined): string {
  if (!point) return "--";
  const station = cleanDisplayText(point.station);
  const source = cleanDisplayText(point.source_file);
  const route = cleanDisplayText(routeName);
  return `${station} • ${route} • ${source}`;
}

function cleanCoords(coords: number[][] | undefined | null): number[][] {
  if (!Array.isArray(coords)) return [];
  return coords.filter(
    (pt): pt is number[] =>
      Array.isArray(pt) &&
      pt.length >= 2 &&
      typeof pt[0] === "number" &&
      typeof pt[1] === "number" &&
      Number.isFinite(pt[0]) &&
      Number.isFinite(pt[1])
  );
}

function getBoundsFromCoords(coords: number[][]): Bounds | null {
  if (!coords.length) return null;
  return {
    minLat: Math.min(...coords.map((p) => p[0])),
    maxLat: Math.max(...coords.map((p) => p[0])),
    minLon: Math.min(...coords.map((p) => p[1])),
    maxLon: Math.max(...coords.map((p) => p[1])),
  };
}

function expandBounds(bounds: Bounds, factor = 0.04): Bounds {
  const latPad = Math.max((bounds.maxLat - bounds.minLat) * factor, 0.00001);
  const lonPad = Math.max((bounds.maxLon - bounds.minLon) * factor, 0.00001);
  return {
    minLat: bounds.minLat - latPad,
    maxLat: bounds.maxLat + latPad,
    minLon: bounds.minLon - lonPad,
    maxLon: bounds.maxLon + lonPad,
  };
}

type ProjectionMetrics = {
  worldWidth: number;
  worldHeight: number;
  contentWidth: number;
  contentHeight: number;
  offsetX: number;
  offsetY: number;
};

function getProjectionMetrics(bounds: Bounds, widthPx: number, heightPx: number): ProjectionMetrics {
  const safeWidth = Math.max(1, widthPx);
  const safeHeight = Math.max(1, heightPx);
  const latSpan = Math.max(bounds.maxLat - bounds.minLat, 0.000001);
  const midLatRad = ((bounds.minLat + bounds.maxLat) / 2) * (Math.PI / 180);
  const lonScale = Math.max(Math.cos(midLatRad), 0.000001);
  const lonSpanAdjusted = Math.max((bounds.maxLon - bounds.minLon) * lonScale, 0.000001);

  const dataAspect = lonSpanAdjusted / latSpan;
  const viewportAspect = safeWidth / safeHeight;

  const worldWidth = PROJECTION_BASE_WIDTH;
  const worldHeight = PROJECTION_BASE_WIDTH / viewportAspect;

  let contentWidth = worldWidth;
  let contentHeight = contentWidth / dataAspect;

  if (contentHeight > worldHeight) {
    contentHeight = worldHeight;
    contentWidth = contentHeight * dataAspect;
  }

  const offsetX = (worldWidth - contentWidth) / 2;
  const offsetY = (worldHeight - contentHeight) / 2;

  return {
    worldWidth,
    worldHeight,
    contentWidth,
    contentHeight,
    offsetX,
    offsetY,
  };
}

function projectWorldPoint(
  lat: number,
  lon: number,
  bounds: Bounds,
  metrics: ProjectionMetrics
): ScreenPoint {
  const latSpan = Math.max(bounds.maxLat - bounds.minLat, 0.000001);
  const lonSpan = Math.max(bounds.maxLon - bounds.minLon, 0.000001);
  return {
    x: metrics.offsetX + ((lon - bounds.minLon) / lonSpan) * metrics.contentWidth,
    y: metrics.offsetY + (1 - (lat - bounds.minLat) / latSpan) * metrics.contentHeight,
  };
}

function buildWorldPath(
  coords: number[][],
  bounds: Bounds | null,
  metrics: ProjectionMetrics | null
): string {
  if (!bounds || !metrics || coords.length < 2) return "";
  return coords
    .map((pt, idx) => {
      const p = projectWorldPoint(pt[0], pt[1], bounds, metrics);
      return `${idx === 0 ? "M" : "L"} ${p.x.toFixed(2)} ${p.y.toFixed(2)}`;
    })
    .join(" ");
}

function viewBoxToString(metrics: ProjectionMetrics | null, viewport: Viewport): string {
  const worldWidth = (metrics?.worldWidth || PROJECTION_BASE_WIDTH) / viewport.zoom;
  const worldHeight = (metrics?.worldHeight || PROJECTION_BASE_WIDTH) / viewport.zoom;
  const x = -viewport.panX / viewport.zoom;
  const y = -viewport.panY / viewport.zoom;
  return `${x} ${y} ${worldWidth} ${worldHeight}`;
}

function screenToWorld(
  screenX: number,
  screenY: number,
  viewport: Viewport
): ScreenPoint {
  return {
    x: (screenX - viewport.panX) / viewport.zoom,
    y: (screenY - viewport.panY) / viewport.zoom,
  };
}


function kmzLineStroke(feature: KmzLineFeature): string {
  return (
    feature.stroke ||
    feature.color ||
    (feature.role === "backbone"
      ? "rgba(140, 195, 230, 0.22)"
      : feature.role === "terminal_tail"
      ? "rgba(160, 190, 215, 0.18)"
      : "rgba(150, 180, 205, 0.16)")
  );
}

function kmzLineWidth(feature: KmzLineFeature): number {
  const raw = feature.stroke_width ?? feature.width;
  if (typeof raw === "number" && Number.isFinite(raw)) {
    return clamp(raw * 0.66, 0.85, 2.4);
  }
  return feature.role === "backbone" ? 1.5 : 1.05;
}

function kmzPolygonFill(feature: KmzPolygonFeature): string {
  return feature.fill_color || feature.fill || "rgba(95, 128, 110, 0.05)";
}

function kmzPolygonStroke(feature: KmzPolygonFeature): string {
  return feature.stroke_color || feature.stroke || "rgba(164, 174, 181, 0.22)";
}

function kmzPolygonOpacity(feature: KmzPolygonFeature): number {
  const raw = feature.fill_opacity;
  if (typeof raw === "number" && Number.isFinite(raw)) {
    return clamp(raw * 0.38, 0.015, 0.12);
  }
  return 0.038;
}

function SummaryCard({ title, value, subtitle }: { title: string; value: string; subtitle: string }) {
  return (
    <div
      style={{
        background: "linear-gradient(180deg, #ffffff 0%, #f8fbff 100%)",
        border: "1px solid #dbe4ee",
        borderRadius: 20,
        padding: 18,
        boxShadow: "0 10px 24px rgba(15, 23, 42, 0.04)",
        minWidth: 0,
        overflow: "hidden",
      }}
    >
      <div style={{ fontSize: 12, color: "#5b6b7d", fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.4, overflowWrap: "anywhere", wordBreak: "break-word" }}>{title}</div>
      <div style={{ marginTop: 10, fontSize: 28, fontWeight: 800, color: "#0f172a", lineHeight: 1.1, overflowWrap: "anywhere", wordBreak: "break-word", whiteSpace: "normal" }}>{value}</div>
      <div style={{ marginTop: 8, fontSize: 12, color: "#6b7280", overflowWrap: "anywhere", wordBreak: "break-word", whiteSpace: "normal" }}>{subtitle}</div>
    </div>
  );
}

function Section({ title, subtitle, children, actions }: { title: string; subtitle?: string; children: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <div
      style={{
        background: "#fff",
        border: "1px solid #dbe4ee",
        borderRadius: 20,
        overflow: "hidden",
        boxShadow: "0 10px 24px rgba(15, 23, 42, 0.04)",
      }}
    >
      <div style={{ padding: 18, borderBottom: "1px solid #e8eef5", display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 800, color: "#0f172a" }}>{title}</div>
          {subtitle ? <div style={{ marginTop: 6, fontSize: 13, color: "#64748b", maxWidth: 900 }}>{subtitle}</div> : null}
        </div>
        {actions ? <div>{actions}</div> : null}
      </div>
      <div style={{ padding: 18 }}>{children}</div>
    </div>
  );
}

function StatusBanner({ tone, text }: { tone: NoteTone; text: string }) {
  const styles: Record<NoteTone, { bg: string; border: string; color: string }> = {
    neutral: { bg: "#eef2f7", border: "#dbe4ee", color: "#334155" },
    success: { bg: "#ecfdf3", border: "#b7ebc8", color: "#166534" },
    warning: { bg: "#fffbeb", border: "#fcd34d", color: "#92400e" },
    error: { bg: "#fef2f2", border: "#fecaca", color: "#991b1b" },
  };
  const s = styles[tone];
  return (
    <div style={{ border: `1px solid ${s.border}`, background: s.bg, color: s.color, borderRadius: 16, padding: 14, fontSize: 14, whiteSpace: "pre-wrap", boxShadow: "0 6px 18px rgba(15, 23, 42, 0.03)" }}>
      {text}
    </div>
  );
}

function SmallRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "160px 1fr", gap: 10, fontSize: 13, padding: "6px 0" }}>
      <div style={{ color: "#64748b", fontWeight: 700 }}>{label}</div>
      <div style={{ color: "#0f172a", wordBreak: "break-word" }}>{value}</div>
    </div>
  );
}

function TooltipRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "92px 1fr",
        gap: 10,
        alignItems: "start",
        fontSize: 12,
        lineHeight: 1.35,
      }}
    >
      <div style={{ color: "#64748b", fontWeight: 800, letterSpacing: 0.15 }}>{label}</div>
      <div style={{ color: "#0f172a", wordBreak: "break-word" }}>{value}</div>
    </div>
  );
}

function buttonStyle(background: string, color: string, borderColor: string, disabled: boolean): React.CSSProperties {
  return {
    background,
    color,
    border: "2px solid #000000",
    borderRadius: 14,
    padding: "12px 14px",
    fontWeight: 800,
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.65 : 1,
    fontSize: 14,
  };
}

const miniMapButton: React.CSSProperties = {
  height: 36,
  borderRadius: 10,
  padding: "0 12px",
  border: "2px solid #000000",
  background: "rgba(15, 23, 42, 0.92)",
  color: "#f8fafc",
  fontWeight: 800,
  cursor: "pointer",
  boxShadow: "0 6px 16px rgba(0,0,0,0.28)",
};

function uploadCardStyle(disabled: boolean): React.CSSProperties {
  return {
    display: "block",
    border: "2px solid #000000",
    borderRadius: 16,
    padding: 16,
    background: disabled ? "#f3f4f6" : "#ffffff",
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.7 : 1,
  };
}

function ShellCard({ title, description, children }: { title: string; description: string; children?: React.ReactNode }) {
  return (
    <div style={{ border: "1px solid #dbe4ee", borderRadius: 16, background: "#fbfdff", padding: 16, minWidth: 0, overflow: "hidden" }}>
      <div style={{ fontSize: 15, fontWeight: 800, color: "#0f172a", overflowWrap: "anywhere", wordBreak: "break-word" }}>{title}</div>
      <div style={{ marginTop: 6, fontSize: 13, color: "#64748b", lineHeight: 1.55, overflowWrap: "anywhere", wordBreak: "break-word", whiteSpace: "normal" }}>{description}</div>
      {children ? <div style={{ marginTop: 12, minWidth: 0 }}>{children}</div> : null}
    </div>
  );
}

function Pill({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={{ border: "1px solid #dbe4ee", background: "#f8fbfe", borderRadius: 999, padding: "8px 12px", fontSize: 12, color: "#334155" }}>
      <strong>{label}:</strong> {value}
    </div>
  );
}

function deriveDesignProjectName(
  kmzReference: BackendState["kmz_reference"] | undefined,
  latestStructuredFile?: string | null
): string {
  const polygonNames = (kmzReference?.polygon_features || [])
    .map((feature) => cleanDisplayText(feature.name))
    .filter((name) => name !== "--");

  const lineFolders = (kmzReference?.line_features || [])
    .map((feature) => cleanDisplayText(feature.source_folder))
    .filter((name) => name !== "--");

  const preferred = [...polygonNames, ...lineFolders].find(Boolean);
  if (preferred) return preferred;

  const latest = cleanDisplayText(latestStructuredFile);
  if (latest !== "--") return latest;

  return "--";
}

type RedlineMapProps = {
  mode?: "mobileWalk" | "default";
};

// V1 Photo GPS Mapping — client-only photo marker.
// Not persisted: resets on refresh. See "Geotagged photos" panel in Section 3.
// `reason` is set at upload time; the render-time bounds check may still hide
// a "mapped" photo if it falls outside the current KMZ design area.
type GpsPhoto = {
  id: string;
  file: File;
  previewUrl: string; // object URL, revoked on clear/unmount
  filename: string;
  sizeBytes: number;
  contentType: string;
  lat: number | null;
  lon: number | null;
  reason: "mapped" | "no_gps" | "unreadable";
  addedAt: number; // Date.now()
};

function OfficeRedlineMapInner({ mode = "default" }: RedlineMapProps) {
  const [state, setState] = useState<BackendState | null>(null);
  const [busy, setBusy] = useState(false);
  const [statusTone, setStatusTone] = useState<NoteTone>("neutral");
  const [statusText, setStatusText] = useState("Connecting to local beta backend...");
  const [jobLabel, setJobLabel] = useState("");
  const [notes, setNotes] = useState("");
  const [costPerFoot, setCostPerFoot] = useState("5.00");
  const [manualFootage, setManualFootage] = useState("");
  const [exceptions, setExceptions] = useState<ExceptionCost[]>([
    { id: "txdot", label: "TXDOT", amount: "" },
    { id: "railroad", label: "Railroad", amount: "" },
    { id: "restoration", label: "Restoration", amount: "" },
  ]);
  const [extraExceptionLabel, setExtraExceptionLabel] = useState("");
  const [extraExceptionAmount, setExtraExceptionAmount] = useState("");
  const [stationPhotos, setStationPhotos] = useState<StationPhoto[]>([]);
  const [stationPhotosLoading, setStationPhotosLoading] = useState(false);
  const [stationPhotoBusy, setStationPhotoBusy] = useState(false);
  // V1 Photo GPS Mapping — client-only, resets on refresh.
  const [gpsPhotos, setGpsPhotos] = useState<GpsPhoto[]>([]);
  const [gpsPhotoBusy, setGpsPhotoBusy] = useState(false);
  const [selectedGpsPhotoId, setSelectedGpsPhotoId] = useState<string | null>(null);
  const [hoverGpsPhotoId, setHoverGpsPhotoId] = useState<string | null>(null);
  const [viewport, setViewport] = useState<Viewport>({ zoom: 1, panX: 0, panY: 0 });
  const [didInitialFit, setDidInitialFit] = useState(false);
  const [isPanning, setIsPanning] = useState(false);
  const panStartRef = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const [containerSize, setContainerSize] = useState({ width: 1200, height: MAP_HEIGHT });
  const [boxZoom, setBoxZoom] = useState<{ startX: number; startY: number; endX: number; endY: number } | null>(null);
  const [selectedStationIndex, setSelectedStationIndex] = useState<number | null>(null);
  const [hoverStationIndex, setHoverStationIndex] = useState<number | null>(null);
  const [showStations, setShowStations] = useState(false);
  const userHasAdjustedViewportRef = useRef(false);
  const lastAutoFitSignatureRef = useRef<string>("");
  const initialFitRafRef = useRef<number | null>(null);
  const initialFitTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const routeCoords = useMemo(() => cleanCoords(state?.route_coords || []), [state]);
  const redlineSegments = state?.redline_segments || [];
  const stationPoints = state?.station_points || [];
  const activeRouteRedlineSegments = state?.active_route_redline_segments || [];
  const activeRouteStationPoints = state?.active_route_station_points || [];
  const selectedMatch = state?.selected_route_match || null;
  const verification = state?.verification_summary || {};
  const designProjectName = useMemo(
    () => deriveDesignProjectName(state?.kmz_reference, state?.latest_structured_file),
    [state?.kmz_reference, state?.latest_structured_file]
  );

  const activeJob =
    jobLabel.trim() ||
    (designProjectName !== "--" ? designProjectName : "") ||
    state?.route_name ||
    state?.selected_route_name ||
    "--";

  const kmzLineFeatures = useMemo(
    () =>
      (state?.kmz_reference?.line_features || [])
        .map((f) => ({ ...f, coords: cleanCoords(f.coords) }))
        .filter((f) => f.coords.length > 1),
    [state]
  );

  const kmzPolygonFeatures = useMemo(
    () =>
      (state?.kmz_reference?.polygon_features || [])
        .map((f) => ({ ...f, coords: cleanCoords(f.coords) }))
        .filter((f) => f.coords.length > 2),
    [state]
  );

  const designCoords = useMemo(() => {
    const coords: number[][] = [];
    kmzLineFeatures.forEach((feature) => cleanCoords(feature.coords).forEach((pt) => coords.push(pt)));
    kmzPolygonFeatures.forEach((feature) => cleanCoords(feature.coords).forEach((pt) => coords.push(pt)));
    return coords;
  }, [kmzLineFeatures, kmzPolygonFeatures]);

  const allCoords = useMemo(() => {
    const coords: number[][] = [];
    designCoords.forEach((pt) => coords.push(pt));
    redlineSegments.forEach((segment) => cleanCoords(segment.coords).forEach((pt) => coords.push(pt)));
    stationPoints.forEach((point) => {
      if (typeof point.lat === "number" && typeof point.lon === "number") {
        coords.push([point.lat, point.lon]);
      }
    });
    return coords;
  }, [designCoords, redlineSegments, stationPoints]);

  const bounds = useMemo(() => {
    const raw = getBoundsFromCoords(allCoords);
    return raw ? expandBounds(raw, 0.12) : null;
  }, [allCoords]);

  const designBounds = useMemo(() => {
    const raw = getBoundsFromCoords(designCoords);
    return raw ? expandBounds(raw, 0.06) : null;
  }, [designCoords]);

  const stationOnlyBounds = useMemo(() => {
    const coords: number[][] = [];
    stationPoints.forEach((point) => {
      if (typeof point.lat === "number" && typeof point.lon === "number") {
        coords.push([point.lat, point.lon]);
      }
    });
    const raw = getBoundsFromCoords(coords);
    return raw ? expandBounds(raw, 0.12) : null;
  }, [stationPoints]);

  const renderBounds = useMemo(() => designBounds || bounds || stationOnlyBounds || null, [designBounds, bounds, stationOnlyBounds]);

  const projectionMetrics = useMemo(
    () => (renderBounds ? getProjectionMetrics(renderBounds, containerSize.width, containerSize.height) : null),
    [renderBounds, containerSize.width, containerSize.height]
  );

  const initialFitBounds = useMemo(() => renderBounds, [renderBounds]);

  const autoFitSignature = useMemo(() => {
    if (!initialFitBounds) return "";
    return JSON.stringify({
      bounds: initialFitBounds,
      width: containerSize.width,
      height: containerSize.height,
      route: state?.selected_route_name || state?.route_name || "",
      designCoordCount: designCoords.length,
      routeCoordCount: routeCoords.length,
      redlineCount: redlineSegments.length,
      stationCount: stationPoints.length,
    });
  }, [
    initialFitBounds,
    containerSize.width,
    containerSize.height,
    state?.selected_route_name,
    state?.route_name,
    designCoords.length,
    routeCoords.length,
    redlineSegments.length,
    stationPoints.length,
  ]);

  const kmzLinePaths = useMemo(
    () =>
      kmzLineFeatures.map((feature) => ({
        id: feature.feature_id || feature.route_id || `${feature.route_name || "kmz"}-${Math.random()}`,
        path: buildWorldPath(feature.coords || [], renderBounds, projectionMetrics),
      })),
    [kmzLineFeatures, renderBounds]
  );

  const kmzPolygonPaths = useMemo(
    () =>
      kmzPolygonFeatures.map((feature) => ({
        id: feature.feature_id || `${feature.name || "polygon"}-${Math.random()}`,
        path: buildWorldPath([...(feature.coords || []), (feature.coords || [])[0]], renderBounds, projectionMetrics),
      })),
    [kmzPolygonFeatures, renderBounds]
  );

  const redlinePaths = useMemo(
    () =>
      redlineSegments.map((segment) => ({
        id: segment.segment_id || `${segment.start_station || "start"}-${segment.end_station || "end"}`,
        path: buildWorldPath(cleanCoords(segment.coords), renderBounds, projectionMetrics),
      })),
    [redlineSegments, renderBounds]
  );

  const projectedStations = useMemo(() => {
    if (!renderBounds || !projectionMetrics) return [] as Array<{ idx: number; point: StationPoint; world: ScreenPoint }>;
    return stationPoints
      .map((point, idx) => {
        if (typeof point.lat !== "number" || typeof point.lon !== "number") return null;
        return {
          idx,
          point,
          world: projectWorldPoint(point.lat, point.lon, renderBounds, projectionMetrics),
        };
      })
      .filter((item): item is { idx: number; point: StationPoint; world: ScreenPoint } => Boolean(item));
  }, [stationPoints, renderBounds, projectionMetrics]);

  // V1 Photo GPS Mapping — render-time projection.
  // Only photos with valid GPS AND lat/lon falling inside the current
  // renderBounds are projected to SVG world coordinates. Photos outside the
  // bounds are filtered here (they stay in gpsPhotos state with reason="mapped"
  // but don't appear on the map; the UI classifies them as "outside design
  // area" in the Unmapped list by comparing the two arrays).
  // IMPORTANT: photo coords are NOT added to the bounds union (`allCoords`), so
  // a rogue EXIF reading cannot reshape the map fit.
  const projectedPhotos = useMemo(() => {
    if (!renderBounds || !projectionMetrics) {
      return [] as Array<{ photo: GpsPhoto; world: ScreenPoint }>;
    }
    return gpsPhotos
      .map((photo) => {
        if (photo.reason !== "mapped") return null;
        if (typeof photo.lat !== "number" || typeof photo.lon !== "number") return null;
        if (
          photo.lat < renderBounds.minLat ||
          photo.lat > renderBounds.maxLat ||
          photo.lon < renderBounds.minLon ||
          photo.lon > renderBounds.maxLon
        ) {
          return null;
        }
        return {
          photo,
          world: projectWorldPoint(photo.lat, photo.lon, renderBounds, projectionMetrics),
        };
      })
      .filter((item): item is { photo: GpsPhoto; world: ScreenPoint } => Boolean(item));
  }, [gpsPhotos, renderBounds, projectionMetrics]);

  const visibleLabelIndices = useMemo(() => {
    const result = new Set<number>();
    if (!showStations || !projectedStations.length || !projectionMetrics) return result;

    const currentWorldWidth = projectionMetrics.worldWidth / viewport.zoom;
    const worldThreshold =
      viewport.zoom < LOW_ZOOM_LABEL_THRESHOLD
        ? Number.POSITIVE_INFINITY
        : viewport.zoom < MID_ZOOM_LABEL_THRESHOLD
        ? currentWorldWidth * (56 / Math.max(containerSize.width, 1))
        : currentWorldWidth * (28 / Math.max(containerSize.width, 1));

    const acceptedWorld: ScreenPoint[] = [];
    for (const station of projectedStations) {
      const mustShow =
        selectedStationIndex === station.idx ||
        hoverStationIndex === station.idx ||
        station.idx === 0 ||
        station.idx === projectedStations.length - 1;

      if (mustShow) {
        result.add(station.idx);
        acceptedWorld.push(station.world);
        continue;
      }

      if (viewport.zoom < LOW_ZOOM_LABEL_THRESHOLD) {
        continue;
      }

      const tooClose = acceptedWorld.some(
        (existing) => Math.hypot(existing.x - station.world.x, existing.y - station.world.y) < worldThreshold
      );

      if (!tooClose) {
        result.add(station.idx);
        acceptedWorld.push(station.world);
      }
    }

    return result;
  }, [
    showStations,
    projectedStations,
    projectionMetrics,
    viewport.zoom,
    containerSize.width,
    selectedStationIndex,
    hoverStationIndex,
  ]);


  const selectedStation =
    selectedStationIndex !== null ? stationPoints[selectedStationIndex] || null : null;

  const hoverStation =
    hoverStationIndex !== null ? stationPoints[hoverStationIndex] || null : null;

  const activeTooltipIndex = showStations ? hoverStationIndex : null;

  const tooltipStation = useMemo(() => {
    if (activeTooltipIndex === null) return null;
    return stationPoints[activeTooltipIndex] || null;
  }, [activeTooltipIndex, stationPoints]);

  const tooltipStationMode = hoverStationIndex !== null ? "Hover" : "";

  const tooltipWorldGeometry = useMemo(() => {
    if (!projectionMetrics || activeTooltipIndex === null || !showStations) {
      return null;
    }

    const station = projectedStations.find((item) => item.idx === activeTooltipIndex);
    if (!station) return null;

    const currentWorldWidth = projectionMetrics.worldWidth / viewport.zoom;
    const currentWorldHeight = projectionMetrics.worldHeight / viewport.zoom;
    const viewLeft = -viewport.panX / viewport.zoom;
    const viewTop = -viewport.panY / viewport.zoom;
    const viewRight = viewLeft + currentWorldWidth;
    const viewBottom = viewTop + currentWorldHeight;

    const baseScale = clamp(2.4 / Math.max(viewport.zoom, 1), 0.38, 2.4);

    const cardWidth = baseScale * 64;
    const margin = baseScale * 3;
    const offsetX = baseScale * 5.25;
    const cornerRadius = baseScale * 4;
    const calloutInset = baseScale * 1.15;
    const calloutStroke = Math.max(0.7, baseScale * 0.34);

    const headerFontSize = baseScale * 1.9;
    const stationFontSize = baseScale * 4.1;
    const rowLabelFontSize = baseScale * 2.2;
    const rowFontSize = baseScale * 2.15;
    const headerLetterSpacing = baseScale * 0.18;
    const rowGap = baseScale * 3.05;
    const paddingX = baseScale * 4.0;
    const headerY = baseScale * 4.7;
    const stationY = baseScale * 9.6;
    const rowsStartY = baseScale * 14.0;
    const valueX = paddingX + baseScale * 12.8;
    const contentBottomPadding = baseScale * 3.3;
    const rowCount = 10;
    const minCardHeight = rowsStartY + rowGap * (rowCount - 1) + contentBottomPadding;
    const cardHeight = Math.max(baseScale * 48, minCardHeight);

    const labelFontSize = baseScale * 2.05;
    const labelHeight = baseScale * 4.15;
    const labelRadius = baseScale * 1.85;
    const labelPaddingX = baseScale * 2.05;
    const labelDx = baseScale * 2.0;
    const labelDy = baseScale * 4.7;

    const preferRight = station.world.x + offsetX + cardWidth <= viewRight - margin;
    const anchorX = preferRight
      ? station.world.x + offsetX
      : Math.max(viewLeft + margin, station.world.x - cardWidth - offsetX);

    const anchorY = Math.min(
      Math.max(viewTop + margin, station.world.y - cardHeight * 0.48),
      viewBottom - cardHeight - margin
    );

    return {
      stationX: station.world.x,
      stationY: station.world.y,
      cardX: anchorX,
      cardY: anchorY,
      cardWidth,
      cardHeight,
      calloutMidY: anchorY + baseScale * 7.2,
      placeRight: preferRight,
      cornerRadius,
      calloutInset,
      calloutStroke,
      paddingX,
      headerY,
      stationYText: stationY,
      rowsStartY,
      valueX,
      headerFontSize,
      stationFontSize,
      rowLabelFontSize,
      rowFontSize,
      headerLetterSpacing,
      rowGap,
      labelDx,
      labelDy,
      labelFontSize,
      labelHeight,
      labelRadius,
      labelPaddingX,
    };
  }, [activeTooltipIndex, projectedStations, projectionMetrics, viewport, showStations]);


  const labelWorldGeometry = useMemo(() => {
    if (!projectionMetrics) return null;

    const currentWorldWidth = projectionMetrics.worldWidth / viewport.zoom;
    const currentWorldHeight = projectionMetrics.worldHeight / viewport.zoom;
    const baseScale = clamp(2.4 / Math.max(viewport.zoom, 1), 0.38, 2.4);

    return {
      calloutStroke: Math.max(0.7, baseScale * 0.34),
      labelDx: baseScale * 2.0,
      labelDy: baseScale * 4.7,
      labelFontSize: baseScale * 2.05,
      labelHeight: baseScale * 4.15,
      labelRadius: baseScale * 1.85,
      labelPaddingX: baseScale * 2.05,
    };
  }, [projectionMetrics, viewport.zoom]);


  const selectedStationIdentity = useMemo(
    () => buildStationIdentity(state?.selected_route_name || state?.route_name, selectedStation),
    [state?.selected_route_name, state?.route_name, selectedStation]
  );

  const selectedStationSummary = useMemo(
    () => buildStationSummary(state?.selected_route_name || state?.route_name, selectedStation),
    [state?.selected_route_name, state?.route_name, selectedStation]
  );

  const calculatedCoveredFootage = useMemo(() => {
    const fromSegments = redlineSegments.reduce((sum, segment) => {
      const len = typeof segment.length_ft === "number" && Number.isFinite(segment.length_ft) ? segment.length_ft : 0;
      return sum + len;
    }, 0);
    if (fromSegments > 0) return fromSegments;
    const backendCovered = typeof state?.covered_length_ft === "number" && Number.isFinite(state.covered_length_ft)
      ? state.covered_length_ft
      : 0;
    return backendCovered;
  }, [redlineSegments, state?.covered_length_ft]);

  const effectiveFootage = useMemo(() => {
    const manual = Number.parseFloat(manualFootage);
    if (Number.isFinite(manual) && manual > 0) return manual;
    return calculatedCoveredFootage;
  }, [manualFootage, calculatedCoveredFootage]);

  const numericCostPerFoot = useMemo(() => {
    const parsed = Number.parseFloat(costPerFoot);
    return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
  }, [costPerFoot]);

  const exceptionTotal = useMemo(
    () =>
      exceptions.reduce((sum, item) => {
        const parsed = Number.parseFloat(item.amount);
        return sum + (Number.isFinite(parsed) ? parsed : 0);
      }, 0),
    [exceptions]
  );

  const baseBillingTotal = useMemo(() => effectiveFootage * numericCostPerFoot, [effectiveFootage, numericCostPerFoot]);
  const finalBillingTotal = useMemo(() => baseBillingTotal + exceptionTotal, [baseBillingTotal, exceptionTotal]);

  const drillPathRows = useMemo(() => {
    type DrillPathRow = {
      id: string;
      startStation: string;
      endStation: string;
      lengthFt: number;
      cost: number;
      print: string;
      sourceFile: string;
      routeName: string;
    };

    type DrillPathWorkingRow = DrillPathRow & {
      groupKey: string;
    };

    const workingRows = redlineSegments.reduce<DrillPathWorkingRow[]>((acc, segment, idx) => {
      const lengthFt =
        typeof segment.length_ft === "number" && Number.isFinite(segment.length_ft) ? segment.length_ft : 0;
      const startStation = cleanDisplayText(segment.start_station);
      const endStation = cleanDisplayText(segment.end_station);
      const print = cleanDisplayText(segment.print);
      const sourceFile = cleanDisplayText(segment.source_file);
      const routeName = cleanDisplayText(segment.route_name);
      const groupKey = `${routeName}||${print}||${sourceFile}`;

      const lastRow = acc.length > 0 ? acc[acc.length - 1] : undefined;

      if (!lastRow || lastRow.groupKey !== groupKey) {
        acc.push({
          id: `drill-path-${idx + 1}`,
          startStation,
          endStation,
          lengthFt,
          cost: lengthFt * numericCostPerFoot,
          print,
          sourceFile,
          routeName,
          groupKey,
        });
        return acc;
      }

      lastRow.endStation = endStation;
      lastRow.lengthFt += lengthFt;
      lastRow.cost += lengthFt * numericCostPerFoot;
      return acc;
    }, []);

    return workingRows.map(({ groupKey: _groupKey, ...row }) => row);
  }, [redlineSegments, numericCostPerFoot]);

  const handleAddException = useCallback(() => {
    const label = extraExceptionLabel.trim();
    if (!label) return;

    const nextExceptions: ExceptionCost[] = [
      ...exceptions,
      { id: `custom-${Date.now()}`, label, amount: extraExceptionAmount.trim() },
    ];

    setExceptions(nextExceptions);
    setExtraExceptionLabel("");
    setExtraExceptionAmount("");
  }, [exceptions, extraExceptionLabel, extraExceptionAmount]);

  const handleRemoveException = useCallback((id: string) => {
    const nextExceptions: ExceptionCost[] = exceptions.filter((item) => item.id !== id);
    setExceptions(nextExceptions);
  }, [exceptions]);

  const handleExceptionChange = useCallback((id: string, field: "label" | "amount", value: string) => {
    const nextExceptions: ExceptionCost[] = exceptions.map((item) =>
      item.id === id ? { ...item, [field]: value } : item
    );
    setExceptions(nextExceptions);
  }, [exceptions]);

  const handlePrintReport = useCallback(() => {
    if (typeof window !== "undefined") {
      window.print();
    }
  }, []);

  const fitToBounds = useCallback((targetBounds: Bounds | null) => {
    const container = mapContainerRef.current;
    if (!container || !targetBounds) return;

    const width = Math.max(1, container.clientWidth);
    const height = Math.max(1, container.clientHeight);
    const metrics = getProjectionMetrics(targetBounds, width, height);

    const topLeft = projectWorldPoint(targetBounds.maxLat, targetBounds.minLon, targetBounds, metrics);
    const bottomRight = projectWorldPoint(targetBounds.minLat, targetBounds.maxLon, targetBounds, metrics);

    const contentWidth = Math.max(1, bottomRight.x - topLeft.x);
    const contentHeight = Math.max(1, bottomRight.y - topLeft.y);
    const usableWidth = Math.max(1, metrics.worldWidth - FIT_PADDING * 2);
    const usableHeight = Math.max(1, metrics.worldHeight - FIT_PADDING * 2);

    const zoom = clamp(Math.min(usableWidth / contentWidth, usableHeight / contentHeight), MIN_ZOOM, MAX_ZOOM);
    const centerWorldX = (topLeft.x + bottomRight.x) / 2;
    const centerWorldY = (topLeft.y + bottomRight.y) / 2;

    setViewport({
      zoom,
      panX: metrics.worldWidth / 2 - centerWorldX * zoom,
      panY: metrics.worldHeight / 2 - centerWorldY * zoom,
    });
  }, []);

  const zoomAt = useCallback((nextZoom: number, anchorX: number, anchorY: number) => {
    setViewport((current) => {
      const zoom = clamp(nextZoom, MIN_ZOOM, MAX_ZOOM);
      if (zoom === current.zoom) return current;

      const world = screenToWorld(anchorX, anchorY, current);
      return {
        zoom,
        panX: anchorX - world.x * zoom,
        panY: anchorY - world.y * zoom,
      };
    });
  }, []);

  async function fetchState(message?: string) {
    if (message) {
      setStatusText(message);
      setStatusTone("neutral");
    }
    try {
      const response = await fetch(`${API_BASE}/api/current-state`);
      const data: BackendState = await response.json();
      if (!response.ok || data.success === false) throw new Error(data.error || "Unable to load current state.");
      setState(data);
      if (data.warning) {
        setStatusText(String(data.warning));
        setStatusTone("warning");
      } else if (data.message) {
        setStatusText(String(data.message));
        setStatusTone("success");
      } else if ((data.redline_segments || []).length > 0) {
        setStatusText("Local backend connected. KMZ, redlines, and stations loaded.");
        setStatusTone("success");
      } else if ((data.kmz_reference?.line_features || []).length > 0) {
        setStatusText("Local backend connected. KMZ loaded. Waiting for bore logs.");
        setStatusTone("success");
      } else {
        setStatusText("Local backend connected. Workspace is empty and ready.");
        setStatusTone("neutral");
      }
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Backend connection failed.");
      setStatusTone("error");
    }
  }

  async function handleReset() {
    setBusy(true);
    try {
      const response = await fetch(`${API_BASE}/api/reset-state`, { method: "POST" });
      const data: BackendState = await response.json();
      if (!response.ok || data.success === false) throw new Error(data.error || "Reset failed.");
      setState(data);
      setDidInitialFit(false);
      userHasAdjustedViewportRef.current = false;
      lastAutoFitSignatureRef.current = "";
      if (initialFitRafRef.current !== null) {
        cancelAnimationFrame(initialFitRafRef.current);
        initialFitRafRef.current = null;
      }
      if (initialFitTimeoutRef.current) {
        clearTimeout(initialFitTimeoutRef.current);
        initialFitTimeoutRef.current = null;
      }
      setSelectedStationIndex(null);
      setHoverStationIndex(null);
      setStatusText(String(data.message || "Workspace reset successfully."));
      setStatusTone("success");
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Reset failed.");
      setStatusTone("error");
    } finally {
      // V1 Photo GPS Mapping — Clear Workspace is a true clean slate, so
      // geotagged photos are cleared alongside KMZ/redline/station state,
      // regardless of whether the backend reset succeeded.
      clearGpsPhotos();
      setBusy(false);
    }
  }

  async function handleDesignUpload(file: File) {
    setBusy(true);
    setStatusText(`Uploading design: ${file.name}`);
    setStatusTone("neutral");
    try {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch(`${API_BASE}/api/upload-design`, { method: "POST", body: form });
      const data: BackendState = await response.json();
      if (!response.ok || data.success === false) throw new Error(data.error || "Design upload failed.");
      setState(data);
      setDidInitialFit(false);
      userHasAdjustedViewportRef.current = false;
      lastAutoFitSignatureRef.current = "";
      if (initialFitRafRef.current !== null) {
        cancelAnimationFrame(initialFitRafRef.current);
        initialFitRafRef.current = null;
      }
      if (initialFitTimeoutRef.current) {
        clearTimeout(initialFitTimeoutRef.current);
        initialFitTimeoutRef.current = null;
      }
      setStatusText(String(data.warning || data.message || "Design uploaded successfully."));
      setStatusTone(data.warning ? "warning" : "success");
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Design upload failed.");
      setStatusTone("error");
    } finally {
      setBusy(false);
    }
  }

  async function handleBoreUpload(files: FileList | null) {
    if (!files || !files.length) return;
    setBusy(true);
    setStatusText(`Uploading ${files.length} structured bore file${files.length > 1 ? "s" : ""}...`);
    setStatusTone("neutral");
    try {
      const form = new FormData();
      Array.from(files).forEach((file) => form.append("files", file));
      const response = await fetch(`${API_BASE}/api/upload-structured-bore-files`, { method: "POST", body: form });
      const data: BackendState = await response.json();
      if (!response.ok || data.success === false) throw new Error(data.error || "Structured bore upload failed.");
      setState(data);
      setDidInitialFit(false);
      userHasAdjustedViewportRef.current = false;
      lastAutoFitSignatureRef.current = "";
      if (initialFitRafRef.current !== null) {
        cancelAnimationFrame(initialFitRafRef.current);
        initialFitRafRef.current = null;
      }
      if (initialFitTimeoutRef.current) {
        clearTimeout(initialFitTimeoutRef.current);
        initialFitTimeoutRef.current = null;
      }
      setStatusText(String(data.warning || data.message || "Structured bore files uploaded successfully."));
      setStatusTone(data.warning ? "warning" : "success");
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Structured bore upload failed.");
      setStatusTone("error");
    } finally {
      setBusy(false);
    }
  }

  async function submitBugNote() {
    if (!notes.trim()) return;
    setBusy(true);
    try {
      const payload = {
        id: `beta-note-${Date.now()}`,
        timestamp: new Date().toISOString(),
        level: "info",
        category: "beta-test",
        message: notes.trim(),
        details: {
          enteredJobLabel: jobLabel,
          selectedRouteName: state?.selected_route_name || state?.route_name || "",
          redlineSegmentCount: (state?.redline_segments || []).length,
          stationPointCount: (state?.station_points || []).length,
        },
      };
      const response = await fetch(`${API_BASE}/api/report-bug`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok || data.success === false) throw new Error(data.error || "Note submission failed.");
      setStatusText(String(data.message || "Operator note submitted."));
      setStatusTone("success");
      setNotes("");
      await fetchState();
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Note submission failed.");
      setStatusTone("error");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    fetchState("Connecting to local beta backend...");
  }, []);

  useEffect(() => {
    if (!showStations) {
      setHoverStationIndex(null);
      setSelectedStationIndex(null);
    }
  }, [showStations]);


  async function fetchStationPhotos(stationIdentity: string) {
    if (!stationIdentity) {
      setStationPhotos([]);
      return;
    }
    setStationPhotosLoading(true);
    try {
      const response = await fetch(
        `${API_BASE}/api/station-photos?station_identity=${encodeURIComponent(stationIdentity)}`
      );
      const data = await response.json();
      if (!response.ok || data.success === false) {
        throw new Error(data.error || "Unable to load station photos.");
      }
      setStationPhotos(Array.isArray(data.photos) ? data.photos : []);
    } catch (error) {
      setStationPhotos([]);
      setStatusText(error instanceof Error ? error.message : "Unable to load station photos.");
      setStatusTone("error");
    } finally {
      setStationPhotosLoading(false);
    }
  }

  async function handleStationPhotoUpload(files: FileList | null) {
    if (!files || !files.length || !selectedStation || !selectedStationIdentity) return;
    setStationPhotoBusy(true);
    setStatusTone("neutral");
    setStatusText(`Uploading ${files.length} station photo${files.length > 1 ? "s" : ""}...`);
    try {
      const form = new FormData();
      form.append("station_identity", selectedStationIdentity);
      form.append("station_summary", selectedStationSummary);
      form.append("route_name", state?.selected_route_name || state?.route_name || "");
      form.append("source_file", selectedStation.source_file || "");
      form.append("station_label", selectedStation.station || "");
      form.append(
        "mapped_station_ft",
        stationIdentityPart(selectedStation.mapped_station_ft, 3)
      );
      form.append(
        "lat",
        stationIdentityPart(selectedStation.lat, 8)
      );
      form.append(
        "lon",
        stationIdentityPart(selectedStation.lon, 8)
      );
      Array.from(files).forEach((file) => form.append("files", file));

      const response = await fetch(`${API_BASE}/api/station-photos/upload`, {
        method: "POST",
        body: form,
      });
      const data = await response.json();
      if (!response.ok || data.success === false) {
        throw new Error(data.error || "Station photo upload failed.");
      }
      setStatusTone("success");
      setStatusText(data.message || "Station photo uploaded.");
      await fetchStationPhotos(selectedStationIdentity);
    } catch (error) {
      setStatusTone("error");
      setStatusText(error instanceof Error ? error.message : "Station photo upload failed.");
    } finally {
      setStationPhotoBusy(false);
    }
  }

  // ─── V1 Photo GPS Mapping — upload handler ──────────────────────────────────
  // Client-only: reads EXIF GPS from each image, creates a blob URL for preview,
  // and adds a GpsPhoto row to local state. No network calls. No mutation of
  // BackendState. Photos with valid GPS are flagged `mapped` and will render as
  // markers; photos without GPS are flagged `no_gps` and appear in the
  // "Unmapped Photos" list.

  async function handleGpsPhotoUpload(files: FileList | null) {
    if (!files || !files.length) return;
    setGpsPhotoBusy(true);
    setStatusText(`Reading GPS from ${files.length} photo${files.length > 1 ? "s" : ""}...`);
    setStatusTone("neutral");

    const fileArray = Array.from(files);
    const newPhotos: GpsPhoto[] = [];

    for (const file of fileArray) {
      let gps: { lat: number; lon: number } | null = null;
      let reason: GpsPhoto["reason"] = "no_gps";
      try {
        gps = await extractGps(file);
        reason = gps ? "mapped" : "no_gps";
      } catch {
        gps = null;
        reason = "unreadable";
      }

      newPhotos.push({
        id: `gpsphoto-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
        file,
        previewUrl: URL.createObjectURL(file),
        filename: file.name,
        sizeBytes: file.size,
        contentType: file.type || "",
        lat: gps?.lat ?? null,
        lon: gps?.lon ?? null,
        reason,
        addedAt: Date.now(),
      });
    }

    setGpsPhotos((prev) => [...prev, ...newPhotos]);

    const mappedCount = newPhotos.filter((p) => p.reason === "mapped").length;
    const unmappedCount = newPhotos.length - mappedCount;
    setStatusTone("success");
    setStatusText(
      `Added ${newPhotos.length} photo${newPhotos.length > 1 ? "s" : ""}: ` +
      `${mappedCount} with GPS, ${unmappedCount} unmapped.`
    );
    setGpsPhotoBusy(false);
  }

  function clearGpsPhotos() {
    setGpsPhotos((prev) => {
      prev.forEach((p) => {
        try { URL.revokeObjectURL(p.previewUrl); } catch { /* noop */ }
      });
      return [];
    });
    setSelectedGpsPhotoId(null);
    setHoverGpsPhotoId(null);
  }

  // Revoke object URLs on unmount. We use a ref so the cleanup sees the
  // latest photo list, not the initial empty array captured by closure.
  const gpsPhotosRef = useRef<GpsPhoto[]>([]);
  useEffect(() => {
    gpsPhotosRef.current = gpsPhotos;
  }, [gpsPhotos]);
  useEffect(() => {
    return () => {
      gpsPhotosRef.current.forEach((p) => {
        try { URL.revokeObjectURL(p.previewUrl); } catch { /* noop */ }
      });
    };
  }, []);



  useEffect(() => {
    if (!selectedStation || !selectedStationIdentity) {
      setStationPhotos([]);
      return;
    }
    fetchStationPhotos(selectedStationIdentity);
  }, [selectedStation, selectedStationIdentity]);

  useEffect(() => {
    const container = mapContainerRef.current;
    if (!container) return;

    let resizeTimeout: ReturnType<typeof setTimeout> | null = null;

    const updateSize = () => {
      setContainerSize((prev) => {
        const newWidth = Math.max(1, Math.round(container.clientWidth));
        const newHeight = Math.max(1, Math.round(container.clientHeight));

        if (prev.width === newWidth && prev.height === newHeight) {
          return prev;
        }

        return {
          width: newWidth,
          height: newHeight,
        };
      });
    };

    updateSize();
    const observer = new ResizeObserver(() => {
      if (resizeTimeout) {
        clearTimeout(resizeTimeout);
      }
      resizeTimeout = setTimeout(updateSize, 100);
    });
    observer.observe(container);

    return () => {
      if (resizeTimeout) {
        clearTimeout(resizeTimeout);
      }
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    if (didInitialFit) return;
    if (userHasAdjustedViewportRef.current) return;
    if (containerSize.width <= 0 || containerSize.height <= 0) return;

    const targetBounds = initialFitBounds;
    if (!targetBounds) return;
    if (!(designCoords.length > 0)) return;
    if (!autoFitSignature) return;
    if (lastAutoFitSignatureRef.current === autoFitSignature) return;

    if (initialFitRafRef.current !== null) {
      cancelAnimationFrame(initialFitRafRef.current);
      initialFitRafRef.current = null;
    }
    if (initialFitTimeoutRef.current) {
      clearTimeout(initialFitTimeoutRef.current);
      initialFitTimeoutRef.current = null;
    }

    initialFitRafRef.current = window.requestAnimationFrame(() => {
      initialFitTimeoutRef.current = setTimeout(() => {
        if (userHasAdjustedViewportRef.current) return;
        if (didInitialFit) return;
        if (containerSize.width <= 0 || containerSize.height <= 0) return;
        if (!(designCoords.length > 0)) return;
        fitToBounds(targetBounds);
        lastAutoFitSignatureRef.current = autoFitSignature;
        setDidInitialFit(true);
      }, 0);
    });

    return () => {
      if (initialFitRafRef.current !== null) {
        cancelAnimationFrame(initialFitRafRef.current);
        initialFitRafRef.current = null;
      }
      if (initialFitTimeoutRef.current) {
        clearTimeout(initialFitTimeoutRef.current);
        initialFitTimeoutRef.current = null;
      }
    };
  }, [
    didInitialFit,
    initialFitBounds,
    autoFitSignature,
    containerSize.width,
    containerSize.height,
    designCoords.length,
    routeCoords.length,
    stationPoints.length,
    fitToBounds,
  ]);

  function handleWheel(e: React.WheelEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    userHasAdjustedViewportRef.current = true;

    const rect = mapContainerRef.current?.getBoundingClientRect();
    if (!rect) return;

    const anchorX = e.clientX - rect.left;
    const anchorY = e.clientY - rect.top;
    zoomAt(viewport.zoom * (e.deltaY < 0 ? WHEEL_IN : WHEEL_OUT), anchorX, anchorY);
  }

  function handlePointerDown(e: React.PointerEvent<HTMLDivElement>) {
    if (e.button !== 0) return;
    const rect = mapContainerRef.current?.getBoundingClientRect();
    if (!rect) return;

    e.preventDefault();
    e.stopPropagation();

    if (e.shiftKey) {
      userHasAdjustedViewportRef.current = true;
      setBoxZoom({
        startX: e.clientX - rect.left,
        startY: e.clientY - rect.top,
        endX: e.clientX - rect.left,
        endY: e.clientY - rect.top,
      });
      e.currentTarget.setPointerCapture?.(e.pointerId);
      return;
    }

    userHasAdjustedViewportRef.current = true;
    panStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      panX: viewport.panX,
      panY: viewport.panY,
    };
    setIsPanning(true);
    e.currentTarget.setPointerCapture?.(e.pointerId);
  }

  function handlePointerMove(e: React.PointerEvent<HTMLDivElement>) {
    const rect = mapContainerRef.current?.getBoundingClientRect();
    if (!rect) return;

    if (boxZoom) {
      setBoxZoom((current) =>
        current
          ? {
              ...current,
              endX: e.clientX - rect.left,
              endY: e.clientY - rect.top,
            }
          : null
      );
      return;
    }

    if (isPanning && panStartRef.current) {
      const dx = e.clientX - panStartRef.current.x;
      const dy = e.clientY - panStartRef.current.y;
      setViewport((current) => ({
        ...current,
        panX: panStartRef.current ? panStartRef.current.panX + dx : current.panX,
        panY: panStartRef.current ? panStartRef.current.panY + dy : current.panY,
      }));
    }
  }

  function handlePointerUp(_: React.PointerEvent<HTMLDivElement>) {
    if (boxZoom && mapContainerRef.current) {
      const width = Math.abs(boxZoom.endX - boxZoom.startX);
      const height = Math.abs(boxZoom.endY - boxZoom.startY);

      if (width > 18 && height > 18) {
        const boxLeft = Math.min(boxZoom.startX, boxZoom.endX);
        const boxTop = Math.min(boxZoom.startY, boxZoom.endY);
        const boxCenterX = boxLeft + width / 2;
        const boxCenterY = boxTop + height / 2;

        const currentWorldWidth = containerSize.width / viewport.zoom;
        const currentWorldHeight = containerSize.height / viewport.zoom;
        const selectedWorldWidth = currentWorldWidth * (width / containerSize.width);
        const selectedWorldHeight = currentWorldHeight * (height / containerSize.height);
        const targetZoom = clamp(
          Math.min(containerSize.width / selectedWorldWidth, containerSize.height / selectedWorldHeight),
          MIN_ZOOM,
          MAX_ZOOM
        );

        const centerWorld = screenToWorld(boxCenterX, boxCenterY, viewport);
        setViewport({
          zoom: targetZoom,
          panX: containerSize.width / 2 - centerWorld.x * targetZoom,
          panY: containerSize.height / 2 - centerWorld.y * targetZoom,
        });
      }

      setBoxZoom(null);
      return;
    }

    setIsPanning(false);
    panStartRef.current = null;
  }

  const redlineStroke = "rgba(255, 72, 72, 1)";
  const redlineCasing = "rgba(18, 4, 6, 0.82)";
  const hasDesign = (kmzLineFeatures.length || kmzPolygonFeatures.length) > 0;
  const hasBoreFiles = (state?.loaded_field_data_files || 0) > 0;
  const hasGeneratedOutput = redlineSegments.length > 0 || stationPoints.length > 0;

  return (
    <div style={{ minHeight: "100vh", background: "linear-gradient(180deg, #eef3f8 0%, #f6f9fc 100%)", fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif", color: "#0f172a" }}>
      <style>{`
        @media print {
          body {
            background: #ffffff !important;
          }
          button, input[type="file"], textarea {
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
          }
          .no-print {
            display: none !important;
          }
          .print-report {
            box-shadow: none !important;
            border-color: #d1d5db !important;
            break-inside: avoid;
          }
        }
      `}</style>
      <div style={{ maxWidth: 1520, margin: "0 auto", padding: 20 }}>
        <div style={{ display: "grid", gap: 18 }}>
          <div
            style={{
              background: "linear-gradient(135deg, #ffffff 0%, #f7fbff 52%, #eef6ff 100%)",
              border: "1px solid #dbe4ee",
              borderRadius: 24,
              padding: 24,
              boxShadow: "0 12px 28px rgba(15, 23, 42, 0.05)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "flex-start", flexWrap: "wrap" }}>
              <div style={{ maxWidth: 860 }}>
                <div style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "6px 10px", borderRadius: 999, background: "#eff6ff", border: "1px solid #cfe0f5", fontSize: 12, fontWeight: 800, color: "#1d4ed8", marginBottom: 12 }}>
                  Phase 1 Safe UI Polish
                </div>
                <div style={{ fontSize: 34, fontWeight: 900, letterSpacing: -0.7 }}>OSP Redlining Operator Workspace</div>
                <div style={{ marginTop: 8, fontSize: 15, color: "#526173", lineHeight: 1.6 }}>
                  Upload design files, load bore logs, generate redlines, review the map, and stage reporting outputs in one cleaner top-to-bottom workflow.
                </div>
                <div style={{ marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap" }}>
                  <Pill label="API" value={API_BASE} />
                  <Pill label="Active job" value={String(activeJob)} />
                  <Pill label="Status" value={String(verification?.status || "waiting")} />
                </div>
              </div>

              <div style={{ display: "grid", gap: 10, minWidth: 320, flex: "0 1 360px" }}>
                <input
                  value={jobLabel}
                  onChange={(e) => setJobLabel(e.target.value)}
                  placeholder="Optional local beta job label"
                  style={{ borderRadius: 14, border: "1px solid #cfd8e3", background: "#fff", padding: "12px 14px", outline: "none", fontSize: 14 }}
                />
                <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 10 }}>
                  <button onClick={() => fetchState("Refreshing backend state...")} disabled={busy} style={buttonStyle("#ffffff", "#0f172a", "#cfd8e3", busy)}>Refresh State</button>
                  <button onClick={handleReset} disabled={busy} style={buttonStyle("#0f172a", "#ffffff", "#0f172a", busy)}>Clear Workspace</button>
                </div>
              </div>
            </div>
          </div>

          <StatusBanner tone={statusTone} text={statusText} />

          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 16, alignItems: "stretch" }}>
            <SummaryCard title="Active Job" value={String(activeJob)} subtitle="Local label or backend-selected route" />
            <SummaryCard title="Files Loaded" value={String((hasDesign ? 1 : 0) + (state?.loaded_field_data_files || 0))} subtitle="Design + structured bore files" />
            <SummaryCard title="QA Status" value={String(verification?.status || "waiting")} subtitle="Real backend verification summary" />
            <SummaryCard title="Output Counts" value={`${stationPoints.length} pts / ${redlineSegments.length} segs`} subtitle="Station points and generated redline segments" />
          </div>

          <Section
            title="1. Upload"
            subtitle="Load the design first, then add one or more structured bore log files. This section stays tied to the current backend workflow."
          >
            <div style={{ display: "grid", gridTemplateColumns: "1.1fr 1.1fr 0.8fr", gap: 16, alignItems: "start" }}>
              <label style={uploadCardStyle(busy)}>
                <input
                  type="file"
                  accept=".kmz,.kml"
                  style={{ display: "none" }}
                  disabled={busy}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleDesignUpload(file);
                    e.currentTarget.value = "";
                  }}
                />
                <div style={{ fontWeight: 800, fontSize: 16 }}>Upload KMZ Design</div>
                <div style={{ marginTop: 6, fontSize: 13, color: "#64748b", lineHeight: 1.55 }}>Loads KMZ layers and selected route geometry without changing map internals.</div>
                <div style={{ marginTop: 14, fontSize: 12, color: hasDesign ? "#166534" : "#64748b", fontWeight: 700 }}>
                  {hasDesign ? "Design appears loaded in backend state." : "No design currently loaded."}
                </div>
              </label>

              <label style={uploadCardStyle(busy)}>
                <input
                  type="file"
                  accept=".xlsx,.xls,.csv"
                  multiple
                  style={{ display: "none" }}
                  disabled={busy}
                  onChange={(e) => {
                    handleBoreUpload(e.target.files);
                    e.currentTarget.value = "";
                  }}
                />
                <div style={{ fontWeight: 800, fontSize: 16 }}>Upload Structured Bore Logs</div>
                <div style={{ marginTop: 6, fontSize: 13, color: "#64748b", lineHeight: 1.55 }}>Triggers the existing backend upload flow for route matching, station mapping, and generated redlines.</div>
                <div style={{ marginTop: 14, fontSize: 12, color: hasBoreFiles ? "#166534" : "#64748b", fontWeight: 700 }}>
                  {hasBoreFiles ? `${state?.loaded_field_data_files || 0} bore file(s) loaded.` : "No bore files currently loaded."}
                </div>
              </label>

              <div style={{ border: "1px solid #dbe4ee", borderRadius: 16, background: "#fbfdff", padding: 16 }}>
                <div style={{ fontWeight: 800, fontSize: 15 }}>File status</div>
                <div style={{ marginTop: 12, display: "grid", gap: 10 }}>
                  <Pill label="Design" value={hasDesign ? "Loaded" : "Waiting"} />
                  <Pill label="Bore files" value={String(state?.loaded_field_data_files || 0)} />
                  <Pill label="Latest file" value={state?.latest_structured_file || "--"} />
                  <Pill label="Output ready" value={hasGeneratedOutput ? "Yes" : "No"} />
                </div>
              </div>
            </div>
          </Section>

          <Section
            title="2. Actions"
            subtitle="Workspace controls and live backend facts. These controls use the existing execution flow exactly as-is."
          >
            <div style={{ display: "grid", gridTemplateColumns: "0.95fr 1.05fr", gap: 16, alignItems: "start" }}>
              <div style={{ display: "grid", gap: 12 }}>
                <div style={{ border: "1px solid #dbe4ee", borderRadius: 16, padding: 16, background: "#fbfdff" }}>
                  <div style={{ fontSize: 15, fontWeight: 800 }}>Workflow guidance</div>
                  <div style={{ marginTop: 8, fontSize: 13, color: "#64748b", lineHeight: 1.65 }}>
                    1. Upload a KMZ design.<br />
                    2. Upload structured bore logs.<br />
                    3. Review generated output on the map.<br />
                    4. Use the reporting shells below for staging pricing, crew, exceptions, and export workflow.
                  </div>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 12 }}>
                  <button onClick={() => fetchState("Refreshing backend state...")} disabled={busy} style={buttonStyle("#ffffff", "#0f172a", "#cfd8e3", busy)}>Refresh Backend State</button>
                  <button onClick={handleReset} disabled={busy} style={buttonStyle("#0f172a", "#ffffff", "#0f172a", busy)}>Clear Workspace</button>
                </div>
              </div>

              <div style={{ border: "1px solid #dbe4ee", borderRadius: 16, padding: 16, background: "#ffffff" }}>
                <div style={{ fontSize: 15, fontWeight: 800, marginBottom: 6 }}>Current backend state</div>
                <SmallRow label="Selected route" value={state?.selected_route_name || state?.route_name || "--"} />
                <SmallRow label="Suggested route id" value={state?.suggested_route_id || "--"} />
                <SmallRow label="Latest bore file" value={state?.latest_structured_file || "--"} />
                <SmallRow label="Field data files" value={String(state?.loaded_field_data_files || 0)} />
                <SmallRow label="Route length" value={`${formatNumber(state?.total_length_ft)} ft`} />
                <SmallRow label="Covered length" value={`${formatNumber(state?.covered_length_ft)} ft`} />
                <SmallRow label="Completion %" value={`${formatNumber(state?.completion_pct)}%`} />
                <SmallRow label="Active-route covered" value={`${formatNumber(state?.active_route_covered_length_ft)} ft`} />
                <SmallRow label="Active-route completion" value={`${formatNumber(state?.active_route_completion_pct)}%`} />
                <SmallRow label="Mapping mode" value={state?.station_mapping_mode || "--"} />
                <SmallRow label="Committed rows" value={String((state?.committed_rows || []).length)} />
                <SmallRow label="Bug report count" value={String(state?.bug_report_count || 0)} />
              </div>
            </div>
          </Section>

          <Section
            title="3. Map Review"
            subtitle="Safe map polish only: smaller black stations, stronger redline readability, cleaner field-review callouts, and initial fit prioritized to the full KMZ design footprint."
            actions={
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button onClick={() => {
                  userHasAdjustedViewportRef.current = true;
                  zoomAt(viewport.zoom * BUTTON_IN, containerSize.width / 2, containerSize.height / 2);
                }} style={miniMapButton}>+</button>
                <button onClick={() => {
                  userHasAdjustedViewportRef.current = true;
                  zoomAt(viewport.zoom * BUTTON_OUT, containerSize.width / 2, containerSize.height / 2);
                }} style={miniMapButton}>-</button>
                <button onClick={() => {
                  userHasAdjustedViewportRef.current = true;
                  fitToBounds(designBounds || bounds);
                }} style={miniMapButton}>Fit All</button>
                <button onClick={() => {
                  userHasAdjustedViewportRef.current = true;
                  fitToBounds(stationOnlyBounds || bounds);
                }} style={miniMapButton}>Fit Stations</button>
                <button onClick={() => setShowStations((current) => !current)} style={miniMapButton}>{showStations ? "Hide Stations" : "Show Stations"}</button>
              </div>
            }
          >
            <div style={{ display: "grid", gap: 16 }}>
              <div
                ref={mapContainerRef}
                style={{
                  position: "relative",
                  height: MAP_HEIGHT,
                  borderRadius: 18,
                  overflow: "hidden",
                  background: "linear-gradient(180deg, #0b1a2a 0%, #060f1c 60%, #03080f 100%)",
                  border: "1px solid #1f3a5e",
                  cursor: boxZoom ? "crosshair" : isPanning ? "grabbing" : "grab",
                  overscrollBehavior: "contain",
                  touchAction: "none",
                  userSelect: "none",
                  boxShadow: "inset 0 1px 0 rgba(255,255,255,0.04)",
                }}
                onWheel={handleWheel}
                onPointerDown={handlePointerDown}
                onPointerMove={handlePointerMove}
                onPointerUp={handlePointerUp}
                onPointerCancel={handlePointerUp}
                onPointerLeave={() => {
                  if (!isPanning) setHoverStationIndex(null);
                }}
              >
                {renderBounds && projectionMetrics && allCoords.length > 0 ? (
                  <svg
                    viewBox={viewBoxToString(projectionMetrics, viewport)}
                    preserveAspectRatio="xMidYMid meet"
                    style={{ position: "absolute", inset: 0, width: "100%", height: "100%", display: "block", shapeRendering: "geometricPrecision" }}
                    onClick={() => {
                      if (selectedStationIndex !== null) {
                        setSelectedStationIndex(null);
                      }
                      if (selectedGpsPhotoId !== null) {
                        setSelectedGpsPhotoId(null);
                      }
                    }}
                  >
                    {/* ─── Visual polish — SVG defs ───────────────────────── */}
                    {/* Grid pattern: faint cool-blue dots/lines that pan and  */}
                    {/* zoom with the map (they live in world coords). Sized   */}
                    {/* in world units; the visual frequency stays roughly     */}
                    {/* constant because the SVG viewBox scales with zoom.     */}
                    {/* Redline glow: feGaussianBlur + feMerge so the bright   */}
                    {/* red stroke gets a soft red bloom around it.            */}
                    <defs>
                      <pattern
                        id="map-grid-pattern"
                        x="0"
                        y="0"
                        width="40"
                        height="40"
                        patternUnits="userSpaceOnUse"
                      >
                        <path
                          d="M 40 0 L 0 0 0 40"
                          fill="none"
                          stroke="rgba(120, 180, 220, 0.05)"
                          strokeWidth="0.6"
                          vectorEffect="non-scaling-stroke"
                        />
                      </pattern>
                      <pattern
                        id="map-grid-pattern-coarse"
                        x="0"
                        y="0"
                        width="200"
                        height="200"
                        patternUnits="userSpaceOnUse"
                      >
                        <path
                          d="M 200 0 L 0 0 0 200"
                          fill="none"
                          stroke="rgba(140, 195, 235, 0.08)"
                          strokeWidth="0.9"
                          vectorEffect="non-scaling-stroke"
                        />
                      </pattern>
                      <filter
                        id="redline-glow"
                        x="-20%"
                        y="-20%"
                        width="140%"
                        height="140%"
                      >
                        <feGaussianBlur stdDeviation="1.6" result="redBlur" />
                        <feMerge>
                          <feMergeNode in="redBlur" />
                          <feMergeNode in="SourceGraphic" />
                        </feMerge>
                      </filter>
                    </defs>

                    <g id="kmz-design-layer">
                      {/* Base dark wash */}
                      <rect
                        x={0}
                        y={0}
                        width={projectionMetrics?.worldWidth || PROJECTION_BASE_WIDTH}
                        height={projectionMetrics?.worldHeight || PROJECTION_BASE_WIDTH}
                        fill="rgba(4,10,18,0.97)"
                      />
                      {/* Fine grid */}
                      <rect
                        x={0}
                        y={0}
                        width={projectionMetrics?.worldWidth || PROJECTION_BASE_WIDTH}
                        height={projectionMetrics?.worldHeight || PROJECTION_BASE_WIDTH}
                        fill="url(#map-grid-pattern)"
                        pointerEvents="none"
                      />
                      {/* Coarse grid for stronger structure at low zoom */}
                      <rect
                        x={0}
                        y={0}
                        width={projectionMetrics?.worldWidth || PROJECTION_BASE_WIDTH}
                        height={projectionMetrics?.worldHeight || PROJECTION_BASE_WIDTH}
                        fill="url(#map-grid-pattern-coarse)"
                        pointerEvents="none"
                      />

                      {kmzPolygonPaths.map((poly, idx) => {
                        const feature = kmzPolygonFeatures[idx];
                        return poly.path ? (
                          <path
                            key={poly.id}
                            d={poly.path}
                            fill={kmzPolygonFill(feature)}
                            fillOpacity={kmzPolygonOpacity(feature)}
                            stroke={kmzPolygonStroke(feature)}
                            strokeWidth={feature?.stroke_width ?? 1.2}
                            vectorEffect="non-scaling-stroke"
                          />
                        ) : null;
                      })}

                      {kmzLinePaths.map((line, idx) => {
                        const feature = kmzLineFeatures[idx];
                        const stroke = kmzLineStroke(feature);
                        const width = kmzLineWidth(feature);
                        return line.path ? (
                          <g key={line.id}>
                            <path
                              d={line.path}
                              fill="none"
                              stroke="rgba(12,18,28,0.18)"
                              strokeWidth={width + 0.8}
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              vectorEffect="non-scaling-stroke"
                            />
                            <path
                              d={line.path}
                              fill="none"
                              stroke={stroke}
                              strokeOpacity={0.78}
                              strokeWidth={width}
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              vectorEffect="non-scaling-stroke"
                            />
                          </g>
                        ) : null;
                      })}
                    </g>

                    <g id="redline-layer">
                      {redlinePaths.map((line) =>
                        line.path ? (
                          <g key={line.id}>
                            <path
                              d={line.path}
                              fill="none"
                              stroke={redlineCasing}
                              strokeWidth={6.2}
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              vectorEffect="non-scaling-stroke"
                            />
                            <path
                              d={line.path}
                              fill="none"
                              stroke={redlineStroke}
                              strokeWidth={4.35}
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              vectorEffect="non-scaling-stroke"
                              filter="url(#redline-glow)"
                            />
                          </g>
                        ) : null
                      )}
                    </g>

                    {showStations ? (
                      <g id="station-layer">
                        {projectedStations.map(({ idx, world, point }) => {
                          const isSelected = selectedStationIndex === idx;
                          const isHovered = hoverStationIndex === idx;
                          const baseRadius = viewport.zoom < 4 ? 1.8 : viewport.zoom < 12 ? 1.5 : 1.25;
                          const radius = isSelected ? baseRadius + 0.8 : isHovered ? baseRadius + 0.45 : baseRadius;
                          const halo = isSelected ? radius + 3.2 : isHovered ? radius + 2.1 : radius + 0.7;
                          const showLabel = visibleLabelIndices.has(idx);
                          const stationLabel = cleanDisplayText(point.station);

                          return (
                            <g
                              key={`station-${idx}`}
                              style={{ cursor: "pointer" }}
                              onPointerDown={(e) => {
                                e.stopPropagation();
                              }}
                              onPointerEnter={() => setHoverStationIndex(idx)}
                              onPointerLeave={() => setHoverStationIndex((current) => (current === idx ? null : current))}
                              onClick={(e) => {
                                e.stopPropagation();
                                setSelectedStationIndex(idx);
                              }}
                            >
                              {(isSelected || isHovered) ? (
                                <circle
                                  cx={world.x}
                                  cy={world.y}
                                  r={halo}
                                  fill={isSelected ? "rgba(255, 214, 10, 0.24)" : "rgba(255,255,255,0.16)"}
                                  pointerEvents="none"
                                />
                              ) : null}
                              <circle
                                cx={world.x}
                                cy={world.y}
                                r={radius + 0.45}
                                fill="rgba(255,255,255,0.82)"
                              />
                              <circle
                                cx={world.x}
                                cy={world.y}
                                r={radius}
                                fill={isSelected ? "#facc15" : isHovered ? "#dbeafe" : "#05070a"}
                                stroke={isSelected ? "rgba(255,255,255,0.96)" : isHovered ? "rgba(255,255,255,0.92)" : "rgba(255,255,255,0.78)"}
                                strokeWidth={isSelected ? 1.05 : isHovered ? 0.95 : 0.8}
                                vectorEffect="non-scaling-stroke"
                              />
                              {showLabel ? (
                                <g pointerEvents="none">
                                  <rect
                                    x={world.x + (labelWorldGeometry?.labelDx ?? 6)}
                                    y={world.y - (labelWorldGeometry?.labelDy ?? 12) - (labelWorldGeometry?.labelHeight ?? 10) * 0.5}
                                    rx={labelWorldGeometry?.labelRadius ?? 4}
                                    ry={labelWorldGeometry?.labelRadius ?? 4}
                                    width={Math.max((labelWorldGeometry?.labelHeight ?? 10) * 2.2, stationLabel.length * (labelWorldGeometry?.labelFontSize ?? 5) * 0.62 + (labelWorldGeometry?.labelPaddingX ?? 4) * 2)}
                                    height={labelWorldGeometry?.labelHeight ?? 10}
                                    fill="rgba(14, 24, 34, 0.88)"
                                    stroke="rgba(255,255,255,0.08)"
                                    strokeWidth={Math.max(0.55, (labelWorldGeometry?.calloutStroke ?? 1) * 0.5)}
                                  />
                                  <text
                                    x={world.x + (labelWorldGeometry?.labelDx ?? 6) + (labelWorldGeometry?.labelPaddingX ?? 4)}
                                    y={world.y - (labelWorldGeometry?.labelDy ?? 12) + (labelWorldGeometry?.labelFontSize ?? 5) * 0.34}
                                    fill="#f8fafc"
                                    fontSize={labelWorldGeometry?.labelFontSize ?? 5}
                                    fontWeight="700"
                                    style={{ userSelect: "none" }}
                                  >
                                    {stationLabel}
                                  </text>
                                </g>
                              ) : null}
                            </g>
                          );
                        })}
                      </g>
                    ) : null}

                    {/* ─── V1 Photo GPS Mapping — photo marker layer ───── */}
                    {/* Renders above stations, below the station tooltip.  */}
                    {/* Distinct amber pin shape so photos never visually    */}
                    {/* collide with the black station dots.                 */}
                    {projectedPhotos.length > 0 ? (
                      <g id="photo-marker-layer">
                        {projectedPhotos.map(({ photo, world }) => {
                          const isSelected = selectedGpsPhotoId === photo.id;
                          const isHovered = hoverGpsPhotoId === photo.id;
                          // Mirror the zoom-aware sizing used by stations so
                          // photo pins don't get huge at low zoom or tiny at
                          // high zoom. Photo pins are slightly larger than
                          // station dots so they read as "pins" not "dots".
                          const baseRadius = viewport.zoom < 4 ? 2.6 : viewport.zoom < 12 ? 2.1 : 1.7;
                          const radius = isSelected ? baseRadius + 1.0 : isHovered ? baseRadius + 0.5 : baseRadius;
                          const tailHeight = radius * 1.4;
                          // Pin body is centered above the actual coordinate;
                          // the tail points down to (world.x, world.y).
                          const bodyCx = world.x;
                          const bodyCy = world.y - tailHeight;
                          return (
                            <g
                              key={`gpsphoto-${photo.id}`}
                              style={{ cursor: "pointer" }}
                              onPointerDown={(e) => {
                                e.stopPropagation();
                              }}
                              onPointerEnter={() => setHoverGpsPhotoId(photo.id)}
                              onPointerLeave={() =>
                                setHoverGpsPhotoId((current) => (current === photo.id ? null : current))
                              }
                              onClick={(e) => {
                                e.stopPropagation();
                                setSelectedGpsPhotoId(photo.id);
                              }}
                            >
                              {/* Pin tail: triangle from body down to the exact coord */}
                              <path
                                d={`M ${bodyCx - radius * 0.55} ${bodyCy + radius * 0.65} L ${world.x} ${world.y} L ${bodyCx + radius * 0.55} ${bodyCy + radius * 0.65} Z`}
                                fill={isSelected ? "#b45309" : "#f59e0b"}
                                stroke="rgba(255,255,255,0.9)"
                                strokeWidth={0.45}
                                vectorEffect="non-scaling-stroke"
                              />
                              {/* Halo for hover/selected */}
                              {(isSelected || isHovered) ? (
                                <circle
                                  cx={bodyCx}
                                  cy={bodyCy}
                                  r={radius + (isSelected ? 2.4 : 1.6)}
                                  fill={isSelected ? "rgba(245, 158, 11, 0.28)" : "rgba(245, 158, 11, 0.18)"}
                                  pointerEvents="none"
                                />
                              ) : null}
                              {/* Pin body — outer amber ring */}
                              <circle
                                cx={bodyCx}
                                cy={bodyCy}
                                r={radius}
                                fill={isSelected ? "#b45309" : "#f59e0b"}
                                stroke="rgba(255,255,255,0.95)"
                                strokeWidth={0.8}
                                vectorEffect="non-scaling-stroke"
                              />
                              {/* Inner lens dot — evokes a camera aperture */}
                              <circle
                                cx={bodyCx}
                                cy={bodyCy}
                                r={radius * 0.45}
                                fill="#ffffff"
                              />
                              <circle
                                cx={bodyCx}
                                cy={bodyCy}
                                r={radius * 0.22}
                                fill={isSelected ? "#b45309" : "#f59e0b"}
                              />
                            </g>
                          );
                        })}
                      </g>
                    ) : null}

                    {tooltipStation && tooltipWorldGeometry ? (
                      <g id="station-tooltip-layer" pointerEvents="none">
                        <path
                          d={
                            tooltipWorldGeometry.placeRight
                              ? `M ${tooltipWorldGeometry.stationX + tooltipWorldGeometry.calloutInset} ${tooltipWorldGeometry.stationY} L ${tooltipWorldGeometry.cardX} ${tooltipWorldGeometry.calloutMidY}`
                              : `M ${tooltipWorldGeometry.stationX - tooltipWorldGeometry.calloutInset} ${tooltipWorldGeometry.stationY} L ${tooltipWorldGeometry.cardX + tooltipWorldGeometry.cardWidth} ${tooltipWorldGeometry.calloutMidY}`
                          }
                          fill="none"
                          stroke="rgba(255,255,255,0.28)"
                          strokeWidth={tooltipWorldGeometry.calloutStroke}
                          strokeLinecap="round"
                        />
                        <rect
                          x={tooltipWorldGeometry.cardX}
                          y={tooltipWorldGeometry.cardY}
                          width={tooltipWorldGeometry.cardWidth}
                          height={tooltipWorldGeometry.cardHeight}
                          rx={tooltipWorldGeometry.cornerRadius}
                          ry={tooltipWorldGeometry.cornerRadius}
                          fill="rgba(255,255,255,0.985)"
                          stroke="rgba(15, 23, 42, 0.16)"
                          strokeWidth={Math.max(0.7, tooltipWorldGeometry.calloutStroke * 0.62)}
                        />
                        <text
                          x={tooltipWorldGeometry.cardX + tooltipWorldGeometry.paddingX}
                          y={tooltipWorldGeometry.cardY + tooltipWorldGeometry.headerY}
                          fill="#64748b"
                          fontSize={tooltipWorldGeometry.headerFontSize}
                          fontWeight="800"
                          style={{ letterSpacing: `${tooltipWorldGeometry.headerLetterSpacing}px`, textTransform: "uppercase" }}
                        >
                          {tooltipStationMode ? `Field inspection • ${tooltipStationMode}` : "Field inspection"}
                        </text>
                        <text
                          x={tooltipWorldGeometry.cardX + tooltipWorldGeometry.paddingX}
                          y={tooltipWorldGeometry.cardY + tooltipWorldGeometry.stationYText}
                          fill="#0f172a"
                          fontSize={tooltipWorldGeometry.stationFontSize}
                          fontWeight="900"
                        >
                          {cleanDisplayText(tooltipStation.station)}
                        </text>

                        {[
                          ["Station", cleanDisplayText(tooltipStation.station)],
                          ["Mapped FT", formatNumber(tooltipStation.mapped_station_ft, 3)],
                          ["Depth FT", formatNumber(tooltipStation.depth_ft)],
                          ["BOC FT", formatNumber(tooltipStation.boc_ft)],
                          ["Date", formatDisplayDate(tooltipStation.date)],
                          ["Crew", cleanDisplayText(tooltipStation.crew)],
                          ["Print", cleanDisplayText(tooltipStation.print)],
                          ["Source", cleanDisplayText(tooltipStation.source_file)],
                          ["Notes", cleanDisplayText(tooltipStation.notes)],
                          ["Lat / Lon", `${formatNumber(tooltipStation.lat, 8)}, ${formatNumber(tooltipStation.lon, 8)}`],
                        ].map(([label, value], rowIdx) => {
                          const rowY = tooltipWorldGeometry.cardY + tooltipWorldGeometry.rowsStartY + rowIdx * tooltipWorldGeometry.rowGap;
                          return (
                            <g key={`${label}-${rowIdx}`}>
                              <text
                                x={tooltipWorldGeometry.cardX + tooltipWorldGeometry.paddingX}
                                y={rowY}
                                fill="#64748b"
                                fontSize={tooltipWorldGeometry.rowLabelFontSize}
                                fontWeight="800"
                              >
                                {label}
                              </text>
                              <text
                                x={tooltipWorldGeometry.cardX + tooltipWorldGeometry.valueX}
                                y={rowY}
                                fill="#0f172a"
                                fontSize={tooltipWorldGeometry.rowFontSize}
                                fontWeight="600"
                              >
                                {String(value)}
                              </text>
                            </g>
                          );
                        })}
                      </g>
                    ) : null}
                  </svg>
                ) : (
                  <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", textAlign: "center", padding: 24, color: "#cbd5e1", fontWeight: 700 }}>
                    Upload a KMZ and structured bore logs to render real map output.
                  </div>
                )}

                {boxZoom ? (
                  <div
                    style={{
                      position: "absolute",
                      left: Math.min(boxZoom.startX, boxZoom.endX),
                      top: Math.min(boxZoom.startY, boxZoom.endY),
                      width: Math.abs(boxZoom.endX - boxZoom.startX),
                      height: Math.abs(boxZoom.endY - boxZoom.startY),
                      background: "rgba(56,189,248,0.12)",
                      border: "2px dashed #38bdf8",
                      pointerEvents: "none",
                      boxSizing: "border-box",
                    }}
                  />
                ) : null}

                {/* ─── V1 Photo GPS Mapping — selected-photo preview popup ──── */}
                {/* HTML overlay (not SVG) so we can use a native <img> tag for   */}
                {/* JPEG/PNG thumbnails. Anchored to the marker's on-screen       */}
                {/* pixel position computed from current viewport + projection.   */}
                {(() => {
                  if (!selectedGpsPhotoId) return null;
                  if (!projectionMetrics) return null;
                  const hit = projectedPhotos.find(({ photo }) => photo.id === selectedGpsPhotoId);
                  if (!hit) return null;
                  const { photo, world } = hit;

                  // World → screen pixel conversion, mirroring the viewBox in
                  // viewBoxToString(). The SVG fills the container 100x100%, so
                  // we can derive pixel coords without querying the DOM.
                  const vbWidth = projectionMetrics.worldWidth / viewport.zoom;
                  const vbHeight = projectionMetrics.worldHeight / viewport.zoom;
                  const vbX = -viewport.panX / viewport.zoom;
                  const vbY = -viewport.panY / viewport.zoom;
                  const screenX = ((world.x - vbX) / vbWidth) * containerSize.width;
                  const screenY = ((world.y - vbY) / vbHeight) * containerSize.height;

                  // Card dimensions. We pick a side (right of marker by
                  // default, left if too close to the right edge) and a
                  // vertical anchor (above if enough room, else below).
                  const cardWidth = 260;
                  const cardHeightEstimate = 260;
                  const margin = 12;
                  const placeRight = screenX + margin + cardWidth < containerSize.width;
                  const cardLeft = placeRight
                    ? Math.min(screenX + margin, containerSize.width - cardWidth - 4)
                    : Math.max(screenX - cardWidth - margin, 4);
                  const cardTop = Math.max(
                    4,
                    Math.min(
                      screenY - cardHeightEstimate / 2,
                      containerSize.height - cardHeightEstimate - 4
                    )
                  );

                  const isHeic = /heic|heif/i.test(photo.contentType) || /\.heic$|\.heif$/i.test(photo.filename);
                  const latText = typeof photo.lat === "number" ? photo.lat.toFixed(6) : "--";
                  const lonText = typeof photo.lon === "number" ? photo.lon.toFixed(6) : "--";

                  return (
                    <div
                      style={{
                        position: "absolute",
                        left: cardLeft,
                        top: cardTop,
                        width: cardWidth,
                        background: "rgba(10, 18, 30, 0.78)",
                        backdropFilter: "blur(14px) saturate(140%)",
                        WebkitBackdropFilter: "blur(14px) saturate(140%)",
                        border: "1px solid rgba(255, 255, 255, 0.16)",
                        borderRadius: 14,
                        boxShadow: "0 20px 45px rgba(0,0,0,0.55), 0 0 0 1px rgba(56, 189, 248, 0.08) inset",
                        overflow: "hidden",
                        zIndex: 900,
                      }}
                      onPointerDown={(e) => e.stopPropagation()}
                      onWheel={(e) => e.stopPropagation()}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          padding: "8px 10px 6px 12px",
                          borderBottom: "1px solid rgba(255,255,255,0.08)",
                          background: "rgba(255,255,255,0.03)",
                        }}
                      >
                        <div style={{ fontSize: 11, fontWeight: 800, color: "#fbbf24", letterSpacing: 0.4 }}>
                          GEOTAGGED PHOTO
                        </div>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedGpsPhotoId(null);
                          }}
                          aria-label="Close photo preview"
                          style={{
                            border: "none",
                            background: "transparent",
                            cursor: "pointer",
                            color: "#cbd5e1",
                            fontSize: 18,
                            lineHeight: 1,
                            padding: "2px 6px",
                            borderRadius: 6,
                          }}
                        >
                          ×
                        </button>
                      </div>
                      <div
                        style={{
                          height: 150,
                          background: "rgba(0,0,0,0.35)",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          color: "#cbd5e1",
                          fontSize: 12,
                          fontWeight: 600,
                          padding: 8,
                          textAlign: "center",
                        }}
                      >
                        {isHeic ? (
                          "HEIC file — download to view"
                        ) : (
                          // Plain <img> intentional: blob URL, no Next Image optimization.
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={photo.previewUrl}
                            alt={photo.filename}
                            loading="lazy"
                            style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
                          />
                        )}
                      </div>
                      <div style={{ padding: "10px 12px 12px" }}>
                        <div style={{ fontSize: 13, fontWeight: 700, color: "#f1f5f9", wordBreak: "break-word" }}>
                          {photo.filename}
                        </div>
                        <div
                          style={{
                            marginTop: 6,
                            fontSize: 11,
                            color: "#94a3b8",
                            fontFamily: "ui-monospace, SFMono-Regular, monospace",
                          }}
                        >
                          {latText}, {lonText}
                        </div>
                        <a
                          href={photo.previewUrl}
                          download={photo.filename}
                          onClick={(e) => e.stopPropagation()}
                          style={{
                            display: "inline-block",
                            marginTop: 10,
                            fontSize: 12,
                            fontWeight: 700,
                            color: "#0f172a",
                            background: "#fbbf24",
                            textDecoration: "none",
                            padding: "6px 10px",
                            border: "1px solid rgba(251, 191, 36, 0.6)",
                            borderRadius: 8,
                          }}
                        >
                          Download original
                        </a>
                      </div>
                    </div>
                  );
                })()}

                              </div>

              <div
                style={{
                  border: "1px solid #dbe4ee",
                  borderRadius: 16,
                  background: "#ffffff",
                  padding: 16,
                  display: "grid",
                  gap: 14,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start", flexWrap: "wrap" }}>
                  <div>
                    <div style={{ fontSize: 15, fontWeight: 800, color: "#0f172a" }}>Station photos</div>
                    <div style={{ marginTop: 6, fontSize: 13, color: "#64748b", lineHeight: 1.55 }}>
                      Manual attach only. Select a station first, then upload one or more photos to that exact station.
                    </div>
                  </div>
                  <div style={{ fontSize: 12, color: "#475569", fontWeight: 700 }}>
                    {selectedStation ? selectedStationSummary : "No station selected"}
                  </div>
                </div>

                {selectedStation ? (
                  <div style={{ display: "grid", gap: 12 }}>
                    <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
                      <label
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          justifyContent: "center",
                          padding: "10px 14px",
                          borderRadius: 12,
                          border: "1px solid #0f172a",
                          background: stationPhotoBusy ? "#e5e7eb" : "#0f172a",
                          color: "#ffffff",
                          fontWeight: 800,
                          cursor: stationPhotoBusy ? "not-allowed" : "pointer",
                          opacity: stationPhotoBusy ? 0.7 : 1,
                        }}
                      >
                        <input
                          type="file"
                          accept="image/*"
                          multiple
                          style={{ display: "none" }}
                          disabled={stationPhotoBusy}
                          onChange={(e) => {
                            handleStationPhotoUpload(e.target.files);
                            e.currentTarget.value = "";
                          }}
                        />
                        {stationPhotoBusy ? "Uploading..." : "Upload Station Photos"}
                      </label>

                      <div style={{ fontSize: 12, color: "#64748b" }}>
                        Stable station key: <strong>{selectedStationIdentity || "--"}</strong>
                      </div>
                    </div>

                    {stationPhotosLoading ? (
                      <div style={{ fontSize: 13, color: "#64748b" }}>Loading station photos...</div>
                    ) : stationPhotos.length ? (
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 12 }}>
                        {stationPhotos.map((photo) => (
                          <a
                            key={photo.photo_id}
                            href={`${API_BASE}${photo.relative_url}`}
                            target="_blank"
                            rel="noreferrer"
                            style={{
                              textDecoration: "none",
                              color: "inherit",
                              border: "1px solid #dbe4ee",
                              borderRadius: 14,
                              overflow: "hidden",
                              background: "#fbfdff",
                            }}
                          >
                            <div
                              style={{
                                height: 112,
                                backgroundImage: `url(${API_BASE}${photo.relative_url})`,
                                backgroundSize: "cover",
                                backgroundPosition: "center",
                                backgroundRepeat: "no-repeat",
                                backgroundColor: "#e5e7eb",
                              }}
                            />
                            <div style={{ padding: 10 }}>
                              <div style={{ fontSize: 12, fontWeight: 700, color: "#0f172a", wordBreak: "break-word" }}>
                                {photo.original_filename}
                              </div>
                              <div style={{ marginTop: 4, fontSize: 11, color: "#64748b" }}>
                                {formatDisplayDate(photo.uploaded_at)}
                              </div>
                            </div>
                          </a>
                        ))}
                      </div>
                    ) : (
                      <div style={{ fontSize: 13, color: "#64748b" }}>
                        No photos attached to this station yet.
                      </div>
                    )}
                  </div>
                ) : (
                  <div style={{ fontSize: 13, color: "#64748b" }}>
                    Select a station on the map first. Photos only attach to the currently selected station.
                  </div>
                )}
              </div>

              {/* ─── V1 Photo GPS Mapping — Geotagged photos panel ─────────── */}
              {/* Client-only. Resets on refresh. Sibling of Station photos    */}
              {/* above; does not interact with it or with the backend.        */}
              <div
                style={{
                  border: "1px solid #dbe4ee",
                  borderRadius: 16,
                  background: "#ffffff",
                  padding: 16,
                  display: "grid",
                  gap: 14,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start", flexWrap: "wrap" }}>
                  <div>
                    <div style={{ fontSize: 15, fontWeight: 800, color: "#0f172a" }}>
                      Geotagged photos <span style={{ fontSize: 11, fontWeight: 700, color: "#b45309", marginLeft: 6, padding: "2px 6px", borderRadius: 6, background: "#fef3c7" }}>BETA</span>
                    </div>
                    <div style={{ marginTop: 6, fontSize: 13, color: "#64748b", lineHeight: 1.55 }}>
                      Upload customer photos. Photos with GPS metadata are placed on the map at their coordinates. Photos without GPS appear below in &quot;Unmapped Photos.&quot; Resets on page refresh.
                    </div>
                  </div>
                  <div style={{ fontSize: 12, color: "#475569", fontWeight: 700, textAlign: "right" }}>
                    {gpsPhotos.length > 0 ? (
                      <>
                        <div>{projectedPhotos.length} on map</div>
                        <div style={{ marginTop: 2, color: "#64748b" }}>{gpsPhotos.length - projectedPhotos.length} unmapped</div>
                      </>
                    ) : (
                      <div style={{ color: "#94a3b8", fontWeight: 600 }}>No photos yet</div>
                    )}
                  </div>
                </div>

                <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
                  <label
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      padding: "10px 14px",
                      borderRadius: 12,
                      border: "1px solid #0f172a",
                      background: gpsPhotoBusy ? "#e5e7eb" : "#0f172a",
                      color: "#ffffff",
                      fontWeight: 800,
                      cursor: gpsPhotoBusy ? "not-allowed" : "pointer",
                      opacity: gpsPhotoBusy ? 0.7 : 1,
                    }}
                  >
                    <input
                      type="file"
                      accept="image/*,.heic,.heif"
                      multiple
                      style={{ display: "none" }}
                      disabled={gpsPhotoBusy}
                      onChange={(e) => {
                        handleGpsPhotoUpload(e.target.files);
                        e.currentTarget.value = "";
                      }}
                    />
                    {gpsPhotoBusy ? "Reading GPS..." : "Upload Geotagged Photos"}
                  </label>

                  {gpsPhotos.length > 0 ? (
                    <button
                      type="button"
                      onClick={clearGpsPhotos}
                      disabled={gpsPhotoBusy}
                      style={{
                        padding: "10px 14px",
                        borderRadius: 12,
                        border: "1px solid #dbe4ee",
                        background: "#ffffff",
                        color: "#475569",
                        fontWeight: 700,
                        fontSize: 13,
                        cursor: gpsPhotoBusy ? "not-allowed" : "pointer",
                      }}
                    >
                      Clear all
                    </button>
                  ) : null}

                  <div style={{ fontSize: 12, color: "#64748b" }}>
                    Accepts JPEG, PNG, HEIC. GPS read client-side (no upload).
                  </div>
                </div>

                {/* Unmapped Photos list: anything in gpsPhotos that did NOT make it
                    into projectedPhotos. Reasons:
                      - no_gps: EXIF had no usable GPS tags
                      - unreadable: exifr threw while parsing
                      - has GPS but outside current KMZ design bounds (or KMZ not loaded yet) */}
                {(() => {
                  const mappedIds = new Set(projectedPhotos.map((p) => p.photo.id));
                  const unmapped = gpsPhotos.filter((p) => !mappedIds.has(p.id));
                  if (unmapped.length === 0) {
                    return gpsPhotos.length > 0 ? (
                      <div style={{ fontSize: 13, color: "#64748b" }}>
                        All uploaded photos have valid GPS and are placed on the map.
                      </div>
                    ) : null;
                  }
                  return (
                    <div style={{ display: "grid", gap: 8 }}>
                      <div style={{ fontSize: 13, fontWeight: 800, color: "#0f172a" }}>
                        Unmapped Photos ({unmapped.length})
                      </div>
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 12 }}>
                        {unmapped.map((photo) => {
                          const hasGps = photo.reason === "mapped" && typeof photo.lat === "number" && typeof photo.lon === "number";
                          const noteText = hasGps
                            ? "GPS present but outside design area"
                            : photo.reason === "unreadable"
                            ? "Could not read photo metadata"
                            : "No GPS metadata";
                          const isHeic = /heic|heif/i.test(photo.contentType) || /\.heic$|\.heif$/i.test(photo.filename);
                          return (
                            <div
                              key={photo.id}
                              style={{
                                border: "1px solid #dbe4ee",
                                borderRadius: 14,
                                overflow: "hidden",
                                background: "#fbfdff",
                              }}
                            >
                              <div
                                style={{
                                  height: 112,
                                  backgroundImage: isHeic ? undefined : `url(${photo.previewUrl})`,
                                  backgroundSize: "cover",
                                  backgroundPosition: "center",
                                  backgroundRepeat: "no-repeat",
                                  backgroundColor: "#e5e7eb",
                                  display: "flex",
                                  alignItems: "center",
                                  justifyContent: "center",
                                  color: "#64748b",
                                  fontSize: 11,
                                  fontWeight: 700,
                                  textAlign: "center",
                                  padding: 8,
                                }}
                              >
                                {isHeic ? "HEIC — download to view" : null}
                              </div>
                              <div style={{ padding: 10 }}>
                                <div style={{ fontSize: 12, fontWeight: 700, color: "#0f172a", wordBreak: "break-word" }}>
                                  {photo.filename}
                                </div>
                                <div style={{ marginTop: 4, fontSize: 11, color: "#b45309", fontWeight: 600 }}>
                                  {noteText}
                                </div>
                                {hasGps ? (
                                  <div style={{ marginTop: 2, fontSize: 10, color: "#64748b", fontFamily: "ui-monospace, SFMono-Regular, monospace" }}>
                                    {photo.lat?.toFixed(5)}, {photo.lon?.toFixed(5)}
                                  </div>
                                ) : null}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  );
                })()}
              </div>

            </div>
          </Section>

          <div style={{ display: "grid", gridTemplateColumns: "1.1fr 0.9fr", gap: 18, alignItems: "start" }}>
            
<Section title="4. Reports" subtitle="Real report output built from current job data, redline sections, pricing inputs, and exception totals.">
              <div className="print-report" style={{ display: "grid", gap: 14 }}>
                <ShellCard
                  title="Field-to-billing report"
                  description="This report uses current route, redline, completion, pricing, and exception values only. Browser print is enabled for clean export."
                >
                  <div style={{ display: "grid", gap: 8 }}>
                    <SmallRow label="Job / Route" value={activeJob} />
                    <SmallRow label="Matched route" value={selectedMatch?.route_name || state?.selected_route_name || state?.route_name || "--"} />
                    <SmallRow label="Total footage" value={`${formatNumber(effectiveFootage)} ft`} />
                    <SmallRow label="Completion %" value={`${formatNumber(state?.completion_pct)}%`} />
                    <SmallRow label="Drill paths" value={String(drillPathRows.length)} />
                    <SmallRow label="Base cost / ft" value={toMoney(numericCostPerFoot)} />
                    <SmallRow label="Exception total" value={toMoney(exceptionTotal)} />
                    <SmallRow label="Final total" value={toMoney(finalBillingTotal)} />
                  </div>
                </ShellCard>

                <ShellCard
                  title="Drill Path Summary"
                  description="Each row collapses adjacent redline segments into one continuous drilled path using the existing redline report data only."
                >
                  {drillPathRows.length ? (
                    <div style={{ overflowX: "auto" }}>
                      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                        <thead>
                          <tr>
                            <th style={{ textAlign: "left", padding: "10px 8px", borderBottom: "1px solid #dbe4ee" }}>Start</th>
                            <th style={{ textAlign: "left", padding: "10px 8px", borderBottom: "1px solid #dbe4ee" }}>End</th>
                            <th style={{ textAlign: "left", padding: "10px 8px", borderBottom: "1px solid #dbe4ee" }}>Length (FT)</th>
                            <th style={{ textAlign: "left", padding: "10px 8px", borderBottom: "1px solid #dbe4ee" }}>Cost</th>
                            <th style={{ textAlign: "left", padding: "10px 8px", borderBottom: "1px solid #dbe4ee" }}>Print</th>
                            <th style={{ textAlign: "left", padding: "10px 8px", borderBottom: "1px solid #dbe4ee" }}>Source</th>
                          </tr>
                        </thead>
                        <tbody>
                          {drillPathRows.map((row) => (
                            <tr key={row.id}>
                              <td style={{ padding: "10px 8px", borderBottom: "1px solid #eef2f7" }}>{row.startStation}</td>
                              <td style={{ padding: "10px 8px", borderBottom: "1px solid #eef2f7" }}>{row.endStation}</td>
                              <td style={{ padding: "10px 8px", borderBottom: "1px solid #eef2f7" }}>{formatNumber(row.lengthFt)}</td>
                              <td style={{ padding: "10px 8px", borderBottom: "1px solid #eef2f7" }}>{toMoney(row.cost)}</td>
                              <td style={{ padding: "10px 8px", borderBottom: "1px solid #eef2f7" }}>{row.print}</td>
                              <td style={{ padding: "10px 8px", borderBottom: "1px solid #eef2f7" }}>{row.sourceFile}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div style={{ fontSize: 13, color: "#64748b" }}>
                      No drill-path summary data is available yet. Upload data or enter manual footage for a billing estimate.
                    </div>
                  )}
                </ShellCard>
              </div>
            </Section>

            <div style={{ display: "grid", gap: 18 }}>
              <Section title="5. Pricing / Crews / Exceptions" subtitle="Real billing controls using actual footage plus editable exception costs.">
                <div style={{ display: "grid", gap: 14 }}>
                  <ShellCard
                    title="Footage calculator"
                    description="Uses summed redline segment lengths first, then covered_length_ft from the backend. Manual footage is optional when no backend value is available."
                  >
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 12 }}>
                      <label style={{ display: "grid", gap: 6, fontSize: 13, color: "#475569" }}>
                        <span>Detected footage (FT)</span>
                        <input value={formatNumber(calculatedCoveredFootage)} readOnly style={{ borderRadius: 12, border: "1px solid #cfd8e3", padding: "10px 12px", background: "#f8fafc", fontSize: 14 }} />
                      </label>
                      <label style={{ display: "grid", gap: 6, fontSize: 13, color: "#475569" }}>
                        <span>Manual footage override (FT)</span>
                        <input value={manualFootage} onChange={(e) => setManualFootage(e.target.value)} placeholder="Optional" style={{ borderRadius: 12, border: "1px solid #cfd8e3", padding: "10px 12px", background: "#ffffff", fontSize: 14 }} />
                      </label>
                      <label style={{ display: "grid", gap: 6, fontSize: 13, color: "#475569" }}>
                        <span>Cost per foot ($)</span>
                        <input value={costPerFoot} onChange={(e) => setCostPerFoot(e.target.value)} style={{ borderRadius: 12, border: "1px solid #cfd8e3", padding: "10px 12px", background: "#ffffff", fontSize: 14 }} />
                      </label>
                      <div style={{ display: "grid", gap: 6, fontSize: 13, color: "#475569" }}>
                        <span>Base total</span>
                        <div style={{ borderRadius: 12, border: "1px solid #cfd8e3", padding: "10px 12px", background: "#f8fafc", fontSize: 14, fontWeight: 800 }}>{toMoney(baseBillingTotal)}</div>
                      </div>
                    </div>
                  </ShellCard>

                  <ShellCard
                    title="Exceptions"
                    description="Add or remove manual cost rows for TXDOT, railroad, restoration, and other job-specific charges."
                  >
                    <div style={{ display: "grid", gap: 10 }}>
                      {exceptions.map((item) => (
                        <div key={item.id} style={{ display: "grid", gridTemplateColumns: "1.4fr 0.8fr auto", gap: 10, alignItems: "center" }}>
                          <input value={item.label} onChange={(e) => handleExceptionChange(item.id, "label", e.target.value)} style={{ borderRadius: 12, border: "1px solid #cfd8e3", padding: "10px 12px", background: "#ffffff", fontSize: 14 }} />
                          <input value={item.amount} onChange={(e) => handleExceptionChange(item.id, "amount", e.target.value)} placeholder="0.00" style={{ borderRadius: 12, border: "1px solid #cfd8e3", padding: "10px 12px", background: "#ffffff", fontSize: 14 }} />
                          <button onClick={() => handleRemoveException(item.id)} style={buttonStyle("#ffffff", "#0f172a", "#000000", false)}>Remove</button>
                        </div>
                      ))}
                      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 0.8fr auto", gap: 10, alignItems: "center" }}>
                        <input value={extraExceptionLabel} onChange={(e) => setExtraExceptionLabel(e.target.value)} placeholder="Add exception label" style={{ borderRadius: 12, border: "1px solid #cfd8e3", padding: "10px 12px", background: "#ffffff", fontSize: 14 }} />
                        <input value={extraExceptionAmount} onChange={(e) => setExtraExceptionAmount(e.target.value)} placeholder="0.00" style={{ borderRadius: 12, border: "1px solid #cfd8e3", padding: "10px 12px", background: "#ffffff", fontSize: 14 }} />
                        <button onClick={handleAddException} style={buttonStyle("#0f172a", "#ffffff", "#000000", false)}>Add</button>
                      </div>
                    </div>
                  </ShellCard>

                  <ShellCard
                    title="Billing summary"
                    description="Usable billing totals built from current footage, cost per foot, and exception totals."
                  >
                    <SmallRow label="Footage used" value={`${formatNumber(effectiveFootage)} ft`} />
                    <SmallRow label="Cost / foot" value={toMoney(numericCostPerFoot)} />
                    <SmallRow label="Base total" value={toMoney(baseBillingTotal)} />
                    <SmallRow label="Exception total" value={toMoney(exceptionTotal)} />
                    <SmallRow label="Final total" value={toMoney(finalBillingTotal)} />
                  </ShellCard>
                </div>
              </Section>

              <Section title="6. Export / Print" subtitle="Real print/export via browser print with a clean report layout.">
                <div style={{ display: "grid", gap: 14 }}>
                  <ShellCard
                    title="Print / export report"
                    description="Use browser print to create a clean printed report or Save as PDF from the browser print dialog."
                  >
                    <button onClick={handlePrintReport} className="no-print" style={{ ...buttonStyle("#0f172a", "#ffffff", "#000000", false), width: "100%" }}>
                      Print / Export Report
                    </button>
                  </ShellCard>
                  <ShellCard
                    title="Operator notes"
                    description="Use this to capture what looked right or wrong during beta testing. Existing note submission behavior remains intact."
                  >
                    <textarea
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      placeholder="Example: Route looked right but station spacing seemed compressed near sheet 14..."
                      style={{ width: "100%", minHeight: 140, borderRadius: 14, border: "1px solid #cfd8e3", padding: 12, outline: "none", resize: "vertical", fontSize: 14, background: "#ffffff" }}
                    />
                    <button
                      onClick={submitBugNote}
                      disabled={busy || !notes.trim()}
                      style={{ ...buttonStyle("#0f172a", "#ffffff", "#0f172a", busy || !notes.trim()), marginTop: 12, width: "100%" }}
                    >
                      Submit Operator Note
                    </button>
                  </ShellCard>
                </div>
              </Section>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function RedlineMap({ mode = "default" }: RedlineMapProps) {
  if (mode === "mobileWalk") {
    return <MobileWalkContainer />;
  }
  return <OfficeRedlineMapInner mode={mode} />;
}
