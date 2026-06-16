"""OWNER-PACKET-2 SOURCE_BINDABLE_HELD_BACK batch source-bind + render -- offline + PDF-gated tests.

Locks the slice's pure laws: the result/blocker enum; the held-back class is exactly {log36, log52, log58};
the slice consumes the ENCODED cross-sheet identities for log52 (flower_pot 0+98 -> 4+57) and log58
(installer_hh 39+79 -> 2+36) and only those; the anchors are identity-only (no coordinate field); log36 is
HELD with corrected_sheets == [] (owner confirmation of source-recovered sheet 17); the render set is
log52 ONLY (the render-safe member; log58 render is held); the seam is unchanged (5 exemplars; all three
held-back refused); and the slice reuses the SHIPPED frame-join primitive + the proven bind/render helpers
and defines no new frame/join math. The heavy PDF binds/renders are verified PDF-gated by running the proof:
both pairs source-bind, the joins are source-backed, log52 renders two RED sheet-local strokes, and log58's
sheet-10 12-vs-13 render ambiguity is proven (not rendered).
"""
import os
from pathlib import Path

import pytest

import truelinev2.match.frames as FR
from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_brenham_corpus import PDF
from truelinev2.render.crop import REDLINE_STROKE_RGB
from truelinev2.seam import ELIGIBLE_EXEMPLARS
from truelinev2.proof.run_source_bindable_held_back_render_slice import (
    ALLOWED,
    BIND,
    HELD_BACK_SET,
    R_PROVEN,
    RENDER_LEGS,
    RENDER_LOGS,
    SEAM_ELIGIBLE,
    _has_coord_keys,
    _refuses_seam,
    main,
)

DOC = load_adjudication()
REC = {r["log_id"]: r for r in DOC["logs"]}
PROOF = Path(__file__).resolve().parent.parent / "proof" / "run_source_bindable_held_back_render_slice.py"
OUT = Path(__file__).resolve().parent.parent.parent / "data" / "outputs" / \
    "source_bindable_held_back_render_slice"


def test_result_enum_exact():
    assert ALLOWED == {
        "SOURCE_BINDABLE_HELD_BACK_RENDER_PROVEN",
        "BLOCKED_HELD_BACK_CENSUS_DRIFT",
        "BLOCKED_HELD_BACK_ANCHORS_INVALID",
        "BLOCKED_HELD_BACK_TERMINUS_BIND_FAILED",
        "BLOCKED_HELD_BACK_CROSS_SHEET_JOIN_NOT_SOURCE_BACKED",
        "BLOCKED_HELD_BACK_RENDER_NOT_SOURCE_BACKED",
        "BLOCKED_HELD_BACK_SILENTLY_PROMOTED",
        "BLOCKED_HELD_BACK_SCOPE_VIOLATION",
    }
    assert R_PROVEN in ALLOWED


def test_held_back_class_is_exactly_the_eight():
    # after the owner-corrected cross-sheet bridges (log11/47/67/69/70, 2026-06-16) the held-back set is 8
    assert HELD_BACK_SET == ("log11", "log36", "log47", "log52", "log58", "log67", "log69", "log70")
    # the class is the closure ledger's HELD_BACK set: anchored AND seam-refused (not promoted)
    with_anchors = {b for b in REC if REC[b].get("endpoint_anchors")}
    held = tuple(sorted((l for l in with_anchors if _refuses_seam(l, REC)), key=lambda s: int(s[3:])))
    assert held == HELD_BACK_SET


def test_consumes_the_encoded_cross_sheet_identities():
    # log52 + log58 carry exactly the two structure-terminus anchors the bind recipe expects -- consumed,
    # never re-derived; and the recipe stations/classes match the owner-reviewed encoded anchors.
    for lid, (sc, sl, ec, el) in {
        "log52": ("flower_pot", "0+98", "flower_pot", "4+57"),
        "log58": ("installer_hh", "39+79", "installer_hh", "2+36"),
    }.items():
        ea = REC[lid]["endpoint_anchors"]
        assert set(ea) == {"start", "end"}
        assert (ea["start"]["structure_class"], ea["start"]["station"]) == (sc, sl)
        assert (ea["end"]["structure_class"], ea["end"]["station"]) == (ec, el)
        assert BIND[lid]["start"]["class"] == sc and BIND[lid]["start"]["label"] == sl
        assert BIND[lid]["end"]["class"] == ec and BIND[lid]["end"]["label"] == el


def test_anchors_are_identity_only_no_coordinates():
    for lid in ("log52", "log58"):
        ea = REC[lid]["endpoint_anchors"]
        assert not _has_coord_keys(ea["start"]) and not _has_coord_keys(ea["end"])


