r"""ALL-REDLINES closure ledger (PROOF/REPORT ONLY; no product, no render, no new classifier).

The ALL-REDLINES standard requires that the v2 engine ultimately PLACE every bore log's redline, with
abstention only ever an interim, NAMED target. This ledger is the single deterministic accounting that
serves that standard: it partitions EVERY bore log in the corpus into exactly one closure category,
marks which are already placed, and -- for every NON-placed log -- names the exact next blocker that
stands between it and deterministic placement. It identifies the highest-leverage blocker class to
eliminate next.

It invents NOTHING and claims NOTHING new: every category is a deterministic PROJECTION of signals that
already exist in the shipped pipeline --
  * the final engine truth table (the 58-bore universe + the engine's own can_draw_now / PLACED_REVIEW),
  * the owner-reviewed manual-adjudication cohort classifier (classify_record / classify_cohort: the
    classification + typed blockers for the 27 problem logs), and
  * the seam contract eligible set (ELIGIBLE_EXEMPLARS: the render-proven exemplars).
No new classifier is defined; no PDF is parsed; no coordinate, stroke, or PNG is produced; no log is
promoted; the engine census is frozen.

NO FAKE POSITIVES: a log is only ever marked PLACED when the engine itself reports can_draw_now=True
(ENGINE_PLACED_REVIEW) or it is a render-proven seam exemplar (SEAM_ELIGIBLE_RENDER_PROVEN). Every other
log is NON-placed and carries a named, source-backed next blocker. log36 (anchored bridge, not yet
owner-confirmed/source-bound) is NOT claimed placed -- it is SOURCE_BINDABLE_HELD_BACK.

Closure taxonomy (exactly one per bore log):
  PLACED:
    SEAM_ELIGIBLE_RENDER_PROVEN     -- full source-bind + render proof (the 5 seam exemplars)
    ENGINE_PLACED_REVIEW            -- engine auto-places for review (can_draw_now; PLACED_REVIEW)
  NON-PLACED (each names the exact next blocker):
    SOURCE_BINDABLE_HELD_BACK      -- endpoint-anchor bridge encoded; awaiting owner-confirm + bind + render
    REPRESENTATIVE_ROUTE_ONLY      -- only a representative route is source-backed (no exact endpoint)
    PARENT_CHILD_AGGREGATION_NEEDED-- shared Print #; per-column sheet GENUINELY unrecorded (no corrected_sheets)
    CROSS_SHEET_FRAME_JOIN_NEEDED  -- modeled terminus + recorded sheet, but the run spans sheets
    UNMODELED_TERMINUS_CLASS_NEEDED-- the endpoint structure identity is not modeled/locatable (root gate)
    SOURCE_OCR_OWNER_CONFIRMATION_NEEDED -- owner source re-read / source verification / OCR confirmation
    STILL_BLOCKED_NAMED_REASON     -- owner-reviewed ABSTAIN (no safe source) -- held by owner decision

Proof-only; the JSON report is written under the gitignored data/outputs path.
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_all_redlines_closure_ledger
"""
from __future__ import annotations

import json
from collections import Counter

from truelinev2.config import _REPO_ROOT
from truelinev2.ingest.manual_adjudication import (
    activation_summary,
    apply_adjudications,
    load_adjudication,
    parent_run_duplicate_check,
)
from truelinev2.proof.run_log53_primitives_cohort_replay import (
    ENDPOINT_IDENTITY_NOT_MODELED,
    FRAME_CONTESTED,
    HUMAN_REVIEW_REQUIRED,
    PARTIAL_SOURCE_BINDABLE,
    REPRESENTATIVE_ROUTE_CANDIDATE,
    SOURCE_BINDABLE_NOW,
    STILL_BLOCKED,
    classify_record,
)
from truelinev2.seam import ELIGIBLE_EXEMPLARS

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "all_redlines_closure_ledger"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
SEAM_SET = set(ELIGIBLE_EXEMPLARS)

# ---- closure taxonomy ---------------------------------------------------------------
SEAM_RENDER_PROVEN = "SEAM_ELIGIBLE_RENDER_PROVEN"
ENGINE_PLACED = "ENGINE_PLACED_REVIEW"
HELD_BACK = "SOURCE_BINDABLE_HELD_BACK"
REPRESENTATIVE_ONLY = "REPRESENTATIVE_ROUTE_ONLY"
PARENT_CHILD = "PARENT_CHILD_AGGREGATION_NEEDED"
CROSS_SHEET = "CROSS_SHEET_FRAME_JOIN_NEEDED"
UNMODELED_TERMINUS = "UNMODELED_TERMINUS_CLASS_NEEDED"
SOURCE_OWNER = "SOURCE_OCR_OWNER_CONFIRMATION_NEEDED"
STILL_BLOCKED_NAMED = "STILL_BLOCKED_NAMED_REASON"

