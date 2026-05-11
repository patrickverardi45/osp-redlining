// All backend-facing and shared UI types for the Redline Map workspace.
// Moved verbatim from components/RedlineMap.tsx as part of Phase 1 extraction.
// No behavior changes. Do not edit shapes here without coordinating with the FastAPI backend.

export type CandidateRanking = {
  route_id?: string;
  route_name?: string;
  source_folder?: string;
  route_role?: string;
  route_length_ft?: number;
  expected_span_ft?: number;
  length_gap_ft?: number;
  score?: number;
  reason?: string;
};

export type VerificationInfo = {
  confidence?: string;
  reason?: string;
  mapping_mode?: string;
  anchor_type?: string;
  print_present?: boolean;
  route_name?: string;
  route_length_ft?: number;
  source_file?: string;
  print?: string;
  candidate_rankings?: CandidateRanking[];
};

export type StationPoint = {
  station?: string;
  /** Fiber / structure id for fiber_pull labeling (optional; bore HDD rows omit). */
  business_id?: string | null;
  station_ft?: number;
  mapped_station_ft?: number;
  lat?: number;
  lon?: number;
  depth_ft?: number | null;
  boc_ft?: number | null;
  notes?: string;
  date?: string;
  crew?: string;
  print?: string;
  source_file?: string;
  point_role?: string;
  verification?: VerificationInfo;
};

export type RedlineSegment = {
  segment_id?: string;
  start_station?: string;
  end_station?: string;
  length_ft?: number;
  print?: string;
  source_file?: string;
  route_name?: string;
  coords?: number[][];
};

export type GroupMatch = {
  route_name?: string;
  route_role?: string;
  confidence_label?: string;
  final_decision?: string;
  expected_span_ft?: number;
  length_gap_ft?: number;
  print?: string;
  candidate_rankings?: CandidateRanking[];
  print_filter?: {
    print_tokens?: string[];
  };
};

export type KmzLineFeature = {
  feature_id?: string;
  route_id?: string;
  route_name?: string;
  source_folder?: string;
  role?: string;
  coords?: number[][];
  color?: string;
  width?: number;
  stroke?: string;
  stroke_width?: number;
};

export type KmzPolygonFeature = {
  feature_id?: string;
  name?: string;
  coords?: number[][];
  fill_color?: string;
  stroke_color?: string;
  fill?: string;
  stroke?: string;
  fill_opacity?: number;
  stroke_width?: number;
};

export type BoreLogSummaryEntry = {
  source_file: string;
  row_count: number;
  min_station_ft?: number | null;
  max_station_ft?: number | null;
  span_ft?: number | null;
  dates?: string[];
  print_tokens?: string[];
  crews?: string[];
  evidence_layer_id?: string;
  engineering_plan_ref?: string | null;
  engineering_plan_date?: string | null;
};

export type EngineeringPlan = {
  plan_id: string;
  session_id: string;
  original_filename: string;
  stored_filename: string;
  file_type: string;
  size_bytes: number;
  uploaded_at: string;
  plan_date?: string | null;
  print_numbers?: string | null;
  sheet_numbers?: string | null;
  street_hints?: string | null;
  notes?: string | null;
};

/**
 * Phase 1A — additive KMZ/KML semantic feature.
 *
 * Each feature corresponds to a single KML <Placemark>. The shape preserves
 * the engineering intelligence that route extraction discards: raw name,
 * description, folder hierarchy, geometry kind, styleUrl, and ExtendedData.
 *
 * Rendering is NOT the source of truth — consumers may use these fields or
 * ignore them. The `classification` is heuristic and additive only; the
 * upstream `role` field on line/polygon/point features is unrelated.
 */
export type SemanticKmzClassification =
  | "handhole"
  | "station_label"
  | "reel"
  | "structure_marker"
  | "route_segment"
  | "boundary_polygon"
  | "annotation"
  | "unknown";

export type SemanticKmzConfidence = "high" | "medium" | "low";

export type SemanticKmzGeometryType =
  | "Point"
  | "LineString"
  | "Polygon"
  | "MultiGeometry"
  | "Other";

/** Phase B — full geometry payloads. Excluded for MultiGeometry placemarks
 *  (use multigeometry_children for those). */
export type SemanticKmzFullGeometry =
  | { kind: "Point"; coord: [number, number] }
  | { kind: "LineString"; coords: Array<[number, number]> }
  | {
      kind: "Polygon";
      outer: Array<[number, number]>;
      inner?: Array<Array<[number, number]>>;
    };

/** Phase B — direct child geometries enumerated for MultiGeometry placemarks. */
export type SemanticKmzMultiGeometryChild = {
  kind: "Point" | "LineString" | "Polygon";
  coord_hint: [number, number] | null;
};

/** Phase C — resolved <Style>/<StyleMap> properties. All fields optional. */
export type SemanticKmzResolvedStyle = {
  line_color?: string;       // "#3b82f6"
  line_width?: number;
  poly_fill?: string;
  icon_href?: string;
  label_color?: string;
};

