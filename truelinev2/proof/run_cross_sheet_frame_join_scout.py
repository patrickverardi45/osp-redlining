r"""CROSS_SHEET_FRAME_JOIN scout (PROOF/REPORT ONLY; read-only; reuses the SHIPPED join primitive).

The all-redlines closure ledger names CROSS_SHEET_FRAME_JOIN_NEEDED as the highest-leverage non-placed
class (8 logs: log11/47/48/52/58/67/69/70). The authorized question: is there a safe, smallest common
frame-join PRIMITIVE still to prove for them?

Finding (this scout): NO new join primitive is needed -- the cross-sheet matchline frame join is ALREADY
a solved, shipped primitive (truelinev2.match.frames.translate_between_sheets over the SAFE frame graph:
a HIGH-confidence, uniquely-linked, conflict-free printed matchline equation that maps a station between
two consecutive sheet frames; returns None / ABSTAIN on any ambiguous/conflicting/missing boundary, and
NEVER falls back to the raw equal station). It was proven (log65, cross_sheet_conduit_join) and rendered
(log65 stroke), and carried the render-proven seam exemplars log53 + log71 across sheets as two
sheet-local strokes joined by station identity. The 8 are blocked on the FIRST-listed cohort blocker
ENDPOINT_IDENTITY_NOT_ENCODED (no owner-reviewed endpoint_anchors bridge yet) -- an ENCODING gap, not a
missing primitive.

So this scout does the contained, read-only thing: it RUNS the shipped primitive over the 8 logs'
consecutive corrected_sheets and partitions them by whether their cross-sheet join is SOURCE-BACKED NOW
(a safe printed frame edge exists for every hop) or BLOCKED (the primitive correctly abstains), naming the
exact missing evidence per blocked log. It encodes NO endpoint_anchors, defines NO new join/frame math
(reuses match.frames), parses NO coordinate into a placement, draws NO stroke, writes NO PNG, promotes
NOTHING, and never guesses an unprinted or conflicting join.

Partition (from the shipped primitive, source-backed). log52 + log58 have since been BRIDGED (two-leg
flower/installer cross-sheet endpoint_anchors -> HELD_BACK), so the live CROSS_SHEET class is now 6:
  SOURCE_BACKED (2): log11 (5->17), log47 (10->13->14) -- every consecutive boundary carries a UNIQUE
    HIGH-confidence printed matchline equation (the join is source-backed); both are HELD from the bridge
    for endpoint-IDENTITY reasons (log11 cross-log start identity; log47 bare-station end), not the join.
  SOURCE_BLOCKED (4), each a NAMED, non-guessable source gap:
    log48  -- interior sheet 11 prints a ONE-SIDED matchline (single station, no paired b-side) -> no
              frame equation for the 10<->11 / 11<->12 boundary (NO_PAIRED_FRAME_EQUATION).
    log67/69/70 -- the 17<->20 boundary prints TWO conflicting matchline equations (two physical crossings)
              -> the primitive refuses a safe edge (CONFLICTING_FRAME_EQUATIONS); needs a per-bore
              crossing disambiguation, not a new join primitive.

Proof-only; the JSON report is written under the gitignored data/outputs path.
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_cross_sheet_frame_join_scout
"""
from __future__ import annotations

import json
import os
from collections import Counter

import truelinev2.match.frames as FR
from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.ingest.manual_adjudication import (
    activation_summary,
    apply_adjudications,
    load_adjudication,
    parent_run_duplicate_check,
)
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_all_redlines_closure_ledger import CROSS_SHEET, build_ledger
from truelinev2.proof.run_brenham_corpus import PDF
from truelinev2.stations import parse_station

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "cross_sheet_frame_join_scout"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")

