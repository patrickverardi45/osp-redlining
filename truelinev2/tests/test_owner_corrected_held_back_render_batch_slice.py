"""OWNER-PACKET-2 owner-corrected HELD_BACK batch source-bind + render -- offline + PDF-gated tests.

Locks the slice's pure laws: the result/blocker enum; the five owner-corrected logs are exactly
{log11, log47, log67, log69, log70}; the full held-back class is the 8 {log11,36,47,52,58,67,69,70}; the
slice consumes the ENCODED owner-corrected identities (and only those) and never re-derives them; the
anchors are identity-only (no coordinate field); SPEC's per-endpoint sheets match the owner-confirmed
corrected_sheets; the render set is log69 ONLY (single-sheet [17], the render-safe member); the cross-sheet
partition is log47/log11 (source-backed join) vs log67/log70 (held, CONFLICTING); the seam is unchanged
(5 exemplars; ALL eight held-back refused -- nothing promoted); and the slice reuses the SHIPPED frame-join
primitive + the proven bind/render helpers and defines no new frame/join/render math. The heavy PDF binds/
renders are verified PDF-gated by running the proof: all five source-bind their termini, log47/log11 joins
are source-backed, log67/log70 joins are CONFLICTING (held), log69 renders ONE RED single-sheet stroke, the
other four are render-held with named blockers, and nothing is promoted.
"""
import os
from pathlib import Path

import pytest

import truelinev2.match.frames as FR
from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_brenham_corpus import PDF
from truelinev2.render.crop import REDLINE_STROKE_RGB
from truelinev2.seam import ELIGIBLE_EXEMPLARS
from truelinev2.proof.run_owner_corrected_held_back_render_batch_slice import (
    ALLOWED,
    CORRECTED,
    FULL_SOURCE_BIND,
    HELD_BACK_8,
    HELD_REASON,
    JOIN_HELD,
    R_PROVEN,
    RENDER_LOGS,
    SEAM_ELIGIBLE,
    SPEC,
    _has_coord_keys,
    _refuses_seam,
    main,
)

DOC = load_adjudication()
REC = {r["log_id"]: r for r in DOC["logs"]}
PROOF = Path(__file__).resolve().parent.parent / "proof" / \
    "run_owner_corrected_held_back_render_batch_slice.py"
OUT = Path(__file__).resolve().parent.parent.parent / "data" / "outputs" / \
    "owner_corrected_held_back_render_batch_slice"

# the owner-corrected encoded identities this slice consumes (the recipe must match the fixture)
ENCODED = {
    "log69": ("installer_hh", "1+45", "installer_hh", "4+54", [17]),
    "log47": ("flower_pot", "3+23", "installer_hh", "4+94", [10, 13, 14]),
    "log67": ("installer_hh", "1+45", "flower_pot", "4+14", [17, 20]),
    "log70": ("installer_hh", "1+45", "flower_pot", "2+15", [17, 20]),
    "log11": ("nextlink_hh", "21+63", "flower_pot", "6+30", [5, 17]),
}


def test_result_enum_exact():
    assert ALLOWED == {
        "OWNER_CORRECTED_HELD_BACK_BATCH_RENDER_PROVEN",
        "BLOCKED_OWNER_CORRECTED_BATCH_CENSUS_DRIFT",
        "BLOCKED_OWNER_CORRECTED_BATCH_ANCHORS_INVALID",
        "BLOCKED_OWNER_CORRECTED_BATCH_TERMINUS_BIND_FAILED",
        "BLOCKED_OWNER_CORRECTED_BATCH_JOIN_PARTITION_WRONG",
        "BLOCKED_OWNER_CORRECTED_BATCH_RENDER_NOT_SOURCE_BACKED",
        "BLOCKED_OWNER_CORRECTED_BATCH_SILENTLY_PROMOTED",
        "BLOCKED_OWNER_CORRECTED_BATCH_SCOPE_VIOLATION",
    }
    assert R_PROVEN in ALLOWED


def test_corrected_five_and_held_back_eight():
    assert CORRECTED == ("log11", "log47", "log67", "log69", "log70")
    assert HELD_BACK_8 == ("log11", "log36", "log47", "log52", "log58", "log67", "log69", "log70")
    # the held-back class is the closure-ledger HELD_BACK set: anchored AND seam-refused (not promoted)
    with_anchors = {b for b in REC if REC[b].get("endpoint_anchors")}
    held = tuple(sorted((l for l in with_anchors if _refuses_seam(l, REC)), key=lambda s: int(s[3:])))
    assert held == HELD_BACK_8
    # the five are a subset of the eight; the older three are covered by the other slice
    assert set(CORRECTED) < set(HELD_BACK_8)
    assert set(HELD_BACK_8) - set(CORRECTED) == {"log36", "log52", "log58"}


