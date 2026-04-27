// web/src/components/office/OfficeMapReviewPanel.tsx
//
// Phase 4B (real implementation) + Phase 4E selection emphasis.
//
// Read-only Leaflet map for the job detail page. Shows:
//   - Design routes from job.routes[*].geometry  → dashed gray polylines
//   - Walk session tracks from job.sessions[*].track_geometry
//                                                → solid colored polylines
//                                                  (one color per session)
//   - When `selectedSessionId` is provided, that session's track is drawn
//     thicker with a yellow halo and the map auto-fits to it on first load.
//
// Pure vanilla Leaflet via dynamic import inside useEffect. The parent on
// /jobs/[jobId] already wraps this component with `next/dynamic({ssr:false})`
// so we don't need to repeat that here. Leaflet CSS is imported globally in
// app/layout.tsx so we don't import it again.
//
// Hard rules respected:
//   - read-only, no redlines generated
//   - no approve / reject / mutate actions
//   - no backend calls — all data comes from the JobDetail prop
//   - GeoJSON is [lon, lat]; Leaflet wants [lat, lng] — swap on read
"use client";

import { useEffect, useRef } from "react";

import type { JobDetail, Route, Session } from "@/lib/api";

// ─── Visual constants ─────────────────────────────────────────────────────────

// Design routes draw underneath everything else. Dashed + neutral gray so
// they recede against the colored session tracks above.
const DESIGN_COLOR = "#475569"; // slate-600
const DESIGN_WEIGHT = 3;
const DESIGN_DASH = "6, 6";
const DESIGN_OPACITY = 0.85;

// Session track palette. Eight colors, deterministically assigned by index
// so a given job always renders the same color for the same session order.
// Red is intentionally absent — red reads as "redline" elsewhere in the
// product and we don't want office staff confusing a walked path for a
// redlined section.
const SESSION_COLORS: ReadonlyArray<string> = [
  "#0ea5e9", // sky-500
  "#10b981", // emerald-500
  "#f59e0b", // amber-500
  "#8b5cf6", // violet-500
  "#06b6d4", // cyan-500
  "#84cc16", // lime-500
  "#ec4899", // pink-500
  "#3b82f6", // blue-500
];

const SESSION_WEIGHT_DEFAULT = 4;
const SESSION_WEIGHT_SELECTED = 6;
const SESSION_OPACITY = 0.95;

// Selected-session halo (drawn underneath the session line). Soft yellow,
// matches the "focused" cue used elsewhere in the workspace.
const SELECTED_HALO_COLOR = "#facc15"; // yellow-400
const SELECTED_HALO_WEIGHT = 11;
const SELECTED_HALO_OPACITY = 0.5;

const FIT_PADDING: [number, number] = [24, 24];
const FIT_MAX_ZOOM = 18;

// ─── Types ────────────────────────────────────────────────────────────────────

type LeafletNS = typeof import("leaflet");

type OfficeMapReviewPanelProps = {
  job: JobDetail;
  // Phase 4E: when present, that session's track is emphasized and the map
  // fits to it on initial render. null/undefined means "no specific session
  // selected" — we fit to all geometry instead.
  selectedSessionId?: string | null;
};

// ─── Helpers (pure) ───────────────────────────────────────────────────────────

// Convert a JobDetail GeoJSON LineString (`[lon, lat]`) to a Leaflet-shaped
// `[lat, lng]` array. Defends against malformed or partial coordinate pairs.
function geometryToLatLngs(
  geometry: { coordinates?: number[][] } | null | undefined,
): Array<[number, number]> {
  const coords = geometry?.coordinates;
  if (!Array.isArray(coords)) return [];
  const out: Array<[number, number]> = [];
  for (const pair of coords) {
    if (!Array.isArray(pair) || pair.length < 2) continue;
    const lon = Number(pair[0]);
    const lat = Number(pair[1]);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
    out.push([lat, lon]);
  }
  return out;
}

function colorForIndex(idx: number): string {
  if (!Number.isFinite(idx) || idx < 0) return SESSION_COLORS[0];
  return SESSION_COLORS[idx % SESSION_COLORS.length];
}

