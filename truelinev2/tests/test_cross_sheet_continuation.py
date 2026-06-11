"""M8.16 -- tests pinning the cross_sheet_origin discovery law (synthetic).

Locks: the note-scoped footage law (footage found deep in its OWN note;
never grabbed across the next run-callout line); the collectors' printed
report shape; every discovery refusal is typed with its evidence class
named (no callout / full-span / no equation / ambiguous equations / no
reciprocal / closure / unmapped conduit class / no reaching structure);
the conduit layer derives ONLY from the printed notes via the dialect
table; rival far-sheet structures bind ONLY when the banked corroboration
band leaves EXACTLY ONE survivor (0 or >= 2 abstain -- corroboration
refuses, never selects); success carries the far sheet, layer, and printed
provenance verbatim; no AUTO exists anywhere in the lane taxonomy."""
from __future__ import annotations

from types import SimpleNamespace

from truelinev2.extract.matchline_join import (
    CHAIN_AMBIGUOUS,
    CHAIN_NONE,
    CHAIN_UNIQUE,
    assemble_callout_chain,
    find_run_callout_footage,
    find_run_callout_to,
    run_callouts_ending_at,
    run_callouts_starting_at,
)
from truelinev2.extract.structure_position import BRENHAM_LANE_DIALECT
from truelinev2.match.symbol_conduit_lane import (
    CS_AMBIGUOUS,
    CS_BOUND,
    CS_REFUSED,
    STATUSES,
    discover_cross_sheet_start,
)

# --- the note-scoped footage law -------------------------------------------------------

NOTE_E = ["STA 2+70 TO STA 2+87", "E/W PORT TERMINAL TAIL",
          "@ 24-36\" MIN. DEPTH", "DIR. BORE (17') 1-1.25\" HDPE"]
NOTE_F = ["STA 0+00 TO STA 2+70", "E/W PORT TERMINAL TAIL",
          "@ 24-36\" MIN. DEPTH", "DIR. BORE (270') 1-1.25\" HDPE"]


def test_footage_found_deep_in_its_own_note():
    # the log42 evidence shape: descriptor lines between callout and footage
    assert find_run_callout_to(NOTE_E, "2+87") == ("2+70", 17.0)
    assert find_run_callout_footage(NOTE_F, "0+00", "2+70") == 270.0


def test_footage_never_grabbed_across_the_next_callout():
    # this callout's note has NO footage; the next note's footage must not
    # be associated backward (the fixed-window law could do exactly that)
    lines = ["STA 1+00 TO STA 2+00",
             "STA 2+00 TO STA 3+00", "DIR. BORE (100')"]
    assert find_run_callout_footage(lines, "1+00", "2+00") is None
    assert find_run_callout_to(lines, "2+00") is None  # no own footage


def test_collectors_report_raw_footage_and_note():
    out = run_callouts_ending_at(NOTE_E, "2+87")
    assert len(out) == 1
    raw, f, note = out[0]
    assert (raw, f) == ("2+70", 17.0)
    assert "TERMINAL TAIL" in note
    out2 = run_callouts_starting_at(NOTE_F, "0+00")
    assert out2[0][0] == "2+70" and out2[0][1] == 270.0


# --- M8.17 segmented callout-chain assembly --------------------------------------------

# the real log8 far-sheet shape: a 2-hop chain 0+00 -> 1+10 -> 1+76, with a
# decoy first-hop (0+00 -> 1+65) and a SECOND run's chain (0+00 -> 1+30 -> 1+77)
LOG8_FARSIDE = [
    "STA 0+00 TO STA 1+65", "DIR. BORE (165')",
    "STA 0+00 TO STA 1+10", "E/W PORT TERMINAL TAIL", "DIR. BORE (110')",
    "STA 0+00 TO STA 1+30", "DIR. BORE (130')",
    "STA 1+10 TO STA 1+76", "DIR. BORE (66') VACANT HDPE",
    "STA 1+30 TO STA 1+77", "DIR. BORE (47') VACANT HDPE",
]


def test_chain_assembles_unique_two_hop():
    r = assemble_callout_chain(LOG8_FARSIDE, "0+00", "1+76")
    assert r["result"] == CHAIN_UNIQUE
    assert [(a, b) for a, b, _, _ in r["hops"]] == [("0+00", "1+10"),
                                                    ("1+10", "1+76")]
    assert r["footage"] == 176.0
    # the other run's chain resolves independently to its own boundary
    r2 = assemble_callout_chain(LOG8_FARSIDE, "0+00", "1+77")
    assert r2["result"] == CHAIN_UNIQUE and r2["footage"] == 177.0


