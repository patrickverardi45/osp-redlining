"""Contract tests for the pure KMZ identity-index adapter.

PDF-FREE / no main import / no rendering / no file I/O. Proves identity-only normalization,
coordinate-blindness, ambiguity detection, empty-input safety, and end-to-end consumption by the
bridge builder with NO world-coordinate leakage.

COMMAND (from repo root):
    python -m pytest backend/tests/test_pdf_kmz_identity_index.py -v
"""
from __future__ import annotations

from app.core import pdf_redline_bridge as B
from app.core import pdf_kmz_identity_index as IX
from app.core import pdf_redline_bridge_builder as BB


# ── canonical normalization (identity only) ───────────────────────────────────
def test_ap_variants_normalize_to_same_key():
    # "AP-120", bare "120" (with ap context), and "TermPortHH 120" → the SAME identity key.
    assert B.canonical_identity_key("AP-120") == "AP-120"
    assert B.canonical_identity_key("AP 120") == "AP-120"
    assert B.canonical_identity_key("120", kind_hint="ap") == "AP-120"
    assert B.canonical_identity_key("TermPortHH 120") == "AP-120"
    assert B.canonical_identity_key("SPLICE LOC 33") == "SPLICE-33"
    # Bare number with NO kind context is NOT assumed to be an AP (safe).
    assert B.canonical_identity_key("120") is None
    # Named HH with no number cannot form a numbered identity.
    assert B.canonical_identity_key("INSTALLER HH") is None
    # Kind prefix prevents bare-number collisions: AP-120 and HH-120 are distinct.
    assert B.canonical_identity_key("HH-120") == "HH-120" != B.canonical_identity_key("AP-120")


# ── adapter output shape + coordinate-blindness ───────────────────────────────
def test_build_index_shape_and_drops_coords():
    xref = {"ap_map": {
        "120": {"folder": "Terminal Port Handhole", "lonlat": ["-96.3", "30.1"], "hh": "12\"x18\""},
        "121": {"folder": "Terminal Port Handhole", "lonlat": ["-96.4", "30.2"]},
    }}
    idx = IX.build_identity_index(xref)
    assert set(idx) == {"AP-120", "AP-121"}
    e = idx["AP-120"]
    assert e["label"] == "AP-120" and e["raw_id"] == "120" and e["kind"] == "ap"
    assert e["source"] == "kmz_xref" and e["feature_id"] == "kmz:termporthh:120"
    assert e["folder"] == "Terminal Port Handhole" and e["evidence_refs"] == []
    # Coordinates from the source must NOT appear anywhere in the entry.
    for k in ("lonlat", "lat", "lon", "coord", "coords", "geometry"):
        assert k not in e, k


def test_coords_do_not_affect_identity():
    with_coords = {"ap_map": {"120": {"folder": "Terminal Port Handhole", "lonlat": ["-96.3", "30.1"]}}}
    without_coords = {"ap_map": {"120": {"folder": "Terminal Port Handhole"}}}
    assert IX.build_identity_index(with_coords) == IX.build_identity_index(without_coords)


def test_caller_feature_id_overrides_synth():
    xref = {"ap_map": {"120": {"folder": "Terminal Port Handhole"}}}
    idx = IX.build_identity_index(xref, feature_id_by_ap={"120": "TX-BRENHAM-TPHH-120"})
    assert idx["AP-120"]["feature_id"] == "TX-BRENHAM-TPHH-120"


# ── ambiguity / duplicates ────────────────────────────────────────────────────
def test_exact_duplicate_collapses_not_ambiguous():
    xref = {"ap_map": {"120": {"folder": "Terminal Port Handhole"}}}
    extra = [{"id": "AP-120", "feature_id": "kmz:termporthh:120", "source": "kml_items"}]
    idx = IX.build_identity_index(xref, extra_identities=extra)
    assert "ambiguous" not in idx["AP-120"]            # same feature_id+kind -> collapses


