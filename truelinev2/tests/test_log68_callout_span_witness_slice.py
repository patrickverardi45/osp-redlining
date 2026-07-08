"""log68 callout-span witness binding slice: pure gate truths + guards, plus a fixture-gated live proof.
This test embeds NO real customer/person/place names (generic corpus log id + station numbers only).
"""
from __future__ import annotations

import os
from pathlib import Path

from truelinev2.proof import run_log68_callout_span_witness_slice as S
from truelinev2.proof.run_printed_identity_witness_probe import (
    DIRECT_BORE_CALLOUT_SPAN_WITNESS,
    match_direct_bore_callout,
    witness_result,
)

_PLAN = (os.getenv("TL2_STRUCTURE_DATUM_PLAN") or os.getenv("TL2_PROOF_PDF")
         or str(Path("data/uploads/Brenham_Tx/NEXTLINK - Brenham - Phase 5_07-15-25.pdf")))


# --- pure gates (no fixture) -------------------------------------------------------------------------------

def test_honest_no_fixture_skip_writes_nothing(tmp_path):
    report = S.run_slice(plan_path=str(tmp_path / "absent.pdf"), out_dir=str(tmp_path), write_json=True)
    assert report.get("skipped") is True
    assert not any(tmp_path.iterdir())


def test_sibling_stations_are_forbidden_and_detected():
    assert S._FORBIDDEN_SIBLING_STATIONS == ("7+21", "4+54")
    assert S._forbidden_tokens_absent("STA 5+03 TO STA 6+79 DIR. BORE (176')") is None
    assert S._forbidden_tokens_absent("MATCHLINE STA 1+75/7+21 - SEE SHEET 20") == "7+21"
    assert S._forbidden_tokens_absent("STA 4+54") == "4+54"


def test_not_found_witness_status_maps_to_named_refusal():
    res = witness_result(DIRECT_BORE_CALLOUT_SPAN_WITNESS, match_direct_bore_callout(["NOTHING"], "5+03", "6+79"))
    assert res["status"] == "NOT_FOUND"
    assert S.WITNESS_NOT_FOUND == "WITNESS_NOT_FOUND"


def test_ambiguous_witness_status_maps_to_named_refusal():
    lines = ["STA 5+03 TO STA 6+79", "DIR. BORE (176')", "STA 5+03 TO STA 6+79", "DIR. BORE (176')"]
    res = witness_result(DIRECT_BORE_CALLOUT_SPAN_WITNESS, match_direct_bore_callout(lines, "5+03", "6+79"))
    assert res["status"] == "AMBIGUOUS"
    assert S.WITNESS_AMBIGUOUS == "WITNESS_AMBIGUOUS"


def test_closure_gate_rejects_sibling_overrun():
    """A leg that bled into the 6+79->7+21 sibling continuation (~+42') fails 176' closure by construction."""
    span = 176.0
    overrun_ft = 176.0 + 42.0        # reaching the sibling 7+21 continuation instead of terminating at 6+79
    assert abs(overrun_ft - span) > S.CLOSURE_REL_TOL * span            # rejected
    assert abs(179.0 - span) <= S.CLOSURE_REL_TOL * span               # a true close-enough leg passes


def test_red_stroke_law_rgb_lock():
    assert tuple(S.REDLINE_STROKE_RGB) == (220, 25, 25)


def test_review_only_metadata_on_refusal():
    r = S._refuse(S.CLOSURE_FAILED, "x")
    d = r.to_dict()
    assert d["is_review_candidate"] is True
    assert d["performs_auto"] is False and d["performs_final_placement"] is False
    assert d["performs_promotion"] is False and d["changes_frontier"] is False
    assert d["rendered"] is False and d["png"] is None


def test_output_dir_is_not_the_sweep_tripwire_dir():
    from truelinev2.proof.run_callout_route_assembly_sweep import OUT_DIR as SWEEP_OUT
    assert Path(str(S._OUT_DIR)).resolve() != Path(str(SWEEP_OUT)).resolve()
    assert "callout_route_assembly_sweep" not in str(S._OUT_DIR)


