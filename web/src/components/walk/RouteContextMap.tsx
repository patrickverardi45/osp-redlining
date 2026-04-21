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
};

const PROJECTION_BASE_WIDTH = 1000;
const DEFAULT_ASPECT = 9 / 16;

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

  return { worldWidth, worldHeight, contentWidth, contentHeight, offsetX, offsetY };
}

function projectWorldPoint(lat: number, lon: number, bounds: Bounds, metrics: ProjectionMetrics) {
  const latSpan = Math.max(bounds.maxLat - bounds.minLat, 0.000001);
  const midLatRad = ((bounds.minLat + bounds.maxLat) / 2) * (Math.PI / 180);
  const lonScale = Math.max(Math.cos(midLatRad), 0.000001);
  const lonSpanAdjusted = Math.max((bounds.maxLon - bounds.minLon) * lonScale, 0.000001);

  return {
    x:
      metrics.offsetX +
      (((lon - bounds.minLon) * lonScale) / lonSpanAdjusted) * metrics.contentWidth,
    y: metrics.offsetY + (1 - (lat - bounds.minLat) / latSpan) * metrics.contentHeight,
  };
}

function buildWorldPath(coords: number[][], bounds: Bounds, metrics: ProjectionMetrics): string {
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
  noRouteMessage?: string;
};

export default function RouteContextMap({
  routeCoords,
  currentGps,
  noRouteMessage = "No route assigned",
}: Props) {
  const combinedBounds = useMemo<Bounds | null>(() => {
    const pointsForBounds: number[][] = [];
    for (const pt of routeCoords) pointsForBounds.push(pt);
    if (currentGps) pointsForBounds.push([currentGps.lat, currentGps.lon]);
    const raw = getBoundsFromCoords(pointsForBounds);
    return raw ? expandBounds(raw) : null;
  }, [routeCoords, currentGps]);

  const metrics = useMemo<ProjectionMetrics | null>(() => {
    if (!combinedBounds) return null;
    const fakeWidth = 360;
    const fakeHeight = fakeWidth / DEFAULT_ASPECT;
    return getProjectionMetrics(combinedBounds, fakeWidth, fakeHeight);
  }, [combinedBounds]);

  const routePath = useMemo(() => {
    if (!combinedBounds || !metrics) return "";
    return buildWorldPath(routeCoords, combinedBounds, metrics);
  }, [routeCoords, combinedBounds, metrics]);

  const gpsProjected = useMemo(() => {
    if (!currentGps || !combinedBounds || !metrics) return null;
    return projectWorldPoint(currentGps.lat, currentGps.lon, combinedBounds, metrics);
  }, [currentGps, combinedBounds, metrics]);

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

        {gpsProjected ? (
          <>
            <circle cx={gpsProjected.x} cy={gpsProjected.y} r={14} fill="rgba(16, 185, 129, 0.18)" />
            <circle cx={gpsProjected.x} cy={gpsProjected.y} r={6} fill="#10b981" stroke="#f0fdf4" strokeWidth={2} />
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
