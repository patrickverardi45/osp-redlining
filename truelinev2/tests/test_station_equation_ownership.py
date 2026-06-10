"""M8.6 -- tests for station-equation ownership / frame-origin binding (no PDF).

Locks the station doctrine: A+B == A*100+B footage math; STA X=0+00 is one
physical structure with two station identities; multiple =0+00 annotations are
DISTINCT origins (never collapsed on the shared zero side); structure labels bind
by text adjacency; HH-HH notes corroborate parent-station deltas exactly; a
bounded bore interval is footage math, and a bounding origin may be an INTERIOR
boundary. Proof-only: nothing here wires into the engine.
"""
from __future__ import annotations

from truelinev2.match.frames import parse_frame_equations
from truelinev2.proof.station_equation_ownership import (
    bore_interval_footage,
    corroborate_pairs,
    extract_reset_origins,
    origins_bounding_interval,
    parse_hh_distances,
    prove_no_collapse,
)
from truelinev2.schema.frames import EquationKind
from truelinev2.stations import parse_station

# The screenshot pattern, as a text-line fixture (the real sheet-10 shape).
SCREENSHOT = [
    "STA 2+72=0+00",
    '13"X24"X24"',
    "INSTALLER HH",
    "STA 2+22=0+00",
    '13"X24"X24"',
    "INSTALLER HH",
    "HH - HH = 50'",
]


def test_station_notation_footage_math():
    assert parse_station("2+22") == 222.0
    assert parse_station("2+72") == 272.0
    assert parse_station("25+50") == 2550.0
    assert parse_station("31+00") == 3100.0
    assert bore_interval_footage("2+22", "2+72") == 50.0


def test_two_reset_annotations_are_two_origins_never_one_zero():
    origins = extract_reset_origins(SCREENSHOT, sheet=10)
    assert len(origins) == 2
    parents = sorted(o.parent_station_ft for o in origins)
    assert parents == [222.0, 272.0]
    assert all(o.local_origin_ft == 0.0 for o in origins)
    nc = prove_no_collapse(origins)
    assert nc["no_collapse"] is True
    assert nc["distinct_origin_ids"] == 2
    # identity is keyed by (sheet, parent) -- NEVER by the shared 0+00 side
    assert {o.origin_id for o in origins} == {"sheet:10/reset@2+72", "sheet:10/reset@2+22"}


def test_structure_labels_bind_by_adjacency():
    origins = extract_reset_origins(SCREENSHOT, sheet=10)
    assert all(o.structure_type == "installer_hh" for o in origins)
    assert all('13"X24"X24"' in (o.structure_label or "") for o in origins)


def test_hh_note_corroborates_parent_delta_exactly():
    origins = extract_reset_origins(SCREENSHOT, sheet=10)
    notes = parse_hh_distances(" ".join(SCREENSHOT))
    assert notes == [50.0]
    pairs = corroborate_pairs(origins, notes)
    assert len(pairs) == 1
    assert pairs[0]["parent_delta_ft"] == 50.0
    assert pairs[0]["hh_note_exact_match"] is True


def test_bore_interval_bounded_by_the_two_origins():
    origins = extract_reset_origins(SCREENSHOT, sheet=10)
    bounding = origins_bounding_interval(origins, 222.0, 272.0)
    assert len(bounding) == 1
    s, e = bounding[0]
    assert s.parent_station_ft == 222.0 and e.parent_station_ft == 272.0


def test_same_parent_on_different_sheets_stays_distinct():
    a = extract_reset_origins(["STA 2+72=0+00", "INSTALLER HH"], sheet=10)
    b = extract_reset_origins(["STA 2+72=0+00", "INSTALLER HH"], sheet=12)
    nc = prove_no_collapse(a + b)
    assert nc["origin_count"] == 2 and nc["no_collapse"] is True


def test_duplicate_annotation_same_sheet_dedupes_but_distinct_parents_never_merge():
    lines = ["STA 2+72=0+00", "STA 2+72=0+00", "STA 2+22=0+00"]
    origins = extract_reset_origins(lines, sheet=10)
    assert len(origins) == 2  # the duplicated annotation is one physical point


def test_reversed_notation_and_literal_zero_parent():
    # 0+00 = X binds the same origin; a literal 0+00=0+00 is not an origin.
    origins = extract_reset_origins(["STA 0+00=2+72", "STA 0+00=0+00"], sheet=3)
    assert [o.parent_station_ft for o in origins] == [272.0]


def test_frames_parser_agrees_these_are_resets_not_cross_frame_edges():
    # The existing equation parser classifies =0+00 annotations as FRAME_RESET
    # (no SEE-SHEET link) -- they build NO translatable edge, so nothing in the
    # engine can treat two local zeros as the same point through translation.
    eqs = parse_frame_equations(" ".join(SCREENSHOT))
    resets = [e for e in eqs if e.kind is EquationKind.FRAME_RESET]
    assert len(resets) == 2
    assert sorted(e.a.feet for e in resets) == [222.0, 272.0]
    assert all(e.b.feet == 0.0 for e in resets)
    assert all(not e.linked_frames for e in resets)


def test_no_engine_wiring():
    # M8.6 is proof-only: the engine must not import the ownership module.
    import truelinev2.match.engine as eng
    src_imports = [m for m in dir(eng) if "ownership" in m.lower()]
    assert not src_imports
