"""M9.0 -- KMZ reader + correlation audit tests.

Pure-helper unit tests + tracked-fixture reader tests (the Brenham KMZ fixture
is committed at backend/tests/fixtures, so these run unconditionally) + the
audit's banked constants and read-only/UNWIRED posture. The live correlation
facts (taxonomy, control AP-join, zero moves) are gated in the audit runner
(G1-G7).
"""
import inspect
from pathlib import Path

from truelinev2.extract import kmz
from truelinev2.extract.kmz import (BRENHAM_KMZ_DIALECT, ap_index, read_kmz)
from truelinev2.proof import run_kmz_correlation_audit as audit

PKG = Path(kmz.__file__).resolve().parents[1]
FIXTURE = str(PKG.parent / "backend" / "tests" / "fixtures"
              / "brenham_phase5_source_truth.kmz")


# ---- pure helpers -----------------------------------------------------------

def test_table_fields_parses_html_pairs():
    html = ('<table><tr><td>AP Number</td><td>120</td></tr>'
            '<tr><td>Note</td><td>AP 120, 8 Port, Splice Loc 28</td></tr></table>')
    f = kmz._table_fields(html)
    assert f["AP Number"] == "120"
    assert "8 Port" in f["Note"]
    assert kmz._table_fields(None) == {} and kmz._table_fields("") == {}


def test_ap_ids_extraction_anchor_only_no_range_inference():
    tok = BRENHAM_KMZ_DIALECT.ap_token
    assert kmz._ap_ids("AP 120", tok) == (120,)
    assert kmz._ap_ids("AP-163", tok) == (163,)
    # a splice range yields only the AP-prefixed anchor (115), never the
    # in-between ids -- no span inference (zero-false). The bore-terminus join
    # uses terminal_port_hh, whose AP Numbers are singular anyway.
    assert kmz._ap_ids("SPLICE LOC 28, AP115-121", tok) == (115,)
    assert kmz._ap_ids("no ap here", tok) == ()


def test_strip_ns_makes_prefixed_kml_parseable():
    import xml.etree.ElementTree as ET
    raw = ('<kml xmlns="http://x" xmlns:gx="http://g"><Document>'
           '<gx:Track><when>t</when></gx:Track></Document></kml>')
    ET.fromstring(kmz._strip_ns(raw))   # must not raise


# ---- reader on the tracked fixture -----------------------------------------

def test_read_kmz_taxonomy_matches_banked():
    m = read_kmz(FIXTURE, BRENHAM_KMZ_DIALECT)
    assert len(m.structures) == 576 and len(m.routes) == 539
    assert m.unclassified_placemarks == 0
    assert m.folder_counts["Vacant Pipe"] == 58      # == bore count
    assert m.folder_counts["Terminal Port Handhole"] == 64
    classes = {s.kmz_class for s in m.structures}
    assert {"terminal_port_hh", "splice_hh", "installer_hh", "flower_pot"} <= classes


def test_ap_join_is_class_scoped_unique():
    m = read_kmz(FIXTURE, BRENHAM_KMZ_DIALECT)
    term = {}
    for s in m.structures:
        if s.kmz_class == "terminal_port_hh":
            for ap in s.ap_ids:
                term.setdefault(ap, []).append(s)
    # control terminals each resolve to exactly ONE terminal_port_hh
    for ap in (163, 105, 145):
        assert len(term.get(ap, [])) == 1, ap
    # raw (cross-class) index pairs splice_hh + terminal_port_hh for the same AP
    idx = ap_index(m)
    assert len(idx[163]) == 2 and {s.kmz_class for s in idx[163]} == {
        "splice_hh", "terminal_port_hh"}


def test_splice_num_parses():
    assert audit._splice_num("Splice Loc 46") == 46
    assert audit._splice_num("SPLICE LOC 25") == 25
    assert audit._splice_num(None) is None and audit._splice_num("none") is None


def test_two_field_join_and_twin_not_colocated():
    # the EARNED primitive: terminal carries BOTH AP and a splice-loc, and the
    # same-AP splice twin is a DIFFERENT structure (NOT co-located) -- so the
    # splice-loc field is load-bearing, not the absent PDF class keyword.
    m = read_kmz(FIXTURE, BRENHAM_KMZ_DIALECT)
    term = {s.ap_ids[0]: s for s in m.structures
            if s.kmz_class == "terminal_port_hh" and s.ap_ids}
    spl = {}
    for s in m.structures:
        if s.kmz_class == "splice_hh":
            for ap in s.ap_ids:
                spl[ap] = s
    assert audit._splice_num(term[163].splice_loc) == 46
    assert audit._splice_num(term[105].splice_loc) == 25
    # control twins are tens-to-hundreds of metres apart (NOT co-located)
    for ap in (163, 105):
        d = audit._haversine_m((term[ap].lon, term[ap].lat),
                               (spl[ap].lon, spl[ap].lat))
        assert d > 25.0, (ap, d)


def test_routes_carry_no_text_id():
    m = read_kmz(FIXTURE, BRENHAM_KMZ_DIALECT)
    vac = [r for r in m.routes if r.kmz_class == "bore_vacant_pipe"]
    assert len(vac) == 58
    # a route is reached via endpoint structures, never a text key
    assert all(len(r.vertices) >= 2 for r in vac)
    assert all(not (r.fields.get("Note") or "").strip() for r in vac)


# ---- audit banked constants + posture --------------------------------------

def test_audit_targets_and_dispositions_banked():
    assert audit.TARGETS == ("log37", "log38", "log43", "log44", "log68")
    assert set(audit.TARGET_DISPOSITION) == set(audit.TARGETS)
    # zero-false: source-broken/void bores are SOURCE_REVIEW_ONLY (no KMZ lever)
    for b in ("log37", "log38", "log43"):
        assert audit.TARGET_DISPOSITION[b][0] == audit.X_SOURCE_ONLY
        assert audit.TARGET_DISPOSITION[b][1] is None      # not future-eligible
    # log44/log68 are FUTURE-eligible (gated), never moved now
    assert audit.TARGET_DISPOSITION["log44"][0] == audit.X_ENDPOINT_BRIDGE
    assert audit.TARGET_DISPOSITION["log68"][0] == audit.X_MATCHLINE_SUB
    assert audit.TARGET_DISPOSITION["log44"][1] and audit.TARGET_DISPOSITION["log68"][1]
    assert audit.CONTROLS == {"log7": 163, "log42": 105}


def test_audit_does_not_move_any_target_bucket():
    # the audit must preserve the 5 targets' M8.27 buckets verbatim.
    assert audit.M827_TARGET_BUCKETS == {
        "log37": "SOURCE_REVIEW_REQUIRED", "log38": "SOURCE_REVIEW_REQUIRED",
        "log43": "SOURCE_OR_KMZ_REQUIRED", "log44": "SOURCE_OR_KMZ_REQUIRED",
        "log68": "SOURCE_OR_KMZ_REQUIRED"}


def test_kmz_reader_unwired_and_audit_not_imported_by_engine():
    engine = (list((PKG / "match").glob("*.py"))
              + list((PKG / "review").glob("*.py")) + [PKG / "service.py"])
    for f in engine:
        src = f.read_text(encoding="utf-8")
        assert "extract.kmz" not in src and "extract import kmz" not in src, f
        assert "run_kmz_correlation_audit" not in src, f


def test_audit_read_only_posture():
    src = inspect.getsource(audit)
    assert "truelinev2.render" not in src and "render_redline_stroke" not in src
    assert 'OUT_DIR.glob("*.png")' in src
    assert "bores_moved_now" in src     # the audit explicitly moves nothing
