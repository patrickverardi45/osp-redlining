"use client";

// Mobile Walk V2 — clean field capture route. Standalone from /walk.
// Owns its own walk_session_id (minted per Start Walk), persists stations
// incrementally on Save Station, and uploads photos exactly once after
// the parent station save succeeds.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { getJobs, type Job } from "@/lib/api";
import {
  apiSaveStationEvent,
  apiUploadStationPhotos,
  apiWalkEnd,
  apiWalkStart,
  clearActiveWalk,
  loadActiveWalk,
  loadDraftForm,
  mintClientEventId,
  mintWalkSessionId,
  saveActiveWalk,
  saveDraftForm,
  type ActiveWalk,
} from "@/lib/walkV2";

const PHOTO_MAX_BYTES = 25 * 1024 * 1024;
const STATION_MAX_LENGTH = 7;

type GpsFix = {
  lat: number;
  lon: number;
  accuracyM: number | null;
  ts: number;
};

type SavedStation = {
  clientUuid: string;
  stationNumber: string;
  depthFt: number;
  bocFt: number;
  lat: number;
  lon: number;
  photoCount: number;
  savedAt: number;
};

type Status = { kind: "idle" | "info" | "ok" | "err"; text: string };

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function getOneShotFix(): Promise<GpsFix> {
  return new Promise((resolve, reject) => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      reject(new Error("Geolocation unavailable on this device."));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        resolve({
          lat: pos.coords.latitude,
          lon: pos.coords.longitude,
          accuracyM:
            typeof pos.coords.accuracy === "number" ? pos.coords.accuracy : null,
          ts: pos.timestamp || Date.now(),
        });
      },
      (err) => reject(new Error(err.message || "Could not get GPS fix.")),
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 15000 },
    );
  });
}

