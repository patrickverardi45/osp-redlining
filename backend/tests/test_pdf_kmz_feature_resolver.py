"""Contract tests for the pure AP→render-feature_id resolver.

PDF-FREE / no main import / no rendering / no file I/O. Proves identity-only extraction from the
KMZ render payload (name -> extended_data -> description), coordinate-blindness, ambiguity, empty
safety, and end-to-end feeding of the identity-index adapter so a REAL feature_id replaces the
synthesized token — with NO world-coordinate leakage into the bridge candidate.

COMMAND (from repo root):
    python -m pytest backend/tests/test_pdf_kmz_feature_resolver.py -v
"""
from __future__ import annotations

from app.core import pdf_redline_bridge as B
from app.core import pdf_kmz_feature_resolver as R
from app.core import pdf_kmz_identity_index as IX
from app.core import pdf_redline_bridge_builder as BB


# ── identity extraction + normalization ───────────────────────────────────────
def test_ap_and_termporthh_resolve_to_same_key():
    p_ap = {"points": [{"feature_id": "F1", "name": "AP-120"}]}
    p_tp = {"points": [{"feature_id": "F2", "name": "TermPortHH 120"}]}
    r_ap = R.resolve_render_feature_ids(p_ap)
    r_tp = R.resolve_render_feature_ids(p_tp)
    assert set(r_ap) == {"AP-120"} and set(r_tp) == {"AP-120"}   # same canonical key
    assert r_ap["AP-120"]["feature_id"] == "F1"
    assert r_tp["AP-120"]["feature_id"] == "F2"
    assert r_ap["AP-120"]["kind"] == "ap" and r_ap["AP-120"]["raw_id"] == "120"


def test_extended_data_resolution_with_kind_from_field_name():
    p = {"points": [{"feature_id": "F2", "name": "",
                     "classification": "terminal_port_handhole",
                     "extended_data": {"AP Number": "121"}}]}
    res = R.resolve_render_feature_ids(p)
    assert res["AP-121"]["feature_id"] == "F2"
    assert any("extended_data" in r for r in res["AP-121"]["evidence_refs"])


def test_description_fallback_requires_explicit_type_token():
    p = {"points": [{"feature_id": "F9", "name": "", "extended_data": {},
                     "description": "Access Point AP-150 near Main St", "classification": "unknown"}]}
    res = R.resolve_render_feature_ids(p)
    assert "AP-150" in res and res["AP-150"]["feature_id"] == "F9"


def test_classification_underscores_hint_ap_not_hh():
    # 'terminal_port_handhole' contains 'handhole' but must hint AP (Terminal Port wins).
    assert R._kind_from_token("terminal_port_handhole") == "ap"
    assert R._kind_from_token("splice_enclosure") == "splice"
    assert R._kind_from_token("generic_handhole") == "hh"


# ── coordinate-blindness ──────────────────────────────────────────────────────
def test_coordinate_only_feature_yields_no_identity():
    p = {"points": [{"feature_id": "X", "name": "", "extended_data": {}, "description": "",
                     "coord": [30.1, -96.3], "classification": "unknown"}]}
    assert R.resolve_render_feature_ids(p) == {}


# ── ambiguity ─────────────────────────────────────────────────────────────────
def test_duplicate_identity_different_features_is_ambiguous():
    p = {"points": [
        {"feature_id": "F_A", "name": "AP-120"},
        {"feature_id": "F_B", "name": "TermPortHH 120"},   # same key, different render feature
    ]}
    e = R.resolve_render_feature_ids(p)["AP-120"]
    assert e.get("ambiguous") is True
    assert e["feature_id"] is None
    assert "AP-120" in e["ambiguous_reason"]


def test_same_feature_id_twice_not_ambiguous():
    p = {"points": [
        {"feature_id": "F_SAME", "name": "AP-120"},
        {"feature_id": "F_SAME", "name": "TermPortHH 120"},
    ]}
    e = R.resolve_render_feature_ids(p)["AP-120"]
    assert "ambiguous" not in e and e["feature_id"] == "F_SAME"


# ── empty / missing safety ────────────────────────────────────────────────────
def test_empty_or_missing_payload_returns_empty():
    assert R.resolve_render_feature_ids(None) == {}
    assert R.resolve_render_feature_ids({}) == {}
    assert R.resolve_render_feature_ids({"points": [], "lines": [], "polygons": []}) == {}


# ── projection to feature_id_by_ap ────────────────────────────────────────────
def test_to_feature_id_by_ap_filters_non_ap_and_ambiguous():
    resolved = {
        "AP-120": {"feature_id": "F1", "kind": "ap", "raw_id": "120"},
        "SPLICE-33": {"feature_id": "F2", "kind": "splice", "raw_id": "33"},        # non-ap -> skip
        "AP-999": {"feature_id": None, "kind": "ap", "raw_id": "999", "ambiguous": True},  # skip
    }
    assert R.to_feature_id_by_ap(resolved) == {"120": "F1"}


# ── end-to-end: real feature_id replaces synth token; no coord leak ───────────
def test_feeds_adapter_real_feature_id():
    payload = {"points": [{"feature_id": "TX-AP120_pt", "name": "AP-120",
                           "classification": "terminal_port_handhole", "coord": [30.1, -96.3]}]}
    fid_by_ap = R.to_feature_id_by_ap(R.resolve_render_feature_ids(payload))
    assert fid_by_ap == {"120": "TX-AP120_pt"}
    xref = {"ap_map": {"120": {"folder": "Terminal Port Handhole"}}}
    # Without resolver -> synthesized token; with resolver -> REAL render feature_id.
    assert IX.build_identity_index(xref)["AP-120"]["feature_id"] == "kmz:termporthh:120"
    idx = IX.build_identity_index(xref, feature_id_by_ap=fid_by_ap)
    assert idx["AP-120"]["feature_id"] == "TX-AP120_pt"


def test_no_world_coord_leaks_into_candidate():
    payload = {"points": [{"feature_id": "TX-AP120_pt", "name": "AP-120",
                           "classification": "terminal_port_handhole",
                           "coord": [30.151, -96.386],
                           "extended_data": {"lat": "30.151", "lon": "-96.386"}}]}
    fid_by_ap = R.to_feature_id_by_ap(R.resolve_render_feature_ids(payload))
    xref = {"ap_map": {"120": {"folder": "Terminal Port Handhole", "lonlat": ["-96.386", "30.151"]}}}
    idx = IX.build_identity_index(xref, feature_id_by_ap=fid_by_ap)
    evidence = {
        "source": {"plan_pdf": "Brenham.pdf"}, "placements": [], "fail_safe": [],
        "review_items": [{
            "log_ids": ["bore_log12"], "sheets": [3],
            "station_range": {"start": "5+50", "end": "10+92"},
            "geo": {"frame": {"page": 3},
                    "geo_anchors": [{"kind": "AP", "id": "AP-120", "coord": [101.5, 222.0]}]},
        }],
    }
    c = BB.build_candidates_from_evidence(evidence, idx, session_id="s", pdf_plan_id="p")[0]
    assert c["status"] == "candidate"
    assert c["kmz_candidate_feature_id"] == "TX-AP120_pt"
    ok, errors = B.validate_bridge_candidate(c)
    assert ok, errors
    for forbidden in ("lat", "lon", "lonlat", "coord", "coords", "geometry"):
        assert forbidden not in c
    assert c["pdf_path_xy"] == []
