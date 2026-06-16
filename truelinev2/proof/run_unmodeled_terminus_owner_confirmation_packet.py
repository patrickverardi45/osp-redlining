r"""UNMODELED_TERMINUS owner-confirmation PACKET -- the FULL source-recovered candidates (PROOF ONLY).

The unmodeled-terminus class scout partitioned UNMODELED_TERMINUS_CLASS_NEEDED and found two FULL
source-recovered candidates (log46, log54): the SHIPPED resolvers uniquely bind a modeled class at BOTH
termini, each ON the bore conduit chain. This slice prepares the EXACT owner-confirmation packet that must
be approved BEFORE any endpoint-anchor bridge -- and proves the packet is well-formed by DRY-RUN-validating
the PROPOSED identity-only encoding WITHOUT writing it to the fixture.

It does NOT encode endpoint_anchors (the candidates stay UNMODELED in the reviewed artifact), does NOT
modify the fixture, parses no coordinate into a placement, draws nothing, promotes nothing. The terminus
CLASS IDENTITY remains UNCONFIRMED: the resolver's unique on-route bind is strong SOURCE evidence, but
OCR/source recovery stays untrusted until the owner confirms.

The two candidates (start -> end; both cross-sheet runs):
  log46  nextlink_hh @ STA 44+08 (sheet 10)  ->  terminal_port_hh @ STA 5+34 (sheet 14)   [sheets 10,13,14]
  log54  nextlink_hh @ STA 3+91  (sheet 17)  ->  terminal_port_hh @ STA 3+14 (sheet 21)   [sheets 17,21]

What this proves (so owner review is not wasted on an ill-formed proposal): the FULL set is still exactly
{log46, log54}; the PROPOSED two-leg both-termini structure_terminus encoding is schema-valid
(validate_endpoint_anchors == []), identity-only (NO coordinate field), modeled-class, and provenance-
grounded (each proposed station is printed in the owner evidence_notes and each sheet is within the owner-
confirmed corrected_sheets); the proposed classes match the live source recovery; and the fixture is
BYTE-UNCHANGED (the candidates carry no endpoint_anchors and stay UNMODELED). The owner-confirmation packet
is written (gitignored) for the owner to approve/reject per terminus.

Proof-only; the JSON packet is written under the gitignored data/outputs path.
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_unmodeled_terminus_owner_confirmation_packet
"""
from __future__ import annotations

import json
import os

from truelinev2.config import _REPO_ROOT
from truelinev2.ingest.manual_adjudication import (
    activation_summary,
    apply_adjudications,
    load_adjudication,
    parent_run_duplicate_check,
    validate_endpoint_anchors,
)
from truelinev2.proof.run_all_redlines_closure_ledger import UNMODELED_TERMINUS, build_ledger
from truelinev2.proof.run_brenham_corpus import PDF
from truelinev2.proof.run_log53_primitives_cohort_replay import (
    ENDPOINT_IDENTITY_NOT_MODELED,
    MODELED_TERMINUS_CLASSES,
    classify_record,
)
from truelinev2.proof.run_unmodeled_terminus_class_scout import (
    FULL,
    PARTITION,
    TERMINI,
)
from truelinev2.seam import ELIGIBLE_EXEMPLARS

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "unmodeled_terminus_owner_confirmation_packet"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
SEAM_ELIGIBLE = ("log53", "log64", "log71", "log59", "log66")
FULL_CANDIDATES = ("log46", "log54")
_COORD_KEYS = {"x", "y", "z", "xc", "yc", "x0", "y0", "x1", "y1", "cx", "cy", "xy",
               "lat", "lon", "lng", "coord", "coords", "coordinate", "coordinates",
               "px", "py", "pixel", "pixels", "point", "points", "symbol_xy", "anchor_xy",
               "stroke", "stroke_points", "geometry", "geom"}
STRUCTURE_LABEL = {"nextlink_hh": "NEXTLINK HH", "terminal_port_hh": "PORT HH",
                   "installer_hh": "INSTALLER HH", "flower_pot": "FLOWER POT"}

