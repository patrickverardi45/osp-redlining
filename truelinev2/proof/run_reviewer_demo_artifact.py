r"""M8.13.a -- static reviewer demo artifact generator (proof/demo only).

Generates a fully self-contained, file://-openable local demo of the reviewer
lane workflow from REAL v2 data: both validated reviewer bundles (verbatim
``ReviewerBundle`` dumps -- the sidecar NEVER mutates them), evidence crops for
every PLACED_REVIEW bore (the existing v2 highlight renderer), full-sheet
context renders for every lane-referenced sheet, and a ``demo_data.js``
(``window.TL2_DEMO = {...}``) consumed by the committed single-file vanilla-JS
viewer (``truelinev2/demo/reviewer_viewer.html``, copied alongside the data).

Honesty contract:
  * evidence crops are CALLOUT HIGHLIGHTS (the plan text the engine anchored
    on) -- they are NOT drawn bore-path strokes; no polyline geometry is
    invented anywhere;
  * pick-card candidates keep the frozen ``SUGGESTION_NOT_PLACEMENT`` label;
  * no numeric confidence exists anywhere in the demo output (walker-enforced);
  * opt-in solvers compose by REVIEWER SERVICE MODE only -- no env flag is
    read or set, nothing activates globally.

Embedded gates (any failure -> nonzero exit, no force-green):
  G1 corpus integrity (58) and the full M8.11 bundle gates: default_baseline
     24 placed; fullest_safe_review 30 placed with lanes 30/16/6/4/2/0;
     cross-mode increment exactly {log7,log15,log16,log27,log45,log72}
  G2 visual/bundle consistency: the visual pass's placed set == the fullest
     bundle's PLACED_REVIEW set
  G3 every PLACED_REVIEW bore yields >= 1 evidence crop, else FAIL naming
     each bore whose callouts carry no renderable bbox
  G4 every visual reference in demo_data.js resolves to a real file
  G5 no numeric confidence anywhere; every pick-card candidate keeps the
     frozen suggestion label; sidecar bundles byte-equal the canonical dumps
  G6 the committed viewer is copied next to demo_data.js

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_reviewer_demo_artifact
Then open:        data\outputs\reviewer_demo\reviewer_viewer.html
"""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
from pathlib import Path
from typing import Dict, List

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.station_axis import parse_tick
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.collision_gate import collect_all_sheet_equations
from truelinev2.match.engine import run_match
from truelinev2.match.reverse_anchor import ReverseAnchorContext
from truelinev2.match.station_axis_interval import StationAxisContext
from truelinev2.match.transition_classifier import conflict_sheet_pairs
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import (
    EXPECTED_DEFAULT,
    EXPECTED_FULLEST_LANES,
    EXPECTED_FULLEST_PLACED,
    EXPECTED_INCREMENT,
    placed_ids,
    resolve_corpus,
)
from truelinev2.render.crop import render_evidence_crop, render_sheet_context
from truelinev2.review.reviewer_payloads import SUGGESTION_LABEL, ReviewerLane
from truelinev2.review.reviewer_service import ReviewerBundleService, ReviewRunMode
from truelinev2.service import _build_plan_frame_graph

DEMO_DIR = _REPO_ROOT / "data" / "outputs" / "reviewer_demo"
VIEWER_SRC = Path(__file__).resolve().parent.parent / "demo" / "reviewer_viewer.html"

_FORBIDDEN_KEY = re.compile(r"(?i)score|probability|percent|likelihood")


# --- pure helpers (offline-tested) ---------------------------------------------------

def build_demo_sidecar(bundles: Dict[str, dict], visuals: Dict[str, dict],
                       sheet_renders: Dict[str, str], meta: dict) -> dict:
    """Sidecar layout: canonical bundle dumps VERBATIM under ``bundles``;
    visuals are a separate harness-level layer keyed by bore_id."""
    return {
        "demo_schema_version": "truelinev2-reviewer-demo-1",
        "meta": copy.deepcopy(meta),
        "bundles": copy.deepcopy(bundles),
        "visuals": copy.deepcopy(visuals),
        "sheet_renders": copy.deepcopy(sheet_renders),
    }


def demo_data_js(sidecar: dict) -> str:
    return "window.TL2_DEMO = " + json.dumps(sidecar, indent=1) + ";\n"


