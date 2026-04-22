const fs = require("fs");
const path = require("path");

const FILES = [
  "web/src/lib/api.ts",
  "web/src/lib/closeoutReadiness.ts",
  "web/src/lib/packageSections.ts",
  "web/src/lib/qaValidation.ts",
  "web/src/lib/workflowTransitions.ts",
  "web/src/lib/statusConfig.ts",

  "web/src/app/jobs/page.tsx",
  "web/src/app/jobs/[jobId]/page.tsx",
  "web/src/app/jobs/[jobId]/artifacts/[artifactId]/page.tsx",

  "web/src/components/office/ArtifactDetailCard.tsx",
  "web/src/components/office/ArtifactJobContextCard.tsx",
  "web/src/components/office/ArtifactsPanel.tsx",
  "web/src/components/office/AttentionJobsPanel.tsx",
  "web/src/components/office/CloseoutContentSummaryPanel.tsx",
  "web/src/components/office/CloseoutReadinessPanel.tsx",
  "web/src/components/office/ExceptionSummaryPanel.tsx",
  "web/src/components/office/ExportPreviewSummaryPanel.tsx",
  "web/src/components/office/JobHeader.tsx",
  "web/src/components/office/JobStatusActionButtons.tsx",
  "web/src/components/office/JobsPipelineView.tsx",
  "web/src/components/office/JobsSummaryCards.tsx",
  "web/src/components/office/JobsTable.tsx",
  "web/src/components/office/OfficeMapReviewPanel.tsx",
  "web/src/components/office/OpenIssuesPanel.tsx",
  "web/src/components/office/PackageBlockersPanel.tsx",
  "web/src/components/office/PackageSectionsPanel.tsx",
  "web/src/components/office/QAHealthBadge.tsx",
  "web/src/components/office/QAValidationSummaryPanel.tsx",
  "web/src/components/office/ReportActionsPanel.tsx",
  "web/src/components/office/RouteListPanel.tsx",
  "web/src/components/office/SessionCoveragePanel.tsx",
  "web/src/components/office/SessionListPanel.tsx",
  "web/src/components/office/ValidationIssuesPanel.tsx",
  "web/src/components/office/WorkflowActionsPanel.tsx",
];

for (const file of FILES) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
}

console.log("✓ All office file pathways created.");