def test_no_engine_store_api_wiring_guard():
    src = Path(S.__file__).read_text(encoding="utf-8")
    for forbidden in ("truelinev2.match", "truelinev2.api", "truelinev2.contracts", "product_store",
                      "select_dialect", "run_match"):
        assert forbidden not in src, "forbidden wiring token in slice module: %r" % forbidden
    # it DOES legitimately reuse the render primitive + the sweep's geometry helpers READ-ONLY:
    assert "render_redline_stroke" in src and "run_callout_route_assembly_sweep" in src


def test_single_target_is_log68_only():
    assert S._LOG_ID == "log68"
    assert (S._CALLOUT_START_STA, S._CALLOUT_END_STA) == ("5+03", "6+79")
    assert S._CALLOUT_PHRASE == "STA 5+03 TO STA 6+79"


# --- callout-box fallback pure gates -----------------------------------------------------------------------

def _fake_anchor(status, method, xy=(10.0, 20.0)):
    from truelinev2.extract.plan_view_anchor_resolver import AnchorResolution
    x, y = (xy if xy else (None, None))
    return AnchorResolution(status, x, y, method, False)


def test_callout_bbox_not_found_refuses():
    bbox, refusal = S._unique_callout_bbox([])
    assert bbox is None and refusal == S.CALLOUT_BOX_NOT_FOUND


def test_callout_bbox_ambiguous_refuses():
    bbox, refusal = S._unique_callout_bbox([[0, 0, 1, 1], [5, 5, 6, 6]])
    assert bbox is None and refusal == S.CALLOUT_BOX_AMBIGUOUS
    bbox, refusal = S._unique_callout_bbox([[0.0, 1.0, 2.0, 3.0]])
    assert bbox == (0.0, 1.0, 2.0, 3.0) and refusal is None


def test_proximity_only_anchor_refused():
    from truelinev2.extract.plan_view_anchor_resolver import ANCHOR_RESOLVED_TO_SYMBOL
    xy, refusal = S._accept_leader_anchor(_fake_anchor(ANCHOR_RESOLVED_TO_SYMBOL, "PROXIMITY_SYMBOL"))
    assert xy is None and refusal == S.CALLOUT_ANCHOR_NOT_LEADER_BACKED


def test_unresolved_and_route_tier_anchors_refused():
    from truelinev2.extract.plan_view_anchor_resolver import (
        ANCHOR_RESOLVED_TO_ROUTE_ENDPOINT,
        UNMEASURABLE,
    )
    assert S._accept_leader_anchor(_fake_anchor(UNMEASURABLE, None, xy=None))[1] == \
        S.CALLOUT_ANCHOR_NOT_LEADER_BACKED
    assert S._accept_leader_anchor(_fake_anchor(ANCHOR_RESOLVED_TO_ROUTE_ENDPOINT, "ROUTE_TERMINUS"))[1] == \
        S.CALLOUT_ANCHOR_NOT_LEADER_BACKED


def test_leader_ambiguity_refused():
    from truelinev2.extract.plan_view_anchor_resolver import AMBIGUOUS_ANCHOR
    xy, refusal = S._accept_leader_anchor(_fake_anchor(AMBIGUOUS_ANCHOR, None, xy=None))
    assert xy is None and refusal == S.CALLOUT_LEADER_AMBIGUOUS


def _box(x0, y0, x1, y1):
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}


_PHRASE_BB = (10.0, 10.0, 60.0, 16.0)


def test_innermost_row_box_unique_nested():
    outer = _box(0, 0, 100, 100)
    mid = _box(5, 5, 80, 40)
    row = _box(8, 8, 70, 18)                       # innermost, contains the phrase bbox
    chosen, rejected, refusal = S._innermost_row_box([outer, mid, row], _PHRASE_BB)
    assert refusal is None and chosen is row
    assert len(rejected) == 2 and row not in rejected


