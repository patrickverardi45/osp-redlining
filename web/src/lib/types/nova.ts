// Nova Phase 1 — read-only job intelligence types.
// Derived entirely from existing pipeline diagnostics and session state.
// No write actions, no external AI calls. Pure read / summarise.
// Phase 1.2: QA flags carry structured explanation (issue/meaning/resolution).
// Phase 1.3: Billing readiness with statusLabel and source-file-specific reasons.

/**
 * One entry from GET /api/debug/pipeline-diag → pipeline_diag[].
 * Index signature allows additional backend checkpoint fields to pass through
 * without breaking the TS shape.
 */
export type PipelineDiagEntry = {
  group_key?: string;
  source_file?: string;
  row_count?: number;
  /** Number of route segments returned for this group. 0 with row_count >= 2 is a Blocked signal. */
  segments_returned?: number;
  print_tokens?: string[];
  stopped_at?: string | null;
  render_allowed?: boolean;
  render_block_reasons?: string[];
  plan_bias_applied?: boolean;
  plan_bias_meta?: Record<string, unknown> | null;
  ambiguity_resolution_status?: string | null;
  ambiguity_resolution_meta?: Record<string, unknown> | null;
  // allow pass-through of other checkpoint fields
  [key: string]: unknown;
};

/**
 * One entry from GET /api/debug/pipeline-diag → engineering_plan_signals[].
 * Extracted from plan filenames and stored metadata — no OCR.
 */
export type EngineeringPlanSignal = {
  plan_id?: string;
  source_file?: string;
  print_tokens?: string[];
  route_hints?: string[];
  phase_hints?: string[];
  date?: string | null;
  revision?: string | null;
  raw_text_tokens?: string[];
};

/**
 * Severity level for a QA flag item.
 * - "error"   : blocks rendering or billing — must be resolved
 * - "warning" : pipeline ran but something unexpected happened — review recommended
 * - "info"    : informational, no action required (e.g. plan-resolved)
 */
export type QaFlagSeverity = "error" | "warning" | "info";

/**
 * One structured QA flag, produced by buildNovaSummary Phase 1.2.
 * Every item carries a human-readable explanation of what happened, why it
 * matters, and what the operator should do about it.
 */
export type QaFlagItem = {
  severity: QaFlagSeverity;
  sourceFile: string;
  /** Short label shown in bold — the "what". */
  issue: string;
  /** One-sentence explanation — the "why it matters". */
  meaning: string;
  /** Concrete next step — the "what to do". */
  resolution: string;
  /** Raw reason strings for debugging / future tooling. */
  rawReasons?: string[];
};

/**
 * The fully structured summary object produced by buildNovaSummary().
 * Read-only. Never used to mutate app state.
 */
export type NovaSummary = {
  jobOverview: {
    totalGroups: number;
    renderedGroups: number;
    blockedGroups: number;
    engineeringPlansDetected: number;
    totalExceptionCost: number;
  };
  billingReadiness: {
    /** Internal discriminator used for pill colour. */
    status: "Ready" | "Needs Review" | "Blocked";
    /**
     * Human-readable display label — never makes legal / compliance claims.
     * "Ready for closeout review" | "Needs review before billing" | "Blocked until issues are resolved"
     */
    statusLabel: string;
    /** Source-file-specific reasons for the current status, ordered by severity. */
    reasons: string[];
    /** Soft warnings that do not change status (e.g. missing exception notes). */
    warnings: string[];
  };
  qaFlags: {
    items: QaFlagItem[];
  };
  planIntelligence: {
    signalCount: number;
    sourceFiles: string[];
    planSupportedBoreLogs: string[];
  };
  exceptionNotes: Array<{
    label: string;
    amount: string;
    note?: string;
    station?: string;
  }>;
  recommendedActions: string[];
};
