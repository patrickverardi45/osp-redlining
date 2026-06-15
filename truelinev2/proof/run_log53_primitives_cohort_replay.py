r"""OWNER-PACKET-2 -- log53 primitive COHORT REPLAY (PROOF ONLY; classification census).

Quantifies how many of the owner-reviewed candidate logs move CLOSER to source-binding
because the already-pushed log53 primitives now exist. It does NOT place a bore, draw a
stroke, render a PNG, parse the plan PDF, or implement any new resolver. It is a deterministic
applicability/placement-readiness CENSUS over the owner-reviewed adjudication artifact.

Why artifact-driven (and NOT a PDF re-bind for every log): the log53 primitives
(resolve_nextlink_hh_callout / resolve_structure_position / BORE - LATERAL seed / matchline
boundary termination / sheet-local continuation) consume a MACHINE-ENCODED endpoint identity
as INPUT. In the reviewed artifact only ``log53`` carries that ``endpoint_anchors`` identity
bridge. Manufacturing endpoint identity for the other logs from free text to force a PDF bind
would be exactly the unreviewed-OCR inference the doctrine forbids. So this census reads ONLY
owner-AUTHORITATIVE facts (correction_types, corrected_start/end/sheets, evidence_notes
structure tokens, endpoint_anchors) and the EXISTING proven placement-readiness seam
(manual_adjudication.placement_geometry_readiness) to classify each log. It invents no
coordinate, no geometry, no identity.

Per candidate log it records which of the FIVE log53 primitives APPLY (never forced) and a
typed classification + typed blockers, then answers:
  * how many logs move closer because of the log53 primitives?
  * what is the biggest repeated blocker class?
  * should the representative-route / mid-callout resolver be the next slice?
  * should the broad renderer wait?

Census-safety: flag-OFF byte-identical (31/6/1/17/3), flag-ON (22/1/4), log44 held
non-drawable, the 4 abstains held, no parent-run duplicate. No PNG ever (no render import).
Proof-only; the JSON report is written under the gitignored data/outputs path.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log53_primitives_cohort_replay
"""
from __future__ import annotations

import json
from collections import Counter

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.structure_position import BRENHAM_STRUCTURE_LAYERS
from truelinev2.ingest.manual_adjudication import (
    PLACE_BLOCKED_ENGINE_LAW,
    PLACE_BLOCKED_SOURCE_VERIFY,
    PLACE_NEEDS_GEOMETRY,
    activation_summary,
    apply_adjudications,
    load_adjudication,
    parent_run_duplicate_check,
    placement_geometry_readiness,
)

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log53_primitives_cohort_replay"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")

# --- structure classes the dialect can deterministically bind from source ---------
# (BRENHAM_STRUCTURE_LAYERS -> resolve_structure_position; nextlink_hh -> the committed
# resolve_nextlink_hh_callout locator). These are the ONLY endpoint identities a log53
# primitive can resolve; a bare "HH" / "structure" / "endpoint" mention is NOT one.
MODELED_TERMINUS_CLASSES = frozenset(set(BRENHAM_STRUCTURE_LAYERS) | {"nextlink_hh"})
# owner-authoritative structure tokens -> modeled class (read from evidence_notes; the
# artifact declares the written facts authoritative). Identity-level only, never geometry.
MODELED_TOKENS = (
    ("FLOWER POT", "flower_pot"),
    ("INSTALLER HH", "installer_hh"),
    ("NEXTLINK HH", "nextlink_hh"),
    ("PORT HH", "terminal_port_hh"),
    ("TERMINAL & PORT", "terminal_port_hh"),
)

# --- the five reusable log53 primitives (applicability keys) -----------------------
PRIM_START_CALLOUT = "start_callout_leader_symbol_binding"
PRIM_STRUCT_ENDPOINT = "existing_structure_endpoint_binding"
PRIM_BORE_LATERAL = "bore_lateral_conduit_seed"
PRIM_MATCHLINE_TERM = "matchline_boundary_termination"
PRIM_SHEET_CONT = "sheet_local_continuation_station_identity"
ALL_PRIMITIVES = (PRIM_START_CALLOUT, PRIM_STRUCT_ENDPOINT, PRIM_BORE_LATERAL,
                  PRIM_MATCHLINE_TERM, PRIM_SHEET_CONT)

