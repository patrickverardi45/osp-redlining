// Nova Phase 1 — deterministic job intelligence builder.
// Pure function. No side effects, no API calls, no mutations.
// Phase 1.2: QA flags carry structured issue/meaning/resolution explanations.
// Phase 1.3: Billing readiness with Blocked/Needs Review/Ready logic,
//            source-file-specific reason strings, and human-readable statusLabel.

import type { PipelineDiagEntry, EngineeringPlanSignal, NovaSummary, QaFlagItem } from "@/lib/types/nova";
import type { ExceptionCost } from "@/lib/types/backend";

/**
 * Ambiguity statuses that require operator review or action.
 */
const REVIEW_STATUSES = new Set(["still_review_required", "not_enough_plan_evidence"]);

// ── Render-block reason explanation map ───────────────────────────────────────

type ReasonExplanation = { meaning: string; resolution: string };

function explainBlockReason(reason: string, sourceFile: string, hasSiblingRendered: boolean): ReasonExplanation {
  if (reason === "no_geometry_output") {
    return {
      meaning: "No route geometry was generated for this group.",
      resolution: "Check that the bore log rows contain valid lat/lon coordinates and form a continuous path.",
    };
  }
  if (reason === "no_matched_route") {
    return {
      meaning: "The system could not find a route on the KMZ design that matches this group's bore path.",
      resolution: "Confirm the bore log rows align with a route segment on the uploaded KMZ, or check for coordinate offset issues.",
    };
  }
  if (reason === "batch_level_conflict_resolution") {
    return {
      meaning: "This group was excluded because it conflicts with another group during batch-level deduplication.",
      resolution: "Review overlapping bore log groups for this file and confirm which group represents the correct bore run.",
    };
  }

  const colonIdx = reason.indexOf(":");
  const prefix = colonIdx !== -1 ? reason.slice(0, colonIdx) : reason;
  const detail = colonIdx !== -1 ? reason.slice(colonIdx + 1) : "";

  if (prefix === "validation_status") {
    return {
      meaning: "This group failed field-data validation — one or more required columns are missing or have invalid values.",
      resolution: "Open the bore log source file and check for missing station IDs, blank footage values, or unrecognised route codes.",
    };
  }

  if (prefix === "route_uniqueness_gate") {
    if (detail === "multiple_candidates") {
      const siblingNote = hasSiblingRendered ? ` Other groups from ${sourceFile} rendered successfully.` : "";
      return {
        meaning: `Multiple routes on the KMZ matched this group's bore path and the system could not determine the correct one.${siblingNote}`,
        resolution: "Upload an engineering plan that clearly identifies the intended route, or manually select the correct route in the review panel.",
      };
    }
    if (detail === "no_candidates") {
      return {
        meaning: "No routes on the KMZ matched this group's bore path coordinates.",
        resolution: "Verify the KMZ design file covers this area, and confirm the bore log coordinates are correct.",
      };
    }
    return {
      meaning: `Route selection failed: ${detail || "unknown route uniqueness issue"}.`,
      resolution: "Review the bore log route codes and confirm they match a route on the uploaded KMZ.",
    };
  }

  if (prefix === "geometry_lock_gate") {
    return {
      meaning: "The route geometry for this group could not be locked to a confirmed path segment.",
      resolution: "Check that the bore log has enough station points and that they fall within the expected route corridor on the KMZ.",
    };
  }

  if (prefix === "chain_gate") {
    return {
      meaning: `Bore log station chain failed validation: ${detail || "chain integrity check failed"}.`,
      resolution: "Review the station sequence in the bore log for gaps, duplicates, or out-of-order entries.",
    };
  }

  if (prefix === "node_resolution_gate") {
    return {
      meaning: `Start or end node for this group could not be resolved on the route network: ${detail || "node resolution failed"}.`,
      resolution: "Confirm the first and last bore log rows have coordinates that fall at or near a valid network node on the KMZ.",
    };
  }

  return {
    meaning: `Render blocked: ${reason}.`,
    resolution: "Review the pipeline diagnostic data for this group.",
  };
}

// ── QA item builders ──────────────────────────────────────────────────────────

