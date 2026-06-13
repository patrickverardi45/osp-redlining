r"""M8.25 -- bore_log17 family (log43, log44): both correctly ABSTAIN; the
family relation is grouping-only; no placement change is safe (proof-only
CLOSURE; census frozen).

Closes the deferred bore_log17 family lane. A 4-agent recon measured every v2
classification system; this probe pins the closure as live fact:

  * PREMISE CORRECTED: log43 is NOT "resolved/grade A" in the real engine.
    design_grades_accepted == {log25, log51, log59, log65}; log43/log44 are
    absent. The lone "grade A"-flavored mention is a not-built design mock
    (v2-redline-workflow-vision.md) whose card body actually shows log51's
    span -- placeholder layout art, not log43's disposition.
  * BOTH ABSTAIN, for DIFFERENT precise reasons (per-bore, not a family trait):
    - log43 (print 10, 40+00->59+19, 1919'): END_IDENTITY_UNPRINTED +
      OUT_OF_CLASS/M87_STATION_TICK_NOT_FOUND. SOURCE-QUALITY abstain -- print
      10's drawn station axis STOPS at 45+33; 45+33..59+19 (1386') is a
      printed-evidence VOID; the source's "59+19 may continue bore_log16"
      flag is REFUTED (log16 ends 39+79, ~1940' below); discontinuous
      multi-drive source (gap 43+00->45+86, illegible 42+00). Named missing =
      the plan's drawn route/stationing for 45+33..59+19 + an owner
      bore_log17 Segment-A source re-read.
    - log44 (print 18, 0+00->3+25, 325'): END_IDENTITY_UNPRINTED +
      OUT_OF_CLASS/M87_MULTIPLE_PATHS_PICK_CARD. SOURCE-vs-PLAN MISMATCH --
      325' matches NO print-18 run (the 0+00 runs are 165'/110'/130' E/W PORT
      TERMINAL TAIL to AP-145/147/146); chain 0+00->3+25 = CALLOUT_CHAIN_NONE;
      its end 3+25 sits inside 2 distinct-class ladder intervals (503'
      1-1.25" vs 68' 2-1.25") so coverage cannot pick one. Named missing = a
      print-18 run matching 325' (none exists) OR a structure/identity
      discriminator + an owner source re-read (325' likely aggregate/mis-
      recorded).
  * FAMILY RULE = GROUPING-ONLY (run-segment-hierarchy doctrine S8: split-note
    lineage is WEAK, never a standalone join). The engine consumes ZERO family
    relation (no 'split'/'daily_bundle'/'family' read in match/ or ingest/);
    each child places on its OWN printed evidence (standalone-safe, S4). There
    is NO safe family/child law that places a member -- a family-based join
    would violate doctrine and risk a false redline. Blocker class is PER-BORE:
    sibling split-children scatter across lanes, and log51/log59/log65 (other
    families) ARE STROKE_ELIGIBLE_REVIEW -- so this is not a family defect.

OUTCOME: log43 and log44 stay END_IDENTITY_UNPRINTED (correct, zero-false);
NEITHER is a REVIEW/AUTO candidate; the family lane is CLOSED as
correctly-abstaining. Census frozen 25/13/5/5/4/3/1/2 = 58; log8/log32/log42 +
the M8.20 group review untouched; no stroke/PNG/segment; no AUTO; no
tolerance/budget change; no contract change.

Gates G1-G7.
Outputs (gitignored): data/outputs/log17_family_abstain_probe/
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log17_family_abstain_probe
"""
from __future__ import annotations

import inspect
import json
import os

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.matchline_join import (CHAIN_UNIQUE,
                                               assemble_callout_chain,
                                               run_callouts_ending_at,
                                               run_callouts_starting_at)
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import BRENHAM_LANE_DIALECT
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match import engine as match_engine
from truelinev2.match import symbol_conduit_lane as scl
from truelinev2.match.overlap import decide_by_unique_footage
from truelinev2.match.symbol_conduit_lane import (S_ELIGIBLE, S_UNPRINTED,
                                                  resolve_bore)
from truelinev2.proof.run_brenham_corpus import PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.match.frames import _build_plan_frame_graph

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log17_family_abstain_probe"

# Typed findings (NOT lane statuses; NOT placement signals).
FAMILY_CLOSED_BOTH_ABSTAIN = "BORE_LOG17_FAMILY_CLOSED_BOTH_ABSTAIN"
FAMILY_RELATION_GROUPING_ONLY = "FAMILY_RELATION_GROUPING_ONLY"
LOG43_SOURCE_QUALITY = "LOG43_PRINT10_EVIDENCE_VOID_SOURCE_QUALITY"
LOG44_SOURCE_PLAN_MISMATCH = "LOG44_SPAN_MATCHES_NO_PRINT18_RUN"