def test_conflicting_identities_marked_ambiguous():
    xref = {"ap_map": {"120": {"folder": "Terminal Port Handhole"}}}  # -> kmz:termporthh:120
    extra = [{"id": "AP-120", "feature_id": "DIFFERENT_FEATURE", "source": "kml_items"}]
    idx = IX.build_identity_index(xref, extra_identities=extra)
    e = idx["AP-120"]
    assert e.get("ambiguous") is True
    assert "AP-120" in e.get("ambiguous_reason", "")
    assert e["feature_id"] is None                     # never expose a guessed target


# ── empty / missing safety ────────────────────────────────────────────────────
def test_empty_or_missing_xref_returns_empty_index():
    assert IX.build_identity_index(None) == {}
    assert IX.build_identity_index({}) == {}
    assert IX.build_identity_index({"ap_map": {}}) == {}
    assert IX.build_identity_index({"cables": [], "streets": []}) == {}   # no ap_map key


def test_unparseable_entries_are_skipped_not_crash():
    xref = {"ap_map": {"": {"folder": "x"}, "NOTANUMBER": {"folder": "y"}}}
    assert IX.build_identity_index(xref) == {}


# ── end-to-end: adapter index feeds the builder, no coord leak ────────────────
def _evidence():
    return {
        "schema_version": "pdf-first-evidence-1", "status": "OK",
        "source": {"plan_pdf": "Brenham.pdf"},
        "placements": [], "fail_safe": [],
        "review_items": [{
            "log_ids": ["bore_log12"], "tier": "MATCHLINE_FRAME_RESOLVER", "surface": "review",
            "sheets": [3], "station_range": {"start": "5+50", "end": "10+92"},
            "geo": {"frame": {"page": 3},
                    "geo_anchors": [
                        {"kind": "AP", "id": "AP-120", "coord": [101.5, 222.0]},
                        {"kind": "AP", "id": "AP-121", "coord": [140.0, 60.0]},
                    ],
                    "pdf_path_trace": {"artifact_name": "bore_log12_pathtrace_s3.png"}},
        }],
    }


def test_index_feeds_builder_and_no_coord_leak():
    xref = {"ap_map": {
        "120": {"folder": "Terminal Port Handhole", "lonlat": ["-96.3", "30.1"]},
        "121": {"folder": "Terminal Port Handhole", "lonlat": ["-96.4", "30.2"]},
    }}
    idx = IX.build_identity_index(xref)
    cands = BB.build_candidates_from_evidence(_evidence(), idx, session_id="sess-1", pdf_plan_id="plan-A")
    assert len(cands) == 1
    c = cands[0]
    assert c["status"] == "candidate"
    assert c["kmz_candidate_feature_id"] == "kmz:termporthh:120"   # identity join AP-120 -> entry
    assert c["structure_start"] == "AP-120" and c["structure_end"] == "AP-121"
    assert "bore_log12_pathtrace_s3.png" in c["evidence_refs"]
    ok, errors = B.validate_bridge_candidate(c)                     # rejects any world/geometry key
    assert ok, errors
    for forbidden in ("lat", "lon", "lonlat", "coord", "coords", "geometry"):
        assert forbidden not in c
    assert c["pdf_path_xy"] == []                                   # draw-free


def test_ambiguous_index_makes_builder_abstain():
    xref = {"ap_map": {"120": {"folder": "Terminal Port Handhole"}}}
    idx = IX.build_identity_index(xref, extra_identities=[{"id": "AP-120", "feature_id": "OTHER"}])
    assert idx["AP-120"].get("ambiguous") is True
    cands = BB.build_candidates_from_evidence(_evidence(), idx, session_id="s", pdf_plan_id="p")
    c = cands[0]
    assert c["status"] == "abstain"
    assert c["abstain_reason"] == "kmz_identity_ambiguous"
    assert c["pdf_path_xy"] == []
