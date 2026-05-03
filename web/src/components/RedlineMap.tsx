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
  EngineeringPlan,
  BoreLogSummaryEntry,
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
import FieldSubmissionsInboxPanel from "@/components/office/FieldSubmissionsInboxPanel";
import SelectedSubmissionReviewPanel from "@/components/office/SelectedSubmissionReviewPanel";
import { getJobById } from "@/lib/api";
import type { JobDetail } from "@/lib/api";
import { clamp, formatNumber, cleanDisplayText, formatDisplayDate } from "@/lib/format/text";
import { toMoney } from "@/lib/format/money";
import { extractGps } from "@/lib/photos/exif";
import { appendSessionId, appendSessionIdToForm, getStoredSessionId, rememberSessionFromResponse } from "@/lib/session";
import type { PipelineDiagEntry, EngineeringPlanSignal, QaFlagItem } from "@/lib/types/nova";
import { buildNovaSummary } from "@/lib/nova/buildNovaSummary";
import CloseoutPacket from "@/components/CloseoutPacket";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/+$/, "") ||
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, "") ||
  "http://127.0.0.1:8000";

const CLEARED_ENGINEERING_PLANS_PREFIX = "osp_cleared_engineering_plans";

function clearedEngineeringPlansStorageKey(projectId: string | undefined, sessionId: string | null): string | null {
  if (!sessionId) return null;
  const scopedProjectId = projectId?.trim();
  return scopedProjectId
    ? `${CLEARED_ENGINEERING_PLANS_PREFIX}:${scopedProjectId}:${sessionId}`
    : `${CLEARED_ENGINEERING_PLANS_PREFIX}:${sessionId}`;
}

function readClearedEngineeringPlanIds(projectId?: string, sessionId = getStoredSessionId(projectId)): Set<string> {
  const key = clearedEngineeringPlansStorageKey(projectId, sessionId);
  if (!key || typeof window === "undefined") return new Set();
  try {
    const raw = window.localStorage.getItem(key);
    const parsed = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(parsed) ? parsed.filter((value): value is string => typeof value === "string") : []);
  } catch {
    return new Set();
  }
}

function rememberClearedEngineeringPlans(plans: EngineeringPlan[], projectId?: string, sessionId = getStoredSessionId(projectId)): void {
  const key = clearedEngineeringPlansStorageKey(projectId, sessionId);
  if (!key || typeof window === "undefined") return;
  const planIds = plans.map((plan) => plan.plan_id).filter((planId): planId is string => Boolean(planId));
  try {
    if (planIds.length > 0) {
      window.localStorage.setItem(key, JSON.stringify(planIds));
    } else {
      window.localStorage.removeItem(key);
    }
  } catch {
    // localStorage can be unavailable in restricted browser contexts.
  }
}

function withoutClearedEngineeringPlans(data: BackendState, projectId?: string, sessionId = getStoredSessionId(projectId)): BackendState {
  const clearedPlanIds = readClearedEngineeringPlanIds(projectId, sessionId);
  if (clearedPlanIds.size === 0 || !Array.isArray(data.engineering_plans)) return data;

  const engineeringPlans = data.engineering_plans.filter((plan) => !clearedPlanIds.has(plan.plan_id));
  return engineeringPlans.length === data.engineering_plans.length ? data : { ...data, engineering_plans: engineeringPlans };
}

function withoutClearedEngineeringPlanSignals(signals: EngineeringPlanSignal[], projectId?: string, sessionId = getStoredSessionId(projectId)): EngineeringPlanSignal[] {
  const clearedPlanIds = readClearedEngineeringPlanIds(projectId, sessionId);
  if (clearedPlanIds.size === 0) return signals;
  return signals.filter((signal) => !signal.plan_id || !clearedPlanIds.has(signal.plan_id));
}

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

/** KMZ line vertex pairs are [lat, lon] (same convention as projectWorldPoint). */
function kmzLineFeaturesToPolylines(features: Array<{ coords: number[][] }>): number[][][] {
  const out: number[][][] = [];
  for (const f of features) {
    const c = cleanCoords(f.coords);
    if (c.length >= 2) out.push(c);
  }
  return out;
}

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

/** Nearest point on KMZ design polylines — visual-only; does not mutate stored GPS. */
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