function buildStoppedItem(sourceFile: string, stoppedAt: string): QaFlagItem {
  if (stoppedAt === "no_rankings_after_all_passes") {
    return {
      severity: "error",
      sourceFile,
      issue: `${sourceFile} — no route rankings produced.`,
      meaning: "The matching pipeline ran all scoring passes but could not produce any ranked route candidates for this group.",
      resolution: "Check that the bore log has sufficient valid rows and that the KMZ contains a route within range of the bore path.",
      rawReasons: [stoppedAt],
    };
  }
  if (stoppedAt === "no_anchored_hypotheses") {
    return {
      severity: "error",
      sourceFile,
      issue: `${sourceFile} — no anchored route hypotheses.`,
      meaning: "The pipeline could not anchor any route hypothesis to the bore log data — typically because no route candidates passed the minimum evidence threshold.",
      resolution: "Review the bore log rows for this group and confirm that station points overlap with at least one route on the KMZ.",
      rawReasons: [stoppedAt],
    };
  }
  if (stoppedAt === "render_gate_blocked") {
    return {
      severity: "error",
      sourceFile,
      issue: `${sourceFile} — stopped at render gate.`,
      meaning: "The system did not generate geometry for this group because required route and point checks failed.",
      resolution: "Review the bore log rows for this group and confirm it has enough valid station points to form a route segment.",
      rawReasons: [stoppedAt],
    };
  }
  return {
    severity: "warning",
    sourceFile,
    issue: `${sourceFile} — pipeline stopped (${stoppedAt}).`,
    meaning: `Processing halted at checkpoint "${stoppedAt}".`,
    resolution: "Review the pipeline diagnostic data for this group.",
    rawReasons: [stoppedAt],
  };
}

function buildBlockedItem(
  sourceFile: string,
  blockReasons: string[],
  hasSiblingRendered: boolean,
): QaFlagItem {
  if (blockReasons.length === 0) {
    return {
      severity: "error",
      sourceFile,
      issue: `${sourceFile} — render blocked (no reason recorded).`,
      meaning: "This group was blocked from rendering but no specific block reason was recorded.",
      resolution: "Review the pipeline diagnostic data for this group.",
      rawReasons: blockReasons,
    };
  }

  const primary = explainBlockReason(blockReasons[0], sourceFile, hasSiblingRendered);
  const siblingNote = hasSiblingRendered ? ` Other groups from the same file rendered successfully.` : "";

  const issueLine =
    blockReasons.length === 1
      ? `${sourceFile} — render blocked: ${blockReasons[0]}.`
      : `${sourceFile} — render blocked (${blockReasons.length} reasons).`;

  return {
    severity: "error",
    sourceFile,
    issue: issueLine,
    meaning: primary.meaning + siblingNote,
    resolution: primary.resolution,
    rawReasons: blockReasons,
  };
}

function buildAmbiguityItem(
  sourceFile: string,
  status: string,
  hasPlanSignals: boolean,
  hasSiblingRendered: boolean,
): QaFlagItem {
  const siblingNote = hasSiblingRendered ? ` Other groups from the same file rendered successfully.` : "";

  if (status === "still_review_required") {
    return {
      severity: "warning",
      sourceFile,
      issue: `${sourceFile} — route ambiguity: plan signal inconclusive.`,
      meaning: `Engineering plans were uploaded but the plan evidence for this group points to a different route or is inconclusive.${siblingNote}`,
      resolution: "Review the selected route in the map against the uploaded plan/sheet and confirm it matches the intended alignment.",
      rawReasons: [status],
    };
  }

  if (status === "not_enough_plan_evidence") {
    if (!hasPlanSignals) {
      return {
        severity: "warning",
        sourceFile,
        issue: `${sourceFile} — route ambiguity: no plan evidence.`,
        meaning: `This group's route could not be uniquely determined and no engineering plans have been uploaded to help resolve it.${siblingNote}`,
        resolution: "Upload an engineering plan that identifies the intended route for this bore run.",
        rawReasons: [status],
      };
    }
    return {
      severity: "warning",
      sourceFile,
      issue: `${sourceFile} — route ambiguity: uploaded plans do not cover this group.`,
      meaning: `Engineering plans are uploaded but none of them contain matching tokens for this group's route or area.${siblingNote}`,
      resolution: "Verify the uploaded plans cover this segment, or perform a manual route review.",
      rawReasons: [status],
    };
  }

  if (status === "resolved_by_plan_signal") {
    return {
      severity: "info",
      sourceFile,
      issue: `${sourceFile} — ambiguity resolved by plan signal.`,
      meaning: "An engineering plan matched this group and was used to confirm the selected route.",
      resolution: "Verify that the selected route on the map matches the expected plan sheet and alignment.",
      rawReasons: [status],
    };
  }

  return {
    severity: "info",
    sourceFile,
    issue: `${sourceFile} — ambiguity status: ${status}.`,
    meaning: `Ambiguity classification returned status "${status}".`,
    resolution: "Review the pipeline diagnostic data for this group.",
    rawReasons: [status],
  };
}

