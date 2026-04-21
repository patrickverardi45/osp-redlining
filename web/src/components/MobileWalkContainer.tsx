"use client";

import React, { useEffect, useMemo, useState } from "react";
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

  const { currentGps, error: gpsError } = useGeolocation(
    activeSession !== null && activeSession.status === "active"
  );

  const gpsClassification = useMemo(() => classifyGpsError(gpsError), [gpsError]);
  const gpsBlocked = gpsClassification?.blocked ?? false;

  useEffect(() => {
    if (currentGps) setGpsBannerDismissed(false);
  }, [currentGps]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const existing = await service.getActiveSession();
        if (!cancelled) setActiveSession(existing);
      } catch {}
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

  useEffect(() => {
    if (!statusMessage) return;
    const timer = window.setTimeout(() => {
      setStatusMessage("");
      setStatusTone("neutral");
    }, 2500);
    return () => window.clearTimeout(timer);
  }, [statusMessage]);

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

  const handleStartWalk = () => setWalkPreflightOpen(true);
  const handleDismissWalkPreflight = () => setWalkPreflightOpen(false);

  const handleConfirmWalkPreflight = async () => {
    setBusy(true);
    try {
      const session = await service.startSession({
        route_name: routeContext.routeName,
        route_length_ft: routeContext.routeLengthFt,
        design_snapshot_label: routeContext.capturedAt,
      });
      setActiveSession(session);
      setEntryExtras({});
      setStatusMessage("");
      setStatusTone("neutral");
      setWalkPreflightOpen(false);
    } catch (err) {
      setStatusMessage(describeError(err, "Failed to start walk."));
      setStatusTone("error");
    } finally {
      setBusy(false);
    }
  };

  const handleAddEntry = async (payload: MobileWalkAddEntryPayload) => {
    if (!activeSession || activeSession.status !== "active") return;

    setBusy(true);
    setStatusMessage("");
    setStatusTone("neutral");

    try {
      const trimmedStation = payload.stationText.trim();
      const result = await service.addEntry({
        stationText: trimmedStation,
        note: payload.note || "",
        photoFile: payload.photoFile ?? null,
        currentGps,
      });

      const extra: EntryExtras = {
        sequence: result.entry.sequence,
        stationText: trimmedStation,
        depth: (payload as Record<string, unknown>).depth && typeof (payload as Record<string, unknown>).depth === "string"
          ? ((payload as Record<string, unknown>).depth as string)
          : "",
        boc: (payload as Record<string, unknown>).boc && typeof (payload as Record<string, unknown>).boc === "string"
          ? ((payload as Record<string, unknown>).boc as string)
          : "",
        note: payload.note || "",
        date: (payload as Record<string, unknown>).date && typeof (payload as Record<string, unknown>).date === "string"
          ? ((payload as Record<string, unknown>).date as string)
          : "",
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
        savedAt: result.entry.created_at,
      };

      setEntryExtras((prev) => ({
        ...prev,
        [result.entry.sequence]: extra,
      }));
      setActiveSession(result.session);
      setShowAddEntryModal(false);
      setStatusMessage("Entry saved");
      setStatusTone("success");
    } catch (err) {
      setStatusMessage(describeError(err, "Failed to save entry."));
      setStatusTone("error");
    } finally {
      setBusy(false);
    }
  };

  const handleEndWalk = async () => {
    setBusy(true);
    try {
      const session = await service.endSession();
      setActiveSession(session);
    } catch (err) {
      setStatusMessage(describeError(err, "Failed to end walk."));
      setStatusTone("error");
    } finally {
      setBusy(false);
    }
  };

  const handleSendHome = async () => {
    setBusy(true);
    try {
      const session = await service.sendHome();
      setActiveSession(session);
    } catch (err) {
      setStatusMessage(describeError(err, "Failed to send home."));
      setStatusTone("error");
    } finally {
      setBusy(false);
    }
  };

  const adaptedSession = activeSession
    ? {
        status:
          activeSession.status === "sent_home"
            ? "ended"
            : activeSession.status,
        entry_count: activeSession.entry_count,
      }
    : null;

  return (
    <div style={{ position: "fixed", inset: 0 }}>
      <RouteContextMap
        routeCoords={routeContext.routeCoords}
        currentGps={currentGps}
        noRouteMessage="No route"
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
        onOpenAddEntry={() => setShowAddEntryModal(true)}
        onCloseAddEntryModal={() => setShowAddEntryModal(false)}
        onAddEntry={handleAddEntry}
        onSendHome={handleSendHome}
        sendHomeBusy={busy}
        canSendHome={true}
      />

      {statusMessage ? (
        <div
          role="status"
          aria-live="polite"
          style={{
            position: "absolute",
            left: "50%",
            bottom: 20,
            transform: "translateX(-50%)",
            padding: "10px 14px",
            borderRadius: 12,
            fontSize: 13,
            fontWeight: 700,
            letterSpacing: 0.2,
            color: "#f8fafc",
            background:
              statusTone === "success"
                ? "rgba(22, 163, 74, 0.92)"
                : statusTone === "error"
                  ? "rgba(220, 38, 38, 0.92)"
                  : "rgba(30, 41, 59, 0.92)",
            border:
              statusTone === "success"
                ? "1px solid rgba(134, 239, 172, 0.45)"
                : statusTone === "error"
                  ? "1px solid rgba(252, 165, 165, 0.45)"
                  : "1px solid rgba(148, 163, 184, 0.35)",
            boxShadow: "0 10px 30px rgba(0,0,0,0.25)",
            pointerEvents: "none",
            zIndex: 1200,
          }}
        >
          {statusMessage}
        </div>
      ) : null}
    </div>
  );
}
