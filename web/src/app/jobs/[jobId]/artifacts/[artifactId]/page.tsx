type ArtifactDetailPageProps = {
  params?: {
    jobId?: string;
    artifactId?: string;
  };
};

export default function ArtifactDetailPage({ params }: ArtifactDetailPageProps) {
  const jobId = params?.jobId ?? "unknown";
  const artifactId = params?.artifactId ?? "unknown";

  return (
    <main style={{ padding: "1rem" }}>
      <h1 style={{ fontSize: "1.25rem", fontWeight: 600, marginBottom: "0.75rem" }}>
        Artifact Detail
      </h1>
      <p style={{ marginBottom: "0.25rem" }}>
        <strong>Job ID:</strong> {jobId}
      </p>
      <p style={{ marginBottom: "0.75rem" }}>
        <strong>Artifact ID:</strong> {artifactId}
      </p>
      <p>Artifact detail page not available yet.</p>
    </main>
  );
}
