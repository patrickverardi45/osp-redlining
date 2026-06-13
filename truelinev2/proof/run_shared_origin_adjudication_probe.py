r"""M8.20 -- shared-origin adjudication probe (proof-only; EXTRACTION, never inference).

M8.18 narrowed log8 and log32 to the same far-sheet structure
``NEXTLINK@378,409`` and M8.19 proved each bore's cross-sheet geometry by
path length -- but both probes DISCARDED the walked geometry, so "the two
bores share one drawn alignment" remained an inference from equal path
lengths (265.7 pt == 265.7 pt). The no-inference rule forbids adjudicating
the collision on that. This probe EXTRACTS the facts the M8.20 adjudication
needs and changes nothing else:

  * the two TRACED walks' ``stroke_points`` + ``visited_pieces`` are RETAINED
    and compared (symmetric cross-deviation via the public
    ``point_to_polyline``; piece-set overlap) against the structural
    JITTER_EQUIV_TOL. HONESTY: once both bores select the same survivor, the
    walks share inputs and the 0.0/1.0 agreement is a deterministic replay;
    the LOAD-BEARING independent measurement is the BOUNDARY-POINT GAP -- two
    DIFFERENT printed equations (1+76 vs 1+77) resolving to one physical
    matchline point (the DIVERGENT counterfactual was live: different
    equations selecting different matchlines/chains produce different walks);
  * each bore's printed callout CHAIN is re-assembled and its NOTE TEXTS are
    reported verbatim with any printed conduit-count tokens -- the positive
    evidence a future multi-drop law would consume;
  * log42's sheet-2 candidates get a per-candidate elimination taxonomy
    (footprint / chain-to-matchline / walk result / length tolerance), naming
    exactly where each of its rivals dies.

The probe is an HONEST MEASUREMENT: the lane is untouched, all three bores
must remain ``STRUCTURE_IDENTITY_BINDING_REQUIRED``, no segment, stroke,
card, or PNG is produced, and no tolerance is introduced or widened
(JITTER_EQUIV_TOL and DESIGN_LENGTH_REL_TOL are imported, never redefined).
Measured-fact gates (G3/G4/G5 expectations) are PINNED from the first
discovery run so any future drift fails loud.

Outputs (gitignored): data/outputs/shared_origin_adjudication_probe/
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_shared_origin_adjudication_probe
"""
from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Sequence, Tuple

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.conduit_topology import connected_chain, symbol_footprint
from truelinev2.extract.design_path import (
    DESIGN_LENGTH_REL_TOL,
    JITTER_EQUIV_TOL,
    TRACED,
    conduit_pieces,
    path_length,
    point_to_polyline,
    walk_design_path,
)
from truelinev2.extract.ladder_cluster import cluster_ladders, coherent_ladder_scale
from truelinev2.extract.matchline_join import (
    CHAIN_UNIQUE,
    assemble_callout_chain,
    extend_dash_to_boundary,
    matchline_bboxes,
    nearest_gap,
    run_callouts_ending_at,
    run_callouts_starting_at,
)
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import BRENHAM_LANE_DIALECT, cluster_symbols
from truelinev2.extract.tick_path import route_ladder_ticks
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.symbol_conduit_lane import S_STRUCTURE_REQUIRED, _sheet_no, resolve_bore
from truelinev2.proof.run_brenham_corpus import PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.match.frames import _build_plan_frame_graph
from truelinev2.stations import parse_station

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "shared_origin_adjudication_probe"
LSET = ("BORE - PORT", "BORE - VACANT PIPE")   # the log8/32/42 run classes (M8.18)

# (bore, far sheet, end sheet, start raw, end raw) -- the M8.18 trio, verbatim.
TARGETS = [
    ("log8", 18, 22, "0+00", "3+90"),
    ("log32", 18, 22, "0+00", "2+13"),
    ("log42", 2, 1, "0+00", "2+87"),
]

# Probe-report classes (typed findings, NOT lane statuses -- nothing consumes
# these as placement evidence; they exist so drift fails loud).
SHARED_ALIGNMENT = "SHARED_ALIGNMENT"
DIVERGENT_PATHS = "DIVERGENT_PATHS"
COMPARISON_NOT_AVAILABLE = "COMPARISON_NOT_AVAILABLE"

