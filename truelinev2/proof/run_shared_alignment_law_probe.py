r"""M8.20 Law 1 proof -- SHARED_ALIGNMENT_MULTI_DROP on log8/log32 (proof-only).

Extracts the per-bore claims (reusing the M8.20 adjudication probe's extractors
verbatim) and the bijection universe of printed origin chains, then runs the
pure corpus-level law (``truelinev2.match.shared_alignment``) and proves:

  G1  the per-bore lane is UNCHANGED (all three stay abstain; nothing placed);
  G2  Law 1 PROVES log8 + log32 -> a REVIEW verdict (every gate holds);
  G3  the verdict is REVIEW-only (never AUTO; SUGGESTION_NOT_PLACEMENT);
  G4  log42 NEVER enters the law (no survivor -> no claim; one claim alone is
      NOT_APPLICABLE) -- the log8/log32 law cannot promote it;
  G5  shared-survivor-alone is INSUFFICIENT: dropping each positive gate yields
      a typed, named, pairwise rejection (per-bore / distinct-chains /
      alignment / conduit / multiport / bijection);
  G6  claim bijection holds for real (printed origin chains == claimed);
  G7  neither bore can steal the other's printed chain (boundary swap rejects);
  G8  nothing is rendered.

Proof-only: the law module is NOT wired into ``resolve_bore`` or the sweep, so
the all-58 census is unchanged. No tolerance is introduced or widened. No
stroke, card, grade, or PNG is produced.

Outputs (gitignored): data/outputs/shared_alignment_law_probe/
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_shared_alignment_law_probe
"""
from __future__ import annotations

import dataclasses
import json
import os
from typing import Dict

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.matchline_join import (
    CHAIN_UNIQUE,
    assemble_callout_chain,
    chain_conduit_evidence,
)
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import BRENHAM_LANE_DIALECT
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.shared_alignment import (
    GATE_BIJECTION,
    GATE_CONDUIT,
    GATE_DISTINCT_CHAINS,
    GATE_MULTIPORT,
    GATE_PER_BORE,
    SUGGESTION_LABEL,
    V_NOT_APPLICABLE,
    V_REJECTED,
    V_REVIEW,
    BoreClaim,
    shared_alignment_verdict,
)
from truelinev2.match.symbol_conduit_lane import (
    S_STRUCTURE_REQUIRED,
    _sheet_no,
    resolve_bore,
)
from truelinev2.proof.run_brenham_corpus import PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.proof.run_shared_origin_adjudication_probe import (
    TARGETS,
    _boundary_and_segments,
    _candidate_walks,
    _matchline_for,
)
from truelinev2.match.frames import _build_plan_frame_graph

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "shared_alignment_law_probe"

# Dialect-sourced gate-4 vocabulary (no convention strings invented here): the
# conduit MATERIAL token and the printed multi-port origin-class keywords come
# from the lane dialect, exactly as the lane would consume them.
_MATERIALS = (BRENHAM_LANE_DIALECT.conduit_key.split()[-1],)   # ("HDPE",)
_PORT_KEYWORDS = next(kw for cls, kw in BRENHAM_LANE_DIALECT.class_keywords
                      if cls == "terminal_port_hh")              # ("PORT HH","TERMINAL")


def _matchline_boundary_stations(graph, far: int, end: int) -> set:
    """Every printed frame-equation boundary station between the two sheets --
    the complete universe the origin-chain enumeration searches (so an
    unclaimed origin run cannot hide from the bijection gate)."""
    out = set()
    for e in graph.edges:
        if {_sheet_no(e.from_frame), _sheet_no(e.to_frame)} == {far, end}:
            out.add(e.a_raw)
            out.add(e.b_raw)
    return out


def _origin_chain_boundaries(far_lines, start_raw: str, boundaries) -> frozenset:
    """The bijection universe: every boundary reachable by a uniqueness-
    mandatory printed chain from the shared origin's start station."""
    out = set()
    for b in boundaries:
        if assemble_callout_chain(far_lines, start_raw, b)["result"] == CHAIN_UNIQUE:
            out.add(b)
    return frozenset(out)


