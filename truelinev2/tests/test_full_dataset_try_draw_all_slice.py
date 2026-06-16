"""FULL-DATASET TRY-DRAW-ALL diagnostic sweep -- offline-law + PDF/env-gated end-to-end tests.

Offline laws (always run, no subprocess): the result/category enums; the 11-category vocabulary; the render
registry covers exactly the 12 drawable-now logs (11 RENDERED_FULL + 1 RENDERED_PARTIAL=log7); the pure
classifier maps every closure category + held-back sub-split to the correct diagnostic category, with render
success overriding; the sweep defines no new frame/join/render math (it drives the shipped render proofs
out-of-process and reuses scout_log/build_ledger). The heavy end-to-end (drives all 12 render proofs as
subprocesses) is gated behind the PDF AND the env flag TL2_TRY_DRAW_E2E=1 so it never bloats the default
suite; it asserts the full 58-log partition, the 12-log rendered set, real PNGs for every rendered log, and
that placement (36) / seam (5) / census are unchanged.
"""
import os
from pathlib import Path

import pytest

import truelinev2.match.frames as FR
from truelinev2.render.crop import REDLINE_STROKE_RGB
from truelinev2.proof.run_brenham_corpus import PDF
from truelinev2.proof.run_all_redlines_closure_ledger import (
    CROSS_SHEET, ENGINE_PLACED, HELD_BACK, SEAM_RENDER_PROVEN, SOURCE_OWNER,
    STILL_BLOCKED_NAMED, UNMODELED_TERMINUS,
)
from truelinev2.proof.run_full_dataset_try_draw_all_slice import (
    ALLOWED, ALL_CATEGORIES, OUT_DIR, PARTIAL_LOGS, RENDERED_LOGS, RENDER_DRIVERS,
    R_COMPLETE, classify, main,
    OUT_OF_CLASS, OWNER_CONFIRMATION, PARENT_CHILD_RECON, REPRESENTATIVE, RENDERED_FULL,
    RENDERED_PARTIAL, SOURCE_BIND_ONLY, SOURCE_OCR_OWNER, TERMINI_BOUND_JOIN, UNMODELED_TERMINUS_B,
    UNSAFE_ABSTAIN,
)

PROOF = Path(__file__).resolve().parent.parent / "proof" / "run_full_dataset_try_draw_all_slice.py"

EXPECTED_RENDERED = ("log25", "log45", "log51", "log52", "log53", "log59",
                     "log64", "log65", "log66", "log69", "log71", "log7")
EXPECTED_PARTITION = {
    RENDERED_FULL: 11, RENDERED_PARTIAL: 1, SOURCE_BIND_ONLY: 3, TERMINI_BOUND_JOIN: 2,
    OWNER_CONFIRMATION: 1, PARENT_CHILD_RECON: 1, SOURCE_OCR_OWNER: 3, UNMODELED_TERMINUS_B: 6,
    REPRESENTATIVE: 26, OUT_OF_CLASS: 0, UNSAFE_ABSTAIN: 4,
}


def test_result_enum_and_categories():
    assert R_COMPLETE in ALLOWED
    assert ALLOWED == {
        "FULL_DATASET_TRY_DRAW_ALL_COMPLETE", "BLOCKED_TRY_DRAW_UNIVERSE_MISSING",
        "BLOCKED_TRY_DRAW_RENDER_DRIVER_FAILED", "BLOCKED_TRY_DRAW_FAKE_POSITIVE",
        "BLOCKED_TRY_DRAW_PARTITION_NOT_TOTAL_OR_DISJOINT", "BLOCKED_TRY_DRAW_CENSUS_OR_PLACEMENT_DRIFT",
        "BLOCKED_TRY_DRAW_SCOPE_VIOLATION",
    }
    # exactly the 11 diagnostic categories the task specified
    assert len(ALL_CATEGORIES) == 11
    assert set(ALL_CATEGORIES) == {
        "RENDERED_FULL", "RENDERED_PARTIAL", "SOURCE_BIND_ONLY_RENDER_BLOCKED", "TERMINI_BOUND_JOIN_BLOCKED",
        "OWNER_CONFIRMATION_BLOCKED", "PARENT_CHILD_RECONSTRUCTION_BLOCKED", "SOURCE_OCR_OWNER_CONFIRMATION_BLOCKED",
        "UNMODELED_TERMINUS_BLOCKED", "REPRESENTATIVE_ROUTE_ONLY", "OUT_OF_CLASS", "UNSAFE_ABSTAIN",
    }


