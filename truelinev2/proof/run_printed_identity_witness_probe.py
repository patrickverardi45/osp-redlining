"""PRINTED-IDENTITY WITNESS PROBE (READ-ONLY proof; no product, no render, no placement, no promotion).

Two owner-adjudicated bores are blocked ONLY by an unmodeled endpoint-identity KIND (closure ledger
``UNMODELED_TERMINUS_CLASS_NEEDED``): their endpoints are defined by a printed station-RESET EQUATION and by a
printed DIRECT-BORE CALLOUT SPAN — not by a modeled structure class. Before any identity-vocabulary capability
is coded, this probe answers the ONE cheap question: does the claimed printed witness actually exist, uniquely,
on the owner-recorded corrected sheet(s)?

For each probe it scans the title-block-resolved PDF page text (``PlanPdf.lines`` — the same page resolution the
census uses) and emits JSON evidence with exactly one status:
  FOUND       exactly one distinct printed hit across the probed sheets
  NOT_FOUND   zero hits            -> named refusal ``PRINTED_WITNESS_NOT_FOUND``
  AMBIGUOUS   >= 2 distinct hits   -> named refusal ``AMBIGUOUS_PRINTED_WITNESS`` (never choose)
Per-sheet resolution failures are named (``SHEET_REF_UNRESOLVED``); a missing adjudication record is named
(``ADJUDICATED_SHEETS_UNAVAILABLE``); an absent plan is an honest skip (nothing written).

Witness kinds (evidence classes only — NEVER a placement):
  RESET_EQUATION_TERMINUS_WITNESS    a printed "STA <datum> = <reset>" station-reset equation
  DIRECT_BORE_CALLOUT_SPAN_WITNESS   a printed "STA <a> TO STA <b> ... BORE ..." callout span

Guarantees (proof scope): pure text scan; imports NOTHING from render / match / api / contracts / product
store; draws nothing; writes NO PNG; edits NO adjudication artifact (the owner artifact is READ for the
corrected sheets only); tunes no threshold; creates no REVIEW candidate; touches no other bore. Probe token
inputs (station strings) are identity-level facts quoted from the owner adjudication's evidence notes — never
geometry, never a coordinate. Output is a single JSON under ``data/outputs/`` — nothing else is written.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from truelinev2.config import _REPO_ROOT

# --- statuses (exactly one per probe) --------------------------------------------------------------------- #
FOUND = "FOUND"
NOT_FOUND = "NOT_FOUND"
AMBIGUOUS = "AMBIGUOUS"
ALL_STATUSES = (FOUND, NOT_FOUND, AMBIGUOUS)

# --- named refusal codes (every non-FOUND outcome names one) ----------------------------------------------- #
PRINTED_WITNESS_NOT_FOUND = "PRINTED_WITNESS_NOT_FOUND"
AMBIGUOUS_PRINTED_WITNESS = "AMBIGUOUS_PRINTED_WITNESS"
SHEET_REF_UNRESOLVED = "SHEET_REF_UNRESOLVED"                    # per-sheet, same vocabulary as Slice 3
ADJUDICATED_SHEETS_UNAVAILABLE = "ADJUDICATED_SHEETS_UNAVAILABLE"

# --- witness kinds ----------------------------------------------------------------------------------------- #
RESET_EQUATION_TERMINUS_WITNESS = "RESET_EQUATION_TERMINUS_WITNESS"
DIRECT_BORE_CALLOUT_SPAN_WITNESS = "DIRECT_BORE_CALLOUT_SPAN_WITNESS"

_OUT_DEFAULT = _REPO_ROOT / "data" / "outputs" / "truelinev2" / "printed_identity_witness" / "witness_probe.json"

# Probe inputs: identity-level station tokens quoted from the OWNER adjudication artifact's evidence notes
# (read-only; the artifact is never edited). Sheets are read from the artifact's structured corrected fields at
# runtime — never hardcoded here. Log ids are generic corpus labels, not customer data.
PROBES = (
    {"log_id": "log46", "witness_kind": RESET_EQUATION_TERMINUS_WITNESS,
     "datum_station": "44+08", "reset_station": "0+00"},
    {"log_id": "log68", "witness_kind": DIRECT_BORE_CALLOUT_SPAN_WITNESS,
     "start_station": "5+03", "end_station": "6+79", "footage_token": "176"},
)


def _sta(tok: str) -> str:
    """A station token as a literal regex fragment (e.g. ``44+08``) with an optional leading STA/STA. label."""
    return r"(?:STA\.?\s*)?" + re.escape(tok)


def _scan(lines: Sequence[str], pat: "re.Pattern[str]") -> List[Dict[str, Any]]:
    """Deterministic per-line scan + adjacent-pair join (text extraction may split a label across two lines).
    A pair is scanned only when neither of its lines already hit alone, so a hit is never double-counted."""
    hits: List[Dict[str, Any]] = []
    hit_idx = set()
    for i, ln in enumerate(lines):
        m = pat.search(ln)
        if m:
            hits.append({"line_index": i, "line": ln.strip(), "matched": m.group(0)})
            hit_idx.add(i)
    for i in range(len(lines) - 1):
        if i in hit_idx or (i + 1) in hit_idx:
            continue
        joined = "%s %s" % (lines[i].strip(), lines[i + 1].strip())
        m = pat.search(joined)
        if m:
            hits.append({"line_index": i, "line": joined, "matched": m.group(0), "joined_pair": True})
    return hits


def match_reset_equation(lines: Sequence[str], datum_station: str, reset_station: str = "0+00"
                         ) -> List[Dict[str, Any]]:
    """Printed station-reset equation hits: ``STA <datum> = <reset>`` (STA labels optional, spacing free)."""
    pat = re.compile(_sta(datum_station) + r"\s*=\s*" + _sta(reset_station), re.IGNORECASE)
    return _scan(lines, pat)


def match_direct_bore_callout(lines: Sequence[str], start_station: str, end_station: str
                              ) -> List[Dict[str, Any]]:
    """Printed direct-bore callout span hits: ``STA <a> TO STA <b>`` with a BORE token in the callout's own
    label BLOCK — the same extracted line or the immediately following one (plan callouts print the station
    pair and the work type as adjacent lines). A bare station pair with no BORE in its block is NOT a bore
    callout witness. The one-line block window is the callout's printed structure, never a tolerance."""
    pat = re.compile(_sta(start_station) + r"\s*TO\s*" + _sta(end_station), re.IGNORECASE)
    out: List[Dict[str, Any]] = []
    for h in _scan(lines, pat):
        nxt = h["line_index"] + (2 if h.get("joined_pair") else 1)
        ctx = h["line"] if nxt >= len(lines) else "%s %s" % (h["line"], lines[nxt].strip())
        if "BORE" in ctx.upper():
            out.append(dict(h, line=ctx))
    return out


