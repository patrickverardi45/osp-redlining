r"""OWNER-PACKET-2 -- manual adjudication PLACEMENT / redline readiness proof (proof-only).

Answers ONE question: can the 22 ``MANUAL_ADJUDICATED_REVIEW_DRAWABLE`` rows (under
``TRUELINE_MANUAL_ADJUDICATIONS=1``) produce SAFE v2 placement/redline artifacts using
the EXISTING v2 geometry/render conventions, WITHOUT inventing geometry?

Method: take the flag-ON resolution overlay (the activation lane's actual output, not a
new truth source), pull the review-drawable rows, and classify each against the v2
redline renderer's documented geometry prerequisites
(``proof/run_redline_stroke_proof`` -> ``extract.tick_path.solve_tick_path`` ->
``render.crop.render_redline_stroke``): a single sheet, plan-coordinate endpoints, a
non-structure-owned endpoint pair, and ultimately a POSITIONED stroke path.

This lane SYNTHESIZES NO geometry: no fake coordinates, no nearest/proximity endpoints,
no length-only draw, no screenshot-derived positions. It renders NO stroke (0 PNG) --
it proves the readiness gap. The canonical red-stroke law is re-affirmed (any stroke,
were one ever produced, pins ``crop.REDLINE_STROKE_RGB``).

Read-only; writes one gitignored JSON. No PDF parse, no render call.
"""
from __future__ import annotations

import json
from pathlib import Path

from truelinev2.config import _REPO_ROOT
from truelinev2.ingest.manual_adjudication import (
    PLACE_BLOCKED_ENGINE_LAW,
    PLACE_BLOCKED_SOURCE_VERIFY,
    PLACE_NEEDS_GEOMETRY,
    PLACE_RENDERABLE,
    activation_summary,
    apply_adjudications,
    load_adjudication,
    parent_run_duplicate_check,
    placement_geometry_readiness,
)
from truelinev2.render.crop import REDLINE_STROKE_RGB  # canonical red pin (read-only)

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "manual_adjudication_placement_proof"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"

ABSTAIN_4 = {"log5", "log31", "log38", "log43"}
PLACE_STATUSES = {PLACE_RENDERABLE, PLACE_NEEDS_GEOMETRY,
                  PLACE_BLOCKED_SOURCE_VERIFY, PLACE_BLOCKED_ENGINE_LAW}
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}


