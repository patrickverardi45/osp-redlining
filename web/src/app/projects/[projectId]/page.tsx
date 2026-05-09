"use client";

import { use, useCallback, useState } from "react";
import Link from "next/link";
import RedlineMap, { type BridgedGpsPhoto } from "@/components/RedlineMap";
import ModernHeroMap from "@/components/ModernHeroMap";

type ProjectPageProps = {
  params: Promise<{
    projectId: string;
  }>;
};

/** e.g. brenham-phase-5 → Brenham Phase 5 */
function projectIdToDisplayName(projectId: string): string {
  return projectId
    .split("-")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}

export default function ProjectPage({ params }: ProjectPageProps) {
  const { projectId } = use(params);
  const projectDisplayName = projectIdToDisplayName(projectId);
  const [selectedFieldSessionId, setSelectedFieldSessionId] = useState<string | null>(
    null,
  );
  const [selectedFieldJobId, setSelectedFieldJobId] = useState<string | null>(null);
  const [modernMapRefreshVersion, setModernMapRefreshVersion] = useState<number>(0);
  const [bridgedGpsPhotos, setBridgedGpsPhotos] = useState<BridgedGpsPhoto[]>([]);

  const handleFieldSelectionChange = useCallback(
    (selection: { sessionId: string | null; jobId: string | null }) => {
      setSelectedFieldSessionId(selection.sessionId);
      setSelectedFieldJobId(selection.jobId);
    },
    [],
  );

  const handleWorkspaceStateChanged = useCallback(() => {
    setModernMapRefreshVersion((v) => v + 1);
  }, []);
  const handleGpsPhotosChange = useCallback((photos: BridgedGpsPhoto[]) => {
    setBridgedGpsPhotos(photos);
  }, []);

  return (
    <main className="tl-page" style={{ display: "flex", flexDirection: "column" }}>
      {/* Workspace header */}
      <header
        className="tl-topbar"
        style={{ padding: "16px 22px 18px" }}
      >
        <div
          style={{
            maxWidth: 1280,
            margin: "0 auto",
            width: "100%",
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            gap: 16,
            flexWrap: "wrap",
          }}
        >
          <div style={{ minWidth: 0 }}>
            <Link
              href="/"
              className="tl-link"
              style={{ display: "inline-block", fontSize: 13, fontWeight: 600 }}
            >
              ← Back to Dashboard
            </Link>
            <div className="tl-eyebrow" style={{ marginTop: 10 }}>
              Workspace
            </div>
            <h1
              className="tl-h1"
              style={{ margin: "6px 0 0", fontSize: 22, lineHeight: 1.25 }}
            >
              {projectDisplayName}
            </h1>
            <p className="tl-subtle" style={{ margin: "6px 0 0", fontSize: 14 }}>
              Project workspace — design, field data, reports, and billing are
              scoped to this job.
            </p>
          </div>

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Link
              href={`/walk?projectId=${encodeURIComponent(projectId)}`}
              className="tl-btn tl-btn-ghost"
              style={{ fontSize: 12, padding: "6px 12px" }}
            >
              Field walk (mobile) →
            </Link>
          </div>
        </div>
      </header>

      {/* Workspace context strip */}
      <div
        style={{
          borderBottom: "1px solid var(--tl-border)",
          background: "var(--tl-bg-grid)",
        }}
      >
        <div
          style={{
            maxWidth: 1280,
            margin: "0 auto",
            padding: "10px 22px",
            display: "flex",
            alignItems: "center",
            gap: 10,
            flexWrap: "wrap",
            fontSize: 12,
          }}
        >
          <span className="tl-pill tl-pill-info">Workspace</span>
          <span style={{ color: "var(--tl-text-muted)" }}>
            <Link href="/" className="tl-link">
              Projects
            </Link>
            <span
              style={{ margin: "0 8px", color: "var(--tl-text-faint)" }}
              aria-hidden="true"
            >
              /
            </span>
            <span style={{ color: "var(--tl-text)", fontWeight: 600 }}>
              {projectDisplayName}
            </span>
          </span>
          <span
            style={{
              marginLeft: "auto",
              color: "var(--tl-text-faint)",
              fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
            }}
          >
            {projectId}
          </span>
        </div>
      </div>

      {/* Operational map first (Leaflet), then workflow/legacy RedlineMap below. */}
      <div
        style={{
          flex: 1,
          padding: "18px 22px 28px",
          maxWidth: 1280,
          width: "100%",
          margin: "0 auto",
          boxSizing: "border-box",
        }}
      >
        <ModernHeroMap
          key={`modern-map-${projectId}`}
          projectId={projectId}
          selectedFieldSessionId={selectedFieldSessionId}
          selectedFieldJobId={selectedFieldJobId}
          refreshVersion={modernMapRefreshVersion}
          bridgedGpsPhotos={bridgedGpsPhotos}
        />
        <div
          className="tl-card"
          style={{ overflow: "hidden", padding: 0, background: "var(--tl-surface)" }}
        >
          <div
            style={{
              padding: "12px 14px",
              borderBottom: "1px solid var(--tl-border)",
              background: "var(--tl-bg-grid)",
            }}
          >
            <div style={{ fontSize: 13, fontWeight: 700, color: "var(--tl-text)" }}>
              Workflow Controls
            </div>
            <div style={{ fontSize: 12, color: "var(--tl-text-muted)", marginTop: 2 }}>
              Upload design files, field data, photos, and manage closeout below. The
              legacy SVG map stays optional under Map and field tools (collapsed details panel).
            </div>
          </div>
          <RedlineMap
            projectId={projectId}
            workspaceTitle={projectDisplayName}
            onFieldSelectionChange={handleFieldSelectionChange}
            onWorkspaceStateChanged={handleWorkspaceStateChanged}
            onGpsPhotosChange={handleGpsPhotosChange}
          />
        </div>
      </div>
    </main>
  );
}