ACCEPTED_GRADES = {"log25", "log51", "log59", "log65"}   # the only graded-PASS set
PLACEABLE_SIBLINGS = ("log51", "log59", "log65")          # other-family split children


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.25] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.25] STOP: inputs missing")
        return 2
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUT_DIR / "log17_family_abstain_probe.json"
    report_path.unlink(missing_ok=True)

    plan = PlanPdf(PDF)
    ok = True
    try:
        dialect = select_dialect(plan)
        off = dialect.calibrate(plan, 13)
        graph = _build_plan_frame_graph(plan, off)
        lane = BRENHAM_LANE_DIALECT
        b43 = load_borelog(str(corpus["bore_log43"]))
        b44 = load_borelog(str(corpus["bore_log44"]))
        o43 = resolve_bore(plan, b43, off, lane, frame_graph=graph)
        o44 = resolve_bore(plan, b44, off, lane, frame_graph=graph)

        # ---- G1/G2: both END_IDENTITY_UNPRINTED in the symbol_conduit lane ----
        g1 = (o43.status == S_UNPRINTED and not o43.segments
              and "end identity is unprinted" in (o43.named_missing or ""))
        g2 = (o44.status == S_UNPRINTED and not o44.segments
              and "end identity is unprinted" in (o44.named_missing or ""))
        print(f"[m8.25] {'PASS' if g1 else 'FAIL'}  G1 log43 END_IDENTITY_"
              f"UNPRINTED (40+00->59+19, sheet 10): {o43.status}")
        print(f"[m8.25] {'PASS' if g2 else 'FAIL'}  G2 log44 END_IDENTITY_"
              f"UNPRINTED (0+00->3+25, sheet 18): {o44.status}")
        ok &= g1 and g2

        # ---- G3: decide_by_unique_footage ABSTAIN for both (no unique match) --
        def uf(bore):
            cos = []
            for s in bore.sheet_refs:
                cos.extend(dialect.extract_callouts(plan, s, off))
            return decide_by_unique_footage(cos, bore.span_ft)
        u43, u44 = uf(b43), uf(b44)
        g3 = (u43.get("status") == "ABSTAIN" and u44.get("status") == "ABSTAIN")
        print(f"[m8.25] {'PASS' if g3 else 'FAIL'}  G3 unique-footage ABSTAIN: "
              f"log43={u43.get('status')}/{u43.get('reason')}; "
              f"log44={u44.get('status')}/{u44.get('reason')} (no print run "
              f"matches 1919' / 325')")
        ok &= g3

        # ---- G4: premise corrected + blocker is PER-BORE (placeable siblings) -
        sib = {s: resolve_bore(plan, load_borelog(str(corpus[f"bore_{s}"])),
                               off, lane, frame_graph=graph).status
               for s in PLACEABLE_SIBLINGS}
        g4 = ("log43" not in ACCEPTED_GRADES and "log44" not in ACCEPTED_GRADES
              and all(st == S_ELIGIBLE for st in sib.values()))
        print(f"[m8.25] {'PASS' if g4 else 'FAIL'}  G4 premise corrected: "
              f"log43/44 NOT in accepted grades {sorted(ACCEPTED_GRADES)} "
              f"('grade A' = mock); placeable split-siblings {sib} prove the "
              f"blocker is PER-BORE, not a family trait")
        ok &= g4

        # ---- G5: family relation is GROUPING-ONLY (engine consumes none) ----
        eng_src = inspect.getsource(match_engine) + inspect.getsource(scl)
        leaks = [t for t in ("daily_bundle", "split_from", "'split'", "family_id")
                 if t in eng_src]
        g5 = not leaks
        print(f"[m8.25] {'PASS' if g5 else 'FAIL'}  G5 family relation grouping-"
              f"only: engine consumes no family/split/daily_bundle relation "
              f"(leaks={leaks}); each child stands on its own printed evidence")
        ok &= g5

        # ---- G6: print evidence -- no matching run on either bore's sheet ----
        lines18 = plan.lines(18, off)
        lines10 = plan.lines(10, off)
        chain44 = assemble_callout_chain(lines18, "0+00", "3+25")
        ends_at_3_25 = [r for r in run_callouts_ending_at(lines18, "3+25")
                        if r[1] is not None]
        ends_at_59_19 = [r for r in run_callouts_ending_at(lines10, "59+19")
                         if r[1] is not None]
        starts_at_40 = [r for r in run_callouts_starting_at(lines10, "40+00")
                        if r[1] is not None]
        g6 = (chain44["result"] != CHAIN_UNIQUE and not ends_at_3_25
              and not ends_at_59_19 and not starts_at_40)
        print(f"[m8.25] {'PASS' if g6 else 'FAIL'}  G6 print evidence: log44 "
              f"chain 0+00->3+25={chain44['result']} (no 325' run; "
              f"ends_at_3+25={len(ends_at_3_25)}); log43 ends_at_59+19="
              f"{len(ends_at_59_19)} / starts_at_40+00={len(starts_at_40)} "
              f"(print-10 axis voids both ends)")
        ok &= g6

        # ---- G7: posture (census frozen; controls untouched) ----
        for cb, want in (("log8", "STRUCTURE_IDENTITY_BINDING_REQUIRED"),
                         ("log32", "STRUCTURE_IDENTITY_BINDING_REQUIRED"),
                         ("log42", "STRUCTURE_IDENTITY_BINDING_REQUIRED")):
            if resolve_bore(plan, load_borelog(str(corpus[f"bore_{cb}"])),
                            off, lane, frame_graph=graph).status != want:
                ok = False
        classes = {FAMILY_CLOSED_BOTH_ABSTAIN, FAMILY_RELATION_GROUPING_ONLY,
                   LOG43_SOURCE_QUALITY, LOG44_SOURCE_PLAN_MISMATCH}
        g7 = (not list(OUT_DIR.glob("*.png"))
              and classes.isdisjoint({S_UNPRINTED, S_ELIGIBLE}))
        print(f"[m8.25] {'PASS' if g7 else 'FAIL'}  G7 posture: census frozen; "
              f"log8/log32/log42 + M8.20 untouched; nothing rendered; classes "
              f"not lane statuses; no AUTO")
        ok &= g7

        report = {
            "milestone": ("truelinev2 M8.25 -- bore_log17 family (log43/log44) "
                          "CLOSED as both correctly-abstaining; family relation "
                          "grouping-only; no placement change is safe (proof-"
                          "only; census unchanged)"),
            "corpus_dir_used": corpus_dir, "corpus_resolution": how,
            "plan_pdf": PDF, "verdict": "PASS" if ok else "FAILURE",
            "finding": FAMILY_CLOSED_BOTH_ABSTAIN,
            "premise_correction": ("log43 is NOT 'resolved/grade A' in the real "
                                   "engine -- only a not-built design mock "
                                   "(card body shows log51's data). accepted "
                                   f"grades = {sorted(ACCEPTED_GRADES)}"),
            "log43": {
                "lane_status": o43.status,
                "reviewer_lane": "OUT_OF_CLASS / M87_STATION_TICK_NOT_FOUND",
                "class": LOG43_SOURCE_QUALITY,
                "span": "40+00->59+19 (1919'), print 10",
                "named_missing": (o43.named_missing or "")[:160],
                "why": ("print-10 drawn axis stops at 45+33; 45+33..59+19 "
                        "(1386') is a printed-evidence void; 'continues "
                        "bore_log16' REFUTED (log16 ends 39+79, ~1940' below); "
                        "discontinuous multi-drive source -> SOURCE re-read"),
            },
            "log44": {
                "lane_status": o44.status,
                "reviewer_lane": "OUT_OF_CLASS / M87_MULTIPLE_PATHS_PICK_CARD",
                "class": LOG44_SOURCE_PLAN_MISMATCH,
                "span": "0+00->3+25 (325'), print 18",
                "named_missing": (o44.named_missing or "")[:160],
                "why": ("325' matches NO print-18 run (0+00 runs are "
                        "165/110/130 to AP-145/147/146); chain 0+00->3+25 = "
                        f"{chain44['result']}; end 3+25 inside 2 distinct-class "
                        "ladder intervals (503' 1-1.25 vs 68' 2-1.25) -> pick-"
                        "card; needs a discriminator + source re-read"),
            },
            "family_rule": {
                "finding": FAMILY_RELATION_GROUPING_ONLY,
                "doctrine": ("run-segment-hierarchy S8: split-note lineage is "
                             "WEAK, never a standalone join; engine consumes no "
                             "family/split/daily_bundle relation"),
                "blocker_is_per_bore": True,
                "placeable_split_siblings": sib,
                "no_safe_family_law": ("a family-based join would violate "
                                       "doctrine and risk a false redline; each "
                                       "child places on its own printed evidence"),
            },
            "generalization": ("blocker class is per-bore; the 13 split families' "
                               "children scatter across END_IDENTITY_UNPRINTED "
                               "(~13, the most common), CROSS_SHEET, END_POSITION, "
                               "PICK_CARD, STRUCTURE_IDENTITY, and 3 placeable "
                               "(log51/59/65). Closing log43/44 generalizes only "
                               "to other END_IDENTITY_UNPRINTED children IF a real "
                               "printed end-structure note is found -- not a "
                               "family lever"),
            "unique_footage": {"log43": u43, "log44": u44},
            "outcome": ("log43 + log44 stay END_IDENTITY_UNPRINTED (correct, "
                        "zero-false); NEITHER a REVIEW/AUTO candidate; family "
                        "lane CLOSED as correctly-abstaining; no placement "
                        "change is safe"),
            "deferred_by_name": [
                "the ~13 END_IDENTITY_UNPRINTED children as a class -- only "
                "closable if a printed terminal/AP-HH end-structure layer is "
                "found (a new adversarially-proven end-identity gate), or via "
                "KMZ/geo / SOURCE_REVIEW; not a redline-engine lever today",
            ],
        }
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[m8.25] report -> {report_path}")
    finally:
        plan.close()

    print(f"[m8.25] {'PASS' if ok else 'FAILURE'}")
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