def test_render_registry_is_the_12_drawable_logs():
    # 12 distinct logs across the proven render drivers; exactly one PARTIAL (log7)
    assert set(RENDERED_LOGS) == set(EXPECTED_RENDERED)
    assert len(RENDERED_LOGS) == 12
    assert PARTIAL_LOGS == ("log7",)
    # the drivers are the proven per-log render proofs; no lane-sweep / reviewer-demo census renderer
    modules = [m for m, _ in RENDER_DRIVERS]
    assert "truelinev2.proof.run_symbol_conduit_lane_sweep" not in modules
    assert "truelinev2.proof.run_reviewer_demo_artifact" not in modules
    # each driver targets only its own log(s); union == the 12
    targeted = [lid for _, rows in RENDER_DRIVERS for lid, _, _ in rows]
    assert sorted(targeted) == sorted(EXPECTED_RENDERED)


def test_classifier_render_success_overrides():
    # any log in the render set classifies RENDERED_* regardless of its closure category
    assert classify("log53", {}, SEAM_RENDER_PROVEN, False) == RENDERED_FULL
    assert classify("log25", {}, ENGINE_PLACED, False) == RENDERED_FULL   # engine-placed but rendered
    assert classify("log45", {}, ENGINE_PLACED, False) == RENDERED_FULL
    assert classify("log7", {}, ENGINE_PLACED, False) == RENDERED_PARTIAL  # the lone partial


def test_classifier_nonrendered_mapping():
    # closure category -> diagnostic category for NON-rendered logs (use ids NOT in the render set)
    assert classify("logX", {"must_remain_abstained": True}, STILL_BLOCKED_NAMED, False) == UNSAFE_ABSTAIN
    assert classify("logX", {}, SOURCE_OWNER, False) == SOURCE_OCR_OWNER
    assert classify("logX", {}, UNMODELED_TERMINUS, False) == UNMODELED_TERMINUS_B
    assert classify("logX", {}, CROSS_SHEET, False) == PARENT_CHILD_RECON
    assert classify("logX", {}, ENGINE_PLACED, False) == REPRESENTATIVE
    # held-back sub-split: empty corrected_sheets -> owner-confirm; join conflict -> termini-bound; else source-bind
    assert classify("logX", {"corrected_sheets": []}, HELD_BACK, False) == OWNER_CONFIRMATION
    assert classify("logX", {"corrected_sheets": [17, 20]}, HELD_BACK, True) == TERMINI_BOUND_JOIN
    assert classify("logX", {"corrected_sheets": [10, 13, 14]}, HELD_BACK, False) == SOURCE_BIND_ONLY


def test_defines_no_new_frame_or_render_math():
    src = PROOF.read_text(encoding="utf-8")
    # reuses shipped primitives; drives render proofs OUT-OF-PROCESS (subprocess), defines none of its own
    assert "import truelinev2.match.frames" in src
    assert "from truelinev2.proof.run_cross_sheet_frame_join_scout import" in src and "scout_log" in src
    assert "from truelinev2.proof.run_all_redlines_closure_ledger import" in src and "build_ledger" in src
    assert "subprocess.run(" in src
    top_defs = {ln.split("(")[0].strip() for ln in src.splitlines() if ln.startswith("def ")}
    for forbidden in ("def translate_between_sheets", "def order_chain_route", "def render_redline_stroke",
                      "def resolve_structure_position", "def scout_log", "def build_ledger",
                      "def solve_tick_path", "def parse_frame_equations"):
        assert forbidden not in top_defs
    assert REDLINE_STROKE_RGB == (220, 25, 25)


@pytest.mark.skipif(not os.path.isfile(PDF), reason="Brenham plan PDF not present")
@pytest.mark.skipif(os.environ.get("TL2_TRY_DRAW_E2E") != "1",
                    reason="heavy end-to-end (drives 12 render subprocesses); set TL2_TRY_DRAW_E2E=1 to run")
def test_end_to_end_full_sweep():
    import json
    rc = main()
    assert rc == 0
    data = json.loads((OUT_DIR / "full_dataset_try_draw_all_slice.json").read_text(encoding="utf-8"))
    assert data["verdict"] == "PASS" and data["result"] == R_COMPLETE
    assert data["universe_total"] == 58
    assert data["rendered_full"] == 11 and data["rendered_partial"] == 1 and data["not_rendered"] == 46
    assert data["category_counts"] == EXPECTED_PARTITION
    assert sorted(data["rendered_logs"], key=lambda s: int(s[3:])) == sorted(EXPECTED_RENDERED, key=lambda s: int(s[3:]))
    # NO FAKE POSITIVE: every rendered log has >=1 real PNG; every non-rendered has a reason + zero artifacts
    repo = Path(__file__).resolve().parent.parent.parent
    for m in data["manifest"]:
        if m["status"] in ("RENDERED_FULL", "RENDERED_PARTIAL"):
            assert m["artifacts"] and all((repo / a).is_file() for a in m["artifacts"])
        else:
            assert not m["artifacts"] and m["reason"]
    # placement / seam unchanged (diagnostic only)
    impact = data["placement_seam_ledger_impact"]
    assert impact["placed_before"] == 36 and impact["placed_after"] == 36
    assert sorted(impact["seam_eligible"]) == sorted(["log53", "log64", "log71", "log59", "log66"])