function shortenId(rawId: string): string {
  if (!rawId) return "—";
  return rawId.length <= 8 ? rawId : rawId.slice(0, 8);
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function OfficeMapReviewPanel({
  job,
  selectedSessionId,
}: OfficeMapReviewPanelProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  // Keep the live Leaflet map + layer references in refs (not state) so we
  // never trigger re-renders from inside the imperative Leaflet update path.
  const mapRef = useRef<ReturnType<LeafletNS["map"]> | null>(null);
  const designLayersRef = useRef<Array<ReturnType<LeafletNS["polyline"]>>>([]);
  const sessionLayersRef = useRef<Array<ReturnType<LeafletNS["polyline"]>>>([]);
  const selectedHaloRef = useRef<ReturnType<LeafletNS["polyline"]> | null>(
    null,
  );
  const leafletNsRef = useRef<LeafletNS | null>(null);

  // Mount Leaflet exactly once. We deliberately use an empty dep array — the
  // job-data effect below handles all subsequent updates by mutating layers
  // directly. Re-creating the map on prop changes would flicker badly.
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
          center: [0, 0],
          zoom: 2,
          zoomControl: true,
          attributionControl: false,
          scrollWheelZoom: true,
          doubleClickZoom: false,
          boxZoom: false,
          keyboard: false,
        });
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 19,
        }).addTo(map);

        leafletNsRef.current = L;
        mapRef.current = map;

        // Trigger a render of the layers now that the map is alive.
        renderLayers();
      } catch {
        // Leaflet failed to load — leave the empty container; the parent
        // already shows a "Loading map…" skeleton via dynamic loading and
        // the data-effect below will silently no-op.
      }
    })();

    return () => {
      cancelled = true;
      try {
        const map = mapRef.current;
        if (map) map.remove();
      } catch {
        /* ignore */
      }
      mapRef.current = null;
      leafletNsRef.current = null;
      designLayersRef.current = [];
      sessionLayersRef.current = [];
      selectedHaloRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Redraw layers whenever the input data or the selection changes.
  // We declare renderLayers outside the effect so the mount-effect can call
  // it as soon as the map is live, then this effect handles every later
  // change.
  const renderLayers = () => {
    const L = leafletNsRef.current;
    const map = mapRef.current;
    if (!L || !map) return;

    // ── Wipe previous layers ──────────────────────────────────────────────
    for (const layer of designLayersRef.current) {
      try {
        layer.remove();
      } catch {
        /* ignore */
      }
    }
    designLayersRef.current = [];
    for (const layer of sessionLayersRef.current) {
      try {
        layer.remove();
      } catch {
        /* ignore */
      }
    }
    sessionLayersRef.current = [];
    if (selectedHaloRef.current) {
      try {
        selectedHaloRef.current.remove();
      } catch {
        /* ignore */
      }
      selectedHaloRef.current = null;
    }

    const allLatLngs: Array<[number, number]> = [];
    const selectedLatLngs: Array<[number, number]> = [];

    // ── Design routes (dashed gray, drawn first / underneath) ─────────────
    const routes: Route[] = Array.isArray(job.routes) ? job.routes : [];
    for (const route of routes) {
      const latlngs = geometryToLatLngs(route.geometry);
      if (latlngs.length < 2) continue;
      const layer = L.polyline(latlngs, {
        color: DESIGN_COLOR,
        weight: DESIGN_WEIGHT,
        opacity: DESIGN_OPACITY,
        dashArray: DESIGN_DASH,
        interactive: false,
      });
      layer.addTo(map);
      designLayersRef.current.push(layer);
      for (const ll of latlngs) allLatLngs.push(ll);
    }

    // ── Walk session tracks (solid colored, drawn on top) ─────────────────
    const sessions: Session[] = Array.isArray(job.sessions) ? job.sessions : [];
    sessions.forEach((session, idx) => {
      const latlngs = geometryToLatLngs(session.track_geometry);
      if (latlngs.length < 2) return;

      const isSelected =
        Boolean(selectedSessionId) && session.id === selectedSessionId;

      // Halo first (so the selected session's color sits on top of it).
      if (isSelected) {
        const halo = L.polyline(latlngs, {
          color: SELECTED_HALO_COLOR,
          weight: SELECTED_HALO_WEIGHT,
          opacity: SELECTED_HALO_OPACITY,
          interactive: false,
        });
        halo.addTo(map);
        selectedHaloRef.current = halo;
      }

      const layer = L.polyline(latlngs, {
        color: colorForIndex(idx),
        weight: isSelected ? SESSION_WEIGHT_SELECTED : SESSION_WEIGHT_DEFAULT,
        opacity: SESSION_OPACITY,
        interactive: false,
      });
      layer.addTo(map);
      sessionLayersRef.current.push(layer);
      for (const ll of latlngs) {
        allLatLngs.push(ll);
        if (isSelected) selectedLatLngs.push(ll);
      }
    });

    // ── Fit ───────────────────────────────────────────────────────────────
    // Prefer the selected session's bounds when one is selected. Otherwise
    // fit the union of every drawn polyline. If nothing was drawn the empty
    // states render as overlays and we leave the world view alone.
    const fitTarget =
      selectedLatLngs.length >= 2 ? selectedLatLngs : allLatLngs;
    if (fitTarget.length >= 2) {
      try {
        const bounds = L.latLngBounds(fitTarget);
        if (bounds.isValid()) {
          map.fitBounds(bounds, {
            padding: FIT_PADDING,
            maxZoom: FIT_MAX_ZOOM,
            animate: false,
          });
        }
      } catch {
        /* ignore */
      }
    }
  };

  useEffect(() => {
    renderLayers();
    // We pass the heavy bits as dependency surrogates: the route count, the
    // session count, and the selected id. We deliberately avoid putting the
    // arrays themselves in the dep list because they're new identities on
    // every parent fetch, but their geometry rarely changes within a single
    // session view.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    job.id,
    (job.routes ?? []).length,
    (job.sessions ?? []).length,
    selectedSessionId ?? null,
  ]);

  // ── Empty-state messaging ──────────────────────────────────────────────────
  // Both can fire at once: a job may have no design and no walks yet.
  const hasDesign = (job.routes ?? []).some(
    (r) => geometryToLatLngs(r.geometry).length >= 2,
  );
  const hasAnyWalkPath = (job.sessions ?? []).some(
    (s) => geometryToLatLngs(s.track_geometry).length >= 2,
  );

  // Selected-session subtitle for the header (compact ID + crew if known).
  const selectedSession =
    selectedSessionId && Array.isArray(job.sessions)
      ? job.sessions.find((s) => s.id === selectedSessionId) ?? null
      : null;

  return (
    <section>
      <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
        <h2 className="text-base font-semibold text-gray-800">
          Map Review
        </h2>
        {selectedSession && (
          <div className="text-xs text-gray-500">
            Highlighting session{" "}
            <span className="font-mono text-gray-700">
              {shortenId(selectedSession.id)}
            </span>
            {selectedSession.crew_name?.trim()
              ? ` — ${selectedSession.crew_name.trim()}`
              : ""}
          </div>
        )}
      </div>

      <div className="rounded-lg border border-gray-200 bg-white overflow-hidden shadow-sm">
        <div className="relative" style={{ height: 540 }}>
          <div
            ref={containerRef}
            className="absolute inset-0"
            style={{ height: "100%", width: "100%" }}
          />

          {/* Empty-state overlays. Stacked vertically when both apply. */}
          {(!hasDesign || !hasAnyWalkPath) && (
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-2 px-6 text-center">
              {!hasDesign && (
                <div className="rounded-md bg-white/85 px-3 py-1.5 text-xs font-medium text-gray-600 shadow-sm border border-gray-200">
                  No design route loaded.
                </div>
              )}
              {!hasAnyWalkPath && (
                <div className="rounded-md bg-white/85 px-3 py-1.5 text-xs font-medium text-gray-600 shadow-sm border border-gray-200">
                  No walk paths available yet.
                </div>
              )}
            </div>
          )}
        </div>

        {/* Legend (only shown when there's something to label). */}
        {(hasDesign || hasAnyWalkPath) && (
          <div className="flex flex-wrap items-center gap-4 border-t border-gray-100 bg-gray-50 px-4 py-2 text-xs text-gray-600">
            {hasDesign && (
              <div className="flex items-center gap-2">
                <span
                  className="inline-block"
                  style={{
                    width: 22,
                    height: 0,
                    borderTop: `${DESIGN_WEIGHT}px dashed ${DESIGN_COLOR}`,
                    opacity: DESIGN_OPACITY,
                  }}
                />
                Design route
              </div>
            )}
            {hasAnyWalkPath && (
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center gap-1">
                  {/* Show up to four palette swatches as a hint that each
                      walked session gets its own color. */}
                  {SESSION_COLORS.slice(0, 4).map((c) => (
                    <span
                      key={c}
                      className="inline-block"
                      style={{
                        width: 12,
                        height: 3,
                        background: c,
                        borderRadius: 1,
                      }}
                    />
                  ))}
                </span>
                Walk session tracks
              </div>
            )}
            {selectedSession && (
              <div className="flex items-center gap-2">
                <span
                  className="inline-block"
                  style={{
                    width: 22,
                    height: SELECTED_HALO_WEIGHT - 4,
                    background: SELECTED_HALO_COLOR,
                    opacity: SELECTED_HALO_OPACITY + 0.2,
                    borderRadius: 2,
                  }}
                />
                Selected submission
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
