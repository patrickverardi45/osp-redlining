r"""M8.16/M8.17 -- cross-sheet origin continuation: the 16-bore evidence census.

The M8.14.c lane's ``cross_sheet_origin`` DISCOVERY law (printed-only:
end-sheet boundary callout -> unique frame-equation edge -> bore-ref check ->
reciprocal far-sheet segment [direct callout OR, M8.17, a uniqueness-mandatory
segmented callout CHAIN] + footage closure -> printed conduit class ->
corroborated unique far-sheet start structure against a CONSISTENT ladder band
-> full b.9 join re-proof) run over ALL 16 banked
CROSS_SHEET_CONTINUATION_REQUIRED bores plus the discovery-law regression set
(log65 printed-identity path; log50 pick-card).

THE BANKED RESULT IS AN HONEST NEGATIVE: ZERO of the 16 convert to strokes
under current printed evidence -- and every blocker is now NAMED per bore.
M8.17 callout-chain assembly sharpened log8 + log32 from "no reciprocal"
(CROSS_SHEET) to "start structure identity required" (their far segment is
PROVEN from a segmented printed chain; only the multi-ladder start-identity
remains -- they join log42 at that frontier):

  * NO printed frame equation at the bore's boundary (the log50-class gap):
    log14 (sheet 15), log61/log62 (sheet 6), log67/log68/log70 (sheet 20)
    -- sheets 4, 6, 11, 15, 16, 19, 20, 21 print NO matchline equations
  * no printed run callout ENDING at the bore end: log46, log71, log72
  * full-span callout only (prints no crossing boundary, yet the drawn chain
    exits the sheet -- a contradiction the census surfaces): log60, log64
  * far-sheet segment is a MULTI-CALLOUT CHAIN (printed as 0+00->mid->boundary):
    M8.17 callout-chain assembly now PROVES the far segment + closure for
    log8 (0+00->1+10->1+76, 110'+66'=176', +214' end = 390' span) and log32
    (0+00->1+30->1+77, 130'+47'=177', +36' end = 213' span); only the start-
    structure identity remains (the multi-ladder band, same as log42) ->
    both advance to STRUCTURE_IDENTITY_BINDING_REQUIRED, NOT strokes
  * the bore log's own sheet references do not name the discovered far sheet
    (the bore references only sheet 3; the equation names sheet 23): log12
  * printed-identity matchline path, no shared boundary callouts: log10
  * rival far-sheet structures on one conduit network; the corroboration
    band has NO consistent basis (the y-band holds ticks from TWO interleaved
    drawn ladders -> multi-modal hop scales; the adversarial review proved a
    naive median would have corroborated exactly the WRONG candidates):
    log42 -> STRUCTURE_IDENTITY_BINDING_REQUIRED (pick-card class)

Embedded gates (any failure -> nonzero exit):
  G1 all 16 bores resolve without crash; every outcome typed; REVIEW-only
  G2 the banked discovery census reproduces EXACTLY (drift fails loud):
     15 CROSS_SHEET_CONTINUATION_REQUIRED + 1 STRUCTURE_IDENTITY_BINDING_
     REQUIRED (log42); ZERO new strokes from this law under current evidence
  G3 every refusal carries a named missing artifact mentioning the exact
     evidence class (equation / callout / closure / reciprocal / structure)
  G4 log42's discovery reached the LAST gate and the corroboration band
     refused HONESTLY: zero survivors, the multi-modal cross-ladder band
     named as the reason, and both rival flower pots named as rivals
     (never as corroborated survivors -- the adversarial finding's fix)
  G5 regression: log65 stays STROKE_ELIGIBLE (printed-identity matchline
     path; note-scoped footage change is behavior-identical for it);
     log50 stays PICK_CARD_WITH_END_ANCHOR (its banked refusal untouched)
  G6 zero-false: no AUTO anywhere; no stroke PNG rendered by this probe

Outputs (gitignored): data/outputs/cross_sheet_continuation_probe/

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_cross_sheet_continuation_probe
"""
from __future__ import annotations

import collections
import json
import os

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import BRENHAM_LANE_DIALECT
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.symbol_conduit_lane import (
    S_CROSS_SHEET,
    S_ELIGIBLE,
    S_PICK,
    S_STRUCTURE_REQUIRED,
    resolve_bore,
)
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.match.frames import _build_plan_frame_graph

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "cross_sheet_continuation_probe"

# The banked all-58 census' 16 CROSS_SHEET bores (M8.14.c.1, G2-pinned there).
CS16 = ("log8", "log10", "log12", "log14", "log32", "log42", "log46",
        "log60", "log61", "log62", "log64", "log67", "log68", "log70",
        "log71", "log72")

