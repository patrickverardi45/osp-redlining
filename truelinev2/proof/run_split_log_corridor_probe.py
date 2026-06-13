r"""M8.21 -- split-log / corridor-pruned trace probe for log42 (proof-only).

The owner-supplied M8.20 correction said log42 (Segment B of split handwritten
parent bore_log13; sibling log41 = Segment A) is a parent/child split-log
context whose printed chain is likely 0+00->2+70 (270'), 2+70->2+87 (17'),
2+87->5+19 (232'). This probe EXTRACTS and adjudicates that lane end to end,
implementing the M8.20-named missing capability (corridor-pruned unique
tracing, ``extract/corridor_prune.py``) and the frame-ownership law its
adversarial review proved necessary. The production lane is UNTOUCHED; all
statuses and the all-58 census are unchanged; no stroke, card, PNG, or AUTO.

ADJUDICATED FINDINGS (each gated below, pinned from the discovery run):
  * the printed parent chain is REAL: all three fragments print verbatim
    (270' + 17' PORT TERMINAL TAIL class; 232' VACANT class); 270+17 = 287 =
    log42's span EXACTLY; the 232' fragment is class-distinct ADJACENT print
    context claimed by NO corpus bore -- it is never summed into log42;
  * the corridor (the existing length law as a piece filter; budget and
    jump cap UNCHANGED) completes the dense sheet-2 search that M8.18-M8.20
    could only leave DESIGN_PATH_SEARCH_EXHAUSTED: every one of the 13
    candidates now dies/survives with a POSITIVE typed certificate, and the
    banked log8/log32 controls reproduce byte-identically under pruning;
  * the unique corridor survivor (the equation-bound 13"X24"X24" INSTALLER
    HH at NEXTLINK@818,419) is NOT log42's origin: the frame-ownership gates
    prove it is the printed INTERIOR reset at callout-frame 0+46 (the M8.6
    interior-boundary case) -- its traced 225.2 ft is footage MINUS the
    printed 46, five independent measurements locking. The origin-identity
    claim is REFUSED (typed INTERIOR_RESET_NOT_ORIGIN); log42 remains a
    typed abstain with a SHARPER named missing artifact: the callout-frame
    origin structure (upstream HH, corridor verdict DESIGN_PATH_AMBIGUOUS --
    a strand discriminator) plus owner source re-reads;
  * log41's handwritten end (0+44, source-flagged ambiguous vs 0+50) maps to
    the printed 46-ft HH-HH hop ending at the installer; 44 != 46 and NO
    tolerance bridges them: typed SOURCE_DIGIT_REREAD_REQUIRED conflict
    enumeration (no preferred reading -- the owner supplies the fact).

Gates:
  G1  lane unchanged: log41 END_IDENTITY_UNPRINTED; log8/log32/log42
      STRUCTURE_IDENTITY_BINDING_REQUIRED; zero segments; TARGETS desync
      guard against the loaded bore sources.
  G2  printed chain: far chain CALLOUT_CHAIN_UNIQUE 270.0 + end callout 17.0
      + closure 270+17 == 287 == span EXACT; exactly one printed callout
      starts at 2+87 (-> 5+19, 232.0, VACANT-classed); class split pinned;
      the 232' fragment claimed by no corpus bore (sheet-1 claimant set ==
      {log41, log42}, neither spanning it); log42's span never re-derived.
  G3  split provenance (proof-local xlsx note read; WEAK grouping only per
      run-segment-hierarchy doctrine *8): both children name bore_log13,
      segments A/B, same source photo/date/crew/print; consumed-artifact
      allowlist holds (corpus xlsx + plan PDF only; no DO_NOT_IMPORT path,
      no backend/ path -- import isolation cannot see file reads, so the
      boundary is gated here).
  G4  printed reset origins adjudicated: exactly 2 on sheet 2; the 0+46
      installer origin's label box contains BOTH the equation token and the
      label words (printed adjacency, never reading-order trust); BOTH
      locator forms (equation-token lane form; label-word + context form)
      bind to the SAME symbol within CLUSTER_RADIUS; rival clusters pinned;
      the second origin (7+40 splice) POSITIVELY excluded with a typed
      reason (class-unmodeled; no modeled-layer cluster nearby; chord
      reported honestly) -- never silently omitted.
  G5  corridor conservativeness controls (log8/log32): pruned == unpruned at
      byte strength -- same survivor, byte-identical stroke points,
      identical paths_found/path_groups, per-candidate elimination-type map
      pinned (typed type-shifts visible, never silent).
  G6  corridor-pruned log42 walks: pinned taxonomy {8 chord-infeasible, 1
      out-of-tolerance, 2 finished-AMBIGUOUS, 1 no-chain, 1 corridor
      survivor}; survivor result TRACED and not EXHAUSTED with one jitter
      group; corridor provenance (universe tag, bound, kept/total pieces)
      on every record; margin sensitivity (inflated bound -> identical
      rounded signature, search finished); slack never load-bearing (max
      vertex min-sum <= exp * (1 + DESIGN_LENGTH_REL_TOL)).
  G7  frame ownership (the adversarial-review law): the sheet-2 lateral
      ladder ticks place the matchline boundary at callout station ~2+70
      and the installer at ~0+46 == the printed equation's parent station;
      survivor path length == (footage - 46) within 1%; printed 46' hop +
      survivor path reconstructs the full 270 within 1.5%; verdict
      INTERIOR_RESET_NOT_ORIGIN pinned; the upstream origin candidate's
      corridor verdict (DESIGN_PATH_AMBIGUOUS, 4 paths) pinned as the named
      missing artifact.
  G8  log41 conflict enumeration: typed SOURCE_DIGIT_REREAD_REQUIRED record
      listing the conflicting readings {0+44 digitized, 0+50 source-alt,
      0+46 printed-candidate} with NO preferred/selected/corrected field
      (validator refuses); engine binding for 44.0 and 50.0 both refuse
      (no tolerance bridges to 46); the record carries OWNER_REREAD action.
  G9  posture: nothing rendered (no PNG); walk geometry in-memory only;
      report verdict classes are not lane statuses.

HONESTY NOTES. Corridor uniqueness is a DIFFERENT certificate class from a
finished full-universe search (it certifies uniqueness among
length-admissible-capable geometry only -- see ``extract/corridor_prune.py``);
every survivor record carries ``uniqueness_universe`` so no consumer can
mistake it for M8.18-class survivorship, and Law 1's gate-1 vocabulary
("M8.18-class single design-path survivor") does NOT accept corridor-class
survivors. The M8.20 UNPRUNED log42 taxonomy stays authoritative for the
full universe and is cross-pinned here, not re-run. The stale
``data/outputs/reviewer_payload_contract.json`` log42 PLACED_REVIEW block is
a pre-M8.14 text-era artifact contradicting lane truth -- superseded,
pending regeneration (named follow-up; never consumed here).

Outputs (gitignored): data/outputs/split_log_corridor_probe/
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_split_log_corridor_probe
"""
from __future__ import annotations