def witness_result(witness_kind: str, hits: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Exactly one status from the deduped hit list — FOUND only on a UNIQUE printed witness; >= 2 distinct
    hits refuse as AMBIGUOUS (never choose); zero hits refuse as NOT_FOUND. Pure; no side effects."""
    distinct = {(h.get("pdf_page"), h["line_index"], h["matched"]) for h in hits}
    if len(distinct) == 1:
        return {"status": FOUND, "refusal": None, "witness_kind": witness_kind, "hits": list(hits)}
    if len(distinct) > 1:
        return {"status": AMBIGUOUS, "refusal": AMBIGUOUS_PRINTED_WITNESS, "witness_kind": witness_kind,
                "hits": list(hits)}
    return {"status": NOT_FOUND, "refusal": PRINTED_WITNESS_NOT_FOUND, "witness_kind": witness_kind, "hits": []}


def _probe_hits(probe: Dict[str, Any], lines: Sequence[str]) -> List[Dict[str, Any]]:
    if probe["witness_kind"] == RESET_EQUATION_TERMINUS_WITNESS:
        return match_reset_equation(lines, probe["datum_station"], probe["reset_station"])
    return match_direct_bore_callout(lines, probe["start_station"], probe["end_station"])


def run_probe(plan_path: Optional[str] = None, out_path: Optional[str] = None) -> Dict[str, Any]:
    """Run both probes against the owner-corrected sheets and return (and optionally write) the JSON report.
    Honest skip (no crash, NOTHING written) when the plan is absent — CI-safe without the private fixture."""
    plan_path = plan_path or os.getenv("TL2_STRUCTURE_DATUM_PLAN") or os.getenv("TL2_PROOF_PDF") or ""
    if not plan_path or not Path(plan_path).is_file():
        return {"skipped": True, "reason": "plan PDF not present (proof-only; not run in CI)",
                "plan_path": plan_path}

    from truelinev2.ingest.manual_adjudication import load_adjudication
    from truelinev2.ingest.pdf import PlanPdf
    from truelinev2.ingest.sheet_label_index import build_sheet_index

    try:
        adj = {r["log_id"]: r for r in load_adjudication()["logs"]}
    except Exception:  # noqa: BLE001 - a missing/unreadable artifact is a NAMED refusal, never a guess
        adj = {}

    plan = PlanPdf(str(plan_path))
    results: List[Dict[str, Any]] = []
    try:
        idx = build_sheet_index(plan)
        for probe in PROBES:
            rec = adj.get(probe["log_id"]) or {}
            sheets = [int(s) for s in (rec.get("corrected_sheets") or ())]
            if not sheets:
                results.append({"log_id": probe["log_id"], "witness_kind": probe["witness_kind"],
                                "status": NOT_FOUND, "refusal": ADJUDICATED_SHEETS_UNAVAILABLE,
                                "hits": [], "sheets_probed": [], "unresolved_sheets": []})
                continue
            hits: List[Dict[str, Any]] = []
            probed: List[Dict[str, int]] = []
            unresolved: List[int] = []
            for s in sheets:
                resolved = idx.resolve_construction_sheet(s)
                if resolved is None:
                    unresolved.append(s)          # named per-sheet: SHEET_REF_UNRESOLVED (never page-guessed)
                    continue
                offset = int(resolved) - s
                for h in _probe_hits(probe, plan.lines(s, offset)):
                    h["engineering_sheet"] = s
                    h["pdf_page"] = int(resolved)
                    hits.append(h)
                probed.append({"engineering_sheet": s, "pdf_page": int(resolved)})
            res = witness_result(probe["witness_kind"], hits)
            ft = probe.get("footage_token")
            if ft and res["status"] == FOUND:      # evidence corroboration only — never a gate, never geometry
                res["footage_token_present"] = any(ft in h["line"] for h in res["hits"])
            res.update({"log_id": probe["log_id"], "sheets_probed": probed, "unresolved_sheets": unresolved,
                        "unresolved_refusal": SHEET_REF_UNRESOLVED if unresolved else None})
            results.append(res)
    finally:
        plan.close()

    report = {
        "milestone": "printed-identity witness probe (read-only)",
        "plan_path": Path(plan_path).name,
        "probes": results,
        "statuses": {r["log_id"]: r["status"] for r in results},
        "guarantees": {"read_only": True, "no_render": True, "no_png": True, "no_placement": True,
                       "no_promotion": True, "no_adjudication_edit": True, "no_threshold_tuning": True,
                       "no_review_candidate": True},
    }
    if out_path is not None:
        op = Path(out_path)
        op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        report["written_to"] = str(op)
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:  # pragma: no cover - CLI parity
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    plan = args[0] if args else None
    out = args[1] if len(args) > 1 else str(_OUT_DEFAULT)
    report = run_probe(plan_path=plan, out_path=out)
    print(json.dumps({k: report[k] for k in report if k != "probes"}, indent=2, sort_keys=True))
    for r in report.get("probes", ()):
        print("[witness] %-6s %-34s %s%s" % (r["log_id"], r["witness_kind"], r["status"],
                                             "" if not r.get("refusal") else " (%s)" % r["refusal"]))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
