"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { getJobs, type Job } from "@/lib/api";
import { getOrCreateSessionId } from "@/lib/session";

// ─── Configuration ────────────────────────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

const FORM_STORAGE_KEY = "osp_walk_form_v1";

const ACCURACY_FILTER_M = 75;
const MIN_POINT_SPACING_M = 3;
const POOR_ACCURACY_M = 30;
const FLUSH_INTERVAL_MS = 10000;

// Map: zoom locked at this value once we get our first fix. We pan but never
// rezoom while the walk is active, per spec.
const MAP_LOCKED_ZOOM = 18;

// Phase 3B-A: cap on individual photo size (bytes) we are willing to keep
// referenced in memory. We do not encode the file or hold its bytes in
// React state — only the File handle plus a small metadata snapshot — but
// browsers vary on object-URL memory pressure, so we still refuse absurd
// inputs early.
const PHOTO_MAX_BYTES = 25 * 1024 * 1024;

// ─── Types ────────────────────────────────────────────────────────────────────

type WalkFormFields = {
  jobId: string;
  crew: string;
  date: string;
  section: string;
};

type WalkStatus = "not_started" | "walking" | "ended";

type GpsStatus =
  | "idle"
  | "requesting"
  | "active"
  | "poor"
  | "denied"
  | "error"
  | "unsupported";

type Breadcrumb = {
  lat: number;
  lon: number;
  accuracy_m: number | null;
  ts: string;
};

type LatestPoint = {
  lat: number;
  lon: number;
  accuracy_m: number | null;
};

type EndSummary = {
  breadcrumb_count: number;
  station_event_count: number;
  last_accuracy_m: number | null;
  gps_status: GpsStatus;
};

// Phase 2D: route-context banner state. "unknown" covers both "no job
// selected yet" and "selected option is the offline fallback that has no Job
// payload behind it" — in both cases we render no banner.
type RouteContextState = "unknown" | "available" | "missing";

// Phase 3B-A: per-entry photo metadata. We hold the original File handle
// (cheap reference, no copy) for a future upload phase, plus a small
// metadata snapshot for display. The object_url is created with
// URL.createObjectURL and MUST be revoked when the entry is dropped.
type EntryPhoto = {
  file: File;
  filename: string;
  size_bytes: number;
  mime_type: string;
  object_url: string;
};

// Phase 3A + 3B-A: a station entry captured during a walk. Stored locally
// only; no backend wiring yet. Photo is optional.
type StationEntry = {
  id: string;
  station_number: string;
  depth_ft: number;
  boc_ft: number;
  lat: number;
  lon: number;
  accuracy_m: number | null;
  ts: string;
  photo: EntryPhoto | null;
};

const STATUS_LABELS: Record<WalkStatus, string> = {
  not_started: "Not Started",
  walking: "Walking",
  ended: "Walk Ended – Ready to Send",
};

const GPS_STATUS_LABELS: Record<GpsStatus, string> = {
  idle: "Idle",
  requesting: "Waiting…",
  active: "Active",
  poor: "Poor accuracy",
  denied: "Permission denied",
  error: "Error",
  unsupported: "Unsupported",
};

// ─── Map controller (vanilla Leaflet, no react-leaflet) ──────────────────────
// Imperatively driven from outside React state so the GPS callback can push
// updates without triggering re-renders. Lives behind a ref-held controller
// object whose methods are no-ops until the map is initialized.

type LeafletNS = typeof import("leaflet");

type MapController = {
  init(container: HTMLDivElement): Promise<boolean>;
  destroy(): void;
  setPosition(lat: number, lon: number): void;
  appendBreadcrumb(lat: number, lon: number): void;
  resetTrail(): void;
};

function createMapController(): MapController {
  let L: LeafletNS | null = null;
  let map: ReturnType<LeafletNS["map"]> | null = null;
  let polyline: ReturnType<LeafletNS["polyline"]> | null = null;
  let positionMarker: ReturnType<LeafletNS["circleMarker"]> | null = null;
  let positionHalo: ReturnType<LeafletNS["circleMarker"]> | null = null;
  let hasCentered = false;
  const trail: Array<[number, number]> = [];

  return {
    async init(container: HTMLDivElement): Promise<boolean> {
      try {
        const mod = await import("leaflet");
        // Some bundlers expose the namespace under .default, others as the
        // module itself. Cover both.
        L =
          (mod as unknown as { default?: LeafletNS }).default ??
          (mod as unknown as LeafletNS);
        map = L.map(container, {
          center: [0, 0],
          zoom: 2,
          zoomControl: false,
          attributionControl: false,
          // Lock zoom interactions so the map doesn't fight the user when
          // we recenter on every fix.
          scrollWheelZoom: false,
          doubleClickZoom: false,
          boxZoom: false,
          touchZoom: false,
          keyboard: false,
        });
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 19,
        }).addTo(map);

        polyline = L.polyline([], {
          color: "#38bdf8", // sky-400
          weight: 4,
          opacity: 0.9,
        }).addTo(map);

        return true;
      } catch {
        // Caller will render the fallback panel.
        return false;
      }
    },

    destroy(): void {
      try {
        polyline?.remove();
        positionMarker?.remove();
        positionHalo?.remove();
        map?.remove();
      } catch {
        /* ignore */
      }
      polyline = null;
      positionMarker = null;
      positionHalo = null;
      map = null;
      L = null;
      hasCentered = false;
      trail.length = 0;
    },

    setPosition(lat: number, lon: number): void {
      if (!L || !map) return;
      const latlng: [number, number] = [lat, lon];
      try {
        if (!positionHalo) {
          positionHalo = L.circleMarker(latlng, {
            radius: 14,
            color: "#38bdf8",
            weight: 0,
            fillColor: "#38bdf8",
            fillOpacity: 0.18,
            interactive: false,
          }).addTo(map);
        } else {
          positionHalo.setLatLng(latlng);
        }
        if (!positionMarker) {
          positionMarker = L.circleMarker(latlng, {
            radius: 7,
            color: "#0c4a6e", // dark ring for contrast
            weight: 2,
            fillColor: "#38bdf8",
            fillOpacity: 1,
            interactive: false,
          }).addTo(map);
        } else {
          positionMarker.setLatLng(latlng);
        }
        if (!hasCentered) {
          map.setView(latlng, MAP_LOCKED_ZOOM, { animate: false });
          hasCentered = true;
        } else {
          // Pan only — never re-zoom. panTo is gentle and cancels any
          // ongoing animation, which keeps movement smooth.
          map.panTo(latlng, { animate: true, duration: 0.35 });
        }
      } catch {
        /* ignore — keep the page alive even if Leaflet errors mid-update */
      }
    },

    appendBreadcrumb(lat: number, lon: number): void {
      if (!polyline) return;
      try {
        trail.push([lat, lon]);
        // addLatLng is the cheap append path — does not redraw the whole
        // line, just extends it.
        polyline.addLatLng([lat, lon]);
      } catch {
        /* ignore */
      }
    },

    resetTrail(): void {
      if (!polyline) return;
      try {
        trail.length = 0;
        polyline.setLatLngs([]);
      } catch {
        /* ignore */
      }
    },
  };
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function todayIso(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function metersBetween(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
): number {
  const R = 6371000;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const meanLat = ((lat1 + lat2) * Math.PI) / 360;
  const x = dLon * Math.cos(meanLat);
  return Math.sqrt(x * x + dLat * dLat) * R;
}

const DEFAULT_FORM: WalkFormFields = {
  jobId: "",
  crew: "",
  date: "",
  section: "",
};

function readPersistedForm(): WalkFormFields | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(FORM_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<WalkFormFields> | null;
    if (!parsed || typeof parsed !== "object") return null;
    return {
      jobId: typeof parsed.jobId === "string" ? parsed.jobId : "",
      crew: typeof parsed.crew === "string" ? parsed.crew : "",
      date: typeof parsed.date === "string" ? parsed.date : "",
      section: typeof parsed.section === "string" ? parsed.section : "",
    };
  } catch {
    return null;
  }
}

