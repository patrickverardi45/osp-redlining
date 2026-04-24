// Browser-only geolocation hook for mobile walk mode.
//
// Subscribes to navigator.geolocation.watchPosition when enabled, returns
// the latest accepted fix as CurrentGps, and cleans up on unmount / disable.
//
// Safe for SSR: all browser access is guarded inside useEffect.

import { useEffect, useRef, useState } from "react";
import type { CurrentGps } from "@/components/MobileWalkUI";

const DEFAULT_OPTIONS: PositionOptions = {
  enableHighAccuracy: true,
  maximumAge: 0,
  timeout: 5000,
};

const MAX_ACCEPTED_ACCURACY_M = 30;
const MIN_ACCEPTED_MOVEMENT_M = 1.5;
const MAX_REASONABLE_SPEED_MPS = 12;
const MAX_SINGLE_JUMP_M = 60;

type AcceptedFix = CurrentGps & {
  timestamp: number;
};

function toRadians(value: number): number {
  return (value * Math.PI) / 180;
}

function distanceMeters(a: CurrentGps, b: CurrentGps): number {
  const earthRadiusM = 6371000;
  const dLat = toRadians(b.lat - a.lat);
  const dLon = toRadians(b.lon - a.lon);
  const lat1 = toRadians(a.lat);
  const lat2 = toRadians(b.lat);
  const h =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
  return 2 * earthRadiusM * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
}

function isFiniteFix(fix: CurrentGps): boolean {
  return (
    Number.isFinite(fix.lat) &&
    Number.isFinite(fix.lon) &&
    Number.isFinite(fix.accuracy_m)
  );
}

export function useGeolocation(enabled: boolean): {
  currentGps: CurrentGps | null;
  error: string | null;
} {
  const [currentGps, setCurrentGps] = useState<CurrentGps | null>(null);
  const [error, setError] = useState<string | null>(null);
  const lastAcceptedRef = useRef<AcceptedFix | null>(null);

  useEffect(() => {
    if (!enabled) {
      setCurrentGps(null);
      setError(null);
      lastAcceptedRef.current = null;
      return;
    }
    if (typeof window === "undefined" || !("geolocation" in navigator)) {
      setError("Geolocation is not available on this device.");
      return;
    }

    let cancelled = false;
    const watchId = navigator.geolocation.watchPosition(
      (pos) => {
        if (cancelled) return;

        const nextFix: AcceptedFix = {
          lat: pos.coords.latitude,
          lon: pos.coords.longitude,
          accuracy_m: pos.coords.accuracy,
          timestamp: pos.timestamp || Date.now(),
        };

        if (!isFiniteFix(nextFix)) {
          return;
        }

        if (nextFix.accuracy_m > MAX_ACCEPTED_ACCURACY_M) {
          setError(`Waiting for better GPS accuracy (±${Math.round(nextFix.accuracy_m)}m).`);
          return;
        }

        const last = lastAcceptedRef.current;
        if (last) {
          const distanceM = distanceMeters(last, nextFix);
          const elapsedS = Math.max((nextFix.timestamp - last.timestamp) / 1000, 0.1);
          const maxAllowedDistanceM = Math.max(
            MAX_SINGLE_JUMP_M,
            elapsedS * MAX_REASONABLE_SPEED_MPS
          );

          if (distanceM < MIN_ACCEPTED_MOVEMENT_M) {
            setError(null);
            return;
          }

          if (distanceM > maxAllowedDistanceM) {
            setError("Ignoring a GPS jump that is too large for walking speed.");
            return;
          }
        }

        lastAcceptedRef.current = nextFix;
        setCurrentGps({
          lat: nextFix.lat,
          lon: nextFix.lon,
          accuracy_m: nextFix.accuracy_m,
        });
        setError(null);
      },
      (err) => {
        if (cancelled) return;
        setError(err.message || "Location unavailable.");
      },
      DEFAULT_OPTIONS
    );

    return () => {
      cancelled = true;
      try {
        navigator.geolocation.clearWatch(watchId);
      } catch {
        /* ignore */
      }
    };
  }, [enabled]);

  return { currentGps, error };
}