# --- classifications --------------------------------------------------------------
SOURCE_BINDABLE_NOW = "SOURCE_BINDABLE_NOW"
PARTIAL_SOURCE_BINDABLE = "PARTIAL_SOURCE_BINDABLE"
REPRESENTATIVE_ROUTE_CANDIDATE = "REPRESENTATIVE_ROUTE_CANDIDATE"
HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
STILL_BLOCKED = "STILL_BLOCKED"
NOT_APPLICABLE = "NOT_APPLICABLE"
CLASSIFICATIONS = frozenset({
    SOURCE_BINDABLE_NOW, PARTIAL_SOURCE_BINDABLE, REPRESENTATIVE_ROUTE_CANDIDATE,
    HUMAN_REVIEW_REQUIRED, STILL_BLOCKED, NOT_APPLICABLE,
})

# --- typed blockers (task vocabulary + precise artifact-derived extensions) --------
OWNER_HELD_ABSTAIN = "OWNER_HELD_ABSTAIN"
SOURCE_VERIFICATION_REQUIRED = "SOURCE_VERIFICATION_REQUIRED"
FRAME_CONTESTED = "FRAME_CONTESTED"                      # cross-sheet coord join deferred
MID_CALLOUT_CONTAINMENT = "MID_CALLOUT_CONTAINMENT"
MULTIPLE_REVERSE_PATHS = "MULTIPLE_REVERSE_PATHS"
MATCHLINE_TERMINATION_NOT_FOUND = "MATCHLINE_TERMINATION_NOT_FOUND"
CONDUIT_SEED_NOT_FOUND = "CONDUIT_SEED_NOT_FOUND"
CALLOUT_NOT_FOUND = "CALLOUT_NOT_FOUND"
CALLOUT_NOT_UNIQUE = "CALLOUT_NOT_UNIQUE"
LEADER_NOT_FOUND = "LEADER_NOT_FOUND"
SYMBOL_NOT_FOUND = "SYMBOL_NOT_FOUND"
OCR_REQUIRED = "OCR_REQUIRED"
# precise extensions (this census measures artifact-level readiness, not PDF geometry):
ENDPOINT_IDENTITY_NOT_ENCODED = "ENDPOINT_IDENTITY_NOT_ENCODED"   # modeled, just no bridge yet
ENDPOINT_IDENTITY_NOT_MODELED = "ENDPOINT_IDENTITY_NOT_MODELED"   # no modeled-class terminus
NO_RECORDED_SHEET = "NO_RECORDED_SHEET"                           # cannot source a sheet ladder
RESET_ORIGIN_FRAME_TRANSLATION = "RESET_ORIGIN_FRAME_TRANSLATION"  # reset 0+00 -> plan coords
REVIEW_FLAG_HELD = "REVIEW_FLAG_HELD"                             # owner needs_review flag
ALLOWED_BLOCKERS = frozenset({
    OWNER_HELD_ABSTAIN, SOURCE_VERIFICATION_REQUIRED, FRAME_CONTESTED, MID_CALLOUT_CONTAINMENT,
    MULTIPLE_REVERSE_PATHS, MATCHLINE_TERMINATION_NOT_FOUND, CONDUIT_SEED_NOT_FOUND,
    CALLOUT_NOT_FOUND, CALLOUT_NOT_UNIQUE, LEADER_NOT_FOUND, SYMBOL_NOT_FOUND, OCR_REQUIRED,
    ENDPOINT_IDENTITY_NOT_ENCODED, ENDPOINT_IDENTITY_NOT_MODELED, NO_RECORDED_SHEET,
    RESET_ORIGIN_FRAME_TRANSLATION, REVIEW_FLAG_HELD,
})


