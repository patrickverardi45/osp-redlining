"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";

export type CurrentGps = { lat: number; lon: number; accuracy_m: number };

export type MobileWalkAddEntryPayload = {
  stationText: string;
  note: string;
  photoFile: File | null;
};

function mobileButtonStyle(background: string, color: string, borderColor: string, disabled: boolean): React.CSSProperties {
  return {
    background,
    color,
    border: "2px solid #000000",
    borderRadius: 14,
    padding: "12px 14px",
    fontWeight: 800,
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.65 : 1,
    fontSize: 14,
  };
}

const STATION_MAX_LEN = 64;

function stationAppend(prev: string, ch: string): string {
  if (prev.length >= STATION_MAX_LEN) return prev;
  if (ch === "+") {
    if (prev.includes("+")) return prev;
    return prev + "+";
  }
  if (ch >= "0" && ch <= "9") return prev + ch;
  return prev;
}

/** Static north-up reference; map must not rotate with device heading. */
export function MobileWalkNorthCompass() {
  return (
    <div
      style={{
        position: "absolute",
        top: 12,
        right: 12,
        zIndex: 998,
        pointerEvents: "none",
        filter: "drop-shadow(0 2px 6px rgba(0,0,0,0.45))",
      }}
      aria-hidden
    >
      <svg width={56} height={56} viewBox="0 0 56 56" fill="none">
        <circle cx={28} cy={28} r={26} fill="rgba(15,23,42,0.88)" stroke="rgba(248,250,252,0.35)" strokeWidth={1.5} />
        <path d="M28 8 L34 26 L28 22 L22 26 Z" fill="#f87171" stroke="#fecaca" strokeWidth={0.75} />
        <text x={28} y={16} textAnchor="middle" fill="#fecaca" fontSize={9} fontWeight={800} fontFamily="Inter,system-ui,sans-serif">
          N
        </text>
        <text x={28} y={48} textAnchor="middle" fill="#94a3b8" fontSize={7} fontWeight={700} fontFamily="Inter,system-ui,sans-serif">
          S
        </text>
        <text x={10} y={31} textAnchor="middle" fill="#94a3b8" fontSize={7} fontWeight={700} fontFamily="Inter,system-ui,sans-serif">
          W
        </text>
        <text x={46} y={31} textAnchor="middle" fill="#94a3b8" fontSize={7} fontWeight={700} fontFamily="Inter,system-ui,sans-serif">
          E
        </text>
      </svg>
    </div>
  );
}

type EntrySheetProps = {
  busy: boolean;
  entryCountLabel: string;
  currentGps: CurrentGps | null;
  onCancel: () => void;
  onSave: (payload: MobileWalkAddEntryPayload) => void | Promise<void>;
};

function StationKeypadButton({
  label,
  onPress,
  disabled,
}: {
  label: React.ReactNode;
  onPress: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onPointerDown={(e) => e.stopPropagation()}
      onClick={() => {
        if (disabled) return;
        onPress();
      }}
      style={{
        flex: 1,
        minHeight: 48,
        borderRadius: 12,
        border: "2px solid #0f172a",
        background: disabled ? "#e2e8f0" : "#f8fafc",
        color: "#0f172a",
        fontSize: 20,
        fontWeight: 800,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.55 : 1,
        userSelect: "none",
        WebkitUserSelect: "none",
        WebkitTapHighlightColor: "transparent",
        touchAction: "manipulation",
      }}
    >
      {label}
    </button>
  );
}