// ── Readiness reason string builder ──────────────────────────────────────────
/**
 * Derive a concise, source-file-specific reason string from a QA flag item.
 * Used to populate billingReadiness.reasons with actionable text.
 */
function buildReadinessReason(item: QaFlagItem): string {
  const sf = item.sourceFile;
  const raw = item.rawReasons?.[0] ?? "";

  // Stopped / pipeline failures → Blocked reasons
  if (raw === "no_rankings_after_all_passes") return `${sf} — pipeline produced no route rankings for a group.`;
  if (raw === "no_anchored_hypotheses")        return `${sf} — pipeline found no viable route hypotheses for a group.`;
  if (raw === "render_gate_blocked")           return `${sf} — one group stopped at the render gate.`;
  if (raw === "no_geometry_output")            return `${sf} — one group did not generate geometry.`;
  if (raw === "no_matched_route")              return `${sf} — one group has no matching route on the KMZ.`;
  if (raw === "batch_level_conflict_resolution") return `${sf} — one group excluded due to batch-level conflict.`;

  // Gate failures
  if (raw.startsWith("validation_status:"))          return `${sf} — one group failed field-data validation.`;
  if (raw.startsWith("route_uniqueness_gate:multiple")) return `${sf} — one group matched multiple routes (manual selection required).`;
  if (raw.startsWith("route_uniqueness_gate:no_cand")) return `${sf} — one group matched no routes on the KMZ.`;
  if (raw.startsWith("route_uniqueness_gate:"))       return `${sf} — one group failed route uniqueness check.`;
  if (raw.startsWith("chain_gate:"))                 return `${sf} — one group failed station chain validation.`;
  if (raw.startsWith("node_resolution_gate:"))       return `${sf} — one group failed node resolution.`;
  if (raw.startsWith("geometry_lock_gate:"))         return `${sf} — one group could not lock route geometry.`;

  // Ambiguity → Needs Review reasons
  if (raw === "still_review_required")    return `${sf} requires route confirmation against uploaded plans.`;
  if (raw === "not_enough_plan_evidence") return `Uploaded plans do not resolve route ambiguity for ${sf}.`;
  if (raw === "resolved_by_plan_signal")  return `${sf} route confirmed by plan signal — verify against plan sheet.`;

  // Generic fallback
  return item.issue;
}

/**
 * Build a read-only Nova summary from existing pipeline diagnostic data.
 *
 * @param pipelineDiag     - Entries from /api/debug/pipeline-diag
 * @param planSignals      - Extracted plan signals from the same endpoint
 * @param exceptions       - Client-side billing exception rows
 * @param exceptionTotal   - Computed exception total (already calculated in component)
 * @param hasKmz           - Whether a KMZ design file is loaded
 * @param hasBoreLogs      - Whether any bore log files have been uploaded
 */
