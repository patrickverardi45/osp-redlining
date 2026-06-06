"""Item 1 (Slice A) — station-role evidence: PDF-free unit tests.

Locks the additive, EVIDENCE-ONLY station-role classifier
(``match_review_queue.station_role_evidence``) and its default-OFF wiring into
``build_review_reason``:
  - endpoint roles: equation_reset_origin / local_zero_reset / authored_endpoint_station /
    terminal_endpoint / interior_boundary_candidate
  - ``local_reset_continuation_risk`` TRUE on a log58-shaped fixture, FALSE on log56/log66 shapes
  - null-safety / purity
  - flag OFF => byte-identical (no ``station_roles`` key); flag ON => additive ONLY
    (code / message / missing / discriminators + every other evidence field unchanged;
     no artifact / drawn change)

NEVER asserts any draw/abstain/placement change — there is none.
"""
from __future__ import annotations

import copy

from backend.app.core.match_review_queue import (
    STATION_ROLE_FLAG,
    build_review_reason,
    station_role_evidence,
)


# ── fixtures shaped from the real resolved logs ──────────────────────────────
def _geo_log56():
    """Cross-sheet matchline-resolved; terminal endpoint structure bound (D24 standalone/safe)."""
    return {
        "geometry_status": "MATCHLINE_FRAME_RESOLVED",
        "frame": {"chainage_start_ft": 0.0, "chainage_end_ft": 276.0, "axis": "x",
                  "eqs_used": ["STA 4+57=0+00"], "multi_sheet": True},
        "matchline_resolution": {"status": "MATCHLINE_FRAME_RESOLVED", "class": "matchline_pair",
                                 "sheets": [17, 21], "boc_ft": 11.0, "hh_hh_ft": 276.0},
        "physical_anchor": {"resolved": True},
    }


def _geo_log66():
    """Single-sheet structure-connector; BOTH ends bound to authored HH structures (D24)."""
    return {
        "geometry_status": "STRUCTURE_CONNECTOR_RESOLVED",
        "frame": {"chainage_start_ft": 0.0, "chainage_end_ft": 55.0, "axis": "x",
                  "eqs_used": ["STA 45+33=0+00"], "multi_sheet": False},
        "physical_anchor": {"resolved": True,
                            "start": {"resolved": True}, "end": {"resolved": True}},
    }


def _geo_log58():
    """Cross-sheet HH_HH_DISTANCE: a leg distance, NO proven terminal end structure.
    D22: STA 2+36 is an INTERIOR boundary of bore_log24's 413' run -> continuation risk."""
    return {
        "geometry_status": "STATION_FRAME_RESOLVED",
        "frame": {"chainage_start_ft": 0.0, "chainage_end_ft": 236.0, "axis": "x",
                  "eqs_used": [], "multi_sheet": True},
        "matchline_resolution": {"status": "STATION_FRAME_RESOLVED", "class": "HH_HH_DISTANCE",
                                 "sheets": [10, 13], "boc_ft": 7.0, "hh_hh_ft": 236.0},
        # NOTE: no physical_anchor terminal binding -> end is an interior-boundary candidate.
    }


# ── role classification (pure helper) ────────────────────────────────────────
def test_equation_reset_origin_role():
    sr = station_role_evidence(_geo_log56())
    assert sr is not None
    assert sr["schema_version"] == "pdf-first-station-roles-1"
    assert sr["start"]["role"] == "equation_reset_origin"
    assert sr["equation_reset"] is True


def test_local_zero_reset_role():
    sr = station_role_evidence(_geo_log58())
    assert sr["start"]["role"] == "local_zero_reset"  # starts at local 0 with NO equation
    assert sr["equation_reset"] is False