/** Mounted only while the add-entry sheet is visible so no stray overlay nodes remain after close. */
export function EntrySheet({ busy, entryCountLabel, currentGps, onCancel, onSave }: EntrySheetProps) {
  const [stationText, setStationText] = useState("");
  const [note, setNote] = useState("");
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [noteExpanded, setNoteExpanded] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const append = useCallback((ch: string) => {
    setStationText((prev) => stationAppend(prev, ch));
  }, []);

  const backspace = useCallback(() => {
    setStationText((prev) => (prev.length ? prev.slice(0, -1) : ""));
  }, []);

  const clearStation = useCallback(() => {
    setStationText("");
  }, []);

  useEffect(() => {
    setStationText("");
    setNote("");
    setPhotoFile(null);
    setNoteExpanded(false);
  }, []);

  const stationDisplay = stationText.length ? stationText : "—";
  const hasPlusSlot = !stationText.includes("+");

  return (
    <div
      style={{
        position: "absolute",
        left: 10,
        right: 10,
        top: 72,
        zIndex: 1007,
        maxWidth: 480,
        marginLeft: "auto",
        marginRight: "auto",
        borderRadius: 16,
        background: "#ffffff",
        border: "1px solid #dbe4ee",
        boxShadow: "0 18px 42px rgba(0,0,0,0.28)",
        padding: 14,
        pointerEvents: "auto",
      }}
      onPointerDown={(e) => e.stopPropagation()}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", pointerEvents: "auto" }}>
        <div style={{ fontWeight: 800, fontSize: 16 }}>Add Walk Entry</div>
        <div style={{ fontSize: 12, color: "#64748b" }}>{entryCountLabel}</div>
      </div>
      {currentGps ? (
        <div style={{ marginTop: 6, fontSize: 11, color: "#64748b" }}>
          Location from walk GPS (±{Math.round(currentGps.accuracy_m)}m)
        </div>
      ) : (
        <div style={{ marginTop: 6, fontSize: 11, color: "#b45309" }}>No accepted GPS fix yet — save will try a one-time fix if needed.</div>
      )}

      <div style={{ marginTop: 12, display: "grid", gap: 12, pointerEvents: "auto" }}>
        <div style={{ display: "grid", gap: 8 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 12, fontWeight: 800, color: "#475569" }}>Station</span>
            <button
              type="button"
              disabled={busy || !stationText}
              onPointerDown={(e) => e.stopPropagation()}
              onClick={clearStation}
              style={{
                ...mobileButtonStyle("#ffffff", "#64748b", "#94a3b8", busy || !stationText),
                padding: "8px 12px",
                fontSize: 13,
                minHeight: 0,
              }}
            >
              Clear
            </button>
          </div>
          <div style={{ fontSize: 11, color: "#64748b", lineHeight: 1.35 }}>Digits and one + (e.g. 01+00, 012+050, 1234+0567).</div>
          <div
            role="status"
            aria-live="polite"
            style={{
              borderRadius: 12,
              border: "2px solid #0f172a",
              padding: "14px 14px",
              fontSize: 22,
              fontWeight: 800,
              width: "100%",
              boxSizing: "border-box",
              textAlign: "center",
              letterSpacing: 1,
              fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
              color: stationText.length ? "#0f172a" : "#94a3b8",
              background: "#f8fafc",
              minHeight: 54,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              userSelect: "none",
              WebkitUserSelect: "none",
              wordBreak: "break-all",
            }}
          >
            {stationDisplay}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8 }}>
            {(["1", "2", "3", "4", "5", "6", "7", "8", "9"] as const).map((d) => (
              <StationKeypadButton key={d} label={d} disabled={busy} onPress={() => append(d)} />
            ))}
            <StationKeypadButton label="+" disabled={busy || !hasPlusSlot} onPress={() => append("+")} />
            <StationKeypadButton label="0" disabled={busy} onPress={() => append("0")} />
            <StationKeypadButton label="⌫" disabled={busy || !stationText} onPress={backspace} />
          </div>
        </div>

        <label style={{ display: "grid", gap: 6 }}>
          <span style={{ fontSize: 12, fontWeight: 800, color: "#475569" }}>Note</span>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Optional note"
            rows={noteExpanded ? 5 : 2}
            onFocus={() => setNoteExpanded(true)}
            style={{
              borderRadius: 12,
              border: "1px solid #cfd8e3",
              padding: "10px 12px",
              fontSize: 15,
              minHeight: noteExpanded ? 100 : 52,
              resize: "vertical",
              width: "100%",
              boxSizing: "border-box",
              lineHeight: 1.45,
            }}
          />
        </label>

        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          capture="environment"
          style={{ display: "none" }}
          onChange={(e) => {
            const f = e.target.files?.[0] ?? null;
            setPhotoFile(f);
            try {
              e.currentTarget.value = "";
            } catch {
              /* ignore */
            }
          }}
        />

        <button
          type="button"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={() => fileInputRef.current?.click()}
          style={{
            ...mobileButtonStyle("#f8fafc", "#0f172a", "#cbd5e1", false),
            width: "100%",
            minHeight: 48,
            fontSize: 15,
          }}
        >
          {photoFile ? `Photo: ${photoFile.name}` : "Add photo (optional)"}
        </button>

        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 4 }}>
          <button
            type="button"
            disabled={busy}
            onPointerDown={(e) => e.stopPropagation()}
            onClick={() => onSave({ stationText, note, photoFile })}
            style={{
              ...mobileButtonStyle("#0f172a", "#ffffff", "#000000", busy),
              width: "100%",
              minHeight: 52,
              fontSize: 17,
            }}
          >
            Save Entry
          </button>
          <button
            type="button"
            disabled={busy}
            onPointerDown={(e) => e.stopPropagation()}
            onClick={onCancel}
            style={{
              ...mobileButtonStyle("#ffffff", "#64748b", "#94a3b8", busy),
              width: "100%",
              minHeight: 46,
              fontSize: 15,
            }}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

