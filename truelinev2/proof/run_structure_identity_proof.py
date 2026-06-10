r"""M8.14.b.1 -- structure-identity binding proof (log7 + log51; identity only).

Gates (any failure -> nonzero exit):
  G1 log7 START binds uniquely to the STA 0+55=0+00 INSTALLER HH by exact
     parent-station equality; rivals 2+22 / 2+72 are NOT selected (the banked
     wrong-HH trap, pinned)
  G2 log7 END (4+51) binds uniquely to the AP-163 TERMINAL note
  G3 log51 END (2+99) binds uniquely to the FLOWER POT note
  G4 log51 START stays STRUCTURE_IDENTITY_BINDING_REQUIRED (no printed
     equation on sheet 8 -- banked abstain, not failure)

No rendering, no position resolution, no stroke change. Output gitignored:
data/outputs/structure_identity_proof.json.

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_structure_identity_proof
"""
from __future__ import annotations

import json
import os

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_anchor import (
    BOUND,
    REQUIRED,
    bind_end_structure_note,
    bind_origin_by_parent_station,
)
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.proof.station_equation_ownership import extract_reset_origins

OUT = _REPO_ROOT / "data" / "outputs" / "structure_identity_proof.json"


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.14b1] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        return 2
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)}
    if len(corpus) != EXPECTED_COUNT:
        return 3
    plan = PlanPdf(PDF)
    rows = {}
    ok = True
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        for stem, sheet in (("bore_log7", 10), ("bore_log51", 8)):
            bore = load_borelog(str(corpus[stem]))
            lines = plan.lines(sheet, offset)
            origins = extract_reset_origins(lines, sheet)
            start = bind_origin_by_parent_station(bore.station_start_ft, origins)
            end = bind_end_structure_note(bore.station_end_ft, lines)
            rows[bore.bore_id] = {
                "sheet": sheet, "start_ft": bore.station_start_ft,
                "end_ft": bore.station_end_ft,
                "start": {"result": start.result,
                          "origin": (start.origin.source_line if start.origin else None),
                          "structure": (start.origin.structure_label if start.origin else None),
                          "rivals_not_selected": list(start.rival_parent_stations),
                          "named": start.named_missing_relationship},
                "end": {"result": end.result, "note": end.note_line,
                        "structure": end.structure_label,
                        "named": end.named_missing_relationship},
            }
    finally:
        plan.close()

    r7, r51 = rows["log7"], rows["log51"]
    gates = [
        ("G1 log7 start = 0+55 HH, rivals excluded",
         r7["start"]["result"] == BOUND
         and r7["start"]["origin"] == "STA 0+55=0+00"
         and "INSTALLER HH" in (r7["start"]["structure"] or "")
         and {222.0, 272.0} <= set(r7["start"]["rivals_not_selected"])),
        ("G2 log7 end = 4+51 AP-163 terminal",
         r7["end"]["result"] == BOUND and "AP-163" in (r7["end"]["structure"] or "")),
        ("G3 log51 end = 2+99 flower pot",
         r51["end"]["result"] == BOUND
         and "FLOWER POT" in (r51["end"]["structure"] or "").upper()),
        ("G4 log51 start stays REQUIRED (banked abstain)",
         r51["start"]["result"] == REQUIRED and r51["start"]["origin"] is None),
    ]
    for name, g in gates:
        print(f"[m8.14b1] {'PASS' if g else 'FAIL'}  {name}")
        ok &= g
    report = {"milestone": "truelinev2 M8.14.b.1 -- structure identity binding proof",
              "corpus_dir_used": corpus_dir, "corpus_resolution": how,
              "verdict": "PASS" if ok else "FAILURE", "bores": rows}
    OUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[m8.14b1] verdict: {report['verdict']}  report -> {OUT}")
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
