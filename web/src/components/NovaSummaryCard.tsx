"use client";

// Nova Phase 2 — job intelligence card with a persisted QA review decision layer.
// Phase 1.2: QA explanation layer (issue / meaning / resolution per item).
// Phase 1.3: Closeout readiness status with statusLabel, source-file reasons,
//            and max-3 visible reasons with expand toggle.
// Phase 2:   Override decisions persist to backend via /api/nova-overrides.
// Phase 2.3: Override-aware status. Engine issues remain visible. Status
//            reflects override decisions without ever claiming engine clearance.

import React, { useState, useEffect, useCallback, useMemo } from "react";
import type { NovaSummary, QaFlagItem, QaFlagSeverity } from "@/lib/types/nova";
import { toMoney } from "@/lib/format/money";
import { appendSessionId, getStoredSessionId } from "@/lib/session";

type Props = {
  summary: NovaSummary;
  onFocusIssue?: (issue: {
    issueId: string;
    source_file: string;
    group_idx: number | null;
    issue_key: string;
    severity: QaFlagSeverity;
    raw_reasons?: string[];
    item: QaFlagItem;
  }) => void;
  onOverrideSourcesChange?: (sourceFiles: string[]) => void;
  /** When true, suppresses the internal "Nova — Job Intelligence" header.
   *  Use when the card is rendered inside a panel that provides its own header. */
  hideHeader?: boolean;
};

const API_BASE =
  (process.env.NEXT_PUBLIC_API_BASE?.replace(/\/+$/, "") ||
    process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, "")) ??
  "";

// ── Types ────────────────────────────────────────────────────────────────────

type OverrideDecision = "Reviewed" | "Accepted Override" | "Needs Rework";

type NovaIssueOverride = {
  id: string;
  source_file: string;
  group_idx: number | null;
  issue_key: string;
  decision: OverrideDecision;
  reason: string;
  created_by: string;
  role: string;
  created_at: string;
};

/**
 * Override-aware display status, layered on top of the engine's status.
 * "Reviewed" = all flagged items have human decisions but engine truth remains.
 */
type DisplayStatus = "Ready" | "Needs Review" | "Blocked" | "Reviewed";

type OverrideAwareResult = {
  status: DisplayStatus;
  statusLabel: string;
  /** If non-empty, replace engine reasons in the status block. */
  reasons: string[];
  summary: { reviewed: number; accepted: number; needsRework: number };
};

// ── Visual constants ──────────────────────────────────────────────────────────

const STATUS_STYLE: Record<DisplayStatus, { bg: string; color: string; border: string }> = {
  Ready:          { bg: "#16a34a", color: "#ffffff", border: "#15803d" },
  "Needs Review": { bg: "#d97706", color: "#ffffff", border: "#b45309" },
  Blocked:        { bg: "#dc2626", color: "#ffffff", border: "#b91c1c" },
  Reviewed:       { bg: "#7c3aed", color: "#ffffff", border: "#6d28d9" },
};

const SEVERITY_STYLE: Record<
  QaFlagSeverity,
  { icon: string; color: string; bg: string; labelColor: string; border: string }
> = {
  error:   { icon: "✗", color: "#991b1b", bg: "#fef2f2", labelColor: "#dc2626", border: "#fecaca" },
  warning: { icon: "⚠", color: "#92400e", bg: "#fffbeb", labelColor: "#d97706", border: "#fde68a" },
  info:    { icon: "✓", color: "#15803d", bg: "#f0fdf4", labelColor: "#16a34a", border: "#bbf7d0" },
};

const REASONS_VISIBLE_DEFAULT = 3;

const AUTHORIZED_OVERRIDE_USER = {
  name: "Demo PM",
  role: "PM",
  canOverride: true,
};

const OVERRIDE_DECISIONS: OverrideDecision[] = [
  "Reviewed",
  "Accepted Override",
  "Needs Rework",
];

const OVERRIDE_BADGE_STYLE: Record<OverrideDecision, { bg: string; color: string; border: string }> = {
  Reviewed:            { bg: "#f8fafc", color: "#475569", border: "#cbd5e1" },
  "Accepted Override": { bg: "#ecfdf3", color: "#047857", border: "#86efac" },
  "Needs Rework":      { bg: "#fff7ed", color: "#b45309", border: "#fdba74" },
};

const STATUS_TOOLTIP: Record<DisplayStatus, string> = {
  Blocked: "Issues prevent reliable output.",
  "Needs Review": "Manual confirmation required.",
  Ready: "No blocking issues detected.",
  Reviewed: "Human review recorded; original engine findings remain visible.",
};

function overrideTooltip(override: NovaIssueOverride): string {
  return `${override.decision}: ${override.reason} — ${override.created_by} (${override.role})`;
}