def test_chain_none_when_boundary_unreachable():
    r = assemble_callout_chain(LOG8_FARSIDE, "0+00", "9+99")
    assert r["result"] == CHAIN_NONE and r["paths"] == 0


def test_chain_ambiguous_when_two_paths_reach_boundary():
    # two distinct printed paths 0+00 -> ... -> 2+00 (each footage-consistent)
    lines = [
        "STA 0+00 TO STA 1+00", "DIR. BORE (100')",
        "STA 1+00 TO STA 2+00", "DIR. BORE (100')",
        "STA 0+00 TO STA 1+50", "DIR. BORE (150')",
        "STA 1+50 TO STA 2+00", "DIR. BORE (50')",
    ]
    r = assemble_callout_chain(lines, "0+00", "2+00")
    assert r["result"] == CHAIN_AMBIGUOUS and r["paths"] == 2


def test_chain_hop_footage_must_match_its_own_station_delta():
    # the 1+10 -> 1+76 hop prints a footage (90') contradicting its 66' delta
    lines = [
        "STA 0+00 TO STA 1+10", "DIR. BORE (110')",
        "STA 1+10 TO STA 1+76", "DIR. BORE (90')",
    ]
    r = assemble_callout_chain(lines, "0+00", "1+76")
    assert r["result"] == CHAIN_NONE   # the bad hop is refused, breaking the path


def test_chain_is_monotonic_no_backtracking():
    # a backward callout (1+76 -> 1+10) can never be used to reach the boundary
    lines = [
        "STA 0+00 TO STA 1+76", "DIR. BORE (176')",   # this IS a direct callout
        "STA 1+76 TO STA 1+10", "DIR. BORE (66')",
    ]
    # direct 1-hop still assembles (degenerate chain == single callout)
    r = assemble_callout_chain(lines, "0+00", "1+76")
    assert r["result"] == CHAIN_UNIQUE and len(r["hops"]) == 1


# --- synthetic far-sheet world for the discovery law -----------------------------------

EQ_WORD = "2+70/5+16"
ML = {"layer": "MATCHLINE", "x0": 1140.0, "y0": 240.0, "x1": 1142.0,
      "y1": 540.0, "xc": 1141.0, "yc": 390.0, "lines": []}


def _dash(x0, x1, y=418.0):
    return {"layer": "BORE - PORT", "x0": x0, "y0": y - 1, "x1": x1,
            "y1": y + 1, "xc": (x0 + x1) / 2.0, "yc": y,
            "lines": [(x0, y, x1, y)]}


def _hh(cx, cy=418.0):
    return {"layer": "NEXTLINK", "x0": cx - 4, "y0": cy - 4, "x1": cx + 4,
            "y1": cy + 4, "xc": cx, "yc": cy,
            "fill": (0.15294, 0.46275, 0.73333), "lines": []}


def _conduit_run(x_from, x_to, step=30.0, dash=20.0):
    out, x = [], x_from
    while x + dash <= x_to:
        out.append(_dash(x, x + dash))
        x += step
    return out


def _tick_words(block=7):
    # a clean ladder block: 0+00 / 1+00 / 2+00 at 1.4 pt/ft
    return [{"text": t, "xc": 700.0 + i * 140.0, "yc": 430.0,
             "x0": 0, "y0": 0, "x1": 0, "y1": 0, "block": block}
            for i, t in enumerate(("0+00", "1+00", "2+00"))]


class _Plan:
    """Sheet 1 = end sheet (lines only); sheet 2 = far sheet."""

    def __init__(self, e_lines=None, f_lines=None, f_words=None,
                 f_drawings=None):
        self.e_lines = NOTE_E if e_lines is None else e_lines
        self.f_lines = NOTE_F if f_lines is None else f_lines
        self.f_words = ([{"text": EQ_WORD, "xc": 1141.0, "yc": 380.0,
                          "x0": 0, "y0": 0, "x1": 0, "y1": 0, "block": 1}]
                        + _tick_words() if f_words is None else f_words)
        # one structure at 766 (270 ft x 1.4 pt/ft = 378 pt from the
        # boundary at 1141) wired to the matchline by a dash chain
        self.f_drawings = ([ML, _hh(766.0)] + _conduit_run(772.0, 1138.0)
                           if f_drawings is None else f_drawings)

    def lines(self, sheet, offset):
        return self.e_lines if sheet == 1 else self.f_lines

    def words(self, sheet, offset):
        return [] if sheet == 1 else self.f_words

    def line_items(self, sheet, offset):
        return [] if sheet == 1 else self.f_drawings