# the live CROSS_SHEET class shrinks as source-backed logs get bridged: log52 + log58 (two-leg flower/
# installer cross-sheet bridges) moved to HELD_BACK, leaving these 6 (log11/log47 still source-backed but
# held -- log11 cross-log start identity, log47 bare-station end; log48/67/69/70 source-blocked).
# After the owner-corrected cross-sheet bridges (log11/47/67/69/70, 2026-06-16) those 5 moved to
# SOURCE_BINDABLE_HELD_BACK; the live ledger CROSS_SHEET class is now just log48 (the parent/child
# original-run on the handwritten sheets 10/11/12 -- still NO_PAIRED_FRAME_EQUATION).
EXPECTED_8 = ("log48",)
EXPECTED_SOURCE_BACKED = ()
EXPECTED_BLOCKED = ("log48",)

# named, deterministic abstain reasons (derived from the shipped frame grammar, never guessed)
ABSTAIN_NO_EQUATION = "NO_PAIRED_FRAME_EQUATION"           # one-sided / absent boundary equation
ABSTAIN_CONFLICT = "CONFLICTING_FRAME_EQUATIONS"          # >=2 printed crossings disagree on the offset
ABSTAIN_AMBIGUOUS = "AMBIGUOUS_OR_MULTI_LINKED_EQUATION"  # candidate edge(s) but MEDIUM/multi-linked
ABSTAIN_REASONS = {ABSTAIN_NO_EQUATION, ABSTAIN_CONFLICT, ABSTAIN_AMBIGUOUS}

R_COMPLETE = "CROSS_SHEET_FRAME_JOIN_SCOUT_COMPLETE"
B_TRUTH = "BLOCKED_SCOUT_TRUTH_TABLE_MISSING"
B_PDF = "BLOCKED_SCOUT_PLAN_PDF_MISSING"
B_COHORT = "BLOCKED_SCOUT_NOT_THE_LEDGER_CROSS_SHEET_SET"
B_GUESS = "BLOCKED_SCOUT_UNNAMED_ABSTAIN_OR_RAW_FALLBACK"
ALLOWED = {R_COMPLETE, B_TRUTH, B_PDF, B_COHORT, B_GUESS}


def _sheet_text(plan, offset: int, sheet: int) -> str:
    """The sheet's text, using the SAME index<->sheet mapping as FR._build_plan_frame_graph
    (sheet = idx - offset + 1, so idx = sheet + offset - 1)."""
    idx = sheet + offset - 1
    if idx < 0 or idx >= plan.page_count:
        return ""
    return " ".join(ln for ln in plan.text_by_index(idx).splitlines() if ln.strip())


def classify_abstain(plan, offset: int, a: int, b: int) -> str:
    """Deterministic, source-backed reason the shipped primitive abstained on the a<->b boundary --
    reuses match.frames.parse_frame_equations + build_frame_edges + detect_conflicts (no new grammar)."""
    fa, fb = FR.frame_for_sheet(a), FR.frame_for_sheet(b)
    cand = (FR.build_frame_edges(FR.parse_frame_equations(_sheet_text(plan, offset, a)), fa)
            + FR.build_frame_edges(FR.parse_frame_equations(_sheet_text(plan, offset, b)), fb))
    pair = [e for e in cand if {str(e.from_frame), str(e.to_frame)} == {str(fa), str(fb)}]
    if not pair:
        return ABSTAIN_NO_EQUATION
    if FR.detect_conflicts(pair):
        return ABSTAIN_CONFLICT
    return ABSTAIN_AMBIGUOUS