function writePersistedForm(fields: WalkFormFields): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(FORM_STORAGE_KEY, JSON.stringify(fields));
  } catch {
    /* ignore */
  }
}

async function postJson(path: string, body: unknown): Promise<Response> {
  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
}

function newEntryId(): string {
  if (
    typeof window !== "undefined" &&
    typeof window.crypto?.randomUUID === "function"
  ) {
    return window.crypto.randomUUID();
  }
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}

function safeRevokeObjectUrl(url: string | null | undefined): void {
  if (!url) return;
  try {
    URL.revokeObjectURL(url);
  } catch {
    /* ignore */
  }
}

function formatBytes(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return "0 B";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function WalkPage() {
  const [hydrated, setHydrated] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);

  const [form, setForm] = useState<WalkFormFields>(DEFAULT_FORM);

  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobsLoading, setJobsLoading] = useState(true);
  const [jobsError, setJobsError] = useState<string | null>(null);

  const [status, setStatus] = useState<WalkStatus>("not_started");
  const [sentHome, setSentHome] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [isEnding, setIsEnding] = useState(false);
  const [isSending, setIsSending] = useState(false);

  const [gpsStatus, setGpsStatus] = useState<GpsStatus>("idle");
  const [latestPoint, setLatestPoint] = useState<LatestPoint | null>(null);
  const [pointCount, setPointCount] = useState<number>(0);
  const [serverPointCount, setServerPointCount] = useState<number>(0);

  const [actionError, setActionError] = useState<string | null>(null);
  const [endSummary, setEndSummary] = useState<EndSummary | null>(null);

  const [mapAvailable, setMapAvailable] = useState<boolean>(true);

  // Phase 3A: station entries captured during this walk. Stored as state
  // (not just a ref) so the entry count rerenders when the user saves one.
  // Local-only — no backend wiring in this phase.
  const [stationEntries, setStationEntries] = useState<StationEntry[]>([]);
  const [entryFormOpen, setEntryFormOpen] = useState<boolean>(false);
  const [entryDraft, setEntryDraft] = useState<{
    station_number: string;
    depth_ft: string;
    boc_ft: string;
  }>({ station_number: "", depth_ft: "", boc_ft: "" });
  const [entryError, setEntryError] = useState<string | null>(null);

  // Phase 3B-A: pending photo for the current entry draft. Held outside the
  // entry list so cancel/clear paths can revoke its object URL cleanly
  // without scanning the saved entries.
  const [photoDraft, setPhotoDraft] = useState<EntryPhoto | null>(null);
  const photoInputRef = useRef<HTMLInputElement | null>(null);

  const watchIdRef = useRef<number | null>(null);
  const pendingPointsRef = useRef<Breadcrumb[]>([]);
  const lastAcceptedRef = useRef<Breadcrumb | null>(null);
  const flushTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const flushInFlightRef = useRef<boolean>(false);
  const sessionIdRef = useRef<string | null>(null);

  // Mirror of latestPoint for the entry-save path. Save reads from the ref
  // so we always pick up the most recent fix even if React hasn't flushed
  // the corresponding render yet.
  const latestPointRef = useRef<LatestPoint | null>(null);

  // Map controller is mounted/unmounted by the MapPanel child component, but
  // it lives in a parent ref so the GPS callback can drive it directly without
  // needing the child to expose anything via React state.
  const mapControllerRef = useRef<MapController | null>(null);

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  useEffect(() => {
    latestPointRef.current = latestPoint;
  }, [latestPoint]);

  useEffect(() => {
    const persisted = readPersistedForm();
    setForm({
      jobId: persisted?.jobId ?? DEFAULT_FORM.jobId,
      crew: persisted?.crew ?? DEFAULT_FORM.crew,
      date:
        persisted?.date && persisted.date.length > 0
          ? persisted.date
          : todayIso(),
      section: persisted?.section ?? DEFAULT_FORM.section,
    });
    setSessionId(getOrCreateSessionId());
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    writePersistedForm(form);
  }, [form, hydrated]);

  const fetchJobs = useCallback(async () => {
    setJobsLoading(true);
    setJobsError(null);
    try {
      const data = await getJobs();
      setJobs(data);
    } catch (err: unknown) {
      setJobsError(
        err instanceof Error ? err.message : "Could not load jobs.",
      );
      setJobs([]);
    } finally {
      setJobsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  useEffect(() => {
    return () => {
      if (watchIdRef.current !== null && typeof navigator !== "undefined") {
        try {
          navigator.geolocation.clearWatch(watchIdRef.current);
        } catch {
          /* ignore */
        }
        watchIdRef.current = null;
      }
      if (flushTimerRef.current !== null) {
        clearInterval(flushTimerRef.current);
        flushTimerRef.current = null;
      }
    };
  }, []);

  // ── Derived ────────────────────────────────────────────────────────────────

  const jobOptions = useMemo<Array<{ id: string; label: string }>>(() => {
    if (jobs.length > 0) {
      return jobs.map((j) => ({
        id: j.id,
        label: j.job_code
          ? `${j.job_code} — ${j.job_name}`
          : j.job_name || j.id,
      }));
    }
    return [{ id: "test-job", label: "test-job" }];
  }, [jobs]);

  const shortSessionId = useMemo(() => {
    if (!sessionId) return "—";
    return sessionId.length <= 8 ? sessionId : sessionId.slice(0, 8);
  }, [sessionId]);

  const selectedJobOption = useMemo(
    () => jobOptions.find((opt) => opt.id === form.jobId) ?? null,
    [jobOptions, form.jobId],
  );

  const selectedJobLabel = selectedJobOption
    ? selectedJobOption.label
    : form.jobId || "—";

  // Phase 2D: pull the actual Job payload (not the trimmed option) so we can
  // read route_count. Falls back to null when:
  //   - no job is selected
  //   - the selected option is the synthetic "test-job" fallback used when
  //     the jobs API failed/returned empty (no real Job record behind it)
  const selectedJob = useMemo<Job | null>(
    () => jobs.find((j) => j.id === form.jobId) ?? null,
    [jobs, form.jobId],
  );

  const routeContext: RouteContextState = useMemo(() => {
    if (!hydrated) return "unknown";
    if (!form.jobId) return "unknown";
    if (!selectedJob) return "unknown"; // fallback option, or job list still loading
    return selectedJob.route_count > 0 ? "available" : "missing";
  }, [hydrated, form.jobId, selectedJob]);

  // ── Handlers ───────────────────────────────────────────────────────────────

  const updateField = <K extends keyof WalkFormFields>(
    key: K,
    value: WalkFormFields[K],
  ): void => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const flushBreadcrumbs = useCallback(
    async (): Promise<number | null> => {
      if (flushInFlightRef.current) return null;
      const pending = pendingPointsRef.current;
      if (pending.length === 0) return serverPointCount;
      const sid = sessionIdRef.current;
      if (!sid) return null;
      const batch = pending.splice(0, pending.length);
      flushInFlightRef.current = true;
      try {
        const res = await postJson("/api/walk/breadcrumbs", {
          session_id: sid,
          points: batch,
        });
        if (!res.ok) {
          pendingPointsRef.current = [...batch, ...pendingPointsRef.current];
          setActionError(
            `Breadcrumb upload failed (${res.status}). Will retry.`,
          );
          return null;
        }
        const data = (await res.json()) as {
          success?: boolean;
          breadcrumb_count?: number;
          accepted?: number;
        };
        if (typeof data.breadcrumb_count === "number") {
          setServerPointCount(data.breadcrumb_count);
        }
        return data.breadcrumb_count ?? null;
      } catch (err) {
        pendingPointsRef.current = [...batch, ...pendingPointsRef.current];
        setActionError(
          err instanceof Error
            ? `Breadcrumb upload error: ${err.message}`
            : "Breadcrumb upload error.",
        );
        return null;
      } finally {
        flushInFlightRef.current = false;
      }
    },
    [serverPointCount],
  );

  const stopGpsWatch = useCallback(() => {
    if (watchIdRef.current !== null && typeof navigator !== "undefined") {
      try {
        navigator.geolocation.clearWatch(watchIdRef.current);
      } catch {
        /* ignore */
      }
      watchIdRef.current = null;
    }
    if (flushTimerRef.current !== null) {
      clearInterval(flushTimerRef.current);
      flushTimerRef.current = null;
    }
  }, []);

  const startGpsWatch = useCallback(() => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setGpsStatus("unsupported");
      return;
    }
    setGpsStatus("requesting");

    const onSuccess = (pos: GeolocationPosition) => {
      const { latitude, longitude, accuracy } = pos.coords;
      const accuracy_m = Number.isFinite(accuracy) ? accuracy : null;

      // Always tell the map where the user is, regardless of capture filters,
      // so the blue dot follows even when accuracy is poor or the user is
      // standing still.
      mapControllerRef.current?.setPosition(latitude, longitude);

      if (accuracy_m !== null && accuracy_m > ACCURACY_FILTER_M) {
        setGpsStatus("poor");
        setLatestPoint({ lat: latitude, lon: longitude, accuracy_m });
        return;
      }

      const last = lastAcceptedRef.current;
      if (
        last &&
        metersBetween(last.lat, last.lon, latitude, longitude) <
          MIN_POINT_SPACING_M
      ) {
        setGpsStatus(
          accuracy_m !== null && accuracy_m > POOR_ACCURACY_M
            ? "poor"
            : "active",
        );
        setLatestPoint({ lat: latitude, lon: longitude, accuracy_m });
        return;
      }

      const point: Breadcrumb = {
        lat: latitude,
        lon: longitude,
        accuracy_m,
        ts: new Date(pos.timestamp || Date.now()).toISOString(),
      };
      lastAcceptedRef.current = point;
      pendingPointsRef.current.push(point);

      // Append to the live polyline directly. No React state pathway — keeps
      // map rendering off the per-tick render budget.
      mapControllerRef.current?.appendBreadcrumb(latitude, longitude);

      setLatestPoint({ lat: latitude, lon: longitude, accuracy_m });
      setPointCount((c) => c + 1);
      setGpsStatus(
        accuracy_m !== null && accuracy_m > POOR_ACCURACY_M ? "poor" : "active",
      );
    };

    const onError = (err: GeolocationPositionError) => {
      if (err.code === err.PERMISSION_DENIED) {
        setGpsStatus("denied");
      } else {
        setGpsStatus("error");
      }
    };

    try {
      const id = navigator.geolocation.watchPosition(onSuccess, onError, {
        enableHighAccuracy: true,
        maximumAge: 1000,
        timeout: 30000,
      });
      watchIdRef.current = id;
    } catch {
      setGpsStatus("error");
      return;
    }

    flushTimerRef.current = setInterval(() => {
      void flushBreadcrumbs();
    }, FLUSH_INTERVAL_MS);
  }, [flushBreadcrumbs]);

  // Phase 3B-A: revoke object URLs for every saved entry's photo and the
  // current draft photo, then clear the lists. Used by Start New Walk and
  // unmount cleanup so we never leak object URLs across walks.
  const revokeAllPhotoUrls = useCallback(
    (entries: StationEntry[], draft: EntryPhoto | null) => {
      for (const entry of entries) {
        safeRevokeObjectUrl(entry.photo?.object_url);
      }
      safeRevokeObjectUrl(draft?.object_url);
    },
    [],
  );

  // Use refs to give the unmount cleanup the latest entries+draft without
  // adding them to a useEffect dep array (which would re-run cleanup on
  // every save).
  const stationEntriesRef = useRef<StationEntry[]>([]);
  const photoDraftRef = useRef<EntryPhoto | null>(null);
  useEffect(() => {
    stationEntriesRef.current = stationEntries;
  }, [stationEntries]);
  useEffect(() => {
    photoDraftRef.current = photoDraft;
  }, [photoDraft]);

  useEffect(() => {
    return () => {
      revokeAllPhotoUrls(stationEntriesRef.current, photoDraftRef.current);
    };
  }, [revokeAllPhotoUrls]);

  const handleStart = useCallback(async () => {
    if (isStarting) return;
    setIsStarting(true);
    try {
      setActionError(null);
      setEndSummary(null);
      const sid = sessionIdRef.current;
      if (!sid) {
        setActionError("Session not ready. Please refresh.");
        return;
      }
      try {
        const res = await postJson("/api/walk/start", {
          session_id: sid,
          job_id: form.jobId,
          job_label: selectedJobOption?.label ?? form.jobId,
          crew: form.crew,
          date: form.date,
          section: form.section,
        });
        if (!res.ok) {
          setActionError(`Start Walk failed (${res.status}).`);
          return;
        }
      } catch (err) {
        setActionError(
          err instanceof Error
            ? `Could not start walk: ${err.message}`
            : "Could not start walk.",
        );
        return;
      }

      pendingPointsRef.current = [];
      lastAcceptedRef.current = null;
      setLatestPoint(null);
      setPointCount(0);
      setServerPointCount(0);
      setSentHome(false);

      // Phase 3A + 3B-A: a fresh walk starts with a fresh entry list and a
      // clean entry-form state. Revoke any object URLs the previous walk
      // left behind so we don't leak browser memory across walks.
      revokeAllPhotoUrls(stationEntriesRef.current, photoDraftRef.current);
      setStationEntries([]);
      setEntryFormOpen(false);
      setEntryDraft({ station_number: "", depth_ft: "", boc_ft: "" });
      setEntryError(null);
      setPhotoDraft(null);
      if (photoInputRef.current) {
        photoInputRef.current.value = "";
      }

      // Wipe any previous trail so a re-Start doesn't visually merge walks.
      mapControllerRef.current?.resetTrail();

      setStatus("walking");
      startGpsWatch();
    } finally {
      setIsStarting(false);
    }
  }, [
    form.crew,
    form.date,
    form.jobId,
    form.section,
    isStarting,
    revokeAllPhotoUrls,
    selectedJobOption?.label,
    startGpsWatch,
  ]);

  const handleEnd = useCallback(async () => {
    if (isEnding) return;
    setIsEnding(true);
    try {
      stopGpsWatch();
      await flushBreadcrumbs();

      const sid = sessionIdRef.current;
      if (!sid) {
        setActionError("Session not ready.");
        setStatus("ended");
        return;
      }
      try {
        const res = await postJson("/api/walk/end", { session_id: sid });
        if (!res.ok) {
          setActionError(`End Walk failed (${res.status}).`);
          setStatus("ended");
          return;
        }
        const data = (await res.json()) as {
          success?: boolean;
          breadcrumb_count?: number;
          station_event_count?: number;
        };
        setEndSummary({
          breadcrumb_count:
            typeof data.breadcrumb_count === "number"
              ? data.breadcrumb_count
              : serverPointCount,
          station_event_count:
            typeof data.station_event_count === "number"
              ? data.station_event_count
              : 0,
          last_accuracy_m: latestPoint?.accuracy_m ?? null,
          gps_status: gpsStatus,
        });
      } catch (err) {
        setActionError(
          err instanceof Error
            ? `End Walk error: ${err.message}`
            : "End Walk error.",
        );
      } finally {
        setStatus("ended");
        // Close any open entry form on End Walk so the user lands on a
        // clean ended view. Drop any unsaved photo draft (revoke its URL).
        setEntryFormOpen(false);
        if (photoDraftRef.current) {
          safeRevokeObjectUrl(photoDraftRef.current.object_url);
          setPhotoDraft(null);
          if (photoInputRef.current) {
            photoInputRef.current.value = "";
          }
        }
      }
    } catch (err) {
      setActionError(
        err instanceof Error
          ? `End Walk error: ${err.message}`
          : "End Walk error.",
      );
    } finally {
      setIsEnding(false);
    }
  }, [
    flushBreadcrumbs,
    gpsStatus,
    isEnding,
    latestPoint?.accuracy_m,
    serverPointCount,
    stopGpsWatch,
  ]);

  const handleSendHome = (): void => {
    if (status !== "ended" || isSending) return;
    setIsSending(true);
    try {
      setSentHome(true);
    } finally {
      setIsSending(false);
    }
  };

  // Phase 3A + 3B-A: station entry form open/close + save.

  const openEntryForm = useCallback(() => {
    setEntryError(null);
    setEntryDraft({ station_number: "", depth_ft: "", boc_ft: "" });
    // Drop any prior photo draft on (re)open so opening a fresh form never
    // inherits a stale selection.
    if (photoDraftRef.current) {
      safeRevokeObjectUrl(photoDraftRef.current.object_url);
    }
    setPhotoDraft(null);
    if (photoInputRef.current) {
      photoInputRef.current.value = "";
    }
    setEntryFormOpen(true);
  }, []);

  const closeEntryForm = useCallback(() => {
    if (photoDraftRef.current) {
      safeRevokeObjectUrl(photoDraftRef.current.object_url);
    }
    setPhotoDraft(null);
    if (photoInputRef.current) {
      photoInputRef.current.value = "";
    }
    setEntryFormOpen(false);
    setEntryError(null);
  }, []);

  const handlePhotoSelected = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      // User cancelled the file picker — files is empty and we should leave
      // any existing draft as-is rather than wiping it.
      const file = event.target.files?.[0];
      if (!file) return;

      // Defend against absurd inputs early (camera-default JPEGs are usually
      // 2-6MB; we cap at 25MB so accidental video selection is rejected).
      if (file.size > PHOTO_MAX_BYTES) {
        setEntryError(
          `Photo is too large (${formatBytes(file.size)}). Max ${formatBytes(
            PHOTO_MAX_BYTES,
          )}.`,
        );
        // Reset input so the same too-big file can be re-tried after the
        // user picks something smaller.
        event.target.value = "";
        return;
      }

      // Replace any prior draft photo and revoke its URL.
      if (photoDraftRef.current) {
        safeRevokeObjectUrl(photoDraftRef.current.object_url);
      }

      let object_url = "";
      try {
        object_url = URL.createObjectURL(file);
      } catch {
        setEntryError("Could not create preview for that photo.");
        event.target.value = "";
        return;
      }

      setEntryError(null);
      setPhotoDraft({
        file,
        filename: file.name || "photo",
        size_bytes: file.size,
        mime_type: file.type || "image/*",
        object_url,
      });
    },
    [],
  );

  const clearPhotoDraft = useCallback(() => {
    if (photoDraftRef.current) {
      safeRevokeObjectUrl(photoDraftRef.current.object_url);
    }
    setPhotoDraft(null);
    if (photoInputRef.current) {
      photoInputRef.current.value = "";
    }
  }, []);

  const saveEntry = useCallback(() => {
    const stationNumber = entryDraft.station_number.trim();
    const depthRaw = entryDraft.depth_ft.trim();
    const bocRaw = entryDraft.boc_ft.trim();

    if (!stationNumber) {
      setEntryError("Station # is required.");
      return;
    }
    if (!depthRaw) {
      setEntryError("Depth (ft) is required.");
      return;
    }
    if (!bocRaw) {
      setEntryError("BOC (ft) is required.");
      return;
    }

    const depth = Number(depthRaw);
    const boc = Number(bocRaw);
    if (!Number.isFinite(depth)) {
      setEntryError("Depth (ft) must be a number.");
      return;
    }
    if (!Number.isFinite(boc)) {
      setEntryError("BOC (ft) must be a number.");
      return;
    }

    const point = latestPointRef.current;
    if (!point) {
      setEntryError(
        "No GPS fix yet — wait for the GPS card to show coordinates.",
      );
      return;
    }

    const entry: StationEntry = {
      id: newEntryId(),
      station_number: stationNumber,
      depth_ft: depth,
      boc_ft: boc,
      lat: point.lat,
      lon: point.lon,
      accuracy_m: point.accuracy_m,
      ts: new Date().toISOString(),
      // Hand off the draft photo (its object URL belongs to the entry now;
      // we do NOT revoke it here — it will be revoked on Start New Walk or
      // unmount).
      photo: photoDraft,
    };

    setStationEntries((prev) => [...prev, entry]);
    setEntryFormOpen(false);
    setEntryError(null);
    setEntryDraft({ station_number: "", depth_ft: "", boc_ft: "" });
    // Photo ownership transferred — clear the draft slot without revoking.
    setPhotoDraft(null);
    if (photoInputRef.current) {
      photoInputRef.current.value = "";
    }
  }, [entryDraft, photoDraft]);

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/* Map sits at the top of the page as the dominant visual layer.
          Stays mounted across the whole walk lifecycle so we never tear
          down/rebuild Leaflet — that would cause flicker and lose the
          breadcrumb trail.

          height is a portion of the viewport so on a phone the map is
          dominant but the controls are still reachable with one scroll. */}
      <div className="h-[55vh] w-full bg-slate-900">
        <MapPanel
          controllerRef={mapControllerRef}
          onAvailabilityChange={setMapAvailable}
        />
      </div>

      <div className="mx-auto flex w-full max-w-md flex-col gap-5 px-4 pb-10 pt-4">
        <header className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold tracking-tight">
            Walk Verification
          </h1>
          <p className="text-sm text-slate-400">
            Field entry shell — Phase 2B (live map)
          </p>
        </header>

        <section
          aria-label="Walk status"
          className="rounded-xl border border-slate-800 bg-slate-900/70 p-4"
        >
          <dl className="grid grid-cols-3 gap-3 text-xs">
            <div className="flex flex-col gap-1">
              <dt className="uppercase tracking-wide text-slate-500">
                Session
              </dt>
              <dd className="font-mono text-sm text-slate-200">
                {hydrated ? shortSessionId : "—"}
              </dd>
            </div>
            <div className="flex flex-col gap-1">
              <dt className="uppercase tracking-wide text-slate-500">Job</dt>
              <dd className="truncate text-sm text-slate-200">
                {hydrated ? selectedJobLabel : "—"}
              </dd>
            </div>
            <div className="flex flex-col gap-1">
              <dt className="uppercase tracking-wide text-slate-500">
                Status
              </dt>
              <dd>
                <StatusBadge status={status} sentHome={sentHome} />
              </dd>
            </div>
          </dl>
        </section>

        {/* Phase 2D: route context banner. Informational only — does not
            block Start Walk. Hidden when no job is selected or when we
            cannot read a Job payload (offline fallback option). */}
        <RouteContextBanner state={routeContext} />

        {(status === "walking" || status === "ended") && (
          <section
            aria-label="GPS status"
            className="rounded-xl border border-slate-800 bg-slate-900/70 p-4"
          >
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
                GPS
              </h2>
              <GpsBadge status={gpsStatus} />
            </div>
            <dl className="mt-3 grid grid-cols-2 gap-3 text-xs">
              <div className="flex flex-col gap-1">
                <dt className="uppercase tracking-wide text-slate-500">
                  Accuracy
                </dt>
                <dd className="text-sm text-slate-200">
                  {latestPoint && latestPoint.accuracy_m !== null
                    ? `${latestPoint.accuracy_m.toFixed(0)} m`
                    : "—"}
                </dd>
              </div>
              <div className="flex flex-col gap-1">
                <dt className="uppercase tracking-wide text-slate-500">
                  Points (local)
                </dt>
                <dd className="text-sm text-slate-200">{pointCount}</dd>
              </div>
              <div className="col-span-2 flex flex-col gap-1">
                <dt className="uppercase tracking-wide text-slate-500">
                  Last coordinate
                </dt>
                <dd className="font-mono text-sm text-slate-200">
                  {latestPoint
                    ? `${latestPoint.lat.toFixed(5)}, ${latestPoint.lon.toFixed(5)}`
                    : "—"}
                </dd>
              </div>
              <div className="col-span-2 flex flex-col gap-1">
                <dt className="uppercase tracking-wide text-slate-500">
                  Synced points
                </dt>
                <dd className="text-sm text-slate-200">{serverPointCount}</dd>
              </div>
            </dl>
            {gpsStatus === "denied" && (
              <p className="mt-3 text-xs text-amber-400">
                GPS permission was denied. Re-enable location for this site in
                your browser settings to capture breadcrumbs.
              </p>
            )}
            {gpsStatus === "unsupported" && (
              <p className="mt-3 text-xs text-amber-400">
                This browser does not expose geolocation. Open /walk in a
                browser that supports it.
              </p>
            )}
            {!mapAvailable && (
              <p className="mt-3 text-xs text-amber-400">
                Map unavailable — GPS tracking and breadcrumb capture still
                work.
              </p>
            )}
          </section>
        )}

        {/* Phase 3A + 3B-A: station entries panel. Visible during a walk
            and after it ends so the user can see what they captured.
            Local-only — entries are not yet sent to backend. */}
        {(status === "walking" || status === "ended") && (
          <section
            aria-label="Station entries"
            className="rounded-xl border border-slate-800 bg-slate-900/70 p-4"
          >
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
                Station Entries
              </h2>
              <span className="inline-flex items-center rounded-md bg-slate-700/40 px-2 py-1 text-xs font-medium text-slate-200 ring-1 ring-inset ring-slate-600/40">
                Entries: {stationEntries.length}
              </span>
            </div>

            {status === "walking" && !entryFormOpen && (
              <div className="mt-3">
                <BigButton variant="muted" onClick={openEntryForm}>
                  + Add Entry
                </BigButton>
              </div>
            )}

            {status === "walking" && entryFormOpen && (
              <div className="mt-3 flex flex-col gap-3 rounded-lg border border-slate-700 bg-slate-950/60 p-3">
                <Field label="Station #" htmlFor="entry-station">
                  <input
                    id="entry-station"
                    type="text"
                    inputMode="text"
                    autoComplete="off"
                    placeholder="e.g. 100+00"
                    value={entryDraft.station_number}
                    onChange={(e) =>
                      setEntryDraft((d) => ({
                        ...d,
                        station_number: e.target.value,
                      }))
                    }
                    className="h-12 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 text-base text-slate-100 placeholder:text-slate-500 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-500"
                  />
                </Field>
                <Field label="Depth (ft)" htmlFor="entry-depth">
                  <input
                    id="entry-depth"
                    type="number"
                    inputMode="decimal"
                    step="0.1"
                    placeholder="e.g. 4.5"
                    value={entryDraft.depth_ft}
                    onChange={(e) =>
                      setEntryDraft((d) => ({
                        ...d,
                        depth_ft: e.target.value,
                      }))
                    }
                    className="h-12 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 text-base text-slate-100 placeholder:text-slate-500 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-500"
                  />
                </Field>
                <Field label="BOC (ft)" htmlFor="entry-boc">
                  <input
                    id="entry-boc"
                    type="number"
                    inputMode="decimal"
                    step="0.1"
                    placeholder="e.g. 2.0"
                    value={entryDraft.boc_ft}
                    onChange={(e) =>
                      setEntryDraft((d) => ({
                        ...d,
                        boc_ft: e.target.value,
                      }))
                    }
                    className="h-12 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 text-base text-slate-100 placeholder:text-slate-500 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-500"
                  />
                </Field>

                {/* Phase 3B-A: optional single-photo attachment. */}
                <div className="flex flex-col gap-2">
                  <label
                    htmlFor="entry-photo"
                    className="text-xs font-medium uppercase tracking-wide text-slate-400"
                  >
                    Photo (optional)
                  </label>
                  <input
                    ref={photoInputRef}
                    id="entry-photo"
                    type="file"
                    accept="image/*"
                    capture="environment"
                    onChange={handlePhotoSelected}
                    className="block w-full text-sm text-slate-300 file:mr-3 file:rounded-md file:border-0 file:bg-slate-800 file:px-3 file:py-2 file:text-sm file:font-medium file:text-slate-100 hover:file:bg-slate-700"
                  />
                  {photoDraft && (
                    <div className="flex items-center gap-3 rounded-lg border border-slate-700 bg-slate-900/60 p-2">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={photoDraft.object_url}
                        alt="Selected photo preview"
                        className="h-16 w-16 flex-none rounded-md object-cover"
                      />
                      <div className="min-w-0 flex-1 text-xs">
                        <div className="truncate text-slate-200">
                          {photoDraft.filename}
                        </div>
                        <div className="text-slate-500">
                          {formatBytes(photoDraft.size_bytes)}
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={clearPhotoDraft}
                        className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
                      >
                        Remove
                      </button>
                    </div>
                  )}
                </div>

                {entryError && (
                  <div
                    role="alert"
                    className="rounded-lg border border-rose-800/60 bg-rose-900/30 p-2 text-xs text-rose-200"
                  >
                    {entryError}
                  </div>
                )}

                {!latestPoint && !entryError && (
                  <p className="text-xs text-amber-400">
                    Waiting for first GPS fix before this entry can be saved.
                  </p>
                )}

                <div className="flex gap-2">
                  <BigButton variant="primary" onClick={saveEntry}>
                    Save Entry
                  </BigButton>
                  <BigButton variant="muted" onClick={closeEntryForm}>
                    Cancel
                  </BigButton>
                </div>
              </div>
            )}
          </section>
        )}

        {status === "ended" && endSummary && (
          <section
            aria-label="Walk summary"
            className="rounded-xl border border-emerald-800/60 bg-emerald-900/20 p-4"
          >
            <h2 className="text-sm font-semibold uppercase tracking-wide text-emerald-300">
              Walk ended
            </h2>
            <dl className="mt-3 grid grid-cols-2 gap-3 text-xs">
              <div className="flex flex-col gap-1">
                <dt className="uppercase tracking-wide text-emerald-400/80">
                  Breadcrumbs
                </dt>
                <dd className="text-base text-emerald-100">
                  {endSummary.breadcrumb_count}
                </dd>
              </div>
              <div className="flex flex-col gap-1">
                <dt className="uppercase tracking-wide text-emerald-400/80">
                  Last accuracy
                </dt>
                <dd className="text-base text-emerald-100">
                  {endSummary.last_accuracy_m !== null
                    ? `${endSummary.last_accuracy_m.toFixed(0)} m`
                    : "—"}
                </dd>
              </div>
              <div className="col-span-2 flex flex-col gap-1">
                <dt className="uppercase tracking-wide text-emerald-400/80">
                  GPS status at end
                </dt>
                <dd className="text-sm text-emerald-100">
                  {GPS_STATUS_LABELS[endSummary.gps_status]}
                </dd>
              </div>
            </dl>
          </section>
        )}

        {actionError && (
          <div
            role="alert"
            className="rounded-xl border border-rose-800/60 bg-rose-900/30 p-3 text-sm text-rose-200"
          >
            {actionError}
          </div>
        )}

        <section
          aria-label="Walk header fields"
          className="flex flex-col gap-4 rounded-xl border border-slate-800 bg-slate-900/40 p-4"
        >
          <Field label="Job" htmlFor="walk-job">
            <select
              id="walk-job"
              value={form.jobId}
              onChange={(e) => updateField("jobId", e.target.value)}
              disabled={!hydrated || jobsLoading || status === "walking"}
              className="h-14 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 text-base text-slate-100 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-500 disabled:opacity-60"
            >
              <option value="">
                {jobsLoading ? "Loading jobs…" : "Select a job"}
              </option>
              {jobOptions.map((opt) => (
                <option key={opt.id} value={opt.id}>
                  {opt.label}
                </option>
              ))}
            </select>
            {jobsError ? (
              <p className="mt-1 text-xs text-amber-400">
                Could not reach jobs API — using fallback option.
              </p>
            ) : null}
          </Field>

          <Field label="Crew" htmlFor="walk-crew">
            <input
              id="walk-crew"
              type="text"
              inputMode="text"
              autoComplete="off"
              placeholder="Crew name"
              value={form.crew}
              onChange={(e) => updateField("crew", e.target.value)}
              disabled={status === "walking"}
              className="h-14 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 text-base text-slate-100 placeholder:text-slate-500 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-500 disabled:opacity-60"
            />
          </Field>

          <Field label="Date" htmlFor="walk-date">
            <input
              id="walk-date"
              type="date"
              value={form.date}
              onChange={(e) => updateField("date", e.target.value)}
              disabled={status === "walking"}
              className="h-14 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 text-base text-slate-100 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-500 disabled:opacity-60"
            />
          </Field>

          <Field label="Section / Segment" htmlFor="walk-section">
            <input
              id="walk-section"
              type="text"
              inputMode="text"
              autoComplete="off"
              placeholder="e.g. STA 100+00 — STA 110+00"
              value={form.section}
              onChange={(e) => updateField("section", e.target.value)}
              disabled={status === "walking"}
              className="h-14 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 text-base text-slate-100 placeholder:text-slate-500 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-500 disabled:opacity-60"
            />
          </Field>
        </section>

        <section aria-label="Walk actions" className="flex flex-col gap-3">
          {status === "not_started" && (
            <BigButton
              variant="primary"
              onClick={() => void handleStart()}
              disabled={isStarting}
            >
              {isStarting ? "Starting Walk…" : "Start Walk"}
            </BigButton>
          )}

          {status === "walking" && (
            <BigButton
              variant="danger"
              onClick={() => void handleEnd()}
              disabled={isEnding}
            >
              {isEnding ? "Ending Walk…" : "End Walk"}
            </BigButton>
          )}

          {status === "ended" && (
            <>
              <BigButton
                variant="muted"
                onClick={() => void handleStart()}
                disabled={isStarting}
              >
                {isStarting ? "Starting Walk…" : "Start New Walk"}
              </BigButton>
              <BigButton
                variant="primary"
                onClick={handleSendHome}
                disabled={status !== "ended" || sentHome || isSending}
              >
                {isSending ? "Sending Home…" : sentHome ? "Sent Home ✓" : "Send Home"}
              </BigButton>
            </>
          )}

          {status !== "ended" && (
            <BigButton variant="muted" onClick={handleSendHome} disabled>
              Send Home
            </BigButton>
          )}
        </section>

        <footer className="pt-2 text-center text-xs text-slate-500">
          Phase 2B — live map. No photos or station entry yet.
        </footer>
      </div>
    </div>
  );
}