# Printed conduit-count token, e.g. `1-1.25"` in `DIR. BORE (110') 1-1.25"
# VACANT HDPE`. Depth ranges (`@ 24-36" MIN. DEPTH`) are excluded by the
# MIN lookahead. Descriptive extraction only -- no law consumes the value here.
_CONDUIT_TOKEN = re.compile(r"\b(\d+)\s*-\s*(\d+(?:\.\d+)?)\s*\"(?!\s*MIN\b)")

# Candidate elimination taxonomy (log42's per-rival accounting).
ELIM_NO_FOOTPRINT = "NO_SYMBOL_FOOTPRINT"
ELIM_NO_CHAIN = "NO_CONDUIT_CHAIN_TO_MATCHLINE"
ELIM_LENGTH = "PATH_LENGTH_OUT_OF_TOLERANCE"
SURVIVED = "SURVIVOR"


def compare_design_walks(points_a: Sequence[Tuple[float, float]],
                         pieces_a: frozenset,
                         points_b: Sequence[Tuple[float, float]],
                         pieces_b: frozenset) -> dict:
    """EXTRACTED walk-vs-walk comparison: symmetric max cross-deviation between
    the two stroke polylines (public ``point_to_polyline``, both directions)
    plus visited-piece overlap. Verdict uses the structural JITTER_EQUIV_TOL
    verbatim -- within the weld-contact scale the two walks are the SAME drawn
    line (M8.14.c law); beyond it they are physically distinct geometry.
    The deviation formula deliberately DUPLICATES design_path._cross_deviation
    via the public point_to_polyline (the private is not exported; proof seams
    duplicate for safety); an equivalence tripwire test pins the two."""
    if len(points_a) < 2 or len(points_b) < 2:
        return {"verdict": COMPARISON_NOT_AVAILABLE, "max_deviation_pt": None,
                "piece_jaccard": None, "shared_pieces": 0}
    dev = max(max(point_to_polyline(p, points_b) for p in points_a),
              max(point_to_polyline(p, points_a) for p in points_b))
    union = pieces_a | pieces_b
    shared = pieces_a & pieces_b
    return {
        "verdict": SHARED_ALIGNMENT if dev <= JITTER_EQUIV_TOL else DIVERGENT_PATHS,
        "max_deviation_pt": round(dev, 2),
        "piece_jaccard": round(len(shared) / len(union), 3) if union else None,
        "shared_pieces": len(shared),
    }


def conduit_tokens(notes: Sequence[str]) -> List[str]:
    """Every printed conduit-count token in the chain's note texts, verbatim
    ``count-diameter`` form (e.g. ``1-1.25``). Reported, never adjudicated."""
    found: List[str] = []
    for note in notes:
        for count, dia in _CONDUIT_TOKEN.findall(note or ""):
            found.append(f"{count}-{dia}")
    return found


def _boundary_and_segments(plan, off, far, end, start_raw, end_raw):
    """(boundary_raw, seg_far_ft, seg_end_ft, chain_dict) with UNIQUENESS
    asserted at every printed lookup (the M8.18 helper trusted print order;
    this probe refuses non-unique prints instead)."""
    ec = [(r, f) for r, f, _ in run_callouts_ending_at(plan.lines(end, off), end_raw)
          if f is not None and r != start_raw]
    if len(ec) != 1:
        raise AssertionError(f"end-sheet callout ending at {end_raw} not unique: {ec}")
    boundary_raw, seg_end = ec[0]
    chain = assemble_callout_chain(plan.lines(far, off), start_raw, boundary_raw)
    if chain["result"] == CHAIN_UNIQUE:
        return boundary_raw, chain["footage"], seg_end, chain
    direct = [f for r, f, _ in run_callouts_starting_at(plan.lines(far, off), start_raw)
              if f is not None and r == boundary_raw]
    if len(direct) != 1:
        raise AssertionError(f"direct far callout {start_raw}->{boundary_raw} "
                             f"not unique: {direct}")
    return boundary_raw, direct[0], seg_end, chain


