"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/apiFetch";
import { getAccessToken } from "@/lib/accessToken";
import { getPilotToken } from "@/lib/pilotToken";
import LogoutButton from "@/components/LogoutButton";

const API_BASE = "";

type Project = {
  projectId: string;
  name: string;
  href: string;
  location: string;
  archived?: boolean;
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

const PROJECTS_STORAGE_KEY = "trueline_projects";

function generateSlug(name: string): string {
  const slug = name
    .toLowerCase()
    .trim()
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9-]/g, "")
    .replace(/-+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug || "new-project";
}

function loadProjectsFromStorage(): Project[] {
  try {
    const raw = window.localStorage.getItem(PROJECTS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

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
  const router = useRouter();
  const [authReady, setAuthReady] = useState(false);
  const [userRole, setUserRole] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [deleteProjectTarget, setDeleteProjectTarget] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [newLocation, setNewLocation] = useState("");
  const nameInputRef = useRef<HTMLInputElement>(null);

  // Local auth gate — defense in depth independent of AuthGuard.
  // Must pass before any project data is read or rendered.
  useEffect(() => {
    const token = getAccessToken();
    if (token || getPilotToken()) {
      if (token) {
        try {
          const payload = JSON.parse(atob(token.split(".")[1]));
          setUserRole(payload.role ?? null);
        } catch {
          // malformed token — no role
        }
      }
      setAuthReady(true);
    } else {
      router.replace("/auth/login");
    }
  }, [router]);

  useEffect(() => {
    if (!authReady) return;
    setProjects(loadProjectsFromStorage());
  }, [authReady]);

  useEffect(() => {
    if (showCreateForm) {
      nameInputRef.current?.focus();
    }
  }, [showCreateForm]);

  const handleCreate = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      const trimmedName = newName.trim();
      if (!trimmedName) return;

      const base = generateSlug(trimmedName);
      const existingSlugs = new Set(projects.map((p) => p.projectId));
      const slug = existingSlugs.has(base) ? `${base}-${Date.now()}` : base;

      const project: Project = {
        projectId: slug,
        name: trimmedName,
        href: `/projects/${slug}`,
        location: newLocation.trim(),
      };

      const next = [...projects, project];
      try {
        window.localStorage.setItem(PROJECTS_STORAGE_KEY, JSON.stringify(next));
      } catch {
        // storage unavailable — navigate anyway
      }
      setProjects(next);
      router.push(`/projects/${slug}`);
    },
    [newName, newLocation, projects, router]
  );

  const handleArchive = useCallback(
    (projectId: string) => {
      const next = projects.map((p) =>
        p.projectId === projectId ? { ...p, archived: true } : p,
      );
      setProjects(next);
      try { window.localStorage.setItem(PROJECTS_STORAGE_KEY, JSON.stringify(next)); } catch { /* ignore */ }
    },
    [projects],
  );

  const handleRestore = useCallback(
    (projectId: string) => {
      const next = projects.map((p) =>
        p.projectId === projectId ? { ...p, archived: false } : p,
      );
      setProjects(next);
      try { window.localStorage.setItem(PROJECTS_STORAGE_KEY, JSON.stringify(next)); } catch { /* ignore */ }
    },
    [projects],
  );

  const handleDeleteProject = useCallback(
    (projectId: string) => {
      const next = projects.filter((p) => p.projectId !== projectId);
      setProjects(next);
      setDeleteProjectTarget(null);
      try { window.localStorage.setItem(PROJECTS_STORAGE_KEY, JSON.stringify(next)); } catch { /* ignore */ }
    },
    [projects],
  );

  if (!authReady) return null;

  const canManageProjects = userRole === "owner" || userRole === "admin";
  const visibleProjects = projects.filter((p) => showArchived || !p.archived);

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
              <div className="tl-eyebrow">Workspace</div>
              <h1 className="tl-h1">Project Dashboard</h1>
              <p className="tl-subtle" style={{ margin: 0, maxWidth: 720 }}>
                Manage active OSP redlining projects, review design and field
                progress, and open each project workspace.
              </p>
            </div>

            <div style={{ display: "flex", gap: 8, flexShrink: 0, flexWrap: "wrap", alignItems: "center" }}>
              <button
                type="button"
                onClick={() => setShowCreateForm((v) => !v)}
                className="tl-btn tl-btn-primary"
                aria-expanded={showCreateForm}
                aria-controls="new-project-form"
                style={{ whiteSpace: "nowrap" }}
              >
                + New Project
              </button>
              <LogoutButton />
            </div>
          </div>

          {showCreateForm && (
            <form
              id="new-project-form"
              onSubmit={handleCreate}
              className="tl-card"
              style={{
                marginTop: 16,
                padding: "16px 18px",
                display: "flex",
                flexDirection: "column",
                gap: 12,
              }}
            >
              <div style={{ fontWeight: 600, fontSize: 14, color: "var(--tl-text)" }}>
                New Project
              </div>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
                <div style={{ flex: "1 1 200px", display: "flex", flexDirection: "column", gap: 4 }}>
                  <label htmlFor="new-project-name" style={{ fontSize: 12, color: "var(--tl-text-muted)" }}>
                    Project name <span aria-hidden>*</span>
                  </label>
                  <input
                    id="new-project-name"
                    ref={nameInputRef}
                    type="text"
                    required
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder="e.g. Brenham Phase 6"
                    style={{
                      padding: "6px 10px",
                      borderRadius: 6,
                      border: "1px solid var(--tl-border)",
                      background: "var(--tl-bg)",
                      color: "var(--tl-text)",
                      fontSize: 14,
                    }}
                  />
                </div>
                <div style={{ flex: "1 1 160px", display: "flex", flexDirection: "column", gap: 4 }}>
                  <label htmlFor="new-project-location" style={{ fontSize: 12, color: "var(--tl-text-muted)" }}>
                    Location (optional)
                  </label>
                  <input
                    id="new-project-location"
                    type="text"
                    value={newLocation}
                    onChange={(e) => setNewLocation(e.target.value)}
                    placeholder="e.g. Brenham, TX"
                    style={{
                      padding: "6px 10px",
                      borderRadius: 6,
                      border: "1px solid var(--tl-border)",
                      background: "var(--tl-bg)",
                      color: "var(--tl-text)",
                      fontSize: 14,
                    }}
                  />
                </div>
                <div style={{ display: "flex", gap: 8, paddingBottom: 1 }}>
                  <button type="submit" className="tl-btn tl-btn-primary" disabled={!newName.trim()}>
                    Create &amp; Open
                  </button>
                  <button
                    type="button"
                    className="tl-btn tl-btn-ghost"
                    onClick={() => {
                      setShowCreateForm(false);
                      setNewName("");
                      setNewLocation("");
                    }}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </form>
          )}

          <div style={{ display: "flex", gap: 10, marginTop: 16, flexWrap: "wrap", alignItems: "center" }}>
            <Link href="/jobs" className="tl-btn tl-btn-ghost">
              Office Jobs
            </Link>
            <Link href="/jobs/inbox" className="tl-btn tl-btn-ghost">
              Field Submissions Inbox
            </Link>
            {(userRole === "owner" || userRole === "admin") && (
              <Link href="/admin" className="tl-btn tl-btn-ghost">
                Admin
              </Link>
            )}
            {projects.some((p) => p.archived) && (
              <button
                type="button"
                className="tl-btn tl-btn-ghost"
                onClick={() => setShowArchived((v) => !v)}
                style={{ fontSize: 13 }}
              >
                {showArchived ? "Hide Archived" : "Show Archived"}
              </button>
            )}
          </div>
        </header>

        {visibleProjects.length === 0 ? (
          <div
            style={{
              textAlign: "center",
              padding: "64px 24px",
              color: "var(--tl-text-muted)",
              fontSize: 14,
            }}
          >
            <div style={{ fontSize: 32, marginBottom: 12, opacity: 0.4 }}>📋</div>
            <div style={{ fontWeight: 600, marginBottom: 6, color: "var(--tl-text)" }}>No projects yet</div>
            <div>Click <strong>+ New Project</strong> to create your first workspace.</div>
          </div>
        ) : (
          <section
            aria-label="Project list"
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
              gap: 16,
            }}
          >
            {visibleProjects.map((project) => (
              <ProjectCard
                key={project.href}
                project={project}
                canManage={canManageProjects}
                onArchive={handleArchive}
                onRestore={handleRestore}
                deleteTarget={deleteProjectTarget}
                onDeleteRequest={setDeleteProjectTarget}
                onDeleteConfirm={handleDeleteProject}
              />
            ))}
          </section>
        )}
      </div>
      <footer style={{ marginTop: 48, paddingTop: 16, borderTop: "1px solid var(--tl-border)", textAlign: "center", fontSize: 12, color: "var(--tl-text-muted)", opacity: 0.5 }}>
        Powered by Midway Data Tech
      </footer>
    </main>
  );
}

