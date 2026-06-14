r"""OWNER-PACKET-2 -- manual adjudication ACTIVATION proof (default-OFF flag).

Proves the resolution-layer activation overlay (flag ``TRUELINE_MANUAL_ADJUDICATIONS`` /
``Settings.manual_adjudications_optin``):

* flag OFF  -> the M8.27 truth-table rows are returned UNCHANGED; the frozen census
               (31 drawable; buckets 31/6/1/17/3) is byte-identical.
* flag ON   -> the 27 reviewed problem logs are reclassified out of their false
               unresolved/owner-source buckets into review-drawable / source-
               verification / hard-abstain, carrying ONLY owner-reviewed corrected
               facts. The 31 already-drawable rows are untouched. No geometry is
               invented; no match engine is re-run; no placement is forced.

Every movement count is computed from the ACTUAL overlay output, not asserted.
Read-only; writes one gitignored JSON. No PDF parse.
"""
from __future__ import annotations

import json
from pathlib import Path

from truelinev2.config import _REPO_ROOT, Settings
from truelinev2.ingest.manual_adjudication import (
    ADJ_BUCKET_ABSTAIN,
    ADJ_BUCKET_REVIEW_DRAWABLE,
    ADJ_BUCKET_SOURCE_VERIFY,
    activation_summary,
    apply_adjudications,
    load_adjudication,
    parent_run_duplicate_check,
    validate_adjudication,
)

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "manual_adjudication_activation"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
RECON2B = _REPO_ROOT / "data" / "outputs" / "parent_child_print_assignment_phase0" / \
    "parent_child_print_assignment_phase0.json"

EXPECTED_27 = {
    "log6", "log63", "log64", "log46", "log47", "log52", "log53", "log58", "log67",
    "log70", "log71", "log11", "log12", "log29", "log36", "log41", "log44", "log48",
    "log54", "log59", "log66", "log68", "log69",
    "log5", "log31", "log38", "log43",
}
SHARED_PRINT_11 = {
    "log6", "log46", "log47", "log52", "log53", "log58", "log63", "log64", "log67",
    "log70", "log71",
}
ABSTAIN_4 = {"log5", "log31", "log38", "log43"}
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}


