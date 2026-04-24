// web/src/lib/api.ts

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

// ─── Allowed statuses ─────────────────────────────────────────────────────────

export type JobStatus =
  | "draft"
  | "ready_for_field"
  | "in_progress"
  | "field_complete"
  | "qa_review"
  | "redlines_ready"
  | "closeout_ready"
  | "billed";

// ─── Status transition map ────────────────────────────────────────────────────
// Centralised so list + detail pages use identical rules.

export const STATUS_ORDER: JobStatus[] = [
  "draft",
  "ready_for_field",
  "in_progress",
  "field_complete",
  "qa_review",
  "redlines_ready",
  "closeout_ready",
  "billed",
];

export const STATUS_LABELS: Record<JobStatus, string> = {
  draft: "Draft",
  ready_for_field: "Ready for Field",
  in_progress: "In Progress",
  field_complete: "Field Complete",
  qa_review: "QA Review",
  redlines_ready: "Redlines Ready",
  closeout_ready: "Closeout Ready",
  billed: "Billed",
};

// Forward-only action labels for the "advance" button
export const ADVANCE_ACTION_LABELS: Partial<Record<JobStatus, string>> = {
  draft: "Mark Ready for Field",
  ready_for_field: "Mark In Progress",
  in_progress: "Mark Field Complete",
  field_complete: "Send to QA Review",
  qa_review: "Mark Redlines Ready",
  redlines_ready: "Mark Closeout Ready",
  closeout_ready: "Mark as Billed",
};

// Steps that require a confirm() before proceeding
export const CONFIRM_REQUIRED_TRANSITIONS = new Set<JobStatus>([
  "qa_review",       // → redlines_ready
  "redlines_ready",  // → closeout_ready
  "closeout_ready",  // → billed
]);

export function getNextStatus(current: JobStatus): JobStatus | null {
  const idx = STATUS_ORDER.indexOf(current);
  if (idx === -1 || idx === STATUS_ORDER.length - 1) return null;
  return STATUS_ORDER[idx + 1];
}

export function getPrevStatus(current: JobStatus): JobStatus | null {
  const idx = STATUS_ORDER.indexOf(current);
  if (idx <= 0) return null;
  return STATUS_ORDER[idx - 1];
}

export function isKnownStatus(status: string): status is JobStatus {
  return STATUS_ORDER.includes(status as JobStatus);
}

// ─── Job List ─────────────────────────────────────────────────────────────────

export interface Job {
  id: string;
  job_code: string;
  job_name: string;
  status: JobStatus | string;
  route_count: number;
  session_count: number;
  exception_count: number;
  last_sync_at: string | null;
}

// ─── Geometry ─────────────────────────────────────────────────────────────────

export interface GeoLineString {
  type: "LineString";
  coordinates: [number, number][];
}

// ─── Job Detail Sub-types ─────────────────────────────────────────────────────

export interface Route {
  id: string;
  route_name: string;
  length_ft: number;
  segment_count: number;
  geometry?: GeoLineString | null;
}

export interface Session {
  id: string;
  crew_name: string;
  status: string;
  started_at: string;
  ended_at: string | null;
  station_count: number;
  photo_count: number;
  latest_photo_url?: string | null;
  track_point_count: number;
  track_geometry?: GeoLineString | null;
}

export interface Station {
  id: string;
  station_number: string;
  depth_ft: number;
  boc_ft: number;
  latitude: number;
  longitude: number;
  review_status: string;
}

export interface Photo {
  id: string;
  station_id: string | null;
  latitude: number;
  longitude: number;
  thumbnail_url: string | null;
}

export interface Exception {
  id: string;
  exception_type: string;
  severity: "low" | "medium" | "high" | "critical" | string;
  status: "open" | "resolved" | "dismissed" | string;
  description: string;
  latitude?: number | null;
  longitude?: number | null;
}

export interface Artifact {
  id: string;
  artifact_type: string;
  version_number: number;
  generation_status: "queued" | "working" | "complete" | "failed" | string;
  file_url: string | null;
  created_at: string;
}

export interface JobDetail extends Job {
  routes: Route[];
  sessions: Session[];
  stations: Station[];
  photos: Photo[];
  exceptions: Exception[];
  artifacts: Artifact[];
}

export interface GenerateReportResult {
  artifact_id: string;
  generation_status: string;
}

// ─── API calls ────────────────────────────────────────────────────────────────

export async function getJobs(): Promise<Job[]> {
  const res = await fetch(`${BASE_URL}/jobs`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to fetch jobs: ${res.status} ${res.statusText}`);
  return res.json();
}

export async function getJobById(jobId: string): Promise<JobDetail> {
  const res = await fetch(`${BASE_URL}/jobs/${jobId}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to fetch job ${jobId}: ${res.status} ${res.statusText}`);
  return res.json();
}

export async function updateJobStatus(
  jobId: string,
  status: JobStatus
): Promise<void> {
  const res = await fetch(`${BASE_URL}/jobs/${jobId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!res.ok) throw new Error(`Failed to update job status: ${res.status} ${res.statusText}`);
}

export async function updateExceptionStatus(
  exceptionId: string,
  status: "resolved" | "dismissed"
): Promise<void> {
  const res = await fetch(`${BASE_URL}/exceptions/${exceptionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!res.ok) throw new Error(`Failed to update exception ${exceptionId}: ${res.status} ${res.statusText}`);
}

export async function generateQaSummary(jobId: string): Promise<GenerateReportResult> {
  const res = await fetch(`${BASE_URL}/jobs/${jobId}/reports/qa-summary`, { method: "POST" });
  if (!res.ok) throw new Error(`Failed to generate QA summary: ${res.status} ${res.statusText}`);
  return res.json();
}

export async function generateRedlineReport(jobId: string): Promise<GenerateReportResult> {
  const res = await fetch(`${BASE_URL}/jobs/${jobId}/reports/redline`, { method: "POST" });
  if (!res.ok) throw new Error(`Failed to generate redline report: ${res.status} ${res.statusText}`);
  return res.json();
}

export async function generateCloseoutReport(jobId: string): Promise<GenerateReportResult> {
  const res = await fetch(`${BASE_URL}/jobs/${jobId}/reports/closeout`, { method: "POST" });
  if (!res.ok) throw new Error(`Failed to generate closeout report: ${res.status} ${res.statusText}`);
  return res.json();
}
