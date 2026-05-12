"use client";

// Phase 1B — KMZ semantic ingestion diagnostics panel.
//
// Read-only debug surface for engineers. Renders nothing in production
// unless NEXT_PUBLIC_SHOW_SEMANTIC_DIAG is "1" or "true" at build time.
//
// Architectural rules observed:
//   * No map mutations — never touches ModernHeroMap or RedlineMap.
//   * No state mutations — does not POST anywhere; consumes
//     /api/current-state read-only.
//   * No expensive polling — fetches once on mount, re-fetches only when
//     `refreshVersion` (bumped after KMZ uploads) increments.
//   * No overlays — does not draw on the map.
//   * Renders nothing when kmz_semantic is absent.
//
// The panel is intentionally compact and uses existing tl-* styling so it
// blends into the workspace without introducing new design.

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

import { appendSessionId } from "@/lib/session";
import { apiFetch } from "@/lib/apiFetch";
import type {
  BackendState,
  IngestionLedgerEntry,
  IngestionLedgerResponse,
  KmzFidelityAuditResponse,
  MatchShadowCompareEntry,
  MatchShadowCompareResponse,
  MatchShadowDisagreementEntry,
  MatchShadowDisagreementResponse,
  MatchShadowSummaryResponse,
  EndpointSnapRecommendationsResponse,
  ReviewedSnapPreviewResponse,
  SnapPreviewMarkersResponse,
  SnapReviewDecision,
  SnapReviewEventRecord,
  SnapReviewEventsSummary,
  SnapReviewEventsResponse,
  RedlineEndpointValidationResponse,
  RedlineNodeContinuityResponse,
  RedlineTopologyContinuityResponse,
  ReviewLabelCurrentResponse,
  ReviewLabelSummaryResponse,
  ReviewLabelValue,
  SemanticKmz,
  SemanticKmzClassification,
  SemanticKmzClassificationDebug,
  SemanticKmzFeature,
  SemanticMatchShadow,
  SemanticMatchShadowGroup,
} from "@/lib/types/backend";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/+$/, "") ||
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, "") ||
  "http://127.0.0.1:8000";

type Props = {
  projectId?: string;
  refreshVersion?: number;
};

const SAMPLE_CLASSES: SemanticKmzClassification[] = [
  "handhole",
  "station_label",
  "reel",
  "structure_marker",
  "annotation",
  "unknown",
];

/** Read-only text scan for diagnostics; does not affect matching. */
function featureDiagnosticTextBlob(f: SemanticKmzFeature): string {
  const ext = Object.entries(f.extended_data ?? {})
    .map(([k, v]) => `${k}:${v}`)
    .join("\n");
  return `${f.placemark_name}\n${f.description}\n${f.description_raw}\n${ext}`;
}

function placemarkHasSpliceRelatedSignal(f: SemanticKmzFeature): boolean {
  const t = featureDiagnosticTextBlob(f);
  return (
    /\bsplice\b/i.test(t) ||
    /\bsplicing\b/i.test(t) ||
    /\bfosc\b/i.test(t) ||
    /\bsplice\s*closure/i.test(t) ||
    /\bsplicecase\b/i.test(t)
  );
}

function placemarkHasNodeLikeToken(f: SemanticKmzFeature): boolean {
  const t = `${f.placemark_name}\n${f.description}`;
  return (
    /\bnode\b/i.test(t) ||
    /\bjunction\b/i.test(t) ||
    /\bpedestal\b/i.test(t) ||
    /\bmanhole\b/i.test(t)
  );
}

type RedlineUsefulTopRow = { label: string; count: number };

type RedlineUsefulSignalsModel = {
  anchorCount: number;
  structureMarker: number;
  routeSegment: number;
  handhole: number;
  nodeLikeHints: number;
  spliceRelated: number;
  topRouteFolders: RedlineUsefulTopRow[];
  topRouteStyles: RedlineUsefulTopRow[];
  folderStyleSource: "route_segment" | "index_fallback";
  warnings: string[];
  verdict: string;
};

function sortCountMapTop(
  m: Map<string, number>,
  limit: number,
): RedlineUsefulTopRow[] {
  return [...m.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, limit)
    .map(([label, count]) => ({ label, count }));
}

/** Pure summary for the semantic diagnostics panel only. */
function computeRedlineUsefulSignals(semantic: SemanticKmz): RedlineUsefulSignalsModel {
  const idx = semantic.index;
  const bc = idx.by_classification ?? {};
  const anchorCount = idx.anchor_catalog?.length ?? 0;
  const structureMarker = bc.structure_marker ?? 0;
  const routeSegment = bc.route_segment ?? 0;
  const handhole = bc.handhole ?? 0;

  let nodeLikeHints = 0;
  let spliceRelated = 0;
  const routeFolders = new Map<string, number>();
  const routeStyles = new Map<string, number>();

  for (const f of semantic.features) {
    if (placemarkHasNodeLikeToken(f)) nodeLikeHints += 1;
    if (placemarkHasSpliceRelatedSignal(f)) spliceRelated += 1;
    if (f.classification === "route_segment") {
      const folderKey =
        f.folder_path_str?.trim() ||
        (f.folder_path?.length ? f.folder_path.join(" / ") : "") ||
        "(root)";
      routeFolders.set(folderKey, (routeFolders.get(folderKey) ?? 0) + 1);
      const su = (f.style_url ?? "").trim() || "—";
      routeStyles.set(su, (routeStyles.get(su) ?? 0) + 1);
    }
  }

  let topRouteFolders = sortCountMapTop(routeFolders, 5);
  let topRouteStyles = sortCountMapTop(routeStyles, 5);
  let folderStyleSource: "route_segment" | "index_fallback" = "route_segment";

  if (routeSegment === 0) {
    folderStyleSource = "index_fallback";
    topRouteFolders = (idx.top_folders ?? []).slice(0, 5).map((r) => ({
      label: r.folder_path_str || "(root)",
      count: r.count,
    }));
    topRouteStyles = (idx.top_style_urls ?? []).slice(0, 5).map((r) => ({
      label: r.style_url || "—",
      count: r.count,
    }));
  }

  const warnings: string[] = [];
  if (idx.truncated) {
    warnings.push(
      "Ingestion hit feature_cap; semantic counts may be incomplete and signals under-reported.",
    );
  }
  if (routeSegment === 0) {
    warnings.push(
      "No placemarks classified as route_segment; route matching still relies on legacy line extraction, not semantic route rows.",
    );
  }
  if (structureMarker === 0 && handhole === 0 && anchorCount === 0) {
    warnings.push(
      "Weak anchor signal: no structure markers, classified handholes, or anchor_catalog entries.",
    );
  } else if (anchorCount === 0 && structureMarker + handhole < 4) {
    warnings.push(
      "Few classified anchor points and an empty anchor_catalog; station-to-KMZ chaining may be coarse.",
    );
  }
  if (routeSegment > 8 && topRouteFolders.length >= 3) {
    const maxShare = topRouteFolders[0].count / routeSegment;
    if (maxShare < 0.2) {
      warnings.push(
        "Route segments are spread across many folders; disambiguation by print/name/folder may dominate.",
      );
    }
  }

  const anchorish = anchorCount + structureMarker + handhole;
  const strong = routeSegment > 0 && anchorish > 0;
  const verdict = strong
    ? "This KMZ shows redline-useful semantic signals (anchors and/or route rows). Diagnostic only — matching is unchanged."
    : "Semantic layer looks thin for redline-style anchoring; expect heavier reliance on legacy KMZ extraction. Diagnostic only.";

  return {
    anchorCount,
    structureMarker,
    routeSegment,
    handhole,
    nodeLikeHints,
    spliceRelated,
    topRouteFolders,
    topRouteStyles,
    folderStyleSource,
    warnings,
    verdict,
  };
}

function fmtCoords(coords: [number, number] | null | undefined): string {
  if (!coords) return "—";
  return `${coords[0].toFixed(5)}, ${coords[1].toFixed(5)}`;
}

function classificationColor(label: string): string {
  switch (label) {
    case "handhole":
      return "#a5f3fc";
    case "station_label":
      return "#fde68a";
    case "reel":
      return "#bbf7d0";
    case "structure_marker":
      return "#c4b5fd";
    case "route_segment":
      return "#fda4af";
    case "boundary_polygon":
      return "#fdba74";
    case "annotation":
      return "#e0e7ff";
    default:
      return "#cbd5e1";
  }
}

function confidenceColor(conf: string): string {
  switch (conf) {
    case "high":
      return "#86efac";
    case "medium":
      return "#fde68a";
    case "low":
      return "#fca5a5";
    default:
      return "#cbd5e1";
  }
}

function lifecycleColor(label: string): string {
  switch (label) {
    case "asbuilt":
      return "#86efac";
    case "existing":
      return "#bae6fd";
    case "proposed":
      return "#fde68a";
    case "decommissioned":
      return "#fca5a5";
    case "survey":
      return "#ddd6fe";
    default:
      return "#cbd5e1";
  }
}