def _graph(*edges):
    if not edges:
        edges = [("sheet:1", "sheet:2", "2+70", "5+16", "STA 2+70/5+16")]
    return SimpleNamespace(edges=[
        SimpleNamespace(from_frame=a, to_frame=b, a_raw=ar, b_raw=br,
                        source=src) for a, b, ar, br, src in edges])


def _bore(start=0.0, end=287.0, sheet_refs=(1, 2)):
    return SimpleNamespace(station_start_ft=start, station_end_ft=end,
                           sheet_refs=list(sheet_refs))


def _discover(plan=None, graph=None, bore=None):
    return discover_cross_sheet_start(
        plan or _Plan(), bore or _bore(), 0, BRENHAM_LANE_DIALECT,
        graph or _graph(), end_sheet=1)


# --- success ---------------------------------------------------------------------------

def test_discovery_binds_with_printed_provenance():
    cs = _discover()
    assert cs["result"] == CS_BOUND
    assert cs["far_sheet"] == 2
    assert cs["start_layer"] == "NEXTLINK"
    assert cs["conduit_layers"] == ("BORE - PORT",)   # from the printed notes
    assert abs(cs["start_xy"][0] - 766.0) < 1.0
    assert cs["boundary_raw"] == "2+70"
    assert cs["seg_far_ft"] == 270.0 and cs["seg_end_ft"] == 17.0
    assert "direct callout" in cs["detail"]


def test_discovery_binds_via_segmented_callout_chain():
    # NO direct 0+00 -> 2+70 callout; instead a 2-hop printed chain. The
    # single-callout refusal is NOT weakened -- the chain recovers it.
    chain_far = [
        "STA 0+00 TO STA 1+30", "E/W PORT TERMINAL TAIL", "DIR. BORE (130')",
        "STA 1+30 TO STA 2+70", "E/W PORT TERMINAL TAIL", "DIR. BORE (140')",
    ]
    cs = _discover(plan=_Plan(f_lines=chain_far))
    assert cs["result"] == CS_BOUND
    assert cs["seg_far_ft"] == 270.0           # 130 + 140, chain-summed
    assert "callout chain 0+00->1+30->2+70" in cs["detail"]
    assert "2 printed segments" in cs["detail"]
    assert abs(cs["start_xy"][0] - 766.0) < 1.0


# --- refusal taxonomy (each names its evidence class) -----------------------------------

def test_no_end_segment_callout_refuses():
    cs = _discover(plan=_Plan(e_lines=["nothing printed"]))
    assert cs["result"] == CS_REFUSED
    assert "printed run callout ENDING" in cs["named_missing"]


def test_full_span_callout_refuses():
    cs = _discover(plan=_Plan(
        e_lines=["STA 0+00 TO STA 2+87", "DIR. BORE (287')"]))
    assert cs["result"] == CS_REFUSED
    assert "full-span callout" in cs["named_missing"]


def test_no_equation_at_boundary_refuses():
    cs = _discover(graph=SimpleNamespace(edges=[]))
    assert cs["result"] == CS_REFUSED
    assert "prints no equation at this boundary" in cs["named_missing"]


def test_two_equations_at_boundary_refuse():
    cs = _discover(graph=_graph(
        ("sheet:1", "sheet:2", "2+70", "5+16", "STA 2+70/5+16"),
        ("sheet:1", "sheet:3", "2+70", "9+99", "STA 2+70/9+99")))
    assert cs["result"] == CS_REFUSED
    assert "frame equations claim boundary" in cs["named_missing"]


def test_far_sheet_outside_bore_refs_refuses():
    # the log12 class: the equation names a far sheet the bore log itself
    # never references -- uncorroborated by the bore's own print references
    cs = _discover(bore=_bore(sheet_refs=(1,)))
    assert cs["result"] == CS_REFUSED
    assert "do not name the discovered far sheet" in cs["named_missing"]


def test_missing_reciprocal_refuses():
    # no direct 0+00 -> 2+70 callout AND no connected chain reaches 2+70
    cs = _discover(plan=_Plan(f_lines=["STA 0+00 TO STA 9+99",
                                       "DIR. BORE (999')"]))
    assert cs["result"] == CS_REFUSED
    assert "neither a direct run callout" in cs["named_missing"]
    assert "nor a connected printed callout chain" in cs["named_missing"]


def test_footage_closure_refuses():
    cs = _discover(plan=_Plan(f_lines=["STA 0+00 TO STA 2+70",
                                       "DIR. BORE (200')"]))
    assert cs["result"] == CS_REFUSED
    assert "footage closure" in cs["named_missing"]


