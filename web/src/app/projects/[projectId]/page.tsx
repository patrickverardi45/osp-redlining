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
    <>
      <header
        style={{
          borderBottom: "1px solid #dbe4ee",
          background: "#ffffff",
          padding: "16px 22px 18px",
          fontFamily: "system-ui, Segoe UI, Roboto, Arial, sans-serif",
        }}
      >
        <Link
          href="/"
          style={{
            display: "inline-block",
            color: "#475569",
            fontSize: 13,
            fontWeight: 600,
            textDecoration: "none",
          }}
        >
          ← Back to Dashboard
        </Link>
        <h1 style={{ margin: "10px 0 0", color: "#0f172a", fontSize: 22, fontWeight: 800, letterSpacing: -0.4, lineHeight: 1.25 }}>
          {projectDisplayName}
        </h1>
        <p style={{ margin: "6px 0 0", color: "#64748b", fontSize: 14, lineHeight: 1.45 }}>
          Project workspace — design, bore logs, reports, and billing are scoped to this job.
        </p>
        <p style={{ margin: "10px 0 0" }}>
          <Link
            href={`/walk?projectId=${encodeURIComponent(projectId)}`}
            style={{
              display: "inline-block",
              color: "#0f172a",
              fontSize: 13,
              fontWeight: 700,
              textDecoration: "underline",
            }}
          >
            Field walk (mobile)
          </Link>
        </p>
      </header>
      <RedlineMap projectId={projectId} workspaceTitle={projectDisplayName} />
    </>
  );
}
