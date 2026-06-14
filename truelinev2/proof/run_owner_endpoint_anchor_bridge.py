r"""OWNER-PACKET-2 -- Endpoint Anchor Schema Bridge proof (log53 only).

Proves the smallest schema/data bridge that preserves Patrick's reviewed endpoint
IDENTITY + BOUNDARY semantics for log53 as machine-consumable input -- WITHOUT
inventing geometry, adding coordinates, or authorizing any draw.

What it gates (any failure -> nonzero exit):
  G1  artifact still parses + validates (fail-closed) with the new field
  G2  schema bumped to truelinev2-manual-adjudication-2
  G3  frozen review summary unchanged (27/23/4/0/0)
  G4  log53 evidence_refs populated; both screenshots exist on disk
  G5  log53 START anchor exact (structure_terminus NEXTLINK HH, evidence 032035)
  G6  log53 END anchor exact (matchline_continuation -> sheet 6; NOT a terminus;
      evidence 032447)
  G7  NO coordinate/stroke field anywhere in log53 endpoint_anchors
  G8  flag OFF inert (overlay returns the baseline object unchanged)
  G9  flag ON counts unchanged (22 review-drawable / 1 source-verify / 4 abstain)
  G10 log44 stays source-verification/non-drawable
  G11 log5/log31/log38/log43 stay abstained
  G12 log53 placement readiness still NEEDS_GEOMETRY (never geometry-ready), no coords
  G13 this proof renders NOTHING (0 PNGs / 0 strokes in the output dir)

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_owner_endpoint_anchor_bridge
Output (gitignored): data/outputs/owner_endpoint_anchor_bridge/
"""
from __future__ import annotations

import json

from truelinev2.config import _REPO_ROOT
from truelinev2.ingest.manual_adjudication import (
    ADJ_BUCKET_ABSTAIN,
    ADJ_BUCKET_SOURCE_VERIFY,
    PLACE_NEEDS_GEOMETRY,
    activation_summary,
    apply_adjudications,
    load_adjudication,
    placement_geometry_readiness,
    summarize,
    validate_adjudication,
)

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "owner_endpoint_anchor_bridge"
EVIDENCE_DIR = (_REPO_ROOT / "truelinev2" / "data" / "manual_adjudications"
                / "evidence" / "2026_06_14" / "log53")
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
_COORD_KEYS = {"x", "y", "z", "xc", "yc", "x0", "y0", "x1", "y1", "cx", "cy", "xy",
               "lat", "lon", "lng", "coord", "coords", "coordinate", "coordinates",
               "px", "py", "pixel", "pixels", "point", "points",
               "symbol_xy", "anchor_xy", "stroke", "stroke_points", "geometry", "geom"}