// ─── Map panel ────────────────────────────────────────────────────────────────
// Mounts a Leaflet map into a div and hands a controller back to the parent
// via the supplied ref. Self-contained: if Leaflet fails to load or init,
// renders a fallback message and tells the parent so the parent can surface
// "Map unavailable" without breaking the rest of the page.

function MapPanel({
  controllerRef,
  onAvailabilityChange,
}: {
  controllerRef: React.MutableRefObject<MapController | null>;
  onAvailabilityChange: (available: boolean) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [failed, setFailed] = useState<boolean>(false);

  useEffect(() => {
    let cancelled = false;
    const controller = createMapController();
    controllerRef.current = controller;

    const node = containerRef.current;
    if (!node) {
      onAvailabilityChange(false);
      setFailed(true);
      return;
    }

    void controller.init(node).then((ok) => {
      if (cancelled) return;
      if (!ok) {
        setFailed(true);
        onAvailabilityChange(false);
        controllerRef.current = null;
      } else {
        onAvailabilityChange(true);
      }
    });

    return () => {
      cancelled = true;
      try {
        controller.destroy();
      } catch {
        /* ignore */
      }
      if (controllerRef.current === controller) {
        controllerRef.current = null;
      }
    };
    // controllerRef and onAvailabilityChange are stable references from the
    // parent; we intentionally run this effect once on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" />
      {failed && (
        <div className="absolute inset-0 flex items-center justify-center bg-slate-900/80 px-6 text-center text-sm text-slate-300">
          Map unavailable on this device. GPS tracking still works below.
        </div>
      )}
    </div>
  );
}

// ─── Local primitives ─────────────────────────────────────────────────────────

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2">
      <label
        htmlFor={htmlFor}
        className="text-xs font-medium uppercase tracking-wide text-slate-400"
      >
        {label}
      </label>
      {children}
    </div>
  );
}