export default function WalkV2Page() {
  // ─── job catalog ─────────────────────────────────────────────────────────
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobsLoading, setJobsLoading] = useState(true);
  const [jobsError, setJobsError] = useState<string | null>(null);

  // ─── pre-walk form ───────────────────────────────────────────────────────
  const [jobId, setJobId] = useState<string>("");
  const [crew, setCrew] = useState<string>("");
  const [date, setDate] = useState<string>(todayIso());

  // ─── active walk ─────────────────────────────────────────────────────────
  const [active, setActive] = useState<ActiveWalk | null>(null);
  const [pendingResume, setPendingResume] = useState<ActiveWalk | null>(null);
  const [starting, setStarting] = useState(false);
  const [ending, setEnding] = useState(false);

  // ─── station capture state ───────────────────────────────────────────────
  const [stationNumber, setStationNumber] = useState<string>("");
  const [depthFt, setDepthFt] = useState<string>("");
  const [bocFt, setBocFt] = useState<string>("");
  const [note, setNote] = useState<string>("");
  const [pendingPhotos, setPendingPhotos] = useState<File[]>([]);
  const [savedStations, setSavedStations] = useState<SavedStation[]>([]);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<Status>({ kind: "idle", text: "" });
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // ─── boot: restore active walk + draft form ──────────────────────────────
  useEffect(() => {
    const draft = loadDraftForm();
    if (draft) {
      setJobId(draft.jobId || "");
      setCrew(draft.crew || "");
      setDate(draft.date || todayIso());
    }
    const existing = loadActiveWalk();
    if (existing) setPendingResume(existing);
  }, []);

  useEffect(() => {
    saveDraftForm({ jobId, jobLabel: "", crew, date });
  }, [jobId, crew, date]);

  // ─── load job catalog ────────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    setJobsLoading(true);
    getJobs()
      .then((rows) => {
        if (cancelled) return;
        setJobs(rows);
        setJobsError(null);
        if (!jobId && rows.length > 0) setJobId(rows[0].id);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setJobsError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setJobsLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedJob = useMemo(
    () => jobs.find((j) => j.id === jobId) || null,
    [jobs, jobId],
  );

  // ─── start walk ──────────────────────────────────────────────────────────
  const handleStartWalk = useCallback(async () => {
    if (!jobId) {
      setStatus({ kind: "err", text: "Pick a job first." });
      return;
    }
    if (!crew.trim()) {
      setStatus({ kind: "err", text: "Enter a crew name." });
      return;
    }
    setStarting(true);
    setStatus({ kind: "info", text: "Starting walk..." });
    try {
      const walkSessionId = mintWalkSessionId();
      const jobLabel = selectedJob?.job_name || jobId;
      const res = await apiWalkStart({
        walkSessionId,
        jobId,
        jobLabel,
        crew: crew.trim(),
        date,
      });
      const next: ActiveWalk = {
        walkSessionId: res.session_id || walkSessionId,
        jobId,
        jobLabel,
        crew: crew.trim(),
        date,
        startedAt: new Date().toISOString(),
      };
      setActive(next);
      saveActiveWalk(next);
      setSavedStations([]);
      setPendingResume(null);
      setStatus({
        kind: "ok",
        text: `Walk started. Session ${next.walkSessionId.slice(0, 16)}…`,
      });
    } catch (e) {
      setStatus({
        kind: "err",
        text: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setStarting(false);
    }
  }, [crew, date, jobId, selectedJob]);

  const handleResume = useCallback(() => {
    if (!pendingResume) return;
    setActive(pendingResume);
    setJobId(pendingResume.jobId);
    setCrew(pendingResume.crew);
    setDate(pendingResume.date);
    setPendingResume(null);
    setStatus({
      kind: "info",
      text: `Resumed walk ${pendingResume.walkSessionId.slice(0, 16)}…`,
    });
  }, [pendingResume]);

  const handleDiscardResume = useCallback(() => {
    clearActiveWalk();
    setPendingResume(null);
    setStatus({ kind: "info", text: "Previous walk discarded. Start a new one." });
  }, []);

  // ─── photo selection (no upload yet) ─────────────────────────────────────
  const handlePhotoChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const incoming = Array.from(e.target.files || []);
      const next: File[] = [];
      for (const f of incoming) {
        if (f.size > PHOTO_MAX_BYTES) {
          setStatus({ kind: "err", text: `${f.name} is too large.` });
          continue;
        }
        next.push(f);
      }
      setPendingPhotos((prev) => [...prev, ...next]);
      if (e.target) e.target.value = "";
    },
    [],
  );

  const removePendingPhoto = useCallback((idx: number) => {
    setPendingPhotos((prev) => prev.filter((_, i) => i !== idx));
  }, []);

  // ─── save station (then upload photos exactly once) ──────────────────────
  const handleSaveStation = useCallback(async () => {
    if (!active) {
      setStatus({ kind: "err", text: "No active walk." });
      return;
    }
    const trimmed = stationNumber.trim();
    if (!trimmed) {
      setStatus({ kind: "err", text: "Enter a station number." });
      return;
    }
    if (trimmed.length > STATION_MAX_LENGTH) {
      setStatus({
        kind: "err",
        text: `Station too long (max ${STATION_MAX_LENGTH} chars).`,
      });
      return;
    }
    const depth = Number(depthFt);
    const boc = Number(bocFt);
    if (!Number.isFinite(depth) || !Number.isFinite(boc)) {
      setStatus({ kind: "err", text: "Depth and BOC must be numbers." });
      return;
    }

    setSaving(true);
    setStatus({ kind: "info", text: "Getting GPS fix..." });
    try {
      const fix = await getOneShotFix();
      const clientUuid = mintClientEventId();

      setStatus({ kind: "info", text: "Saving station..." });
      await apiSaveStationEvent({
        walkSessionId: active.walkSessionId,
        event: {
          clientUuid,
          stationNumber: trimmed,
          depthFt: depth,
          bocFt: boc,
          lat: fix.lat,
          lon: fix.lon,
          accuracyM: fix.accuracyM,
          note: note.trim() || undefined,
          crew: active.crew,
          tsMs: fix.ts,
        },
      });

      let uploadedPhotos = 0;
      if (pendingPhotos.length > 0) {
        setStatus({
          kind: "info",
          text: `Uploading ${pendingPhotos.length} photo${pendingPhotos.length === 1 ? "" : "s"}...`,
        });
        const result = await apiUploadStationPhotos({
          walkSessionId: active.walkSessionId,
          jobId: active.jobId,
          stationNumber: trimmed,
          lat: fix.lat,
          lon: fix.lon,
          files: pendingPhotos,
          note: note.trim() || undefined,
        });
        uploadedPhotos = Array.isArray(result.photos) ? result.photos.length : 0;
      }

      setSavedStations((prev) => [
        ...prev,
        {
          clientUuid,
          stationNumber: trimmed,
          depthFt: depth,
          bocFt: boc,
          lat: fix.lat,
          lon: fix.lon,
          photoCount: uploadedPhotos,
          savedAt: Date.now(),
        },
      ]);
      setStationNumber("");
      setDepthFt("");
      setBocFt("");
      setNote("");
      setPendingPhotos([]);
      if (fileInputRef.current) fileInputRef.current.value = "";
      setStatus({
        kind: "ok",
        text: `Saved ${trimmed}${uploadedPhotos ? ` with ${uploadedPhotos} photo${uploadedPhotos === 1 ? "" : "s"}` : ""}.`,
      });
    } catch (e) {
      setStatus({
        kind: "err",
        text: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setSaving(false);
    }
  }, [active, bocFt, depthFt, note, pendingPhotos, stationNumber]);

  // ─── end walk ────────────────────────────────────────────────────────────
  const handleEndWalk = useCallback(async () => {
    if (!active) return;
    if (!confirm("End this walk? Stations are already saved server-side.")) return;
    setEnding(true);
    setStatus({ kind: "info", text: "Ending walk..." });
    try {
      const res = await apiWalkEnd(active.walkSessionId);
      clearActiveWalk();
      setActive(null);
      setStatus({
        kind: "ok",
        text: `Walk ended. ${res.station_event_count} station${res.station_event_count === 1 ? "" : "s"} synced.`,
      });
    } catch (e) {
      setStatus({
        kind: "err",
        text: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setEnding(false);
    }
  }, [active]);

  // ─── render ──────────────────────────────────────────────────────────────
  return (
    <main className="mx-auto max-w-md min-h-screen bg-slate-50 px-4 pb-24 pt-4 text-slate-900">
      <header className="mb-4">
        <div className="flex items-baseline justify-between">
          <h1 className="text-xl font-semibold">Walk V2</h1>
          <span className="text-xs uppercase tracking-wide text-slate-500">
            mobile field
          </span>
        </div>
        <p className="mt-1 text-sm text-slate-600">
          Field capture only. Each Start Walk creates a new session.
        </p>
      </header>

      {pendingResume && !active ? (
        <section className="mb-4 rounded-xl border border-amber-300 bg-amber-50 p-4">
          <div className="text-sm font-medium text-amber-900">
            Active walk found
          </div>
          <div className="mt-1 text-xs text-amber-800">
            Job <span className="font-mono">{pendingResume.jobId}</span> · Crew{" "}
            {pendingResume.crew} · Started{" "}
            {new Date(pendingResume.startedAt).toLocaleString()}
          </div>
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={handleResume}
              className="flex-1 rounded-lg bg-amber-600 px-3 py-2 text-sm font-medium text-white"
            >
              Resume
            </button>
            <button
              type="button"
              onClick={handleDiscardResume}
              className="flex-1 rounded-lg border border-amber-700 px-3 py-2 text-sm font-medium text-amber-900"
            >
              Discard & start new
            </button>
          </div>
        </section>
      ) : null}

      {!active ? (
        <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="text-sm font-semibold text-slate-700">Start a walk</h2>
          <div className="mt-3 space-y-3">
            <label className="block text-xs font-medium text-slate-600">
              Job
              <select
                className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-base"
                value={jobId}
                onChange={(e) => setJobId(e.target.value)}
                disabled={jobsLoading}
              >
                {jobsLoading ? (
                  <option value="">Loading jobs...</option>
                ) : jobs.length === 0 ? (
                  <option value="">No jobs found</option>
                ) : (
                  jobs.map((j) => (
                    <option key={j.id} value={j.id}>
                      {j.job_code} — {j.job_name}
                    </option>
                  ))
                )}
              </select>
            </label>
            {jobsError ? (
              <p className="text-xs text-red-700">{jobsError}</p>
            ) : null}

            <label className="block text-xs font-medium text-slate-600">
              Crew
              <input
                type="text"
                className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-base"
                placeholder="e.g. Crew A"
                value={crew}
                onChange={(e) => setCrew(e.target.value)}
              />
            </label>

            <label className="block text-xs font-medium text-slate-600">
              Date
              <input
                type="date"
                className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-base"
                value={date}
                onChange={(e) => setDate(e.target.value)}
              />
            </label>

            <button
              type="button"
              onClick={handleStartWalk}
              disabled={starting || !jobId}
              className="w-full rounded-lg bg-emerald-600 px-4 py-3 text-base font-semibold text-white disabled:bg-slate-400"
            >
              {starting ? "Starting..." : "Start Walk"}
            </button>
          </div>
        </section>
      ) : (
        <>
          <section className="rounded-xl border border-emerald-300 bg-emerald-50 p-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="font-medium text-emerald-900">Walk active</span>
              <span className="font-mono text-[10px] text-emerald-800">
                {active.walkSessionId}
              </span>
            </div>
            <div className="mt-1 text-xs text-emerald-900">
              Job <span className="font-mono">{active.jobId}</span> · {active.crew}{" "}
              · {active.date}
            </div>
          </section>

          <section className="mt-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <h2 className="text-sm font-semibold text-slate-700">Add Station</h2>
            <div className="mt-3 space-y-3">
              <label className="block text-xs font-medium text-slate-600">
                Station Number
                <input
                  type="text"
                  inputMode="text"
                  autoComplete="off"
                  maxLength={STATION_MAX_LENGTH}
                  placeholder="e.g. 01+00"
                  className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-base font-mono"
                  value={stationNumber}
                  onChange={(e) => setStationNumber(e.target.value)}
                />
              </label>

              <div className="grid grid-cols-2 gap-3">
                <label className="block text-xs font-medium text-slate-600">
                  Depth (ft)
                  <input
                    type="number"
                    inputMode="decimal"
                    step="0.1"
                    className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-base"
                    value={depthFt}
                    onChange={(e) => setDepthFt(e.target.value)}
                  />
                </label>
                <label className="block text-xs font-medium text-slate-600">
                  BOC (ft)
                  <input
                    type="number"
                    inputMode="decimal"
                    step="0.1"
                    className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-base"
                    value={bocFt}
                    onChange={(e) => setBocFt(e.target.value)}
                  />
                </label>
              </div>

              <label className="block text-xs font-medium text-slate-600">
                Note
                <input
                  type="text"
                  className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-base"
                  placeholder="optional"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                />
              </label>

              <div>
                <div className="text-xs font-medium text-slate-600">
                  Photos ({pendingPhotos.length})
                </div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  multiple
                  capture="environment"
                  onChange={handlePhotoChange}
                  className="mt-1 block w-full text-sm"
                />
                {pendingPhotos.length > 0 ? (
                  <ul className="mt-2 space-y-1">
                    {pendingPhotos.map((f, i) => (
                      <li
                        key={`${f.name}-${i}`}
                        className="flex items-center justify-between rounded border border-slate-200 px-2 py-1 text-xs"
                      >
                        <span className="truncate">{f.name}</span>
                        <button
                          type="button"
                          onClick={() => removePendingPhoto(i)}
                          className="text-red-600"
                        >
                          remove
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>

              <button
                type="button"
                onClick={handleSaveStation}
                disabled={saving}
                className="w-full rounded-lg bg-sky-600 px-4 py-3 text-base font-semibold text-white disabled:bg-slate-400"
              >
                {saving ? "Saving..." : "Save Station"}
              </button>
            </div>
          </section>

          <section className="mt-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-700">
                Saved this walk ({savedStations.length})
              </h2>
            </div>
            {savedStations.length === 0 ? (
              <p className="mt-2 text-xs text-slate-500">
                No stations saved yet.
              </p>
            ) : (
              <ul className="mt-2 divide-y divide-slate-100">
                {savedStations.map((s) => (
                  <li key={s.clientUuid} className="py-2 text-sm">
                    <div className="flex items-baseline justify-between">
                      <span className="font-mono font-medium">
                        {s.stationNumber}
                      </span>
                      <span className="text-xs text-slate-500">
                        {new Date(s.savedAt).toLocaleTimeString()}
                      </span>
                    </div>
                    <div className="text-xs text-slate-600">
                      depth {s.depthFt}ft · BOC {s.bocFt}ft · photos {s.photoCount}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="mt-4">
            <button
              type="button"
              onClick={handleEndWalk}
              disabled={ending}
              className="w-full rounded-lg border border-red-300 bg-white px-4 py-3 text-base font-semibold text-red-700 disabled:opacity-60"
            >
              {ending ? "Ending..." : "End Walk"}
            </button>
          </section>
        </>
      )}

      {status.text ? (
        <div
          className={[
            "fixed inset-x-0 bottom-0 mx-auto max-w-md px-4 pb-3",
            "pointer-events-none",
          ].join(" ")}
        >
          <div
            className={[
              "pointer-events-auto rounded-lg px-3 py-2 text-sm shadow",
              status.kind === "ok"
                ? "bg-emerald-600 text-white"
                : status.kind === "err"
                  ? "bg-red-600 text-white"
                  : status.kind === "info"
                    ? "bg-slate-800 text-white"
                    : "bg-slate-200 text-slate-800",
            ].join(" ")}
          >
            {status.text}
          </div>
        </div>
      ) : null}
    </main>
  );
}
