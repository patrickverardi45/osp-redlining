"use client";

import React, { useCallback, useEffect, useState } from "react";
import MobileWalkUI, {
  MobileWalkNorthCompass,
  type MobileWalkAddEntryPayload,
} from "@/components/MobileWalkUI";
import { defaultWalkService, type WalkSessionSnapshot, type WalkService } from "@/lib/walk/service";
import { useGeolocation } from "@/lib/walk/useGeolocation";

type Props = {
  /** Optional service override; defaults to the module-scoped in-memory service. */
  service?: WalkService;
};

/**
 * Full-viewport container for the mobile walk experience.
 *
 * Owns walk session state and wires every MobileWalkUI callback to the walk service
 * adapter. No backend calls. No office chrome. When backend walk endpoints ship,
 * swapping the service is the only change.
 */
export default function MobileWalkContainer({ service = defaultWalkService }: Props) {
  const [busy, setBusy] = useState(false);
  const [activeSession, setActiveSession] = useState<WalkSessionSnapshot | null>(null);
  const [showAddEntryModal, setShowAddEntryModal] = useState(false);
  const [walkPreflightOpen, setWalkPreflightOpen] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string>("");
  const [statusTone, setStatusTone] = useState<"neutral" | "success" | "error">("neutral");

  // GPS runs only while a session is active, to save battery.
  const { currentGps, error: gpsError } = useGeolocation(
    activeSession !== null && activeSession.status === "active"
  );

  // Rehydrate any in-flight session on mount (no-op for LocalWalkService, real work once remote).
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
        route_name: null,
        route_length_ft: null,
        design_snapshot_label: null,
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
  }, [service]);

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
        // Re-read the session so entry_count stays the source of truth.
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

  // MobileWalkUI expects a narrower session shape; adapt our snapshot to it.
  const adaptedSession = activeSession
    ? { status: activeSession.status, entry_count: activeSession.entry_count }
    : null;

  const canSendHome = activeSession !== null;

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
      {/* Placeholder map canvas area. Backend walks + full map rendering land in a follow-up batch. */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "radial-gradient(ellipse at 50% 40%, rgba(30, 64, 125, 0.55) 0%, rgba(15, 23, 42, 1) 75%)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          pointerEvents: "none",
        }}
      >
        <div
          style={{
            textAlign: "center",
            maxWidth: 320,
            padding: 16,
            opacity: 0.85,
            pointerEvents: "none",
          }}
        >
          <div style={{ fontSize: 20, fontWeight: 800, letterSpacing: -0.4 }}>Walk mode</div>
          <div style={{ marginTop: 8, fontSize: 13, color: "#cbd5e1", lineHeight: 1.5 }}>
            {activeSession && activeSession.status === "active"
              ? "Session active. Use the controls below to record stations."
              : "Tap Start Walk to begin a session."}
          </div>
          {currentGps ? (
            <div style={{ marginTop: 10, fontSize: 12, color: "#94a3b8" }}>
              GPS {currentGps.lat.toFixed(5)}, {currentGps.lon.toFixed(5)} • ±
              {Math.round(currentGps.accuracy_m)}m
            </div>
          ) : gpsError ? (
            <div style={{ marginTop: 10, fontSize: 12, color: "#fca5a5" }}>GPS: {gpsError}</div>
          ) : null}
        </div>
      </div>

      <MobileWalkNorthCompass />

      {/* Status toast — top-left so it doesn't collide with the compass. */}
      {statusMessage ? (
        <div
          role="status"
          aria-live="polite"
          style={{
            position: "absolute",
            top: 12,
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
        designRouteReady={true}
        walkPreflightOpen={walkPreflightOpen}
        walkPreflightRouteName={null}
        walkPreflightRouteLengthLabel="—"
        walkPreflightSnapshotLabel=""
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
