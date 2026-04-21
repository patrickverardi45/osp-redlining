"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import MobileWalkUI, {
  MobileWalkNorthCompass,
  type MobileWalkAddEntryPayload,
} from "@/components/MobileWalkUI";
import RouteContextMap from "@/components/walk/RouteContextMap";
import { defaultWalkService, type WalkSessionSnapshot, type WalkService } from "@/lib/walk/service";
import { useGeolocation } from "@/lib/walk/useGeolocation";
import {
  defaultOfficeContextService,
  EMPTY_ROUTE_CONTEXT,
  type OfficeContextService,
  type RouteContext,
} from "@/lib/walk/officeContextService";

type Props = {
  /** Optional service override; defaults to the module-scoped in-memory service. */
  service?: WalkService;
  /** Optional read-only office adapter for route/design awareness. */
  officeContextService?: OfficeContextService;
  /**
   * Optional auto-populated crew identifier shown read-only on the entry form.
   * Falls back to routeContext.crew (if present), then "".
   */
  crew?: string;
  /**
   * Optional auto-populated print / drawing identifier shown read-only on the
   * entry form. Falls back to routeContext.print (if present), then the route
   * name, then "".
   */
  print?: string;
};

/**
 * Shape of the mobile-only extras the UI collects but the current service
 * contract does not yet accept. Kept in local container state so the data
 * structure is locked and verifiable NOW; backend persistence is a
 * follow-up batch and deliberately not part of this pass.
 */
type EntryExtras = {
  sequence: number;
  stationText: string;
  depth: string;
  boc: string;
  note: string;
  date: string;
  crew: string;
  print: string;
  hasPhoto: boolean;
  gps: { lat: number; lon: number; accuracy_m: number } | null;
  savedAt: string;
};

function formatFeet(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  return `${value.toFixed(0)} ft`;
}

function describeError(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) return err.message;
  if (typeof err === "string" && err) return err;
  return fallback;
}

/**
 * Safely read an optional string field from an unknown-shaped record without
 * requiring the source type to declare it. Used so the container can pick up
 * crew / print from routeContext if the office adapter supplies them, without
 * modifying the RouteContext type.
 */
function readOptionalString(source: unknown, key: string): string {
  if (!source || typeof source !== "object") return "";
  const v = (source as Record<string, unknown>)[key];
  return typeof v === "string" ? v : "";
}

/**
 * Classify a raw geolocation error message into one of a few coarse buckets
 * so the field UI can show a clear, calm message instead of a raw browser
 * error string. Matching is intentionally loose — Safari, Chrome and the WebView
 * each phrase these slightly differently.
 */
function classifyGpsError(raw: string | null | undefined): {
  blocked: boolean;
  label: string;
} | null {
  if (!raw) return null;
  const s = raw.toLowerCase();

  // Permission denied / origin not permitted — the user (or the browser's
  // insecure-origin policy) has blocked geolocation for this page.
  // iOS Safari on non-HTTPS LAN origins emits: "Origin does not have permission to use Geolocation service".
  if (
    s.includes("permission") ||
    s.includes("denied") ||
    s.includes("not have permission") ||
    s.includes("user denied") ||
    s.includes("secure origin")
  ) {
    return {
      blocked: true,
      label: "GPS blocked — allow Location for this site, or use HTTPS. Manual entry still works.",
    };
  }

  // Position unavailable — hardware failure, no sky view, airplane mode, etc.
  if (s.includes("unavailable") || s.includes("position unavailable")) {
    return {
      blocked: true,
      label: "GPS unavailable on this device. Manual entry still works.",
    };
  }

  // Timeout — took too long to get a fix.
  if (s.includes("timeout") || s.includes("timed out")) {
    return {
      blocked: false,
      label: "GPS slow to acquire. Manual entry still works.",
    };
  }

  // Not supported at all (very old browsers).
  if (s.includes("not supported") || s.includes("unsupported")) {
    return {
      blocked: true,
      label: "This browser has no GPS support. Manual entry still works.",
    };
  }

  // Unknown — surface the raw short form but still treat as non-fatal.
  return {
    blocked: false,
    label: `GPS: ${raw}`,
  };
}

/**
 * Full-viewport container for the mobile walk experience.
 *
 * Owns walk session state and wires every MobileWalkUI callback to the walk service
 * adapter. Fetches read-only route context from the office backend on mount so the
 * field user can orient against the assigned route.
 *
 * No office chrome. No upload panels. No billing / review / analytics.
 */