def _matchline_for(plan, off, graph, dialect, far, end, boundary_raw, drawings):
    edges = [e for e in graph.edges
             if {_sheet_no(e.from_frame), _sheet_no(e.to_frame)} == {far, end}
             and boundary_raw in (e.a_raw, e.b_raw)]
    if len(edges) != 1:   # printed-artifact uniqueness, same posture as callouts
        raise AssertionError(f"frame-equation edge for {boundary_raw} between "
                             f"sheets {far}/{end} not unique: {len(edges)}")
    edge = edges[0]
    eqt = edge.source.split(None, 1)[-1]
    eqxy = next(((w["xc"], w["yc"]) for w in plan.words(far, off)
                 if w["text"] == eqt), None)
    return min(matchline_bboxes(drawings, dialect.matchline_layer),
               key=lambda bb: nearest_gap([eqxy], bb))


def _candidate_walks(plan, off, dialect, far, ml, seg_far, scale):
    """M8.18's ``_discriminate`` with the walked geometry RETAINED and every
    candidate's elimination gate RECORDED (same candidate universe, same gate
    order, same imported tolerances -- zero behavioral relaxation)."""
    drawings = plan.line_items(far, off)
    conduit = [x for x in drawings if x["layer"] in LSET]
    pieces = conduit_pieces(drawings, dialect.path_layers)
    exp = seg_far * scale
    survivors, taxonomy = [], []
    for lay in sorted({v[1] for v in dialect.structure_layers.values()}):
        for c in cluster_symbols(drawings, lay):
            label = f"{lay}@{c.x:.0f},{c.y:.0f}"
            bb = symbol_footprint(drawings, lay, (c.x, c.y))
            if not bb:
                taxonomy.append({"id": label, "eliminated_by": ELIM_NO_FOOTPRINT})
                continue
            chain = connected_chain(conduit, bb)
            bnd = extend_dash_to_boundary(chain, ml) if chain else None
            if bnd is None:
                taxonomy.append({"id": label, "eliminated_by": ELIM_NO_CHAIN})
                continue
            xy = ((bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0)
            walk = walk_design_path(pieces, xy, bnd)
            if walk["result"] != TRACED:
                taxonomy.append({"id": label, "eliminated_by": walk["result"],
                                 "paths_found": walk.get("paths_found"),
                                 "path_groups": walk.get("path_groups")})
                continue
            plen = path_length(walk["stroke_points"])
            if not (exp > 0 and abs(plen - exp) / exp <= DESIGN_LENGTH_REL_TOL):
                taxonomy.append({"id": label, "eliminated_by": ELIM_LENGTH,
                                 "path_len": round(plen, 1),
                                 "expected": round(exp, 1)})
                continue
            taxonomy.append({"id": label, "eliminated_by": SURVIVED})
            survivors.append({"id": label, "xy": xy, "bnd": bnd,
                              "path_len": round(plen, 1),
                              "stroke_points": walk["stroke_points"],
                              "visited_pieces": walk["visited_pieces"]})
    return survivors, taxonomy


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.20] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.20] STOP: inputs missing")
        return 2
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUT_DIR / "shared_origin_adjudication_probe.json"
    report_path.unlink(missing_ok=True)   # a crash must never leave a stale PASS

    plan = PlanPdf(PDF)
    ok = True
    try:
        dialect = select_dialect(plan)
        off = dialect.calibrate(plan, 13)
        graph = _build_plan_frame_graph(plan, off)

        # G1 -- the production lane is UNCHANGED (all three stay abstain), and
        # the hardcoded TARGETS stay synchronized with the loaded bore sources
        # (an env-overridden corpus must never silently desync the targets).
        statuses = {}
        for bid, _far, _end, sr, er in TARGETS:
            bore = load_borelog(str(corpus[f"bore_{bid}"]))
            if (bore.station_start_ft != parse_station(sr)
                    or bore.station_end_ft != parse_station(er)):
                raise AssertionError(
                    f"{bid} TARGETS desync: bore prints "
                    f"{bore.station_start}->{bore.station_end}, "
                    f"probe expects {sr}->{er}")
            out = resolve_bore(plan, bore, off, BRENHAM_LANE_DIALECT,
                               frame_graph=graph)
            statuses[bid] = out.status
            if out.segments:
                ok = False
                print(f"[m8.20] FAIL  {bid} emitted segments -- forbidden")
        g1 = all(s == S_STRUCTURE_REQUIRED for s in statuses.values())
        print(f"[m8.20] {'PASS' if g1 else 'FAIL'}  G1 lane unchanged "
              f"(all STRUCTURE_IDENTITY_BINDING_REQUIRED): {statuses}")
        ok &= g1

        rows: Dict[str, dict] = {}
        for bid, far, end, sr, er in TARGETS:
            boundary_raw, seg_far, seg_end, chain = _boundary_and_segments(
                plan, off, far, end, sr, er)
            ticks, _ = route_ladder_ticks(plan, far, off)
            scale = coherent_ladder_scale(cluster_ladders(ticks))
            if scale is None:   # a fallback scale would be a guess -- fail loud
                raise AssertionError(f"{bid}: no coherent ladder scale on "
                                     f"sheet {far}")
            drawings = plan.line_items(far, off)
            ml = _matchline_for(plan, off, graph, BRENHAM_LANE_DIALECT, far,
                                end, boundary_raw, drawings)
            survivors, taxonomy = _candidate_walks(
                plan, off, BRENHAM_LANE_DIALECT, far, ml, seg_far, scale)
            rows[bid] = {
                "bore_id": bid, "far_sheet": far, "end_sheet": end,
                "boundary": boundary_raw, "seg_far_ft": seg_far,
                "seg_end_ft": seg_end, "coherent_scale": scale,
                "chain_result": chain["result"],
                "chain_hops": [(a, b, f) for a, b, f, _ in chain.get("hops", [])],
                "chain_notes": chain.get("notes", []),
                "printed_conduit_tokens": conduit_tokens(chain.get("notes", [])),
                "survivors": [{"id": s["id"], "path_len": s["path_len"],
                               "bnd": [round(v, 1) for v in s["bnd"]]}
                              for s in survivors],
                "candidate_taxonomy": taxonomy,
                "_walks": survivors,   # in-memory only; geometry never serialized
            }

        # G2 -- M8.18 reproduced: survivors 1/1/0 and the same structure.
        n = {b: len(rows[b]["survivors"]) for b in rows}
        same = (n["log8"] == 1 and n["log32"] == 1
                and rows["log8"]["survivors"][0]["id"]
                == rows["log32"]["survivors"][0]["id"])
        g2 = same and n["log42"] == 0
        print(f"[m8.20] {'PASS' if g2 else 'FAIL'}  G2 M8.18 reproduced: "
              f"survivors {n} and log8/log32 collide on "
              f"{rows['log8']['survivors'][0]['id'] if same else None!r}")
        ok &= g2

        # G3 -- THE EXTRACTION (pinned: SHARED_ALIGNMENT). Honesty: with one
        # shared survivor the walk inputs coincide, so dev/jaccard replay one
        # deterministic walk; the INDEPENDENT clause is the boundary gap --
        # two DIFFERENT printed equations resolving to one physical point.
        cmpres = {"verdict": COMPARISON_NOT_AVAILABLE}
        bnd_gap = None
        if g2:
            w8 = rows["log8"]["_walks"][0]
            w32 = rows["log32"]["_walks"][0]
            cmpres = compare_design_walks(w8["stroke_points"], w8["visited_pieces"],
                                          w32["stroke_points"], w32["visited_pieces"])
            bnd_gap = round(((w8["bnd"][0] - w32["bnd"][0]) ** 2
                             + (w8["bnd"][1] - w32["bnd"][1]) ** 2) ** 0.5, 2)
        g3 = (cmpres["verdict"] == SHARED_ALIGNMENT
              and bnd_gap is not None and bnd_gap <= JITTER_EQUIV_TOL)
        print(f"[m8.20] {'PASS' if g3 else 'FAIL'}  G3 EXTRACTED comparison: "
              f"{cmpres['verdict']} (max dev {cmpres.get('max_deviation_pt')} pt, "
              f"piece jaccard {cmpres.get('piece_jaccard')}, boundary gap "
              f"{bnd_gap} pt vs JITTER_EQUIV_TOL {JITTER_EQUIV_TOL})")
        ok &= g3

        # G4 -- the two printed chains are DISTINCT printed objects (the plan
        # itself enumerates two runs over the shared alignment): different
        # intermediate hops AND different boundary stations, each closure-proven.
        h8 = rows["log8"]["chain_hops"]
        h32 = rows["log32"]["chain_hops"]
        g4 = (rows["log8"]["chain_result"] == CHAIN_UNIQUE
              and rows["log32"]["chain_result"] == CHAIN_UNIQUE
              and h8 != h32
              and rows["log8"]["boundary"] != rows["log32"]["boundary"])
        print(f"[m8.20] {'PASS' if g4 else 'FAIL'}  G4 distinct printed chains: "
              f"log8 {h8} vs log32 {h32}; conduit tokens "
              f"log8 {rows['log8']['printed_conduit_tokens']} / "
              f"log32 {rows['log32']['printed_conduit_tokens']}")
        ok &= g4

        # G5 -- log42 per-candidate elimination taxonomy, PINNED to the
        # discovery-run composition (13 candidates: 12 search-exhausted +
        # 1 no-chain) so taxonomy drift fails loud, not just survivor count.
        tax42 = rows["log42"]["candidate_taxonomy"]
        dist = {}
        for t in tax42:
            dist[t["eliminated_by"]] = dist.get(t["eliminated_by"], 0) + 1
        g5 = (n["log42"] == 0
              and dist == {"DESIGN_PATH_SEARCH_EXHAUSTED": 12,
                           ELIM_NO_CHAIN: 1})
        print(f"[m8.20] {'PASS' if g5 else 'FAIL'}  G5 log42 taxonomy pinned: "
              f"{dist}")
        ok &= g5

        # G6 -- nothing rendered, nothing placed.
        g6 = not list(OUT_DIR.glob("*.png"))
        print(f"[m8.20] {'PASS' if g6 else 'FAIL'}  G6 no artifact rendered")
        ok &= g6

        for row in rows.values():       # geometry stays in-memory only
            row.pop("_walks", None)

        report = {
            "milestone": ("truelinev2 M8.20 -- shared-origin adjudication probe "
                          "(extraction, not inference; lane unchanged; zero "
                          "strokes)"),
            "corpus_dir_used": corpus_dir, "corpus_resolution": how,
            "plan_pdf": PDF, "verdict": "PASS" if ok else "FAILURE",
            "adjudication": {
                "walk_comparison": cmpres,
                "walk_comparison_honesty": (
                    "with one shared survivor the two walks share inputs, so "
                    "max_deviation/jaccard replay one deterministic walk; the "
                    "independent measured clause is boundary_gap_pt -- two "
                    "different printed equations (1+76 / 1+77) resolving to "
                    "one physical matchline point"),
                "boundary_gap_pt": bnd_gap,
                "finding": (
                    "log8 and log32 are TWO DISTINCT PRINTED RUNS (unique "
                    "callout chains with different intermediate and boundary "
                    "stations, each footage-closure-proven) that bind ONE "
                    "shared drawn alignment from ONE shared origin structure. "
                    "The collision is therefore a SHARED-ALIGNMENT duo, not a "
                    "wrong-candidate selection; neither bore can be placed "
                    "until a multi-drop law consumes positive printed "
                    "evidence at the origin/alignment."),
                "named_missing": (
                    "a printed multi-conduit statement binding the shared "
                    "alignment (per-chain conduit tokens or an aggregate "
                    "count callout) consumable by a future, separately "
                    "authorized multi-drop evidence law; log42 separately "
                    "needs a uniquely traceable sheet-2 design path (see "
                    "candidate_taxonomy for where each rival dies)"),
            },
            "bores": list(rows.values()),
        }
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[m8.20] report -> {report_path}")
    finally:
        plan.close()

    print(f"[m8.20] {'PASS' if ok else 'FAILURE'}")
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
