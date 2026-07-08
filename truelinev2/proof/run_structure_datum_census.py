"""READ-ONLY structure-datum refusal census — classify every real bore into a mutually-exclusive conversion
matrix so the NEXT capability is chosen from measured evidence, not two samples.

It runs the SHIPPED standalone reasoner (``harness.structure_datum_reasoning``) UNCHANGED across the corpus and
records, per bore, the print-ref chain (print_raw -> engineering sheet -> resolved PDF page -> station span), the
per-endpoint observer statuses, whether the span exceeds the resolved sheet's printed station range, whether a
matchline continuation is implicated, and the current engine's deterministic verdict (the CONTROL baseline). It
draws nothing, places nothing, promotes nothing, mutates no product store, and changes no engine/render/AUTO
behavior; it re-uses the read-only observers + ``run_match`` for the baseline only. Output is a single JSON report
under ``data/outputs/`` — nothing else is written.

Buckets (strict precedence, FIRST match wins -> mutually exclusive + exhaustive):
  1. CONTROL_DETERMINISTIC_PLACED   the current engine already places it (AUTO/REVIEW) -> out of the cold datum scope
  2. NO_PRINT_REF                   the bore log carries no print/sheet reference (reasoner NO_PRINT_SHEET_REF)
  3. MULTI_REF_PASS_THROUGH         >1 distinct print/sheet ref (reasoner MULTI_SHEET_REFS_UNSUPPORTED)
  4. OTHER_REFUSAL                  a resolution/span precondition refusal (NO_CONFIRMED_SPAN / SHEET_REF_UNRESOLVED)
  5. CANDIDATE_PRODUCED            the reasoner produced a REVIEW candidate
  6. SPAN_EXCEEDS_PRINTED_SHEET    the logged span extends beyond the resolved sheet's printed station range
                                    (a matchline-continuation gap, NOT a datum-disambiguation gap)
  7. AMBIGUOUS_ONLY_FAR_SUPPORTED  one endpoint resolves to >= 2 plausible datums, the OTHER endpoint is supported
                                    (the population a human pick-card would convert)
  8. UNSUPPORTED_FAR_ONLY          one endpoint is datum-anchored, the other lands on no source evidence
  9. DOUBLE_BLOCKED               an endpoint is ambiguous AND the other endpoint is also blocked (no clean traction)
 10. NO_WITNESS                    neither endpoint binds any printed datum (reasoner NO_PRINTED_DATUM_WITNESS)
Anything unforeseen -> OTHER_REFUSAL (safety net; the classifier is total).

This is proof scope. It measures; it never tunes a threshold, never OCRs, never touches KMZ, never claims a
multi-sheet placement. Real corpus/plan paths are runtime data (env / repo-relative default); absent -> honest skip.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from truelinev2.config import _REPO_ROOT
from truelinev2.harness import structure_datum_reasoning as sdr
from truelinev2.harness.span_extractor import SPAN_ROW_CONFIRMED, SpanRow, _STATION_TOKEN_RE
from truelinev2.stations import feet_to_station, parse_station

# --- buckets ---------------------------------------------------------------------------------------------- #
CONTROL_DETERMINISTIC_PLACED = "CONTROL_DETERMINISTIC_PLACED"
CANDIDATE_PRODUCED = "CANDIDATE_PRODUCED"
AMBIGUOUS_ONLY_FAR_SUPPORTED = "AMBIGUOUS_ONLY_FAR_SUPPORTED"
UNSUPPORTED_FAR_ONLY = "UNSUPPORTED_FAR_ONLY"
DOUBLE_BLOCKED = "DOUBLE_BLOCKED"
SPAN_EXCEEDS_PRINTED_SHEET = "SPAN_EXCEEDS_PRINTED_SHEET"
MULTI_REF_PASS_THROUGH = "MULTI_REF_PASS_THROUGH"
NO_WITNESS = "NO_WITNESS"
NO_PRINT_REF = "NO_PRINT_REF"
OTHER_REFUSAL = "OTHER_REFUSAL"
ALL_BUCKETS = (CONTROL_DETERMINISTIC_PLACED, CANDIDATE_PRODUCED, AMBIGUOUS_ONLY_FAR_SUPPORTED,
               UNSUPPORTED_FAR_ONLY, DOUBLE_BLOCKED, SPAN_EXCEEDS_PRINTED_SHEET, MULTI_REF_PASS_THROUGH,
               NO_WITNESS, NO_PRINT_REF, OTHER_REFUSAL)

_SHEET_SOURCE_DEFAULT = "DEFAULT_PLAN_SHEET"     # a bore with no print ref (Slice-3 default) — reasoner refuses upstream
_RANGE_TOL_FT = 5.0                              # a station must clear the printed range by this much to "exceed"
_ML_TOL_FT = 2.0                                 # endpoint within this of a printed matchline station


def classify_census_bucket(*, deterministic_placed: bool, reasoner_status: str, reasoner_ready: bool,
                           span_exceeds: bool, far_endpoint_supported: bool) -> str:
    """Pure, TOTAL classifier — strict precedence, first match wins (see module docstring). Never places or
    promotes; it only labels. ``far_endpoint_supported`` is meaningful only for the AMBIGUOUS split."""
    if deterministic_placed:
        return CONTROL_DETERMINISTIC_PLACED
    if reasoner_status == sdr.NO_PRINT_SHEET_REF:
        return NO_PRINT_REF
    if reasoner_status == sdr.MULTI_SHEET_REFS_UNSUPPORTED:
        return MULTI_REF_PASS_THROUGH
    if reasoner_status in (sdr.NO_CONFIRMED_SPAN, sdr.SHEET_REF_UNRESOLVED):
        return OTHER_REFUSAL
    if reasoner_ready:
        return CANDIDATE_PRODUCED
    if span_exceeds:
        return SPAN_EXCEEDS_PRINTED_SHEET
    if reasoner_status == sdr.AMBIGUOUS_STRUCTURE_DATUM:
        return AMBIGUOUS_ONLY_FAR_SUPPORTED if far_endpoint_supported else DOUBLE_BLOCKED
    if reasoner_status == sdr.UNSUPPORTED_FAR_ENDPOINT:
        return UNSUPPORTED_FAR_ONLY
    if reasoner_status == sdr.NO_PRINTED_DATUM_WITNESS:
        return NO_WITNESS
    return OTHER_REFUSAL


def _span_row(bore) -> SpanRow:
    """A SpanRow carrying the strict reader's confirmed span (same start/end/footage/sheet_refs/print_raw the
    generic extractor would preserve) — the reasoner's input, built from REAL bore-log data."""
    return SpanRow(span_id=str(getattr(bore, "bore_id", "bore")), source_file=str(bore.source_file),
                   source_page=None, source_kind="XLSX_TABLE", start_station=bore.station_start,
                   end_station=bore.station_end, footage=bore.span_ft, start_structure=None, end_structure=None,
                   status=SPAN_ROW_CONFIRMED, confidence="HIGH", citation="", bbox=None, detail={},
                   print_raw=bore.print_raw, sheet_refs=tuple(int(s) for s in (bore.sheet_refs or ())))