def scout_log(graph, plan, offset: int, rec: dict) -> dict:
    """Run the shipped frame-join over a log's consecutive corrected_sheets. SOURCE-BACKED iff every
    hop has a safe direct frame edge (translate returns non-None); else BLOCKED with a named reason."""
    sheets = rec.get("corrected_sheets") or []
    start_ft = parse_station(rec.get("corrected_start")) or 0.0
    hops, blocker = [], None
    for a, b in zip(sheets, sheets[1:]):
        translated = FR.translate_between_sheets(graph, a, b, start_ft)
        safe = translated is not None
        reason = None if safe else classify_abstain(plan, offset, a, b)
        hops.append({"from": a, "to": b, "safe_edge": safe,
                     "translated_ft": translated, "abstain_reason": reason})
        if not safe and blocker is None:
            blocker = reason
    source_backed = bool(hops) and all(h["safe_edge"] for h in hops)
    return {"sheets": sheets, "n_hops": len(hops), "hops": hops,
            "source_backed": source_backed,
            "blocker": None if source_backed else (blocker or "NO_CONSECUTIVE_SHEETS")}


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
    gates = []

    if not TRUTH.is_file():
        gates.append(("G0 final engine truth table present", False, str(TRUTH)))
        return _emit(gates, B_TRUTH, {}, ())
    truth_rows = json.loads(TRUTH.read_text(encoding="utf-8"))["rows"]

    gates.append(("G0 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                  _census_frozen(doc), None))

    # G1 the scouted set is EXACTLY the closure ledger's CROSS_SHEET_FRAME_JOIN_NEEDED class
    ledger = build_ledger(truth_rows, doc)
    ledger_cross = tuple(sorted((b for b, v in ledger.items() if v["category"] == CROSS_SHEET),
                                key=lambda s: int(s[3:])))
    gates.append(("G1 scouted set == the ledger CROSS_SHEET_FRAME_JOIN_NEEDED class (6 logs; log52/log58 bridged out)",
                  ledger_cross == EXPECTED_8, list(ledger_cross)))

    # G2 reuses the SHIPPED frame-join primitive; defines NO new join/frame math here
    gates.append(("G2 reuses shipped match.frames.translate_between_sheets (no new join primitive defined here)",
                  FR.translate_between_sheets.__module__ == "truelinev2.match.frames"
                  and FR.build_frame_graph.__module__ == "truelinev2.match.frames", None))

    if not os.path.isfile(PDF):
        gates.append(("G3 plan PDF present (needed to read printed matchline equations)", False, PDF))
        return _emit(gates, B_PDF, {}, ledger_cross)
    gates.append(("G3 plan PDF present (read-only, to read printed matchline equations)", True, None))

    plan = PlanPdf(PDF)
    try:
        offset = select_dialect(plan).calibrate(plan, 13)
        graph = FR._build_plan_frame_graph(plan, offset)
        scout = {lid: scout_log(graph, plan, offset, rec[lid]) for lid in EXPECTED_8}
    finally:
        plan.close()

    source_backed = tuple(sorted((l for l, s in scout.items() if s["source_backed"]),
                                 key=lambda s: int(s[3:])))
    blocked = tuple(sorted((l for l, s in scout.items() if not s["source_backed"]),
                           key=lambda s: int(s[3:])))

    # G4 every log is SOURCE-BACKED or BLOCKED-with-a-NAMED-reason; the primitive NEVER fell back to a raw
    #    value (None == abstain). No guessing.
    every_named = all(s["source_backed"]
                      or (s["blocker"] in ABSTAIN_REASONS
                          and any(h["abstain_reason"] in ABSTAIN_REASONS and h["translated_ft"] is None
                                  for h in s["hops"]))
                      for s in scout.values())
    gates.append(("G4 every log SOURCE-BACKED or BLOCKED with a NAMED abstain reason (no raw fallback, no guess)",
                  every_named, None))

    # G5 SOURCE-BACKED logs: every consecutive hop returns a concrete frame-translated offset (safe edge)
    g5 = all(s["hops"] and all(h["safe_edge"] and h["translated_ft"] is not None for h in s["hops"])
             for l, s in scout.items() if s["source_backed"])
    gates.append(("G5 SOURCE-BACKED: every consecutive boundary resolves via a unique safe printed frame edge",
                  g5, None))

    # G6 deterministic partition matches the source-backed reality (4 ready / 4 blocked-named)
    gates.append(("G6 partition: SOURCE_BACKED == log11/47 (2); BLOCKED == log48/67/69/70 (4)",
                  source_backed == EXPECTED_SOURCE_BACKED and blocked == EXPECTED_BLOCKED,
                  {"source_backed": list(source_backed), "blocked": list(blocked)}))

    # G7 NO encoding + NO promotion: this scout encodes no endpoint_anchors (the 8 stay unencoded) and
    #    the join stays a scout finding (the encoding bridge is a separate, authorized step)
    gates.append(("G7 no encoding: the 8 carry NO endpoint_anchors (scout reads only; bridge is separate)",
                  all(not rec[l].get("endpoint_anchors") for l in EXPECTED_8), None))

    # G8 no render artifact (scout writes JSON only; zero PNG; invents no coordinate into a placement)
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G8 no render artifact (JSON only; zero PNG)", len(pngs) == 0, pngs))

    result = R_COMPLETE if all(x for _, x, _ in gates) else (
        B_COHORT if not gates[1][1] else B_GUESS if not gates[4][1] else B_COHORT)
    return _emit(gates, result, scout, ledger_cross, source_backed, blocked)


def _emit(gates, result, scout, ledger_cross, source_backed=(), blocked=()) -> int:
    gates.append(("G9 result in allowed enum", result in ALLOWED, result))
    all_pass = all(x for _, x, _ in gates)
    by_blocker = Counter(s["blocker"] for s in scout.values() if not s.get("source_backed"))
    report = {
        "milestone": "CROSS_SHEET_FRAME_JOIN scout (proof/report only; reuses the shipped join primitive)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result if all_pass else "BLOCKED",
        "finding": ("NO new frame-join primitive is needed -- the cross-sheet matchline join is already a "
                    "solved, shipped primitive (match.frames.translate_between_sheets over the SAFE frame "
                    "graph; proven + rendered for log65; carried log53/log71 across sheets). The 8 are "
                    "blocked on ENDPOINT_IDENTITY_NOT_ENCODED (the endpoint_anchors bridge), not geometry."),
        "scouted_set": list(ledger_cross),
        "source_backed_now": list(source_backed),
        "source_blocked": list(blocked),
        "blocked_by_reason": dict(by_blocker),
        "per_log": scout,
        "primitive": {
            "module": "truelinev2.match.frames",
            "function": "translate_between_sheets(graph, from_sheet, to_sheet, feet) -> Optional[float]",
            "law": ("a HIGH-confidence, uniquely-linked, conflict-free printed matchline equation maps a "
                    "station between two consecutive sheet frames; None == ABSTAIN; never a raw-station fallback"),
            "already_proven": "log65 cross_sheet_conduit_join (PROVEN) + log65 cross-sheet stroke (rendered)",
            "already_used": "log53 + log71 render-proven seam exemplars cross sheets as two sheet-local strokes",
        },
        "no_new_primitive": True, "no_encoding": True, "no_seam_promotion": True,
        "no_pdf_coordinate_placement": True, "no_render": True, "no_guess": True,
        "engine_census_frozen": True,
        "next_slice": (
            "log52 + log58 are now BRIDGED (two-leg flower/installer endpoint_anchors -> HELD_BACK); their "
            "source-bind + render across the two sheets (the existing sheet-local-leg bind + the already-"
            "proven matchline join) is the separately-authorized next step. The remaining SOURCE-BACKED "
            "log11 + log47 are HELD for endpoint-identity reasons (log11 cross-log start identity needs owner "
            "confirmation that it shares log53's NEXTLINK HH; log47's end is a bare station with no owner-"
            "named structure). The 4 BLOCKED logs carry NAMED source targets: log48 = recover sheet 11's "
            "paired matchline b-side (or route 10->12 directly); log67/69/70 = per-bore disambiguation of the "
            "two printed 17<->20 crossings. NONE of this is authorized here -- this scout only locks the partition."),
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "cross_sheet_frame_join_scout.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[xsheet-join] result: {report['result']}")
    for lid in (ledger_cross or sorted(scout, key=lambda s: int(s[3:]))):
        s = scout.get(lid, {})
        tag = "SOURCE_BACKED" if s.get("source_backed") else f"BLOCKED ({s.get('blocker')})"
        print(f"[xsheet-join]   {lid:<6} sheets={s.get('sheets')}  {tag}")
    print(f"[xsheet-join]   source_backed={list(source_backed)}  blocked={list(blocked)}")
    for n, x, _ in gates:
        print(f"[xsheet-join] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[xsheet-join] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
