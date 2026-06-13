"""M8.21 -- split-log corridor probe tests (offline; pure helpers + posture).

Pins the probe's pure helpers (frame-ownership law, conflict-record
validator, split-note reader) with synthetic data, and the engine-isolation
posture: the probe renders nothing, no engine module imports the probe, the
per-bore lane and the shipped Law-1 stack never consume corridor results,
and the probe never overrides the walk budget.
"""
import inspect
from pathlib import Path

import openpyxl
import pytest

from truelinev2.extract.ladder_cluster import Ladder
from truelinev2.extract.tick_path import Tick
from truelinev2.proof import run_split_log_corridor_probe as probe

PKG = Path(probe.__file__).resolve().parents[1]


def _ladder(*ticks):
    return Ladder(ticks=tuple(Tick(s, x, y) for s, x, y in ticks),
                  scale=1.44)


# ------------------------------------------------------------ frame law

def test_ladder_station_direction_aware():
    east = _ladder((100.0, 896.7, 413.9), (200.0, 1040.7, 413.6))
    assert probe.ladder_station(east, 1141.2) == pytest.approx(269.8, abs=0.1)
    west = _ladder((100.0, 674.4, 424.1), (500.0, 98.4, 424.1))
    # westward: station INCREASES as x decreases; its own 0+00 back-projects
    # east of the 1+00 tick
    assert probe.ladder_station(west, 674.4) == pytest.approx(100.0)
    assert probe._x_at_station(west, 0.0) > 674.4


def test_callout_frame_owner_unique_by_printed_boundary():
    east = _ladder((100.0, 896.7, 413.9), (200.0, 1040.7, 413.6))
    west = _ladder((100.0, 674.4, 424.1), (500.0, 98.4, 424.1))
    main = _ladder((600.0, 1020.0, 356.5), (1200.0, 155.8, 357.9))
    got = probe.callout_frame_owner([west, east, main],
                                    boundary_x=1141.2, boundary_ft=270.0)
    assert got is not None
    owner, resid = got
    assert owner is east and resid <= 1.0


def test_callout_frame_owner_refuses_interior_violation():
    # a ladder drawing stations beyond the callout span never owns it
    too_long = _ladder((100.0, 896.7, 413.9), (500.0, 1472.7, 413.9))
    assert probe.callout_frame_owner([too_long], 1141.2, 270.0) is None


def test_callout_frame_owner_refuses_ambiguity():
    east = _ladder((100.0, 896.7, 413.9), (200.0, 1040.7, 413.6))
    twin = _ladder((100.0, 896.7, 300.0), (200.0, 1040.7, 300.0))
    assert probe.callout_frame_owner([east, twin], 1141.2, 270.0) is None


def test_callout_frame_owner_band_is_ladder_derived():
    # residual beyond half the ladder's own tick step -> not an owner
    east = _ladder((100.0, 896.7, 413.9), (200.0, 1040.7, 413.6))
    # boundary_x placing the printed boundary 60 ft off (> 50 = half step)
    bad_x = probe._x_at_station(east, 270.0 + 60.0)
    assert probe.callout_frame_owner([east], bad_x, 270.0) is None


# ------------------------------------------------------- conflict record

def test_conflict_record_refuses_preference_keys():
    base = {"finding": probe.SOURCE_DIGIT_REREAD_REQUIRED,
            "conflicting_readings": [{"reading": "0+44"}],
            "action": "OWNER_REREAD_SOURCE_PHOTO"}
    probe.validate_conflict_record(dict(base))     # canonical shape passes
    for bad in probe.FORBIDDEN_CONFLICT_KEYS:
        record = dict(base)
        record[bad] = "0+46"
        with pytest.raises(AssertionError, match="forbidden"):
            probe.validate_conflict_record(record)
    with pytest.raises(AssertionError, match="readings"):
        probe.validate_conflict_record(
            {"finding": probe.SOURCE_DIGIT_REREAD_REQUIRED})


# ------------------------------------------------------- split-note reader

def test_read_split_notes_roundtrip(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["station", "depth", "boc", "date", "crew", "print", "notes"])
    ws.append(["0+00", 4.2, 8, "2025-12-03", "tx1-1", "1,2",
               "Segment A (col1) split from bore_log13.xlsx. "
               "Source: 2025-12-03_212755 - Jimenez."])
    ws.append(["0+44", 4.2, 8, "2025-12-03", "tx1-1", "1,2", None])
    p = tmp_path / "bore_log_test.xlsx"
    wb.save(p)
    got = probe.read_split_notes(str(p))
    assert got["stations"] == ["0+00", "0+44"]
    assert any("bore_log13" in n for n in got["notes"])
    assert got["prints"] == {"1,2"}
    assert got["crews"] == {"tx1-1"}


# ---------------------------------------------------------------- posture

def test_probe_never_renders():
    src = inspect.getsource(probe)
    assert "truelinev2.render" not in src
    assert "render_redline_stroke" not in src
    assert "REDLINE_STROKE_RGB" not in src


def test_probe_never_overrides_walk_budget():
    src = inspect.getsource(probe)
    assert "max_expansions=" not in src
    from truelinev2.extract import corridor_prune
    assert "max_expansions" not in inspect.getsource(corridor_prune)


def test_engine_never_imports_probe_or_corridor_results():
    # The per-bore lane, the shipped Law-1 stack, and the reviewer surfaces
    # must never consume the probe or corridor-class certificates.
    engine_files = (list((PKG / "match").glob("*.py"))
                    + list((PKG / "review").glob("*.py"))
                    + [PKG / "service.py"])
    for f in engine_files:
        src = f.read_text(encoding="utf-8")
        assert "run_split_log_corridor_probe" not in src, f
        assert "corridor_prune" not in src, f
    # Law 1 vocabulary stays full-universe: the shared-alignment stack never
    # references the corridor universe.
    for name in ("shared_alignment.py", "shared_alignment_extract.py"):
        src = (PKG / "match" / name).read_text(encoding="utf-8")
        assert "corridor" not in src.lower(), name


def test_probe_classes_are_not_lane_statuses():
    from truelinev2.match.symbol_conduit_lane import (S_CROSS_SHEET,
                                                      S_STRUCTURE_REQUIRED,
                                                      S_UNPRINTED)
    lane = {S_CROSS_SHEET, S_STRUCTURE_REQUIRED, S_UNPRINTED}
    classes = {probe.SURVIVOR_IN_CORRIDOR, probe.INTERIOR_RESET_NOT_ORIGIN,
               probe.SOURCE_DIGIT_REREAD_REQUIRED,
               probe.ADJACENT_PRINT_CONTEXT, probe.ORIGIN_CLASS_UNMODELED}
    assert classes.isdisjoint(lane)


def test_pruned_taxonomy_pin_is_complete_and_cross_pinned():
    # 13 candidates accounted for, and the unpruned cross-pin matches the
    # M8.20 authority (which re-proves the full universe separately).
    assert sum(probe.EXPECT_PRUNED_42.values()) == 13
    assert sum(probe.EXPECT_UNPRUNED_M820.values()) == 13
    m820 = (PKG / "proof" / "run_shared_origin_adjudication_probe.py"
            ).read_text(encoding="utf-8")
    assert '"DESIGN_PATH_SEARCH_EXHAUSTED": 12' in m820


def test_forbidden_conflict_keys_cover_preference_vocabulary():
    for key in ("preferred", "selected", "corrected", "chosen"):
        assert any(key in k for k in probe.FORBIDDEN_CONFLICT_KEYS)