import json
import math
import os
from typing import Dict, List, Optional, Sequence, Tuple

import openpyxl

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.conduit_topology import (FOOTPRINT_RADIUS,
                                                 MAX_DASH_GAP, connected_chain,
                                                 symbol_footprint)
from truelinev2.extract.corridor_prune import (LENGTH_INFEASIBLE_CHORD,
                                               UNIVERSE_LENGTH_CORRIDOR,
                                               chord_infeasible,
                                               corridor_bound, prune_pieces)
from truelinev2.extract.design_path import (DESIGN_LENGTH_REL_TOL, TRACED,
                                            conduit_pieces, path_length,
                                            walk_design_path)
from truelinev2.extract.ladder_cluster import (cluster_ladders,
                                               coherent_ladder_scale)
from truelinev2.extract.matchline_join import (CHAIN_UNIQUE,
                                               assemble_callout_chain,
                                               extend_dash_to_boundary,
                                               matchline_bboxes, nearest_gap,
                                               run_callouts_ending_at,
                                               run_callouts_starting_at)
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_anchor import (BOUND,
                                                 bind_origin_by_parent_station)
from truelinev2.extract.structure_position import (BRENHAM_LANE_DIALECT,
                                                   CLUSTER_RADIUS,
                                                   POSITION_BOUND,
                                                   cluster_symbols,
                                                   resolve_structure_position)
from truelinev2.extract.tick_path import route_ladder_ticks
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.symbol_conduit_lane import (S_STRUCTURE_REQUIRED,
                                                  S_UNPRINTED, _sheet_no,
                                                  resolve_bore)
from truelinev2.proof.run_brenham_corpus import PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.proof.station_equation_ownership import extract_reset_origins
from truelinev2.service import _build_plan_frame_graph
from truelinev2.stations import parse_station

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "split_log_corridor_probe"
LSET = ("BORE - PORT", "BORE - VACANT PIPE")   # the M8.18/M8.20 run classes

# The split family under adjudication (sources verbatim; G1 desync-guarded).
TARGETS = [
    ("log42", 2, 1, "0+00", "2+87"),   # Segment B (col2) of bore_log13
    ("log8", 18, 22, "0+00", "3+90"),  # control (banked M8.18 survivor)
    ("log32", 18, 22, "0+00", "2+13"),  # control (banked M8.18 survivor)
]
LOG41 = ("log41", "0+00", "0+44")      # Segment A (col1) of bore_log13

# Probe-report classes (typed findings, NOT lane statuses).
SURVIVOR_IN_CORRIDOR = "SURVIVOR_IN_CORRIDOR"
INTERIOR_RESET_NOT_ORIGIN = "INTERIOR_RESET_NOT_ORIGIN"
SOURCE_DIGIT_REREAD_REQUIRED = "SOURCE_DIGIT_REREAD_REQUIRED"
ADJACENT_PRINT_CONTEXT = "ADJACENT_PRINT_CONTEXT_NOT_CLAIMED"
ORIGIN_CLASS_UNMODELED = "ORIGIN_CLASS_UNMODELED"

# Cross-pin of the banked M8.20 UNPRUNED log42 taxonomy (the full-universe
# authority; run_shared_origin_adjudication_probe G5 re-proves it).
EXPECT_UNPRUNED_M820 = {"DESIGN_PATH_SEARCH_EXHAUSTED": 12,
                        "NO_CONDUIT_CHAIN_TO_MATCHLINE": 1}

# Pinned from the discovery run (drift fails loud, never absorbed).
EXPECT_PRUNED_42 = {LENGTH_INFEASIBLE_CHORD: 8,
                    "PATH_LENGTH_OUT_OF_TOLERANCE": 1,
                    "DESIGN_PATH_AMBIGUOUS": 2,
                    "NO_CONDUIT_CHAIN_TO_MATCHLINE": 1,
                    SURVIVOR_IN_CORRIDOR: 1}
EXPECT_SURVIVOR_42 = "NEXTLINK@818,419"
EXPECT_SURVIVOR_PLEN = 324.2
EXPECT_UPSTREAM_ID = "NEXTLINK@819,351"
EXPECT_UPSTREAM = {"eliminated_by": "DESIGN_PATH_AMBIGUOUS", "paths_found": 4}
EXPECT_CONTROL_SURVIVOR = "NEXTLINK@378,409"
EXPECT_CONTROL_PLEN = 265.7
# Control per-candidate elimination map: banked unpruned type -> pruned type.
# Type SHIFTS are expected and visible (chord pre-gate fires before walking);
# eliminated stays eliminated, survivor stays survivor.
EXPECT_CONTROL_TYPE_SHIFTS = {
    "PATH_LENGTH_OUT_OF_TOLERANCE": {"PATH_LENGTH_OUT_OF_TOLERANCE",
                                     LENGTH_INFEASIBLE_CHORD},
    "DESIGN_PATH_NOT_CONNECTED": {"DESIGN_PATH_NOT_CONNECTED",
                                  LENGTH_INFEASIBLE_CHORD},
    "SURVIVOR": {"SURVIVOR"},
}
# G4 pins (printed-evidence uniqueness; coordinates rounded to 1 decimal).
EXPECT_EQ_SYMBOL = (818.4, 419.0)
EXPECT_EQ_RIVALS = ((819.0, 351.5), (455.7, 419.1), (481.0, 352.1))
EXPECT_LABEL_BOX_WORDS = {"STA", "0+46=0+00", '13"X24"X24"', "INSTALLER",
                          "HH"}
