r"""M8.7 -- station-axis interval-containment proof over the real corpus.

Proof-only (nothing wired; run_match invoked only flag-OFF to reproduce the
corrected-source default baseline). Primary target: log15 -- field review showed
its end ``31+00`` is a drawn station tick on the Chappell Hill St path, not a
callout/structure endpoint, so M8.5's END_STATION_NOT_FOUND named the wrong
relationship. Secondary scan: every other ABSTAIN log.

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_station_axis_interval_containment
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
from truelinev2.match.engine import run_match
from truelinev2.proof.run_brenham_corpus import CORPUS_DIR, EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.station_axis_interval_containment import READY, prove_interval_path

OUT_JSON = _REPO_ROOT / "data" / "outputs" / "station_axis_interval_containment.json"
OUT_MD = _REPO_ROOT / "data" / "outputs" / "station_axis_interval_containment.md"

# Corrected-source baseline (see run_reverse_endpoint_anchor_proof provenance).
EXPECTED_OFF = {"AUTO_SELECT": 14, "REVIEW": 11, "ABSTAIN": 33, "ERROR": 0, "PLACED": 25}
PRIMARY = "log15"
# The bore's print refs plus adjacent sheets: the path may continue past the
# referenced sheets' edges (log15's 24+00 sits at/off the sheet bottom).
ADJACENT = 1


def _sheets_for(bore) -> List[int]:
    s = set()
    for r in bore.sheet_refs:
        s.update({r - ADJACENT, r, r + ADJACENT})
    return sorted(x for x in s if x >= 1)


def main() -> int:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    if not os.path.isfile(PDF) or not os.path.isdir(CORPUS_DIR):
        print("[m8.7] STOP: inputs missing")
        return 2
    corpus = enumerate_corpus(CORPUS_DIR)
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.7] STOP: corpus drift ({len(corpus)})")
        return 3
    settings = Settings.for_proof()
    plan = PlanPdf(PDF)
    dialect = select_dialect(plan)
    offset = dialect.calibrate(plan, settings.sheet_offset)

    # gate: corrected default baseline (flag-OFF run_match, read-only)
    rows = []
    bores = {}
    for p in corpus:
        try:
            b = load_borelog(str(p))
        except Exception:
            rows.append(("ERROR", p.stem))
            continue
        bores[b.bore_id] = b
        rows.append((run_match(b, plan, dialect, offset).status.value, b.bore_id))
    counts = {k: sum(1 for s, _ in rows if s == k)
              for k in ("AUTO_SELECT", "REVIEW", "ABSTAIN", "ERROR")}
    counts["PLACED"] = counts["AUTO_SELECT"] + counts["REVIEW"]
    if counts != EXPECTED_OFF:
        print(f"[m8.7] STOP: default sweep drifted: {counts} != {EXPECTED_OFF}")
        plan.close()
        return 4

    proofs: List[Dict[str, Any]] = []
    for status, bid in rows:
        if status != "ABSTAIN":
            continue
        b = bores[bid]
        sheets = _sheets_for(b)
        ticks = {s: [t for t in (parse_tick(w["text"]) for w in plan.words(s, offset))
                     if t is not None] for s in sheets}
        callouts = []
        for s in sheets:
            callouts.extend(dialect.extract_callouts(plan, s, offset))
        proof = prove_interval_path(
            bore_id=bid, bore_start_ft=b.station_start_ft,
            bore_end_ft=b.station_end_ft, span_ft=b.span_ft,
            ticks_by_sheet=ticks, callouts=callouts,
            sheet_refs=list(b.sheet_refs))
        proof["sheet_refs"] = list(b.sheet_refs)
        proof["sheets_searched"] = sheets
        proofs.append(proof)
    plan.close()

    by_verdict: Dict[str, List[str]] = {}
    for p in proofs:
        by_verdict.setdefault(str(p["result"]), []).append(str(p["bore_id"]))
    ready = sorted(p["bore_id"] for p in proofs if p["result"] == READY)

    report = {
        "milestone": "truelinev2 M8.7 -- station-axis interval containment / path-walk (proof-only)",
        "default_sweep_reproduced": counts, "expected_off": EXPECTED_OFF,
        "verdict_index": {k: sorted(v) for k, v in sorted(by_verdict.items())},
        "ready_set": ready,
        "auto_promotions_possible": False,
        "primary_target": next((p for p in proofs if p["bore_id"] == PRIMARY), None),
        "proofs": proofs,
    }
    OUT_JSON.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    prim = report["primary_target"]
    L = ["# M8.7 -- station-axis interval containment proof", "",
         f"- default sweep reproduced: {counts} (gate: {EXPECTED_OFF})",
         f"- verdicts: " + ", ".join(f"{k}={len(v)}" for k, v in sorted(by_verdict.items())),
         f"- READY set (REVIEW-gated only): **{ready or 'EMPTY'}**", "",
         f"## Primary target {PRIMARY}", "",
         f"```json", json.dumps(prim, indent=1, default=str)[:4000], "```", "",
         "## All abstain verdicts", ""]
    for p in proofs:
        L.append(f"- {p['bore_id']}: **{p['result']}** -- "
                 f"{p.get('named_missing_relationship', '(READY)')}")
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")

    print(f"[m8.7] default sweep: {counts} (gate ok)")
    print(f"[m8.7] verdicts: " + ", ".join(f"{k}={len(v)}" for k, v in sorted(by_verdict.items())))
    print(f"[m8.7] READY set: {ready or 'EMPTY'}")
    if prim:
        print(f"[m8.7] {PRIMARY}: {prim['result']} end_ticks={prim.get('end_axis_ticks')} "
              f"sheets={prim.get('sheets_crossed')} joins={len(prim.get('sheet_joins', []))}")
        print(f"[m8.7] {PRIMARY} walk: {prim.get('walk')}")
    print(f"[m8.7] report -> {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
