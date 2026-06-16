r"""CROSS-SHEET endpoint-anchor bridge slice (PROOF ONLY; identity encoding) -- log52 + log58.

The all-redlines closure ledger named CROSS_SHEET_FRAME_JOIN_NEEDED the highest-leverage non-placed class
(8 logs), and the cross-sheet frame-join scout proved 4 of them are SOURCE-BACKED-NOW (log11/47/52/58: a
unique HIGH-confidence printed matchline equation links every consecutive sheet, so the shipped
match.frames.translate_between_sheets returns a concrete offset). The per-endpoint identity + unique-bind
investigation (adversarially verified) then split those 4:

  SAFE (both endpoints owner-NAMED modeled structures that BIND UNIQUELY) -> bridged here:
    log52  FLOWER POT @ STA 0+98 (sheet 7)  ->  FLOWER POT @ STA 4+57 (sheet 8)   [flower_pot <-> flower_pot]
    log58  INSTALLER HH @ STA 39+79 (sheet 10) -> INSTALLER HH @ STA 2+36 (sheet 13) [installer_hh <-> installer_hh]
  HELD (named blocker, NOT bridged):
    log11  -- start identity is the NEXTLINK HH owner-named only via log53's adjudication of the IDENTICAL
              unique reset 'STA 21+63=0+00' on sheet 5 (source-deterministic, but NOT named in log11's own
              owner-review) -> a cross-log identity outside the own-review bridge precedent; hold for owner
              confirmation that log11 shares log53's start before bridging.
    log47  -- end 'STA 4+94, opposite side of Woodson Ln' (sheet 14) is a BARE STATION with NO owner-named
              modeled structure (flower_pot does not bind there; an installer_hh symbol binds but the owner
              never named it INSTALLER HH -> encoding it would INVENT an identity). End not bridgeable.

This slice encodes the two SAFE bridges as IDENTITY-ONLY two-leg both-termini anchors (the log71 schema:
start structure_terminus + end structure_terminus; the intermediate matchline is ROUTE CONTEXT recorded in
the owner_note_text, NOT an anchor; the cross-sheet COORDINATE reconciliation stays the separately-
authorized render-time step). It encodes NO coordinates, keeps corrected_sheets UNCHANGED (the owner-
confirmed sheet sets [8,7] and [10,13]), source-binds nothing here, renders nothing, promotes nothing.

Proves: log52 + log58 anchors present + schema-valid + owner-named + modeled + machine-consumable; the
cohort classifier moves both PARTIAL_SOURCE_BINDABLE -> SOURCE_BINDABLE_NOW (the explicit, deterministic,
log52/log58-LIMITED cohort delta); the frozen ENGINE census is unchanged (identity-only addition; flag-OFF
31/6/1/17/3, flag-ON 22/1/4); both are HELD BACK (anchored but NOT seam-promoted -- ELIGIBLE_EXEMPLARS
unchanged at 5, seam refuses both); the held-back set becomes {log36, log52, log58}; log11 + log47 stay
un-anchored with named blockers; no renderer.

Proof-only; the JSON report is written under the gitignored data/outputs path.
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_cross_sheet_endpoint_anchor_bridge_slice
"""
from __future__ import annotations

import json

from truelinev2.config import _REPO_ROOT
from truelinev2.ingest.manual_adjudication import (
    PLACE_NEEDS_GEOMETRY,
    activation_summary,
    apply_adjudications,
    flag_on_disposition,
    load_adjudication,
    parent_run_duplicate_check,
    placement_geometry_readiness,
    resolve,
    validate_adjudication,
    validate_endpoint_anchors,
)
from truelinev2.proof.run_log53_primitives_cohort_replay import (
    MODELED_TERMINUS_CLASSES,
    PARTIAL_SOURCE_BINDABLE,
    SOURCE_BINDABLE_NOW,
    classify_record,
)
from truelinev2.seam import ELIGIBLE_EXEMPLARS, build_seam_payload

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "cross_sheet_endpoint_anchor_bridge_slice"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
SEAM_ELIGIBLE = ("log53", "log64", "log71", "log59", "log66")   # unchanged: this slice promotes nothing
# the held-back (anchored, NOT seam-promoted) set after this slice
HELD_BACK_BRIDGED = ("log36", "log52", "log58")
# the 8 logs carrying an endpoint-anchor bridge after this slice
EXPECTED_ANCHOR_LOGS = ("log36", "log52", "log53", "log58", "log59", "log64", "log66", "log71")
HELD_NAMED_BLOCKER = ("log11", "log47")   # source-backed cross-sheet logs NOT bridged (named reasons)

