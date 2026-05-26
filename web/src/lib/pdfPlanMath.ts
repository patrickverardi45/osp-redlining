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