# G7 pins (frame ownership; measured on the discovery run).
EXPECT_BOUNDARY_STA_FT = 269.8      # matchline boundary in callout frame
EXPECT_INSTALLER_STA_FT = 45.9      # == printed STA 0+46=0+00 parent side
FRAME_RESIDUAL_TOL = 0.01           # |plen_ft - (footage-46)| / (footage-46)
ARC_RESIDUAL_TOL = 0.015            # |(hop+plen)_ft - footage| / footage

# Keys that may NEVER appear in a conflict-enumeration record: the engine
# names the conflict, the owner supplies the fact (suggestion-not-placement
# precedent applied to source re-reads).
FORBIDDEN_CONFLICT_KEYS = ("preferred", "selected", "corrected",
                           "corrected_value", "chosen", "expected_reading")


def _d(p, q) -> float:
    return math.hypot(p[0] - q[0], p[1] - q[1])


def read_split_notes(xlsx_path: str) -> dict:
    """Proof-local split-provenance reader (NO shipped extractor parses the
    'split from' notes -- named artifact of this probe; WEAK grouping
    evidence only, never a join). Reads notes/date/crew/print verbatim."""
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    header = [str(c).strip().lower() if c is not None else "" for c in rows[0]]
    col = {name: header.index(name) for name in
           ("station", "date", "crew", "print", "notes") if name in header}
    out = {"stations": [], "notes": [], "dates": set(), "crews": set(),
           "prints": set()}
    for r in rows[1:]:
        if col.get("station") is not None and r[col["station"]] is not None:
            out["stations"].append(str(r[col["station"]]).strip())
        for key, field in (("notes", "notes"), ("date", "dates"),
                           ("crew", "crews"), ("print", "prints")):
            ci = col.get(key)
            if ci is not None and ci < len(r) and r[ci] not in (None, ""):
                if key == "notes":
                    out["notes"].append(str(r[ci]))
                else:
                    out[field].add(str(r[ci]))
    wb.close()
    return out


def validate_conflict_record(record: dict) -> None:
    """A conflict enumeration must never carry a preference -- fail loud."""
    for key in FORBIDDEN_CONFLICT_KEYS:
        if key in record:
            raise AssertionError(f"conflict record carries forbidden "
                                 f"key {key!r} -- the engine never picks a "
                                 f"reading")
    if not record.get("conflicting_readings"):
        raise AssertionError("conflict record without readings")


def ladder_station(ladder, x: float) -> float:
    """Station (ft) of an x position in a drawn ladder's own frame --
    DIRECTION-AWARE two-point linear projection (a ladder may run east or
    west; sign comes from the ticks themselves, never assumed)."""
    a, b = ladder.ticks[0], ladder.ticks[-1]
    return a.station_ft + (x - a.x) * (b.station_ft - a.station_ft) / (b.x
                                                                       - a.x)


def _x_at_station(ladder, station_ft: float) -> float:
    """Inverse of ``ladder_station`` (direction-aware)."""
    a, b = ladder.ticks[0], ladder.ticks[-1]
    return a.x + (station_ft - a.station_ft) * (b.x - a.x) / (b.station_ft
                                                              - a.station_ft)