def _sheet_context(bore, sheet_index) -> Dict[str, Any]:
    """Derive the Slice-3 sheet_context from the bore's own print/sheet refs (mirrors
    ``product_readiness_bridge._derive_sheet_context``): no refs -> default; >1 distinct -> multi refusal; one
    ref -> title-block resolve (unresolvable -> named refusal). Read-only; never guesses a page."""
    refs: List[int] = []
    for r in (bore.sheet_refs or ()):
        if int(r) not in refs:
            refs.append(int(r))
    if not refs:
        return {"engineering_sheet": 1, "pdf_page": 1, "sheet_offset": 0, "source": _SHEET_SOURCE_DEFAULT,
                "sheet_refs": [], "refusal": None}
    if len(refs) > 1:
        return {"engineering_sheet": None, "pdf_page": None, "sheet_offset": None, "source": None,
                "sheet_refs": refs, "refusal": sdr.MULTI_SHEET_REFS_UNSUPPORTED}
    resolved = sheet_index.resolve_construction_sheet(refs[0])
    if resolved is None:
        return {"engineering_sheet": refs[0], "pdf_page": None, "sheet_offset": None, "source": None,
                "sheet_refs": refs, "refusal": sdr.SHEET_REF_UNRESOLVED}
    return {"engineering_sheet": refs[0], "pdf_page": int(resolved), "sheet_offset": int(resolved) - refs[0],
            "source": sdr.SHEET_SOURCE_SHEET_REF, "sheet_refs": refs, "refusal": None}


def _printed_range(plan, sheet: int, offset: int) -> Tuple[Optional[float], Optional[float], int]:
    """(min_ft, max_ft, token_count) of printed station tokens on the resolved page — reuses the span-extractor
    station token regex (never re-parses the grammar)."""
    fts = sorted({parse_station(m.group(0)) for ln in plan.lines(int(sheet), int(offset))
                  for m in _STATION_TOKEN_RE.finditer(ln) if parse_station(m.group(0)) is not None})
    return (fts[0] if fts else None, fts[-1] if fts else None, len(fts))


