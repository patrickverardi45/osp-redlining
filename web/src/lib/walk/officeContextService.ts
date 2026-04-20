// Office context service for the walk app.
//
// Purpose: /walk needs to know what route is assigned, but should NOT consume
// the full office `BackendState`. This adapter reads `/api/current-state` and
// returns only the three fields the field app needs: route name, route length,
// and route coordinates. Everything else is discarded at this boundary so the
// walk UI cannot accidentally grow a dependency on office-specific fields.
//
// Read-only. No mutations, no uploads, no POSTs. If you find yourself adding a
// POST here, put it in `service.ts` (the walk service) instead.

import type { BackendState } from "@/lib/types/backend";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/+$/, "") ||
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, "") ||
  "http://127.0.0.1:8000";

export type RouteContext = {
  /** Active route name, or null if no route is loaded in the office workspace. */
  routeName: string | null;
  /** Total route length in feet, if known. */
  routeLengthFt: number | null;
  /** Route polyline as [lat, lon][] pairs. Empty array if no route is loaded. */
  routeCoords: number[][];
  /** ISO timestamp when this snapshot was captured on the client. */
  capturedAt: string;
};

export const EMPTY_ROUTE_CONTEXT: RouteContext = {
  routeName: null,
  routeLengthFt: null,
  routeCoords: [],
  capturedAt: new Date(0).toISOString(),
};

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

export interface OfficeContextService {
  /** Fetch the currently assigned route context. Safe to call on mount. */
  fetchRouteContext(): Promise<RouteContext>;
}

class HttpOfficeContextService implements OfficeContextService {
  async fetchRouteContext(): Promise<RouteContext> {
    const response = await fetch(`${API_BASE}/api/current-state`);
    if (!response.ok) {
      throw new Error(`current-state request failed: ${response.status}`);
    }
    const data: BackendState = await response.json();

    const selectedName =
      (typeof data.selected_route_name === "string" && data.selected_route_name.trim()) ||
      (typeof data.route_name === "string" && data.route_name.trim()) ||
      null;

    const lengthFt =
      typeof data.total_length_ft === "number" && Number.isFinite(data.total_length_ft)
        ? data.total_length_ft
        : null;

    const coords = cleanCoords(data.route_coords);

    return {
      routeName: selectedName,
      routeLengthFt: lengthFt,
      routeCoords: coords,
      capturedAt: new Date().toISOString(),
    };
  }
}

export const defaultOfficeContextService: OfficeContextService = new HttpOfficeContextService();