type MobileWalkUIProps = {
  busy: boolean;
  activeSession: { status: "active" | "ended"; entry_count: number } | null;
  showAddEntryModal: boolean;
  currentGps: CurrentGps | null;
  /** When false, Start Walk stays disabled (e.g. mobile /walk before KMZ loads route_coords). */
  designRouteReady?: boolean;
  walkPreflightOpen?: boolean;
  walkPreflightRouteName?: string | null;
  walkPreflightRouteLengthLabel?: string;
  walkPreflightSnapshotLabel?: string;
  onStartWalk: () => void;
  onConfirmWalkPreflight?: () => void;
  onDismissWalkPreflight?: () => void;
  onEndWalk: () => void;
  onOpenAddEntry: () => void;
  onCloseAddEntryModal: () => void;
  onAddEntry: (payload: MobileWalkAddEntryPayload) => void | Promise<void>;
  onSendHome: () => void | Promise<void>;
  sendHomeBusy?: boolean;
  canSendHome?: boolean;
};

export default function MobileWalkUI({
  busy,
  activeSession,
  showAddEntryModal,
  currentGps,
  designRouteReady = true,
  walkPreflightOpen = false,
  walkPreflightRouteName = null,
  walkPreflightRouteLengthLabel = "—",
  walkPreflightSnapshotLabel = "",
  onStartWalk,
  onConfirmWalkPreflight = () => {},
  onDismissWalkPreflight = () => {},
  onEndWalk,
  onOpenAddEntry,
  onCloseAddEntryModal,
  onAddEntry,
  onSendHome,
  sendHomeBusy = false,
  canSendHome = false,
}: MobileWalkUIProps) {
  const sendHomeDisabled = busy || sendHomeBusy || !canSendHome;
  const startWalkDisabled =
    busy || (!!activeSession && activeSession.status === "active") || !designRouteReady || walkPreflightOpen;
  const routeNameDisplay = walkPreflightRouteName?.trim() ? walkPreflightRouteName : "—";
  const snapshotLabel =
    walkPreflightSnapshotLabel && !Number.isNaN(Date.parse(walkPreflightSnapshotLabel))
      ? new Date(walkPreflightSnapshotLabel).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" })
      : walkPreflightSnapshotLabel || "—";

  return (
    <>
      {showAddEntryModal ? (
        <>
          <div
            role="presentation"
            style={{
              position: "absolute",
              inset: 0,
              zIndex: 1005,
              background: "rgba(15,23,42,0.28)",
              pointerEvents: "auto",
            }}
            onPointerDown={(e) => {
              e.stopPropagation();
              if (!busy) onCloseAddEntryModal();
            }}
          />
          <EntrySheet
            key="walk-entry-sheet"
            busy={busy}
            entryCountLabel={activeSession ? `${activeSession.entry_count} entries` : "No active session"}
            currentGps={currentGps}
            onCancel={onCloseAddEntryModal}
            onSave={onAddEntry}
          />
        </>
      ) : null}

      {walkPreflightOpen ? (
        <>
          <div
            role="presentation"
            style={{
              position: "absolute",
              inset: 0,
              zIndex: 1003,
              background: "rgba(15,23,42,0.32)",
              pointerEvents: "auto",
            }}
            onPointerDown={(e) => {
              e.stopPropagation();
              if (!busy) onDismissWalkPreflight();
            }}
          />
          <div
            style={{
              position: "absolute",
              left: 12,
              right: 12,
              top: "18%",
              zIndex: 1006,
              maxWidth: 480,
              marginLeft: "auto",
              marginRight: "auto",
              borderRadius: 16,
              background: "#ffffff",
              border: "2px solid #0f172a",
              boxShadow: "0 18px 42px rgba(0,0,0,0.35)",
              padding: 16,
              pointerEvents: "auto",
            }}
            onPointerDown={(e) => e.stopPropagation()}
          >
            <div style={{ fontWeight: 900, fontSize: 17, color: "#0f172a" }}>Confirm route</div>
            <div style={{ marginTop: 10, display: "grid", gap: 8, fontSize: 14, color: "#334155" }}>
              <div>
                <span style={{ fontWeight: 800, color: "#64748b" }}>Route </span>
                {routeNameDisplay}
              </div>
              <div>
                <span style={{ fontWeight: 800, color: "#64748b" }}>Length </span>
                {walkPreflightRouteLengthLabel}
              </div>
              <div>
                <span style={{ fontWeight: 800, color: "#64748b" }}>Snapshot </span>
                {snapshotLabel}
              </div>
            </div>
            <div style={{ marginTop: 14, display: "grid", gap: 10 }}>
              <button
                type="button"
                disabled={busy || !designRouteReady}
                onPointerDown={(e) => e.stopPropagation()}
                onClick={() => {
                  if (!busy && designRouteReady) onConfirmWalkPreflight();
                }}
                style={{
                  width: "100%",
                  ...mobileButtonStyle("#0f172a", "#ffffff", "#0f172a", busy || !designRouteReady),
                  fontSize: 17,
                  minHeight: 52,
                }}
              >
                Confirm and Start Walk
              </button>
              <button
                type="button"
                disabled={busy}
                onPointerDown={(e) => e.stopPropagation()}
                onClick={() => onDismissWalkPreflight()}
                style={{
                  width: "100%",
                  ...mobileButtonStyle("#ffffff", "#64748b", "#94a3b8", busy),
                  fontSize: 15,
                  minHeight: 46,
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        </>
      ) : null}

      <div
        style={{
          position: "absolute",
          left: 10,
          right: 10,
          bottom: 10,
          zIndex: 1001,
          display: "flex",
          flexDirection: "column",
          gap: 10,
          maxWidth: 520,
          marginLeft: "auto",
          marginRight: "auto",
          pointerEvents: "auto",
        }}
        onPointerDown={(e) => e.stopPropagation()}
      >
        {!designRouteReady && !activeSession ? (
          <div
            style={{
              borderRadius: 12,
              border: "1px solid #f59e0b",
              background: "rgba(254,243,199,0.95)",
              padding: "10px 12px",
              fontSize: 13,
              fontWeight: 700,
              color: "#92400e",
              lineHeight: 1.4,
            }}
          >
            No route loaded — ask office to load the correct job before starting.
          </div>
        ) : null}
        <button
          onPointerDown={(e) => e.stopPropagation()}
          onClick={onStartWalk}
          disabled={startWalkDisabled}
          style={{
            width: "100%",
            ...mobileButtonStyle("#0f172a", "#ffffff", "#0f172a", startWalkDisabled),
            fontSize: 17,
            minHeight: 54,
            paddingTop: 12,
            paddingBottom: 12,
          }}
        >
          Start Walk
        </button>
        <button
          onPointerDown={(e) => e.stopPropagation()}
          onClick={onOpenAddEntry}
          disabled={busy || !activeSession || activeSession.status !== "active"}
          style={{
            width: "100%",
            ...mobileButtonStyle("#ffffff", "#0f172a", "#cfd8e3", busy || !activeSession || activeSession.status !== "active"),
            fontSize: 17,
            minHeight: 54,
            paddingTop: 12,
            paddingBottom: 12,
          }}
        >
          Add Station / Event
        </button>
        <div style={{ display: "flex", gap: 10, width: "100%" }}>
          <button
            onPointerDown={(e) => e.stopPropagation()}
            onClick={onEndWalk}
            disabled={busy || !activeSession || activeSession.status !== "active"}
            style={{
              flex: 1,
              ...mobileButtonStyle("#ef4444", "#ffffff", "#ef4444", busy || !activeSession || activeSession.status !== "active"),
              fontSize: 17,
              minHeight: 54,
              paddingTop: 12,
              paddingBottom: 12,
            }}
          >
            End Walk
          </button>
          <button
            onPointerDown={(e) => e.stopPropagation()}
            onClick={() => void onSendHome()}
            disabled={sendHomeDisabled}
            style={{
              flex: 1,
              ...mobileButtonStyle("#10b981", "#ffffff", "#10b981", sendHomeDisabled),
              fontSize: 17,
              minHeight: 54,
              paddingTop: 12,
              paddingBottom: 12,
            }}
          >
            Send Home
          </button>
        </div>
      </div>
    </>
  );
}