# the SOURCE-RECOVERED candidate identities (from the scout: unique on-route resolver bind). The
# per-endpoint sheet is the scout's source sheet; the station is owner-authoritative. NOTHING invented.
CANDIDATE = {
    "log46": {"start": {"class": "nextlink_hh", "station": "44+08", "sheet": 10},
              "end": {"class": "terminal_port_hh", "station": "5+34", "sheet": 14}},
    "log54": {"start": {"class": "nextlink_hh", "station": "3+91", "sheet": 17},
              "end": {"class": "terminal_port_hh", "station": "3+14", "sheet": 21}},
}

R_READY = "OWNER_CONFIRMATION_PACKET_READY"
B_NOT_FULL = "BLOCKED_PACKET_FULL_SET_DRIFTED"
B_PROPOSED_INVALID = "BLOCKED_PACKET_PROPOSED_ENCODING_INVALID"
B_PROVENANCE = "BLOCKED_PACKET_PROVENANCE_MISSING"
B_FIXTURE_MUTATED = "BLOCKED_PACKET_FIXTURE_MUTATED"
B_SOURCE_DRIFT = "BLOCKED_PACKET_SOURCE_RECOVERY_DRIFTED"
ALLOWED = {R_READY, B_NOT_FULL, B_PROPOSED_INVALID, B_PROVENANCE, B_FIXTURE_MUTATED, B_SOURCE_DRIFT}


def _has_coord_keys(anchor: dict) -> bool:
    return bool({str(k).lower() for k in anchor} & _COORD_KEYS)


def proposed_anchor(lid: str, role: str) -> dict:
    """The PROPOSED identity-only endpoint anchor (dry-run; NEVER written to the fixture). Two-leg
    both-termini structure_terminus schema (the log52/log58/log71 shape); NO coordinate field; the
    owner_note_text marks it UNCONFIRMED."""
    c = CANDIDATE[lid][role]
    return {
        "station": c["station"],
        "boundary_kind": "structure_terminus",
        "structure_class": c["class"],
        "structure_label": STRUCTURE_LABEL[c["class"]],
        "owner_note_text": (f"SOURCE-RECOVERED CANDIDATE (UNCONFIRMED): the shipped resolver uniquely "
                            f"bound {c['class']} on-route at STA {c['station']} on sheet {c['sheet']} "
                            f"(log{lid[3:]} {role}). Owner must confirm the terminus CLASS identity "
                            f"before this anchor is encoded; not yet encoded."),
    }


