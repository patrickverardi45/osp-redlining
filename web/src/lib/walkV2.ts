// Walk V2 helpers. Intentionally standalone — does NOT import @/lib/session.
// The walk session id is minted fresh per Start Walk. Browser/local storage
// is used only for draft recovery (Resume vs Start New on reopen), never as
// the source of identity.

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

const ACTIVE_WALK_KEY = "osp_walk_v2_active_v1";
const DRAFT_FORM_KEY = "osp_walk_v2_form_v1";

export type ActiveWalk = {
  walkSessionId: string;
  jobId: string;
  jobLabel: string;
  crew: string;
  date: string;
  startedAt: string;
};

export type WalkV2DraftForm = {
  jobId: string;
  jobLabel: string;
  crew: string;
  date: string;
};

function canUseStorage(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function freshId(): string {
  if (typeof window !== "undefined" && typeof window.crypto?.randomUUID === "function") {
    return window.crypto.randomUUID().replace(/-/g, "");
  }
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`;
}

export function mintWalkSessionId(): string {
  return `walk-v2-${freshId()}`;
}

export function mintClientEventId(): string {
  return `evt-${freshId()}`;
}

export function loadActiveWalk(): ActiveWalk | null {
  if (!canUseStorage()) return null;
  try {
    const raw = window.localStorage.getItem(ACTIVE_WALK_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ActiveWalk;
    if (!parsed?.walkSessionId) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function saveActiveWalk(active: ActiveWalk): void {
  if (!canUseStorage()) return;
  window.localStorage.setItem(ACTIVE_WALK_KEY, JSON.stringify(active));
}

export function clearActiveWalk(): void {
  if (!canUseStorage()) return;
  window.localStorage.removeItem(ACTIVE_WALK_KEY);
}

export function loadDraftForm(): WalkV2DraftForm | null {
  if (!canUseStorage()) return null;
  try {
    const raw = window.localStorage.getItem(DRAFT_FORM_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as WalkV2DraftForm;
  } catch {
    return null;
  }
}

export function saveDraftForm(draft: WalkV2DraftForm): void {
  if (!canUseStorage()) return;
  window.localStorage.setItem(DRAFT_FORM_KEY, JSON.stringify(draft));
}

// ─── API wrappers ─────────────────────────────────────────────────────────

export type WalkStartResult = {
  ok: boolean;
  session_id: string;
  walk_active: boolean;
};

export async function apiWalkStart(args: {
  walkSessionId: string;
  jobId: string;
  jobLabel: string;
  crew: string;
  date: string;
}): Promise<WalkStartResult> {
  const res = await fetch(`${API_BASE}/api/walk/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: args.walkSessionId,
      job_id: args.jobId,
      job_label: args.jobLabel,
      crew: args.crew,
      date: args.date,
    }),
  });
  if (!res.ok) throw new Error(`Start walk failed: ${res.status} ${res.statusText}`);
  return res.json();
}

export type StationEventInput = {
  clientUuid: string;
  stationNumber: string;
  depthFt: number;
  bocFt: number;
  lat: number;
  lon: number;
  accuracyM?: number | null;
  note?: string;
  crew?: string;
  tsMs: number;
};

export async function apiSaveStationEvent(args: {
  walkSessionId: string;
  event: StationEventInput;
}): Promise<{ ok: boolean; count: number }> {
  const ev: Record<string, unknown> = {
    client_uuid: args.event.clientUuid,
    station_number: args.event.stationNumber,
    depth_ft: args.event.depthFt,
    boc_ft: args.event.bocFt,
    lat: args.event.lat,
    lon: args.event.lon,
    ts: args.event.tsMs,
  };
  if (args.event.accuracyM != null && Number.isFinite(args.event.accuracyM)) {
    ev.accuracy_m = args.event.accuracyM;
  }
  if (args.event.note) ev.note = args.event.note;
  if (args.event.crew) ev.crew = args.event.crew;

  const res = await fetch(`${API_BASE}/api/walk/station-events`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: args.walkSessionId, events: [ev] }),
  });
  if (!res.ok) throw new Error(`Save station failed: ${res.status} ${res.statusText}`);
  return res.json();
}

export async function apiUploadStationPhotos(args: {
  walkSessionId: string;
  jobId: string;
  stationNumber: string;
  lat: number;
  lon: number;
  files: File[];
  note?: string;
}): Promise<{ ok: boolean; photos: unknown[] }> {
  const SOURCE = "walk-v2";
  const stationLabel = args.stationNumber;
  const mappedFt = "";
  const latStr = String(args.lat);
  const lonStr = String(args.lon);
  const stationIdentity = [
    args.jobId || "",
    SOURCE,
    stationLabel,
    mappedFt,
    latStr,
    lonStr,
  ].join("|");

  const form = new FormData();
  form.append("station_identity", stationIdentity);
  form.append("session_id", args.walkSessionId);
  form.append("station_summary", args.note ? args.note.slice(0, 200) : stationLabel);
  form.append("route_name", args.jobId || "");
  form.append("source_file", SOURCE);
  form.append("station_label", stationLabel);
  form.append("mapped_station_ft", mappedFt);
  form.append("lat", latStr);
  form.append("lon", lonStr);
  for (const f of args.files) form.append("files", f, f.name);

  const res = await fetch(`${API_BASE}/api/station-photos/upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error(`Photo upload failed: ${res.status} ${res.statusText}`);
  return res.json();
}

export async function apiWalkEnd(walkSessionId: string): Promise<{
  ok: boolean;
  station_event_count: number;
  breadcrumb_count: number;
}> {
  const res = await fetch(`${API_BASE}/api/walk/end`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: walkSessionId }),
  });
  if (!res.ok) throw new Error(`End walk failed: ${res.status} ${res.statusText}`);
  return res.json();
}