function StatusBadge({
  status,
  sentHome,
}: {
  status: WalkStatus;
  sentHome: boolean;
}) {
  if (sentHome) {
    return (
      <span className="inline-flex items-center rounded-md bg-emerald-500/15 px-2 py-1 text-xs font-medium text-emerald-300 ring-1 ring-inset ring-emerald-500/30">
        Sent Home
      </span>
    );
  }
  const styles: Record<WalkStatus, string> = {
    not_started: "bg-slate-500/15 text-slate-300 ring-slate-500/30",
    walking: "bg-sky-500/15 text-sky-300 ring-sky-500/40",
    ended: "bg-amber-500/15 text-amber-300 ring-amber-500/40",
  };
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-1 text-xs font-medium ring-1 ring-inset ${styles[status]}`}
    >
      {STATUS_LABELS[status]}
    </span>
  );
}

function GpsBadge({ status }: { status: GpsStatus }) {
  const styles: Record<GpsStatus, string> = {
    idle: "bg-slate-500/15 text-slate-300 ring-slate-500/30",
    requesting: "bg-sky-500/15 text-sky-300 ring-sky-500/40",
    active: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/40",
    poor: "bg-amber-500/15 text-amber-300 ring-amber-500/40",
    denied: "bg-rose-500/15 text-rose-300 ring-rose-500/40",
    error: "bg-rose-500/15 text-rose-300 ring-rose-500/40",
    unsupported: "bg-rose-500/15 text-rose-300 ring-rose-500/40",
  };
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-1 text-xs font-medium ring-1 ring-inset ${styles[status]}`}
    >
      {GPS_STATUS_LABELS[status]}
    </span>
  );
}

