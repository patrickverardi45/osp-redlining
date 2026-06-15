"""OWNER-PACKET-2 log53 conduit-layer coverage -- offline tests.

Locks: the additive lateral-coverage constant (BORE - LATERAL only) is SEPARATE from the
frozen base conduit table; the result enum; and the seed principle (a lateral run connected
to the start footprint extends the connected_chain toward the matchline where base-only does
not). No PDF parse here (the proof runs the real sheet-5 coverage).
"""
from truelinev2.extract.conduit_topology import connected_chain, dash_endpoints
from truelinev2.extract.structure_position import (
    BRENHAM_CONDUIT_LAYERS,
    BRENHAM_LATERAL_CONDUIT_LAYERS,
)
from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_log53_conduit_layer_coverage_slice import (
    ALLOWED,
    R_CONFIRMED,
    R_NOT_CONNECTED,
    R_NO_SEED,
    R_PARTIAL,
)


def _seg(layer, x0, y0, x1, y1):
    return {"layer": layer, "x0": min(x0, x1), "y0": min(y0, y1),
            "x1": max(x0, x1), "y1": max(y0, y1),
            "xc": (x0 + x1) / 2, "yc": (y0 + y1) / 2, "lines": [(x0, y0, x1, y1)]}


# --- additive constant invariants (census safety) -------------------------------
def test_base_conduit_table_frozen():
    assert dict(BRENHAM_CONDUIT_LAYERS) == {"VACANT HDPE": "BORE - VACANT PIPE",
                                            "TERMINAL TAIL": "BORE - PORT"}
    # the new coverage layers are NOT in the frozen base table
    assert "BORE - LATERAL" not in BRENHAM_CONDUIT_LAYERS.values()
    assert "BORE - PATH" not in BRENHAM_CONDUIT_LAYERS.values()


def test_lateral_coverage_is_additive_and_lateral_only():
    assert dict(BRENHAM_LATERAL_CONDUIT_LAYERS) == {"LATERAL HDPE": "BORE - LATERAL"}
    # BORE - PATH is deliberately excluded (not connected to log53's start)
    assert "BORE - PATH" not in BRENHAM_LATERAL_CONDUIT_LAYERS.values()
    # base and lateral sets are disjoint
    assert set(BRENHAM_CONDUIT_LAYERS.values()).isdisjoint(BRENHAM_LATERAL_CONDUIT_LAYERS.values())


def test_result_enum_exact():
    assert ALLOWED == {
        "CONDUIT_LAYER_COVERAGE_CONFIRMED",
        "CONDUIT_LAYER_PARTIAL_COVERAGE_CONFIRMED",
        "BLOCKED_LAYER_TOO_BROAD",
        "BLOCKED_LAYER_NOT_CONNECTED_TO_START",
        "BLOCKED_LAYER_AMBIGUOUS",
        "BLOCKED_NO_SAFE_CONDUIT_SEED",
    }
    assert {R_CONFIRMED, R_PARTIAL, R_NOT_CONNECTED, R_NO_SEED} <= ALLOWED


# --- seed principle: lateral extends the chain toward the matchline --------------
def test_lateral_extends_chain_where_base_does_not():
    fp = (678.0, 438.0, 682.0, 444.0)  # bound start NEXTLINK HH footprint
    port = _seg("BORE - PORT", 680, 444, 680, 500)        # base: only runs DOWN from start
    lateral = _seg("BORE - LATERAL", 680, 438, 680, 85)   # lateral: runs UP toward matchline (y85)

    base_eps = dash_endpoints(connected_chain([port], fp))
    ext_eps = dash_endpoints(connected_chain([port, lateral], fp))
    base_min_y = min(p[1] for p in base_eps)
    ext_min_y = min(p[1] for p in ext_eps)

    assert base_min_y == 444.0            # base-only never reaches toward the matchline
    assert ext_min_y == 85.0              # base|lateral reaches the matchline band
    assert ext_min_y < base_min_y - 35.0  # the seed law: lateral adds real reach


def test_lateral_not_connected_yields_no_extension():
    fp = (678.0, 438.0, 682.0, 444.0)
    far_lateral = _seg("BORE - LATERAL", 900, 438, 900, 85)  # exists but far from the start
    chain = connected_chain([far_lateral], fp)
    assert chain == []  # disconnected lateral provides no seed


# --- bridge consumption ----------------------------------------------------------
def test_slice_consumes_start_anchor_bridge():
    doc = load_adjudication()
    l53 = next(r for r in doc["logs"] if r["log_id"] == "log53")
    start = l53["endpoint_anchors"]["start"]
    assert start["structure_class"] == "nextlink_hh"
    assert start["station"] == "21+63"