/** Phase C — lifecycle hint. label is one of a known set; null when no
 *  signal matched. */
export type SemanticKmzLifecycle = {
  label: "existing" | "proposed" | "asbuilt" | "decommissioned" | "survey";
  confidence: SemanticKmzConfidence;
  reason: string;
};

/** Additive read-only explainability metadata produced alongside each
 *  classification. Never affects the classification result itself. */
export type SemanticKmzClassificationDebug = {
  /** Which kind(s) of signal triggered the classification.
   *  Values: "name_regex" | "description_regex" | "extended_data_key"
   *        | "name_contains" | "folder_hint" | "style_url_hint" | "geometry_type" */
  matched_by: string[];
  /** The actual text tokens/strings that matched (regex capture group,
   *  ExtendedData key name, or substring keyword). */
  matched_tokens: string[];
  /** Which input fields were consulted.
   *  Values: "placemark_name" | "placemark_description" | "folder_path"
   *        | "style_url" | "extended_data" | "geometry_type" */
  heuristic_sources: string[];
  /** Which geometry node provided the representative coordinate hint.
   *  "Point" | "LineString" | "Polygon" | null when coords_hint is null. */
  coordinate_source: "Point" | "LineString" | "Polygon" | null;
};

export type SemanticKmzFeature = {
  feature_id: string;
  /** Phase 1B — KML <Placemark id="..."> attribute when present, null
   *  otherwise. Combine with source_filename for cross-file joins. */
  placemark_id?: string | null;
  placemark_name: string;
  /** HTML stripped + whitespace collapsed. */
  description: string;
  /** Verbatim KML <description> text, including any HTML the source used. */
  description_raw: string;
  folder_path: string[];
  folder_path_str: string;
  geometry_type: SemanticKmzGeometryType;
  style_url: string;
  /** Flat key/value map from <ExtendedData><Data> and <SchemaData><SimpleData>. */
  extended_data: Record<string, string>;
  /** Best-effort representative [lat, lon]; null when no geometry was found. */
  coords_hint: [number, number] | null;
  classification: SemanticKmzClassification;
  confidence: SemanticKmzConfidence;
  /** Short string describing which signal triggered the classification. */
  classification_reason: string;
  /** Phase 1B — name of the source KMZ/KML this feature came from. Useful
   *  when a project ingests multiple design files. */
  source_filename?: string;
  /** Phase A — chainage (in feet) parsed from "STA NN+NN" tokens.
   *  null when no chainage token was present. */
  chainage_ft?: number | null;
  chainage_source?: "name" | "description" | null;
  /** Phase A — sequence number parsed from classification-specific tokens
   *  ("HH-12" → 12 when classification === "handhole"). null otherwise. */
  sequence_number?: number | null;
  sequence_kind?:
    | "handhole"
    | "manhole"
    | "reel"
    | "structure"
    | null;
  /** Phase B — full geometry payload for non-MultiGeometry placemarks.
   *  null for MultiGeometry; see multigeometry_children. */
  full_geometry?: SemanticKmzFullGeometry | null;
  multigeometry_children?: SemanticKmzMultiGeometryChild[];
  /** Phase C — style resolved against the document-level <Style>/<StyleMap>
   *  table. null when style_url is empty or unresolved. */
  style_resolved?: SemanticKmzResolvedStyle | null;
  lifecycle?: SemanticKmzLifecycle | null;
  /** Additive read-only explainability metadata. Present from parser_version
   *  "semantic-1" onward. Never affects classification, scoring, or rendering. */
  classification_debug?: SemanticKmzClassificationDebug | null;
};