function ProjectCard({
  project,
  canManage,
  onArchive,
  onRestore,
  deleteTarget,
  onDeleteRequest,
  onDeleteConfirm,
}: {
  project: Project;
  canManage: boolean;
  onArchive: (id: string) => void;
  onRestore: (id: string) => void;
  deleteTarget: string | null;
  onDeleteRequest: (id: string | null) => void;
  onDeleteConfirm: (id: string) => void;
}) {
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
        const response = await apiFetch(`${API_BASE}/api/current-state?session_id=${encodeURIComponent(sessionId)}`);
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
        <Metric label="Field data" value={!summary.hasLiveState ? "—" : String(summary.boreLogs ?? 0)} />
        <Metric label="Photos" value={!summary.hasLiveState ? "—" : String(summary.photos ?? 0)} />
        {summary.lastUpdated ? <Metric label="Last updated" value={summary.lastUpdated} /> : null}
      </div>

      {deleteTarget === project.projectId ? (
        <div style={{ padding: "10px 12px", borderRadius: 6, background: "#2a1212", border: "1px solid #7f1d1d", display: "flex", flexDirection: "column", gap: 8 }}>
          <span style={{ fontSize: 13, color: "#fca5a5" }}>
            Delete <strong>{project.name}</strong>?<br />
            <span style={{ fontSize: 11, opacity: 0.8 }}>
              Removes from dashboard. Server uploads are not deleted (localStorage-only project record).
            </span>
          </span>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              type="button"
              className="tl-btn tl-btn-ghost"
              style={{ fontSize: 12, padding: "5px 12px", color: "#fca5a5", borderColor: "#7f1d1d" }}
              onClick={() => onDeleteConfirm(project.projectId)}
            >
              Yes, delete
            </button>
            <button
              type="button"
              className="tl-btn tl-btn-ghost"
              style={{ fontSize: 12, padding: "5px 12px" }}
              onClick={() => onDeleteRequest(null)}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          {project.archived ? (
            <>
              <span style={{ padding: "2px 10px", borderRadius: 4, background: "#1c1917", border: "1px solid #57534e", color: "#a8a29e", fontSize: 12, fontWeight: 600 }}>
                Archived
              </span>
              {canManage && (
                <button
                  type="button"
                  className="tl-btn tl-btn-ghost"
                  style={{ fontSize: 13 }}
                  onClick={() => onRestore(project.projectId)}
                >
                  Restore
                </button>
              )}
              {canManage && (
                <button
                  type="button"
                  className="tl-btn tl-btn-ghost"
                  style={{ fontSize: 11, padding: "4px 8px", color: "#fca5a5", borderColor: "#7f1d1d" }}
                  onClick={() => onDeleteRequest(project.projectId)}
                >
                  Delete
                </button>
              )}
            </>
          ) : (
            <>
              <Link href={project.href} className="tl-btn tl-btn-primary" style={{ flex: 1, textAlign: "center" }}>
                Open Project →
              </Link>
              {canManage && (
                <button
                  type="button"
                  className="tl-btn tl-btn-ghost"
                  style={{ fontSize: 12, padding: "6px 10px", color: "var(--tl-text-muted)" }}
                  onClick={() => onArchive(project.projectId)}
                >
                  Archive
                </button>
              )}
              {canManage && (
                <button
                  type="button"
                  className="tl-btn tl-btn-ghost"
                  style={{ fontSize: 11, padding: "4px 8px", color: "#fca5a5", borderColor: "#7f1d1d" }}
                  onClick={() => onDeleteRequest(project.projectId)}
                >
                  Delete
                </button>
              )}
            </>
          )}
        </div>
      )}
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