export default function KmzSemanticDiagnosticsPanel({
  projectId: projectIdProp,
  refreshVersion = 0,
}: Props) {
  const routeParams = useParams();
  /** Must match project-scoped session storage used by RedlineMap / ModernHeroMap.
   * If `projectId` prop were ever omitted, appendSessionId(undefined) falls back to
   * global `osp_session_id` instead of `osp_session_id:<project>` — a different session. */
  const projectIdForSession = useMemo(() => {
    const fromProp = projectIdProp?.trim();
    if (fromProp) return fromProp;
    const raw = routeParams?.projectId;
    const fromRoute = Array.isArray(raw) ? raw[0] : raw;
    return typeof fromRoute === "string" ? fromRoute.trim() : undefined;
  }, [projectIdProp, routeParams]);

  const [state, setState] = useState<BackendState | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<boolean>(true);
  const [ledgerEntries, setLedgerEntries] = useState<IngestionLedgerEntry[]>([]);
  const [shadowSummary, setShadowSummary] = useState<MatchShadowSummaryResponse | null>(null);
  const [shadowCompareEntries, setShadowCompareEntries] = useState<MatchShadowCompareEntry[]>([]);
  const [disagreementData, setDisagreementData] = useState<MatchShadowDisagreementResponse | null>(null);
  // Phase 1K — label map: key = group_id (or "__null__" for null group_id)
  // → most-recently-applied ReviewLabelValue for this session / pass.
  // Observability-only. Never alters disagreement rendering or sort order.
  const [labelMap, setLabelMap] = useState<Record<string, ReviewLabelValue>>({});
  // Phase 1L — compute-on-read review label analytics summary.
  // Fetched once on mount; re-fetched when refreshVersion increments.
  // Observability-only. Never alters any operational behavior.
  const [reviewLabelSummary, setReviewLabelSummary] = useState<ReviewLabelSummaryResponse | null>(null);
  // Phase 1M — KMZ engineering fidelity audit.
  // Fetched once on mount; re-fetched when refreshVersion increments.
  // Observability-only. Never alters any operational behavior.
  const [fidelityAudit, setFidelityAudit] = useState<KmzFidelityAuditResponse | null>(null);
  // Phase 1P — redline topology continuity advisor.
  // Fetched once on mount; re-fetched when refreshVersion increments.
  // Advisory only. Never alters matching, scoring, redline geometry, or billing.
  const [continuitAdvisor, setContinuityAdvisor] = useState<RedlineTopologyContinuityResponse | null>(null);
  // Phase 1Q — node-anchored redline continuity advisor.
  // Advisory only. Groups segments by endpoint coincidence with KMZ handholes/nodes.
  // Never alters any operational behavior.
  const [nodeAdvisor, setNodeAdvisor] = useState<RedlineNodeContinuityResponse | null>(null);
  // Phase 1S — bore-log redline endpoint validator.
  // Advisory only. Classifies each redline endpoint as anchored/near/orphan/no_anchors_in_kmz.
  // Never alters any operational behavior.
  const [endpointValidation, setEndpointValidation] = useState<RedlineEndpointValidationResponse | null>(null);
  // Phase 1T — deterministic endpoint snap recommendations.
  // Advisory only. Candidate anchor coordinates for near/orphan endpoints.
  // Never alters any operational behavior.
  const [snapRecs, setSnapRecs] = useState<EndpointSnapRecommendationsResponse | null>(null);
  // Phase 1U — snap review events + current decisions.
  const [snapReviewSummary, setSnapReviewSummary] = useState<SnapReviewEventsSummary | null>(null);
  // Map of "<segment_id>|<endpoint>" → latest non-revoked event (or undefined = unreviewed)
  const [snapDecisions, setSnapDecisions] = useState<Record<string, SnapReviewEventRecord | null>>({});
  // Phase 1V — snap preview markers (diagnostic-only, OFF by default).
  const [snapMarkers, setSnapMarkers] = useState<SnapPreviewMarkersResponse | null>(null);
  // Phase 1W — reviewed snap geometry preview (diagnostic-only, OFF by default).
  const [snapPreview, setSnapPreview] = useState<ReviewedSnapPreviewResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load(): Promise<void> {
      setLoading(true);
      setError(null);
      try {
        const res = await apiFetch(
          appendSessionId(`${API_BASE}/api/current-state`, projectIdForSession),
          { cache: "no-store" },
        );
        const data = (await res.json()) as BackendState;
        if (!res.ok || data.success === false) {
          throw new Error(data.error || "Unable to load semantic diagnostics.");
        }
        if (!cancelled) setState(data);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [projectIdForSession, refreshVersion]);

  // Phase 1D — fetch ingestion ledger once on mount; re-fetch when
  // refreshVersion increments (same trigger as the main state fetch).
  // No polling. Does not mutate STATE or affect matching/rendering.
  useEffect(() => {
    let cancelled = false;
    async function loadLedger(): Promise<void> {
      try {
        const res = await apiFetch(
          `${API_BASE}/api/observability/ingestion-ledger?limit=10`,
          { cache: "no-store" },
        );
        if (!res.ok) return;
        const data = (await res.json()) as IngestionLedgerResponse;
        if (!cancelled && Array.isArray(data.entries)) {
          setLedgerEntries(data.entries);
        }
      } catch {
        // Silently ignore — ledger is diagnostic only.
      }
    }
    void loadLedger();
    return () => {
      cancelled = true;
    };
  }, [refreshVersion]);

  // Phase 1H-C — fetch shadow-compare summary + recent compare rows.
  // Fetch once on mount; re-fetch only when refreshVersion increments.
  // No polling. Silent failure. Does not affect matching/rendering.
  useEffect(() => {
    let cancelled = false;
    async function loadShadow(): Promise<void> {
      try {
        const [summaryRes, compareRes] = await Promise.all([
          apiFetch(`${API_BASE}/api/observability/match-shadow-summary?limit=500`, {
            cache: "no-store",
          }),
          apiFetch(`${API_BASE}/api/observability/match-shadow-compare?limit=10`, {
            cache: "no-store",
          }),
        ]);
        if (!cancelled && summaryRes.ok) {
          const data = (await summaryRes.json()) as MatchShadowSummaryResponse;
          if (typeof data?.window?.rows_read === "number") {
            setShadowSummary(data);
          }
        }
        if (!cancelled && compareRes.ok) {
          const data = (await compareRes.json()) as MatchShadowCompareResponse;
          if (Array.isArray(data?.entries)) {
            setShadowCompareEntries(data.entries);
          }
        }
      } catch {
        // Silently ignore — shadow review is diagnostic only.
      }
    }
    void loadShadow();
    return () => {
      cancelled = true;
    };
  }, [refreshVersion]);

  // Phase 1I-B — fetch disagreement drilldown rows.
  // Fetch once on mount; re-fetch only when refreshVersion increments.
  // No polling. Silent failure. Does not affect matching/rendering.
  useEffect(() => {
    let cancelled = false;
    async function loadDisagreements(): Promise<void> {
      try {
        const res = await apiFetch(
          `${API_BASE}/api/observability/match-shadow-disagreements?limit=500&min_review_priority=standard`,
          { cache: "no-store" },
        );
        if (!res.ok) return;
        const data = (await res.json()) as MatchShadowDisagreementResponse;
        if (!cancelled && typeof data?.window?.rows_read === "number") {
          setDisagreementData(data);
        }
      } catch {
        // Silently ignore — drilldown is diagnostic only.
      }
    }
    void loadDisagreements();
    return () => {
      cancelled = true;
    };
  }, [refreshVersion]);

  // Phase 1K — fetch initial label state for the most recent match_pass_id.
  // Runs once after disagreementData populates. Silent failure; observability only.
  useEffect(() => {
    if (!disagreementData?.entries?.length) return;
    const passId = disagreementData.entries[0]?.match_pass_id;
    if (!passId) return;
    let cancelled = false;
    async function loadLabels(): Promise<void> {
      try {
        const res = await apiFetch(
          `${API_BASE}/api/observability/review-labels/current?match_pass_id=${encodeURIComponent(passId ?? "")}`,
          { cache: "no-store" },
        );
        if (!res.ok) return;
        const data = (await res.json()) as ReviewLabelCurrentResponse;
        if (!cancelled && Array.isArray(data?.resolved)) {
          const map: Record<string, ReviewLabelValue> = {};
          for (const r of data.resolved) {
            if (r.label) {
              map[r.group_id ?? "__null__"] = r.label;
            }
          }
          setLabelMap(map);
        }
      } catch {
        // Silently ignore — labels are diagnostic only.
      }
    }
    void loadLabels();
    return () => {
      cancelled = true;
    };
  }, [disagreementData]);

  // Phase 1L — fetch review-label analytics summary.
  // Fetch once on mount; re-fetch only when refreshVersion increments.
  // No polling. Silent failure. Does not affect matching/rendering.
  useEffect(() => {
    let cancelled = false;
    async function loadReviewLabelSummary(): Promise<void> {
      try {
        const res = await apiFetch(
          `${API_BASE}/api/observability/review-label-summary`,
          { cache: "no-store" },
        );
        if (!res.ok) return;
        const data = (await res.json()) as ReviewLabelSummaryResponse;
        if (!cancelled && typeof data?.total_review_labels === "number") {
          setReviewLabelSummary(data);
        }
      } catch {
        // Silently ignore — analytics summary is diagnostic only.
      }
    }
    void loadReviewLabelSummary();
    return () => {
      cancelled = true;
    };
  }, [refreshVersion]);

  // Phase 1M — fetch KMZ engineering fidelity audit.
  // Fetch once on mount; re-fetch only when refreshVersion increments.
  // No polling. Silent failure. Does not affect matching/rendering.
  useEffect(() => {
    let cancelled = false;
    async function loadFidelityAudit(): Promise<void> {
      try {
        const res = await apiFetch(
          `${API_BASE}/api/observability/kmz-fidelity-audit`,
          { cache: "no-store" },
        );
        if (!res.ok) return;
        const data = (await res.json()) as KmzFidelityAuditResponse;
        if (!cancelled && typeof data?.window?.semantic_feature_count === "number") {
          setFidelityAudit(data);
        }
      } catch {
        // Silently ignore — fidelity audit is diagnostic only.
      }
    }
    void loadFidelityAudit();
    return () => {
      cancelled = true;
    };
  }, [refreshVersion]);

  // Phase 1P — fetch redline topology continuity advisor.
  // Fetch once on mount; re-fetch only when refreshVersion increments.
  // No polling. Silent failure. Advisory only — never affects operational behavior.
  useEffect(() => {
    let cancelled = false;
    async function loadContinuityAdvisor(): Promise<void> {
      try {
        const res = await apiFetch(
          `${API_BASE}/api/observability/redline-topology-continuity`,
          { cache: "no-store" },
        );
        if (!res.ok) return;
        const data = (await res.json()) as RedlineTopologyContinuityResponse;
        if (!cancelled && Array.isArray(data?.groups)) {
          setContinuityAdvisor(data);
        }
      } catch {
        // Silently ignore — continuity advisor is advisory only.
      }
    }
    void loadContinuityAdvisor();
    return () => {
      cancelled = true;
    };
  }, [refreshVersion]);

  // Phase 1Q — fetch node-anchored redline continuity advisor.
  // Silent failure. Advisory only — never affects operational behavior.
  useEffect(() => {
    let cancelled = false;
    async function loadNodeAdvisor(): Promise<void> {
      try {
        const res = await apiFetch(
          `${API_BASE}/api/observability/redline-node-continuity`,
          { cache: "no-store" },
        );
        if (!res.ok) return;
        const data = (await res.json()) as RedlineNodeContinuityResponse;
        if (!cancelled && Array.isArray(data?.groups)) {
          setNodeAdvisor(data);
        }
      } catch {
        // Silently ignore — node continuity advisor is advisory only.
      }
    }
    void loadNodeAdvisor();
    return () => {
      cancelled = true;
    };
  }, [refreshVersion]);

  // Phase 1S — fetch bore-log redline endpoint validator.
  // Silent failure. Advisory only — never affects operational behavior.
  useEffect(() => {
    let cancelled = false;
    async function loadEndpointValidation(): Promise<void> {
      try {
        const res = await apiFetch(
          `${API_BASE}/api/observability/redline-endpoint-validation`,
          { cache: "no-store" },
        );
        if (!res.ok) return;
        const data = (await res.json()) as RedlineEndpointValidationResponse;
        if (!cancelled && typeof data?.schema_version === "string") {
          setEndpointValidation(data);
        }
      } catch {
        // Silently ignore — endpoint validator is advisory only.
      }
    }
    void loadEndpointValidation();
    return () => {
      cancelled = true;
    };
  }, [refreshVersion]);

  // Phase 1T — fetch deterministic endpoint snap recommendations.
  // Silent failure. Advisory only — never affects operational behavior.
  useEffect(() => {
    let cancelled = false;
    async function loadSnapRecs(): Promise<void> {
      try {
        const res = await apiFetch(
          `${API_BASE}/api/observability/endpoint-snap-recommendations`,
          { cache: "no-store" },
        );
        if (!res.ok) return;
        const data = (await res.json()) as EndpointSnapRecommendationsResponse;
        if (!cancelled && typeof data?.schema_version === "string") {
          setSnapRecs(data);
        }
      } catch {
        // Silently ignore — snap recommendations are advisory only.
      }
    }
    void loadSnapRecs();
    return () => {
      cancelled = true;
    };
  }, [refreshVersion]);

  // Phase 1U — fetch snap review events + compute current decisions.
  // Silent failure. Advisory only — never affects operational behavior.
  const refreshSnapReviews = useCallback(async () => {
    try {
      const res = await apiFetch(
        `${API_BASE}/api/observability/snap-review-events?limit=1000`,
        { cache: "no-store" },
      );
      if (!res.ok) return;
      const data = (await res.json()) as SnapReviewEventsResponse;
      if (data?.summary) setSnapReviewSummary(data.summary);
      // Compute current decisions client-side: latest-wins per key.
      const resolved: Record<string, SnapReviewEventRecord | null> = {};
      for (const ev of (data.events ?? []).slice().reverse()) {
        const k = `${ev.recommendation_key?.segment_id}|${ev.recommendation_key?.endpoint}`;
        if (!(k in resolved)) {
          resolved[k] = ev.decision === "revoked" ? null : ev;
        }
      }
      setSnapDecisions(resolved);
    } catch {
      // Silently ignore — snap review events are advisory only.
    }
  }, []);

  useEffect(() => {
    void refreshSnapReviews();
  }, [refreshVersion, refreshSnapReviews]);

  // Phase 1V — fetch snap preview markers (diagnostic-only).
  // Refreshed whenever decisions change, since markers carry decision badges.
  const refreshSnapMarkers = useCallback(async () => {
    try {
      const res = await apiFetch(
        `${API_BASE}/api/observability/snap-preview-markers`,
        { cache: "no-store" },
      );
      if (!res.ok) return;
      const data = (await res.json()) as SnapPreviewMarkersResponse;
      setSnapMarkers(data);
    } catch {
      // Silently ignore — markers are advisory review aids only.
    }
  }, []);

  useEffect(() => {
    void refreshSnapMarkers();
  }, [refreshVersion, snapDecisions, refreshSnapMarkers]);

  // Phase 1W — fetch reviewed snap preview (diagnostic-only).
  const refreshSnapPreview = useCallback(async () => {
    try {
      const res = await apiFetch(
        `${API_BASE}/api/observability/reviewed-snap-preview`,
        { cache: "no-store" },
      );
      if (!res.ok) return;
      const data = (await res.json()) as ReviewedSnapPreviewResponse;
      setSnapPreview(data);
    } catch {
      // Silently ignore — preview is advisory review aid only.
    }
  }, []);

  useEffect(() => {
    void refreshSnapPreview();
  }, [refreshVersion, snapDecisions, refreshSnapPreview]);

  const semantic: SemanticKmz | null = state?.kmz_semantic ?? null;

  const featureMap = useMemo(() => {
    const map = new Map<string, SemanticKmzFeature>();
    if (!semantic) return map;
    for (const feature of semantic.features) {
      if (feature?.feature_id) map.set(feature.feature_id, feature);
    }
    return map;
  }, [semantic]);

  const redlineSignalsModel = useMemo(() => {
    if (!semantic || semantic.features.length === 0) return null;
    return computeRedlineUsefulSignals(semantic);
  }, [semantic]);

  // When the panel is mounted (env flag is on) but no semantic payload is
  // available, render a small empty-state card instead of returning null.
  // Without this, the same `null` return covered three indistinguishable
  // failure modes (still loading, payload missing entirely, parser produced
  // zero features) and engineers had no way to tell which was which.
  // The card stays compact and clearly tagged DEBUG so it can't be mistaken
  // for production UI.
  if (loading && !state) {
    return (
      <DiagEmptyState
        statusLabel="Loading…"
        message="Fetching /api/current-state for semantic diagnostics."
        hint={null}
      />
    );
  }
  if (error) {
    return (
      <DiagEmptyState
        statusLabel="Fetch error"
        message={error}
        hint={"Backend may be down or the project session id is unknown."}
      />
    );
  }
  if (!semantic) {
    const hasKmzReference = Boolean(
      state?.kmz_reference &&
        ((state.kmz_reference.line_features?.length ?? 0) > 0 ||
          (state.kmz_reference.polygon_features?.length ?? 0) > 0),
    );
    return (
      <DiagEmptyState
        statusLabel="No semantic data"
        message={
          hasKmzReference
            ? "kmz_reference is populated but kmz_semantic is null. Likely cause: this project's KMZ was uploaded before the Phase 1A semantic parser landed."
            : "No KMZ has been uploaded for this project (kmz_reference is empty), so kmz_semantic is null."
        }
        hint={"Re-upload the KMZ to populate kmz_semantic."}
      />
    );
  }
  if (semantic.features.length === 0) {
    return (
      <DiagEmptyState
        statusLabel="0 features"
        message={`Parser ran (parser_version ${semantic.parser_version}) but produced 0 features. KMZ may contain no <Placemark> elements, or every placemark was skipped by the per-placemark error guard.`}
        hint={"Inspect the source KMZ; if you expect features, this is a parser bug."}
      />
    );
  }

  const idx = semantic.index;
  const featureCount = idx.feature_count;
  const sourceFilenames = idx.source_filenames ?? [];

  return (
    <section
      className="tl-card"
      style={{
        marginTop: 14,
        padding: 0,
        background: "var(--tl-surface)",
        border: "1px dashed rgba(250, 204, 21, 0.45)",
      }}
    >
      <button
        type="button"
        onClick={() => setCollapsed((v) => !v)}
        aria-expanded={!collapsed}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          width: "100%",
          padding: "10px 14px",
          border: "none",
          background: "transparent",
          color: "var(--tl-text)",
          cursor: "pointer",
          textAlign: "left",
          fontFamily: "inherit",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span
            className="tl-pill"
            style={{
              fontSize: 10,
              fontWeight: 800,
              letterSpacing: 0.5,
              color: "#fde68a",
              border: "1px solid rgba(250, 204, 21, 0.55)",
              background: "rgba(250, 204, 21, 0.10)",
              padding: "2px 8px",
              borderRadius: 999,
              textTransform: "uppercase",
            }}
          >
            DEBUG
          </span>
          <span style={{ fontSize: 13, fontWeight: 700 }}>
            Semantic Ingestion · v{semantic.parser_version}
          </span>
          <span style={{ fontSize: 12, color: "var(--tl-text-muted)" }}>
            {featureCount.toLocaleString()} features
          </span>
          {idx.truncated ? (
            <span
              style={{
                fontSize: 10,
                fontWeight: 800,
                color: "#fca5a5",
                border: "1px solid rgba(248, 113, 113, 0.55)",
                background: "rgba(127, 29, 29, 0.18)",
                padding: "1px 7px",
                borderRadius: 999,
                textTransform: "uppercase",
              }}
              title={`Parsing capped at ${idx.feature_cap ?? "feature_cap"} placemarks. Some features may be missing.`}
            >
              TRUNCATED
            </span>
          ) : null}
          {sourceFilenames.length > 0 ? (
            <span style={{ fontSize: 11, color: "var(--tl-text-faint)" }}>
              {sourceFilenames.join(", ")}
            </span>
          ) : null}
        </div>
        <span style={{ fontSize: 11, color: "var(--tl-text-muted)" }}>
          {collapsed ? "Show details ▾" : "Hide details ▴"}
        </span>
      </button>

      {!collapsed ? (
        <div
          style={{
            padding: "0 14px 14px",
            display: "grid",
            gap: 14,
            fontFamily:
              "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
            fontSize: 11,
            color: "var(--tl-text)",
          }}
        >
          {error ? (
            <div
              style={{
                fontSize: 11,
                color: "#fca5a5",
                background: "rgba(127, 29, 29, 0.18)",
                border: "1px solid rgba(248, 113, 113, 0.45)",
                borderRadius: 6,
                padding: "6px 8px",
              }}
            >
              Diagnostics fetch error: {error}
            </div>
          ) : null}

          {redlineSignalsModel ? (
            <DiagRedlineUsefulSignals model={redlineSignalsModel} />
          ) : null}

          <DiagCountSection
            title="By classification"
            entries={Object.entries(idx.by_classification ?? {})}
            colorOf={classificationColor}
          />
          <DiagCountSection
            title="By geometry type"
            entries={Object.entries(idx.by_geometry_type ?? {})}
            colorOf={() => "#cbd5e1"}
          />
          <DiagCountSection
            title="By confidence"
            entries={Object.entries(idx.by_confidence ?? {})}
            colorOf={confidenceColor}
          />

          <DiagExtractionSummary
            featureCount={featureCount}
            withChainage={idx.features_with_chainage}
            withSequence={idx.features_with_sequence}
            withFullGeometry={idx.features_with_full_geometry}
            withResolvedStyle={idx.features_with_resolved_style}
            stylesResolvedCount={idx.styles_resolved_count}
          />

          {idx.by_lifecycle && Object.keys(idx.by_lifecycle).length > 0 ? (
            <DiagCountSection
              title="By lifecycle"
              entries={Object.entries(idx.by_lifecycle)}
              colorOf={lifecycleColor}
            />
          ) : null}

          <DiagTopList
            title={`Top folders (max ${idx.top_folders?.length ?? 0})`}
            items={(idx.top_folders ?? []).map((row) => ({
              key: row.folder_path_str || "(root)",
              count: row.count,
            }))}
          />
          <DiagTopList
            title={`Top styleUrls (max ${idx.top_style_urls?.length ?? 0})`}
            items={(idx.top_style_urls ?? []).map((row) => ({
              key: row.style_url,
              count: row.count,
            }))}
          />
          {(idx.top_resolved_line_colors ?? []).length > 0 ? (
            <DiagColorTopList
              title="Top resolved line colors"
              items={idx.top_resolved_line_colors ?? []}
            />
          ) : null}

          <DiagStyleResolutionHealth
            resolution={idx.style_resolution}
            missingStyleUrls={idx.missing_style_urls ?? []}
          />

          <DiagAnchorCatalog
            entries={idx.anchor_catalog ?? []}
            truncated={Boolean(idx.anchor_catalog_truncated)}
            cap={idx.anchor_cap}
          />

          <DiagKeyList
            title="ExtendedData keys"
            items={idx.extended_data_keys ?? []}
          />

          {SAMPLE_CLASSES.map((cls) => {
            const ids = idx.classification_samples?.[cls] ?? [];
            if (ids.length === 0) return null;
            const samples = ids
              .map((id) => featureMap.get(id))
              .filter((x): x is SemanticKmzFeature => Boolean(x));
            if (samples.length === 0) return null;
            return (
              <DiagSampleSection
                key={cls}
                title={`Sample · ${cls}`}
                colorBar={classificationColor(cls)}
                samples={samples}
              />
            );
          })}

          <DiagClassificationExplainability
            classificationSamples={idx.classification_samples ?? {}}
            featureMap={featureMap}
          />

          <DiagSkippedPlacemarks
            count={idx.skipped_placemark_count ?? 0}
            samples={idx.skipped_placemark_samples ?? []}
            warnings={semantic.warnings ?? []}
          />

          <DiagIngestionLedger entries={ledgerEntries} />

          <DiagSemanticShadowReview
            summary={shadowSummary}
            compareEntries={shadowCompareEntries}
          />

          <DiagSemanticDisagreementDrilldown
            data={disagreementData}
            labelMap={labelMap}
            onLabelChange={(groupId, label) =>
              setLabelMap((prev) => ({ ...prev, [groupId ?? "__null__"]: label }))
            }
          />

          <DiagReviewLabelSummary data={reviewLabelSummary} />

          <DiagKmzFidelityAudit data={fidelityAudit} />

          <DiagRedlineTopologyContinuity data={continuitAdvisor} />

          <DiagRedlineNodeContinuity data={nodeAdvisor} />

          <DiagAnchorGroupedReview data={nodeAdvisor} />

          <DiagRedlineEndpointValidation data={endpointValidation} />

          <DiagEndpointSnapCandidates
            data={snapRecs}
            decisions={snapDecisions}
            reviewSummary={snapReviewSummary}
            onDecisionChange={refreshSnapReviews}
          />
          <DiagSnapPreviewMarkers data={snapMarkers} />
          <DiagReviewedSnapPreview data={snapPreview} />

          {state?.kmz_semantic_match_shadow ? (
            <DiagShadowMatching shadow={state.kmz_semantic_match_shadow} />
          ) : null}

          <div
            style={{
              fontSize: 10,
              color: "var(--tl-text-faint)",
              borderTop: "1px dashed rgba(148, 163, 184, 0.25)",
              paddingTop: 8,
            }}
          >
            Read-only · additive · parser_version {semantic.parser_version} ·
            feature_cap {idx.feature_cap ?? "—"} · sample_cap {idx.sample_cap ?? "—"}
          </div>
        </div>
      ) : null}
    </section>
  );
}

// Phase 1D — collapsed table of recent ingestion ledger rows.
function DiagIngestionLedger({ entries }: { entries: IngestionLedgerEntry[] }) {
  const [open, setOpen] = useState(false);

  if (entries.length === 0) return null;

  return (
    <div
      style={{
        borderTop: "1px solid rgba(148, 163, 184, 0.18)",
        paddingTop: 8,
        marginTop: 8,
      }}
    >
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          background: "none",
          border: "none",
          cursor: "pointer",
          color: "var(--tl-text-faint)",
          fontSize: 11,
          fontWeight: 600,
          padding: "2px 0",
          textAlign: "left",
          width: "100%",
        }}
      >
        {open ? "▾" : "▸"} Ingestion ledger ({entries.length} recent)
      </button>
      {open && (
        <div style={{ overflowX: "auto", marginTop: 4 }}>
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: 10,
              color: "var(--tl-text-faint)",
            }}
          >
            <thead>
              <tr>
                {["ingested_at", "filename", "sha256[:8]", "features", "skipped", "warnings"].map(
                  (h) => (
                    <th
                      key={h}
                      style={{
                        textAlign: "left",
                        padding: "2px 6px",
                        borderBottom: "1px solid rgba(148,163,184,0.2)",
                        fontWeight: 600,
                        whiteSpace: "nowrap",
                      }}
                    >
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {entries.map((e, i) => {
                const ts = (() => {
                  try {
                    return new Date(e.ingested_at).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                      second: "2-digit",
                    });
                  } catch {
                    return e.ingested_at.slice(11, 19);
                  }
                })();
                const hasSkipped = e.skipped_placemark_count > 0;
                const hasWarnings = e.warnings_count > 0;
                return (
                  <tr key={i} style={{ borderBottom: "1px solid rgba(148,163,184,0.1)" }}>
                    <td style={{ padding: "2px 6px", whiteSpace: "nowrap" }}>{ts}</td>
                    <td
                      style={{
                        padding: "2px 6px",
                        maxWidth: 140,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                      title={e.filename}
                    >
                      {e.filename}
                    </td>
                    <td style={{ padding: "2px 6px", fontFamily: "monospace" }}>
                      {e.input_sha256.slice(0, 8)}
                    </td>
                    <td style={{ padding: "2px 6px" }}>{e.feature_count}</td>
                    <td
                      style={{
                        padding: "2px 6px",
                        color: hasSkipped ? "#f87171" : undefined,
                      }}
                    >
                      {e.skipped_placemark_count}
                    </td>
                    <td
                      style={{
                        padding: "2px 6px",
                        color: hasWarnings ? "#fbbf24" : undefined,
                      }}
                    >
                      {e.warnings_count}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function DiagClassificationExplainability({
  classificationSamples,
  featureMap,
}: {
  classificationSamples: Partial<Record<SemanticKmzClassification, string[]>>;
  featureMap: Map<string, SemanticKmzFeature>;
}) {
  const [open, setOpen] = useState(false);

  const samples = useMemo(() => {
    const out: Array<{ feature: SemanticKmzFeature; debug: SemanticKmzClassificationDebug }> = [];
    for (const ids of Object.values(classificationSamples)) {
      for (const id of ids ?? []) {
        const f = featureMap.get(id);
        if (f?.classification_debug) {
          out.push({ feature: f, debug: f.classification_debug });
          if (out.length >= 15) return out;
        }
      }
    }
    return out;
  }, [classificationSamples, featureMap]);

  if (samples.length === 0) return null;

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          border: "none",
          background: "transparent",
          cursor: "pointer",
          padding: 0,
          color: "var(--tl-text)",
          fontFamily: "inherit",
          fontSize: 10,
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: 0.5,
          marginBottom: open ? 6 : 0,
        }}
      >
        <span style={{ color: "var(--tl-text-muted)" }}>
          Classification explainability · {samples.length} sample{samples.length !== 1 ? "s" : ""}
        </span>
        <span style={{ color: "var(--tl-text-faint)" }}>{open ? "▴" : "▾"}</span>
      </button>

      {open ? (
        <div style={{ display: "grid", gap: 6 }}>
          {samples.map(({ feature, debug }, i) => (
            <div
              key={feature.feature_id}
              style={{
                background: "rgba(15, 23, 42, 0.55)",
                border: "1px solid rgba(148, 163, 184, 0.18)",
                borderRadius: 5,
                padding: "6px 8px",
                display: "grid",
                gap: 3,
              }}
            >
              <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                <span
                  style={{
                    fontSize: 10,
                    fontWeight: 700,
                    color: "#fde68a",
                    background: "rgba(250, 204, 21, 0.10)",
                    border: "1px solid rgba(250, 204, 21, 0.35)",
                    borderRadius: 999,
                    padding: "1px 7px",
                  }}
                >
                  {feature.classification}
                </span>
                <span style={{ color: "var(--tl-text)", fontWeight: 600, fontSize: 11 }}>
                  {feature.placemark_name || `(unnamed #${i + 1})`}
                </span>
              </div>
              <div style={{ display: "grid", gap: 1, paddingTop: 2 }}>
                <DebugRow label="matched_by" value={debug.matched_by.join(", ") || "—"} />
                <DebugRow label="matched_tokens" value={debug.matched_tokens.join(", ") || "—"} />
                <DebugRow label="heuristic_sources" value={debug.heuristic_sources.join(", ") || "—"} />
                <DebugRow label="coordinate_source" value={debug.coordinate_source ?? "null"} />
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function DebugRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", gap: 6 }}>
      <span style={{ color: "var(--tl-text-faint)", minWidth: 130, flexShrink: 0 }}>{label}</span>
      <span style={{ color: "var(--tl-text-muted)", wordBreak: "break-all" }}>{value}</span>
    </div>
  );
}

function DiagStyleResolutionHealth({
  resolution,
  missingStyleUrls,
}: {
  resolution?: {
    ids_declared: number;
    ids_referenced: number;
    ids_referenced_unresolved: number;
    stylemap_count: number;
    stylemap_unresolved_count: number;
    stylemap_cycle_count: number;
  };
  missingStyleUrls: string[];
}) {
  if (!resolution) return null;
  const {
    ids_declared,
    ids_referenced,
    ids_referenced_unresolved,
    stylemap_count,
    stylemap_unresolved_count,
    stylemap_cycle_count,
  } = resolution;
  const hasAnything = ids_declared > 0 || ids_referenced > 0 || stylemap_count > 0;
  if (!hasAnything) return null;

  const hasIssues = ids_referenced_unresolved > 0 || stylemap_unresolved_count > 0;
  const [open, setOpen] = useState(false);

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          border: "none",
          background: "transparent",
          cursor: "pointer",
          padding: 0,
          color: "var(--tl-text)",
          fontFamily: "inherit",
          fontSize: 10,
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: 0.5,
          marginBottom: open ? 6 : 0,
        }}
      >
        <span style={{ color: hasIssues ? "#fca5a5" : "var(--tl-text-muted)" }}>
          Style resolution health
          {hasIssues ? ` · ${ids_referenced_unresolved} unresolved` : " · ok"}
        </span>
        <span style={{ color: "var(--tl-text-faint)" }}>{open ? "▴" : "▾"}</span>
      </button>

      {open ? (
        <div style={{ display: "grid", gap: 3 }}>
          {(
            [
              ["Declared Style IDs", ids_declared],
              ["Referenced styleUrls", ids_referenced],
              ["Unresolved references", ids_referenced_unresolved, true],
              ["StyleMap count", stylemap_count],
              ["StyleMap unresolved", stylemap_unresolved_count, true],
              ["StyleMap cycles", stylemap_cycle_count, stylemap_cycle_count > 0],
            ] as Array<[string, number, boolean?]>
          ).map(([label, value, isIssue]) => (
            <div
              key={label}
              style={{
                display: "flex",
                justifyContent: "space-between",
                gap: 8,
                padding: "2px 0",
                borderBottom: "1px solid rgba(148, 163, 184, 0.10)",
                color: isIssue && value > 0 ? "#fca5a5" : "var(--tl-text-muted)",
              }}
            >
              <span>{label}</span>
              <span style={{ fontWeight: 700 }}>{value.toLocaleString()}</span>
            </div>
          ))}

          {missingStyleUrls.length > 0 ? (
            <div style={{ marginTop: 6 }}>
              <div
                style={{
                  fontSize: 10,
                  fontWeight: 700,
                  color: "#fca5a5",
                  textTransform: "uppercase",
                  letterSpacing: 0.5,
                  marginBottom: 4,
                }}
              >
                Missing styleUrls (cap 25)
              </div>
              <div style={{ display: "grid", gap: 2 }}>
                {missingStyleUrls.map((url) => (
                  <div
                    key={url}
                    style={{
                      padding: "2px 6px",
                      background: "rgba(127, 29, 29, 0.14)",
                      border: "1px solid rgba(248, 113, 113, 0.25)",
                      borderRadius: 3,
                      color: "#fca5a5",
                      wordBreak: "break-all",
                    }}
                  >
                    {url}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function DiagSkippedPlacemarks({
  count,
  samples,
  warnings,
}: {
  count: number;
  samples: Array<{ placemark_index_in_doc: number; error_kind: string; message: string }>;
  warnings: string[];
}) {
  if (count === 0 && warnings.length === 0) return null;
  return (
    <div>
      <div
        style={{
          fontSize: 10,
          fontWeight: 700,
          color: "#fca5a5",
          textTransform: "uppercase",
          letterSpacing: 0.5,
          marginBottom: 4,
        }}
      >
        Skipped placemarks · {count.toLocaleString()}
        {warnings.length > 0 ? ` · ${warnings.length} warning${warnings.length !== 1 ? "s" : ""}` : ""}
      </div>
      {count === 0 ? null : (
        <div
          style={{
            background: "rgba(127, 29, 29, 0.14)",
            border: "1px solid rgba(248, 113, 113, 0.35)",
            borderRadius: 6,
            padding: "6px 8px",
            marginBottom: samples.length > 0 ? 6 : 0,
          }}
        >
          {count} placemark{count !== 1 ? "s" : ""} were skipped due to parse
          errors during semantic ingestion. Matching behavior is unchanged — only
          diagnostics data is affected.
        </div>
      )}
      {samples.length > 0 ? (
        <div style={{ display: "grid", gap: 4 }}>
          {samples.map((s, i) => (
            <div
              key={i}
              style={{
                background: "rgba(15, 23, 42, 0.55)",
                border: "1px solid rgba(248, 113, 113, 0.25)",
                borderRadius: 4,
                padding: "4px 7px",
                display: "grid",
                gap: 1,
              }}
            >
              <span style={{ color: "#fca5a5", fontWeight: 700 }}>
                #{s.placemark_index_in_doc} · {s.error_kind}
              </span>
              <span style={{ color: "var(--tl-text-muted)", wordBreak: "break-all" }}>
                {s.message || "(no message)"}
              </span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function DiagCountSection({
  title,
  entries,
  colorOf,
}: {
  title: string;
  entries: Array<[string, number]>;
  colorOf: (key: string) => string;
}) {
  if (entries.length === 0) return null;
  const sorted = entries.slice().sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const total = sorted.reduce((acc, [, n]) => acc + n, 0);
  return (
    <div>
      <div style={{ fontSize: 10, fontWeight: 700, color: "var(--tl-text-muted)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>
        {title} · {total.toLocaleString()}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
        {sorted.map(([key, count]) => (
          <span
            key={key}
            style={{
              border: "1px solid var(--tl-border)",
              borderRadius: 999,
              padding: "1px 8px",
              fontSize: 10,
              fontWeight: 600,
              background: colorOf(key),
              color: "#0f172a",
            }}
          >
            {key} <strong style={{ fontWeight: 800 }}>{count}</strong>
          </span>
        ))}
      </div>
    </div>
  );
}

function DiagTopList({
  title,
  items,
}: {
  title: string;
  items: Array<{ key: string; count: number }>;
}) {
  if (items.length === 0) return null;
  return (
    <div>
      <div style={{ fontSize: 10, fontWeight: 700, color: "var(--tl-text-muted)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>
        {title}
      </div>
      <div style={{ display: "grid", gap: 2 }}>
        {items.map((row) => (
          <div
            key={row.key}
            style={{
              display: "flex",
              justifyContent: "space-between",
              gap: 8,
              fontSize: 11,
              color: "var(--tl-text)",
              padding: "1px 0",
            }}
          >
            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={row.key}>
              {row.key || "(empty)"}
            </span>
            <span style={{ color: "var(--tl-text-muted)", fontVariantNumeric: "tabular-nums" }}>
              {row.count}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function DiagKeyList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <div style={{ fontSize: 10, fontWeight: 700, color: "var(--tl-text-muted)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>
        {title} · {items.length}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
        {items.map((key) => (
          <span
            key={key}
            style={{
              border: "1px solid var(--tl-border)",
              borderRadius: 4,
              padding: "1px 6px",
              fontSize: 10,
              color: "var(--tl-text)",
              background: "var(--tl-bg-grid)",
            }}
          >
            {key}
          </span>
        ))}
      </div>
    </div>
  );
}

function DiagSampleSection({
  title,
  colorBar,
  samples,
}: {
  title: string;
  colorBar: string;
  samples: SemanticKmzFeature[];
}) {
  return (
    <div>
      <div
        style={{
          fontSize: 10,
          fontWeight: 700,
          color: "var(--tl-text-muted)",
          textTransform: "uppercase",
          letterSpacing: 0.5,
          marginBottom: 4,
          display: "flex",
          alignItems: "center",
          gap: 6,
        }}
      >
        <span
          aria-hidden="true"
          style={{
            display: "inline-block",
            width: 8,
            height: 8,
            borderRadius: 2,
            background: colorBar,
          }}
        />
        {title} · {samples.length}
      </div>
      <div style={{ display: "grid", gap: 4 }}>
        {samples.map((s) => (
          <div
            key={s.feature_id}
            style={{
              border: "1px solid var(--tl-border)",
              borderRadius: 4,
              padding: "5px 7px",
              background: "var(--tl-bg-grid)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginBottom: 2 }}>
              <span style={{ fontWeight: 700, color: "var(--tl-text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={s.placemark_name}>
                {s.placemark_name || "(unnamed)"}
              </span>
              <span style={{ color: "var(--tl-text-faint)" }}>
                {s.geometry_type}
              </span>
            </div>
            <div style={{ color: "var(--tl-text-muted)", fontSize: 10, lineHeight: 1.4 }}>
              <div>
                folder:{" "}
                <span style={{ color: "var(--tl-text)" }}>
                  {s.folder_path_str || "(root)"}
                </span>
              </div>
              <div>
                reason:{" "}
                <span style={{ color: "var(--tl-text)" }}>
                  {s.classification_reason}
                </span>
              </div>
              <div>
                conf: <span style={{ color: confidenceColor(s.confidence) }}>{s.confidence}</span>
                {" · "}
                coords: <span style={{ color: "var(--tl-text)" }}>{fmtCoords(s.coords_hint)}</span>
              </div>
              {(typeof s.chainage_ft === "number" ||
                typeof s.sequence_number === "number" ||
                s.lifecycle ||
                s.style_resolved?.line_color) ? (
                <div>
                  {typeof s.chainage_ft === "number" ? (
                    <>
                      chainage:{" "}
                      <span style={{ color: "var(--tl-text)" }}>
                        {s.chainage_ft.toFixed(1)} ft
                      </span>
                      {" · "}
                    </>
                  ) : null}
                  {typeof s.sequence_number === "number" ? (
                    <>
                      seq:{" "}
                      <span style={{ color: "var(--tl-text)" }}>
                        {s.sequence_kind || "?"} #{s.sequence_number}
                      </span>
                      {" · "}
                    </>
                  ) : null}
                  {s.lifecycle ? (
                    <>
                      lifecycle:{" "}
                      <span style={{ color: lifecycleColor(s.lifecycle.label) }}>
                        {s.lifecycle.label}
                      </span>
                      {" · "}
                    </>
                  ) : null}
                  {s.style_resolved?.line_color ? (
                    <>
                      style:{" "}
                      <span
                        aria-hidden="true"
                        style={{
                          display: "inline-block",
                          width: 8,
                          height: 8,
                          borderRadius: 2,
                          background: s.style_resolved.line_color,
                          border: "1px solid rgba(148, 163, 184, 0.4)",
                          verticalAlign: "middle",
                          marginRight: 4,
                        }}
                      />
                      <span style={{ color: "var(--tl-text)" }}>
                        {s.style_resolved.line_color}
                      </span>
                    </>
                  ) : null}
                </div>
              ) : null}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function DiagRedlineUsefulSignals({ model }: { model: RedlineUsefulSignalsModel }) {
  const folderTitle =
    model.folderStyleSource === "route_segment"
      ? "Top folders among route_segment placemarks"
      : "Top folders (index — no route_segment to weight)";
  const styleTitle =
    model.folderStyleSource === "route_segment"
      ? "Top styleUrls among route_segment placemarks"
      : "Top styleUrls (index — no route_segment to weight)";

  return (
    <div
      style={{
        border: "1px solid rgba(56, 189, 248, 0.35)",
        borderRadius: 8,
        padding: "8px 10px",
        background: "rgba(14, 116, 144, 0.12)",
      }}
    >
      <div
        style={{
          fontSize: 10,
          fontWeight: 800,
          color: "#7dd3fc",
          textTransform: "uppercase",
          letterSpacing: 0.6,
          marginBottom: 6,
        }}
      >
        Redline-useful KMZ signals
      </div>
      <div
        style={{
          fontSize: 11,
          lineHeight: 1.45,
          color: "var(--tl-text)",
          marginBottom: 8,
        }}
      >
        {model.verdict}
      </div>
      <div style={{ display: "grid", gap: 4, fontSize: 11, marginBottom: 8 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
          <span style={{ color: "var(--tl-text-muted)" }}>anchor_catalog</span>
          <span style={{ fontWeight: 700 }}>{model.anchorCount.toLocaleString()}</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
          <span style={{ color: "var(--tl-text-muted)" }}>structure_marker</span>
          <span style={{ fontWeight: 700 }}>{model.structureMarker.toLocaleString()}</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
          <span style={{ color: "var(--tl-text-muted)" }}>route_segment</span>
          <span style={{ fontWeight: 700 }}>{model.routeSegment.toLocaleString()}</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
          <span style={{ color: "var(--tl-text-muted)" }}>handholes (classified)</span>
          <span style={{ fontWeight: 700 }}>{model.handhole.toLocaleString()}</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
          <span style={{ color: "var(--tl-text-muted)" }}>node-like text hits</span>
          <span style={{ fontWeight: 700 }}>{model.nodeLikeHints.toLocaleString()}</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
          <span style={{ color: "var(--tl-text-muted)" }}>splice-related placemarks</span>
          <span style={{ fontWeight: 700 }}>{model.spliceRelated.toLocaleString()}</span>
        </div>
      </div>
      <div style={{ fontSize: 10, fontWeight: 700, color: "var(--tl-text-muted)", marginBottom: 4 }}>
        {folderTitle}
      </div>
      <ul style={{ margin: "0 0 8px 16px", padding: 0, fontSize: 10, lineHeight: 1.5 }}>
        {model.topRouteFolders.length === 0 ? (
          <li style={{ color: "var(--tl-text-faint)" }}>—</li>
        ) : (
          model.topRouteFolders.map((row) => (
            <li key={row.label}>
              <span style={{ color: "var(--tl-text-muted)" }}>{row.count}×</span>{" "}
              <span style={{ wordBreak: "break-word" }}>{row.label}</span>
            </li>
          ))
        )}
      </ul>
      <div style={{ fontSize: 10, fontWeight: 700, color: "var(--tl-text-muted)", marginBottom: 4 }}>
        {styleTitle}
      </div>
      <ul style={{ margin: "0 0 8px 16px", padding: 0, fontSize: 10, lineHeight: 1.5 }}>
        {model.topRouteStyles.length === 0 ? (
          <li style={{ color: "var(--tl-text-faint)" }}>—</li>
        ) : (
          model.topRouteStyles.map((row) => (
            <li key={row.label}>
              <span style={{ color: "var(--tl-text-muted)" }}>{row.count}×</span>{" "}
              <span style={{ wordBreak: "break-all" }}>{row.label}</span>
            </li>
          ))
        )}
      </ul>
      {model.warnings.length > 0 ? (
        <div
          style={{
            fontSize: 10,
            lineHeight: 1.45,
            color: "#fcd34d",
            background: "rgba(120, 53, 15, 0.22)",
            border: "1px solid rgba(251, 191, 36, 0.45)",
            borderRadius: 6,
            padding: "6px 8px",
          }}
        >
          <div style={{ fontWeight: 800, marginBottom: 4 }}>Warnings</div>
          <ul style={{ margin: 0, paddingLeft: 16 }}>
            {model.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <div
        style={{
          marginTop: 6,
          fontSize: 9,
          color: "var(--tl-text-faint)",
        }}
      >
        Heuristic text scan for splice/node tokens; classifications come from the parser index only.
      </div>
    </div>
  );
}

function DiagExtractionSummary({
  featureCount,
  withChainage,
  withSequence,
  withFullGeometry,
  withResolvedStyle,
  stylesResolvedCount,
}: {
  featureCount: number;
  withChainage?: number;
  withSequence?: number;
  withFullGeometry?: number;
  withResolvedStyle?: number;
  stylesResolvedCount?: number;
}) {
  const total = Math.max(featureCount, 1);
  const stat = (n?: number) =>
    typeof n === "number"
      ? `${n.toLocaleString()} (${Math.round((n / total) * 100)}%)`
      : "—";
  return (
    <div>
      <div
        style={{
          fontSize: 10,
          fontWeight: 700,
          color: "var(--tl-text-muted)",
          textTransform: "uppercase",
          letterSpacing: 0.5,
          marginBottom: 4,
        }}
      >
        Extraction coverage · of {featureCount.toLocaleString()} features
      </div>
      <div style={{ display: "grid", gap: 2, fontSize: 11 }}>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span>chainage_ft extracted</span>
          <span style={{ color: "var(--tl-text-muted)" }}>{stat(withChainage)}</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span>sequence_number extracted</span>
          <span style={{ color: "var(--tl-text-muted)" }}>{stat(withSequence)}</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span>full_geometry populated</span>
          <span style={{ color: "var(--tl-text-muted)" }}>{stat(withFullGeometry)}</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span>style_resolved populated</span>
          <span style={{ color: "var(--tl-text-muted)" }}>{stat(withResolvedStyle)}</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span>{"<Style>/<StyleMap> blocks parsed"}</span>
          <span style={{ color: "var(--tl-text-muted)" }}>
            {typeof stylesResolvedCount === "number"
              ? stylesResolvedCount.toLocaleString()
              : "—"}
          </span>
        </div>
      </div>
    </div>
  );
}

function DiagColorTopList({
  title,
  items,
}: {
  title: string;
  items: Array<{ color: string; count: number }>;
}) {
  if (items.length === 0) return null;
  return (
    <div>
      <div
        style={{
          fontSize: 10,
          fontWeight: 700,
          color: "var(--tl-text-muted)",
          textTransform: "uppercase",
          letterSpacing: 0.5,
          marginBottom: 4,
        }}
      >
        {title} · {items.length}
      </div>
      <div style={{ display: "grid", gap: 2 }}>
        {items.map((row) => (
          <div
            key={row.color}
            style={{
              display: "flex",
              justifyContent: "space-between",
              gap: 8,
              fontSize: 11,
              padding: "1px 0",
            }}
          >
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <span
                aria-hidden="true"
                style={{
                  display: "inline-block",
                  width: 12,
                  height: 12,
                  borderRadius: 2,
                  background: row.color,
                  border: "1px solid rgba(148, 163, 184, 0.4)",
                }}
              />
              <span style={{ color: "var(--tl-text)" }}>{row.color}</span>
            </span>
            <span style={{ color: "var(--tl-text-muted)", fontVariantNumeric: "tabular-nums" }}>
              {row.count}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

type AnchorCatalogEntry = NonNullable<
  import("@/lib/types/backend").SemanticKmzIndex["anchor_catalog"]
>[number];

function DiagAnchorCatalog({
  entries,
  truncated,
  cap,
}: {
  entries: AnchorCatalogEntry[];
  truncated: boolean;
  cap?: number;
}) {
  if (entries.length === 0) return null;
  const preview = entries.slice(0, 10);
  return (
    <div>
      <div
        style={{
          fontSize: 10,
          fontWeight: 700,
          color: "var(--tl-text-muted)",
          textTransform: "uppercase",
          letterSpacing: 0.5,
          marginBottom: 4,
        }}
      >
        Anchor catalog · {entries.length.toLocaleString()}
        {truncated && cap ? ` (capped at ${cap.toLocaleString()})` : ""}
      </div>
      <div style={{ display: "grid", gap: 4 }}>
        {preview.map((entry) => (
          <div
            key={entry.feature_id}
            style={{
              border: "1px solid var(--tl-border)",
              borderRadius: 4,
              padding: "5px 7px",
              background: "var(--tl-bg-grid)",
              fontSize: 11,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
              <span style={{ fontWeight: 700, color: "var(--tl-text)" }}>
                {entry.classification}
                {typeof entry.sequence_number === "number"
                  ? ` #${entry.sequence_number}`
                  : ""}
                {typeof entry.chainage_ft === "number"
                  ? ` · ${entry.chainage_ft.toFixed(1)} ft`
                  : ""}
              </span>
              <span style={{ color: confidenceColor(entry.confidence) }}>
                {entry.confidence}
              </span>
            </div>
            <div style={{ color: "var(--tl-text-muted)", fontSize: 10 }}>
              folder:{" "}
              <span style={{ color: "var(--tl-text)" }}>
                {entry.folder_path_str || "(root)"}
              </span>
              {entry.lifecycle ? (
                <>
                  {" · lifecycle: "}
                  <span style={{ color: lifecycleColor(entry.lifecycle) }}>
                    {entry.lifecycle}
                  </span>
                </>
              ) : null}
              {" · coord: "}
              <span style={{ color: "var(--tl-text)" }}>
                {fmtCoords(entry.coord)}
              </span>
            </div>
          </div>
        ))}
        {entries.length > preview.length ? (
          <div style={{ fontSize: 10, color: "var(--tl-text-faint)", paddingTop: 2 }}>
            …showing first {preview.length} of {entries.length.toLocaleString()}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function DiagShadowMatching({ shadow }: { shadow: SemanticMatchShadow }) {
  const summary = shadow.summary;
  const total = summary.groups_total;
  const agreement = summary.groups_in_agreement;
  const disagreement = summary.groups_in_disagreement;
  const noSignal = summary.groups_with_no_anchors;
  const disagreementGroups = (shadow.groups || []).filter(
    (g) => g.agreement === false,
  );
  const agreementSamples = (shadow.groups || [])
    .filter((g) => g.agreement === true)
    .slice(0, 3);

  return (
    <div>
      <div
        style={{
          fontSize: 10,
          fontWeight: 700,
          color: "var(--tl-text-muted)",
          textTransform: "uppercase",
          letterSpacing: 0.5,
          marginBottom: 4,
          display: "flex",
          alignItems: "center",
          gap: 6,
        }}
      >
        <span
          aria-hidden="true"
          style={{
            display: "inline-block",
            width: 8,
            height: 8,
            borderRadius: 2,
            background: "#fde68a",
          }}
        />
        Shadow-mode matching · v{shadow.version} · {total.toLocaleString()} group
        {total === 1 ? "" : "s"}
      </div>
      <div
        style={{
          fontSize: 10,
          color: "var(--tl-text-faint)",
          marginBottom: 6,
        }}
      >
        Read-only diagnostic. Existing matching is unchanged. Numbers compare
        the operational selection against the anchor-catalog signal at proximity
        ≤ {summary.weights.proximity_far_ft.toFixed(0)} ft.
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 6 }}>
        <ShadowChip label="agree" count={agreement} color="#86efac" />
        <ShadowChip label="disagree" count={disagreement} color="#fca5a5" />
        <ShadowChip label="no signal" count={noSignal} color="#cbd5e1" />
        <ShadowChip
          label="anchors"
          count={summary.anchors_considered}
          color="#bae6fd"
        />
      </div>

      {disagreementGroups.length > 0 ? (
        <div style={{ display: "grid", gap: 4, marginBottom: 6 }}>
          <div
            style={{
              fontSize: 10,
              fontWeight: 700,
              color: "#fca5a5",
              textTransform: "uppercase",
              letterSpacing: 0.5,
            }}
          >
            Disagreements ({disagreementGroups.length})
          </div>
          {disagreementGroups.slice(0, 10).map((g) => (
            <ShadowGroupCard key={g.group_id} group={g} accent="#fca5a5" />
          ))}
          {disagreementGroups.length > 10 ? (
            <div style={{ fontSize: 10, color: "var(--tl-text-faint)" }}>
              …showing first 10 of {disagreementGroups.length}
            </div>
          ) : null}
        </div>
      ) : null}

      {agreementSamples.length > 0 ? (
        <div style={{ display: "grid", gap: 4 }}>
          <div
            style={{
              fontSize: 10,
              fontWeight: 700,
              color: "#86efac",
              textTransform: "uppercase",
              letterSpacing: 0.5,
            }}
          >
            Agreement samples (first {agreementSamples.length})
          </div>
          {agreementSamples.map((g) => (
            <ShadowGroupCard key={g.group_id} group={g} accent="#86efac" />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ShadowChip({
  label,
  count,
  color,
}: {
  label: string;
  count: number;
  color: string;
}) {
  return (
    <span
      style={{
        border: "1px solid var(--tl-border)",
        borderRadius: 999,
        padding: "1px 8px",
        fontSize: 10,
        fontWeight: 600,
        background: color,
        color: "#0f172a",
      }}
    >
      {label} <strong style={{ fontWeight: 800 }}>{count}</strong>
    </span>
  );
}

function ShadowGroupCard({
  group,
  accent,
}: {
  group: SemanticMatchShadowGroup;
  accent: string;
}) {
  return (
    <div
      style={{
        border: "1px solid var(--tl-border)",
        borderLeft: `3px solid ${accent}`,
        borderRadius: 4,
        padding: "5px 7px",
        background: "var(--tl-bg-grid)",
        fontSize: 11,
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: 8,
          marginBottom: 2,
        }}
      >
        <span style={{ fontWeight: 700, color: "var(--tl-text)" }}>
          {group.group_id}
        </span>
        <span style={{ color: "var(--tl-text-faint)", fontSize: 10 }}>
          existing → {group.existing_selected_route_name || group.existing_selected_route_id || "—"}
          {group.semantic_best_route_id
            ? ` · semantic → ${group.semantic_best_route_name || group.semantic_best_route_id}`
            : ""}
        </span>
      </div>
      <div style={{ color: "var(--tl-text-muted)", fontSize: 10, lineHeight: 1.4 }}>
        {group.explanation}
      </div>
      <div
        style={{
          color: "var(--tl-text-muted)",
          fontSize: 10,
          marginTop: 2,
          display: "flex",
          gap: 10,
          flexWrap: "wrap",
        }}
      >
        <span>
          near selected:{" "}
          <span style={{ color: "var(--tl-text)" }}>
            {group.anchors_near_selected_route}
          </span>
        </span>
        <span>
          near semantic best:{" "}
          <span style={{ color: "var(--tl-text)" }}>
            {group.anchors_near_semantic_best_route}
          </span>
        </span>
        <span>
          existing score:{" "}
          <span style={{ color: "var(--tl-text)" }}>
            {group.existing_score.toFixed(2)}
          </span>
        </span>
        <span>
          semantic score:{" "}
          <span style={{ color: "var(--tl-text)" }}>
            {group.semantic_best_score.toFixed(2)}
          </span>
        </span>
      </div>
      {group.contributing_anchor_ids.length > 0 ? (
        <div
          style={{
            color: "var(--tl-text-faint)",
            fontSize: 10,
            marginTop: 2,
          }}
        >
          contributors:{" "}
          {group.contributing_anchor_ids.slice(0, 5).join(", ")}
          {group.contributing_anchor_ids.length > 5
            ? ` (+${group.contributing_anchor_ids.length - 5} more)`
            : ""}
        </div>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Phase 1H-C — Semantic shadow review panel
// ---------------------------------------------------------------------------

function fmtRate(r: number | null): string {
  if (r === null) return "—";
  return `${(r * 100).toFixed(1)}%`;
}

function fmtAvg(n: number | null): string {
  if (n === null) return "—";
  return n.toFixed(2);
}

function ShadowStatRow({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: string;
}) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        gap: 8,
        padding: "2px 0",
        borderBottom: "1px solid rgba(148, 163, 184, 0.10)",
        fontSize: 11,
      }}
    >
      <span style={{ color: "var(--tl-text-muted)" }}>{label}</span>
      <span style={{ fontWeight: 700, color: accent ?? "var(--tl-text)" }}>{value}</span>
    </div>
  );
}

function ShadowAgreementChip({ agreement, hadShadow }: { agreement: boolean | null; hadShadow: boolean }) {
  if (!hadShadow) {
    return (
      <span
        style={{
          fontSize: 9,
          fontWeight: 700,
          padding: "1px 6px",
          borderRadius: 999,
          background: "rgba(100, 116, 139, 0.18)",
          color: "#94a3b8",
          border: "1px solid rgba(100, 116, 139, 0.3)",
          whiteSpace: "nowrap",
        }}
      >
        no shadow
      </span>
    );
  }
  if (agreement === true) {
    return (
      <span
        style={{
          fontSize: 9,
          fontWeight: 700,
          padding: "1px 6px",
          borderRadius: 999,
          background: "rgba(134, 239, 172, 0.18)",
          color: "#86efac",
          border: "1px solid rgba(134, 239, 172, 0.4)",
          whiteSpace: "nowrap",
        }}
      >
        agree
      </span>
    );
  }
  if (agreement === false) {
    return (
      <span
        style={{
          fontSize: 9,
          fontWeight: 700,
          padding: "1px 6px",
          borderRadius: 999,
          background: "rgba(251, 191, 36, 0.14)",
          color: "#fbbf24",
          border: "1px solid rgba(251, 191, 36, 0.4)",
          whiteSpace: "nowrap",
        }}
        title="Semantic shadow signal preferred a different route. Review only — operational winner is unchanged."
      >
        review
      </span>
    );
  }
  return (
    <span
      style={{
        fontSize: 9,
        fontWeight: 700,
        padding: "1px 6px",
        borderRadius: 999,
        background: "rgba(100, 116, 139, 0.12)",
        color: "#64748b",
        border: "1px solid rgba(100, 116, 139, 0.25)",
        whiteSpace: "nowrap",
      }}
    >
      no signal
    </span>
  );
}

function DiagSemanticShadowReview({
  summary,
  compareEntries,
}: {
  summary: MatchShadowSummaryResponse | null;
  compareEntries: MatchShadowCompareEntry[];
}) {
  const [open, setOpen] = useState(false);

  const rowsRead = summary?.window?.rows_read ?? 0;
  if (rowsRead === 0) return null;

  const win = summary!.window;
  const avail = summary!.shadow_availability;
  const agr = summary!.agreement;
  const ap = summary!.anchor_participation;
  const topPasses = summary!.top_disagreement_passes ?? [];
  const stabilityNote = summary!.stability_note ?? "";

  const passCount = win.match_pass_count;
  const shaCount = win.unique_input_sha256_count;
  const belowThreshold = avail.shadow_availability_rate === null;

  return (
    <div
      style={{
        borderTop: "1px solid rgba(148, 163, 184, 0.18)",
        paddingTop: 8,
        marginTop: 8,
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={{
          background: "none",
          border: "none",
          cursor: "pointer",
          color: "var(--tl-text-faint)",
          fontSize: 11,
          fontWeight: 600,
          padding: "2px 0",
          textAlign: "left",
          width: "100%",
          display: "flex",
          alignItems: "center",
          gap: 6,
          flexWrap: "wrap",
        }}
      >
        <span>{open ? "▾" : "▸"} Semantic shadow review</span>
        <span style={{ color: "var(--tl-text-faint)", fontWeight: 400 }}>
          {rowsRead.toLocaleString()} groups · {passCount} pass{passCount !== 1 ? "es" : ""} · {shaCount} KMZ SHA
          {shaCount !== 1 ? "s" : ""}
        </span>
        {(agr.disagree_count ?? 0) > 0 && (
          <span
            style={{
              fontSize: 9,
              fontWeight: 700,
              padding: "1px 6px",
              borderRadius: 999,
              background: "rgba(251, 191, 36, 0.14)",
              color: "#fbbf24",
              border: "1px solid rgba(251, 191, 36, 0.4)",
            }}
          >
            {agr.disagree_count} for review
          </span>
        )}
      </button>

      {open && (
        <div style={{ marginTop: 8, display: "grid", gap: 10 }}>

          {/* Summary metrics */}
          <div
            style={{
              border: "1px solid rgba(56, 189, 248, 0.2)",
              borderRadius: 6,
              padding: "8px 10px",
              background: "rgba(14, 116, 144, 0.08)",
              display: "grid",
              gap: 0,
            }}
          >
            <div
              style={{
                fontSize: 9,
                fontWeight: 800,
                color: "#7dd3fc",
                textTransform: "uppercase",
                letterSpacing: 0.6,
                marginBottom: 6,
              }}
            >
              Semantic shadow signal · provisional
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 16px" }}>
              <div>
                <ShadowStatRow label="Rows read" value={rowsRead.toLocaleString()} />
                <ShadowStatRow label="Match passes" value={passCount.toLocaleString()} />
                <ShadowStatRow label="Unique KMZ SHAs" value={shaCount.toLocaleString()} />
                <ShadowStatRow
                  label="Shadow availability"
                  value={belowThreshold ? `${avail.rows_with_shadow_payload}/${avail.sample_size}` : fmtRate(avail.shadow_availability_rate)}
                />
              </div>
              <div>
                <ShadowStatRow
                  label="Agreement"
                  value={agr.agree_rate !== null ? fmtRate(agr.agree_rate) : `${agr.agree_count} groups`}
                  accent="#86efac"
                />
                <ShadowStatRow
                  label="Disagreement"
                  value={agr.disagree_rate !== null ? fmtRate(agr.disagree_rate) : `${agr.disagree_count} groups`}
                  accent={agr.disagree_count > 0 ? "#fbbf24" : undefined}
                />
                <ShadowStatRow
                  label="Shadow had no opinion"
                  value={agr.inconclusive_rate !== null ? fmtRate(agr.inconclusive_rate) : `${agr.inconclusive_count} groups`}
                />
                <ShadowStatRow
                  label="Avg anchors near op. winner"
                  value={fmtAvg(ap.avg_anchors_near_op)}
                />
              </div>
            </div>

            {belowThreshold && (
              <div
                style={{
                  fontSize: 10,
                  color: "#94a3b8",
                  marginTop: 4,
                  fontStyle: "italic",
                }}
              >
                Rates shown when ≥ {summary!.guards.min_samples_for_rate} shadow-available groups.
              </div>
            )}
          </div>

          {/* Stability note */}
          <div
            style={{
              fontSize: 10,
              color: "#64748b",
              lineHeight: 1.5,
              padding: "6px 8px",
              border: "1px solid rgba(100, 116, 139, 0.25)",
              borderRadius: 5,
              background: "rgba(15, 23, 42, 0.35)",
              fontStyle: "italic",
            }}
          >
            {stabilityNote}
          </div>

          {/* Top disagreement passes (if any) */}
          {topPasses.length > 0 && (
            <div>
              <div
                style={{
                  fontSize: 10,
                  fontWeight: 700,
                  color: "#fbbf24",
                  textTransform: "uppercase",
                  letterSpacing: 0.5,
                  marginBottom: 4,
                }}
              >
                Passes with most review groups
              </div>
              <div style={{ display: "grid", gap: 3 }}>
                {topPasses.slice(0, 5).map((p) => (
                  <div
                    key={p.match_pass_id}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      gap: 8,
                      padding: "3px 6px",
                      background: "rgba(120, 53, 15, 0.12)",
                      border: "1px solid rgba(251, 191, 36, 0.2)",
                      borderRadius: 4,
                      fontSize: 10,
                      color: "var(--tl-text-muted)",
                    }}
                  >
                    <span
                      style={{ fontFamily: "monospace", color: "var(--tl-text-faint)" }}
                      title={p.match_pass_id}
                    >
                      {p.match_pass_id.slice(0, 8)}…
                    </span>
                    <span>
                      <span style={{ color: "#fbbf24", fontWeight: 700 }}>
                        {p.disagree_count}
                      </span>
                      <span style={{ color: "var(--tl-text-faint)" }}>
                        {" "}review of {p.group_count} groups
                      </span>
                    </span>
                    {p.input_sha256 && (
                      <span style={{ fontFamily: "monospace", color: "var(--tl-text-faint)" }}>
                        {p.input_sha256.slice(0, 8)}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Recent compare rows */}
          {compareEntries.length > 0 && (
            <div>
              <div
                style={{
                  fontSize: 10,
                  fontWeight: 700,
                  color: "var(--tl-text-muted)",
                  textTransform: "uppercase",
                  letterSpacing: 0.5,
                  marginBottom: 4,
                }}
              >
                Recent compare rows (last {compareEntries.length})
              </div>
              <div style={{ overflowX: "auto" }}>
                <table
                  style={{
                    width: "100%",
                    borderCollapse: "collapse",
                    fontSize: 10,
                    color: "var(--tl-text-faint)",
                  }}
                >
                  <thead>
                    <tr>
                      {[
                        "group",
                        "operational winner",
                        "semantic shadow winner",
                        "status",
                        "anch op",
                        "anch sem",
                      ].map((h) => (
                        <th
                          key={h}
                          style={{
                            textAlign: "left",
                            padding: "2px 6px",
                            borderBottom: "1px solid rgba(148,163,184,0.2)",
                            fontWeight: 600,
                            whiteSpace: "nowrap",
                          }}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {compareEntries.map((e, i) => (
                      <tr
                        key={i}
                        style={{
                          borderBottom: "1px solid rgba(148,163,184,0.08)",
                          background:
                            e.agreement === false
                              ? "rgba(120, 53, 15, 0.08)"
                              : undefined,
                        }}
                      >
                        <td
                          style={{
                            padding: "3px 6px",
                            fontFamily: "monospace",
                            whiteSpace: "nowrap",
                            maxWidth: 80,
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                          }}
                          title={e.group_id ?? ""}
                        >
                          {e.group_id ?? "—"}
                        </td>
                        <td
                          style={{
                            padding: "3px 6px",
                            maxWidth: 120,
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                            color: "var(--tl-text)",
                          }}
                          title={e.operational_winner_route_name ?? ""}
                        >
                          {e.operational_winner_route_name ?? e.operational_winner_route_id ?? "—"}
                        </td>
                        <td
                          style={{
                            padding: "3px 6px",
                            maxWidth: 120,
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                            color:
                              e.agreement === false
                                ? "#fbbf24"
                                : "var(--tl-text-muted)",
                          }}
                          title={e.shadow_explanation ?? ""}
                        >
                          {e.had_shadow_payload
                            ? e.semantic_winner_route_name ?? e.semantic_winner_route_id ?? "—"
                            : "—"}
                        </td>
                        <td style={{ padding: "3px 6px", whiteSpace: "nowrap" }}>
                          <ShadowAgreementChip
                            agreement={e.agreement}
                            hadShadow={e.had_shadow_payload}
                          />
                        </td>
                        <td style={{ padding: "3px 6px", textAlign: "right" }}>
                          {e.anchors_near_operational_winner}
                        </td>
                        <td style={{ padding: "3px 6px", textAlign: "right" }}>
                          {e.anchors_near_semantic_winner}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div
                style={{
                  fontSize: 9,
                  color: "var(--tl-text-faint)",
                  marginTop: 4,
                  fontStyle: "italic",
                }}
              >
                "review" = semantic shadow signal preferred a different route. Operational winner is
                unchanged. Read-only.
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Phase 1I-B — Semantic disagreement drilldown panel
// ---------------------------------------------------------------------------

const _LABEL_DISPLAY: Record<string, string> = {
  DOMINANT_SHADOW_SUPPORT: "Dominant shadow support",
  MODEST_SHADOW_SUPPORT: "Modest shadow support",
  COMPETING_SUPPORT: "Competing support",
  THIN_EVIDENCE: "Thin evidence",
  NO_CONTRIBUTORS_LISTED: "Missing contributor list",
};

function DisagreementPriorityChip({ priority }: { priority: string }) {
  const styles: Record<string, React.CSSProperties> = {
    elevated: {
      background: "rgba(251, 191, 36, 0.14)",
      color: "#fbbf24",
      border: "1px solid rgba(251, 191, 36, 0.4)",
    },
    standard: {
      background: "rgba(148, 163, 184, 0.12)",
      color: "#94a3b8",
      border: "1px solid rgba(148, 163, 184, 0.3)",
    },
    low: {
      background: "rgba(71, 85, 105, 0.10)",
      color: "#64748b",
      border: "1px solid rgba(71, 85, 105, 0.25)",
    },
  };
  return (
    <span
      style={{
        fontSize: 9,
        fontWeight: 700,
        padding: "1px 6px",
        borderRadius: 999,
        whiteSpace: "nowrap",
        ...(styles[priority] ?? styles.low),
      }}
    >
      {priority}
    </span>
  );
}

function DisagreementKindChip({ label }: { label: string }) {
  return (
    <span
      style={{
        fontSize: 9,
        fontWeight: 600,
        padding: "1px 5px",
        borderRadius: 3,
        background: "rgba(56, 189, 248, 0.10)",
        color: "#7dd3fc",
        border: "1px solid rgba(56, 189, 248, 0.25)",
        whiteSpace: "nowrap",
      }}
    >
      {_LABEL_DISPLAY[label] ?? label}
    </span>
  );
}

function DisagreementEntryCard({
  entry,
  currentLabel,
  onLabel,
}: {
  entry: MatchShadowDisagreementEntry;
  currentLabel: ReviewLabelValue | null;
  onLabel: (label: ReviewLabelValue) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const isElevated = entry.review_priority === "elevated";

  async function handleLabel(label: ReviewLabelValue): Promise<void> {
    if (submitting) return;
    setSubmitting(true);
    try {
      await apiFetch(`${API_BASE}/api/observability/review-labels`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          match_pass_id: entry.match_pass_id,
          group_id: entry.group_id,
          input_sha256: entry.input_sha256,
          label,
          previous_label: currentLabel,
        }),
      });
      onLabel(label);
    } catch {
      // Silently ignore — labels are observability telemetry only.
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      style={{
        border: isElevated
          ? "1px solid rgba(251, 191, 36, 0.3)"
          : "1px solid rgba(148, 163, 184, 0.15)",
        borderLeft: isElevated ? "3px solid #fbbf24" : "3px solid rgba(148, 163, 184, 0.25)",
        borderRadius: 4,
        padding: "5px 7px",
        background: isElevated
          ? "rgba(120, 53, 15, 0.06)"
          : "rgba(15, 23, 42, 0.35)",
        fontSize: 10,
        display: "grid",
        gap: 3,
      }}
    >
      {/* Row 1: priority + group + route names */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
        <DisagreementPriorityChip priority={entry.review_priority} />
        {entry.group_id && (
          <span style={{ color: "var(--tl-text-faint)", fontFamily: "monospace" }}>
            {entry.group_id}
          </span>
        )}
      </div>

      {/* Row 2: op winner → semantic winner */}
      <div style={{ display: "flex", gap: 4, alignItems: "center", flexWrap: "wrap" }}>
        <span style={{ color: "var(--tl-text-muted)" }}>op:</span>
        <span style={{ color: "var(--tl-text)", fontWeight: 600 }}>
          {entry.operational_winner_route_name ?? entry.operational_winner_route_id ?? "—"}
        </span>
        <span style={{ color: "var(--tl-text-faint)" }}>→</span>
        <span style={{ color: "var(--tl-text-muted)" }}>shadow:</span>
        <span
          style={{
            color: isElevated ? "#fbbf24" : "var(--tl-text-muted)",
            fontWeight: isElevated ? 600 : 400,
          }}
        >
          {entry.semantic_winner_route_name ?? entry.semantic_winner_route_id ?? "—"}
        </span>
      </div>

      {/* Row 3: anchor counts + contributor count */}
      <div style={{ display: "flex", gap: 10, color: "var(--tl-text-muted)", flexWrap: "wrap" }}>
        <span>
          anchors near op:{" "}
          <span style={{ color: "var(--tl-text)", fontWeight: 700 }}>
            {entry.anchors_near_operational_winner}
          </span>
        </span>
        <span>
          anchors near shadow:{" "}
          <span style={{ color: "var(--tl-text)", fontWeight: 700 }}>
            {entry.anchors_near_semantic_winner}
          </span>
        </span>
        <span>
          contributors:{" "}
          <span style={{ color: "var(--tl-text)" }}>
            {entry.contributing_anchor_count}
          </span>
        </span>
      </div>

      {/* Row 4: kind chips */}
      {entry.disagreement_kind.length > 0 && (
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
          {entry.disagreement_kind.map((lbl) => (
            <DisagreementKindChip key={lbl} label={lbl} />
          ))}
        </div>
      )}

      {/* Row 5: explanation (expandable) */}
      {entry.shadow_explanation && (
        <div>
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              color: "var(--tl-text-faint)",
              fontSize: 9,
              padding: 0,
              textAlign: "left",
            }}
          >
            {expanded ? "▾ hide explanation" : "▸ explanation"}
          </button>
          {expanded && (
            <div
              style={{
                marginTop: 3,
                color: "var(--tl-text-muted)",
                lineHeight: 1.5,
                wordBreak: "break-word",
                fontStyle: "italic",
              }}
            >
              {entry.shadow_explanation}
            </div>
          )}
        </div>
      )}

      {/* Row 6: priority reasons (collapsed by default) */}
      {entry.review_priority_reasons.length > 0 && (
        <div
          style={{
            color: "var(--tl-text-faint)",
            fontSize: 9,
          }}
        >
          reasons: {entry.review_priority_reasons.join(", ")}
        </div>
      )}

      {/* Row 7: review label buttons (observability telemetry only) */}
      <div style={{ display: "flex", alignItems: "center", gap: 5, marginTop: 2 }}>
        {(["useful_catch", "noise", "unclear"] as ReviewLabelValue[]).map((lbl) => {
          const active = currentLabel === lbl;
          return (
            <button
              key={lbl}
              type="button"
              disabled={submitting}
              onClick={() => void handleLabel(lbl)}
              style={{
                background: active ? "rgba(148, 163, 184, 0.18)" : "none",
                border: active
                  ? "1px solid rgba(148, 163, 184, 0.4)"
                  : "1px solid rgba(148, 163, 184, 0.18)",
                borderRadius: 3,
                cursor: submitting ? "not-allowed" : "pointer",
                color: active ? "var(--tl-text-muted)" : "var(--tl-text-faint)",
                fontSize: 9,
                padding: "1px 6px",
                opacity: submitting ? 0.5 : 1,
                transition: "background 0.1s, border-color 0.1s",
              }}
            >
              {lbl.replace("_", " ")}
            </button>
          );
        })}
        {currentLabel && (
          <span
            style={{
              fontSize: 9,
              color: "var(--tl-text-faint)",
              marginLeft: 2,
              fontStyle: "italic",
            }}
          >
            {currentLabel.replace("_", " ")}
          </span>
        )}
      </div>
    </div>
  );
}

function DiagSemanticDisagreementDrilldown({
  data,
  labelMap,
  onLabelChange,
}: {
  data: MatchShadowDisagreementResponse | null;
  labelMap: Record<string, ReviewLabelValue>;
  onLabelChange: (groupId: string | null, label: ReviewLabelValue) => void;
}) {
  const [open, setOpen] = useState(false);

  if (!data || data.window.rows_read === 0 || data.entries.length === 0) return null;

  const tax = data.taxonomy;
  const elevated = tax.totals_by_priority.elevated;
  const standard = tax.totals_by_priority.standard;
  const low = tax.totals_by_priority.low;

  return (
    <div
      style={{
        borderTop: "1px solid rgba(148, 163, 184, 0.18)",
        paddingTop: 8,
        marginTop: 8,
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={{
          background: "none",
          border: "none",
          cursor: "pointer",
          color: "var(--tl-text-faint)",
          fontSize: 11,
          fontWeight: 600,
          padding: "2px 0",
          textAlign: "left",
          width: "100%",
          display: "flex",
          alignItems: "center",
          gap: 6,
          flexWrap: "wrap",
        }}
      >
        <span>{open ? "▾" : "▸"} Semantic disagreement drilldown</span>
        <span style={{ color: "var(--tl-text-faint)", fontWeight: 400 }}>
          {data.entries.length} shown
        </span>
        {elevated > 0 && (
          <span
            style={{
              fontSize: 9,
              fontWeight: 700,
              padding: "1px 6px",
              borderRadius: 999,
              background: "rgba(251, 191, 36, 0.14)",
              color: "#fbbf24",
              border: "1px solid rgba(251, 191, 36, 0.4)",
            }}
          >
            {elevated} elevated
          </span>
        )}
        {standard > 0 && (
          <span
            style={{
              fontSize: 9,
              fontWeight: 600,
              padding: "1px 6px",
              borderRadius: 999,
              background: "rgba(148, 163, 184, 0.10)",
              color: "#94a3b8",
              border: "1px solid rgba(148, 163, 184, 0.25)",
            }}
          >
            {standard} standard
          </span>
        )}
        {low > 0 && (
          <span
            style={{
              fontSize: 9,
              fontWeight: 400,
              padding: "1px 6px",
              borderRadius: 999,
              color: "#64748b",
              border: "1px solid rgba(71, 85, 105, 0.2)",
            }}
          >
            {low} low
          </span>
        )}
        <span
          style={{
            fontSize: 9,
            color: "var(--tl-text-faint)",
            fontStyle: "italic",
            fontWeight: 400,
          }}
        >
          · Review only
        </span>
      </button>

      {open && (
        <div style={{ marginTop: 8, display: "grid", gap: 10 }}>

          {/* Taxonomy summary chips */}
          <div>
            <div
              style={{
                fontSize: 9,
                fontWeight: 700,
                color: "var(--tl-text-faint)",
                textTransform: "uppercase",
                letterSpacing: 0.5,
                marginBottom: 4,
              }}
            >
              Evidence kind (all disagreements in window)
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
              {data.taxonomy.approved_labels.map((lbl) => {
                const n = tax.totals_by_kind[lbl] ?? 0;
                if (n === 0) return null;
                return (
                  <span
                    key={lbl}
                    style={{
                      fontSize: 9,
                      fontWeight: 600,
                      padding: "2px 7px",
                      borderRadius: 999,
                      background: "rgba(56, 189, 248, 0.08)",
                      color: "#7dd3fc",
                      border: "1px solid rgba(56, 189, 248, 0.2)",
                    }}
                  >
                    {_LABEL_DISPLAY[lbl] ?? lbl}{" "}
                    <strong style={{ fontWeight: 800 }}>{n}</strong>
                  </span>
                );
              })}
            </div>
          </div>

          {/* Stability note */}
          <div
            style={{
              fontSize: 10,
              color: "#64748b",
              lineHeight: 1.5,
              padding: "5px 7px",
              border: "1px solid rgba(100, 116, 139, 0.2)",
              borderRadius: 4,
              background: "rgba(15, 23, 42, 0.30)",
              fontStyle: "italic",
            }}
          >
            {data.stability_note}
          </div>

          {/* Entry cards */}
          <div>
            <div
              style={{
                fontSize: 9,
                fontWeight: 700,
                color: "var(--tl-text-faint)",
                textTransform: "uppercase",
                letterSpacing: 0.5,
                marginBottom: 6,
              }}
            >
              Operator may want to compare — evidence strength only, not correctness
            </div>
            <div style={{ display: "grid", gap: 5 }}>
              {data.entries.map((entry, i) => (
                <DisagreementEntryCard
                  key={`${entry.match_pass_id ?? ""}:${entry.group_id ?? i}`}
                  entry={entry}
                  currentLabel={labelMap[entry.group_id ?? "__null__"] ?? null}
                  onLabel={(label) => onLabelChange(entry.group_id, label)}
                />
              ))}
            </div>
          </div>

        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Phase 1P — Redline topology continuity advisor panel
// ---------------------------------------------------------------------------

function DiagRedlineTopologyContinuity({
  data,
}: {
  data: RedlineTopologyContinuityResponse | null;
}) {
  const [open, setOpen] = useState(false);

  if (!data) return null;

  const { groups, ungrouped_segment_ids } = data;
  const totalGrouped = groups.reduce((n, g) => n + g.source_segment_ids.length, 0);
  const totalUngrouped = ungrouped_segment_ids.length;

  if (groups.length === 0 && totalUngrouped === 0) return null;

  return (
    <div
      style={{
        borderTop: "1px solid rgba(148, 163, 184, 0.18)",
        paddingTop: 8,
        marginTop: 8,
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={{
          background: "none",
          border: "none",
          cursor: "pointer",
          color: "var(--tl-text-faint)",
          fontSize: 11,
          fontWeight: 600,
          padding: "2px 0",
          textAlign: "left",
          width: "100%",
          display: "flex",
          alignItems: "center",
          gap: 6,
          flexWrap: "wrap",
        }}
      >
        <span>{open ? "▾" : "▸"} Redline topology continuity advisor</span>
        <span style={{ color: "var(--tl-text-faint)", fontWeight: 400 }}>
          {groups.length} continuity {groups.length === 1 ? "group" : "groups"} ·{" "}
          {totalGrouped} grouped · {totalUngrouped} ungrouped
        </span>
      </button>

      {open && (
        <div style={{ display: "grid", gap: 8, marginTop: 6 }}>

          {/* Summary row */}
          <div style={{ display: "grid", gap: 2, fontSize: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
              <span style={{ color: "var(--tl-text-muted)" }}>continuity groups</span>
              <span style={{ color: "var(--tl-text)", fontWeight: 600 }}>{groups.length}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
              <span style={{ color: "var(--tl-text-muted)" }}>grouped segments</span>
              <span style={{ color: "var(--tl-text)", fontWeight: 600 }}>{totalGrouped}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
              <span style={{ color: "var(--tl-text-muted)" }}>ungrouped segments</span>
              <span style={{ color: "var(--tl-text)", fontWeight: 600 }}>{totalUngrouped}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
              <span style={{ color: "var(--tl-text-muted)" }}>advisory signal</span>
              <span
                style={{
                  color: "var(--tl-text-faint)",
                  fontWeight: 400,
                  fontFamily: "monospace",
                  fontSize: 9,
                }}
              >
                multigeometry_group
              </span>
            </div>
          </div>

          {/* Per-group cards */}
          {groups.length > 0 && (
            <div>
              <div
                style={{
                  fontSize: 9,
                  fontWeight: 700,
                  color: "var(--tl-text-faint)",
                  textTransform: "uppercase",
                  letterSpacing: 0.5,
                  marginBottom: 4,
                }}
              >
                grouped fragments (review aid — advisory only)
              </div>
              <div style={{ display: "grid", gap: 4 }}>
                {groups.map((grp) => (
                  <div
                    key={grp.engineering_object_id}
                    style={{
                      background: "rgba(148, 163, 184, 0.05)",
                      border: "1px solid rgba(148, 163, 184, 0.14)",
                      borderRadius: 4,
                      padding: "5px 7px",
                      fontSize: 10,
                      display: "grid",
                      gap: 2,
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <span style={{ color: "var(--tl-text-faint)", fontSize: 9 }}>
                        engineering object
                      </span>
                      <span
                        style={{
                          color: "var(--tl-text)",
                          fontFamily: "monospace",
                          fontSize: 9,
                          fontWeight: 600,
                        }}
                      >
                        {grp.engineering_object_id}
                      </span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <span style={{ color: "var(--tl-text-faint)", fontSize: 9 }}>
                        grouped fragments
                      </span>
                      <span style={{ color: "var(--tl-text)", fontWeight: 600 }}>
                        {grp.evidence.fragment_count}
                      </span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <span style={{ color: "var(--tl-text-faint)", fontSize: 9 }}>signal</span>
                      <span
                        style={{
                          color: "var(--tl-text-faint)",
                          fontFamily: "monospace",
                          fontSize: 9,
                        }}
                      >
                        {grp.signal}
                      </span>
                    </div>
                    <div
                      style={{
                        color: "var(--tl-text-faint)",
                        fontSize: 9,
                        fontFamily: "monospace",
                        marginTop: 2,
                        lineHeight: 1.5,
                      }}
                    >
                      {grp.source_segment_ids.join(" · ")}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div
            style={{
              color: "var(--tl-text-faint)",
              fontSize: 9,
              fontStyle: "italic",
              lineHeight: 1.4,
            }}
          >
            {data.stability_note}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Phase 1Q — Node-anchored redline continuity advisor panel
// ---------------------------------------------------------------------------

function DiagRedlineNodeContinuity({
  data,
}: {
  data: RedlineNodeContinuityResponse | null;
}) {
  const [open, setOpen] = useState(false);

  if (!data) return null;

  const { groups, ungrouped_segment_ids, stats } = data;

  if (groups.length === 0 && ungrouped_segment_ids.length === 0) return null;

  return (
    <div
      style={{
        borderTop: "1px solid rgba(148, 163, 184, 0.18)",
        paddingTop: 8,
        marginTop: 8,
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={{
          background: "none",
          border: "none",
          cursor: "pointer",
          color: "var(--tl-text-faint)",
          fontSize: 11,
          fontWeight: 600,
          padding: "2px 0",
          textAlign: "left",
          width: "100%",
          display: "flex",
          alignItems: "center",
          gap: 6,
          flexWrap: "wrap",
        }}
      >
        <span>{open ? "▾" : "▸"} Node-anchored redline continuity advisor</span>
        <span style={{ color: "var(--tl-text-faint)", fontWeight: 400 }}>
          {groups.length} anchor {groups.length === 1 ? "group" : "groups"} ·{" "}
          {stats.redline_segments_anchored} anchored ·{" "}
          {stats.redline_segments_unanchored} unanchored
        </span>
      </button>

      {open && (
        <div style={{ display: "grid", gap: 8, marginTop: 6 }}>

          {/* Stats summary */}
          <div style={{ display: "grid", gap: 2, fontSize: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
              <span style={{ color: "var(--tl-text-muted)" }}>anchor groups</span>
              <span style={{ color: "var(--tl-text)", fontWeight: 600 }}>{groups.length}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
              <span style={{ color: "var(--tl-text-muted)" }}>anchors considered</span>
              <span style={{ color: "var(--tl-text)", fontWeight: 600 }}>
                {stats.anchor_points_considered}
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
              <span style={{ color: "var(--tl-text-muted)" }}>segments anchored</span>
              <span style={{ color: "var(--tl-text)", fontWeight: 600 }}>
                {stats.redline_segments_anchored}
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
              <span style={{ color: "var(--tl-text-muted)" }}>segments unanchored</span>
              <span style={{ color: "var(--tl-text)", fontWeight: 600 }}>
                {stats.redline_segments_unanchored}
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
              <span style={{ color: "var(--tl-text-muted)" }}>tolerance</span>
              <span
                style={{
                  color: "var(--tl-text-faint)",
                  fontFamily: "monospace",
                  fontSize: 9,
                }}
              >
                {data.tolerance_ft.toFixed(1)} ft (fixed)
              </span>
            </div>
          </div>

          {/* Per-group anchor cards */}
          {groups.length > 0 && (
            <div>
              <div
                style={{
                  fontSize: 9,
                  fontWeight: 700,
                  color: "var(--tl-text-faint)",
                  textTransform: "uppercase",
                  letterSpacing: 0.5,
                  marginBottom: 4,
                }}
              >
                anchor continuity groups (review aid — advisory only)
              </div>
              <div style={{ display: "grid", gap: 4 }}>
                {groups.map((grp) => (
                  <div
                    key={grp.anchor_reference_feature_id}
                    style={{
                      background: "rgba(148, 163, 184, 0.05)",
                      border: "1px solid rgba(148, 163, 184, 0.14)",
                      borderRadius: 4,
                      padding: "5px 7px",
                      fontSize: 10,
                      display: "grid",
                      gap: 2,
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <span style={{ color: "var(--tl-text-faint)", fontSize: 9 }}>
                        handhole/node anchor
                      </span>
                      <span
                        style={{
                          color: "var(--tl-text)",
                          fontFamily: "monospace",
                          fontSize: 9,
                          fontWeight: 600,
                        }}
                      >
                        {grp.anchor_reference_feature_id}
                      </span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <span style={{ color: "var(--tl-text-faint)", fontSize: 9 }}>
                        anchor name
                      </span>
                      <span style={{ color: "var(--tl-text)", fontSize: 9 }}>
                        {grp.anchor_name}
                      </span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <span style={{ color: "var(--tl-text-faint)", fontSize: 9 }}>
                        endpoint hits
                      </span>
                      <span style={{ color: "var(--tl-text)", fontWeight: 600 }}>
                        {grp.endpoint_count}
                      </span>
                    </div>
                    <div
                      style={{
                        color: "var(--tl-text-faint)",
                        fontSize: 9,
                        fontFamily: "monospace",
                        marginTop: 2,
                        lineHeight: 1.5,
                      }}
                    >
                      {grp.source_segment_ids.join(" · ")}
                    </div>
                    {grp.evidence.length > 0 && (
                      <div
                        style={{
                          color: "var(--tl-text-faint)",
                          fontSize: 9,
                          marginTop: 2,
                          lineHeight: 1.6,
                        }}
                      >
                        {grp.evidence.map((ev, i) => (
                          <div key={i}>
                            <span style={{ fontFamily: "monospace" }}>{ev.segment_id}</span>
                            {" "}
                            <span style={{ opacity: 0.7 }}>{ev.endpoint}</span>
                            {" "}
                            <span style={{ opacity: 0.7 }}>{ev.distance_ft} ft</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div
            style={{
              color: "var(--tl-text-faint)",
              fontSize: 9,
              fontStyle: "italic",
              lineHeight: 1.4,
            }}
          >
            {data.stability_note}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Phase 1R — Anchor-grouped redline review surface
// ---------------------------------------------------------------------------

function DiagAnchorGroupedReview({
  data,
}: {
  data: RedlineNodeContinuityResponse | null;
}) {
  const [open, setOpen] = useState(false);

  if (!data) return null;

  const multiGroups = data.groups.filter(
    (g) => g.source_segment_ids.length >= 2,
  );

  if (multiGroups.length === 0) return null;

  return (
    <div
      style={{
        borderTop: "1px solid rgba(148, 163, 184, 0.18)",
        paddingTop: 8,
        marginTop: 8,
      }}
    >
      {/* Section header */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={{
          background: "none",
          border: "none",
          cursor: "pointer",
          color: "var(--tl-text-faint)",
          fontSize: 11,
          fontWeight: 600,
          padding: "2px 0",
          textAlign: "left",
          width: "100%",
          display: "flex",
          alignItems: "center",
          gap: 6,
          flexWrap: "wrap",
        }}
      >
        <span>{open ? "▾" : "▸"} Anchor-grouped redline review</span>
        <span style={{ color: "var(--tl-text-faint)", fontWeight: 400 }}>
          {multiGroups.length} continuity{" "}
          {multiGroups.length === 1 ? "group" : "groups"}
        </span>
      </button>

      {open && (
        <div style={{ display: "grid", gap: 10, marginTop: 6 }}>

          {/* Disclaimer — required, fixed wording */}
          <div
            style={{
              fontSize: 10,
              color: "var(--tl-text-muted)",
              background: "rgba(148, 163, 184, 0.07)",
              border: "1px solid rgba(148, 163, 184, 0.18)",
              borderRadius: 4,
              padding: "5px 8px",
              lineHeight: 1.5,
            }}
          >
            Anchor grouping is advisory only. Continuity is not a guarantee.
          </div>

          {/* Multi-segment group cards */}
          <div style={{ display: "grid", gap: 6 }}>
            {multiGroups.map((grp) => {
              const segCount = grp.source_segment_ids.length;
              const folderDisplay =
                grp.anchor_folder_path
                  ? Array.isArray(grp.anchor_folder_path)
                    ? grp.anchor_folder_path.join(" / ")
                    : String(grp.anchor_folder_path)
                  : null;

              return (
                <div
                  key={grp.anchor_reference_feature_id}
                  style={{
                    background: "rgba(148, 163, 184, 0.05)",
                    border: "1px solid rgba(148, 163, 184, 0.18)",
                    borderRadius: 5,
                    overflow: "hidden",
                  }}
                >
                  {/* Group header */}
                  <div
                    style={{
                      background: "rgba(148, 163, 184, 0.08)",
                      borderBottom: "1px solid rgba(148, 163, 184, 0.14)",
                      padding: "5px 8px",
                      display: "grid",
                      gap: 2,
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "baseline",
                        gap: 8,
                      }}
                    >
                      <span
                        style={{
                          color: "var(--tl-text)",
                          fontSize: 10,
                          fontWeight: 700,
                        }}
                      >
                        {grp.anchor_name}
                      </span>
                      <span
                        style={{
                          color: "var(--tl-text-faint)",
                          fontSize: 9,
                          fontWeight: 400,
                          whiteSpace: "nowrap",
                        }}
                      >
                        {segCount} segments
                      </span>
                    </div>
                    {folderDisplay && (
                      <div
                        style={{
                          color: "var(--tl-text-faint)",
                          fontSize: 9,
                        }}
                      >
                        {folderDisplay}
                      </div>
                    )}
                    <div
                      style={{
                        color: "var(--tl-text-faint)",
                        fontSize: 9,
                        fontFamily: "monospace",
                      }}
                    >
                      {grp.anchor_reference_feature_id}
                    </div>
                  </div>

                  {/* Member rows */}
                  <div style={{ display: "grid", gap: 0 }}>
                    {grp.source_segment_ids.map((sid, idx) => {
                      const engId = grp.engineering_object_ids[idx] ?? null;
                      const evItems = grp.evidence.filter(
                        (ev) => ev.segment_id === sid,
                      );
                      return (
                        <div
                          key={sid}
                          style={{
                            padding: "4px 8px",
                            borderTop:
                              idx > 0
                                ? "1px solid rgba(148, 163, 184, 0.1)"
                                : undefined,
                            display: "grid",
                            gap: 1,
                          }}
                        >
                          {/* Segment ID */}
                          <div
                            style={{
                              fontFamily: "monospace",
                              fontSize: 9,
                              color: "var(--tl-text)",
                              fontWeight: 600,
                            }}
                          >
                            {sid}
                          </div>
                          {/* Engineering object ID */}
                          {engId && (
                            <div
                              style={{
                                display: "flex",
                                gap: 6,
                                alignItems: "center",
                              }}
                            >
                              <span
                                style={{
                                  color: "var(--tl-text-faint)",
                                  fontSize: 9,
                                }}
                              >
                                route ref
                              </span>
                              <span
                                style={{
                                  fontFamily: "monospace",
                                  fontSize: 9,
                                  color: "var(--tl-text-faint)",
                                }}
                              >
                                {engId}
                              </span>
                            </div>
                          )}
                          {/* Endpoint evidence */}
                          {evItems.map((ev, ei) => (
                            <div
                              key={ei}
                              style={{
                                display: "flex",
                                gap: 6,
                                alignItems: "center",
                                fontSize: 9,
                                color: "var(--tl-text-faint)",
                              }}
                            >
                              <span style={{ opacity: 0.7 }}>
                                {ev.endpoint} endpoint
                              </span>
                              <span
                                style={{
                                  fontFamily: "monospace",
                                  opacity: 0.8,
                                }}
                              >
                                {ev.distance_ft} ft
                              </span>
                            </div>
                          ))}
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Ungrouped list */}
          {data.ungrouped_segment_ids.length > 0 && (
            <div>
              <div
                style={{
                  fontSize: 9,
                  fontWeight: 700,
                  color: "var(--tl-text-faint)",
                  textTransform: "uppercase",
                  letterSpacing: 0.5,
                  marginBottom: 4,
                }}
              >
                ungrouped segments
              </div>
              <div
                style={{
                  fontFamily: "monospace",
                  fontSize: 9,
                  color: "var(--tl-text-faint)",
                  lineHeight: 1.6,
                }}
              >
                {data.ungrouped_segment_ids.join(" · ")}
              </div>
            </div>
          )}

          {/* Stability note */}
          <div
            style={{
              color: "var(--tl-text-faint)",
              fontSize: 9,
              fontStyle: "italic",
              lineHeight: 1.4,
              borderTop: "1px solid rgba(148, 163, 184, 0.12)",
              paddingTop: 6,
            }}
          >
            {data.stability_note}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Phase 1S — Bore-log redline endpoint validator panel
// ---------------------------------------------------------------------------

function DiagRedlineEndpointValidation({
  data,
}: {
  data: RedlineEndpointValidationResponse | null;
}) {
  const [open, setOpen] = useState(false);

  const s = data?.summary;
  const hasData = s && s.total_endpoints > 0;

  const anchoredPct =
    s?.anchored_pct != null ? (s.anchored_pct * 100).toFixed(1) + "%" : "—";
  const flagCount = s?.flagged_segments?.length ?? 0;

  return (
    <div
      style={{
        border: "1px solid rgba(148, 163, 184, 0.18)",
        borderRadius: 6,
        overflow: "hidden",
      }}
    >
      {/* Header / toggle */}
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          width: "100%",
          background: "rgba(148, 163, 184, 0.07)",
          border: "none",
          padding: "7px 10px",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
        }}
      >
        <span
          style={{
            color: "var(--tl-text)",
            fontSize: 10,
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: 0.5,
          }}
        >
          Bore-log redline endpoint validation
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {hasData && (
            <span
              style={{
                color:
                  s.anchored_pct != null && s.anchored_pct >= 0.95
                    ? "var(--tl-green, #4ade80)"
                    : "var(--tl-amber, #fbbf24)",
                fontSize: 9,
                fontWeight: 600,
              }}
            >
              {anchoredPct} anchored
            </span>
          )}
          <span
            style={{
              color: "var(--tl-text-faint)",
              fontSize: 9,
              transform: open ? "rotate(180deg)" : undefined,
              display: "inline-block",
            }}
          >
            ▾
          </span>
        </span>
      </button>

      {open && (
        <div
          style={{
            padding: "10px 12px",
            display: "grid",
            gap: 10,
          }}
        >
          {!hasData ? (
            <div
              style={{
                color: "var(--tl-text-faint)",
                fontSize: 9,
                fontStyle: "italic",
              }}
            >
              {data
                ? "No redline endpoints to validate — upload a KMZ and generate a redline first."
                : "Endpoint validation not yet computed."}
            </div>
          ) : (
            <>
              {/* Summary counts */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 6 }}>
                {(
                  [
                    ["anchored", s.anchored_count, "var(--tl-green, #4ade80)"],
                    ["near", s.near_count, "var(--tl-amber, #fbbf24)"],
                    ["orphan", s.orphan_count, "var(--tl-red, #f87171)"],
                    ["no anchors", s.no_anchors_in_kmz_count, "var(--tl-text-faint)"],
                  ] as [string, number, string][]
                ).map(([label, count, color]) => (
                  <div
                    key={label}
                    style={{
                      background: "rgba(148, 163, 184, 0.05)",
                      border: "1px solid rgba(148, 163, 184, 0.13)",
                      borderRadius: 4,
                      padding: "5px 6px",
                      textAlign: "center",
                    }}
                  >
                    <div style={{ color, fontSize: 13, fontWeight: 700 }}>
                      {count}
                    </div>
                    <div
                      style={{
                        color: "var(--tl-text-faint)",
                        fontSize: 8,
                        textTransform: "uppercase",
                        letterSpacing: 0.4,
                      }}
                    >
                      {label}
                    </div>
                  </div>
                ))}
              </div>

              {/* Anchored % bar */}
              <div>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    marginBottom: 3,
                  }}
                >
                  <span
                    style={{ color: "var(--tl-text-faint)", fontSize: 9 }}
                  >
                    anchored
                  </span>
                  <span
                    style={{
                      color:
                        s.anchored_pct != null && s.anchored_pct >= 0.95
                          ? "var(--tl-green, #4ade80)"
                          : "var(--tl-amber, #fbbf24)",
                      fontSize: 9,
                      fontWeight: 600,
                    }}
                  >
                    {anchoredPct}
                  </span>
                </div>
                <div
                  style={{
                    height: 4,
                    background: "rgba(148, 163, 184, 0.15)",
                    borderRadius: 2,
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      height: "100%",
                      width: `${(s.anchored_pct ?? 0) * 100}%`,
                      background:
                        s.anchored_pct != null && s.anchored_pct >= 0.95
                          ? "var(--tl-green, #4ade80)"
                          : "var(--tl-amber, #fbbf24)",
                      borderRadius: 2,
                    }}
                  />
                </div>
              </div>

              {/* Flagged segments */}
              {flagCount > 0 && (
                <div>
                  <div
                    style={{
                      fontSize: 9,
                      fontWeight: 700,
                      color: "var(--tl-text-faint)",
                      textTransform: "uppercase",
                      letterSpacing: 0.5,
                      marginBottom: 4,
                    }}
                  >
                    flagged segments ({flagCount} with non-anchored endpoint)
                  </div>
                  <div
                    style={{
                      fontFamily: "monospace",
                      fontSize: 9,
                      color: "var(--tl-amber, #fbbf24)",
                      lineHeight: 1.7,
                      maxHeight: 100,
                      overflowY: "auto",
                    }}
                  >
                    {s.flagged_segments.join(" · ")}
                  </div>
                </div>
              )}

              {/* By-route summary */}
              {Object.keys(s.by_route).length > 0 && (
                <div>
                  <div
                    style={{
                      fontSize: 9,
                      fontWeight: 700,
                      color: "var(--tl-text-faint)",
                      textTransform: "uppercase",
                      letterSpacing: 0.5,
                      marginBottom: 4,
                    }}
                  >
                    by route
                  </div>
                  <div
                    style={{
                      display: "grid",
                      gap: 3,
                      maxHeight: 160,
                      overflowY: "auto",
                    }}
                  >
                    {Object.entries(s.by_route).map(([routeId, counts]) => {
                      const total =
                        counts.anchored +
                        counts.near +
                        counts.orphan +
                        counts.no_anchors_in_kmz;
                      const pct =
                        total > 0
                          ? ((counts.anchored / total) * 100).toFixed(0) + "%"
                          : "—";
                      const hasIssue = counts.near > 0 || counts.orphan > 0;
                      return (
                        <div
                          key={routeId}
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            gap: 8,
                          }}
                        >
                          <span
                            style={{
                              fontFamily: "monospace",
                              fontSize: 9,
                              color: hasIssue
                                ? "var(--tl-amber, #fbbf24)"
                                : "var(--tl-text-faint)",
                              flex: 1,
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {routeId}
                          </span>
                          <span
                            style={{
                              fontSize: 9,
                              color: "var(--tl-text-faint)",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {pct} anchored
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </>
          )}

          {/* Stability note */}
          <div
            style={{
              color: "var(--tl-text-faint)",
              fontSize: 9,
              fontStyle: "italic",
              lineHeight: 1.4,
              borderTop: "1px solid rgba(148, 163, 184, 0.12)",
              paddingTop: 6,
            }}
          >
            {data?.stability_note ?? "Endpoint validation is advisory only."}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Phase 1T — Endpoint snap candidates panel
// ---------------------------------------------------------------------------

function DiagEndpointSnapCandidates({
  data,
  decisions,
  reviewSummary,
  onDecisionChange,
}: {
  data: EndpointSnapRecommendationsResponse | null;
  decisions: Record<string, SnapReviewEventRecord | null>;
  reviewSummary: SnapReviewEventsSummary | null;
  onDecisionChange: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [posting, setPosting] = useState<string | null>(null); // composite key being posted

  const s = data?.summary;
  const total = s?.total_recommendations ?? 0;
  const recs = data?.recommendations ?? [];

  async function submitDecision(
    segId: string,
    ep: string,
    decision: SnapReviewDecision,
  ) {
    const key = `${segId}|${ep}`;
    setPosting(key);
    try {
      await apiFetch(`${API_BASE}/api/observability/snap-review-events`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          segment_id: segId,
          endpoint: ep,
          decision,
          operator_id: "office-reviewer",
        }),
      });
      onDecisionChange();
    } catch {
      // Silently ignore — advisory only.
    } finally {
      setPosting(null);
    }
  }

  const decisionColorMap: Record<string, string> = {
    approved: "var(--tl-green, #4ade80)",
    rejected: "var(--tl-red, #f87171)",
  };

  return (
    <div
      style={{
        border: "1px solid rgba(148, 163, 184, 0.18)",
        borderRadius: 6,
        overflow: "hidden",
      }}
    >
      {/* Header / toggle */}
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          width: "100%",
          background: "rgba(148, 163, 184, 0.07)",
          border: "none",
          padding: "7px 10px",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
        }}
      >
        <span
          style={{
            color: "var(--tl-text)",
            fontSize: 10,
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: 0.5,
          }}
        >
          Endpoint snap candidates
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {total > 0 && (
            <span
              style={{
                color: "var(--tl-text-faint)",
                fontSize: 9,
                fontWeight: 500,
              }}
            >
              {total} candidate{total !== 1 ? "s" : ""}
            </span>
          )}
          <span
            style={{
              color: "var(--tl-text-faint)",
              fontSize: 9,
              transform: open ? "rotate(180deg)" : undefined,
              display: "inline-block",
            }}
          >
            ▾
          </span>
        </span>
      </button>

      {open && (
        <div
          style={{
            padding: "10px 12px",
            display: "grid",
            gap: 10,
          }}
        >
          {/* Phase 1U — review summary block */}
          {reviewSummary && (
            <div
              style={{
                display: "flex",
                gap: 8,
                flexWrap: "wrap",
                borderBottom: "1px solid rgba(148, 163, 184, 0.12)",
                paddingBottom: 8,
              }}
            >
              {(
                [
                  ["events", reviewSummary.total_events, "var(--tl-text-faint)"],
                  ["approved", reviewSummary.approved_count, "var(--tl-green, #4ade80)"],
                  ["rejected", reviewSummary.rejected_count, "var(--tl-red, #f87171)"],
                  ["revoked", reviewSummary.revoked_count, "var(--tl-text-faint)"],
                  ["reviewed", reviewSummary.reviewed_recommendation_count, "var(--tl-blue, #60a5fa)"],
                  ["unreviewed", reviewSummary.unreviewed_recommendation_count, "var(--tl-amber, #fbbf24)"],
                ] as [string, number, string][]
              ).map(([label, count, color]) => (
                <span
                  key={label}
                  style={{
                    background: "rgba(148, 163, 184, 0.06)",
                    border: "1px solid rgba(148, 163, 184, 0.15)",
                    borderRadius: 3,
                    padding: "2px 6px",
                    fontSize: 9,
                    color,
                    fontWeight: 500,
                  }}
                >
                  {count} {label}
                </span>
              ))}
            </div>
          )}

          {total === 0 ? (
            <div
              style={{
                color: "var(--tl-text-faint)",
                fontSize: 9,
                fontStyle: "italic",
              }}
            >
              {data
                ? "No snap candidates — all endpoints are already anchored or no anchors are present."
                : "Snap candidates not yet computed."}
            </div>
          ) : (
            <>
              {/* Summary pills */}
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {(
                  [
                    ["near", s?.near_recommendations ?? 0, "var(--tl-amber, #fbbf24)"],
                    ["orphan", s?.orphan_recommendations ?? 0, "var(--tl-red, #f87171)"],
                  ] as [string, number, string][]
                ).map(([label, count, color]) =>
                  count > 0 ? (
                    <span
                      key={label}
                      style={{
                        background: "rgba(148, 163, 184, 0.07)",
                        border: "1px solid rgba(148, 163, 184, 0.18)",
                        borderRadius: 3,
                        padding: "2px 6px",
                        fontSize: 9,
                        color,
                        fontWeight: 600,
                      }}
                    >
                      {count} {label}
                    </span>
                  ) : null,
                )}
              </div>

              {/* Per-recommendation rows */}
              <div
                style={{
                  display: "grid",
                  gap: 4,
                  maxHeight: 400,
                  overflowY: "auto",
                }}
              >
                {recs.map((rec, idx) => {
                  const compositeKey = `${rec.segment_id}|${rec.endpoint}`;
                  const currentEvent = compositeKey in decisions ? decisions[compositeKey] : undefined;
                  const currentDecision: SnapReviewDecision | null =
                    currentEvent !== undefined ? (currentEvent?.decision ?? null) : null;
                  const isPosting = posting === compositeKey;

                  return (
                    <div
                      key={`${rec.segment_id}-${rec.endpoint}-${idx}`}
                      style={{
                        background: "rgba(148, 163, 184, 0.04)",
                        border: "1px solid rgba(148, 163, 184, 0.13)",
                        borderRadius: 4,
                        padding: "5px 8px",
                        display: "grid",
                        gap: 4,
                      }}
                    >
                      {/* Row 1: segment + endpoint + classification + decision badge */}
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "baseline",
                          gap: 8,
                        }}
                      >
                        <span
                          style={{
                            fontFamily: "monospace",
                            fontSize: 9,
                            fontWeight: 700,
                            color: "var(--tl-text)",
                          }}
                        >
                          {rec.segment_id}
                          <span
                            style={{
                              fontWeight: 400,
                              color: "var(--tl-text-faint)",
                              marginLeft: 4,
                            }}
                          >
                            [{rec.endpoint}]
                          </span>
                        </span>
                        <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          {currentDecision && (
                            <span
                              style={{
                                fontSize: 8,
                                fontWeight: 700,
                                color: decisionColorMap[currentDecision] ?? "var(--tl-text-faint)",
                                textTransform: "uppercase",
                                letterSpacing: 0.3,
                              }}
                            >
                              {currentDecision}
                              {currentEvent?.created_at && (
                                <span
                                  style={{
                                    fontWeight: 400,
                                    color: "var(--tl-text-faint)",
                                    marginLeft: 4,
                                    textTransform: "none",
                                  }}
                                >
                                  {new Date(currentEvent.created_at).toLocaleTimeString([], {
                                    hour: "2-digit",
                                    minute: "2-digit",
                                  })}
                                </span>
                              )}
                            </span>
                          )}
                          <span
                            style={{
                              fontSize: 9,
                              fontWeight: 600,
                              color:
                                rec.classification === "orphan"
                                  ? "var(--tl-red, #f87171)"
                                  : "var(--tl-amber, #fbbf24)",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {rec.classification}
                          </span>
                        </span>
                      </div>

                      {/* Row 2: delta + candidate anchor */}
                      <div
                        style={{
                          display: "flex",
                          gap: 12,
                          alignItems: "center",
                          flexWrap: "wrap",
                        }}
                      >
                        <span
                          style={{
                            fontSize: 9,
                            color: "var(--tl-text-faint)",
                          }}
                        >
                          delta{" "}
                          <span
                            style={{
                              fontFamily: "monospace",
                              color: "var(--tl-text)",
                            }}
                          >
                            {rec.snap_delta_ft.toFixed(2)} ft
                          </span>
                        </span>
                        <span
                          style={{
                            fontSize: 9,
                            color: "var(--tl-text-faint)",
                          }}
                        >
                          candidate{" "}
                          <span
                            style={{
                              fontFamily: "monospace",
                              color: "var(--tl-text)",
                            }}
                          >
                            {rec.candidate_anchor_name ?? rec.candidate_anchor_id}
                          </span>
                        </span>
                      </div>

                      {/* Row 3: Phase 1U review decision buttons */}
                      <div
                        style={{
                          display: "flex",
                          gap: 5,
                          flexWrap: "wrap",
                          paddingTop: 3,
                          borderTop: "1px solid rgba(148, 163, 184, 0.10)",
                        }}
                      >
                        {(["approved", "rejected"] as SnapReviewDecision[]).map((dec) => {
                          const isActive = currentDecision === dec;
                          return (
                            <button
                              key={dec}
                              disabled={isPosting || isActive}
                              onClick={() => void submitDecision(rec.segment_id, rec.endpoint, dec)}
                              style={{
                                fontSize: 8,
                                padding: "2px 7px",
                                borderRadius: 3,
                                border: `1px solid ${isActive ? decisionColorMap[dec] : "rgba(148, 163, 184, 0.22)"}`,
                                background: isActive
                                  ? `${decisionColorMap[dec]}22`
                                  : "transparent",
                                color: isActive
                                  ? decisionColorMap[dec]
                                  : "var(--tl-text-faint)",
                                cursor: isPosting || isActive ? "default" : "pointer",
                                opacity: isPosting ? 0.5 : 1,
                                fontWeight: isActive ? 700 : 400,
                                textTransform: "capitalize",
                              }}
                            >
                              Mark {dec}
                            </button>
                          );
                        })}
                        {currentDecision && currentDecision !== "revoked" && (
                          <button
                            disabled={isPosting}
                            onClick={() => void submitDecision(rec.segment_id, rec.endpoint, "revoked")}
                            style={{
                              fontSize: 8,
                              padding: "2px 7px",
                              borderRadius: 3,
                              border: "1px solid rgba(148, 163, 184, 0.22)",
                              background: "transparent",
                              color: "var(--tl-text-faint)",
                              cursor: isPosting ? "default" : "pointer",
                              opacity: isPosting ? 0.5 : 1,
                            }}
                          >
                            Revoke
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          )}

          {/* Disclaimer */}
          <div
            style={{
              color: "var(--tl-text-faint)",
              fontSize: 9,
              fontStyle: "italic",
              lineHeight: 1.5,
              borderTop: "1px solid rgba(148, 163, 184, 0.12)",
              paddingTop: 6,
            }}
          >
            These are review aids only. Candidate coordinates are the exact
            nearest anchor locations already identified by the endpoint
            validator — no new geometry is computed. Decisions are advisory
            events and do not modify geometry, matching, or any operational
            system.
          </div>

          {/* Stability note */}
          <div
            style={{
              color: "var(--tl-text-faint)",
              fontSize: 9,
              fontStyle: "italic",
              lineHeight: 1.4,
            }}
          >
            {data?.stability_note ?? "Snap recommendations are advisory only."}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Phase 1V — Endpoint-Only Snap Preview Markers (diagnostic-only)
// ---------------------------------------------------------------------------

function DiagSnapPreviewMarkers({
  data,
}: {
  data: SnapPreviewMarkersResponse | null;
}) {
  // OFF by default — strict requirement of Phase 1V.
  const [open, setOpen] = useState(false);

  const summary = data?.summary;
  const total = summary?.total_markers ?? 0;
  const markers = data?.markers ?? [];

  const decisionColorMap: Record<string, string> = {
    approved: "var(--tl-green, #4ade80)",
    rejected: "var(--tl-red, #f87171)",
  };

  return (
    <div
      style={{
        border: "1px solid rgba(148, 163, 184, 0.18)",
        borderRadius: 6,
        overflow: "hidden",
      }}
    >
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          width: "100%",
          background: "rgba(148, 163, 184, 0.07)",
          border: "none",
          padding: "7px 10px",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
        }}
      >
        <span
          style={{
            color: "var(--tl-text)",
            fontSize: 10,
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: 0.5,
          }}
        >
          Snap preview markers
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {total > 0 && (
            <span
              style={{
                color: "var(--tl-text-faint)",
                fontSize: 9,
                fontWeight: 500,
              }}
            >
              {total} marker{total !== 1 ? "s" : ""}
            </span>
          )}
          <span
            style={{
              color: "var(--tl-text-faint)",
              fontSize: 9,
              transform: open ? "rotate(180deg)" : undefined,
              display: "inline-block",
            }}
          >
            ▾
          </span>
        </span>
      </button>

      {open && (
        <div
          style={{
            padding: "10px 12px",
            display: "grid",
            gap: 10,
          }}
        >
          {/* Summary block */}
          {summary && (
            <div
              style={{
                display: "flex",
                gap: 8,
                flexWrap: "wrap",
              }}
            >
              {(
                [
                  ["total", summary.total_markers, "var(--tl-text-faint)"],
                  ["near", summary.near_markers, "var(--tl-amber, #fbbf24)"],
                  ["orphan", summary.orphan_markers, "var(--tl-red, #f87171)"],
                  ["with decision", summary.with_decision, "var(--tl-blue, #60a5fa)"],
                  ["unreviewed", summary.without_decision, "var(--tl-text-faint)"],
                ] as [string, number, string][]
              ).map(([label, count, color]) => (
                <span
                  key={label}
                  style={{
                    background: "rgba(148, 163, 184, 0.06)",
                    border: "1px solid rgba(148, 163, 184, 0.15)",
                    borderRadius: 3,
                    padding: "2px 6px",
                    fontSize: 9,
                    color,
                    fontWeight: 500,
                  }}
                >
                  {count} {label}
                </span>
              ))}
            </div>
          )}

          {total === 0 ? (
            <div
              style={{
                color: "var(--tl-text-faint)",
                fontSize: 9,
                fontStyle: "italic",
              }}
            >
              {data
                ? "No preview markers — no snap candidates exist for the current upload."
                : "Preview markers not yet computed."}
            </div>
          ) : (
            <div
              style={{
                display: "grid",
                gap: 4,
                maxHeight: 360,
                overflowY: "auto",
              }}
            >
              {markers.map((m) => (
                <div
                  key={m.marker_id}
                  style={{
                    background: "rgba(148, 163, 184, 0.04)",
                    border: "1px solid rgba(148, 163, 184, 0.13)",
                    borderRadius: 4,
                    padding: "5px 8px",
                    display: "grid",
                    gap: 3,
                  }}
                >
                  {/* Row 1: segment+endpoint, classification, decision badge */}
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "baseline",
                      gap: 8,
                    }}
                  >
                    <span
                      style={{
                        fontFamily: "monospace",
                        fontSize: 9,
                        fontWeight: 700,
                        color: "var(--tl-text)",
                      }}
                    >
                      {m.segment_id}
                      <span
                        style={{
                          fontWeight: 400,
                          color: "var(--tl-text-faint)",
                          marginLeft: 4,
                        }}
                      >
                        [{m.endpoint}]
                      </span>
                    </span>
                    <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      {m.current_decision && (
                        <span
                          style={{
                            fontSize: 8,
                            fontWeight: 700,
                            color:
                              decisionColorMap[m.current_decision] ??
                              "var(--tl-text-faint)",
                            textTransform: "uppercase",
                            letterSpacing: 0.3,
                          }}
                        >
                          {m.current_decision}
                        </span>
                      )}
                      <span
                        style={{
                          fontSize: 9,
                          fontWeight: 600,
                          color:
                            m.classification === "orphan"
                              ? "var(--tl-red, #f87171)"
                              : "var(--tl-amber, #fbbf24)",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {m.classification}
                      </span>
                    </span>
                  </div>

                  {/* Row 2: candidate anchor name + delta */}
                  <div
                    style={{
                      display: "flex",
                      gap: 12,
                      alignItems: "center",
                      flexWrap: "wrap",
                    }}
                  >
                    <span
                      style={{
                        fontSize: 9,
                        color: "var(--tl-text-faint)",
                      }}
                    >
                      candidate{" "}
                      <span
                        style={{
                          fontFamily: "monospace",
                          color: "var(--tl-text)",
                        }}
                      >
                        {m.candidate_anchor_name ?? m.candidate_anchor_id}
                      </span>
                    </span>
                    <span
                      style={{
                        fontSize: 9,
                        color: "var(--tl-text-faint)",
                      }}
                    >
                      delta{" "}
                      <span
                        style={{
                          fontFamily: "monospace",
                          color: "var(--tl-text)",
                        }}
                      >
                        {(m.snap_delta_ft ?? 0).toFixed(2)} ft
                      </span>
                    </span>
                    <span
                      style={{
                        fontSize: 8,
                        color: "var(--tl-text-faint)",
                        fontFamily: "monospace",
                        opacity: 0.7,
                      }}
                    >
                      {m.marker_id}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Stability note */}
          <div
            style={{
              color: "var(--tl-text-faint)",
              fontSize: 9,
              fontStyle: "italic",
              lineHeight: 1.5,
              borderTop: "1px solid rgba(148, 163, 184, 0.12)",
              paddingTop: 6,
            }}
          >
            {data?.stability_note ??
              "Snap preview markers are advisory review aids only."}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Phase 1W — Reviewed Snap Preview Geometry (diagnostic-only)
// ---------------------------------------------------------------------------

function DiagReviewedSnapPreview({
  data,
}: {
  data: ReviewedSnapPreviewResponse | null;
}) {
  // OFF by default — strict requirement of Phase 1W.
  const [open, setOpen] = useState(false);

  const summary = data?.summary;
  const total = summary?.total_previews ?? 0;
  const previews = data?.previews ?? [];

  return (
    <div
      style={{
        border: "1px solid rgba(148, 163, 184, 0.18)",
        borderRadius: 6,
        overflow: "hidden",
      }}
    >
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          width: "100%",
          background: "rgba(148, 163, 184, 0.07)",
          border: "none",
          padding: "7px 10px",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
        }}
      >
        <span
          style={{
            color: "var(--tl-text)",
            fontSize: 10,
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: 0.5,
          }}
        >
          Reviewed snap preview geometry
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {total > 0 && (
            <span
              style={{
                color: "var(--tl-text-faint)",
                fontSize: 9,
                fontWeight: 500,
              }}
            >
              {total} preview{total !== 1 ? "s" : ""}
            </span>
          )}
          <span
            style={{
              color: "var(--tl-text-faint)",
              fontSize: 9,
              transform: open ? "rotate(180deg)" : undefined,
              display: "inline-block",
            }}
          >
            ▾
          </span>
        </span>
      </button>

      {open && (
        <div style={{ padding: "10px 12px", display: "grid", gap: 10 }}>
          {/* Summary block */}
          {summary && (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {(
                [
                  ["total previews", summary.total_previews, "var(--tl-text-faint)"],
                  ["start only", summary.previews_with_start_only, "var(--tl-amber, #fbbf24)"],
                  ["end only", summary.previews_with_end_only, "var(--tl-amber, #fbbf24)"],
                  ["both", summary.previews_with_both, "var(--tl-green, #4ade80)"],
                  ["stale", summary.stale_previews, "var(--tl-red, #f87171)"],
                ] as [string, number, string][]
              ).map(([label, count, color]) => (
                <span
                  key={label}
                  style={{
                    background: "rgba(148, 163, 184, 0.06)",
                    border: "1px solid rgba(148, 163, 184, 0.15)",
                    borderRadius: 3,
                    padding: "2px 6px",
                    fontSize: 9,
                    color,
                    fontWeight: 500,
                  }}
                >
                  {count} {label}
                </span>
              ))}
            </div>
          )}

          {total === 0 ? (
            <div
              style={{
                color: "var(--tl-text-faint)",
                fontSize: 9,
                fontStyle: "italic",
              }}
            >
              {data
                ? "No preview geometry — no approved endpoint substitutions exist."
                : "Preview geometry not yet computed."}
            </div>
          ) : (
            <div
              style={{
                display: "grid",
                gap: 5,
                maxHeight: 400,
                overflowY: "auto",
              }}
            >
              {previews.map((p) => {
                const subStart = p.endpoint_substitutions.start;
                const subEnd = p.endpoint_substitutions.end;
                const vertexCount = p.preview_geometry.coordinates.length;

                return (
                  <div
                    key={p.preview_id}
                    style={{
                      background: "rgba(148, 163, 184, 0.04)",
                      border: "1px solid rgba(148, 163, 184, 0.13)",
                      borderRadius: 4,
                      padding: "5px 8px",
                      display: "grid",
                      gap: 3,
                    }}
                  >
                    {/* Row 1: segment + vertex count */}
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "baseline",
                        gap: 8,
                      }}
                    >
                      <span
                        style={{
                          fontFamily: "monospace",
                          fontSize: 9,
                          fontWeight: 700,
                          color: "var(--tl-text)",
                        }}
                      >
                        {p.source_segment_id}
                      </span>
                      <span
                        style={{ fontSize: 8, color: "var(--tl-text-faint)" }}
                      >
                        {vertexCount} vertices
                      </span>
                    </div>

                    {/* Row 2: substitution summary */}
                    <div
                      style={{
                        display: "flex",
                        gap: 8,
                        flexWrap: "wrap",
                        alignItems: "center",
                      }}
                    >
                      {(
                        [
                          ["start", subStart],
                          ["end", subEnd],
                        ] as [string, typeof subStart][]
                      ).map(([ep, sub]) => (
                        <span
                          key={ep}
                          style={{
                            fontSize: 8,
                            color: sub
                              ? "var(--tl-green, #4ade80)"
                              : "var(--tl-text-faint)",
                            fontWeight: sub ? 600 : 400,
                          }}
                        >
                          {ep}:{" "}
                          {sub ? (
                            <span style={{ fontFamily: "monospace" }}>
                              {sub.candidate_anchor_id}
                            </span>
                          ) : (
                            "unchanged"
                          )}
                        </span>
                      ))}
                    </div>

                    {/* Row 3: checksum + preview_id */}
                    <div
                      style={{
                        display: "flex",
                        gap: 12,
                        alignItems: "center",
                        flexWrap: "wrap",
                      }}
                    >
                      <span
                        style={{
                          fontSize: 8,
                          color: "var(--tl-text-faint)",
                          fontFamily: "monospace",
                          opacity: 0.7,
                        }}
                      >
                        checksum: {p.operational_segment_checksum.slice(0, 12)}…
                      </span>
                      <span
                        style={{
                          fontSize: 8,
                          color: "var(--tl-text-faint)",
                          fontFamily: "monospace",
                          opacity: 0.6,
                        }}
                      >
                        pid: {p.preview_id}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Stability note */}
          <div
            style={{
              color: "var(--tl-text-faint)",
              fontSize: 9,
              fontStyle: "italic",
              lineHeight: 1.5,
              borderTop: "1px solid rgba(148, 163, 184, 0.12)",
              paddingTop: 6,
            }}
          >
            {data?.stability_note ??
              "Reviewed snap preview geometry is advisory only."}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Phase 1M — KMZ engineering fidelity audit panel
// ---------------------------------------------------------------------------

function FidelityStatRow({
  label,
  value,
  sub,
}: {
  label: string;
  value: string | number;
  sub?: string;
}) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
      <span style={{ color: "var(--tl-text-muted)" }}>{label}</span>
      <span style={{ color: "var(--tl-text)", fontWeight: 600, textAlign: "right" }}>
        {value}
        {sub && (
          <span style={{ color: "var(--tl-text-faint)", fontWeight: 400, marginLeft: 4 }}>
            {sub}
          </span>
        )}
      </span>
    </div>
  );
}

function FidelitySection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div
        style={{
          fontSize: 9,
          fontWeight: 700,
          color: "var(--tl-text-faint)",
          textTransform: "uppercase",
          letterSpacing: 0.5,
          marginBottom: 4,
        }}
      >
        {title}
      </div>
      <div style={{ display: "grid", gap: 2, fontSize: 10 }}>{children}</div>
    </div>
  );
}

function DiagKmzFidelityAudit({ data }: { data: KmzFidelityAuditResponse | null }) {
  const [open, setOpen] = useState(false);

  if (!data || !data.window.has_semantic_ingest) return null;

  const w = data.window;
  const sf = data.style_fidelity;
  const ff = data.folder_fidelity;
  const ed = data.extended_data_fidelity;
  const gf = data.geometry_fidelity;
  const rs = data.render_simplification;

  const pctStr = (rate: number | null) =>
    rate !== null ? `${(rate * 100).toFixed(1)}%` : "0 %";

  return (
    <div
      style={{
        borderTop: "1px solid rgba(148, 163, 184, 0.18)",
        paddingTop: 8,
        marginTop: 8,
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={{
          background: "none",
          border: "none",
          cursor: "pointer",
          color: "var(--tl-text-faint)",
          fontSize: 11,
          fontWeight: 600,
          padding: "2px 0",
          textAlign: "left",
          width: "100%",
          display: "flex",
          alignItems: "center",
          gap: 6,
          flexWrap: "wrap",
        }}
      >
        <span>{open ? "▾" : "▸"} KMZ engineering fidelity audit</span>
        <span style={{ color: "var(--tl-text-faint)", fontWeight: 400 }}>
          {w.semantic_feature_count} semantic / {w.reference_line_count + w.reference_polygon_count + w.reference_point_count} render features
        </span>
      </button>

      {open && (
        <div style={{ display: "grid", gap: 10, marginTop: 6 }}>

          <FidelitySection title="Style fidelity">
            <FidelityStatRow label="unique style URLs in semantic" value={sf.unique_style_urls_in_semantic} />
            <FidelityStatRow label="features with resolved style props" value={sf.features_with_resolved_style_props} />
            <FidelityStatRow label="features with KML line color" value={sf.features_with_kml_line_color} />
            <FidelityStatRow label="features with KML poly fill" value={sf.features_with_kml_poly_fill} />
            <FidelityStatRow label="features with icon href" value={sf.features_with_icon_href} />
            <FidelityStatRow
              label="style URL preservation in render"
              value={pctStr(sf.style_url_preservation_rate)}
              sub="(render ingest has no style_url field)"
            />
          </FidelitySection>

          <FidelitySection title="Folder hierarchy fidelity">
            <FidelityStatRow label="max folder depth" value={ff.max_folder_depth} />
            <FidelityStatRow
              label="avg folder depth"
              value={ff.avg_folder_depth !== null ? ff.avg_folder_depth.toFixed(2) : "—"}
            />
            <FidelityStatRow label="features with multi-level path" value={ff.features_with_multi_level_path} />
            <FidelityStatRow
              label="hierarchy preservation in render"
              value={pctStr(ff.hierarchy_preservation_rate)}
              sub="(render uses flat string)"
            />
          </FidelitySection>

          <FidelitySection title="ExtendedData fidelity">
            <FidelityStatRow label="unique ExtendedData keys" value={ed.unique_key_count} />
            <FidelityStatRow label="total key/value pairs" value={ed.total_value_count} />
            <FidelityStatRow
              label="ExtendedData preservation in render"
              value={pctStr(ed.preservation_rate)}
              sub="(render ingest has no extended_data)"
            />
            {ed.top_keys.length > 0 && (
              <div style={{ color: "var(--tl-text-faint)", fontSize: 9, marginTop: 2 }}>
                top dropped keys:{" "}
                {ed.top_keys.map((k) => `${k.key} (${k.count})`).join(", ")}
              </div>
            )}
          </FidelitySection>

          <FidelitySection title="MultiGeometry fidelity">
            <FidelityStatRow label="MultiGeometry placemarks" value={gf.multigeometry_placemark_count} />
            <FidelityStatRow label="total child geometries" value={gf.multigeometry_child_count} />
            <FidelityStatRow
              label="parent placemark identity preserved"
              value={gf.reference_preserves_parent_placemark_identity ? "yes" : "no"}
              sub="(render explodes into flat geometries)"
            />
          </FidelitySection>

          <FidelitySection title="Render simplification">
            <FidelityStatRow label="semantic feature fields" value={rs.semantic_field_count} />
            <FidelityStatRow label="render line feature fields" value={rs.reference_line_field_count} />
            <FidelityStatRow label="dropped field count" value={rs.dropped_field_count} />
            {rs.fields_in_semantic_not_in_reference.length > 0 && (
              <div
                style={{
                  color: "var(--tl-text-faint)",
                  fontSize: 9,
                  fontFamily: "monospace",
                  lineHeight: 1.6,
                  marginTop: 2,
                }}
              >
                {rs.fields_in_semantic_not_in_reference.join(" · ")}
              </div>
            )}
          </FidelitySection>

          <div
            style={{
              color: "var(--tl-text-faint)",
              fontSize: 9,
              fontStyle: "italic",
              lineHeight: 1.4,
            }}
          >
            {data.stability_note}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Phase 1L — Review telemetry summary panel
// ---------------------------------------------------------------------------

function DiagReviewLabelSummary({
  data,
}: {
  data: ReviewLabelSummaryResponse | null;
}) {
  const [open, setOpen] = useState(false);

  if (!data || data.total_review_labels === 0) return null;

  const uc = data.resolved_label_counts.useful_catch;
  const noise = data.resolved_label_counts.noise;
  const unclear = data.resolved_label_counts.unclear;
  const total = data.window.resolved_labels;

  const pctStr = (rate: number | null) =>
    rate !== null ? `${(rate * 100).toFixed(1)}%` : "—";

  return (
    <div
      style={{
        borderTop: "1px solid rgba(148, 163, 184, 0.18)",
        paddingTop: 8,
        marginTop: 8,
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={{
          background: "none",
          border: "none",
          cursor: "pointer",
          color: "var(--tl-text-faint)",
          fontSize: 11,
          fontWeight: 600,
          padding: "2px 0",
          textAlign: "left",
          width: "100%",
          display: "flex",
          alignItems: "center",
          gap: 6,
          flexWrap: "wrap",
        }}
      >
        <span>{open ? "▾" : "▸"} Review telemetry summary</span>
        <span style={{ color: "var(--tl-text-faint)", fontWeight: 400 }}>
          {total} resolved label{total !== 1 ? "s" : ""}
        </span>
      </button>

      {open && (
        <div style={{ display: "grid", gap: 8, marginTop: 6, fontSize: 10 }}>

          {/* Resolved label counts */}
          <div>
            <div
              style={{
                fontSize: 9,
                fontWeight: 700,
                color: "var(--tl-text-faint)",
                textTransform: "uppercase",
                letterSpacing: 0.5,
                marginBottom: 4,
              }}
            >
              Label coverage
            </div>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              {[
                { label: "useful catch", value: uc },
                { label: "noise", value: noise },
                { label: "unclear", value: unclear },
              ].map(({ label, value }) => (
                <span key={label} style={{ color: "var(--tl-text-muted)" }}>
                  {label}:{" "}
                  <span style={{ color: "var(--tl-text)", fontWeight: 700 }}>
                    {value}
                  </span>
                </span>
              ))}
              <span style={{ color: "var(--tl-text-muted)" }}>
                total:{" "}
                <span style={{ color: "var(--tl-text)" }}>{data.window.label_events_read}</span>
                {" "}events /{"  "}
                <span style={{ color: "var(--tl-text)" }}>{total}</span>
                {" "}resolved
              </span>
            </div>
          </div>

          {/* Usefulness by review priority */}
          {(["elevated", "standard", "low"] as const).some(
            (p) => data.useful_catch_rate_by_review_priority[p].labeled > 0
          ) && (
            <div>
              <div
                style={{
                  fontSize: 9,
                  fontWeight: 700,
                  color: "var(--tl-text-faint)",
                  textTransform: "uppercase",
                  letterSpacing: 0.5,
                  marginBottom: 4,
                }}
              >
                Review usefulness by evidence category
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "80px 60px 60px 60px",
                  gap: "2px 8px",
                  color: "var(--tl-text-muted)",
                }}
              >
                <span style={{ fontWeight: 700, color: "var(--tl-text-faint)" }}>priority</span>
                <span style={{ fontWeight: 700, color: "var(--tl-text-faint)" }}>labeled</span>
                <span style={{ fontWeight: 700, color: "var(--tl-text-faint)" }}>useful catch</span>
                <span style={{ fontWeight: 700, color: "var(--tl-text-faint)" }}>rate</span>
                {(["elevated", "standard", "low"] as const).map((p) => {
                  const row = data.useful_catch_rate_by_review_priority[p];
                  return row.labeled > 0 ? (
                    <>
                      <span key={`${p}-label`}>{p}</span>
                      <span key={`${p}-n`}>{row.labeled}</span>
                      <span key={`${p}-uc`}>{row.useful_catch}</span>
                      <span key={`${p}-r`}>{pctStr(row.rate)}</span>
                    </>
                  ) : null;
                })}
              </div>
            </div>
          )}

          {/* Usefulness by disagreement kind */}
          {data.useful_catch_rate_by_disagreement_kind.length > 0 && (
            <div>
              <div
                style={{
                  fontSize: 9,
                  fontWeight: 700,
                  color: "var(--tl-text-faint)",
                  textTransform: "uppercase",
                  letterSpacing: 0.5,
                  marginBottom: 4,
                }}
              >
                Review usefulness by disagreement kind
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "180px 50px 60px 50px",
                  gap: "2px 8px",
                  color: "var(--tl-text-muted)",
                }}
              >
                <span style={{ fontWeight: 700, color: "var(--tl-text-faint)" }}>kind</span>
                <span style={{ fontWeight: 700, color: "var(--tl-text-faint)" }}>labeled</span>
                <span style={{ fontWeight: 700, color: "var(--tl-text-faint)" }}>useful catch</span>
                <span style={{ fontWeight: 700, color: "var(--tl-text-faint)" }}>rate</span>
                {data.useful_catch_rate_by_disagreement_kind.map((row) => (
                  <>
                    <span
                      key={`${row.kind}-k`}
                      style={{ fontFamily: "monospace", fontSize: 9 }}
                    >
                      {row.kind}
                    </span>
                    <span key={`${row.kind}-n`}>{row.labeled}</span>
                    <span key={`${row.kind}-uc`}>{row.useful_catch}</span>
                    <span key={`${row.kind}-r`}>{pctStr(row.rate)}</span>
                  </>
                ))}
              </div>
            </div>
          )}

          {/* Stability note */}
          <div
            style={{
              color: "var(--tl-text-faint)",
              fontSize: 9,
              fontStyle: "italic",
              lineHeight: 1.4,
            }}
          >
            {data.stability_note}
          </div>
        </div>
      )}
    </div>
  );
}

function DiagEmptyState({
  statusLabel,
  message,
  hint,
}: {
  statusLabel: string;
  message: string;
  hint: string | null;
}) {
  return (
    <section
      className="tl-card"
      style={{
        marginTop: 14,
        padding: "10px 14px",
        background: "var(--tl-surface)",
        border: "1px dashed rgba(250, 204, 21, 0.45)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span
          className="tl-pill"
          style={{
            fontSize: 10,
            fontWeight: 800,
            letterSpacing: 0.5,
            color: "#fde68a",
            border: "1px solid rgba(250, 204, 21, 0.55)",
            background: "rgba(250, 204, 21, 0.10)",
            padding: "2px 8px",
            borderRadius: 999,
            textTransform: "uppercase",
          }}
        >
          DEBUG
        </span>
        <span style={{ fontSize: 13, fontWeight: 700 }}>
          Semantic Ingestion · {statusLabel}
        </span>
      </div>
      <div
        style={{
          fontSize: 11,
          color: "var(--tl-text-muted)",
          marginTop: 6,
          lineHeight: 1.4,
        }}
      >
        {message}
      </div>
      {hint ? (
        <div
          style={{
            fontSize: 11,
            color: "var(--tl-text-faint)",
            marginTop: 4,
            fontStyle: "italic",
          }}
        >
          {hint}
        </div>
      ) : null}
    </section>
  );
}
