"""M8.14.b.3 -- tests pinning the symbol-anchored stroke contract (synthetic).

Locks: anchor ticks exist ONLY for POSITION_BOUND verdicts (an unresolved
endpoint REFUSES anchoring -- never a label, never a guess); an anchor tick at
the exact span bound makes the UNCHANGED solver start/end the stroke ON the
symbol; rival symbols may never be stroke vertices; stroke endpoints may never
sit at identity label words (the r3-class failure)."""
from __future__ import annotations

from truelinev2.extract.structure_position import (
    POSITION_BOUND,
    SYMBOL_NOT_UNIQUE,
    StructurePositionVerdict,
)
from truelinev2.extract.tick_path import READY, Tick, solve_tick_path
from truelinev2.proof.run_symbol_anchored_stroke_proof import (
    anchor_ticks_from_verdicts,
    label_offset_safety,
    rival_vertex_safety,
    stroke_endpoint_fidelity,
)


def _bound(text="0+55=0+00", xy=(861.3, 354.2)):
    return StructurePositionVerdict(label_text=text, structure_class="installer_hh",
                                    result=POSITION_BOUND, symbol_xy=xy)


def _unbound(text="2+99"):
    return StructurePositionVerdict(label_text=text, structure_class="installer_hh",
                                    result=SYMBOL_NOT_UNIQUE,
                                    named_missing_relationship="no symbol at tip")


def test_anchor_ticks_require_position_bound_both_ends():
    anchors, refusal = anchor_ticks_from_verdicts(
        _bound(), _bound("AP-163", (291.6, 355.3)), 55.0, 451.0)
    assert refusal is None
    assert anchors[0] == Tick(55.0, 861.3, 354.2)
    assert anchors[1] == Tick(451.0, 291.6, 355.3)


def test_anchor_refused_when_an_endpoint_is_unresolved():
    anchors, refusal = anchor_ticks_from_verdicts(_bound(), _unbound(), 55.0, 451.0)
    assert anchors is None
    assert "may not be anchored" in refusal
    anchors2, refusal2 = anchor_ticks_from_verdicts(_unbound(), _bound(), 55.0, 451.0)
    assert anchors2 is None and refusal2


def test_anchored_solver_starts_and_ends_on_symbols():
    """An anchor tick at the exact span bound -> the trimmed stroke's first/last
    points ARE the symbol positions (interpolation lands on the anchor)."""
    ladder = [Tick(100.0, 800.0, 360.0), Tick(200.0, 650.0, 360.0),
              Tick(300.0, 500.0, 360.0), Tick(400.0, 350.0, 360.0)]
    anchors = [Tick(55.0, 861.3, 354.2), Tick(451.0, 291.6, 355.3)]
    v = solve_tick_path(bore_id="log7", sheet=10, start_ft=55.0, end_ft=451.0,
                        ticks=ladder + anchors)
    assert v.result == READY and v.strokes_found == 1
    assert stroke_endpoint_fidelity(v, (861.3, 354.2), (291.6, 355.3))
    interior = v.stroke_points[1:-1]
    assert [p[0] for p in interior] == [800.0, 650.0, 500.0, 350.0]


def test_endpoint_fidelity_rejects_non_ready_and_drift():
    assert not stroke_endpoint_fidelity(
        solve_tick_path(bore_id="x", sheet=1, start_ft=55.0, end_ft=451.0, ticks=[]),
        (861.3, 354.2), (291.6, 355.3))
    ladder = [Tick(55.0, 860.0, 354.0), Tick(451.0, 290.0, 355.0)]
    v = solve_tick_path(bore_id="x", sheet=1, start_ft=55.0, end_ft=451.0,
                        ticks=ladder)
    # READY, but endpoints are NOT the expected symbols -> fidelity fails
    assert v.result == READY
    assert not stroke_endpoint_fidelity(v, (861.3, 354.2), (291.6, 355.3))


def test_rival_vertex_safety():
    stroke = [(861.3, 354.2), (796.4, 359.7), (652.4, 360.1), (291.6, 355.3)]
    rivals = [(621.2, 354.6), (548.4, 354.9)]
    ok = rival_vertex_safety(stroke, rivals)
    assert ok["safe"] and ok["min_vertex_to_rival_pt"] >= 25.0
    bad = rival_vertex_safety([(621.2, 354.6)], rivals)
    assert not bad["safe"] and bad["min_vertex_to_rival_pt"] == 0.0


def test_label_offset_safety():
    # b.2 facts: start label word (840.5,323.1) vs start symbol (861.3,354.2)
    ok = label_offset_safety([(861.3, 354.2), (291.6, 355.3)],
                             [(840.5, 323.1), (322.2, 305.1)])
    assert ok["safe"] and ok["min_endpoint_to_label_pt"] >= 20.0
    bad = label_offset_safety([(840.5, 323.1)], [(840.5, 323.1)])
    assert not bad["safe"]
