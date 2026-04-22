// web/src/lib/statusConfig.ts
// Shared badge colour classes used by JobsPipelineView, JobsTable, WorkflowActionsPanel, etc.

export const STATUS_BADGE_CLASSES: Record<string, string> = {
  draft: "bg-gray-100 text-gray-600",
  ready_for_field: "bg-indigo-100 text-indigo-700",
  in_progress: "bg-blue-100 text-blue-700",
  field_complete: "bg-cyan-100 text-cyan-700",
  qa_review: "bg-yellow-100 text-yellow-700",
  redlines_ready: "bg-purple-100 text-purple-700",
  closeout_ready: "bg-orange-100 text-orange-700",
  billed: "bg-green-100 text-green-700",
  // legacy / fallback values
  pending: "bg-gray-100 text-gray-700",
  complete: "bg-green-100 text-green-700",
  on_hold: "bg-yellow-100 text-yellow-700",
};