export type SemanticKmzIndex = {
  feature_count: number;
  truncated: boolean;
  by_classification: Record<string, number>;
  by_geometry_type: Record<string, number>;
  by_folder: Record<string, number>;
  by_confidence: Record<string, number>;
  style_url_count: Record<string, number>;
  extended_data_keys: string[];
  /** Phase 1B — top 10 folder paths by feature count, sorted desc by count
   *  then asc by name. */
  top_folders?: Array<{ folder_path_str: string; count: number }>;
  /** Phase 1B — top 10 styleUrls by feature count, same sort order. */
  top_style_urls?: Array<{ style_url: string; count: number }>;
  /** Phase 1B — bounded sample feature_ids per classification (max 5
   *  per category). Look up details in `features[]` by feature_id. */
  classification_samples?: Partial<Record<SemanticKmzClassification, string[]>>;
  /** Phase 1B — distinct source filenames present in this semantic
   *  ingestion (currently always one entry, but plumbed for future
   *  multi-KMZ ingestion). */
  source_filenames?: string[];
  /** Phase 1B — caps used by the parser, surfaced for diagnostics UX. */
  feature_cap?: number;
  sample_cap?: number;
  /** Phase A/B/C — counts of features for which deterministic extractions
   *  produced a non-null value. Read by the diagnostics panel. */
  features_with_chainage?: number;
  features_with_sequence?: number;
  features_with_full_geometry?: number;
  features_with_resolved_style?: number;
  /** Phase C — number of <Style id="…"> blocks (after StyleMap resolution)
   *  parsed from the document. */
  styles_resolved_count?: number;
  /** Phase C — bucketed lifecycle counts. */
  by_lifecycle?: Record<string, number>;
  top_lifecycle?: Array<{ label: string; count: number }>;
  /** Phase C — top resolved <LineStyle><color> values across all features.
   *  Useful for spotting "this color = role X" conventions in real KMZs. */
  top_resolved_line_colors?: Array<{ color: string; count: number }>;
  /** Phase A/B/C — read-only candidate anchor catalog. The redline engine
   *  MAY consume this in a future phase; today it is purely diagnostic. */
  anchor_catalog?: Array<{
    feature_id: string;
    classification: SemanticKmzClassification;
    sequence_number?: number | null;
    sequence_kind?: string | null;
    chainage_ft?: number | null;
    coord: [number, number];
    confidence: SemanticKmzConfidence;
    folder_path_str: string;
    lifecycle?: string | null;
  }>;
  anchor_catalog_truncated?: boolean;
  anchor_cap?: number;
  /** Skipped-placemark observability (additive). 0 when every placemark
   *  parsed successfully. Present from parser_version "semantic-1" onward. */
  skipped_placemark_count?: number;
  skipped_placemark_samples?: Array<{
    placemark_index_in_doc: number;
    error_kind: string;
    message: string;
  }>;
  /** Style resolution health — additive diagnostic. Never affects matching or
   *  rendering. Counts derived from the KML document's Style/StyleMap elements
   *  and the placemark-referenced styleUrls. */
  style_resolution?: {
    ids_declared: number;
    ids_referenced: number;
    ids_referenced_unresolved: number;
    stylemap_count: number;
    stylemap_unresolved_count: number;
    /** Always 0 in semantic-1; cycle detection not yet tracked per-run. */
    stylemap_cycle_count: number;
  };
  /** Unresolved styleUrl strings referenced by placemarks, capped at 25. */
  missing_style_urls?: string[];
};

export type SemanticKmz = {
  parser_version: string;
  features: SemanticKmzFeature[];
  index: SemanticKmzIndex;
  /** Additive warning strings emitted during ingestion. Each entry corresponds
   *  to one skipped placemark: "placemark N (ErrorKind): message". Empty array
   *  when every placemark parsed successfully. Capped at 200. */
  warnings?: string[];
};

/**
 * Phase 1D — IngestionLedger.
 *
 * One row per KMZ semantic ingestion, persisted to ingestion_ledger.jsonl.
 * Exposed read-only via GET /api/observability/ingestion-ledger.
 * Never affects matching, scoring, or rendering.
 */
export type IngestionLedgerEntry = {
  ingested_at: string;
  filename: string;
  input_sha256: string;
  parser_version: string | null;
  feature_count: number;
  anchor_count: number;
  skipped_placemark_count: number;
  warnings_count: number;
  truncated: boolean;
  anchor_catalog_truncated: boolean;
  styles_resolved_count: number;
  ids_referenced_unresolved: number;
  stylemap_unresolved_count: number;
};

export type IngestionLedgerResponse = {
  entries: IngestionLedgerEntry[];
};

/**
 * Phase 1H-A — match-shadow-1 compare row.
 *
 * One row per group_match per matching pass, persisted to
 * match_shadow_compare.jsonl.  Exposed read-only via
 * GET /api/observability/match-shadow-compare.
 * Never affects matching, scoring, or rendering.
 */
export type MatchShadowCompareEntry = {
  schema_version: string;
  decided_at: string;
  match_pass_id: string;
  session_id_hint: string | null;
  input_sha256: string | null;
  shadow_version: string | null;
  had_shadow_payload: boolean;
  group_id: string | null;
  group_index: number;
  operational_winner_route_id: string | null;
  operational_winner_route_name: string | null;
  operational_confidence: number | null;
  semantic_winner_route_id: string | null;
  semantic_winner_route_name: string | null;
  semantic_winner_score: number | null;
  /** true = shadow agrees; false = shadow disagrees (review warranted);
   *  null = no anchor contributed or shadow unavailable. */
  agreement: boolean | null;
  anchors_near_operational_winner: number;
  anchors_near_semantic_winner: number;
  contributing_anchor_ids: string[];
  shadow_explanation: string | null;
};

export type MatchShadowCompareResponse = {
  entries: MatchShadowCompareEntry[];
};

/**
 * Phase 1H-B-I — match-shadow-summary-1 analytics response.
 *
 * Computed on-the-fly from match_shadow_compare.jsonl rows.
 * Exposed read-only via GET /api/observability/match-shadow-summary.
 * Metrics are PROVISIONAL — see stability_note in the response.
 */
export type MatchShadowSummaryWindow = {
  rows_read: number;
  match_pass_count: number;
  unique_input_sha256_count: number;
  earliest_decided_at: string | null;
  latest_decided_at: string | null;
};

export type MatchShadowSummaryShadowAvailability = {
  sample_size: number;
  rows_with_shadow_payload: number;
  shadow_availability_rate: number | null;
};

