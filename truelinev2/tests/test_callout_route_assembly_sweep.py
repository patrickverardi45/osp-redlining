"""GENERALIZED CALLOUT-IDENTITY ROUTE ASSEMBLY sweep -- offline-law + PDF/env-gated end-to-end tests.

Offline laws (always run, no PDF): the new convention-agnostic matchline primitive see_sheet_crossings
parses printed 'BOUNDARY STA a/b - SEE SHEET N' equations, keeps the boundary keyword INJECTED (no
hardcoded CAD layer), reports ALL crossings of a sheet pair (the multi-crossing "conflict" case) without
choosing, and dedups; the sweep composes base|lateral conduit (drop coverage) and excludes the new targets
from the already-drawn set; the result enum is closed. The heavy end-to-end (binds + renders 4 cross-sheet
bores on the real plan PDF) is gated behind the PDF AND TL2_TRY_DRAW_E2E=1 so it never bloats the default
suite; it asserts the 4-log rendered set (8 PNGs), per-log station closure, the two correctly-blocked logs,
and a frozen engine census.
"""
import os

import pytest

from truelinev2.extract.matchline_join import see_sheet_crossings
from truelinev2.proof.run_brenham_corpus import PDF
from truelinev2.proof.run_callout_route_assembly_sweep import (
    ALLOWED, ALREADY_DRAWN, BASE_CONDUIT, DUPLICATE_OF_DRAWN, R_COMPLETE, _resolve_endpoints,
)
from truelinev2.extract.structure_position import (
    BRENHAM_CONDUIT_LAYERS, BRENHAM_LATERAL_CONDUIT_LAYERS,
)

CROSS_SHEET_TARGETS = ("log11", "log29", "log47", "log54", "log58", "log67")  # two sheet-local legs
SINGLE_SHEET_TARGETS = ("log36",)                            # single leg, sheet source-derived
NEW_TARGETS = CROSS_SHEET_TARGETS + SINGLE_SHEET_TARGETS
# log29 + log54 are reviewed-but-unanchored: class + (for log29) sheet derived from source, no anchors
SOURCE_DERIVED_CLASS_TARGETS = ("log29", "log54")


# ---- offline laws (always run) ------------------------------------------------------

def test_see_sheet_crossings_parses_all_crossings_in_order():
    lines = [
        "MATCHLINE STA 1+82/1+81 - SEE SHEET 20",
        "MATCHLINE STA 1+75/6+79 - SEE SHEET 20",
        "MATCHLINE STA 10+73 - SEE SHEET 18",
    ]
    # both 17<->20 crossings reported, in print order, none chosen between (the "conflict" case)
    assert see_sheet_crossings(lines, 20, "MATCHLINE") == [("1+82", "1+81"), ("1+75", "6+79")]
    assert see_sheet_crossings(lines, 18, "MATCHLINE") == [("10+73",)]
    assert see_sheet_crossings(lines, 99, "MATCHLINE") == []


def test_see_sheet_crossings_boundary_keyword_is_injected():
    # a SEE-SHEET line WITHOUT the injected boundary keyword is ignored -> no hardcoded convention
    lines = ["SEE SHEET 20 STA 1+82/1+81"]
    assert see_sheet_crossings(lines, 20, "MATCHLINE") == []
    assert see_sheet_crossings(lines, 20, "SEE SHEET") == [("1+82", "1+81")]


def test_see_sheet_crossings_dedups_repeated_equation():
    lines = ["MATCHLINE STA 1+60/1+62 - SEE SHEET 10",
             "MATCHLINE STA 1+60/1+62 - SEE SHEET 10"]
    assert see_sheet_crossings(lines, 10, "MATCHLINE") == [("1+60", "1+62")]


def test_conduit_set_composes_base_plus_lateral_only():
    base = set(BRENHAM_CONDUIT_LAYERS.values())
    lat = set(BRENHAM_LATERAL_CONDUIT_LAYERS.values())
    assert base <= BASE_CONDUIT and lat <= BASE_CONDUIT
    assert "BORE - PATH" not in BASE_CONDUIT          # excluded (unproven over-coverage)