def _engine_placed(bore, plan, dialect, offset: int, sheet_index) -> Dict[str, Any]:
    """The current engine's deterministic verdict (the CONTROL baseline) via ``run_match`` — read-only, no store,
    no artifact, no draw. ``placed`` True for AUTO_SELECT / REVIEW (the engine's placed classes)."""
    from truelinev2.match.engine import run_match
    try:
        pl = run_match(bore, plan, dialect, offset, sheet_index=sheet_index)
        sv = pl.status.value
        return {"placed": sv in ("AUTO_SELECT", "REVIEW"), "status": sv, "tier": pl.tier, "reason": pl.reason}
    except Exception as exc:  # noqa: BLE001 - an engine error is recorded, never a placement
        return {"placed": False, "status": "ENGINE_ERROR", "tier": None, "reason": str(exc)[:120]}


def census_bore(bore, plan, plan_path: str, dialect, offset: int, sheet_index) -> Dict[str, Any]:
    """Classify ONE real bore. Records the full print-ref chain, per-endpoint observer status, span-vs-sheet
    range, matchline implication, the engine CONTROL baseline, and the bucket. Read-only; nothing is drawn."""
    span = _span_row(bore)
    ctx = _sheet_context(bore, sheet_index)
    result = sdr.reason_structure_datum(span, ctx, plan_path)
    baseline = _engine_placed(bore, plan, dialect, offset, sheet_index)

    start_ft, end_ft = parse_station(bore.station_start), parse_station(bore.station_end)
    eng_sheet, pdf_page, off = ctx["engineering_sheet"], ctx["pdf_page"], ctx["sheet_offset"]

    w_start = w_end = None
    rng = (None, None, 0)
    span_exceeds = False
    matchline_implicated = False
    if ctx["refusal"] is None and off is not None and start_ft is not None and end_ft is not None:
        partners = [s for s in ctx["sheet_refs"] if s != eng_sheet]
        ml = sdr._matchline_stations(plan_path, eng_sheet, off, partners)
        w_start = sdr._witness_at(plan_path, eng_sheet, start_ft, off, ml)
        w_end = sdr._witness_at(plan_path, eng_sheet, end_ft, off, ml)
        rng = _printed_range(plan, eng_sheet, off)
        lo, hi = rng[0], rng[1]
        if lo is not None and hi is not None:
            span_exceeds = (end_ft > hi + _RANGE_TOL_FT) or (start_ft < lo - _RANGE_TOL_FT)
        on_ml = any(w is not None and w.kind == sdr.MATCHLINE_STATION_EQUATION for w in (w_start, w_end))
        near_ml = any(abs(s - f) <= _ML_TOL_FT for s in ml for f in (start_ft, end_ft))
        matchline_implicated = bool(span_exceeds or on_ml or near_ml)

    # far_endpoint_supported: for a single-endpoint ambiguity, is the OTHER endpoint supported?
    far_supported = False
    if result.status == sdr.AMBIGUOUS_STRUCTURE_DATUM and w_start is not None and w_end is not None:
        if w_start.ambiguous and not w_end.ambiguous:
            far_supported = w_end.supported
        elif w_end.ambiguous and not w_start.ambiguous:
            far_supported = w_start.supported

    bucket = classify_census_bucket(
        deterministic_placed=baseline["placed"], reasoner_status=result.status,
        reasoner_ready=result.ready, span_exceeds=span_exceeds, far_endpoint_supported=far_supported)

    def _w(w):
        return None if w is None else {"status": w.status, "kind": w.kind, "supported": w.supported,
                                       "ambiguous": w.ambiguous}

    return {
        "bore_id": span.span_id, "bucket": bucket,
        "print_raw": bore.print_raw, "sheet_refs": list(span.sheet_refs),
        "engineering_sheet": eng_sheet, "resolved_pdf_page": pdf_page, "sheet_offset": off,
        "start_station": bore.station_start, "end_station": bore.station_end,
        "start_ft": start_ft, "end_ft": end_ft, "footage_ft": bore.span_ft,
        "printed_sheet_range_ft": [rng[0], rng[1]], "printed_station_count": rng[2],
        "printed_sheet_range_sta": [feet_to_station(rng[0]) if rng[0] is not None else None,
                                    feet_to_station(rng[1]) if rng[1] is not None else None],
        "endpoint_start": _w(w_start), "endpoint_end": _w(w_end),
        "reasoner_status": result.status, "reasoner_ready": result.ready,
        "far_endpoint_supported": far_supported,
        "engine_baseline": baseline, "control": baseline["placed"],
        "span_exceeds_printed_sheet": span_exceeds, "matchline_implicated": matchline_implicated,
    }


