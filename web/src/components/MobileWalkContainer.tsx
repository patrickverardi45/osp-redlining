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
          setRouteContextError(err instanceof Error ? err.message : "Failed to load route.");
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
      setStatusMessage(err instanceof Error ? err.message : "Failed to start walk.");
      setStatusTone("error");
    } finally {
      setBusy(false);
    }
  }, [service, routeContext]);

  const handleOpenAddEntry = useCallback(() => {
    setShowAddEntryModal(true);
  }, []);

  const handleCloseAddEntryModal = useCallback(() => {
    setShowAddEntryModal(false);
  }, []);

  const handleAddEntry = useCallback(
    async (payload: MobileWalkAddEntryPayload) => {
      setBusy(true);
      try {
        const entry = await service.addEntry({ ...payload, currentGps });
        const session = await service.getActiveSession();
        if (session) setActiveSession(session);
        setShowAddEntryModal(false);
        setStatusMessage(`Entry #${entry.sequence} saved.`);
        setStatusTone("success");
      } catch (err) {
        setStatusMessage(err instanceof Error ? err.message : "Failed to save entry.");
        setStatusTone("error");
      } finally {
        setBusy(false);
      }
    },
    [service, currentGps]
  );

  const handleEndWalk = useCallback(async () => {
    setBusy(true);
    try {
      const session = await service.endSession();
      setActiveSession(session);
      setStatusMessage("Walk ended.");
      setStatusTone("success");
    } catch (err) {
      setStatusMessage(err instanceof Error ? err.message : "Failed to end walk.");
      setStatusTone("error");
    } finally {
      setBusy(false);
    }
  }, [service]);

  const handleSendHome = useCallback(async () => {
    setBusy(true);
    try {
      const session = await service.sendHome();
      setActiveSession(session);
      setStatusMessage("Sent home.");
      setStatusTone("success");
    } catch (err) {
      setStatusMessage(err instanceof Error ? err.message : "Failed to send home.");
      setStatusTone("error");
    } finally {
      setBusy(false);
    }
  }, [service]);

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
