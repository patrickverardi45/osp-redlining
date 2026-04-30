"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/+$/, "") ||
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, "") ||
  "http://127.0.0.1:8000";

type Project = {
  projectId: string;
  name: string;
  href: string;
  location: string;
};

type ProjectState = {
  success?: boolean;
  kmz_reference?: {
    line_features?: unknown[];
    polygon_features?: unknown[];
  } | null;
  redline_segments?: Array<{
    length_ft?: number | null;
  }>;
  bore_log_summary?: unknown[];
  loaded_field_data_files?: number;
  coverage_summary?: {
    bore_logs?: unknown[];
    bore_log_count?: number;
  };
  station_photos?: unknown[];
  stationPhotos?: unknown[];
  gpsPhotos?: unknown[];
  total_length_ft?: number | null;
  covered_length_ft?: number | null;
  active_route_covered_length_ft?: number | null;
  updated_at?: string;
  last_updated?: string;
  timestamp?: string;
};

type ProjectSummary = {
  status: "No data yet" | "No uploads yet" | "Design loaded";
  hasSession: boolean;
  hasLiveState: boolean;
  kmzLoaded: boolean;
  plannedFootage: number | null;
  drilledFootage: number | null;
  boreLogs: number | null;
  photos: number | null;
  completion: string | null;
  lastUpdated: string | null;
};

const projects: Project[] = [
  {
    projectId: "brenham-phase-5",
    name: "Brenham Phase 5",
    href: "/projects/brenham-phase-5",
    location: "Brenham, TX",
  },
  {
    projectId: "dublin-tx",
    name: "Dublin TX",
    href: "/projects/dublin-tx",
    location: "Dublin, TX",
  },
  {
    projectId: "san-antonio-test-build",
    name: "San Antonio Test Build",
    href: "/projects/san-antonio-test-build",
    location: "San Antonio, TX",
  },
  {
    projectId: "future-project",
    name: "Future Project",
    href: "/projects/future-project",
    location: "TBD",
  },
];

function getProjectSessionId(projectId: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(`osp_session_id:${projectId}`)?.trim() || null;
  } catch {
    return null;
  }
}

function getManualPlannedFootage(projectId: string): number | null {
  if (typeof window === "undefined") return null;
  const keyPrefix = `osp_project_planned_footage:${projectId}:`;
  try {
    let best: number | null = null;
    for (let index = 0; index < window.localStorage.length; index += 1) {
      const key = window.localStorage.key(index);
      if (!key?.startsWith(keyPrefix)) continue;
      const raw = window.localStorage.getItem(key);
      const value = raw === null ? NaN : parseFloat(raw.trim());
      if (Number.isFinite(value) && value > 0) {
        best = best === null ? value : Math.max(best, value);
      }
    }
    return best;
  } catch {
    return null;
  }
}

function hasKmz(state: ProjectState): boolean {
  const lines = state.kmz_reference?.line_features ?? [];
  const polygons = state.kmz_reference?.polygon_features ?? [];
  return lines.length > 0 || polygons.length > 0;
}

function getBoreLogCount(state: ProjectState): number {
  if (Array.isArray(state.bore_log_summary) && state.bore_log_summary.length > 0) {
    return state.bore_log_summary.length;
  }
  if (typeof state.loaded_field_data_files === "number" && state.loaded_field_data_files > 0) {
    return state.loaded_field_data_files;
  }
  if (typeof state.coverage_summary?.bore_log_count === "number") return state.coverage_summary.bore_log_count;
  if (Array.isArray(state.coverage_summary?.bore_logs)) return state.coverage_summary.bore_logs.length;
  return 0;
}

function getPhotoCount(state: ProjectState): number {
  if (Array.isArray(state.station_photos)) return state.station_photos.length;
  if (Array.isArray(state.stationPhotos)) return state.stationPhotos.length;
  if (Array.isArray(state.gpsPhotos)) return state.gpsPhotos.length;
  return 0;
}

