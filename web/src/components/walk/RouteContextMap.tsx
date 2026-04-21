"use client";

import React, { useMemo } from "react";
import type { CurrentGps } from "@/components/MobileWalkUI";

type Bounds = {
  minLat: number;
  maxLat: number;
  minLon: number;
  maxLon: number;
};

type ProjectionMetrics = {
  worldWidth: number;
  worldHeight: number;
  contentWidth: number;
  contentHeight: number;
  offsetX: number;
  offsetY: number;
  lonScale: number;
};

const PROJECTION_BASE_WIDTH = 1000;

function getBoundsFromCoords(coords: number[][]): Bounds | null {
  if (!coords.length) return null;
  return {
    minLat: Math.min(...coords.map((p) => p[0])),
    maxLat: Math.max(...coords.map((p) => p[0])),
    minLon: Math.min(...coords.map((p) => p[1])),
    maxLon: Math.max(...coords.map((p) => p[1])),
  };
}

function expandBounds(bounds: Bounds, factor = 0.08): Bounds {
  const latPad = Math.max((bounds.maxLat - bounds.minLat) * factor, 0.00001);
  const lonPad = Math.max((bounds.maxLon - bounds.minLon) * factor, 0.00001);
  return {
    minLat: bounds.minLat - latPad,
    maxLat: bounds.maxLat + latPad,
    minLon: bounds.minLon - lonPad,
    maxLon: bounds.maxLon + lonPad,
  };
}

/**
 * Produce a world box whose aspect matches the cosine-corrected data aspect.
 * The real on-screen aspect of the <svg> is handled by preserveAspectRatio,
 * so we do NOT assume any particular device/viewport dimensions here.
 */
function getProjectionMetrics(bounds: Bounds): ProjectionMetrics {
  const latSpan = Math.max(bounds.maxLat - bounds.minLat, 0.000001);
  const midLatRad = ((bounds.minLat + bounds.maxLat) / 2) * (Math.PI / 180);
  const lonScale = Math.max(Math.cos(midLatRad), 0.000001);
  const lonSpanAdjusted = Math.max(
    (bounds.maxLon - bounds.minLon) * lonScale,
    0.000001
  );

  const dataAspect = lonSpanAdjusted / latSpan;

  const worldWidth = PROJECTION_BASE_WIDTH;
  const worldHeight = worldWidth / dataAspect;

  return {
    worldWidth,
    worldHeight,
    contentWidth: worldWidth,
    contentHeight: worldHeight,
    offsetX: 0,
    offsetY: 0,
    lonScale,
  };
}

function projectWorldPoint(
  lat: number,
  lon: number,
  bounds: Bounds,
  metrics: ProjectionMetrics
) {
  const latSpan = Math.max(bounds.maxLat - bounds.minLat, 0.000001);
  const lonSpanAdjusted = Math.max(
    (bounds.maxLon - bounds.minLon) * metrics.lonScale,
    0.000001
  );
  return {
    x:
      metrics.offsetX +
      (((lon - bounds.minLon) * metrics.lonScale) / lonSpanAdjusted) *
        metrics.contentWidth,
    y:
      metrics.offsetY +
      (1 - (lat - bounds.minLat) / latSpan) * metrics.contentHeight,
  };
}

function buildWorldPath(
  coords: number[][],
  bounds: Bounds,
  metrics: ProjectionMetrics
): string {
  if (coords.length < 2) return "";
  return coords
    .map((pt, idx) => {
      const p = projectWorldPoint(pt[0], pt[1], bounds, metrics);
      return `${idx === 0 ? "M" : "L"} ${p.x.toFixed(2)} ${p.y.toFixed(2)}`;
    })
    .join(" ");
}

type Props = {
  routeCoords: number[][];
  currentGps: CurrentGps | null;
  /** Breadcrumb trail of GPS fixes captured this session, oldest-first. */
  walkTrail?: number[][];
  /** Shown when routeCoords is empty. */
  noRouteMessage?: string;
};