def test_log36_held_on_owner_confirmation():
    # sheet 17 is SOURCE-RECOVERED, not owner-recorded -> corrected_sheets == []; the anchor note names the
    # owner-confirmation requirement. log36 is anchored but seam-refused (held, not promoted).
    l36 = REC["log36"]
    assert l36.get("endpoint_anchors") and list(l36.get("corrected_sheets") or []) == []
    note = (str(l36["endpoint_anchors"]["start"].get("owner_note_text") or "")).upper()
    assert "SOURCE-RECOVERED" in note and "OWNER CONFIRMATION" in note
    assert _refuses_seam("log36", REC)


def test_render_set_is_log52_only():
    # the render-safe member is log52 only; log58 render is held (sheet-10 crossing ambiguity)
    assert RENDER_LOGS == ("log52",)
    assert "log58" not in RENDER_LOGS and "log36" not in RENDER_LOGS
    assert set(RENDER_LEGS) == {"log52"}
    # the two legs are the two owner-confirmed sheets, joined later by station identity
    assert [leg["sheet"] for leg in RENDER_LEGS["log52"]] == [7, 8]


def test_log52_corrected_sheets_are_owner_set_unlike_log36():
    # log52/log58 sheets are owner-confirmed SETS (so they may render); log36's sheet is recovered-only
    assert sorted(REC["log52"]["corrected_sheets"]) == [7, 8]
    assert sorted(REC["log58"]["corrected_sheets"]) == [10, 13]
    assert REC["log36"]["corrected_sheets"] == []


def test_seam_unchanged_nothing_promoted():
    assert SEAM_ELIGIBLE == ("log53", "log64", "log71", "log59", "log66")
    assert tuple(ELIGIBLE_EXEMPLARS) == SEAM_ELIGIBLE
    for lid in HELD_BACK_SET:
        assert _refuses_seam(lid, REC)        # none of the three is promoted into the seam


def test_reuses_shipped_primitives_defines_no_new_frame_math():
    # the cross-sheet join is the SHIPPED primitive; the slice defines no frame/join grammar of its own
    assert FR.translate_between_sheets.__module__ == "truelinev2.match.frames"
    src = PROOF.read_text(encoding="utf-8")
    assert "import truelinev2.match.frames" in src
    assert "from truelinev2.proof.run_cross_sheet_frame_join_scout import scout_log" in src
    top_defs = {ln.split("(")[0].strip() for ln in src.splitlines() if ln.startswith("def ")}
    for forbidden in ("def translate_between_sheets", "def translate_station_ft",
                      "def parse_frame_equations", "def build_frame_edges", "def order_chain_route",
                      "def resolve_structure_position", "def render_redline_stroke"):
        assert forbidden not in top_defs


def test_render_lane_is_red_and_present():
    # unlike the source-bind-only slices, this slice DOES render (log52) -- with the canonical RED stroke
    src = PROOF.read_text(encoding="utf-8")
    assert "render_redline_stroke" in src and "REDLINE_STROKE_RGB" in src
    assert REDLINE_STROKE_RGB == (220, 25, 25)


@pytest.mark.skipif(not os.path.isfile(PDF), reason="Brenham plan PDF not present")
def test_end_to_end_proof_passes():
    # the heavy read-only PDF binds/renders: both pairs source-bind, the joins are source-backed, log52
    # renders two RED sheet-local strokes, log58's render ambiguity is proven, nothing is promoted.
    rc = main()
    assert rc == 0
    report = OUT / "source_bindable_held_back_render_slice.json"
    import json
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["verdict"] == "PASS" and data["result"] == R_PROVEN
    assert data["passed_source_bind"] == ["log52", "log58"]
    assert data["passed_render"] == ["log52"]
    # exactly the two log52 sheet-local PNGs were drawn (render-safe member only)
    assert sorted(data["artifacts"]) == ["log52_s7_redline_stroke.png", "log52_s8_redline_stroke.png"]
    pngs = sorted(p.name for p in OUT.glob("*.png"))
    assert pngs == ["log52_s7_redline_stroke.png", "log52_s8_redline_stroke.png"]
    # both cross-sheet joins are source-backed; the abstain guard returned None (no raw fallback)
    assert all(data["cross_sheet_joins"][lid]["source_backed"] for lid in ("log52", "log58"))
    assert data["abstain_guard"]["translate_is_none"] is True
    # log58 render blocker is PROVEN from source (sheet-10 links both 12 and 13)
    assert data["log58_render_blocker"]["blocker_proven"] is True
    assert data["log58_render_blocker"]["sheet10_links_both_12_and_13"] is True