export type MatchShadowSummaryAgreement = {
  sample_size: number;
  agree_count: number;
  disagree_count: number;
  inconclusive_count: number;
  agree_rate: number | null;
  disagree_rate: number | null;
  inconclusive_rate: number | null;
};

export type MatchShadowSummaryAnchorParticipation = {
  sample_size: number;
  groups_with_anchors_near_op: number;
  groups_with_anchors_near_sem: number;
  rate_anchors_near_op: number | null;
  rate_anchors_near_sem: number | null;
  avg_anchors_near_op: number | null;
  avg_anchors_near_sem: number | null;
};

export type MatchShadowSummaryTopDisagreementPass = {
  match_pass_id: string;
  decided_at: string | null;
  input_sha256: string | null;
  disagree_count: number;
  group_count: number;
};

export type MatchShadowSummaryBySha = {
  input_sha256: string;
  rows_in_window: number;
  shadow_availability_rate: number | null;
  agree_rate: number | null;
  disagree_rate: number | null;
  inconclusive_rate: number | null;
  rate_anchors_near_op: number | null;
  rate_anchors_near_sem: number | null;
  sample_size: number;
};

export type MatchShadowSummaryResponse = {
  schema_version: string;
  computed_at: string;
  window: MatchShadowSummaryWindow;
  shadow_availability: MatchShadowSummaryShadowAvailability;
  agreement: MatchShadowSummaryAgreement;
  anchor_participation: MatchShadowSummaryAnchorParticipation;
  top_disagreement_passes: MatchShadowSummaryTopDisagreementPass[];
  by_input_sha256: MatchShadowSummaryBySha[];
  guards: {
    min_samples_for_rate: number;
    min_samples_for_rate_per_sha: number;
    rate_below_threshold_returns_null: boolean;
  };
  stability_note: string;
};

/**
 * Phase 1I-A — match-shadow-disagreements-1 drilldown types.
 *
 * Computed on-the-fly from match_shadow_compare.jsonl disagreement rows.
 * Exposed read-only via GET /api/observability/match-shadow-disagreements.
 * Labels describe evidence strength only — not correctness of any route selection.
 * Never affects matching, scoring, or rendering.
 */
export type MatchShadowDisagreementEntry = {
  decided_at: string | null;
  match_pass_id: string | null;
  input_sha256: string | null;
  group_id: string | null;
  operational_winner_route_id: string | null;
  operational_winner_route_name: string | null;
  semantic_winner_route_id: string | null;
  semantic_winner_route_name: string | null;
  anchors_near_operational_winner: number;
  anchors_near_semantic_winner: number;
  contributing_anchor_count: number;
  shadow_explanation: string | null;
  /** Multi-label set: e.g. ["DOMINANT_SHADOW_SUPPORT", "THIN_EVIDENCE"] */
  disagreement_kind: string[];
  /** "elevated" | "standard" | "low" — evidence strength only, not correctness */
  review_priority: "elevated" | "standard" | "low";
  review_priority_reasons: string[];
};

export type MatchShadowDisagreementTaxonomy = {
  totals_by_priority: {
    elevated: number;
    standard: number;
    low: number;
  };
  totals_by_kind: Record<string, number>;
  approved_labels: string[];
};

export type MatchShadowDisagreementWindow = {
  rows_read: number;
  match_pass_count: number;
  unique_input_sha256_count: number;
  earliest_decided_at: string | null;
  latest_decided_at: string | null;
};

export type MatchShadowDisagreementResponse = {
  schema_version: string;
  computed_at: string;
  window: MatchShadowDisagreementWindow;
  filters: { min_review_priority: string };
  taxonomy: MatchShadowDisagreementTaxonomy;
  entries: MatchShadowDisagreementEntry[];
  guards: { min_review_priority_default: string };
  stability_note: string;
};

/**
 * Phase 1K — Review Label telemetry types.
 *
 * Observability-only.  Labels are append-only human-review telemetry.
 * They NEVER influence matching, scoring, rendering, or any operational
 * system.  See backend/LABEL_USAGE_POLICY.md.
 */
export type ReviewLabelValue = "useful_catch" | "noise" | "unclear" | "cleared";

export type ReviewLabelEvent = {
  schema_version: "review-label-1";
  labeled_at: string;
  match_pass_id: string | null;
  group_id: string | null;
  input_sha256: string | null;
  label: ReviewLabelValue;
  previous_label: string | null;
  reviewer_hint: string | null;
  note: string | null;
  tombstone: boolean;
};

export type ReviewLabelResolved = {
  group_id: string | null;
  label: ReviewLabelValue | null;
  labeled_at: string | null;
  reviewer_hint: string | null;
  note: string | null;
};

export type ReviewLabelResponse = {
  events: ReviewLabelEvent[];
};

export type ReviewLabelCurrentResponse = {
  resolved: ReviewLabelResolved[];
};

/**
 * Phase 1L — Review label analytics summary types.
 *
 * Compute-on-read.  No writes, no operational influence.
 * All metrics are review telemetry patterns only.
 */