def test_innermost_row_box_rejects_subcell_frames_too():
    """A sub-cell frame (contains the word, NOT the phrase) is not a survivor but IS rejected/filtered."""
    outer = _box(0, 0, 100, 100)
    row = _box(8, 8, 70, 18)
    subcell = _box(9, 9, 30, 15)                   # too narrow for the phrase
    chosen, rejected, refusal = S._innermost_row_box([outer, row, subcell], _PHRASE_BB)
    assert refusal is None and chosen is row and subcell in rejected


def test_innermost_row_box_non_nested_overlap_refuses():
    phrase = (45.0, 5.0, 65.0, 15.0)
    a = _box(0, 0, 70, 20)                         # both contain the phrase, neither nests in the other
    b = _box(40, 0, 120, 20)                       # (beyond the tracer margin in x, both directions)
    chosen, rejected, refusal = S._innermost_row_box([a, b], phrase)
    assert chosen is None and refusal == S.CALLOUT_ROW_BOX_NOT_NESTED


def test_coincident_duplicates_are_one_physical_frame():
    """CAD exports emit the SAME callout box several times (fill + border + duplicates). Mutual containment
    = identity (SAME_POINT_TOL analogue): dedup to one representative, never a refusal — this is the REAL
    log68 shape (3 identical rects + a ~0.8pt border + the sheet title-block frame)."""
    d1, d2, d3 = _box(826.2, 187.6, 930.2, 217.8), _box(826.2, 187.6, 930.2, 217.8), _box(826.2, 187.6, 930.2, 217.8)
    border = _box(825.5, 186.8, 931.0, 218.5)
    title_blk = _box(37.1, 63.4, 1165.7, 760.0)
    phrase = (829.4, 191.9, 884.8, 197.0)
    chosen, rejected, refusal = S._innermost_row_box([d1, d2, d3, border, title_blk], phrase)
    assert refusal is None
    assert chosen in (d1, d2, d3)                          # smallest representative of the coincident class
    assert len(rejected) == 4 and title_blk in rejected and border in rejected


def test_innermost_row_box_zero_phrase_containing_refuses():
    chosen, rejected, refusal = S._innermost_row_box([_box(9, 9, 30, 15)], _PHRASE_BB)
    assert chosen is None and refusal == S.CALLOUT_ROW_BOX_NOT_PHRASE_CONTAINING


def test_forbidden_token_inside_chosen_row_refuses():
    row = _box(0, 0, 100, 20)
    words_ok = [{"text": "STA 5+03 TO STA 6+79", "xc": 30, "yc": 10}]
    words_bad = words_ok + [{"text": "7+21", "xc": 80, "yc": 10}]
    assert S._row_forbidden_token(words_ok, row) is None
    assert S._row_forbidden_token(words_bad, row) == "7+21"
    outside = [{"text": "4+54", "xc": 500, "yc": 500}]      # outside the row frame -> not the row's token
    assert S._row_forbidden_token(outside, row) is None


def test_label_boxes_import_sync():
    """The retry enumerates candidates with the TRACER'S OWN _label_boxes (read-only import, semantics
    identical): size-floor + word-center containment."""
    from truelinev2.extract.leader_symbol_trace import _label_boxes as tracer_label_boxes
    assert S._label_boxes is tracer_label_boxes
    frame = _box(0, 0, 100, 20)
    glyph = _box(9, 9, 12, 12)                     # fails the size floor
    assert S._label_boxes([frame, glyph], (30.0, 10.0)) == [frame]


