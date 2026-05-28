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
  return <MatchReviewQueuePanel sessionId={sessionId} />;
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