function normalizeSourceFileKey(value: unknown): string {
  return String(value ?? "")
    .trim()
    .replace(/\\/g, "/")
    .split("/")
    .pop()
    ?.toLowerCase() ?? "";
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

function escapeXml(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function kmlCoordinateFromLatLon(lat: unknown, lon: unknown): string | null {
  if (typeof lat !== "number" || typeof lon !== "number") return null;
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;
  return `${lon.toFixed(8)},${lat.toFixed(8)},0`;
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

function worldPointToLatLon(
  world: ScreenPoint,
  bounds: Bounds,
  metrics: ProjectionMetrics
): { lat: number; lon: number } {
  const xRatio = clamp((world.x - metrics.offsetX) / Math.max(metrics.contentWidth, 0.000001), 0, 1);
  const yRatio = clamp((world.y - metrics.offsetY) / Math.max(metrics.contentHeight, 0.000001), 0, 1);
  return {
    lat: bounds.maxLat - yRatio * (bounds.maxLat - bounds.minLat),
    lon: bounds.minLon + xRatio * (bounds.maxLon - bounds.minLon),
  };
}


function kmzLineStroke(feature: KmzLineFeature): string {
  return (
    feature.stroke ||
    feature.color ||
    (feature.role === "backbone"
      ? "rgba(59, 130, 246, 0.78)"
      : feature.role === "terminal_tail"
      ? "rgba(251, 191, 36, 0.16)"
      : "rgba(96, 165, 250, 0.66)")
  );
}

function kmzLineWidth(feature: KmzLineFeature): number {
  const raw = feature.stroke_width ?? feature.width;
  if (typeof raw === "number" && Number.isFinite(raw)) {
    return clamp(raw * 0.62, 0.74, 2.18);
  }
  return feature.role === "backbone" ? 1.38 : 0.78;
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

/** Render-only: simplify KMZ clutter for demos; does not mutate data. */
function presentationKmzPaint(
  feature: KmzLineFeature,
  presentationView: boolean
): { omit: boolean; casingOpacity: number; lineOpacity: number } {
  if (!presentationView) {
    return { omit: false, casingOpacity: 1, lineOpacity: 0.94 };
  }
  const role = feature.role;
  if (role === "backbone" || role === "underground_cable") {
    return { omit: false, casingOpacity: 1, lineOpacity: 0.94 };
  }
  return { omit: true, casingOpacity: 0, lineOpacity: 0 };
}

// ─── Evidence-layer color assignment ───────────────────────────────────────
// Deterministic: same evidence_layer_id always maps to the same color.
// Colors are chosen for high contrast on the dark map background.
const EVIDENCE_LAYER_PALETTE = [
  "rgba(248, 52, 62, 1)",   // red — cleaner, less muddy on dark base
  "rgba(248, 52, 62, 1)",
  "rgba(248, 52, 62, 1)",
  "rgba(248, 52, 62, 1)",
  "rgba(248, 52, 62, 1)",
  "rgba(248, 52, 62, 1)",
  "rgba(248, 52, 62, 1)",
  "rgba(248, 52, 62, 1)",
];

const EVIDENCE_LAYER_CASING_PALETTE = [
  "rgba(22, 10, 12, 0.42)", // subtler dark casing
  "rgba(22, 10, 12, 0.42)",
  "rgba(22, 10, 12, 0.42)",
  "rgba(22, 10, 12, 0.42)",
  "rgba(22, 10, 12, 0.42)",
  "rgba(22, 10, 12, 0.42)",
  "rgba(22, 10, 12, 0.42)",
  "rgba(22, 10, 12, 0.42)",
];

function layerPaletteIndex(layerId: string | undefined | null): number {
  if (!layerId) return 0;
  // Simple djb2-style hash over the layer id characters.
  let h = 5381;
  for (let i = 0; i < layerId.length; i++) {
    h = ((h << 5) + h) ^ layerId.charCodeAt(i);
    h = h >>> 0; // keep unsigned 32-bit
  }
  return h % EVIDENCE_LAYER_PALETTE.length;
}

function getColorForLayer(layerId: string | undefined | null): string {
  return EVIDENCE_LAYER_PALETTE[layerPaletteIndex(layerId)];
}

function getCasingForLayer(layerId: string | undefined | null): string {
  return EVIDENCE_LAYER_CASING_PALETTE[layerPaletteIndex(layerId)];
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

function Section({
  title,
  subtitle,
  children,
  actions,
  style,
  headerStyle,
  contentStyle,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
  style?: React.CSSProperties;
  headerStyle?: React.CSSProperties;
  contentStyle?: React.CSSProperties;
}) {
  return (
    <div
      style={{
        background: "#fff",
        border: "1px solid #dbe4ee",
        borderRadius: 20,
        overflow: "hidden",
        boxShadow: "0 10px 24px rgba(15, 23, 42, 0.04)",
        ...style,
      }}
    >
      <div style={{ padding: 18, borderBottom: "1px solid #e8eef5", display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, flexWrap: "wrap", ...headerStyle }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 800, color: "#0f172a" }}>{title}</div>
          {subtitle ? <div style={{ marginTop: 6, fontSize: 13, color: "#64748b", maxWidth: 900 }}>{subtitle}</div> : null}
        </div>
        {actions ? <div>{actions}</div> : null}
      </div>
      <div style={{ padding: 18, ...contentStyle }}>{children}</div>
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
  borderRadius: 999,
  padding: "0 12px",
  borderWidth: 1,
  borderStyle: "solid",
  borderColor: "rgba(148, 163, 184, 0.28)",
  background: "rgba(2, 6, 23, 0.72)",
  color: "#e2e8f0",
  fontWeight: 800,
  cursor: "pointer",
  boxShadow: "0 10px 28px rgba(0,0,0,0.38), inset 0 1px 0 rgba(255,255,255,0.08)",
  backdropFilter: "blur(14px) saturate(135%)",
  WebkitBackdropFilter: "blur(14px) saturate(135%)",
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
  projectId?: string;
  /** When set (e.g. project route), replaces the generic operator workspace title. */
  workspaceTitle?: string;
};

type WorkspaceTab = "setup" | "map" | "reports" | "billing";

type BillingApprovalStatus = "not_submitted" | "pending" | "approved";

const WORKSPACE_TABS: Array<{ id: WorkspaceTab; label: string }> = [
  { id: "setup", label: "Setup" },
  { id: "map", label: "Map" },
  { id: "reports", label: "Reports" },
  { id: "billing", label: "Billing / Export" },
];

type NovaIssueFocusPayload = {
  issueId: string;
  source_file: string;
  group_idx: number | null;
  issue_key: string;
  severity: QaFlagItem["severity"];
  raw_reasons?: string[];
  item: QaFlagItem;
};

type FocusedNovaIssue = {
  sourceFile: string;
  sourceKey: string;
  layerId: string | null;
  issueKey: string;
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
  displayLat?: number;
  displayLon?: number;
  displayAdjustedAt?: number;
  reason: "mapped" | "no_gps" | "unreadable";
  addedAt: number; // Date.now()
};

function OfficeRedlineMapInner({ mode = "default", projectId, workspaceTitle }: RedlineMapProps) {
  const [activeWorkspaceTab, setActiveWorkspaceTab] = useState<WorkspaceTab>("setup");
  const [state, setState] = useState<BackendState | null>(null);
  const [busy, setBusy] = useState(false);
  const [statusTone, setStatusTone] = useState<NoteTone>("neutral");
  const [statusText, setStatusText] = useState("Connecting to local beta backend...");
  const [jobLabel, setJobLabel] = useState("");
  const [notes, setNotes] = useState("");
  const [manualProjectPlannedFootage, setManualProjectPlannedFootage] = useState("");
  const [costPerFoot, setCostPerFoot] = useState("5.00");
  const [manualFootage, setManualFootage] = useState("");
  const [exceptions, setExceptions] = useState<ExceptionCost[]>([
    { id: "txdot", label: "TXDOT", amount: "" },
    { id: "railroad", label: "Railroad", amount: "" },
    { id: "restoration", label: "Restoration", amount: "" },
  ]);
  const [extraExceptionLabel, setExtraExceptionLabel] = useState("");
  const [extraExceptionAmount, setExtraExceptionAmount] = useState("");
  const [extraExceptionNote, setExtraExceptionNote] = useState("");
  const [billingApprovalStatus, setBillingApprovalStatus] = useState<BillingApprovalStatus>("not_submitted");
  // Nova Phase 1 — read-only job intelligence state. Never mutates other state.
  const [pipelineDiag, setPipelineDiag] = useState<PipelineDiagEntry[]>([]);
  const [engineeringPlanSignals, setEngineeringPlanSignals] = useState<EngineeringPlanSignal[]>([]);
  const [stationPhotos, setStationPhotos] = useState<StationPhoto[]>([]);
  const [stationPhotosLoading, setStationPhotosLoading] = useState(false);
  const [stationPhotoBusy, setStationPhotoBusy] = useState(false);
  const [engPlansBusy, setEngPlansBusy] = useState(false);
  // V1 Photo GPS Mapping — client-only, resets on refresh.
  const [gpsPhotos, setGpsPhotos] = useState<GpsPhoto[]>([]);
  const [gpsPhotoBusy, setGpsPhotoBusy] = useState(false);
  const [selectedGpsPhotoId, setSelectedGpsPhotoId] = useState<string | null>(null);
  const [hoverGpsPhotoId, setHoverGpsPhotoId] = useState<string | null>(null);
  const [gpsPhotoDrag, setGpsPhotoDrag] = useState<{
    id: string;
    offsetWorldX: number;
    offsetWorldY: number;
  } | null>(null);
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
  const [showPlannedRouteHighlight, setShowPlannedRouteHighlight] = useState(false);
  const [presentationView, setPresentationView] = useState(false);
  // Evidence-layer visibility: Set of hidden layer ids. Empty = all visible.
  const [hiddenLayers, setHiddenLayers] = useState<Set<string>>(new Set());
  const [focusedNovaIssue, setFocusedNovaIssue] = useState<FocusedNovaIssue | null>(null);
  const [novaOverrideSourceKeys, setNovaOverrideSourceKeys] = useState<Set<string>>(new Set());
  const userHasAdjustedViewportRef = useRef(false);
  const plannedFootageRestoringRef = useRef(false);
  const lastAutoFitSignatureRef = useRef<string>("");
  const initialFitRafRef = useRef<number | null>(null);
  const initialFitTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const focusedNovaIssueTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const focusStatusTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [selectedFieldSessionId, setSelectedFieldSessionId] = useState<string | null>(null);
  const [selectedFieldJobId, setSelectedFieldJobId] = useState<string | null>(null);
  const [selectedFieldJobDetail, setSelectedFieldJobDetail] = useState<JobDetail | null>(null);
  const [selectedFieldJobLoading, setSelectedFieldJobLoading] = useState(false);
  const [selectedFieldJobError, setSelectedFieldJobError] = useState<string | null>(null);

  const selectedFieldSession = useMemo(() => {
    if (!selectedFieldSessionId || !selectedFieldJobDetail) return null;
    return (
      (selectedFieldJobDetail.sessions ?? []).find((s) => s.id === selectedFieldSessionId) ??
      null
    );
  }, [selectedFieldSessionId, selectedFieldJobDetail]);

  const clearFieldSubmissionSelection = useCallback(() => {
    setSelectedFieldSessionId(null);
    setSelectedFieldJobId(null);
    setSelectedFieldJobDetail(null);
    setSelectedFieldJobError(null);
    setSelectedFieldJobLoading(false);
  }, []);

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

  const projectPlannedFootageStorageKey = useMemo(() => {
    const rawKey = activeJob && activeJob !== "--" ? activeJob : "default";
    const safeKey = rawKey
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9._-]+/g, "-")
      .replace(/^-+|-+$/g, "") || "default";
    return projectId
      ? `osp_project_planned_footage:${projectId}:${safeKey}`
      : `osp_project_planned_footage:${safeKey}`;
  }, [activeJob, projectId]);

  useEffect(() => {
    try {
      plannedFootageRestoringRef.current = true;
      setManualProjectPlannedFootage(window.localStorage.getItem(projectPlannedFootageStorageKey) ?? "");
    } catch {
      plannedFootageRestoringRef.current = false;
    }
  }, [projectPlannedFootageStorageKey]);

  useEffect(() => {
    if (plannedFootageRestoringRef.current) {
      plannedFootageRestoringRef.current = false;
      return;
    }
    try {
      const value = manualProjectPlannedFootage.trim();
      if (value) {
        window.localStorage.setItem(projectPlannedFootageStorageKey, value);
      } else {
        window.localStorage.removeItem(projectPlannedFootageStorageKey);
      }
    } catch {
      // localStorage can be unavailable in restricted browser contexts.
    }
  }, [manualProjectPlannedFootage, projectPlannedFootageStorageKey]);

  useEffect(() => {
    if (!selectedFieldJobId) {
      setSelectedFieldJobDetail(null);
      setSelectedFieldJobError(null);
      setSelectedFieldJobLoading(false);
      return;
    }
    let cancelled = false;
    setSelectedFieldJobLoading(true);
    setSelectedFieldJobError(null);
    void getJobById(selectedFieldJobId, projectId)
      .then((detail) => {
        if (!cancelled) setSelectedFieldJobDetail(detail);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setSelectedFieldJobDetail(null);
          setSelectedFieldJobError(
            err instanceof Error ? err.message : "Failed to load job",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setSelectedFieldJobLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedFieldJobId, projectId]);

  const kmzLineFeatures = useMemo(
    () =>
      (state?.kmz_reference?.line_features || [])
        .map((f) => ({ ...f, coords: cleanCoords(f.coords) }))
        .filter((f) => f.coords.length > 1),
    [state]
  );

  const kmzSnapPolylines = useMemo(
    () => kmzLineFeaturesToPolylines(kmzLineFeatures),
    [kmzLineFeatures],
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
    [kmzLineFeatures, renderBounds, projectionMetrics]
  );

  const kmzPolygonPaths = useMemo(
    () =>
      kmzPolygonFeatures.map((feature) => ({
        id: feature.feature_id || `${feature.name || "polygon"}-${Math.random()}`,
        path: buildWorldPath([...(feature.coords || []), (feature.coords || [])[0]], renderBounds, projectionMetrics),
      })),
    [kmzPolygonFeatures, renderBounds, projectionMetrics]
  );

  const redlinePaths = useMemo(
    () =>
      redlineSegments.map((segment) => ({
        id: segment.segment_id || `${segment.start_station || "start"}-${segment.end_station || "end"}`,
        path: buildWorldPath(cleanCoords(segment.coords), renderBounds, projectionMetrics),
        evidenceLayerId: (segment as { evidence_layer_id?: string }).evidence_layer_id ?? null,
        sourceFile: segment.source_file ?? "",
        sourceKey: normalizeSourceFileKey(segment.source_file),
      })),
    [redlineSegments, renderBounds, projectionMetrics]
  );

  // Derive source_file → evidence_layer_id from bore_log_summary so stations
  // can be filtered by the same layer-visibility state as redline segments.
  const sourceFileToLayerId = useMemo(() => {
    const map = new Map<string, string>();
    for (const entry of state?.bore_log_summary ?? []) {
      if (entry.source_file && entry.evidence_layer_id) {
        map.set(entry.source_file, entry.evidence_layer_id);
      }
    }
    return map;
  }, [state?.bore_log_summary]);

  const sourceKeyToLayerId = useMemo(() => {
    const map = new Map<string, string>();
    for (const entry of state?.bore_log_summary ?? []) {
      const key = normalizeSourceFileKey(entry.source_file);
      if (key && entry.evidence_layer_id) {
        map.set(key, entry.evidence_layer_id);
      }
    }
    return map;
  }, [state?.bore_log_summary]);

  const projectedStations = useMemo(() => {
    if (!renderBounds || !projectionMetrics) return [] as Array<{ idx: number; point: StationPoint; world: ScreenPoint }>;
    return stationPoints
      .map((point, idx) => {
        if (typeof point.lat !== "number" || typeof point.lon !== "number") return null;
        // Hide station when its evidence layer is toggled off.
        const layerId = sourceFileToLayerId.get(String(point.source_file ?? "").trim());
        if (layerId && hiddenLayers.has(layerId)) return null;
        const snapped = snapLatLonToKmzPolylines(point.lat, point.lon, kmzSnapPolylines);
        return {
          idx,
          point,
          world: projectWorldPoint(snapped.lat, snapped.lon, renderBounds, projectionMetrics),
        };
      })
      .filter((item): item is { idx: number; point: StationPoint; world: ScreenPoint } => Boolean(item));
  }, [stationPoints, renderBounds, projectionMetrics, sourceFileToLayerId, hiddenLayers, kmzSnapPolylines]);

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
        const markerLat = typeof photo.displayLat === "number" ? photo.displayLat : photo.lat;
        const markerLon = typeof photo.displayLon === "number" ? photo.displayLon : photo.lon;
        if (
          markerLat < renderBounds.minLat ||
          markerLat > renderBounds.maxLat ||
          markerLon < renderBounds.minLon ||
          markerLon > renderBounds.maxLon
        ) {
          return null;
        }
        return {
          photo,
          world: projectWorldPoint(markerLat, markerLon, renderBounds, projectionMetrics),
        };
      })
      .filter((item): item is { photo: GpsPhoto; world: ScreenPoint } => Boolean(item));
  }, [gpsPhotos, renderBounds, projectionMetrics]);

  // ── Field session overlay: project selected inbox submission onto the workspace map ──
  const projectedFieldStations = useMemo(() => {
    if (!selectedFieldJobDetail || !renderBounds || !projectionMetrics || !selectedFieldSessionId) {
      return [];
    }
    const toNum = (s: string) => {
      const [major, minor] = s.split("+");
      return (parseInt(major ?? "0", 10) * 100) + parseInt(minor ?? "0", 10);
    };
    const sessionFilter = selectedFieldSessionId.trim();
    const fieldStationsFiltered = (selectedFieldJobDetail.stations ?? []).filter((st) => {
      const lat = Number(st.latitude);
      const lon = Number(st.longitude);
      if (!Number.isFinite(lat) || !Number.isFinite(lon) || (lat === 0 && lon === 0)) {
        return false;
      }
      const sid = String(st.session_id ?? "").trim();
      if (!sid || sid !== sessionFilter) return false;
      return true;
    });
    const originalLog = fieldStationsFiltered.map((st) => ({
      station_number: st.station_number,
      parsed: toNum(st.station_number),
    }));
    if (process.env.NODE_ENV === "development") {
      console.log(
        "[field-overlay] original station order (API / after lat-lon filter):",
        originalLog,
      );
      console.log(
        "[field-overlay] parsed numeric (same order):",
        fieldStationsFiltered.map((st) => toNum(st.station_number)),
      );
    }
    const fieldStationsSorted = fieldStationsFiltered
      .slice()
      .sort((a, b) => toNum(a.station_number) - toNum(b.station_number));
    const sortedLog = fieldStationsSorted.map((st) => ({
      station_number: st.station_number,
      parsed: toNum(st.station_number),
    }));
    if (process.env.NODE_ENV === "development") {
      console.log(
        "[field-overlay] final sorted order (used for path + markers):",
        sortedLog,
      );
    }
    const nanKeys = originalLog.filter((o) => !Number.isFinite(o.parsed));
    if (nanKeys.length > 0 && process.env.NODE_ENV === "development") {
      console.warn("[field-overlay] NaN / non-finite sort keys:", nanKeys);
    }
    return fieldStationsSorted.map((st) => {
      const rawLat = Number(st.latitude);
      const rawLon = Number(st.longitude);
      const snapped = snapLatLonToKmzPolylines(rawLat, rawLon, kmzSnapPolylines);
      return {
        st,
        displayLat: snapped.lat,
        displayLon: snapped.lon,
        world: projectWorldPoint(snapped.lat, snapped.lon, renderBounds, projectionMetrics),
      };
    });
  }, [selectedFieldJobDetail, selectedFieldSessionId, renderBounds, projectionMetrics, kmzSnapPolylines]);

  const fieldStationPath = useMemo(() => {
    if (projectedFieldStations.length < 2 || !renderBounds || !projectionMetrics) return "";
    return buildWorldPath(
      projectedFieldStations.map(({ displayLat, displayLon }) => [displayLat, displayLon]),
      renderBounds,
      projectionMetrics,
    );
  }, [projectedFieldStations, renderBounds, projectionMetrics]);

  const fieldTrackPath = useMemo(() => {
    const geo = selectedFieldSession?.track_geometry;
    if (!geo || !renderBounds || !projectionMetrics) return "";
    // GeoJSON coordinates are [lon, lat] — swap to [lat, lon] for buildWorldPath
    const coords = (geo.coordinates ?? []).map(([lon, lat]): [number, number] => [lat, lon]);
    return buildWorldPath(coords, renderBounds, projectionMetrics);
  }, [selectedFieldSession, renderBounds, projectionMetrics]);

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
    const raw = manualFootage.trim().replace(/,/g, "");
    if (raw === "") return calculatedCoveredFootage;
    const manual = Number.parseFloat(raw);
    if (Number.isFinite(manual) && manual >= 0) return manual;
    return calculatedCoveredFootage;
  }, [manualFootage, calculatedCoveredFootage]);

  const projectCompletionSummary = useMemo(() => {
    const manualPlanned = Number.parseFloat(manualProjectPlannedFootage);
    const manualPlannedFootage = Number.isFinite(manualPlanned) && manualPlanned > 0 ? manualPlanned : null;
    const touchedDesignRouteScope =
      typeof state?.total_length_ft === "number" && Number.isFinite(state.total_length_ft) && state.total_length_ft > 0
        ? state.total_length_ft
        : null;
    const drilledFootage = calculatedCoveredFootage;
    const remainingFootage = manualPlannedFootage !== null ? Math.max(manualPlannedFootage - drilledFootage, 0) : null;
    const calculatedPct =
      manualPlannedFootage !== null && manualPlannedFootage > 0
        ? clamp((drilledFootage / manualPlannedFootage) * 100, 0, 100)
        : null;

    return {
      plannedFootage: manualPlannedFootage,
      drilledFootage,
      remainingFootage,
      percentComplete: calculatedPct,
      touchedDesignRouteScope,
      plannedSource: manualPlannedFootage !== null ? "manual" : null,
    };
  }, [calculatedCoveredFootage, manualProjectPlannedFootage, state?.total_length_ft]);

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

  // Nova Phase 1 — deterministic read-only summary. Recomputes after any upload.
  const novaSummary = useMemo(() => {
    const hasKmz = (state?.kmz_reference?.line_features || []).length > 0;
    const hasBoreLogs = (state?.bore_log_summary || []).length > 0;
    return buildNovaSummary(pipelineDiag, engineeringPlanSignals, exceptions, exceptionTotal, hasKmz, hasBoreLogs);
  }, [pipelineDiag, engineeringPlanSignals, exceptions, exceptionTotal, state?.kmz_reference?.line_features, state?.bore_log_summary]);

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
      {
        id: `custom-${Date.now()}`,
        label,
        amount: extraExceptionAmount.trim(),
        note: extraExceptionNote.trim() || undefined,
        billing_relevant: true,
      },
    ];

    setExceptions(nextExceptions);
    setExtraExceptionLabel("");
    setExtraExceptionAmount("");
    setExtraExceptionNote("");
  }, [exceptions, extraExceptionLabel, extraExceptionAmount, extraExceptionNote]);

  const handleRemoveException = useCallback((id: string) => {
    const nextExceptions: ExceptionCost[] = exceptions.filter((item) => item.id !== id);
    setExceptions(nextExceptions);
  }, [exceptions]);

  const handleExceptionChange = useCallback((id: string, field: "label" | "amount" | "note", value: string) => {
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

  const handleExportKml = useCallback(() => {
    const designCoveragePlacemarks: string[] = [];
    const designRoutePlacemarks: string[] = [];
    const redlinePlacemarks: string[] = [];
    const photoPlacemarks: string[] = [];
    const stationPlacemarks: string[] = [];

    const buildFolder = (name: string, folderPlacemarks: string[]) => `    <Folder>
      <name>${escapeXml(name)}</name>
${folderPlacemarks.join("\n")}
    </Folder>`;

    kmzPolygonFeatures.forEach((feature, idx) => {
      const ringCoords = cleanCoords(feature.coords);
      if (ringCoords.length < 3) return;

      const first = ringCoords[0];
      const last = ringCoords[ringCoords.length - 1];
      const closedRing =
        first[0] === last[0] && first[1] === last[1]
          ? ringCoords
          : [...ringCoords, first];
      const coordinates = closedRing
        .map((pt) => kmlCoordinateFromLatLon(pt[0], pt[1]))
        .filter((coord): coord is string => Boolean(coord));
      if (coordinates.length < 4) return;

      const name = cleanDisplayText(feature.name || feature.feature_id || `Coverage ${idx + 1}`);
      designCoveragePlacemarks.push(`      <Placemark>
        <name>${escapeXml(name)}</name>
        <styleUrl>#coveragePolyStyle</styleUrl>
        <Polygon>
          <tessellate>1</tessellate>
          <outerBoundaryIs>
            <LinearRing>
              <coordinates>
                ${coordinates.join("\n                ")}
              </coordinates>
            </LinearRing>
          </outerBoundaryIs>
        </Polygon>
      </Placemark>`);
    });

    kmzLineFeatures.forEach((feature, idx) => {
      const coordinates = cleanCoords(feature.coords)
        .map((pt) => kmlCoordinateFromLatLon(pt[0], pt[1]))
        .filter((coord): coord is string => Boolean(coord));
      if (coordinates.length < 2) return;

      const name = cleanDisplayText(
        feature.route_name ||
          feature.route_id ||
          feature.feature_id ||
          feature.role ||
          `Design Route ${idx + 1}`
      );
      designRoutePlacemarks.push(`      <Placemark>
        <name>${escapeXml(name)}</name>
        <styleUrl>#designLineStyle</styleUrl>
        <LineString>
          <tessellate>1</tessellate>
          <coordinates>
            ${coordinates.join("\n            ")}
          </coordinates>
        </LineString>
      </Placemark>`);
    });

    redlineSegments.forEach((segment, idx) => {
      const coordinates = cleanCoords(segment.coords)
        .map((pt) => kmlCoordinateFromLatLon(pt[0], pt[1]))
        .filter((coord): coord is string => Boolean(coord));
      if (coordinates.length < 2) return;
      const name = cleanDisplayText(segment.source_file || segment.segment_id || `Redline ${idx + 1}`);
      redlinePlacemarks.push(`      <Placemark>
        <name>${escapeXml(`Redline - ${name}`)}</name>
        <styleUrl>#redlineStyle</styleUrl>
        <LineString>
          <tessellate>1</tessellate>
          <coordinates>
            ${coordinates.join("\n            ")}
          </coordinates>
        </LineString>
      </Placemark>`);
    });

    gpsPhotos.forEach((photo) => {
      if (photo.reason !== "mapped") return;
      const markerLat = typeof photo.displayLat === "number" ? photo.displayLat : photo.lat;
      const markerLon = typeof photo.displayLon === "number" ? photo.displayLon : photo.lon;
      const coordinate = kmlCoordinateFromLatLon(markerLat, markerLon);
      if (!coordinate) return;
      const hasAdjusted = typeof photo.displayLat === "number" && typeof photo.displayLon === "number";
      const description = [
        `Original GPS: ${typeof photo.lat === "number" ? photo.lat.toFixed(6) : "--"}, ${typeof photo.lon === "number" ? photo.lon.toFixed(6) : "--"}`,
        hasAdjusted ? `Adjusted: ${photo.displayLat!.toFixed(6)}, ${photo.displayLon!.toFixed(6)}` : "Adjusted: none",
      ].join("\n");
      photoPlacemarks.push(`      <Placemark>
        <name>${escapeXml(photo.filename)}</name>
        <description>${escapeXml(description)}</description>
        <styleUrl>#photoStyle</styleUrl>
        <Point>
          <coordinates>${coordinate}</coordinates>
        </Point>
      </Placemark>`);
    });

    stationPoints.forEach((point, idx) => {
      const coordinate = kmlCoordinateFromLatLon(point.lat, point.lon);
      if (!coordinate) return;
      const stationLabel = cleanDisplayText(point.station);
      stationPlacemarks.push(`      <Placemark>
        <name>${escapeXml(`Station ${stationLabel !== "--" ? stationLabel : idx + 1}`)}</name>
        <description>${escapeXml(`Source: ${cleanDisplayText(point.source_file)}\nMapped FT: ${formatNumber(point.mapped_station_ft, 3)}`)}</description>
        <styleUrl>#stationStyle</styleUrl>
        <Point>
          <coordinates>${coordinate}</coordinates>
        </Point>
      </Placemark>`);
    });

    const kml = `<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>${escapeXml(activeJob !== "--" ? activeJob : "OSP Redlining Export")}</name>
    <Style id="redlineStyle">
      <LineStyle>
        <color>ff0000ff</color>
        <width>6</width>
      </LineStyle>
    </Style>
    <Style id="designLineStyle">
      <LineStyle>
        <color>9900ffff</color>
        <width>1</width>
      </LineStyle>
    </Style>
    <Style id="coveragePolyStyle">
      <LineStyle>
        <color>ff22c55e</color>
        <width>2</width>
      </LineStyle>
      <PolyStyle>
        <color>7f22c55e</color>
        <fill>1</fill>
        <outline>1</outline>
      </PolyStyle>
    </Style>
    <Style id="photoStyle">
      <IconStyle>
        <scale>0.9</scale>
      </IconStyle>
    </Style>
    <Style id="stationStyle">
      <IconStyle>
        <scale>0.7</scale>
      </IconStyle>
    </Style>
${buildFolder("Design / Coverage", designCoveragePlacemarks)}
${buildFolder("Design Routes", designRoutePlacemarks)}
${buildFolder("As-Built Redlines", redlinePlacemarks)}
${buildFolder("Photos", photoPlacemarks)}
${buildFolder("Stations", stationPlacemarks)}
  </Document>
</kml>
`;

    const blob = new Blob([kml], { type: "application/vnd.google-earth.kml+xml" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "osp_redlining_export.kml";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }, [activeJob, gpsPhotos, kmzLineFeatures, kmzPolygonFeatures, redlineSegments, stationPoints]);

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

  const focusMapCoords = useCallback((coords: number[][]): boolean => {
    if (!renderBounds || !projectionMetrics || coords.length === 0) return false;
    const rawBounds = getBoundsFromCoords(coords);
    if (!rawBounds) return false;

    const targetBounds = expandBounds(rawBounds, 0.22);
    const topLeft = projectWorldPoint(targetBounds.maxLat, targetBounds.minLon, renderBounds, projectionMetrics);
    const bottomRight = projectWorldPoint(targetBounds.minLat, targetBounds.maxLon, renderBounds, projectionMetrics);

    const contentWidth = Math.max(1, Math.abs(bottomRight.x - topLeft.x));
    const contentHeight = Math.max(1, Math.abs(bottomRight.y - topLeft.y));
    const usableWidth = Math.max(1, projectionMetrics.worldWidth - FIT_PADDING * 2);
    const usableHeight = Math.max(1, projectionMetrics.worldHeight - FIT_PADDING * 2);
    const zoom = clamp(Math.min(usableWidth / contentWidth, usableHeight / contentHeight), MIN_ZOOM, MAX_ZOOM);
    const centerWorldX = (topLeft.x + bottomRight.x) / 2;
    const centerWorldY = (topLeft.y + bottomRight.y) / 2;

    userHasAdjustedViewportRef.current = true;
    setViewport({
      zoom,
      panX: projectionMetrics.worldWidth / 2 - centerWorldX * zoom,
      panY: projectionMetrics.worldHeight / 2 - centerWorldY * zoom,
    });
    return true;
  }, [projectionMetrics, renderBounds]);

  const handleFocusNovaIssue = useCallback((issue: NovaIssueFocusPayload) => {
    const sourceFile = String(issue.source_file || issue.item.sourceFile || "").trim();
    const previousStatusText = statusText;
    const previousStatusTone = statusTone;
    if (focusStatusTimeoutRef.current) {
      clearTimeout(focusStatusTimeoutRef.current);
      focusStatusTimeoutRef.current = null;
    }
    setStatusTone("neutral");
    setStatusText(`Focusing: ${sourceFile || "issue"}`);

    const sourceKey = normalizeSourceFileKey(sourceFile);
    if (!sourceKey) {
      setStatusTone("warning");
      setStatusText("No map geometry available for this issue.");
      return;
    }

    const layerId = sourceKeyToLayerId.get(sourceKey) ?? null;
    const matchingSegments = redlineSegments.filter((segment) => {
      const segmentLayerId = (segment as { evidence_layer_id?: string }).evidence_layer_id ?? null;
      return normalizeSourceFileKey(segment.source_file) === sourceKey || Boolean(layerId && segmentLayerId === layerId);
    });
    const matchingStationEntries = stationPoints
      .map((point, idx) => ({ point, idx }))
      .filter(({ point }) => {
        const pointKey = normalizeSourceFileKey(point.source_file);
        const pointLayerId = sourceKeyToLayerId.get(pointKey) ?? null;
        return pointKey === sourceKey || Boolean(layerId && pointLayerId === layerId);
      });

    const focusCoords: number[][] = [];
    for (const segment of matchingSegments) {
      cleanCoords(segment.coords).forEach((pt) => focusCoords.push(pt));
    }
    for (const { point } of matchingStationEntries) {
      if (typeof point.lat === "number" && typeof point.lon === "number") {
        focusCoords.push([point.lat, point.lon]);
      }
    }

    if (focusCoords.length === 0) {
      setStatusTone("warning");
      setStatusText("No map geometry available for this issue.");
      return;
    }

    if (layerId) {
      setHiddenLayers((prev) => {
        if (!prev.has(layerId)) return prev;
        const next = new Set(prev);
        next.delete(layerId);
        return next;
      });
    }

    if (matchingStationEntries.length > 0) {
      setShowStations(true);
      setSelectedStationIndex(matchingStationEntries[0].idx);
    } else {
      setSelectedStationIndex(null);
    }
    setSelectedGpsPhotoId(null);
    setFocusedNovaIssue({
      sourceFile,
      sourceKey,
      layerId,
      issueKey: issue.issue_key || issue.issueId,
    });

    if (focusedNovaIssueTimeoutRef.current) {
      clearTimeout(focusedNovaIssueTimeoutRef.current);
    }
    focusedNovaIssueTimeoutRef.current = setTimeout(() => {
      setFocusedNovaIssue(null);
      focusedNovaIssueTimeoutRef.current = null;
    }, 9000);

    const didFocus = focusMapCoords(focusCoords);
    mapContainerRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    if (!didFocus) {
      setStatusTone("success");
      setStatusText(`Focusing: ${sourceFile}`);
    }
    focusStatusTimeoutRef.current = setTimeout(() => {
      setStatusText(previousStatusText);
      setStatusTone(previousStatusTone);
      focusStatusTimeoutRef.current = null;
    }, 1600);
  }, [focusMapCoords, redlineSegments, sourceKeyToLayerId, stationPoints, statusText, statusTone]);

  const handleNovaOverrideSourcesChange = useCallback((sourceFiles: string[]) => {
    const next = new Set(
      sourceFiles
        .map((sourceFile) => normalizeSourceFileKey(sourceFile))
        .filter((sourceKey) => sourceKey.length > 0)
    );
    setNovaOverrideSourceKeys((prev) => {
      if (prev.size === next.size && Array.from(prev).every((sourceKey) => next.has(sourceKey))) {
        return prev;
      }
      return next;
    });
  }, []);

  async function fetchState(message?: string) {
    if (message) {
      setStatusText(message);
      setStatusTone("neutral");
    }
    try {
      const response = await fetch(appendSessionId(`${API_BASE}/api/current-state`, projectId));
      const data: BackendState = await response.json();
      const sessionId = rememberSessionFromResponse(data, projectId);
      if (!response.ok || data.success === false) throw new Error(data.error || "Unable to load current state.");
      setState(withoutClearedEngineeringPlans(data, projectId, sessionId));
      fetchPipelineDiag(); // Nova Phase 1 — non-blocking refresh
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

  // Nova Phase 1 — fire-and-forget. Non-fatal. Nova degrades gracefully if unavailable.
  async function fetchPipelineDiag(): Promise<void> {
    try {
      const res = await fetch(appendSessionId(`${API_BASE}/api/debug/pipeline-diag`, projectId));
      if (!res.ok) return;
      const data = await res.json();
      if (Array.isArray(data.pipeline_diag)) setPipelineDiag(data.pipeline_diag);
      if (Array.isArray(data.engineering_plan_signals)) {
        setEngineeringPlanSignals(withoutClearedEngineeringPlanSignals(data.engineering_plan_signals, projectId));
      }
    } catch {
      // non-fatal — Nova works with whatever data it already has
    }
  }

  async function handleReset() {
    setBusy(true);
    try {
      const response = await fetch(appendSessionId(`${API_BASE}/api/reset-state`, projectId), { method: "POST" });
      const data: BackendState = await response.json();
      const sessionId = rememberSessionFromResponse(data, projectId);
      if (!response.ok || data.success === false) throw new Error(data.error || "Reset failed.");
      rememberClearedEngineeringPlans([...(state?.engineering_plans ?? []), ...(data.engineering_plans ?? [])], projectId, sessionId);
      setState({ ...data, engineering_plans: [] });
      // Nova Phase 1 — clear diagnostics on workspace reset
      setPipelineDiag([]);
      setEngineeringPlanSignals([]);
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
      if (focusStatusTimeoutRef.current) {
        clearTimeout(focusStatusTimeoutRef.current);
        focusStatusTimeoutRef.current = null;
      }
      setSelectedStationIndex(null);
      setHoverStationIndex(null);
      setFocusedNovaIssue(null);
      setNovaOverrideSourceKeys(new Set());
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
      setManualFootage("");
      setBillingApprovalStatus("not_submitted");
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
      appendSessionIdToForm(form, projectId);
      const scopedProject = projectId?.trim();
      if (scopedProject) form.append("project_id", scopedProject);
      const response = await fetch(appendSessionId(`${API_BASE}/api/upload-design`, projectId), { method: "POST", body: form });
      const data: BackendState = await response.json();
      rememberSessionFromResponse(data, projectId);
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
      appendSessionIdToForm(form, projectId);
      const response = await fetch(`${API_BASE}/api/upload-structured-bore-files`, { method: "POST", body: form });
      const data: BackendState = await response.json();
      rememberSessionFromResponse(data, projectId);
      if (!response.ok || data.success === false) throw new Error(data.error || "Structured bore upload failed.");
      setState(data);
      fetchPipelineDiag(); // Nova Phase 1 — refresh diagnostics after bore log upload
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

  async function handleEngineeringPlansUpload(files: FileList | null) {
    if (!files || files.length === 0) return;
    setEngPlansBusy(true);
    setStatusText(`Uploading ${files.length} engineering plan file${files.length > 1 ? "s" : ""}...`);
    setStatusTone("neutral");
    try {
      const form = new FormData();
      appendSessionIdToForm(form, projectId);
      Array.from(files).forEach((f) => form.append("files", f));
      const response = await fetch(`${API_BASE}/api/upload-engineering-plans`, { method: "POST", body: form });
      const data = await response.json();
      rememberSessionFromResponse(data, projectId);
      if (!response.ok || data.success === false) throw new Error(data.error || "Engineering plan upload failed.");
      setState((prev) => {
        if (!prev) return prev;
        const nextState = { ...prev, engineering_plans: data.engineering_plans ?? prev.engineering_plans };
        return withoutClearedEngineeringPlans(nextState, projectId);
      });
      fetchPipelineDiag(); // Nova Phase 1 — refresh plan signals after engineering plan upload
      setStatusText(String(data.message || "Engineering plans uploaded successfully."));
      setStatusTone("success");
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Engineering plan upload failed.");
      setStatusTone("error");
    } finally {
      setEngPlansBusy(false);
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
      const response = await fetch(appendSessionId(`${API_BASE}/api/report-bug`, projectId), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      rememberSessionFromResponse(data, projectId);
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
        appendSessionId(`${API_BASE}/api/station-photos?station_identity=${encodeURIComponent(stationIdentity)}`, projectId)
      );
      const data = await response.json();
      rememberSessionFromResponse(data, projectId);
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
      appendSessionIdToForm(form, projectId);

      const response = await fetch(`${API_BASE}/api/station-photos/upload`, {
        method: "POST",
        body: form,
      });
      const data = await response.json();
      rememberSessionFromResponse(data, projectId);
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
    setGpsPhotoDrag(null);
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
    return () => {
      if (focusedNovaIssueTimeoutRef.current) {
        clearTimeout(focusedNovaIssueTimeoutRef.current);
        focusedNovaIssueTimeoutRef.current = null;
      }
      if (focusStatusTimeoutRef.current) {
        clearTimeout(focusStatusTimeoutRef.current);
        focusStatusTimeoutRef.current = null;
      }
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

  const hasDesign = (kmzLineFeatures.length || kmzPolygonFeatures.length) > 0;
  const hasBoreFiles = (state?.loaded_field_data_files || 0) > 0;
  const hasGeneratedOutput = redlineSegments.length > 0 || stationPoints.length > 0;
  const billingChecklistComplete =
    hasDesign && hasBoreFiles && (stationPhotos.length > 0 || gpsPhotos.length > 0);
  const billingApproved = billingApprovalStatus === "approved";
  const desktopMapHeight = Math.max(MAP_HEIGHT, 900);
  const mapScrollGutterWidth = 34;
  const isProjectWorkspace = Boolean(workspaceTitle?.trim());

  return (
    <div style={{ minHeight: "100vh", background: "linear-gradient(180deg, #eef3f8 0%, #f6f9fc 100%)", fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif", color: "#0f172a" }}>
      <style>{`
        @media print {
          body {
            background: #ffffff !important;
            margin: 0 !important;
            padding: 0 !important;
          }
          .osp-workspace-main {
            display: none !important;
          }
          #osp-print-report {
            display: block !important;
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
        @media screen {
          #osp-print-report {
            display: none !important;
          }
        }
        #osp-print-report {
          font-family: Inter, ui-sans-serif, system-ui, sans-serif;
          color: #0f172a;
          background: #ffffff;
          padding: 32px 40px;
          max-width: 960px;
          margin: 0 auto;
        }
        #osp-print-report h1 {
          font-size: 22px;
          font-weight: 900;
          margin: 0 0 4px 0;
          letter-spacing: -0.4px;
        }
        #osp-print-report h2 {
          font-size: 13px;
          font-weight: 800;
          text-transform: uppercase;
          letter-spacing: 0.06em;
          color: #475569;
          margin: 20px 0 8px 0;
          padding-bottom: 4px;
          border-bottom: 1px solid #e2e8f0;
        }
        #osp-print-report .rpt-meta {
          font-size: 12px;
          color: #64748b;
          margin-bottom: 16px;
        }
        #osp-print-report .rpt-kpi-row {
          display: flex;
          gap: 20px;
          flex-wrap: wrap;
          margin-bottom: 6px;
        }
        #osp-print-report .rpt-kpi {
          background: #f8fafc;
          border: 1px solid #e2e8f0;
          border-radius: 8px;
          padding: 10px 16px;
          min-width: 140px;
        }
        #osp-print-report .rpt-kpi-label {
          font-size: 10px;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          color: #94a3b8;
        }
        #osp-print-report .rpt-kpi-value {
          font-size: 18px;
          font-weight: 800;
          color: #0f172a;
          margin-top: 2px;
        }
        #osp-print-report table {
          width: 100%;
          border-collapse: collapse;
          font-size: 12px;
          margin-bottom: 6px;
        }
        #osp-print-report th {
          background: #f1f5f9;
          text-align: left;
          padding: 6px 10px;
          font-weight: 700;
          font-size: 11px;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: #475569;
          border: 1px solid #e2e8f0;
        }
        #osp-print-report td {
          padding: 6px 10px;
          border: 1px solid #e2e8f0;
          vertical-align: top;
          line-height: 1.45;
        }
        #osp-print-report tr:nth-child(even) td {
          background: #fafbfc;
        }
        #osp-print-report .rpt-total-row td {
          font-weight: 800;
          background: #f1f5f9 !important;
          border-top: 2px solid #cbd5e1;
        }
        #osp-print-report .rpt-notes {
          background: #fafbfc;
          border: 1px solid #e2e8f0;
          border-radius: 8px;
          padding: 12px 16px;
          font-size: 13px;
          line-height: 1.6;
          white-space: pre-wrap;
          color: #334155;
        }
        #osp-print-report .rpt-footer {
          margin-top: 28px;
          padding-top: 12px;
          border-top: 1px solid #e2e8f0;
          font-size: 10px;
          color: #94a3b8;
          display: flex;
          justify-content: space-between;
        }
        @media print {
          #osp-print-report h2 { break-after: avoid; }
          #osp-print-report table { break-inside: auto; }
          #osp-print-report tr { break-inside: avoid; }
        }
      `}</style>
      <div className="osp-workspace-main" style={{ maxWidth: 1520, margin: "0 auto", padding: 20 }}>
        <div style={{ display: "grid", gap: 8 }}>
          {isProjectWorkspace ? (
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                gap: 10,
                padding: "6px 10px",
                background: "#ffffff",
                border: "1px solid #e2e8f0",
                borderRadius: 10,
              }}
            >
              <input
                value={jobLabel}
                onChange={(e) => setJobLabel(e.target.value)}
                placeholder="Optional local beta job label"
                style={{
                  flex: "1 1 200px",
                  minWidth: 160,
                  maxWidth: 520,
                  borderRadius: 10,
                  border: "1px solid #cfd8e3",
                  background: "#fff",
                  padding: "8px 11px",
                  outline: "none",
                  fontSize: 14,
                }}
              />
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, flex: "0 0 auto" }}>
                <button onClick={() => fetchState("Refreshing backend state...")} disabled={busy} style={buttonStyle("#ffffff", "#0f172a", "#cfd8e3", busy)}>Refresh State</button>
                <button onClick={handleReset} disabled={busy} style={buttonStyle("#0f172a", "#ffffff", "#0f172a", busy)}>Clear Workspace</button>
              </div>
            </div>
          ) : (
            <div
              style={{
                background: "linear-gradient(135deg, #ffffff 0%, #f7fbff 52%, #eef6ff 100%)",
                border: "1px solid #dbe4ee",
                borderRadius: 18,
                padding: "14px 18px",
                boxShadow: "0 8px 20px rgba(15, 23, 42, 0.04)",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "flex-start", flexWrap: "wrap" }}>
                <div style={{ maxWidth: 720 }}>
                  <div style={{ fontSize: 22, fontWeight: 900, letterSpacing: -0.5, color: "#0f172a" }}>
                    OSP Redlining Operator Workspace
                  </div>
                  <div style={{ marginTop: 6, fontSize: 14, color: "#526173", lineHeight: 1.5 }}>
                    Upload design and bore logs, review the map, then use Reports and Billing for outputs.
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
          )}

          <StatusBanner tone={statusTone} text={statusText} />

          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 16, alignItems: "stretch" }}>
            <SummaryCard title="Active Job" value={String(activeJob)} subtitle="Local label or backend-selected route" />
            <SummaryCard title="Files Loaded" value={String((hasDesign ? 1 : 0) + (state?.loaded_field_data_files || 0))} subtitle="Design + structured bore files" />
            <SummaryCard title="QA Status" value={String(verification?.status || "waiting")} subtitle="Real backend verification summary" />
            <SummaryCard title="Output Counts" value={`${stationPoints.length} pts / ${redlineSegments.length} segs`} subtitle="Station points and generated redline segments" />
          </div>

          <div
            role="tablist"
            aria-label="Operator workspace sections"
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: 8,
              padding: 8,
              border: "1px solid #dbe4ee",
              borderRadius: 18,
              background: "#ffffff",
              boxShadow: "0 10px 24px rgba(15, 23, 42, 0.04)",
              marginBottom: -8,
            }}
          >
            {WORKSPACE_TABS.map((tab) => {
              const active = activeWorkspaceTab === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onPointerDown={() => setActiveWorkspaceTab(tab.id)}
                  onClick={() => setActiveWorkspaceTab(tab.id)}
                  style={{
                    border: active ? "1px solid #0f172a" : "1px solid #dbe4ee",
                    borderRadius: 12,
                    background: active ? "#0f172a" : "#f8fafc",
                    color: active ? "#ffffff" : "#334155",
                    padding: "10px 14px",
                    fontSize: 13,
                    fontWeight: 800,
                    cursor: "pointer",
                  }}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>

          <Section
            title="1. Upload"
            subtitle="KMZ design, structured bore logs, and optional engineering plan PDFs/images. Same upload behavior as before."
            style={{ display: activeWorkspaceTab === "setup" ? "block" : "none" }}
          >
            <div
              style={{
                marginBottom: 14,
                padding: "8px 12px",
                borderRadius: 10,
                border: "1px solid #e2e8f0",
                background: "#f8fafc",
                fontSize: 12,
                color: "#475569",
                lineHeight: 1.5,
              }}
            >
              <span style={{ fontWeight: 800, color: "#0f172a" }}>Workflow: </span>
              Upload KMZ and bore logs (optional plans) → review on the Map tab → open Reports or Billing / Export for summaries and print.
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 16, alignItems: "start" }}>
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

              <label style={{
                display: "block",
                border: "2px solid #000000",
                borderRadius: 16,
                padding: 16,
                background: engPlansBusy ? "#f3f4f6" : "#ffffff",
                cursor: engPlansBusy ? "not-allowed" : "pointer",
                opacity: engPlansBusy ? 0.7 : 1,
              }}>
                <input
                  type="file"
                  accept=".pdf,.png,.jpg,.jpeg"
                  multiple
                  style={{ display: "none" }}
                  disabled={engPlansBusy}
                  onChange={(e) => {
                    handleEngineeringPlansUpload(e.target.files);
                    e.currentTarget.value = "";
                  }}
                />
                <div style={{ fontWeight: 800, fontSize: 16 }}>Upload Engineering Plans</div>
                <div style={{ marginTop: 6, fontSize: 13, color: "#64748b", lineHeight: 1.55 }}>
                  PDF, PNG, JPG or JPEG. Multiple files allowed. Session-scoped job evidence only.
                </div>
                <div style={{ marginTop: 14, fontSize: 12, fontWeight: 700, color: (state?.engineering_plans?.length ?? 0) > 0 ? "#166534" : "#64748b" }}>
                  {engPlansBusy
                    ? "Uploading..."
                    : (state?.engineering_plans?.length ?? 0) > 0
                      ? `${state!.engineering_plans!.length} plan file${state!.engineering_plans!.length !== 1 ? "s" : ""} uploaded.`
                      : "No engineering plans uploaded yet."}
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

            <div style={{ border: "1px solid #dbe4ee", borderRadius: 16, background: "#fbfdff", padding: 16, minHeight: 100, marginTop: 16 }}>
              <div style={{ fontWeight: 800, fontSize: 15, marginBottom: 10 }}>
                Engineering Plans
                {(state?.engineering_plans?.length ?? 0) > 0 && (
                  <span style={{ marginLeft: 8, fontSize: 12, fontWeight: 600, color: "#64748b" }}>
                    ({state!.engineering_plans!.length})
                  </span>
                )}
              </div>
              {(state?.engineering_plans?.length ?? 0) === 0 ? (
                <div style={{ fontSize: 13, color: "#94a3b8" }}>No plans uploaded for this session.</div>
              ) : (
                <div style={{ display: "grid", gap: 8 }}>
                  {state!.engineering_plans!.map((plan: EngineeringPlan) => {
                    const sizeKb = (plan.size_bytes / 1024).toFixed(1);
                    const sizeMb = (plan.size_bytes / (1024 * 1024)).toFixed(2);
                    const sizeLabel = plan.size_bytes >= 1024 * 1024 ? `${sizeMb} MB` : `${sizeKb} KB`;
                    const uploadedDate = plan.uploaded_at
                      ? new Date(plan.uploaded_at).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" })
                      : "";
                    const typeLabel = plan.file_type === "application/pdf"
                      ? "PDF"
                      : plan.file_type?.startsWith("image/")
                        ? plan.file_type.split("/")[1]?.toUpperCase() ?? "Image"
                        : plan.file_type ?? "";
                    return (
                      <div key={plan.plan_id} style={{ borderRadius: 10, border: "1px solid #e2e8f0", background: "#ffffff", padding: "10px 12px" }}>
                        <div style={{ fontWeight: 700, fontSize: 13, color: "#0f172a", wordBreak: "break-all" }}>{plan.original_filename}</div>
                        <div style={{ marginTop: 4, display: "flex", gap: 12, flexWrap: "wrap", fontSize: 12, color: "#64748b" }}>
                          <span>{typeLabel}</span>
                          <span>{sizeLabel}</span>
                          {uploadedDate && <span>{uploadedDate}</span>}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </Section>

          <Section
            title={activeWorkspaceTab === "setup" ? "Field Photo Evidence" : "Map Review"}
            subtitle={
              activeWorkspaceTab === "setup"
                ? "Station-attached photos and geotagged photo review, using the existing photo state and upload behavior."
                : undefined
            }
            style={{
              display: activeWorkspaceTab === "map" || activeWorkspaceTab === "setup" ? "block" : "none",
              border: activeWorkspaceTab === "map" ? "none" : "1px solid #cbd5e1",
              background: activeWorkspaceTab === "map" ? "transparent" : "#ffffff",
              boxShadow: activeWorkspaceTab === "map" ? "none" : "0 18px 42px rgba(15, 23, 42, 0.10)",
              order: activeWorkspaceTab === "setup" ? 3 : undefined,
            }}
            headerStyle={{
              display: activeWorkspaceTab === "map" ? "none" : "flex",
            }}
            contentStyle={{
              padding: activeWorkspaceTab === "map" ? 0 : 18,
            }}
          >
            <div style={{ display: "grid", gap: activeWorkspaceTab === "map" ? 6 : 18 }}>

              {/* ─── Bore Log Layers panel ───────────────────────────── */}
              {activeWorkspaceTab === "map" && (state?.bore_log_summary?.length ?? 0) > 0 && (() => {
                const layers = state!.bore_log_summary!;
                const allVisible = layers.every((e) => !e.evidence_layer_id || !hiddenLayers.has(e.evidence_layer_id));
                const allHidden  = layers.every((e) => e.evidence_layer_id && hiddenLayers.has(e.evidence_layer_id));
                return (
                  <div
                    style={{
                      border: "1px solid #e2e8f0",
                      borderRadius: 10,
                      background: "rgba(255, 255, 255, 0.7)",
                      padding: "3px 7px",
                      order: -1,
                    }}
                  >
                    {/* Header row */}
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 4, marginBottom: 2 }}>
                      <div style={{ fontSize: 10, fontWeight: 800, color: "#334155" }}>
                        Bore Log Layers
                        <span style={{ marginLeft: 5, fontSize: 9, fontWeight: 600, color: "#64748b" }}>
                          ({layers.filter((e) => !e.evidence_layer_id || !hiddenLayers.has(e.evidence_layer_id)).length} / {layers.length} visible)
                        </span>
                      </div>
                      <div style={{ display: "flex", gap: 4 }}>
                        <button
                          type="button"
                          disabled={allVisible}
                          onClick={() => setHiddenLayers(new Set())}
                          style={{
                            padding: "3px 7px",
                            fontSize: 10,
                            fontWeight: 700,
                            borderRadius: 8,
                            border: "1px solid #dbe4ee",
                            background: allVisible ? "#f8fafc" : "#ffffff",
                            color: allVisible ? "#94a3b8" : "#0f172a",
                            cursor: allVisible ? "default" : "pointer",
                          }}
                        >
                          Show All
                        </button>
                        <button
                          type="button"
                          disabled={allHidden}
                          onClick={() => {
                            const ids = new Set(
                              layers.map((e) => e.evidence_layer_id).filter(Boolean) as string[]
                            );
                            setHiddenLayers(ids);
                            setSelectedStationIndex(null);
                          }}
                          style={{
                            padding: "3px 7px",
                            fontSize: 10,
                            fontWeight: 700,
                            borderRadius: 8,
                            border: "1px solid #dbe4ee",
                            background: allHidden ? "#f8fafc" : "#ffffff",
                            color: allHidden ? "#94a3b8" : "#0f172a",
                            cursor: allHidden ? "default" : "pointer",
                          }}
                        >
                          Hide All
                        </button>
                      </div>
                    </div>

                    {/* Checkbox rows */}
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "3px 12px" }}>
                      {layers.map((entry) => {
                        const lid = entry.evidence_layer_id ?? "";
                        const isVisible = !lid || !hiddenLayers.has(lid);
                        const shortName = entry.source_file.split(/[/\\]/).pop() ?? entry.source_file;
                        const color = getColorForLayer(lid || null);
                        return (
                          <label
                            key={lid || entry.source_file}
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: 5,
                              cursor: "pointer",
                              userSelect: "none",
                              opacity: isVisible ? 1 : 0.45,
                            }}
                          >
                            <input
                              type="checkbox"
                              checked={isVisible}
                              onChange={() => {
                                if (!lid) return;
                                setHiddenLayers((prev) => {
                                  const next = new Set(prev);
                                  if (next.has(lid)) {
                                    next.delete(lid);
                                  } else {
                                    next.add(lid);
                                    // Close inspector if selected station belongs to this layer.
                                    if (selectedStation) {
                                      const selLid = sourceFileToLayerId.get(
                                        String(selectedStation.source_file ?? "").trim()
                                      );
                                      if (selLid === lid) setSelectedStationIndex(null);
                                    }
                                  }
                                  return next;
                                });
                              }}
                              style={{ width: 11, height: 11, accentColor: color, cursor: "pointer", flexShrink: 0 }}
                            />
                            {/* Color swatch */}
                            <span
                              style={{
                                display: "inline-block",
                                width: 8,
                                height: 8,
                                borderRadius: "50%",
                                background: color,
                                flexShrink: 0,
                              }}
                            />
                            <span style={{ fontSize: 11, fontWeight: 600, color: "#334155", maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                              {shortName}
                            </span>
                            {entry.dates?.[0] && (
                              <span style={{ fontSize: 10, color: "#64748b" }}>
                                {formatDisplayDate(entry.dates[0])}
                              </span>
                            )}
                          </label>
                        );
                      })}
                    </div>
                  </div>
                );
              })()}

              {/* ─── Map + Inspector wrapper ─────────────────────────── */}
              {/* Inspector is position:absolute so map container width    */}
              {/* never changes — projection stays stable on station click. */}
              <div style={{ position: "relative", display: activeWorkspaceTab === "map" ? "block" : "none", order: -2 }}>
                <div
                  ref={mapContainerRef}
                  style={{
                    position: "relative",
                    width: `calc(100% - ${mapScrollGutterWidth}px)`,
                    height: desktopMapHeight,
                    borderRadius: 18,
                    overflow: "hidden",
                    background: "radial-gradient(circle at 28% 18%, rgba(30, 64, 82, 0.42), transparent 34%), radial-gradient(circle at 76% 72%, rgba(44, 73, 48, 0.30), transparent 32%), linear-gradient(180deg, #020617 0%, #030712 58%, #010409 100%)",
                    border: "1px solid rgba(96, 165, 250, 0.26)",
                    cursor: boxZoom ? "crosshair" : isPanning ? "grabbing" : "grab",
                    overscrollBehavior: "contain",
                    touchAction: "none",
                    userSelect: "none",
                    boxShadow: "inset 0 1px 0 rgba(255,255,255,0.06), inset 0 0 80px rgba(0,0,0,0.42)",
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
                <div
                  style={{
                    position: "absolute",
                    top: 12,
                    left: selectedStation ? 12 : undefined,
                    right: selectedStation ? undefined : 12,
                    zIndex: 25,
                    display: "flex",
                    gap: 8,
                    flexWrap: "wrap",
                    justifyContent: selectedStation ? "flex-start" : "flex-end",
                    maxWidth: selectedStation
                      ? `calc(100% - ${276 + mapScrollGutterWidth + 24}px)`
                      : "calc(100% - 24px)",
                  }}
                  onPointerDown={(e) => e.stopPropagation()}
                  onWheel={(e) => e.stopPropagation()}
                >
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
                  <button
                    type="button"
                    onClick={() => setPresentationView((v) => !v)}
                    title="Hides or dims secondary design lines and background texture for cleaner demos. Does not change data."
                    style={{
                      ...miniMapButton,
                      ...(presentationView
                        ? {
                            background: "rgba(30, 58, 95, 0.88)",
                            borderColor: "rgba(147, 197, 253, 0.42)",
                            color: "#e0f2fe",
                          }
                        : {}),
                    }}
                  >
                    {presentationView ? "Normal View" : "Presentation View"}
                  </button>
                </div>
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
                    {/* Grid: faint L-shaped corner ticks (world coords).       */}
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
                          stroke="rgba(120, 180, 220, 0.032)"
                          strokeWidth="0.5"
                          vectorEffect="non-scaling-stroke"
                        />
                      </pattern>
                      <radialGradient id="satellite-map-wash" cx="34%" cy="18%" r="82%">
                        <stop offset="0%" stopColor="#183244" />
                        <stop offset="48%" stopColor="#07111d" />
                        <stop offset="100%" stopColor="#010409" />
                      </radialGradient>
                      <pattern
                        id="terrain-speckle-pattern"
                        x="0"
                        y="0"
                        width="96"
                        height="96"
                        patternUnits="userSpaceOnUse"
                      >
                        <circle cx="18" cy="22" r="1.1" fill="rgba(148, 163, 184, 0.035)" />
                        <circle cx="68" cy="34" r="1.4" fill="rgba(132, 204, 22, 0.028)" />
                        <circle cx="42" cy="76" r="1.2" fill="rgba(56, 189, 248, 0.024)" />
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
                          stroke="rgba(140, 195, 235, 0.048)"
                          strokeWidth="0.72"
                          vectorEffect="non-scaling-stroke"
                        />
                      </pattern>
                    </defs>

                    <g id="kmz-design-layer">
                      {/* Base dark wash */}
                      <rect
                        x={0}
                        y={0}
                        width={projectionMetrics?.worldWidth || PROJECTION_BASE_WIDTH}
                        height={projectionMetrics?.worldHeight || PROJECTION_BASE_WIDTH}
                        fill="url(#satellite-map-wash)"
                      />
                      <rect
                        x={0}
                        y={0}
                        width={projectionMetrics?.worldWidth || PROJECTION_BASE_WIDTH}
                        height={projectionMetrics?.worldHeight || PROJECTION_BASE_WIDTH}
                        fill="url(#terrain-speckle-pattern)"
                        opacity={presentationView ? 0.42 : 1}
                        pointerEvents="none"
                      />
                      {/* Fine grid */}
                      <rect
                        x={0}
                        y={0}
                        width={projectionMetrics?.worldWidth || PROJECTION_BASE_WIDTH}
                        height={projectionMetrics?.worldHeight || PROJECTION_BASE_WIDTH}
                        fill="url(#map-grid-pattern)"
                        opacity={presentationView ? 0.32 : 1}
                        pointerEvents="none"
                      />
                      {/* Coarse grid for stronger structure at low zoom */}
                      <rect
                        x={0}
                        y={0}
                        width={projectionMetrics?.worldWidth || PROJECTION_BASE_WIDTH}
                        height={projectionMetrics?.worldHeight || PROJECTION_BASE_WIDTH}
                        fill="url(#map-grid-pattern-coarse)"
                        opacity={presentationView ? 0.35 : 1}
                        pointerEvents="none"
                      />

                      {kmzLinePaths.map((line, idx) => {
                        const feature = kmzLineFeatures[idx];
                        const presentationPaint = presentationKmzPaint(feature, presentationView);
                        if (presentationPaint.omit) return null;
                        const stroke = kmzLineStroke(feature);
                        const width = kmzLineWidth(feature);
                        return line.path ? (
                          <g key={line.id}>
                            <path
                              d={line.path}
                              fill="none"
                              stroke="rgba(10, 16, 26, 0.1)"
                              strokeOpacity={presentationPaint.casingOpacity}
                              strokeWidth={width + 0.45}
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              vectorEffect="non-scaling-stroke"
                            />
                            <path
                              d={line.path}
                              fill="none"
                              stroke={stroke}
                              strokeOpacity={presentationPaint.lineOpacity}
                              strokeWidth={width}
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              vectorEffect="non-scaling-stroke"
                            />
                          </g>
                        ) : null;
                      })}
                      {showPlannedRouteHighlight && !presentationView ? (
                        <g id="planned-route-highlight-layer" pointerEvents="none">
                          {kmzLinePaths.map((line, idx) => {
                            const feature = kmzLineFeatures[idx];
                            const width = kmzLineWidth(feature);
                            return line.path ? (
                              <path
                                key={`planned-highlight-${line.id}`}
                                d={line.path}
                                fill="none"
                                stroke="rgba(253, 224, 112, 0.48)"
                                strokeWidth={Math.max(width + 1.45, 2.85)}
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeDasharray="6 14"
                                strokeOpacity={0.3}
                                vectorEffect="non-scaling-stroke"
                              />
                            ) : null;
                          })}
                        </g>
                      ) : null}
                    </g>

                    <g id="redline-layer">
                      {redlinePaths.map((line) => {
                        if (!line.path) return null;
                        // Respect layer visibility toggle.
                        if (line.evidenceLayerId && hiddenLayers.has(line.evidenceLayerId)) return null;
                        const isNovaFocused =
                          Boolean(focusedNovaIssue) &&
                          (line.sourceKey === focusedNovaIssue?.sourceKey ||
                            Boolean(line.evidenceLayerId && line.evidenceLayerId === focusedNovaIssue?.layerId));
                        const hasOverrideCue = novaOverrideSourceKeys.has(line.sourceKey);
                        const segStroke = getColorForLayer(line.evidenceLayerId);
                        const segCasing = getCasingForLayer(line.evidenceLayerId);
                        return (
                          <g key={line.id}>
                            {hasOverrideCue && (
                              <path
                                d={line.path}
                                fill="none"
                                stroke="rgba(196, 181, 253, 0.48)"
                                strokeWidth={5.45}
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                vectorEffect="non-scaling-stroke"
                                pointerEvents="none"
                              />
                            )}
                            <path
                              d={line.path}
                              fill="none"
                              stroke={segCasing}
                              strokeWidth={4.62}
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              vectorEffect="non-scaling-stroke"
                            />
                            <path
                              d={line.path}
                              fill="none"
                              stroke={segStroke}
                              strokeWidth={3.05}
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              vectorEffect="non-scaling-stroke"
                            />
                            {isNovaFocused && (
                              <path
                                d={line.path}
                                fill="none"
                                stroke="#facc15"
                                strokeWidth={6.45}
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeOpacity={0.9}
                                vectorEffect="non-scaling-stroke"
                                pointerEvents="none"
                              />
                            )}
                          </g>
                        );
                      })}
                    </g>

                    {showStations ? (
                      <g id="station-layer">
                        {projectedStations.map(({ idx, world, point }) => {
                          const isSelected = selectedStationIndex === idx;
                          const isHovered = hoverStationIndex === idx;
                          const pointSourceKey = normalizeSourceFileKey(point.source_file);
                          const pointLayerId = sourceKeyToLayerId.get(pointSourceKey) ?? null;
                          const isNovaFocused =
                            Boolean(focusedNovaIssue) &&
                            (pointSourceKey === focusedNovaIssue?.sourceKey ||
                              Boolean(pointLayerId && pointLayerId === focusedNovaIssue?.layerId));
                          const hasOverrideCue = novaOverrideSourceKeys.has(pointSourceKey);
                          // Smaller, less dominant markers so redline colors read first.
                          // Base sizes tuned by zoom level; selected/hover add modest bump only.
                          const baseRadius = viewport.zoom < 4 ? 1.1 : viewport.zoom < 12 ? 0.95 : 0.8;
                          const radius = isSelected ? baseRadius + 0.55 : isHovered || isNovaFocused ? baseRadius + 0.3 : baseRadius;
                          // Halo only on select/hover — no ambient white ring on idle markers.
                          const halo = isSelected ? radius + 2.2 : radius + 1.4;
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
                              {(isSelected || isHovered || isNovaFocused) ? (
                                <circle
                                  cx={world.x}
                                  cy={world.y}
                                  r={halo}
                                  fill={isSelected || isNovaFocused ? "rgba(250, 204, 21, 0.18)" : "rgba(255,255,255,0.10)"}
                                  pointerEvents="none"
                                />
                              ) : null}
                              {hasOverrideCue && !isSelected && !isNovaFocused ? (
                                <circle
                                  cx={world.x}
                                  cy={world.y}
                                  r={radius + 1.6}
                                  fill="rgba(196, 181, 253, 0.12)"
                                  stroke="rgba(196, 181, 253, 0.42)"
                                  strokeWidth={0.45}
                                  vectorEffect="non-scaling-stroke"
                                  pointerEvents="none"
                                />
                              ) : null}
                              {/* Single compact dot — no oversized white ring on idle state */}
                              <circle
                                cx={world.x}
                                cy={world.y}
                                r={radius}
                                fill={isSelected || isNovaFocused ? "#facc15" : isHovered ? "#93c5fd" : "#1e293b"}
                                stroke={isSelected || isNovaFocused ? "rgba(255,255,255,0.9)" : isHovered ? "rgba(255,255,255,0.75)" : "rgba(255,255,255,0.45)"}
                                strokeWidth={0.6}
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

                    {/* ─── Field session overlay ───────────────────────── */}
                    {/* GPS track + station path + markers for the selected */}
                    {/* inbox submission. Renders above design/walk layers.  */}
                    {selectedFieldSessionId ? (
                      <g id="field-session-overlay" pointerEvents="none">
                        {fieldTrackPath ? (
                          <path
                            d={fieldTrackPath}
                            fill="none"
                            stroke="#f97316"
                            strokeWidth={4}
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeOpacity={0.9}
                            vectorEffect="non-scaling-stroke"
                          />
                        ) : null}
                        {fieldStationPath ? (
                          <path
                            d={fieldStationPath}
                            fill="none"
                            stroke="#ef4444"
                            strokeWidth={4}
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeDasharray="5 4"
                            strokeOpacity={0.85}
                            vectorEffect="non-scaling-stroke"
                          />
                        ) : null}
                        {projectedFieldStations.map(({ st, world }) => (
                          <g key={`field-station-${st.id}`}>
                            <circle
                              cx={world.x}
                              cy={world.y}
                              r={4}
                              fill="#facc15"
                              stroke="rgba(14,24,34,0.85)"
                              strokeWidth={0.8}
                              vectorEffect="non-scaling-stroke"
                            />
                            <text
                              x={world.x + 4.5}
                              y={world.y - 3.5}
                              fill="#facc15"
                              fontSize={5}
                              fontWeight="700"
                              stroke="rgba(14,24,34,0.85)"
                              strokeWidth={2.5}
                              paintOrder="stroke"
                              style={{ userSelect: "none" }}
                            >
                              {st.station_number}
                            </text>
                          </g>
                        ))}
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
                          const isDragging = gpsPhotoDrag?.id === photo.id;
                          // Mirror the zoom-aware sizing used by stations so
                          // photo pins don't get huge at low zoom or tiny at
                          // high zoom. Photo pins are slightly larger than
                          // station dots so they read as "pins" not "dots".
                          const baseRadius = viewport.zoom < 4 ? 2.6 : viewport.zoom < 12 ? 2.1 : 1.7;
                          const radius = isSelected || isDragging ? baseRadius + 1.0 : isHovered ? baseRadius + 0.5 : baseRadius;
                          const tailHeight = radius * 1.4;
                          // Pin body is centered above the actual coordinate;
                          // the tail points down to (world.x, world.y).
                          const bodyCx = world.x;
                          const bodyCy = world.y - tailHeight;
                          return (
                            <g
                              key={`gpsphoto-${photo.id}`}
                              style={{ cursor: isDragging ? "grabbing" : "grab", touchAction: "none" }}
                              onPointerDown={(e) => {
                                if (e.button !== 0) return;
                                if (!mapContainerRef.current) return;
                                e.preventDefault();
                                e.stopPropagation();
                                const rect = mapContainerRef.current.getBoundingClientRect();
                                const pointerWorld = screenToWorld(
                                  e.clientX - rect.left,
                                  e.clientY - rect.top,
                                  viewport
                                );
                                (e.currentTarget as SVGGElement).setPointerCapture(e.pointerId);
                                setGpsPhotoDrag({
                                  id: photo.id,
                                  offsetWorldX: pointerWorld.x - world.x,
                                  offsetWorldY: pointerWorld.y - world.y,
                                });
                                setSelectedGpsPhotoId(photo.id);
                              }}
                              onPointerMove={(e) => {
                                if (gpsPhotoDrag?.id !== photo.id || !renderBounds || !projectionMetrics || !mapContainerRef.current) return;
                                e.preventDefault();
                                e.stopPropagation();
                                const rect = mapContainerRef.current.getBoundingClientRect();
                                const pointerWorld = screenToWorld(
                                  e.clientX - rect.left,
                                  e.clientY - rect.top,
                                  viewport
                                );
                                const nextAnchor = {
                                  x: pointerWorld.x - gpsPhotoDrag.offsetWorldX,
                                  y: pointerWorld.y - gpsPhotoDrag.offsetWorldY,
                                };
                                const nextDisplay = worldPointToLatLon(nextAnchor, renderBounds, projectionMetrics);
                                setGpsPhotos((prev) =>
                                  prev.map((item) =>
                                    item.id === photo.id
                                      ? {
                                          ...item,
                                          displayLat: nextDisplay.lat,
                                          displayLon: nextDisplay.lon,
                                          displayAdjustedAt: Date.now(),
                                        }
                                      : item
                                  )
                                );
                              }}
                              onPointerUp={(e) => {
                                if (gpsPhotoDrag?.id !== photo.id) return;
                                e.preventDefault();
                                e.stopPropagation();
                                if (renderBounds && projectionMetrics && mapContainerRef.current) {
                                  const rect = mapContainerRef.current.getBoundingClientRect();
                                  const pointerWorld = screenToWorld(
                                    e.clientX - rect.left,
                                    e.clientY - rect.top,
                                    viewport
                                  );
                                  const nextAnchor = {
                                    x: pointerWorld.x - gpsPhotoDrag.offsetWorldX,
                                    y: pointerWorld.y - gpsPhotoDrag.offsetWorldY,
                                  };
                                  const nextDisplay = worldPointToLatLon(nextAnchor, renderBounds, projectionMetrics);
                                  setGpsPhotos((prev) =>
                                    prev.map((item) =>
                                      item.id === photo.id
                                        ? {
                                            ...item,
                                            displayLat: nextDisplay.lat,
                                            displayLon: nextDisplay.lon,
                                            displayAdjustedAt: Date.now(),
                                          }
                                        : item
                                    )
                                  );
                                }
                                (e.currentTarget as SVGGElement).releasePointerCapture(e.pointerId);
                                setGpsPhotoDrag(null);
                              }}
                              onPointerCancel={(e) => {
                                if (gpsPhotoDrag?.id !== photo.id) return;
                                e.stopPropagation();
                                setGpsPhotoDrag(null);
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
                                  r={radius + (isSelected || isDragging ? 2.4 : 1.6)}
                                  fill={isSelected || isDragging ? "rgba(245, 158, 11, 0.28)" : "rgba(245, 158, 11, 0.18)"}
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

                    {/* Station tooltip replaced by click-to-inspect side panel */}
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
                  const isAdjusted =
                    typeof photo.displayLat === "number" &&
                    typeof photo.displayLon === "number";
                  const displayLatText = isAdjusted ? photo.displayLat!.toFixed(6) : "--";
                  const displayLonText = isAdjusted ? photo.displayLon!.toFixed(6) : "--";

                  return (
                    <div
                      style={{
                        position: "absolute",
                        left: cardLeft,
                        top: cardTop,
                        width: cardWidth,
                        background: "rgba(2, 6, 23, 0.76)",
                        backdropFilter: "blur(18px) saturate(150%)",
                        WebkitBackdropFilter: "blur(18px) saturate(150%)",
                        border: "1px solid rgba(148, 163, 184, 0.22)",
                        borderRadius: 12,
                        boxShadow: "0 20px 45px rgba(0,0,0,0.58), 0 0 0 1px rgba(250, 204, 21, 0.08) inset",
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
                          padding: "7px 10px 6px 12px",
                          borderBottom: "1px solid rgba(148,163,184,0.16)",
                          background: "rgba(15, 23, 42, 0.46)",
                        }}
                      >
                        <div style={{ fontSize: 11, fontWeight: 800, color: "#fbbf24", letterSpacing: 0.4 }}>
                          GEOTAGGED PHOTO
                        </div>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            if (gpsPhotoDrag?.id === photo.id) setGpsPhotoDrag(null);
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
                          Original GPS: {latText}, {lonText}
                        </div>
                        <div
                          style={{
                            marginTop: 4,
                            fontSize: 11,
                            color: "#cbd5e1",
                          }}
                        >
                          Drag this marker to adjust display position. Original GPS is preserved.
                        </div>
                        {isAdjusted ? (
                          <div
                            style={{
                              marginTop: 4,
                              fontSize: 11,
                              color: "#fbbf24",
                              fontFamily: "ui-monospace, SFMono-Regular, monospace",
                            }}
                          >
                            Display: {displayLatText}, {displayLonText}
                          </div>
                        ) : null}
                        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
                          {isAdjusted ? (
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                setGpsPhotoDrag((current) => (current?.id === photo.id ? null : current));
                                setGpsPhotos((prev) =>
                                  prev.map((item) =>
                                    item.id === photo.id
                                      ? {
                                          ...item,
                                          displayLat: undefined,
                                          displayLon: undefined,
                                          displayAdjustedAt: undefined,
                                        }
                                      : item
                                  )
                                );
                              }}
                              style={{
                                fontSize: 12,
                                fontWeight: 800,
                                color: "#f1f5f9",
                                background: "rgba(15, 23, 42, 0.66)",
                                border: "1px solid rgba(255, 255, 255, 0.18)",
                                borderRadius: 8,
                                padding: "6px 10px",
                                cursor: "pointer",
                              }}
                            >
                              Reset to GPS
                            </button>
                          ) : null}
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
                  aria-hidden="true"
                  title="Scroll page"
                  style={{
                    position: "absolute",
                    top: 0,
                    right: 0,
                    width: mapScrollGutterWidth,
                    height: desktopMapHeight,
                    borderRadius: "0 18px 18px 0",
                    background: "linear-gradient(180deg, rgba(248, 250, 252, 0.82), rgba(226, 232, 240, 0.70))",
                    border: "1px solid rgba(203, 213, 225, 0.85)",
                    borderLeft: "none",
                    color: "#64748b",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 10,
                    fontWeight: 800,
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                    writingMode: "vertical-rl",
                    userSelect: "none",
                    pointerEvents: "auto",
                  }}
                >
                  Scroll
                </div>

                {/* ─── Station Inspector Panel (absolute overlay) ────── */}
                {/* Positioned absolute so the map container never resizes */}
                {selectedStation ? (
                  <div
                    style={{
                      position: "absolute",
                      top: 0,
                      right: mapScrollGutterWidth,
                      width: 276,
                      height: desktopMapHeight,
                      overflowY: "auto",
                      borderRadius: "0 18px 18px 0",
                      borderLeft: "1px solid rgba(148, 163, 184, 0.20)",
                      background: "rgba(2, 6, 23, 0.78)",
                      backdropFilter: "blur(18px) saturate(145%)",
                      WebkitBackdropFilter: "blur(18px) saturate(145%)",
                      display: "flex",
                      flexDirection: "column",
                      zIndex: 20,
                      boxShadow: "-8px 0 30px rgba(0, 0, 0, 0.34)",
                    }}
                  >
                    {/* Header */}
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        padding: "10px 14px 9px",
                        borderBottom: "1px solid rgba(148, 163, 184, 0.16)",
                        flexShrink: 0,
                      }}
                    >
                      <div>
                        <div style={{ fontSize: 11, fontWeight: 800, color: "#93c5fd", textTransform: "uppercase", letterSpacing: 0.5 }}>
                          Field Inspection
                        </div>
                        <div style={{ fontSize: 15, fontWeight: 900, color: "#f8fafc", marginTop: 2, lineHeight: 1.2 }}>
                          {cleanDisplayText(selectedStation.station)}
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => setSelectedStationIndex(null)}
                        aria-label="Close inspector"
                        style={{
                          background: "rgba(15, 23, 42, 0.72)",
                          cursor: "pointer",
                          color: "#cbd5e1",
                          fontSize: 16,
                          lineHeight: 1,
                          padding: "4px 8px",
                          borderRadius: 8,
                          border: "1px solid rgba(148, 163, 184, 0.18)",
                          flexShrink: 0,
                        }}
                      >
                        ×
                      </button>
                    </div>

                    {/* Detail rows */}
                    <div style={{ padding: "12px 14px", display: "grid", gap: 7, flexShrink: 0 }}>
                      {(
                        [
                          ["Station", cleanDisplayText(selectedStation.station)],
                          ["Mapped FT", formatNumber(selectedStation.mapped_station_ft, 3)],
                          ["Depth FT", formatNumber(selectedStation.depth_ft)],
                          ["BOC FT", formatNumber(selectedStation.boc_ft)],
                          ["Date", formatDisplayDate(selectedStation.date)],
                          ["Crew", cleanDisplayText(selectedStation.crew)],
                          ["Print", cleanDisplayText(selectedStation.print)],
                          ["Source", cleanDisplayText(selectedStation.source_file)],
                          ["Notes", cleanDisplayText(selectedStation.notes)],
                          ["Lat", formatNumber(selectedStation.lat, 6)],
                          ["Lon", formatNumber(selectedStation.lon, 6)],
                        ] as [string, string][]
                      ).map(([label, value]) => (
                        <div key={label} style={{ display: "grid", gridTemplateColumns: "80px 1fr", gap: 6, alignItems: "baseline" }}>
                          <span style={{ fontSize: 11, fontWeight: 800, color: "#94a3b8", textTransform: "uppercase", letterSpacing: 0.3 }}>
                            {label}
                          </span>
                          <span
                            style={{
                              fontSize: 12,
                              fontWeight: 600,
                              color: value === "--" ? "#64748b" : "#e2e8f0",
                              wordBreak: "break-all",
                            }}
                          >
                            {value}
                          </span>
                        </div>
                      ))}
                    </div>

                    {/* Photos */}
                    {stationPhotos.length > 0 ? (
                      <div style={{ padding: "0 14px 14px", flexShrink: 0 }}>
                        <div style={{ fontSize: 11, fontWeight: 800, color: "#64748b", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8 }}>
                          Photos ({stationPhotos.length})
                        </div>
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                          {stationPhotos.map((photo) => (
                            <a
                              key={photo.photo_id}
                              href={`${API_BASE}${photo.relative_url}`}
                              target="_blank"
                              rel="noreferrer"
                              style={{ textDecoration: "none", color: "inherit", borderRadius: 10, overflow: "hidden", border: "1px solid #e2e8f0", display: "block" }}
                            >
                              <div
                                style={{
                                  height: 72,
                                  backgroundImage: `url(${API_BASE}${photo.relative_url})`,
                                  backgroundSize: "cover",
                                  backgroundPosition: "center",
                                  backgroundColor: "#e5e7eb",
                                }}
                              />
                              <div style={{ padding: "5px 7px" }}>
                                <div style={{ fontSize: 10, fontWeight: 700, color: "#0f172a", wordBreak: "break-all", lineHeight: 1.3 }}>
                                  {photo.original_filename}
                                </div>
                              </div>
                            </a>
                          ))}
                        </div>
                      </div>
                    ) : stationPhotosLoading ? (
                      <div style={{ padding: "0 14px 14px", fontSize: 12, color: "#64748b" }}>Loading photos…</div>
                    ) : (
                      <div style={{ padding: "0 14px 14px", fontSize: 12, color: "#94a3b8" }}>No photos attached.</div>
                    )}
                  </div>
                ) : null}
              </div>
              {/* ─── End Map + Inspector wrapper ─────────────────────── */}

              {/* ─── Phase 4D: Field Submissions Inbox ───────────────────── */}
              {/* Secondary in Map tab: keep the map as the first workspace surface. */}
              <div style={{ display: activeWorkspaceTab === "map" ? "block" : "none" }}>
                <FieldSubmissionsInboxPanel
                  onSelectSession={(sessionId, jobId) => {
                    setSelectedFieldSessionId(sessionId);
                    setSelectedFieldJobId(jobId);
                  }}
                />
                {selectedFieldSessionId ? (
                  <div style={{ marginTop: 16 }}>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "flex-end",
                        marginBottom: 10,
                      }}
                    >
                      <button
                        type="button"
                        onClick={clearFieldSubmissionSelection}
                        style={{
                          padding: "6px 12px",
                          fontSize: 12,
                          fontWeight: 700,
                          borderRadius: 10,
                          border: "1px solid #cfd8e3",
                          background: "#ffffff",
                          color: "#0f172a",
                          cursor: "pointer",
                        }}
                      >
                        Clear selection
                      </button>
                    </div>
                    {selectedFieldJobLoading ? (
                      <div style={{ fontSize: 13, color: "#64748b" }}>Loading job…</div>
                    ) : null}
                    {selectedFieldJobError ? (
                      <div
                        style={{
                          border: "1px solid #fecaca",
                          background: "#fef2f2",
                          color: "#991b1b",
                          borderRadius: 12,
                          padding: "10px 12px",
                          fontSize: 13,
                        }}
                      >
                        {selectedFieldJobError}
                      </div>
                    ) : null}
                    {!selectedFieldJobLoading && !selectedFieldJobError && selectedFieldJobDetail ? (
                      <SelectedSubmissionReviewPanel
                        selectedSessionId={selectedFieldSessionId}
                        session={selectedFieldSession}
                      />
                    ) : null}
                  </div>
                ) : null}
              </div>

              <div
                style={{
                  border: "1px solid #dbe4ee",
                  borderRadius: 16,
                  background: "#ffffff",
                  padding: 16,
                  display: activeWorkspaceTab === "setup" ? "grid" : "none",
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
                  display: activeWorkspaceTab === "setup" ? "grid" : "none",
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

          <div style={{ display: activeWorkspaceTab === "reports" || activeWorkspaceTab === "billing" ? "grid" : "none", gridTemplateColumns: "1fr", gap: 18, alignItems: "start" }}>
            
<Section title="4. Reports" subtitle="Real report output built from current job data, redline sections, pricing inputs, and exception totals." style={{ display: activeWorkspaceTab === "reports" ? "block" : "none" }}>
              <div className="print-report" style={{ display: "grid", gap: 14 }}>
                <ShellCard
                  title="Field-to-billing report"
                  description="This report uses current route, redline, pricing, and exception values only. Browser print is enabled for clean export."
                >
                  <div style={{ display: "grid", gap: 8 }}>
                    <SmallRow label="Job / Route" value={activeJob} />
                    <SmallRow label="Matched route" value={selectedMatch?.route_name || state?.selected_route_name || state?.route_name || "--"} />
                    <SmallRow label="Total footage" value={`${formatNumber(effectiveFootage)} ft`} />
                    <SmallRow label="Drill paths" value={String(drillPathRows.length)} />
                    <SmallRow label="Base cost / ft" value={toMoney(numericCostPerFoot)} />
                    <SmallRow label="Exception total" value={toMoney(exceptionTotal)} />
                    <SmallRow label="Final total" value={toMoney(finalBillingTotal)} />
                  </div>
                </ShellCard>

                <ShellCard
                  title={projectCompletionSummary.plannedSource === "manual" ? "Project Completion Summary" : "As-Built Upload Summary"}
                  description={
                    projectCompletionSummary.plannedSource === "manual"
                      ? "Overall drilled progress using the engineering/material takeoff total."
                      : "Uploaded as-built footage and touched backend route scope only. This is not full project completion."
                  }
                >
                  <div style={{ display: "grid", gridTemplateColumns: projectCompletionSummary.plannedSource === "manual" ? "160px minmax(0, 1fr)" : "1fr", gap: 18, alignItems: "center" }}>
                    {projectCompletionSummary.plannedSource === "manual" ? (
                      <div
                        aria-label="Project completion"
                        style={{
                          width: 138,
                          height: 138,
                          borderRadius: "50%",
                          background:
                            projectCompletionSummary.percentComplete !== null
                              ? `conic-gradient(#16a34a 0 ${projectCompletionSummary.percentComplete}%, #e5e7eb ${projectCompletionSummary.percentComplete}% 100%)`
                              : "conic-gradient(#e5e7eb 0 100%)",
                          display: "grid",
                          placeItems: "center",
                          boxShadow: "inset 0 0 0 1px rgba(15, 23, 42, 0.08)",
                        }}
                      >
                        <div
                          style={{
                            width: 92,
                            height: 92,
                            borderRadius: "50%",
                            background: "#ffffff",
                            display: "grid",
                            placeItems: "center",
                            textAlign: "center",
                            boxShadow: "0 0 0 1px #e2e8f0",
                          }}
                        >
                          <div>
                            <div style={{ fontSize: 24, fontWeight: 900, color: "#0f172a", lineHeight: 1 }}>
                              {projectCompletionSummary.percentComplete !== null
                                ? `${formatNumber(projectCompletionSummary.percentComplete, 1)}%`
                                : "--"}
                            </div>
                            <div style={{ marginTop: 4, fontSize: 10, fontWeight: 800, color: "#64748b", textTransform: "uppercase", letterSpacing: 0.5 }}>
                              Complete
                            </div>
                          </div>
                        </div>
                      </div>
                    ) : null}
                    <div style={{ display: "grid", gap: 8 }}>
                      {projectCompletionSummary.plannedSource !== "manual" && (state?.engineering_plans?.length ?? 0) === 0 ? (
                        <div style={{ justifySelf: "start", borderRadius: 999, background: "#fef3c7", color: "#92400e", border: "1px solid #fbbf24", padding: "4px 9px", fontSize: 11, fontWeight: 900, textTransform: "uppercase", letterSpacing: 0.3 }}>
                          Enter engineering/material takeoff total to calculate full project completion.
                        </div>
                      ) : null}
                      {projectCompletionSummary.plannedSource === "manual" ? (
                        <>
                          <SmallRow label="Planned footage" value={`${formatNumber(projectCompletionSummary.plannedFootage)} ft`} />
                          <SmallRow label="Drilled/as-built footage" value={`${formatNumber(projectCompletionSummary.drilledFootage)} ft`} />
                          <SmallRow label="Remaining footage" value={`${formatNumber(projectCompletionSummary.remainingFootage)} ft`} />
                          <SmallRow
                            label="Percent complete"
                            value={
                              projectCompletionSummary.percentComplete !== null
                                ? `${formatNumber(projectCompletionSummary.percentComplete, 1)}%`
                                : "--"
                            }
                          />
                        </>
                      ) : (
                        <>
                          <SmallRow label="Uploaded as-built footage" value={`${formatNumber(projectCompletionSummary.drilledFootage)} ft`} />
                          <SmallRow
                            label="Touched design route scope"
                            value={
                              projectCompletionSummary.touchedDesignRouteScope !== null
                                ? `${formatNumber(projectCompletionSummary.touchedDesignRouteScope)} ft`
                                : "--"
                            }
                          />
                          <div style={{ fontSize: 12, color: "#64748b", fontWeight: 700 }}>
                            Touched route scope is not full project completion.
                          </div>
                        </>
                      )}
                      {projectCompletionSummary.plannedSource === "manual" ? (
                        <div style={{ marginTop: 2, fontSize: 12, color: "#64748b", fontWeight: 700 }}>
                          Source: Manual engineering total
                        </div>
                      ) : null}
                    </div>
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

            <div style={{ display: activeWorkspaceTab === "billing" ? "grid" : "none", gap: 18 }}>
              <Section title="5. Pricing / Crews / Exceptions" subtitle="Real billing controls using actual footage plus editable exception costs.">
                <div style={{ display: "grid", gap: 14 }}>
                  <ShellCard
                    title="Footage calculator"
                    description="Footage pre-fills from summed redline segments, then covered_length_ft from the backend. Leave the field blank to track detected footage live, or type your own amount for billing."
                  >
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 12 }}>
                      <label style={{ display: "grid", gap: 6, fontSize: 13, color: "#475569" }}>
                        <span>Footage (FT)</span>
                        <input
                          value={
                            manualFootage !== ""
                              ? manualFootage
                              : calculatedCoveredFootage > 0
                                ? formatNumber(calculatedCoveredFootage)
                                : ""
                          }
                          onChange={(e) => setManualFootage(e.target.value)}
                          placeholder={calculatedCoveredFootage > 0 ? undefined : "Enter footage (ft)"}
                          disabled={billingApproved}
                          style={{ borderRadius: 12, border: "1px solid #cfd8e3", padding: "10px 12px", background: billingApproved ? "#f1f5f9" : "#ffffff", fontSize: 14 }}
                        />
                      </label>
                      <label style={{ display: "grid", gap: 6, fontSize: 13, color: "#475569" }}>
                        <span>Cost per foot ($)</span>
                        <input value={costPerFoot} onChange={(e) => setCostPerFoot(e.target.value)} disabled={billingApproved} style={{ borderRadius: 12, border: "1px solid #cfd8e3", padding: "10px 12px", background: billingApproved ? "#f1f5f9" : "#ffffff", fontSize: 14 }} />
                      </label>
                      <div style={{ display: "grid", gap: 6, fontSize: 13, color: "#475569", gridColumn: "1 / -1" }}>
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
                        <div key={item.id} style={{ display: "grid", gap: 6 }}>
                          <div style={{ display: "grid", gridTemplateColumns: "1.4fr 0.8fr auto", gap: 10, alignItems: "center" }}>
                            <input value={item.label} onChange={(e) => handleExceptionChange(item.id, "label", e.target.value)} disabled={billingApproved} style={{ borderRadius: 12, border: "1px solid #cfd8e3", padding: "10px 12px", background: billingApproved ? "#f1f5f9" : "#ffffff", fontSize: 14 }} />
                            <input value={item.amount} onChange={(e) => handleExceptionChange(item.id, "amount", e.target.value)} placeholder="0.00" disabled={billingApproved} style={{ borderRadius: 12, border: "1px solid #cfd8e3", padding: "10px 12px", background: billingApproved ? "#f1f5f9" : "#ffffff", fontSize: 14 }} />
                            <button type="button" onClick={() => handleRemoveException(item.id)} disabled={billingApproved} style={buttonStyle("#ffffff", "#0f172a", "#000000", billingApproved)}>Remove</button>
                          </div>
                          <input
                            value={item.note || ""}
                            onChange={(e) => handleExceptionChange(item.id, "note", e.target.value)}
                            placeholder="Note / context (optional)"
                            disabled={billingApproved}
                            style={{ borderRadius: 8, border: "1px solid #e2e8f0", padding: "6px 10px", background: billingApproved ? "#f1f5f9" : "#f8fafc", fontSize: 12, color: "#475569" }}
                          />
                        </div>
                      ))}
                      <div style={{ display: "grid", gap: 6 }}>
                        <div style={{ display: "grid", gridTemplateColumns: "1.4fr 0.8fr auto", gap: 10, alignItems: "center" }}>
                          <input value={extraExceptionLabel} onChange={(e) => setExtraExceptionLabel(e.target.value)} placeholder="Add exception label" disabled={billingApproved} style={{ borderRadius: 12, border: "1px solid #cfd8e3", padding: "10px 12px", background: billingApproved ? "#f1f5f9" : "#ffffff", fontSize: 14 }} />
                          <input value={extraExceptionAmount} onChange={(e) => setExtraExceptionAmount(e.target.value)} placeholder="0.00" disabled={billingApproved} style={{ borderRadius: 12, border: "1px solid #cfd8e3", padding: "10px 12px", background: billingApproved ? "#f1f5f9" : "#ffffff", fontSize: 14 }} />
                          <button type="button" onClick={handleAddException} disabled={billingApproved} style={buttonStyle("#0f172a", "#ffffff", "#000000", billingApproved)}>Add</button>
                        </div>
                        <input
                          value={extraExceptionNote}
                          onChange={(e) => setExtraExceptionNote(e.target.value)}
                          placeholder="Note / context (optional)"
                          disabled={billingApproved}
                          style={{ borderRadius: 8, border: "1px solid #e2e8f0", padding: "6px 10px", background: billingApproved ? "#f1f5f9" : "#f8fafc", fontSize: 12, color: "#475569" }}
                        />
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

                  <ShellCard
                    title="Evidence checklist"
                    description="Design, bore files, and at least one field photo (station-attached or geotagged) before submit."
                  >
                    <div style={{ display: "grid", gap: 10, fontSize: 13, color: "#334155" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <span style={{ fontWeight: 800, color: hasDesign ? "#166534" : "#94a3b8", minWidth: 18 }}>{hasDesign ? "✓" : "○"}</span>
                        <span>KMZ design loaded</span>
                      </div>
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <span style={{ fontWeight: 800, color: hasBoreFiles ? "#166534" : "#94a3b8", minWidth: 18 }}>{hasBoreFiles ? "✓" : "○"}</span>
                        <span>Structured bore logs loaded</span>
                      </div>
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <span style={{ fontWeight: 800, color: stationPhotos.length > 0 || gpsPhotos.length > 0 ? "#166534" : "#94a3b8", minWidth: 18 }}>
                          {stationPhotos.length > 0 || gpsPhotos.length > 0 ? "✓" : "○"}
                        </span>
                        <span>Field photos ({stationPhotos.length} station / {gpsPhotos.length} geotagged)</span>
                      </div>
                    </div>
                  </ShellCard>

                  <ShellCard title="Approval" description="Submit billing for review, then record approval. Values above lock after approval.">
                    <div style={{ display: "grid", gap: 12 }}>
                      {billingApprovalStatus === "not_submitted" ? (
                        <>
                          <button
                            type="button"
                            onClick={() => setBillingApprovalStatus("pending")}
                            disabled={busy || !billingChecklistComplete}
                            style={{
                              ...buttonStyle("#0f172a", "#ffffff", "#000000", busy || !billingChecklistComplete),
                              justifySelf: "start",
                            }}
                          >
                            Submit for Approval
                          </button>
                          {!billingChecklistComplete ? (
                            <div style={{ fontSize: 12, color: "#64748b", lineHeight: 1.45 }}>
                              Complete every checklist item before submitting.
                            </div>
                          ) : null}
                        </>
                      ) : null}
                      {billingApprovalStatus === "pending" ? (
                        <>
                          <div style={{ fontSize: 14, fontWeight: 800, color: "#92400e" }}>Status: Pending Approval</div>
                          <button
                            type="button"
                            onClick={() => setBillingApprovalStatus("approved")}
                            disabled={busy}
                            style={{ ...buttonStyle("#0f172a", "#ffffff", "#000000", busy), justifySelf: "start" }}
                          >
                            Mark Approved
                          </button>
                        </>
                      ) : null}
                      {billingApprovalStatus === "approved" ? (
                        <div style={{ fontSize: 14, fontWeight: 800, color: "#166534" }}>Status: Approved</div>
                      ) : null}
                    </div>
                  </ShellCard>
                </div>
              </Section>

              <Section title="6. Export / Print" subtitle="Opens a clean print-only report — use browser Save as PDF for a file.">
                <div style={{ display: "grid", gap: 14 }}>
                  <ShellCard
                    title="Closeout Packet V1"
                    description="Generate a structured closeout packet from existing job data — bore logs, QA flags, overrides, billing, and plan evidence. Preview in-browser, then Print / Save as PDF."
                  >
                    <CloseoutPacket
                      activeJob={activeJob}
                      state={state}
                      selectedMatch={selectedMatch}
                      projectCompletionPercent={projectCompletionSummary.percentComplete}
                      effectiveFootage={effectiveFootage}
                      numericCostPerFoot={numericCostPerFoot}
                      baseBillingTotal={baseBillingTotal}
                      exceptionTotal={exceptionTotal}
                      finalBillingTotal={finalBillingTotal}
                      exceptions={exceptions}
                      drillPathRows={drillPathRows}
                      novaSummary={novaSummary}
                      pipelineDiag={pipelineDiag}
                      engineeringPlanSignals={engineeringPlanSignals}
                      hasDesign={hasDesign}
                      hasBoreFiles={hasBoreFiles}
                      hasGeneratedOutput={hasGeneratedOutput}
                      notes={notes}
                      stationPhotos={stationPhotos}
                      geoTaggedPhotos={gpsPhotos.map((p) => ({
                        id: p.id,
                        filename: p.filename,
                        lat: p.lat,
                        lon: p.lon,
                        reason: p.reason,
                        addedAt: p.addedAt,
                        previewUrl: p.previewUrl,
                      }))}
                    />
                  </ShellCard>
                  <ShellCard
                    title="Print / export report"
                    description="Use browser print to create a clean printed report or Save as PDF from the browser print dialog."
                  >
                    <div className="no-print" style={{ display: "grid", gap: 10 }}>
                      <button onClick={handleExportKml} style={{ ...buttonStyle("#ffffff", "#0f172a", "#cfd8e3", false), width: "100%" }}>
                        Export to Google Earth (KML)
                      </button>
                      <button onClick={handlePrintReport} style={{ ...buttonStyle("#0f172a", "#ffffff", "#000000", false), width: "100%" }}>
                        Print / Export Report
                      </button>
                    </div>
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

      {/* ── Print-only report ── rendered in DOM always, visible only in @media print ── */}
      <div id="osp-print-report">
        {/* Header */}
        <h1>OSP Redlining Field Report</h1>
        <div className="rpt-meta">
          {activeJob !== "--" ? <><strong>Job:</strong>{" "}{activeJob}{" "}</> : null}
          {(state?.selected_route_name || state?.route_name) ? (
            <><strong>Route:</strong>{" "}{state?.selected_route_name || state?.route_name}{" "}</>
          ) : null}
          <strong>Generated:</strong> {new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })}
        </div>

        {/* KPI summary row */}
        <div className="rpt-kpi-row">
          <div className="rpt-kpi">
            <div className="rpt-kpi-label">Total Footage</div>
            <div className="rpt-kpi-value">{formatNumber(effectiveFootage)} ft</div>
          </div>
          <div className="rpt-kpi">
            <div className="rpt-kpi-label">Project completion</div>
            <div className="rpt-kpi-value">
              {projectCompletionSummary.percentComplete !== null
                ? `${formatNumber(projectCompletionSummary.percentComplete, 1)}%`
                : "--"}
            </div>
          </div>
          <div className="rpt-kpi">
            <div className="rpt-kpi-label">Drill Paths</div>
            <div className="rpt-kpi-value">{drillPathRows.length}</div>
          </div>
          <div className="rpt-kpi">
            <div className="rpt-kpi-label">Final Billing</div>
            <div className="rpt-kpi-value">{toMoney(finalBillingTotal)}</div>
          </div>
        </div>

        {/* Drill path summary */}
        {drillPathRows.length > 0 && (
          <>
            <h2>Drill Path Summary</h2>
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Route</th>
                  <th>Print</th>
                  <th>Start Station</th>
                  <th>End Station</th>
                  <th>Length (ft)</th>
                  <th>Cost</th>
                  <th>Source File</th>
                </tr>
              </thead>
              <tbody>
                {drillPathRows.map((row, i) => (
                  <tr key={row.id}>
                    <td>{i + 1}</td>
                    <td>{row.routeName}</td>
                    <td>{row.print}</td>
                    <td>{row.startStation}</td>
                    <td>{row.endStation}</td>
                    <td>{formatNumber(row.lengthFt)}</td>
                    <td>{toMoney(row.cost)}</td>
                    <td style={{ fontSize: 10, wordBreak: "break-all" }}>{row.sourceFile}</td>
                  </tr>
                ))}
                <tr className="rpt-total-row">
                  <td colSpan={5} style={{ textAlign: "right" }}>Total</td>
                  <td>{formatNumber(drillPathRows.reduce((s, r) => s + r.lengthFt, 0))}</td>
                  <td>{toMoney(drillPathRows.reduce((s, r) => s + r.cost, 0))}</td>
                  <td></td>
                </tr>
              </tbody>
            </table>
          </>
        )}

        {/* Bore log reference line */}
        {(state?.bore_log_summary?.length ?? 0) > 0 && (
          <p style={{ margin: "0 0 12px 0", fontSize: 13, color: "#475569" }}>
            Source bore logs reviewed: <strong>{state!.bore_log_summary!.length} {state!.bore_log_summary!.length === 1 ? "file" : "files"}</strong>
          </p>
        )}

        {/* Billing summary */}
        <h2>Billing Summary</h2>
        <table>
          <tbody>
            <tr><td style={{ fontWeight: 600 }}>Footage used</td><td>{formatNumber(effectiveFootage)} ft</td></tr>
            <tr><td style={{ fontWeight: 600 }}>Cost per foot</td><td>{toMoney(numericCostPerFoot)}</td></tr>
            <tr><td style={{ fontWeight: 600 }}>Base total</td><td>{toMoney(baseBillingTotal)}</td></tr>
          </tbody>
        </table>

        {/* Exceptions */}
        {exceptions.filter(e => e.amount.trim() && Number.parseFloat(e.amount) !== 0).length > 0 && (
          <>
            <h2>Exceptions</h2>
            <table>
              <thead>
                <tr><th>Label</th><th>Amount</th></tr>
              </thead>
              <tbody>
                {exceptions
                  .filter(e => e.amount.trim() && Number.isFinite(Number.parseFloat(e.amount)))
                  .map(e => (
                    <tr key={e.id}>
                      <td>
                        {e.label}
                        {e.note && (
                          <div style={{ fontSize: "0.82em", color: "#64748b", fontStyle: "italic", marginTop: 2 }}>{e.note}</div>
                        )}
                      </td>
                      <td>{toMoney(Number.parseFloat(e.amount))}</td>
                    </tr>
                  ))}
                <tr className="rpt-total-row">
                  <td>Exception Total</td>
                  <td>{toMoney(exceptionTotal)}</td>
                </tr>
              </tbody>
            </table>
          </>
        )}

        {/* Final billing */}
        <table style={{ marginTop: 8 }}>
          <tbody>
            <tr className="rpt-total-row">
              <td style={{ fontWeight: 800, fontSize: 14 }}>Final Billing Total</td>
              <td style={{ fontWeight: 800, fontSize: 14 }}>{toMoney(finalBillingTotal)}</td>
            </tr>
          </tbody>
        </table>

        {/* Operator notes */}
        {notes.trim() && (
          <>
            <h2>Operator Notes</h2>
            <div className="rpt-notes">{notes.trim()}</div>
          </>
        )}

        {/* Footer */}
        <div className="rpt-footer">
          <span>
            {workspaceTitle?.trim()
              ? `${workspaceTitle.trim()} — Field Report`
              : "OSP Redlining Operator Workspace — Field Report"}
          </span>
          <span>{new Date().toISOString().slice(0, 10)}</span>
        </div>
      </div>
    </div>
  );
}

export default function RedlineMap({ mode = "default", projectId, workspaceTitle }: RedlineMapProps) {
  if (mode === "mobileWalk") {
    return <MobileWalkContainer />;
  }
  return <OfficeRedlineMapInner mode={mode} projectId={projectId} workspaceTitle={workspaceTitle} />;
}