export type ReviewLabelSummaryRateEntry = {
  labeled: number;
  useful_catch: number;
  rate: number | null;
};

export type ReviewLabelSummaryCoverageEntry = {
  total_disagreements: number;
  labeled: number;
  coverage_rate: number | null;
};

export type ReviewLabelSummaryKindRow = {
  kind: string;
  labeled: number;
  useful_catch: number;
  rate: number | null;
};

export type ReviewLabelSummaryNoiseRow = {
  input_sha256: string;
  total_labeled: number;
  noise: number;
  noise_rate: number | null;
};

export type ReviewLabelSummaryResponse = {
  schema_version: string;
  generated_at: string;
  window: {
    label_events_read: number;
    shadow_rows_read: number;
    resolved_labels: number;
    disagreements_in_window: number;
  };
  total_review_labels: number;
  resolved_label_counts: {
    useful_catch: number;
    noise: number;
    unclear: number;
  };
  useful_catch_rate_by_review_priority: {
    elevated: ReviewLabelSummaryRateEntry;
    standard: ReviewLabelSummaryRateEntry;
    low: ReviewLabelSummaryRateEntry;
  };
  useful_catch_rate_by_disagreement_kind: ReviewLabelSummaryKindRow[];
  label_coverage_by_review_priority: {
    elevated: ReviewLabelSummaryCoverageEntry;
    standard: ReviewLabelSummaryCoverageEntry;
    low: ReviewLabelSummaryCoverageEntry;
  };
  top_input_sha256_by_noise_rate: ReviewLabelSummaryNoiseRow[];
  stability_note: string;
};

/**
 * Phase 1P — Redline Topology Continuity Advisor types.
 *
 * Advisory only. Groups existing redline segments by MultiGeometry engineering
 * object identity from the KMZ topology sidecar.  Read-only, post-redline,
 * operationally inert.  No matcher/scorer/billing/closeout influence.
 */
export type RedlineTopologyContinuityEvidence = {
  shared_group_id: string;
  fragment_count: number;
};

export type RedlineTopologyContinuityGroup = {
  engineering_object_id: string;
  signal: string;
  source_segment_ids: string[];
  evidence: RedlineTopologyContinuityEvidence;
};

export type RedlineTopologyContinuityResponse = {
  schema_version: string;
  generated_at?: string;
  groups: RedlineTopologyContinuityGroup[];
  ungrouped_segment_ids: string[];
  stability_note: string;
};

/**
 * Phase 1W — Reviewed Snapped Geometry Preview Layer types.
 *
 * Diagnostic-only advisory preview geometry. Clones operational redline
 * segments with ONLY approved endpoint coordinates substituted.
 * Never rendered into the operational map.
 */
export type ReviewedSnapSubstitution = {
  approved_event_id: string;
  recommendation_key: {
    segment_id: string;
    endpoint: "start" | "end";
  };
  original_coordinate: [number, number];
  substituted_coordinate: [number, number];
  candidate_anchor_id: string;
};

export type ReviewedSnapPreviewRecord = {
  preview_id: string;
  source_segment_id: string;
  preview_geometry: {
    type: "LineString";
    coordinates: [number, number][];
  };
  endpoint_substitutions: {
    start: ReviewedSnapSubstitution | null;
    end: ReviewedSnapSubstitution | null;
  };
  operational_segment_checksum: string;
  presentation_role: "preview_polyline";
};

export type ReviewedSnapPreviewSummary = {
  total_previews: number;
  previews_with_start_only: number;
  previews_with_end_only: number;
  previews_with_both: number;
  stale_previews: number;
};

export type ReviewedSnapPreviewResponse = {
  schema_version: string;
  generated_at: string;
  previews: ReviewedSnapPreviewRecord[];
  summary: ReviewedSnapPreviewSummary;
  stability_note: string;
};

/**
 * Phase 1V — Endpoint-Only Snap Preview Marker types.
 *
 * Diagnostic-only review aids derived from existing endpoint snap
 * recommendations and operator review events. No new geometry.
 * Never rendered into the operational map.
 */
export type SnapPreviewMarker = {
  marker_id: string;
  segment_id: string;
  endpoint: "start" | "end";
  current_coordinate: [number, number];
  candidate_coordinate: [number, number];
  candidate_anchor_id: string;
  candidate_anchor_name: string | null;
  snap_delta_ft: number;
  classification: "near" | "orphan";
  current_decision: "approved" | "rejected" | null;
  presentation_role: "ghost_marker";
};

export type SnapPreviewMarkersSummary = {
  total_markers: number;
  near_markers: number;
  orphan_markers: number;
  with_decision: number;
  without_decision: number;
};

export type SnapPreviewMarkersResponse = {
  schema_version: string;
  generated_at: string;
  markers: SnapPreviewMarker[];
  summary: SnapPreviewMarkersSummary;
  stability_note: string;
};

/**
 * Phase 1U — Operator-Approved Snap Review Event types.
 *
 * Advisory only. Append-only operator review decisions on Phase 1T
 * snap recommendations. Never influence geometry, matching, billing,
 * closeout, or any operational system.
 */
