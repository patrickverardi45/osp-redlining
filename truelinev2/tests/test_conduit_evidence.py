"""M8.20 Phase 1 -- hardened printed conduit-token grammar.

A multi-drop (Law 1) gate consumes "every claiming chain carries its own
printed conduit statement". The bare ``count-size"`` shape also matches a
depth/cover range, so these tests pin that conduit evidence is recognized
ONLY when positively bound to a conduit MATERIAL word -- a loose string
coincidence (a depth range) must never count as conduit evidence.
"""
from __future__ import annotations

from truelinev2.extract.matchline_join import (
    chain_conduit_evidence,
    parse_conduit_evidence,
)

MATERIALS = ("HDPE", "PVC")

# The real Brenham log8/log32 chain hop notes (verbatim).
HOP1 = ('STA 0+00 TO STA 1+10 E/W PORT TERMINAL TAIL @ 24-36" MIN. DEPTH '
        'DIR. BORE (110\') 1-1.25" HDPE')
HOP2 = ('STA 1+10 TO STA 1+76 DIR. BORE (66\') 1-1.25" VACANT HDPE FOR '
        'FIBER DROP @ 24-36" MIN. DEPTH')


def test_parses_decimal_conduit_bound_to_material():
    out = parse_conduit_evidence(HOP1, MATERIALS)
    assert len(out) == 1
    assert out[0]["count"] == 1
    assert out[0]["size"] == "1.25"
    assert out[0]["material"] == "HDPE"
    assert out[0]["raw"] == '1-1.25" HDPE'


def test_material_after_one_descriptor_word():
    # `1-1.25" VACANT HDPE` -- one descriptor word ('VACANT') before HDPE.
    out = parse_conduit_evidence(HOP2, MATERIALS)
    assert len(out) == 1
    assert out[0]["material"] == "HDPE"
    assert out[0]["raw"] == '1-1.25" VACANT HDPE'


def test_rejects_depth_and_cover_ranges():
    # The depth range `24-36"` shares the count-size shape but carries no
    # material -- it must yield ZERO conduit statements.
    assert parse_conduit_evidence('@ 24-36" MIN. DEPTH', MATERIALS) == []
    assert parse_conduit_evidence('@ 24-36" DEPTH', MATERIALS) == []
    assert parse_conduit_evidence('@ 18-24" COVER', MATERIALS) == []
    assert parse_conduit_evidence('24-36" MINIMUM DEPTH', MATERIALS) == []


def test_count_size_without_material_is_not_conduit():
    # The shape alone is never conduit evidence; a non-material trailing word
    # (here 'JOINT') does not bind it.
    assert parse_conduit_evidence('DIR. BORE (40\') 1-2" JOINT TRENCH',
                                  MATERIALS) == []


def test_parses_fraction_and_mixed_number_as_present_evidence():
    # The pre-law close item: fraction/mixed-number notation must be CAPTURED
    # (presence is the gate), not silently missed.
    frac = parse_conduit_evidence('DIR. BORE (50\') 1-1/4" PVC', MATERIALS)
    assert len(frac) == 1 and frac[0]["material"] == "PVC"
    assert frac[0]["size"] in ("1/4", "1-1/4")  # the printed fraction, verbatim
    whole = parse_conduit_evidence('DIR. BORE (50\') 2-2" HDPE', MATERIALS)
    assert len(whole) == 1 and whole[0]["count"] == 2 and whole[0]["size"] == "2"


def test_missing_or_no_materials_yields_empty():
    assert parse_conduit_evidence(None, MATERIALS) == []
    assert parse_conduit_evidence("", MATERIALS) == []
    assert parse_conduit_evidence(HOP1, ()) == []   # no material vocabulary
    assert parse_conduit_evidence('plain prose, no conduit', MATERIALS) == []


def test_chain_conduit_evidence_per_chain_distinction():
    # log8's chain (HOP1+HOP2) and a synthetic PVC chain extract distinctly.
    log8 = chain_conduit_evidence([HOP1, HOP2], MATERIALS)
    assert len(log8) == 2
    assert {e["material"] for e in log8} == {"HDPE"}

    other = chain_conduit_evidence(
        ['STA 0+00 TO STA 0+90 DIR. BORE (90\') 2-2" PVC'], MATERIALS)
    assert len(other) == 1 and other[0]["material"] == "PVC"
    # The two chains' evidence sets are independent (no bleed).
    assert chain_conduit_evidence([], MATERIALS) == []


def test_depth_range_and_conduit_in_one_note_keeps_only_conduit():
    # HOP1 contains BOTH a depth range and a real conduit -- exactly one
    # conduit statement survives.
    out = parse_conduit_evidence(HOP1, MATERIALS)
    assert [e["raw"] for e in out] == ['1-1.25" HDPE']
