r"""M8.2f -- read-only PROOF/REPORT for the cross-sheet transition classifier.

Runs the SHIPPED v2 matcher over the real corpus with ``frame_graph=None`` (the default
23/58 -- never altered), then classifies every cross-sheet transition with the new
``match/transition_classifier`` against the REAL safe frame graph, and reports whether a
FUTURE classifier-gated frame opt-in could preserve all current placements. It answers,
with evidence per log:

  * for each of the 8 M8.2d-regressed logs: are its cross-sheet transitions preserved as
    ``continuous_station`` (so the classifier would NOT break them)?
  * log11 [5,17]: does the classifier call the relationship ``reset_equation`` -- while the
    engine still ABSTAINS for missing anchor/box/footage evidence?
  * does the classifier ever call a continuous (no-edge) transition a reset?  (must be 0)
  * does it ever let a reset/equation pass as continuous via a raw equal-station?  (must be 0)
  * would a classifier-gated opt-in preserve ALL 23 current placements?
  * what evidence is still missing before any NEW placement is safe?

It then prints a single verdict for the NEXT activation attempt:
``READY_FOR_SAFE_OPTIN_ATTEMPT`` / ``NEEDS_MORE_EVIDENCE`` / ``NOT_SAFE``.

READ-ONLY: NO engine / decide / default-``run_match`` / adapter change. Frame translation
stays INACTIVE in the default path and the M8.2d opt-in result remains NOT_SAFE -- this
report does NOT activate anything; outputs go to gitignored ``data/outputs/`` ONLY.

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_transition_classifier_report
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from typing import Any, Dict, List, Optional

from truelinev2.config import Settings, _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.engine import run_match
from truelinev2.match.transition_classifier import (
    DEFAULT_LINK_TOL,
    classify_chain,
    classify_sheet_relationship,
    conflict_sheet_pairs,
    cross_sheet_transitions,
)
from truelinev2.proof.run_brenham_corpus import CORPUS_DIR, EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_frame_optin_validation import build_plan_frame_graph

PLACED = ("AUTO_SELECT", "REVIEW")
# Measured current default 25/58. This file was the lone straggler still on the old
# 23/58 GOLDEN, so the delta spans TWO corrections (both already live, now reflected):
#   REVIEW 9->10 = catch-up to the 2026-06-10 corrected-source baseline (log9; never
#                  applied here); REVIEW 10->11 = RECON-2A log37 `STA ` activation.
#   ABSTAIN 33 net-unchanged = log9 leaving ABSTAIN (-1) + log38 entering ABSTAIN (+1).
GOLDEN = {"AUTO_SELECT": 14, "REVIEW": 11, "ABSTAIN": 33, "ERROR": 0}
# The 8 logs M8.2d's edge-required opt-in regressed (placed by default -> abstain under opt-in).
REGRESSED = ["log2", "log3", "log4", "log42", "log50", "log57", "log62", "log65"]
LOG11 = "log11"


def _log_key(stem_or_id: str) -> str:
    """Normalize ``bore_log42`` / ``log42`` / ``bore_log42.xlsx`` -> ``log42``."""
    m = re.search(r"(\d+)", str(stem_or_id))
    return f"log{m.group(1)}" if m else str(stem_or_id)


def _span(c) -> str:
    return f"s{c.sheet} {c.from_sta}->{c.to_sta} ({c.from_ft:.0f}-{c.to_ft:.0f}ft)"


def _sheet_relationships(sheet_refs: List[int], graph, cp) -> List[Dict[str, Any]]:
    """Relationship-level classification for each consecutive distinct sheet pair (used
    when a bore ABSTAINED and so has no placed chain to read transitions from)."""
    out = []
    for a, b in zip(sheet_refs, sheet_refs[1:]):
        if a != b:
            out.append(classify_sheet_relationship(graph, cp, a, b).to_dict())
    return out


def _detail(bore, plan, dialect, offset, graph, cp, stem: str) -> Dict[str, Any]:
    pl = run_match(bore, plan, dialect, offset, frame_graph=None)   # DEFAULT path only
    status = pl.status.value
    chain = list(pl.matched_callouts)
    chain_tr = classify_chain(graph, cp, chain)
    cross = cross_sheet_transitions(chain_tr)
    return {
        "bore_id": bore.bore_id, "log_key": _log_key(stem), "source_file": stem,
        "sheet_refs": list(bore.sheet_refs),
        "span": f"{bore.station_start}->{bore.station_end}", "span_ft": bore.span_ft,
        "default_status": status, "tier": pl.tier, "reason": pl.reason,
        "sheets": list(pl.sheets),
        "chain": [_span(c) for c in chain],
        "cross_sheet_transitions": [t.to_dict() for t in cross],
        "cross_classes": [t.classification.value for t in cross],
        "all_cross_linkable": all(t.linkable for t in cross),
        "has_cross_sheet": bool(cross),
        "sheet_relationships": _sheet_relationships(list(bore.sheet_refs), graph, cp),
    }


def _classify_corpus(details: Dict[str, Dict[str, Any]], errors: List[str]):
    default_dist: Dict[str, int] = {}
    for d in details.values():
        default_dist[d["default_status"]] = default_dist.get(d["default_status"], 0) + 1
    default_dist["ERROR"] = len(errors)
    default_ok = all(default_dist.get(k, 0) == v for k, v in GOLDEN.items())
    return default_dist, default_ok


def _analyze(details: Dict[str, Dict[str, Any]]):
    by_key = {d["log_key"]: d for d in details.values()}
    placed = [d for d in details.values() if d["default_status"] in PLACED]
    abstains = [d for d in details.values() if d["default_status"] == "ABSTAIN"]

    # Q1 -- the 8 regressed logs preserved as continuous_station
    regressed_rows = []
    for k in REGRESSED:
        d = by_key.get(k)
        if d is None:
            continue
        cont = d["has_cross_sheet"] and all(c == "continuous_station" for c in d["cross_classes"])
        regressed_rows.append({**{kk: d[kk] for kk in (
            "log_key", "default_status", "sheet_refs", "cross_classes")},
            "cross_sheet_transitions": d["cross_sheet_transitions"],
            "preserved_continuous": cont})
    regressed_all_continuous = bool(regressed_rows) and all(r["preserved_continuous"] for r in regressed_rows)

    # Q2 -- log11
    l11 = by_key.get(LOG11)
    log11 = None
    if l11:
        rels = l11["sheet_relationships"]
        rel_classes = [r["classification"] for r in rels]
        log11 = {
            "sheet_refs": l11["sheet_refs"], "default_status": l11["default_status"],
            "default_reason": l11["reason"], "relationship_classification": rel_classes,
            "relationships": rels,
            "is_reset_equation": any(c == "reset_equation" for c in rel_classes),
            "still_abstains": l11["default_status"] == "ABSTAIN",
            "missing_evidence": ("frame edge resolves the cross-frame LINK, but a unique start "
                                 "anchor + an authored box whose footage/endpoints match the span "
                                 "in the translated frame are still MISSING"),
        }

    # Q3 -- a continuous (no-edge) transition must never be classified reset
    reset_on_no_edge = [t for d in details.values() for t in d["cross_sheet_transitions"]
                        if not t["safe_edge"] and t["classification"] == "reset_equation"]
    # Q4 -- a reset (safe edge, raw within tol, translated beyond tol) must never be continuous
    reset_through_raw = [
        t for d in details.values() for t in d["cross_sheet_transitions"]
        if t["safe_edge"] and t["raw_gap_ft"] is not None and t["raw_gap_ft"] <= DEFAULT_LINK_TOL
        and t["translated_gap_ft"] is not None and t["translated_gap_ft"] > DEFAULT_LINK_TOL
        and t["classification"] == "continuous_station"]
    ambiguous_coincidences = [
        t for d in details.values() for t in d["cross_sheet_transitions"]
        if t["classification"] == "ambiguous"]

    # Q5 -- would a classifier-gated opt-in preserve all current placements?
    placed_offenders = [{"log_key": d["log_key"], "cross_classes": d["cross_classes"]}
                        for d in placed if not d["all_cross_linkable"]]
    placed_all_linkable = not placed_offenders

    # Q6 -- representative abstains + missing-evidence backlog
    backlog = Counter(d["reason"] for d in abstains)
    abstain_examples, seen = [], set()
    for d in sorted(abstains, key=lambda x: x["log_key"]):
        if d["reason"] not in seen:
            seen.add(d["reason"])
            abstain_examples.append({"log_key": d["log_key"], "sheet_refs": d["sheet_refs"],
                                     "reason": d["reason"],
                                     "sheet_relationships": d["sheet_relationships"]})
        if len(abstain_examples) >= 5:
            break
    for d in sorted(abstains, key=lambda x: x["log_key"]):  # top up to >=5 if few distinct reasons
        if len(abstain_examples) >= 5:
            break
        if d["log_key"] not in {a["log_key"] for a in abstain_examples}:
            abstain_examples.append({"log_key": d["log_key"], "sheet_refs": d["sheet_refs"],
                                     "reason": d["reason"],
                                     "sheet_relationships": d["sheet_relationships"]})

    return {
        "placed_count": len(placed), "abstain_count": len(abstains),
        "regressed_rows": regressed_rows, "regressed_all_continuous": regressed_all_continuous,
        "log11": log11,
        "reset_on_no_edge_count": len(reset_on_no_edge),
        "reset_through_raw_count": len(reset_through_raw),
        "ambiguous_coincidence_count": len(ambiguous_coincidences),
        "placed_all_linkable": placed_all_linkable, "placed_offenders": placed_offenders,
        "missing_evidence_backlog": dict(backlog),
        "abstain_examples": abstain_examples,
    }


def _verdict(default_ok: bool, a: Dict[str, Any]) -> Dict[str, str]:
    if not default_ok:
        v, why = "NOT_SAFE", "default run did NOT reproduce the 23/58 golden -- comparison untrustworthy"
    elif a["regressed_all_continuous"] and a["placed_all_linkable"] \
            and a["reset_on_no_edge_count"] == 0 and a["reset_through_raw_count"] == 0:
        v = "READY_FOR_SAFE_OPTIN_ATTEMPT"
        why = ("the classifier preserves all 8 regressed runs as continuous_station and every one "
               "of the current placements links under {same_sheet|continuous_station|reset_equation}; "
               "a classifier-gated opt-in is now worth ATTEMPTING and re-validating via M8.2d "
               "(this does NOT activate translation or place any new log)")
    else:
        v = "NEEDS_MORE_EVIDENCE"
        why = ("the classifier does not yet preserve every current placement (or mis-handles a "
               "continuous/reset case) -- investigate the offenders before any opt-in attempt")
    return {"verdict": v, "verdict_reason": why}


def main() -> int:
    out_dir = _REPO_ROOT / "data" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "transition_classifier_report.json"
    md_path = out_dir / "transition_classifier_report.md"

    if not os.path.isfile(PDF) or not os.path.isdir(CORPUS_DIR):
        report = {"status": "INPUTS_MISSING", "pdf": PDF, "corpus_dir": CORPUS_DIR,
                  "verdict": "NEEDS_MORE_EVIDENCE"}
        json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[m8.2f] STOP: inputs missing (pdf={os.path.isfile(PDF)} corpus={os.path.isdir(CORPUS_DIR)})")
        return 2
    corpus = enumerate_corpus(CORPUS_DIR)
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.2f] STOP: expected {EXPECTED_COUNT} logs, got {len(corpus)} -- corpus drift.")
        return 3

    offset = Settings.for_proof().sheet_offset
    plan = PlanPdf(PDF)
    dialect = select_dialect(plan)
    graph = build_plan_frame_graph(plan, offset)
    cp = conflict_sheet_pairs(graph)

    details: Dict[str, Dict[str, Any]] = {}
    errors: List[str] = []
    for p in corpus:
        try:
            bore = load_borelog(str(p))
        except Exception as e:  # ingest failure -> ERROR (matches the sweep), do not crash
            errors.append(f"{p.stem}: {type(e).__name__}: {e}")
            continue
        details[bore.bore_id] = _detail(bore, plan, dialect, offset, graph, cp, p.stem)
    plan.close()

    default_dist, default_ok = _classify_corpus(details, errors)
    analysis = _analyze(details)
    verdict = _verdict(default_ok, analysis)

    report = {
        "milestone": "truelinev2 M8.2f -- cross-sheet transition classifier (read-only helper + proof)",
        "read_only": True, "default_run_match_unchanged": True,
        "frame_translation_active": False,
        "m8_2d_optin_status": "NOT_SAFE (unchanged -- this report does not activate anything)",
        "link_tol_ft": DEFAULT_LINK_TOL,
        "pdf": PDF, "corpus_dir": CORPUS_DIR, "logs": len(details) + len(errors),
        "frame_graph": {"safe_edges": len(graph.edges), "conflicts": len(graph.conflicts),
                        "conflict_sheet_pairs": sorted([list(x) for x in cp])},
        "default_distribution": default_dist, "default_matches_golden": default_ok, "golden": GOLDEN,
        "errors": errors,
        "questions": {
            "q1_regressed_preserved_as_continuous": analysis["regressed_all_continuous"],
            "q2_log11_is_reset_equation_but_still_abstains": bool(
                analysis["log11"] and analysis["log11"]["is_reset_equation"]
                and analysis["log11"]["still_abstains"]),
            "q3_no_continuous_classified_as_reset": analysis["reset_on_no_edge_count"] == 0,
            "q4_no_reset_passed_through_raw_matching": analysis["reset_through_raw_count"] == 0,
            "q5_optin_would_preserve_all_current_placements": analysis["placed_all_linkable"],
            "q6_missing_evidence_for_new_placements": analysis["missing_evidence_backlog"],
        },
        "analysis": analysis,
        **verdict,
    }
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")

    print(f"[m8.2f] default={default_dist} golden_ok={default_ok} "
          f"safe_edges={len(graph.edges)} conflicts={len(graph.conflicts)}")
    print(f"[m8.2f] regressed_all_continuous={analysis['regressed_all_continuous']} "
          f"placed_all_linkable={analysis['placed_all_linkable']} "
          f"(placed={analysis['placed_count']})")
    print(f"[m8.2f] no_continuous_as_reset={analysis['reset_on_no_edge_count']==0} "
          f"no_reset_through_raw={analysis['reset_through_raw_count']==0} "
          f"ambiguous_coincidences={analysis['ambiguous_coincidence_count']}")
    if analysis["log11"]:
        print(f"[m8.2f] log11 relationship={analysis['log11']['relationship_classification']} "
              f"default={analysis['log11']['default_status']} still_abstains={analysis['log11']['still_abstains']}")
    print(f"[m8.2f] M8.2d opt-in status: NOT_SAFE (unchanged); frame translation INACTIVE")
    print(f"[m8.2f] VERDICT: {verdict['verdict']} -- {verdict['verdict_reason']}")
    print(f"[m8.2f] report -> {md_path}")
    return 0


def _yn(b: bool) -> str:
    return "YES" if b else "NO"


def _render_md(r: Dict[str, Any]) -> str:
    a = r["analysis"]
    q = r["questions"]
    parts = [
        "# TrueLine v2 M8.2f -- Cross-Sheet Transition Classifier (read-only proof)",
        "",
        "**This is a helper + proof report. It does NOT change default behavior, does NOT wire the",
        "classifier into `decide.py`/`run_match`, and does NOT activate frame translation.**",
        f"- default distribution: `{r['default_distribution']}` (matches 23/58 golden: "
        f"**{_yn(r['default_matches_golden'])}**)",
        f"- safe frame edges: {r['frame_graph']['safe_edges']}  ·  conflicts: "
        f"{r['frame_graph']['conflicts']}  ·  conflicting sheet pairs: "
        f"{r['frame_graph']['conflict_sheet_pairs']}",
        f"- M8.2d opt-in status: **{r['m8_2d_optin_status']}**  ·  frame translation active: "
        f"**{r['frame_translation_active']}**",
        "",
        f"## VERDICT: {r['verdict']}",
        f"{r['verdict_reason']}",
        "",
        "> READY_FOR_SAFE_OPTIN_ATTEMPT means only that a classifier-gated opt-in is now worth",
        "> ATTEMPTING and re-validating via M8.2d. It is NOT an activation and NOT a product claim.",
        "> The current M8.2c-Step-2 opt-in rule remains NOT_SAFE until a future activation proof exists.",
        "",
        "## The six questions",
        f"1. **Each regressed log preserved as `continuous_station`?** {_yn(q['q1_regressed_preserved_as_continuous'])}",
        f"2. **log11 classified `reset_equation` yet still abstains (missing anchor evidence)?** "
        f"{_yn(q['q2_log11_is_reset_equation_but_still_abstains'])}",
        f"3. **Never classifies a continuous (no-edge) transition as a reset?** "
        f"{_yn(q['q3_no_continuous_classified_as_reset'])}  (offending count: {a['reset_on_no_edge_count']})",
        f"4. **Never lets a reset/equation pass as continuous via raw equal-station?** "
        f"{_yn(q['q4_no_reset_passed_through_raw_matching'])}  (offending count: "
        f"{a['reset_through_raw_count']}; ambiguous coincidences flagged: {a['ambiguous_coincidence_count']})",
        f"5. **Would a classifier-gated opt-in preserve ALL {a['placed_count']} current placements?** "
        f"{_yn(q['q5_optin_would_preserve_all_current_placements'])}  (offenders: {a['placed_offenders']})",
        "6. **What evidence is still missing before a NEW placement is safe?** see backlog below.",
        "",
        "## Q1 -- the 8 M8.2d-regressed logs (must stay `continuous_station`)",
    ]
    for row in a["regressed_rows"]:
        parts.append(f"- **{row['log_key']}** (default {row['default_status']}, sheets {row['sheet_refs']}): "
                     f"cross-sheet classes = {row['cross_classes']}  -> preserved="
                     f"{_yn(row['preserved_continuous'])}")
    parts += [
        "",
        "## Q2 -- log11",
        (json.dumps(a["log11"], indent=2) if a["log11"] else "  - (log11 not found)"),
        "",
        f"## Q5 -- current placements ({a['placed_count']}) under the classifier",
        f"- all current placements link under {{same_sheet|continuous_station|reset_equation}}: "
        f"**{_yn(a['placed_all_linkable'])}**",
        f"- offenders (placements a classifier-gated opt-in would NOT preserve): {a['placed_offenders']}",
        "",
        "## Q6 -- missing-evidence backlog across the abstains",
        json.dumps(a["missing_evidence_backlog"], indent=2),
        "",
        "### Representative abstains (>=5)",
    ]
    for ex in a["abstain_examples"]:
        rels = [rr["classification"] for rr in ex["sheet_relationships"]]
        parts.append(f"- **{ex['log_key']}** sheets {ex['sheet_refs']} relationship={rels} "
                     f"reason=`{ex['reason']}`")
    parts += [
        "",
        "## What this does NOT prove",
        "- NOT product readiness, NOT zero false placements, NOT that frame activation is safe.",
        "- The classifier is a HELPER only; it is not wired into the matcher and changes no placement.",
        "- The M8.2d opt-in remains NOT_SAFE; any activation requires a separate proof that re-runs",
        "  M8.2d with the classifier gating the cross-sheet link and shows zero regression.",
    ]
    return "\n".join(parts) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