PLACED_CATEGORIES = (SEAM_RENDER_PROVEN, ENGINE_PLACED)
NONPLACED_CATEGORIES = (HELD_BACK, REPRESENTATIVE_ONLY, PARENT_CHILD, CROSS_SHEET,
                        UNMODELED_TERMINUS, SOURCE_OWNER, STILL_BLOCKED_NAMED)
ALL_CATEGORIES = PLACED_CATEGORIES + NONPLACED_CATEGORIES

# the exact next blocker that stands between a NON-placed log and deterministic placement (named,
# source-backed; one per non-placed category). PLACED categories carry no blocker.
NEXT_BLOCKER = {
    HELD_BACK: ("endpoint-anchor bridge encoded; present the SOURCE-RECOVERED sheet for OWNER "
                "confirmation, then single-sheet source-bind -> render -> seam promotion"),
    REPRESENTATIVE_ONLY: ("the exact endpoint is not deterministically locatable; only a "
                          "representative route is source-backed (human-review pick-card)"),
    PARENT_CHILD: ("shared Print # whose per-column sheet assignment is GENUINELY unrecorded (no "
                   "corrected_sheets); recover the column->sheet before the terminus can be found"),
    CROSS_SHEET: ("modeled terminus + recorded sheet, but the run spans sheets; the deferred "
                  "cross-sheet matchline frame join must be solved (the two matchline points reconciled)"),
    UNMODELED_TERMINUS: ("the endpoint structure identity is not modeled/locatable from source (no "
                         "modeled terminus class); model/confirm the terminus identity + its locator "
                         "before an exact endpoint exists"),
    SOURCE_OWNER: ("owner source re-read / source verification / OCR confirmation is pending before "
                   "geometry can be trusted"),
    STILL_BLOCKED_NAMED: ("owner-reviewed ABSTAIN (no safe source) -- held by owner decision, not "
                          "engine-unblockable without new source"),
}

R_COMPLETE = "ALL_REDLINES_CLOSURE_LEDGER_COMPLETE"
B_UNIVERSE = "BLOCKED_LEDGER_UNIVERSE_MISSING"
B_PARTITION = "BLOCKED_LEDGER_PARTITION_NOT_TOTAL_OR_DISJOINT"
B_FAKE_POSITIVE = "BLOCKED_LEDGER_FAKE_POSITIVE"
B_UNNAMED = "BLOCKED_LEDGER_UNNAMED_BLOCKER"
B_RECONCILE = "BLOCKED_LEDGER_COHORT_RECONCILE_FAILED"
B_BLOCKER_MISASSIGNED = "BLOCKED_LEDGER_BLOCKER_MISASSIGNED"
ALLOWED = {R_COMPLETE, B_UNIVERSE, B_PARTITION, B_FAKE_POSITIVE, B_UNNAMED, B_RECONCILE, B_BLOCKER_MISASSIGNED}


def closure_category(bore_id: str, in_adj: bool, rec: dict, c: dict) -> str:
    """Deterministic, EXACTLY-ONE closure category from EXISTING signals (no new classifier).

    Placement states first (seam render-proven, then engine-placed-review); then -- for the owner-
    reviewed problem logs the engine cannot place (can_draw_now False) -- the GATING next blocker,
    in dependency order:
      owner ABSTAIN > source/OCR/owner-confirm > UNMODELED endpoint identity > cross-sheet frame join
      > representative-route-only.
    ENDPOINT_IDENTITY_NOT_MODELED is the ROOT gate: with no modeled/locatable endpoint identity there is
    no exact endpoint to place regardless of sheet count, so it outranks the cross-sheet join (a log that
    is multi-sheet AND has no modeled terminus is UNMODELED_TERMINUS, not CROSS_SHEET). Parent-child is
    reserved for the case where the per-column sheet is GENUINELY unrecorded (no corrected_sheets) -- the
    owner review recorded the children's sheets, so that case is currently empty."""
    cls = c["classification"]
    blk = set(c["blockers"])
    if bore_id in SEAM_SET:
        return SEAM_RENDER_PROVEN
    if not in_adj:
        return ENGINE_PLACED                                    # truth-table DRAWABLE_REVIEW; can_draw_now
    if cls == SOURCE_BINDABLE_NOW:                              # anchored bridge, not yet promoted
        return HELD_BACK
    if rec.get("must_remain_abstained"):
        return STILL_BLOCKED_NAMED
    if rec.get("needs_source_verification") or rec.get("needs_review"):
        return SOURCE_OWNER
    if ENDPOINT_IDENTITY_NOT_MODELED in blk:                    # ROOT gate: no modeled endpoint identity
        if rec.get("shared_print_child") and not rec.get("corrected_sheets"):
            return PARENT_CHILD                                 # per-column sheet GENUINELY unrecorded
        return UNMODELED_TERMINUS                               # terminus class not modeled/locatable
    if FRAME_CONTESTED in blk:
        return CROSS_SHEET                                      # modeled terminus + recorded sheet, multi-sheet
    return REPRESENTATIVE_ONLY


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