def _claim(plan, off, graph, bid, far, end, sr, er) -> BoreClaim:
    boundary_raw, seg_far, seg_end, chain = _boundary_and_segments(
        plan, off, far, end, sr, er)
    if chain["result"] != CHAIN_UNIQUE:
        raise AssertionError(f"{bid}: far chain not unique ({chain['result']})")
    from truelinev2.extract.ladder_cluster import (
        cluster_ladders, coherent_ladder_scale)
    from truelinev2.extract.tick_path import route_ladder_ticks
    ticks, _ = route_ladder_ticks(plan, far, off)
    scale = coherent_ladder_scale(cluster_ladders(ticks))
    drawings = plan.line_items(far, off)
    ml = _matchline_for(plan, off, graph, BRENHAM_LANE_DIALECT, far, end,
                        boundary_raw, drawings)
    survivors, _tax = _candidate_walks(plan, off, BRENHAM_LANE_DIALECT, far,
                                       ml, seg_far, scale)
    if len(survivors) != 1:
        raise AssertionError(f"{bid}: expected 1 survivor, got {len(survivors)}")
    s = survivors[0]
    notes = chain.get("notes", [])
    first_note = (notes[0] if notes else "").upper()
    return BoreClaim(
        bore_id=bid,
        survivor_id=s["id"],
        boundary_raw=boundary_raw,
        chain_unique=True,
        join_proven=True,   # M8.19 path-length join PROVEN (banked, re-proven there)
        chain_hops=tuple((a, b, f) for a, b, f, _ in chain["hops"]),
        walk_points=tuple(s["stroke_points"]),
        boundary_xy=tuple(s["bnd"]),
        conduit_count=len(chain_conduit_evidence(notes, _MATERIALS)),
        origin_multiport=any(k in first_note for k in _PORT_KEYWORDS),
    )


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.20-law] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.20-law] STOP: inputs missing")
        return 2
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUT_DIR / "shared_alignment_law_probe.json"
    report_path.unlink(missing_ok=True)

    by_id = {t[0]: t for t in TARGETS}
    plan = PlanPdf(PDF)
    ok = True
    try:
        dialect = select_dialect(plan)
        off = dialect.calibrate(plan, 13)
        graph = _build_plan_frame_graph(plan, off)

        # G1 -- the per-bore lane is UNCHANGED.
        statuses = {}
        for bid, _f, _e, _s, _r in TARGETS:
            out = resolve_bore(plan, load_borelog(str(corpus[f"bore_{bid}"])),
                               off, BRENHAM_LANE_DIALECT, frame_graph=graph)
            statuses[bid] = out.status
            if out.segments:
                ok = False
                print(f"[m8.20-law] FAIL  {bid} emitted segments -- forbidden")
        g1 = all(s == S_STRUCTURE_REQUIRED for s in statuses.values())
        print(f"[m8.20-law] {'PASS' if g1 else 'FAIL'}  G1 lane unchanged: {statuses}")
        ok &= g1

        # Extract the two sharing claims + the bijection universe.
        c8 = _claim(plan, off, graph, *by_id["log8"])
        c32 = _claim(plan, off, graph, *by_id["log32"])
        claims = [c8, c32]
        far = by_id["log8"][1]
        universe = _origin_chain_boundaries(
            plan.lines(far, off), "0+00",
            _matchline_boundary_stations(graph, far, by_id["log8"][2]))

        verdict = shared_alignment_verdict(claims,
                                           origin_chain_boundaries=universe)

        # G2 -- Law 1 PROVES the pair (every gate holds).
        g2 = (verdict["verdict"] == V_REVIEW
              and verdict["shared_origin"] == "NEXTLINK@378,409"
              and verdict["bores"] == ["log32", "log8"]
              and sorted(verdict["boundaries"]) == ["1+76", "1+77"])
        print(f"[m8.20-law] {'PASS' if g2 else 'FAIL'}  G2 Law 1 PROVES "
              f"log8+log32: {verdict['verdict']} on {verdict.get('shared_origin')} "
              f"boundaries {verdict.get('boundaries')}")
        ok &= g2

        # G3 -- REVIEW-only, never AUTO, never a placement.
        g3 = (verdict.get("review_only") is True and verdict.get("auto") is False
              and verdict.get("mode") == "REVIEW_ONLY"
              and verdict.get("label") == SUGGESTION_LABEL)
        print(f"[m8.20-law] {'PASS' if g3 else 'FAIL'}  G3 REVIEW-only "
              f"(auto={verdict.get('auto')}, label={verdict.get('label')})")
        ok &= g3

        # G4 -- log42 NEVER enters: it has no survivor, so it forms no claim,
        # and a single claim alone is NOT_APPLICABLE (no one-bore promotion).
        far42, end42 = by_id["log42"][1], by_id["log42"][2]
        _b, _sf, _se, _ch = _boundary_and_segments(plan, off, far42, end42,
                                                    "0+00", "2+87")
        ml42 = _matchline_for(plan, off, graph, BRENHAM_LANE_DIALECT, far42,
                              end42, _b, plan.line_items(far42, off))
        from truelinev2.extract.ladder_cluster import (
            cluster_ladders as _cl, coherent_ladder_scale as _cs)
        from truelinev2.extract.tick_path import route_ladder_ticks as _rt
        t42, _ = _rt(plan, far42, off)
        surv42, _ = _candidate_walks(plan, off, BRENHAM_LANE_DIALECT, far42,
                                     ml42, _sf, _cs(_cl(t42)) or 1.44)
        na = shared_alignment_verdict([c8], origin_chain_boundaries=universe)
        g4 = (len(surv42) == 0 and na["verdict"] == V_NOT_APPLICABLE)
        print(f"[m8.20-law] {'PASS' if g4 else 'FAIL'}  G4 log42 excluded "
              f"(survivors={len(surv42)}; one-bore -> {na['verdict']})")
        ok &= g4

        # G5 -- shared-survivor-alone INSUFFICIENT: each positive gate, when
        # removed, yields a typed pairwise rejection naming the exact gate.
        rej = {}
        rej[GATE_PER_BORE] = shared_alignment_verdict(
            [dataclasses.replace(c8, join_proven=False), c32],
            origin_chain_boundaries=universe)
        rej[GATE_CONDUIT] = shared_alignment_verdict(
            [dataclasses.replace(c8, conduit_count=0), c32],
            origin_chain_boundaries=universe)
        rej[GATE_MULTIPORT] = shared_alignment_verdict(
            [dataclasses.replace(c8, origin_multiport=False), c32],
            origin_chain_boundaries=universe)
        rej[GATE_BIJECTION] = shared_alignment_verdict(
            claims, origin_chain_boundaries=frozenset(universe | {"9+99"}))
        rej[GATE_DISTINCT_CHAINS] = shared_alignment_verdict(
            [c8, dataclasses.replace(c32, boundary_raw=c8.boundary_raw,
                                     chain_hops=c8.chain_hops)],
            origin_chain_boundaries=universe)
        g5 = all(
            v["verdict"] == V_REJECTED and v["failed_gate"] == gate
            and v["bores"] == ["log32", "log8"] and v.get("named_missing")
            for gate, v in rej.items())
        summary = ", ".join(f"{gate}->{v['verdict']}" for gate, v in rej.items())
        print(f"[m8.20-law] {'PASS' if g5 else 'FAIL'}  G5 typed pairwise "
              f"rejections: {summary}")
        ok &= g5

        # G6 -- the bijection universe is REAL (exactly the two claimed runs).
        g6 = sorted(universe) == ["1+76", "1+77"]
        print(f"[m8.20-law] {'PASS' if g6 else 'FAIL'}  G6 bijection universe "
              f"{sorted(universe)} == claimed ['1+76','1+77']")
        ok &= g6

        # G7 -- neither bore can steal the other's chain (boundary swap = gate 3).
        steal = shared_alignment_verdict(
            [dataclasses.replace(c8, boundary_raw=c32.boundary_raw), c32],
            origin_chain_boundaries=universe)
        g7 = (steal["verdict"] == V_REJECTED
              and steal["failed_gate"] == GATE_DISTINCT_CHAINS)
        print(f"[m8.20-law] {'PASS' if g7 else 'FAIL'}  G7 chain-steal rejected: "
              f"{steal['verdict']}/{steal.get('failed_gate')}")
        ok &= g7

        # G8 -- nothing rendered.
        g8 = not list(OUT_DIR.glob("*.png"))
        print(f"[m8.20-law] {'PASS' if g8 else 'FAIL'}  G8 no artifact rendered")
        ok &= g8

        report = {
            "milestone": ("truelinev2 M8.20 Law 1 -- SHARED_ALIGNMENT_MULTI_DROP "
                          "proof (REVIEW-only; lane unchanged; zero strokes)"),
            "corpus_dir_used": corpus_dir, "corpus_resolution": how,
            "plan_pdf": PDF, "verdict": "PASS" if ok else "FAILURE",
            "law_verdict": verdict,
            "lane_statuses": statuses,
            "bijection_universe": sorted(universe),
            "rejections": {k: {"verdict": v["verdict"],
                               "failed_gate": v.get("failed_gate"),
                               "named_missing": v.get("named_missing")}
                           for k, v in rej.items()},
            "materials": list(_MATERIALS),
            "port_keywords": list(_PORT_KEYWORDS),
        }
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[m8.20-law] report -> {report_path}")
    finally:
        plan.close()

    print(f"[m8.20-law] {'PASS' if ok else 'FAILURE'}")
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