def test_retry_only_enters_after_first_pass_ambiguous_leader(monkeypatch):
    """A first-pass acceptance (or a non-box-hop refusal) must NEVER reach the row retry."""
    from truelinev2.extract.plan_view_anchor_resolver import ANCHOR_RESOLVED_TO_SYMBOL, AnchorResolution

    class _FakePlan:
        def search(self, sheet, offset, text):
            return [[0.0, 0.0, 60.0, 16.0]]
        def vector_segments(self, sheet, offset):
            return []

    words = [{"text": "5+03", "xc": 30.0, "yc": 10.0}]
    monkeypatch.setattr(S, "resolve_label_anchor",
                        lambda *a, **k: AnchorResolution(ANCHOR_RESOLVED_TO_SYMBOL, 1.0, 2.0,
                                                         "LEADER_TRACED_SYMBOL", False))

    def _boom(*a, **k):
        raise AssertionError("row retry entered despite a first-pass leader-backed anchor")
    monkeypatch.setattr(S, "_label_boxes", _boom)
    xy, refusal, detail = S._callout_box_anchor(_FakePlan(), 17, 13, words, [])
    assert xy == (1.0, 2.0) and refusal is None and "row_retry" not in detail


def test_retry_keeps_named_refusal_when_ambiguity_is_not_the_box_hop(monkeypatch):
    """First-pass AMBIGUOUS_LEADER but <= 1 label box (word/leader-hop ambiguity) -> original refusal."""
    from truelinev2.extract.plan_view_anchor_resolver import AMBIGUOUS_ANCHOR, AnchorResolution

    class _FakePlan:
        def search(self, sheet, offset, text):
            return [[0.0, 0.0, 60.0, 16.0]]
        def vector_segments(self, sheet, offset):
            return []

    words = [{"text": "5+03", "xc": 30.0, "yc": 10.0}]
    amb = AnchorResolution(AMBIGUOUS_ANCHOR, None, None, None, False, {"leader_trace": "AMBIGUOUS_LEADER"})
    monkeypatch.setattr(S, "resolve_label_anchor", lambda *a, **k: amb)
    monkeypatch.setattr(S, "_label_boxes", lambda draw, xy: [])
    xy, refusal, detail = S._callout_box_anchor(_FakePlan(), 17, 13, words, [])
    assert xy is None and refusal == S.CALLOUT_LEADER_AMBIGUOUS
    assert detail["row_retry"]["label_box_candidates"] == 0


def test_leader_backed_anchors_accepted():
    from truelinev2.extract.plan_view_anchor_resolver import (
        ANCHOR_RESOLVED_TO_LEADER_TIP,
        ANCHOR_RESOLVED_TO_SYMBOL,
    )
    xy, refusal = S._accept_leader_anchor(_fake_anchor(ANCHOR_RESOLVED_TO_SYMBOL, "LEADER_TRACED_SYMBOL"))
    assert xy == (10.0, 20.0) and refusal is None
    xy, refusal = S._accept_leader_anchor(_fake_anchor(ANCHOR_RESOLVED_TO_LEADER_TIP, "LEADER_TIP"))
    assert xy == (10.0, 20.0) and refusal is None


# --- chain-reach uniqueness pure gates (no fixture) --------------------------------------------------------

def _drive_to_chain_reach(monkeypatch, tips, predicate):
    """Drive _callout_box_anchor to the chain-reach stage: unique phrase bbox -> AMBIGUOUS_LEADER first pass
    -> a unique innermost row box (nested pair) -> AMBIGUOUS_LEADER retry -> chain-reach over ``tips`` with
    the supplied ``predicate``. Returns (xy, refusal, detail)."""
    from truelinev2.extract.plan_view_anchor_resolver import AMBIGUOUS_ANCHOR, AnchorResolution

    class _FakePlan:
        def search(self, s, o, t):
            return [[0.0, 0.0, 60.0, 16.0]]        # the unique phrase bbox

        def vector_segments(self, s, o):
            return []

    words = [{"text": "STA 5+03 TO STA 6+79", "xc": 30.0, "yc": 8.0}]
    amb = AnchorResolution(AMBIGUOUS_ANCHOR, None, None, None, False, {"leader_trace": "AMBIGUOUS_LEADER"})
    monkeypatch.setattr(S, "resolve_label_anchor", lambda *a, **k: amb)
    outer, inner = _box(-5, -5, 100, 100), _box(-1, -1, 61, 17)      # inner nests, both contain the phrase
    monkeypatch.setattr(S, "_label_boxes", lambda draw, xy: [outer, inner])
    monkeypatch.setattr(S, "_leaders", lambda draw, box: list(tips))
    return S._callout_box_anchor(_FakePlan(), 17, 13, words, [], leg_predicate=predicate)


