r"""M8.10 -- reviewer payload contract over the whole corrected Brenham corpus.

Proof/design only (no UI, no backend/web, nothing wired): runs the corpus in the
fullest safe configuration (M8.5 + M8.8 contexts injected), maps EVERY bore into
exactly one reviewer lane, validates each payload against the pydantic contract
(validation IS the contract check), and emits the gitignored report.

Embedded gates: corrected default baseline 24 AND combined M8.5+M8.8 30 placed.

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_reviewer_payload_contract
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from truelinev2.config import Settings, _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.station_axis import parse_tick
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.collision_gate import collect_all_sheet_equations, collect_equations
from truelinev2.match.engine import run_match
from truelinev2.match.reverse_anchor import ReverseAnchorContext
from truelinev2.match.station_axis_interval import StationAxisContext, prove_interval_path
from truelinev2.match.transition_classifier import conflict_sheet_pairs
from truelinev2.proof.frame_ownership_candidates import classify_frame_ownership
from truelinev2.proof.run_brenham_corpus import CORPUS_DIR, EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.station_equation_ownership import extract_reset_origins, parse_hh_distances
from truelinev2.review.reviewer_payloads import (
    payload_from_frame_ownership,
    payload_from_placement,
    payload_out_of_class,
    payload_source_error,
)
from truelinev2.service import _build_plan_frame_graph

OUT_JSON = _REPO_ROOT / "data" / "outputs" / "reviewer_payload_contract.json"
OUT_MD = _REPO_ROOT / "data" / "outputs" / "reviewer_payload_contract.md"

EXPECTED_OFF = {"AUTO_SELECT": 14, "REVIEW": 10, "ABSTAIN": 32, "ERROR": 2, "PLACED": 24}
EXPECTED_COMBINED_PLACED = 30

# the named next solver per M8.7 verdict, for OUT_OF_CLASS routing
NEXT_SOLVER = {
    "END_STATION_NOT_FOUND": ("structure-identity binding at the bore end / "
                              "interval endpoint-rounding evidence"),
    "STATION_TICK_NOT_FOUND": ("vision/crop inspection of the drawn path or a "
                               "bore-frame binding datum"),
    "PATH_DISCONTINUITY": ("the missing sheet's ticks or a frame equation to "
                           "prove path continuity"),
    "FOOTAGE_MISMATCH": ("the missing authored interval or drawn-path geometry "
                         "(vector layer)"),
}


def main() -> int:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    if not os.path.isfile(PDF) or not os.path.isdir(CORPUS_DIR):
        print("[m8.10] STOP: inputs missing")
        return 2
    corpus = enumerate_corpus(CORPUS_DIR)
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.10] STOP: corpus drift ({len(corpus)})")
        return 3
    settings = Settings.for_proof()
    plan = PlanPdf(PDF)
    dialect = select_dialect(plan)
    offset = dialect.calibrate(plan, settings.sheet_offset)
    graph = _build_plan_frame_graph(plan, offset)
    conflicts = conflict_sheet_pairs(graph)
    # M8.12: canonical ALL-SHEETS reverse-anchor equation universe (far-side
    # matchline masking; the banked log62 divergence).
    eq_all = collect_all_sheet_equations(plan, offset)

    payloads: List[Any] = []
    off_statuses: List[str] = []
    combined_statuses: List[str] = []
    for p in corpus:
        try:
            bore = load_borelog(str(p))
        except Exception as e:
            off_statuses.append("ERROR")
            combined_statuses.append("ERROR")
            payloads.append(payload_source_error(
                p.stem.replace("bore_log", "log"), f"{type(e).__name__}: {e}"))
            continue
        axis_sheets = sorted({x for r in bore.sheet_refs for x in (r - 1, r, r + 1) if x >= 1})
        axis_ctx = StationAxisContext(
            ticks_by_sheet={s: tuple(t for t in (parse_tick(w["text"])
                                                 for w in plan.words(s, offset))
                                     if t is not None) for s in axis_sheets},
            callouts=tuple(c for s in axis_sheets
                           for c in dialect.extract_callouts(plan, s, offset)))
        rev_ctx = ReverseAnchorContext(
            graph=graph, conflicts=conflicts, equations_by_sheet=eq_all)
        off_statuses.append(run_match(bore, plan, dialect, offset).status.value)
        pl = run_match(bore, plan, dialect, offset, reverse_anchor=rev_ctx,
                       station_axis=axis_ctx)
        combined_statuses.append(pl.status.value)
        if pl.status.value in ("AUTO_SELECT", "REVIEW"):
            payloads.append(payload_from_placement(bore, pl))
            continue
        # remaining abstain: M8.7 verdict routes in-class vs out-of-class
        m87 = prove_interval_path(
            bore_id=bore.bore_id, bore_start_ft=bore.station_start_ft,
            bore_end_ft=bore.station_end_ft, span_ft=bore.span_ft,
            ticks_by_sheet=dict(axis_ctx.ticks_by_sheet),
            callouts=list(axis_ctx.callouts), sheet_refs=list(bore.sheet_refs))
        if m87["result"] != "FRAME_OR_SHEET_CONFLICT":
            payloads.append(payload_out_of_class(
                bore, m87["result"],
                NEXT_SOLVER.get(m87["result"], "named-solver triage"),
                named=m87.get("named_missing_relationship")))
            continue
        origins, hh_by_sheet = [], {}
        for s in axis_sheets:
            lines = plan.lines(s, offset)
            origins.extend(extract_reset_origins(lines, s))
            notes = parse_hh_distances(" ".join(lines))
            if notes:
                hh_by_sheet[s] = notes
        verdict = classify_frame_ownership(
            bore_id=bore.bore_id, bore_start_ft=bore.station_start_ft,
            bore_end_ft=bore.station_end_ft, span_ft=bore.span_ft,
            ticks_by_sheet=dict(axis_ctx.ticks_by_sheet),
            callouts=list(axis_ctx.callouts), origins=origins,
            hh_notes_by_sheet=hh_by_sheet, sheet_refs=list(bore.sheet_refs),
            equations_by_sheet=collect_equations(plan, offset, axis_sheets))
        payloads.append(payload_from_frame_ownership(bore, verdict))
    plan.close()

    off_counts = {k: off_statuses.count(k) for k in ("AUTO_SELECT", "REVIEW", "ABSTAIN", "ERROR")}
    off_counts["PLACED"] = off_counts["AUTO_SELECT"] + off_counts["REVIEW"]
    combined_placed = (combined_statuses.count("AUTO_SELECT")
                       + combined_statuses.count("REVIEW"))
    gates_ok = off_counts == EXPECTED_OFF and combined_placed == EXPECTED_COMBINED_PLACED
    if not gates_ok:
        print(f"[m8.10] STOP: gate drift off={off_counts} combined={combined_placed}")
        return 4

    by_lane: Dict[str, List[str]] = {}
    for pay in payloads:
        by_lane.setdefault(pay.lane.value, []).append(pay.bore_id)
    total = len(payloads)

    report = {
        "milestone": "truelinev2 M8.10 -- reviewer payload contract (contract/proof only)",
        "schema_version": payloads[0].schema_version if payloads else None,
        "default_sweep_reproduced": off_counts, "expected_off": EXPECTED_OFF,
        "combined_m85_m88_placed": combined_placed,
        "total_payloads": total,
        "lane_counts": {k: len(v) for k, v in sorted(by_lane.items())},
        "lane_index": {k: sorted(v) for k, v in sorted(by_lane.items())},
        "payloads": [pay.model_dump(mode="json") for pay in payloads],
    }
    OUT_JSON.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    L = ["# M8.10 -- reviewer payload contract", "",
         f"- gates: default {off_counts} (ok); combined placed {combined_placed} (ok)",
         f"- total payloads: {total} / {EXPECTED_COUNT} (every bore reaches a lane)",
         f"- lanes: " + ", ".join(f"{k}={len(v)}" for k, v in sorted(by_lane.items())), ""]
    for k, v in sorted(by_lane.items()):
        L.append(f"## {k} ({len(v)})")
        L.append(", ".join(sorted(v)))
        L.append("")
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")

    print(f"[m8.10] gates ok: default {off_counts}, combined placed {combined_placed}")
    print(f"[m8.10] total payloads: {total}/{EXPECTED_COUNT}")
    for k, v in sorted(by_lane.items()):
        print(f"[m8.10]   {k}: {len(v)}")
    print(f"[m8.10] report -> {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
