r"""OWNER-PACKET-2 -- exemplar -> pipeline SEAM scout (PROOF/SCOUT ONLY; no product, no render).

Three v2 exemplars now have full source-bind + render proof coverage:
  log53 -- hard TWO-sheet MATCHLINE-ENDPOINT run (NEXTLINK HH -> 24+11 matchline -> 26+38 FLOWER POT);
  log64 -- clean SINGLE-sheet STRUCTURE-to-STRUCTURE run (INSTALLER HH 3+69 -> 1+00 FLOWER POT);
  log71 -- TWO-sheet STRUCTURE-to-STRUCTURE run with an INTERMEDIATE 5+45 matchline as ROUTE CONTEXT
           and a BENDING ordered source route on sheet 24.

This scout determines the SMALLEST reusable seam that could consume the proven exemplar patterns and
produce a generalized, render-ready payload for ELIGIBLE logs -- WITHOUT wiring anything into
product/runtime, without a broad renderer, without cross-sheet frame solving, without a
representative-route resolver, and without parent/child aggregation. It is a comparison + contract
proposal + honest eligibility classification over COMMITTED data (the owner-reviewed adjudication +
the proven exemplar topology). It parses NO PDF, draws NO stroke, writes NO PNG, and invents NO
coordinate -- the normalized payload is deliberately COORDINATE-FREE (it carries identity, boundary
semantics, route MODE and source-evidence DESCRIPTORS; the deterministic engine still computes every
position downstream, exactly as the exemplars proved).

It optionally CORROBORATES (read-only) against the exemplars' gitignored proof-output JSONs when
present (e.g. log71's bend), but never depends on them for PASS -- only a real contradiction fails.

Proof/scout-only; the JSON report is written under the gitignored data/outputs path.
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_exemplar_pipeline_seam_scout
"""
from __future__ import annotations

import json

from truelinev2.config import _REPO_ROOT
from truelinev2.ingest.manual_adjudication import (
    activation_summary,
    apply_adjudications,
    load_adjudication,
    parent_run_duplicate_check,
)

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "exemplar_pipeline_seam_scout"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")

EXEMPLARS = ("log53", "log64", "log71")
RENDER_MODES = {"continuous_corridor", "ordered_chain_path"}

# Proven exemplar topology -- the parts NOT carried by endpoint_anchors: per-leg (sheet, render_mode)
# and the matchline split station. Boundary KINDS (structure_terminus vs matchline_continuation) are
# READ from the committed endpoint_anchors, so the matchline-endpoint-vs-route-context distinction is
# never hardcoded here. render_mode is what each committed source-bind + render proof established:
# log71 sheet 24's direct corridor bends (direct_corridor_continuous == False) -> ordered_chain_path;
# every other proven leg is a continuous corridor.
EXEMPLAR_TOPOLOGY = {
    "log64": {"shape": "single_sheet_structure_to_structure", "sheets": [21],
              "legs": [(21, ("anchor", "start"), ("anchor", "end"), "continuous_corridor")]},
    "log53": {"shape": "two_sheet_matchline_endpoint", "sheets": [5, 6],
              "legs": [(5, ("anchor", "start"), ("matchline", "24+11"), "continuous_corridor"),
                       (6, ("matchline", "24+11"), ("continuation", "26+38"), "continuous_corridor")]},
    "log71": {"shape": "two_sheet_structure_to_structure_route_context", "sheets": [24, 23],
              "legs": [(24, ("anchor", "start"), ("matchline", "5+45"), "ordered_chain_path"),
                       (23, ("matchline", "5+45"), ("anchor", "end"), "continuous_corridor")]},
}

