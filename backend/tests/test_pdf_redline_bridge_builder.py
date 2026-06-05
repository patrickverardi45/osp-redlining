"""Contract tests for the read-only PDF↔KMZ bridge candidate BUILDER.

PDF-FREE / no main import / no rendering. Drives app.core.pdf_redline_bridge_builder against a
synthetic pdf_first_evidence payload (mirroring the verified canonical shape) + a KMZ identity
index. Proves: identity-only join (exact, never nearest), abstain-first, NO coordinate leakage,
evidence refs collected, every candidate schema-valid, and that the builder draws nothing.

COMMAND (from repo root):
    python -m pytest backend/tests/test_pdf_redline_bridge_builder.py -v
"""
from __future__ import annotations

from app.core import pdf_redline_bridge as B
from app.core import pdf_redline_bridge_builder as BB

# KMZ identity index (caller would build this from kmz_xref.ap_map / render payload).
KMZ_INDEX = {
    "AP-120": {"feature_id": "TermPortHH_120"},  # explicit feature id (canonical key)
    "AP-121": {},                                 # no feature_id -> builder falls back to key "AP-121"
}


def _evidence():
    """Two cards: log12 (AP-120/AP-121, WITH page-space coords) and log99 (AP-999 not in index)."""
    log12 = {
        "log_ids": ["bore_log12"], "tier": "MATCHLINE_FRAME_RESOLVER", "surface": "review",
        "sheets": [3, 23], "station_range": {"start": "5+50", "end": "10+92"},
        "end_structures": ["AP-120", "AP-121"],
        "render_artifact_ref": ["bore_log12_card_s3.png"],
        "geo": {
            "geometry_status": "RESOLVED",
            "frame": {"multi_sheet": True, "page": 3, "chainage_start_ft": 550.0, "chainage_end_ft": 1092.0},
            "geo_anchors": [
                {"kind": "AP", "id": "AP-120", "sta": "5+50", "coord": [101.5, 222.0], "chainage_ft": 550.0},
                {"kind": "AP", "id": "AP-121", "sta": "10+92", "coord": [140.0, 60.0], "chainage_ft": 1092.0},
            ],
            "pdf_path_trace": {"artifact_name": "bore_log12_pathtrace_s3.png"},
        },
    }
    log99 = {
        "log_ids": ["bore_log99"], "tier": "REVIEW", "surface": "review",
        "sheets": [7], "station_range": {"start": "0+00", "end": "1+10"},
        "end_structures": ["AP-999"],
        "geo": {"geo_anchors": [{"kind": "AP", "id": "AP-999", "coord": [10.0, 20.0]}]},
    }
    return {
        "schema_version": "pdf-first-evidence-1", "status": "OK",
        "source": {"plan_pdf": "Brenham.pdf", "input": "committed_rows"},
        "placements": [], "review_items": [log12, log99], "fail_safe": [],
    }


def _build(**over):
    kw = dict(session_id="sess-1", pdf_plan_id="plan-A",
              created_from_flags=["TRUELINE_PDF_FIRST_ENGINE"])
    kw.update(over)
    return BB.build_candidates_from_evidence(_evidence(), KMZ_INDEX, **kw)


def test_builder_flag_default_off(monkeypatch):
    monkeypatch.delenv(BB.BUILDER_FLAG, raising=False)
    assert BB.enabled() is False
    monkeypatch.setenv(BB.BUILDER_FLAG, "1")
    assert BB.enabled() is True


def test_normalize_kmz_feature_key():
    # Now returns the SHARED canonical KIND-NUMBER key (matches the identity-index adapter).
    assert BB.normalize_kmz_feature_key("AP-120") == "AP-120"
    assert BB.normalize_kmz_feature_key("AP 120") == "AP-120"
    assert BB.normalize_kmz_feature_key("120", kind_hint="ap") == "AP-120"
    assert BB.normalize_kmz_feature_key("120") is None   # bare number, no kind -> no key (safe)
    assert BB.normalize_kmz_feature_key("") is None
    assert BB.normalize_kmz_feature_key(None) is None


def test_identity_join_produces_candidate():
    cands = _build()
    by_log = {c["log_id"]: c for c in cands}
    c12 = by_log["bore_log12"]
    assert c12["status"] == "candidate"
    assert c12["kmz_candidate_feature_id"] == "TermPortHH_120"   # exact identity hit on canonical AP-120
    assert c12["structure_start"] == "AP-120" and c12["structure_end"] == "AP-121"
    assert c12["station_start"] == "5+50" and c12["station_end"] == "10+92"
    assert "bore_log12_pathtrace_s3.png" in c12["evidence_refs"]
    ok, errors = B.validate_bridge_candidate(c12)
    assert ok, errors


def test_abstains_when_identity_not_in_index():
    c99 = {c["log_id"]: c for c in _build()}["bore_log99"]
    assert c99["status"] == "abstain"
    assert c99["abstain_reason"] == "kmz_identity_target_not_found"
    assert c99["pdf_path_xy"] == []            # abstain draws nothing
    assert c99["kmz_candidate_feature_id"] is None
    ok, errors = B.validate_bridge_candidate(c99)
    assert ok, errors


def test_blocked_without_plan_or_session():
    no_plan = {c["log_id"]: c for c in _build(pdf_plan_id=None, session_id="s")}  # source.plan_pdf fallback fills it
    # source.plan_pdf = "Brenham.pdf" backfills pdf_plan_id, so these are NOT blocked on plan:
    assert no_plan["bore_log12"]["status"] in ("candidate", "abstain")
    # Force a true block: no session AND strip the source fallback.
    ev = _evidence()
    ev["source"] = {}
    blocked = BB.build_candidates_from_evidence(ev, KMZ_INDEX, session_id=None, pdf_plan_id=None)
    assert blocked and all(c["status"] == "blocked" for c in blocked)
    assert any("no_pdf_plan_id" in c["blockers"] for c in blocked)
    assert any("no_session_id" in c["blockers"] for c in blocked)


def test_never_propagates_world_or_page_coords():
    """Input evidence has geo_anchors[].coord; candidates must carry NO coords and NO drawn path."""
    for c in _build():
        ok, errors = B.validate_bridge_candidate(c)   # validator rejects any world/geometry key
        assert ok, errors
        for forbidden in ("coord", "coords", "lat", "lon", "lonlat", "geometry", "segments"):
            assert forbidden not in c, (forbidden, c["log_id"])
        assert c["pdf_path_xy"] == []                  # draw-free


def test_route_id_target_alone_makes_candidate():
    # Even with no KMZ identity hit, a caller-provided map route id is a valid world target.
    cands = {c["log_id"]: c for c in _build(route_id_by_log={"bore_log99": "route-77"})}
    c99 = cands["bore_log99"]
    assert c99["status"] == "candidate"
    assert c99["map_candidate_route_id"] == "route-77"


def test_all_candidates_validate_and_draw_nothing():
    cands = _build()
    assert len(cands) == 2
    for c in cands:
        ok, errors = B.validate_bridge_candidate(c)
        assert ok, errors
        assert c["pdf_path_xy"] == []
        assert c["confidence"] is None
