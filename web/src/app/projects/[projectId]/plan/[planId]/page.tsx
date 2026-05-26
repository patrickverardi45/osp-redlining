"use client";

/**
 * PDF Plan Mode — Step 1 route.
 *
 * Dedicated read-only PDF page viewer at:
 *   /projects/[projectId]/plan/[planId]
 *
 * The viewer is intentionally isolated from the existing project workspace
 * (which mounts ModernHeroMap + Leaflet at /projects/[projectId]).  No
 * shared layout — this page inherits only the root app/layout.tsx shell.
 *
 * Authoritative design: wiki/sprints/pdf-plan-mode/step-1-ratification-packet
 * (Pending ingestion — current spec lives in the chat-history ratification
 * packet that authorized this ship.)
 */

import { use } from "react";
import PdfPlanCanvas from "@/components/PdfPlanCanvas";

type PdfPlanPageProps = {
  params: Promise<{
    projectId: string;
    planId: string;
  }>;
};

export default function PdfPlanPage({ params }: PdfPlanPageProps) {
  const { projectId, planId } = use(params);
  return <PdfPlanCanvas projectId={projectId} planId={planId} />;
}
