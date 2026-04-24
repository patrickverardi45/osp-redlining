"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import MobileWalkUI, {
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
  service?: WalkService;
  officeContextService?: OfficeContextService;
  crew?: string;
  print?: string;
};

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

const TRAIL_MIN_DISTANCE_M = 2;
const TRAIL_MAX_SEGMENT_M = 45;
const TRAIL_MAX_POINTS = 2000;

function toRadians(value: number): number {
  return (value * Math.PI) / 180;
}

function distanceMeters(a: number[], b: number[]): number {
  const earthRadiusM = 6371000;
  const dLat = toRadians(b[0] - a[0]);
  const dLon = toRadians(b[1] - a[1]);
  const lat1 = toRadians(a[0]);
  const lat2 = toRadians(b[0]);
  const h =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
  return 2 * earthRadiusM * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
}

function formatFeet(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  return `${value.toFixed(0)} ft`;
}

function describeError(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) return err.message;
  if (typeof err === "string" && err) return err;
  return fallback;
}

function readOptionalString(source: unknown, key: string): string {
  if (!source || typeof source !== "object") return "";
  const v = (source as Record<string, unknown>)[key];
  return typeof v === "string" ? v : "";
}

function readOptionalPayloadString(payload: MobileWalkAddEntryPayload, key: string): string {
  const rec = payload as unknown as Record<string, unknown>;
  const v = rec[key];
  return typeof v === "string" ? v : "";
}