// ── Override-aware status computation ────────────────────────────────────────

/**
 * Compute a display status that acknowledges persisted override decisions
 * while never claiming the engine has cleared any issue.
 *
 * Rules:
 * - Engine "Ready" → always show "Ready" (no engine issues exist).
 * - Any item marked "Needs Rework" → "Blocked — rework required by reviewer."
 * - Engine "Blocked" + unreviewed error items → "Blocked until issues are resolved."
 * - Engine "Blocked" + all errors reviewed/accepted + no Needs Rework
 *   → "Reviewed" status: "Blocked items reviewed — final review required."
 * - Engine "Needs Review" + unreviewed warning items → "Needs review before billing."
 * - Engine "Needs Review" + all warnings reviewed + no Needs Rework
 *   → "Reviewed" status: "Review items acknowledged — final review required."
 */
function computeOverrideAwareStatus(
  engineStatus: "Ready" | "Needs Review" | "Blocked",
  qaItemsWithIds: Array<{ item: QaFlagItem; issueId: string }>,
  issueOverrides: Record<string, NovaIssueOverride>,
): OverrideAwareResult {
  const errorItems  = qaItemsWithIds.filter(x => x.item.severity === "error");
  const warningItems = qaItemsWithIds.filter(x => x.item.severity === "warning");
  const actionable  = [...errorItems, ...warningItems];

  // Count overrides by decision
  let reviewed = 0, accepted = 0, needsRework = 0;
  for (const { issueId } of actionable) {
    const ov = issueOverrides[issueId];
    if (!ov) continue;
    if (ov.decision === "Reviewed")            reviewed++;
    else if (ov.decision === "Accepted Override") accepted++;
    else if (ov.decision === "Needs Rework")    needsRework++;
  }
  const overrideSummary = { reviewed, accepted, needsRework };

  // Items by review state
  const needsReworkItems   = actionable.filter(x => issueOverrides[x.issueId]?.decision === "Needs Rework");
  const unreviewedErrors   = errorItems.filter(x => !issueOverrides[x.issueId]);
  const unreviewedWarnings = warningItems.filter(x => !issueOverrides[x.issueId]);

  // ── Engine says Ready: nothing to overlay ───────────────────────────────
  if (engineStatus === "Ready") {
    return {
      status: "Ready",
      statusLabel: "Ready for closeout review",
      reasons: [],
      summary: overrideSummary,
    };
  }

  // ── Any "Needs Rework" decision → force Blocked regardless of engine status ─
  if (needsReworkItems.length > 0) {
    const reworkReasons = needsReworkItems.map(({ item, issueId }) => {
      const ov = issueOverrides[issueId]!;
      return `${item.sourceFile} marked "Needs Rework" by ${ov.created_by} (${ov.role}).`;
    });
    return {
      status: "Blocked",
      statusLabel: "Blocked — rework required by reviewer",
      reasons: reworkReasons,
      summary: overrideSummary,
    };
  }

  // ── Engine "Blocked" ────────────────────────────────────────────────────
  if (engineStatus === "Blocked") {
    if (unreviewedErrors.length > 0) {
      // Some error items still have no review decision — engine block stands.
      return {
        status: "Blocked",
        statusLabel: "Blocked until issues are resolved",
        reasons: [],          // fall through to engine reasons
        summary: overrideSummary,
      };
    }
    // All error items have been reviewed or accepted.
    return {
      status: "Reviewed",
      statusLabel: "Blocked items reviewed — final review required",
      reasons: [
        "All blocked groups have been reviewed by a PM.",
        `${reviewed + accepted} issue${reviewed + accepted !== 1 ? "s" : ""} acknowledged via human decision — not cleared by engine.`,
        "Original engine findings remain on record and visible below.",
      ],
      summary: overrideSummary,
    };
  }

  // ── Engine "Needs Review" ──────────────────────────────────────────────
  if (unreviewedWarnings.length > 0) {
    // Some warning items still have no review decision.
    return {
      status: "Needs Review",
      statusLabel: "Needs review before billing",
      reasons: [],           // fall through to engine reasons
      summary: overrideSummary,
    };
  }
  // All warning items reviewed.
  return {
    status: "Reviewed",
    statusLabel: "Review items acknowledged — final review required",
    reasons: [
      "All flagged items have been reviewed by a PM.",
      `${reviewed + accepted} item${reviewed + accepted !== 1 ? "s" : ""} acknowledged via human decision — not cleared by engine.`,
      "Original engine findings remain on record and visible below.",
    ],
    summary: overrideSummary,
  };
}

// ── Helper functions ──────────────────────────────────────────────────────────

