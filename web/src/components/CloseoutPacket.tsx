"use client";

// CloseoutPacket V1.1 — client-safe language + field photo evidence.
// No AI calls. No state mutation. No backend changes. No billing math changes.
// Internal Nova language removed from all client-facing output.
// Photos: stationPhotos (backend-persisted) and geoTaggedPhotos (client-session GPS photos).
// Print: station photo thumbnails embedded via absolute same-origin URL
//        (window.location.origin + relative_url); geotagged blob-URL previews
//        pre-converted to data URLs by handlePrint and embedded into the print
//        HTML so they survive crossing into the about:blank popup
//        (PT.CO R1, 2026-05-21).

import React, { useState, useEffect, useCallback, useMemo } from "react";
import type { NovaSummary, PipelineDiagEntry, EngineeringPlanSignal, QaFlagItem } from "@/lib/types/nova";
import type { BackendState, GroupMatch, ExceptionCost, StationPhoto } from "@/lib/types/backend";
import { toMoney } from "@/lib/format/money";
import { formatNumber } from "@/lib/format/text";
// Export/read-only surface — must never call acceptSessionFromMutation.
import { appendSessionId, getStoredSessionId } from "@/lib/session";
import { apiFetch } from "@/lib/apiFetch";

// ── Types ─────────────────────────────────────────────────────────────────────

export type DrillPathRow = {
  id: string;
  startStation: string;
  endStation: string;
  lengthFt: number;
  cost: number;
  print: string;
  sourceFile: string;
  routeName: string;
};

/** Serialisable subset of GpsPhoto — File and blob URL stripped for cross-window safety. */
export type GeoTaggedPhoto = {
  id: string;
  filename: string;
  lat: number | null;
  lon: number | null;
  reason: "mapped" | "no_gps" | "unreadable";
  addedAt: number; // Date.now()
  previewUrl: string; // object URL — valid in modal, NOT across new windows
};

type ReviewOverride = {
  id: string;
  source_file: string;
  group_idx: number | null;
  issue_key: string;
  decision: string;
  reason: string;
  created_by: string;
  role: string;
  created_at: string;
};

export type CloseoutPacketProps = {
  activeJob: string;
  state: BackendState | undefined | null;
  selectedMatch: GroupMatch | null | undefined;
  effectiveFootage: number;
  numericCostPerFoot: number;
  baseBillingTotal: number;
  exceptionTotal: number;
  finalBillingTotal: number;
  exceptions: ExceptionCost[];
  drillPathRows: DrillPathRow[];
  novaSummary: NovaSummary;
  pipelineDiag: PipelineDiagEntry[];
  engineeringPlanSignals: EngineeringPlanSignal[];
  hasDesign: boolean;
  hasBoreFiles: boolean;
  hasGeneratedOutput: boolean;
  notes: string;
  /** Backend-persisted station photos. relative_url is safe for HTTP <img> embedding. */
  stationPhotos: StationPhoto[];
  /** Client-session geotagged photos. previewUrl is a blob URL — modal only. */
  geoTaggedPhotos: GeoTaggedPhoto[];
  /** Drilled ÷ planned footage from engineering takeoff (Reports). Null if no planned footage — not backend route completion_pct. */
  projectCompletionPercent: number | null;
  /** When true, the closeout checklist treats operator notes as satisfied without text */
  operatorNotesNotRequired?: boolean;
  /** When true, review decision actions are disabled (closeout locked server-side). */
  closeoutLocked?: boolean;
  /** Billing / closeout approval panel — when approved and checklist gates pass, status shows "Approved for Billing". */
  billingApproved?: boolean;
};

// ── Constants ─────────────────────────────────────────────────────────────────

const API_BASE = "";

// Client-safe status colours (same palette, no "Nova" label)
const STATUS_COLOR: Record<string, string> = {
  Ready: "#16a34a",
  "Needs Review": "#d97706",
  Blocked: "#dc2626",
  Reviewed: "#7c3aed",
};

const SEV_COLOR: Record<string, string> = {
  error: "#dc2626",
  warning: "#d97706",
  info: "#16a34a",
};

// Override decision translations — client-safe
const DECISION_LABEL: Record<string, string> = {
  Reviewed: "Reviewed",
  "Accepted Override": "Reviewed and Accepted",
  "Needs Rework": "Requires Rework",
};

/** Must match NovaSummaryCard override `decision` values / API. */
type OverrideDecision = "Reviewed" | "Accepted Override" | "Needs Rework";

const CLOSEOUT_ACTION_USER = { name: "Demo PM", role: "PM" } as const;

const CLOSEOUT_DECISION_OPTIONS: OverrideDecision[] = [
  "Reviewed",
  "Accepted Override",
  "Needs Rework",
];

const AUTO_REASON_CLOSEOUT: Record<OverrideDecision, string> = {
  Reviewed: "Reviewed in closeout packet.",
  "Accepted Override": "Accepted in closeout packet for closeout continuity.",
  "Needs Rework": "Marked for rework from closeout packet.",
};

// ── Status translation (internal → client-safe) ───────────────────────────────

function translateStatus(raw: string): string {
  switch (raw) {
    case "Blocked":      return "Requires Review Before Closeout";
    case "Needs Review": return "Review Required Before Billing";
    case "Ready":        return "Ready for Closeout Review";
    case "Reviewed":     return "Reviewed";
    default:             return raw;
  }
}

/** Same gates as Final Review Checklist rows except the status line itself (avoids circular logic). */
function allChecklistGatesComplete(
  hasDesign: boolean,
  hasBoreFiles: boolean,
  hasEngineeringPlans: boolean,
  allReviewResolved: boolean,
  hasPhotoEvidence: boolean,
  notesSatisfied: boolean,
): boolean {
  return (
    hasDesign &&
    hasBoreFiles &&
    hasEngineeringPlans &&
    allReviewResolved &&
    hasPhotoEvidence &&
    notesSatisfied
  );
}

type CloseoutReviewResolved = {
  label: string;
  color: string;
  checklistRowComplete: boolean;
};

/** Billing approval + checklist gates override Nova readiness when both are satisfied. */
function resolveCloseoutReviewDisplay(
  rawStatus: string,
  billingApproved: boolean,
  gatesComplete: boolean,
): CloseoutReviewResolved {
  // Keep packet status aligned with the shell's approval source:
  // once billing is approved, show approved client-facing status regardless
  // of internal checklist gate state.
  if (billingApproved) {
    return {
      label: "Ready for Billing",
      color: "#16a34a",
      checklistRowComplete: true,
    };
  }
  if (rawStatus === "Blocked") {
    return {
      label: "Requires Review Before Closeout",
      color: "#dc2626",
      checklistRowComplete: false,
    };
  }
  if (rawStatus === "Needs Review") {
    return {
      label: "Review Required Before Billing",
      color: "#d97706",
      checklistRowComplete: false,
    };
  }
  if (rawStatus === "Ready") {
    return {
      label: "Ready for Closeout Review",
      color: "#16a34a",
      checklistRowComplete: true,
    };
  }
  const label = translateStatus(rawStatus);
  const color = STATUS_COLOR[rawStatus] ?? "#64748b";
  const checklistRowComplete = rawStatus !== "Blocked" && rawStatus !== "Needs Review";
  return { label, color, checklistRowComplete };
}

