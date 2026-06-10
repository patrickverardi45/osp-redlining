"""M8.14.b.1 -- tests pinning structure-identity binding (synthetic; no PDF).

Locks: START binds by EXACT parent-station equality only (a near-miss is not
an identity; never nearest-fit); 0 or >=2 matches -> named abstain; the
wrong-HH trap is pinned (start 55 binds 0+55, never 2+22/2+72); END notes
bind by grammar (run callouts ``STA a TO STA b`` and ``=0+00`` equations are
excluded; a structure keyword is required, same or following lines); two
same-station notes abstain."""
from __future__ import annotations

from truelinev2.extract.structure_anchor import (
    BOUND,
    REQUIRED,
    bind_end_structure_note,
    bind_origin_by_parent_station,
)
from truelinev2.proof.station_equation_ownership import StructureOrigin


def _origin(parent_ft, raw=None, structure='13"X24"X24" INSTALLER HH'):
    return StructureOrigin(sheet=10, parent_station_raw=raw or "x",
                           parent_station_ft=float(parent_ft),
                           structure_type="installer_hh", structure_label=structure,
                           source_line=f"STA {raw or parent_ft}=0+00")


ORIGINS = [_origin(55, "0+55"), _origin(222, "2+22"), _origin(272, "2+72")]


def test_start_binds_by_exact_equality_wrong_hh_pinned():
    b = bind_origin_by_parent_station(55.0, ORIGINS)
    assert b.result == BOUND and b.origin.parent_station_raw == "0+55"
    assert set(b.rival_parent_stations) == {222.0, 272.0}  # never selected


def test_near_miss_is_not_an_identity():
    b = bind_origin_by_parent_station(54.9, ORIGINS)
    assert b.result == REQUIRED and b.origin is None
    assert "implicit/unprinted" in b.named_missing_relationship


def test_zero_and_ambiguous_origins_abstain_named():
    b0 = bind_origin_by_parent_station(0.0, [])
    assert b0.result == REQUIRED and "forbidden" in b0.named_missing_relationship
    b2 = bind_origin_by_parent_station(55.0, ORIGINS + [_origin(55, "0+55b")])
    assert b2.result == REQUIRED and "ambiguous" in b2.named_missing_relationship


LINES = ["STA 0+00 TO STA 2+99", "DIR. BORE (299') 1-1.25\" VACANT HDPE",
         "STA 2+99", '11"X11"X12"', "FLOWER POT", "STA 2+34", '11"X11"X12"',
         "FLOWER POT", "STA 0+55=0+00", '13"X24"X24" INSTALLER HH']


def test_end_note_binds_with_grammar():
    b = bind_end_structure_note(299.0, LINES)
    assert b.result == BOUND and b.note_line == "STA 2+99"
    assert "FLOWER POT" in b.structure_label


def test_run_callouts_and_equations_excluded():
    # 0+00 only appears in the run callout / equation forms -> no candidate
    b = bind_end_structure_note(0.0, LINES)
    assert b.result == REQUIRED and b.candidates == 0


def test_structure_keyword_required():
    b = bind_end_structure_note(299.0, ["STA 2+99", "SOME RANDOM TEXT"])
    assert b.result == REQUIRED


def test_two_same_station_notes_abstain():
    dup = LINES + ["STA 2+99", "INSTALLER HH"]
    b = bind_end_structure_note(299.0, dup)
    assert b.result == REQUIRED and b.candidates == 2
    assert "ambiguous" in b.named_missing_relationship
