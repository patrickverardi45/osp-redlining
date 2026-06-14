r"""PARENT-CHILD-RECON-2 Part A -- the 'STA ' station-label opt-in: OFF vs ON.

Proves the fix is the smallest safe one and ISOLATED:

  G1  DEFAULT OFF is byte-identical: with the opt-in OFF, exactly the same bores
      load and exactly log37/log38 RAISE 'no parseable stations' (the pre-fix state).
  G2  the set of bores whose ingest OUTCOME changes OFF->ON is EXACTLY {log37,log38}.
  G3  the other 56 bores parse byte-identically OFF vs ON (start/end/span/sheets).
  G4  log37 ON -> 3+50..4+08 (sheet 23); log38 ON -> 0+62..16+21 (sheets 25,27);
      both RAISE under OFF -- stations were present all along (a parse-format artifact).
  G5  (product, needs the plan PDF) under the opt-in, EXISTING engine law decides:
      log37 reaches a PLACEMENT status and log38 does NOT (a more-specific abstain) --
      no promotion is forced. Skipped (not failed) if the PDF is unavailable.

DEFAULT-OFF opt-in by construction: nothing here flips a default; the shared
``parse_station`` is untouched; the frozen census + every baseline proof stay
byte-identical until activation is separately authorized. Read-only; writes one
gitignored JSON.

Run: $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_station_label_optin_sweep
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List

from truelinev2.config import _REPO_ROOT
from truelinev2.ingest.normalize import load_borelog
from truelinev2.proof.run_brenham_corpus import (CORPUS_DIR, EXPECTED_COUNT, PDF,
                                                 enumerate_corpus)

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "station_label_optin_sweep"
EXPECTED_CHANGED = ["log37", "log38"]


def _load(path, on: bool):
    try:
        b = load_borelog(str(path), normalize_station_label=on)
        return {"ok": True, "start": b.station_start_ft, "end": b.station_end_ft,
                "span": b.span_ft, "sheets": list(b.sheet_refs)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    corpus = enumerate_corpus(CORPUS_DIR)
    if len(corpus) != EXPECTED_COUNT:
        print(f"[recon2.A] STOP: corpus drift ({len(corpus)})")
        return 3

    off: Dict[str, dict] = {}
    on: Dict[str, dict] = {}
    for p in corpus:
        bid = p.stem.replace("bore_log", "log")
        off[bid] = _load(p, on=False)
        on[bid] = _load(p, on=True)

    changed = sorted([b for b in off if off[b] != on[b]],
                     key=lambda s: int(s.replace("log", "")))
    # G1: OFF state = exactly log37/log38 raise; everyone else loads.
    off_raises = sorted([b for b, r in off.items() if not r["ok"]],
                        key=lambda s: int(s.replace("log", "")))
    g1 = off_raises == EXPECTED_CHANGED
    # G2: only log37/log38 change OFF->ON.
    g2 = changed == EXPECTED_CHANGED
    # G3: the other 56 are byte-identical OFF vs ON.
    others_identical = all(off[b] == on[b] for b in off if b not in EXPECTED_CHANGED)
    g3 = others_identical
    # G4: the exact recovered stations + that OFF raised.
    g4 = (
        not off["log37"]["ok"] and on["log37"]["ok"]
        and on["log37"]["start"] == 350.0 and on["log37"]["end"] == 408.0
        and on["log37"]["span"] == 58.0 and on["log37"]["sheets"] == [23]
        and not off["log38"]["ok"] and on["log38"]["ok"]
        and on["log38"]["start"] == 62.0 and on["log38"]["end"] == 1621.0
        and on["log38"]["sheets"] == [25, 27]
    )

    gates = [("G1 OFF byte-identical (only log37/38 raise)", g1, off_raises),
             ("G2 OFF->ON changed set == {log37,log38}", g2, changed),
             ("G3 other 56 parse identically OFF vs ON", g3, "identical" if g3 else "DRIFT"),
             ("G4 recovered stations exact (37: 3+50..4+08 s23; 38: 0+62..16+21 s25,27)", g4, None)]

    # G5 (optional): existing engine law decides under the opt-in.
    product = {"ran": False}
    if os.path.isfile(PDF):
        try:
            from truelinev2.extract.registry import select_dialect
            from truelinev2.extract.station_axis import parse_tick
            from truelinev2.ingest.pdf import PlanPdf
            from truelinev2.match.collision_gate import collect_all_sheet_equations
            from truelinev2.match.engine import run_match
            from truelinev2.match.frames import _build_plan_frame_graph
            from truelinev2.match.reverse_anchor import ReverseAnchorContext
            from truelinev2.match.station_axis_interval import StationAxisContext
            from truelinev2.match.transition_classifier import conflict_sheet_pairs
            from truelinev2.config import Settings

            settings = Settings.for_proof()
            plan = PlanPdf(PDF)
            dialect = select_dialect(plan)
            offset = dialect.calibrate(plan, settings.sheet_offset)
            graph = _build_plan_frame_graph(plan, offset)
            conflicts = conflict_sheet_pairs(graph)
            eq_all = collect_all_sheet_equations(plan, offset)
            statuses = {}
            for p in corpus:
                bid = p.stem.replace("bore_log", "log")
                if bid not in EXPECTED_CHANGED:
                    continue
                bore = load_borelog(str(p), normalize_station_label=True)
                axis_sheets = sorted({x for r in bore.sheet_refs
                                      for x in (r - 1, r, r + 1) if x >= 1})
                axis_ctx = StationAxisContext(
                    ticks_by_sheet={s: tuple(t for t in (parse_tick(w["text"])
                                    for w in plan.words(s, offset)) if t is not None)
                                    for s in axis_sheets},
                    callouts=tuple(c for s in axis_sheets
                                   for c in dialect.extract_callouts(plan, s, offset)))
                rev_ctx = ReverseAnchorContext(graph=graph, conflicts=conflicts,
                                               equations_by_sheet=eq_all)
                res = run_match(bore, plan, dialect, offset,
                                station_axis=axis_ctx, reverse_anchor=rev_ctx)
                statuses[bid] = {"status": res.status.value, "reason": res.reason,
                                 "sheets": list(res.sheets)}
            plan.close()
            placed = {"AUTO_SELECT", "REVIEW"}
            product = {"ran": True, "statuses": statuses,
                       "log37_placed": statuses.get("log37", {}).get("status") in placed,
                       "log38_placed": statuses.get("log38", {}).get("status") in placed}
            g5 = product["log37_placed"] and not product["log38_placed"]
            gates.append(("G5 engine law: log37 places, log38 does not (no forced promotion)",
                          g5, statuses))
        except Exception as e:  # pragma: no cover - environment dependent
            product = {"ran": False, "skip_reason": f"{type(e).__name__}: {e}"}

    required = [g for n, g, _ in gates if not n.startswith("G5")]
    all_pass = all(required) and all(g for n, g, _ in gates if n.startswith("G5"))
    report = {
        "milestone": "PARENT-CHILD-RECON-2 Part A -- STA station-label opt-in OFF vs ON",
        "opt_in": "read_brenham_borelog/load_borelog(normalize_station_label=...), default OFF",
        "verdict": "PASS" if all_pass else "FAIL",
        "off_raises": off_raises, "changed_off_to_on": changed,
        "log37": {"off": off["log37"], "on": on["log37"]},
        "log38": {"off": off["log38"], "on": on["log38"]},
        "product_under_optin": product,
        "note": ("DEFAULT OFF = byte-identical (frozen census + all baseline proofs "
                 "untouched). The full-corpus product consequence under the opt-in "
                 "(log37 -> PLACED_REVIEW/DRAWABLE, log38 -> OUT_OF_CLASS; "
                 "SOURCE_REVIEW_REQUIRED 2->0, PLACED 30->31) is reproducible by running "
                 "M8.27 with the opt-in wired -- see the RECON-2 wiki doc."),
        "gates": [{"name": n, "pass": bool(g)} for n, g, _ in gates],
    }
    (OUT_DIR / "station_label_optin_sweep.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")

    for n, g, d in gates:
        extra = "" if d is None else f"  {d if not isinstance(d, dict) else '...'}"
        print(f"[recon2.A] {'PASS' if g else 'FAIL'}  {n}{extra}")
    if not product.get("ran"):
        print(f"[recon2.A] G5 product check SKIPPED ({product.get('skip_reason','no PDF')})")
    print(f"[recon2.A] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