SHARED_PRIMITIVES = {
    "endpoint_identity": ("endpoint_anchors schema-2 (start/end termini; boundary_kind, "
                          "structure_class, structure_label, station, owner_note_text, clarity); "
                          "validate_endpoint_anchors"),
    "source_bind": ("resolve_structure_position (label box -> leader -> modeled symbol) + "
                    "resolve_nextlink_hh_callout (ANNOTATION callout locator); symbol_footprint + "
                    "connected_chain + dash_endpoints; POSITION_BOUND"),
    "route_context_matchline": ("matchline_bboxes + nearest_gap + extend_dash_to_boundary + "
                                "locate_matchline_boundary (chain-reach disambiguation, distinct-bbox "
                                "keyed)"),
    "ordered_route": ("two proven builders: order_route (vertical spine-hugging corridor) for "
                      "continuous legs; order_chain_route (shortest path over the bound conduit chain) "
                      "for bending legs"),
    "render_ready_payload": ("render_redline_stroke (red REVIEW dashed stroke, per sheet) + "
                             "REDLINE_STROKE_RGB; one sheet-local PNG per leg"),
    "invariant_guard": ("apply_adjudications + activation_summary + parent_run_duplicate_check "
                        "(engine census frozen)"),
}
EXEMPLAR_SPECIFIC = {
    "log53": "matchline-as-ENDPOINT (boundary_kind matchline_continuation); reverse chain trace; the 24+11 boundary typeset on both sheets",
    "log64": "single-sheet 100' DIRECT-BORE callout grammar (_SEG_RE / _FOOTAGE_RE)",
    "log71": "BENDING chain-path route (order_chain_route); owner-confirmed NEXTLINK start identity; per-sheet 5+45 chain-reach dedup",
    "deferred_for_all": ("cross-sheet FRAME solving (legs stay sheet-local; the two matchline points "
                         "are never reconciled); representative-route resolution; parent/child run "
                         "aggregation; broad batch rendering"),
}

# coordinate-style keys the normalized seam payload must NEVER carry (it is identity/contract only).
_COORD_KEYS = {"x", "y", "z", "xc", "yc", "x0", "y0", "x1", "y1", "xy", "cx", "cy",
               "lat", "lon", "lng", "coord", "coords", "coordinate", "coordinates", "px", "py",
               "point", "points", "symbol_xy", "anchor_xy", "stroke", "stroke_points", "geometry",
               "geom", "symbol_x", "symbol_y", "vertices", "route_vertices"}

R_PASS = "EXEMPLAR_PIPELINE_SEAM_SCOUT_PASS"
B_PAYLOAD = "BLOCKED_SEAM_PAYLOAD_CANNOT_REPRESENT_EXEMPLAR"
B_INVARIANT = "BLOCKED_SEAM_INVARIANT_VIOLATED"
B_CLASSIFY = "BLOCKED_SEAM_CLASSIFICATION_DISHONEST"
B_CONTRADICTED = "BLOCKED_SEAM_CONTRADICTED_BY_PROOF_OUTPUT"
ALLOWED = {R_PASS, B_PAYLOAD, B_INVARIANT, B_CLASSIFY, B_CONTRADICTED}


