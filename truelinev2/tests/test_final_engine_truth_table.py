"""M8.27 -- final engine truth-table proof tests (offline; pure + posture).

Pin the pure bucket-derivation, the banked reconciliation constants, the
OUT_OF_CLASS refinement, and the read-only posture (no placement/render/AUTO; no
engine module imports the proof). The live drift-guarded facts (58 rows, 59
review items, lane/census reconciliation, controls) are gated inside the runner
(G1-G14), as with the other v2 corpus probes.
"""
import inspect
from pathlib import Path
from types import SimpleNamespace

from truelinev2.proof import run_final_engine_truth_table as tt
from truelinev2.review.reviewer_payloads import ReviewerLane

PKG = Path(tt.__file__).resolve().parents[1]


def test_completion_bucket_is_one_to_one_for_contract_lanes():
    assert tt.completion_bucket(ReviewerLane.PLACED_REVIEW.value, "logX") == (
        tt.B_DRAWABLE, None)
    assert tt.completion_bucket(
        ReviewerLane.PICK_CARD_ROUTE_SUGGESTION.value, "logX") == (tt.B_PICK, None)
    assert tt.completion_bucket(
        ReviewerLane.HUMAN_ADJUSTABLE_LENGTH_REDLINE.value, "logX") == (
        tt.B_ADJUST, None)
    assert tt.completion_bucket(
        ReviewerLane.SOURCE_REVIEW_REQUIRED.value, "logX") == (tt.B_SOURCE, None)


def test_out_of_class_refinement_is_grounded_and_exact():
    # exactly the 4 OUT_OF_CLASS bores; 3 source/geo, log11 is a routing-order
    # pick-card (M8.7 MULTIPLE_PATHS_PICK_CARD, no source defect) -- review-
    # eligible NOW, NOT engine-blocked (M8.27 audit fix).
    assert set(tt.OUT_OF_CLASS_REFINE) == {"log43", "log44", "log68", "log11"}
    for b in ("log43", "log44", "log68"):
        assert tt.completion_bucket(ReviewerLane.OUT_OF_CLASS.value, b)[0] == \
            tt.B_SRC_KMZ
    assert tt.completion_bucket(ReviewerLane.OUT_OF_CLASS.value, "log11")[0] == \
        tt.B_PICK


def test_banked_constants_reconcile():
    assert sum(tt.BANKED_FULLEST_LANES.values()) == 58
    assert sum(tt.BANKED_STROKE_CENSUS.values()) == 58
    # PLACED == AUTO + REVIEW; statuses sum to 58
    s = tt.BANKED_DEFAULT_STATUS
    assert s["PLACED"] == s["AUTO_SELECT"] + s["REVIEW"] == 24
    assert s["AUTO_SELECT"] + s["REVIEW"] + s["ABSTAIN"] + s["ERROR"] == 58
    assert tt.BANKED_FULLEST_LANES["PLACED_REVIEW"] == 30


def test_controls_pin_two_axes_and_group_membership():
    # log8/log32/log42 product-PLACED but stroke STRUCTURE_IDENTITY; log8/32 in
    # the group card, log42 excluded.
    assert tt.CONTROLS["log8"] == (
        "PLACED_REVIEW", "STRUCTURE_IDENTITY_BINDING_REQUIRED", True)
    assert tt.CONTROLS["log42"] == (
        "PLACED_REVIEW", "STRUCTURE_IDENTITY_BINDING_REQUIRED", False)


def test_family_annotation_is_grouping_only():
    assert tt.KNOWN_FAMILIES == {"bore_log17": ("log43", "log44")}
    fam = SimpleNamespace(bore_id="log43", source_file="/x/bore_log43.xlsx")
    assert tt._family_of(fam) == "bore_log17"
    standalone = SimpleNamespace(bore_id="log7", source_file="/x/bore_log7.xlsx")
    assert tt._family_of(standalone) == "bore_log7"


def test_num_orders_numerically():
    assert tt._num("log8") == 8 and tt._num("log72") == 72


def test_read_only_posture_no_placement_no_render():
    src = inspect.getsource(tt)
    assert "truelinev2.render" not in src
    assert "render_redline_stroke" not in src
    assert 'OUT_DIR.glob("*.png")' in src              # G14 asserts zero PNGs
    # consumes the shipped contracts; never mutates them or invents AUTO
    assert "AUTO_SELECT" in src                        # reads the status, fine
    assert "status = Status.AUTO" not in src and "force" not in src.lower()


def test_no_engine_module_imports_the_proof():
    engine = (list((PKG / "match").glob("*.py"))
              + list((PKG / "review").glob("*.py")) + [PKG / "service.py"])
    for f in engine:
        assert "run_final_engine_truth_table" not in f.read_text(
            encoding="utf-8"), f