# Banked discovery outcome per bore (drift fails loud, never absorbed).
# M8.17 callout-chain assembly: log8 + log32 advance CROSS_SHEET ->
# STRUCTURE_IDENTITY_BINDING_REQUIRED -- their far segment is now PROVEN from
# a segmented printed callout chain (0+00->mid->boundary), closure holds, and
# only the start-structure identity remains (the SAME multi-ladder band that
# blocks log42). They join log42 at the start-identity frontier.
EXPECT_STATUS = {
    **{b: S_CROSS_SHEET for b in CS16},
    "log8": S_STRUCTURE_REQUIRED,
    "log32": S_STRUCTURE_REQUIRED,
    "log42": S_STRUCTURE_REQUIRED,
}
# Evidence-class needle each bore's named_missing must mention (G3).
EXPECT_NEEDLE = {
    "log8": "the far segment is PROVEN",          # chain assembled; start id left
    "log10": "run callouts sharing one boundary", # printed-identity path
    "log12": "do not name the discovered far sheet",  # refs [3], equation -> 23
    "log14": "prints no equation at this boundary",
    "log32": "the far segment is PROVEN",         # chain assembled; start id left
    "log42": "cannot be uniquely bound",          # rival far structures (direct)
    "log46": "printed run callout ENDING",
    "log60": "full-span callout",
    "log61": "prints no equation at this boundary",
    "log62": "prints no equation at this boundary",
    "log64": "full-span callout",
    "log67": "prints no equation at this boundary",
    "log68": "prints no equation at this boundary",
    "log70": "prints no equation at this boundary",
    "log71": "printed run callout ENDING",
    "log72": "printed run callout ENDING",
}
REGRESSION = {"log65": S_ELIGIBLE, "log50": S_PICK}


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.16] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.16] STOP: inputs missing")
        return 2
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)}
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.16] STOP: corpus drift ({len(corpus)})")
        return 3
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    plan = PlanPdf(PDF)
    ok = True
    rows = []
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        graph = _build_plan_frame_graph(plan, offset)
        outcomes = {}
        for bid in CS16 + tuple(REGRESSION):
            bore = load_borelog(str(corpus[f"bore_{bid}"]))
            out = resolve_bore(plan, bore, offset, BRENHAM_LANE_DIALECT,
                               frame_graph=graph)
            outcomes[bid] = out
            rows.append({
                "bore_id": bid, "status": out.status,
                "named_missing": out.named_missing,
                "evidence_chain": [e.to_dict() for e in out.evidence],
                "segments": [s.to_dict() for s in out.segments],
            })

        g1 = (len(outcomes) == len(CS16) + len(REGRESSION)
              and all(o.review_only and "AUTO" not in o.status
                      for o in outcomes.values()))
        print(f"[m8.16] {'PASS' if g1 else 'FAIL'}  G1 all "
              f"{len(outcomes)} bores typed, REVIEW-only")
        ok &= g1

        got = {b: outcomes[b].status for b in CS16}
        census = collections.Counter(got.values())
        new_strokes = [b for b in CS16 if outcomes[b].segments]
        g2 = got == EXPECT_STATUS and not new_strokes
        print(f"[m8.16] {'PASS' if g2 else 'FAIL'}  G2 banked census: "
              f"{dict(sorted(census.items()))}, new strokes {new_strokes}")
        if not g2:
            for b in CS16:
                if got[b] != EXPECT_STATUS[b]:
                    print(f"[m8.16]      drift {b}: {got[b]} "
                          f"(banked {EXPECT_STATUS[b]})")
        ok &= g2

        g3 = True
        for b, needle in EXPECT_NEEDLE.items():
            nm = outcomes[b].named_missing or ""
            if needle not in nm:
                g3 = False
                print(f"[m8.16]      G3 miss {b}: {needle!r} not in {nm[:90]!r}")
        print(f"[m8.16] {'PASS' if g3 else 'FAIL'}  G3 every refusal names "
              f"its evidence class")
        ok &= g3

        cs42 = [e for e in outcomes["log42"].evidence
                if e.component == "cross_sheet_origin"]
        nm42 = outcomes["log42"].named_missing or ""
        det42 = outcomes["log42"].detail
        g4 = (len(cs42) == 1 and cs42[0].result == "REFUSED"
              and "survivors: none" in nm42
              and "multi-modal" in nm42
              and "FLOWER POT@129,418" in det42.get("rivals", [])
              and "FLOWER POT@278,419" in det42.get("rivals", [])
              and det42.get("survivors") == [])
        print(f"[m8.16] {'PASS' if g4 else 'FAIL'}  G4 log42 corroboration "
              f"refused honestly: zero survivors, multi-modal band named, "
              f"rivals listed as rivals only")
        ok &= g4

        g5 = all(outcomes[b].status == s for b, s in REGRESSION.items())
        print(f"[m8.16] {'PASS' if g5 else 'FAIL'}  G5 regression: "
              f"log65={outcomes['log65'].status}, "
              f"log50={outcomes['log50'].status}")
        ok &= g5

        g6 = not list(OUT_DIR.glob("*.png"))
        print(f"[m8.16] {'PASS' if g6 else 'FAIL'}  G6 probe renders nothing")
        ok &= g6

        # G7 (M8.17): log8 + log32's far segment was assembled from a 2-hop
        # printed callout CHAIN (the segmented reciprocity law), distinct from
        # log42's DIRECT single callout -- and neither placed a stroke.
        g7 = True
        for b, hops in (("log8", "0+00->1+10->1+76"), ("log32", "0+00->1+30->1+77")):
            proof = (outcomes[b].detail or {}).get("far_segment_proof", "")
            nm = outcomes[b].named_missing or ""
            okb = ("callout chain" in proof and hops in proof
                   and "2 printed segments" in proof
                   and "the far segment is PROVEN" in nm
                   and not outcomes[b].segments)
            if not okb:
                g7 = False
                print(f"[m8.16]      G7 miss {b}: proof={proof!r}")
        # log42 used the DIRECT callout (no chain) -- provenance must differ
        g7 &= "callout chain" not in (
            (outcomes["log42"].detail or {}).get("far_segment_proof", ""))
        print(f"[m8.16] {'PASS' if g7 else 'FAIL'}  G7 log8/log32 far segment "
              f"assembled from a printed callout CHAIN; log42 stays DIRECT; "
              f"no chain-bore placed a stroke")
        ok &= g7

        report = {
            "milestone": ("truelinev2 M8.16/M8.17 -- cross-sheet origin "
                          "continuation discovery + segmented callout-chain "
                          "assembly: 16-bore evidence census (HONEST "
                          "NEGATIVE: zero stroke conversions; M8.17 chain "
                          "assembly proves log8/log32's far segment, leaving "
                          "only start-structure identity; every blocker "
                          "named)"),
            "corpus_dir_used": corpus_dir, "corpus_resolution": how,
            "plan_pdf": PDF, "verdict": "PASS" if ok else "FAILURE",
            "law": ("end-sheet boundary callout (uniqueness-mandatory, note-"
                    "scoped footage) -> EXACTLY ONE printed frame-equation "
                    "edge at that boundary -> the bore log's own sheet "
                    "references must name the far sheet -> reciprocal far-"
                    "sheet callout with the SAME boundary raw + 0.5 ft "
                    "closure -> printed conduit class via the dialect table "
                    "-> reaching far-sheet structures adjudicated ONLY by "
                    "the banked corroboration band against a CONSISTENT "
                    "(unimodal) ladder band, EXACTLY ONE survivor -> full "
                    "b.9 matchline-join re-proof + per-sheet design-path "
                    "geometry"),
            "named_next_capabilities": [
                "far-sheet callout-CHAIN assembly (log8 + log32: printed "
                "0+00->mid->boundary segment chains; single-callout "
                "reciprocity correctly refuses today)",
                "structure-identity discriminator for rival far-sheet "
                "candidates (log42: the E/W terminal-tail origin prints no "
                "identity; the multi-ladder y-band gives corroboration no "
                "consistent basis; rivals' printed labels belong to other "
                "runs' frames)",
                "per-ladder tick clustering (the log42 adversarial finding: "
                "a y-band can interleave ticks from two drawn ladders; "
                "clustering ticks per drawn ladder would give corroboration "
                "an honest basis where today it refuses)",
                "sheets 4/6/11/15/16/19/20/21 print NO matchline equations "
                "-- 7 bores' joins are unprovable from printed plan "
                "evidence alone (log10/14/61/62/67/68/70); their lane is "
                "geo/KMZ corroboration or reviewer pick-cards",
            ],
            "bores": rows,
        }
        (OUT_DIR / "cross_sheet_continuation_probe.json").write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"[m8.16] verdict: {report['verdict']}")
        print(f"[m8.16] report -> "
              f"{OUT_DIR / 'cross_sheet_continuation_probe.json'}")
    finally:
        plan.close()
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