def has_coord_keys(obj) -> bool:
    """True if any dict key anywhere in ``obj`` is a coordinate-style key (the seam payload is
    coordinate-free; positions are produced downstream by the deterministic engine)."""
    if isinstance(obj, dict):
        if {str(k).lower() for k in obj} & _COORD_KEYS:
            return True
        return any(has_coord_keys(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return any(has_coord_keys(v) for v in obj)
    return False


def _terminus_binder(structure_class):
    return ("nextlink_hh_callout_locator" if structure_class == "nextlink_hh"
            else "structure_position_label_leader_symbol" if structure_class
            else None)


def resolve_boundary(ref, anchors: dict) -> dict:
    """Resolve a topology leg-boundary ref into a COORDINATE-FREE descriptor. ``('anchor', which)``
    reads the committed endpoint anchor (kind = its boundary_kind); ``('matchline', sta)`` is a
    MODELED matchline endpoint IFF an anchor carries boundary_kind matchline_continuation at that
    station (log53), else ROUTE CONTEXT (log71's 5+45); ``('continuation', sta)`` is the far
    structure terminus named by an anchor's continues_as (re-derived at render). No coordinate."""
    kind_ref = ref[0]
    arg = ref[1] if len(ref) > 1 else None
    if kind_ref == "anchor":
        a = anchors.get(arg) or {}
        return {"role": arg, "boundary": a.get("boundary_kind"),
                "station": a.get("station"), "structure_class": a.get("structure_class"),
                "structure_label": a.get("structure_label"), "clarity": a.get("clarity"),
                "from_endpoint_anchor": True,
                "source_binder": _terminus_binder(a.get("structure_class"))}
    if kind_ref == "matchline":
        modeled = any((anchors.get(w) or {}).get("boundary_kind") == "matchline_continuation"
                      and (anchors.get(w) or {}).get("station") == arg for w in ("start", "end"))
        return {"role": "matchline", "station": arg,
                "boundary": "matchline_continuation" if modeled else "matchline_route_context",
                "structure_class": None, "structure_label": None,
                "modeled_endpoint": modeled, "from_endpoint_anchor": modeled,
                "source_binder": "locate_matchline_boundary_chain_reach"}
    # continuation terminus (named by endpoint_anchors.end.continues_as; class re-derived at render)
    return {"role": "continuation_terminus", "boundary": "structure_terminus", "station": arg,
            "structure_class": "flower_pot", "structure_label": "FLOWER POT",
            "from_endpoint_anchor": False,
            "source_binder": "structure_position_label_leader_symbol",
            "provenance": "endpoint_anchor.continues_as + render re-derivation"}


def normalize_exemplar(log_id: str, record: dict) -> dict:
    """Build the COORDINATE-FREE normalized seam payload for an exemplar from its committed
    endpoint_anchors + the proven topology. Represents single-sheet S2S, two-sheet matchline-endpoint,
    and two-sheet S2S + intermediate route context, with per-leg render MODE (continuous vs bending)."""
    topo = EXEMPLAR_TOPOLOGY[log_id]
    anchors = record.get("endpoint_anchors") or {}
    legs = []
    for sheet, sref, eref, mode in topo["legs"]:
        start_b = resolve_boundary(sref, anchors)
        end_b = resolve_boundary(eref, anchors)
        mls = [b for b in (start_b, end_b) if b.get("boundary") in
               ("matchline_continuation", "matchline_route_context")]
        route_context = None
        if mls:
            m = mls[0]
            route_context = {"matchline_station": m["station"],
                             "role": ("modeled_matchline_endpoint" if m["boundary"] == "matchline_continuation"
                                      else "between_leg_crossing_route_context")}
        legs.append({"sheet": sheet, "start_anchor": start_b, "end_anchor": end_b,
                     "route_context": route_context, "render_mode": mode,
                     "source_evidence": {"conduit": "base_conduit_chain (connected_chain)",
                                         "terminus_binders": sorted({b["source_binder"] for b in (start_b, end_b)
                                                                     if b.get("source_binder")})}})
    matchline_stations = sorted({leg["route_context"]["matchline_station"]
                                 for leg in legs if leg["route_context"]})
    return {
        "bore_id": log_id, "shape": topo["shape"], "review_status": record.get("status"),
        "eligible": True, "abstain_reason": None,
        "sheets": list(topo["sheets"]), "legs": legs,
        "matchline_stations": matchline_stations,
        "cross_sheet_join": ("deferred" if len(topo["sheets"]) > 1 else None),
        "cross_sheet_coordinate_reconciliation": False,
    }


def classify_record(record: dict):
    """Honest seam eligibility for one log. Eligible ONLY when endpoint_anchors are encoded AND the
    owner allows the draw (not abstain, not pending source verification). Returns (eligible, reason,
    categories). Never silently upgrades an uncertain log."""
    if record.get("must_remain_abstained"):
        return False, "owner-reviewed ABSTAIN_NO_SAFE_SOURCE", ["owner_abstain"]
    if record.get("needs_source_verification"):
        return False, "needs source verification before geometry", ["needs_source_verification"]
    if not record.get("endpoint_anchors"):
        ct = set(record.get("correction_types") or [])
        cats = ["no_endpoint_anchors_pending_owner_bridge"]
        if {"STATION_OCR_CORRECTION", "PRINT_OCR_CORRECTION"} & ct:
            cats.append("ocr_correction")
        if "ORIGINAL_PARENT_COLUMN_SPLIT" in ct:
            cats.append("ownership_adjudication")
        if record.get("shared_print_child"):
            cats.append("parent_child_aggregation")
        if len(record.get("corrected_sheets") or []) > 1 or "MATCHLINE_CHAIN" in ct:
            cats.append("cross_sheet_frame_solving")
        if record.get("needs_review"):
            cats.append("needs_review")
        return False, "endpoint_anchors not yet encoded (owner-reviewed bridge required)", cats
    return True, "endpoint_anchors encoded + source-bind/render proven", []


def _read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    except (OSError, ValueError):
        return None


def corroborate() -> dict:
    """Read-only cross-check against the exemplars' (gitignored) proof outputs when present. Confirms
    the seam's render-mode call against the source-bind's measured direct-corridor continuity and the
    render's bend ratio. Returns corroborated / outputs_absent / contradicted; only a real
    contradiction is a blocker (absent outputs are fine -- fresh clone / CI)."""
    notes, contradicted, seen = [], False, False
    sb = _read_json(OUT_DIR.parent / "log71_two_leg_source_bind_slice" / "log71_two_leg_source_bind_slice.json")
    if sb:
        seen = True
        legs = {l.get("sheet"): l for l in ((sb.get("source_bind_payload") or {}).get("legs") or [])}
        s24 = (legs.get(24, {}).get("corridor") or {}).get("direct_corridor_continuous")
        s23 = (legs.get(23, {}).get("corridor") or {}).get("direct_corridor_continuous")
        if s24 is not None and s24 is not False:
            contradicted = True
            notes.append(f"CONTRADICTION: log71 s24 direct_continuous={s24} but seam says ordered_chain_path (bend)")
        if s23 is not None and s23 is not True:
            contradicted = True
            notes.append(f"CONTRADICTION: log71 s23 direct_continuous={s23} but seam says continuous_corridor")
        notes.append(f"log71 source-bind: s24 direct_continuous={s24} (-> ordered_chain_path), s23={s23} (-> continuous_corridor)")
    else:
        notes.append("log71 source-bind output absent (gitignored) -- corroboration skipped")
    rd = _read_json(OUT_DIR.parent / "log71_render_artifact" / "log71_render_artifact.json")
    if rd:
        seen = True
        ratio = ((rd.get("legs") or {}).get("sheet_24_start") or {}).get("bend_ratio")
        if ratio is not None and ratio < 1.10:
            contradicted = True
            notes.append(f"CONTRADICTION: log71 render s24 bend_ratio={ratio} < 1.10 (not a bend)")
        else:
            notes.append(f"log71 render: s24 bend_ratio={ratio} (>= 1.10 confirms ordered_chain_path)")
    else:
        notes.append("log71 render output absent (gitignored) -- corroboration skipped")
    status = "contradicted" if contradicted else ("corroborated" if seen else "outputs_absent")
    return {"status": status, "notes": notes}


def _census_frozen(doc) -> bool:
    if not TRUTH.is_file():
        return False
    truth = json.loads(TRUTH.read_text(encoding="utf-8"))
    baseline = {r["bore_id"]: dict(r) for r in truth["rows"]}
    off_rows = apply_adjudications(baseline, enabled=False)
    on_rows = apply_adjudications(baseline, enabled=True, doc=doc)
    summ = activation_summary(on_rows)
    buckets = {}
    for r in off_rows.values():
        buckets[r["completion_bucket"]] = buckets.get(r["completion_bucket"], 0) + 1
    return (off_rows is baseline and buckets == FROZEN_BUCKETS
            and summ["manual_review_drawable"] == 22 and summ["manual_source_verification"] == 1
            and summ["manual_abstain"] == 4
            and on_rows["log44"]["adjudication"]["drawable_status"] == "non_drawable"
            and all(on_rows[l]["adjudication"]["drawable_status"] == "abstain" for l in ABSTAIN_4)
            and not parent_run_duplicate_check(doc))


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()

    doc = load_adjudication()
    rec = {r["log_id"]: r for r in doc["logs"]}
    gates = []

    gates.append(("G0 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                  _census_frozen(doc), None))
    l53s = (rec["log53"].get("endpoint_anchors") or {}).get("start") or {}
    l53e = (rec["log53"].get("endpoint_anchors") or {}).get("end") or {}
    l64s = (rec["log64"].get("endpoint_anchors") or {}).get("start") or {}
    l71s = (rec["log71"].get("endpoint_anchors") or {}).get("start") or {}
    gates.append(("G0b log53 + log64 + log71 encoded anchors unchanged (behavior preserved)",
                  l53s.get("structure_class") == "nextlink_hh"
                  and l53e.get("boundary_kind") == "matchline_continuation"
                  and l64s.get("structure_class") == "installer_hh"
                  and l71s.get("structure_class") == "nextlink_hh", None))

    # ---- normalize the three exemplars -----------------------------------------
    payloads = {lid: normalize_exemplar(lid, rec[lid]) for lid in EXEMPLARS}
    gates.append(("G1 all three exemplars normalize from endpoint_anchors (no product code, no PDF)",
                  all(rec[lid].get("endpoint_anchors") for lid in EXEMPLARS)
                  and all(payloads[lid]["legs"] for lid in EXEMPLARS), sorted(payloads)))

    shapes = {payloads[lid]["shape"] for lid in EXEMPLARS}
    leg_counts = {lid: len(payloads[lid]["legs"]) for lid in EXEMPLARS}
    gates.append(("G2 normalized payload represents all 3 exemplar shapes (1 / 2 / 2 legs; distinct shapes)",
                  len(shapes) == 3 and leg_counts == {"log64": 1, "log53": 2, "log71": 2}, leg_counts))

    coord_free = not any(has_coord_keys(p) for p in payloads.values())
    anchors_preserved = (
        payloads["log64"]["legs"][0]["start_anchor"]["structure_class"] == "installer_hh"
        and payloads["log64"]["legs"][0]["start_anchor"]["station"] == "3+69"
        and payloads["log64"]["legs"][0]["end_anchor"]["structure_class"] == "flower_pot"
        and payloads["log71"]["legs"][0]["start_anchor"]["structure_class"] == "nextlink_hh"
        and payloads["log71"]["legs"][-1]["end_anchor"]["structure_class"] == "flower_pot")
    gates.append(("G3 payload preserves endpoint anchors + invents NO coordinate (coordinate-free seam)",
                  coord_free and anchors_preserved, {"coord_free": coord_free}))

    # matchline: log53 MODELED endpoint (boundary_kind matchline_continuation); log71 ROUTE CONTEXT
    l53_ml = payloads["log53"]["legs"][0]["end_anchor"]
    l71_ml = payloads["log71"]["legs"][0]["end_anchor"]
    matchline_ok = (l53_ml["boundary"] == "matchline_continuation" and l53_ml["modeled_endpoint"] is True
                    and l71_ml["boundary"] == "matchline_route_context" and l71_ml["modeled_endpoint"] is False)
    gates.append(("G4 matchline = route context UNLESS modeled (log53 matchline-endpoint; log71 5+45 context)",
                  matchline_ok, {"log53": l53_ml["boundary"], "log71": l71_ml["boundary"]}))

    all_modes = {leg["render_mode"] for p in payloads.values() for leg in p["legs"]}
    bend_ok = (payloads["log71"]["legs"][0]["render_mode"] == "ordered_chain_path"
               and all_modes <= RENDER_MODES
               and not any("straight" in m or "diagonal" in m for m in all_modes))
    gates.append(("G5 bending route = ordered_chain_path (log71 s24); no straight-shortcut mode exists",
                  bend_ok, sorted(all_modes)))

    one_sheet_per_leg = all(isinstance(leg["sheet"], int)
                            for p in payloads.values() for leg in p["legs"])
    no_recon = all(p["cross_sheet_coordinate_reconciliation"] is False for p in payloads.values())
    multi_deferred = all(payloads[lid]["cross_sheet_join"] == "deferred" for lid in ("log53", "log71"))
    gates.append(("G6 no cross-sheet coordinate reconciliation (legs sheet-local; multi-sheet = deferred join)",
                  one_sheet_per_leg and no_recon and multi_deferred
                  and payloads["log64"]["cross_sheet_join"] is None, None))

    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G7 no render artifact generated (scout writes JSON only; zero PNG)", len(pngs) == 0, pngs))

    # ---- honest cohort eligibility classification ------------------------------
    eligible, blocked = {}, {}
    for r in doc["logs"]:
        ok, reason, cats = classify_record(r)
        (eligible if ok else blocked)[r["log_id"]] = {"reason": reason, "categories": cats}
    classified = len(eligible) + len(blocked)
    honest = (set(eligible) == set(EXEMPLARS)            # exactly the 3 anchor-encoded exemplars
              and classified == len(doc["logs"])         # every cohort log classified
              and not (set(eligible) & set(blocked))     # never both
              and all(blocked[l]["categories"] for l in blocked))  # every block has a named category
    gates.append(("G8 eligibility honest: eligible == 3 exemplars; abstains/needs-verify blocked; no silent upgrade",
                  honest, {"eligible": sorted(eligible), "blocked": len(blocked), "classified": classified}))

    corr = corroborate()
    gates.append(("G9 not contradicted by any present proof output (read-only corroboration; absent is OK)",
                  corr["status"] != "contradicted", corr["status"]))

    result = (R_PASS if all(x for _, x, _ in gates)
              else B_INVARIANT if not gates[0][1]
              else B_CONTRADICTED if corr["status"] == "contradicted"
              else B_CLASSIFY if not honest else B_PAYLOAD)
    return _emit(gates, result, payloads, eligible, blocked, corr)


def _emit(gates, result, payloads, eligible, blocked, corr) -> int:
    gates.append(("G10 result in allowed enum", result in ALLOWED, result))
    all_pass = all(x for _, x, _ in gates)
    # group blocked logs by PRIMARY category for the summary
    blocked_by_primary = {}
    for lid, info in blocked.items():
        primary = info["categories"][0] if info["categories"] else "unknown"
        blocked_by_primary.setdefault(primary, []).append(lid)
    report = {
        "milestone": "OWNER-PACKET-2 -- exemplar -> pipeline seam scout (proof/scout only; no product, no render)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result if all_pass else "BLOCKED",
        "exemplars_consumed": {lid: {"shape": payloads[lid]["shape"], "legs": len(payloads[lid]["legs"])}
                               for lid in EXEMPLARS},
        "shared_primitives": SHARED_PRIMITIVES,
        "exemplar_specific_not_generalized_yet": EXEMPLAR_SPECIFIC,
        "normalized_payload_proposal": {
            "fields": ["bore_id", "shape", "review_status", "eligible", "abstain_reason", "sheets",
                       "legs[ sheet, start_anchor, end_anchor, route_context, render_mode, source_evidence ]",
                       "matchline_stations", "cross_sheet_join", "cross_sheet_coordinate_reconciliation"],
            "leg_boundary_kinds": ["structure_terminus", "matchline_continuation (modeled endpoint)",
                                   "matchline_route_context (intermediate)"],
            "render_modes": sorted(RENDER_MODES),
            "coordinate_free": True,
            "note": ("identity + boundary + route MODE + source-evidence descriptors only; the "
                     "deterministic engine computes every position downstream (exactly as the "
                     "exemplars proved). No coordinate is carried; no cross-sheet frame is solved."),
        },
        "normalized_exemplar_payloads": payloads,
        "eligible_now": {lid: eligible[lid] for lid in sorted(eligible)},
        "not_eligible": {lid: blocked[lid] for lid in sorted(blocked)},
        "not_eligible_by_primary_category": {k: sorted(v) for k, v in sorted(blocked_by_primary.items())},
        "corroboration": corr,
        "invariants_preserved": {
            "engine_census": "frozen (OFF 31/6/1/17/3, ON 22/1/4, log44 non_drawable, 4 abstains held)",
            "log53_behavior": "unchanged (anchors intact; matchline-endpoint exemplar)",
            "log64_behavior": "unchanged (anchors intact; single-sheet S2S exemplar)",
            "log71_behavior": "unchanged (anchors intact; two-sheet S2S + route context + bend)",
            "no_generated_artifacts": "JSON report only under gitignored data/outputs; zero PNG/PDF",
        },
        "scope_guard": {"product_wiring": False, "broad_renderer": False, "cross_sheet_join": False,
                        "cross_sheet_frame_solving": False, "representative_route_resolver": False,
                        "parent_child_aggregation": False, "batch_placement_or_rendering": False,
                        "pdf_parsed": False, "coordinates_invented": False},
        "next_slice": ("if accepted, a CONTAINED seam module (pure, in truelinev2/) that builds this "
                       "coordinate-free payload from endpoint_anchors for the 3 eligible exemplars and "
                       "hands it to the EXISTING per-leg source-bind + render proofs -- still no product "
                       "wiring, no batch, no cross-sheet join; new logs become eligible only as their "
                       "owner-reviewed endpoint_anchors are encoded."),
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "exemplar_pipeline_seam_scout.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[seam-scout] result: {report['result']}")
    for lid in EXEMPLARS:
        print(f"[seam-scout]   {lid}: shape={payloads[lid]['shape']} legs={len(payloads[lid]['legs'])}")
    print(f"[seam-scout]   eligible_now: {sorted(eligible)}")
    print(f"[seam-scout]   blocked: {len(blocked)} by category {dict((k, len(v)) for k, v in sorted(blocked_by_primary.items()))}")
    print(f"[seam-scout]   corroboration: {corr['status']}")
    for n, x, _ in gates:
        print(f"[seam-scout] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[seam-scout] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