def derive_signals(rec: dict) -> dict:
    """Owner-AUTHORITATIVE signals only (correction_types, sheets, evidence_notes structure
    tokens, endpoint_anchors). No coordinate, no PDF, no geometry."""
    cts = set(rec.get("correction_types") or [])
    sheets = list(rec.get("corrected_sheets") or [])
    up = str(rec.get("evidence_notes") or "").upper()
    modeled = {cls for tok, cls in MODELED_TOKENS if tok in up}
    ea = rec.get("endpoint_anchors") or {}
    for side in ("start", "end"):
        sc = (ea.get(side) or {}).get("structure_class")
        if sc in MODELED_TERMINUS_CLASSES:
            modeled.add(sc)
    start = rec.get("corrected_start")
    return {
        "correction_types": sorted(cts),
        "sheets": sheets,
        "n_sheets": len(sheets),
        "modeled_terminus_classes": sorted(modeled),
        "has_modeled_terminus": bool(modeled),
        "has_anchor_bridge": bool(ea),
        "reset_origin": "STATION_RESET_SEGMENT_BOUNDARY" in cts and start in ("0+00", None),
        "matchline_chain": "MATCHLINE_CHAIN" in cts,
        "hh_hh": "HH_HH_ANNOTATION" in cts,
        "leader": "LEADER_LINE_TO_STRUCTURE" in cts,
        "direct_callout": "DIRECT_BORE_CALLOUT" in cts,
    }


def applicable_primitives(sig: dict) -> list:
    """Which of the FIVE log53 primitives APPLY to this log (never forced)."""
    helped = []
    classes = set(sig["modeled_terminus_classes"])
    if (sig["leader"] or sig["direct_callout"]
            or {"installer_hh", "nextlink_hh"} & classes):
        helped.append(PRIM_START_CALLOUT)
    if sig["has_modeled_terminus"]:
        helped.append(PRIM_STRUCT_ENDPOINT)
    if sig["hh_hh"]:
        helped.append(PRIM_BORE_LATERAL)
    if sig["matchline_chain"] and sig["n_sheets"] > 1:
        helped.append(PRIM_MATCHLINE_TERM)
        helped.append(PRIM_SHEET_CONT)
    return helped


def classify_record(rec: dict) -> dict:
    """Deterministic typed classification of ONE adjudication record. Pure: reads only the
    reviewed artifact fields; invents nothing; authorizes no drawing."""
    sig = derive_signals(rec)
    helped = applicable_primitives(sig)
    readiness = placement_geometry_readiness(rec)

    def v(classification, blockers, next_action):
        return {"log_id": rec.get("log_id"), "classification": classification,
                "primitives_that_helped": helped, "blockers": blockers,
                "next_action": next_action, "signals": sig,
                "placement_readiness": readiness["status"]}

    # 1. owner-held abstain (engine law): never drawn
    if rec.get("must_remain_abstained"):
        return v(STILL_BLOCKED, [OWNER_HELD_ABSTAIN],
                 "hold abstain (owner-reviewed: no safe source); no action")
    # 2. source-verification / not allowed_to_draw (e.g. log44 chained segment)
    if rec.get("needs_source_verification") or not rec.get("allowed_to_draw"):
        return v(HUMAN_REVIEW_REQUIRED, [SOURCE_VERIFICATION_REQUIRED],
                 "owner-verify exact start/end against the source bore row before encoding")
    # 3. recovered + allowed but owner-flagged for review (e.g. missing-print / tolerance)
    if rec.get("needs_review"):
        return v(HUMAN_REVIEW_REQUIRED, [REVIEW_FLAG_HELD],
                 "owner review the flagged reconstruction/tolerance before encoding")

    # 4. SOURCE_BINDABLE_NOW -- the proven exemplar shape: an owner-ENCODED endpoint-anchor
    #    bridge with a modeled structure_terminus start + a terminus/continuation end
    #    (the only log carrying it is log53, which is rendered on real source).
    ea = rec.get("endpoint_anchors") or {}
    start_a, end_a = ea.get("start") or {}, ea.get("end") or {}
    if (start_a.get("boundary_kind") == "structure_terminus"
            and start_a.get("structure_class") in MODELED_TERMINUS_CLASSES
            and end_a.get("boundary_kind") in ("structure_terminus", "matchline_continuation")):
        return v(SOURCE_BINDABLE_NOW, [],
                 "proven on real source (log53 exemplar); ready as a review-drawable artifact")

    # 5. PARTIAL_SOURCE_BINDABLE -- >=1 modeled terminus the existing resolver can bind from
    #    source AND a recorded sheet to bind it on. Remaining gap is encoding +/- cross-sheet.
    if sig["has_modeled_terminus"] and sig["n_sheets"] >= 1:
        blockers = [ENDPOINT_IDENTITY_NOT_ENCODED]
        if sig["n_sheets"] > 1:
            blockers.append(FRAME_CONTESTED)
            action = ("encode endpoint_anchors bridge + replay log53 sheet-local segment "
                      "binding per sheet; cross-sheet coordinate join deferred")
        else:
            action = ("encode endpoint_anchors bridge + bind both termini with the existing "
                      "structure resolver (single sheet -> no cross-sheet) -> fastest convert")
        return v(PARTIAL_SOURCE_BINDABLE, blockers, action)

    # 6. REPRESENTATIVE_ROUTE_CANDIDATE -- route is owner-source-backed but exact placement is
    #    gated on a missing sheet, an unmodeled endpoint identity, and/or reset-origin/cross-
    #    sheet frame work (the representative-route doctrine is not built).
    blockers = []
    if sig["has_modeled_terminus"] and sig["n_sheets"] == 0:
        blockers.append(NO_RECORDED_SHEET)
        action = "recover the print/sheet so the modeled terminus can bind on a real sheet"
    else:
        blockers.append(ENDPOINT_IDENTITY_NOT_MODELED)
        if sig["n_sheets"] > 1:
            blockers.append(FRAME_CONTESTED)
        action = ("confirm with a focused PDF probe whether a representative-route / mid-callout "
                  "resolver is actually needed before building it")
    if sig["reset_origin"]:
        blockers.append(RESET_ORIGIN_FRAME_TRANSLATION)
    return v(REPRESENTATIVE_ROUTE_CANDIDATE, blockers, action)