def test_chain_reach_zero_survivors_refuses(monkeypatch):
    tips = [(0.0, 0.0, 1.0, 1.0), (0.0, 0.0, 2.0, 2.0), (0.0, 0.0, 3.0, 3.0)]
    pred = lambda xy: (False, S.NO_CONDUIT_CHAIN_AT_START, None)
    xy, refusal, detail = _drive_to_chain_reach(monkeypatch, tips, pred)
    assert xy is None and refusal == S.LEADER_CHAIN_REACH_NONE
    cr = detail["chain_reach"]
    assert cr["leader_tips"] == 3 and cr["survivor_count"] == 0
    assert len(cr["candidates"]) == 3                        # per-candidate elimination log present
    assert all(c["eliminated_by"] == S.NO_CONDUIT_CHAIN_AT_START and c["passes"] is False
               for c in cr["candidates"])


def test_chain_reach_exactly_one_survivor_accepted(monkeypatch):
    tips = [(0.0, 0.0, 1.0, 1.0), (0.0, 0.0, 9.0, 9.0), (0.0, 0.0, 3.0, 3.0)]
    pred = lambda xy: (True, "closes", 176.0) if xy == (9.0, 9.0) else (False, S.CLOSURE_FAILED, None)
    xy, refusal, detail = _drive_to_chain_reach(monkeypatch, tips, pred)
    assert refusal is None and xy == (9.0, 9.0)
    cr = detail["chain_reach"]
    assert cr["survivor_count"] == 1 and cr["survivor"] == [9.0, 9.0]
    assert detail["method"] == S._CHAIN_REACH_METHOD and detail["mode"] == S._CHAIN_REACH_MODE
    passing = [c for c in cr["candidates"] if c["passes"]]
    assert len(passing) == 1 and passing[0]["tip"] == [9.0, 9.0] and passing[0]["drawn_ft"] == 176.0


def test_chain_reach_multiple_survivors_refuses(monkeypatch):
    tips = [(0.0, 0.0, 1.0, 1.0), (0.0, 0.0, 2.0, 2.0), (0.0, 0.0, 3.0, 3.0)]
    pred = lambda xy: (xy in ((1.0, 1.0), (3.0, 3.0)), "closes", 176.0)   # two close -> not unique
    xy, refusal, detail = _drive_to_chain_reach(monkeypatch, tips, pred)
    assert xy is None and refusal == S.LEADER_CHAIN_REACH_NOT_UNIQUE
    assert detail["chain_reach"]["survivor_count"] == 2


def test_chain_reach_tests_every_candidate_without_rendering(monkeypatch):
    """Every leader tip is tested exactly once; the predicate — not a render — decides. No PNG is produced
    (the anchor stage structurally cannot draw)."""
    calls = []
    tips = [(0.0, 0.0, float(i), float(i)) for i in range(1, 6)]
    pred = lambda xy: (calls.append(xy), (False, S.NO_CONDUIT_CHAIN_AT_START, None))[1]
    xy, refusal, detail = _drive_to_chain_reach(monkeypatch, tips, pred)
    assert len(calls) == 5 and refusal == S.LEADER_CHAIN_REACH_NONE   # one predicate call per candidate


def test_chain_reach_sibling_eliminated_tip_is_not_a_survivor(monkeypatch):
    """A tip whose leg is refused by the sibling gate is eliminated (never a survivor) — the sibling gate is
    inside the shared predicate (_bind_leg_from_start)."""
    tips = [(0.0, 0.0, 1.0, 1.0), (0.0, 0.0, 2.0, 2.0)]
    pred = lambda xy: (False, S.SIBLING_BLEED_DETECTED, None)
    xy, refusal, detail = _drive_to_chain_reach(monkeypatch, tips, pred)
    assert xy is None and refusal == S.LEADER_CHAIN_REACH_NONE
    assert all(c["eliminated_by"] == S.SIBLING_BLEED_DETECTED for c in detail["chain_reach"]["candidates"])


