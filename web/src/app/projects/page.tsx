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
  const [showNewProjectNotice, setShowNewProjectNotice] = useState(false);

  return (
    <main className="tl-page">
      <div className="tl-page-inner">
        <header style={{ marginBottom: 28 }}>
          <div
            style={{
              display: "flex",
              alignItems: "flex-start",
              justifyContent: "space-between",
              gap: 16,
              flexWrap: "wrap",
            }}
          >
            <div style={{ minWidth: 0 }}>
              <div className="tl-eyebrow">TrueLine · Field Operations Platform</div>
              <h1 className="tl-h1">Project Dashboard</h1>
              <p className="tl-subtle" style={{ margin: 0, maxWidth: 720 }}>
                Manage active OSP redlining projects, review design and field
                progress, and open each project workspace.
              </p>
            </div>

            <button
              type="button"
              onClick={() => setShowNewProjectNotice((v) => !v)}
              className="tl-btn tl-btn-primary"
              aria-expanded={showNewProjectNotice}
              aria-controls="new-project-notice"
              style={{ flexShrink: 0, whiteSpace: "nowrap" }}
            >
              + New Project
            </button>
          </div>

          {showNewProjectNotice && (
            <div
              id="new-project-notice"
              role="status"
              className="tl-card"
              style={{
                marginTop: 16,
                padding: "12px 14px",
                display: "flex",
                alignItems: "flex-start",
                justifyContent: "space-between",
                gap: 12,
                borderColor: "var(--tl-amber-border)",
                background: "var(--tl-surface)",
                color: "#fde68a",
                fontSize: 13,
                lineHeight: 1.5,
              }}
            >
              <div>
                <strong style={{ fontWeight: 700 }}>
                  Coming next: project creation.
                </strong>{" "}
                Backend wiring for new-project setup isn&apos;t hooked up yet —
                this button is a placeholder so the workflow has a home in the
                UI.
              </div>
              <button
                type="button"
                onClick={() => setShowNewProjectNotice(false)}
                className="tl-btn tl-btn-ghost"
                aria-label="Dismiss new project notice"
                style={{
                  fontSize: 12,
                  padding: "4px 10px",
                  color: "#fde68a",
                  borderColor: "var(--tl-amber-border)",
                }}
              >
                Close
              </button>
            </div>
          )}

          <div style={{ display: "flex", gap: 10, marginTop: 16, flexWrap: "wrap" }}>
            <Link href="/jobs" className="tl-btn tl-btn-ghost">
              Office Jobs
            </Link>
            <Link href="/jobs/inbox" className="tl-btn tl-btn-ghost">
              Field Submissions Inbox
            </Link>
          </div>
        </header>

        <section
          aria-label="Project list"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
            gap: 16,
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

  const pillClass =
    summary.status === "Design loaded"
      ? "tl-pill tl-pill-success"
      : summary.status === "No uploads yet"
        ? "tl-pill tl-pill-warn"
        : "tl-pill";

  return (
    <article
      className="tl-card tl-card-padded tl-card-hover"
      style={{ display: "grid", gap: 16 }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
        <div>
          <h2 className="tl-h2" style={{ fontSize: 18 }}>
            {project.name}
          </h2>
          <div style={{ marginTop: 4, color: "var(--tl-text-muted)", fontSize: 13 }}>
            {project.location}
          </div>
        </div>
        <span className={pillClass}>{summary.status}</span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
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
          value={!summary.hasLiveState ? "—" : summary.completion ?? "—"}
          accent={summary.completion ? "info" : undefined}
        />
        <Metric label="Bore logs" value={!summary.hasLiveState ? "—" : String(summary.boreLogs ?? 0)} />
        <Metric label="Photos" value={!summary.hasLiveState ? "—" : String(summary.photos ?? 0)} />
        {summary.lastUpdated ? <Metric label="Last updated" value={summary.lastUpdated} /> : null}
      </div>

      <Link href={project.href} className="tl-btn tl-btn-primary">
        Open Project →
      </Link>
    </article>
  );
}

function Metric({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: "info" | "success" | "warn" | "danger";
}) {
  const accentColor =
    accent === "info"
      ? "#7dd3fc"
      : accent === "success"
        ? "#86efac"
        : accent === "warn"
          ? "#fcd34d"
          : accent === "danger"
            ? "#fca5a5"
            : "var(--tl-text)";
  return (
    <div className="tl-metric">
      <div className="tl-metric-label">{label}</div>
      <div className="tl-metric-value" style={{ color: accentColor }}>
        {value}
      </div>
    </div>
  );
}
