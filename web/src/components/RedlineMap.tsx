"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { strToU8, unzipSync, zipSync } from "fflate";
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
  SemanticKmz,
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
import FieldSubmissionsInboxPanel from "@/components/office/FieldSubmissionsInboxPanel";
import SelectedSubmissionReviewPanel from "@/components/office/SelectedSubmissionReviewPanel";
import { buildSessionPacketHtml } from "@/lib/office/sessionPacketHtml";
import { useSessionReview, useSessionReviewNote } from "@/lib/office/sessionReview";
import SessionPhotoGalleryModal, {
  sortPhotosByUploadedDesc,
  type SessionPhotoGallery,
} from "@/components/office/SessionPhotoGalleryModal";
import { getJobById } from "@/lib/api";
import type { JobDetail, Photo } from "@/lib/api";
import { clamp, formatNumber, cleanDisplayText, formatDisplayDate } from "@/lib/format/text";
import { toMoney } from "@/lib/format/money";
import { extractGps } from "@/lib/photos/exif";
import { acceptSessionFromMutation, appendSessionId, appendSessionIdReadOnly, appendSessionIdToForm, getStoredSessionId, peekSessionId } from "@/lib/session";
import { apiFetch } from "@/lib/apiFetch";
// PT.IU R3 — token-presence helpers for the upload diagnostic panel.
// Read-only boolean checks; token VALUES are never displayed.
import { getAccessToken } from "@/lib/accessToken";
import { getPilotToken } from "@/lib/pilotToken";
import type { PipelineDiagEntry, EngineeringPlanSignal, QaFlagItem } from "@/lib/types/nova";
import { buildNovaSummary } from "@/lib/nova/buildNovaSummary";
import CloseoutPacket from "@/components/CloseoutPacket";

const API_BASE = "";

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

/** Closest point on segment plus clamped segment parameter t ∈ [0,1]. */
function closestPointWithTOnSegment(
  lat: number,
  lon: number,
  a: number[],
  b: number[],
): { lat: number; lon: number; t: number } {
  const alat = a[0];
  const alon = a[1];
  const blat = b[0];
  const blon = b[1];
  const dlat = blat - alat;
  const dlon = blon - alon;
  const len2 = dlat * dlat + dlon * dlon;
  if (len2 < 1e-20) return { lat: alat, lon: alon, t: 0 };
  let t = ((lat - alat) * dlat + (lon - alon) * dlon) / len2;
  t = Math.max(0, Math.min(1, t));
  return { lat: alat + t * dlat, lon: alon + t * dlon, t };
}

/**
 * Arc length from the start of the winning KMZ polyline to the snapped point (planar lat/lon).
 * Tie-break: smallest perpendicular distance² to segment chooses the segment.
 */
function distanceAlongPolylinesFromSnappedPoint(
  snapLat: number,
  snapLon: number,
  polylines: number[][][],
): { polyIdx: number; distAlong: number } {
  if (!Number.isFinite(snapLat) || !Number.isFinite(snapLon) || polylines.length === 0) {
    return { polyIdx: 0, distAlong: 0 };
  }
  let bestMetric = Infinity;
  let bestPoly = 0;
  let bestAlong = 0;
  for (let pi = 0; pi < polylines.length; pi++) {
    const line = polylines[pi];
    let cumulative = 0;
    for (let i = 0; i < line.length - 1; i++) {
      const a = line[i];
      const b = line[i + 1];
      const slat = b[0] - a[0];
      const slon = b[1] - a[1];
      const segLen = Math.sqrt(slat * slat + slon * slon);
      const { lat: clat, lon: clon, t } = closestPointWithTOnSegment(snapLat, snapLon, a, b);
      const d2 = (clat - snapLat) ** 2 + (clon - snapLon) ** 2;
      if (d2 < bestMetric) {
        bestMetric = d2;
        bestPoly = pi;
        bestAlong = cumulative + t * segLen;
      }
      cumulative += segLen;
    }
  }
  return { polyIdx: bestPoly, distAlong: bestAlong };
}

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

/** Prefer API `mapped_station_ft` when numeric; else chainage from `station_number` (e.g. 00+46 → 46). */
function fieldStationFtFromRow(st: { station_number: string; mapped_station_ft?: unknown }): number {
  const m = (st as { mapped_station_ft?: number }).mapped_station_ft;
  if (typeof m === "number" && Number.isFinite(m)) {
    return m;
  }
  const [major, minor] = String(st.station_number).split("+");
  const v = (parseInt(major ?? "0", 10) * 100) + parseInt(minor ?? "0", 10);
  return Number.isFinite(v) ? v : NaN;
}

/** Point at `distanceFt` along concatenated polylines (0 = start of first polyline). */
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

/** [lat, lon] points along concatenated KMZ polylines from startFt to endFt (haversine ft), inclusive. */
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
  if (totalFt <= 0) {
    return [];
  }
  let s = Math.max(0, Math.min(startFt, totalFt));
  let e = Math.max(0, Math.min(endFt, totalFt));
  if (s > e) {
    const tmp = s;
    s = e;
    e = tmp;
  }
  if (e - s < 1e-9) {
    return [];
  }
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
      if (e <= segStart) {
        return out;
      }
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
      if (t1 - t0 > 1e-12) {
        addPt(lat1, lon1);
      }
      cum = segEnd;
      if (cum >= e - 1e-9) {
        return out;
      }
    }
  }
  return out;
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

// Phase 2C — blend any KMZ source hex ~55% toward slate-400 (#94a3b8) to kill
// neon KML saturation while preserving hue identity. Pure function, never throws.
function muteKmzColor(hex: string | null | undefined): string {
  const fallback = "#7c8da6";
  if (!hex || !/^#[0-9a-fA-F]{6}$/.test(hex)) return fallback;
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  const mr = Math.round(r * 0.55 + 148 * 0.45);
  const mg = Math.round(g * 0.55 + 163 * 0.45);
  const mb = Math.round(b * 0.55 + 184 * 0.45);
  return `#${mr.toString(16).padStart(2, "0")}${mg.toString(16).padStart(2, "0")}${mb.toString(16).padStart(2, "0")}`;
}

function escapeXml(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

/** Google Earth: HTML description table; labels and cell text are entity-escaped. */
function kmlDescriptionTable(rows: Array<{ label: string; value: string }>): string {
  const body = rows
    .map(
      (r) =>
        `<tr><td><strong>${escapeXml(r.label)}</strong></td><td>${escapeXml(r.value)}</td></tr>`,
    )
    .join("");
  const html = `<table border="1" cellspacing="0" cellpadding="4"><tbody>${body}</tbody></table>`;
  const safe = html.replace(/\]\]>/g, "]]]]><![CDATA[>");
  return `<![CDATA[${safe}]]>`;
}

function kmlStationFtSlashMapped(stationFt: string, mappedFt: string): string {
  if (stationFt === "--" && mappedFt === "--") return "--";
  return `${stationFt} / ${mappedFt}`;
}

function kmlLatLonCells(lat: unknown, lon: unknown): { lat: string; lon: string } {
  const lt = typeof lat === "number" ? lat : NaN;
  const ln = typeof lon === "number" ? lon : NaN;
  return {
    lat: Number.isFinite(lt) ? lt.toFixed(8) : "--",
    lon: Number.isFinite(ln) ? ln.toFixed(8) : "--",
  };
}

function kmlFieldJobRouteJob(detail: JobDetail | null): string {
  if (!detail) return "--";
  const code = cleanDisplayText(detail.job_code);
  const name = cleanDisplayText(detail.job_name);
  if (code !== "--" && name !== "--") return `${code} — ${name}`;
  if (code !== "--") return code;
  if (name !== "--") return name;
  return cleanDisplayText(detail.id);
}

function kmlSessionPhotoCountForStation(
  photos: readonly Photo[],
  sessionId: string,
  stationLabelNorm: string,
): string {
  if (!photos.length || !stationLabelNorm) return "--";
  const n = photos.filter(
    (p) =>
      String(p.session_id ?? "") === sessionId &&
      String(p.station_label ?? "").trim() === stationLabelNorm,
  ).length;
  return String(n);
}