def _enumerate(corpus_dir: str) -> List[Path]:
    """Top-level ``bore_log*.xlsx`` only, sorted by log number (non-recursive glob excludes any subfolder)."""
    d = Path(corpus_dir)
    if not d.is_dir():
        return []
    def _num(p: Path) -> int:
        s = "".join(ch for ch in p.stem if ch.isdigit())
        return int(s) if s else 0
    return sorted(d.glob("bore_log*.xlsx"), key=_num)


def run_census(corpus_dir: Optional[str] = None, plan_path: Optional[str] = None,
               out_path: Optional[str] = None) -> Dict[str, Any]:
    """Run the census over the real corpus and return the report dict (also written to ``out_path`` when given,
    the ONLY thing this function writes). Honest skip (no crash, no write) when the corpus or plan is absent so
    the module imports + runs without the private fixtures (CI-safe)."""
    corpus_dir = corpus_dir or os.getenv("TL2_STRUCTURE_DATUM_CORPUS") or os.getenv("TL2_BRENHAM_CORPUS") or ""
    plan_path = plan_path or os.getenv("TL2_STRUCTURE_DATUM_PLAN") or os.getenv("TL2_PROOF_PDF") or str(
        _REPO_ROOT / "data" / "uploads" / "Brenham_Tx" / "NEXTLINK - Brenham - Phase 5_07-15-25.pdf")

    logs = _enumerate(corpus_dir)
    if not logs or not Path(plan_path).is_file():
        return {"skipped": True, "reason": "real corpus and/or plan not present (proof-only; not run in CI)",
                "corpus_dir": corpus_dir, "plan_path": plan_path, "log_count": len(logs)}

    from truelinev2.extract.registry import select_dialect
    from truelinev2.ingest.normalize import load_borelog
    from truelinev2.ingest.pdf import PlanPdf
    from truelinev2.ingest.sheet_label_index import build_sheet_index

    plan = PlanPdf(str(plan_path))
    rows: List[Dict[str, Any]] = []
    page_count = plan.page_count
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13) if dialect is not None else 13
        idx = build_sheet_index(plan)
        for lp in logs:
            try:
                bore = load_borelog(str(lp))
                bore.bore_id = lp.stem
                rows.append(census_bore(bore, plan, str(plan_path), dialect, offset, idx))
            except Exception as exc:  # noqa: BLE001 - an unreadable bore is recorded as OTHER_REFUSAL, never placed
                rows.append({"bore_id": lp.stem, "bucket": OTHER_REFUSAL, "reasoner_status": "READ_ERROR",
                             "reason": str(exc)[:140], "control": False})
    finally:
        plan.close()

    counts = {b: sum(1 for r in rows if r.get("bucket") == b) for b in ALL_BUCKETS}
    report = {
        "milestone": "structure-datum refusal census (read-only)",
        "corpus_dir": corpus_dir, "plan_path": Path(plan_path).name, "plan_pages": page_count,
        "log_count": len(rows), "bucket_counts": counts,
        "aggregate": {
            "control": sum(1 for r in rows if r.get("control")),
            "cold_subject": sum(1 for r in rows if not r.get("control")),
            "span_exceeds": sum(1 for r in rows if r.get("span_exceeds_printed_sheet")),
            "matchline_implicated": sum(1 for r in rows if r.get("matchline_implicated")),
            "candidate_produced": counts[CANDIDATE_PRODUCED],
            "convertible_by_pickcard": counts[AMBIGUOUS_ONLY_FAR_SUPPORTED],
        },
        "buckets_are_mutually_exclusive": sum(counts.values()) == len(rows),
        "rows": rows,
    }
    if out_path is not None:
        op = Path(out_path)
        op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        report["written_to"] = str(op)
    return report


def main(argv=None) -> int:  # pragma: no cover - CLI parity
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    out = args[0] if args else str(_REPO_ROOT / "data" / "outputs" / "truelinev2" /
                                   "structure_datum_census" / "census.json")
    report = run_census(out_path=out)
    print(json.dumps({k: report[k] for k in report if k != "rows"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
