"use client";

import { use, useCallback, useState } from "react";
import Link from "next/link";
import RedlineMap, { type BridgedGpsPhoto } from "@/components/RedlineMap";
import ModernHeroMap from "@/components/ModernHeroMap";
import KmzSemanticDiagnosticsPanel from "@/components/KmzSemanticDiagnosticsPanel";
import type { SemanticKmz } from "@/lib/types/backend";

// Phase 1B — KMZ semantic diagnostics panel is gated behind a build-time
// env flag so production end-users never see it. Set
// NEXT_PUBLIC_SHOW_SEMANTIC_DIAG=1 in .env.local to enable.
const SHOW_SEMANTIC_DIAG =
  process.env.NEXT_PUBLIC_SHOW_SEMANTIC_DIAG === "1" ||
  process.env.NEXT_PUBLIC_SHOW_SEMANTIC_DIAG === "true";

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
  const [kmzSemantic, setKmzSemantic] = useState<SemanticKmz | null>(null);

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
  const handleKmzSemanticChange = useCallback((semantic: SemanticKmz | null) => {
    setKmzSemantic(semantic);
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
              Uploads and tooling first; Project Map (Leaflet) follows geotagged photo
              controls; legacy SVG stays optional under Map and field tools.
            </div>
          </div>
          <RedlineMap
            projectId={projectId}
            workspaceTitle={projectDisplayName}
            onFieldSelectionChange={handleFieldSelectionChange}
            onWorkspaceStateChanged={handleWorkspaceStateChanged}
            onGpsPhotosChange={handleGpsPhotosChange}
            onKmzSemanticChange={handleKmzSemanticChange}
            operationalMap={
              <ModernHeroMap
                key={`modern-map-${projectId}`}
                projectId={projectId}
                selectedFieldSessionId={selectedFieldSessionId}
                selectedFieldJobId={selectedFieldJobId}
                refreshVersion={modernMapRefreshVersion}
                bridgedGpsPhotos={bridgedGpsPhotos}
                kmzSemantic={kmzSemantic}
              />
            }
          />
          {SHOW_SEMANTIC_DIAG ? (
            <KmzSemanticDiagnosticsPanel
              projectId={projectId}
              refreshVersion={modernMapRefreshVersion}
            />
          ) : null}
        </div>
      </div>
    </main>
  );
}
