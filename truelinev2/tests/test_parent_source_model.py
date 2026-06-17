"""ORIGINAL_HANDWRITTEN_PARENT_SOURCE_MODEL -- Phase 4 safety tests.

Prove the canonical parent-source model + render gate make the log48<-log50 sibling mixup impossible: a
split child may be placed ONLY through its parent group, which disambiguates ownership by span + sheets.
The committed model JSON is consumed directly (no corpus / no PDF / no census).
"""
from truelinev2.ingest import parent_source as ps


# ---- model integrity: original source grouping survives ingest ----------------------

def test_model_covers_all_children_and_families():
    m = ps.load_model()
    assert m["counts"]["child_entries_total"] == 58          # every corpus child grouped
    assert m["counts"]["split_families"] == 13               # 13 original handwritten parents were split
    assert m["counts"]["standalone_parents"] == 26
    assert m["counts"]["parents_total"] == 39
    # every entry carries the required canonical schema keys
    for p in m["parents"]:
        assert {"source_parent_id", "source_file", "sibling_group_id", "run_group_id", "entries"} <= set(p)
        for e in p["entries"]:
            assert {"source_entry_id", "log_id", "entry_role", "entry_span", "start_station",
                    "end_station", "sheet_context", "ownership_disambiguation", "placement_status",
                    "segment_order"} <= set(e)


def test_entry_roles_are_in_the_supported_set():
    allowed = {"standalone_bore", "child_segment", "sibling_bore", "daily_bundle_entry",
               "continuous_run_segment", "parent_run", "ambiguous_review_required"}
    for p in ps.load_model()["parents"]:
        for e in p["entries"]:
            assert e["entry_role"] in allowed, e


# ---- the log48 / log20 proof case ---------------------------------------------------

def test_log48_log49_log50_share_parent_bore_log20():
    assert ps.parent_of("log48") == "bore_log20"
    assert ps.parent_of("log49") == "bore_log20"
    assert ps.parent_of("log50") == "bore_log20"
    assert set(ps.siblings("log48")) == {"log49", "log50"}   # siblings stay grouped


def test_log48_cannot_claim_log50s_5_14_route():
    # log50's route (0+00->5+14 = 514ft, sheets [10,11]) must NOT be ownable by log48
    ok, reason = ps.child_owns_route("log48", 514.0, [10, 11])
    assert not ok and "sibling" in reason.lower(), reason
    # symmetric: log50 cannot be assigned log48's 0+00->5+09 (509ft) route
    ok2, reason2 = ps.child_owns_route("log50", 509.0, [10])
    assert not ok2, reason2


def test_each_sibling_owns_its_own_route():
    assert ps.child_owns_route("log48", 509.0, [10])[0]       # log48 owns 0+00->5+09
    assert ps.child_owns_route("log50", 514.0, [10, 11])[0]   # log50 owns 0+00->5+14


def test_log48_own_span_rejects_corrupted_adjudication():
    # PHASE 5: log48's adjudication is CORRUPTED -- it carries sibling log50's Segment-C route (corrected_end
    # 5+14). The model must use the CORPUS span (0+00->5+09, the true Segment A) as log48's canonical identity,
    # NOT the corrupted adjudication, so log48 can never render the sibling route.
    _, e = ps.entry("log48")
    assert e["entry_span"] == "0+00->5+09"                    # corpus (true Segment A) span
    assert e["adj_corrected_span"] == "0+00->5+14"            # corrupted adjudication == sibling Segment C
    own_str, own_ft = ps._own_span("log48", e)
    assert own_str == "0+00->5+09" and own_ft == 509.0        # corpus identity wins; corruption rejected


def test_span_collision_is_detected_for_the_shared_0_00_start():
    # log48 and log50 share the 0+00 start -> flagged as colliding; log49 (44+89 start) does not
    assert "bore_log50" in ps.span_collision_siblings("log48")
    assert "bore_log48" in ps.span_collision_siblings("log50")
    assert ps.span_collision_siblings("log49") == []


# ---- general gate behaviour ---------------------------------------------------------

def test_unknown_child_cannot_be_placed():
    ok, reason = ps.child_owns_route("log999", 100.0, [1])
    assert not ok and "not in the parent-source model" in reason


def test_standalone_bore_is_its_own_parent_with_no_siblings():
    assert ps.parent_of("log2") == "bore_log2"
    assert ps.siblings("log2") == []
    assert not ps.is_split_family_member("log2")
    assert ps.is_split_family_member("log48")


def test_route_on_disjoint_sheets_is_rejected():
    # log48's own span on a totally different sheet set is not its route
    ok, reason = ps.child_owns_route("log48", 509.0, [99])
    assert not ok and "disjoint" in reason