def classify_cohort(doc: dict) -> list:
    """Classify every adjudicated candidate log (the verified cohort = the artifact's logs)."""
    return [classify_record(rec) for rec in doc.get("logs", [])]


def _consistent(cls: str, readiness: str) -> bool:
    """Each classification must agree with the existing placement-readiness seam:
    abstain <-> engine-law; source-verify <-> source-verify block; everything else is a
    review-drawable (NEEDS_GEOMETRY) sub-classification."""
    if cls == STILL_BLOCKED:
        return readiness == PLACE_BLOCKED_ENGINE_LAW
    if readiness == PLACE_BLOCKED_ENGINE_LAW:
        return cls == STILL_BLOCKED
    if readiness == PLACE_BLOCKED_SOURCE_VERIFY:
        return cls == HUMAN_REVIEW_REQUIRED
    # readiness == PLACE_NEEDS_GEOMETRY (review-drawable): any non-blocked class is valid
    return readiness == PLACE_NEEDS_GEOMETRY and cls != STILL_BLOCKED


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()  # no render/stroke lane: a PNG must never exist

    doc = load_adjudication()
    gates = []

    # ---- census-safety (frozen engine) -------------------------------------------
    if not TRUTH.is_file():
        gates.append(("G0 truth table present (census-safety baseline)", False, str(TRUTH)))
        return _emit(gates, [], {}, doc)
    truth = json.loads(TRUTH.read_text(encoding="utf-8"))
    baseline = {r["bore_id"]: dict(r) for r in truth["rows"]}
    off_rows = apply_adjudications(baseline, enabled=False)
    on_rows = apply_adjudications(baseline, enabled=True, doc=doc)
    summ = activation_summary(on_rows)

    def buckets(rows):
        c = {}
        for r in rows.values():
            c[r["completion_bucket"]] = c.get(r["completion_bucket"], 0) + 1
        return c

    gates.append(("G1 flag OFF byte-identical (31/6/1/17/3)",
                  off_rows is baseline and buckets(off_rows) == FROZEN_BUCKETS, buckets(off_rows)))
    gates.append(("G2 flag ON 22/1/4",
                  summ["manual_review_drawable"] == 22 and summ["manual_source_verification"] == 1
                  and summ["manual_abstain"] == 4, None))
    gates.append(("G3 log44 held non-drawable / 4 abstains held / no parent-run duplicate",
                  on_rows["log44"]["adjudication"]["drawable_status"] == "non_drawable"
                  and all(on_rows[l]["adjudication"]["drawable_status"] == "abstain" for l in ABSTAIN_4)
                  and not parent_run_duplicate_check(doc), None))

    # ---- the cohort replay census ------------------------------------------------
    rows = classify_cohort(doc)
    counts = Counter(r["classification"] for r in rows)
    blocker_counts = Counter(b for r in rows for b in r["blockers"])

    gates.append(("G4 every adjudicated candidate log classified exactly once (27)",
                  len(rows) == len(doc["logs"]) == 27
                  and len({r["log_id"] for r in rows}) == 27, len(rows)))
    gates.append(("G5 every classification in the allowed enum",
                  all(r["classification"] in CLASSIFICATIONS for r in rows),
                  sorted({r["classification"] for r in rows})))
    gates.append(("G6 every blocker in the allowed typed enum",
                  all(b in ALLOWED_BLOCKERS for r in rows for b in r["blockers"]),
                  sorted(blocker_counts)))
    gates.append(("G7 classification counts reconcile to 27",
                  sum(counts.values()) == 27, dict(counts)))
    gates.append(("G8 log53 is the proven SOURCE_BINDABLE_NOW exemplar",
                  next(r["classification"] for r in rows if r["log_id"] == "log53")
                  == SOURCE_BINDABLE_NOW, None))
    gates.append(("G9 the 4 owner abstains are STILL_BLOCKED; log44 is HUMAN_REVIEW_REQUIRED",
                  all(next(r["classification"] for r in rows if r["log_id"] == l) == STILL_BLOCKED
                      for l in ABSTAIN_4)
                  and next(r["classification"] for r in rows if r["log_id"] == "log44")
                  == HUMAN_REVIEW_REQUIRED, None))
    gates.append(("G10 classification consistent with placement_geometry_readiness seam",
                  all(_consistent(r["classification"], r["placement_readiness"]) for r in rows),
                  None))

    summary = {
        "tested_logs": len(rows),
        "classification_counts": dict(counts),
        "moved_closer_because_of_log53_primitives":
            counts[SOURCE_BINDABLE_NOW] + counts[PARTIAL_SOURCE_BINDABLE]
            + counts[REPRESENTATIVE_ROUTE_CANDIDATE],
        "largest_repeated_blocker": (blocker_counts.most_common(1)[0] if blocker_counts else None),
        "blocker_counts": dict(blocker_counts.most_common()),
    }
    return _emit(gates, rows, summary, doc)


