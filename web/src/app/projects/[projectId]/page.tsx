import Link from "next/link";
import RedlineMap from "@/components/RedlineMap";

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

export default async function ProjectPage({ params }: ProjectPageProps) {
  const { projectId } = await params;
  const projectDisplayName = projectIdToDisplayName(projectId);

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
              TrueLine · Workspace
            </div>
            <h1
              className="tl-h1"
              style={{ margin: "6px 0 0", fontSize: 22, lineHeight: 1.25 }}
            >
              {projectDisplayName}
            </h1>
            <p className="tl-subtle" style={{ margin: "6px 0 0", fontSize: 14 }}>
              Project workspace — design, bore logs, reports, and billing are
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

      {/* Map workspace — RedlineMap framed inside a dark dashboard surface.
          The component itself is mounted exactly as before; only the chrome
          around it is themed. */}
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
          style={{
            overflow: "hidden",
            padding: 0,
            background: "var(--tl-surface)",
          }}
        >
          <RedlineMap projectId={projectId} workspaceTitle={projectDisplayName} />
        </div>
      </div>
    </main>
  );
}