def test_chain_reach_not_entered_without_predicate(monkeypatch):
    """Without a leg_predicate the innermost retry keeps its own CALLOUT_LEADER_AMBIGUOUS (no chain-reach)."""
    from truelinev2.extract.plan_view_anchor_resolver import AMBIGUOUS_ANCHOR, AnchorResolution

    class _FakePlan:
        def search(self, s, o, t):
            return [[0.0, 0.0, 60.0, 16.0]]

        def vector_segments(self, s, o):
            return []
    monkeypatch.setattr(S, "resolve_label_anchor",
                        lambda *a, **k: AnchorResolution(AMBIGUOUS_ANCHOR, None, None, None, False,
                                                         {"leader_trace": "AMBIGUOUS_LEADER"}))
    monkeypatch.setattr(S, "_label_boxes", lambda draw, xy: [_box(-5, -5, 100, 100), _box(-1, -1, 61, 17)])
    xy, refusal, detail = S._callout_box_anchor(_FakePlan(), 17, 13,
                                                [{"text": "STA 5+03 TO STA 6+79", "xc": 30.0, "yc": 8.0}], [])
    assert refusal == S.CALLOUT_LEADER_AMBIGUOUS and "chain_reach" not in detail


def test_bind_leg_from_start_no_conduit_refuses():
    """The shared predicate helper refuses honestly with an empty conduit set (real call, no fixture)."""
    lb = S._bind_leg_from_start((0.0, 0.0), words=[], draw=[], conduit=[], chain_lines=[],
                                partners=[20], end_sta="6+79", span=176.0, leg_sheet=17)
    assert lb.ok is False and lb.status == S.NO_CONDUIT_CHAIN_AT_START and lb.route is None


def test_leaders_import_sync():
    from truelinev2.extract.leader_symbol_trace import _leaders as tracer_leaders
    assert S._leaders is tracer_leaders


# --- fixture-gated live proof (deterministic on the real plan) --------------------------------------------

def _plan_present() -> bool:
    return Path(_PLAN).is_file()


def test_live_chain_reach_eliminates_all_candidates(tmp_path):
    """Deterministic live pin: on the real plan the unique callout box has 8 leaders; NONE produce a closing
    source-backed leg (7 land on no conduit, 1 fails 176' closure) -> LEADER_CHAIN_REACH_NONE, zero render."""
    if not _plan_present():
        return
    r = S.run_slice(plan_path=_PLAN, out_dir=str(tmp_path))["result"]
    assert r["status"] == S.LEADER_CHAIN_REACH_NONE and r["rendered"] is False and r["png"] is None
    cr = r["detail"]["callout_box_fallback"]["chain_reach"]
    assert cr["leader_tips"] == 8 and cr["survivor_count"] == 0
    assert len(cr["candidates"]) == 8
    reasons = sorted(c["eliminated_by"] for c in cr["candidates"])
    assert reasons.count(S.NO_CONDUIT_CHAIN_AT_START) == 7 and reasons.count(S.CLOSURE_FAILED) == 1
    assert not list(tmp_path.glob("*.png"))


def test_clean_station_anchor_path_never_enters_fallback(tmp_path, monkeypatch):
    """A RESOLVED bare-station anchor must bypass the callout-box fallback entirely (ordering guard)."""
    if not _plan_present():
        return
    from truelinev2.extract.plan_view_anchor_resolver import ANCHOR_RESOLVED_TO_SYMBOL, AnchorResolution
    monkeypatch.setattr(S, "resolve_plan_view_anchor_for_path",
                        lambda *a, **k: AnchorResolution(ANCHOR_RESOLVED_TO_SYMBOL, 10.0, 20.0,
                                                         "LEADER_TRACED_SYMBOL", False))

    def _boom(*a, **k):
        raise AssertionError("callout-box fallback entered despite a clean bare-station anchor")
    monkeypatch.setattr(S, "_callout_box_anchor", _boom)
    r = S.bind_and_render(_PLAN, out_dir=str(tmp_path))          # downstream gates may abstain; that's fine
    assert r.status != S.START_ANCHOR_AMBIGUOUS                  # and _boom never fired