function classifyGpsError(raw: string | null | undefined): {
  blocked: boolean;
  label: string;
} | null {
  if (!raw) return null;
  const s = raw.toLowerCase();

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

  if (s.includes("unavailable") || s.includes("position unavailable")) {
    return {
      blocked: true,
      label: "GPS unavailable on this device. Manual entry still works.",
    };
  }

  if (s.includes("timeout") || s.includes("timed out")) {
    return {
      blocked: false,
      label: "GPS slow to acquire. Manual entry still works.",
    };
  }

  if (s.includes("not supported") || s.includes("unsupported")) {
    return {
      blocked: true,
      label: "This browser has no GPS support. Manual entry still works.",
    };
  }

  return {
    blocked: false,
    label: `GPS: ${raw}`,
  };
}

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

  const [gpsBannerDismissed, setGpsBannerDismissed] = useState(false);
  const [entryExtras, setEntryExtras] = useState<Record<number, EntryExtras>>({});

  // Breadcrumb trail of GPS fixes for the active session. Rendered as the
  // blue tracer on the map. Cleared when a new session starts.
  const [walkTrail, setWalkTrail] = useState<number[][]>([]);

  const { currentGps, error: gpsError } = useGeolocation(
    activeSession !== null && activeSession.status === "active"
  );

  const gpsClassification = useMemo(() => classifyGpsError(gpsError), [gpsError]);
  const gpsBlocked = gpsClassification?.blocked ?? false;

  useEffect(() => {
    if (currentGps) setGpsBannerDismissed(false);
  }, [currentGps]);

  // Append each sufficiently-distinct GPS fix to the walk trail while a
  // session is active. Deduplication prevents jitter from filling the trail.
  useEffect(() => {
    if (!currentGps) return;
    if (!activeSession || activeSession.status !== "active") return;
    setWalkTrail((prev) => {
      const nextPoint = [currentGps.lat, currentGps.lon];
      const last = prev[prev.length - 1];
      if (last) {
        const distanceM = distanceMeters(last, nextPoint);
        if (distanceM < TRAIL_MIN_DISTANCE_M || distanceM > TRAIL_MAX_SEGMENT_M) {
          return prev;
        }
      }
      const next = [...prev, nextPoint];
      if (next.length > TRAIL_MAX_POINTS) {
        return next.slice(next.length - TRAIL_MAX_POINTS);
      }
      return next;
    });
  }, [currentGps, activeSession]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const existing = await service.getActiveSession();
        if (!cancelled) setActiveSession(existing);
      } catch {
        /* ignore rehydrate errors */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [service]);

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

  // Auto-clear only SUCCESS/NEUTRAL status toasts. Errors stick until the
  // next action so the user cannot miss them.
  useEffect(() => {
    if (!statusMessage) return;
    if (statusTone === "error") return;
    const timer = window.setTimeout(() => {
      setStatusMessage("");
      setStatusTone("neutral");
    }, 2500);
    return () => window.clearTimeout(timer);
  }, [statusMessage, statusTone]);

  const hasAssignedRoute = routeContext.routeCoords.length >= 2;

  const resolvedCrew = useMemo(() => {
    if (crewProp) return crewProp;
    return readOptionalString(routeContext, "crew");
  }, [crewProp, routeContext]);

  const resolvedPrint = useMemo(() => {
    if (printProp) return printProp;
    return (
      readOptionalString(routeContext, "print") ||
      routeContext.routeName ||
      ""
    );
  }, [printProp, routeContext]);

  const handleStartWalk = useCallback(() => setWalkPreflightOpen(true), []);
  const handleDismissWalkPreflight = useCallback(() => setWalkPreflightOpen(false), []);

  const handleConfirmWalkPreflight = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    try {
      const session = await service.startSession({
        route_name: routeContext.routeName,
        route_length_ft: routeContext.routeLengthFt,
        design_snapshot_label: routeContext.capturedAt,
      });
      setActiveSession(session);
      setEntryExtras({});
      setWalkTrail([]); // fresh trail per session
      setStatusMessage("Walk started.");
      setStatusTone("success");
      setWalkPreflightOpen(false);
    } catch (err) {
      setStatusMessage(describeError(err, "Failed to start walk."));
      setStatusTone("error");
    } finally {
      setBusy(false);
    }
  }, [busy, service, routeContext]);

  const handleOpenAddEntry = useCallback(() => {
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
   * Save flow — hardened.
   *
   * Ordering is strict so the UI never ends up in a confusing state:
   *   1. Re-entrancy guard via `busy` AND a ref, so a double-tap cannot
   *      fire two concurrent saves.
   *   2. Validate session + station before touching the service.
   *   3. Call service.addEntry with the ORIGINAL narrow contract only.
   *   4. ONLY on success: update session, record extras, close modal,
   *      show success toast. Any thrown error keeps the modal open,
   *      shows an error toast, and clears busy in `finally`.
   *   5. Success toast is ALWAYS set so the user sees confirmation.
   */
  const saveInFlightRef = useRef(false);
  const handleAddEntry = useCallback(
    async (payload: MobileWalkAddEntryPayload) => {
      if (saveInFlightRef.current || busy) return;

      if (!activeSession || activeSession.status !== "active") {
        setStatusMessage("No active walk session.");
        setStatusTone("error");
        return;
      }

      const trimmedStation = (payload.stationText || "").trim();
      if (!trimmedStation) {
        setStatusMessage("Enter a station value before saving.");
        setStatusTone("error");
        return;
      }

      saveInFlightRef.current = true;
      setBusy(true);
      try {
        const result = await service.addEntry({
          stationText: trimmedStation,
          note: payload.note || "",
          photoFile: payload.photoFile ?? null,
          currentGps,
        });

        if (!result || !result.entry || !result.session) {
          throw new Error("Service returned an invalid save result.");
        }

        const extra: EntryExtras = {
          sequence: result.entry.sequence,
          stationText: trimmedStation,
          depth: readOptionalPayloadString(payload, "depth"),
          boc: readOptionalPayloadString(payload, "boc"),
          note: payload.note || "",
          date: readOptionalPayloadString(payload, "date") || new Date().toISOString(),
          crew: resolvedCrew,
          print: resolvedPrint,
          hasPhoto: Boolean(payload.photoFile),
          gps: currentGps
            ? {
                lat: currentGps.lat,
                lon: currentGps.lon,
                accuracy_m: currentGps.accuracy_m,
              }
            : null,
          savedAt:
            (result.entry as unknown as { created_at?: string }).created_at ||
            new Date().toISOString(),
        };

        // Commit state in one logical batch:
        setEntryExtras((prev) => ({ ...prev, [result.entry.sequence]: extra }));
        setActiveSession(result.session);
        setShowAddEntryModal(false);
        setStatusMessage(`Entry #${result.entry.sequence} saved.`);
        setStatusTone("success");

        if (typeof console !== "undefined" && console.log) {
          console.log("[walk] entry saved", {
            sequence: result.entry.sequence,
            extras: extra,
          });
        }
      } catch (err) {
        // Modal stays open, keypad input intact, error visible.
        const message = describeError(err, "Failed to save entry.");
        setStatusMessage(message);
        setStatusTone("error");
        if (typeof console !== "undefined" && console.error) {
          console.error("[walk] addEntry failed:", err);
        }
      } finally {
        saveInFlightRef.current = false;
        setBusy(false);
      }
    },
    [busy, activeSession, service, currentGps, resolvedCrew, resolvedPrint]
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
    ? {
        status:
          activeSession.status === "sent_home"
            ? "ended"
            : activeSession.status,
        entry_count: activeSession.entry_count,
      }
    : null;

  const canSendHome = activeSession !== null;

  return (
    <div style={{ position: "fixed", inset: 0 }}>
      <RouteContextMap
        routeCoords={routeContext.routeCoords}
        currentGps={currentGps}
        walkTrail={walkTrail}
        noRouteMessage={
          routeContextLoaded
            ? routeContextError
              ? "Office unreachable"
              : "No route assigned"
            : "Loading route…"
        }
      />

      <MobileWalkUI
        busy={busy}
        activeSession={adaptedSession}
        showAddEntryModal={showAddEntryModal}
        currentGps={currentGps}
        gpsBlocked={gpsBlocked}
        designRouteReady={hasAssignedRoute}
        walkPreflightOpen={walkPreflightOpen}
        walkPreflightRouteName={routeContext.routeName}
        walkPreflightRouteLengthLabel={formatFeet(routeContext.routeLengthFt)}
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
        sendHomeBusy={busy}
        canSendHome={canSendHome}
      />

      {!gpsBannerDismissed && gpsClassification && !currentGps ? (
        <button
          type="button"
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
          <div>{gpsClassification.label}</div>
          <div style={{ marginTop: 4, fontSize: 10, fontWeight: 700, color: "#a16207" }}>
            Tap to dismiss
          </div>
        </button>
      ) : null}

      {statusMessage ? (
        <div
          role="status"
          aria-live="polite"
          style={{
            position: "absolute",
            left: "50%",
            bottom: "calc(20px + env(safe-area-inset-bottom))",
            transform: "translateX(-50%)",
            padding: "10px 14px",
            borderRadius: 12,
            fontSize: 13,
            fontWeight: 700,
            letterSpacing: 0.2,
            color: "#f8fafc",
            background:
              statusTone === "success"
                ? "rgba(22, 163, 74, 0.94)"
                : statusTone === "error"
                  ? "rgba(220, 38, 38, 0.94)"
                  : "rgba(30, 41, 59, 0.94)",
            border:
              statusTone === "success"
                ? "1px solid rgba(134, 239, 172, 0.45)"
                : statusTone === "error"
                  ? "1px solid rgba(252, 165, 165, 0.45)"
                  : "1px solid rgba(148, 163, 184, 0.35)",
            boxShadow: "0 10px 30px rgba(0,0,0,0.25)",
            pointerEvents: "none",
            zIndex: 1200,
            maxWidth: "86%",
            textAlign: "center",
          }}
        >
          {statusMessage}
        </div>
      ) : null}
    </div>
  );
}
