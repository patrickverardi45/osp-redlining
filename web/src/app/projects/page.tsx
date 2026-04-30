import Link from "next/link";

const projects = [
  {
    name: "Brenham Phase 5",
    href: "/projects/brenham-phase-5",
    status: "Active",
    location: "Brenham, TX",
    plannedFootage: "42,500 ft",
    drilledFootage: "31,880 ft",
    completion: "75%",
    boreLogs: "18",
    photos: "126",
    lastUpdated: "Today, 8:45 AM",
  },
  {
    name: "Dublin TX",
    href: "/projects/dublin-tx",
    status: "Review",
    location: "Dublin, TX",
    plannedFootage: "28,400 ft",
    drilledFootage: "26,950 ft",
    completion: "95%",
    boreLogs: "11",
    photos: "84",
    lastUpdated: "Yesterday, 4:20 PM",
  },
  {
    name: "San Antonio Test Build",
    href: "/projects/san-antonio-test-build",
    status: "Active",
    location: "San Antonio, TX",
    plannedFootage: "15,200 ft",
    drilledFootage: "6,100 ft",
    completion: "40%",
    boreLogs: "7",
    photos: "39",
    lastUpdated: "Apr 29, 2026",
  },
  {
    name: "Future Project",
    href: "/projects/future-project",
    status: "Not Started",
    location: "TBD",
    plannedFootage: "0 ft",
    drilledFootage: "0 ft",
    completion: "0%",
    boreLogs: "0",
    photos: "0",
    lastUpdated: "Not started",
  },
];

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
          {projects.map((project) => {
            const statusColor =
              project.status === "Active"
                ? "#166534"
                : project.status === "Review"
                  ? "#92400e"
                  : "#475569";
            const statusBackground =
              project.status === "Active"
                ? "#dcfce7"
                : project.status === "Review"
                  ? "#fef3c7"
                  : "#e2e8f0";

            return (
              <article
                key={project.href}
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
                    {project.status}
                  </span>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
                  <Metric label="Planned footage" value={project.plannedFootage} />
                  <Metric label="Drilled footage" value={project.drilledFootage} />
                  <Metric label="Completion" value={project.completion} />
                  <Metric label="Bore logs" value={project.boreLogs} />
                  <Metric label="Photos" value={project.photos} />
                  <Metric label="Last updated" value={project.lastUpdated} />
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
          })}
        </section>
      </div>
    </main>
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