# per-log expected bridge identity (two-leg both-termini; the log71 schema)
BRIDGED = {
    "log52": {"start": ("flower_pot", "FLOWER POT", "0+98"),
              "end": ("flower_pot", "FLOWER POT", "4+57"), "sheets": [8, 7]},
    "log58": {"start": ("installer_hh", "INSTALLER HH", "39+79"),
              "end": ("installer_hh", "INSTALLER HH", "2+36"), "sheets": [10, 13]},
}

_COORD_KEYS = {"x", "y", "z", "xc", "yc", "x0", "y0", "x1", "y1", "cx", "cy", "xy",
               "lat", "lon", "lng", "coord", "coords", "coordinate", "coordinates",
               "px", "py", "pixel", "pixels", "point", "points", "symbol_xy", "anchor_xy",
               "stroke", "stroke_points", "geometry", "geom"}

R_ENCODED = "CROSS_SHEET_ENDPOINT_ANCHORS_ENCODED"
B_SCHEMA = "BLOCKED_CROSS_SHEET_SCHEMA_GAP"
B_IDENTITY = "BLOCKED_CROSS_SHEET_IDENTITY_NOT_REPRESENTABLE"
B_PROMOTED = "BLOCKED_CROSS_SHEET_SILENTLY_PROMOTED"
B_CENSUS = "BLOCKED_CROSS_SHEET_CENSUS_DRIFT"
ALLOWED = {R_ENCODED, B_SCHEMA, B_IDENTITY, B_PROMOTED, B_CENSUS}


def _has_coord_keys(anchor: dict) -> bool:
    return bool({str(k).lower() for k in anchor} & _COORD_KEYS)