/** Drilled / as-built footage for dashboard: sum of redline segment lengths only (matches workspace drilled total). */
function getDrilledFootageFromRedlines(state: ProjectState): number | null {
  const segments = state.redline_segments;
  if (!Array.isArray(segments) || segments.length === 0) return null;
  const sum = segments.reduce((total, segment) => {
    const length = segment.length_ft;
    return typeof length === "number" && Number.isFinite(length) ? total + length : total;
  }, 0);
  return sum;
}

function formatCompletion(plannedFootage: number | null, drilledFootage: number | null): string | null {
  if (plannedFootage === null || !Number.isFinite(plannedFootage) || plannedFootage <= 0 || drilledFootage === null) return null;
  const completion = (drilledFootage / plannedFootage) * 100;
  return `${completion.toFixed(1)}%`;
}

function formatFeet(value: number | null, decimals = 2): string {
  if (value === null || !Number.isFinite(value)) return "—";
  const fixed = decimals === 0 ? Math.round(value).toString() : value.toFixed(decimals);
  const [whole, frac] = fixed.split(".");
  const withCommas = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return frac !== undefined ? `${withCommas}.${frac}` : withCommas;
}

function formatFeetSmart(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  const decimals = Math.abs(value - Math.round(value)) < 1e-6 ? 0 : 2;
  return formatFeet(value, decimals);
}

function formatLastUpdated(state: ProjectState): string | null {
  const value = state.updated_at || state.last_updated || state.timestamp;
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
}

function summarizeState(state: ProjectState, projectId: string): ProjectSummary {
  const kmzLoaded = hasKmz(state);
  const plannedFootage = getManualPlannedFootage(projectId);
  const drilledFootage = getDrilledFootageFromRedlines(state);
  const boreLogs = getBoreLogCount(state);
  const photos = getPhotoCount(state);
  const filesLoaded = (state.loaded_field_data_files ?? 0) > 0;
  const hasRedlines = (state.redline_segments?.length ?? 0) > 0;
  const hasUploads = kmzLoaded || filesLoaded || hasRedlines || boreLogs > 0 || photos > 0;
  const status: ProjectSummary["status"] = kmzLoaded
    ? "Design loaded"
    : hasUploads
      ? "No uploads yet"
      : "No uploads yet";

  return {
    status,
    hasSession: true,
    hasLiveState: true,
    kmzLoaded,
    plannedFootage,
    drilledFootage,
    boreLogs,
    photos,
    completion: formatCompletion(plannedFootage, drilledFootage),
    lastUpdated: formatLastUpdated(state),
  };
}

export default function ProjectsPage() {
  return (
    <main style={{ minHeight: "100vh", background: "#f5f7fa", color: "#172033", fontFamily: "Arial, sans-serif", padding: "32px" }}>
      <div style={{ maxWidth: "1180px", margin: "0 auto" }}>
        <header style={{ marginBottom: "24px" }}>
          <div style={{ color: "#64748b", fontSize: "13px", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase" }}>
            OSP Redlining
          </div>
          <h1 style={{ margin: "8px 0 8px", fontSize: "34px", lineHeight: 1.1 }}>Project Dashboard</h1>
          <p style={{ margin: 0, maxWidth: "720px", color: "#526173", fontSize: "16px", lineHeight: 1.6 }}>
            Manage active OSP redlining projects, review progress, and open each project workspace.
          </p>
        </header>

        <section
          aria-label="Project list"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
            gap: "16px",
          }}
        >
          {projects.map((project) => (
            <ProjectCard key={project.href} project={project} />
          ))}
        </section>
      </div>
    </main>
  );
}