function buildIssueId(item: QaFlagItem, index: number): string {
  return [
    item.sourceFile || "unknown",
    item.severity,
    item.issue,
    item.rawReasons?.join("|") || "",
    index,
  ].join("::");
}

function formatOverrideTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

// ── Sub-components ────────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontSize: 10,
        fontWeight: 800,
        color: "#94a3b8",
        textTransform: "uppercase",
        letterSpacing: "0.08em",
        marginBottom: 6,
      }}
    >
      {children}
    </div>
  );
}

function SummaryCount({
  label,
  value,
  accent,
}: {
  label: string;
  value: string | number;
  accent?: string;
}) {
  return (
    <span style={{ fontSize: 13, color: accent ?? "#475569" }}>
      <span style={{ fontWeight: 700, color: accent ?? "#0f172a" }}>{value}</span>{" "}
      {label}
    </span>
  );
}

/**
 * One QA flag row in the details panel.
 * Issue headline always visible; meaning / resolution / raw reasons behind toggle.
 * Override panel allows PM to record a review decision that persists to backend.
 */
function QaFlagDetail({
  item,
  issueId,
  override,
  onSaveOverride,
  onFocusIssue,
}: {
  item: QaFlagItem;
  issueId: string;
  override?: NovaIssueOverride;
  onSaveOverride: (record: NovaIssueOverride) => void;
  onFocusIssue?: (issue: {
    issueId: string;
    source_file: string;
    group_idx: number | null;
    issue_key: string;
    severity: QaFlagSeverity;
    raw_reasons?: string[];
    item: QaFlagItem;
  }) => void;
}) {
  const [open, setOpen] = useState(false);
  const [overridePanelOpen, setOverridePanelOpen] = useState(false);
  const [decision, setDecision] = useState<OverrideDecision>(override?.decision ?? "Reviewed");
  const [reason, setReason] = useState(override?.reason ?? "");
  const [reasonError, setReasonError] = useState("");
  const sty = SEVERITY_STYLE[item.severity];
  const badgeStyle = override ? OVERRIDE_BADGE_STYLE[override.decision] : undefined;

  function openOverridePanel() {
    setDecision(override?.decision ?? "Reviewed");
    setReason(override?.reason ?? "");
    setReasonError("");
    setOverridePanelOpen(true);
  }

  function saveOverride() {
    const trimmedReason = reason.trim();
    if (!trimmedReason) {
      setReasonError("Enter a reason before saving.");
      return;
    }
    onSaveOverride({
      id: issueId,
      source_file: item.sourceFile,
      group_idx: null,
      issue_key: issueId,
      decision,
      reason: trimmedReason,
      created_by: AUTHORIZED_OVERRIDE_USER.name,
      role: AUTHORIZED_OVERRIDE_USER.role,
      created_at: new Date().toISOString(),
    });
    setReasonError("");
    setOverridePanelOpen(false);
    setOpen(true);
  }

  function focusIssueOnMap() {
    const rawItem = item as unknown as Record<string, unknown>;
    const rawGroupIdx = rawItem.group_idx ?? rawItem.groupIdx;
    onFocusIssue?.({
      issueId,
      source_file: item.sourceFile,
      group_idx: typeof rawGroupIdx === "number" ? rawGroupIdx : null,
      issue_key: issueId,
      severity: item.severity,
      raw_reasons: item.rawReasons,
      item,
    });
  }

  return (
    <div
      style={{
        background: sty.bg,
        border: `1px solid ${sty.border}`,
        borderRadius: 8,
        overflow: "hidden",
      }}
    >
      {/* ── Issue header row ── */}
      <div
        style={{
          width: "100%",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: 8,
          padding: "8px 10px",
        }}
      >
        <button
          onClick={() => setOpen((v) => !v)}
          style={{
            flex: 1,
            minWidth: 0,
            display: "grid",
            gap: 4,
            padding: 0,
            background: "none",
            border: "none",
            cursor: "pointer",
            textAlign: "left",
          }}
        >
          <span style={{ fontSize: 12, fontWeight: 700, color: sty.color, lineHeight: 1.45 }}>
            {sty.icon} {item.issue}
          </span>
          {override && badgeStyle && (
            <span
              title={overrideTooltip(override)}
              style={{
                width: "fit-content",
                border: `1px solid ${badgeStyle.border}`,
                background: badgeStyle.bg,
                color: badgeStyle.color,
                borderRadius: 999,
                padding: "2px 8px",
                fontSize: 10,
                fontWeight: override.decision === "Accepted Override" ? 900 : 800,
                letterSpacing: "0.02em",
              }}
            >
              {override.decision}
            </span>
          )}
        </button>

        <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
          {onFocusIssue && (
            <button
              onClick={focusIssueOnMap}
              style={{
                border: "1px solid #bfdbfe",
                background: "#eff6ff",
                color: "#1d4ed8",
                borderRadius: 999,
                padding: "4px 8px",
                fontSize: 10,
                fontWeight: 800,
                cursor: "pointer",
                whiteSpace: "nowrap",
              }}
            >
              Focus on map
            </button>
          )}
          {AUTHORIZED_OVERRIDE_USER.canOverride && (
            <button
              onClick={openOverridePanel}
              style={{
                border: "1px solid #cbd5e1",
                background: "#ffffff",
                color: "#334155",
                borderRadius: 999,
                padding: "4px 8px",
                fontSize: 10,
                fontWeight: 700,
                cursor: "pointer",
                whiteSpace: "nowrap",
              }}
            >
              Resolve / Override
            </button>
          )}
          <button
            onClick={() => setOpen((v) => !v)}
            style={{
              background: "none",
              border: "none",
              color: "#94a3b8",
              cursor: "pointer",
              fontSize: 11,
              padding: 0,
              whiteSpace: "nowrap",
            }}
          >
            {open ? "Hide ▲" : "Details ▼"}
          </button>
        </div>
      </div>

      {/* ── Override input panel ── */}
      {overridePanelOpen && (
        <div
          style={{
            borderTop: `1px solid ${sty.border}`,
            background: "#ffffff",
            padding: "9px 10px",
            display: "grid",
            gap: 8,
          }}
        >
          <div style={{ fontSize: 11, fontWeight: 800, color: "#334155" }}>
            Review decision by {AUTHORIZED_OVERRIDE_USER.name} ({AUTHORIZED_OVERRIDE_USER.role})
          </div>
          <label style={{ display: "grid", gap: 4, fontSize: 11, color: "#475569", fontWeight: 700 }}>
            Decision
            <select
              value={decision}
              onChange={(e) => setDecision(e.target.value as OverrideDecision)}
              style={{
                border: "1px solid #cbd5e1",
                borderRadius: 8,
                padding: "7px 8px",
                fontSize: 12,
                color: "#0f172a",
                background: "#ffffff",
              }}
            >
              {OVERRIDE_DECISIONS.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </label>
          <label style={{ display: "grid", gap: 4, fontSize: 11, color: "#475569", fontWeight: 700 }}>
            Reason
            <textarea
              value={reason}
              onChange={(e) => {
                setReason(e.target.value);
                if (reasonError) setReasonError("");
              }}
              rows={3}
              placeholder="Explain why this issue was reviewed or what rework is needed."
              style={{
                border: `1px solid ${reasonError ? "#dc2626" : "#cbd5e1"}`,
                borderRadius: 8,
                padding: "7px 8px",
                fontSize: 12,
                color: "#0f172a",
                resize: "vertical",
              }}
            />
          </label>
          {reasonError && (
            <div style={{ fontSize: 11, color: "#dc2626", fontWeight: 700 }}>{reasonError}</div>
          )}
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
            <button
              onClick={() => setOverridePanelOpen(false)}
              style={{
                border: "1px solid #cbd5e1",
                background: "#ffffff",
                color: "#475569",
                borderRadius: 8,
                padding: "6px 10px",
                fontSize: 11,
                fontWeight: 700,
                cursor: "pointer",
              }}
            >
              Cancel
            </button>
            <button
              onClick={saveOverride}
              style={{
                border: "1px solid #1d4ed8",
                background: "#2563eb",
                color: "#ffffff",
                borderRadius: 8,
                padding: "6px 10px",
                fontSize: 11,
                fontWeight: 800,
                cursor: "pointer",
              }}
            >
              Save Decision
            </button>
          </div>
        </div>
      )}

      {/* ── Expanded detail: meaning + resolution + raw + override record ── */}
      {open && (
        <div
          style={{
            borderTop: `1px solid ${sty.border}`,
            padding: "8px 10px",
            display: "grid",
            gap: 6,
          }}
        >
          <div style={{ fontSize: 12, color: "#718096", lineHeight: 1.55, fontWeight: 400 }}>
            {item.meaning}
          </div>
          <div style={{ fontSize: 12, color: "#475569", lineHeight: 1.55, fontWeight: 400 }}>
            <span style={{ fontWeight: 700, color: sty.labelColor }}>→ </span>
            {item.resolution}
          </div>
          {item.rawReasons && item.rawReasons.length > 0 && (
            <div style={{ fontSize: 10, color: "#94a3b8", fontFamily: "monospace", marginTop: 2 }}>
              {item.rawReasons.join(", ")}
            </div>
          )}
          {override && (
            <div
              style={{
                borderTop: `1px solid ${sty.border}`,
                marginTop: 4,
                paddingTop: 8,
                display: "grid",
                gap: 4,
              }}
            >
              <div style={{ fontSize: 11, fontWeight: 800, color: "#334155" }}>
                Override Review: {override.decision}
              </div>
              <div style={{ fontSize: 12, color: "#475569", lineHeight: 1.5 }}>
                {override.reason}
              </div>
              <div style={{ fontSize: 10, color: "#94a3b8" }}>
                {formatOverrideTimestamp(override.created_at)} · {override.created_by} ({override.role})
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main card ─────────────────────────────────────────────────────────────────

export default function NovaSummaryCard({ summary, onFocusIssue, onOverrideSourcesChange, hideHeader = false }: Props) {
  const [detailsExpanded, setDetailsExpanded] = useState(false);
  const [allReasonsExpanded, setAllReasonsExpanded] = useState(false);
  const [nextActionsExpanded, setNextActionsExpanded] = useState(false);
  const [issueOverrides, setIssueOverrides] = useState<Record<string, NovaIssueOverride>>({});
  const [overridesLoaded, setOverridesLoaded] = useState(false);

  const {
    jobOverview,
    billingReadiness,
    qaFlags,
    planIntelligence,
    exceptionNotes,
    recommendedActions,
  } = summary;

  // ── Load persisted overrides on mount ──────────────────────────────────────
  useEffect(() => {
    async function loadOverrides() {
      const sessionId = getStoredSessionId();
      if (!sessionId || !API_BASE) { setOverridesLoaded(true); return; }
      try {
        const res = await fetch(appendSessionId(`${API_BASE}/api/nova-overrides`));
        if (!res.ok) { setOverridesLoaded(true); return; }
        const data = await res.json();
        if (Array.isArray(data.overrides)) {
          const map: Record<string, NovaIssueOverride> = {};
          for (const r of data.overrides) {
            if (r.id) map[r.id] = r as NovaIssueOverride;
          }
          setIssueOverrides(map);
        }
      } catch (err) {
        console.warn("[Nova] Failed to load persisted overrides:", err);
      } finally {
        setOverridesLoaded(true);
      }
    }
    loadOverrides();
  }, []);

  // ── Save override: optimistic local update + backend persist ──────────────
  const handleSaveOverride = useCallback(async (record: NovaIssueOverride) => {
    setIssueOverrides((prev) => ({ ...prev, [record.id]: record }));
    const sessionId = getStoredSessionId();
    if (!sessionId || !API_BASE) return;
    try {
      const res = await fetch(`${API_BASE}/api/nova-overrides`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...record, session_id: sessionId }),
      });
      if (!res.ok) {
        const text = await res.text().catch(() => "(no body)");
        console.warn(`[Nova] Override save failed (${res.status}): ${text}`);
      }
    } catch (err) {
      console.warn("[Nova] Override save network error:", err);
    }
  }, []);

  // ── Stable item list ───────────────────────────────────────────────────────
  const qaItemsWithIds = useMemo(
    () => qaFlags.items.map((item, index) => ({
      item,
      index,
      issueId: buildIssueId(item, index),
    })),
    [qaFlags.items],
  );

  useEffect(() => {
    if (!onOverrideSourcesChange) return;
    const sourceFiles = qaItemsWithIds
      .filter(({ issueId }) => Boolean(issueOverrides[issueId]))
      .map(({ item }) => item.sourceFile)
      .filter((sourceFile) => sourceFile.trim().length > 0);
    onOverrideSourcesChange(Array.from(new Set(sourceFiles)));
  }, [issueOverrides, onOverrideSourcesChange, qaItemsWithIds]);

  // ── Override-aware status (computed after overrides load) ──────────────────
  // While loading, fall back to engine status so there's no flash of wrong colour.
  const overrideResult: OverrideAwareResult | null = overridesLoaded
    ? computeOverrideAwareStatus(billingReadiness.status, qaItemsWithIds, issueOverrides)
    : null;

  const displayStatus    = overrideResult?.status    ?? (billingReadiness.status as DisplayStatus);
  const displayLabel     = overrideResult?.statusLabel ?? billingReadiness.statusLabel;
  // Override reasons (if any) replace engine reasons; otherwise show engine reasons.
  const displayReasons   = (overrideResult?.reasons?.length ?? 0) > 0
    ? (overrideResult!.reasons)
    : billingReadiness.reasons;
  const overrideSummary  = overrideResult?.summary ?? { reviewed: 0, accepted: 0, needsRework: 0 };
  const totalOverrides   = overrideSummary.reviewed + overrideSummary.accepted + overrideSummary.needsRework;

  const statusStyle = STATUS_STYLE[displayStatus] ?? STATUS_STYLE["Blocked"];

  // Reasons pagination
  const visibleReasons   = allReasonsExpanded
    ? displayReasons
    : displayReasons.slice(0, REASONS_VISIBLE_DEFAULT);
  const hiddenReasonCount = displayReasons.length - REASONS_VISIBLE_DEFAULT;

  const noData =
    jobOverview.totalGroups === 0 &&
    planIntelligence.signalCount === 0 &&
    exceptionNotes.length === 0;

  // Top issues: errors first, warnings second — cap at 3 for summary, exclude info
  const actionableItems = [
    ...qaItemsWithIds.filter(({ item }) => item.severity === "error"),
    ...qaItemsWithIds.filter(({ item }) => item.severity === "warning"),
  ];
  const topIssues       = actionableItems.slice(0, 3);
  const totalActionable = actionableItems.length;

  const topActions = recommendedActions.slice(0, 3);

  const hasDetails =
    qaFlags.items.length > 0 ||
    exceptionNotes.length > 0 ||
    billingReadiness.warnings.length > 0;

  return (
    <div
      style={{
        border: "1px solid #c7d9f0",
        borderRadius: 16,
        background: "#f5f9ff",
        padding: "14px 16px",
        minWidth: 0,
        overflow: "hidden",
      }}
    >
      {/* ── Header (hidden when card is inside a panel that provides its own header) ── */}
      {!hideHeader && (
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 8,
            marginBottom: 12,
          }}
        >
          <span style={{ fontSize: 13, fontWeight: 800, color: "#0f172a", letterSpacing: "-0.01em" }}>
            Nova — Job Intelligence
          </span>
          <span style={{ fontSize: 11, color: overridesLoaded ? "#94a3b8" : "#cbd5e1" }}>
            {overridesLoaded ? "review layer · persisted" : "loading…"}
          </span>
        </div>
      )}

      {/* ── Readiness status block ───────────────────────────────────────────── */}
      <div
        style={{
          background: "#ffffff",
          border: `1.5px solid ${statusStyle.border}`,
          borderRadius: 10,
          padding: "10px 12px",
          marginBottom: 14,
        }}
      >
        {/* Pill + label */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
          <span
            title={STATUS_TOOLTIP[displayStatus]}
            style={{
              background: statusStyle.bg,
              color: statusStyle.color,
              borderRadius: 999,
              padding: "3px 11px",
              fontSize: 12,
              fontWeight: 800,
              letterSpacing: "0.02em",
              flexShrink: 0,
            }}
          >
            {displayStatus}
          </span>
          <span style={{ fontSize: 14, fontWeight: 700, color: "#0f172a" }}>
            {displayLabel}
          </span>
        </div>

        {/* Compact override summary — only when overrides exist */}
        {totalOverrides > 0 && (
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "4px 12px",
              marginBottom: 8,
              padding: "5px 8px",
              background: "#f8f7ff",
              border: "1px solid #e9d5ff",
              borderRadius: 6,
            }}
          >
            <span style={{ fontSize: 10, fontWeight: 700, color: "#6d28d9", marginRight: 4 }}>
              Overrides:
            </span>
            {overrideSummary.reviewed > 0 && (
              <span style={{ fontSize: 10, color: "#1d4ed8" }}>
                {overrideSummary.reviewed} reviewed
              </span>
            )}
            {overrideSummary.accepted > 0 && (
              <span style={{ fontSize: 10, color: "#15803d" }}>
                {overrideSummary.accepted} accepted
              </span>
            )}
            {overrideSummary.needsRework > 0 && (
              <span style={{ fontSize: 10, color: "#c2410c", fontWeight: 700 }}>
                {overrideSummary.needsRework} needs rework
              </span>
            )}
          </div>
        )}

        {/* "Reviewed" status caveat — reminds user this is human decision, not engine clearance */}
        {displayStatus === "Reviewed" && (
          <div
            style={{
              fontSize: 11,
              color: "#6d28d9",
              background: "#f8f7ff",
              border: "1px solid #e9d5ff",
              borderRadius: 6,
              padding: "5px 8px",
              marginBottom: 8,
              lineHeight: 1.5,
            }}
          >
            ⚠ Human review recorded — engine-detected issues remain present. This does not replace a technical resolution.
          </div>
        )}

        {/* Reasons list */}
        {visibleReasons.length > 0 && (
          <ul style={{ margin: 0, paddingLeft: 16, display: "grid", gap: 3 }}>
            {visibleReasons.map((r, i) => (
              <li key={i} style={{ fontSize: 12, color: "#475569", lineHeight: 1.5 }}>{r}</li>
            ))}
          </ul>
        )}

        {/* Show more / fewer reasons toggle */}
        {hiddenReasonCount > 0 && (
          <button
            onClick={() => setAllReasonsExpanded((v) => !v)}
            style={{
              marginTop: 6,
              fontSize: 11,
              color: "#64748b",
              background: "none",
              border: "none",
              cursor: "pointer",
              padding: "0",
              textDecoration: "underline",
              textUnderlineOffset: 2,
            }}
          >
            {allReasonsExpanded
              ? "Show fewer"
              : `Show ${hiddenReasonCount} more reason${hiddenReasonCount > 1 ? "s" : ""}`}
          </button>
        )}
      </div>

      {/* ── No-data placeholder ──────────────────────────────────────────────── */}
      {noData ? (
        <div style={{ fontSize: 13, color: "#64748b", lineHeight: 1.5 }}>
          Upload a KMZ and structured bore logs to generate job intelligence.
        </div>
      ) : (
        <>
          {/* ── Summary counts ────────────────────────────────────────────── */}
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "5px 14px",
              padding: "8px 10px",
              background: "#edf2fb",
              borderRadius: 8,
              marginBottom: 14,
            }}
          >
            <SummaryCount label="groups" value={jobOverview.totalGroups} />
            <SummaryCount label="rendered" value={jobOverview.renderedGroups} accent="#16a34a" />
            {jobOverview.blockedGroups > 0 && (
              <SummaryCount label="blocked" value={jobOverview.blockedGroups} accent="#dc2626" />
            )}
            {planIntelligence.signalCount > 0 && (
              <SummaryCount
                label={`plan${planIntelligence.signalCount !== 1 ? "s" : ""} loaded`}
                value={planIntelligence.signalCount}
              />
            )}
            {jobOverview.totalExceptionCost !== 0 && (
              <SummaryCount label="exceptions" value={toMoney(jobOverview.totalExceptionCost)} />
            )}
          </div>

          {/* ── Top Issues ────────────────────────────────────────────────── */}
          {topIssues.length > 0 && (
            <div style={{ marginBottom: 14 }}>
              <SectionLabel>
                Top Issues{totalActionable > 3 ? ` (${totalActionable} total)` : ""}
              </SectionLabel>
              <div style={{ display: "grid", gap: 5 }}>
                {topIssues.map(({ item, issueId }, i) => {
                  const sty = SEVERITY_STYLE[item.severity];
                  const override = issueOverrides[issueId];
                  const badgeStyle = override ? OVERRIDE_BADGE_STYLE[override.decision] : undefined;
                  return (
                    <div
                      key={i}
                      style={{
                        display: "flex",
                        alignItems: "flex-start",
                        gap: 6,
                        fontSize: 13,
                        color: sty.color,
                        lineHeight: 1.4,
                      }}
                    >
                      <span style={{ flexShrink: 0, marginTop: 1 }}>{sty.icon}</span>
                      <span style={{ display: "grid", gap: 3, flex: 1, minWidth: 0 }}>
                        <span>{item.issue}</span>
                        <span style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                          {override && badgeStyle && (
                            <span
                              title={overrideTooltip(override)}
                              style={{
                                width: "fit-content",
                                border: `1px solid ${badgeStyle.border}`,
                                background: badgeStyle.bg,
                                color: badgeStyle.color,
                                borderRadius: 999,
                                padding: "1px 7px",
                                fontSize: 10,
                                fontWeight: override.decision === "Accepted Override" ? 900 : 800,
                              }}
                            >
                              {override.decision}
                            </span>
                          )}
                          {onFocusIssue && (
                            <button
                              onClick={() => {
                                const rawItem = item as unknown as Record<string, unknown>;
                                const rawGroupIdx = rawItem.group_idx ?? rawItem.groupIdx;
                                onFocusIssue({
                                  issueId,
                                  source_file: item.sourceFile,
                                  group_idx: typeof rawGroupIdx === "number" ? rawGroupIdx : null,
                                  issue_key: issueId,
                                  severity: item.severity,
                                  raw_reasons: item.rawReasons,
                                  item,
                                });
                              }}
                              style={{
                                border: "1px solid #bfdbfe",
                                background: "#eff6ff",
                                color: "#1d4ed8",
                                borderRadius: 999,
                                padding: "1px 7px",
                                fontSize: 10,
                                fontWeight: 800,
                                cursor: "pointer",
                              }}
                            >
                              Focus on map
                            </button>
                          )}
                        </span>
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* ── Next Actions ──────────────────────────────────────────────── */}
          {topActions.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <button
                onClick={() => setNextActionsExpanded((v) => !v)}
                style={{
                  width: "100%",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: 8,
                  padding: "6px 8px",
                  border: "1px solid #dbe4ee",
                  borderRadius: 8,
                  background: "#ffffff",
                  cursor: "pointer",
                  textAlign: "left",
                  marginBottom: nextActionsExpanded ? 8 : 0,
                }}
              >
                <span style={{ fontSize: 10, fontWeight: 800, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.08em" }}>
                  Next Actions ({topActions.length})
                </span>
                <span style={{ fontSize: 11, color: "#94a3b8", fontWeight: 700 }}>
                  {nextActionsExpanded ? "Hide ▲" : "Show ▼"}
                </span>
              </button>
              {nextActionsExpanded && (
                <ol style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 4 }}>
                  {topActions.map((action, i) => (
                    <li key={i} style={{ fontSize: 13, color: "#334155", lineHeight: 1.5 }}>
                      {action}
                    </li>
                  ))}
                </ol>
              )}
            </div>
          )}

          {/* ── Plan intelligence summary ──────────────────────────────────── */}
          {planIntelligence.planSupportedBoreLogs.length > 0 && (
            <div style={{ fontSize: 12, color: "#15803d", marginBottom: 12 }}>
              ✓ Plan-confirmed: {planIntelligence.planSupportedBoreLogs.join(", ")}
            </div>
          )}

          {/* ── Show / Hide Details toggle ─────────────────────────────────── */}
          {hasDetails && (
            <button
              onClick={() => setDetailsExpanded((v) => !v)}
              style={{
                width: "100%",
                padding: "6px 0",
                fontSize: 12,
                fontWeight: 600,
                color: "#475569",
                background: "#e2e8f0",
                border: "none",
                borderRadius: 8,
                cursor: "pointer",
                letterSpacing: "0.01em",
              }}
            >
              {detailsExpanded ? "Hide Details ▲" : "Show Details ▼"}
            </button>
          )}

          {/* ── Details panel ─────────────────────────────────────────────── */}
          {detailsExpanded && (
            <div style={{ marginTop: 14, display: "grid", gap: 14 }}>

              {/* All QA flags — each with expand toggle + override panel */}
              {qaFlags.items.length > 0 && (
                <div>
                  <SectionLabel>All QA Flags ({qaFlags.items.length})</SectionLabel>
                  <div style={{ display: "grid", gap: 6 }}>
                    {qaItemsWithIds.map(({ item, issueId }) => (
                      <QaFlagDetail
                        key={issueId}
                        item={item}
                        issueId={issueId}
                        override={issueOverrides[issueId]}
                        onSaveOverride={handleSaveOverride}
                        onFocusIssue={onFocusIssue}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* Exception notes */}
              {exceptionNotes.length > 0 && (
                <div>
                  <SectionLabel>Exception Notes</SectionLabel>
                  <div style={{ display: "grid", gap: 5 }}>
                    {exceptionNotes.map((e, i) => (
                      <div
                        key={i}
                        style={{
                          fontSize: 12,
                          color: "#334155",
                          display: "flex",
                          flexWrap: "wrap",
                          gap: 6,
                          alignItems: "baseline",
                          padding: "5px 8px",
                          background: "#f1f5f9",
                          borderRadius: 6,
                        }}
                      >
                        <span style={{ fontWeight: 600 }}>{e.label}:</span>
                        <span>{toMoney(Number.parseFloat(e.amount))}</span>
                        {e.note ? (
                          <span style={{ color: "#64748b", fontStyle: "italic" }}>— {e.note}</span>
                        ) : (
                          <span style={{ color: "#f59e0b", fontSize: 11 }}>no note</span>
                        )}
                        {e.station && (
                          <span style={{ color: "#94a3b8", fontSize: 11 }}>sta. {e.station}</span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Warnings */}
              {billingReadiness.warnings.length > 0 && (
                <div
                  style={{
                    background: "#fffbeb",
                    border: "1px solid #fde68a",
                    borderRadius: 8,
                    padding: "8px 10px",
                    display: "grid",
                    gap: 3,
                  }}
                >
                  {billingReadiness.warnings.map((w, i) => (
                    <div key={i} style={{ fontSize: 12, color: "#92400e" }}>⚠ {w}</div>
                  ))}
                </div>
              )}

              {/* Full actions list if more than 3 */}
              {recommendedActions.length > 3 && (
                <div>
                  <SectionLabel>All Actions ({recommendedActions.length})</SectionLabel>
                  <ol style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 4 }}>
                    {recommendedActions.map((action, i) => (
                      <li key={i} style={{ fontSize: 12, color: "#334155", lineHeight: 1.5 }}>
                        {action}
                      </li>
                    ))}
                  </ol>
                </div>
              )}

            </div>
          )}
        </>
      )}
    </div>
  );
}
