/**
 * PDF Plan Mode — small math helpers used by the PDF plan viewer.
 *
 * Pure functions only.  No DOM, no network, no React.  Coordinate
 * units are PDF-pixel coordinates at the page's native DPI.
 */

import type { PdfPoint } from "@/lib/types/pdfPlan";

/** Parse a station-label string like "11+60", "STA 11+60", "11+60.5", or
 *  raw-feet "1160" into a feet value.  Returns null on unparseable input.
 *
 *  Mirrors backend ``parse_station_label_to_ft`` in
 *  backend/app/core/pdf_plan_trace_store.py so a label that the frontend
 *  accepts will also pass server-side validation. */
export function parseStationLabel(input: string): number | null {
  if (typeof input !== "string") return null;
  const stripped = input.trim();
  if (!stripped) return null;
  const m = /^(?:STA\s+)?(\d{1,5})\s*\+\s*(\d{1,3}(?:\.\d+)?)\s*$/i.exec(stripped);
  if (m) {
    const hundreds = parseInt(m[1], 10);
    const fraction = parseFloat(m[2]);
    if (!Number.isFinite(hundreds) || !Number.isFinite(fraction)) return null;
    return hundreds * 100 + fraction;
  }
  // Raw feet fallback
  const asFloat = parseFloat(stripped);
  if (Number.isFinite(asFloat)) return asFloat;
  return null;
}

/** Inverse of parseStationLabel for display.  1160 -> "11+60". */
export function formatStationFt(ft: number): string {
  if (!Number.isFinite(ft) || ft < 0) return "0+00";
  const hundreds = Math.floor(ft / 100);
  const remainder = ft - hundreds * 100;
  if (Math.abs(remainder - Math.round(remainder)) < 1e-9) {
    return `${hundreds}+${String(Math.round(remainder)).padStart(2, "0")}`;
  }
  return `${hundreds}+${remainder.toFixed(2).padStart(5, "0")}`;
}

/** Distance from a 2D point to a line segment, both in PDF pixels. */
export function distancePointToSegment(
  p: PdfPoint,
  a: PdfPoint,
  b: PdfPoint,
): number {
  const px = p[0], py = p[1];
  const ax = a[0], ay = a[1];
  const bx = b[0], by = b[1];
  const dx = bx - ax;
  const dy = by - ay;
  const lengthSq = dx * dx + dy * dy;
  if (lengthSq <= 1e-12) {
    const cx = px - ax;
    const cy = py - ay;
    return Math.sqrt(cx * cx + cy * cy);
  }
  let t = ((px - ax) * dx + (py - ay) * dy) / lengthSq;
  t = Math.max(0, Math.min(1, t));
  const cx = ax + t * dx - px;
  const cy = ay + t * dy - py;
  return Math.sqrt(cx * cx + cy * cy);
}

export type NearestPointResult = {
  point: PdfPoint;
  distance: number;
  segIndex: number;
  t: number;
};

/** Find the nearest point on a polyline to a given query point.  Returns
 *  the snapped point, the polyline segment index, the parametric t in
 *  [0, 1] along that segment, and the distance from the query to the
 *  snap.  Returns null when the polyline has fewer than 2 vertices. */
export function nearestPointOnPolyline(
  p: PdfPoint,
  polyline: PdfPoint[],
): NearestPointResult | null {
  if (!Array.isArray(polyline) || polyline.length < 2) return null;
  let best: NearestPointResult | null = null;
  for (let i = 0; i < polyline.length - 1; i++) {
    const a = polyline[i];
    const b = polyline[i + 1];
    const dx = b[0] - a[0];
    const dy = b[1] - a[1];
    const lengthSq = dx * dx + dy * dy;
    let t = 0;
    let snappedX = a[0];
    let snappedY = a[1];
    if (lengthSq > 1e-12) {
      t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / lengthSq;
      t = Math.max(0, Math.min(1, t));
      snappedX = a[0] + t * dx;
      snappedY = a[1] + t * dy;
    }
    const cx = snappedX - p[0];
    const cy = snappedY - p[1];
    const dist = Math.sqrt(cx * cx + cy * cy);
    if (best === null || dist < best.distance) {
      best = {
        point: [snappedX, snappedY],
        distance: dist,
        segIndex: i,
        t,
      };
    }
  }
  return best;
}