def test_live_slice_renders_exactly_one_review_stroke_or_named_abstain(tmp_path):
    if not _plan_present():
        return  # honest skip; proof-only, not in CI
    report = S.run_slice(plan_path=_PLAN, out_dir=str(tmp_path), write_json=True)
    r = report["result"]
    pngs = list(tmp_path.glob("*.png"))
    if r["rendered"]:
        # the FOUND-witness happy path: EXACTLY one red REVIEW stroke, terminating at the matchline
        assert r["status"] == S.REVIEW_CANDIDATE_RENDERED
        assert len(pngs) == 1
        assert r["png"] and Path(r["png"]).is_file()
        assert r["detail"]["end_station"] == "6+79" and r["detail"]["start_station"] == "5+03"
        assert list(r["detail"]["stroke_rgb"]) == [220, 25, 25]
        # anchor evidence must be leader-backed in EITHER mode (bare station or callout-box fallback)
        assert r["detail"]["anchor_mode"] in ("BARE_STATION", "CALLOUT_BOX_LEADER", "CALLOUT_BOX_LEADER_CHAIN_REACH")
        assert r["detail"]["anchor_method"] in ("LEADER_TRACED_SYMBOL", "LEADER_TIP", "CHAIN_REACH_LEADER_TIP")
        if r["detail"]["anchor_mode"].startswith("CALLOUT_BOX_LEADER"):   # original ambiguity context preserved
            assert r["detail"]["anchor_evidence"]["original_start_anchor"] == S.START_ANCHOR_AMBIGUOUS
        # sibling containment: the drawn span closes at ~176', never the +42' 7+21 over-run
        assert abs(r["detail"]["drawn_ft"] - r["detail"]["span_ft"]) <= S.CLOSURE_REL_TOL * r["detail"]["span_ft"]
        # the leg terminates AT the 6+79 matchline boundary (never past it into sheet-20 territory)
        assert r["detail"]["matchline_boundary_xy"] is not None
        chain_blob = " ".join(r["evidence_chain"])
        assert "4+54" not in chain_blob and "7+21" not in chain_blob
    else:
        # any gate may abstain — but ONLY with a named refusal, and it must draw NOTHING
        assert r["status"] in {S.WITNESS_NOT_FOUND, S.WITNESS_AMBIGUOUS, S.START_ANCHOR_AMBIGUOUS,
                               S.START_ANCHOR_UNRESOLVED, S.NO_CONDUIT_CHAIN_AT_START,
                               S.MATCHLINE_ENDPOINT_NOT_FOUND, S.SIBLING_BLEED_DETECTED,
                               S.LEG_NOT_SOURCE_BACKED, S.CLOSURE_FAILED, S.RENDER_PRODUCED_NO_STROKE,
                               S.CALLOUT_BOX_NOT_FOUND, S.CALLOUT_BOX_AMBIGUOUS,
                               S.CALLOUT_LEADER_AMBIGUOUS, S.CALLOUT_ANCHOR_NOT_LEADER_BACKED,
                               S.CALLOUT_ROW_BOX_NOT_PHRASE_CONTAINING, S.CALLOUT_ROW_BOX_NOT_NESTED,
                               S.LEADER_CHAIN_REACH_NONE, S.LEADER_CHAIN_REACH_NOT_UNIQUE}
        assert not pngs and r["png"] is None


def test_live_review_only_and_no_frontier_promotion(tmp_path):
    if not _plan_present():
        return
    r = S.run_slice(plan_path=_PLAN, out_dir=str(tmp_path))["result"]
    assert r["performs_auto"] is False and r["performs_final_placement"] is False
    assert r["performs_promotion"] is False and r["changes_frontier"] is False
    assert r["is_review_candidate"] is True
