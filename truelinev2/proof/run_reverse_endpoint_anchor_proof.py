r"""M8.5 -- reverse endpoint anchor PROOF over the real Brenham corpus.

Proof-first: this runner calls the PURE solver directly (run_match is invoked only
flag-OFF, to reproduce the default sweep -- the proof itself cannot change it). For
every ABSTAIN log it runs the reverse-endpoint solver over the SAME callout universe
the engine saw (the bore's sheet_refs), against the SAME safe frame graph and
matchline equations, and reports one of the six fixed verdicts with a named missing
relationship on every non-READY outcome. The default-OFF engine wiring proven by
this report lives behind TL2_REVERSE_ENDPOINT_ANCHOR_OPTIN (see
run_reverse_endpoint_optin_sweep for the OFF/ON changed-set sweep).

Primary targets (the M8.4-discovered start-anchor class): log9 / log15 / log16 --
each gets the full 10-question evidence report incl. a whole-document text-layer
scan for the literal end-station string (the OCR-fallback question) and a rendered
crop of the end-anchor callout when one exists.

Embedded gate: the default sweep MUST reproduce the corrected-source baseline
(EXPECTED_OFF) or the proof aborts (corpus/engine drift, results untrustworthy).

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_reverse_endpoint_anchor_proof
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from truelinev2.config import Settings, _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.collision_gate import collect_equations
from truelinev2.match.engine import run_match
from truelinev2.match.reverse_anchor import (
    PICK_CARD,
    READY,
    prove_reverse_anchor,
)
from truelinev2.match.transition_classifier import conflict_sheet_pairs
from truelinev2.proof.run_brenham_corpus import CORPUS_DIR, EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.match.frames import _build_plan_frame_graph

OUT_JSON = _REPO_ROOT / "data" / "outputs" / "reverse_endpoint_anchor_proof.json"
OUT_MD = _REPO_ROOT / "data" / "outputs" / "reverse_endpoint_anchor_proof.md"
CROPS_DIR = _REPO_ROOT / "data" / "outputs" / "m85_crops"

# Corrected-source baseline 2026-06-10 (bore_log9/15/16 station OCR fixed;
# log9 places REVIEW via the M7 unique-footage fallback): default 23 -> 24.
EXPECTED_OFF = {"AUTO_SELECT": 14, "REVIEW": 11, "ABSTAIN": 33, "ERROR": 0, "PLACED": 25}
PRIMARY = ("log9", "log15", "log16")
AMBIGUITY_REASONS = ("GE_2_COEQUAL_CANDIDATES_NO_TIEBREAKER",)


def _counts(statuses: List[str]) -> Dict[str, int]:
    c = {k: statuses.count(k) for k in ("AUTO_SELECT", "REVIEW", "ABSTAIN", "ERROR")}
    c["PLACED"] = c["AUTO_SELECT"] + c["REVIEW"]
    return c


def _scan_text_for_station(plan: PlanPdf, station_text: str, offset: int) -> Dict[str, Any]:
    """Whole-document text-layer scan for a literal station string (e.g. '31+00').
    Answers the OCR question: found nowhere -> the text layer cannot see it."""
    pages: List[Dict[str, Any]] = []
    for idx in range(plan.page_count):
        text = plan.text_by_index(idx)
        if station_text in text:
            pages.append({"page_index": idx, "sheet": idx - offset + 1})
    return {"station": station_text, "found": bool(pages), "pages": pages}


def _render_anchor_crop(plan: PlanPdf, offset: int, bore_id: str,
                        proof: Dict[str, Any], callouts_by_text) -> Optional[str]:
    """Crop of the winning/first end-anchor callout (visual evidence, Q5)."""
    target_text = None
    if proof.get("winning_path"):
        target_text = proof["winning_path"]["chain"][-1]
    elif proof.get("end_anchor_candidates"):
        target_text = proof["end_anchor_candidates"][0]["callout"]
    if not target_text:
        return None
    c = callouts_by_text.get(target_text)
    if c is None or not c.bbox:
        return None
    rendered = plan.render_clip(c.sheet, offset, c.bbox, zoom=2.5, pad=220.0)
    if rendered is None:
        return None
    img, _x, _y = rendered
    CROPS_DIR.mkdir(parents=True, exist_ok=True)
    path = CROPS_DIR / f"{bore_id}__end_anchor_s{c.sheet}.png"
    img.save(path)
    return str(path)


def main() -> int:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    if not os.path.isfile(PDF) or not os.path.isdir(CORPUS_DIR):
        print("[m8.5] STOP: inputs missing")
        return 2
    corpus = enumerate_corpus(CORPUS_DIR)
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.5] STOP: corpus drift ({len(corpus)})")
        return 3

    settings = Settings.for_proof()
    assert settings.reset_collision_optin is False
    assert settings.frame_continuation_optin is False
    plan = PlanPdf(PDF)
    dialect = select_dialect(plan)
    offset = dialect.calibrate(plan, settings.sheet_offset)
    graph = _build_plan_frame_graph(plan, offset)
    conflicts = conflict_sheet_pairs(graph)
    all_sheets = list(range(1, plan.page_count - offset + 1))
    equations_by_sheet = collect_equations(plan, offset, all_sheets)

    # --- embedded gate: reproduce the default sweep (read-only run_match) -------
    rows: List[Dict[str, Any]] = []
    bores: Dict[str, Any] = {}
    for p in corpus:
        try:
            bore = load_borelog(str(p))
        except Exception as e:
            rows.append({"bore_id": p.stem.replace("bore_log", "log"), "status": "ERROR",
                         "reason": f"{type(e).__name__}"})
            continue
        pl = run_match(bore, plan, dialect, offset)
        bores[bore.bore_id] = bore
        rows.append({"bore_id": bore.bore_id, "status": pl.status.value, "reason": pl.reason})
    off_counts = _counts([r["status"] for r in rows])
    if off_counts != EXPECTED_OFF:
        print(f"[m8.5] STOP: default sweep drifted: {off_counts} != {EXPECTED_OFF}")
        plan.close()
        return 4
    status_by_id = {r["bore_id"]: r for r in rows}

    # --- reverse-endpoint proof for every ABSTAIN log ----------------------------
    proofs: List[Dict[str, Any]] = []
    for r in rows:
        if r["status"] != "ABSTAIN":
            continue
        bore = bores[r["bore_id"]]
        callouts = []
        for s in bore.sheet_refs:
            callouts.extend(dialect.extract_callouts(plan, s, offset))
        scan = _scan_text_for_station(plan, bore.station_end, offset)
        proof = prove_reverse_anchor(
            bore_id=bore.bore_id, bore_start_ft=bore.station_start_ft,
            bore_end_ft=bore.station_end_ft, span_ft=bore.span_ft,
            callouts=callouts, graph=graph, conflicts=conflicts,
            equations_by_sheet=equations_by_sheet,
            end_text_found_in_plan=scan["found"])
        proof["sheet_refs"] = list(bore.sheet_refs)
        proof["default_reason"] = r["reason"]
        proof["ambiguity_abstain"] = r["reason"] in AMBIGUITY_REASONS
        proof["end_station_text_scan"] = scan
        if bore.bore_id in PRIMARY:
            cmap = {c.text: c for c in callouts}
            crop = _render_anchor_crop(plan, offset, bore.bore_id, proof, cmap)
            proof["end_anchor_crop"] = crop
        proofs.append(proof)

    # ERROR logs: reverse anchoring is N/A (no parseable stations).
    for r in rows:
        if r["status"] == "ERROR":
            proofs.append({"bore_id": r["bore_id"], "result": "NOT_APPLICABLE_INGEST_ERROR",
                           "named_missing_relationship":
                               "bore log has no parseable stations (adapter-parse class); "
                               "reverse anchoring consumes stations -- the next solver is "
                               "the adapter station-format fix, not endpoint anchoring"})

    # --- predicted opt-in changed set (REVIEW-gated only, ambiguity excluded) ----
    ready = [p for p in proofs if p.get("result") == READY]
    ready_eligible = [p for p in ready if not p.get("ambiguity_abstain")]
    pick_cards = [p for p in proofs if p.get("result") == PICK_CARD]
    by_verdict: Dict[str, List[str]] = {}
    for p in proofs:
        by_verdict.setdefault(str(p.get("result")), []).append(str(p.get("bore_id")))

    report = {
        "milestone": "truelinev2 M8.5 -- reverse endpoint anchor proof (proof-only, nothing wired)",
        "default_sweep_reproduced": off_counts,
        "expected_off": EXPECTED_OFF,
        "frame_graph": {"safe_edges": len(graph.edges), "conflicts": len(graph.conflicts)},
        "verdict_index": {k: sorted(v) for k, v in sorted(by_verdict.items())},
        "predicted_optin_changed_set": sorted(p["bore_id"] for p in ready_eligible),
        "predicted_optin_excluded_ambiguity": sorted(
            p["bore_id"] for p in ready if p.get("ambiguity_abstain")),
        "pick_cards": sorted(p["bore_id"] for p in pick_cards),
        "auto_promotions_possible": False,
        "primary_targets": {p["bore_id"]: p for p in proofs if p.get("bore_id") in PRIMARY},
        "proofs": proofs,
    }
    OUT_JSON.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    lines = ["# M8.5 -- reverse endpoint anchor proof", "",
             f"- default sweep reproduced: {off_counts} (gate: {EXPECTED_OFF})",
             f"- safe frame edges: {len(graph.edges)} / conflicts: {len(graph.conflicts)}",
             f"- verdicts: " + ", ".join(f"{k}={len(v)}" for k, v in sorted(by_verdict.items())),
             f"- predicted opt-in changed set (REVIEW only, ambiguity excluded): "
             f"**{sorted(p['bore_id'] for p in ready_eligible) or 'EMPTY'}**",
             f"- pick-cards (human tiebreak): {sorted(p['bore_id'] for p in pick_cards) or 'NONE'}",
             "", "## Primary targets", ""]
    for tid in PRIMARY:
        p = next((x for x in proofs if x.get("bore_id") == tid), None)
        if p is None:
            st = status_by_id.get(tid, {})
            lines.append(f"### {tid}: not ABSTAIN in the default sweep "
                         f"(status={st.get('status')}) -- no reverse proof needed")
            continue
        lines += [f"### {tid} -- **{p['result']}**",
                  f"- bore: start {p.get('bore_start_sta')} end {p.get('bore_end_sta')} "
                  f"span {p.get('span_ft')} ft; sheets {p.get('sheet_refs')}",
                  f"- end-station text scan: found={p['end_station_text_scan']['found']} "
                  f"pages={[(x['sheet']) for x in p['end_station_text_scan']['pages']]}",
                  f"- end-anchor candidates: {p.get('end_anchor_candidates')}",
                  f"- matchline-masked: {p.get('matchline_masked_candidates', [])}"]
        if p.get("winning_path"):
            w = p["winning_path"]
            lines += [f"- winning path (sheets {w['sheets']}): {w['chain']}",
                      f"- hops: {w['hops']}",
                      f"- computed start {p['computed_start_sta']} vs bore "
                      f"{p['bore_start_sta']} -> delta {p['start_delta_vs_borelog_ft']} ft "
                      f"(confirmed={p['start_confirmed']})",
                      f"- caveats: {p.get('caveats')}"]
        lines += [f"- named relationship: {p.get('named_missing_relationship', '(READY)')}",
                  f"- crop: {p.get('end_anchor_crop')}", ""]
    lines += ["## All abstain/error verdicts", ""]
    for p in proofs:
        nm = p.get("named_missing_relationship", "(READY)")
        lines.append(f"- {p.get('bore_id')}: **{p.get('result')}** -- {nm}")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    plan.close()

    print(f"[m8.5] default sweep: {off_counts} (gate ok)")
    print(f"[m8.5] verdicts: " + ", ".join(f"{k}={len(v)}" for k, v in sorted(by_verdict.items())))
    print(f"[m8.5] predicted opt-in changed set: "
          f"{sorted(p['bore_id'] for p in ready_eligible) or 'EMPTY'}")
    print(f"[m8.5] pick-cards: {sorted(p['bore_id'] for p in pick_cards) or 'NONE'}")
    for tid in PRIMARY:
        p = next((x for x in proofs if x.get("bore_id") == tid), None)
        print(f"[m8.5] {tid}: {p['result'] if p else 'not-abstain'}")
    print(f"[m8.5] report -> {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