// ───────────────────────────────────────────────────────────────────────────
// Step 3A — polyline distance math for manual station segments
// ───────────────────────────────────────────────────────────────────────────

/** Cumulative pixel lengths along a polyline.  Returns an array of size
 *  ``polyline.length`` where index i is the total pixel distance from
 *  the start of the polyline to vertex i (so [0] === 0 and the last
 *  entry is the total polyline length). */
export function cumulativePolylineLengths(polyline: PdfPoint[]): number[] {
  if (!Array.isArray(polyline) || polyline.length === 0) return [];
  const out: number[] = new Array(polyline.length);
  out[0] = 0;
  for (let i = 1; i < polyline.length; i++) {
    const dx = polyline[i][0] - polyline[i - 1][0];
    const dy = polyline[i][1] - polyline[i - 1][1];
    out[i] = out[i - 1] + Math.sqrt(dx * dx + dy * dy);
  }
  return out;
}

/** Convert a snapped-on-polyline (segIndex, t) pair into a cumulative
 *  pixel distance from the polyline start. */
export function snapToCumDistance(
  cumLengths: number[],
  segIndex: number,
  t: number,
): number {
  if (cumLengths.length < 2) return 0;
  const clampedSeg = Math.max(0, Math.min(cumLengths.length - 2, segIndex));
  const segLen = cumLengths[clampedSeg + 1] - cumLengths[clampedSeg];
  const clampedT = Math.max(0, Math.min(1, t));
  return cumLengths[clampedSeg] + clampedT * segLen;
}

/** Anchors annotated with their cumulative pixel distance along the
 *  trace polyline.  Sorted by station_ft ascending. */
export type AnchorWithDistance = {
  station_ft: number;
  pixel_distance: number;
  label: string;
};

/** Annotate each anchor with its on-polyline pixel distance, then sort
 *  by station_ft ascending.  Used as the keypoints for the piecewise-
 *  linear stationFt -> pixel-distance interpolator below. */
export function anchorsWithCumulativeDistance(
  anchors: Array<{ station_ft: number; label: string; point: PdfPoint }>,
  polyline: PdfPoint[],
  cumLengths: number[],
): AnchorWithDistance[] {
  if (!Array.isArray(anchors) || anchors.length === 0) return [];
  if (polyline.length < 2 || cumLengths.length !== polyline.length) return [];
  const out: AnchorWithDistance[] = [];
  for (const a of anchors) {
    const snap = nearestPointOnPolyline(a.point, polyline);
    if (!snap) continue;
    out.push({
      station_ft: a.station_ft,
      pixel_distance: snapToCumDistance(cumLengths, snap.segIndex, snap.t),
      label: a.label,
    });
  }
  // Stable sort by station_ft ascending — Array.sort is stable in modern engines.
  out.sort((a, b) => a.station_ft - b.station_ft);
  return out;
}

/** Map a station_ft value to a cumulative pixel distance along the
 *  polyline using piecewise-linear interpolation between sorted anchors.
 *  Extrapolates outside the anchor range using the nearest pair's slope
 *  (and clamps to [0, totalLength] to keep the result on the polyline).
 *
 *  Returns null when fewer than 2 anchors are available or anchor
 *  station_ft values are degenerate (all equal). */