def test_consumes_the_encoded_identities_recipe_matches_fixture():
    for lid, (sc, sl, ec, el, sheets) in ENCODED.items():
        ea = REC[lid]["endpoint_anchors"]
        assert set(ea) == {"start", "end"}
        assert (ea["start"]["structure_class"], ea["start"]["station"]) == (sc, sl)
        assert (ea["end"]["structure_class"], ea["end"]["station"]) == (ec, el)
        assert list(REC[lid].get("corrected_sheets") or []) == sheets
        # the slice's bind recipe matches the encoded identity exactly (never re-derived)
        assert (SPEC[lid]["start"]["class"], SPEC[lid]["start"]["station"]) == (sc, sl)
        assert (SPEC[lid]["end"]["class"], SPEC[lid]["end"]["station"]) == (ec, el)
        assert SPEC[lid]["sheets"] == sheets


def test_anchors_are_identity_only_no_coordinates():
    for lid in CORRECTED:
        ea = REC[lid]["endpoint_anchors"]
        assert not _has_coord_keys(ea["start"]) and not _has_coord_keys(ea["end"])


def test_render_set_is_log69_only_single_sheet():
    assert RENDER_LOGS == ("log69",)
    assert SPEC["log69"].get("single_sheet") == 17 and SPEC["log69"]["sheets"] == [17]
    # the render-safe member is single-sheet; everything else stays multi-sheet (held)
    for lid in ("log47", "log67", "log70", "log11"):
        assert len(SPEC[lid]["sheets"]) >= 2


def test_partition_full_bind_vs_join_held():
    assert FULL_SOURCE_BIND == ("log47", "log11")          # termini bind + join source-backed
    assert JOIN_HELD == ("log67", "log70")                 # termini bind; join CONFLICTING
    # render-held logs each carry a non-empty named blocker
    for lid in ("log47", "log11", "log67", "log70"):
        assert HELD_REASON[lid]


def test_seam_unchanged_nothing_promoted():
    assert SEAM_ELIGIBLE == ("log53", "log64", "log71", "log59", "log66")
    assert tuple(ELIGIBLE_EXEMPLARS) == SEAM_ELIGIBLE
    for lid in HELD_BACK_8:
        assert _refuses_seam(lid, REC)                     # none of the eight is promoted into the seam


def test_reuses_shipped_primitives_defines_no_new_frame_or_render_math():
    assert FR.translate_between_sheets.__module__ == "truelinev2.match.frames"
    src = PROOF.read_text(encoding="utf-8")
    assert "import truelinev2.match.frames" in src
    assert "from truelinev2.proof.run_cross_sheet_frame_join_scout import" in src
    assert "scout_log" in src
    assert "order_chain_route" in src and "render_redline_stroke" in src
    top_defs = {ln.split("(")[0].strip() for ln in src.splitlines() if ln.startswith("def ")}
    for forbidden in ("def translate_between_sheets", "def translate_station_ft",
                      "def parse_frame_equations", "def build_frame_edges", "def order_chain_route",
                      "def scout_log", "def resolve_structure_position", "def resolve_nextlink_hh_callout",
                      "def render_redline_stroke", "def classify_record"):
        assert forbidden not in top_defs


def test_render_lane_is_red():
    src = PROOF.read_text(encoding="utf-8")
    assert "render_redline_stroke" in src and "REDLINE_STROKE_RGB" in src
    assert REDLINE_STROKE_RGB == (220, 25, 25)


@pytest.mark.skipif(not os.path.isfile(PDF), reason="Brenham plan PDF not present")
def test_end_to_end_proof_passes():
    rc = main()
    assert rc == 0
    import json
    data = json.loads((OUT / "owner_corrected_held_back_render_batch_slice.json").read_text(encoding="utf-8"))
    assert data["verdict"] == "PASS" and data["result"] == R_PROVEN
    assert data["passed_source_bind"] == ["log69", "log47", "log11"]
    assert data["passed_render"] == ["log69"]
    assert data["termini_bound_join_held"] == ["log67", "log70"]
    # exactly the one log69 single-sheet PNG was drawn (render-safe member only)
    assert sorted(data["artifacts"]) == ["log69_s17_redline_stroke.png"]
    pngs = sorted(p.name for p in OUT.glob("*.png"))
    assert pngs == ["log69_s17_redline_stroke.png"]
    # all five bound BOTH termini
    for lid in CORRECTED:
        assert data["binds"][lid]["start"]["xy"] is not None
        assert data["binds"][lid]["end"]["xy"] is not None
    # join partition: log47/log11 source-backed; log67/log70 CONFLICTING (held)
    assert data["cross_sheet_joins"]["log47"]["source_backed"] is True
    assert data["cross_sheet_joins"]["log11"]["source_backed"] is True
    for lid in ("log67", "log70"):
        assert data["cross_sheet_joins"][lid]["source_backed"] is False
        assert data["cross_sheet_joins"][lid]["blocker"] == "CONFLICTING_FRAME_EQUATIONS"
    # the abstain guard returned None (no raw fallback / no fake join)
    assert data["abstain_guard"]["translate_is_none"] is True
    # the render-held logs carry named blockers; nothing promoted
    for lid in ("log47", "log11", "log67", "log70"):
        assert data["held"][lid]
    assert data["no_seam_promotion"] is True and data["engine_census_frozen"] is True