def test_authored_endpoint_and_terminal_endpoint_roles():
    sr = station_role_evidence(_geo_log56())
    assert sr["end"]["role"] == "terminal_endpoint"
    # a non-zero authored start is NOT a reset; with a bound endpoint the end is terminal.
    sr2 = station_role_evidence({
        "geometry_status": "STATION_FRAME_RESOLVED",
        "frame": {"chainage_start_ft": 1263.0, "chainage_end_ft": 2071.0, "eqs_used": []},
        "physical_anchor": {"resolved": True},
    })
    assert sr2["start"]["role"] == "authored_endpoint_station"
    assert sr2["end"]["role"] == "terminal_endpoint"


def test_interior_boundary_candidate_role():
    sr = station_role_evidence(_geo_log58())
    assert sr["end"]["role"] == "interior_boundary_candidate"


# ── the D22 signal ───────────────────────────────────────────────────────────
def test_continuation_risk_true_on_log58_shape():
    sr = station_role_evidence(_geo_log58())
    assert sr["local_reset_continuation_risk"] is True
    assert "interior segment" in sr["note"]


def test_continuation_risk_false_on_log56_and_log66_shapes():
    assert station_role_evidence(_geo_log56())["local_reset_continuation_risk"] is False
    assert station_role_evidence(_geo_log66())["local_reset_continuation_risk"] is False


# ── null-safety / purity ─────────────────────────────────────────────────────
def test_null_safety_and_purity():
    assert station_role_evidence(None) is None
    assert station_role_evidence("nope") is None  # type: ignore[arg-type]
    assert station_role_evidence(123) is None  # type: ignore[arg-type]
    assert station_role_evidence({}) is None
    # malformed shapes never raise
    res = station_role_evidence({"frame": "x", "physical_anchor": ["y"], "matchline_resolution": 3})
    assert res is None or isinstance(res, dict)
    # pure: input is not mutated
    g = _geo_log58()
    before = copy.deepcopy(g)
    station_role_evidence(g)
    assert g == before


# ── default-OFF byte-identical / flag-ON additive-only ───────────────────────
def test_flag_off_is_byte_identical(monkeypatch):
    monkeypatch.delenv(STATION_ROLE_FLAG, raising=False)  # default OFF
    for geo in (_geo_log56(), _geo_log66(), _geo_log58()):
        rr = build_review_reason(geo)
        assert rr is not None
        assert "station_roles" not in rr["evidence"]


def test_flag_on_is_additive_only(monkeypatch):
    # ON adds ONLY evidence.station_roles; code/message/missing/discriminators + every other
    # evidence field are unchanged vs OFF (no draw/abstain/placement/artifact change).
    for geo in (_geo_log56(), _geo_log66(), _geo_log58()):
        monkeypatch.delenv(STATION_ROLE_FLAG, raising=False)
        off = build_review_reason(geo)
        monkeypatch.setenv(STATION_ROLE_FLAG, "1")
        on = build_review_reason(geo)
        assert "station_roles" not in off["evidence"]
        assert "station_roles" in on["evidence"]
        assert on["code"] == off["code"]
        assert on["message"] == off["message"]
        assert on["missing"] == off["missing"]
        assert on["discriminators"] == off["discriminators"]
        on_ev = {k: v for k, v in on["evidence"].items() if k != "station_roles"}
        assert on_ev == off["evidence"]  # every pre-existing evidence field byte-identical


def test_flag_on_log58_surfaces_continuation_risk(monkeypatch):
    monkeypatch.setenv(STATION_ROLE_FLAG, "1")
    rr = build_review_reason(_geo_log58())
    sr = rr["evidence"]["station_roles"]
    assert sr["local_reset_continuation_risk"] is True
    # the flag did NOT push the card into an abstain or change its placement-facing code.
    assert "abstain" not in rr["code"]


def test_no_artifact_or_drawn_change(monkeypatch):
    # station_roles must never introduce/alter any artifact / drawn / geometry signal.
    monkeypatch.setenv(STATION_ROLE_FLAG, "1")
    sr = build_review_reason(_geo_log56())["evidence"]["station_roles"]
    for k in ("artifact_name", "drawn", "coords", "coordinates", "geometry",
              "segments", "polyline", "path_xy", "lat", "lon"):
        assert k not in sr