export function stationFtToPolylineDistance(
  stationFt: number,
  sortedAnchors: AnchorWithDistance[],
  totalLength: number,
): number | null {
  if (!Number.isFinite(stationFt)) return null;
  if (!Array.isArray(sortedAnchors) || sortedAnchors.length < 2) return null;
  // Below first anchor: extrapolate from first segment of the map.
  if (stationFt <= sortedAnchors[0].station_ft) {
    const a = sortedAnchors[0];
    const b = sortedAnchors[1];
    const spanFt = b.station_ft - a.station_ft;
    if (Math.abs(spanFt) < 1e-9) return a.pixel_distance;
    const slope = (b.pixel_distance - a.pixel_distance) / spanFt;
    const px = a.pixel_distance + (stationFt - a.station_ft) * slope;
    return Math.max(0, Math.min(totalLength, px));
  }
  const lastIdx = sortedAnchors.length - 1;
  // Above last anchor: extrapolate from last segment of the map.
  if (stationFt >= sortedAnchors[lastIdx].station_ft) {
    const a = sortedAnchors[lastIdx - 1];
    const b = sortedAnchors[lastIdx];
    const spanFt = b.station_ft - a.station_ft;
    if (Math.abs(spanFt) < 1e-9) return b.pixel_distance;
    const slope = (b.pixel_distance - a.pixel_distance) / spanFt;
    const px = b.pixel_distance + (stationFt - b.station_ft) * slope;
    return Math.max(0, Math.min(totalLength, px));
  }
  // Between two anchors: piecewise-linear interpolation.
  for (let i = 0; i < lastIdx; i++) {
    const a = sortedAnchors[i];
    const b = sortedAnchors[i + 1];
    if (stationFt >= a.station_ft && stationFt <= b.station_ft) {
      const spanFt = b.station_ft - a.station_ft;
      if (Math.abs(spanFt) < 1e-9) return a.pixel_distance;
      const frac = (stationFt - a.station_ft) / spanFt;
      const px = a.pixel_distance + frac * (b.pixel_distance - a.pixel_distance);
      return Math.max(0, Math.min(totalLength, px));
    }
  }
  return null;
}

/** Extract the subpath of a polyline lying between two cumulative pixel
 *  distances along it.  Returns at least 2 points when startDist !==
 *  endDist; returns [] when the polyline is empty or distances are
 *  invalid. */
export function extractPolylineSubpath(
  polyline: PdfPoint[],
  cumLengths: number[],
  startDist: number,
  endDist: number,
): PdfPoint[] {
  if (polyline.length < 2 || cumLengths.length !== polyline.length) return [];
  if (!Number.isFinite(startDist) || !Number.isFinite(endDist)) return [];
  let s = startDist;
  let e = endDist;
  if (s > e) {
    const tmp = s;
    s = e;
    e = tmp;
  }
  const totalLength = cumLengths[cumLengths.length - 1];
  s = Math.max(0, Math.min(totalLength, s));
  e = Math.max(0, Math.min(totalLength, e));

  const findSegmentForDistance = (dist: number): number => {
    // Find the segment index i where cumLengths[i] <= dist <= cumLengths[i+1].
    for (let i = 0; i < cumLengths.length - 1; i++) {
      if (dist >= cumLengths[i] && dist <= cumLengths[i + 1]) return i;
    }
    return cumLengths.length - 2;
  };

  const pointAt = (segIndex: number, dist: number): PdfPoint => {
    const segLen = cumLengths[segIndex + 1] - cumLengths[segIndex];
    let t = 0;
    if (segLen > 1e-9) {
      t = (dist - cumLengths[segIndex]) / segLen;
      t = Math.max(0, Math.min(1, t));
    }
    const a = polyline[segIndex];
    const b = polyline[segIndex + 1];
    return [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])];
  };

  const startSeg = findSegmentForDistance(s);
  const endSeg = findSegmentForDistance(e);
  const out: PdfPoint[] = [];
  out.push(pointAt(startSeg, s));
  // Add intermediate polyline vertices that fall strictly between s and e.
  for (let i = startSeg + 1; i <= endSeg; i++) {
    if (cumLengths[i] > s && cumLengths[i] < e) {
      out.push([polyline[i][0], polyline[i][1]]);
    }
  }
  out.push(pointAt(endSeg, e));
  return out;
}
