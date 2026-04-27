"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { getJobs, type Job } from "@/lib/api";
import { getOrCreateSessionId } from "@/lib/session";

// ─── Configuration ────────────────────────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

// Versioned localStorage key for header form. Schema bump → new key, no
// collision with old saved state.
const FORM_STORAGE_KEY = "osp_walk_form_v1";

// Drop GPS fixes worse than this. Spec: 75m.
const ACCURACY_FILTER_M = 75;

// Don't accept a new point if it's within this distance of the previous
// accepted point. Cheap dedup so a phone sitting still doesn't fill the
// breadcrumb list.
const MIN_POINT_SPACING_M = 3;

// Threshold above which we surface the "poor accuracy" state to the user
// (still captured, but flagged in the UI).
const POOR_ACCURACY_M = 30;

// Periodic flush cadence while walking, plus on End Walk.
const FLUSH_INTERVAL_MS = 10000;

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

const STATUS_LABELS: Record<WalkStatus, string> = {
  not_started: "Not Started",
  walking: "Walking",
  ended: "Ended",
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

// ─── Helpers ──────────────────────────────────────────────────────────────────

function todayIso(): string {
  // YYYY-MM-DD in local time so the field matches the user's wall date.
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
  // Equirectangular approximation. Good enough at the breadcrumb scale.
  const R = 6371000; // meters
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
    // Storage unavailable (private mode, quota). Silent fail is OK — the
    // user just loses persistence for the current session.
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

  // GPS / breadcrumb state surfaced to the UI.
  const [gpsStatus, setGpsStatus] = useState<GpsStatus>("idle");
  const [latestPoint, setLatestPoint] = useState<LatestPoint | null>(null);
  const [pointCount, setPointCount] = useState<number>(0);
  const [serverPointCount, setServerPointCount] = useState<number>(0);

  const [actionError, setActionError] = useState<string | null>(null);
  const [endSummary, setEndSummary] = useState<EndSummary | null>(null);

  // Refs for things that change quickly and shouldn't trigger re-renders, or
  // that need to survive across renders without state churn:
  //  - the geolocation watch handle (so we can stop it cleanly)
  //  - the unflushed breadcrumb buffer (mutated from inside the GPS callback)
  //  - the last accepted point (for spacing dedup, also without re-rendering)
  //  - the periodic flush timer
  //  - the "are we currently flushing" guard (prevents overlapping POSTs)
  const watchIdRef = useRef<number | null>(null);
  const pendingPointsRef = useRef<Breadcrumb[]>([]);
  const lastAcceptedRef = useRef<Breadcrumb | null>(null);
  const flushTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const flushInFlightRef = useRef<boolean>(false);
  const sessionIdRef = useRef<string | null>(null);

  // Keep a ref mirror of sessionId so async callbacks always see the latest.
  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  // ── Lifecycle: hydrate form + session ──────────────────────────────────────

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

  // Cleanup on unmount: stop watcher, clear timer.
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
    // Fallback so the page works with a flaky/offline backend.
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

  // ── Handlers ───────────────────────────────────────────────────────────────

  const updateField = <K extends keyof WalkFormFields>(
    key: K,
    value: WalkFormFields[K],
  ): void => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  // Flush pending breadcrumbs to the backend. Safe to call from anywhere;
  // returns the post-flush server count (or null on failure).
  const flushBreadcrumbs = useCallback(
    async (): Promise<number | null> => {
      if (flushInFlightRef.current) return null;
      const pending = pendingPointsRef.current;
      if (pending.length === 0) return serverPointCount;
      const sid = sessionIdRef.current;
      if (!sid) return null;
      // Take ownership of the pending buffer atomically — anything that
      // arrives during the POST goes into a fresh array.
      const batch = pending.splice(0, pending.length);
      flushInFlightRef.current = true;
      try {
        const res = await postJson("/api/walk/breadcrumbs", {
          session_id: sid,
          points: batch,
        });
        if (!res.ok) {
          // Restore the batch at the front so we retry next flush.
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
        // Network error — restore so we don't lose points.
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

      // Filter on accuracy floor.
      if (accuracy_m !== null && accuracy_m > ACCURACY_FILTER_M) {
        setGpsStatus("poor");
        // Still surface the latest reading so the user sees movement, but
        // don't add it to the captured stream.
        setLatestPoint({ lat: latitude, lon: longitude, accuracy_m });
        return;
      }

      // Spatial dedup against the previous accepted point.
      const last = lastAcceptedRef.current;
      if (
        last &&
        metersBetween(last.lat, last.lon, latitude, longitude) <
          MIN_POINT_SPACING_M
      ) {
        // Treat as a still-active reading; refresh the surface state but
        // don't capture.
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

    // Periodic flush while walking. Capture-by-closure of flushBreadcrumbs
    // is fine here — the function body is stable across calls thanks to
    // useCallback above.
    flushTimerRef.current = setInterval(() => {
      void flushBreadcrumbs();
    }, FLUSH_INTERVAL_MS);
  }, [flushBreadcrumbs]);

  const handleStart = useCallback(async () => {
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

    // Reset capture state for a fresh walk.
    pendingPointsRef.current = [];
    lastAcceptedRef.current = null;
    setLatestPoint(null);
    setPointCount(0);
    setServerPointCount(0);
    setSentHome(false);

    setStatus("walking");
    startGpsWatch();
  }, [
    form.crew,
    form.date,
    form.jobId,
    form.section,
    selectedJobOption?.label,
    startGpsWatch,
  ]);

  const handleEnd = useCallback(async () => {
    stopGpsWatch();
    // Final flush of anything still in the buffer.
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
    }
  }, [
    flushBreadcrumbs,
    gpsStatus,
    latestPoint?.accuracy_m,
    serverPointCount,
    stopGpsWatch,
  ]);

  const handleSendHome = (): void => {
    if (status !== "ended") return;
    setSentHome(true);
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto flex w-full max-w-md flex-col gap-5 px-4 pb-10 pt-6">
        {/* Header */}
        <header className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold tracking-tight">
            Walk Verification
          </h1>
          <p className="text-sm text-slate-400">
            Field entry shell — Phase 2A (GPS)
          </p>
        </header>

        {/* Status strip */}
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

        {/* GPS card — visible once a walk has started or ended */}
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
          </section>
        )}

        {/* End summary — visible once End Walk has completed */}
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

        {/* Error banner */}
        {actionError && (
          <div
            role="alert"
            className="rounded-xl border border-rose-800/60 bg-rose-900/30 p-3 text-sm text-rose-200"
          >
            {actionError}
          </div>
        )}

        {/* Form (locked once walk has started) */}
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

        {/* Action buttons */}
        <section aria-label="Walk actions" className="flex flex-col gap-3">
          {status === "not_started" && (
            <BigButton variant="primary" onClick={() => void handleStart()}>
              Start Walk
            </BigButton>
          )}

          {status === "walking" && (
            <BigButton variant="danger" onClick={() => void handleEnd()}>
              End Walk
            </BigButton>
          )}

          {status === "ended" && (
            <>
              <BigButton variant="muted" onClick={() => void handleStart()}>
                Start New Walk
              </BigButton>
              <BigButton
                variant="primary"
                onClick={handleSendHome}
                disabled={sentHome}
              >
                {sentHome ? "Sent Home ✓" : "Send Home"}
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
          Phase 2A — GPS + breadcrumbs. No map, photos, or station entry yet.
        </footer>
      </div>
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
