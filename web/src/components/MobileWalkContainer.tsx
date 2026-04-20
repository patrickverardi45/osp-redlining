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

  // GPS runs only while a session is active, to save battery.
  const { currentGps, error: gpsError } = useGeolocation(
    activeSession !== null && activeSession.status === "active"
  );

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
   * Defensive save flow:
   *  1. Validate session state before calling the service.
   *  2. Validate the payload (at minimum, station text) before calling the service.
   *  3. Use the atomic {entry, session} returned by service.addEntry so the UI
   *     can never be in a state where the entry exists but entry_count didn't update.
   *  4. Any error ALWAYS surfaces in the status toast. Modal stays open on error
   *     so the user can retry without losing their keypad input.
   *  5. `busy` is cleared in finally so the UI cannot get stuck disabled.
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
        const result = await service.addEntry({
          stationText: stationTrimmed,
          note: payload.note || "",
          photoFile: payload.photoFile ?? null,
          currentGps,
        });

        // Atomic: service returns both the entry and the refreshed session.
        setActiveSession(result.session);
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
          top: 12,
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
            ) : gpsError ? (
              <>
                {" • "}GPS: {gpsError}
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
            top: 76,
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

      <MobileWalkUI
        busy={busy}
        activeSession={adaptedSession}
        showAddEntryModal={showAddEntryModal}
        currentGps={currentGps}
        designRouteReady={hasAssignedRoute}
        walkPreflightOpen={walkPreflightOpen}
        walkPreflightRouteName={routeContext.routeName}
        walkPreflightRouteLengthLabel={routeLengthLabel}
        walkPreflightSnapshotLabel={routeContext.capturedAt}
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