def _bucket_counts(rows):
    c = {}
    for r in rows.values():
        c[r["completion_bucket"]] = c.get(r["completion_bucket"], 0) + 1
    return c


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    truth = json.loads(TRUTH.read_text(encoding="utf-8"))
    baseline = {r["bore_id"]: dict(r) for r in truth["rows"]}
    doc = load_adjudication()

    # default-OFF flag check (constructed Settings, no env mutation)
    default_off = Settings.from_env().manual_adjudications_optin

    off_rows = apply_adjudications(baseline, enabled=False)
    on_rows = apply_adjudications(baseline, enabled=True, doc=doc)
    summ = activation_summary(on_rows)

    gates = []

    # G0 -- the flag defaults OFF
    gates.append(("G0 flag TRUELINE_MANUAL_ADJUDICATIONS defaults OFF", default_off is False,
                  {"default": default_off}))

    # G1 -- flag OFF is byte-identical: same object, no overlay key, census frozen
    off_counts = _bucket_counts(off_rows)
    g1 = (off_rows is baseline
          and not any("adjudication" in r for r in off_rows.values())
          and off_counts == FROZEN_BUCKETS)
    gates.append(("G1 flag OFF census byte-identical (31/6/1/17/3)", g1, off_counts))

    # G2 -- flag ON: artifact loads + validates
    errs = validate_adjudication(doc)
    gates.append(("G2 flag ON artifact loads and validates", not errs, errs[:5]))

    # G3 -- all 27 logs represented exactly once and overlaid under flag ON
    overlaid = {b for b, r in on_rows.items() if r.get("adjudication")}
    g3 = overlaid == EXPECTED_27 and len(overlaid) == 27
    gates.append(("G3 all 27 logs represented exactly once", g3,
                  {"n": len(overlaid), "missing": sorted(EXPECTED_27 - overlaid),
                   "extra": sorted(overlaid - EXPECTED_27)}))

    # G4 -- the 4 abstains remain abstained (hard) under flag ON
    g4 = all(on_rows[l]["adjudication"]["drawable_status"] == "abstain"
             and on_rows[l]["completion_bucket"] == ADJ_BUCKET_ABSTAIN
             and on_rows[l]["can_draw_now"] is False for l in ABSTAIN_4)
    gates.append(("G4 the 4 no-good logs remain abstained", g4, sorted(ABSTAIN_4)))

    # G5 -- log44 non-drawable / source-verification
    a44 = on_rows["log44"]["adjudication"]
    g5 = (a44["drawable_status"] == "non_drawable"
          and on_rows["log44"]["completion_bucket"] == ADJ_BUCKET_SOURCE_VERIFY
          and a44["needs_source_verification"] is True
          and on_rows["log44"]["can_draw_now"] is False)
    gates.append(("G5 log44 source-verification / non-drawable", g5, a44["drawable_status"]))

    # G6 -- log68 / log69 not mixed
    a68, a69 = on_rows["log68"]["adjudication"], on_rows["log69"]["adjudication"]
    g6 = (a68["corrected_start"] == "5+03" and a68["corrected_end"] == "6+79"
          and "4+54" not in (a68["corrected_start"], a68["corrected_end"])
          and a69["corrected_start"] == "2+15" and a69["corrected_end"] == "4+54")
    gates.append(("G6 log68=5+03->6+79 (never 4+54); log69=2+15->4+54", g6,
                  {"log68": (a68["corrected_start"], a68["corrected_end"]),
                   "log69": (a69["corrected_start"], a69["corrected_end"])}))

    # G7 -- corrected print 17,20 for log67/68/69/70
    g7 = all(on_rows[l]["adjudication"]["corrected_prints"] == [17, 20]
             for l in ("log67", "log68", "log69", "log70"))
    gates.append(("G7 log67/68/69/70 corrected print = 17,20", g7,
                  {l: on_rows[l]["adjudication"]["corrected_prints"]
                   for l in ("log67", "log68", "log69", "log70")}))

    # G8 -- the 11 shared-print children no longer OWNER_SOURCE_REQUIRED_SHARED_PRINT_AMBIGUITY
    g8 = all(on_rows[l]["completion_bucket"] == ADJ_BUCKET_REVIEW_DRAWABLE
             and on_rows[l]["adjudication"]["drawable_status"] == "review_drawable"
             for l in SHARED_PRINT_11)
    cross = {}
    if RECON2B.is_file():
        r2 = {c["child"]: c for c in json.loads(RECON2B.read_text(encoding="utf-8"))["children"]}
        was_ambig = {l for l in SHARED_PRINT_11
                     if r2.get(l, {}).get("classification") == "UNASSIGNABLE_SHARED_PRINT_AMBIGUITY"}
        cross = {"recon2b_were_ambiguous": sorted(was_ambig)}
        g8 = g8 and (was_ambig == SHARED_PRINT_11)
    gates.append(("G8 11 shared-print children -> review-drawable (were ambiguous)", g8, cross))

    # G9 -- no parent/child duplicate overlapping redline (artifact-level + flag-on family check)
    dup = parent_run_duplicate_check(doc)
    fam_geo = {}
    fam_dup = []
    for b, r in on_rows.items():
        adj = r.get("adjudication")
        if not adj or adj["drawable_status"] != "review_drawable":
            continue
        fam = baseline[b].get("source_family")
        key = (fam, adj["corrected_start"], adj["corrected_end"], tuple(adj["corrected_sheets"]))
        if None in (adj["corrected_start"], adj["corrected_end"]):
            continue
        if key in fam_geo:
            fam_dup.append(f"{b} duplicates {fam_geo[key]}")
        else:
            fam_geo[key] = b
    g9 = (not dup) and (not fam_dup)
    gates.append(("G9 no parent/child duplicate overlapping redline", g9,
                  {"artifact": dup, "flag_on_family": fam_dup}))

    # G10 -- movement count proven from ACTUAL overlay output
    g10 = (summ["moved_count"] == 27
           and summ["manual_review_drawable"] == 22
           and summ["manual_source_verification"] == 1
           and summ["manual_abstain"] == 4
           and summ["engine_drawable_unchanged"] == 31)
    gates.append(("G10 movement from actual output (27 moved: 22/1/4; 31 engine-drawable)",
                  g10, {k: summ[k] for k in ("moved_count", "manual_review_drawable",
                        "manual_source_verification", "manual_abstain",
                        "engine_drawable_unchanged")}))

    # G11 -- flag ON leaves the 31 engine-drawable rows untouched (no overlay, still DRAWABLE_REVIEW)
    engine_dr = [b for b, r in on_rows.items()
                 if not r.get("adjudication") and r["completion_bucket"] == "DRAWABLE_REVIEW"]
    g11 = (len(engine_dr) == 31
           and all(on_rows[b] == baseline[b] for b in engine_dr))
    gates.append(("G11 flag ON does not touch the 31 engine-drawable", g11, {"n": len(engine_dr)}))

    # G12 -- census conservation: ON buckets sum to 58
    on_counts = _bucket_counts(on_rows)
    g12 = sum(on_counts.values()) == 58 and sum(off_counts.values()) == 58
    gates.append(("G12 census conservation (58 both states)", g12,
                  {"on": on_counts, "off_total": sum(off_counts.values())}))

    all_pass = all(g for _, g, _ in gates)

    report = {
        "milestone": "OWNER-PACKET-2 -- manual adjudication ACTIVATION proof (default-OFF)",
        "verdict": "PASS" if all_pass else "FAIL",
        "flag": "TRUELINE_MANUAL_ADJUDICATIONS (Settings.manual_adjudications_optin)",
        "flag_default": default_off,
        "consumer": "truelinev2.ingest.manual_adjudication.apply_adjudications "
                    "(resolution-layer overlay over the M8.27 truth-table rows)",
        "flag_off": {"bucket_counts": off_counts, "byte_identical": g1},
        "flag_on": {
            "bucket_counts": on_counts,
            "engine_drawable_unchanged": summ["engine_drawable_unchanged"],
            "manual_review_drawable": summ["manual_review_drawable"],
            "manual_source_verification": summ["manual_source_verification"],
            "manual_abstain": summ["manual_abstain"],
            "moved_count": summ["moved_count"],
            "movement": summ["moved"],
        },
        "counts": {
            "drawable_flag_off": off_counts.get("DRAWABLE_REVIEW", 0),
            "review_drawable_flag_on_total": summ["engine_drawable_unchanged"] + summ["manual_review_drawable"],
            "still_abstain": summ["manual_abstain"],
            "still_source_verification": summ["manual_source_verification"],
            "remaining_unresolved": 0,
        },
        "gates": [{"name": n, "pass": bool(g), "detail": d} for n, g, d in gates],
    }
    (OUT_DIR / "manual_adjudication_activation.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")

    print("[activation] flag default OFF:", default_off)
    print("[activation] flag OFF buckets:", off_counts)
    print("[activation] flag ON  buckets:", on_counts)
    print(f"[activation] flag ON movement: {summ['moved_count']} moved "
          f"(review-drawable {summ['manual_review_drawable']}, "
          f"source-verify {summ['manual_source_verification']}, "
          f"abstain {summ['manual_abstain']}; engine-drawable {summ['engine_drawable_unchanged']} unchanged)")
    for n, g, d in gates:
        print(f"[activation] {'PASS' if g else 'FAIL'}  {n}")
    print(f"[activation] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
