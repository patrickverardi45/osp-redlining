"use client";

import type { JobDetail } from "@/lib/api";

type OfficeMapReviewPanelProps = {
  job: JobDetail;
};

export default function OfficeMapReviewPanel({ job }: OfficeMapReviewPanelProps) {
  return (
    <section>
      <h2 className="text-base font-semibold text-gray-800 mb-3">Map Review</h2>
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <p className="text-sm text-gray-600">
          Map review panel is unavailable for this job.
        </p>
        <p className="mt-2 text-xs text-gray-500">Job ID: {job.id}</p>
      </div>
    </section>
  );
}
