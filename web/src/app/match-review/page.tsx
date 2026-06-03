// web/src/app/match-review/page.tsx
//
// Read-only Match Review Queue review surface. Auth is enforced globally by
// AuthGuard in the root layout. Renders the queue (Slice B + C1) with the
// Plan Sheet Graph precision-evidence badge. No route/matching behavior here —
// observation only.

"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import MatchReviewQueuePanel from "@/components/MatchReviewQueuePanel";

function MatchReviewInner() {
  const params = useSearchParams();
  const sessionId = params.get("session_id");
  // Optional ?projectId=<slug> enables read-only "View on map" deep-links into
  // the live ModernHeroMap (/projects/<projectId>?focus=<source_file>). When
  // absent, the panel simply omits the link — projectId is never guessed.
  const projectId = params.get("projectId");
  // Carry the same context (session_id / projectId) to the sibling review surface.
  const query = params.toString();
  const trustLedgerHref = query ? `/trust-ledger?${query}` : "/trust-ledger";
  // Back-to-Workspace deep link. Only when projectId is known (never guessed);
  // preserves session_id so the workspace rebinds to the same session. When
  // projectId is absent the header "← Projects" link remains the fallback.
  const workspaceHref = projectId
    ? sessionId
      ? `/projects/${encodeURIComponent(projectId)}?session_id=${encodeURIComponent(sessionId)}`
      : `/projects/${encodeURIComponent(projectId)}`
    : null;
  return (
    <>
      <div style={{ marginBottom: 16, display: "flex", gap: 8, flexWrap: "wrap" }}>
        {workspaceHref ? (
          <Link href={workspaceHref} className="tl-btn tl-btn-primary" style={{ fontSize: 12 }}>
            ← Back to Workspace
          </Link>
        ) : null}
        <Link href={trustLedgerHref} className="tl-btn tl-btn-ghost" style={{ fontSize: 12 }}>
          Trust Ledger →
        </Link>
      </div>
      <MatchReviewQueuePanel sessionId={sessionId} projectId={projectId} />
    </>
  );
}

export default function MatchReviewPage() {
  return (
    <main className="tl-page">
      <div className="tl-page-inner">
        <header
          style={{
            marginBottom: 24,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            gap: 16,
            flexWrap: "wrap",
          }}
        >
          <div>
            <div className="tl-eyebrow">Office Review</div>
            <h1 className="tl-h1">Match Review Queue</h1>
            <p className="tl-subtle" style={{ margin: 0 }}>
              Read-only operator review of route-matching outcomes for the active workspace
              session. Plan-sheet evidence is shown only where the backend flags it.
            </p>
          </div>
          <Link href="/projects" className="tl-btn tl-btn-ghost" style={{ whiteSpace: "nowrap" }}>
            ← Projects
          </Link>
        </header>

        <Suspense fallback={null}>
          <MatchReviewInner />
        </Suspense>
      </div>
    </main>
  );
}