function ProjectCard({ project }: { project: Project }) {
  const [summary, setSummary] = useState<ProjectSummary>({
    status: "No data yet",
    hasSession: false,
    hasLiveState: false,
    kmzLoaded: false,
    plannedFootage: null,
    drilledFootage: null,
    boreLogs: null,
    photos: null,
    completion: null,
    lastUpdated: null,
  });

  useEffect(() => {
    let cancelled = false;

    async function loadProjectStatus() {
      const sessionId = getProjectSessionId(project.projectId);
      if (!sessionId) {
        if (!cancelled) {
          setSummary({
            status: "No data yet",
            hasSession: false,
            hasLiveState: false,
            kmzLoaded: false,
            plannedFootage: null,
            drilledFootage: null,
            boreLogs: null,
            photos: null,
            completion: null,
            lastUpdated: null,
          });
        }
        return;
      }

      try {
        const response = await fetch(`${API_BASE}/api/current-state?session_id=${encodeURIComponent(sessionId)}`);
        if (!response.ok) return;
        const data = await response.json();
        if (cancelled || data?.success === false) return;
        setSummary(summarizeState(data, project.projectId));
      } catch {
        // Dashboard status is best-effort; project workspaces remain authoritative.
      }
    }

    loadProjectStatus();
    const onStorage = (event: StorageEvent) => {
      if (event.key?.startsWith(`osp_project_planned_footage:${project.projectId}:`)) {
        loadProjectStatus();
      }
      if (event.key === `osp_session_id:${project.projectId}`) {
        loadProjectStatus();
      }
    };
    window.addEventListener("focus", loadProjectStatus);
    window.addEventListener("storage", onStorage);
    return () => {
      cancelled = true;
      window.removeEventListener("focus", loadProjectStatus);
      window.removeEventListener("storage", onStorage);
    };
  }, [project.projectId]);

  const statusColor =
    summary.status === "Design loaded"
      ? "#166534"
      : summary.status === "No uploads yet"
        ? "#92400e"
        : "#475569";
  const statusBackground =
    summary.status === "Design loaded"
      ? "#dcfce7"
      : summary.status === "No uploads yet"
        ? "#fef3c7"
        : "#e2e8f0";

  return (
    <article
      style={{
        display: "grid",
        gap: "16px",
        border: "1px solid #dbe3ee",
        borderRadius: "16px",
        background: "#ffffff",
        padding: "18px",
        boxShadow: "0 8px 22px rgba(15, 23, 42, 0.06)",
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "12px" }}>
        <div>
          <h2 style={{ margin: 0, color: "#0f172a", fontSize: "20px", lineHeight: 1.25 }}>{project.name}</h2>
          <div style={{ marginTop: "6px", color: "#64748b", fontSize: "14px" }}>{project.location}</div>
        </div>
        <span
          style={{
            borderRadius: "999px",
            background: statusBackground,
            color: statusColor,
            fontSize: "12px",
            fontWeight: 800,
            padding: "5px 9px",
            whiteSpace: "nowrap",
          }}
        >
          {summary.status}
        </span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
        <Metric label="Design" value={summary.kmzLoaded ? "Design loaded" : summary.hasSession ? "Not loaded" : "No data yet"} />
        <Metric
          label="Planned footage"
          value={!summary.hasLiveState ? "—" : summary.plannedFootage === null ? "—" : `${formatFeetSmart(summary.plannedFootage)} ft`}
        />
        <Metric
          label="Drilled footage"
          value={!summary.hasLiveState ? "—" : summary.drilledFootage === null ? "—" : `${formatFeet(summary.drilledFootage, 2)} ft`}
        />
        <Metric
          label="Completion"
          value={
            !summary.hasLiveState
              ? "—"
              : summary.completion ?? "—"
          }
        />
        <Metric label="Bore logs" value={!summary.hasLiveState ? "—" : String(summary.boreLogs ?? 0)} />
        <Metric label="Photos" value={!summary.hasLiveState ? "—" : String(summary.photos ?? 0)} />
        {summary.lastUpdated ? <Metric label="Last updated" value={summary.lastUpdated} /> : null}
      </div>

      <Link
        href={project.href}
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          borderRadius: "10px",
          background: "#0f172a",
          color: "#ffffff",
          fontSize: "14px",
          fontWeight: 800,
          padding: "10px 12px",
          textDecoration: "none",
        }}
      >
        Open Project
      </Link>
    </article>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        border: "1px solid #edf2f7",
        borderRadius: "12px",
        background: "#f8fafc",
        padding: "10px",
      }}
    >
      <div style={{ color: "#64748b", fontSize: "12px", fontWeight: 700 }}>{label}</div>
      <div
        style={{
          marginTop: "4px",
          color: "#0f172a",
          fontSize: "14px",
          fontWeight: 800,
          overflowWrap: "anywhere",
        }}
      >
        {value}
      </div>
    </div>
  );
}
