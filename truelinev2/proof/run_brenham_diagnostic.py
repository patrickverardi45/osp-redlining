r"""M6 diagnostic: explain every M5 outcome with the REAL matcher's own evidence.

Proof/diagnostic ONLY — reuses shipped extraction + chain/score/decide-tolerance
logic READ-ONLY to surface, per log: callouts on the bore's print-sheets, whether a
chain can start (absolute start_delta), footage-uniqueness, best-chain deltas, and
matchline links — the evidence that splits M5's provisional buckets into CONFIRMED
classes. For placements it copies the FULL chain crops (every matched callout) for
zero-false grading. Changes NO engine/adapter code; the matcher is imported, not
modified.

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_brenham_diagnostic
"""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from truelinev2.config import Settings, _REPO_ROOT
from truelinev2.context import require_context
from truelinev2.extract.registry import select_dialect
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.chains import build_chains
from truelinev2.match.decide import tolerances
from truelinev2.match.score import score_chain
from truelinev2.service import RedlineService
from truelinev2.store.artifacts import ArtifactStore
from truelinev2.store.db import ReviewStore
from truelinev2.proof.run_brenham_corpus import CORPUS_DIR, EXPECTED_COUNT, PDF, enumerate_corpus

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "truelinev2" / "m6_brenham_diag"
TENANT = "proof-tenant"
START_TOL = 8.0
_SEE_SHEET = re.compile(r"SEE\s+SHEET\s+(\d+)", re.I)
_MATCHLINE = re.compile(r"MATCHLINE", re.I)


def _matchline_links(plan: PlanPdf, sheet: int, offset: int):
    has_ml, links = False, set()
    for ln in plan.lines(sheet, offset):
        if _MATCHLINE.search(ln):
            has_ml = True
        for m in _SEE_SHEET.finditer(ln):
            links.add(int(m.group(1)))
    return has_ml, sorted(links)


def _co(c) -> Dict[str, Any]:
    return {"sheet": c.sheet, "from": c.from_sta, "to": c.to_sta,
            "ft": round(c.footage, 1), "vacant": c.vacant, "verified": c.footage_verified}


def diagnose(plan: PlanPdf, dialect, offset: int, bore) -> Dict[str, Any]:
    lo, hi, span = bore.station_start_ft, bore.station_end_ft, bore.span_ft
    callouts: List = []
    for s in bore.sheet_refs:
        callouts.extend(dialect.extract_callouts(plan, s, offset))
    tol = tolerances(span)
    start_cands = [c for c in callouts if abs(c.from_ft - lo) <= START_TOL]
    foot_cands = [c for c in callouts if abs(c.footage - span) <= tol["review_foot"]]
    abs_match = [c for c in callouts
                 if abs(c.from_ft - lo) <= START_TOL and abs(c.to_ft - hi) <= START_TOL]
    best = None
    for ch in build_chains(callouts, lo, hi):
        sc = score_chain(ch, lo, hi, span)
        tot = sc["start_delta"] + sc["end_delta"] + sc["foot_delta"]
        if best is None or tot < best[0]:
            best = (tot, sc)
    ml = {}
    for s in bore.sheet_refs:
        has_ml, links = _matchline_links(plan, s, offset)
        ml[str(s)] = {"matchline": has_ml, "see_sheets": links}
    max_single = round(max((c.footage for c in callouts), default=0.0), 1)
    return {
        "span_ft": span,
        "n_callouts_on_print_sheets": len(callouts),
        "max_single_callout_ft": max_single,
        "span_exceeds_any_single": span > max_single + 5.0,
        "start_candidates_abs": len(start_cands),
        "n_footage_candidates": len(foot_cands),
        "footage_candidates": [_co(c) for c in foot_cands][:8],
        "abs_endpoint_match_exists": len(abs_match) > 0,
        "best_chain": (best[1] if best else None),
        "matchline_by_sheet": ml,
        "callouts_sample": [_co(c) for c in callouts][:14],
    }


def derive_hint(status: str, d: Optional[Dict]) -> str:
    if status in ("AUTO_SELECT", "REVIEW"):
        return "PLACED -> grade full chain"
    if status == "ERROR" or d is None:
        return "ERROR -> adapter parse gap (confirm classifiable w/o fixing)"
    if d["n_callouts_on_print_sheets"] == 0:
        return "0 callouts on print-sheets -> wrong sheet_refs (adapter) OR needs-data"
    if d["abs_endpoint_match_exists"]:
        return "abs endpoint match EXISTS yet abstained -> coequal/tiebreaker (investigate)"
    if d["n_footage_candidates"] == 1 and d["start_candidates_abs"] == 0:
        return "footage-UNIQUE, no abs-start -> BUCKET3 local-frame (generic-fixable, uniqueness-gated)"
    if d["n_footage_candidates"] >= 2:
        return "footage AMBIGUOUS (>=2 candidates) -> honest abstain / needs principled tiebreaker"
    if d["n_footage_candidates"] == 0:
        if d["span_exceeds_any_single"] and any(m["see_sheets"] for m in d["matchline_by_sheet"].values()):
            return "span > any single callout + matchline present -> BUCKET2 multi-drive bridgeable (candidate)"
        return "no footage match on print-sheets -> needs-data / BUCKET4 (likely local-frame w/o derivable binding)"
    return "uncategorized"


