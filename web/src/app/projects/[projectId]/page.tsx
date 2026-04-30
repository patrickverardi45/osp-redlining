import Link from "next/link";
import RedlineMap from "@/components/RedlineMap";

type ProjectPageProps = {
  params: Promise<{
    projectId: string;
  }>;
};

export default async function ProjectPage({ params }: ProjectPageProps) {
  const { projectId } = await params;

  return (
    <>
      <header style={{ borderBottom: "1px solid #dbe4ee", background: "#ffffff", padding: "14px 20px", fontFamily: "Arial, sans-serif" }}>
        <Link href="/" style={{ color: "#334155", fontSize: 13, fontWeight: 700, textDecoration: "none" }}>
          Back to Dashboard
        </Link>
        <h1 style={{ margin: "8px 0 0", color: "#0f172a", fontSize: 20, lineHeight: 1.2 }}>
          Project Workspace: {projectId}
        </h1>
      </header>
      <RedlineMap />
    </>
  );
}