def callout_frame_owner(ladders, boundary_x: float, boundary_ft: float):
    """THE M8.21 frame-ownership law: the ladder that OWNS a printed callout
    frame is the one that (i) draws only stations interior to the callout's
    span (0, boundary_ft) and (ii) places the printed boundary station at
    the physical boundary point within HALF ITS OWN median tick step (a
    ladder-derived band, not a new tunable). Uniqueness mandatory: 0 or >= 2
    owners -> None (typed CALLOUT_FRAME_OWNERSHIP_AMBIGUOUS abstain).
    Naive y-band/nearest-ladder selection is FORBIDDEN here -- the discovery
    run measured two drawn runs' ladders 5.1 pt apart in y (the banked
    M8.16 interleaved-band trap, again); printed-boundary projection is the
    only honest discriminator."""
    owners = []
    for lad in ladders:
        if len(lad.ticks) < 2:
            continue
        steps = [b.station_ft - a.station_ft
                 for a, b in zip(lad.ticks, lad.ticks[1:])]
        steps.sort()
        half_step = steps[len(steps) // 2] / 2.0
        interior = all(0.0 < t.station_ft < boundary_ft for t in lad.ticks)
        resid = abs(ladder_station(lad, boundary_x) - boundary_ft)
        if interior and resid <= half_step:
            owners.append((lad, resid))
    return owners[0] if len(owners) == 1 else None


def _boundary_and_segments(plan, off, far, end, start_raw, end_raw):
    """M8.20's hardened helper, duplicated by proof-seam convention
    (uniqueness asserted at every printed lookup)."""
    ec = [(r, f) for r, f, _ in run_callouts_ending_at(plan.lines(end, off),
                                                       end_raw)
          if f is not None and r != start_raw]
    if len(ec) != 1:
        raise AssertionError(f"end-sheet callout ending at {end_raw} not "
                             f"unique: {ec}")
    boundary_raw, seg_end = ec[0]
    chain = assemble_callout_chain(plan.lines(far, off), start_raw,
                                   boundary_raw)
    if chain["result"] == CHAIN_UNIQUE:
        return boundary_raw, chain["footage"], seg_end, chain
    direct = [f for r, f, _ in run_callouts_starting_at(plan.lines(far, off),
                                                        start_raw)
              if f is not None and r == boundary_raw]
    if len(direct) != 1:
        raise AssertionError(f"direct far callout {start_raw}->{boundary_raw} "
                             f"not unique: {direct}")
    return boundary_raw, direct[0], seg_end, chain


def _matchline_for(plan, off, graph, dialect, far, end, boundary_raw,
                   drawings):
    edges = [e for e in graph.edges
             if {_sheet_no(e.from_frame), _sheet_no(e.to_frame)} == {far, end}
             and boundary_raw in (e.a_raw, e.b_raw)]
    if len(edges) != 1:
        raise AssertionError(f"frame-equation edge for {boundary_raw} between "
                             f"sheets {far}/{end} not unique: {len(edges)}")
    edge = edges[0]
    eqt = edge.source.split(None, 1)[-1]
    eqxy = next(((w["xc"], w["yc"]) for w in plan.words(far, off)
                 if w["text"] == eqt), None)
    return min(matchline_bboxes(drawings, dialect.matchline_layer),
               key=lambda bb: nearest_gap([eqxy], bb))


def candidate_walks(plan, off, dialect, far, ml, seg_far, scale, *,
                    prune: bool):
    """M8.20's ``_candidate_walks`` with the corridor applied when ``prune``:
    same candidate universe, same gate order, same imported tolerances, same
    UNCHANGED budget and jump cap -- the ONLY change is the piece universe
    (and the typed chord pre-gate). Every pruned record carries corridor
    provenance so its certificate class is visible in the artifact."""
    drawings = plan.line_items(far, off)
    conduit = [x for x in drawings if x["layer"] in LSET]
    pieces = conduit_pieces(drawings, dialect.path_layers)
    exp, bound = corridor_bound(seg_far, scale)
    survivors, taxonomy = [], []
    for lay in sorted({v[1] for v in dialect.structure_layers.values()}):
        for c in cluster_symbols(drawings, lay):
            label = f"{lay}@{c.x:.0f},{c.y:.0f}"
            bb = symbol_footprint(drawings, lay, (c.x, c.y))
            if not bb:
                taxonomy.append({"id": label,
                                 "eliminated_by": "NO_SYMBOL_FOOTPRINT"})
                continue
            chain = connected_chain(conduit, bb)
            bnd = extend_dash_to_boundary(chain, ml) if chain else None
            if bnd is None:
                taxonomy.append({"id": label, "eliminated_by":
                                 "NO_CONDUIT_CHAIN_TO_MATCHLINE"})
                continue
            xy = ((bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0)
            prov = {}
            if prune:
                prov = {"uniqueness_universe": UNIVERSE_LENGTH_CORRIDOR,
                        "bound": round(bound, 1),
                        "pieces_total": len(pieces)}
                if chord_infeasible(xy, bnd, bound):
                    taxonomy.append({"id": label,
                                     "eliminated_by": LENGTH_INFEASIBLE_CHORD,
                                     "chord": round(_d(xy, bnd), 1), **prov})
                    continue
                use = prune_pieces(pieces, xy, bnd, bound)
                prov["pieces_kept"] = len(use)
            else:
                use = pieces
            walk = walk_design_path(use, xy, bnd)
            if walk["result"] != TRACED:
                taxonomy.append({"id": label, "eliminated_by": walk["result"],
                                 "paths_found": walk.get("paths_found"),
                                 **prov})
                continue
            plen = path_length(walk["stroke_points"])
            if not (exp > 0 and abs(plen - exp) / exp <= DESIGN_LENGTH_REL_TOL):
                taxonomy.append({"id": label,
                                 "eliminated_by":
                                 "PATH_LENGTH_OUT_OF_TOLERANCE",
                                 "path_len": round(plen, 1),
                                 "expected": round(exp, 1), **prov})
                continue
            kind = SURVIVOR_IN_CORRIDOR if prune else "SURVIVOR"
            taxonomy.append({"id": label, "eliminated_by": kind,
                             "path_len": round(plen, 1),
                             "expected": round(exp, 1), **prov})
            survivors.append({"id": label, "xy": xy, "bnd": bnd,
                              "path_len": round(plen, 1), "plen_raw": plen,
                              "stroke_points": walk["stroke_points"],
                              "paths_found": walk.get("paths_found"),
                              "path_groups": walk.get("path_groups"),
                              **prov})
    return survivors, taxonomy, (exp, bound, pieces)


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.21] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.21] STOP: inputs missing")
        return 2
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUT_DIR / "split_log_corridor_probe.json"
    report_path.unlink(missing_ok=True)   # a crash must never leave stale PASS

    # G3's negative-I/O allowlist: every artifact this probe consumes.
    consumed = [PDF] + [str(corpus[f"bore_{b}"]) for b in
                        ("log41", "log42", "log8", "log32")]

    plan = PlanPdf(PDF)
    ok = True
    try:
        dialect = select_dialect(plan)
        off = dialect.calibrate(plan, 13)
        graph = _build_plan_frame_graph(plan, off)
        lane = BRENHAM_LANE_DIALECT

        # ---- G1: production lane unchanged (incl. log41) + desync guard ----
        statuses: Dict[str, str] = {}
        bores = {}
        for bid, _far, _end, sr, er in TARGETS:
            bore = load_borelog(str(corpus[f"bore_{bid}"]))
            bores[bid] = bore
            if (bore.station_start_ft != parse_station(sr)
                    or bore.station_end_ft != parse_station(er)):
                raise AssertionError(f"{bid} TARGETS desync: bore prints "
                                     f"{bore.station_start}->"
                                     f"{bore.station_end}")
            out = resolve_bore(plan, bore, off, lane, frame_graph=graph)
            statuses[bid] = out.status
            if out.segments:
                ok = False
                print(f"[m8.21] FAIL  {bid} emitted segments -- forbidden")
        b41 = load_borelog(str(corpus["bore_log41"]))
        if (b41.station_start_ft != parse_station(LOG41[1])
                or b41.station_end_ft != parse_station(LOG41[2])):
            raise AssertionError("log41 TARGETS desync")
        out41 = resolve_bore(plan, b41, off, lane, frame_graph=graph)
        statuses["log41"] = out41.status
        g1 = (all(statuses[b] == S_STRUCTURE_REQUIRED
                  for b in ("log42", "log8", "log32"))
              and statuses["log41"] == S_UNPRINTED
              and not out41.segments)
        print(f"[m8.21] {'PASS' if g1 else 'FAIL'}  G1 lane unchanged: "
              f"{statuses}")
        ok &= g1

        # ---- G2: the printed parent chain ----
        boundary_raw, seg_far, seg_end, chain = _boundary_and_segments(
            plan, off, 2, 1, "0+00", "2+87")
        lines1 = plan.lines(1, off)
        third = [(r, f, n) for r, f, n in
                 run_callouts_starting_at(lines1, "2+87") if f is not None]
        end_note = next(n for r, f, n in
                        run_callouts_ending_at(lines1, "2+87")
                        if r == boundary_raw)
        sheet1_claimants = set()
        for stem, path in corpus.items():
            try:
                b = load_borelog(str(path))
            except ValueError:
                continue   # log37/log38: banked BORE_SOURCE_UNPARSEABLE gap
            if b is not None and 1 in (b.sheet_refs or []):
                sheet1_claimants.add(b.bore_id)
        frag_unclaimed = (sheet1_claimants == {"log41", "log42"}
                          and bores["log42"].span_ft == 287.0
                          and b41.span_ft < 232.0)
        g2 = (boundary_raw == "2+70" and seg_far == 270.0 and seg_end == 17.0
              and chain["result"] == CHAIN_UNIQUE
              and seg_far + seg_end == 287.0
              and bores["log42"].span_ft == 287.0
              and len(third) == 1
              and third[0][0] == "5+19" and third[0][1] == 232.0
              and "VACANT" in third[0][2]
              and "PORT TERMINAL" in end_note and "VACANT" not in end_note
              and "PORT TERMINAL" in (chain.get("notes") or [""])[0]
              and frag_unclaimed)
        print(f"[m8.21] {'PASS' if g2 else 'FAIL'}  G2 printed chain: "
              f"270+17=287 closure exact; third fragment 2+87->5+19 (232') "
              f"VACANT, sheet-1 claimants {sorted(sheet1_claimants)} -> "
              f"ADJACENT_PRINT_CONTEXT_NOT_CLAIMED")
        ok &= g2

        # ---- G3: split provenance (WEAK) + consumed-artifact allowlist ----
        n41 = read_split_notes(str(corpus["bore_log41"]))
        n42 = read_split_notes(str(corpus["bore_log42"]))
        prov41 = " ".join(n41["notes"])
        prov42 = " ".join(n42["notes"])
        bad_paths = [p for p in consumed
                     if "combined_originals" in p.replace("\\", "/")
                     or "/backend/" in p.replace("\\", "/")
                     or p.replace("\\", "/").startswith("backend/")]
        g3 = ("bore_log13" in prov41 and "Segment A" in prov41
              and "bore_log13" in prov42 and "Segment B" in prov42
              and "2025-12-03_212755" in prov41
              and "2025-12-03_212755" in prov42
              and n41["dates"] == n42["dates"]
              and n41["crews"] == n42["crews"]
              and n41["prints"] == n42["prints"] == {"1,2"}
              and not bad_paths)
        print(f"[m8.21] {'PASS' if g3 else 'FAIL'}  G3 split provenance "
              f"(WEAK grouping only) + I/O allowlist "
              f"({len(consumed)} artifacts, 0 forbidden)")
        ok &= g3

        # ---- G4: reset origins adjudicated ----
        origins = extract_reset_origins(plan.lines(2, off), 2)
        installer = [o for o in origins if o.parent_station_ft == 46.0]
        other = [o for o in origins if o.parent_station_ft != 46.0]
        words2 = plan.words(2, off)
        drawings2 = plan.line_items(2, off)
        binds = {}
        for label_text, ctx in (("0+46=0+00", ()),          # lane locator form
                                ("INSTALLER", ("0+46=0+00",)),
                                ("HH", ("0+46=0+00",)),
                                ('13"X24"X24"', ("0+46=0+00",))):
            v = resolve_structure_position(
                label_text=label_text, structure_class="installer_hh",
                words=words2, drawings=drawings2,
                layer_table=lane.structure_layers, context_texts=ctx)
            binds[label_text] = v
        v0 = binds["0+46=0+00"]
        box_words = set()
        if v0.label_box:
            x0, y0, x1, y1 = v0.label_box
            box_words = {w["text"] for w in words2
                         if x0 <= w["xc"] <= x1 and y0 <= w["yc"] <= y1}
        sym_pts = {(round(v.symbol_xy[0], 1), round(v.symbol_xy[1], 1))
                   for v in binds.values() if v.symbol_xy}
        rivals = {tuple(round(c, 1) for c in xy)
                  for v in binds.values() for xy in v.rival_cluster_xys}
        # The second printed reset origin (7+40): positively excluded, typed.
        splice = other[0] if other else None
        splice_excl = None
        if splice is not None:
            eqw = next((w for w in words2
                        if splice.parent_station_raw in w["text"]
                        and "=0+00" in w["text"]), None)
            near = None
            if eqw is not None:
                cands = [c for layv in
                         sorted({v[1] for v in lane.structure_layers.values()})
                         for c in cluster_symbols(drawings2, layv)]
                if cands:
                    near = min(_d((c.x, c.y), (eqw["xc"], eqw["yc"]))
                               for c in cands)
            splice_excl = {
                "origin": splice.source_line,
                "structure_type": splice.structure_type,
                "typed_exclusion": ORIGIN_CLASS_UNMODELED,
                "reason": (f"structure_type {splice.structure_type!r} has no "
                           f"layer-table entry; nearest modeled-layer "
                           f"cluster is {round(near, 1) if near else None} pt "
                           f"away (>> FOOTPRINT_RADIUS {FOOTPRINT_RADIUS})"),
                "nearest_modeled_cluster_pt": round(near, 1) if near else None,
            }
        g4 = (len(origins) == 2 and len(installer) == 1
              and installer[0].structure_type == "installer_hh"
              and "INSTALLER HH" in installer[0].structure_label
              and all(v.result == POSITION_BOUND for v in binds.values())
              and len(sym_pts) == 1
              and next(iter(sym_pts)) == EXPECT_EQ_SYMBOL
              and box_words == EXPECT_LABEL_BOX_WORDS
              and rivals == set(EXPECT_EQ_RIVALS)
              and splice_excl is not None
              and splice_excl["nearest_modeled_cluster_pt"] is not None
              and splice_excl["nearest_modeled_cluster_pt"]
              > FOOTPRINT_RADIUS)
        print(f"[m8.21] {'PASS' if g4 else 'FAIL'}  G4 reset origins: 2 on "
              f"sheet 2; installer label box {sorted(box_words)} binds both "
              f"locator forms to {next(iter(sym_pts)) if sym_pts else None}; "
              f"splice origin excluded typed ({ORIGIN_CLASS_UNMODELED})")
        ok &= g4

        # ---- G5: corridor conservativeness controls (log8/log32) ----
        g5 = True
        control_rows = {}
        for bid, far, end, sr, er in TARGETS[1:]:
            b_raw, sf, se, _ch = _boundary_and_segments(plan, off, far, end,
                                                        sr, er)
            ticks, _ = route_ladder_ticks(plan, far, off)
            scale = coherent_ladder_scale(cluster_ladders(ticks))
            if scale is None:
                raise AssertionError(f"{bid}: no coherent ladder scale")
            drawings = plan.line_items(far, off)
            ml = _matchline_for(plan, off, graph, lane, far, end, b_raw,
                                drawings)
            s_full, t_full, _ = candidate_walks(plan, off, lane, far, ml, sf,
                                                scale, prune=False)
            s_prun, t_prun, _ = candidate_walks(plan, off, lane, far, ml, sf,
                                                scale, prune=True)
            full_map = {t["id"]: t["eliminated_by"] for t in t_full}
            prun_map = {t["id"]: t["eliminated_by"] for t in t_prun}
            shifts_ok = all(
                prun_map[cid].replace(SURVIVOR_IN_CORRIDOR, "SURVIVOR")
                in EXPECT_CONTROL_TYPE_SHIFTS.get(kind, {kind})
                for cid, kind in full_map.items())
            byte_equal = (len(s_full) == 1 and len(s_prun) == 1
                          and s_full[0]["id"] == s_prun[0]["id"]
                          == EXPECT_CONTROL_SURVIVOR
                          and s_full[0]["stroke_points"]
                          == s_prun[0]["stroke_points"]
                          and s_full[0]["paths_found"]
                          == s_prun[0]["paths_found"]
                          and s_full[0]["path_groups"]
                          == s_prun[0]["path_groups"]
                          and s_prun[0]["path_len"] == EXPECT_CONTROL_PLEN)
            control_rows[bid] = {
                "survivor": s_prun[0]["id"] if s_prun else None,
                "path_len": s_prun[0]["path_len"] if s_prun else None,
                "stroke_points_byte_identical": byte_equal,
                "elimination_type_map": {cid: [full_map[cid], prun_map[cid]]
                                         for cid in sorted(full_map)},
            }
            g5 &= byte_equal and shifts_ok
        print(f"[m8.21] {'PASS' if g5 else 'FAIL'}  G5 controls: log8/log32 "
              f"pruned == unpruned byte-identical "
              f"(survivor {EXPECT_CONTROL_SURVIVOR}, plen "
              f"{EXPECT_CONTROL_PLEN}); type shifts typed")
        ok &= g5

        # ---- G6: corridor-pruned log42 ----
        ticks2, _ = route_ladder_ticks(plan, 2, off)
        ladders2 = cluster_ladders(ticks2)
        scale2 = coherent_ladder_scale(ladders2)
        if scale2 is None:
            raise AssertionError("log42: no coherent ladder scale -- a "
                                 "fallback would be a guess")
        ml2 = _matchline_for(plan, off, graph, lane, 2, 1, boundary_raw,
                             plan.line_items(2, off))
        s42, t42, (exp42, bound42, pieces42) = candidate_walks(
            plan, off, lane, 2, ml2, seg_far, scale2, prune=True)
        dist = {}
        for t in t42:
            dist[t["eliminated_by"]] = dist.get(t["eliminated_by"], 0) + 1
        surv = s42[0] if len(s42) == 1 else None
        margin_same = slack_free = False
        max_minsum = None
        if surv is not None:
            kept = prune_pieces(pieces42, surv["xy"], surv["bnd"],
                                bound42 + 2.0 * MAX_DASH_GAP)
            w2 = walk_design_path(kept, surv["xy"], surv["bnd"])
            margin_same = (w2["result"] == TRACED
                           and [(round(x, 1), round(y, 1)) for x, y in
                                w2["stroke_points"]]
                           == [(round(x, 1), round(y, 1)) for x, y in
                               surv["stroke_points"]])
            max_minsum = max(_d(surv["xy"], v) + _d(v, surv["bnd"])
                             for v in surv["stroke_points"])
            slack_free = max_minsum <= exp42 * (1.0 + DESIGN_LENGTH_REL_TOL)
        up = next((t for t in t42 if t["id"] == EXPECT_UPSTREAM_ID), {})
        g6 = (dist == EXPECT_PRUNED_42
              and surv is not None and surv["id"] == EXPECT_SURVIVOR_42
              and surv["path_len"] == EXPECT_SURVIVOR_PLEN
              and surv["path_groups"] == 1
              and surv["paths_found"] is not None
              and surv["paths_found"] >= 1
              and surv["uniqueness_universe"] == UNIVERSE_LENGTH_CORRIDOR
              and up.get("eliminated_by") == EXPECT_UPSTREAM["eliminated_by"]
              and up.get("paths_found") == EXPECT_UPSTREAM["paths_found"]
              and margin_same and slack_free)
        print(f"[m8.21] {'PASS' if g6 else 'FAIL'}  G6 corridor log42: "
              f"taxonomy {dist}; survivor "
              f"{surv['id'] if surv else None} plen "
              f"{surv['path_len'] if surv else None} "
              f"(universe {UNIVERSE_LENGTH_CORRIDOR}, bound "
              f"{round(bound42, 1)}, kept "
              f"{surv.get('pieces_kept') if surv else None}/"
              f"{len(pieces42)}); margin-stable {margin_same}; max vertex "
              f"min-sum {round(max_minsum, 1) if max_minsum else None} <= "
              f"{round(exp42 * 1.25, 1)} (slack never load-bearing)")
        ok &= g6

        # ---- G7: frame ownership (the adversarial-review law) ----
        owner = (callout_frame_owner(ladders2, surv["bnd"][0], seg_far)
                 if surv is not None else None)
        g7 = False
        frame = {}
        if surv is not None and owner is not None:
            lateral, owner_resid = owner
            sta_boundary = ladder_station(lateral, surv["bnd"][0])
            sta_installer = ladder_station(lateral, surv["xy"][0])
            plen_ft = surv["plen_raw"] / scale2
            remainder_ft = seg_far - installer[0].parent_station_ft
            frame_resid = abs(plen_ft - remainder_ft) / remainder_ft
            up_c = next((c for c in cluster_symbols(drawings2, "NEXTLINK")
                         if f"NEXTLINK@{c.x:.0f},{c.y:.0f}"
                         == EXPECT_UPSTREAM_ID), None)
            hop_ft = (_d((up_c.x, up_c.y), surv["xy"]) / scale2
                      if up_c else None)
            arc_resid = (abs((hop_ft + plen_ft) - seg_far) / seg_far
                         if hop_ft else None)
            west = [l for l in ladders2 if l is not lateral
                    and len(l.ticks) >= 2
                    and ladder_station(l, surv["xy"][0]) < 60.0]
            frame = {
                "frame_owner_law": (
                    "owner = the unique ladder with interior tick stations "
                    "that places the printed boundary (2+70) at the physical "
                    "boundary point within half its own tick step; y-band / "
                    "nearest-ladder selection FORBIDDEN (two runs' ladders "
                    "measured 5.1 pt apart in y on this sheet)"),
                "owner_boundary_residual_ft": round(owner_resid, 2),
                "rejected_ladders": [
                    {"ticks": len(l.ticks), "span": l.station_span,
                     "boundary_projection_ft":
                     round(ladder_station(l, surv["bnd"][0]), 1)}
                    for l in ladders2 if l is not lateral],
                "westward_run_zero_note": (
                    "measured context (not adjudicated): a rejected ladder "
                    "back-projects ITS OWN 0+00 to "
                    f"x~{round(_x_at_station(west[0], 0.0), 1) if west else None}"
                    " (the installer cluster) -- the printed STA 0+46=0+00 "
                    "equation plausibly marks the 526-ft westward run's "
                    "origin AT the installer structure, further "
                    "corroborating that the installer is not the eastward "
                    "270-ft run's origin"
                ) if west else None,
                "lateral_ladder_ticks": [(t.station_ft, t.x, t.y)
                                         for t in lateral.ticks],
                "boundary_station_ft": round(sta_boundary, 1),
                "installer_station_ft": round(sta_installer, 1),
                "printed_equation_parent_ft": installer[0].parent_station_ft,
                "survivor_path_ft": round(plen_ft, 2),
                "remainder_ft": remainder_ft,
                "frame_residual": round(frame_resid, 4),
                "printed_hop_note": "HH - HH = 46'",
                "drawn_hop_ft": round(hop_ft, 1) if hop_ft else None,
                "arc_total_ft": (round(hop_ft + plen_ft, 1)
                                 if hop_ft else None),
                "arc_residual": (round(arc_resid, 4)
                                 if arc_resid is not None else None),
                "verdict": INTERIOR_RESET_NOT_ORIGIN,
                "named_missing": (
                    "log42's origin is the callout-frame 0+00 structure "
                    f"(upstream HH {EXPECT_UPSTREAM_ID}, corridor verdict "
                    f"DESIGN_PATH_AMBIGUOUS with "
                    f"{EXPECT_UPSTREAM['paths_found']} complete paths -> a "
                    "strand discriminator at the origin), plus owner source "
                    "re-reads: bore_log13 block semantics (is Segment B's "
                    "0+00 the callout-frame origin or the installer reset?) "
                    "and the log41 end-digit (see "
                    "source_digit_conflict)"),
            }
            g7 = (owner_resid <= 1.0
                  and abs(sta_boundary - EXPECT_BOUNDARY_STA_FT) <= 1.0
                  and abs(sta_installer - EXPECT_INSTALLER_STA_FT) <= 1.0
                  and abs(sta_installer
                          - installer[0].parent_station_ft) <= 1.5
                  and frame_resid <= FRAME_RESIDUAL_TOL
                  and arc_resid is not None
                  and arc_resid <= ARC_RESIDUAL_TOL)
        print(f"[m8.21] {'PASS' if g7 else 'FAIL'}  G7 frame ownership: "
              f"boundary at {frame.get('boundary_station_ft')} ft (~2+70), "
              f"installer at {frame.get('installer_station_ft')} ft == "
              f"printed 0+46; survivor path {frame.get('survivor_path_ft')} "
              f"ft == footage-46 ({frame.get('remainder_ft')}) resid "
              f"{frame.get('frame_residual')}; arc 46'+path = "
              f"{frame.get('arc_total_ft')} ft vs 270 resid "
              f"{frame.get('arc_residual')} -> {INTERIOR_RESET_NOT_ORIGIN}")
        ok &= g7

        # ---- G8: log41 conflict enumeration (no preference, ever) ----
        conflict = {
            "finding": SOURCE_DIGIT_REREAD_REQUIRED,
            "bore_id": "log41",
            "conflicting_readings": [
                {"reading": "0+44", "source":
                 "bore_log41.xlsx row 2 station as digitized"},
                {"reading": "0+50", "source":
                 "bore_log41.xlsx NEEDS REVIEW note (source-flagged "
                 "alternative)"},
                {"reading": "0+46", "source":
                 "printed sheet-2 candidates: STA 0+46=0+00 equation + "
                 "HH - HH = 46' span (candidate only -- the engine never "
                 "selects)"},
            ],
            "action": "OWNER_REREAD_SOURCE_PHOTO",
            "source_photo": "2025-12-03_212755 - Jimenez",
        }
        validate_conflict_record(conflict)
        bind44 = bind_origin_by_parent_station(44.0, origins)
        bind50 = bind_origin_by_parent_station(50.0, origins)
        g8 = (bind44.result != BOUND and bind50.result != BOUND
              and b41.span_ft == 44.0)
        print(f"[m8.21] {'PASS' if g8 else 'FAIL'}  G8 log41 conflict "
              f"enumeration: 44.0/50.0 both refuse engine binding (no "
              f"tolerance bridges to printed 46); typed "
              f"{SOURCE_DIGIT_REREAD_REQUIRED}, owner re-read named")
        ok &= g8

        # ---- G9: posture ----
        lane_statuses = {S_STRUCTURE_REQUIRED, S_UNPRINTED}
        probe_classes = {SURVIVOR_IN_CORRIDOR, INTERIOR_RESET_NOT_ORIGIN,
                         SOURCE_DIGIT_REREAD_REQUIRED, ADJACENT_PRINT_CONTEXT,
                         ORIGIN_CLASS_UNMODELED, LENGTH_INFEASIBLE_CHORD}
        g9 = (not list(OUT_DIR.glob("*.png"))
              and not (probe_classes & lane_statuses))
        print(f"[m8.21] {'PASS' if g9 else 'FAIL'}  G9 posture: nothing "
              f"rendered; probe classes disjoint from lane statuses")
        ok &= g9

        for s in s42:                 # geometry stays in-memory only
            s.pop("stroke_points", None)

        report = {
            "milestone": ("truelinev2 M8.21 -- split-log parent/child + "
                          "corridor-pruned trace + frame-ownership "
                          "adjudication for log42 (proof-only; lane, census, "
                          "grades, tolerances, budget ALL unchanged; zero "
                          "strokes)"),
            "corpus_dir_used": corpus_dir, "corpus_resolution": how,
            "plan_pdf": PDF, "verdict": "PASS" if ok else "FAILURE",
            "lane_statuses": statuses,
            "printed_chain": {
                "fragments": [
                    {"from": "0+00", "to": "2+70", "ft": 270.0, "sheet": 2,
                     "class": "PORT TERMINAL TAIL",
                     "note": (chain.get("notes") or [None])[0]},
                    {"from": "2+70", "to": "2+87", "ft": 17.0, "sheet": 1,
                     "class": "PORT TERMINAL TAIL", "note": end_note},
                    {"from": "2+87", "to": "5+19", "ft": 232.0, "sheet": 1,
                     "class": "VACANT",
                     "typed": ADJACENT_PRINT_CONTEXT,
                     "claimed_by_corpus_bore": None},
                ],
                "closure": "270 + 17 == 287 == log42 span (exact)",
                "owner_519_chain": ("printed as three fragments; log42's "
                                    "bore is exactly the first two (287); "
                                    "519 is arithmetic, never printed"),
                "sheet1_claimants": sorted(sheet1_claimants),
            },
            "split_provenance": {
                "parent": "bore_log13.xlsx (absent from corpus by design; "
                          "never read)",
                "children": {"log41": "Segment A (col1)",
                             "log42": "Segment B (col2)"},
                "evidence_strength": ("WEAK -- grouping hint only, never a "
                                      "join (run-segment-hierarchy *8)"),
                "shared": {"source_photo": "2025-12-03_212755 - Jimenez",
                           "date": sorted(n41["dates"]),
                           "crew": sorted(n41["crews"]),
                           "print": sorted(n41["prints"])},
            },
            "reset_origins": {
                "sheet2": [{"source": o.source_line,
                            "parent_ft": o.parent_station_ft,
                            "type": o.structure_type,
                            "label": o.structure_label} for o in origins],
                "installer_binding": {
                    "locator_forms_bound": sorted(binds),
                    "symbol_xy": list(next(iter(sym_pts))) if sym_pts else None,
                    "label_box_words": sorted(box_words),
                    "rival_clusters": sorted(map(list, rivals)),
                },
                "second_origin_exclusion": splice_excl,
            },
            "corridor": {
                "module": "truelinev2/extract/corridor_prune.py",
                "bound_pts": round(bound42, 1),
                "expected_pts": round(exp42, 1),
                "uniqueness_universe": UNIVERSE_LENGTH_CORRIDOR,
                "certificate_note": (
                    "corridor uniqueness certifies length-admissible-capable "
                    "geometry ONLY; it is NOT an M8.18-class full-universe "
                    "certificate and Law 1 gate 1 does not accept it; any "
                    "future lane wiring requires a fresh adversarial "
                    "judgment"),
                "unpruned_authority": ("M8.20 run_shared_origin_adjudication_"
                                       "probe G5 (cross-pinned: "
                                       f"{EXPECT_UNPRUNED_M820})"),
                "log42_taxonomy": t42,
                "controls": control_rows,
            },
            "frame_adjudication": frame,
            "source_digit_conflict": conflict,
            "stale_artifact_note": (
                "data/outputs/reviewer_payload_contract.json still carries a "
                "pre-M8.14 text-era log42 PLACED_REVIEW/AUTO_EXACT_MATCH "
                "block contradicting lane truth; superseded, pending "
                "regeneration -- named follow-up, never consumed here"),
            "deferred_by_name": [
                "bore_log17 family (log43/log44): different prints (10/18), "
                "unresolved source-quality flags, print-18 adjacency to the "
                "frozen log8/log32 controls -- a separate milestone",
                "strand discriminator at the callout-frame origin "
                f"({EXPECT_UPSTREAM_ID}) -- the named log42 unlock",
                "owner re-reads: bore_log13 block semantics; log41 end digit",
            ],
        }
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[m8.21] report -> {report_path}")
    finally:
        plan.close()

    print(f"[m8.21] {'PASS' if ok else 'FAILURE'}")
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