export default function RouteContextMap({
  routeCoords,
  currentGps,
  walkTrail = [],
  noRouteMessage = "No route assigned",
}: Props) {
  // Framing bounds are STABLE — derived from the route only, not from GPS.
  // This prevents the viewBox from rescaling every time a GPS fix arrives,
  // which was making the map appear to "twitch" or "zoom" as the user walked.
  const routeBounds = useMemo<Bounds | null>(() => {
    const raw = getBoundsFromCoords(routeCoords);
    return raw ? expandBounds(raw) : null;
  }, [routeCoords]);

  const metrics = useMemo<ProjectionMetrics | null>(() => {
    if (!routeBounds) return null;
    return getProjectionMetrics(routeBounds);
  }, [routeBounds]);

  const routePath = useMemo(() => {
    if (!routeBounds || !metrics) return "";
    return buildWorldPath(routeCoords, routeBounds, metrics);
  }, [routeCoords, routeBounds, metrics]);

  const trailPath = useMemo(() => {
    if (!routeBounds || !metrics || walkTrail.length < 2) return "";
    return buildWorldPath(walkTrail, routeBounds, metrics);
  }, [walkTrail, routeBounds, metrics]);

  const gpsProjected = useMemo(() => {
    if (!currentGps || !routeBounds || !metrics) return null;
    return projectWorldPoint(
      currentGps.lat,
      currentGps.lon,
      routeBounds,
      metrics
    );
  }, [currentGps, routeBounds, metrics]);

  const viewBox = metrics
    ? `0 0 ${metrics.worldWidth.toFixed(2)} ${metrics.worldHeight.toFixed(2)}`
    : "0 0 1000 1600";

  const hasRoute = routeCoords.length >= 2;

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        background:
          "radial-gradient(ellipse at 50% 40%, rgba(30, 64, 125, 0.55) 0%, rgba(15, 23, 42, 1) 75%)",
        overflow: "hidden",
      }}
    >
      <svg
        width="100%"
        height="100%"
        viewBox={viewBox}
        preserveAspectRatio="xMidYMid meet"
        style={{ display: "block", pointerEvents: "none" }}
        aria-hidden
      >
        {hasRoute && routePath ? (
          <>
            <path
              d={routePath}
              fill="none"
              stroke="rgba(148, 163, 184, 0.35)"
              strokeWidth={6}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              d={routePath}
              fill="none"
              stroke="#f8fafc"
              strokeWidth={2.25}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </>
        ) : null}

        {/* Blue tracer — path of collected GPS points this session. */}
        {trailPath ? (
          <>
            <path
              d={trailPath}
              fill="none"
              stroke="rgba(59, 130, 246, 0.35)"
              strokeWidth={6}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              d={trailPath}
              fill="none"
              stroke="#3b82f6"
              strokeWidth={3}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </>
        ) : null}

        {gpsProjected ? (
          <>
            <circle
              cx={gpsProjected.x}
              cy={gpsProjected.y}
              r={14}
              fill="rgba(16, 185, 129, 0.18)"
            />
            <circle
              cx={gpsProjected.x}
              cy={gpsProjected.y}
              r={6}
              fill="#10b981"
              stroke="#f0fdf4"
              strokeWidth={2}
            />
          </>
        ) : null}
      </svg>

      {!hasRoute ? (
        <div
          role="status"
          aria-live="polite"
          style={{
            position: "absolute",
            top: "50%",
            left: "50%",
            transform: "translate(-50%, -50%)",
            padding: "10px 14px",
            borderRadius: 12,
            background: "rgba(30, 41, 59, 0.85)",
            color: "#fca5a5",
            border: "1px solid rgba(248, 113, 113, 0.35)",
            fontSize: 13,
            fontWeight: 700,
            letterSpacing: 0.2,
            textAlign: "center",
            pointerEvents: "none",
          }}
        >
          {noRouteMessage}
        </div>
      ) : null}
    </div>
  );
}
