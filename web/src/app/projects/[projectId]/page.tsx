"use client";

import { use, useCallback, useState } from "react";
import Link from "next/link";
import LogoutButton from "@/components/LogoutButton";
import MatchReviewLink from "@/components/MatchReviewLink";
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

// Stable resolved fallback so `use()` can run unconditionally even if the page
// is ever rendered without the (Next-provided) searchParams promise.
const EMPTY_SEARCH_PARAMS: Promise<Record<string, string | string[] | undefined>> =
  Promise.resolve({});

type ProjectPageProps = {
  params: Promise<{
    projectId: string;
  }>;
  // Next 16 passes searchParams to the page as a Promise (read with `use`),
  // the same async-prop pattern as `params`. Read-only — used only for the
  // ?focus=<source_file> hero-map deep-link; never mutated.
  searchParams?: Promise<{ [key: string]: string | string[] | undefined }>;
};

/** e.g. brenham-phase-5 → Brenham Phase 5 */
function projectIdToDisplayName(projectId: string): string {
  return projectId
    .split("-")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}

export default function ProjectPage({ params, searchParams }: ProjectPageProps) {
  const { projectId } = use(params);
  const projectDisplayName = projectIdToDisplayName(projectId);
  // Read-only ?focus=<source_file> deep-link target for the live hero map.
  // Resolved via the async searchParams prop (same `use()` pattern as params),
  // so no useSearchParams/Suspense plumbing is required.
  const resolvedSearch = use(searchParams ?? EMPTY_SEARCH_PARAMS);
  const focusParam = resolvedSearch?.focus;
  let focusedSourceFile: string | null = null;
  if (typeof focusParam === "string") {
    focusedSourceFile = focusParam;
  } else if (Array.isArray(focusParam) && typeof focusParam[0] === "string") {
    focusedSourceFile = focusParam[0];
  }
  // Optional ?session_id= passed through from the review surfaces. Preserved on
  // the return-path links below; never minted here (read-only).
  const sessionParam = resolvedSearch?.session_id;
  let sessionIdParam: string | null = null;
  if (typeof sessionParam === "string") {
    sessionIdParam = sessionParam;
  } else if (Array.isArray(sessionParam) && typeof sessionParam[0] === "string") {
    sessionIdParam = sessionParam[0];
  }
  // Return-path links for the focused-review banner. projectId always preserved;
  // session_id only when present in the current URL (the review surfaces resolve
  // the session via peekSessionId(projectId) when it is absent).
  const reviewCtx = new URLSearchParams({ projectId });
  if (sessionIdParam) reviewCtx.set("session_id", sessionIdParam);
  const matchReviewHref = `/match-review?${reviewCtx.toString()}`;
  // Trust Ledger return carries the focused source_file so the ledger scrolls to
  // + highlights that row ("return to row"). Match Review link intentionally
  // unchanged (no row-focus there yet).
  const trustLedgerCtx = new URLSearchParams(reviewCtx);
  if (focusedSourceFile) trustLedgerCtx.set("focus", focusedSourceFile);
  const trustLedgerHref = `/trust-ledger?${trustLedgerCtx.toString()}`;
  const clearFocusHref = sessionIdParam
    ? `/projects/${projectId}?session_id=${encodeURIComponent(sessionIdParam)}`
    : `/projects/${projectId}`;
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
              href="/projects"
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

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <Link
              href={`/trust-ledger?projectId=${encodeURIComponent(projectId)}`}
              className="tl-btn tl-btn-ghost"
              style={{ fontSize: 13, whiteSpace: "nowrap" }}
            >
              Trust Ledger
            </Link>
            <LogoutButton />
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
            <Link href="/projects" className="tl-link">
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

      {/* Focused-review banner — shown only when a ?focus=<source_file> deep-link
          is active (operator arrived from Trust Ledger or Match Review). Honest
          language; no proof claims here. Return links preserve projectId (and
          session_id when present); "Clear focus" drops the ?focus= param.
          Read-only — uses the existing ModernHeroMap focus behavior. */}
      {focusedSourceFile && (
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
              gap: 12,
              flexWrap: "wrap",
              fontSize: 12,
            }}
          >
            <span className="tl-pill tl-pill-info">Focused review</span>
            <span style={{ color: "var(--tl-text-muted)" }}>
              Source file:{" "}
              <span
                style={{
                  fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                  color: "var(--tl-text)",
                  fontWeight: 600,
                }}
              >
                {focusedSourceFile}
              </span>
            </span>
            <span
              style={{
                display: "inline-flex",
                gap: 8,
                flexWrap: "wrap",
                alignItems: "center",
                marginLeft: "auto",
              }}
            >
              <Link
                href={trustLedgerHref}
                className="tl-btn tl-btn-ghost"
                style={{ fontSize: 12, padding: "2px 10px", whiteSpace: "nowrap" }}
              >
                ← Back to Trust Ledger
              </Link>
              <MatchReviewLink
                href={matchReviewHref}
                projectId={projectId}
                className="tl-btn tl-btn-ghost"
                style={{ fontSize: 12, padding: "2px 10px", whiteSpace: "nowrap" }}
              >
                ← Back to Match Review
              </MatchReviewLink>
              <Link
                href={clearFocusHref}
                className="tl-link"
                style={{ fontSize: 12, whiteSpace: "nowrap" }}
              >
                Clear focus
              </Link>
            </span>
          </div>
        </div>
      )}

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
                focusedSourceFile={focusedSourceFile}
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
