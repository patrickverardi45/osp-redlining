"""Item 3 — deterministic physical HH/structure anchor proof (PDF-FREE / synthetic).

Locks the contract that the engine binds the PHYSICAL structure symbol (authored CAD
``NEXTLINK`` layer, uniqueness-gated) and NEVER a text label or an unrelated nearby
structure (TEL-HH / FLOWER POT / HOUSES). Mirrors the log66 single-sheet HH-HH crossing.
The optional evidence enrichment (``rejected_candidates``) is asserted to be evidence-ONLY:
it records the rejected look-alikes but never changes the resolve/anchor decision.

COMMAND (from repo root):
    python -m pytest backend/tests/test_physical_anchor_resolver.py -v
"""
from __future__ import annotations

from backend.app.core.redline_consult import physical_anchor_resolver as P


def _path(layer, x0, y0, x1, y1):
    return {"layer": layer, "bbox_display": [float(x0), float(y0), float(x1), float(y1)]}


def _blob(layer, cx, cy, s=8.0):
    """One small symbol blob (single stroke) centered at (cx, cy) on ``layer``."""
    h = s / 2.0
    return [_path(layer, cx - h, cy - h, cx + h, cy + h)]


def _callout(cx, cy, s=10.0):
    h = s / 2.0
    return [cx - h, cy - h, cx + h, cy + h]


# Proven callout at (100,100); the real installer HH (NEXTLINK) sits 50px below. Decoys
# (TEL-HH / FLOWER POT / HOUSES) are WITHIN radius but on NON-allowed layers.
HH = (100.0, 50.0)
CALLOUT = _callout(100.0, 100.0)
DECOYS = (_blob("FLOWER POT", 130.0, 100.0) + _blob("TEL-HH", 100.0, 140.0)
          + _blob("HOUSES", 70.0, 120.0))


def test_unique_nextlink_blob_resolves_over_decoys():
    out = P.resolve_physical_anchor(CALLOUT, _blob("NEXTLINK", *HH) + DECOYS)
    assert out["resolved"] is True
    assert out["reason"] == "unique_structure_blob"
    assert out["anchor"][0] == 100.0 and abs(out["anchor"][1] - 50.0) < 1e-6
    assert all(e["layer"] == "NEXTLINK" for e in out["evidence"])  # decoys never in allowed evidence


def test_decoys_recorded_as_rejected_candidates():
    out = P.resolve_physical_anchor(CALLOUT, _blob("NEXTLINK", *HH) + DECOYS)
    rej_layers = {r["layer"] for r in out["rejected_candidates"]}
    assert {"FLOWER POT", "TEL-HH", "HOUSES"} <= rej_layers
    assert all(r["reason"] == "layer_not_allowed" for r in out["rejected_candidates"])
    assert "NEXTLINK" not in rej_layers  # the chosen layer is never "rejected"


def test_zero_allowed_blob_abstains():
    out = P.resolve_physical_anchor(CALLOUT, list(DECOYS))  # decoys only, no NEXTLINK
    assert out["resolved"] is False
    assert out["reason"] == "no_structure_blob_on_allowed_layer_within_radius"
    assert out["anchor"] is None
    assert {r["layer"] for r in out["rejected_candidates"]} >= {"FLOWER POT", "TEL-HH"}


def test_multiple_allowed_blobs_abstain_ambiguous():
    paths = _blob("NEXTLINK", 100.0, 60.0) + _blob("NEXTLINK", 110.0, 120.0)  # two within radius
    out = P.resolve_physical_anchor(CALLOUT, paths)
    assert out["resolved"] is False
    assert out["reason"] == "ambiguous_multiple_structure_blobs"
    assert out["anchor"] is None


def test_enrichment_does_not_change_resolution():
    """The rejected-candidate enrichment is evidence-ONLY: identical decision with/without decoys."""
    base = P.resolve_physical_anchor(CALLOUT, _blob("NEXTLINK", *HH))
    withdecoys = P.resolve_physical_anchor(CALLOUT, _blob("NEXTLINK", *HH) + DECOYS)
    assert base["resolved"] == withdecoys["resolved"] is True
    assert base["anchor"] == withdecoys["anchor"]
    assert base["reason"] == withdecoys["reason"]
    assert base["rejected_candidates"] == []   # no decoys -> nothing rejected
    assert withdecoys["rejected_candidates"]    # decoys present -> recorded


def test_connector_both_ends_resolve_with_corroboration():
    paths = _blob("NEXTLINK", 100.0, 100.0) + _blob("NEXTLINK", 300.0, 100.0)
    out = P.resolve_connector_anchors(_callout(100.0, 100.0), _callout(300.0, 100.0), paths)
    assert out["resolved"] is True
    assert out["start_anchor"][0] == 100.0 and out["end_anchor"][0] == 300.0
    assert isinstance(out["corroboration"]["tighter_than_textbox"], bool)
    assert out["corroboration"]["resolved_span_px"] >= 0.0


def test_connector_one_end_unresolved_falls_back_no_mixed_anchor():
    # start has a unique NEXTLINK HH; end has NONE on the allowed layer.
    paths = _blob("NEXTLINK", 100.0, 100.0) + _blob("FLOWER POT", 300.0, 100.0)
    out = P.resolve_connector_anchors(_callout(100.0, 100.0), _callout(300.0, 100.0), paths)
    assert out["resolved"] is False
    assert str(out.get("reason", "")).startswith("fallback_to_text_anchor")
    assert "start_anchor" not in out and "end_anchor" not in out  # never one physical + one text
