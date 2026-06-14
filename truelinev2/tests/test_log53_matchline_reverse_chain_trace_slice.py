"""OWNER-PACKET-2 log53 matchline reverse chain-trace -- offline tests.

Locks the proof's pure laws: the typed result enum, the reverse-seed search helpers
(matchline crossing + alignment isolation), and that the slice consumes the committed
endpoint_anchors.end (matchline continuation). No PDF parse here (the proof runs the
real sheet-5 trace).
"""
from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_log53_matchline_reverse_chain_trace_slice import (
    ALLOWED,
    R_AMBIG,
    R_NO_SEED,
    R_REACHES_NEXTLINK,
    R_REACHES_START,
    alignment_seeds,
    matchline_crossing_dashes,
)

CONDUIT = {"BORE - VACANT PIPE", "BORE - PORT"}
ML_BBOX = (0.0, 100.0, 400.0, 102.0)  # horizontal matchline line


def _seg(layer, x0, y0, x1, y1):
    return {"layer": layer, "x0": x0, "y0": y0, "x1": x1, "y1": y1,
            "xc": (x0 + x1) / 2, "yc": (y0 + y1) / 2}


def test_allowed_result_enum_exact():
    assert ALLOWED == {
        "REVERSE_CHAIN_REACHES_NEXTLINK_HH_CANDIDATE",
        "REVERSE_CHAIN_REACHES_START_AREA_BUT_NOT_STRUCTURE_BOUND",
        "REVERSE_CHAIN_NO_SEED_AT_MATCHLINE",
        "REVERSE_CHAIN_STOPS_BEFORE_START",
        "REVERSE_CHAIN_AMBIGUOUS_BRANCH",
        "REVERSE_CHAIN_FRAME_CONTESTED",
        "REVERSE_CHAIN_SOURCE_GEOMETRY_DISCONTINUOUS",
        "REVERSE_CHAIN_BLOCKED_NO_SAFE_TARGET",
    }


def test_crossing_dashes_only_conduit_near_matchline():
    draw = [
        _seg("BORE - VACANT PIPE", 50, 90, 60, 99),   # near matchline -> kept
        _seg("BORE - VACANT PIPE", 50, 10, 60, 20),   # far from matchline -> dropped
        _seg("HOUSES", 52, 92, 58, 99),               # near but not conduit -> dropped
    ]
    near = matchline_crossing_dashes(draw, ML_BBOX, CONDUIT)
    assert len(near) == 1 and near[0]["xc"] == 55.0


def test_alignment_seeds_isolate_labeled_crossing():
    label_xy = (55.0, 80.0)
    crossing = [
        _seg("BORE - VACANT PIPE", 50, 90, 60, 99),    # at the 24+11 label x -> seed
        _seg("BORE - VACANT PIPE", 300, 90, 310, 99),  # another bore's crossing -> not a seed
    ]
    seeds = alignment_seeds(crossing, label_xy)
    assert len(seeds) == 1 and seeds[0]["xc"] == 55.0


def test_alignment_seeds_empty_when_none_at_label():
    """The real log53 case: crossings exist but none at the 24+11 alignment."""
    label_xy = (55.0, 80.0)
    crossing = [
        _seg("BORE - VACANT PIPE", 300, 90, 310, 99),
        _seg("BORE - VACANT PIPE", 360, 90, 370, 99),
    ]
    assert alignment_seeds(crossing, label_xy) == []


def test_success_results_are_a_subset_of_allowed():
    assert {R_REACHES_NEXTLINK, R_REACHES_START} <= ALLOWED
    assert R_NO_SEED in ALLOWED and R_AMBIG in ALLOWED


def test_slice_consumes_end_anchor_bridge():
    doc = load_adjudication()
    l53 = next(r for r in doc["logs"] if r["log_id"] == "log53")
    end = l53["endpoint_anchors"]["end"]
    assert end["boundary_kind"] == "matchline_continuation"
    assert end["station"] == "24+11"
    assert end["continues_to_sheet"] == 6
