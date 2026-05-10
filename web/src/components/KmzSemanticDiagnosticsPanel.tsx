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

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

import { appendSessionId } from "@/lib/session";
import type {
  BackendState,
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

  useEffect(() => {
    let cancelled = false;
    async function load(): Promise<void> {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(
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
