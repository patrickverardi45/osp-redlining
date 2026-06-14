r"""M8.12.a -- reverse-anchor equation-universe reconciliation proof (read-only A/B).

The M8.11 named follow-up, proven before the call sites were standardized: two
constructions of ``ReverseAnchorContext.equations_by_sheet`` coexisted in the
tree -- ALL-SHEETS (the original M8.5 solver proof, where the adversarial mask
lessons were banked, and ``RedlineService``) vs PER-BORE ``sheet_refs`` (the
M8.5/M8.8 sweeps, the M8.10 lane proof, the M8.11 bundle service as shipped at
`0b54233`). ``matchline_mask`` masks via equations authored on the callout's
own sheet OR on a far-side sheet that links it -- a per-bore universe cannot
see far-side-authored matchlines outside the bore's refs, so it UNDER-MASKS,
the unsafe direction (under-masking anchors continuations).

This runner permanently banks the A/B (it constructs BOTH universes itself, so
it stays valid after the call sites standardize on all-sheets):

  G1 corpus integrity: exactly 58 enumerated bore logs
  G2 ENGINE-level A/B (fullest-safe composition, only the equation universe
     differs): ZERO status/reason/sheets/caveats differences across the corpus
     -- the standardization is corpus-inert at the output level
  G3 both legs reproduce the banked fullest-safe distribution
     (AUTO 14 / REVIEW 16 / ABSTAIN 26 over 56 parsed; 2 ingest errors; 30 placed)
  G4 the log62 SOLVER-level divergence, pinned exactly: per-bore leaves the
     9-ft vacant run ``STA 1+92 TO STA 2+01`` UNMASKED as anchor evidence and
     returns MULTIPLE_REVERSE_PATHS_PICK_CARD; all-sheets masks it via a
     far-side matchline equation and returns END_STATION_NOT_FOUND
  G5 log62 is the ONLY solver-level result divergence on this corpus (the
     banked record is complete)

log62 never reaches the engine differently because it places on the DEFAULT
path (the reverse retry fires only for abstains) -- the divergence is latent,
which is exactly why it is banked here before any API backing.

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_equation_universe_reconciliation
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Tuple

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.station_axis import parse_tick
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.collision_gate import collect_equations
from truelinev2.match.engine import run_match
from truelinev2.match.reverse_anchor import ReverseAnchorContext, prove_reverse_anchor
from truelinev2.match.station_axis_interval import StationAxisContext
from truelinev2.match.transition_classifier import conflict_sheet_pairs
from truelinev2.proof.run_brenham_corpus import CORPUS_DIR, EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.match.frames import _build_plan_frame_graph

OUT_JSON = _REPO_ROOT / "data" / "outputs" / "equation_universe_reconciliation.json"
OUT_MD = _REPO_ROOT / "data" / "outputs" / "equation_universe_reconciliation.md"

EXPECTED_PARSED = {"AUTO_SELECT": 14, "REVIEW": 17, "ABSTAIN": 27}  # RECON-2A: +log37 REVIEW, +log38 ABSTAIN
EXPECTED_ERRORS = 0   # RECON-2A: log37/log38 now parse (was 2)
PIN_BORE = "log62"
PIN_MASKED_SUBSTR = "STA 1+92 TO STA 2+01"
PIN_PERBORE_RESULT = "MULTIPLE_REVERSE_PATHS_PICK_CARD"
PIN_ALLSHEETS_RESULT = "END_STATION_NOT_FOUND"


def main() -> int:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    corpus_dir, how = resolve_corpus()
    print(f"[m8.12a] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.12a] STOP: inputs missing")
        return 2
    corpus = enumerate_corpus(corpus_dir)
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.12a] STOP: corpus drift ({len(corpus)})")
        return 3

    plan = PlanPdf(PDF)
    dialect = select_dialect(plan)
    offset = dialect.calibrate(plan, 13)
    graph = _build_plan_frame_graph(plan, offset)
    conflicts = conflict_sheet_pairs(graph)
    # the two universes under reconciliation -- constructed HERE, independent of
    # whatever the production call sites use, so this A/B stays a valid record
    eq_all = collect_equations(plan, offset, range(1, plan.page_count - offset + 1))

    engine_diffs: List[dict] = []
    verdict_diffs: List[dict] = []
    mask_diffs: List[dict] = []
    counts = {"perbore": {}, "allsheets": {}}
    errors = 0
    pin_record: Dict[str, dict] = {}
    for p in corpus:
        try:
            bore = load_borelog(str(p))
        except Exception:
            errors += 1
            continue
        eq_per = collect_equations(plan, offset, bore.sheet_refs)
        axis_sheets = sorted({x for r in bore.sheet_refs
                              for x in (r - 1, r, r + 1) if x >= 1})
        axis_ctx = StationAxisContext(
            ticks_by_sheet={s: tuple(t for t in (parse_tick(w["text"])
                                                 for w in plan.words(s, offset))
                                     if t is not None) for s in axis_sheets},
            callouts=tuple(c for s in axis_sheets
                           for c in dialect.extract_callouts(plan, s, offset)))
        res = {}
        for leg, eqs in (("perbore", eq_per), ("allsheets", eq_all)):
            rev = ReverseAnchorContext(graph=graph, conflicts=conflicts,
                                       equations_by_sheet=eqs)
            pl = run_match(bore, plan, dialect, offset,
                           reverse_anchor=rev, station_axis=axis_ctx)
            res[leg] = {"status": pl.status.value, "reason": pl.reason,
                        "sheets": list(pl.sheets), "caveats": list(pl.caveats)}
            counts[leg][pl.status.value] = counts[leg].get(pl.status.value, 0) + 1
        if res["perbore"] != res["allsheets"]:
            engine_diffs.append({"bore_id": bore.bore_id, **res})

        # solver-verdict A/B over the ENGINE-SCOPED callout universe (sheet_refs)
        eng_callouts = [c for s in bore.sheet_refs
                        for c in dialect.extract_callouts(plan, s, offset)]
        if not eng_callouts:
            continue
        v: Dict[str, Tuple[str, Tuple[str, ...]]] = {}
        for leg, eqs in (("perbore", eq_per), ("allsheets", eq_all)):
            r = prove_reverse_anchor(
                bore_id=bore.bore_id, bore_start_ft=bore.station_start_ft,
                bore_end_ft=bore.station_end_ft, span_ft=bore.span_ft,
                callouts=eng_callouts, graph=graph, conflicts=conflicts,
                equations_by_sheet=eqs)
            v[leg] = (r["result"],
                      tuple(sorted(m["callout"] for m in
                                   r.get("matchline_masked_candidates", []))))
        if bore.bore_id == PIN_BORE:
            pin_record = {leg: {"result": v[leg][0], "masked": list(v[leg][1])}
                          for leg in v}
        if v["perbore"][0] != v["allsheets"][0]:
            verdict_diffs.append({"bore_id": bore.bore_id,
                                  "perbore": v["perbore"][0],
                                  "allsheets": v["allsheets"][0]})
        if v["perbore"][1] != v["allsheets"][1]:
            mask_diffs.append({"bore_id": bore.bore_id,
                               "perbore_masked": list(v["perbore"][1]),
                               "allsheets_masked": list(v["allsheets"][1])})
    plan.close()

    gates: List[Tuple[str, bool, str]] = []

    def gate(name: str, ok: bool, detail: str) -> None:
        gates.append((name, ok, detail))
        print(f"[m8.12a] {'PASS' if ok else 'FAIL'}  {name}: {detail}")

    placed = {leg: counts[leg].get("AUTO_SELECT", 0) + counts[leg].get("REVIEW", 0)
              for leg in counts}
    gate("G1 corpus integrity", len(corpus) == EXPECTED_COUNT,
         f"{len(corpus)} bore logs")
    gate("G2 zero engine-level diff", not engine_diffs,
         f"{len(engine_diffs)} engine-level differences")
    gate("G3 banked fullest-safe distribution",
         counts["perbore"] == EXPECTED_PARSED and counts["allsheets"] == EXPECTED_PARSED
         and errors == EXPECTED_ERRORS and placed["allsheets"] == 31,  # RECON-2A: +log37
         f"perbore {counts['perbore']}, allsheets {counts['allsheets']}, "
         f"errors {errors}, placed {placed}")
    pin_ok = bool(pin_record) and (
        pin_record["perbore"]["result"] == PIN_PERBORE_RESULT
        and pin_record["allsheets"]["result"] == PIN_ALLSHEETS_RESULT
        and not any(PIN_MASKED_SUBSTR in m for m in pin_record["perbore"]["masked"])
        and any(PIN_MASKED_SUBSTR in m for m in pin_record["allsheets"]["masked"]))
    gate("G4 log62 divergence pinned", pin_ok, f"{pin_record}")
    gate("G5 log62 is the only solver-level result divergence",
         [d["bore_id"] for d in verdict_diffs] == [PIN_BORE],
         f"verdict diffs: {[d['bore_id'] for d in verdict_diffs]}")
    all_ok = all(ok for _, ok, _ in gates)

    report = {
        "milestone": ("truelinev2 M8.12.a -- reverse-anchor equation-universe "
                      "reconciliation A/B (read-only proof)"),
        "corpus_dir_used": corpus_dir, "corpus_resolution": how, "plan_pdf": PDF,
        "verdict": "PASS" if all_ok else "FAILURE",
        "gates": [{"name": n, "ok": ok, "detail": d} for n, ok, d in gates],
        "engine_level_diffs": engine_diffs,
        "solver_verdict_diffs": verdict_diffs,
        "masked_candidate_diffs": mask_diffs,
        "log62_pin": pin_record,
        "status_counts": counts, "ingest_errors": errors,
    }
    OUT_JSON.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    L = ["# M8.12.a -- equation-universe reconciliation A/B", "",
         f"- verdict: **{report['verdict']}**",
         f"- corpus: `{corpus_dir}` ({how})", "",
         "## Gates", ""]
    for n, ok, d in gates:
        L.append(f"- {'PASS' if ok else 'FAIL'} -- {n}: {d}")
    L += ["", "## log62 pin (the latent under-masking divergence)", "",
          f"- per-bore : {pin_record.get('perbore')}",
          f"- all-sheets: {pin_record.get('allsheets')}",
          "", f"- masked-candidate-set diffs: {mask_diffs}", ""]
    OUT_MD.write_text("\n".join(L), encoding="utf-8")
    print(f"[m8.12a] verdict: {report['verdict']}")
    print(f"[m8.12a] report -> {OUT_MD}")
    return 0 if all_ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