def assert_no_numeric_confidence(obj, path: str = "$") -> None:
    """No numeric-confidence smell anywhere: forbidden key names, and any key
    mentioning 'confidence' must hold a non-numeric (closed-class) value."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if _FORBIDDEN_KEY.search(str(k)):
                raise ValueError(f"forbidden numeric-confidence key {k!r} at {path}")
            if "confidence" in str(k).lower() and isinstance(v, (int, float)):
                raise ValueError(f"numeric confidence value under {k!r} at {path}")
            assert_no_numeric_confidence(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            assert_no_numeric_confidence(v, f"{path}[{i}]")


def assert_suggestion_labels(bundle: dict) -> None:
    """Every pick-card candidate keeps the frozen suggestion label."""
    for p in bundle.get("payloads", []):
        for c in p.get("candidates", []):
            if c.get("label") != SUGGESTION_LABEL:
                raise ValueError(
                    f"candidate label drift on {p.get('bore_id')}: {c.get('label')!r}")


def assert_placed_have_crops(bundle: dict, visuals: Dict[str, dict]) -> None:
    """Every PLACED_REVIEW bore must carry >= 1 evidence crop -- otherwise the
    demo would show a placement with no visual anchor. Fails naming each gap."""
    missing = [p["bore_id"] for p in bundle.get("payloads", [])
               if p.get("lane") == ReviewerLane.PLACED_REVIEW.value
               and not visuals.get(p["bore_id"], {}).get("evidence_crops")]
    if missing:
        raise ValueError(
            f"PLACED_REVIEW bores with no renderable callout bbox/crop: {missing} "
            f"-- name the bbox gap, do not demo a placement without evidence")


def assert_visual_refs_resolve(sidecar: dict, base_dir) -> None:
    """Every relative visual reference must resolve to a real file."""
    base = Path(base_dir)
    refs: List[str] = list(sidecar.get("sheet_renders", {}).values())
    for v in sidecar.get("visuals", {}).values():
        refs.extend(v.get("evidence_crops", []))
        refs.extend(v.get("sheet_context", []))
    broken = [r for r in refs if not (base / r).is_file()]
    if broken:
        raise ValueError(f"visual references do not resolve: {broken}")


# --- generation ----------------------------------------------------------------------

def _fullest_visual_pass(corpus, plan, dialect, offset, crops_dir: Path
                         ) -> Dict[str, dict]:
    """Re-run the engine in the fullest-safe composition (same construction as
    ReviewerBundleService) to obtain Placements with matched_callouts, then
    render evidence crops. Returns visuals keyed by bore_id."""
    graph = _build_plan_frame_graph(plan, offset)
    rev_ctx = ReverseAnchorContext(
        graph=graph, conflicts=conflict_sheet_pairs(graph),
        equations_by_sheet=collect_all_sheet_equations(plan, offset))
    visuals: Dict[str, dict] = {}
    for p in corpus:
        try:
            bore = load_borelog(str(p))
        except Exception:
            continue
        axis_sheets = sorted({x for r in bore.sheet_refs
                              for x in (r - 1, r, r + 1) if x >= 1})
        axis_ctx = StationAxisContext(
            ticks_by_sheet={s: tuple(t for t in (parse_tick(w["text"])
                                                 for w in plan.words(s, offset))
                                     if t is not None) for s in axis_sheets},
            callouts=tuple(c for s in axis_sheets
                           for c in dialect.extract_callouts(plan, s, offset)))
        pl = run_match(bore, plan, dialect, offset,
                       reverse_anchor=rev_ctx, station_axis=axis_ctx)
        if pl.status.value not in ("AUTO_SELECT", "REVIEW"):
            continue
        crops: List[str] = []
        bboxes: List[dict] = []
        for c in pl.matched_callouts:
            out = render_evidence_crop(plan, bore.bore_id, c, str(crops_dir), offset)
            if out:
                crops.append(f"visuals/crops/{Path(out).name}")
                bboxes.append({"sheet": c.sheet, "bbox": list(c.bbox),
                               "text": c.text})
        visuals[bore.bore_id] = {
            "status": pl.status.value, "reason": pl.reason,
            "evidence_crops": crops, "callout_bboxes": bboxes,
            "sheet_context": [],  # filled after shared sheet renders exist
        }
    return visuals


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.13a] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.13a] STOP: inputs missing")
        return 2
    corpus = enumerate_corpus(corpus_dir)
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.13a] STOP: corpus drift ({len(corpus)})")
        return 3
    if not VIEWER_SRC.is_file():
        print(f"[m8.13a] STOP: committed viewer missing: {VIEWER_SRC}")
        return 2

    crops_dir = DEMO_DIR / "visuals" / "crops"
    sheets_dir = DEMO_DIR / "visuals" / "sheets"
    for d in (crops_dir, sheets_dir):
        d.mkdir(parents=True, exist_ok=True)

    # 1. canonical bundles -- the M8.11 seam, modes only, no env flags
    svc = ReviewerBundleService(corpus_dir=corpus_dir, plan_pdf_path=PDF,
                                project_id="brenham-ph5", bore_log_paths=corpus)
    bundle_objs = {m.value: svc.generate(m) for m in
                   (ReviewRunMode.DEFAULT_BASELINE, ReviewRunMode.FULLEST_SAFE_REVIEW)}
    default = bundle_objs[ReviewRunMode.DEFAULT_BASELINE.value]
    fullest = bundle_objs[ReviewRunMode.FULLEST_SAFE_REVIEW.value]
    increment = placed_ids(fullest) - placed_ids(default)
    g1 = (default.status_counts == EXPECTED_DEFAULT
          and fullest.status_counts["PLACED"] == EXPECTED_FULLEST_PLACED
          and fullest.lane_counts == EXPECTED_FULLEST_LANES
          and increment == EXPECTED_INCREMENT)
    print(f"[m8.13a] {'PASS' if g1 else 'FAIL'}  G1 bundle gates: "
          f"default {default.status_counts}, fullest lanes {fullest.lane_counts}, "
          f"increment {sorted(increment)}")
    if not g1:
        return 4
    bundles = {k: b.model_dump(mode="json") for k, b in bundle_objs.items()}

    # 2. visuals -- evidence crops for every fullest-mode placed bore
    plan = PlanPdf(PDF)
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        visuals = _fullest_visual_pass(corpus, plan, dialect, offset, crops_dir)
        fullest_placed = {p.bore_id for p in fullest.payloads
                          if p.lane is ReviewerLane.PLACED_REVIEW}
        g2 = set(visuals) == fullest_placed
        print(f"[m8.13a] {'PASS' if g2 else 'FAIL'}  G2 visual/bundle consistency: "
              f"visual placed {len(visuals)}, bundle placed {len(fullest_placed)}, "
              f"diff {sorted(set(visuals) ^ fullest_placed)}")
        if not g2:
            return 4

        # 3. shared full-sheet context renders for every lane-referenced sheet
        ref_sheets = sorted({s for b in bundle_objs.values()
                             for p in b.payloads for s in p.sheets})
        sheet_renders: Dict[str, str] = {}
        for s in ref_sheets:
            out = render_sheet_context(plan, s, offset, str(sheets_dir))
            if out:
                sheet_renders[str(s)] = f"visuals/sheets/{Path(out).name}"
        for v_bore, v in visuals.items():
            v_sheets = sorted({b["sheet"] for b in v["callout_bboxes"]})
            v["sheet_context"] = [sheet_renders[str(s)] for s in v_sheets
                                  if str(s) in sheet_renders]
    finally:
        plan.close()

    # 4. sidecar + gates
    meta = {
        "milestone": "truelinev2 M8.13.a -- static reviewer demo artifact",
        "corpus_dir": corpus_dir, "corpus_resolution": how, "plan_pdf": PDF,
        "opt_in_composition": ("by reviewer-service MODE only -- no env flag "
                               "read or set; nothing activated globally"),
        "evidence_note": ("evidence crops are callout highlights (the plan text "
                          "the engine anchored on) -- NOT drawn bore-path "
                          "strokes; no polyline geometry is invented"),
    }
    sidecar = build_demo_sidecar(bundles, visuals, sheet_renders, meta)
    g5_msgs = []
    try:
        assert_no_numeric_confidence(sidecar)
    except ValueError as e:
        g5_msgs.append(str(e))
    for k, b in bundles.items():
        try:
            assert_suggestion_labels(b)
        except ValueError as e:
            g5_msgs.append(f"{k}: {e}")
    if sidecar["bundles"] != bundles:
        g5_msgs.append("sidecar mutated the canonical bundle dumps")
    try:
        assert_placed_have_crops(bundles[ReviewRunMode.FULLEST_SAFE_REVIEW.value],
                                 visuals)
    except ValueError as e:
        g5_msgs.append(str(e))
    print(f"[m8.13a] {'PASS' if not g5_msgs else 'FAIL'}  G3+G5 crops/labels/"
          f"confidence/verbatim: {g5_msgs or 'ok'}")
    if g5_msgs:
        return 4

    (DEMO_DIR / "demo_data.js").write_text(demo_data_js(sidecar), encoding="utf-8")
    shutil.copyfile(VIEWER_SRC, DEMO_DIR / "reviewer_viewer.html")
    try:
        assert_visual_refs_resolve(sidecar, DEMO_DIR)
    except ValueError as e:
        print(f"[m8.13a] FAIL  G4 visual refs: {e}")
        return 4
    g6 = (DEMO_DIR / "reviewer_viewer.html").is_file()
    print(f"[m8.13a] PASS  G4 visual refs resolve "
          f"({sum(len(v['evidence_crops']) for v in visuals.values())} crops, "
          f"{len(sheet_renders)} sheet renders)")
    print(f"[m8.13a] {'PASS' if g6 else 'FAIL'}  G6 viewer copied")
    if not g6:
        return 4

    print(f"[m8.13a] demo ready -> {DEMO_DIR / 'reviewer_viewer.html'}")
    print("[m8.13a] open it directly in a browser (file://, no server needed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