function translateDecision(raw: string): string {
  return DECISION_LABEL[raw] ?? raw;
}

/** Same composite key as NovaSummaryCard `buildIssueId` — must match persisted `issue_key`. */
function buildIssueId(item: QaFlagItem, index: number): string {
  return [
    item.sourceFile || "unknown",
    item.severity,
    item.issue,
    item.rawReasons?.join("|") || "",
    index,
  ].join("::");
}

/** Decision counts as addressed for checklist / Sec. 4 (persisted or client-facing labels). */
function isResolvedReviewDecision(decision: string | undefined | null): boolean {
  const raw = decision == null ? "" : String(decision).trim();
  if (!raw) return false;
  if (raw === "Reviewed" || raw === "Accepted Override") return true;
  if (raw === "Reviewed and Accepted") return true;
  const lower = raw.toLowerCase();
  return (
    lower === "reviewed" ||
    lower === "accepted override" ||
    lower === "reviewed and accepted"
  );
}

function countUnresolvedActionableIssues(qaItems: QaFlagItem[], overrides: ReviewOverride[]): number {
  let n = 0;
  qaItems.forEach((q, i) => {
    if (q.severity === "info") return;
    const issueId = buildIssueId(q, i);
    const ov = overrides.find((o) => o.issue_key === issueId);
    if (!isResolvedReviewDecision(ov?.decision)) n += 1;
  });
  return n;
}

/** Copy for Sec. 11 checklist row + print checklist (must stay in sync with ok=allReviewResolved). */
function formatReviewNotesChecklistLabel(
  qaItems: QaFlagItem[],
  overrides: ReviewOverride[],
  allResolved: boolean,
): string {
  const actionableCount = qaItems.filter((q) => q.severity !== "info").length;
  if (actionableCount === 0) return "Review notes — none found";
  if (allResolved) return "Review notes addressed";
  const pending = countUnresolvedActionableIssues(qaItems, overrides);
  const n = pending > 0 ? pending : actionableCount;
  return `Review notes pending (${n} item${n !== 1 ? "s" : ""} requiring attention)`;
}

/** Every actionable (non-info) review item has an accepted / reviewed decision recorded. */
function allReviewItemsResolved(qaItems: QaFlagItem[], overrides: ReviewOverride[]): boolean {
  return qaItems.every((q, i) => {
    if (q.severity === "info") return true;
    const issueId = buildIssueId(q, i);
    const ov = overrides.find((o) => o.issue_key === issueId);
    return isResolvedReviewDecision(ov?.decision);
  });
}