def main() -> int:
    if not os.path.isfile(PDF) or not os.path.isdir(CORPUS_DIR):
        print("[m6] STOP: inputs missing")
        return 2
    corpus = enumerate_corpus(CORPUS_DIR)
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m6] STOP: expected {EXPECTED_COUNT}, got {len(corpus)}")
        return 3
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    settings = Settings.for_proof()
    svc = RedlineService(settings, ArtifactStore(settings.artifact_root), ReviewStore(settings.db_path))
    plan = PlanPdf(PDF)
    dialect = select_dialect(plan)
    offset = dialect.calibrate(plan, settings.sheet_offset)
    print(f"[m6] dialect={dialect.name} offset={offset}")

    rows: List[Dict[str, Any]] = []
    hint_counts: Dict[str, int] = {}
    for p in corpus:
        session = "brenham-" + p.stem
        rec: Dict[str, Any] = {"bore_id": p.stem.replace("bore_log", "log"), "source_file": p.name}
        try:
            bore = load_borelog(str(p))
        except Exception as e:
            rec.update({"status": "ERROR", "error": f"{type(e).__name__}: {e}", "hint": derive_hint("ERROR", None)})
            rows.append(rec)
            hint_counts[rec["hint"]] = hint_counts.get(rec["hint"], 0) + 1
            print(f"[m6] {rec['bore_id']:>8} ERROR        {rec['error']}")
            continue
        item = svc.run(require_context(TENANT, session), str(p), PDF).items[0]
        pl = item.placement
        status = pl.status.value
        d = diagnose(plan, dialect, offset, bore)
        hint = derive_hint(status, d)
        rec.update({"status": status, "tier": pl.tier, "reason": pl.reason,
                    "span": f"{bore.station_start}->{bore.station_end}", "span_ft": bore.span_ft,
                    "sheet_refs": bore.sheet_refs, "print_raw": bore.print_raw,
                    "diag": d, "hint": hint})
        if status in ("AUTO_SELECT", "REVIEW"):
            rec["matched_chain"] = [{"sheet": c.sheet, "from": c.from_sta, "to": c.to_sta,
                                     "ft": round(c.footage, 1), "text": c.text} for c in pl.matched_callouts]
            rec["chain_sheets"] = sorted({c.sheet for c in pl.matched_callouts})
            crops = []
            for i, art in enumerate(pl.artifacts):
                disk = settings.artifact_root / TENANT / session / art.name
                if disk.is_file():
                    gp = OUT_DIR / f"{p.stem}__chain{i}_s{art.sheet}.png"
                    try:
                        shutil.copyfile(disk, gp)
                        crops.append(str(gp))
                    except Exception:
                        pass
            rec["chain_crops"] = crops
            print(f"[m6] {rec['bore_id']:>8} {status:<11} chain={rec['chain_sheets']} "
                  f"absmatch={d['abs_endpoint_match_exists']} crops={len(crops)}  {hint}")
        else:
            bc = d["best_chain"]
            bc_s = (f"best(s/e/f)={bc['start_delta']}/{bc['end_delta']}/{bc['foot_delta']}"
                    if bc else "best=none")
            ml = sorted({n for m in d["matchline_by_sheet"].values() for n in m["see_sheets"]})
            print(f"[m6] {rec['bore_id']:>8} {status:<11} refs={bore.sheet_refs} "
                  f"nco={d['n_callouts_on_print_sheets']} startC={d['start_candidates_abs']} "
                  f"footC={d['n_footage_candidates']} {bc_s} ML->{ml}  {hint}")
        hint_counts[hint] = hint_counts.get(hint, 0) + 1
        rows.append(rec)
    plan.close()

    report = {
        "milestone": "truelinev2 M6 — grade & classify (proof/diagnostic only; no engine change)",
        "pdf": PDF, "corpus_dir": CORPUS_DIR, "enumerated": len(corpus),
        "hint_counts": hint_counts, "rows": rows,
    }
    (OUT_DIR / "m6_diagnostic.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("\n[m6] hint summary:")
    for k in sorted(hint_counts, key=lambda x: -hint_counts[x]):
        print(f"   {hint_counts[k]:>3}  {k}")
    print(f"[m6] report -> {OUT_DIR / 'm6_diagnostic.json'}")
    print(f"[m6] full-chain crops -> {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
