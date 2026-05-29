// web/src/app/trust-ledger/page.tsx
//
// Read-only Trust Ledger review surface (KMZ Automatic Redline Placement).
// Mirrors /match-review: a thin client page that reads session_id / projectId
// from the URL and renders the TrustLedgerPanel. AuthGuard (root layout) gates
// access. Reached by direct URL or the cross-link on /match-review; pass
// ?projectId=<slug> to bind to that project's workspace session.

"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import TrustLedgerPanel from "@/components/TrustLedgerPanel";

function TrustLedgerInner() {
  const params = useSearchParams();
  const sessionId = params.get("session_id");
  const projectId = params.get("projectId");
  // Carry the same context (session_id / projectId) to the sibling review surface.
  const query = params.toString();
  const matchReviewHref = query ? `/match-review?${query}` : "/match-review";
  return (
    <>
      <div style={{ marginBottom: 16 }}>
        <Link href={matchReviewHref} className="tl-btn tl-btn-ghost" style={{ fontSize: 12 }}>
          Match Review →
        </Link>
      </div>
      <TrustLedgerPanel sessionId={sessionId} projectId={projectId} />
    </>
  );
}

export default function TrustLedgerPage() {
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
            <h1 className="tl-h1">Trust Ledger</h1>
            <p className="tl-subtle" style={{ margin: 0 }}>
              Read-only proof verdict for every bore-log placement in the active workspace session:
              proven from evidence, abstained, or missing proof. Route-index evidence and the plan-sheet
              (PSG) warning are shown separately, never merged.
            </p>
          </div>
          <Link href="/projects" className="tl-btn tl-btn-ghost" style={{ whiteSpace: "nowrap" }}>
            ← Projects
          </Link>
        </header>
        <Suspense fallback={null}>
          <TrustLedgerInner />
        </Suspense>
      </div>
    </main>
  );
}