export type SnapReviewDecision = "approved" | "rejected" | "revoked";

export type SnapReviewKey = {
  segment_id: string;
  endpoint: "start" | "end";
};

export type SnapReviewSnapshot = {
  route_id: string | null;
  current_coordinate: [number, number];
  current_distance_ft: number;
  candidate_anchor_id: string;
  candidate_anchor_name: string | null;
  candidate_coordinate: [number, number];
  snap_delta_ft: number;
  classification: "near" | "orphan";
};

export type SnapReviewEventRecord = {
  schema_version: string;
  event_id: string;
  created_at: string;
  recommendation_key: SnapReviewKey;
  recommendation_snapshot: SnapReviewSnapshot;
  input_sha256: string;
  decision: SnapReviewDecision;
  operator_id: string;
  session_id: string | null;
};

export type SnapReviewEventsSummary = {
  total_events: number;
  approved_count: number;
  rejected_count: number;
  revoked_count: number;
  reviewed_recommendation_count: number;
  unreviewed_recommendation_count: number;
};

export type SnapReviewEventsResponse = {
  events: SnapReviewEventRecord[];
  summary: SnapReviewEventsSummary;
};

export type SnapReviewCurrentResponse = {
  current: SnapReviewEventRecord | null;
};

/**
 * Phase 1T — Deterministic Endpoint Snap Recommendation types.
 *
 * Advisory only. For each near/orphan redline endpoint, provides the
 * candidate anchor coordinate from the Phase 1S validator.
 * No new geometry. snap_delta_ft == current_distance_ft by construction.
 * Read-only, post-validator, operationally inert.
 * No geometry / matcher / scorer / billing / closeout influence.
 */
export type SnapRecommendation = {
  segment_id: string;
  route_id: string | null;
  endpoint: "start" | "end";
  current_coordinate: [number, number];
  current_distance_ft: number;
  candidate_anchor_id: string;
  candidate_anchor_name: string | null;
  candidate_coordinate: [number, number];
  snap_delta_ft: number;
  classification: "near" | "orphan";
};

export type SnapRecommendationSummary = {
  total_recommendations: number;
  near_recommendations: number;
  orphan_recommendations: number;
};

export type EndpointSnapRecommendationsResponse = {
  schema_version: string;
  tolerance_ft: number;
  near_band_ft: number;
  generated_at?: string;
  recommendations: SnapRecommendation[];
  summary: SnapRecommendationSummary;
  stability_note: string;
};

/**
 * Phase 1S — Bore-log Redline Endpoint Validator types.
 *
 * Advisory only. Classifies each redline segment endpoint as
 * anchored / near / orphan / no_anchors_in_kmz.
 * Read-only, post-redline, operationally inert.
 * No geometry / matcher / scorer / billing / closeout influence.
 */
export type EndpointClassification =
  | "anchored"
  | "near"
  | "orphan"
  | "no_anchors_in_kmz";

export type RedlineEndpointRecord = {
  segment_id: string;
  route_id: string | null;
  endpoint: "start" | "end";
  coordinate: [number, number];
  nearest_anchor_id: string | null;
  nearest_anchor_name: string | null;
  distance_ft: number | null;
  classification: EndpointClassification;
};

export type RedlineEndpointByRoute = {
  anchored: number;
  near: number;
  orphan: number;
  no_anchors_in_kmz: number;
};

export type RedlineEndpointSummary = {
  total_endpoints: number;
  anchored_count: number;
  near_count: number;
  orphan_count: number;
  no_anchors_in_kmz_count: number;
  anchored_pct: number | null;
  by_route: Record<string, RedlineEndpointByRoute>;
  flagged_segments: string[];
};

export type RedlineEndpointValidationResponse = {
  schema_version: string;
  tolerance_ft: number;
  near_band_ft: number;
  generated_at?: string;
  endpoints: RedlineEndpointRecord[];
  summary: RedlineEndpointSummary;
  stability_note: string;
};

/**
 * Phase 1Q — Node-anchored Redline Continuity Advisor types.
 *
 * Advisory only. Groups existing redline segments by endpoint coincidence
 * with KMZ point features (handholes/nodes) within a fixed tolerance.
 * Read-only, post-redline, operationally inert.
 * No matcher/scorer/billing/closeout influence.
 */
export type RedlineNodeContinuityEvidenceItem = {
  segment_id: string;
  endpoint: "start" | "end";
  distance_ft: number;
};

export type RedlineNodeContinuityGroup = {
  anchor_reference_feature_id: string;
  anchor_folder_path: string | string[] | null;
  anchor_name: string;
  anchor_coordinate: [number, number];
  source_segment_ids: string[];
  engineering_object_ids: string[];
  endpoint_count: number;
  evidence: RedlineNodeContinuityEvidenceItem[];
};

export type RedlineNodeContinuityStats = {
  anchor_points_considered: number;
  anchor_points_with_groups: number;
  redline_segments_total: number;
  redline_segments_anchored: number;
  redline_segments_unanchored: number;
};