def test_unmapped_conduit_class_refuses():
    cs = _discover(plan=_Plan(
        e_lines=["STA 2+70 TO STA 2+87", "DIR. BORE (17') STEEL CASING"],
        f_lines=["STA 0+00 TO STA 2+70", "DIR. BORE (270') STEEL CASING"]))
    assert cs["result"] == CS_REFUSED
    assert "mapped conduit class" in cs["named_missing"]


def test_two_conduit_classes_refuse():
    both = "VACANT HDPE TERMINAL TAIL"
    cs = _discover(plan=_Plan(
        e_lines=["STA 2+70 TO STA 2+87", f"DIR. BORE (17') {both}"],
        f_lines=["STA 0+00 TO STA 2+70", f"DIR. BORE (270') {both}"]))
    assert cs["result"] == CS_REFUSED
    assert "mapped conduit classes" in cs["named_missing"]


def test_equation_not_typeset_on_far_sheet_refuses():
    cs = _discover(plan=_Plan(f_words=[]))
    assert cs["result"] == CS_REFUSED
    assert "typeset at sheet" in cs["named_missing"]


def test_no_reaching_structure_refuses():
    # conduit present but not wired to any structure footprint
    cs = _discover(plan=_Plan(f_drawings=[ML] + _conduit_run(900.0, 1138.0)))
    assert cs["result"] == CS_REFUSED
    assert "may span further sheets" in cs["named_missing"]


# --- rival structures: corroboration refuses, never selects -----------------------------

def test_rival_refused_by_corroboration_leaves_unique_survivor():
    # second structure ALSO on the network but at a distance the printed
    # footage cannot account for -> the band refuses it; the true one binds
    drawings = ([ML, _hh(766.0), _hh(1000.0)]
                + _conduit_run(772.0, 1138.0)
                + [_dash(1000.0 + 6, 1000.0 + 26)])
    cs = _discover(plan=_Plan(f_drawings=drawings))
    assert cs["result"] == CS_BOUND
    assert abs(cs["start_xy"][0] - 766.0) < 1.0


def test_two_corroborated_rivals_abstain():
    # both rivals sit within the banked band of the printed footage -> the
    # identity is NOT uniquely bound; guessing is forbidden
    drawings = ([ML, _hh(766.0), _hh(790.0)]
                + _conduit_run(772.0, 1138.0))
    cs = _discover(plan=_Plan(f_drawings=drawings))
    assert cs["result"] == CS_AMBIGUOUS
    assert "guessing is forbidden" in cs["named_missing"]


def test_no_ladder_band_refuses_all_rivals():
    # >= 2 reaching structures and NO clean ladder -> zero survivors -> abstain
    words = [{"text": EQ_WORD, "xc": 1141.0, "yc": 380.0,
              "x0": 0, "y0": 0, "x1": 0, "y1": 0, "block": 1}]
    drawings = ([ML, _hh(766.0), _hh(1000.0)]
                + _conduit_run(772.0, 1138.0)
                + [_dash(1006.0, 1026.0)])
    cs = _discover(plan=_Plan(f_words=words, f_drawings=drawings))
    assert cs["result"] == CS_AMBIGUOUS
    assert "0 corroborate" in cs["named_missing"]


def test_multimodal_ladder_band_is_no_corroboration_basis():
    # the log42 adversarial finding: a y-band interleaving ticks from TWO
    # drawn ladders yields multi-modal hop scales whose median is a cross-
    # ladder artifact -- such a band corroborates NOTHING (a naive median
    # would have corroborated exactly the WRONG candidates)
    two_ladders = _tick_words(block=7) + [
        {"text": t, "xc": x, "yc": 430.0,
         "x0": 0, "y0": 0, "x1": 0, "y1": 0, "block": 8}
        for t, x in (("1+00", 1000.0), ("2+00", 640.0), ("3+00", 280.0))]
    words = [{"text": EQ_WORD, "xc": 1141.0, "yc": 380.0,
              "x0": 0, "y0": 0, "x1": 0, "y1": 0, "block": 1}] + two_ladders
    drawings = ([ML, _hh(766.0), _hh(1000.0)]
                + _conduit_run(772.0, 1138.0)
                + [_dash(1006.0, 1026.0)])
    cs = _discover(plan=_Plan(f_words=words, f_drawings=drawings))
    assert cs["result"] == CS_AMBIGUOUS
    assert "survivors: none" in cs["named_missing"]
    assert "multi-modal" in cs["named_missing"]


# --- taxonomy guard ---------------------------------------------------------------------

def test_lane_taxonomy_unchanged_and_no_auto():
    assert len(set(STATUSES)) == len(STATUSES) == 8
    assert all("AUTO" not in s for s in STATUSES)
    for r in (CS_BOUND, CS_REFUSED, CS_AMBIGUOUS):
        assert "AUTO" not in r