function RouteContextBanner({ state }: { state: RouteContextState }) {
  if (state === "unknown") return null;
  if (state === "available") {
    return (
      <div
        role="status"
        className="rounded-xl border border-emerald-800/60 bg-emerald-900/20 px-4 py-3 text-sm text-emerald-200"
      >
        Route context available for this job.
      </div>
    );
  }
  // missing
  return (
    <div
      role="status"
      className="rounded-xl border border-amber-700/60 bg-amber-900/20 px-4 py-3 text-sm text-amber-200"
    >
      No route/design loaded for this job yet. Office must upload the KMZ
      before field walking.
    </div>
  );
}

function BigButton({
  variant,
  onClick,
  disabled,
  children,
}: {
  variant: "primary" | "danger" | "muted";
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  const base =
    "flex min-h-[60px] w-full items-center justify-center rounded-xl px-5 py-4 text-base font-semibold transition-colors active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-50";
  const variants: Record<"primary" | "danger" | "muted", string> = {
    primary:
      "bg-sky-500 text-white hover:bg-sky-400 disabled:hover:bg-sky-500",
    danger:
      "bg-rose-500 text-white hover:bg-rose-400 disabled:hover:bg-rose-500",
    muted:
      "border border-slate-700 bg-slate-900 text-slate-200 hover:bg-slate-800 disabled:hover:bg-slate-900",
  };
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`${base} ${variants[variant]}`}
    >
      {children}
    </button>
  );
}