export type RedlineNodeContinuityResponse = {
  schema_version: string;
  tolerance_ft: number;
  generated_at?: string;
  groups: RedlineNodeContinuityGroup[];
  ungrouped_segment_ids: string[];
  stats: RedlineNodeContinuityStats;
  stability_note: string;
};

/**
 * Phase 1M — KMZ Engineering Fidelity Audit types.
 *
 * Compute-on-read.  Compares semantic ingest vs render ingest field coverage.
 * No writes, no operational influence.  Fidelity diagnostics only.
 */
export type KmzFidelityAuditWindow = {
  semantic_feature_count: number;
  reference_line_count: number;
  reference_polygon_count: number;
  reference_point_count: number;
  has_semantic_ingest: boolean;
  has_reference_ingest: boolean;
};

export type KmzFidelityStyleSection = {
  unique_style_urls_in_semantic: number;
  features_with_resolved_style_props: number;
  features_with_kml_line_color: number;
  features_with_kml_poly_fill: number;
  features_with_icon_href: number;
  reference_feature_has_style_url: false;
  style_url_preservation_rate: number | null;
};

export type KmzFidelityFolderSection = {
  max_folder_depth: number;
  avg_folder_depth: number | null;
  features_with_multi_level_path: number;
  features_with_single_level_path: number;
  reference_folder_is_flat_string: true;
  hierarchy_preservation_rate: number | null;
};

export type KmzFidelityExtendedDataSection = {
  unique_key_count: number;
  total_value_count: number;
  reference_has_extended_data_field: false;
  top_keys: Array<{ key: string; count: number }>;
  preservation_rate: number | null;
};

export type KmzFidelityGeometrySection = {
  multigeometry_placemark_count: number;
  multigeometry_child_count: number;
  reference_preserves_parent_placemark_identity: false;
  exploded_into_flat_geometries: true;
};

export type KmzFidelityRenderSimplificationSection = {
  semantic_field_count: number;
  reference_line_field_count: number;
  fields_in_semantic_not_in_reference: string[];
  dropped_field_count: number;
};

export type KmzFidelityAuditResponse = {
  schema_version: string;
  generated_at: string;
  window: KmzFidelityAuditWindow;
  style_fidelity: KmzFidelityStyleSection;
  folder_fidelity: KmzFidelityFolderSection;
  extended_data_fidelity: KmzFidelityExtendedDataSection;
  geometry_fidelity: KmzFidelityGeometrySection;
  render_simplification: KmzFidelityRenderSimplificationSection;
  stability_note: string;
};

/**
 * Phase 1C — SHADOW MODE matching diagnostics.
 *
 * Purely informational. The matching engine continues to ignore this; the
 * diagnostics panel surfaces it so engineers can audit whether the anchor
 * catalog would agree with current route selection. Never affects
 * operational behavior.
 */
export type SemanticMatchShadowGroup = {
  group_id: string;
  group_index: number;
  existing_selected_route_id: string;
  existing_selected_route_name: string;
  existing_score: number;
  semantic_best_route_id: string | null;
  semantic_best_route_name: string | null;
  semantic_best_score: number;
  /** true when semantic best == existing selected; false on disagreement;
   *  null when no anchors contributed (no signal). */
  agreement: boolean | null;
  anchors_near_selected_route: number;
  anchors_near_semantic_best_route: number;
  contributing_anchor_ids: string[];
  explanation: string;
  ranked_routes: Array<{
    route_id: string;
    route_name: string;
    anchor_count: number;
    semantic_score: number;
  }>;
};

export type SemanticMatchShadow = {
  version: string;
  summary: {
    groups_total: number;
    groups_in_agreement: number;
    groups_in_disagreement: number;
    groups_with_no_anchors: number;
    anchors_considered: number;
    weights: {
      confidence: Record<string, number>;
      classification: Record<string, number>;
      proximity_near_ft: number;
      proximity_far_ft: number;
    };
  };
  groups: SemanticMatchShadowGroup[];
};

export type BackendState = {
  success?: boolean;
  session_id?: string;
  message?: string;
  warning?: string;
  error?: string;
  route_name?: string | null;
  selected_route_name?: string | null;
  selected_route_match?: GroupMatch | null;
  route_coords?: number[][];
  loaded_field_data_files?: number;
  latest_structured_file?: string | null;
  redline_segments?: RedlineSegment[];
  station_points?: StationPoint[];
  active_route_redline_segments?: RedlineSegment[];
  active_route_station_points?: StationPoint[];
  verification_summary?: {
    status?: string;
    route_selection_reason?: string;
  };
  total_length_ft?: number;
  covered_length_ft?: number;
  completion_pct?: number;
  active_route_covered_length_ft?: number;
  active_route_completion_pct?: number;
  active_route_station_points_count?: number;
  active_route_redline_segments_count?: number;
  committed_rows?: Array<Record<string, unknown>>;
  bug_report_count?: number;
  suggested_route_id?: string | null;
  station_mapping_mode?: string | null;
  kmz_reference?: {
    line_features?: KmzLineFeature[];
    polygon_features?: KmzPolygonFeature[];
  };
  /** Phase 1A — additive semantic layer. null/absent until a KMZ is uploaded
   *  or when the additive parse failed; consumers must treat absence as
   *  "no semantic data available" and continue using kmz_reference for
   *  rendering. */
  kmz_semantic?: SemanticKmz | null;
  /** Phase 1C — shadow-mode matching diagnostics. Read-only, additive.
   *  null when prerequisites (anchor catalog, route_match_candidates) are
   *  missing. Never affects operational behavior. */
  kmz_semantic_match_shadow?: SemanticMatchShadow | null;
  engineering_plans?: EngineeringPlan[];
  bore_log_summary?: BoreLogSummaryEntry[];
  photo_points?: GlobalPhotoPoint[];
  closeout_locked?: boolean;
  closeout_locked_by?: string | null;
  closeout_locked_at?: string | null;
  /** When is_locked, mutating endpoints return 403 Closeout is locked */
  closeout_lock?: {
    is_locked?: boolean;
    locked_by?: string | null;
    locked_at?: string | null;
  };
};

