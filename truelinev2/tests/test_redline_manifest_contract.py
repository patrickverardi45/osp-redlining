"""Phase-1 redline-manifest CONTRACT test (no engine, no render, no PDF).

Proves the committed example manifest conforms to the committed JSON Schema and
reconciles to the current 50/58 drawn truth. The website/backend will consume the
manifest described here -- so this test pins the contract, not the engine.

Two validation paths:
  * a dependency-free validator that reads redline_manifest.schema.json and checks
    the example against it (always runs -- jsonschema need not be installed); and
  * jsonschema itself when present (CI with the dep), as a stronger cross-check.

Plus explicit reconciliation assertions (counts, log3, log14, the 7 blockers,
boolean/status/provenance consistency, unsafe-source exclusion). Pure stdlib; this
test imports no truelinev2 engine module.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"
SCHEMA_PATH = CONTRACTS / "redline_manifest.schema.json"
EXAMPLE_PATH = CONTRACTS / "examples" / "brenham_50_of_58_redline_manifest.example.json"

SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
MANIFEST = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
LOGS = {lg["log_id"]: lg for lg in MANIFEST["logs"]}

# Current-truth reference sets (continued-36 ledger).
ALL_58 = {
    "log2", "log3", "log4", "log5", "log6", "log7", "log8", "log9", "log10",
    "log11", "log12", "log14", "log15", "log16", "log19", "log23", "log25",
    "log27", "log29", "log30", "log31", "log32", "log36", "log37", "log38",
    "log39", "log41", "log42", "log43", "log44", "log45", "log46", "log47",
    "log48", "log49", "log50", "log51", "log52", "log53", "log54", "log55",
    "log56", "log57", "log58", "log59", "log60", "log61", "log62", "log63",
    "log64", "log65", "log66", "log67", "log68", "log69", "log70", "log71",
    "log72",
}
OWNER_LOCKED = {"log5", "log31", "log38", "log43"}
SOURCE_GAP = {"log15", "log16"}
MISSING_SHEET = {"log57"}
KNOWN_BLOCKED = OWNER_LOCKED | SOURCE_GAP | MISSING_SHEET
ALREADY_DRAWN = {
    "log7", "log25", "log45", "log50", "log51", "log52", "log53", "log59",
    "log64", "log65", "log66", "log69", "log71",
}

STATUS_BOOLS = {
    "DRAWN_REDLINE": (True, False, False),
    "COVERED_BY_EXISTING_REDLINE": (False, True, False),
    "OWNER_LOCKED_ABSTAIN": (False, False, True),
    "SOURCE_GAP_BLOCKED": (False, False, True),
    "MISSING_SOURCE_SHEET_BLOCKED": (False, False, True),
}
STATUS_PROVENANCE_OK = {
    "DRAWN_REDLINE": {"DETERMINISTIC_AUTO", "OWNER_CONFIRMED_HUMAN_ADJUSTABLE"},
    "COVERED_BY_EXISTING_REDLINE": {"COVERED_BY_EXISTING_REDLINE"},
    "OWNER_LOCKED_ABSTAIN": {"BLOCKED_OWNER_LOCKED"},
    "SOURCE_GAP_BLOCKED": {"BLOCKED_SOURCE_GAP"},
    "MISSING_SOURCE_SHEET_BLOCKED": {"BLOCKED_MISSING_SOURCE"},
}
STATUS_BLOCKER_CATEGORY = {
    "OWNER_LOCKED_ABSTAIN": "OWNER_LOCKED",
    "SOURCE_GAP_BLOCKED": "SOURCE_GAP",
    "MISSING_SOURCE_SHEET_BLOCKED": "MISSING_SOURCE_SHEET",
}


# --------------------------------------------------------------------------- #
# Dependency-free JSON-Schema validator (subset used by the contract schema).
# Supports: type (incl. list/null), enum, const, required, properties,
# additionalProperties (bool), items, minItems, minimum.
# --------------------------------------------------------------------------- #
def _type_ok(inst, t):
    if t == "object":
        return isinstance(inst, dict)
    if t == "array":
        return isinstance(inst, list)
    if t == "string":
        return isinstance(inst, str)
    if t == "integer":
        return isinstance(inst, int) and not isinstance(inst, bool)
    if t == "number":
        return isinstance(inst, (int, float)) and not isinstance(inst, bool)
    if t == "boolean":
        return isinstance(inst, bool)
    if t == "null":
        return inst is None
    raise AssertionError("schema uses unsupported type %r" % (t,))


def _walk(inst, schema, path, errors):
    if "const" in schema and inst != schema["const"]:
        errors.append("%s: expected const %r, got %r" % (path, schema["const"], inst))
    if "enum" in schema and inst not in schema["enum"]:
        errors.append("%s: %r not in enum %r" % (path, inst, schema["enum"]))
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_type_ok(inst, t) for t in types):
            errors.append("%s: %r is not of type %r" % (path, inst, types))
            return  # a type mismatch makes deeper checks meaningless
    if isinstance(inst, dict):
        props = schema.get("properties", {})
        for req in schema.get("required", []):
            if req not in inst:
                errors.append("%s: missing required property %r" % (path, req))
        if schema.get("additionalProperties") is False:
            for key in inst:
                if key not in props:
                    errors.append("%s: additional property %r not allowed" % (path, key))
        for key, subschema in props.items():
            if key in inst:
                _walk(inst[key], subschema, "%s/%s" % (path, key), errors)
    if isinstance(inst, list):
        if "minItems" in schema and len(inst) < schema["minItems"]:
            errors.append("%s: %d items < minItems %d" % (path, len(inst), schema["minItems"]))
        item_schema = schema.get("items")
        if item_schema is not None:
            for i, el in enumerate(inst):
                _walk(el, item_schema, "%s[%d]" % (path, i), errors)
    if "minimum" in schema and isinstance(inst, (int, float)) and not isinstance(inst, bool):
        if inst < schema["minimum"]:
            errors.append("%s: %r < minimum %r" % (path, inst, schema["minimum"]))


def validate(instance, schema):
    errors = []
    _walk(instance, schema, "$", errors)
    return errors


# --------------------------------------------------------------------------- #
# Conformance
# --------------------------------------------------------------------------- #
def test_example_conforms_to_schema_portable():
    errors = validate(MANIFEST, SCHEMA)
    assert errors == [], "schema violations:\n" + "\n".join(errors)


def test_example_conforms_to_schema_jsonschema():
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(instance=MANIFEST, schema=SCHEMA)


def test_portable_validator_actually_rejects_bad_docs():
    # Guard against a vacuous validator: known-bad mutations must be caught.
    assert validate({"schema_version": "9.9.9"}, SCHEMA)  # wrong const + missing keys
    bad = json.loads(json.dumps(MANIFEST))
    bad["logs"][0]["status"] = "NOT_A_STATUS"
    assert validate(bad, SCHEMA)
    bad2 = json.loads(json.dumps(MANIFEST))
    bad2["logs"][0]["surprise"] = 1  # additionalProperties: false
    assert validate(bad2, SCHEMA)
    bad3 = json.loads(json.dumps(MANIFEST))
    del bad3["logs"][0]["closure"]  # required key (nullable, but must be present)
    assert validate(bad3, SCHEMA)


# --------------------------------------------------------------------------- #
# Header / provenance reflects current truth
# --------------------------------------------------------------------------- #
def test_header_reflects_current_state():
    assert MANIFEST["schema_version"] == "1.0.0"
    assert MANIFEST["mock_example"] is True
    assert MANIFEST["project_id"] == "brenham"
    assert MANIFEST["engine"]["render_commit"] == "c19b565"
    assert MANIFEST["summary"]["frontier"] == "50/58"


# --------------------------------------------------------------------------- #
# Count reconciliation
# --------------------------------------------------------------------------- #
def test_log_id_set_matches_known_58():
    assert len(MANIFEST["logs"]) == 58
    assert set(LOGS) == ALL_58


def test_summary_counts_reconcile():
    s = MANIFEST["summary"]
    drawn = [lg for lg in LOGS.values() if lg["drawn"]]
    covered = [lg for lg in LOGS.values() if lg["covered"]]
    blocked = [lg for lg in LOGS.values() if lg["blocked"]]
    assert s["total_logs"] == 58 == len(LOGS)
    assert s["drawn_count"] == 50 == len(drawn)
    assert s["covered_count"] == 1 == len(covered)
    assert s["blocked_count"] == 7 == len(blocked)
    assert s["drawn_count"] + s["covered_count"] + s["blocked_count"] == 58


def test_status_counts_match_logs():
    tally = {}
    for lg in LOGS.values():
        tally[lg["status"]] = tally.get(lg["status"], 0) + 1
    assert MANIFEST["status_counts"] == tally
    assert MANIFEST["status_counts"] == {
        "DRAWN_REDLINE": 50,
        "COVERED_BY_EXISTING_REDLINE": 1,
        "OWNER_LOCKED_ABSTAIN": 4,
        "SOURCE_GAP_BLOCKED": 2,
        "MISSING_SOURCE_SHEET_BLOCKED": 1,
    }
    assert sum(MANIFEST["status_counts"].values()) == 58


def test_provenance_counts_match_logs():
    tally = {}
    for lg in LOGS.values():
        tally[lg["provenance"]] = tally.get(lg["provenance"], 0) + 1
    assert MANIFEST["provenance_counts"] == tally
    assert sum(MANIFEST["provenance_counts"].values()) == 58
    assert MANIFEST["provenance_counts"]["DETERMINISTIC_AUTO"] == 49
    assert MANIFEST["provenance_counts"]["OWNER_CONFIRMED_HUMAN_ADJUSTABLE"] == 1


def test_drawn_lane_rosters():
    already = {k for k, lg in LOGS.items() if lg["drawn_lane"] == "ALREADY_DRAWN"}
    new = {k for k, lg in LOGS.items() if lg["drawn_lane"] == "NEW_TARGETS"}
    assert already == ALREADY_DRAWN
    assert len(already) == 13 and len(new) == 37
    assert already.isdisjoint(new)
    # Only drawn logs carry a lane; non-drawn carry null.
    for k, lg in LOGS.items():
        assert (lg["drawn_lane"] is not None) == lg["drawn"]


# --------------------------------------------------------------------------- #
# Per-log invariants
# --------------------------------------------------------------------------- #
def test_boolean_and_provenance_consistency():
    for k, lg in LOGS.items():
        trio = (lg["drawn"], lg["covered"], lg["blocked"])
        assert sum(trio) == 1, "%s: exactly one of drawn/covered/blocked must be true" % k
        assert trio == STATUS_BOOLS[lg["status"]], k
        assert lg["provenance"] in STATUS_PROVENANCE_OK[lg["status"]], k
        # blocker present iff blocked, and its category matches the status.
        assert (lg["blocker"] is not None) == lg["blocked"], k
        if lg["blocked"]:
            assert lg["blocker"]["category"] == STATUS_BLOCKER_CATEGORY[lg["status"]], k
            assert lg["blocker"]["unlock_requirement"].strip(), k
        # non-drawn logs never carry artifacts.
        if not lg["drawn"]:
            assert lg["artifacts"] == [], k


def test_exactly_one_owner_confirmed_geometry_is_log3():
    geom = [k for k, lg in LOGS.items()
            if lg["provenance"] == "OWNER_CONFIRMED_HUMAN_ADJUSTABLE"]
    assert geom == ["log3"]
    log3 = LOGS["log3"]
    assert log3["status"] == "DRAWN_REDLINE" and log3["drawn"] is True
    assert log3["coverage"]["downstream_covered_by"] == ["log4"]
    assert log3["span"]["label"] == "12+63->21+63"
    # Every other drawn log is deterministic-auto (log3 is the only geometry render).
    for k, lg in LOGS.items():
        if lg["drawn"] and k != "log3":
            assert lg["provenance"] == "DETERMINISTIC_AUTO", k


def test_log14_covered_by_log10_no_duplicate_stroke():
    log14 = LOGS["log14"]
    assert log14["status"] == "COVERED_BY_EXISTING_REDLINE"
    assert log14["provenance"] == "COVERED_BY_EXISTING_REDLINE"
    assert log14["drawn"] is False and log14["covered"] is True
    assert log14["coverage"]["covered_by"] == "log10"
    assert log14["artifacts"] == []  # no duplicate artifact
    assert log14["blocker"] is None
    assert LOGS["log10"]["status"] == "DRAWN_REDLINE"  # the covering stroke exists


def test_blocked_logs_are_the_known_seven():
    blocked = {k for k, lg in LOGS.items() if lg["blocked"]}
    assert blocked == KNOWN_BLOCKED
    for k in OWNER_LOCKED:
        assert LOGS[k]["status"] == "OWNER_LOCKED_ABSTAIN"
        assert LOGS[k]["provenance"] == "BLOCKED_OWNER_LOCKED"
        assert "owner lifts the abstain" in LOGS[k]["blocker"]["unlock_requirement"]
    for k in SOURCE_GAP:
        assert LOGS[k]["status"] == "SOURCE_GAP_BLOCKED"
        assert LOGS[k]["provenance"] == "BLOCKED_SOURCE_GAP"
    assert LOGS["log57"]["status"] == "MISSING_SOURCE_SHEET_BLOCKED"
    assert ".FS" in LOGS["log57"]["blocker"]["unlock_requirement"]


def test_artifacts_are_final_only_and_marked_mock():
    for k, lg in LOGS.items():
        for art in lg["artifacts"]:
            assert art["kind"] == "FINAL_REDLINE_PNG", k  # no helper/proof leakage
            assert art["example_placeholder"] is True, k  # honesty: not real output
            assert art["sha256"] is None, k               # no live publishing yet
    # Drawn logs carry at least one final artifact placeholder.
    for k, lg in LOGS.items():
        if lg["drawn"]:
            assert lg["artifacts"], k


# --------------------------------------------------------------------------- #
# Unsafe sources excluded (audit's "never consume" list)
# --------------------------------------------------------------------------- #
def test_no_log_field_named_placement_status():
    # placement_status may be NAMED in prohibitions, but must not be a data field
    # or an evidence source for any log.
    for k, lg in LOGS.items():
        assert "placement_status" not in lg, k
        for ev in lg["evidence"]:
            assert "placement_status" not in ev["ref"], k
            assert "parent_source_model" not in ev["ref"], k


def test_consumption_rules_forbid_unsafe_sources():
    rules = " ".join(MANIFEST["consumption_rules"]).lower()
    assert "parent_source_model.json" in rules
    assert "placement_status" in rules
    assert "filename" in rules
    assert "final_redline_png" in rules


def test_stored_anchor_debt_surfaced_as_warnings():
    # log48 (corrupted 5+14) and log70 (superseded 1+45) must warn consumers.
    assert any("B-DATA-LOG48-ADJ-1" in w for w in LOGS["log48"]["warnings"])
    assert any("B-DATA-LOG48-ADJ-1" in w for w in LOGS["log70"]["warnings"])
    # Gated/override renders whose raw placement_status is stale carry a warning.
    for k in ("log3", "log30", "log42", "log44"):
        assert any("placement_status" in w for w in LOGS[k]["warnings"]), k
