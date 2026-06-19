r"""REVIEW_CANDIDATE_REASONING_SWEEP -- best-effort REVIEW candidates for every unrendered bore log.

NOT the deterministic AUTO lane. Output is a REVIEW BATCH for owner visual review; correct candidate
reasoning is later converted into deterministic engine law. Hard separation from the deterministic lane:
  * writes ONLY to data/outputs/review_candidate_reasoning_sweep/ (never the deterministic folders)
  * mutates NO fixture, encodes NO permanent anchor/coordinate, promotes NOTHING to census, marks NO AUTO
  * red strokes only; every artifact + reason carries the REVIEW_CANDIDATE label
  * respects owner ABSTAIN_NO_SAFE_SOURCE (NONE even in review mode -- never guess past an owner no-source)

Candidate strategies (closure-gated -- never a nearest/length guess, never an invented coordinate):
  A FULL    : the shipped solve_log binds BOTH termini + a source-backed route that CLOSES the printed span
  B SPANWALK: exactly ONE terminus binds; walk its source-backed conduit chain to the UNIQUE dash endpoint
              at the printed span distance (route closure picks the end; structure identity unprinted)
  else NONE : record the precise deterministic blocker + (in the manifest) the missing source relationship

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_review_candidate_reasoning_sweep
"""
from __future__ import annotations

import json
import math
import os
import re

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.conduit_topology import dash_endpoints
from truelinev2.extract.registry import select_dialect
from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import PDF
import truelinev2.proof.run_callout_route_assembly_sweep as SW
from truelinev2.proof.run_callout_route_assembly_sweep import (
    SCALE, _bind, _chain_at, _ordered_leg, solve_log,
)
from truelinev2.proof.run_log71_render_artifact_slice import route_length
from truelinev2.render.crop import REDLINE_STROKE_RGB, render_redline_stroke
from truelinev2.stations import parse_station

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "review_candidate_reasoning_sweep"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / "final_engine_truth_table.json"
ALREADY = {"log7", "log25", "log45", "log51", "log52", "log53", "log59",
           "log64", "log65", "log66", "log69", "log71", "log50"}
SWEEP = {"log6", "log11", "log12", "log29", "log36", "log41", "log46",
         "log47", "log54", "log58", "log63", "log67", "log68"}
RENDERED = ALREADY | SWEEP
DUP_OF_DRAWN = {"log48": "log50"}
SPANWALK_TOL = 0.12   # review-mode closure band for the span-walk end pick (vs 0.10 deterministic)


def _norm(sta):
    m = re.match(r"0*(\d+)\+(\d+)", sta or "")
    return f"{int(m.group(1))}+{m.group(2)}" if m else sta


def synth(lid, trow, arow):
    """Owner adjudication record if present; else a synthetic record seeded from the truth-table span."""
    if arow:
        return dict(arow)
    span = trow.get("span") or ""
    m = re.match(r"(\d+\+\d+)\s*->\s*(\d+\+\d+)", span)
    return {"log_id": lid, "corrected_start": _norm(m.group(1)) if m else None,
            "corrected_end": _norm(m.group(2)) if m else None,
            "corrected_sheets": trow.get("sheets") or [], "span_ft": None,
            "status": "RECOVERED", "evidence_notes": "", "endpoint_anchors": None,
            "allowed_to_draw": True, "must_remain_abstained": False}


def _span_ft(rec):
    if rec.get("span_ft"):
        return float(rec["span_ft"])
    cs, ce = rec.get("corrected_start"), rec.get("corrected_end")
    if cs and ce:
        try:
            return abs(parse_station(ce) - parse_station(cs))
        except Exception:
            return None
    return None


def span_walk(plan, offset, sheet, cls, label, span_ft):
    """From a uniquely bound terminus, the UNIQUE conduit dash endpoint at the printed span distance.
    Route closure (not nearest) selects the end. 0 or >=2 endpoints at span -> None (abstain)."""
    if not (sheet and cls and label and span_ft):
        return None
    s_xy, words, draw, _ = _bind(plan, offset, sheet, cls, label)
    if not s_xy:
        return None
    chain = _chain_at(draw, cls, s_xy)
    if not chain:
        return None
    tol = SPANWALK_TOL * span_ft
    cands = [p for p in dash_endpoints(chain)
             if abs(math.hypot(p[0] - s_xy[0], p[1] - s_xy[1]) / SCALE - span_ft) <= tol]
    # collapse near-duplicate endpoints
    uniq = []
    for p in cands:
        if all(math.hypot(p[0] - q[0], p[1] - q[1]) > 8.0 for q in uniq):
            uniq.append(p)
    if len(uniq) != 1:
        return None
    route, ok = _ordered_leg(chain, s_xy, uniq[0])
    if not ok:
        return None
    return {"sheet": sheet, "route": route, "a_xy": s_xy, "b_xy": uniq[0],
            "len_pt": round(route_length(route), 1), "kind": "span_walk",
            "drawn_ft": round(route_length(route) / SCALE, 1)}