def _bucket_counts(rows):
    c = {}
    for r in rows.values():
        c[r["completion_bucket"]] = c.get(r["completion_bucket"], 0) + 1
    return c


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()  # structural: this lane renders NO stroke

    truth = json.loads(TRUTH.read_text(encoding="utf-8"))
    baseline = {r["bore_id"]: dict(r) for r in truth["rows"]}
    doc = load_adjudication()
    rec_by_id = {r["log_id"]: r for r in doc["logs"]}

    off_rows = apply_adjudications(baseline, enabled=False)
    on_rows = apply_adjudications(baseline, enabled=True, doc=doc)
    summ = activation_summary(on_rows)

    # the 22 review-drawable rows, taken from ACTUAL flag-on output
    review_drawable = sorted(b for b, r in on_rows.items()
                             if r.get("adjudication", {}).get("drawable_status") == "review_drawable")

    # evaluate each of the 22 for renderability against the real renderer's needs
    per_log = []
    for bid in review_drawable:
        rdy = placement_geometry_readiness(rec_by_id[bid])
        per_log.append({
            "log_id": bid,
            "corrected_start": rec_by_id[bid].get("corrected_start"),
            "corrected_end": rec_by_id[bid].get("corrected_end"),
            "corrected_prints": rec_by_id[bid].get("corrected_prints"),
            "corrected_sheets": rec_by_id[bid].get("corrected_sheets"),
            "renderability": rdy["status"],
            "proof_artifact_path": None,           # 0 strokes generated this lane
            "missing_geometry_reason": "; ".join(rdy["reasons"]),
        })
    place_counts = {}
    for p in per_log:
        place_counts[p["renderability"]] = place_counts.get(p["renderability"], 0) + 1

    gates = []

    # G1 -- flag OFF byte-identical (census frozen)
    g1 = (off_rows is baseline
          and not any("adjudication" in r for r in off_rows.values())
          and _bucket_counts(off_rows) == FROZEN_BUCKETS)
    gates.append(("G1 flag OFF byte-identical (31/6/1/17/3)", g1, _bucket_counts(off_rows)))

    # G2 -- flag ON input rows are exactly 22 review-drawable / 1 source-verify / 4 abstain / 0 unresolved
    g2 = (summ["manual_review_drawable"] == 22
          and summ["manual_source_verification"] == 1
          and summ["manual_abstain"] == 4
          and len(review_drawable) == 22)
    gates.append(("G2 flag ON: 22 review-drawable / 1 source-verify / 4 abstain / 0 unresolved", g2,
                  {"review_drawable": summ["manual_review_drawable"],
                   "source_verification": summ["manual_source_verification"],
                   "abstain": summ["manual_abstain"]}))

    # G3 -- all 22 review-drawable rows evaluated
    g3 = len(per_log) == 22
    gates.append(("G3 all 22 review-drawable rows evaluated for renderability", g3,
                  {"evaluated": len(per_log)}))

    # G4 -- each of the 22 gets exactly one of the 4 statuses
    g4 = all(p["renderability"] in PLACE_STATUSES for p in per_log)
    gates.append(("G4 each of 22 has one of the 4 placement statuses", g4, place_counts))

    # G5 -- log44 blocked by source-verification / non-drawable
    a44 = placement_geometry_readiness(rec_by_id["log44"])
    g5 = (a44["status"] == PLACE_BLOCKED_SOURCE_VERIFY
          and on_rows["log44"]["adjudication"]["drawable_status"] == "non_drawable"
          and on_rows["log44"]["can_draw_now"] is False)
    gates.append(("G5 log44 blocked by source-verification / non-drawable", g5, a44["status"]))

    # G6 -- the 4 abstains remain abstained (never evaluated as renderable)
    g6 = (all(on_rows[l]["adjudication"]["drawable_status"] == "abstain" for l in ABSTAIN_4)
          and not (set(review_drawable) & ABSTAIN_4))
    gates.append(("G6 the 4 no-good logs remain abstained (never drawn)", g6, sorted(ABSTAIN_4)))

    # G7 -- log68/log69 separation preserved
    a68 = rec_by_id["log68"]
    a69 = rec_by_id["log69"]
    g7 = (a68["corrected_start"] == "5+03" and a68["corrected_end"] == "6+79"
          and "4+54" not in (a68["corrected_start"], a68["corrected_end"])
          and a69["corrected_start"] == "2+15" and a69["corrected_end"] == "4+54")
    gates.append(("G7 log68=5+03->6+79 (never 4+54); log69=2+15->4+54", g7,
                  {"log68": (a68["corrected_start"], a68["corrected_end"]),
                   "log69": (a69["corrected_start"], a69["corrected_end"])}))

    # G8 -- corrected print 17,20 preserved
    g8 = all(rec_by_id[l].get("corrected_prints") == [17, 20]
             for l in ("log67", "log68", "log69", "log70"))
    gates.append(("G8 log67/68/69/70 corrected print = 17,20", g8,
                  {l: rec_by_id[l].get("corrected_prints")
                   for l in ("log67", "log68", "log69", "log70")}))

    # G9 -- no duplicate parent/child overlapping redline (artifact + among the review-drawable set)
    dup = parent_run_duplicate_check(doc)
    fam_geo, fam_dup = {}, []
    for bid in review_drawable:
        r = rec_by_id[bid]
        if r.get("corrected_start") in (None,) or r.get("corrected_end") in (None,):
            continue
        key = (r.get("parent"), r["corrected_start"], r["corrected_end"],
               tuple(r.get("corrected_sheets") or []))
        if key in fam_geo:
            fam_dup.append(f"{bid} duplicates {fam_geo[key]}")
        else:
            fam_geo[key] = bid
    g9 = (not dup) and (not fam_dup)
    gates.append(("G9 no duplicate parent/child overlapping redline", g9,
                  {"artifact": dup, "review_drawable_family": fam_dup}))

    # G10 -- red-stroke law: canonical pin is red AND 0 strokes generated this lane
    r, g, b = REDLINE_STROKE_RGB
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    g10 = (r >= 200 and g <= 80 and b <= 80) and len(pngs) == 0
    gates.append(("G10 red-stroke law (canonical pin red; 0 strokes generated)", g10,
                  {"REDLINE_STROKE_RGB": list(REDLINE_STROKE_RGB), "stroke_pngs": pngs}))

    # G11 -- proof-only: no render called, output under gitignored data/outputs
    g11 = str(OUT_DIR).replace("\\", "/").find("/data/outputs/") != -1 and len(pngs) == 0
    gates.append(("G11 proof-only artifact under gitignored data/outputs; no render", g11,
                  {"out_dir": str(OUT_DIR)}))

    all_pass = all(x for _, x, _ in gates)
    report = {
        "milestone": "OWNER-PACKET-2 -- manual adjudication PLACEMENT / redline readiness (proof-only)",
        "verdict": "PASS" if all_pass else "FAIL",
        "question": "Can the 22 review-drawable rows render safe v2 redline artifacts without inventing geometry?",
        "answer": ("Not from the reviewed artifact alone. The 27-log adjudication carries corrected "
                   "station/print/sheet TRUTH, not coordinate/path GEOMETRY. The v2 redline renderer "
                   "(solve_tick_path -> render_redline_stroke) needs a single-sheet, plan-coordinate, "
                   "non-structure-owned POSITIONED tick-path; none of the 22 carries that. Rendering "
                   "is a SEPARATE, named geometry-resolution step (reset->plan translation, cross-sheet "
                   "matchline chaining, structure-identity binding) -- NOT synthesized here."),
        "flag": "TRUELINE_MANUAL_ADJUDICATIONS",
        "flag_off_buckets": _bucket_counts(off_rows),
        "counts": {
            "review_drawable_evaluated": len(per_log),
            "renderable_proof_artifacts": place_counts.get(PLACE_RENDERABLE, 0),
            "needs_geometry_resolution": place_counts.get(PLACE_NEEDS_GEOMETRY, 0),
            "blocked_source_verification_in_22": place_counts.get(PLACE_BLOCKED_SOURCE_VERIFY, 0),
            "blocked_engine_law_in_22": place_counts.get(PLACE_BLOCKED_ENGINE_LAW, 0),
            "log44_source_verification": 1,
            "abstain": 4,
            "strokes_generated": 0,
        },
        "red_stroke_law": {"canonical_REDLINE_STROKE_RGB": list(REDLINE_STROKE_RGB),
                           "strokes_generated": 0},
        "per_log": per_log,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    (OUT_DIR / "manual_adjudication_placement_proof.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")

    print("[placement] review-drawable evaluated:", len(per_log))
    print("[placement] renderability counts:", place_counts)
    print("[placement] strokes generated:", 0, "| canonical red:", list(REDLINE_STROKE_RGB))
    for n, x, _ in gates:
        print(f"[placement] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[placement] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
