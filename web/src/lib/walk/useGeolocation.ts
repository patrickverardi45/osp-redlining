// Browser-only geolocation hook for mobile walk mode.
//
// Subscribes to navigator.geolocation.watchPosition when enabled, returns
// the latest accepted fix as CurrentGps, and cleans up on unmount / disable.
//
// Safe for SSR: all browser access is guarded inside useEffect.

import { useEffect, useState } from "react";
import type { CurrentGps } from "@/components/MobileWalkUI";

const DEFAULT_OPTIONS: PositionOptions = {
  enableHighAccuracy: true,
  maximumAge: 1000,
  timeout: 15000,
};

export function useGeolocation(enabled: boolean): {
  currentGps: CurrentGps | null;
  error: string | null;
} {
  const [currentGps, setCurrentGps] = useState<CurrentGps | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) {
      setCurrentGps(null);
      setError(null);
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
        setCurrentGps({
          lat: pos.coords.latitude,
          lon: pos.coords.longitude,
          accuracy_m: pos.coords.accuracy,
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