function decisionColumnStyle(override: ReviewOverride | undefined): { label: string; color: string } {
  if (!override) {
    return { label: "Needs Review", color: "#d97706" };
  }
  const d = override.decision;
  if (d === "Needs Rework") return { label: d, color: "#dc2626" };
  if (isResolvedReviewDecision(d)) {
    const canon = String(d).trim();
    const isReviewedOnly =
      canon === "Reviewed" || canon.toLowerCase() === "reviewed";
    return {
      label: translateDecision(canon) ?? canon,
      color: isReviewedOnly ? "#2563eb" : "#16a34a",
    };
  }
  return { label: d, color: "#64748b" };
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function shortFile(path: string): string {
  return path.split(/[/\\]/).pop() || path;
}

// ── Print HTML builder ────────────────────────────────────────────────────────

function buildPrintHtml(
  props: CloseoutPacketProps,
  overrides: ReviewOverride[],
  dateStr: string,
  geoPhotoDataUrls: Map<string, string>,
): string {
  const {
    activeJob,
    state,
    effectiveFootage,
    numericCostPerFoot,
    baseBillingTotal,
    exceptionTotal,
    finalBillingTotal,
    exceptions,
    drillPathRows,
    novaSummary,
    engineeringPlanSignals,
    hasDesign,
    hasBoreFiles,
    notes,
    stationPhotos,
    geoTaggedPhotos,
    projectCompletionPercent,
    operatorNotesNotRequired = false,
    billingApproved = false,
  } = props;

  const routeName = state?.selected_route_name || state?.route_name || "—";
  const rawStatus = novaSummary.billingReadiness.status;
  const plans = state?.engineering_plans ?? [];
  const qaItems = novaSummary.qaFlags.items;

  const hasPhotoEvidence = stationPhotos.length > 0 || geoTaggedPhotos.length > 0;
  const mappedGpsPhotos = geoTaggedPhotos.filter((p) => p.reason === "mapped");

  function row(label: string, value: string): string {
    return `<tr><td style="font-weight:600;padding:5px 10px;border:1px solid #e2e8f0;background:#f8fafc;white-space:nowrap;font-size:12px">${label}</td><td style="padding:5px 10px;border:1px solid #e2e8f0;font-size:13px">${value}</td></tr>`;
  }

  function h2(title: string, num: string): string {
    return `<h2 style="font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:0.06em;color:#475569;margin:24px 0 8px;padding-bottom:4px;border-bottom:2px solid #e2e8f0">${num}. ${title}</h2>`;
  }

  const qaRows = qaItems
    .map((item, itemIndex) => {
    const sevColor = SEV_COLOR[item.severity] ?? "#64748b";
    // Rewrite severity label for client audience
    const sevLabel = item.severity === "error" ? "ACTION REQUIRED" : item.severity === "warning" ? "REVIEW RECOMMENDED" : "INFO";
    const issueId = buildIssueId(item, itemIndex);
    const ov = overrides.find((o) => o.issue_key === issueId);
    const dec = decisionColumnStyle(ov);
    return `<tr>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px"><span style="color:${sevColor};font-weight:700">${sevLabel}</span></td>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px;word-break:break-all">${shortFile(item.sourceFile)}</td>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px"><strong>${item.issue}</strong><br/><span style="color:#475569">${item.meaning}</span></td>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px">${item.resolution}</td>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px"><span style="color:${dec.color};font-weight:700">${dec.label}</span></td>
    </tr>`;
  })
    .join("");

  const overrideRows = overrides.map((ov) => {
    const clientDecision = translateDecision(ov.decision);
    const decColor = ov.decision === "Reviewed" ? "#7c3aed" : ov.decision === "Accepted Override" ? "#16a34a" : "#dc2626";
    return `<tr>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px;word-break:break-all">${shortFile(ov.source_file)}</td>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px">${ov.group_idx ?? "—"}</td>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px"><span style="color:${decColor};font-weight:700">${clientDecision}</span></td>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px">${ov.reason || "—"}</td>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px">${ov.created_by} (${ov.role})</td>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px">${ov.created_at ? new Date(ov.created_at).toLocaleString() : "—"}</td>
    </tr>`;
  }).join("");

  const exceptionRows = exceptions.filter((e) => e.label || e.amount).map((e) =>
    `<tr>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px">${e.label || "—"}</td>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px">${toMoney(Number.parseFloat(e.amount) || 0)}</td>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px">${e.note || "—"}</td>
    </tr>`
  ).join("");

  const drillRows = drillPathRows.map((r) =>
    `<tr>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px">${r.routeName}</td>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px">${r.print}</td>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px">${r.startStation}</td>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px">${r.endStation}</td>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px">${formatNumber(r.lengthFt)} ft</td>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px">${toMoney(r.cost)}</td>
    </tr>`
  ).join("");

  const planSignalRows = engineeringPlanSignals.map((sig) =>
    `<tr>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px;word-break:break-all">${shortFile(sig.source_file ?? "—")}</td>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px">${(sig.print_tokens ?? []).join(", ") || "—"}</td>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px">${(sig.route_hints ?? []).join(", ") || "—"}</td>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px">${sig.date || "—"}</td>
    </tr>`
  ).join("");

  // PT.CO R1 — print HTML is written into a window.open("", "_blank") popup
  // whose location is about:blank; relative URLs do not inherit the parent
  // origin in that context and silently fail (the existing onerror handler
  // hides broken images, which is why station photos previously did not
  // appear in print). Use window.location.origin to produce an absolute URL
  // the popup can resolve.
  const sameOrigin = typeof window !== "undefined" ? window.location.origin : "";
  // Station photos — backend-persisted; embed via absolute same-origin URL.
  const stationPhotoRows = stationPhotos.map((p) => {
    const imgSrc = `${sameOrigin}${p.relative_url}`;
    const thumb = `<img src="${imgSrc}" alt="${p.original_filename}" style="width:56px;height:56px;object-fit:cover;border-radius:4px;border:1px solid #e2e8f0" onerror="this.style.display='none'"/>`;
    return `<tr>
      <td style="padding:6px 8px;border:1px solid #e2e8f0;font-size:11px">${p.station_identity || "—"}</td>
      <td style="padding:6px 8px;border:1px solid #e2e8f0;font-size:11px">${p.uploaded_at ? new Date(p.uploaded_at).toLocaleString() : "—"}</td>
      <td style="padding:6px 8px;border:1px solid #e2e8f0">${thumb}</td>
    </tr>`;
  }).join("");

  // PT.CO R1 — geotagged GPS photos now include embedded previews via data URLs
  // pre-computed in handlePrint (fetch blob -> FileReader.readAsDataURL). If
  // conversion failed for a single photo (e.g., blob revoked / network drop),
  // that photo's row falls back to "Preview unavailable" metadata-only without
  // breaking the rest of the print.
  const gpsPhotoRows = geoTaggedPhotos.map((p) => {
    const latLon = (p.lat != null && p.lon != null) ? `${p.lat.toFixed(6)}, ${p.lon.toFixed(6)}` : "No GPS";
    const ts = new Date(p.addedAt).toLocaleString();
    const statusLabel2 = p.reason === "mapped" ? "Located" : p.reason === "no_gps" ? "No GPS data" : "Unreadable";
    const dataUrl = geoPhotoDataUrls.get(p.id);
    const previewCell = dataUrl
      ? `<img src="${dataUrl}" alt="${p.filename}" style="width:56px;height:56px;object-fit:cover;border-radius:4px;border:1px solid #e2e8f0"/>`
      : `<span style="font-size:10px;color:#94a3b8">Preview unavailable</span>`;
    return `<tr>
      <td style="padding:6px 8px;border:1px solid #e2e8f0;font-size:11px">${latLon}</td>
      <td style="padding:6px 8px;border:1px solid #e2e8f0;font-size:11px">${ts}</td>
      <td style="padding:6px 8px;border:1px solid #e2e8f0;font-size:11px">${statusLabel2}</td>
      <td style="padding:6px 8px;border:1px solid #e2e8f0">${previewCell}</td>
    </tr>`;
  }).join("");

  const checkItem = (ok: boolean, label: string) =>
    `<div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid #f1f5f9">
      <span style="font-size:14px;color:${ok ? "#16a34a" : "#94a3b8"}">${ok ? "✓" : "○"}</span>
      <span style="font-size:13px;color:#0f172a">${label}</span>
    </div>`;

  const hasEngineeringPlans = plans.length > 0;
  const allReviewResolved = allReviewItemsResolved(qaItems, overrides);

  const notesSatisfied =
    notes.trim().length > 0 || operatorNotesNotRequired === true;
  const notesCheckLabel =
    notes.trim().length > 0
      ? "Operator notes provided"
      : operatorNotesNotRequired
        ? "No operator notes required"
        : "Operator notes required";

  const checklistGatesComplete = allChecklistGatesComplete(
    hasDesign,
    hasBoreFiles,
    hasEngineeringPlans,
    allReviewResolved,
    hasPhotoEvidence,
    notesSatisfied,
  );
  const resolvedStatus = resolveCloseoutReviewDisplay(rawStatus, billingApproved, checklistGatesComplete);
  const statusLabel = resolvedStatus.label;
  const statusColor = resolvedStatus.color;

  const checklist = [
    checkItem(hasDesign, "Design file loaded"),
    checkItem(hasBoreFiles, "Field data files loaded"),
    checkItem(hasEngineeringPlans, `Engineering plans attached (${plans.length} plan${plans.length !== 1 ? "s" : ""})`),
    checkItem(
      allReviewResolved,
      formatReviewNotesChecklistLabel(qaItems, overrides, allReviewResolved),
    ),
    checkItem(overrides.length >= 0, overrides.length > 0 ? `Review decisions documented (${overrides.length} recorded)` : "No review decisions recorded"),
    checkItem(hasPhotoEvidence, hasPhotoEvidence ? `Field photo evidence attached (${stationPhotos.length + geoTaggedPhotos.length} photo${stationPhotos.length + geoTaggedPhotos.length !== 1 ? "s" : ""})` : "Field photo evidence not attached"),
    checkItem(resolvedStatus.checklistRowComplete, `Closeout review status: ${statusLabel}`),
    checkItem(notesSatisfied, notesCheckLabel),
  ].join("");

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Closeout Packet — ${activeJob}</title>
<style>
  @page { size: auto; margin: 0.5in; }
  * { box-sizing: border-box; }
  html, body { overflow-x: hidden; }
  body { font-family: Inter, ui-sans-serif, system-ui, sans-serif; color: #0f172a; background: #fff; margin: 0 auto; padding: 32px 40px; max-width: 980px; }
  h1 { font-size: 24px; font-weight: 900; margin: 0 0 4px; letter-spacing: -0.5px; }
  h2 { font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.06em; color: #475569; margin: 24px 0 8px; padding-bottom: 4px; border-bottom: 2px solid #e2e8f0; }
  table { width: 100%; border-collapse: collapse; margin-bottom: 8px; }
  th { text-align: left; padding: 6px 8px; background: #f1f5f9; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #475569; border: 1px solid #e2e8f0; }
  img { max-width: 100%; height: auto; }
  .meta { font-size: 12px; color: #64748b; margin-bottom: 20px; }
  .status-pill { display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 11px; font-weight: 700; color: #fff; background: ${statusColor}; }
  .disc { background: #fafbfc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 14px; font-size: 11px; color: #475569; margin: 8px 0; line-height: 1.5; }
  .footer { margin-top: 32px; padding-top: 12px; border-top: 1px solid #e2e8f0; font-size: 10px; color: #94a3b8; display: flex; justify-content: space-between; }
  @media print { body { padding: 0; max-width: none; margin: 0; } h2 { break-after: avoid; } table { break-inside: auto; table-layout: fixed; } tr { break-inside: avoid; page-break-inside: avoid; } img { break-inside: avoid; page-break-inside: avoid; } }
</style>
</head>
<body>
<h1>OSP Redlining — Closeout Packet</h1>
<div class="meta">
  <strong>Job:</strong> ${activeJob}&nbsp;&nbsp;
  <strong>Route:</strong> ${routeName}&nbsp;&nbsp;
  <strong>Generated:</strong> ${dateStr}&nbsp;&nbsp;
  <span class="status-pill">${statusLabel}</span>
</div>
<div class="disc">
  <strong>Review document only.</strong>
  This packet summarises available field records, billing data, review notes, and supporting evidence.
  It does not constitute final approval or compliance certification.
  Review decisions record human assessments and do not replace original field findings.
  All billing totals reflect values entered by the operator.
</div>

${h2("Job Summary", "1")}
<table><tbody>
  ${row("Job / Route", activeJob)}
  ${row("Selected Route", routeName)}
  ${row("Design File", hasDesign ? "Loaded" : "Not loaded")}
  ${row("Field Data Files", hasBoreFiles ? `${state?.loaded_field_data_files ?? 0} file(s) loaded` : "Not loaded")}
  ${row("Engineering Plans", plans.length > 0 ? `${plans.length} plan(s)` : "None attached")}
  ${row("Date Generated", dateStr)}
  ${row("Closeout Review Status", `<span style="color:${statusColor};font-weight:700">${statusLabel}</span>`)}
</tbody></table>
${novaSummary.billingReadiness.reasons.length > 0
  ? `<div class="disc"><strong>Review notes:</strong> ${novaSummary.billingReadiness.reasons.join("; ")}</div>`
  : ""}

${h2("Route / Production Summary", "2")}
<table><tbody>
  ${row("Total Route Footage", state?.total_length_ft ? `${formatNumber(state.total_length_ft)} ft` : "—")}
  ${row("Project completion %", projectCompletionPercent !== null ? `${formatNumber(projectCompletionPercent, 1)}%` : "—")}
  ${row("Covered Footage", state?.covered_length_ft ? `${formatNumber(state.covered_length_ft)} ft` : "—")}
  ${row("Drill Paths", String(drillPathRows.length))}
  ${row("Processed Groups", String(novaSummary.jobOverview.renderedGroups))}
  ${row("Groups Requiring Review", String(novaSummary.jobOverview.blockedGroups))}
  ${row("Total Field Data Groups", String(novaSummary.jobOverview.totalGroups))}
</tbody></table>

${drillPathRows.length > 0 ? `${h2("Drill Path Detail", "2a")}
<table>
  <thead><tr><th>Route</th><th>Print</th><th>Start Station</th><th>End Station</th><th>Length</th><th>Cost</th></tr></thead>
  <tbody>${drillRows}</tbody>
  <tfoot><tr>
    <td colspan="4" style="text-align:right;padding:5px 8px;border:1px solid #e2e8f0;font-weight:700;font-size:11px">Total</td>
    <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px;font-weight:700">${formatNumber(drillPathRows.reduce((s, r) => s + r.lengthFt, 0))} ft</td>
    <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px;font-weight:700">${toMoney(drillPathRows.reduce((s, r) => s + r.cost, 0))}</td>
  </tr></tfoot>
</table>` : ""}

${h2("Engineering Plan Evidence", "3")}
${plans.length === 0 && engineeringPlanSignals.length === 0
  ? `<p style="font-size:13px;color:#64748b">No engineering plans attached.</p>`
  : `<table><tbody>
  ${row("Plans Attached", String(plans.length))}
  ${novaSummary.planIntelligence.planSupportedBoreLogs.length > 0 ? row("Plan-Referenced Field Data", novaSummary.planIntelligence.planSupportedBoreLogs.map(shortFile).join(", ")) : ""}
</tbody></table>
${engineeringPlanSignals.length > 0 ? `<table style="margin-top:8px">
  <thead><tr><th>Plan File</th><th>Sheet / Print Tokens</th><th>Route References</th><th>Date</th></tr></thead>
  <tbody>${planSignalRows}</tbody>
</table>` : ""}`}

${h2("Field Photo Evidence", "4")}
${!hasPhotoEvidence
  ? `<p style="font-size:13px;color:#64748b;font-style:italic">Photo evidence not attached in this packet.</p>`
  : `${stationPhotos.length > 0 ? `<p style="font-size:11px;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:0.04em;margin:0 0 6px">Station Photos (${stationPhotos.length})</p>
<table>
  <thead><tr><th>Station</th><th>Uploaded</th><th>Preview</th></tr></thead>
  <tbody>${stationPhotoRows}</tbody>
</table>` : ""}
${geoTaggedPhotos.length > 0 ? `<p style="font-size:11px;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:0.04em;margin:12px 0 6px">Geotagged Field Photos (${geoTaggedPhotos.length} — ${mappedGpsPhotos.length} with GPS location)</p>
<table>
  <thead><tr><th>Coordinates (Lat, Lon)</th><th>Captured</th><th>Location Status</th><th>Preview</th></tr></thead>
  <tbody>${gpsPhotoRows}</tbody>
</table>` : ""}`}

${h2("Exceptions / Additional Costs", "5")}
${exceptions.filter((e) => e.label || e.amount).length === 0
  ? `<p style="font-size:13px;color:#64748b">No exceptions recorded.</p>`
  : `<table>
  <thead><tr><th>Label</th><th>Amount</th><th>Note / Context</th></tr></thead>
  <tbody>${exceptionRows}</tbody>
  <tfoot><tr>
    <td style="padding:5px 8px;border:1px solid #e2e8f0;font-weight:700;font-size:11px">Exception Total</td>
    <td style="padding:5px 8px;border:1px solid #e2e8f0;font-weight:700;font-size:11px">${toMoney(exceptionTotal)}</td>
    <td style="padding:5px 8px;border:1px solid #e2e8f0"></td>
  </tr></tfoot>
</table>`}

${h2("Billing Summary", "6")}
<table style="max-width:400px"><tbody>
  ${row("Effective Footage", `${formatNumber(effectiveFootage)} ft`)}
  ${row("Cost per Foot", toMoney(numericCostPerFoot))}
  ${row("Base Total", toMoney(baseBillingTotal))}
  ${row("Exception Total", toMoney(exceptionTotal))}
  ${row("Final Billing Total", `<strong style="font-size:15px">${toMoney(finalBillingTotal)}</strong>`)}
</tbody></table>
<div class="disc">Billing values are entered by the operator and have not been independently verified or approved by this system.</div>

${h2("Operator Notes", "7")}
${notes.trim()
  ? `<div style="background:#fafbfc;border:1px solid #e2e8f0;border-radius:8px;padding:12px 16px;font-size:13px;line-height:1.6;white-space:pre-wrap;color:#334155">${notes.trim()}</div>`
  : operatorNotesNotRequired
    ? `<p style="font-size:13px;color:#64748b;font-style:italic">No operator notes required.</p>`
    : `<p style="font-size:13px;color:#64748b;font-style:italic">No operator notes provided.</p>`}

<div class="footer">
  <span>OSP Redlining — Closeout Packet V1.1</span>
  <span>${dateStr}</span>
</div>
</body>
</html>`;
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function CloseoutPacket(props: CloseoutPacketProps) {
  const {
    activeJob,
    state,
    effectiveFootage,
    numericCostPerFoot,
    baseBillingTotal,
    exceptionTotal,
    finalBillingTotal,
    exceptions,
    drillPathRows,
    novaSummary,
    engineeringPlanSignals,
    hasDesign,
    hasBoreFiles,
    notes,
    stationPhotos,
    geoTaggedPhotos,
    projectCompletionPercent,
    operatorNotesNotRequired = false,
    closeoutLocked = false,
    billingApproved = false,
  } = props;

  const notesSatisfied =
    notes.trim().length > 0 || operatorNotesNotRequired === true;
  const notesCheckLabel =
    notes.trim().length > 0
      ? "Operator notes provided"
      : operatorNotesNotRequired
        ? "No operator notes required"
        : "Operator notes required";

  const [open, setOpen] = useState(false);
  const [overrides, setOverrides] = useState<ReviewOverride[]>([]);
  const [overridesLoaded, setOverridesLoaded] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [savingIssueId, setSavingIssueId] = useState<string | null>(null);
  const [rowSaveErrors, setRowSaveErrors] = useState<Record<string, string>>({});

  const rawStatus = novaSummary.billingReadiness.status;
  const qaItems = novaSummary.qaFlags.items;
  const overrideByIssueKey = useMemo(() => {
    const m = new Map<string, ReviewOverride>();
    for (const o of overrides) {
      if (o.issue_key) m.set(o.issue_key, o);
    }
    return m;
  }, [overrides]);
  const allReviewResolved = useMemo(
    () => allReviewItemsResolved(qaItems, overrides),
    [qaItems, overrides],
  );
  const plans = state?.engineering_plans ?? [];
  const hasPhotoEvidence = stationPhotos.length > 0 || geoTaggedPhotos.length > 0;
  const mappedGpsPhotos = geoTaggedPhotos.filter((p) => p.reason === "mapped");

  const checklistGatesComplete = useMemo(
    () =>
      allChecklistGatesComplete(
        hasDesign,
        hasBoreFiles,
        plans.length > 0,
        allReviewResolved,
        hasPhotoEvidence,
        notesSatisfied,
      ),
    [hasDesign, hasBoreFiles, plans.length, allReviewResolved, hasPhotoEvidence, notesSatisfied],
  );

  const closeoutReviewResolved = useMemo(
    () => resolveCloseoutReviewDisplay(rawStatus, billingApproved, checklistGatesComplete),
    [rawStatus, billingApproved, checklistGatesComplete],
  );

  const statusColor = closeoutReviewResolved.color;
  const statusDisplay = closeoutReviewResolved.label;

  // Fetch review decisions on open (read-only — same endpoint as NovaSummaryCard)
  useEffect(() => {
    if ((!open && !billingApproved) || overridesLoaded) return;
    async function load() {
      const sessionId = getStoredSessionId();
      if (!sessionId) { setOverridesLoaded(true); return; }
      try {
        const res = await apiFetch(appendSessionId(`${API_BASE}/api/nova-overrides`));
        if (!res.ok) { setOverridesLoaded(true); return; }
        const data = await res.json();
        if (Array.isArray(data.overrides)) setOverrides(data.overrides as ReviewOverride[]);
      } catch { /* network error — continue without */ }
      finally { setOverridesLoaded(true); }
    }
    load();
  }, [open, billingApproved, overridesLoaded]);

  const saveCloseoutIssueDecision = useCallback(
    async (
      item: QaFlagItem,
      index: number,
      decision: OverrideDecision,
      previousOverride: ReviewOverride | undefined,
    ) => {
      if (closeoutLocked) return;
      const issueId = buildIssueId(item, index);
      const record: ReviewOverride = {
        id: issueId,
        source_file: item.sourceFile,
        group_idx: null,
        issue_key: issueId,
        decision,
        reason: AUTO_REASON_CLOSEOUT[decision],
        created_by: CLOSEOUT_ACTION_USER.name,
        role: CLOSEOUT_ACTION_USER.role,
        created_at: new Date().toISOString(),
      };

      setSavingIssueId(issueId);
      setRowSaveErrors((prev) => {
        const next = { ...prev };
        delete next[issueId];
        return next;
      });
      setOverrides((prev) => [...prev.filter((o) => o.issue_key !== issueId), record]);

      const sessionId = getStoredSessionId();
      if (!sessionId) {
        setOverrides((prev) => {
          const filtered = prev.filter((o) => o.issue_key !== issueId);
          return previousOverride ? [...filtered, previousOverride] : filtered;
        });
        setRowSaveErrors((prev) => ({
          ...prev,
          [issueId]: "No session — sign in again.",
        }));
        setSavingIssueId(null);
        return;
      }

      try {
        const res = await apiFetch(`${API_BASE}/api/nova-overrides`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...record, session_id: sessionId }),
        });
        if (!res.ok) {
          const text = await res.text().catch(() => "");
          throw new Error(text.trim() || `Save failed (${res.status})`);
        }
      } catch (e) {
        setOverrides((prev) => {
          const filtered = prev.filter((o) => o.issue_key !== issueId);
          return previousOverride ? [...filtered, previousOverride] : filtered;
        });
        setRowSaveErrors((prev) => ({
          ...prev,
          [issueId]: e instanceof Error ? e.message : "Save failed.",
        }));
      } finally {
        setSavingIssueId(null);
      }
    },
    [closeoutLocked],
  );

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  // Lock body scroll
  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [open]);

  const handlePrint = useCallback(async () => {
    setGenerating(true);
    let popupWindow: Window | null = null;
    try {
      // PT.CO R1 — open the popup synchronously to preserve the user-gesture
      // context (popup blockers may reject window.open after an async await).
      // Write a placeholder while we preprocess geotagged photo data URLs.
      popupWindow = window.open("", "_blank", "width=960,height=800,scrollbars=yes");
      if (!popupWindow) {
        alert("Popup blocked. Allow popups for this page and try again.");
        return;
      }
      popupWindow.document.write(
        '<!DOCTYPE html><html><head><title>Generating closeout packet…</title></head>' +
          '<body style="font-family:Inter,ui-sans-serif,system-ui,sans-serif;padding:40px;color:#475569;font-size:14px">' +
          'Generating closeout packet, please wait…' +
          '</body></html>',
      );
      popupWindow.document.close();
      popupWindow.focus();

      // PT.CO R1 — convert geotagged photo blob URLs into data URLs so they
      // survive crossing into the about:blank popup. Blob URLs are
      // origin/document-scoped; data URLs are inline and unrestricted.
      // Per-photo failure is silent — that photo's row falls back to
      // "Preview unavailable" in buildPrintHtml via the Map lookup.
      const geoPhotoDataUrls = new Map<string, string>();
      await Promise.all(
        geoTaggedPhotos.map(async (photo) => {
          if (!photo.previewUrl) return;
          try {
            const resp = await fetch(photo.previewUrl);
            if (!resp.ok) return;
            const blob = await resp.blob();
            const dataUrl = await new Promise<string | null>((resolve) => {
              const reader = new FileReader();
              reader.onload = () => resolve(typeof reader.result === "string" ? reader.result : null);
              reader.onerror = () => resolve(null);
              reader.readAsDataURL(blob);
            });
            if (dataUrl) geoPhotoDataUrls.set(photo.id, dataUrl);
          } catch {
            // Per-photo failures are silent; print continues with whatever data URLs succeeded.
          }
        }),
      );

      const dateStr = new Date().toLocaleString("en-US", {
        year: "numeric", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit",
      });
      const html = buildPrintHtml(props, overrides, dateStr, geoPhotoDataUrls);
      // Guard against the popup having been closed during the await.
      if (popupWindow.closed) return;
      // Replace the placeholder with the real HTML.
      popupWindow.document.open();
      popupWindow.document.write(html);
      popupWindow.document.close();
      popupWindow.focus();

      const targetWindow = popupWindow;
      let fallbackCloseId: number | undefined;
      const closePrintWindow = () => {
        if (fallbackCloseId != null) {
          window.clearTimeout(fallbackCloseId);
          fallbackCloseId = undefined;
        }
        try {
          if (!targetWindow.closed) targetWindow.close();
        } catch {
          /* ignore */
        }
      };
      targetWindow.onafterprint = () => {
        closePrintWindow();
      };
      setTimeout(() => {
        try {
          targetWindow.print();
          fallbackCloseId = window.setTimeout(() => {
            closePrintWindow();
          }, 2500);
        } catch {
          closePrintWindow();
        }
      }, 400);
    } finally {
      setGenerating(false);
    }
  }, [props, overrides, geoTaggedPhotos]);

  // ── Button (collapsed) ────────────────────────────────────────────────────

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        style={{
          display: "flex", alignItems: "center", gap: 10, width: "100%",
          background: "#0f172a", border: "1.5px solid #1e3a5f", borderRadius: 12,
          padding: "12px 16px", cursor: "pointer", color: "#f1f5f9",
          fontSize: 14, fontWeight: 800, letterSpacing: "-0.01em",
          textAlign: "left", fontFamily: "inherit",
        }}
      >
        <svg viewBox="0 0 24 24" width={20} height={20} fill="none" stroke="#38bdf8" strokeWidth="1.6" style={{ flexShrink: 0 }}>
          <path d="M9 12h6M12 9v6M3 12a9 9 0 1 0 18 0 9 9 0 0 0-18 0z"/>
        </svg>
        <span style={{ flex: 1 }}>Generate Closeout Packet</span>
        <span style={{ background: statusColor, color: "#fff", borderRadius: 999, padding: "2px 8px", fontSize: 10, fontWeight: 700 }}>
          {statusDisplay}
        </span>
        <span style={{ color: "#475569", fontSize: 13 }}>›</span>
      </button>

      {/* ── Modal ──────────────────────────────────────────────────────────── */}
      {open && (
        <>
          <div
            aria-hidden="true"
            onClick={() => setOpen(false)}
            style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 8998 }}
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Closeout Packet Preview"
            style={{
              position: "fixed", inset: "32px auto",
              left: "50%", transform: "translateX(-50%)",
              width: "min(960px, 96vw)", maxHeight: "calc(100dvh - 64px)",
              background: "#ffffff", borderRadius: 16,
              boxShadow: "0 24px 80px rgba(0,0,0,0.28)",
              zIndex: 8999, display: "flex", flexDirection: "column",
              overflow: "hidden", fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
            }}
          >
            {/* Header */}
            <div style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              padding: "14px 20px", background: "#0f172a",
              borderBottom: "1px solid #1e293b", flexShrink: 0,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <svg viewBox="0 0 24 24" width={18} height={18} fill="none" stroke="#38bdf8" strokeWidth="1.8">
                  <path d="M9 12h6M12 9v6M3 12a9 9 0 1 0 18 0 9 9 0 0 0-18 0z"/>
                </svg>
                <span style={{ fontSize: 14, fontWeight: 800, color: "#f1f5f9", letterSpacing: "-0.01em" }}>
                  Closeout Packet V1.1
                </span>
                <span style={{ background: statusColor, color: "#fff", borderRadius: 999, padding: "2px 8px", fontSize: 10, fontWeight: 700 }}>
                  {statusDisplay}
                </span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 10, color: "#475569" }}>
                  {overridesLoaded ? "Review decisions loaded" : "Loading…"}
                </span>
                <button
                  onClick={handlePrint}
                  disabled={generating}
                  style={{
                    padding: "7px 14px", background: "#1d4ed8", color: "#fff",
                    border: "none", borderRadius: 8, fontSize: 12, fontWeight: 700,
                    cursor: generating ? "not-allowed" : "pointer",
                    opacity: generating ? 0.7 : 1, fontFamily: "inherit",
                  }}
                >
                  {generating ? "Opening…" : "Print / Save as PDF"}
                </button>
                <button
                  onClick={() => setOpen(false)}
                  aria-label="Close"
                  style={{
                    background: "transparent", border: "none", borderRadius: 6,
                    padding: "4px 8px", color: "#64748b", fontSize: 16, lineHeight: 1, cursor: "pointer",
                  }}
                >
                  ✕
                </button>
              </div>
            </div>

            {/* Body */}
              <div style={{ flex: 1, overflowY: "auto", padding: "24px 28px", background: "#fff", color: "#0f172a", fontSize: 13, lineHeight: 1.6 }}>

              {closeoutLocked ? (
                <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, padding: "10px 14px", marginBottom: 16, fontSize: 12, color: "#991b1b", fontWeight: 600 }}>
                  Closeout is locked — review decisions cannot be changed until an admin or manager unlocks the workspace.
                </div>
              ) : null}

              {/* Disclaimer */}
              <div style={{ background: "#fefce8", border: "1px solid #fde68a", borderRadius: 8, padding: "10px 14px", marginBottom: 20, fontSize: 12, color: "#78350f", lineHeight: 1.5 }}>
                <strong>Review document only.</strong>{" "}
                This packet summarises available field records, billing data, review notes, and supporting evidence.
                It does not constitute final approval or compliance certification.
                Review decisions record human assessments and do not replace original field findings.
              </div>

              {/* ── 1. Job Summary ────────────────────────────────────────── */}
              <PS num="1" title="Job Summary">
                <KVTable rows={[
                  ["Job / Route", activeJob],
                  ["Selected Route", state?.selected_route_name || state?.route_name || "—"],
                  ["Design File", hasDesign ? "Loaded" : "Not loaded"],
                  ["Field Data Files", hasBoreFiles ? `${state?.loaded_field_data_files ?? 0} file(s) loaded` : "Not loaded"],
                  ["Engineering Plans", plans.length > 0 ? `${plans.length} plan(s)` : "None attached"],
                  ["Date Generated", new Date().toLocaleString("en-US", { year: "numeric", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit" })],
                  ["Closeout Review Status", statusDisplay],
                ]} statusCell={{ rowLabel: "Closeout Review Status", color: statusColor }} />
                {novaSummary.billingReadiness.reasons.length > 0 && (
                  <div style={{ marginTop: 8, background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 6, padding: "8px 12px", fontSize: 12, color: "#475569" }}>
                    <strong>Review notes: </strong>{novaSummary.billingReadiness.reasons.join("; ")}
                  </div>
                )}
              </PS>

              {/* ── 2. Route / Production Summary ─────────────────────────── */}
              <PS num="2" title="Route / Production Summary">
                <KVTable rows={[
                  ["Total Route Footage", state?.total_length_ft ? `${formatNumber(state.total_length_ft)} ft` : "—"],
                  ["Project completion %", projectCompletionPercent !== null ? `${formatNumber(projectCompletionPercent, 1)}%` : "—"],
                  ["Covered Footage", state?.covered_length_ft ? `${formatNumber(state.covered_length_ft)} ft` : "—"],
                  ["Drill Paths", String(drillPathRows.length)],
                  ["Processed Groups", String(novaSummary.jobOverview.renderedGroups)],
                  ["Groups Requiring Review", String(novaSummary.jobOverview.blockedGroups)],
                  ["Total Field Data Groups", String(novaSummary.jobOverview.totalGroups)],
                ]} />
                {drillPathRows.length > 0 && (
                  <div style={{ marginTop: 12 }}>
                    <SectionSubtitle>Drill Path Detail</SectionSubtitle>
                    <div style={{ overflowX: "auto" }}>
                      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                        <thead>
                          <tr>{["Route", "Print", "Start", "End", "Length", "Cost"].map((h) => <th key={h} style={thS}>{h}</th>)}</tr>
                        </thead>
                        <tbody>
                          {drillPathRows.map((r) => (
                            <tr key={r.id}>
                              <td style={tdS}>{r.routeName}</td>
                              <td style={tdS}>{r.print}</td>
                              <td style={tdS}>{r.startStation}</td>
                              <td style={tdS}>{r.endStation}</td>
                              <td style={tdS}>{formatNumber(r.lengthFt)} ft</td>
                              <td style={tdS}>{toMoney(r.cost)}</td>
                            </tr>
                          ))}
                          <tr style={{ borderTop: "2px solid #cbd5e1" }}>
                            <td colSpan={4} style={{ ...tdS, textAlign: "right", fontWeight: 700 }}>Total</td>
                            <td style={{ ...tdS, fontWeight: 700 }}>{formatNumber(drillPathRows.reduce((s, r) => s + r.lengthFt, 0))} ft</td>
                            <td style={{ ...tdS, fontWeight: 700 }}>{toMoney(drillPathRows.reduce((s, r) => s + r.cost, 0))}</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </PS>

              {/* ── 3. Engineering Plan Evidence ─────────────────────────── */}
              <PS num="3" title="Engineering Plan Evidence">
                {plans.length === 0 && engineeringPlanSignals.length === 0 ? (
                  <Empty>No engineering plans attached.</Empty>
                ) : (
                  <>
                    <KVTable rows={[
                      ["Plans Attached", String(plans.length)],
                      ...(novaSummary.planIntelligence.planSupportedBoreLogs.length > 0
                        ? [["Plan-Referenced Field Data", novaSummary.planIntelligence.planSupportedBoreLogs.map(shortFile).join(", ")]] as [string, string][]
                        : []),
                    ]} />
                    {engineeringPlanSignals.length > 0 && (
                      <div style={{ marginTop: 10 }}>
                        <SectionSubtitle>Plan Signals</SectionSubtitle>
                        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                          <thead><tr>{["Plan File", "Sheet / Print Tokens", "Route References", "Date"].map((h) => <th key={h} style={thS}>{h}</th>)}</tr></thead>
                          <tbody>
                            {engineeringPlanSignals.map((sig, i) => (
                              <tr key={i}>
                                <td style={tdS}>{shortFile(sig.source_file ?? "—")}</td>
                                <td style={tdS}>{(sig.print_tokens ?? []).join(", ") || "—"}</td>
                                <td style={tdS}>{(sig.route_hints ?? []).join(", ") || "—"}</td>
                                <td style={tdS}>{sig.date || "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </>
                )}
              </PS>

              {/* ── 4. Field Photo Evidence ──────────────────────────────── */}
              <PS num="4" title="Field Photo Evidence">
                {!hasPhotoEvidence ? (
                  <Empty>Photo evidence not attached in this packet.</Empty>
                ) : (
                  <>
                    {/* Station Photos — backend-persisted */}
                    {stationPhotos.length > 0 && (
                      <>
                        <SectionSubtitle>Station Photos ({stationPhotos.length})</SectionSubtitle>
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 10, marginBottom: 12 }}>
                          {stationPhotos.map((photo) => {
                            const imgSrc = API_BASE ? `${API_BASE}${photo.relative_url}` : photo.relative_url;
                            return (
                              <div key={photo.photo_id} style={{ border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden", background: "#f8fafc" }}>
                                <div style={{ height: 120, background: "#e2e8f0", display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden" }}>
                                  <img
                                    src={imgSrc}
                                    alt={photo.original_filename}
                                    style={{ width: "100%", height: "100%", objectFit: "cover" }}
                                    onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                                  />
                                </div>
                                <div style={{ padding: "8px 10px" }}>
                                  <div style={{ fontSize: 11, fontWeight: 700, color: "#0f172a", marginBottom: 2 }}>{photo.station_identity || "—"}</div>
                                  <div style={{ fontSize: 10, color: "#64748b", marginBottom: 2, wordBreak: "break-all" }}>{photo.original_filename}</div>
                                  {photo.uploaded_at && (
                                    <div style={{ fontSize: 10, color: "#94a3b8" }}>{new Date(photo.uploaded_at).toLocaleString()}</div>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </>
                    )}

                    {/* Geotagged GPS Photos — client-session */}
                    {geoTaggedPhotos.length > 0 && (
                      <>
                        <SectionSubtitle>
                          Geotagged Field Photos ({geoTaggedPhotos.length} — {mappedGpsPhotos.length} with GPS location)
                        </SectionSubtitle>
                        <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 6, padding: "6px 10px", marginBottom: 8, fontSize: 11, color: "#64748b" }}>
                          These photos are session-only and will not persist after refresh.
                          Previews are embedded into the printed/saved closeout packet (PT.CO R1).
                        </div>
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 10, marginBottom: 12 }}>
                          {geoTaggedPhotos.map((photo) => (
                            <div key={photo.id} style={{ border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden", background: "#f8fafc" }}>
                              <div style={{ height: 100, background: "#e2e8f0", display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden" }}>
                                {photo.previewUrl ? (
                                  <img
                                    src={photo.previewUrl}
                                    alt={photo.filename}
                                    style={{ width: "100%", height: "100%", objectFit: "cover" }}
                                    onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                                  />
                                ) : (
                                  <svg viewBox="0 0 24 24" width={28} height={28} fill="none" stroke="#94a3b8" strokeWidth="1.2">
                                    <rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="12" cy="12" r="3"/>
                                  </svg>
                                )}
                              </div>
                              <div style={{ padding: "7px 9px" }}>
                                <div style={{ fontSize: 10, fontWeight: 700, color: "#0f172a", marginBottom: 2, wordBreak: "break-all" }}>{photo.filename}</div>
                                {photo.lat != null && photo.lon != null ? (
                                  <div style={{ fontSize: 10, color: "#475569" }}>
                                    {photo.lat.toFixed(5)}, {photo.lon.toFixed(5)}
                                  </div>
                                ) : (
                                  <div style={{ fontSize: 10, color: "#94a3b8" }}>No GPS data</div>
                                )}
                                <div style={{ fontSize: 10, color: "#94a3b8", marginTop: 2 }}>
                                  {new Date(photo.addedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </>
                    )}
                  </>
                )}
              </PS>

              {/* ── 5. Exceptions / Additional Costs ─────────────────────── */}
              <PS num="5" title="Exceptions / Additional Costs">
                {exceptions.filter((e) => e.label || e.amount).length === 0 ? (
                  <Empty>No exceptions recorded.</Empty>
                ) : (
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                    <thead><tr>{["Label", "Amount", "Note / Context"].map((h) => <th key={h} style={thS}>{h}</th>)}</tr></thead>
                    <tbody>
                      {exceptions.filter((e) => e.label || e.amount).map((e) => (
                        <tr key={e.id}>
                          <td style={tdS}>{e.label || "—"}</td>
                          <td style={tdS}>{toMoney(Number.parseFloat(e.amount) || 0)}</td>
                          <td style={tdS}>{e.note || "—"}</td>
                        </tr>
                      ))}
                      <tr style={{ borderTop: "2px solid #cbd5e1" }}>
                        <td style={{ ...tdS, fontWeight: 700 }}>Exception Total</td>
                        <td style={{ ...tdS, fontWeight: 700 }}>{toMoney(exceptionTotal)}</td>
                        <td style={tdS} />
                      </tr>
                    </tbody>
                  </table>
                )}
              </PS>

              {/* ── 6. Billing Summary ────────────────────────────────────── */}
              <PS num="6" title="Billing Summary">
                <KVTable rows={[
                  ["Effective Footage", `${formatNumber(effectiveFootage)} ft`],
                  ["Cost per Foot", toMoney(numericCostPerFoot)],
                  ["Base Total", toMoney(baseBillingTotal)],
                  ["Exception Total", toMoney(exceptionTotal)],
                  ["Final Billing Total", toMoney(finalBillingTotal)],
                ]} boldLastRow />
                <div style={{ marginTop: 8, background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 6, padding: "8px 12px", fontSize: 11, color: "#475569" }}>
                  Billing values are entered by the operator and have not been independently verified or approved by this system.
                </div>
              </PS>

              {/* ── 7. Operator Notes ────────────────────────────────────── */}
              <PS num="7" title="Operator Notes">
                {notes.trim() ? (
                  <div style={{ background: "#fafbfc", border: "1px solid #e2e8f0", borderRadius: 8, padding: "12px 16px", fontSize: 13, lineHeight: 1.6, whiteSpace: "pre-wrap", color: "#334155" }}>
                    {notes.trim()}
                  </div>
                ) : operatorNotesNotRequired ? (
                  <Empty>No operator notes required.</Empty>
                ) : (
                  <Empty>No operator notes provided.</Empty>
                )}
              </PS>

              {/* Footer */}
              <div style={{ marginTop: 28, paddingTop: 12, borderTop: "1px solid #e2e8f0", fontSize: 11, color: "#94a3b8", display: "flex", justifyContent: "space-between" }}>
                <span>OSP Redlining — Closeout Packet V1.1</span>
                <span>{new Date().toISOString().slice(0, 10)}</span>
              </div>
            </div>
          </div>
        </>
      )}
    </>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────────

const tdS: React.CSSProperties = { padding: "5px 8px", border: "1px solid #e2e8f0", fontSize: 12, verticalAlign: "top", lineHeight: 1.45 };
const thS: React.CSSProperties = { textAlign: "left", padding: "5px 8px", background: "#f1f5f9", fontSize: 10, fontWeight: 700, textTransform: "uppercase" as const, letterSpacing: "0.04em", color: "#475569", border: "1px solid #e2e8f0" };

function PS({ num, title, children }: { num: string; title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 20 }}>
      <h2 style={{ fontSize: 11, fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.06em", color: "#475569", margin: "0 0 8px", paddingBottom: 4, borderBottom: "2px solid #e2e8f0", display: "flex", gap: 6, alignItems: "center" }}>
        <span style={{ background: "#1e293b", color: "#94a3b8", borderRadius: 4, padding: "1px 6px", fontSize: 10 }}>{num}</span>
        {title}
      </h2>
      {children}
    </div>
  );
}

function SectionSubtitle({ children }: { children: React.ReactNode }) {
  return <div style={{ fontSize: 11, fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>{children}</div>;
}

function KVTable({ rows, statusCell, boldLastRow }: { rows: [string, string][]; statusCell?: { rowLabel: string; color: string }; boldLastRow?: boolean }) {
  return (
    <table style={{ borderCollapse: "collapse", fontSize: 13 }}>
      <tbody>
        {rows.map(([label, value], i) => {
          const isStatus = statusCell && label === statusCell.rowLabel;
          const isLast = boldLastRow && i === rows.length - 1;
          return (
            <tr key={label}>
              <td style={{ padding: "5px 10px", border: "1px solid #e2e8f0", background: "#f8fafc", fontWeight: 600, whiteSpace: "nowrap", fontSize: 12, color: "#334155" }}>{label}</td>
              <td style={{ padding: "5px 10px", border: "1px solid #e2e8f0", color: isStatus ? statusCell!.color : "#0f172a", fontWeight: isLast || isStatus ? 700 : 400, fontSize: isLast ? 15 : 13 }}>{value}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function CI({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 0", borderBottom: "1px solid #f1f5f9" }}>
      <span style={{ fontSize: 15, color: ok ? "#16a34a" : "#94a3b8", flexShrink: 0 }}>{ok ? "✓" : "○"}</span>
      <span style={{ fontSize: 13, color: "#0f172a" }}>{label}</span>
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p style={{ fontSize: 13, color: "#94a3b8", fontStyle: "italic", margin: "4px 0" }}>{children}</p>;
}