def _emit(gates, rows, summary, doc) -> int:
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G11 zero PNG / zero stroke (no render lane)", len(pngs) == 0, {"pngs": pngs}))
    all_pass = all(x for _, x, _ in gates)
    result = "COHORT_REPLAY_COMPLETE" if (all_pass and rows) else "BLOCKED_CENSUS_INCOMPLETE"
    report = {
        "milestone": "OWNER-PACKET-2 -- log53 primitive cohort replay (proof only; classification census)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result,
        "question": ("how many owner-reviewed candidate logs move closer to source-binding because "
                     "the log53 primitives now exist, and what is the biggest next blocker?"),
        "method": ("deterministic artifact-driven applicability census over owner-AUTHORITATIVE "
                   "facts + the existing placement_geometry_readiness seam; no PDF parse, no "
                   "coordinate, no geometry, no render, no new resolver, no forced placement"),
        "five_primitives": list(ALL_PRIMITIVES),
        "modeled_terminus_classes": sorted(MODELED_TERMINUS_CLASSES),
        "summary": summary,
        "per_log": rows,
        "no_pdf_parse": True, "no_render": True, "no_invented_coordinates": True,
        "no_forced_placement": True, "no_new_resolver": True,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "log53_primitives_cohort_replay.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[cohort-replay] result: {result}")
    if summary:
        print(f"[cohort-replay] counts: {summary['classification_counts']}")
        print(f"[cohort-replay] moved closer (bindable/partial/representative): "
              f"{summary['moved_closer_because_of_log53_primitives']}")
        print(f"[cohort-replay] largest repeated blocker: {summary['largest_repeated_blocker']}")
    for r in rows:
        print(f"[cohort-replay]   {r['log_id']:>6} | {r['classification']:<30} | "
              f"helped={','.join(r['primitives_that_helped']) or '-'} | "
              f"blockers={','.join(r['blockers']) or '-'}")
    for n, x, _ in gates:
        print(f"[cohort-replay] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[cohort-replay] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