export default function MobileWalkContainer({
  service = defaultWalkService,
  officeContextService = defaultOfficeContextService,
  crew: crewProp,
  print: printProp,
}: Props) {
  const [busy, setBusy] = useState(false);
  const [activeSession, setActiveSession] = useState<WalkSessionSnapshot | null>(null);
  const [showAddEntryModal, setShowAddEntryModal] = useState(false);
  const [walkPreflightOpen, setWalkPreflightOpen] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string>("");
  const [statusTone, setStatusTone] = useState<"neutral" | "success" | "error">("neutral");

  const [routeContext, setRouteContext] = useState<RouteContext>(EMPTY_ROUTE_CONTEXT);
  const [routeContextLoaded, setRouteContextLoaded] = useState(false);
  const [routeContextError, setRouteContextError] = useState<string | null>(null);

  // Dismissible GPS banner — set when we classify a blocked/unavailable state,
  // cleared when the user taps it or GPS starts working.
  const [gpsBannerDismissed, setGpsBannerDismissed] = useState(false);

  /**
   * Local capture of the extended field set for each saved entry, keyed by
   * the service-assigned sequence number. This is the deliberate scope of
   * this pass: the mobile data structure is captured and verifiable in the
   * browser (console + component state) without touching the service or
   * backend contracts. Persistence will be wired in a follow-up batch.
   */
  const [entryExtras, setEntryExtras] = useState<Record<number, EntryExtras>>({});

  // GPS runs only while a session is active, to save battery.
  const { currentGps, error: gpsError } = useGeolocation(
    activeSession !== null && activeSession.status === "active"
  );

  const gpsClassification = useMemo(() => classifyGpsError(gpsError), [gpsError]);
  const gpsBlocked = gpsClassification?.blocked ?? false;

  // If GPS starts working again, un-dismiss so the banner can reappear on a
  // later failure.
  useEffect(() => {
    if (currentGps) {
      setGpsBannerDismissed(false);
    }
  }, [currentGps]);

  // Rehydrate any in-flight session on mount (no-op for LocalWalkService).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const existing = await service.getActiveSession();
        if (!cancelled) setActiveSession(existing);
      } catch {
        /* ignore rehydrate errors in local mode */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [service]);

  // Fetch the assigned route context on mount.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const ctx = await officeContextService.fetchRouteContext();
        if (!cancelled) {
          setRouteContext(ctx);
          setRouteContextLoaded(true);
          setRouteContextError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setRouteContext(EMPTY_ROUTE_CONTEXT);
          setRouteContextLoaded(true);
          setRouteContextError(describeError(err, "Failed to load route."));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [officeContextService]);

  const hasAssignedRoute = routeContext.routeCoords.length >= 2;

  // Resolve crew/print from (in priority order) explicit props, routeContext
  // extension fields, or empty. Using readOptionalString keeps us from having
  // to modify the RouteContext type definition.
  const resolvedCrew = useMemo(() => {
    if (typeof crewProp === "string" && crewProp.trim().length) return crewProp;
    const fromCtx = readOptionalString(routeContext, "crew");
    if (fromCtx) return fromCtx;
    return "";
  }, [crewProp, routeContext]);

  const resolvedPrint = useMemo(() => {
    if (typeof printProp === "string" && printProp.trim().length) return printProp;
    const fromCtx =
      readOptionalString(routeContext, "print") ||
      readOptionalString(routeContext, "printName") ||
      readOptionalString(routeContext, "drawing") ||
      readOptionalString(routeContext, "drawingName");
    if (fromCtx) return fromCtx;
    // Last resort: the route name itself identifies the print for simple jobs.
    return routeContext.routeName || "";
  }, [printProp, routeContext]);

  const handleStartWalk = useCallback(() => {
    setWalkPreflightOpen(true);
  }, []);

  const handleDismissWalkPreflight = useCallback(() => {
    setWalkPreflightOpen(false);
  }, []);

  const handleConfirmWalkPreflight = useCallback(async () => {
    setBusy(true);
    try {
      const session = await service.startSession({
        route_name: routeContext.routeName,
        route_length_ft: routeContext.routeLengthFt,
        design_snapshot_label: routeContext.capturedAt,
      });
      setActiveSession(session);
      // Starting a new session clears any local extras from a prior session
      // so sequence numbers don't collide across walks.
      setEntryExtras({});
      setWalkPreflightOpen(false);
      setStatusMessage("Walk started.");
      setStatusTone("success");
    } catch (err) {
      setStatusMessage(describeError(err, "Failed to start walk."));
      setStatusTone("error");
    } finally {
      setBusy(false);
    }
  }, [service, routeContext]);

  const handleOpenAddEntry = useCallback(() => {
    // Guard against the sheet opening when there's no active session.
    // The MobileWalkUI already disables the button in that case, but we
    // defend here too so a stale UI state can't produce a confusing sheet.
    if (!activeSession || activeSession.status !== "active") {
      setStatusMessage("Start a walk before adding an entry.");
      setStatusTone("error");
      return;
    }
    setShowAddEntryModal(true);
  }, [activeSession]);

  const handleCloseAddEntryModal = useCallback(() => {
    if (busy) return;
    setShowAddEntryModal(false);
  }, [busy]);

  /**
   * Save flow for a walk entry.
   *
   * CONTRACT: service.addEntry accepts ONLY
   *   { stationText, note, photoFile, currentGps }
   * The mobile form collects additional fields (depth, boc, date, crew,
   * print). In THIS pass we deliberately do NOT send those extras through
   * the service — the backend contract is unchanged. Instead:
   *
   *   1. The service call goes through with exactly the supported shape,
   *      so the existing working pipeline is not broken.
   *   2. On a successful save, the container logs the full field set to
   *      the console tagged as `[walk] entry extras` for verification.
   *   3. The container also records the extras in local state
   *      (`entryExtras`), keyed by the service-assigned sequence number,
   *      so the data is inspectable in-memory while the UI is running.
   *   4. Persistence of the extras to the backend is a later batch.
   */
  const handleAddEntry = useCallback(
    async (payload: MobileWalkAddEntryPayload): Promise<void> => {
      if (busy) return;

      // Session guard — if the service rejects, we want to fail loudly here first.
      if (!activeSession || activeSession.status !== "active") {
        setStatusMessage("No active walk session. Start a walk before adding an entry.");
        setStatusTone("error");
        return;
      }

      // Payload guard — require at least a non-empty station string.
      const stationTrimmed = (payload.stationText || "").trim();
      if (!stationTrimmed) {
        setStatusMessage("Enter a station value before saving.");
        setStatusTone("error");
        return;
      }

      setBusy(true);
      try {
        // ---- Service call: original narrow shape ONLY. ----
        const result = await service.addEntry({
          stationText: stationTrimmed,
          note: payload.note || "",
          photoFile: payload.photoFile ?? null,
          currentGps,
        });

        // Atomic: service returns both the entry and the refreshed session.
        setActiveSession(result.session);

        // ---- Capture extras locally, keyed by sequence. ----
        const extras: EntryExtras = {
          sequence: result.entry.sequence,
          stationText: stationTrimmed,
          depth: (payload.depth || "").trim(),
          boc: (payload.boc || "").trim(),
          note: payload.note || "",
          date: payload.date || new Date().toISOString(),
          crew: payload.crew || "",
          print: payload.print || "",
          hasPhoto: !!payload.photoFile,
          gps: currentGps
            ? { lat: currentGps.lat, lon: currentGps.lon, accuracy_m: currentGps.accuracy_m }
            : null,
          savedAt: new Date().toISOString(),
        };

        setEntryExtras((prev) => ({ ...prev, [extras.sequence]: extras }));

        // ---- Verification log. Visible in Safari Web Inspector. ----
        if (typeof console !== "undefined" && console.log) {
          console.log("[walk] entry extras", extras);
        }

        setShowAddEntryModal(false);
        setStatusMessage(`Entry #${result.entry.sequence} saved.`);
        setStatusTone("success");
      } catch (err) {
        // Failure case: keep the modal open, tell the user, leave their input intact.
        const message = describeError(err, "Failed to save entry.");
        setStatusMessage(message);
        setStatusTone("error");
        if (typeof console !== "undefined" && console.error) {
          // Surface the raw error for debugging; does not leak to the user.
          console.error("[walk] addEntry failed:", err);
        }
      } finally {
        setBusy(false);
      }
    },
    [busy, activeSession, service, currentGps]
  );

  const handleEndWalk = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    try {
      const session = await service.endSession();
      setActiveSession(session);
      setStatusMessage("Walk ended.");
      setStatusTone("success");
    } catch (err) {
      setStatusMessage(describeError(err, "Failed to end walk."));
      setStatusTone("error");
    } finally {
      setBusy(false);
    }
  }, [busy, service]);

  const handleSendHome = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    try {
      const session = await service.sendHome();
      setActiveSession(session);
      setStatusMessage("Sent home.");
      setStatusTone("success");
    } catch (err) {
      setStatusMessage(describeError(err, "Failed to send home."));
      setStatusTone("error");
    } finally {
      setBusy(false);
    }
  }, [busy, service]);

  const adaptedSession = activeSession
    ? { status: activeSession.status, entry_count: activeSession.entry_count }
    : null;

  const canSendHome = activeSession !== null;

  const routeLengthLabel = useMemo(() => formatFeet(routeContext.routeLengthFt), [routeContext.routeLengthFt]);

  const noRouteMessage = routeContextLoaded
    ? routeContextError
      ? "Office unreachable"
      : "No route assigned"
    : "Loading route…";

  const showGpsBanner = !gpsBannerDismissed && !!gpsClassification && !currentGps;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "#0f172a",
        overflow: "hidden",
        touchAction: "none",
        fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
        color: "#f8fafc",
      }}
    >
      <RouteContextMap
        routeCoords={routeContext.routeCoords}
        currentGps={currentGps}
        noRouteMessage={noRouteMessage}
      />

      <MobileWalkNorthCompass />

      {/* Route header strip, top-center. Stays minimal. */}
      <div
        style={{
          position: "absolute",
          top: "max(12px, env(safe-area-inset-top))",
          left: 76,
          right: 76,
          zIndex: 998,
          display: "flex",
          justifyContent: "center",
          pointerEvents: "none",
        }}
      >
        <div
          style={{
            maxWidth: 360,
            padding: "8px 12px",
            borderRadius: 12,
            background: "rgba(15, 23, 42, 0.78)",
            border: "1px solid rgba(148, 163, 184, 0.35)",
            boxShadow: "0 6px 16px rgba(0,0,0,0.35)",
            textAlign: "center",
            color: "#f8fafc",
          }}
        >
          <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: 0.8, color: "#94a3b8", textTransform: "uppercase" }}>
            Route
          </div>
          <div style={{ marginTop: 2, fontSize: 14, fontWeight: 800, letterSpacing: -0.2 }}>
            {routeContext.routeName || "—"}
          </div>
          <div style={{ marginTop: 2, fontSize: 11, color: "#cbd5e1" }}>
            {routeLengthLabel}
            {currentGps ? (
              <>
                {" • "}GPS ±{Math.round(currentGps.accuracy_m)}m
              </>
            ) : gpsBlocked ? (
              <>
                {" • "}GPS off
              </>
            ) : null}
          </div>
        </div>
      </div>

      {/* Status toast, top-left under the route header. */}
      {statusMessage ? (
        <div
          role="status"
          aria-live="polite"
          style={{
            position: "absolute",
            top: "calc(max(12px, env(safe-area-inset-top)) + 64px)",
            left: 12,
            zIndex: 999,
            maxWidth: 260,
            borderRadius: 12,
            padding: "8px 10px",
            fontSize: 12,
            fontWeight: 700,
            color:
              statusTone === "error"
                ? "#7f1d1d"
                : statusTone === "success"
                ? "#065f46"
                : "#1f2937",
            background:
              statusTone === "error"
                ? "#fee2e2"
                : statusTone === "success"
                ? "#d1fae5"
                : "#e2e8f0",
            boxShadow: "0 6px 16px rgba(0,0,0,0.35)",
          }}
        >
          {statusMessage}
        </div>
      ) : null}

      {/* GPS banner — dismissible. Never blocks the walk flow. */}
      {showGpsBanner ? (
        <button
          type="button"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={() => setGpsBannerDismissed(true)}
          aria-label="Dismiss GPS warning"
          style={{
            position: "absolute",
            top: "calc(max(12px, env(safe-area-inset-top)) + 64px)",
            right: 12,
            zIndex: 999,
            maxWidth: 280,
            borderRadius: 12,
            padding: "10px 12px",
            fontSize: 12,
            fontWeight: 700,
            lineHeight: 1.4,
            color: "#92400e",
            background: "#fef3c7",
            border: "1px solid #f59e0b",
            boxShadow: "0 6px 16px rgba(0,0,0,0.35)",
            textAlign: "left",
            cursor: "pointer",
            WebkitTapHighlightColor: "transparent",
            touchAction: "manipulation",
          }}
        >
          <div>{gpsClassification?.label}</div>
          <div style={{ marginTop: 4, fontSize: 10, fontWeight: 700, color: "#a16207" }}>Tap to dismiss</div>
        </button>
      ) : null}

      <MobileWalkUI
        busy={busy}
        activeSession={adaptedSession}
        showAddEntryModal={showAddEntryModal}
        currentGps={currentGps}
        gpsBlocked={gpsBlocked}
        designRouteReady={hasAssignedRoute}
        walkPreflightOpen={walkPreflightOpen}
        walkPreflightRouteName={routeContext.routeName}
        walkPreflightRouteLengthLabel={routeLengthLabel}
        walkPreflightSnapshotLabel={routeContext.capturedAt}
        crew={resolvedCrew}
        print={resolvedPrint}
        onStartWalk={handleStartWalk}
        onConfirmWalkPreflight={handleConfirmWalkPreflight}
        onDismissWalkPreflight={handleDismissWalkPreflight}
        onEndWalk={handleEndWalk}
        onOpenAddEntry={handleOpenAddEntry}
        onCloseAddEntryModal={handleCloseAddEntryModal}
        onAddEntry={handleAddEntry}
        onSendHome={handleSendHome}
        sendHomeBusy={false}
        canSendHome={canSendHome}
      />
    </div>
  );
}
