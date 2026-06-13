"""M8.26 Phase 0 -- END_IDENTITY_UNPRINTED population probe tests (offline).

Pin the pure evidence-classification helpers, the banked honest-negative
constants, and the read-only posture (no placement/render/AUTO; no engine
module imports the probe). The live drift-guarded facts (population == 25, no
AP-id terminal at any end, log27 the only BOUND-but-unclassified note, zero
gate candidates, controls unchanged) are gated inside the runner itself
(G1-G6), as with the other v2 corpus probes.
"""
import inspect
from pathlib import Path

from truelinev2.proof import run_end_identity_population_probe as probe

PKG = Path(probe.__file__).resolve().parents[1]


def test_bucket_sta_line_grammar_exclusions():
    # equation and run-callout STA-end lines are exactly what the end-note
    # grammar excludes; a bare note line without a keyword is a non-binding note.
    assert probe._bucket_sta_line("STA 21+63=0+00", "21+63") == "equation"
    assert probe._bucket_sta_line("STA 21+63 TO STA 24+11",
                                  "21+63") == "callout_starting_at_end"
    assert probe._bucket_sta_line("STA 13+55", "13+55") == "note_without_keyword"
    assert probe._bucket_sta_line("STA 2+99 FLOWER POT",
                                  "2+99") == "note_with_keyword"


def test_ap_ids_and_structure_keywords():
    note = ("STA 0+00 TO STA 1+65 ... E/W PORT TERMINAL TAIL to AP-145 "
            "and AP-9 INSTALLER HH")
    assert probe._ap_ids(note) == ["AP-9", "AP-145"]          # numeric sort
    kw = probe._structure_keywords(note)
    assert "TERMINAL" in kw and "INSTALLER HH" in kw
    assert probe._ap_ids("") == [] and probe._structure_keywords("") == []


def test_num_orders_bores_numerically():
    assert probe._num("log3") == 3 and probe._num("log27") == 27


def test_banked_honest_negative_constants():
    # the AP-HH terminal gate does NOT exist for this population.
    assert probe.BANKED_POPULATION == 25
    assert probe.BANKED_ENDING_AP_IDS == ()        # no AP terminal at any end
    assert probe.BANKED_GATE_CANDIDATES == ()      # no safe-movable bore
    assert probe.BANKED_BOUND_UNCLASSIFIED == ("log27",)
    assert probe.CONTROL == {
        "log8": "STRUCTURE_IDENTITY_BINDING_REQUIRED",
        "log32": "STRUCTURE_IDENTITY_BINDING_REQUIRED",
        "log42": "STRUCTURE_IDENTITY_BINDING_REQUIRED"}


def test_read_only_posture_no_placement_no_render():
    src = inspect.getsource(probe)
    assert "truelinev2.render" not in src
    assert "render_redline_stroke" not in src
    assert 'OUT_DIR.glob("*.png")' in src           # G6 asserts zero PNGs
    # the probe classifies/refuses; it never emits an AUTO placement
    assert "AUTO" not in src
    assert "StrokeSegment" not in src and "segments=" not in src


def test_no_engine_module_imports_the_probe():
    engine = (list((PKG / "match").glob("*.py"))
              + list((PKG / "review").glob("*.py")) + [PKG / "service.py"])
    for f in engine:
        assert "run_end_identity_population_probe" not in f.read_text(
            encoding="utf-8"), f