export type GlobalPhotoPoint = {
  id: string;
  source_type: string;
  lat: number;
  lon: number;
  original_lat?: number;
  original_lon?: number;
  adjusted_lat?: number | null;
  adjusted_lon?: number | null;
  adjusted_at?: string | null;
  is_adjusted?: boolean;
  thumbnail_url: string | null;
  original_url: string | null;
  filename: string;
  station_label: string;
  session_id: string;
  uploaded_at: string;
  note?: string | null;
};

export type StationPhoto = {
  photo_id: string;
  session_id?: string;
  station_identity: string;
  station_summary: string;
  original_filename: string;
  stored_filename: string;
  content_type?: string;
  uploaded_at: string;
  relative_url: string;
  public_url?: string;
  original_lat?: number | null;
  original_lon?: number | null;
  adjusted_lat?: number | null;
  adjusted_lon?: number | null;
  adjusted_at?: string | null;
  is_adjusted?: boolean;
};

export type ExceptionCost = {
  id: string;
  label: string;
  amount: string;
  note?: string;
  station?: string;
  billing_relevant?: boolean;
};

export type NoteTone = "neutral" | "success" | "warning" | "error";

export type Bounds = {
  minLat: number;
  maxLat: number;
  minLon: number;
  maxLon: number;
};

export type ScreenPoint = { x: number; y: number };

export type Viewport = {
  zoom: number;
  panX: number;
  panY: number;
};

// ---------------------------------------------------------------------------
// Phase 2A — KMZ Engineering Render Payload types
// Schema version: "kmz-render-payload-1"
// ---------------------------------------------------------------------------

/** Phase 2B — shared Tier-1 metadata fields on every KMZ render record. */
export type KmzRenderMeta = {
  description: string;
  /** Phase 2I: original KML <description> HTML, capped 4096 chars. Empty string when absent. */
  description_raw: string;
  extended_data: Record<string, string>;
  chainage_ft: number | null;
  sequence_number: string | null;
  sequence_kind: string | null;
  lifecycle: { label: string; confidence: string; reason: string } | null;
  /** Phase 2I: placemark's <styleUrl> value, empty string when absent. */
  style_url: string;
  /** Phase 2I: icon href from resolved KML IconStyle, empty string when absent. */
  icon_href: string;
};

export type KmzRenderPoint = KmzRenderMeta & {
  feature_id: string;
  /** [lat, lon] */
  coord: [number, number];
  classification: string;
  name: string;
  icon_glyph: "circle" | "square" | "diamond" | "ring";
  color: string;
  folder_path: string[];
};

export type KmzRenderLine = KmzRenderMeta & {
  feature_id: string;
  /** [[lat, lon], ...] — max 200 vertices */
  coords: [number, number][];
  classification: string;
  name: string;
  color: string;
  width: number;
  dash: boolean;
  folder_path: string[];
};

export type KmzRenderPolygon = KmzRenderMeta & {
  feature_id: string;
  /** [[lat, lon], ...] outer ring */
  outer: [number, number][];
  /** inner rings for donut-hole rendering */
  inner: [number, number][][];
  classification: string;
  name: string;
  fill_color: string;
  folder_path: string[];
};

export type KmzRenderCategory = {
  classification: string;
  point_count: number;
  line_count: number;
  polygon_count: number;
  total: number;
};

export type KmzRenderSummary = {
  total_points: number;
  total_lines: number;
  total_polygons: number;
  points_truncated: boolean;
  lines_truncated: boolean;
  polygons_truncated: boolean;
  source_feature_count: number;
};

export type KmzRenderPayloadResponse = {
  schema_version: string;
  generated_at: string;
  render_caps: {
    max_points: number;
    max_lines: number;
    max_polygons: number;
    max_vertices_per_line: number;
  };
  points: KmzRenderPoint[];
  lines: KmzRenderLine[];
  polygons: KmzRenderPolygon[];
  categories: KmzRenderCategory[];
  summary: KmzRenderSummary;
};