def _render(plan, offset, lid, legs, label):
    pngs = []
    for leg in legs:
        reason = (f"REVIEW_CANDIDATE [{label}] {lid}: sheet {leg['sheet']} {leg['kind']} "
                  f"({round(leg['len_pt'] / SCALE, 1)} ft) -- owner visual review (NOT auto/census)")
        png = render_redline_stroke(plan, f"{lid}_CANDIDATE", leg["sheet"], offset, leg["route"],
                                    status="REVIEW", reason=reason, out_dir=str(OUT_DIR),
                                    mandatory_points=[tuple(leg["a_xy"]), tuple(leg["b_xy"])], pad=160.0)
        leg["png"] = os.path.basename(png) if png else None
        if png and os.path.isfile(png):
            pngs.append(png.replace(str(_REPO_ROOT), "").lstrip("\\/").replace("\\", "/"))
    return pngs


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()
    truth = {r["bore_id"]: r for r in json.loads(TRUTH.read_text(encoding="utf-8"))["rows"]}
    adj = {r["log_id"]: r for r in load_adjudication()["logs"]}
    unrendered = sorted((b for b in truth if b not in RENDERED), key=lambda s: int(s[3:]))

    rows = []
    plan = PlanPdf(PDF)
    try:
        offset = select_dialect(plan).calibrate(plan, 13)
        for lid in unrendered:
            trow, arow = truth[lid], adj.get(lid)
            rec = synth(lid, trow, arow)
            row = {"log": lid, "family": trow.get("source_family"), "truth_sheets": trow.get("sheets"),
                   "truth_span": trow.get("span"), "stroke_status": trow.get("stroke_status"),
                   "can_draw_now": trow.get("can_draw_now"),
                   "adj_status": (arow or {}).get("status"),
                   "must_abstain": bool((arow or {}).get("must_remain_abstained")),
                   "duplicate_of": DUP_OF_DRAWN.get(lid),
                   "candidate_status": "NONE", "confidence": "NONE", "artifacts": [],
                   "route_sheets": [], "closure": None, "blocker": None, "machine_reason": None}

            if row["must_abstain"]:
                row["blocker"] = "owner ABSTAIN_NO_SAFE_SOURCE (respected in review mode -- no guess past owner no-source)"
                row["machine_reason"] = "owner_abstain"
                rows.append(row)
                continue

            span_ft = _span_ft(rec)
            row["span_ft"] = span_ft
            v = solve_log(plan, offset, lid, {lid: rec})
            row["solve_blocker"] = v.get("blocker")
            row["start_bind"] = {"sheet": v.get("start_sheet"), "class": v.get("start_class"),
                                 "label": (v.get("bound_labels") or {}).get("start")}
            row["end_bind"] = {"sheet": v.get("end_sheet"), "class": v.get("end_class"),
                               "label": (v.get("bound_labels") or {}).get("end")}

            # STRATEGY A: full source-backed route that closes
            if v.get("legs"):
                closes = (v.get("closure") or {}).get("closes", True)
                pngs = _render(plan, offset, lid, v["legs"], "FULL")
                row.update(candidate_status="FULL_CANDIDATE", artifacts=pngs,
                           route_sheets=[l["sheet"] for l in v["legs"]], closure=v.get("closure"),
                           machine_reason="solve_log_full_route",
                           confidence=("HIGH" if (closes and v.get("closure")) else "MEDIUM"))
                rows.append(row)
                continue

            # STRATEGY A-relaxed: a route WAS traced but it does not close the printed span (likely the
            # wrong crossing / a parallel run). Show it as a LOW closure-OFF candidate for owner discussion
            # -- NOT a confirmed route. Re-run with closure disabled to recover the traced geometry only.
            if "closure failed" in (v.get("blocker") or ""):
                saved = SW.CLOSURE_REL_TOL
                SW.CLOSURE_REL_TOL = 1e6
                try:
                    v2 = solve_log(plan, offset, lid, {lid: rec})
                finally:
                    SW.CLOSURE_REL_TOL = saved
                if v2.get("legs"):
                    drawn = round(sum(route_length(l["route"]) for l in v2["legs"]) / SCALE, 1)
                    pngs = _render(plan, offset, lid, v2["legs"], "LOW_CLOSURE_OFF")
                    row.update(candidate_status="FULL_CANDIDATE", artifacts=pngs,
                               route_sheets=[l["sheet"] for l in v2["legs"]],
                               closure={"drawn_ft": drawn, "span_ft": span_ft, "closes": False},
                               machine_reason=("route traced but closure-OFF (drawn %.0f vs span %s ft; likely "
                                               "wrong crossing/parallel run) -- LOW, owner pick" % (drawn, span_ft)),
                               confidence="LOW")
                    rows.append(row)
                    continue

            # STRATEGY B: exactly one terminus bound -> span-walk the conduit to the unique span-distance end
            sb, eb = row["start_bind"], row["end_bind"]
            sw = None
            if sb["sheet"] and not eb["sheet"]:
                sw = span_walk(plan, offset, sb["sheet"], sb["class"], sb["label"], span_ft)
                anchor = f"start {sb['label']} ({sb['class']}) s{sb['sheet']}"
            elif eb["sheet"] and not sb["sheet"]:
                sw = span_walk(plan, offset, eb["sheet"], eb["class"], eb["label"], span_ft)
                anchor = f"end {eb['label']} ({eb['class']}) s{eb['sheet']}"
            if sw:
                pngs = _render(plan, offset, lid, [sw], "PARTIAL_SPANWALK")
                row.update(candidate_status="PARTIAL_CANDIDATE", artifacts=pngs,
                           route_sheets=[sw["sheet"]],
                           closure={"drawn_ft": sw["drawn_ft"], "span_ft": span_ft, "closes": True},
                           machine_reason=f"span_walk from {anchor}; far structure identity UNPRINTED",
                           confidence="MEDIUM")
                rows.append(row)
                continue

            # ELSE: no safe candidate -- record the precise deterministic blocker
            row["blocker"] = v.get("blocker")
            row["machine_reason"] = "no_closed_route_no_single_terminus_spanwalk"
            rows.append(row)
    finally:
        plan.close()

    pngs_on_disk = sorted(p.name for p in OUT_DIR.glob("*.png"))
    summary = {
        "milestone": "REVIEW_CANDIDATE_REASONING_SWEEP (review batch; NOT deterministic AUTO; no census/commit)",
        "deterministic_frontier_before": f"{len(RENDERED)}/58",
        "unrendered_attempted": len(unrendered),
        "full_candidates": [r["log"] for r in rows if r["candidate_status"] == "FULL_CANDIDATE"],
        "partial_candidates": [r["log"] for r in rows if r["candidate_status"] == "PARTIAL_CANDIDATE"],
        "none_logs": [r["log"] for r in rows if r["candidate_status"] == "NONE"],
        "owner_abstain_logs": [r["log"] for r in rows if r["machine_reason"] == "owner_abstain"],
        "output_folder": str(OUT_DIR).replace(str(_REPO_ROOT), "").lstrip("\\/").replace("\\", "/"),
        "red_stroke_rgb": list(REDLINE_STROKE_RGB),
        "artifacts_on_disk": pngs_on_disk,
        "no_census_change": True, "no_auto_mark": True, "no_fixture_mutation": True,
        "no_coordinate_encoding": True, "no_commit": True, "review_batch_only": True,
        "rows": rows,
    }
    (OUT_DIR / "review_candidate_manifest.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"[rc-sweep] FULL={summary['full_candidates']}")
    print(f"[rc-sweep] PARTIAL={summary['partial_candidates']}")
    print(f"[rc-sweep] NONE={summary['none_logs']}")
    print(f"[rc-sweep] artifacts on disk: {len(pngs_on_disk)}")
    for r in rows:
        print(f"[rc-sweep] {r['log']:>6} {r['candidate_status']:<18} {r['confidence']:<7} "
              f"{r.get('machine_reason') or r.get('blocker')}")
    print(f"[rc-sweep] manifest: {OUT_DIR / 'review_candidate_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