export function buildNovaSummary(
  pipelineDiag: PipelineDiagEntry[],
  planSignals: EngineeringPlanSignal[],
  exceptions: ExceptionCost[],
  exceptionTotal: number,
  hasKmz: boolean,
  hasBoreLogs: boolean,
): NovaSummary {
  // ── Job overview counts ──────────────────────────────────────────────────
  const totalGroups = pipelineDiag.length;
  const renderedGroups = pipelineDiag.filter((d) => d.render_allowed === true).length;
  const blockedGroups = pipelineDiag.filter((d) => d.render_allowed === false).length;
  const engineeringPlansDetected = planSignals.length;

  // ── Sibling-render map ─────────────────────────────────────────────────────
  // For each source_file, track whether at least one group from that file rendered.
  const fileRenderCount = new Map<string, number>();
  const fileTotalCount = new Map<string, number>();

  for (const d of pipelineDiag) {
    const sf = String(d.source_file || d.group_key || "unknown");
    fileTotalCount.set(sf, (fileTotalCount.get(sf) ?? 0) + 1);
    if (d.render_allowed === true) {
      fileRenderCount.set(sf, (fileRenderCount.get(sf) ?? 0) + 1);
    }
  }

  function hasSiblingRendered(sourceFile: string): boolean {
    return (fileRenderCount.get(sourceFile) ?? 0) > 0;
  }

  // ── QA items (Phase 1.2 — structured) ─────────────────────────────────────
  const qaItems: QaFlagItem[] = [];

  // Stopped groups (pipeline halted mid-run)
  for (const d of pipelineDiag) {
    if (typeof d.stopped_at === "string" && d.stopped_at.length > 0) {
      const sf = String(d.source_file || d.group_key || "unknown");
      qaItems.push(buildStoppedItem(sf, d.stopped_at));
    }
  }

  // Blocked groups (render gate rejected) — skip if also stopped (no duplicate)
  for (const d of pipelineDiag) {
    if (
      d.render_allowed === false &&
      Array.isArray(d.render_block_reasons) &&
      d.render_block_reasons.length > 0
    ) {
      const alreadyStopped = typeof d.stopped_at === "string" && d.stopped_at.length > 0;
      if (!alreadyStopped) {
        const sf = String(d.source_file || d.group_key || "unknown");
        qaItems.push(
          buildBlockedItem(sf, d.render_block_reasons as string[], hasSiblingRendered(sf)),
        );
      }
    }
  }

  // Ambiguous groups (plan intelligence layer)
  for (const d of pipelineDiag) {
    const ambStatus = d.ambiguity_resolution_status;
    if (typeof ambStatus !== "string") continue;
    const sf = String(d.source_file || d.group_key || "unknown");
    if (REVIEW_STATUSES.has(ambStatus) || ambStatus === "resolved_by_plan_signal") {
      qaItems.push(
        buildAmbiguityItem(sf, ambStatus, planSignals.length > 0, hasSiblingRendered(sf)),
      );
    }
  }

  // ── Plan intelligence ──────────────────────────────────────────────────────
  const planSourceFiles = planSignals
    .map((s) => String(s.source_file || s.plan_id || "unknown"))
    .filter(Boolean);

  const planSupportedBoreLogs = pipelineDiag
    .filter((d) => d.ambiguity_resolution_status === "resolved_by_plan_signal")
    .map((d) => String(d.source_file || d.group_key || "unknown"));

  // ── Exception notes ────────────────────────────────────────────────────────
  const exceptionNotes = exceptions
    .filter((e) => {
      const parsed = Number.parseFloat(e.amount);
      return e.label.trim().length > 0 && Number.isFinite(parsed) && parsed !== 0;
    })
    .map((e) => ({
      label: e.label,
      amount: e.amount,
      note: e.note,
      station: e.station,
    }));

  const exceptionsWithoutNotes = exceptions.filter((e) => {
    const parsed = Number.parseFloat(e.amount);
    return Number.isFinite(parsed) && parsed !== 0 && !e.note?.trim();
  });

  // ── Billing readiness (Phase 1.3) ─────────────────────────────────────────
  const reasons: string[] = [];
  const warnings: string[] = [];
  let billingStatus: "Ready" | "Needs Review" | "Blocked" = "Ready";

  // ── BLOCKED conditions ────────────────────────────────────────────────────

  if (!hasKmz) {
    billingStatus = "Blocked";
    reasons.push("No KMZ design file uploaded.");
  }
  if (!hasBoreLogs) {
    if (billingStatus !== "Blocked") billingStatus = "Blocked";
    reasons.push("No bore log files uploaded.");
  }

  // Error-severity QA items → Blocked (stopped_at and render_allowed === false)
  if (hasKmz && hasBoreLogs) {
    const errorItems = qaItems.filter((q) => q.severity === "error");
    if (errorItems.length > 0) {
      billingStatus = "Blocked";
      for (const item of errorItems) {
        reasons.push(buildReadinessReason(item));
      }
    }
  }

  // segments_returned === 0 when row_count >= 2 → Blocked
  // Skip groups already covered by an error-severity QA item to avoid duplicate reasons.
  const coveredByStopped = new Set(
    qaItems.filter((q) => q.severity === "error").map((q) => q.sourceFile),
  );
  for (const d of pipelineDiag) {
    const segs = typeof d.segments_returned === "number" ? d.segments_returned : undefined;
    const rows = typeof d.row_count === "number" ? d.row_count : undefined;
    if (segs === 0 && rows !== undefined && rows >= 2) {
      const sf = String(d.source_file || d.group_key || "unknown");
      if (!coveredByStopped.has(sf)) {
        if (billingStatus !== "Blocked") billingStatus = "Blocked";
        reasons.push(`${sf} — ${rows} rows present but zero segments returned.`);
        coveredByStopped.add(sf);
      }
    }
  }

  // ── NEEDS REVIEW conditions (only if not already Blocked) ─────────────────

  if (billingStatus === "Ready") {
    const warningItems = qaItems.filter((q) => q.severity === "warning");
    if (warningItems.length > 0) {
      billingStatus = "Needs Review";
      for (const item of warningItems) {
        reasons.push(buildReadinessReason(item));
      }
    }

    // render_block_reasons on a group that did render (unusual, forward-looking check)
    for (const d of pipelineDiag) {
      if (
        d.render_allowed === true &&
        Array.isArray(d.render_block_reasons) &&
        (d.render_block_reasons as string[]).length > 0
      ) {
        billingStatus = "Needs Review";
        const sf = String(d.source_file || d.group_key || "unknown");
        reasons.push(`${sf} — rendered but carries block-reason flags (review recommended).`);
      }
    }
  }

  // Soft warning: exceptions without notes (does not change billing status)
  if (exceptionsWithoutNotes.length > 0) {
    warnings.push(
      `${exceptionsWithoutNotes.length} exception${exceptionsWithoutNotes.length > 1 ? "s" : ""} without context notes.`,
    );
  }

  // ── READY confirmation reasons ─────────────────────────────────────────────
  if (billingStatus === "Ready" && totalGroups > 0 && reasons.length === 0) {
    reasons.push("All bore log groups rendered successfully.");
    if (!qaItems.some((q) => q.severity === "warning")) {
      reasons.push("No unresolved ambiguity detected.");
    }
    reasons.push("No blocked pipeline groups detected.");
  }

  // ── Status label (never makes legal / compliance claims) ───────────────────
  const statusLabel =
    billingStatus === "Blocked"
      ? "Blocked until issues are resolved"
      : billingStatus === "Needs Review"
      ? "Needs review before billing"
      : "Ready for closeout review";

  // ── Recommended actions ───────────────────────────────────────────────────
  const actions: string[] = [];

  if (!hasKmz) {
    actions.push("Upload a KMZ design file to begin.");
  } else if (!hasBoreLogs) {
    actions.push("Upload bore log files to generate route matches.");
  }

  for (const severity of ["error", "warning", "info"] as const) {
    for (const item of qaItems) {
      if (item.severity === severity) {
        actions.push(`${item.sourceFile}: ${item.resolution}`);
      }
    }
  }

  if (exceptionsWithoutNotes.length > 0) {
    actions.push("Add context notes to exception rows before billing.");
  }

  if (actions.length === 0 && billingStatus === "Ready" && totalGroups > 0) {
    actions.push("All checks passed. Billing totals are ready for closeout.");
  } else if (actions.length === 0 && totalGroups === 0 && hasKmz && hasBoreLogs) {
    actions.push("Pipeline produced no groups. Check that bore log files contain valid rows.");
  }

  // ── Assemble ───────────────────────────────────────────────────────────────
  return {
    jobOverview: {
      totalGroups,
      renderedGroups,
      blockedGroups,
      engineeringPlansDetected,
      totalExceptionCost: exceptionTotal,
    },
    billingReadiness: {
      status: billingStatus,
      statusLabel,
      reasons,
      warnings,
    },
    qaFlags: {
      items: qaItems,
    },
    planIntelligence: {
      signalCount: engineeringPlansDetected,
      sourceFiles: planSourceFiles,
      planSupportedBoreLogs,
    },
    exceptionNotes,
    recommendedActions: actions,
  };
}