def _no_coords(obj) -> bool:
    """True iff no coordinate-named key and no float/list-pair value appears."""
    if isinstance(obj, dict):
        if any(str(k).lower() in _COORD_KEYS for k in obj):
            return False
        return all(_no_coords(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return False  # an anchor payload carries no sequences (coords are sequences)
    return not isinstance(obj, float)


def _synthetic_baseline(doc):
    rows = {r["log_id"]: {"bore_id": r["log_id"], "completion_bucket": "PICK_CARD_REVIEW",
                          "source_family": r.get("parent") or r["log_id"],
                          "can_draw_now": False} for r in doc["logs"]}
    for d in ("logD1", "logD2"):
        rows[d] = {"bore_id": d, "completion_bucket": "DRAWABLE_REVIEW",
                   "source_family": d, "can_draw_now": True}
    return rows


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()  # G13: this lane never renders; no PNG may exist

    doc = load_adjudication()
    rec = {r["log_id"]: r for r in doc["logs"]}
    l53 = rec["log53"]
    ea = l53.get("endpoint_anchors") or {}
    start = ea.get("start") or {}
    end = ea.get("end") or {}
    gates = []

    gates.append(("G1 artifact parses + validates", validate_adjudication(doc) == [],
                  {"errors": validate_adjudication(doc)}))
    gates.append(("G2 schema == manual-adjudication-2",
                  doc.get("schema") == "truelinev2-manual-adjudication-2", doc.get("schema")))

    s = summarize(doc)
    g3 = (s["original_problem_logs"], s["recoverable_or_correct_as_drawn"],
          s["valid_abstain_no_good"], s["active_unknowns"],
          s["shared_print_owner_source_required_after_review"]) == (27, 23, 4, 0, 0)
    gates.append(("G3 frozen summary 27/23/4/0/0", g3, s))

    g4 = (l53.get("evidence_refs") == ["Screenshot 2026-06-14 032035.png",
                                       "Screenshot 2026-06-14 032447.png"]
          and (EVIDENCE_DIR / "Screenshot 2026-06-14 032035.png").is_file()
          and (EVIDENCE_DIR / "Screenshot 2026-06-14 032447.png").is_file())
    gates.append(("G4 evidence_refs populated + files exist", g4,
                  {"refs": l53.get("evidence_refs"), "dir": str(EVIDENCE_DIR)}))

    g5 = (start.get("station") == "21+63"
          and start.get("boundary_kind") == "structure_terminus"
          and start.get("structure_class") == "nextlink_hh"
          and start.get("structure_label") == "NEXTLINK HH"
          and start.get("evidence_ref") == "Screenshot 2026-06-14 032035.png"
          and start.get("clarity") == "CLEAR")
    gates.append(("G5 start anchor exact (NEXTLINK HH terminus)", g5, start))

    g6 = (end.get("station") == "24+11"
          and end.get("boundary_kind") == "matchline_continuation"
          and end.get("continues_to_sheet") == 6
          and end.get("continues_as") == "STA 24+11 TO STA 26+38"
          and end.get("structure_class") is None
          and end.get("structure_label") is None
          and end.get("evidence_ref") == "Screenshot 2026-06-14 032447.png")
    gates.append(("G6 end anchor exact (matchline continuation, NOT terminus)", g6, end))

    gates.append(("G7 no coordinate/stroke field in endpoint_anchors", _no_coords(ea), None))

    baseline = _synthetic_baseline(doc)
    off = apply_adjudications(baseline, enabled=False)
    gates.append(("G8 flag OFF inert (same object)", off is baseline, None))

    on = apply_adjudications(baseline, enabled=True, doc=doc)
    summ = activation_summary(on)
    g9 = (summ["manual_review_drawable"] == 22 and summ["manual_source_verification"] == 1
          and summ["manual_abstain"] == 4)
    gates.append(("G9 flag ON 22/1/4 unchanged", g9,
                  {k: summ[k] for k in ("manual_review_drawable", "manual_source_verification",
                                        "manual_abstain")}))

    g10 = (on["log44"]["adjudication"]["drawable_status"] == "non_drawable"
           and on["log44"]["completion_bucket"] == ADJ_BUCKET_SOURCE_VERIFY
           and on["log44"]["can_draw_now"] is False)
    gates.append(("G10 log44 source-verification/non-drawable", g10, None))

    g11 = all(on[l]["adjudication"]["drawable_status"] == "abstain"
              and on[l]["completion_bucket"] == ADJ_BUCKET_ABSTAIN for l in ABSTAIN_4)
    gates.append(("G11 log5/31/38/43 abstained", g11, None))

    pr = placement_geometry_readiness(l53)
    g12 = (pr["status"] == PLACE_NEEDS_GEOMETRY and pr["has_positioned_geometry"] is False
           and not any(k in pr for k in ("x", "y", "stroke_points", "lat", "lon", "coords"))
           and any("matchline continuation" in r for r in pr["reasons"]))
    gates.append(("G12 log53 placement NEEDS_GEOMETRY (never ready), no coords", g12,
                  {"status": pr["status"]}))

    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G13 zero PNG / zero stroke rendered", len(pngs) == 0, {"pngs": pngs}))

    all_pass = all(x for _, x, _ in gates)
    report = {
        "milestone": "OWNER-PACKET-2 -- Endpoint Anchor Schema Bridge (log53 only)",
        "verdict": "PASS" if all_pass else "FAIL",
        "target": "log53",
        "schema": doc.get("schema"),
        "log53_endpoint_anchors": ea,
        "log53_evidence_refs": l53.get("evidence_refs"),
        "log53_placement_status": pr["status"],
        "authorizes_drawing": False,
        "coordinates_added": False,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    (OUT_DIR / "owner_endpoint_anchor_bridge.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    for n, x, _ in gates:
        print(f"[endpoint-bridge] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[endpoint-bridge] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