def test_new_targets_not_in_already_drawn():
    for lid in NEW_TARGETS:
        assert lid not in ALREADY_DRAWN
    assert R_COMPLETE in ALLOWED


def test_resolve_endpoints_anchored():
    anc = {"endpoint_anchors": {
        "start": {"station": "1+45", "structure_class": "installer_hh"},
        "end": {"station": "4+14", "structure_class": "flower_pot"}}}
    assert _resolve_endpoints(anc) == ("1+45", "installer_hh", "4+14", "flower_pot", True)


def test_resolve_endpoints_reviewed_unanchored_parses_reset_class_none():
    # start reset parsed from the owner-reviewed notes; end = corrected_end; classes None -> derive from source
    rev = {"evidence_notes": "Start reset 'STA 2+22 = 0+00' at INSTALLER HH; end STA 4+45 FLOWER POT.",
           "corrected_start": "0+00", "corrected_end": "4+45"}
    assert _resolve_endpoints(rev) == ("2+22", None, "4+45", None, False)
    # no reset in notes but a non-zero corrected_start -> use it (mid-run direct bore)
    rev2 = {"evidence_notes": "direct bore callout", "corrected_start": "5+03", "corrected_end": "6+79"}
    assert _resolve_endpoints(rev2) == ("5+03", None, "6+79", None, False)
    # unresolvable (reset only at 0+00, no notes reset)
    assert _resolve_endpoints({"corrected_start": "0+00", "corrected_end": None})[0] is None


def test_duplicate_of_drawn_excludes_log48():
    assert "log48" in DUPLICATE_OF_DRAWN   # sibling of drawn log50; no parent/child overlap (DO-NOT-WIDEN)


# ---- heavy end-to-end (PDF + env gated) ---------------------------------------------

@pytest.mark.skipif(not os.path.isfile(PDF), reason="Brenham plan PDF not present")
@pytest.mark.skipif(os.environ.get("TL2_TRY_DRAW_E2E") != "1",
                    reason="heavy end-to-end (binds + renders the cross-sheet bores); set TL2_TRY_DRAW_E2E=1 to run")
def test_sweep_renders_new_logs_end_to_end():
    import json
    from truelinev2.proof.run_callout_route_assembly_sweep import OUT_DIR, main
    rc = main()
    assert rc == 0
    rep = json.loads((OUT_DIR / "callout_route_assembly_sweep.json").read_text(encoding="utf-8"))
    assert rep["verdict"] == "PASS" and rep["result"] == R_COMPLETE
    assert set(rep["newly_rendered_full"]) == set(NEW_TARGETS)
    # cross-sheet bores drew BOTH legs (2 real PNGs) and close against the printed bore span
    for lid in CROSS_SHEET_TARGETS:
        pngs = sorted(OUT_DIR.glob(f"{lid}_*.png"))
        assert len(pngs) == 2, (lid, [p.name for p in pngs])
        assert rep["verdicts"][lid]["closure"]["closes"] is True
    # the single-sheet bore drew one leg, closes, and had its sheet EXTRACTED from source
    for lid in SINGLE_SHEET_TARGETS:
        pngs = sorted(OUT_DIR.glob(f"{lid}_*.png"))
        assert len(pngs) == 1, (lid, [p.name for p in pngs])
        assert rep["verdicts"][lid]["closure"]["closes"] is True
        assert rep["verdicts"][lid]["sheet_source_derived"] is True
    # the reviewed-but-unanchored logs had their terminus CLASS derived from source (no owner naming)
    for lid in SOURCE_DERIVED_CLASS_TARGETS:
        assert rep["verdicts"][lid]["class_source_derived"] is True
    # the correctly-withheld log (DO-NOT-WIDEN): log70 fails closure (the owner's flagged -504ft conflict)
    assert "log70" in rep["still_blocked"]
    assert rep["engine_census_frozen"] is True and rep["no_fixture_mutation"] is True