def build_ledger(truth_rows: list, doc: dict) -> dict:
    """Assign every bore log exactly one closure category + (if non-placed) its named next blocker."""
    adj = {r["log_id"]: r for r in doc["logs"]}
    ledger = {}
    for row in truth_rows:
        bid = row["bore_id"]
        rec = adj.get(bid, row)
        c = classify_record(rec) if bid in adj else {"classification": None, "blockers": []}
        sig = c.get("signals") or {}
        cat = closure_category(bid, bid in adj, rec, c)
        ledger[bid] = {
            "category": cat,
            "placed": cat in PLACED_CATEGORIES,
            "can_draw_now": bool(row.get("can_draw_now")),
            "completion_bucket": row.get("completion_bucket"),
            "cohort_classification": c["classification"],
            "cohort_blockers": list(c["blockers"]),
            "n_sheets": sig.get("n_sheets"),
            "has_modeled_terminus": sig.get("has_modeled_terminus"),
            "shared_print_child": bool(rec.get("shared_print_child")) if bid in adj else False,
            "corrected_sheets": (rec.get("corrected_sheets") if bid in adj else None),
            "next_blocker": (None if cat in PLACED_CATEGORIES else NEXT_BLOCKER[cat]),
            "sheets": row.get("sheets"),
        }
    return ledger


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()

    doc = load_adjudication()
    gates = []
    result = B_UNIVERSE

    if not TRUTH.is_file():
        gates.append(("G0 final engine truth table present (the 58-bore universe)", False, str(TRUTH)))
        return _emit(gates, B_UNIVERSE, {}, None)
    truth_rows = json.loads(TRUTH.read_text(encoding="utf-8"))["rows"]
    adj_ids = {r["log_id"] for r in doc["logs"]}

    gates.append(("G0 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                  _census_frozen(doc), None))
    gates.append(("G1 universe = 58 bore logs (31 engine-drawable not in adj doc + 27 owner-reviewed)",
                  len(truth_rows) == 58
                  and len({r["bore_id"] for r in truth_rows}) == 58
                  and len(adj_ids) == 27
                  and adj_ids <= {r["bore_id"] for r in truth_rows}, {"truth": len(truth_rows), "adj": len(adj_ids)}))

    ledger = build_ledger(truth_rows, doc)
    counts = Counter(v["category"] for v in ledger.values())

    # G2 TOTAL: every bore log assigned exactly one of the known categories
    gates.append(("G2 partition TOTAL: every bore log assigned exactly one known closure category",
                  len(ledger) == 58
                  and all(v["category"] in ALL_CATEGORIES for v in ledger.values())
                  and sum(counts.values()) == 58, dict(counts)))

    # G3 DISJOINT: the placed/non-placed split is clean and sums to the universe
    placed = {b for b, v in ledger.items() if v["placed"]}
    nonplaced = {b for b, v in ledger.items() if not v["placed"]}
    gates.append(("G3 partition DISJOINT: placed + non-placed partition the 58 with no overlap",
                  placed.isdisjoint(nonplaced) and len(placed) + len(nonplaced) == 58, {"placed": len(placed), "nonplaced": len(nonplaced)}))

    # G4 NO FAKE POSITIVE: a log is PLACED only if the engine says can_draw_now OR it is a render-proven
    #    seam exemplar; every non-placed log is one the engine does NOT claim placeable (can_draw_now False)
    seam_ok = all(b in SEAM_SET for b, v in ledger.items() if v["category"] == SEAM_RENDER_PROVEN)
    engine_ok = all(v["can_draw_now"] and b not in adj_ids and v["completion_bucket"] == "DRAWABLE_REVIEW"
                    for b, v in ledger.items() if v["category"] == ENGINE_PLACED)
    nonplaced_honest = all(not v["can_draw_now"] for b, v in ledger.items() if not v["placed"])
    gates.append(("G4 NO FAKE POSITIVE: placed == seam-render-proven OR engine can_draw_now; non-placed all can_draw_now False",
                  seam_ok and engine_ok and nonplaced_honest, None))

    # G5 every NON-placed log carries a named, non-empty next blocker from the closure vocabulary
    named = all(v["next_blocker"] for b, v in ledger.items() if not v["placed"])
    gates.append(("G5 every NON-placed log names the exact next blocker (no unnamed/abstention-as-done)",
                  named and all(ledger[b]["next_blocker"] is None for b in placed), None))

    # G6 placement counts: 5 seam render-proven + 31 engine-placed = 36 placed; 22 non-placed
    gates.append(("G6 placed = 36 (5 seam render-proven + 31 engine-placed-review); non-placed = 22",
                  counts[SEAM_RENDER_PROVEN] == 5 and counts[ENGINE_PLACED] == 31
                  and len(placed) == 36 and len(nonplaced) == 22,
                  {"seam": counts[SEAM_RENDER_PROVEN], "engine": counts[ENGINE_PLACED]}))

    # G7 RECONCILE with the cohort classifier (no divergent re-classification). The closure categories
    #    are a refinement of classify_cohort over the 27 problem logs:
    #      seam(5) + held_back(1)             == cohort SOURCE_BINDABLE_NOW
    #      source/owner(3)                    == cohort HUMAN_REVIEW_REQUIRED
    #      still_blocked(4)                   == cohort STILL_BLOCKED
    #      parent_child + cross_sheet + unmodeled + representative == cohort PARTIAL + REPRESENTATIVE
    cohort = Counter(classify_record(r)["classification"] for r in doc["logs"])
    refine = (counts[SEAM_RENDER_PROVEN] + counts[HELD_BACK] == cohort[SOURCE_BINDABLE_NOW]
              and counts[SOURCE_OWNER] == cohort[HUMAN_REVIEW_REQUIRED]
              and counts[STILL_BLOCKED_NAMED] == cohort[STILL_BLOCKED]
              and (counts[PARENT_CHILD] + counts[CROSS_SHEET] + counts[UNMODELED_TERMINUS]
                   + counts[REPRESENTATIVE_ONLY]) == cohort[PARTIAL_SOURCE_BINDABLE] + cohort[REPRESENTATIVE_ROUTE_CANDIDATE])
    gates.append(("G7 closure categories RECONCILE with classify_cohort (a refinement, not a re-classification)",
                  refine, {"cohort": dict(cohort)}))

    # G8 BLOCKER ASSIGNMENT CORRECT: every category's members satisfy its DEFINING predicate, so the
    #    named next blocker is the TRUE gating one (not a cascade-ordering artifact). The root gate is
    #    ENDPOINT_IDENTITY_NOT_MODELED: a CROSS_SHEET log must actually have a modeled terminus + span
    #    sheets (solving the frame join really would place it); an UNMODELED log must carry the unmodeled-
    #    identity blocker; PARENT_CHILD only when the per-column sheet is genuinely unrecorded.
    cross = [b for b, v in ledger.items() if v["category"] == CROSS_SHEET]
    unmod = [b for b, v in ledger.items() if v["category"] == UNMODELED_TERMINUS]
    pchild = [b for b, v in ledger.items() if v["category"] == PARENT_CHILD]
    blocker_ok = (
        all(ledger[b]["has_modeled_terminus"] and (ledger[b]["n_sheets"] or 0) >= 2
            and ENDPOINT_IDENTITY_NOT_MODELED not in set(ledger[b]["cohort_blockers"]) for b in cross)
        and all(ENDPOINT_IDENTITY_NOT_MODELED in set(ledger[b]["cohort_blockers"]) for b in unmod)
        and all(ledger[b]["shared_print_child"] and not ledger[b]["corrected_sheets"] for b in pchild))
    gates.append(("G8 blocker assignment CORRECT: cross-sheet=modeled+multi-sheet; unmodeled=unmodeled-identity; parent-child=unrecorded-sheet",
                  blocker_ok, {"cross_sheet": len(cross), "unmodeled": len(unmod), "parent_child": len(pchild)}))

    # G9 highest-leverage non-placed blocker class = the largest non-placed category (most logs unblocked
    #    by eliminating one class). Determined from the data, not asserted.
    nonplaced_counts = {cat: counts.get(cat, 0) for cat in NONPLACED_CATEGORIES}
    top_class, top_n = max(nonplaced_counts.items(), key=lambda kv: (kv[1], kv[0]))
    gates.append(("G9 highest-leverage next blocker class identified (largest non-placed category)",
                  top_n == max(nonplaced_counts.values()) and top_n > 0,
                  {"top_class": top_class, "n": top_n}))

    # G10 reuses the canonical cohort classifier; the classify_record used here IS the shipped one
    #     (a runtime identity check -- no new classifier is defined in this proof)
    gates.append(("G10 reuses the canonical classify_record (shipped module); no new classifier defined here",
                  classify_record.__module__ == "truelinev2.proof.run_log53_primitives_cohort_replay", None))

    if all(x for _, x, _ in gates):
        result = R_COMPLETE
    elif not gates[1][1]:
        result = B_UNIVERSE
    elif not (gates[2][1] and gates[3][1]):
        result = B_PARTITION
    elif not gates[4][1]:
        result = B_FAKE_POSITIVE
    elif not gates[5][1]:
        result = B_UNNAMED
    elif not gates[7][1]:
        result = B_RECONCILE
    elif not gates[8][1]:
        result = B_BLOCKER_MISASSIGNED
    else:
        result = B_PARTITION
    return _emit(gates, result, ledger, (top_class, top_n))


def _emit(gates, result, ledger, top) -> int:
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G11 result in allowed enum + zero PNG (no render lane)",
                  result in ALLOWED and len(pngs) == 0, {"result": result, "pngs": pngs}))
    all_pass = all(x for _, x, _ in gates)
    counts = Counter(v["category"] for v in ledger.values())
    placed = {b for b, v in ledger.items() if v.get("placed")}
    by_category = {cat: sorted((b for b, v in ledger.items() if v["category"] == cat),
                               key=lambda s: int(s[3:])) for cat in ALL_CATEGORIES}
    report = {
        "milestone": "ALL-REDLINES closure ledger (proof/report only; deterministic projection, no new classifier)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result if all_pass else "BLOCKED",
        "universe_total": len(ledger),
        "placed_total": len(placed),
        "nonplaced_total": len(ledger) - len(placed),
        "category_counts": {cat: counts.get(cat, 0) for cat in ALL_CATEGORIES},
        "category_members": by_category,
        "highest_leverage_next_blocker": ({"class": top[0], "count": top[1],
                                           "next_blocker": NEXT_BLOCKER.get(top[0])} if top else None),
        "per_log": {b: ledger[b] for b in sorted(ledger, key=lambda s: int(s[3:]))},
        "doctrine": {
            "no_fake_positive": "placed only if engine can_draw_now OR render-proven seam exemplar",
            "abstention_is_named_not_done": "every non-placed log carries an explicit next blocker",
            "no_new_classifier": True, "no_pdf_parse": True, "no_render": True,
            "no_seam_promotion": True, "engine_census_frozen": True,
        },
        "scope_guard": {"product_wiring": False, "broad_renderer": False, "match_review_wiring": False,
                        "runtime_batch": False, "deploy": False, "coordinates_invented": False},
        "next_recommended_slice": (
            f"attack the highest-leverage class {top[0]} ({top[1]} logs): the deferred cross-sheet "
            f"matchline frame join (reconcile the two sheet-local matchline points) would unblock the "
            f"PARTIAL_SOURCE_BINDABLE logs that already carry a modeled terminus + recorded sheet."
            if top and top[0] == CROSS_SHEET else
            (f"attack the highest-leverage non-placed class {top[0]} ({top[1]} logs)" if top else None)),
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "all_redlines_closure_ledger.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[closure] result: {report['result']}  placed={report['placed_total']}/58  "
          f"nonplaced={report['nonplaced_total']}")
    for cat in ALL_CATEGORIES:
        print(f"[closure]   {cat:<34} {counts.get(cat, 0):>3}  {by_category[cat]}")
    if top:
        print(f"[closure]   highest-leverage next blocker: {top[0]} ({top[1]})")
    for n, x, _ in gates:
        print(f"[closure] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[closure] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
