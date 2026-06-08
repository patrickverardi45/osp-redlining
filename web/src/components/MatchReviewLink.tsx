"use client";

// A+B+C gate: a Match Review navigation link that DISABLES itself while the background
// MRQ preseed is still building this session's PDF evidence (read from
// /api/current-state -> mrq_preseed.status). Prevents a user from opening Match Review
// mid-build (which would otherwise pay the heavy cold build on the request path -> 504).
// Falls back to a normal enabled <Link> whenever preseed is NOT actively building
// (ready / skipped / failed / absent / no session). Additive + reversible: when preseed
// never runs there is no mrq_preseed key, so this stays a normal link. The backend guard
// at /api/match-review-queue is the authoritative 504 backstop; this is the UX layer.

import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/apiFetch";
import { peekSessionId } from "@/lib/session";

const PREPARING_LABEL = "Match Review preparing — building PDF evidence";
const POLL_MS = 4000;

export default function MatchReviewLink({
  href,
  projectId,
  sessionId,
  className,
  style,
  children,
}: {
  href: string;
  projectId?: string | null;
  sessionId?: string | null;
  className?: string;
  style?: CSSProperties;
  children: ReactNode;
}) {
  const [preparing, setPreparing] = useState(false);
  const aliveRef = useRef(true);

  useEffect(() => {
    aliveRef.current = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    // Explicit session_id wins; otherwise resolve the project-scoped workspace session
    // (never minted here — peekSessionId only reads). No session => nothing to gate.
    const sid = (sessionId ?? "").trim() || peekSessionId(projectId ?? undefined);
    if (!sid) {
      setPreparing(false);
      return () => {
        aliveRef.current = false;
      };
    }
    const poll = async () => {
      try {
        const url = `/api/current-state?session_id=${encodeURIComponent(sid)}`;
        const res = await apiFetch(url, {}, "mrq_gate_current_state");
        if (aliveRef.current && res.ok) {
          const j = (await res.json()) as { mrq_preseed?: { status?: string } };
          const st = j?.mrq_preseed?.status;
          // Only "scheduled" / "building" gate the button; ready/skipped/failed/absent
          // enable it (never block forever).
          setPreparing(st === "scheduled" || st === "building");
        }
      } catch {
        // Network error must NOT trap the user behind a disabled button — leave enabled.
        if (aliveRef.current) setPreparing(false);
      }
      if (aliveRef.current) timer = setTimeout(poll, POLL_MS);
    };
    void poll();
    return () => {
      aliveRef.current = false;
      if (timer) clearTimeout(timer);
    };
  }, [projectId, sessionId]);

  if (preparing) {
    return (
      <button type="button" disabled className={className} style={style} title={PREPARING_LABEL}>
        {PREPARING_LABEL}
      </button>
    );
  }
  return (
    <Link href={href} className={className} style={style}>
      {children}
    </Link>
  );
}
