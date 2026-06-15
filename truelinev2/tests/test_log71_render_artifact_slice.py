"""OWNER-PACKET-2 log71 render artifact -- offline tests.

Locks the pure render-route law for the bending sheet-24 leg: ``order_chain_route`` is the shortest
path through the drawn conduit chain (intra-dash + dash-gap edges), so it FOLLOWS THE DRAWN BEND
(an L, not a straight diagonal), invents no coordinate, anchors the exact proven endpoints, and
refuses (returns []) when the chain does not connect the two anchors. Also locks the result enum,
the canonical red color, log71-only sheet-local output naming, the 5+45-as-route-context invariant,
that the slice consumes log71's encoded identity, and that the proof is a contained artifact (no
product/API/match wiring). The PNG render itself is run by the proof against the real PDF; no
artifact is asserted/committed here.
"""
import math
from pathlib import Path

from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_log71_render_artifact_slice import (
    ALLOWED,
    BEND_MIN_RATIO,
    OUT_DIR,
    R_CREATED,
    order_chain_route,
    route_length,
)
from truelinev2.render.crop import REDLINE_STROKE_RGB


def test_result_enum_exact():
    assert ALLOWED == {
        "LOG71_RENDER_ARTIFACT_CREATED",
        "BLOCKED_LOG71_RENDER_ENDPOINT_MISMATCH",
        "BLOCKED_LOG71_RENDER_MATCHLINE_NOT_LOCATED",
        "BLOCKED_LOG71_RENDER_START_ROUTE_NOT_SOURCE_BACKED",
        "BLOCKED_LOG71_RENDER_END_ROUTE_NOT_SOURCE_BACKED",
        "BLOCKED_LOG71_RENDER_ARTIFACT_FAILED",
    }
    assert R_CREATED == "LOG71_RENDER_ARTIFACT_CREATED"


def test_canonical_red_only():
    assert REDLINE_STROKE_RGB == (220, 25, 25)


# a synthetic L-shaped conduit chain: up the left side (0,0)->(0,100), then right (0,100)->(100,100)
_L_CHAIN = [
    {"lines": [(0.0, 0.0, 0.0, 30.0)]},
    {"lines": [(0.0, 35.0, 0.0, 65.0)]},
    {"lines": [(0.0, 70.0, 0.0, 100.0)]},
    {"lines": [(0.0, 100.0, 30.0, 100.0)]},
    {"lines": [(35.0, 100.0, 65.0, 100.0)]},
    {"lines": [(70.0, 100.0, 100.0, 100.0)]},
]


def test_order_chain_route_follows_bend_not_diagonal():
    route = order_chain_route(_L_CHAIN, (0.0, 0.0), (100.0, 100.0))
    assert route[0] == (0.0, 0.0) and route[-1] == (100.0, 100.0)   # exact proven anchors
    assert len(route) >= 3
    straight = math.hypot(100.0, 100.0)                             # ~141.4
    assert route_length(route) >= straight * BEND_MIN_RATIO         # bends; never a diagonal shortcut
    assert any(abs(p[0]) < 1.0 and abs(p[1] - 100.0) < 1.0 for p in route)   # turns at the (0,100) corner


def test_order_chain_route_invents_no_coordinate():
    s, e = (0.0, 0.0), (100.0, 100.0)
    route = order_chain_route(_L_CHAIN, s, e)
    drawn = {(round(x, 1), round(y, 1))
             for seg in _L_CHAIN for ln in seg["lines"]
             for (x, y) in ((ln[0], ln[1]), (ln[2], ln[3]))}
    for p in route:
        assert p == s or p == e or (round(p[0], 1), round(p[1], 1)) in drawn


def test_order_chain_route_anchors_exact_endpoints():
    chain = [{"lines": [(0.0, 0.0, 0.0, 50.0)]}, {"lines": [(0.0, 50.0, 0.0, 100.0)]}]
    route = order_chain_route(chain, (0.0, 0.0), (0.0, 100.0))
    assert route[0] == (0.0, 0.0) and route[-1] == (0.0, 100.0)
    assert (0.0, 50.0) in route          # the real interior dash endpoint is kept


def test_order_chain_route_refuses_when_disconnected():
    # two dash islands separated by a gap > MAX_DASH_GAP: no source-connected path -> refuse
    chain = [{"lines": [(0.0, 0.0, 0.0, 20.0)]}, {"lines": [(0.0, 200.0, 0.0, 220.0)]}]
    assert order_chain_route(chain, (0.0, 0.0), (0.0, 220.0)) == []


def test_output_dir_is_gitignored_data_outputs():
    p = str(OUT_DIR).replace("\\", "/")
    assert "/data/outputs/log71_render_artifact" in p


def test_matchline_5_45_is_route_context_not_endpoint():
    doc = load_adjudication()
    l71 = next(r for r in doc["logs"] if r["log_id"] == "log71")
    ea = l71["endpoint_anchors"]
    assert set(ea) == {"start", "end"}                                 # no third anchor
    assert ea["start"]["station"] != "5+45" and ea["end"]["station"] != "5+45"
    assert "5+45" in ea["end"]["owner_note_text"].upper()              # preserved as route context


def test_slice_consumes_log71_encoded_identity():
    doc = load_adjudication()
    l71 = next(r for r in doc["logs"] if r["log_id"] == "log71")
    s, e = l71["endpoint_anchors"]["start"], l71["endpoint_anchors"]["end"]
    assert (s["structure_class"], s["station"]) == ("nextlink_hh", "7+50")
    assert (e["structure_class"], e["station"]) == ("flower_pot", "6+95")
    assert list(l71["corrected_sheets"]) == [23, 24]


def test_proof_is_contained_no_product_wiring():
    src = Path(__file__).resolve().parent.parent / "proof" / "run_log71_render_artifact_slice.py"
    text = src.read_text(encoding="utf-8")
    # contained artifact: uses the render.crop helper directly, never the product pipeline
    assert "truelinev2.service" not in text
    assert "truelinev2.api" not in text
    assert "from truelinev2.match" not in text