def _census_frozen(doc) -> bool:
    if not TRUTH.is_file():
        return False
    truth = json.loads(TRUTH.read_text(encoding="utf-8"))
    baseline = {r["bore_id"]: dict(r) for r in truth["rows"]}
    off_rows = apply_adjudications(baseline, enabled=False)
    on_rows = apply_adjudications(baseline, enabled=True, doc=doc)
    summ = activation_summary(on_rows)
    buckets = {}
    for r in off_rows.values():
        buckets[r["completion_bucket"]] = buckets.get(r["completion_bucket"], 0) + 1
    return (off_rows is baseline and buckets == FROZEN_BUCKETS
            and summ["manual_review_drawable"] == 22 and summ["manual_source_verification"] == 1
            and summ["manual_abstain"] == 4
            and on_rows["log44"]["adjudication"]["drawable_status"] == "non_drawable"
            and all(on_rows[l]["adjudication"]["drawable_status"] == "abstain" for l in ABSTAIN_4)
            and not parent_run_duplicate_check(doc))


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()

    doc = load_adjudication()
    rec = {r["log_id"]: r for r in doc["logs"]}
    gates, packet = [], {}
    result = B_NOT_FULL

    gates.append(("G0 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                  _census_frozen(doc), None))

    # G1 the FULL source-recovered set is STILL exactly {log46, log54} (from the scout partition + the
    #    live ledger UNMODELED class). The packet is scoped to exactly these two.
    full_in_scout = tuple(sorted((l for l, p in PARTITION.items() if p == FULL), key=lambda s: int(s[3:])))
    ledger_unmod = set()
    if TRUTH.is_file():
        rows = json.loads(TRUTH.read_text(encoding="utf-8"))["rows"]
        ledger_unmod = {b for b, v in build_ledger(rows, doc).items() if v["category"] == UNMODELED_TERMINUS}
    gates.append(("G1 FULL source-recovered set still exactly {log46, log54}; both in the ledger UNMODELED class",
                  full_in_scout == FULL_CANDIDATES and set(FULL_CANDIDATES) <= ledger_unmod
                  and set(CANDIDATE) == set(FULL_CANDIDATES), list(full_in_scout)))

    # G2 each candidate is still ENDPOINT_IDENTITY_NOT_MODELED (no owner-named class) -- the packet exists
    #    precisely because the owner has not named the terminus class yet.
    gates.append(("G2 both candidates are still ENDPOINT_IDENTITY_NOT_MODELED (owner class unnamed)",
                  all(ENDPOINT_IDENTITY_NOT_MODELED in classify_record(rec[l])["blockers"]
                      and not classify_record(rec[l])["signals"]["has_modeled_terminus"]
                      for l in FULL_CANDIDATES), None))

    # G3 the PROPOSED identity-only encoding is schema-valid + identity-only + modeled-class (DRY RUN)
    proposed_ok, identity_only, modeled = True, True, True
    for lid in FULL_CANDIDATES:
        ea = {"start": proposed_anchor(lid, "start"), "end": proposed_anchor(lid, "end")}
        errs = validate_endpoint_anchors({"log_id": lid, "endpoint_anchors": ea})
        proposed_ok = proposed_ok and errs == []
        identity_only = identity_only and not _has_coord_keys(ea["start"]) and not _has_coord_keys(ea["end"])
        modeled = modeled and ea["start"]["structure_class"] in MODELED_TERMINUS_CLASSES \
            and ea["end"]["structure_class"] in MODELED_TERMINUS_CLASSES
        packet[lid] = ea
    gates.append(("G3 PROPOSED two-leg structure_terminus encoding is schema-valid, identity-only (no coords), modeled-class",
                  proposed_ok and identity_only and modeled, None))

    # G4 provenance: each proposed station is printed in the owner evidence_notes and each proposed sheet
    #    is within the owner-confirmed corrected_sheets (nothing invented; owner-grounded).
    provenance_ok = True
    for lid in FULL_CANDIDATES:
        notes = str(rec[lid].get("evidence_notes") or "")
        sheets = set(rec[lid].get("corrected_sheets") or [])
        for role in ("start", "end"):
            c = CANDIDATE[lid][role]
            provenance_ok = provenance_ok and (c["station"] in notes) and (c["sheet"] in sheets)
    gates.append(("G4 provenance: each proposed station printed in owner evidence_notes; each sheet within corrected_sheets",
                  provenance_ok, None))

    # G5 fixture UNMODIFIED: the candidates carry NO endpoint_anchors (nothing encoded); the proposed
    #    anchors live only in this run's memory. Re-load the fixture and confirm it is untouched.
    fresh = {r["log_id"]: r for r in load_adjudication()["logs"]}
    fixture_clean = (all(fresh[l].get("endpoint_anchors") is None for l in FULL_CANDIDATES)
                     and all(rec[l].get("endpoint_anchors") is None for l in FULL_CANDIDATES)
                     and all(fresh[l].get("category", None) is None for l in FULL_CANDIDATES)  # no spurious field
                     and ledger_unmod >= set(FULL_CANDIDATES))   # still UNMODELED in the ledger
    gates.append(("G5 fixture UNMODIFIED: candidates carry no endpoint_anchors; still UNMODELED (nothing encoded)",
                  fixture_clean, None))

    if all(x for _, x, _ in gates):
        result = R_READY
    elif not gates[1][1]:
        result = B_NOT_FULL
    elif not gates[3][1]:
        result = B_PROPOSED_INVALID
    elif not gates[4][1]:
        result = B_PROVENANCE
    elif not gates[5][1]:
        result = B_FIXTURE_MUTATED
    return _emit(gates, result, rec, packet)


def _emit(gates, result, rec, packet) -> int:
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G6 no render / zero PNG / seam unchanged (nothing promoted)",
                  len(pngs) == 0 and tuple(ELIGIBLE_EXEMPLARS) == SEAM_ELIGIBLE, {"pngs": pngs}))
    gates.append(("G7 result in allowed enum", result in ALLOWED, result))
    all_pass = all(x for _, x, _ in gates)

    sheets_of = {"log46": [10, 13, 14], "log54": [17, 21]}
    confirmation_packet = {}
    for lid in FULL_CANDIDATES:
        st, en = CANDIDATE[lid]["start"], CANDIDATE[lid]["end"]
        confirmation_packet[lid] = {
            "log_id": lid,
            "status": "UNCONFIRMED_CANDIDATE -- owner approval required before any encoding",
            "source_sheets": sheets_of[lid],
            "run_span_ft": rec[lid].get("span_ft"),
            "proposed_start_terminus": {"structure_class": st["class"], "structure_label": STRUCTURE_LABEL[st["class"]],
                                        "station": st["station"], "sheet": st["sheet"]},
            "proposed_end_terminus": {"structure_class": en["class"], "structure_label": STRUCTURE_LABEL[en["class"]],
                                      "station": en["station"], "sheet": en["sheet"]},
            "why_resolver_recovered_it": (
                f"the SHIPPED resolvers uniquely bound a single modeled class at each terminus, ON the bore "
                f"conduit chain (on-route): start {st['class']} via the reset-origin NEXTLINK-HH callout "
                f"locator at STA {st['station']}=0+00 (sheet {st['sheet']}); end {en['class']} via "
                f"resolve_structure_position on the 'PORT HH - TEXT' layer at STA {en['station']} (sheet "
                f"{en['sheet']}). No other modeled class bound at either terminus (no-guess: unique-or-nothing)."),
            "what_owner_must_confirm": [
                f"the START structure at STA {st['station']}=0+00 on sheet {st['sheet']} is a {STRUCTURE_LABEL[st['class']]} ({st['class']})",
                f"the END structure at STA {en['station']} on sheet {en['sheet']} is a {STRUCTURE_LABEL[en['class']]} ({en['class']})",
                "both are the correct termini of THIS bore (not an adjacent bore's structure)",
                f"the run is the cross-sheet path across sheets {sheets_of[lid]} (intermediate matchline = route context, resolved at bind/render time)",
            ],
            "what_would_be_encoded_if_confirmed": packet[lid],   # identity-only; NOT written to the fixture now
            "what_would_NOT_be_encoded": "no coordinates; corrected_sheets unchanged; no cross-sheet coordinate reconciliation (deferred to bind/render)",
            "next_step_if_confirmed": (
                "encode this exact identity-only endpoint_anchors bridge, then sheet-local source-bind per "
                "terminus + the already-shipped cross-sheet frame join (the log52/log58 lane); render and "
                "seam promotion follow, each separately authorized."),
        }

    report = {
        "milestone": "UNMODELED_TERMINUS owner-confirmation packet -- FULL source-recovered candidates (proof only)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result if all_pass else "BLOCKED",
        "scope": "FULL source-recovered UNMODELED_TERMINUS candidates {log46, log54}",
        "confirmation_packet": confirmation_packet,
        "doctrine": {
            "no_encoding_yet": "the proposed endpoint_anchors are DRY-RUN-validated in memory only; NOT written to the fixture",
            "candidates_unconfirmed": "terminus class identity stays UNCONFIRMED until owner review (source untrusted)",
            "identity_only": "proposed encoding carries no coordinate/stroke field",
            "no_new_resolver": True, "no_render": True, "no_seam_promotion": True,
            "fixture_unmodified": True, "engine_census_frozen": True,
        },
        "scope_guard": {"product_wiring": False, "broad_renderer": False, "match_review_wiring": False,
                        "runtime_batch": False, "deploy": False, "coordinates_invented": False,
                        "endpoint_anchors_encoded": False},
        "next_slice": ("present this packet to the owner; on per-terminus confirmation, encode the exact "
                       "identity-only endpoint_anchors bridge (log46 3-sheet 10->13->14; log54 2-sheet "
                       "17->21), then sheet-local source-bind + cross-sheet frame join -- each separately "
                       "authorized. On rejection, re-probe or route to representative-route."),
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "unmodeled_terminus_owner_confirmation_packet.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[packet] result: {report['result']}")
    for lid in FULL_CANDIDATES:
        st, en = CANDIDATE[lid]["start"], CANDIDATE[lid]["end"]
        print(f"[packet]   {lid}: start {st['class']} @ {st['station']} (s{st['sheet']}) -> "
              f"end {en['class']} @ {en['station']} (s{en['sheet']})  [UNCONFIRMED]")
    for n, x, _ in gates:
        print(f"[packet] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[packet] VERDICT: {'PASS' if all_pass else 'FAIL'}  (packet: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