function kmlSessionPhotoNotesForStation(
  photos: readonly Photo[],
  sessionId: string,
  stationLabelNorm: string,
): string {
  if (!photos.length || !stationLabelNorm) return "--";
  const parts = photos
    .filter(
      (p) =>
        String(p.session_id ?? "") === sessionId &&
        String(p.station_label ?? "").trim() === stationLabelNorm,
    )
    .map((p) => (p.note ?? "").trim())
    .filter(Boolean);
  return parts.length ? parts.join("; ") : "--";
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

export type BridgedGpsPhoto = {
  id: string;
  filename: string;
  previewUrl: string;
  lat: number | null;
  lon: number | null;
  displayLat?: number;
  displayLon?: number;
  contentType?: string;
  reason?: "mapped" | "no_gps" | "unreadable";
  addedAt?: number;
};

type RedlineMapProps = {
  projectId?: string;
  /** When set (e.g. project route), replaces the generic operator workspace title. */
  workspaceTitle?: string;
  /** Optional project flavor; `fiber_pull` shows a non-interactive placeholder in the inspector until data is wired. */
  projectType?: string | null;
  /** Bridge for sibling components (e.g. ModernHeroMap) that need to mirror the
   *  inbox's selected field submission. Fires whenever the internal
   *  selectedFieldSessionId / selectedFieldJobId pair changes. Optional — when
   *  omitted, behavior is unchanged. */
  onFieldSelectionChange?: (selection: {
    sessionId: string | null;
    jobId: string | null;
  }) => void;
  /** Fires after a successful KMZ/design upload (and any other workspace state
   *  mutation we route through here) so a sibling component like ModernHeroMap
   *  can refetch /api/current-state without the user pressing Refresh State. */
  onWorkspaceStateChanged?: () => void;
  /** Fires whenever the client-side geotagged photos change. Payload is a
   *  sanitized array (no File objects) for passing to sibling components like
   *  ModernHeroMap. Optional — omit to ignore. */
  onGpsPhotosChange?: (photos: BridgedGpsPhoto[]) => void;
  /** Fires whenever the hydrated kmz_semantic changes (e.g. after KMZ upload or
   *  state refresh). Forwards the already-parsed semantic object so a sibling
   *  component like ModernHeroMap can pre-fetch the render payload without an
   *  extra current-state round-trip. Optional — omit to ignore. */
  onKmzSemanticChange?: (semantic: SemanticKmz | null) => void;
  /** Primary operational map (e.g. ModernHeroMap) rendered after uploads / geotagged
   *  tooling and before the legacy SVG surface. Optional — omit for legacy-only layout. */
  operationalMap?: React.ReactNode;
};

type WorkspaceTab = "workspace" | "closeout";

type BoreLogRow = {
  station: string;
  station_ft: number;
  depth_ft: number | null;
  boc_ft: number | null;
  notes: string;
  photo_count: number;
  timestamp: string | null;
};

const boreLogTh: React.CSSProperties = {
  textAlign: "left",
  padding: "6px 8px",
  borderBottom: "1px solid #e2e8f0",
  fontSize: 11,
  fontWeight: 700,
  textTransform: "uppercase",
  letterSpacing: 0.04,
  color: "#64748b",
  whiteSpace: "nowrap",
};

const boreLogTd: React.CSSProperties = {
  padding: "6px 8px",
  verticalAlign: "top",
  color: "#0f172a",
};

/** RFC 4180-style CSV cell: quote when needed; null/undefined → empty field. */
function csvEscapeCell(value: unknown): string {
  if (value == null) return "";
  const s = String(value);
  if (/[",\r\n]/.test(s)) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

type BillingApprovalStatus = "not_submitted" | "pending" | "approved";

const WORKSPACE_TABS: Array<{ id: WorkspaceTab; label: string }> = [
  { id: "workspace", label: "Workspace" },
  { id: "closeout", label: "Closeout" },
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

function OfficeRedlineMapInner({
  projectId,
  workspaceTitle,
  projectType = null,
  onFieldSelectionChange,
  onWorkspaceStateChanged,
  onGpsPhotosChange,
  onKmzSemanticChange,
  operationalMap,
}: RedlineMapProps) {
  const [activeWorkspaceTab, setActiveWorkspaceTab] = useState<WorkspaceTab>("workspace");
  const [state, setState] = useState<BackendState | null>(null);
  const [busy, setBusy] = useState(false);
  const [statusTone, setStatusTone] = useState<NoteTone>("neutral");
  const [statusText, setStatusText] = useState("Connecting to local beta backend...");

  // PT.IU R2 — operator-visible diagnostic for the engineering-plan PDF upload
  // flow. Mirrors the 5 structured `[eng-plan-upload]` console events into
  // visible UI so failures (CORS, missing NEXT_PUBLIC_API_BASE, JWT, 413, 500)
  // are diagnosable without DevTools. The panel renders adjacent to the
  // Upload button below; only the most recent event is shown.
  //
  // PT.IU R3 — extended with browser/runtime context (origin, href, UA,
  // build-time NEXT_PUBLIC_API_BASE, token-presence boolean, planned request
  // header names, failure_class heuristic) plus a manual probe button result.
  // None of these expose token values. The probe button fires a real
  // direct-to-Render GET via apiFetch so the operator can see — from inside
  // the actual browser context — whether the cross-origin/preflight/auth path
  // works for a non-upload request.
  type EngUploadProbeResult =
    | { state: "probing"; ts: string }
    | { state: "ok"; ts: string; status: number; elapsed_ms: number }
    | { state: "http_error"; ts: string; status: number; elapsed_ms: number; body_snippet?: string }
    | { state: "exception"; ts: string; message: string; elapsed_ms: number };
  type EngUploadDiag = {
    event:
      | "upload_start"
      | "upload_success"
      | "upload_failed"
      | "non_json_response"
      | "upload_exception";
    ts: string;
    direct_to_render?: boolean;
    target?: string;
    file_count?: number;
    total_mb?: number;
    status?: number;
    backend_error?: string;
    body_snippet?: string;
    message?: string;
    uploaded_count?: number;
    elapsed_ms?: number;
    // PT.IU R3 — browser / runtime context
    origin?: string;
    href?: string;
    user_agent_short?: string;
    next_public_api_base?: string;
    access_token_present?: boolean;
    request_header_names?: string[];
    // PT.IU R3 — failure-class heuristic computed in upload_exception
    failure_class?:
      | "likely_cors_or_network_or_browser_blocked"
      | "likely_timeout_or_abort"
      | "likely_offline"
      | "other";
    // PT.IU R3 — in-page probe result (manual button)
    probe_result?: EngUploadProbeResult;
  };
  const [engUploadDiag, setEngUploadDiag] = useState<EngUploadDiag | null>(null);

  // PT.IU R3 — capture build-time + browser/runtime context the diagnostic
  // panel renders. All read-only; nothing here reads token VALUES.
  function _engUploadEnvSnapshot() {
    if (typeof window === "undefined") {
      return {
        origin: "(ssr)",
        href: "(ssr)",
        user_agent_short: "(ssr)",
        next_public_api_base:
          process.env.NEXT_PUBLIC_API_BASE ||
          process.env.NEXT_PUBLIC_API_BASE_URL ||
          "(unset)",
        access_token_present: false,
        request_header_names: [] as string[],
      };
    }
    const accessToken = getAccessToken();
    const pilotToken = !accessToken ? getPilotToken() : null;
    const tokenPresent = Boolean(accessToken) || Boolean(pilotToken);
    const headerNames: string[] = [];
    if (tokenPresent) headerNames.push("authorization");
    headerNames.push("x-tl-request-id");
    headerNames.push("content-type (auto: multipart/form-data; boundary=...)");
    const ua = (window.navigator && window.navigator.userAgent) || "";
    return {
      origin: window.location.origin,
      href: window.location.href,
      user_agent_short: ua.length > 140 ? ua.slice(0, 137) + "..." : ua,
      next_public_api_base:
        process.env.NEXT_PUBLIC_API_BASE ||
        process.env.NEXT_PUBLIC_API_BASE_URL ||
        "(unset)",
      access_token_present: tokenPresent,
      request_header_names: headerNames,
    };
  }

  // PT.IU R3 — heuristic classifier for the upload_exception path. Pure
  // text-pattern matching on the thrown error message; raw message is still
  // displayed alongside the class.
  function _classifyUploadException(error: unknown): EngUploadDiag["failure_class"] {
    const msg = error instanceof Error ? error.message : String(error || "");
    if (/failed to fetch|networkerror|load failed/i.test(msg)) {
      return "likely_cors_or_network_or_browser_blocked";
    }
    if (/timeout|timed out|aborted/i.test(msg)) {
      return "likely_timeout_or_abort";
    }
    if (/offline|disconnected/i.test(msg)) {
      return "likely_offline";
    }
    return "other";
  }

  // PT.IU R3 — manual probe button handler. Fires a direct-to-Render GET
  // against /api/current-state through apiFetch so the operator can see —
  // from inside the same browser context the upload uses — whether the
  // cross-origin + JWT + preflight (via x-tl-request-id custom header) path
  // is healthy for a non-upload request. Result is written into
  // engUploadDiag.probe_result; original event/start fields are preserved
  // so the panel keeps showing what the operator was diagnosing.
  async function handleEngUploadProbe() {
    const env = _engUploadEnvSnapshot();
    const renderBase = (env.next_public_api_base === "(unset)" ? "" : env.next_public_api_base).replace(/\/+$/, "");
    if (!renderBase) {
      // Caller would have no direct-to-Render path to probe — surface that.
      setEngUploadDiag((prev) => ({
        ...(prev ?? { event: "upload_exception", ts: new Date().toISOString() }),
        ...env,
        probe_result: {
          state: "exception",
          ts: new Date().toISOString(),
          message:
            "NEXT_PUBLIC_API_BASE is not set in this build — no direct-to-Render base to probe.",
          elapsed_ms: 0,
        },
      }));
      return;
    }
    const probeUrl = `${renderBase}/api/current-state`;
    setEngUploadDiag((prev) => ({
      ...(prev ?? { event: "upload_start", ts: new Date().toISOString() }),
      ...env,
      probe_result: { state: "probing", ts: new Date().toISOString() },
    }));
    const startedAt = Date.now();
    try {
      const resp = await apiFetch(probeUrl, { method: "GET" });
      const elapsed = Date.now() - startedAt;
      if (resp.ok) {
        setEngUploadDiag((prev) => ({
          ...(prev ?? { event: "upload_start", ts: new Date().toISOString() }),
          ...env,
          probe_result: {
            state: "ok",
            ts: new Date().toISOString(),
            status: resp.status,
            elapsed_ms: elapsed,
          },
        }));
      } else {
        const txt = await resp.text().catch(() => "");
        const snippet = txt.slice(0, 200).trim();
        setEngUploadDiag((prev) => ({
          ...(prev ?? { event: "upload_start", ts: new Date().toISOString() }),
          ...env,
          probe_result: {
            state: "http_error",
            ts: new Date().toISOString(),
            status: resp.status,
            elapsed_ms: elapsed,
            body_snippet: snippet || undefined,
          },
        }));
      }
    } catch (error) {
      const elapsed = Date.now() - startedAt;
      setEngUploadDiag((prev) => ({
        ...(prev ?? { event: "upload_start", ts: new Date().toISOString() }),
        ...env,
        probe_result: {
          state: "exception",
          ts: new Date().toISOString(),
          message: error instanceof Error ? error.message : String(error || "(unknown)"),
          elapsed_ms: elapsed,
        },
      }));
    }
  }
  const [jobLabel, setJobLabel] = useState("");
  const [notes, setNotes] = useState("");
  const [operatorNotesNotRequired, setOperatorNotesNotRequired] = useState(false);
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
  const [engineeringPlansExpanded, setEngineeringPlansExpanded] = useState(false);
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
  const [layerRoutes, setLayerRoutes] = useState(true);
  const [layerStructures, setLayerStructures] = useState(true);
  const [layerPhotos, setLayerPhotos] = useState(true);
  // Phase 1X — reviewed snap preview overlay. OFF by default. Advisory only.
  // Never mutates operational geometry. Not persisted to localStorage.
  const [layerSnapPreview, setLayerSnapPreview] = useState(false);
  const [snapPreviewData, setSnapPreviewData] = useState<import("@/lib/types/backend").ReviewedSnapPreviewResponse | null>(null);
  // Phase 2A — KMZ engineering context layer. OFF by default. Advisory/display only.
  // Never mutates operational geometry or matching state.
  const [layerKmzContext, setLayerKmzContext] = useState(false);
  const [kmzRenderPayload, setKmzRenderPayload] = useState<import("@/lib/types/backend").KmzRenderPayloadResponse | null>(null);
  // Phase 2D — selected KMZ feature for info popup. Read-only. No operational impact.
  type SelectedKmzFeature = {
    feature_id: string;
    feature_type: "point" | "line" | "polygon";
    name?: string;
    classification?: string;
    folder_path?: string[];
    description?: string;
    extended_data?: Record<string, string>;
    chainage_ft?: number | null;
    sequence_number?: string | null;
    sequence_kind?: string | null;
    lifecycle?: { label: string; confidence: string; reason: string } | null;
  };
  const [selectedKmzFeature, setSelectedKmzFeature] = useState<SelectedKmzFeature | null>(null);
  // Phase 2E — KMZ folder/category visibility toggles. Local state only. No backend impact.
  const [kmzHiddenCategories, setKmzHiddenCategories] = useState<Set<string>>(new Set());
  const [mapBaseStyle, setMapBaseStyle] = useState<"standard" | "satellite">("satellite");
  const [showPlannedRouteHighlight, setShowPlannedRouteHighlight] = useState(false);
  const [presentationView, setPresentationView] = useState(false);
  const [showLegacyMap, setShowLegacyMap] = useState(false);
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
  // F7b — non-KML assets (icons, images) extracted from the most recently
  // uploaded source KMZ. Populated in handleDesignUpload, consumed in
  // handleExportEngineeringKml. In-memory only; lost on reload.
  const kmzAssetsRef = useRef<Map<string, Uint8Array>>(new Map());
  const fieldInboxRefreshRef = useRef<(() => void) | null>(null);

  const [selectedFieldSessionId, setSelectedFieldSessionId] = useState<string | null>(null);
  const [selectedFieldJobId, setSelectedFieldJobId] = useState<string | null>(null);
  const [selectedFieldJobDetail, setSelectedFieldJobDetail] = useState<JobDetail | null>(null);
  const [selectedFieldJobLoading, setSelectedFieldJobLoading] = useState(false);
  const [selectedFieldJobError, setSelectedFieldJobError] = useState<string | null>(null);
  const [selectedFieldGallery, setSelectedFieldGallery] =
    useState<SessionPhotoGallery | null>(null);
  const [boreLogRows, setBoreLogRows] = useState<BoreLogRow[] | null>(null);
  const [boreLogLoading, setBoreLogLoading] = useState(false);
  const [boreLogError, setBoreLogError] = useState<string | null>(null);
  const [engExportError, setEngExportError] = useState<string | null>(null);
  const [fieldReviewPhotosOpen, setFieldReviewPhotosOpen] = useState(false);
  const [fieldReviewBoreOpen, setFieldReviewBoreOpen] = useState(false);
  const [showFieldGpsEvidenceTrail, setShowFieldGpsEvidenceTrail] = useState(false);
  const [selectedFieldStationIdx, setSelectedFieldStationIdx] = useState<number | null>(null);
  const [hoverFieldStationIdx, setHoverFieldStationIdx] = useState<number | null>(null);

  const selectedFieldSession = useMemo(() => {
    if (!selectedFieldSessionId || !selectedFieldJobDetail) return null;
    return (
      (selectedFieldJobDetail.sessions ?? []).find((s) => s.id === selectedFieldSessionId) ??
      null
    );
  }, [selectedFieldSessionId, selectedFieldJobDetail]);

  const { status: fieldSubmissionReviewStatus } = useSessionReview(selectedFieldSessionId);
  const { note: fieldSubmissionReviewNote } = useSessionReviewNote(selectedFieldSessionId);

  const isFiberPullWorkspace = useMemo(() => {
    const fromJob = String(selectedFieldJobDetail?.project_type ?? "").toLowerCase() === "fiber_pull";
    const fromProp = String(projectType ?? "").trim().toLowerCase() === "fiber_pull";
    return fromJob || fromProp;
  }, [selectedFieldJobDetail?.project_type, projectType]);

  const clearFieldSubmissionSelection = useCallback(() => {
    setSelectedFieldSessionId(null);
    setSelectedFieldJobId(null);
    setSelectedFieldJobDetail(null);
    setSelectedFieldJobError(null);
    setSelectedFieldJobLoading(false);
    setSelectedFieldGallery(null);
    setBoreLogRows(null);
    setBoreLogError(null);
    setBoreLogLoading(false);
    setShowFieldGpsEvidenceTrail(false);
  }, []);

  // Close any open gallery and discard cached bore-log rows when the user
  // switches to a different submission so neither shows stale data from the
  // previous selection.
  useEffect(() => {
    setSelectedFieldGallery(null);
    setBoreLogRows(null);
    setBoreLogError(null);
    setBoreLogLoading(false);
    setFieldReviewPhotosOpen(false);
    setFieldReviewBoreOpen(false);
    setShowFieldGpsEvidenceTrail(false);
    setSelectedFieldStationIdx(null);
    setHoverFieldStationIdx(null);
  }, [selectedFieldSessionId]);

  const handlePrintSessionPacket = useCallback(() => {
    const session = selectedFieldSession;
    const job = selectedFieldJobDetail;
    const sid = selectedFieldSessionId?.trim();
    if (!session || !job || !sid) return;

    const jobLabel =
      job.job_code && job.job_name
        ? `${job.job_code} — ${job.job_name}`
        : job.job_name || job.job_code || job.id;

    const sessionPhotos = (job.photos ?? []).filter(
      (p) => String(p.session_id ?? "") === sid,
    );

    const html = buildSessionPacketHtml({
      jobLabel,
      session,
      boreLogRows: boreLogRows ?? [],
      photos: sessionPhotos,
      reviewerNote: fieldSubmissionReviewNote,
      reviewStatus: fieldSubmissionReviewStatus,
      apiBase: API_BASE,
    });

    const printWin = window.open("", "_blank");
    if (!printWin) return;
    printWin.document.open();
    printWin.document.write(html);
    printWin.document.close();
    setTimeout(() => {
      try {
        printWin.focus();
        printWin.print();
      } catch {
        /* ignore */
      }
    }, 400);
  }, [
    API_BASE,
    boreLogRows,
    fieldSubmissionReviewNote,
    fieldSubmissionReviewStatus,
    selectedFieldJobDetail,
    selectedFieldSession,
    selectedFieldSessionId,
  ]);

  const handleLoadBoreLog = useCallback(async () => {
    const sid = selectedFieldSessionId;
    if (!sid) return;
    setBoreLogLoading(true);
    setBoreLogError(null);
    try {
      const res = await apiFetch(
        `${API_BASE}/api/walk-sessions/${encodeURIComponent(sid)}/bore-log`,
        { cache: "no-store" },
      );
      if (!res.ok) {
        throw new Error(`Field data fetch failed: ${res.status} ${res.statusText}`);
      }
      const data = (await res.json()) as BoreLogRow[];
      setBoreLogRows(Array.isArray(data) ? data : []);
    } catch (e) {
      setBoreLogError(e instanceof Error ? e.message : String(e));
    } finally {
      setBoreLogLoading(false);
    }
  }, [selectedFieldSessionId]);

  const handleExportBoreLogCsv = useCallback(() => {
    if (!boreLogRows || boreLogRows.length === 0 || !selectedFieldSessionId?.trim()) return;
    const header =
      "station,station_ft,depth_ft,boc_ft,notes,photo_count,timestamp";
    const lines = boreLogRows.map((r) =>
      [
        csvEscapeCell(r.station),
        csvEscapeCell(r.station_ft),
        csvEscapeCell(r.depth_ft),
        csvEscapeCell(r.boc_ft),
        csvEscapeCell(r.notes),
        csvEscapeCell(r.photo_count),
        csvEscapeCell(r.timestamp),
      ].join(","),
    );
    const csv = [header, ...lines].join("\r\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `bore_log_${selectedFieldSessionId}.csv`;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }, [boreLogRows, selectedFieldSessionId]);

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

  // Bridge: notify parent when the inbox-driven field submission selection
  // changes. Ref-stored handler so identity changes from the parent do not
  // re-trigger this effect; we only fire on real ID changes.
  const onFieldSelectionChangeRef = useRef(onFieldSelectionChange);
  useEffect(() => {
    onFieldSelectionChangeRef.current = onFieldSelectionChange;
  }, [onFieldSelectionChange]);
  useEffect(() => {
    onFieldSelectionChangeRef.current?.({
      sessionId: selectedFieldSessionId,
      jobId: selectedFieldJobId,
    });
  }, [selectedFieldSessionId, selectedFieldJobId]);

  // Phase 1X — fetch reviewed snap preview geometry when overlay is enabled.
  // Read-only. Never mutates operational state. Silent failure.
  useEffect(() => {
    if (!layerSnapPreview) return;
    let cancelled = false;
    async function loadSnapPreview() {
      try {
        const res = await apiFetch(
          `${API_BASE}/api/observability/reviewed-snap-preview`,
          { cache: "no-store" },
        );
        if (!res.ok || cancelled) return;
        const data = (await res.json()) as import("@/lib/types/backend").ReviewedSnapPreviewResponse;
        if (!cancelled) setSnapPreviewData(data);
      } catch {
        // Silently ignore — overlay is advisory review aid only.
      }
    }
    void loadSnapPreview();
    return () => {
      cancelled = true;
    };
  }, [layerSnapPreview]);

  // Phase 2A — fetch KMZ engineering render payload when context layer is enabled.
  // Read-only. Never mutates operational state. Silent failure.
  useEffect(() => {
    if (!layerKmzContext) return;
    let cancelled = false;
    async function loadKmzRenderPayload() {
      try {
        const res = await apiFetch(
          `${API_BASE}/api/observability/kmz-render-payload`,
          { cache: "no-store" },
        );
        if (!res.ok || cancelled) return;
        const data = (await res.json()) as import("@/lib/types/backend").KmzRenderPayloadResponse;
        if (!cancelled) setKmzRenderPayload(data);
      } catch {
        // Silently ignore — layer is advisory display-only.
      }
    }
    void loadKmzRenderPayload();
    return () => {
      cancelled = true;
    };
  }, [layerKmzContext]);

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

  // Snap target for normal station placement. Combines the operational
  // redline polylines with the KMZ design polylines so stations land on the
  // nearest visible operational path — preferring redlines when they're
  // nearer (operational truth) and falling back to KMZ when no redline
  // exists nearby. KMZ design lines remain the snap target for everything
  // else (field-station footage interpolation, connector subpath, etc.).
  const stationSnapPolylines = useMemo<number[][][]>(() => {
    const out: number[][][] = [];
    for (const seg of redlineSegments) {
      const c = cleanCoords(seg.coords);
      if (c.length >= 2) out.push(c);
    }
    for (const poly of kmzSnapPolylines) {
      if (Array.isArray(poly) && poly.length >= 2) out.push(poly);
    }
    return out;
  }, [redlineSegments, kmzSnapPolylines]);

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
    if (selectedFieldSessionId) {
      const sid = selectedFieldSessionId.trim();
      (selectedFieldJobDetail?.stations ?? []).forEach((st) => {
        if (String(st.session_id ?? "").trim() !== sid) return;
        const lat = Number(st.latitude);
        const lon = Number(st.longitude);
        if (Number.isFinite(lat) && Number.isFinite(lon) && !(lat === 0 && lon === 0)) {
          coords.push([lat, lon]);
        }
      });
    }
    const raw = getBoundsFromCoords(coords);
    return raw ? expandBounds(raw, 0.12) : null;
  }, [stationPoints, selectedFieldSessionId, selectedFieldJobDetail]);

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
        // Snap to redlines + KMZ union so markers sit on the operational
        // path. snapLatLonToKmzPolylines is generic — it picks the nearest
        // point across every polyline in the pool.
        const snapPool =
          stationSnapPolylines.length > 0 ? stationSnapPolylines : kmzSnapPolylines;
        const snapped = snapLatLonToKmzPolylines(point.lat, point.lon, snapPool);
        return {
          idx,
          point,
          world: projectWorldPoint(snapped.lat, snapped.lon, renderBounds, projectionMetrics),
        };
      })
      .filter((item): item is { idx: number; point: StationPoint; world: ScreenPoint } => Boolean(item));
  }, [stationPoints, renderBounds, projectionMetrics, sourceFileToLayerId, hiddenLayers, stationSnapPolylines, kmzSnapPolylines]);

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
    const totalKmzFt = totalKmzPolylinesLengthFt(kmzSnapPolylines);
    const rows = fieldStationsFiltered.map((st) => {
      const stationFt = fieldStationFtFromRow(st);
      const rawLat = Number(st.latitude);
      const rawLon = Number(st.longitude);
      let displayLat = rawLat;
      let displayLon = rawLon;
      if (kmzSnapPolylines.length > 0 && totalKmzFt > 0 && Number.isFinite(stationFt)) {
        const alongFt = Math.max(0, Math.min(stationFt, totalKmzFt));
        const onLine = latLonAlongPolylinesByDistanceFt(kmzSnapPolylines, alongFt, totalKmzFt);
        if (onLine) {
          displayLat = onLine.lat;
          displayLon = onLine.lon;
        }
      }
      return { st, stationFt, displayLat, displayLon };
    });
    const ordered = rows.slice().sort((a, b) => {
      const fa = Number.isFinite(a.stationFt) ? a.stationFt : Number.POSITIVE_INFINITY;
      const fb = Number.isFinite(b.stationFt) ? b.stationFt : Number.POSITIVE_INFINITY;
      return fa - fb;
    });
    if (process.env.NODE_ENV === "development") {
      console.log("[field-overlay] order for path + markers (station_ft along KMZ):", {
        totalKmzFt,
        ordered: ordered.map((row) => ({
          station_number: row.st.station_number,
          station_ft: row.stationFt,
        })),
      });
    }
    return ordered.map(({ st, displayLat, displayLon }) => ({
      st,
      displayLat,
      displayLon,
      world: projectWorldPoint(displayLat, displayLon, renderBounds, projectionMetrics),
    }));
  }, [selectedFieldJobDetail, selectedFieldSessionId, renderBounds, projectionMetrics, kmzSnapPolylines]);

  const fieldStationPath = useMemo(() => {
    if (projectedFieldStations.length < 2 || !renderBounds || !projectionMetrics) return "";
    const finiteFts = projectedFieldStations
      .map(({ st }) => fieldStationFtFromRow(st))
      .filter((ft): ft is number => Number.isFinite(ft));
    if (finiteFts.length >= 2 && kmzSnapPolylines.length > 0) {
      const startFt = Math.min(...finiteFts);
      const endFt = Math.max(...finiteFts);
      const coords = kmzSubpathCoordsByDistanceRangeFt(kmzSnapPolylines, startFt, endFt);
      if (coords.length >= 2) {
        return buildWorldPath(coords, renderBounds, projectionMetrics);
      }
    }
    return buildWorldPath(
      projectedFieldStations.map(({ displayLat, displayLon }) => [displayLat, displayLon]),
      renderBounds,
      projectionMetrics,
    );
  }, [projectedFieldStations, renderBounds, projectionMetrics, kmzSnapPolylines]);

  const fieldTrackPath = useMemo(() => {
    const geo = selectedFieldSession?.track_geometry;
    if (!geo || !renderBounds || !projectionMetrics) return "";
    // GeoJSON coordinates are [lon, lat] — swap to [lat, lon] for buildWorldPath
    const coords = (geo.coordinates ?? []).map(([lon, lat]): [number, number] => [lat, lon]);
    return buildWorldPath(coords, renderBounds, projectionMetrics);
  }, [selectedFieldSession, renderBounds, projectionMetrics]);

  const visibleLabelIndices = useMemo(() => {
    const result = new Set<number>();
    if (!layerStructures || !projectedStations.length || !projectionMetrics) return result;

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
    layerStructures,
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

  const activeTooltipIndex = layerStructures ? hoverStationIndex : null;

  const tooltipStation = useMemo(() => {
    if (activeTooltipIndex === null) return null;
    return stationPoints[activeTooltipIndex] || null;
  }, [activeTooltipIndex, stationPoints]);

  const tooltipStationMode = hoverStationIndex !== null ? "Hover" : "";

  const tooltipWorldGeometry = useMemo(() => {
    if (!projectionMetrics || activeTooltipIndex === null || !layerStructures) {
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
  }, [activeTooltipIndex, projectedStations, projectionMetrics, viewport, layerStructures]);


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
    [state?.selected_route_name, state?.route_name, selectedStation],
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

  const handleExportKml = useCallback(async () => {
    const designCoveragePlacemarks: string[] = [];
    const designRoutePlacemarks: string[] = [];
    const redlinePlacemarks: string[] = [];
    const photoPlacemarks: string[] = [];
    const stationPlacemarks: string[] = [];

    const buildFolder = (name: string, folderPlacemarks: string[]) => `    <Folder>
      <name>${escapeXml(name)}</name>
${folderPlacemarks.join("\n")}
    </Folder>`;

    const photoDataUrlMap = new Map<string, string>();
    await Promise.all(
      gpsPhotos
        .filter((p) => p.reason === "mapped" && p.file)
        .map((p) => {
          return new Promise<void>((resolve) => {
            const reader = new FileReader();
            reader.onload = () => {
              photoDataUrlMap.set(p.id, reader.result as string);
              resolve();
            };
            reader.onerror = () => resolve();
            reader.readAsDataURL(p.file);
          });
        }),
    );

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

    gpsPhotos.forEach((p) => {
      if (p.reason !== "mapped") return;
      const markerLat = typeof p.displayLat === "number" ? p.displayLat : p.lat;
      const markerLon = typeof p.displayLon === "number" ? p.displayLon : p.lon;
      const coordinate = kmlCoordinateFromLatLon(markerLat, markerLon);
      if (!coordinate) return;
      const dataUrl = photoDataUrlMap.get(p.id);
      const descriptionHtml = `
  <div style="font-family: Arial; font-size: 12px;">
    <strong>${p.filename || "Photo"}</strong><br/><br/>
    ${
      dataUrl
        ? `<img src="${dataUrl}" style="max-width:300px; border:1px solid #ccc;" /><br/><br/>`
        : `<i>No preview available</i><br/><br/>`
    }
    <b>Original GPS:</b> ${typeof p.lat === "number" ? p.lat.toFixed(6) : "--"}, ${typeof p.lon === "number" ? p.lon.toFixed(6) : "--"}<br/>
    <b>Adjusted:</b> ${
      typeof p.displayLat === "number" && typeof p.displayLon === "number"
        ? `${p.displayLat.toFixed(6)}, ${p.displayLon.toFixed(6)}`
        : "none"
    }
  </div>
`;
      photoPlacemarks.push(`      <Placemark>
        <name>${escapeXml(p.filename)}</name>
        <description><![CDATA[${descriptionHtml.replaceAll("]]>", "]]]]><![CDATA[>")}]]></description>
        <styleUrl>#photoStyle</styleUrl>
        <Point>
          <coordinates>${coordinate}</coordinates>
        </Point>
      </Placemark>`);
    });

    const officeRouteJob = cleanDisplayText(
      (state?.selected_route_name && state.selected_route_name.trim()) ||
        (state?.route_name && state.route_name.trim()) ||
        (activeJob !== "--" ? String(activeJob) : ""),
    );

    stationPoints.forEach((point, idx) => {
      const coordinate = kmlCoordinateFromLatLon(point.lat, point.lon);
      if (!coordinate) return;
      const stationLabel = cleanDisplayText(point.station);
      const ll = kmlLatLonCells(point.lat, point.lon);
      const stationFtCell = formatNumber(point.station_ft, 3);
      const mappedFtCell = formatNumber(point.mapped_station_ft, 3);
      stationPlacemarks.push(`      <Placemark>
        <name>${escapeXml(`Station ${stationLabel !== "--" ? stationLabel : idx + 1}`)}</name>
        <description>${kmlDescriptionTable([
          { label: "Station", value: stationLabel },
          {
            label: "Station FT / mapped footage",
            value: kmlStationFtSlashMapped(stationFtCell, mappedFtCell),
          },
          { label: "Source file", value: cleanDisplayText(point.source_file) },
          { label: "Route / job", value: officeRouteJob },
          { label: "Session ID", value: "--" },
          { label: "Crew", value: cleanDisplayText(point.crew) },
          { label: "Date / timestamp", value: cleanDisplayText(point.date) },
          { label: "Depth FT", value: formatNumber(point.depth_ft, 3) },
          { label: "BOC FT", value: formatNumber(point.boc_ft, 3) },
          { label: "Notes", value: cleanDisplayText(point.notes) },
          { label: "Photo count", value: "--" },
          { label: "Latitude", value: ll.lat },
          { label: "Longitude", value: ll.lon },
        ])}</description>
        <styleUrl>#stationStyle</styleUrl>
        <Point>
          <coordinates>${coordinate}</coordinates>
        </Point>
      </Placemark>`);
    });

    const fieldSubmissionPlacemarks: string[] = [];
    if (
      selectedFieldSessionId?.trim() &&
      layerRoutes &&
      projectedFieldStations.length >= 2
    ) {
      const finiteFts = projectedFieldStations
        .map(({ st }) => fieldStationFtFromRow(st))
        .filter((ft): ft is number => Number.isFinite(ft));
      let pathCoords: number[][] = [];
      if (finiteFts.length >= 2 && kmzSnapPolylines.length > 0) {
        const startFt = Math.min(...finiteFts);
        const endFt = Math.max(...finiteFts);
        pathCoords = kmzSubpathCoordsByDistanceRangeFt(kmzSnapPolylines, startFt, endFt);
      }
      if (pathCoords.length < 2) {
        pathCoords = projectedFieldStations.map(({ displayLat, displayLon }) => [displayLat, displayLon]);
      }
      const coordinates = pathCoords
        .map((pt) => kmlCoordinateFromLatLon(pt[0], pt[1]))
        .filter((coord): coord is string => Boolean(coord));
      if (coordinates.length >= 2) {
        const sessionId = selectedFieldSessionId.trim();
        const crew = selectedFieldSession?.crew_name ? cleanDisplayText(selectedFieldSession.crew_name) : "";
        const rawStarted = selectedFieldSession?.started_at;
        const rawEnded = selectedFieldSession?.ended_at;
        const sessionPhotos = selectedFieldJobDetail?.photos ?? [];
        const fieldRouteJob = kmlFieldJobRouteJob(selectedFieldJobDetail ?? null);
        const sessionTsRaw = rawStarted || rawEnded || "";
        const sessionDateCell = sessionTsRaw
          ? `${formatDisplayDate(sessionTsRaw)} (${sessionTsRaw})`
          : "--";
        const sessionPhotoTotal = sessionPhotos.filter((p) => String(p.session_id ?? "") === sessionId).length;
        const crewCell = crew && crew !== "--" ? crew : "--";
        const withFt = projectedFieldStations.map((row) => ({ row, ft: fieldStationFtFromRow(row.st) }));
        const sortedByFt = withFt.filter((x) => Number.isFinite(x.ft)).sort((a, b) => a.ft - b.ft);
        const sortedAllByFt = [...withFt].sort((a, b) => {
          const fa = Number.isFinite(a.ft) ? a.ft : Number.POSITIVE_INFINITY;
          const fb = Number.isFinite(b.ft) ? b.ft : Number.POSITIVE_INFINITY;
          if (fa !== fb) return fa - fb;
          return String(a.row.st.id).localeCompare(String(b.row.st.id));
        });
        const startStationLabel =
          sortedByFt.length > 0 ? cleanDisplayText(sortedByFt[0].row.st.station_number) : "--";
        const endStationLabel =
          sortedByFt.length > 0
            ? cleanDisplayText(sortedByFt[sortedByFt.length - 1].row.st.station_number)
            : "--";
        const lineOverviewNote =
          startStationLabel !== "--" && endStationLabel !== "--"
            ? `Path from ${startStationLabel} through ${endStationLabel}`
            : startStationLabel !== "--"
              ? `Path from ${startStationLabel}`
              : endStationLabel !== "--"
                ? `Path through ${endStationLabel}`
                : "--";
        fieldSubmissionPlacemarks.push(`      <Placemark>
        <name>${escapeXml(`Field Submission ${sessionId}`)}</name>
        <description>${kmlDescriptionTable([
          { label: "Station", value: "Field submission path" },
          { label: "Station FT / mapped footage", value: "--" },
          { label: "Source file", value: "--" },
          { label: "Route / job", value: fieldRouteJob },
          { label: "Session ID", value: sessionId },
          { label: "Crew", value: crewCell },
          { label: "Date / timestamp", value: sessionDateCell },
          { label: "Depth FT", value: "--" },
          { label: "BOC FT", value: "--" },
          { label: "Notes", value: lineOverviewNote },
          { label: "Photo count", value: String(sessionPhotoTotal) },
          { label: "Latitude", value: "--" },
          { label: "Longitude", value: "--" },
        ])}</description>
        <styleUrl>#fieldSubmissionStyle</styleUrl>
        <LineString>
          <tessellate>1</tessellate>
          <coordinates>
            ${coordinates.join("\n            ")}
          </coordinates>
        </LineString>
      </Placemark>`);

        if (sortedByFt.length > 0) {
          const firstEntry = sortedByFt[0];
          const lastEntry = sortedByFt[sortedByFt.length - 1];
          const startCoord = kmlCoordinateFromLatLon(firstEntry.row.displayLat, firstEntry.row.displayLon);
          if (startCoord) {
            const startNum = cleanDisplayText(firstEntry.row.st.station_number);
            const stationKeyStart = String(firstEntry.row.st.station_number ?? "").trim();
            const mapStartRaw = (firstEntry.row.st as { mapped_station_ft?: number }).mapped_station_ft;
            const mappedStart =
              typeof mapStartRaw === "number" && Number.isFinite(mapStartRaw)
                ? formatNumber(mapStartRaw, 3)
                : "--";
            const ftStart = Number.isFinite(firstEntry.ft)
              ? formatNumber(firstEntry.ft, 3)
              : "--";
            const llS = kmlLatLonCells(firstEntry.row.displayLat, firstEntry.row.displayLon);
            fieldSubmissionPlacemarks.push(`      <Placemark>
        <name>${escapeXml(`Start ${startNum}`)}</name>
        <description>${kmlDescriptionTable([
          { label: "Station", value: `${startNum} (start)` },
          {
            label: "Station FT / mapped footage",
            value: kmlStationFtSlashMapped(ftStart, mappedStart),
          },
          { label: "Source file", value: "--" },
          { label: "Route / job", value: fieldRouteJob },
          { label: "Session ID", value: sessionId },
          { label: "Crew", value: crewCell },
          { label: "Date / timestamp", value: sessionDateCell },
          {
            label: "Depth FT",
            value: formatNumber(firstEntry.row.st.depth_ft, 3),
          },
          {
            label: "BOC FT",
            value: formatNumber(firstEntry.row.st.boc_ft, 3),
          },
          {
            label: "Notes",
            value: kmlSessionPhotoNotesForStation(sessionPhotos, sessionId, stationKeyStart),
          },
          {
            label: "Photo count",
            value: kmlSessionPhotoCountForStation(sessionPhotos, sessionId, stationKeyStart),
          },
          { label: "Latitude", value: llS.lat },
          { label: "Longitude", value: llS.lon },
        ])}</description>
        <styleUrl>#stationStyle</styleUrl>
        <Point>
          <coordinates>${startCoord}</coordinates>
        </Point>
      </Placemark>`);
          }
          const endCoord = kmlCoordinateFromLatLon(lastEntry.row.displayLat, lastEntry.row.displayLon);
          if (endCoord) {
            const endNum = cleanDisplayText(lastEntry.row.st.station_number);
            const stationKeyEnd = String(lastEntry.row.st.station_number ?? "").trim();
            const mapEndRaw = (lastEntry.row.st as { mapped_station_ft?: number }).mapped_station_ft;
            const mappedEnd =
              typeof mapEndRaw === "number" && Number.isFinite(mapEndRaw)
                ? formatNumber(mapEndRaw, 3)
                : "--";
            const ftEnd = Number.isFinite(lastEntry.ft) ? formatNumber(lastEntry.ft, 3) : "--";
            const llE = kmlLatLonCells(lastEntry.row.displayLat, lastEntry.row.displayLon);
            fieldSubmissionPlacemarks.push(`      <Placemark>
        <name>${escapeXml(`End ${endNum}`)}</name>
        <description>${kmlDescriptionTable([
          { label: "Station", value: `${endNum} (end)` },
          {
            label: "Station FT / mapped footage",
            value: kmlStationFtSlashMapped(ftEnd, mappedEnd),
          },
          { label: "Source file", value: "--" },
          { label: "Route / job", value: fieldRouteJob },
          { label: "Session ID", value: sessionId },
          { label: "Crew", value: crewCell },
          { label: "Date / timestamp", value: sessionDateCell },
          {
            label: "Depth FT",
            value: formatNumber(lastEntry.row.st.depth_ft, 3),
          },
          {
            label: "BOC FT",
            value: formatNumber(lastEntry.row.st.boc_ft, 3),
          },
          {
            label: "Notes",
            value: kmlSessionPhotoNotesForStation(sessionPhotos, sessionId, stationKeyEnd),
          },
          {
            label: "Photo count",
            value: kmlSessionPhotoCountForStation(sessionPhotos, sessionId, stationKeyEnd),
          },
          { label: "Latitude", value: llE.lat },
          { label: "Longitude", value: llE.lon },
        ])}</description>
        <styleUrl>#stationStyle</styleUrl>
        <Point>
          <coordinates>${endCoord}</coordinates>
        </Point>
      </Placemark>`);
          }
        }

        for (const { row, ft } of sortedAllByFt) {
          const coord = kmlCoordinateFromLatLon(row.displayLat, row.displayLon);
          if (!coord) continue;
          const st = row.st;
          const sn = cleanDisplayText(st.station_number);
          const stationKey = String(st.station_number ?? "").trim();
          const mapRowRaw = (st as { mapped_station_ft?: number }).mapped_station_ft;
          const mappedSt =
            typeof mapRowRaw === "number" && Number.isFinite(mapRowRaw)
              ? formatNumber(mapRowRaw, 3)
              : "--";
          const ftCell = Number.isFinite(ft) ? formatNumber(ft, 3) : "--";
          const ll = kmlLatLonCells(row.displayLat, row.displayLon);
          fieldSubmissionPlacemarks.push(`      <Placemark>
        <name>${escapeXml(`Station ${sn}`)}</name>
        <description>${kmlDescriptionTable([
          { label: "Station", value: sn },
          {
            label: "Station FT / mapped footage",
            value: kmlStationFtSlashMapped(ftCell, mappedSt),
          },
          { label: "Source file", value: "--" },
          { label: "Route / job", value: fieldRouteJob },
          { label: "Session ID", value: sessionId },
          { label: "Crew", value: crewCell },
          { label: "Date / timestamp", value: sessionDateCell },
          {
            label: "Depth FT",
            value: formatNumber(st.depth_ft, 3),
          },
          {
            label: "BOC FT",
            value: formatNumber(st.boc_ft, 3),
          },
          {
            label: "Notes",
            value: kmlSessionPhotoNotesForStation(sessionPhotos, sessionId, stationKey),
          },
          {
            label: "Photo count",
            value: kmlSessionPhotoCountForStation(sessionPhotos, sessionId, stationKey),
          },
          { label: "Latitude", value: ll.lat },
          { label: "Longitude", value: ll.lon },
        ])}</description>
        <styleUrl>#stationStyle</styleUrl>
        <Point>
          <coordinates>${coord}</coordinates>
        </Point>
      </Placemark>`);
        }
      }
    }

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
    <Style id="fieldSubmissionStyle">
      <LineStyle>
        <color>ff0000ff</color>
        <width>7</width>
      </LineStyle>
    </Style>
${buildFolder("Design / Coverage", designCoveragePlacemarks)}
${buildFolder("Design Routes", designRoutePlacemarks)}
${buildFolder("As-Built Redlines", redlinePlacemarks)}
${buildFolder("Photos", photoPlacemarks)}
${buildFolder("Stations", stationPlacemarks)}
${fieldSubmissionPlacemarks.length > 0 ? buildFolder("Selected Field Submission", fieldSubmissionPlacemarks) : ""}
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
  }, [
    activeJob,
    gpsPhotos,
    kmzLineFeatures,
    kmzPolygonFeatures,
    kmzSnapPolylines,
    layerRoutes,
    projectedFieldStations,
    redlineSegments,
    selectedFieldJobDetail,
    selectedFieldSession,
    selectedFieldSessionId,
    state?.route_name,
    state?.selected_route_name,
    stationPoints,
  ]);

  // Phase 2H — Engineering KML export mode.
  // Fetches the rich kmz-render-payload and emits full engineering context + redlines.
  // Does NOT modify handleExportKml; that closeout export is preserved unchanged.
  const handleExportEngineeringKml = useCallback(async () => {
    setEngExportError(null);
    let payload: import("@/lib/types/backend").KmzRenderPayloadResponse | null = null;
    try {
      const res = await apiFetch(appendSessionIdReadOnly(`${API_BASE}/api/engineering-kmz-payload`, projectId), { cache: "no-store" });
      if (!res.ok) {
        // Read the actual response body so the operator sees the real backend
        // error (e.g. "Token expired", "Missing or invalid Authorization header")
        // instead of a generic hint. apiFetch already retried once on 401.
        const bodyText = await res.text().catch(() => "");
        const snippet = bodyText.slice(0, 200).trim();
        console.warn("[eng-kml-export] payload fetch failed:", res.status, snippet);
        const detail = res.status === 401
          ? "Session may have expired — refresh the page to log in again."
          : "Check browser console for details.";
        setEngExportError(`Export failed — server returned ${res.status}. ${detail}${snippet ? ` (${snippet})` : ""}`);
        return;
      }
      payload = (await res.json()) as import("@/lib/types/backend").KmzRenderPayloadResponse;
    } catch (e) {
      console.warn("[eng-kml-export] fetch error:", e);
      setEngExportError("Export failed — could not reach the server. Check your connection and try again.");
      return;
    }
    if (!payload) return;

    const mappedPhotos = gpsPhotos.filter((p) => p.reason === "mapped" && p.file);
    const photoDataUrlMap = new Map<string, string>();
    if (mappedPhotos.length > 0) {
      await Promise.all(
        mappedPhotos.map((p) =>
          new Promise<void>((resolve) => {
            const reader = new FileReader();
            reader.onload = () => { photoDataUrlMap.set(p.id, reader.result as string); resolve(); };
            reader.onerror = () => resolve();
            reader.readAsDataURL(p.file);
          })
        ),
      );
    }

    const buildEngFolder = (name: string, marks: string[], visibility: 0 | 1 = 1, open: 0 | 1 = 0) =>
      `    <Folder>\n      <name>${escapeXml(name)}</name>\n      <visibility>${visibility}</visibility>\n      <open>${open}</open>\n${marks.join("\n")}\n    </Folder>`;

    // Build metadata description table for any engineering feature.
    const engMeta = (f: {
      description: string;
      description_raw: string;
      classification: string;
      folder_path: string[];
      chainage_ft: number | null;
      sequence_number: string | null;
      sequence_kind: string | null;
      lifecycle: { label: string; confidence: string; reason: string } | null;
      extended_data: Record<string, string>;
    }) => {
      if (f.description_raw) {
        return `<![CDATA[${f.description_raw.replaceAll("]]>", "]]]]><![CDATA[>")}]]>`;
      }
      const rows: Array<{ label: string; value: string }> = [];
      if (f.description) rows.push({ label: "Description", value: f.description });
      rows.push({ label: "Classification", value: f.classification });
      rows.push({ label: "Folder", value: (f.folder_path ?? []).join(" / ") || "--" });
      if (f.chainage_ft != null) rows.push({ label: "Chainage (ft)", value: String(f.chainage_ft) });
      if (f.sequence_number) rows.push({ label: "Sequence #", value: f.sequence_number });
      if (f.sequence_kind) rows.push({ label: "Sequence kind", value: f.sequence_kind });
      if (f.lifecycle) rows.push({ label: "Lifecycle", value: `${f.lifecycle.label} (${f.lifecycle.confidence})` });
      for (const [k, v] of Object.entries(f.extended_data ?? {})) {
        rows.push({ label: k, value: String(v) });
      }
      return kmlDescriptionTable(rows);
    };

    // F7d — Nested folder hierarchy reconstruction.
    // Source folder ancestry (from `folder_path: string[]` per feature) becomes
    // a nested <Folder> tree at export emission so Google Earth Desktop renders
    // each source level as an independently-toggleable sidebar checkbox.
    // The prior flat bucketing model (folder_path.join(" / ") as Map key)
    // collapsed every source level into a single sibling <Folder>. The tree
    // model below preserves source nesting with insertion-ordered children.
    //
    // FolderNode is intentionally function-scoped (not exported) and is NOT
    // added to web/src/lib/types/backend.ts — this is a transient in-memory
    // shape used only during a single export pass. No schema bump.
    //
    // TL-generated folders (Photos, Stations, Selected Field Submission,
    // As-Built Redlines) remain flat top-level siblings emitted via
    // buildEngFolder() at the kml template below. F7d does NOT change their
    // structure or emission order.
    type FolderNode = {
      name: string;
      placemarks: string[];
      children: Map<string, FolderNode>;
    };
    // Virtual root: never emitted as a <Folder>. Its `.children` become
    // top-level siblings under <Document>.
    const folderTree: FolderNode = {
      name: "",
      placemarks: [],
      children: new Map(),
    };
    // Caller-facing interface preserved verbatim:
    //   getFolderBucket(fp).push(xml)
    // still works exactly like the prior flat-Map implementation. The returned
    // array is now the leaf node's `.placemarks` instead of a flat Map value.
    // Callers at lines downstream remain BYTE-IDENTICAL.
    const getFolderBucket = (fp: string[]): string[] => {
      const path = fp ?? [];
      if (path.length === 0) {
        // Empty path → "Uncategorized" top-level sibling (preserves prior fallback).
        let bucket = folderTree.children.get("Uncategorized");
        if (!bucket) {
          bucket = { name: "Uncategorized", placemarks: [], children: new Map() };
          folderTree.children.set("Uncategorized", bucket);
        }
        return bucket.placemarks;
      }
      let current = folderTree;
      for (const segment of path) {
        let next = current.children.get(segment);
        if (!next) {
          next = { name: segment, placemarks: [], children: new Map() };
          current.children.set(segment, next);
        }
        current = next;
      }
      return current.placemarks;
    };
    // True iff this subtree contributes zero placemarks. Used at emission time
    // to prune empty branches (matches the prior `marks.length > 0` filter).
    const folderIsEmpty = (node: FolderNode): boolean => {
      if (node.placemarks.length > 0) return false;
      for (const child of node.children.values()) {
        if (!folderIsEmpty(child)) return false;
      }
      return true;
    };
    // Recursive nested-folder emitter. Child folders emitted before sibling
    // placemarks (matches source XML convention). Indentation is cosmetic only —
    // KML is whitespace-insensitive; Google Earth parses structure regardless.
    const emitFolder = (node: FolderNode, indent: string, visibility: 0 | 1 = 0, open: 0 | 1 = 0): string => {
      const childBlocks: string[] = [];
      for (const child of node.children.values()) {
        if (folderIsEmpty(child)) continue;
        childBlocks.push(emitFolder(child, indent + "  "));
      }
      const innerParts: string[] = [...childBlocks, ...node.placemarks];
      const inner = innerParts.length > 0 ? innerParts.join("\n") : "";
      return `${indent}<Folder>\n${indent}  <name>${escapeXml(node.name)}</name>\n${indent}  <visibility>${visibility}</visibility>\n${indent}  <open>${open}</open>\n${inner}\n${indent}</Folder>`;
    };

    // F3 helpers — scoped to export path, no external side effects
    const hexToKmlColor = (hex: string, alphaHex = "ff"): string => {
      const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
      if (!m) return `${alphaHex}ffffff`;
      return `${alphaHex}${m[3]}${m[2]}${m[1]}`; // aabbggrr
    };
    const sanitizeFeatId = (id: string): string =>
      (id || "f").replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 48);
    const featureStyles: string[] = [];
    // F7c — track icon_href values referenced by per-feature styles so the
    // KMZ packager can include matching asset bytes from kmzAssetsRef.
    const referencedHrefs = new Set<string>();

    // Points
    let _ptStyleIdx = 0;
    for (const pt of (payload.points ?? [])) {
      const [lat, lon] = pt.coord ?? [];
      const coord = kmlCoordinateFromLatLon(lat, lon);
      if (!coord) continue;
      const name = pt.name || pt.classification || "Unnamed Point";
      let ptStyleUrl = "#engPointStyle";
      if (pt.icon_href) {
        const ptStyleId = `pt_${sanitizeFeatId(pt.feature_id)}_${_ptStyleIdx++}`;
        featureStyles.push(
          // F7e — hide source-point map text labels (LabelStyle scale=0 per OGC KML).
          // Placemark <name> remains in XML for popup title + sidebar tree.
          // Operator names (Photos/Stations/FieldSub/Redlines) use separate
          // document-level styles and are NOT affected.
          `    <Style id="${ptStyleId}">\n      <IconStyle><scale>0.8</scale><Icon><href>${pt.icon_href}</href></Icon></IconStyle>\n      <LabelStyle><scale>0</scale></LabelStyle>\n    </Style>`,
        );
        ptStyleUrl = `#${ptStyleId}`;
        referencedHrefs.add(pt.icon_href);
      }
      getFolderBucket(pt.folder_path).push(
        `      <Placemark>\n        <name>${escapeXml(name)}</name>\n        <description>${engMeta(pt)}</description>\n        <styleUrl>${ptStyleUrl}</styleUrl>\n        <Point><coordinates>${coord}</coordinates></Point>\n      </Placemark>`,
      );
    }

    // Lines
    let _lineStyleIdx = 0;
    for (const line of (payload.lines ?? [])) {
      const coords = (line.coords ?? [])
        .map((p) => kmlCoordinateFromLatLon(p[0], p[1]))
        .filter((c): c is string => Boolean(c));
      if (coords.length < 2) continue;
      const name = line.name || "Unnamed Line";
      const lineKmlColor = hexToKmlColor(line.color || "#94a3b8", line.dash ? "88" : "ff");
      const lineWidth = typeof line.width === "number" ? Math.max(0.5, line.width) : 2;
      const lineStyleId = `fl_${sanitizeFeatId(line.feature_id)}_${_lineStyleIdx++}`;
      featureStyles.push(
        `    <Style id="${lineStyleId}">\n      <LineStyle><color>${lineKmlColor}</color><width>${lineWidth}</width></LineStyle>\n    </Style>`,
      );
      getFolderBucket(line.folder_path).push(
        `      <Placemark>\n        <name>${escapeXml(name)}</name>\n        <description>${engMeta(line)}</description>\n        <styleUrl>#${lineStyleId}</styleUrl>\n        <LineString><tessellate>1</tessellate><coordinates>${coords.join(" ")}</coordinates></LineString>\n      </Placemark>`,
      );
    }

    // Polygons
    let _polyStyleIdx = 0;
    for (const poly of (payload.polygons ?? [])) {
      const outer = (poly.outer ?? [])
        .map((p) => kmlCoordinateFromLatLon(p[0], p[1]))
        .filter((c): c is string => Boolean(c));
      if (outer.length < 3) continue;
      const name = poly.name || "Unnamed Polygon";
      const innerRingsXml = (poly.inner ?? [])
        .map((ring) => {
          const rc = ring.map((p) => kmlCoordinateFromLatLon(p[0], p[1])).filter((c): c is string => Boolean(c));
          if (rc.length < 3) return "";
          return `          <innerBoundaryIs><LinearRing><coordinates>${rc.join(" ")}</coordinates></LinearRing></innerBoundaryIs>`;
        })
        .filter(Boolean)
        .join("\n");
      const polyOutlineColor = hexToKmlColor(poly.fill_color || "#94a3b8", "ff");
      const polyFillColor = hexToKmlColor(poly.fill_color || "#94a3b8", "33");
      const polyStyleId = `fp_${sanitizeFeatId(poly.feature_id)}_${_polyStyleIdx++}`;
      featureStyles.push(
        `    <Style id="${polyStyleId}">\n      <LineStyle><color>${polyOutlineColor}</color><width>1</width></LineStyle>\n      <PolyStyle><color>${polyFillColor}</color><fill>1</fill><outline>1</outline></PolyStyle>\n    </Style>`,
      );
      getFolderBucket(poly.folder_path).push(
        `      <Placemark>\n        <name>${escapeXml(name)}</name>\n        <description>${engMeta(poly)}</description>\n        <styleUrl>#${polyStyleId}</styleUrl>\n        <Polygon><tessellate>1</tessellate><outerBoundaryIs><LinearRing><coordinates>${outer.join(" ")}</coordinates></LinearRing></outerBoundaryIs>${innerRingsXml ? "\n" + innerRingsXml : ""}\n        </Polygon>\n      </Placemark>`,
      );
    }

    const photoPlacemarks: string[] = [];
    gpsPhotos.forEach((p) => {
      if (p.reason !== "mapped") return;
      const markerLat = typeof p.displayLat === "number" ? p.displayLat : p.lat;
      const markerLon = typeof p.displayLon === "number" ? p.displayLon : p.lon;
      const coordinate = kmlCoordinateFromLatLon(markerLat, markerLon);
      if (!coordinate) return;
      const dataUrl = photoDataUrlMap.get(p.id);
      const descriptionHtml = `\n  <div style="font-family: Arial; font-size: 12px;">\n    <strong>${p.filename || "Photo"}</strong><br/><br/>\n    ${dataUrl ? `<img src="${dataUrl}" style="max-width:300px; border:1px solid #ccc;" /><br/><br/>` : `<i>No preview available</i><br/><br/>`}\n    <b>Original GPS:</b> ${typeof p.lat === "number" ? p.lat.toFixed(6) : "--"}, ${typeof p.lon === "number" ? p.lon.toFixed(6) : "--"}<br/>\n    <b>Adjusted:</b> ${typeof p.displayLat === "number" && typeof p.displayLon === "number" ? `${p.displayLat.toFixed(6)}, ${p.displayLon.toFixed(6)}` : "none"}\n  </div>\n`;
      photoPlacemarks.push(
        `      <Placemark>\n        <name>${escapeXml(p.filename)}</name>\n        <description><![CDATA[${descriptionHtml.replaceAll("]]>", "]]]]><![CDATA[>")}]]></description>\n        <styleUrl>#engPhotoStyle</styleUrl>\n        <Point><coordinates>${coordinate}</coordinates></Point>\n      </Placemark>`,
      );
    });

    const officeRouteJob = cleanDisplayText(
      (state?.selected_route_name && state.selected_route_name.trim()) ||
        (state?.route_name && state.route_name.trim()) ||
        (activeJob !== "--" ? String(activeJob) : ""),
    );

    const stationPlacemarks: string[] = [];
    stationPoints.forEach((point, idx) => {
      const coordinate = kmlCoordinateFromLatLon(point.lat, point.lon);
      if (!coordinate) return;
      const stationLabel = cleanDisplayText(point.station);
      const ll = kmlLatLonCells(point.lat, point.lon);
      const stationFtCell = formatNumber(point.station_ft, 3);
      const mappedFtCell = formatNumber(point.mapped_station_ft, 3);
      stationPlacemarks.push(`      <Placemark>
        <name>${escapeXml(`Station ${stationLabel !== "--" ? stationLabel : idx + 1}`)}</name>
        <description>${kmlDescriptionTable([
          { label: "Station", value: stationLabel },
          { label: "Station FT / mapped footage", value: kmlStationFtSlashMapped(stationFtCell, mappedFtCell) },
          { label: "Source file", value: cleanDisplayText(point.source_file) },
          { label: "Route / job", value: officeRouteJob },
          { label: "Session ID", value: "--" },
          { label: "Crew", value: cleanDisplayText(point.crew) },
          { label: "Date / timestamp", value: cleanDisplayText(point.date) },
          { label: "Depth FT", value: formatNumber(point.depth_ft, 3) },
          { label: "BOC FT", value: formatNumber(point.boc_ft, 3) },
          { label: "Notes", value: cleanDisplayText(point.notes) },
          { label: "Photo count", value: "--" },
          { label: "Latitude", value: ll.lat },
          { label: "Longitude", value: ll.lon },
        ])}</description>
        <styleUrl>#engStationStyle</styleUrl>
        <Point>
          <coordinates>${coordinate}</coordinates>
        </Point>
      </Placemark>`);
    });

    const fieldSubmissionPlacemarks: string[] = [];
    if (
      selectedFieldSessionId?.trim() &&
      layerRoutes &&
      projectedFieldStations.length >= 2
    ) {
      const finiteFts = projectedFieldStations
        .map(({ st }) => fieldStationFtFromRow(st))
        .filter((ft): ft is number => Number.isFinite(ft));
      let pathCoords: number[][] = [];
      if (finiteFts.length >= 2 && kmzSnapPolylines.length > 0) {
        const startFt = Math.min(...finiteFts);
        const endFt = Math.max(...finiteFts);
        pathCoords = kmzSubpathCoordsByDistanceRangeFt(kmzSnapPolylines, startFt, endFt);
      }
      if (pathCoords.length < 2) {
        pathCoords = projectedFieldStations.map(({ displayLat, displayLon }) => [displayLat, displayLon]);
      }
      const coordinates = pathCoords
        .map((pt) => kmlCoordinateFromLatLon(pt[0], pt[1]))
        .filter((coord): coord is string => Boolean(coord));
      if (coordinates.length >= 2) {
        const sessionId = selectedFieldSessionId.trim();
        const crew = selectedFieldSession?.crew_name ? cleanDisplayText(selectedFieldSession.crew_name) : "";
        const rawStarted = selectedFieldSession?.started_at;
        const rawEnded = selectedFieldSession?.ended_at;
        const sessionPhotos = selectedFieldJobDetail?.photos ?? [];
        const fieldRouteJob = kmlFieldJobRouteJob(selectedFieldJobDetail ?? null);
        const sessionTsRaw = rawStarted || rawEnded || "";
        const sessionDateCell = sessionTsRaw
          ? `${formatDisplayDate(sessionTsRaw)} (${sessionTsRaw})`
          : "--";
        const sessionPhotoTotal = sessionPhotos.filter((p) => String(p.session_id ?? "") === sessionId).length;
        const crewCell = crew && crew !== "--" ? crew : "--";
        const withFt = projectedFieldStations.map((row) => ({ row, ft: fieldStationFtFromRow(row.st) }));
        const sortedByFt = withFt.filter((x) => Number.isFinite(x.ft)).sort((a, b) => a.ft - b.ft);
        const sortedAllByFt = [...withFt].sort((a, b) => {
          const fa = Number.isFinite(a.ft) ? a.ft : Number.POSITIVE_INFINITY;
          const fb = Number.isFinite(b.ft) ? b.ft : Number.POSITIVE_INFINITY;
          if (fa !== fb) return fa - fb;
          return String(a.row.st.id).localeCompare(String(b.row.st.id));
        });
        const startStationLabel =
          sortedByFt.length > 0 ? cleanDisplayText(sortedByFt[0].row.st.station_number) : "--";
        const endStationLabel =
          sortedByFt.length > 0
            ? cleanDisplayText(sortedByFt[sortedByFt.length - 1].row.st.station_number)
            : "--";
        const lineOverviewNote =
          startStationLabel !== "--" && endStationLabel !== "--"
            ? `Path from ${startStationLabel} through ${endStationLabel}`
            : startStationLabel !== "--"
              ? `Path from ${startStationLabel}`
              : endStationLabel !== "--"
                ? `Path through ${endStationLabel}`
                : "--";
        fieldSubmissionPlacemarks.push(`      <Placemark>
        <name>${escapeXml(`Field Submission ${sessionId}`)}</name>
        <description>${kmlDescriptionTable([
          { label: "Station", value: "Field submission path" },
          { label: "Station FT / mapped footage", value: "--" },
          { label: "Source file", value: "--" },
          { label: "Route / job", value: fieldRouteJob },
          { label: "Session ID", value: sessionId },
          { label: "Crew", value: crewCell },
          { label: "Date / timestamp", value: sessionDateCell },
          { label: "Depth FT", value: "--" },
          { label: "BOC FT", value: "--" },
          { label: "Notes", value: lineOverviewNote },
          { label: "Photo count", value: String(sessionPhotoTotal) },
          { label: "Latitude", value: "--" },
          { label: "Longitude", value: "--" },
        ])}</description>
        <styleUrl>#engFieldSubmissionStyle</styleUrl>
        <LineString>
          <tessellate>1</tessellate>
          <coordinates>
            ${coordinates.join("\n            ")}
          </coordinates>
        </LineString>
      </Placemark>`);

        if (sortedByFt.length > 0) {
          const firstEntry = sortedByFt[0];
          const lastEntry = sortedByFt[sortedByFt.length - 1];
          const startCoord = kmlCoordinateFromLatLon(firstEntry.row.displayLat, firstEntry.row.displayLon);
          if (startCoord) {
            const startNum = cleanDisplayText(firstEntry.row.st.station_number);
            const stationKeyStart = String(firstEntry.row.st.station_number ?? "").trim();
            const mapStartRaw = (firstEntry.row.st as { mapped_station_ft?: number }).mapped_station_ft;
            const mappedStart =
              typeof mapStartRaw === "number" && Number.isFinite(mapStartRaw)
                ? formatNumber(mapStartRaw, 3)
                : "--";
            const ftStart = Number.isFinite(firstEntry.ft) ? formatNumber(firstEntry.ft, 3) : "--";
            const llS = kmlLatLonCells(firstEntry.row.displayLat, firstEntry.row.displayLon);
            fieldSubmissionPlacemarks.push(`      <Placemark>
        <name>${escapeXml(`Start ${startNum}`)}</name>
        <description>${kmlDescriptionTable([
          { label: "Station", value: `${startNum} (start)` },
          { label: "Station FT / mapped footage", value: kmlStationFtSlashMapped(ftStart, mappedStart) },
          { label: "Source file", value: "--" },
          { label: "Route / job", value: fieldRouteJob },
          { label: "Session ID", value: sessionId },
          { label: "Crew", value: crewCell },
          { label: "Date / timestamp", value: sessionDateCell },
          { label: "Depth FT", value: formatNumber(firstEntry.row.st.depth_ft, 3) },
          { label: "BOC FT", value: formatNumber(firstEntry.row.st.boc_ft, 3) },
          { label: "Notes", value: kmlSessionPhotoNotesForStation(sessionPhotos, sessionId, stationKeyStart) },
          { label: "Photo count", value: kmlSessionPhotoCountForStation(sessionPhotos, sessionId, stationKeyStart) },
          { label: "Latitude", value: llS.lat },
          { label: "Longitude", value: llS.lon },
        ])}</description>
        <styleUrl>#engStationStyle</styleUrl>
        <Point>
          <coordinates>${startCoord}</coordinates>
        </Point>
      </Placemark>`);
          }
          const endCoord = kmlCoordinateFromLatLon(lastEntry.row.displayLat, lastEntry.row.displayLon);
          if (endCoord) {
            const endNum = cleanDisplayText(lastEntry.row.st.station_number);
            const stationKeyEnd = String(lastEntry.row.st.station_number ?? "").trim();
            const mapEndRaw = (lastEntry.row.st as { mapped_station_ft?: number }).mapped_station_ft;
            const mappedEnd =
              typeof mapEndRaw === "number" && Number.isFinite(mapEndRaw)
                ? formatNumber(mapEndRaw, 3)
                : "--";
            const ftEnd = Number.isFinite(lastEntry.ft) ? formatNumber(lastEntry.ft, 3) : "--";
            const llE = kmlLatLonCells(lastEntry.row.displayLat, lastEntry.row.displayLon);
            fieldSubmissionPlacemarks.push(`      <Placemark>
        <name>${escapeXml(`End ${endNum}`)}</name>
        <description>${kmlDescriptionTable([
          { label: "Station", value: `${endNum} (end)` },
          { label: "Station FT / mapped footage", value: kmlStationFtSlashMapped(ftEnd, mappedEnd) },
          { label: "Source file", value: "--" },
          { label: "Route / job", value: fieldRouteJob },
          { label: "Session ID", value: sessionId },
          { label: "Crew", value: crewCell },
          { label: "Date / timestamp", value: sessionDateCell },
          { label: "Depth FT", value: formatNumber(lastEntry.row.st.depth_ft, 3) },
          { label: "BOC FT", value: formatNumber(lastEntry.row.st.boc_ft, 3) },
          { label: "Notes", value: kmlSessionPhotoNotesForStation(sessionPhotos, sessionId, stationKeyEnd) },
          { label: "Photo count", value: kmlSessionPhotoCountForStation(sessionPhotos, sessionId, stationKeyEnd) },
          { label: "Latitude", value: llE.lat },
          { label: "Longitude", value: llE.lon },
        ])}</description>
        <styleUrl>#engStationStyle</styleUrl>
        <Point>
          <coordinates>${endCoord}</coordinates>
        </Point>
      </Placemark>`);
          }
        }

        for (const { row, ft } of sortedAllByFt) {
          const coord = kmlCoordinateFromLatLon(row.displayLat, row.displayLon);
          if (!coord) continue;
          const st = row.st;
          const sn = cleanDisplayText(st.station_number);
          const stationKey = String(st.station_number ?? "").trim();
          const mapRowRaw = (st as { mapped_station_ft?: number }).mapped_station_ft;
          const mappedSt =
            typeof mapRowRaw === "number" && Number.isFinite(mapRowRaw)
              ? formatNumber(mapRowRaw, 3)
              : "--";
          const ftCell = Number.isFinite(ft) ? formatNumber(ft, 3) : "--";
          const ll = kmlLatLonCells(row.displayLat, row.displayLon);
          fieldSubmissionPlacemarks.push(`      <Placemark>
        <name>${escapeXml(`Station ${sn}`)}</name>
        <description>${kmlDescriptionTable([
          { label: "Station", value: sn },
          { label: "Station FT / mapped footage", value: kmlStationFtSlashMapped(ftCell, mappedSt) },
          { label: "Source file", value: "--" },
          { label: "Route / job", value: fieldRouteJob },
          { label: "Session ID", value: sessionId },
          { label: "Crew", value: crewCell },
          { label: "Date / timestamp", value: sessionDateCell },
          { label: "Depth FT", value: formatNumber(st.depth_ft, 3) },
          { label: "BOC FT", value: formatNumber(st.boc_ft, 3) },
          { label: "Notes", value: kmlSessionPhotoNotesForStation(sessionPhotos, sessionId, stationKey) },
          { label: "Photo count", value: kmlSessionPhotoCountForStation(sessionPhotos, sessionId, stationKey) },
          { label: "Latitude", value: ll.lat },
          { label: "Longitude", value: ll.lon },
        ])}</description>
        <styleUrl>#engStationStyle</styleUrl>
        <Point>
          <coordinates>${coord}</coordinates>
        </Point>
      </Placemark>`);
        }
      }
    }

    // Engineering context folders — F7d: nested-tree traversal from folderTree.
    // folderTree's virtual root is not emitted; its non-empty children become
    // top-level <Folder> siblings under <Document>. Each child recursively
    // emits its own nested <Folder> descendants via emitFolder().
    const engFolderBlocks = Array.from(folderTree.children.values())
      .filter((child) => !folderIsEmpty(child))
      .map((child) => emitFolder(child, "    ", 0, 0))
      .join("\n");

    // As-Built Redlines (same logic as existing export, no mutation)
    const redlinePlacemarks: string[] = [];
    redlineSegments.forEach((segment, idx) => {
      const coordinates = cleanCoords(segment.coords)
        .map((pt) => kmlCoordinateFromLatLon(pt[0], pt[1]))
        .filter((c): c is string => Boolean(c));
      if (coordinates.length < 2) return;
      const name = cleanDisplayText(segment.source_file || segment.segment_id || `Redline ${idx + 1}`);
      redlinePlacemarks.push(
        `      <Placemark>\n        <name>${escapeXml(`Redline - ${name}`)}</name>\n        <styleUrl>#engRedlineStyle</styleUrl>\n        <gx:drawOrder>1000</gx:drawOrder>\n        <LineString><tessellate>1</tessellate><coordinates>${coordinates.join(" ")}</coordinates></LineString>\n      </Placemark>`,
      );
    });

    const kml = `<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2">
  <Document>
    <open>1</open>
    <name>${escapeXml("Engineering KMZ Context + Redlines")}</name>
    <Style id="engLineStyle">
      <LineStyle><color>ff94a3b8</color><width>2</width></LineStyle>
    </Style>
    <Style id="engPointStyle">
      <IconStyle><scale>0.8</scale></IconStyle>
      <!-- F7e: scale=0 hides repeated source-point map text labels. -->
      <!-- Name still present in placemark <name> for popup + sidebar. -->
      <LabelStyle><scale>0</scale></LabelStyle>
    </Style>
    <Style id="engPolyStyle">
      <LineStyle><color>8894a3b8</color><width>1</width></LineStyle>
      <PolyStyle><color>1a94a3b8</color><fill>1</fill><outline>1</outline></PolyStyle>
    </Style>
    <Style id="engRedlineStyle">
      <LineStyle><color>ff0000ff</color><width>8</width></LineStyle>
    </Style>
    <Style id="engPhotoStyle">
      <IconStyle><scale>0.9</scale></IconStyle>
    </Style>
    <Style id="engStationStyle">
      <IconStyle><scale>0.7</scale></IconStyle>
    </Style>
    <Style id="engFieldSubmissionStyle">
      <LineStyle><color>ff0000ff</color><width>7</width></LineStyle>
    </Style>
${featureStyles.length > 0 ? featureStyles.join("\n") + "\n" : ""}${engFolderBlocks}
${photoPlacemarks.length > 0 ? buildEngFolder("Photos", photoPlacemarks, 1, 0) : ""}
${stationPlacemarks.length > 0 ? buildEngFolder("Stations", stationPlacemarks, 0, 0) : ""}
${fieldSubmissionPlacemarks.length > 0 ? buildEngFolder("Selected Field Submission", fieldSubmissionPlacemarks, 0, 0) : ""}
${redlinePlacemarks.length > 0 ? buildEngFolder("As-Built Redlines", redlinePlacemarks, 1, 1) : ""}
  </Document>
</kml>`;

    // F7a + F7c — wrap KML in a real KMZ ZIP archive with doc.kml at the root,
    // and embed referenced icon assets at their original relative paths so
    // Google Earth resolves them inside the archive. Absolute URLs and data
    // URIs pass through the KML unchanged and require no archive entry.
    const zipEntries: Record<string, Uint8Array> = {
      "doc.kml": strToU8(kml),
    };
    for (const href of referencedHrefs) {
      if (/^(https?:|data:|file:)/i.test(href)) continue;
      const bytes = kmzAssetsRef.current.get(href);
      if (bytes) zipEntries[href] = bytes;
    }
    const zipBytes = zipSync(zipEntries);
    // Copy into a fresh ArrayBuffer so the Blob owns standalone bytes
    // independent of any pooled buffer fflate may share.
    const blob = new Blob([new Uint8Array(zipBytes)], { type: "application/vnd.google-earth.kmz" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "engineering_kmz_context_plus_redlines.kmz";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    setEngExportError(null);
  }, [activeJob, gpsPhotos, kmzSnapPolylines, layerRoutes, projectedFieldStations, redlineSegments, selectedFieldJobDetail, selectedFieldSession, selectedFieldSessionId, state, stationPoints]);

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
      setLayerStructures(true);
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
      const response = await apiFetch(appendSessionIdReadOnly(`${API_BASE}/api/current-state`, projectId));
      // Read text first so a non-JSON body (e.g. Vercel edge 404 "The page
      // could not be found") surfaces a readable snippet instead of a raw
      // "Unexpected token 'T', 'The page c'..." JSON.parse error in the
      // workspace status banner. Mirrors handleEngineeringPlansUpload below.
      const responseText = await response.text();
      let data: BackendState;
      try {
        data = (responseText ? JSON.parse(responseText) : {}) as BackendState;
      } catch {
        const snippet = responseText.slice(0, 200).trim() || `HTTP ${response.status}`;
        throw new Error(`Current state load failed (${response.status}): ${snippet}`);
      }
      const sessionId = peekSessionId(projectId);
      if (!response.ok || data.success === false) throw new Error(data.error || "Unable to load current state.");
      setState(withoutClearedEngineeringPlans(data, projectId, sessionId));
      onWorkspaceStateChanged?.();
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
        setStatusText("Local backend connected. KMZ loaded. Waiting for field data.");
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
      const res = await apiFetch(appendSessionId(`${API_BASE}/api/debug/pipeline-diag`, projectId));
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
      const response = await apiFetch(appendSessionId(`${API_BASE}/api/reset-state`, projectId), { method: "POST" });
      const data: BackendState = await response.json();
      const sessionId = acceptSessionFromMutation(data, projectId);
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
      onWorkspaceStateChanged?.();
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

  async function handleLockCloseout() {
    const sid = getStoredSessionId(projectId);
    if (!sid) {
      setStatusText("No active session for lock.");
      setStatusTone("error");
      return;
    }
    if (!billingApproved) {
      setStatusText("Closeout can only be locked after billing is approved.");
      setStatusTone("warning");
      return;
    }
    const lockJobId = String(selectedFieldJobDetail?.id || "test-job");
    setBusy(true);
    try {
      const res = await apiFetch(appendSessionId(`${API_BASE}/api/jobs/${encodeURIComponent(lockJobId)}/lock-closeout`, projectId), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sid,
          user: (process.env.NEXT_PUBLIC_CLOSEOUT_USER_NAME || "").trim() || "Operator",
        }),
      });
      const data = (await res.json().catch(() => ({}))) as { error?: string };
      if (!res.ok) throw new Error(data.error || `Lock failed (${res.status}).`);
      await fetchState("Closeout locked.");
    } catch (e) {
      setStatusText(e instanceof Error ? e.message : "Lock failed.");
      setStatusTone("error");
    } finally {
      setBusy(false);
    }
  }

  async function handleUnlockCloseout() {
    const sid = getStoredSessionId(projectId);
    if (!sid) {
      setStatusText("No active session for unlock.");
      setStatusTone("error");
      return;
    }
    const confirmed = window.confirm("Unlock this closeout for revisions?");
    if (!confirmed) return;
    const expectedPasscode = String(process.env.NEXT_PUBLIC_CLOSEOUT_UNLOCK_CODE || "").trim();
    if (expectedPasscode) {
      const enteredPasscode = window.prompt("Enter unlock passcode") ?? "";
      if (enteredPasscode !== expectedPasscode) {
        setStatusText("Unlock passcode invalid.");
        setStatusTone("error");
        return;
      }
    }
    const unlockJobId = String(selectedFieldJobDetail?.id || "test-job");
    const requestedRole = (process.env.NEXT_PUBLIC_USER_ROLE || "").toLowerCase();
    const unlockRole = requestedRole === "admin" || requestedRole === "manager" ? requestedRole : "manager";
    setBusy(true);
    try {
      const res = await apiFetch(appendSessionId(`${API_BASE}/api/jobs/${encodeURIComponent(unlockJobId)}/unlock-closeout`, projectId), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sid,
          role: unlockRole,
        }),
      });
      const data = (await res.json().catch(() => ({}))) as { error?: string };
      if (!res.ok) throw new Error(data.error || `Unlock failed (${res.status}).`);
      await fetchState("Closeout unlocked.");
    } catch (e) {
      setStatusText(e instanceof Error ? e.message : "Unlock failed.");
      setStatusTone("error");
    } finally {
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
      const response = await apiFetch(appendSessionId(`${API_BASE}/api/upload-design`, projectId), { method: "POST", body: form });
      const data: BackendState = await response.json();
      acceptSessionFromMutation(data, projectId);
      if (!response.ok || data.success === false) throw new Error(data.error || "Design upload failed.");
      setState(data);
      // F7b — capture non-KML assets (icons, images) from the source KMZ so
      // they can be repackaged into the engineering KMZ export. Silent failure:
      // any error here MUST NOT break the upload UX.
      if (file.name.toLowerCase().endsWith(".kmz")) {
        try {
          const buf = new Uint8Array(await file.arrayBuffer());
          const entries = unzipSync(buf);
          const assets = new Map<string, Uint8Array>();
          for (const [path, bytes] of Object.entries(entries)) {
            if (!path.toLowerCase().endsWith(".kml")) {
              assets.set(path, bytes);
            }
          }
          kmzAssetsRef.current = assets;
        } catch {
          kmzAssetsRef.current = new Map();
        }
      } else {
        kmzAssetsRef.current = new Map();
      }
      onWorkspaceStateChanged?.();
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
    setStatusText(`Uploading ${files.length} field data file${files.length > 1 ? "s" : ""}...`);
    setStatusTone("neutral");
    try {
      const form = new FormData();
      Array.from(files).forEach((file) => form.append("files", file));
      appendSessionIdToForm(form, projectId);
      const response = await apiFetch(`${API_BASE}/api/upload-structured-bore-files`, { method: "POST", body: form });
      const data: BackendState = await response.json();
      acceptSessionFromMutation(data, projectId);
      if (!response.ok || data.success === false) throw new Error(data.error || "Field data upload failed.");
      setState(data);
      onWorkspaceStateChanged?.();
      fetchPipelineDiag(); // Nova Phase 1 — refresh diagnostics after field data upload
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
      setStatusText(String(data.warning || data.message || "Field data uploaded successfully."));
      setStatusTone(data.warning ? "warning" : "success");
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Field data upload failed.");
      setStatusTone("error");
    } finally {
      setBusy(false);
    }
  }

  async function handleEngineeringPlansUpload(files: FileList | null) {
    if (!files || files.length === 0) return;

    // PT.IU R1 — direct-to-Render upload bypasses Vercel ~4.5 MB serverless ceiling.
    // Resolves at build time via Next.js inline-replacement of NEXT_PUBLIC_* vars.
    // If unset (dev/local without env), falls back to same-origin proxy with the
    // original 4 MB safety cap preserved.
    const RENDER_BASE = (
      process.env.NEXT_PUBLIC_API_BASE ||
      process.env.NEXT_PUBLIC_API_BASE_URL ||
      ""
    ).replace(/\/+$/, "");
    const uploadUrl = RENDER_BASE
      ? `${RENDER_BASE}/api/upload-engineering-plans`
      : `${API_BASE}/api/upload-engineering-plans`;
    const directToRender = Boolean(RENDER_BASE);

    // PT.IU R1 — per-file size cap. 100 MB direct-to-Render; 4 MB on proxy fallback.
    // Rationale: Brenham max is ~14 MB; 100 MB provides headroom for future
    // GIS/DWG/LiDAR artifacts while keeping Render memory spike bounded
    // (file_bytes is read into RAM in upload_engineering_plans; ~512 MB container cap).
    const PER_FILE_MAX_MB = directToRender ? 100 : 4;
    const oversized = Array.from(files).filter((f) => f.size / (1024 * 1024) > PER_FILE_MAX_MB);
    if (oversized.length > 0) {
      const list = oversized
        .map((f) => `${f.name} (${(f.size / (1024 * 1024)).toFixed(1)} MB)`)
        .join(", ");
      const hint = directToRender
        ? `Per-file maximum is ${PER_FILE_MAX_MB} MB.`
        : `Vercel proxy limit applies (${PER_FILE_MAX_MB} MB); contact support if direct upload is unavailable.`;
      setStatusText(`Engineering plan file(s) exceed the size limit: ${list}. ${hint}`);
      setStatusTone("error");
      return;
    }

    // PT.IU R1 — structured observability for future GIS-scale debugging.
    const totalBytes = Array.from(files).reduce((sum, f) => sum + f.size, 0);
    const uploadStartedAt = Date.now();
    console.info("[eng-plan-upload]", {
      event: "upload_start",
      ts: new Date().toISOString(),
      target: uploadUrl,
      direct_to_render: directToRender,
      file_count: files.length,
      total_bytes: totalBytes,
      total_mb: Number((totalBytes / (1024 * 1024)).toFixed(2)),
    });
    // PT.IU R2 — mirror the structured event into operator-visible state.
    // PT.IU R3 — also capture browser/runtime context (origin, href, UA,
    // build-time NEXT_PUBLIC_API_BASE, token-presence boolean, planned
    // request header names) so the operator can correlate against the
    // manual curl preflight without DevTools.
    setEngUploadDiag({
      event: "upload_start",
      ts: new Date().toISOString(),
      target: uploadUrl,
      direct_to_render: directToRender,
      file_count: files.length,
      total_mb: Number((totalBytes / (1024 * 1024)).toFixed(2)),
      ..._engUploadEnvSnapshot(),
    });

    setEngPlansBusy(true);
    setStatusText(`Uploading ${files.length} engineering plan file${files.length > 1 ? "s" : ""}...`);
    setStatusTone("neutral");
    try {
      const form = new FormData();
      appendSessionIdToForm(form, projectId);
      Array.from(files).forEach((f) => form.append("files", f));
      const response = await apiFetch(uploadUrl, { method: "POST", body: form });
      // Read body once as text; backend always returns JSON via _ok()/_err(),
      // so any non-JSON body means an upstream gateway error (Vercel timeout
      // 504, payload-too-large 413, Render 5xx, etc.). Surface that raw text
      // instead of a generic "Unexpected token R..." JSON.parse failure.
      const responseText = await response.text();
      let data: { success?: boolean; error?: string; message?: string; engineering_plans?: EngineeringPlan[] } = {};
      try {
        data = responseText ? JSON.parse(responseText) : {};
      } catch {
        const snippet = responseText.slice(0, 200).trim() || `HTTP ${response.status}`;
        console.warn("[eng-plan-upload]", {
          event: "non_json_response",
          ts: new Date().toISOString(),
          target: uploadUrl,
          status: response.status,
          body_snippet: snippet,
        });
        setEngUploadDiag({
          event: "non_json_response",
          ts: new Date().toISOString(),
          target: uploadUrl,
          direct_to_render: directToRender,
          status: response.status,
          body_snippet: snippet,
        });
        throw new Error(`Engineering plan upload failed (${response.status}): ${snippet}`);
      }
      acceptSessionFromMutation(data, projectId);
      if (!response.ok || data.success === false) {
        console.warn("[eng-plan-upload]", {
          event: "upload_failed",
          ts: new Date().toISOString(),
          target: uploadUrl,
          status: response.status,
          backend_error: data.error,
        });
        setEngUploadDiag({
          event: "upload_failed",
          ts: new Date().toISOString(),
          target: uploadUrl,
          direct_to_render: directToRender,
          status: response.status,
          backend_error: data.error,
        });
        throw new Error(data.error || "Engineering plan upload failed.");
      }
      setState((prev) => {
        if (!prev) return prev;
        const nextState = { ...prev, engineering_plans: data.engineering_plans ?? prev.engineering_plans };
        return withoutClearedEngineeringPlans(nextState, projectId);
      });
      fetchPipelineDiag(); // Nova Phase 1 — refresh plan signals after engineering plan upload
      console.info("[eng-plan-upload]", {
        event: "upload_success",
        ts: new Date().toISOString(),
        target: uploadUrl,
        status: response.status,
        uploaded_count: data.engineering_plans?.length ?? 0,
        elapsed_ms: Date.now() - uploadStartedAt,
      });
      setEngUploadDiag({
        event: "upload_success",
        ts: new Date().toISOString(),
        target: uploadUrl,
        direct_to_render: directToRender,
        status: response.status,
        uploaded_count: data.engineering_plans?.length ?? 0,
        elapsed_ms: Date.now() - uploadStartedAt,
      });
      setStatusText(String(data.message || "Engineering plans uploaded successfully."));
      setStatusTone("success");
    } catch (error) {
      console.warn("[eng-plan-upload]", {
        event: "upload_exception",
        ts: new Date().toISOString(),
        target: uploadUrl,
        message: error instanceof Error ? error.message : "Unknown error",
      });
      setEngUploadDiag({
        event: "upload_exception",
        ts: new Date().toISOString(),
        target: uploadUrl,
        direct_to_render: directToRender,
        message: error instanceof Error ? error.message : "Unknown error",
        elapsed_ms: Date.now() - uploadStartedAt,
        // PT.IU R3 — heuristic class + browser/runtime context for the
        // operator to see immediately on a "Failed to fetch" exception.
        failure_class: _classifyUploadException(error),
        ..._engUploadEnvSnapshot(),
      });
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
      const response = await apiFetch(appendSessionIdReadOnly(`${API_BASE}/api/report-bug`, projectId), {
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
    if (!layerStructures) {
      setHoverStationIndex(null);
      setSelectedStationIndex(null);
    }
  }, [layerStructures]);


  async function fetchStationPhotos(stationIdentity: string) {
    if (!stationIdentity) {
      setStationPhotos([]);
      return;
    }
    setStationPhotosLoading(true);
    try {
      const response = await apiFetch(
        appendSessionIdReadOnly(`${API_BASE}/api/station-photos?station_identity=${encodeURIComponent(stationIdentity)}`, projectId)
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
      appendSessionIdToForm(form, projectId);

      const response = await apiFetch(`${API_BASE}/api/station-photos/upload`, {
        method: "POST",
        body: form,
      });
      const data = await response.json();
      acceptSessionFromMutation(data, projectId);
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
    if (!onGpsPhotosChange) return;
    onGpsPhotosChange(
      gpsPhotos.map((p) => ({
        id: p.id,
        filename: p.filename,
        previewUrl: p.previewUrl,
        lat: p.lat,
        lon: p.lon,
        displayLat: p.displayLat,
        displayLon: p.displayLon,
        contentType: p.contentType,
        reason: p.reason,
        addedAt: p.addedAt,
      })),
    );
  }, [gpsPhotos, onGpsPhotosChange]);
  useEffect(() => {
    onKmzSemanticChange?.(state?.kmz_semantic ?? null);
  }, [state?.kmz_semantic, onKmzSemanticChange]);
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
  const closeoutLocked = Boolean(state?.closeout_lock?.is_locked || state?.closeout_locked);
  const workspaceReadOnly = billingApproved || closeoutLocked;
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
                <button onClick={handleReset} disabled={busy || closeoutLocked} style={buttonStyle("#0f172a", "#ffffff", "#0f172a", busy || closeoutLocked)}>Clear Workspace</button>
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
                    Upload design and field data, review the map on the Workspace tab, then use Closeout for reports and billing.
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
                    <button onClick={handleReset} disabled={busy || closeoutLocked} style={buttonStyle("#0f172a", "#ffffff", "#0f172a", busy || closeoutLocked)}>Clear Workspace</button>
                  </div>
                </div>
              </div>
            </div>
          )}

          <StatusBanner tone={statusTone} text={statusText} />

          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 16, alignItems: "stretch" }}>
            <SummaryCard title="Active Job" value={String(activeJob)} subtitle="Local label or backend-selected route" />
            <SummaryCard title="Files Loaded" value={String((hasDesign ? 1 : 0) + (state?.loaded_field_data_files || 0))} subtitle="Design + field data files" />
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
            subtitle="KMZ design, field data, and optional reference plan evidence uploads."
            style={{ display: activeWorkspaceTab === "workspace" ? "block" : "none" }}
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
                    Upload KMZ and field data first. Reference plans are optional closeout evidence and do not drive map generation.
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 16, alignItems: "start" }}>
              <label style={uploadCardStyle(busy || closeoutLocked)}>
                <input
                  type="file"
                  accept=".kmz,.kml"
                  style={{ display: "none" }}
                  disabled={busy || closeoutLocked}
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

              <label style={uploadCardStyle(busy || closeoutLocked)}>
                <input
                  type="file"
                  accept=".xlsx,.xls,.csv"
                  multiple
                  style={{ display: "none" }}
                  disabled={busy || closeoutLocked}
                  onChange={(e) => {
                    handleBoreUpload(e.target.files);
                    e.currentTarget.value = "";
                  }}
                />
                <div style={{ fontWeight: 800, fontSize: 16 }}>Upload Field Data</div>
                <div style={{ marginTop: 6, fontSize: 13, color: "#64748b", lineHeight: 1.55 }}>Triggers the existing backend upload flow for route matching, station mapping, and generated redlines.</div>
                <div style={{ marginTop: 14, fontSize: 12, color: hasBoreFiles ? "#166534" : "#64748b", fontWeight: 700 }}>
                  {hasBoreFiles ? `${state?.loaded_field_data_files || 0} field data file(s) loaded.` : "No field data files currently loaded."}
                </div>
              </label>

              <div style={{ border: "1px solid #dbe4ee", borderRadius: 16, background: "#fbfdff", padding: 16 }}>
                <div style={{ fontWeight: 800, fontSize: 15 }}>File status</div>
                <div style={{ marginTop: 12, display: "grid", gap: 10 }}>
                  <Pill label="Design" value={hasDesign ? "Loaded" : "Waiting"} />
                  <Pill label="Field data files" value={String(state?.loaded_field_data_files || 0)} />
                  <Pill label="Latest file" value={state?.latest_structured_file || "--"} />
                  <Pill label="Output ready" value={hasGeneratedOutput ? "Yes" : "No"} />
                </div>
              </div>
            </div>

            <div style={{ border: "1px solid #dbe4ee", borderRadius: 16, background: "#fbfdff", marginTop: 16, overflow: "hidden" }}>
              <button
                type="button"
                onClick={() => setEngineeringPlansExpanded((prev) => !prev)}
                style={{
                  width: "100%",
                  border: "none",
                  background: "transparent",
                  cursor: "pointer",
                  padding: "12px 14px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 10,
                  textAlign: "left",
                }}
                aria-expanded={engineeringPlansExpanded}
              >
                <div>
                  <div style={{ fontWeight: 800, fontSize: 14, color: "#0f172a" }}>
                    Reference Plans / Closeout Evidence
                    {(state?.engineering_plans?.length ?? 0) > 0 ? (
                      <span style={{ marginLeft: 8, fontSize: 12, fontWeight: 600, color: "#64748b" }}>
                        ({state!.engineering_plans!.length})
                      </span>
                    ) : null}
                  </div>
                  <div style={{ marginTop: 3, fontSize: 12, color: "#64748b" }}>
                    Optional documentation for office review and closeout packages.
                  </div>
                </div>
                <span style={{ fontSize: 12, color: "#64748b", fontWeight: 700 }}>
                  {engineeringPlansExpanded ? "Hide" : "Show"}
                </span>
              </button>
              {engineeringPlansExpanded ? (
                <div style={{ borderTop: "1px solid #e2e8f0", padding: "12px 14px", display: "grid", gap: 8 }}>
                  <label
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 8,
                      cursor: engPlansBusy ? "default" : "pointer",
                      opacity: engPlansBusy ? 0.6 : 1,
                      padding: "8px 14px",
                      borderRadius: 10,
                      border: "1px solid #0f172a",
                      background: "#0f172a",
                      color: "#ffffff",
                      fontSize: 13,
                      fontWeight: 700,
                      justifySelf: "start",
                    }}
                  >
                    <input
                      type="file"
                      accept=".pdf,application/pdf"
                      multiple
                      disabled={engPlansBusy}
                      style={{ display: "none" }}
                      onChange={(e) => {
                        handleEngineeringPlansUpload(e.target.files);
                        e.currentTarget.value = "";
                      }}
                    />
                    {engPlansBusy ? "Uploading..." : "Upload Engineering Plan PDFs"}
                  </label>
                  {engUploadDiag && (
                    <div
                      style={{
                        marginTop: 8,
                        padding: "8px 10px",
                        border: "1px solid #1e293b",
                        borderRadius: 6,
                        background: "#0b1220",
                        fontSize: 11,
                        color: "#e2e8f0",
                        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                        lineHeight: 1.4,
                        wordBreak: "break-all",
                      }}
                    >
                      <div style={{ marginBottom: 4 }}>
                        <strong
                          style={{
                            color:
                              engUploadDiag.event === "upload_success"
                                ? "#86efac"
                                : engUploadDiag.event === "upload_start"
                                  ? "#93c5fd"
                                  : "#fca5a5",
                          }}
                        >
                          {engUploadDiag.event}
                        </strong>
                        <span style={{ color: "#94a3b8", marginLeft: 8 }}>
                          {engUploadDiag.ts}
                        </span>
                      </div>
                      {engUploadDiag.direct_to_render !== undefined && (
                        <div>
                          direct_to_render: <strong>{String(engUploadDiag.direct_to_render)}</strong>
                        </div>
                      )}
                      {engUploadDiag.target && <div>target: {engUploadDiag.target}</div>}
                      {engUploadDiag.file_count !== undefined && (
                        <div>
                          files: {engUploadDiag.file_count}
                          {engUploadDiag.total_mb !== undefined
                            ? ` (${engUploadDiag.total_mb} MB)`
                            : ""}
                        </div>
                      )}
                      {engUploadDiag.status !== undefined && (
                        <div>http status: {engUploadDiag.status}</div>
                      )}
                      {engUploadDiag.backend_error && (
                        <div>backend_error: {engUploadDiag.backend_error}</div>
                      )}
                      {engUploadDiag.body_snippet && (
                        <div>body_snippet: {engUploadDiag.body_snippet}</div>
                      )}
                      {engUploadDiag.message && (
                        <div>message: {engUploadDiag.message}</div>
                      )}
                      {engUploadDiag.uploaded_count !== undefined && (
                        <div>uploaded_count: {engUploadDiag.uploaded_count}</div>
                      )}
                      {engUploadDiag.elapsed_ms !== undefined && (
                        <div>elapsed_ms: {engUploadDiag.elapsed_ms}</div>
                      )}
                      {/* PT.IU R3 — failure-class heuristic */}
                      {engUploadDiag.failure_class && (
                        <div>
                          failure_class: <strong>{engUploadDiag.failure_class}</strong>
                        </div>
                      )}
                      {/* PT.IU R3 — browser / runtime context (operator
                          copy-pastes to correlate against curl preflight) */}
                      {(engUploadDiag.origin ||
                        engUploadDiag.href ||
                        engUploadDiag.user_agent_short ||
                        engUploadDiag.next_public_api_base ||
                        engUploadDiag.access_token_present !== undefined ||
                        (engUploadDiag.request_header_names &&
                          engUploadDiag.request_header_names.length > 0)) && (
                        <div
                          style={{
                            marginTop: 6,
                            paddingTop: 6,
                            borderTop: "1px dashed #334155",
                            color: "#cbd5e1",
                          }}
                        >
                          <div style={{ color: "#94a3b8", marginBottom: 2 }}>
                            -- browser / runtime context --
                          </div>
                          {engUploadDiag.origin && (
                            <div>origin: {engUploadDiag.origin}</div>
                          )}
                          {engUploadDiag.href && (
                            <div>href: {engUploadDiag.href}</div>
                          )}
                          {engUploadDiag.user_agent_short && (
                            <div>user_agent: {engUploadDiag.user_agent_short}</div>
                          )}
                          {engUploadDiag.next_public_api_base && (
                            <div>
                              next_public_api_base: {engUploadDiag.next_public_api_base}
                            </div>
                          )}
                          {engUploadDiag.access_token_present !== undefined && (
                            <div>
                              access_token_present:{" "}
                              <strong>{String(engUploadDiag.access_token_present)}</strong>
                            </div>
                          )}
                          {engUploadDiag.request_header_names &&
                            engUploadDiag.request_header_names.length > 0 && (
                              <div>
                                request_header_names:{" "}
                                {engUploadDiag.request_header_names.join(", ")}
                              </div>
                            )}
                        </div>
                      )}
                      {/* PT.IU R3 — probe result */}
                      {engUploadDiag.probe_result && (
                        <div
                          style={{
                            marginTop: 6,
                            paddingTop: 6,
                            borderTop: "1px dashed #334155",
                            color: "#cbd5e1",
                          }}
                        >
                          <div style={{ color: "#94a3b8", marginBottom: 2 }}>
                            -- probe (direct-to-Render GET /api/current-state) --
                          </div>
                          <div>
                            probe_state:{" "}
                            <strong
                              style={{
                                color:
                                  engUploadDiag.probe_result.state === "ok"
                                    ? "#86efac"
                                    : engUploadDiag.probe_result.state === "probing"
                                      ? "#93c5fd"
                                      : "#fca5a5",
                              }}
                            >
                              {engUploadDiag.probe_result.state}
                            </strong>
                            <span style={{ color: "#94a3b8", marginLeft: 8 }}>
                              {engUploadDiag.probe_result.ts}
                            </span>
                          </div>
                          {"status" in engUploadDiag.probe_result && (
                            <div>probe_status: {engUploadDiag.probe_result.status}</div>
                          )}
                          {"elapsed_ms" in engUploadDiag.probe_result &&
                            engUploadDiag.probe_result.elapsed_ms !== undefined && (
                              <div>probe_elapsed_ms: {engUploadDiag.probe_result.elapsed_ms}</div>
                            )}
                          {"body_snippet" in engUploadDiag.probe_result &&
                            engUploadDiag.probe_result.body_snippet && (
                              <div>probe_body_snippet: {engUploadDiag.probe_result.body_snippet}</div>
                            )}
                          {"message" in engUploadDiag.probe_result && (
                            <div>probe_message: {engUploadDiag.probe_result.message}</div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                  {/* PT.IU R3 — manual probe button. Always rendered when the
                      Upload Engineering Plan PDFs button is rendered; lets
                      operator test direct-to-Render reachability without
                      DevTools and without firing an actual upload. */}
                  <button
                    type="button"
                    onClick={handleEngUploadProbe}
                    disabled={engUploadDiag?.probe_result?.state === "probing"}
                    style={{
                      marginTop: 8,
                      padding: "6px 10px",
                      fontSize: 11,
                      fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                      background: "#1e293b",
                      color: "#e2e8f0",
                      border: "1px solid #334155",
                      borderRadius: 6,
                      cursor:
                        engUploadDiag?.probe_result?.state === "probing"
                          ? "wait"
                          : "pointer",
                    }}
                  >
                    {engUploadDiag?.probe_result?.state === "probing"
                      ? "Probing..."
                      : "Test backend connection (direct-to-Render)"}
                  </button>
                  {(state?.engineering_plans?.length ?? 0) === 0 ? (
                    <div style={{ fontSize: 13, color: "#94a3b8" }}>No plans uploaded for this session.</div>
                  ) : (
                    state!.engineering_plans!.map((plan: EngineeringPlan) => {
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
                            {uploadedDate ? <span>{uploadedDate}</span> : null}
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              ) : null}
            </div>
          </Section>

          <Section
            title="Map & field tools"
            subtitle={undefined}
            style={{
              display: activeWorkspaceTab === "workspace" ? "block" : "none",
              border: "none",
              background: "transparent",
              boxShadow: "none",
            }}
            headerStyle={{
              display: "none",
            }}
            contentStyle={{
              padding: 0,
            }}
          >
            <div style={{ display: "grid", gap: 6 }}>
              {operationalMap ? (
                <div
                  style={{
                    display: activeWorkspaceTab === "workspace" ? "block" : "none",
                    order: 18,
                  }}
                >
                  {operationalMap}
                </div>
              ) : null}

              <details
                style={{
                  border: "1px solid #e2e8f0",
                  borderRadius: 10,
                  background: "rgba(255, 255, 255, 0.7)",
                  order: 24,
                  display: activeWorkspaceTab === "workspace" ? "block" : "none",
                }}
              >
                <summary
                  style={{
                    padding: "10px 12px",
                    cursor: "pointer",
                    fontSize: 12,
                    color: "#0f172a",
                    fontWeight: 800,
                    listStyle: "none",
                  }}
                >
                  Legacy SVG map (debug / fallback — Project Map above is primary)
                </summary>
                <div style={{ padding: "4px 12px 10px", display: "grid", gap: 8 }}>
                  <div style={{ fontSize: 11, color: "#475569", lineHeight: 1.45 }}>
                    Open this panel only when you need the pre-Leaflet workspace map. Normal ops use{" "}
                    <strong>Project Map</strong>.
                  </div>
                  <label
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 6,
                      cursor: "pointer",
                      userSelect: "none",
                      fontSize: 11,
                      color: "#334155",
                      fontWeight: 700,
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={showLegacyMap}
                      onChange={(e) => setShowLegacyMap(e.target.checked)}
                    />
                    Render legacy SVG surface
                  </label>
                </div>

                {/* ─── Map + Inspector wrapper ─────────────────────────── */}
                {/* Inspector is position:absolute so map container width    */}
                {/* never changes — projection stays stable on station click. */}
                <div style={{ position: "relative", display: showLegacyMap ? "block" : "none" }}>
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
                  <button
                    type="button"
                    onClick={() => setLayerStructures((current) => !current)}
                    style={miniMapButton}
                  >
                    {layerStructures ? "Hide Stations" : "Show Stations"}
                  </button>
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
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      flexWrap: "wrap",
                      padding: "6px 12px",
                      borderRadius: 999,
                      background: "rgba(2, 6, 23, 0.72)",
                      border: "1px solid rgba(148, 163, 184, 0.28)",
                      color: "#e2e8f0",
                      fontSize: 11,
                      fontWeight: 700,
                    }}
                  >
                    <span style={{ opacity: 0.88 }}>Layers</span>
                    {([
                      ["Routes", layerRoutes, setLayerRoutes] as const,
                      ["Structures", layerStructures, setLayerStructures] as const,
                      ["Photos", layerPhotos, setLayerPhotos] as const,
                    ]).map(([label, checked, setter]) => (
                      <label
                        key={label}
                        style={{ display: "inline-flex", alignItems: "center", gap: 5, cursor: "pointer", userSelect: "none" }}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={(e) => setter(e.target.checked)}
                        />
                        {label}
                      </label>
                    ))}
                    {/* Phase 1X — reviewed snap preview overlay toggle. OFF by default. */}
                    <label
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 5,
                        cursor: "pointer",
                        userSelect: "none",
                        color: layerSnapPreview ? "rgba(20,184,166,0.95)" : undefined,
                      }}
                      title="Show deterministic endpoint snap preview geometry (advisory review only)"
                    >
                      <input
                        type="checkbox"
                        checked={layerSnapPreview}
                        onChange={(e) => setLayerSnapPreview(e.target.checked)}
                      />
                      Preview
                    </label>
                  </div>
                  {/* Phase 2E.1 — KMZ folder/category filter panel.
                      Keyed by folder_path.join(" / ") for fine-grained per-folder control.
                      Derived from actual feature data — one row per unique folder path.
                      Filtering is frontend-only — no backend calls, no operational impact. */}
                  {layerKmzContext && kmzRenderPayload && (() => {
                    // Build a map: folderKey -> { shortLabel, fullLabel, count }
                    const _folderMap = new Map<string, { short: string; full: string; count: number }>();
                    const _allFeatures = [
                      ...(kmzRenderPayload.points ?? []),
                      ...(kmzRenderPayload.lines ?? []),
                      ...(kmzRenderPayload.polygons ?? []),
                    ];
                    for (const f of _allFeatures) {
                      const fp = Array.isArray(f.folder_path) ? f.folder_path : [];
                      const key = fp.join(" / ");
                      if (!key) continue;
                      const existing = _folderMap.get(key);
                      if (existing) {
                        existing.count++;
                      } else {
                        const parts = fp;
                        const short = parts[parts.length - 1] ?? key;
                        _folderMap.set(key, { short, full: key, count: 1 });
                      }
                    }
                    if (_folderMap.size === 0) return null;
                    const _folderRows = Array.from(_folderMap.entries()).sort((a, b) => a[0].localeCompare(b[0]));
                    const hasHouseDrop = _folderRows.some(([k]) => k.includes("House Drop"));
                    return (
                      <div
                        style={{
                          marginTop: 4,
                          padding: "6px 10px",
                          background: "rgba(2,8,23,0.82)",
                          border: "1px solid rgba(251,191,36,0.22)",
                          borderRadius: 8,
                          fontSize: 10,
                          color: "#e2e8f0",
                          fontFamily: "ui-sans-serif,system-ui,-apple-system,'Segoe UI',sans-serif",
                          maxHeight: 160,
                          overflowY: "auto",
                          minWidth: 220,
                        }}
                      >
                        {/* Header row */}
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                          <span style={{ fontWeight: 700, fontSize: 10, color: "rgba(251,191,36,0.82)", letterSpacing: "0.04em", textTransform: "uppercase" }}>
                            KMZ Layers
                          </span>
                          <div style={{ display: "flex", gap: 6 }}>
                            {hasHouseDrop && (
                              <button
                                type="button"
                                title="Hide all House Drop folder features"
                                style={{ background: "none", border: "1px solid rgba(148,163,184,0.28)", borderRadius: 4, cursor: "pointer", color: "rgba(148,163,184,0.72)", fontSize: 9, padding: "1px 5px" }}
                                onClick={() => {
                                  setKmzHiddenCategories(prev => {
                                    const next = new Set(prev);
                                    for (const [k] of _folderRows) {
                                      if (k.includes("House Drop")) next.add(k);
                                    }
                                    return next;
                                  });
                                }}
                              >
                                Hide drops
                              </button>
                            )}
                            <button
                              type="button"
                              title="Show all KMZ folders"
                              style={{ background: "none", border: "1px solid rgba(148,163,184,0.28)", borderRadius: 4, cursor: "pointer", color: "rgba(148,163,184,0.72)", fontSize: 9, padding: "1px 5px" }}
                              onClick={() => setKmzHiddenCategories(new Set())}
                            >
                              Show all
                            </button>
                          </div>
                        </div>
                        {/* Folder rows */}
                        {_folderRows.map(([_folderKey, _meta]) => {
                          const _isVisible = !kmzHiddenCategories.has(_folderKey);
                          return (
                            <label
                              key={_folderKey}
                              title={_meta.full}
                              style={{
                                display: "flex",
                                alignItems: "center",
                                gap: 5,
                                cursor: "pointer",
                                userSelect: "none",
                                padding: "1px 0",
                                color: _isVisible ? "#cbd5e1" : "rgba(148,163,184,0.38)",
                              }}
                            >
                              <input
                                type="checkbox"
                                checked={_isVisible}
                                onChange={(e) => {
                                  setKmzHiddenCategories(prev => {
                                    const next = new Set(prev);
                                    if (e.target.checked) next.delete(_folderKey);
                                    else next.add(_folderKey);
                                    return next;
                                  });
                                }}
                                style={{ accentColor: "rgba(251,191,36,0.9)", cursor: "pointer" }}
                              />
                              <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                {_meta.short}
                              </span>
                              <span style={{ color: "rgba(148,163,184,0.45)", fontSize: 9, flexShrink: 0 }}>
                                {_meta.count}
                              </span>
                            </label>
                          );
                        })}
                      </div>
                    );
                  })()}
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                    <button
                      type="button"
                      onClick={() => setMapBaseStyle("standard")}
                      title="Lighter cartographic-style base"
                      style={{
                        ...miniMapButton,
                        ...(mapBaseStyle === "standard"
                          ? {
                              background: "rgba(30, 58, 95, 0.88)",
                              borderColor: "rgba(147, 197, 253, 0.42)",
                              color: "#e0f2fe",
                            }
                          : {}),
                      }}
                    >
                      Standard map
                    </button>
                    <button
                      type="button"
                      onClick={() => setMapBaseStyle("satellite")}
                      title="Dark aerial-style base (default)"
                      style={{
                        ...miniMapButton,
                        ...(mapBaseStyle === "satellite"
                          ? {
                              background: "rgba(30, 58, 95, 0.88)",
                              borderColor: "rgba(147, 197, 253, 0.42)",
                              color: "#e0f2fe",
                            }
                          : {}),
                      }}
                    >
                      Satellite
                    </button>
                  </div>
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
                      <radialGradient id="standard-map-wash" cx="38%" cy="32%" r="78%">
                        <stop offset="0%" stopColor="#f1f5f9" />
                        <stop offset="45%" stopColor="#cbd5e1" />
                        <stop offset="100%" stopColor="#94a3b8" />
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
                        fill={mapBaseStyle === "satellite" ? "url(#satellite-map-wash)" : "url(#standard-map-wash)"}
                      />
                      <rect
                        x={0}
                        y={0}
                        width={projectionMetrics?.worldWidth || PROJECTION_BASE_WIDTH}
                        height={projectionMetrics?.worldHeight || PROJECTION_BASE_WIDTH}
                        fill="url(#terrain-speckle-pattern)"
                        opacity={mapBaseStyle === "satellite" ? (presentationView ? 0.42 : 1) : (presentationView ? 0.22 : 0.45)}
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

                      {layerRoutes ? (
                        <>
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
                        </>
                      ) : null}
                    </g>

                    {layerRoutes ? (
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
                    ) : null}

                    {/* Phase 2A — KMZ Engineering Context Layer.
                        Advisory display-only. Never mutates operational geometry.
                        Renders ONLY when layerKmzContext toggle is ON.
                        Drawn BEFORE operational redlines so redlines stay on top.
                        pointerEvents="none" on all elements — no click interception.
                        Render order: polygons → lines → points → labels. */}
                    {layerKmzContext && renderBounds && projectionMetrics && kmzRenderPayload ? (
                      /* Phase 2C: opacity={0.78} whole-layer dimming — KMZ stays behind operational redlines */
                      <g id="kmz-context-layer" aria-label="KMZ engineering context (advisory)" opacity={0.78}>
                        {/* 1. Polygons — muted fill, evenodd inner-ring holes, clickable */}
                        {(kmzRenderPayload.polygons ?? []).map((poly) => {
                          if (kmzHiddenCategories.has((poly.folder_path ?? []).join(" / "))) return null;
                          const outerCoords = poly.outer;
                          if (!Array.isArray(outerCoords) || outerCoords.length < 3) return null;
                          const validOuter: number[][] = [];
                          for (const pt of outerCoords) {
                            if (Array.isArray(pt) && pt.length >= 2 && typeof pt[0] === "number" && typeof pt[1] === "number" && Number.isFinite(pt[0]) && Number.isFinite(pt[1])) {
                              validOuter.push([pt[0], pt[1]]);
                            }
                          }
                          if (validOuter.length < 3) return null;
                          const outerPath = buildWorldPath([...validOuter, validOuter[0]], renderBounds, projectionMetrics);
                          if (!outerPath) return null;
                          let combinedPath = outerPath + " Z";
                          for (const ring of (Array.isArray(poly.inner) ? poly.inner : [])) {
                            if (!Array.isArray(ring) || ring.length < 3) continue;
                            const validInner: number[][] = [];
                            for (const ip of ring) {
                              if (Array.isArray(ip) && ip.length >= 2 && typeof ip[0] === "number" && typeof ip[1] === "number" && Number.isFinite(ip[0]) && Number.isFinite(ip[1])) {
                                validInner.push([ip[0], ip[1]]);
                              }
                            }
                            if (validInner.length < 3) continue;
                            const innerPath = buildWorldPath([...validInner, validInner[0]], renderBounds, projectionMetrics);
                            if (innerPath) combinedPath += " " + innerPath + " Z";
                          }
                          const fillColor = muteKmzColor(poly.fill_color);
                          return (
                            <path
                              key={`kmzpoly-${poly.feature_id}`}
                              d={combinedPath}
                              fillRule="evenodd"
                              fill={fillColor}
                              fillOpacity={0.10}
                              stroke={fillColor}
                              strokeWidth={0.9}
                              strokeOpacity={0.35}
                              vectorEffect="non-scaling-stroke"
                              style={{ cursor: "pointer" }}
                              onClick={(e) => { e.stopPropagation(); setSelectedKmzFeature({ feature_id: poly.feature_id, feature_type: "polygon", name: poly.name, classification: poly.classification, folder_path: poly.folder_path, description: poly.description, extended_data: poly.extended_data, chainage_ft: poly.chainage_ft, sequence_number: poly.sequence_number, sequence_kind: poly.sequence_kind, lifecycle: poly.lifecycle }); }}
                            />
                          );
                        })}
                        {/* 2. Lines — muted color, dark casing, slimmed width, clickable */}
                        {(kmzRenderPayload.lines ?? []).map((line) => {
                          if (kmzHiddenCategories.has((line.folder_path ?? []).join(" / "))) return null;
                          const lineCoords = line.coords;
                          if (!Array.isArray(lineCoords) || lineCoords.length < 2) return null;
                          const validLine: number[][] = [];
                          for (const pt of lineCoords) {
                            if (Array.isArray(pt) && pt.length >= 2 && typeof pt[0] === "number" && typeof pt[1] === "number" && Number.isFinite(pt[0]) && Number.isFinite(pt[1])) {
                              validLine.push([pt[0], pt[1]]);
                            }
                          }
                          if (validLine.length < 2) return null;
                          const linePath = buildWorldPath(validLine, renderBounds, projectionMetrics);
                          if (!linePath) return null;
                          const lineColor = muteKmzColor(line.color);
                          const lineWidth = Math.min(line.width ?? 1.2, 1.4);
                          const dashArr = line.dash ? "5 3" : undefined;
                          const _onClickLine = (e: React.MouseEvent) => { e.stopPropagation(); setSelectedKmzFeature({ feature_id: line.feature_id, feature_type: "line", name: line.name, classification: line.classification, folder_path: line.folder_path, description: line.description, extended_data: line.extended_data, chainage_ft: line.chainage_ft, sequence_number: line.sequence_number, sequence_kind: line.sequence_kind, lifecycle: line.lifecycle }); };
                          return (
                            <g key={`kmzline-${line.feature_id}`} style={{ cursor: "pointer" }} onClick={_onClickLine}>
                              {/* Dark satellite casing — wide hit area */}
                              <path d={linePath} fill="none" stroke="rgba(15,23,42,0.55)" strokeWidth={lineWidth + 0.9} strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" pointerEvents="none" />
                              {/* Transparent wider hit path for easier click */}
                              <path d={linePath} fill="none" stroke="transparent" strokeWidth={8} strokeLinecap="round" pointerEvents="stroke" />
                              {/* Muted feature color */}
                              <path d={linePath} fill="none" stroke={lineColor} strokeWidth={lineWidth} strokeOpacity={0.42} strokeDasharray={dashArr} strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" pointerEvents="none" />
                            </g>
                          );
                        })}
                        {/* 3. Points — smaller glyphs, muted colors, dark outline, clickable */}
                        {(kmzRenderPayload.points ?? []).map((pt) => {
                          if (kmzHiddenCategories.has((pt.folder_path ?? []).join(" / "))) return null;
                          if (!Array.isArray(pt.coord) || pt.coord.length < 2) return null;
                          const [ptLat, ptLon] = pt.coord;
                          if (!Number.isFinite(ptLat) || !Number.isFinite(ptLon)) return null;
                          const ptColor = muteKmzColor(pt.color);
                          const { x: svgX, y: svgY } = projectWorldPoint(ptLat, ptLon, renderBounds, projectionMetrics);
                          const glyph = pt.icon_glyph ?? "ring";
                          const halo = "rgba(15,23,42,0.65)";
                          const _onClickPt = (e: React.MouseEvent) => { e.stopPropagation(); setSelectedKmzFeature({ feature_id: pt.feature_id, feature_type: "point", name: pt.name, classification: pt.classification, folder_path: pt.folder_path, description: pt.description, extended_data: pt.extended_data, chainage_ft: pt.chainage_ft, sequence_number: pt.sequence_number, sequence_kind: pt.sequence_kind, lifecycle: pt.lifecycle }); };
                          return (
                            <g key={`kmzpt-${pt.feature_id}`} style={{ cursor: "pointer" }} onClick={_onClickPt}>
                              {/* Transparent hit circle for easier touch/click */}
                              <circle cx={svgX} cy={svgY} r={7} fill="transparent" pointerEvents="all" />
                              {glyph === "circle" && (
                                <circle cx={svgX} cy={svgY} r={2.2} fill={ptColor} fillOpacity={0.55} stroke={halo} strokeWidth={0.9} vectorEffect="non-scaling-stroke" pointerEvents="none" />
                              )}
                              {glyph === "square" && (
                                <rect x={svgX - 2} y={svgY - 2} width={4} height={4} fill={ptColor} fillOpacity={0.55} stroke={halo} strokeWidth={0.9} vectorEffect="non-scaling-stroke" pointerEvents="none" />
                              )}
                              {glyph === "diamond" && (
                                <polygon points={`${svgX},${svgY - 3} ${svgX + 2.4},${svgY} ${svgX},${svgY + 3} ${svgX - 2.4},${svgY}`} fill={ptColor} fillOpacity={0.55} stroke={halo} strokeWidth={0.9} vectorEffect="non-scaling-stroke" pointerEvents="none" />
                              )}
                              {glyph === "ring" && (
                                <circle cx={svgX} cy={svgY} r={2.2} fill="none" stroke={ptColor} strokeOpacity={0.62} strokeWidth={1.1} vectorEffect="non-scaling-stroke" pointerEvents="none" />
                              )}
                            </g>
                          );
                        })}
                        {/* 4. Point labels — halo for readability, neutral fill, 16-char truncation */}
                        {viewport.zoom >= LOW_ZOOM_LABEL_THRESHOLD && (kmzRenderPayload.points ?? []).map((pt) => {
                          if (kmzHiddenCategories.has((pt.folder_path ?? []).join(" / "))) return null;
                          if (!pt.name) return null;
                          if (!Array.isArray(pt.coord) || pt.coord.length < 2) return null;
                          const [ptLat, ptLon] = pt.coord;
                          if (!Number.isFinite(ptLat) || !Number.isFinite(ptLon)) return null;
                          const { x: svgX, y: svgY } = projectWorldPoint(ptLat, ptLon, renderBounds, projectionMetrics);
                          const display = pt.name.length > 16 ? pt.name.slice(0, 16) + "…" : pt.name;
                          return (
                            <text
                              key={`kmzlbl-${pt.feature_id}`}
                              x={svgX + 4}
                              y={svgY - 4}
                              fontSize={7}
                              fontFamily="ui-sans-serif,system-ui,-apple-system,'Segoe UI',sans-serif"
                              fontWeight={500}
                              fill="rgba(226,232,240,0.88)"
                              stroke="rgba(15,23,42,0.88)"
                              strokeWidth={2.4}
                              paintOrder="stroke"
                              strokeLinejoin="round"
                              pointerEvents="none"
                            >
                              {display}
                            </text>
                          );
                        })}
                        {/* 5. Line labels — "House Drop" suppressed (density); others halo-styled */}
                        {viewport.zoom >= LOW_ZOOM_LABEL_THRESHOLD && (kmzRenderPayload.lines ?? []).map((line) => {
                          if (kmzHiddenCategories.has((line.folder_path ?? []).join(" / "))) return null;
                          if (!line.name || line.name === "House Drop") return null;
                          const _lineClasses = new Set(["cable", "cable_route", "backbone", "lateral", "drop", "duct", "route_segment"]);
                          if (!_lineClasses.has(line.classification)) return null;
                          const lineCoords = line.coords;
                          if (!Array.isArray(lineCoords) || lineCoords.length < 2) return null;
                          const midIdx = Math.floor(lineCoords.length / 2);
                          const midPt = lineCoords[midIdx];
                          if (!Array.isArray(midPt) || midPt.length < 2) return null;
                          const [mlat, mlon] = midPt;
                          if (!Number.isFinite(mlat) || !Number.isFinite(mlon)) return null;
                          const { x: svgX, y: svgY } = projectWorldPoint(mlat, mlon, renderBounds, projectionMetrics);
                          const display = line.name.length > 16 ? line.name.slice(0, 16) + "…" : line.name;
                          return (
                            <text
                              key={`kmzlinelbl-${line.feature_id}`}
                              x={svgX + 4}
                              y={svgY - 4}
                              fontSize={7}
                              fontFamily="ui-sans-serif,system-ui,-apple-system,'Segoe UI',sans-serif"
                              fontWeight={500}
                              fill="rgba(226,232,240,0.88)"
                              stroke="rgba(15,23,42,0.88)"
                              strokeWidth={2.4}
                              paintOrder="stroke"
                              strokeLinejoin="round"
                              pointerEvents="none"
                            >
                              {display}
                            </text>
                          );
                        })}
                        {/* 6. Polygon labels — halo-styled at centroid */}
                        {viewport.zoom >= LOW_ZOOM_LABEL_THRESHOLD && (kmzRenderPayload.polygons ?? []).map((poly) => {
                          if (kmzHiddenCategories.has((poly.folder_path ?? []).join(" / "))) return null;
                          if (!poly.name) return null;
                          const outerCoords = poly.outer;
                          if (!Array.isArray(outerCoords) || outerCoords.length < 3) return null;
                          let sumLat = 0, sumLon = 0, cnt = 0;
                          for (const pv of outerCoords) {
                            if (Array.isArray(pv) && pv.length >= 2 && Number.isFinite(pv[0]) && Number.isFinite(pv[1])) {
                              sumLat += pv[0]; sumLon += pv[1]; cnt++;
                            }
                          }
                          if (cnt === 0) return null;
                          const { x: svgX, y: svgY } = projectWorldPoint(sumLat / cnt, sumLon / cnt, renderBounds, projectionMetrics);
                          const display = poly.name.length > 16 ? poly.name.slice(0, 16) + "…" : poly.name;
                          return (
                            <text
                              key={`kmzpolylbl-${poly.feature_id}`}
                              x={svgX + 4}
                              y={svgY - 4}
                              fontSize={7}
                              fontFamily="ui-sans-serif,system-ui,-apple-system,'Segoe UI',sans-serif"
                              fontWeight={500}
                              fill="rgba(226,232,240,0.88)"
                              stroke="rgba(15,23,42,0.88)"
                              strokeWidth={2.4}
                              paintOrder="stroke"
                              strokeLinejoin="round"
                              pointerEvents="none"
                            >
                              {display}
                            </text>
                          );
                        })}
                        {/* In-map legend */}
                        <g pointerEvents="none" transform="translate(12, 38)">
                          {(() => {
                            const _anyCapped = kmzRenderPayload.summary?.points_truncated || kmzRenderPayload.summary?.lines_truncated || kmzRenderPayload.summary?.polygons_truncated;
                            const _legendH = _anyCapped ? 38 : 22;
                            return (
                              <>
                                <rect x={0} y={0} width={150} height={_legendH} rx={3} fill="rgba(0,0,0,0.52)" stroke="rgba(251,191,36,0.45)" strokeWidth={0.8} />
                                <circle cx={10} cy={11} r={3.5} fill="none" stroke="rgba(251,191,36,0.85)" strokeWidth={1.2} />
                                <text x={20} y={15} fill="rgba(251,191,36,0.92)" fontSize={9} fontFamily="monospace" fontWeight="600">
                                  KMZ context
                                </text>
                                {_anyCapped && (
                                  <text x={20} y={31} fill="rgba(251,191,36,0.65)" fontSize={7} fontFamily="monospace">
                                    +more (capped)
                                  </text>
                                )}
                              </>
                            );
                          })()}
                        </g>
                      </g>
                    ) : null}

                    {/* Phase 1X — Reviewed Snap Preview Overlay.
                        Advisory review aid only. Never mutates operational geometry.
                        Renders ONLY when layerSnapPreview toggle is ON.
                        pointerEvents="none" on all elements — no click interception.
                        presentation_role guard: only "preview_polyline" entries rendered. */}
                    {layerSnapPreview && renderBounds && projectionMetrics ? (
                      <g id="snap-preview-layer" aria-label="Reviewed preview geometry (advisory)">
                        {(snapPreviewData?.previews ?? []).map((preview) => {
                          // Safety guard: only render advisory preview_polyline entries.
                          if (preview.presentation_role !== "preview_polyline") return null;
                          const rawCoords = preview.preview_geometry?.coordinates;
                          if (!Array.isArray(rawCoords) || rawCoords.length < 2) return null;
                          // GeoJSON coordinates are [lon, lat]; buildWorldPath expects [lat, lon].
                          const latLonCoords: number[][] = [];
                          for (const pt of rawCoords) {
                            if (
                              Array.isArray(pt) &&
                              pt.length >= 2 &&
                              typeof pt[0] === "number" &&
                              typeof pt[1] === "number" &&
                              Number.isFinite(pt[0]) &&
                              Number.isFinite(pt[1])
                            ) {
                              latLonCoords.push([pt[1], pt[0]]); // swap: [lon,lat]→[lat,lon]
                            }
                          }
                          if (latLonCoords.length < 2) return null;
                          const previewPath = buildWorldPath(latLonCoords, renderBounds, projectionMetrics);
                          if (!previewPath) return null;
                          return (
                            <g key={preview.preview_id} pointerEvents="none">
                              {/* Outer halo for visibility against dark redlines */}
                              <path
                                d={previewPath}
                                fill="none"
                                stroke="rgba(0,0,0,0.35)"
                                strokeWidth={3.4}
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeDasharray="5 4"
                                vectorEffect="non-scaling-stroke"
                                pointerEvents="none"
                              />
                              {/* Advisory preview line — dashed teal, thinner than operational */}
                              <path
                                d={previewPath}
                                fill="none"
                                stroke="rgba(20,184,166,0.82)"
                                strokeWidth={1.9}
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeDasharray="5 4"
                                vectorEffect="non-scaling-stroke"
                                pointerEvents="none"
                              />
                            </g>
                          );
                        })}
                        {/* In-map legend — visible only when overlay is active */}
                        <g pointerEvents="none" transform="translate(12, 12)">
                          <rect
                            x={0}
                            y={0}
                            width={180}
                            height={22}
                            rx={3}
                            fill="rgba(0,0,0,0.52)"
                            stroke="rgba(20,184,166,0.55)"
                            strokeWidth={0.8}
                          />
                          <line
                            x1={8}
                            y1={11}
                            x2={26}
                            y2={11}
                            stroke="rgba(20,184,166,0.9)"
                            strokeWidth={2}
                            strokeDasharray="4 3"
                            strokeLinecap="round"
                          />
                          <text
                            x={32}
                            y={15}
                            fill="rgba(20,184,166,0.92)"
                            fontSize={9}
                            fontFamily="monospace"
                            fontWeight="600"
                          >
                            Preview geometry (review-only)
                          </text>
                        </g>
                      </g>
                    ) : null}

                    {layerStructures ? (
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
                      <g id="field-session-overlay">
                        {layerRoutes && showFieldGpsEvidenceTrail && fieldTrackPath ? (
                          <path
                            d={fieldTrackPath}
                            fill="none"
                            stroke="#94a3b8"
                            strokeWidth={2}
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeDasharray="4 6"
                            strokeOpacity={0.45}
                            vectorEffect="non-scaling-stroke"
                            pointerEvents="none"
                          />
                        ) : null}
                        {layerRoutes && fieldStationPath ? (
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
                            pointerEvents="none"
                          />
                        ) : null}
                        {layerStructures
                          ? projectedFieldStations.map(({ st, world }, fsi) => {
                              const isFSSelected = selectedFieldStationIdx === fsi;
                              const isFSHovered = hoverFieldStationIdx === fsi;
                              const baseR = 4;
                              const r = isFSSelected ? baseR + 1.2 : isFSHovered ? baseR + 0.6 : baseR;
                              const viewWidth = projectionMetrics.worldWidth / viewport.zoom;
                              const viewHeight = projectionMetrics.worldHeight / viewport.zoom;
                              const viewX = -viewport.panX / viewport.zoom;
                              const viewY = -viewport.panY / viewport.zoom;
                              const isFSMarkerVisible =
                                world.x >= viewX &&
                                world.x <= viewX + viewWidth &&
                                world.y >= viewY &&
                                world.y <= viewY + viewHeight;
                              return (
                                <g
                                  key={`field-station-${st.id}`}
                                  style={{ cursor: "pointer" }}
                                  onPointerDown={(e) => e.stopPropagation()}
                                  onPointerEnter={() => setHoverFieldStationIdx(fsi)}
                                  onPointerLeave={() =>
                                    setHoverFieldStationIdx((cur) => (cur === fsi ? null : cur))
                                  }
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setSelectedFieldStationIdx((cur) => (cur === fsi ? null : fsi));
                                  }}
                                >
                                  {(isFSSelected || isFSHovered) ? (
                                    <circle
                                      cx={world.x}
                                      cy={world.y}
                                      r={r + 2.2}
                                      fill={isFSSelected ? "rgba(250,204,21,0.18)" : "rgba(255,255,255,0.10)"}
                                      pointerEvents="none"
                                    />
                                  ) : null}
                                  <circle
                                    cx={world.x}
                                    cy={world.y}
                                    r={r}
                                    fill="#facc15"
                                    stroke={isFSSelected ? "rgba(255,255,255,0.9)" : "rgba(14,24,34,0.85)"}
                                    strokeWidth={isFSSelected ? 0.9 : 0.8}
                                    vectorEffect="non-scaling-stroke"
                                  />
                                  {isFSMarkerVisible ? (
                                    <text
                                      x={world.x + 4.5}
                                      y={world.y - 3.5}
                                      fill="#facc15"
                                      fontSize={5}
                                      fontWeight="700"
                                      stroke="rgba(14,24,34,0.85)"
                                      strokeWidth={2.5}
                                      paintOrder="stroke"
                                      pointerEvents="none"
                                      style={{ userSelect: "none" }}
                                    >
                                      {st.station_number}
                                    </text>
                                  ) : null}
                                </g>
                              );
                            })
                          : null}
                      </g>
                    ) : null}

                    {/* ─── V1 Photo GPS Mapping — photo marker layer ───── */}
                    {/* Renders above stations, below the station tooltip.  */}
                    {/* Distinct amber pin shape so photos never visually    */}
                    {/* collide with the black station dots.                 */}
                    {layerPhotos && projectedPhotos.length > 0 ? (
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
                    Upload field data to render map output.
                  </div>
                )}

                {/* Phase 2D — KMZ Feature Info Popup.
                    Read-only. No operational impact. No backend calls.
                    Anchored top-right inside map container. Closes on X button.
                    Positioned to avoid layer-controls widget (which is top-right at z=25). */}
                {selectedKmzFeature && (
                  <div
                    style={{
                      position: "absolute",
                      top: 56,
                      right: 12,
                      zIndex: 30,
                      width: 320,
                      maxWidth: "calc(100% - 24px)",
                      background: "rgba(2,8,23,0.93)",
                      border: "1px solid rgba(148,163,184,0.28)",
                      borderRadius: 10,
                      boxShadow: "0 4px 32px rgba(0,0,0,0.72), inset 0 1px 0 rgba(255,255,255,0.05)",
                      fontFamily: "ui-sans-serif,system-ui,-apple-system,'Segoe UI',sans-serif",
                      fontSize: 11,
                      color: "#e2e8f0",
                      pointerEvents: "all",
                      userSelect: "text",
                    }}
                  >
                    {/* Header row */}
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 12px 6px", borderBottom: "1px solid rgba(148,163,184,0.15)" }}>
                      <span style={{ fontWeight: 700, fontSize: 11, color: "rgba(251,191,36,0.92)", letterSpacing: "0.04em", textTransform: "uppercase" }}>
                        KMZ Feature
                      </span>
                      <button
                        type="button"
                        onClick={() => setSelectedKmzFeature(null)}
                        style={{ background: "none", border: "none", cursor: "pointer", color: "rgba(148,163,184,0.72)", fontSize: 14, lineHeight: 1, padding: "0 2px", display: "flex", alignItems: "center" }}
                        title="Close"
                        aria-label="Close KMZ feature info"
                      >
                        ×
                      </button>
                    </div>

                    {/* Body */}
                    <div style={{ padding: "8px 12px 10px", display: "flex", flexDirection: "column", gap: 5 }}>
                      {/* Name */}
                      {selectedKmzFeature.name && (
                        <div>
                          <span style={{ color: "rgba(148,163,184,0.65)", marginRight: 4 }}>Name</span>
                          <span style={{ fontWeight: 600, color: "#f1f5f9" }}>{selectedKmzFeature.name}</span>
                        </div>
                      )}
                      {/* Type / Classification */}
                      <div style={{ display: "flex", gap: 12 }}>
                        <div>
                          <span style={{ color: "rgba(148,163,184,0.65)", marginRight: 4 }}>Type</span>
                          <span style={{ color: "#cbd5e1" }}>{selectedKmzFeature.feature_type}</span>
                        </div>
                        {selectedKmzFeature.classification && (
                          <div>
                            <span style={{ color: "rgba(148,163,184,0.65)", marginRight: 4 }}>Class</span>
                            <span style={{ color: "#cbd5e1" }}>{selectedKmzFeature.classification}</span>
                          </div>
                        )}
                      </div>
                      {/* Folder path */}
                      {Array.isArray(selectedKmzFeature.folder_path) && selectedKmzFeature.folder_path.length > 0 && (
                        <div>
                          <span style={{ color: "rgba(148,163,184,0.65)", marginRight: 4 }}>Folder</span>
                          <span style={{ color: "#94a3b8", fontStyle: "italic" }}>{selectedKmzFeature.folder_path.join(" / ")}</span>
                        </div>
                      )}
                      {/* Description */}
                      {selectedKmzFeature.description && (
                        <div>
                          <div style={{ color: "rgba(148,163,184,0.65)", marginBottom: 2 }}>Description</div>
                          <div style={{ color: "#cbd5e1", lineHeight: 1.45, whiteSpace: "pre-wrap", wordBreak: "break-word", maxHeight: 60, overflow: "hidden" }}>
                            {selectedKmzFeature.description.length > 180 ? selectedKmzFeature.description.slice(0, 180) + "…" : selectedKmzFeature.description}
                          </div>
                        </div>
                      )}
                      {/* Chainage */}
                      {selectedKmzFeature.chainage_ft != null && (
                        <div>
                          <span style={{ color: "rgba(148,163,184,0.65)", marginRight: 4 }}>Chainage</span>
                          <span style={{ color: "#cbd5e1" }}>{selectedKmzFeature.chainage_ft} ft</span>
                        </div>
                      )}
                      {/* Sequence */}
                      {(selectedKmzFeature.sequence_number || selectedKmzFeature.sequence_kind) && (
                        <div style={{ display: "flex", gap: 12 }}>
                          {selectedKmzFeature.sequence_number && (
                            <div>
                              <span style={{ color: "rgba(148,163,184,0.65)", marginRight: 4 }}>Seq#</span>
                              <span style={{ color: "#cbd5e1" }}>{selectedKmzFeature.sequence_number}</span>
                            </div>
                          )}
                          {selectedKmzFeature.sequence_kind && (
                            <div>
                              <span style={{ color: "rgba(148,163,184,0.65)", marginRight: 4 }}>Kind</span>
                              <span style={{ color: "#cbd5e1" }}>{selectedKmzFeature.sequence_kind}</span>
                            </div>
                          )}
                        </div>
                      )}
                      {/* Lifecycle */}
                      {selectedKmzFeature.lifecycle && (
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <span style={{ color: "rgba(148,163,184,0.65)", marginRight: 4 }}>Lifecycle</span>
                          <span style={{ color: "#fbbf24", fontWeight: 600 }}>{selectedKmzFeature.lifecycle.label}</span>
                          {selectedKmzFeature.lifecycle.confidence && (
                            <span style={{ color: "rgba(148,163,184,0.55)", fontSize: 10 }}>({selectedKmzFeature.lifecycle.confidence})</span>
                          )}
                        </div>
                      )}
                      {/* Extended data */}
                      {selectedKmzFeature.extended_data && Object.keys(selectedKmzFeature.extended_data).length > 0 && (
                        <div style={{ marginTop: 4, borderTop: "1px solid rgba(148,163,184,0.12)", paddingTop: 5 }}>
                          <div style={{ color: "rgba(148,163,184,0.65)", marginBottom: 3, fontSize: 10, textTransform: "uppercase", letterSpacing: "0.05em" }}>Extended data</div>
                          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                            {Object.entries(selectedKmzFeature.extended_data).slice(0, 8).map(([k, v]) => (
                              <div key={k} style={{ display: "flex", gap: 6, alignItems: "baseline" }}>
                                <span style={{ color: "rgba(148,163,184,0.72)", minWidth: 80, flexShrink: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{k}</span>
                                <span style={{ color: "#cbd5e1", wordBreak: "break-word" }}>{String(v)}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
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

                {/* ─── Field station info card ──────────────────────── */}
                {(() => {
                  if (selectedFieldStationIdx === null) return null;
                  if (!projectionMetrics) return null;
                  const hit = projectedFieldStations[selectedFieldStationIdx];
                  if (!hit) return null;
                  const { st, world } = hit;

                  const vbWidth = projectionMetrics.worldWidth / viewport.zoom;
                  const vbHeight = projectionMetrics.worldHeight / viewport.zoom;
                  const vbX = -viewport.panX / viewport.zoom;
                  const vbY = -viewport.panY / viewport.zoom;
                  const screenX = ((world.x - vbX) / vbWidth) * containerSize.width;
                  const screenY = ((world.y - vbY) / vbHeight) * containerSize.height;

                  const cardWidth = 240;
                  const cardHeightEst = 230;
                  const margin = 12;
                  const placeRight = screenX + margin + cardWidth < containerSize.width;
                  const cardLeft = placeRight
                    ? Math.min(screenX + margin, containerSize.width - cardWidth - 4)
                    : Math.max(screenX - cardWidth - margin, 4);
                  const cardTop = Math.max(
                    4,
                    Math.min(screenY - cardHeightEst / 2, containerSize.height - cardHeightEst - 4),
                  );

                  const stFt = fieldStationFtFromRow(st);
                  const crew = selectedFieldSession?.crew_name?.trim() || "—";
                  const dateStr = selectedFieldSession?.started_at
                    ? new Date(selectedFieldSession.started_at).toLocaleString()
                    : "—";
                  const photoCount = selectedFieldSession?.photo_count ?? null;

                  const rows: [string, string][] = [
                    ["Station FT", Number.isFinite(stFt) ? String(stFt) : "—"],
                    ["Depth FT", st.depth_ft != null ? String(st.depth_ft) : "—"],
                    ["BOC FT", st.boc_ft != null ? String(st.boc_ft) : "—"],
                    ["Crew", crew],
                    ["Date", dateStr],
                    ...(photoCount != null ? [["Photos", String(photoCount)] as [string, string]] : []),
                    ["Session", st.session_id ?? "—"],
                  ];

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
                        boxShadow: "0 20px 45px rgba(0,0,0,0.58), 0 0 0 1px rgba(250,204,21,0.08) inset",
                        overflow: "hidden",
                        zIndex: 900,
                        fontSize: 12,
                        color: "#f8fafc",
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
                          background: "rgba(15,23,42,0.46)",
                        }}
                      >
                        <div style={{ fontSize: 11, fontWeight: 800, color: "#facc15", letterSpacing: 0.4 }}>
                          FIELD STATION
                        </div>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedFieldStationIdx(null);
                          }}
                          aria-label="Close field station info"
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
                      <div style={{ padding: "10px 12px", display: "flex", flexDirection: "column", gap: 5 }}>
                        <div style={{ fontSize: 20, fontWeight: 800, color: "#facc15", letterSpacing: -0.3, marginBottom: 4 }}>
                          {st.station_number}
                        </div>
                        {rows.map(([label, value]) => (
                          <div
                            key={label}
                            style={{
                              display: "flex",
                              justifyContent: "space-between",
                              gap: 8,
                              borderBottom: "1px solid rgba(148,163,184,0.08)",
                              paddingBottom: 4,
                            }}
                          >
                            <span style={{ color: "#94a3b8", fontWeight: 600, whiteSpace: "nowrap" }}>{label}</span>
                            <span style={{ color: "#f1f5f9", textAlign: "right", wordBreak: "break-all" }}>{value}</span>
                          </div>
                        ))}
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
                          ...(selectedStation?.business_id != null &&
                          String(selectedStation.business_id).trim() !== ""
                            ? ([["Business ID", cleanDisplayText(String(selectedStation.business_id))]] as [string, string][])
                            : []),
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

                    {isFiberPullWorkspace ? (
                      <div
                        style={{
                          padding: "12px 14px",
                          flexShrink: 0,
                          borderTop: "1px solid rgba(148, 163, 184, 0.14)",
                          fontSize: 12,
                          lineHeight: 1.5,
                          color: "#94a3b8",
                          fontStyle: "italic",
                        }}
                      >
                        Fiber workflow data will appear here once project data is loaded.
                      </div>
                    ) : null}

                    {/* Photos */}
                    {stationPhotos.length > 0 ? (
                      <div style={{ padding: "0 14px 14px", flexShrink: 0 }}>
                        <div style={{ fontSize: 11, fontWeight: 800, color: "#64748b", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8 }}>
                          Photos ({stationPhotos.length})
                        </div>
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                          {stationPhotos.map((photo) => (
                            <StationPhotoCard key={photo.photo_id} photo={photo} />
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
              </details>

              {/* ─── Phase 4D: Field Submissions Inbox ───────────────────── */}
              {/* Secondary in Map tab: keep the map as the first workspace surface. */}
              <div style={{ display: activeWorkspaceTab === "workspace" ? "block" : "none", order: 30 }}>
                <FieldSubmissionsInboxPanel
                  collapsible
                  inboxRefreshRef={fieldInboxRefreshRef}
                  onSelectSession={(sessionId, jobId) => {
                    setSelectedFieldSessionId(sessionId);
                    setSelectedFieldJobId(jobId);
                  }}
                  showViewAllLink={false}
                />
                {selectedFieldSessionId ? (
                  <div style={{ marginTop: 16 }}>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "flex-end",
                        flexWrap: "wrap",
                        gap: 8,
                        marginBottom: 10,
                      }}
                    >
                      <button
                        type="button"
                        onClick={handlePrintSessionPacket}
                        disabled={!selectedFieldSession || !selectedFieldJobDetail}
                        style={{
                          padding: "6px 12px",
                          fontSize: 12,
                          fontWeight: 700,
                          borderRadius: 10,
                          border: "1px solid #cfd8e3",
                          background: "#ffffff",
                          color: "#0f172a",
                          cursor:
                            selectedFieldSession && selectedFieldJobDetail
                              ? "pointer"
                              : "not-allowed",
                          opacity: selectedFieldSession && selectedFieldJobDetail ? 1 : 0.55,
                        }}
                      >
                        Generate Closeout Packet
                      </button>
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
                    <label
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 8,
                        marginBottom: 10,
                        fontSize: 12,
                        color: "#475569",
                        cursor: "pointer",
                        userSelect: "none",
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={showFieldGpsEvidenceTrail}
                        onChange={(e) => setShowFieldGpsEvidenceTrail(e.target.checked)}
                      />
                      Show GPS evidence trail
                    </label>
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
                      <>
                        <SelectedSubmissionReviewPanel
                          selectedSessionId={selectedFieldSessionId}
                          session={selectedFieldSession}
                          projectId={projectId}
                          onArchived={() => {
                            clearFieldSubmissionSelection();
                            fieldInboxRefreshRef.current?.();
                          }}
                        />
                        {(() => {
                          const sessionPhotos = (selectedFieldJobDetail.photos ?? []).filter(
                            (p) => String(p.session_id ?? "") === selectedFieldSessionId,
                          );
                          const fallbackUrl =
                            sessionPhotos.length === 0 && selectedFieldSession?.latest_photo_url
                              ? String(selectedFieldSession.latest_photo_url)
                              : null;
                          return (
                            <div
                              style={{
                                marginTop: 12,
                                background: "#ffffff",
                                border: "1px solid #dbe4ee",
                                borderRadius: 12,
                                overflow: "hidden",
                              }}
                            >
                              <div
                                style={{
                                  display: "flex",
                                  justifyContent: "space-between",
                                  alignItems: "center",
                                  gap: 10,
                                  flexWrap: "wrap",
                                  padding: "12px 14px",
                                  borderBottom: fieldReviewPhotosOpen
                                    ? "1px solid #eef2f7"
                                    : "none",
                                }}
                              >
                                <button
                                  type="button"
                                  onClick={() =>
                                    setFieldReviewPhotosOpen((open) => !open)
                                  }
                                  style={{
                                    flex: "1 1 160px",
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 8,
                                    border: "none",
                                    background: "transparent",
                                    cursor: "pointer",
                                    padding: 0,
                                    textAlign: "left",
                                    fontSize: 13,
                                    fontWeight: 700,
                                    color: "#0f172a",
                                  }}
                                  aria-expanded={fieldReviewPhotosOpen}
                                >
                                  <span style={{ fontSize: 11, color: "#64748b", width: 14 }}>
                                    {fieldReviewPhotosOpen ? "▼" : "▶"}
                                  </span>
                                  <span>
                                    Photos for this submission
                                    <span
                                      style={{
                                        marginLeft: 8,
                                        fontSize: 12,
                                        fontWeight: 500,
                                        color: "#64748b",
                                      }}
                                    >
                                      ({sessionPhotos.length})
                                    </span>
                                  </span>
                                </button>
                                <div
                                  style={{
                                    display: "flex",
                                    flexWrap: "wrap",
                                    gap: 8,
                                    alignItems: "center",
                                  }}
                                >
                                  {sessionPhotos.length > 0 ? (
                                    <button
                                      type="button"
                                      onClick={() =>
                                        setSelectedFieldGallery({
                                          kind: "list",
                                          photos: sortPhotosByUploadedDesc(sessionPhotos),
                                        })
                                      }
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
                                      {`View ${sessionPhotos.length} photo${sessionPhotos.length === 1 ? "" : "s"}`}
                                    </button>
                                  ) : fallbackUrl ? (
                                    <button
                                      type="button"
                                      onClick={() =>
                                        setSelectedFieldGallery({
                                          kind: "fallback",
                                          url: fallbackUrl,
                                        })
                                      }
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
                                      View photo
                                    </button>
                                  ) : null}
                                </div>
                              </div>
                              {fieldReviewPhotosOpen ? (
                                sessionPhotos.length > 0 ? (
                                  <div
                                    style={{
                                      padding: "0 14px 12px",
                                      display: "grid",
                                      gridTemplateColumns:
                                        "repeat(auto-fill, minmax(80px, 1fr))",
                                      gap: 6,
                                    }}
                                  >
                                    {sortPhotosByUploadedDesc(sessionPhotos)
                                      .slice(0, 8)
                                      .map((photo) => (
                                        <FieldSessionPhotoThumb
                                          key={photo.id}
                                          photo={photo}
                                          onClick={() =>
                                            setSelectedFieldGallery({
                                              kind: "list",
                                              photos: sortPhotosByUploadedDesc(sessionPhotos),
                                            })
                                          }
                                        />
                                      ))}
                                  </div>
                                ) : (
                                  <div
                                    style={{
                                      padding: "0 14px 12px",
                                      fontSize: 12,
                                      color: "#94a3b8",
                                    }}
                                  >
                                    {fallbackUrl
                                      ? "Photos available — click View photo to open."
                                      : "No photos in this submission."}
                                  </div>
                                )
                              ) : null}
                            </div>
                          );
                        })()}
                        <div
                          style={{
                            marginTop: 12,
                            background: "#ffffff",
                            border: "1px solid #dbe4ee",
                            borderRadius: 12,
                            overflow: "hidden",
                          }}
                        >
                          <div
                            style={{
                              display: "flex",
                              justifyContent: "space-between",
                              alignItems: "center",
                              gap: 10,
                              flexWrap: "wrap",
                              padding: "12px 14px",
                              borderBottom: fieldReviewBoreOpen
                                ? "1px solid #eef2f7"
                                : "none",
                            }}
                          >
                            <button
                              type="button"
                              onClick={() => setFieldReviewBoreOpen((open) => !open)}
                              style={{
                                flex: "1 1 160px",
                                display: "flex",
                                alignItems: "center",
                                gap: 8,
                                border: "none",
                                background: "transparent",
                                cursor: "pointer",
                                padding: 0,
                                textAlign: "left",
                                fontSize: 13,
                                fontWeight: 700,
                                color: "#0f172a",
                              }}
                              aria-expanded={fieldReviewBoreOpen}
                            >
                              <span style={{ fontSize: 11, color: "#64748b", width: 14 }}>
                                {fieldReviewBoreOpen ? "▼" : "▶"}
                              </span>
                              <span>
                                Field Data
                                {boreLogRows !== null ? (
                                  <span
                                    style={{
                                      marginLeft: 8,
                                      fontSize: 12,
                                      fontWeight: 500,
                                      color: "#64748b",
                                    }}
                                  >
                                    ({boreLogRows.length})
                                  </span>
                                ) : null}
                              </span>
                            </button>
                            <div
                              style={{
                                display: "flex",
                                flexWrap: "wrap",
                                gap: 8,
                                alignItems: "center",
                              }}
                            >
                              <button
                                type="button"
                                onClick={handleLoadBoreLog}
                                disabled={boreLogLoading}
                                style={{
                                  padding: "6px 12px",
                                  fontSize: 12,
                                  fontWeight: 700,
                                  borderRadius: 10,
                                  border: "1px solid #cfd8e3",
                                  background: "#ffffff",
                                  color: "#0f172a",
                                  cursor: boreLogLoading ? "not-allowed" : "pointer",
                                  opacity: boreLogLoading ? 0.6 : 1,
                                }}
                              >
                                {boreLogLoading
                                  ? "Loading…"
                                  : boreLogRows
                                    ? "Refresh Field Data"
                                    : "View Field Data"}
                              </button>
                              <button
                                type="button"
                                onClick={handleExportBoreLogCsv}
                                disabled={
                                  !boreLogRows ||
                                  boreLogRows.length === 0 ||
                                  !selectedFieldSessionId?.trim()
                                }
                                title={
                                  boreLogRows && boreLogRows.length > 0
                                    ? "Download loaded field data as CSV"
                                    : "Load field data first to enable export"
                                }
                                style={{
                                  padding: "6px 12px",
                                  fontSize: 12,
                                  fontWeight: 700,
                                  borderRadius: 10,
                                  border: "1px solid #cfd8e3",
                                  background: "#ffffff",
                                  color: "#0f172a",
                                  cursor:
                                    boreLogRows &&
                                    boreLogRows.length > 0 &&
                                    selectedFieldSessionId?.trim()
                                      ? "pointer"
                                      : "not-allowed",
                                  opacity:
                                    boreLogRows &&
                                    boreLogRows.length > 0 &&
                                    selectedFieldSessionId?.trim()
                                      ? 1
                                      : 0.5,
                                }}
                              >
                                Export CSV
                              </button>
                            </div>
                          </div>
                          {fieldReviewBoreOpen ? (
                            <>
                              {boreLogError ? (
                                <div
                                  style={{
                                    margin: "0 14px 10px",
                                    border: "1px solid #fecaca",
                                    background: "#fef2f2",
                                    color: "#991b1b",
                                    borderRadius: 8,
                                    padding: "8px 10px",
                                    fontSize: 12,
                                  }}
                                >
                                  {boreLogError}
                                </div>
                              ) : null}
                              {boreLogRows && boreLogRows.length === 0 ? (
                                <div
                                  style={{
                                    margin: "0 14px 10px",
                                    fontSize: 12,
                                    color: "#94a3b8",
                                  }}
                                >
                                  No field data loaded
                                </div>
                              ) : null}
                              {boreLogRows && boreLogRows.length > 0 ? (
                                <div
                                  style={{
                                    margin: "0 14px 12px",
                                    overflowX: "auto",
                                  }}
                                >
                                  <table
                                    style={{
                                      width: "100%",
                                      borderCollapse: "collapse",
                                      fontSize: 12,
                                    }}
                                  >
                                    <thead>
                                      <tr>
                                        <th style={boreLogTh}>station</th>
                                        <th style={{ ...boreLogTh, textAlign: "right" }}>
                                          station_ft
                                        </th>
                                        <th style={{ ...boreLogTh, textAlign: "right" }}>
                                          depth_ft
                                        </th>
                                        <th style={{ ...boreLogTh, textAlign: "right" }}>
                                          boc_ft
                                        </th>
                                        <th style={boreLogTh}>notes</th>
                                        <th style={{ ...boreLogTh, textAlign: "right" }}>
                                          photo_count
                                        </th>
                                        <th style={boreLogTh}>timestamp</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {boreLogRows.map((row, idx) => (
                                        <tr
                                          key={`${row.station}-${idx}`}
                                          style={{
                                            borderTop: "1px solid #eef2f7",
                                          }}
                                        >
                                          <td
                                            style={{
                                              ...boreLogTd,
                                              fontFamily:
                                                "ui-monospace, SFMono-Regular, Menlo, monospace",
                                            }}
                                          >
                                            {row.station}
                                          </td>
                                          <td
                                            style={{
                                              ...boreLogTd,
                                              textAlign: "right",
                                              fontVariantNumeric: "tabular-nums",
                                            }}
                                          >
                                            {row.station_ft}
                                          </td>
                                          <td
                                            style={{
                                              ...boreLogTd,
                                              textAlign: "right",
                                              fontVariantNumeric: "tabular-nums",
                                            }}
                                          >
                                            {row.depth_ft == null ? "—" : row.depth_ft}
                                          </td>
                                          <td
                                            style={{
                                              ...boreLogTd,
                                              textAlign: "right",
                                              fontVariantNumeric: "tabular-nums",
                                            }}
                                          >
                                            {row.boc_ft == null ? "—" : row.boc_ft}
                                          </td>
                                          <td style={boreLogTd}>
                                            {row.notes || (
                                              <span style={{ color: "#cbd5e1" }}>—</span>
                                            )}
                                          </td>
                                          <td
                                            style={{
                                              ...boreLogTd,
                                              textAlign: "right",
                                              fontVariantNumeric: "tabular-nums",
                                            }}
                                          >
                                            {row.photo_count}
                                          </td>
                                          <td
                                            style={{
                                              ...boreLogTd,
                                              color: "#64748b",
                                              whiteSpace: "nowrap",
                                            }}
                                          >
                                            {row.timestamp || "—"}
                                          </td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              ) : null}
                            </>
                          ) : null}
                        </div>
                      </>
                    ) : null}
                  </div>
                ) : null}
                <SessionPhotoGalleryModal
                  gallery={selectedFieldGallery}
                  onClose={() => setSelectedFieldGallery(null)}
                />
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
                  display: activeWorkspaceTab === "workspace" ? "grid" : "none",
                  gap: 14,
                  order: 15,
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
                      background: gpsPhotoBusy || closeoutLocked ? "#e5e7eb" : "#0f172a",
                      color: "#ffffff",
                      fontWeight: 800,
                      cursor: gpsPhotoBusy || closeoutLocked ? "not-allowed" : "pointer",
                      opacity: gpsPhotoBusy || closeoutLocked ? 0.7 : 1,
                    }}
                  >
                    <input
                      type="file"
                      accept="image/*,.heic,.heif"
                      multiple
                      style={{ display: "none" }}
                      disabled={gpsPhotoBusy || closeoutLocked}
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
                      disabled={gpsPhotoBusy || closeoutLocked}
                      style={{
                        padding: "10px 14px",
                        borderRadius: 12,
                        border: "1px solid #dbe4ee",
                        background: "#ffffff",
                        color: "#475569",
                        fontWeight: 700,
                        fontSize: 13,
                        cursor: gpsPhotoBusy || closeoutLocked ? "not-allowed" : "pointer",
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

          <div style={{ display: activeWorkspaceTab === "closeout" ? "grid" : "none", gridTemplateColumns: "1fr", gap: 18, alignItems: "start" }}>
            
<Section title="4. Reports" subtitle="Real report output built from current job data, redline sections, pricing inputs, and exception totals." style={{ display: activeWorkspaceTab === "closeout" ? "block" : "none" }}>
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
                  title={
                    projectCompletionSummary.plannedSource === "manual"
                      ? "Project Completion Summary"
                      : "Field footage & scope"
                  }
                  description={
                    projectCompletionSummary.plannedSource === "manual"
                      ? "Overall drilled progress using the engineering/material takeoff total."
                      : "Footage from as-built uploads and design route scope on the map."
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

            <div style={{ display: activeWorkspaceTab === "closeout" ? "grid" : "none", gap: 18 }}>
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
                          disabled={workspaceReadOnly}
                          style={{ borderRadius: 12, border: "1px solid #cfd8e3", padding: "10px 12px", background: workspaceReadOnly ? "#f1f5f9" : "#ffffff", fontSize: 14 }}
                        />
                      </label>
                      <label style={{ display: "grid", gap: 6, fontSize: 13, color: "#475569" }}>
                        <span>Cost per foot ($)</span>
                        <input value={costPerFoot} onChange={(e) => setCostPerFoot(e.target.value)} disabled={workspaceReadOnly} style={{ borderRadius: 12, border: "1px solid #cfd8e3", padding: "10px 12px", background: workspaceReadOnly ? "#f1f5f9" : "#ffffff", fontSize: 14 }} />
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
                            <input value={item.label} onChange={(e) => handleExceptionChange(item.id, "label", e.target.value)} disabled={workspaceReadOnly} style={{ borderRadius: 12, border: "1px solid #cfd8e3", padding: "10px 12px", background: workspaceReadOnly ? "#f1f5f9" : "#ffffff", fontSize: 14 }} />
                            <input value={item.amount} onChange={(e) => handleExceptionChange(item.id, "amount", e.target.value)} placeholder="0.00" disabled={workspaceReadOnly} style={{ borderRadius: 12, border: "1px solid #cfd8e3", padding: "10px 12px", background: workspaceReadOnly ? "#f1f5f9" : "#ffffff", fontSize: 14 }} />
                            <button type="button" onClick={() => handleRemoveException(item.id)} disabled={workspaceReadOnly} style={buttonStyle("#ffffff", "#0f172a", "#000000", workspaceReadOnly)}>Remove</button>
                          </div>
                          <input
                            value={item.note || ""}
                            onChange={(e) => handleExceptionChange(item.id, "note", e.target.value)}
                            placeholder="Note / context (optional)"
                            disabled={workspaceReadOnly}
                            style={{ borderRadius: 8, border: "1px solid #e2e8f0", padding: "6px 10px", background: workspaceReadOnly ? "#f1f5f9" : "#f8fafc", fontSize: 12, color: "#475569" }}
                          />
                        </div>
                      ))}
                      <div style={{ display: "grid", gap: 6 }}>
                        <div style={{ display: "grid", gridTemplateColumns: "1.4fr 0.8fr auto", gap: 10, alignItems: "center" }}>
                          <input value={extraExceptionLabel} onChange={(e) => setExtraExceptionLabel(e.target.value)} placeholder="Add exception label" disabled={workspaceReadOnly} style={{ borderRadius: 12, border: "1px solid #cfd8e3", padding: "10px 12px", background: workspaceReadOnly ? "#f1f5f9" : "#ffffff", fontSize: 14 }} />
                          <input value={extraExceptionAmount} onChange={(e) => setExtraExceptionAmount(e.target.value)} placeholder="0.00" disabled={workspaceReadOnly} style={{ borderRadius: 12, border: "1px solid #cfd8e3", padding: "10px 12px", background: workspaceReadOnly ? "#f1f5f9" : "#ffffff", fontSize: 14 }} />
                          <button type="button" onClick={handleAddException} disabled={workspaceReadOnly} style={buttonStyle("#0f172a", "#ffffff", "#000000", workspaceReadOnly)}>Add</button>
                        </div>
                        <input
                          value={extraExceptionNote}
                          onChange={(e) => setExtraExceptionNote(e.target.value)}
                          placeholder="Note / context (optional)"
                          disabled={workspaceReadOnly}
                          style={{ borderRadius: 8, border: "1px solid #e2e8f0", padding: "6px 10px", background: workspaceReadOnly ? "#f1f5f9" : "#f8fafc", fontSize: 12, color: "#475569" }}
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

                  <ShellCard title="Approval" description="Submit billing for review, then record approval. Values above lock after approval.">
                    <div style={{ display: "grid", gap: 12 }}>
                      {billingApprovalStatus === "not_submitted" ? (
                        <>
                          <button
                            type="button"
                            onClick={() => setBillingApprovalStatus("pending")}
                            disabled={busy || !billingChecklistComplete || closeoutLocked}
                            style={{
                              ...buttonStyle("#0f172a", "#ffffff", "#000000", busy || !billingChecklistComplete || closeoutLocked),
                              justifySelf: "start",
                            }}
                          >
                            Submit for Approval
                          </button>
                          {!billingChecklistComplete && !closeoutLocked && (
                            <div style={{ fontSize: 12, color: "#92400e", background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 8, padding: "8px 12px" }}>
                              <strong>Required before submitting:</strong>
                              <ul style={{ margin: "4px 0 0", paddingLeft: 18, lineHeight: 1.7 }}>
                                {!hasDesign && <li>Design file (KMZ/KML) not loaded</li>}
                                {!hasBoreFiles && <li>Field data files not loaded</li>}
                                {stationPhotos.length === 0 && gpsPhotos.length === 0 && (
                                  <li>Photo evidence required — upload geotagged photos or select a station to upload station photos</li>
                                )}
                              </ul>
                            </div>
                          )}
                        </>
                      ) : null}
                      {billingApprovalStatus === "pending" ? (
                        <>
                          <div style={{ fontSize: 14, fontWeight: 800, color: "#92400e" }}>Status: Pending Approval</div>
                          <button
                            type="button"
                            onClick={() => setBillingApprovalStatus("approved")}
                            disabled={busy || closeoutLocked}
                            style={{ ...buttonStyle("#0f172a", "#ffffff", "#000000", busy || closeoutLocked), justifySelf: "start" }}
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
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
                    {closeoutLocked ? (
                      <div
                        style={{
                          flex: "1 1 280px",
                          padding: "10px 14px",
                          borderRadius: 12,
                          background: "#fef3c7",
                          border: "1px solid #fcd34d",
                          fontSize: 13,
                          color: "#92400e",
                          fontWeight: 600,
                        }}
                      >
                        🔒 Closeout Locked — Approved for Billing. Locked by {String(state?.closeout_lock?.locked_by ?? state?.closeout_locked_by ?? "—")} at{" "}
                        {state?.closeout_lock?.locked_at
                          ? new Date(String(state.closeout_lock.locked_at)).toLocaleString()
                          : state?.closeout_locked_at
                            ? new Date(String(state.closeout_locked_at)).toLocaleString()
                            : "—"}
                      </div>
                    ) : null}
                    {!closeoutLocked && billingApproved ? (
                      <button
                        type="button"
                        onClick={() => void handleLockCloseout()}
                        disabled={busy}
                        style={buttonStyle("#0f172a", "#ffffff", "#000000", busy)}
                      >
                        Lock Closeout
                      </button>
                    ) : null}
                    {closeoutLocked ? (
                      <button
                        type="button"
                        onClick={() => void handleUnlockCloseout()}
                        disabled={busy}
                        style={buttonStyle("#ffffff", "#0f172a", "#cbd5e1", busy)}
                      >
                        Unlock Closeout
                      </button>
                    ) : null}
                  </div>
                  <ShellCard
                    title="Closeout Packet V1"
                    description="Generate a structured closeout packet from existing job data — field data, QA flags, overrides, billing, and plan evidence. Preview in-browser, then Print / Save as PDF."
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
                      operatorNotesNotRequired={operatorNotesNotRequired}
                      closeoutLocked={closeoutLocked}
                      billingApproved={billingApproved}
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
                      <button onClick={handleExportEngineeringKml} style={{ ...buttonStyle("#0f2a1a", "#86efac", "#22c55e", false), width: "100%" }}>
                        Export Engineering KMZ + Redlines
                      </button>
                      {engExportError && (
                        <div style={{ fontSize: 12, color: "#ef4444", padding: "6px 10px", borderRadius: 8, background: "#fef2f2", border: "1px solid #fecaca" }}>
                          {engExportError}
                        </div>
                      )}
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
                      disabled={workspaceReadOnly}
                      style={{ width: "100%", minHeight: 140, borderRadius: 14, border: "1px solid #cfd8e3", padding: 12, outline: "none", resize: "vertical", fontSize: 14, background: workspaceReadOnly ? "#f1f5f9" : "#ffffff" }}
                    />
                    <label
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        marginTop: 10,
                        fontSize: 13,
                        color: "#475569",
                        cursor: "pointer",
                        userSelect: "none",
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={operatorNotesNotRequired}
                        onChange={(e) => setOperatorNotesNotRequired(e.target.checked)}
                        disabled={workspaceReadOnly}
                        style={{ width: 16, height: 16, flexShrink: 0 }}
                      />
                      No operator notes required
                    </label>
                    <button
                      onClick={submitBugNote}
                      disabled={busy || !notes.trim() || workspaceReadOnly}
                      style={{ ...buttonStyle("#0f172a", "#ffffff", "#0f172a", busy || !notes.trim() || workspaceReadOnly), marginTop: 12, width: "100%" }}
                    >
                      Submit Operator Note
                    </button>
                  </ShellCard>
                </div>
              </Section>
            </div>
          </div>
        </div>
        <p
          className="no-print"
          style={{
            margin: "16px 0 0",
            paddingTop: 14,
            borderTop: "1px solid #e8eef5",
            fontSize: 11,
            color: "#94a3b8",
            textAlign: "center",
            fontWeight: 500,
            letterSpacing: 0.01,
          }}
        >
          Powered by Midway Data Tech Solutions
        </p>
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

        {/* Field data reference line */}
        {(state?.bore_log_summary?.length ?? 0) > 0 && (
          <p style={{ margin: "0 0 12px 0", fontSize: 13, color: "#475569" }}>
            Source field data reviewed: <strong>{state!.bore_log_summary!.length} {state!.bore_log_summary!.length === 1 ? "file" : "files"}</strong>
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

// ─── Authenticated photo helpers ─────────────────────────────────────────────
// Station photo file routes require an Authorization header that browser-native
// image/navigation requests cannot supply. These components fetch via apiFetch
// (which attaches the token) and render from a revocable blob: URL.

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
      onClick={handleOpen}
      style={{
        color: "inherit",
        borderRadius: 10,
        overflow: "hidden",
        border: "1px solid #e2e8f0",
        display: "block",
        padding: 0,
        background: "none",
        cursor: "pointer",
        width: "100%",
        textAlign: "left",
        font: "inherit",
      }}
    >
      <div
        style={{
          height: 72,
          backgroundImage: blobSrc ? `url(${blobSrc})` : undefined,
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
    </button>
  );
}

function FieldSessionPhotoThumb({
  photo,
  onClick,
}: {
  photo: Pick<Photo, "id" | "thumbnail_url" | "station_label">;
  onClick: () => void;
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

  return (
    <button
      type="button"
      onClick={onClick}
      title={photo.station_label || ""}
      style={{
        height: 64,
        padding: 0,
        borderRadius: 8,
        border: "1px solid #e2e8f0",
        backgroundColor: "#e5e7eb",
        backgroundImage: blobSrc ? `url(${blobSrc})` : undefined,
        backgroundSize: "cover",
        backgroundPosition: "center",
        cursor: "pointer",
      }}
      aria-label={photo.station_label ? `Photo at ${photo.station_label}` : "Submission photo"}
    />
  );
}

export default function RedlineMap({
  projectId,
  workspaceTitle,
  projectType = null,
  onFieldSelectionChange,
  onWorkspaceStateChanged,
  onGpsPhotosChange,
  operationalMap,
}: RedlineMapProps) {
  return (
    <OfficeRedlineMapInner
      projectId={projectId}
      workspaceTitle={workspaceTitle}
      projectType={projectType}
      onFieldSelectionChange={onFieldSelectionChange}
      onWorkspaceStateChanged={onWorkspaceStateChanged}
      onGpsPhotosChange={onGpsPhotosChange}
      operationalMap={operationalMap}
    />
  );
}
