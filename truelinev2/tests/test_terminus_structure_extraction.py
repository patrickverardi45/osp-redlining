"""M8.3b -- pure tests for terminus-structure extraction (no PDF, no engine).

Locks: the real Brenham-shaped callout tails classify into the right structure
classes; AP / SPLICE LOC numbers are NAMED identities; noise tokens never classify;
the tail-line grabber stops at the next STA line; merge unions both sources.
(Fixture strings are real plan-annotation shapes; this file is test scope, outside
the core convention guard.)
"""
from __future__ import annotations

from truelinev2.proof.terminus_structure_extraction import (
    TerminusEvidence,
    callout_tail_lines,
    classify_structure_text,
    extract_from_tail,
    merge_evidence,
)


def test_terminal_hh_ap_with_identity():
    ev = classify_structure_text("E/W PORT TERMINAL TAIL TERMINAL 6 PORT HH AP-163 SPLICE LOC 46")
    assert "terminal" in ev.classes and "handhole" in ev.classes and "access_point" in ev.classes
    assert "splice" in ev.classes
    assert ev.ap_ids == ["163"] and ev.splice_locs == ["46"]
    assert ev.has_identity is True


def test_flower_pot_drop_no_identity():
    ev = classify_structure_text('1-1.25" VACANT HDPE FOR FIBER DROP 11"X11"X12" FLOWER POT')
    assert "flower_pot" in ev.classes and "drop_context" in ev.classes
    assert "vacant_context" in ev.classes
    assert ev.has_identity is False  # a flower pot is a TYPE, not a named identity


def test_installer_hh():
    ev = classify_structure_text('13"X24"X24" INSTALLER HH')
    assert "installer_handhole" in ev.classes and "handhole" in ev.classes


def test_noise_never_classifies():
    ev = classify_structure_text('@ 24-36" MIN. DEPTH POTHOLE ROW D/W 288CT FIBER OPTIC CABLE')
    assert ev.classes == [] and ev.has_identity is False


def test_ap_id_variants():
    assert classify_structure_text("AP 164").ap_ids == ["164"]
    assert classify_structure_text("AP-007").ap_ids == ["7"]
    assert classify_structure_text("TAP-12 MAP").ap_ids == []  # word boundary holds


def test_tail_lines_stop_at_next_sta():
    lines = [
        "STA 0+00 TO STA 2+70",
        'DIR. BORE (270\') 1-1.25" HDPE',
        "E/W PORT TERMINAL TAIL",
        '@ 24-36" MIN. DEPTH',
        "STA 5+16 TO STA 7+40",       # next callout: must NOT bleed in
        "DIR. BORE (224') 2-1.25\" HDPE",
    ]
    tail = callout_tail_lines(lines, "0+00", "2+70")
    assert tail == ['DIR. BORE (270\') 1-1.25" HDPE', "E/W PORT TERMINAL TAIL",
                    '@ 24-36" MIN. DEPTH']
    ev = extract_from_tail(lines, "0+00", "2+70")
    assert "terminal" in ev.classes and ev.source == "tail_lines"


def test_merge_unions_sources():
    a = classify_structure_text("FLOWER POT", source="tail_lines")
    b = classify_structure_text("AP-164 TERMINAL", source="nearby_words")
    m = merge_evidence(a, b)
    assert m.source == "both"
    assert "flower_pot" in m.classes and "terminal" in m.classes
    assert m.ap_ids == ["164"] and m.has_identity is True


def test_empty_is_empty():
    ev = classify_structure_text("")
    assert ev.classes == [] and not ev.has_identity
    assert isinstance(ev, TerminusEvidence)
