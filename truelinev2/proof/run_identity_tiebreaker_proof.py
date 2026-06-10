r"""M8.3a -- run-identity tiebreaker PROOF (log48-first; read-only; no engine change).

Sweeps the corpus for ``GE_2_COEQUAL_CANDIDATES_NO_TIEBREAKER`` abstains, then for
each tie: collapses near-duplicate readings into physically-distinct routes,
extracts each route's identity evidence (conduit thread, corridor/street tokens,
end-structure labels, frame-graph hop classes), and applies the ONLY safe rule the
helpers permit -- auto-resolve IFF exactly one physical route survives collapse.
>=2 survivors are profiled for a human pick-card, never auto-picked.

READ-ONLY: imports the matcher pieces exactly like the M6 diagnostic (build_chains/
score_chain/decide are CALLED, not modified); decide.py/chains.py/engine.py and the
reset-collision gate are untouched; default behavior unchanged; outputs land in
gitignored data/outputs/ only.

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_identity_tiebreaker_proof
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence

from truelinev2.config import Settings, _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.chains import build_chains
from truelinev2.match.collision_gate import collect_equations
from truelinev2.match.decide import decide
from truelinev2.match.frames import build_frame_edges, build_frame_graph, frame_for_sheet
from truelinev2.match.score import score_chain
from truelinev2.match.transition_classifier import classify_callout_transition, conflict_sheet_pairs
from truelinev2.proof.run_brenham_corpus import CORPUS_DIR, EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_identity_tiebreaker import (
    BoxRead,
    RouteProfile,
    collapse_near_duplicates,
    conduit_uniform,
    decide_tiebreak,
    street_tokens,
    structure_tokens,
    _signature,
)

OUT_JSON = _REPO_ROOT / "data" / "outputs" / "run_identity_tiebreaker_proof.json"
OUT_MD = _REPO_ROOT / "data" / "outputs" / "run_identity_tiebreaker_proof.md"
NEAR_X, NEAR_Y = 200.0, 120.0  # display-space token radius around a box (probe-validated)


def _nearby_words(plan: PlanPdf, sheet: int, offset: int,
                  bbox: Optional[List[float]]) -> List[str]:
    if not bbox:
        return []
    cx, cy = (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0
    return [w["text"] for w in plan.words(sheet, offset)
            if abs(w["xc"] - cx) <= NEAR_X and abs(w["yc"] - cy) <= NEAR_Y]


def _box_reads(chain) -> List[BoxRead]:
    return [BoxRead(sheet=c.sheet, from_ft=c.from_ft, to_ft=c.to_ft,
                    conduit=c.conduit, vacant=c.vacant, text=c.text) for c in chain]


def _profile(plan: PlanPdf, offset: int, graph, conflicts, chain,
             readings: int, deltas) -> RouteProfile:
    reads = _box_reads(chain)
    corridors: List[str] = []
    for c in chain:
        corridors.extend(street_tokens(_nearby_words(plan, c.sheet, offset, c.bbox)))
    end_words = _nearby_words(plan, chain[-1].sheet, offset, chain[-1].bbox)
    hops = []
    for a, b in zip(chain, chain[1:]):
        if a.sheet != b.sheet:
            hops.append(classify_callout_transition(graph, conflicts, a, b).classification.value)
    return RouteProfile(
        signature=_signature(reads), readings=readings, boxes=reads,
        conduit_thread=[(c.conduit or "?") for c in chain],
        conduit_uniform_type=conduit_uniform(reads),
        corridors=sorted(set(corridors)),
        end_structures=structure_tokens(end_words),
        hop_classes=hops, deltas=deltas)


def main() -> int:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    import os
    if not os.path.isfile(PDF) or not os.path.isdir(CORPUS_DIR):
        print("[m8.3a] STOP: inputs missing")
        return 2
    corpus = enumerate_corpus(CORPUS_DIR)
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.3a] STOP: corpus drift ({len(corpus)} != {EXPECTED_COUNT})")
        return 3

    settings = Settings.for_proof()
    plan = PlanPdf(PDF)
    dialect = select_dialect(plan)
    offset = dialect.calibrate(plan, settings.sheet_offset)

    coequal: List[Dict[str, Any]] = []
    for p in corpus:
        try:
            bore = load_borelog(str(p))
        except Exception:
            continue  # ERROR class; not a coequal tie
        callouts = []
        for s in bore.sheet_refs:
            callouts.extend(dialect.extract_callouts(plan, s, offset))
        if not callouts:
            continue
        chains = build_chains(callouts, bore.station_start_ft, bore.station_end_ft)
        scored = [(ch, score_chain(ch, bore.station_start_ft, bore.station_end_ft, bore.span_ft))
                  for ch in chains]
        d = decide(scored, bore.span_ft)
        if d["reason"] != "GE_2_COEQUAL_CANDIDATES_NO_TIEBREAKER":
            continue

        cands = d["ambiguous"]
        eqs = collect_equations(plan, offset, bore.sheet_refs)
        edges = []
        for s, e in eqs.items():
            edges.extend(build_frame_edges(list(e), frame_for_sheet(s)))
        graph = build_frame_graph(edges)
        conflicts = conflict_sheet_pairs(graph)

        groups = collapse_near_duplicates([_box_reads(ch) for ch in cands])
        profiles: List[RouteProfile] = []
        for g in groups:
            ch = cands[g[0]]
            sc = score_chain(ch, bore.station_start_ft, bore.station_end_ft, bore.span_ft)
            profiles.append(_profile(plan, offset, graph, conflicts, ch, len(g),
                                     (sc["start_delta"], sc["end_delta"], sc["foot_delta"])))
        verdict = decide_tiebreak(profiles)
        coequal.append({
            "bore_id": bore.bore_id, "sheet_refs": list(bore.sheet_refs),
            "span_ft": bore.span_ft,
            "raw_candidates": len(cands),
            "physical_routes_after_collapse": len(groups),
            "routes": [{
                "readings_collapsed": pr.readings,
                "boxes": [f"s{b.sheet} {b.from_ft:.0f}->{b.to_ft:.0f} ({(b.conduit or '?')})"
                          for b in pr.boxes],
                "conduit_uniform_type": pr.conduit_uniform_type,
                "corridors": pr.corridors,
                "end_structures": pr.end_structures,
                "hop_classes": pr.hop_classes,
                "deltas_start_end_foot": pr.deltas,
            } for pr in profiles],
            "verdict": verdict,
        })
    plan.close()

    ready = [r for r in coequal if r["verdict"]["verdict"].endswith("READY_FOR_OPT_IN")]
    pick_card = [r for r in coequal
                 if r["verdict"].get("recovery") == "HUMAN_PICK_CARD"]
    log48 = next((r for r in coequal if r["bore_id"] == "log48"), None)

    report = {
        "milestone": "truelinev2 M8.3a -- run-identity tiebreaker proof (read-only)",
        "read_only": True, "default_behavior_changed": False,
        "engine_edited": False, "reset_collision_gate_touched": False,
        "coequal_logs_found": [r["bore_id"] for r in coequal],
        "auto_resolvable_by_near_duplicate_collapse": [r["bore_id"] for r in ready],
        "human_pick_card_candidates": [r["bore_id"] for r in pick_card],
        "recovery_mode_if_implemented": "REVIEW (never AUTO via a new rule)",
        "log48": log48,
        "all": coequal,
    }
    OUT_JSON.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    L = ["# M8.3a -- run-identity tiebreaker proof (read-only)", ""]
    L.append(f"- coequal-tie abstains found: {[r['bore_id'] for r in coequal]}")
    L.append(f"- auto-resolvable by near-duplicate collapse (exactly 1 physical route): "
             f"{[r['bore_id'] for r in ready] or 'NONE'}")
    L.append(f"- human pick-card candidates (>=2 distinct routes, corridors differ): "
             f"{[r['bore_id'] for r in pick_card] or 'NONE'}")
    L.append("- recovery mode if ever implemented: REVIEW-gated (never AUTO via a new rule)")
    L.append("")
    for r in coequal:
        L.append(f"## {r['bore_id']} (sheets {r['sheet_refs']}, span {r['span_ft']})")
        L.append(f"- raw candidates {r['raw_candidates']} -> physical routes "
                 f"{r['physical_routes_after_collapse']}")
        for i, rt in enumerate(r["routes"]):
            L.append(f"- route {i}: x{rt['readings_collapsed']} readings; "
                     f"deltas {rt['deltas_start_end_foot']}; hops {rt['hop_classes']}")
            for b in rt["boxes"]:
                L.append(f"    - {b}")
            L.append(f"    - corridors: {rt['corridors']} | end structures: {rt['end_structures']} "
                     f"| conduit uniform: {rt['conduit_uniform_type']}")
        L.append(f"- **verdict: {r['verdict']['verdict']}** ({r['verdict'].get('recovery')})")
        L.append(f"- {r['verdict']['reason']}")
        L.append("")
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")

    print(f"[m8.3a] coequal logs: {[r['bore_id'] for r in coequal]}")
    for r in coequal:
        print(f"[m8.3a]   {r['bore_id']}: {r['raw_candidates']} cands -> "
              f"{r['physical_routes_after_collapse']} routes -> {r['verdict']['verdict']}"
              f" ({r['verdict'].get('recovery')})")
    print(f"[m8.3a] report -> {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