def _refuses_seam(log_id: str, rec: dict) -> bool:
    try:
        build_seam_payload(log_id, rec.get(log_id, {}))
        return False
    except ValueError:
        return True


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()

    doc = load_adjudication()
    rec = {r["log_id"]: r for r in doc["logs"]}
    gates = []
    result = B_SCHEMA

    gates.append(("G1 whole artifact still validates clean (additive)",
                  validate_adjudication(doc) == [], None))

    # G2..G5 per bridged log: anchors present, schema-valid, identity-only, two-leg both-termini
    for lid in ("log52", "log58"):
        l = rec.get(lid, {})
        ea = l.get("endpoint_anchors") or {}
        start, end = ea.get("start") or {}, ea.get("end") or {}
        exp = BRIDGED[lid]
        notes_up = str(l.get("evidence_notes") or "").upper()
        ok_present = bool(ea) and validate_endpoint_anchors(l) == []
        ok_start = (start.get("boundary_kind") == "structure_terminus"
                    and start.get("structure_class") == exp["start"][0]
                    and start.get("structure_label") == exp["start"][1]
                    and start.get("station") == exp["start"][2]
                    and start.get("structure_class") in MODELED_TERMINUS_CLASSES)
        ok_end = (end.get("boundary_kind") == "structure_terminus"
                  and end.get("structure_class") == exp["end"][0]
                  and end.get("structure_label") == exp["end"][1]
                  and end.get("station") == exp["end"][2]
                  and end.get("structure_class") in MODELED_TERMINUS_CLASSES)
        ok_coords = not _has_coord_keys(start) and not _has_coord_keys(end)
        ok_shape = (set(ea) == {"start", "end"}
                    and start.get("boundary_kind") == "structure_terminus"
                    and end.get("boundary_kind") == "structure_terminus")     # two-leg, no matchline anchor
        ok_named = (exp["start"][2] in notes_up and exp["end"][2] in notes_up
                    and exp["start"][1] in notes_up and exp["end"][1] in notes_up)
        ok_sheets = l.get("corrected_sheets") == exp["sheets"]                 # UNCHANGED owner set
        gates.append((f"G2.{lid} anchors present + schema-valid (validate_endpoint_anchors == [])",
                      ok_present, None))
        gates.append((f"G3.{lid} both endpoints structure_terminus modeled ({exp['start'][0]} {exp['start'][2]} -> {exp['end'][0]} {exp['end'][2]}); owner-named; identity-only; corrected_sheets {exp['sheets']} UNCHANGED",
                      ok_start and ok_end and ok_coords and ok_shape and ok_named and ok_sheets,
                      {"start": start, "end": end}))

    # G6 cohort classifier moves BOTH log52 + log58 PARTIAL_SOURCE_BINDABLE -> SOURCE_BINDABLE_NOW
    cls = {lid: classify_record(rec[lid])["classification"] for lid in ("log52", "log58")}
    gates.append(("G6 cohort: log52 + log58 move PARTIAL_SOURCE_BINDABLE -> SOURCE_BINDABLE_NOW",
                  all(cls[lid] == SOURCE_BINDABLE_NOW for lid in ("log52", "log58")),
                  {"now": cls, "was": PARTIAL_SOURCE_BINDABLE}))

    # G7 both bridges consumed by resolve()+overlay; drawable stays review_drawable; NEEDS_GEOMETRY
    disp = resolve(doc)
    g7 = all(disp.get(lid) is not None and disp[lid].endpoint_anchors is not None
             and flag_on_disposition(rec[lid]).get("drawable_status") == "review_drawable"
             and placement_geometry_readiness(rec[lid])["status"] == PLACE_NEEDS_GEOMETRY
             for lid in ("log52", "log58"))
    gates.append(("G7 bridges consumed by resolve()+overlay; drawable stays review_drawable; NEEDS_GEOMETRY", g7, None))

    # G8 NOT promoted: ELIGIBLE_EXEMPLARS unchanged (5); the seam refuses log52 + log58 (held back)
    gates.append(("G8 NOT promoted: ELIGIBLE_EXEMPLARS == log53/64/71/59/66 (5); seam refuses log52 + log58",
                  tuple(ELIGIBLE_EXEMPLARS) == SEAM_ELIGIBLE
                  and _refuses_seam("log52", rec) and _refuses_seam("log58", rec), None))

    # G9 held-back set is exactly {log36, log52, log58}: anchored, seam-refused; log36 (corrected_sheets [])
    #    + log52/log58 (corrected_sheets owner-set) are all anchored-but-not-promoted.
    with_anchors = {r["log_id"] for r in doc["logs"] if r.get("endpoint_anchors")}
    held_back = tuple(sorted((l for l in with_anchors if _refuses_seam(l, rec)), key=lambda s: int(s[3:])))
    gates.append(("G9 held-back (anchored + seam-refused) == {log36, log52, log58}; prior anchors intact",
                  held_back == HELD_BACK_BRIDGED
                  and set(EXPECTED_ANCHOR_LOGS) == with_anchors, {"held_back": list(held_back)}))

    # G10 log11 + log47 NOT anchored (held with NAMED blockers): cross-log start identity / end bare station
    gates.append(("G10 log11 + log47 NOT anchored (held with named blockers: cross-log identity / bare-station end)",
                  all(not rec[l].get("endpoint_anchors") for l in HELD_NAMED_BLOCKER), None))

    if TRUTH.is_file():
        truth = json.loads(TRUTH.read_text(encoding="utf-8"))
        baseline = {r["bore_id"]: dict(r) for r in truth["rows"]}
        off_rows = apply_adjudications(baseline, enabled=False)
        on_rows = apply_adjudications(baseline, enabled=True, doc=doc)
        summ = activation_summary(on_rows)

        def buckets(rows):
            c = {}
            for r in rows.values():
                c[r["completion_bucket"]] = c.get(r["completion_bucket"], 0) + 1
            return c
        census_ok = (off_rows is baseline and buckets(off_rows) == FROZEN_BUCKETS
                     and summ["manual_review_drawable"] == 22
                     and summ["manual_source_verification"] == 1 and summ["manual_abstain"] == 4
                     and on_rows["log44"]["adjudication"]["drawable_status"] == "non_drawable"
                     and all(on_rows[l]["adjudication"]["drawable_status"] == "abstain" for l in ABSTAIN_4)
                     and not parent_run_duplicate_check(doc))
        gates.append(("G11 ENGINE census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                      census_ok, None))
    else:
        gates.append(("G11 truth table present (census-safety baseline)", False, str(TRUTH)))

    if all(x for _, x, _ in gates):
        result = R_ENCODED
    elif not (gates[-1][1]):
        result = B_CENSUS
    elif not gates[8][1]:
        result = B_PROMOTED
    else:
        result = B_SCHEMA
    return _emit(gates, result, rec, cls, held_back)


def _emit(gates, result, rec, cls, held_back) -> int:
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G12 zero PNG / zero stroke (no render lane)", len(pngs) == 0, {"pngs": pngs}))
    gates.append(("G13 result in allowed enum", result in ALLOWED, result))
    all_pass = all(x for _, x, _ in gates)
    report = {
        "milestone": "CROSS-SHEET endpoint-anchor bridge slice (proof only; identity encoding) -- log52 + log58",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result if all_pass else "BLOCKED",
        "bridged": {lid: {"start": rec[lid]["endpoint_anchors"]["start"],
                          "end": rec[lid]["endpoint_anchors"]["end"],
                          "corrected_sheets": rec[lid]["corrected_sheets"]} for lid in ("log52", "log58")},
        "shape": "two_leg_both_termini (log71 schema; intermediate matchline = route context, not an anchor)",
        "cohort_delta": {lid: {"from": PARTIAL_SOURCE_BINDABLE, "to": cls[lid]} for lid in cls},
        "held_back_set": list(held_back),
        "seam_eligible_unchanged": list(ELIGIBLE_EXEMPLARS),
        "held_with_named_blocker": {
            "log11": ("source-backed cross-sheet join + end flower_pot binds, but the START identity is the "
                      "NEXTLINK HH owner-named only via log53's adjudication of the identical unique reset "
                      "'STA 21+63=0+00' on sheet 5 (source-deterministic but cross-log, not named in log11's "
                      "own owner-review). Hold for owner confirmation that log11 shares log53's start."),
            "log47": ("end 'STA 4+94, opposite side of Woodson Ln' on sheet 14 is a BARE STATION with no "
                      "owner-named modeled structure (flower_pot does not bind; an installer_hh binds but the "
                      "owner never named it -> encoding it would invent identity). Also the start flower_pot "
                      "binds on sheet 13, not the owner's stated sheet 10. End not bridgeable."),
        },
        "no_coordinates": True, "no_source_bind": True, "no_render": True, "no_seam_promotion": True,
        "corrected_sheets_unchanged": True, "engine_census_frozen": True,
        "next_slice": ("source-bind + render log52/log58 across their two sheets (the existing sheet-local-leg "
                       "bind + the already-proven matchline join), then seam promotion -- each separately "
                       "authorized. For log11: owner-confirm it shares log53's NEXTLINK HH start, then bridge. "
                       "For log47: recover an owner-named end structure (or confirm the installer HH)."),
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "cross_sheet_endpoint_anchor_bridge_slice.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[xsheet-bridge] result: {result if all_pass else 'BLOCKED'}")
    for lid in ("log52", "log58"):
        ea = rec[lid]["endpoint_anchors"]
        print(f"[xsheet-bridge]   {lid}: {ea['start']['structure_class']} {ea['start']['station']} "
              f"-> {ea['end']['structure_class']} {ea['end']['station']}  sheets={rec[lid]['corrected_sheets']}")
    print(f"[xsheet-bridge]   held_back={list(held_back)}  held_with_blocker={list(HELD_NAMED_BLOCKER)}")
    for n, x, _ in gates:
        print(f"[xsheet-bridge] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[xsheet-bridge] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
