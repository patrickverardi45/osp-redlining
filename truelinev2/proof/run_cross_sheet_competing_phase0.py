r"""M9.5 Phase 0 -- CROSS_SHEET_COMPETING departures: frame-graph feasibility audit.

PROOF-ONLY / READ-ONLY; no extractor/core/service shipped; zero bores moved. Decides
whether the M9.4.1/M9.4.2 FRAME-SCOPED competing-departure limitation can be SAFELY
lifted by using the SHIPPED frame-equation/matchline graph (match.frames) to enumerate
physical run-callout departures at a shared physical terminal that are drawn on a sheet
OUTSIDE the END bore's own frame -- WITHOUT proximity-only inference and WITHOUT raw
cross-sheet station-number matching.

THE QUESTION (the M9.4.1 named limitation):
  M9.4.1's competing guard counts the physical departures printed WITHIN the terminal's
  own frame (the END bore's sheets). A matchline-adjacent lateral drawn SOLELY on a far
  sheet is not enumerated, because a station token is frame-local (the M9.2 trap: the
  same local station number recurs in every sheet's stationing -- a corpus-wide scan
  would false-positive). Can the frame-equation graph identify FRAME-EQUIVALENT sheets
  strongly enough to enumerate cross-sheet departures by FRAME-PROVEN station
  translation (an exact affine offset through HIGH-confidence matchline edges), instead
  of raw-number equality or proximity?

THE SAFE MECHANISM (what "frame-proven" means here):
  match.frames builds SAFE edges ONLY from a matchline frame equation (``STA a / b`` or
  ``STA a = b``) carrying EXACTLY ONE ``SEE SHEET N`` link AND a matchline marker (HIGH
  confidence), de-conflicted by offset. translate_between_sheets() then maps a station
  (ft) from one sheet's frame into another's THROUGH that exact offset, or returns None
  (abstain -- never a raw fallback). So "sheet 24 STA 10+00" maps to "sheet 25 STA 2+58"
  (NOT "sheet 25 STA 10+00"): a repeated local station number on an unrelated frame
  translates to a DIFFERENT physical station, or does not translate at all. That is the
  M9.2-trap avoidance -- frame equivalence, never number equality, never proximity. This
  proof also composes a MULTI-HOP frame reach (a chain of HIGH-confidence safe edges,
  abstaining on any offset-inconsistent node) so the proof-of-zero covers the WHOLE
  frame-reachable component, not just directly-adjacent sheets.

THE THREE TERMINALS UNDER TEST (the M9.3.1/M9.4.1 bore-to-bore junctions):
  AP-152  log10 END -> log27 START   (RUN_ASSEMBLY_REVIEW_CANDIDATE)
  AP-117  log72 END -> log39 START   (RUN_ASSEMBLY_REVIEW_CANDIDATE)
  AP-163  log7  END -> log65 START   (JUNCTION_DROP_BRANCH, log65 prints FOR FIBER DROP)

MEASURED RESULT (this proof, live):
  * AP-152: the terminal note sits on sheet 15, which is an ISOLATED node in the safe
    frame graph (0 safe edges incident). Its only matchline equation (``STA 4+02/4+16``)
    is MULTI-linked (SEE SHEET 7 AND 14 -> MEDIUM, builds NO safe edge); both the anchor
    sheet 15 AND the departing bore log27's other sheet 16 are isolated. The frame graph
    cannot reach any far sheet for this terminal -> a NAMED sub-gap (the missing evidence
    target is a UNIQUELY-linked HIGH-confidence matchline edge connecting the AP-152
    frame neighbourhood (sheets 15/16) to any other sheet). log10's other sheet 7 has
    edges, but the node is not on sheet 7, so they are irrelevant to this terminal.
  * AP-117: the terminal note sits on sheet 24, which HAS a safe edge 24<->25 and a
    multi-hop component {25,26,27,28}. Frame-proven translation of the node
    (10+00 -> sheet 25 STA 2+58); EXACT-station cross-sheet departures = 0 across the
    WHOLE component. The only run callout within a diagnostic 5 ft window (sheet 25
    ``STA 2+61 TO STA 4+73``) begins EXACTLY at the matchline partner station (the b-side
    of the edge equation ``STA 10+03/2+61``), 3 ft past the node, and sits on sheet 25 --
    the START bore log39's OWN sheet (log39.sheet_refs = [24, 25]). It is the matchline-
    crossing continuation callout on the departing bore's own sheet, NOT a NEW foreign
    competing departure; counting it would require a forbidden 3 ft proximity tolerance.
    (NOTE: this callout is UNCOUNTED by M9.4.1 -- the in-frame guard counts 0 run callouts
    at AP-117; the competing_departures==1 comes solely from the one JUNCTION_ORIGIN
    bore. The point is only that no NEW competitor exists.)
  * AP-163: the terminal note sits on sheet 10, which HAS safe edges 10<->9/12/13 and a
    multi-hop component {7,8,9,12,13,14}. Frame-proven translations resolve; EXACT-station
    cross-sheet departures = 0 across the WHOLE component, with no near-miss anywhere.

SCOPE (named, honest boundaries):
  * Only the 3 bore-to-bore JUNCTION terminals are searched -- the domain of the M9.4.1
    competing guard. The other 4 clean END-of-feed terminals (AP-105/121/148/157 =
    log42/12/2/57) have ZERO resolved departures; a terminal whose SOLE departure were
    drawn off-frame would never form a JUNCTION_ORIGIN and so would never reach this
    proof. That off-frame-only dead-end case is a distinct, un-tested completeness
    question (recorded, gated by G13).
  * Multi-hop frame composition here is a PROOF DIAGNOSTIC (abstain-first); the shipped
    translate_between_sheets is single-hop. Both single-hop (G5) and full-component
    multi-hop (G12) enumeration yield 0 -- the zero is not a single-hop artifact.

VERDICT: SAFE_FRAME_GRAPH_EXTENSION_FEASIBLE. A safe frame-equivalence relation EXISTS
(proven for 2 of 3 terminals), and a proximity-free, raw-equality-free cross-sheet
competing-departure enumeration is therefore FEASIBLE to build (the synthetic G10 gate
proves the enumerator is NON-VACUOUS -- it WOULD catch a real cross-sheet competitor).
BUT on the current corpus it surfaces ZERO additional competing departures (single-hop
AND full multi-hop component), so it changes NONE of the three known outcomes and log65
stays a drop; and AP-152's terminal frame is unreachable. The disciplined recommendation
is to DEFER any core widen: a zero-yield, partial extension is a named, justified
capability awaiting a corpus that presents a frame-linked cross-sheet competitor -- never
a silent widen now. The M9.4.1/M9.4.2 frame-scoped competing guard stays exactly as
shipped.

VERDICT BRANCHES (the task's closed set, all reachable):
  * BLOCKED_NEEDS_SOURCE_REREAD if any junction bore carries a PDF<->KMZ / source
    contradiction (the cross-sheet question cannot be trusted until an owner reread).
  * SAFE_FRAME_GRAPH_EXTENSION_FEASIBLE if a safe frame-equivalence relation exists
    (>=1 junction terminal frame is reachable) and the enumerator is sound + non-vacuous.
  * HONEST_NEGATIVE_FRAME_GRAPH_INSUFFICIENT if NO junction terminal frame is reachable.

Exit codes: 0 PASS, 2 inputs missing, 3 corpus drift, 4 gate FAILURE.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_cross_sheet_competing_phase0
"""
from __future__ import annotations

import collections
import json
import os
import re
from collections import deque
from typing import Dict, List, Sequence, Set, Tuple

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.kmz import BRENHAM_KMZ_DIALECT, read_kmz
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.terminus_profile import BRENHAM_TERMINUS_PROFILE
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match import frames as FR
from truelinev2.match import run_assembly as RA
from truelinev2.match import terminus_attribution as TA
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_kmz_correlation_audit import resolve_kmz
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.proof.run_run_assembly_phase0 import EXPECT_CLEAN_END, EXPECT_JUNCTIONS
from truelinev2.schema.frames import FrameEdge, FrameGraph, ParseConfidence
from truelinev2.stations import feet_to_station, parse_station

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "cross_sheet_competing_phase0"

# verdict tokens (the task's closed set -- all three reachable, see verdict logic below)
SAFE_FRAME_GRAPH_EXTENSION_FEASIBLE = "SAFE_FRAME_GRAPH_EXTENSION_FEASIBLE"
HONEST_NEGATIVE_FRAME_GRAPH_INSUFFICIENT = "HONEST_NEGATIVE_FRAME_GRAPH_INSUFFICIENT"
BLOCKED_NEEDS_SOURCE_REREAD = "BLOCKED_NEEDS_SOURCE_REREAD"

# banked structural facts (drift fails loud). Anchor = the sheet the terminal note
# physically prints on; far-reach = the far sheets a SINGLE safe edge connects to it;
# component = the WHOLE multi-hop safe-edge component reachable from the anchor.
EXPECT_STRUCTURES, EXPECT_ROUTES = 576, 539
EXPECT_ANCHOR_SHEET = {152: 15, 117: 24, 163: 10}
EXPECT_FAR_REACH: Dict[int, Set[int]] = {152: set(), 117: {25}, 163: {9, 12, 13}}
EXPECT_COMPONENT_REACH: Dict[int, Set[int]] = {
    152: set(), 117: {25, 26, 27, 28}, 163: {7, 8, 9, 12, 13, 14}}
EXPECT_CANDIDATES = {("log10", "log27"), ("log72", "log39")}
EXPECT_DROPS = {("log7", "log65")}
# clean END-of-feed terminals that never form a junction (zero resolved departures) ->
# out of scope for this junction-based cross-sheet search (G13 names the boundary).
EXPECT_DEADEND_TERMINALS = {105, 121, 148, 157}
DIAG_WINDOW_FT = 5.0   # DIAGNOSTIC near-miss window (NEVER a verdict gate -- proximity is forbidden)
_COMP_TOL_FT = 2.0     # multi-hop composed-offset agreement tolerance (mirrors frames._CONFLICT_TOL_FT)


# ---- pure helpers (testable offline, no PDF) --------------------------------

def _sheet_of(frame_id) -> int:
    return int(str(frame_id).split(":")[1])


def safe_far_reach(graph: FrameGraph, anchor_sheet: int) -> Set[int]:
    """The far sheets a SINGLE safe edge connects to ``anchor_sheet`` (either
    direction). Empty == the anchor frame is isolated in the safe graph (no frame-
    proven cross-sheet reach). The shipped translate_between_sheets is single-hop."""
    out: Set[int] = set()
    for e in graph.edges:
        fs, ts = _sheet_of(e.from_frame), _sheet_of(e.to_frame)
        if fs == anchor_sheet:
            out.add(ts)
        elif ts == anchor_sheet:
            out.add(fs)
    return out


def safe_component_offsets(graph: FrameGraph, anchor_sheet: int, *,
                           tol_ft: float = _COMP_TOL_FT) -> Dict[int, float]:
    """BFS the SAFE-edge connected component from ``anchor_sheet``, composing the frame
    offset along each path. The composed offset for sheet ``s`` is defined so that
    ``station_on_s_ft == anchor_term_ft - offset[s]`` (consistent with single-hop
    translate_between_sheets). A node reachable by two paths with INCONSISTENT composed
    offsets (spread > ``tol_ft``) is AMBIGUOUS and EXCLUDED -- a multi-hop translation
    must be as safe as a single-hop one (abstain-first; never proximity, never raw
    equality). Returns {sheet: composed_offset} for unambiguous reachable sheets
    (excluding the anchor)."""
    adj: Dict[int, List[Tuple[int, float]]] = {}
    for e in graph.edges:
        u, v, off = _sheet_of(e.from_frame), _sheet_of(e.to_frame), e.offset_ft
        adj.setdefault(u, []).append((v, off))    # station_v = station_u - off -> off[v]=off[u]+off
        adj.setdefault(v, []).append((u, -off))   # station_u = station_v + off -> off[u]=off[v]-off
    offset: Dict[int, float] = {anchor_sheet: 0.0}
    ambiguous: Set[int] = set()
    q = deque([anchor_sheet])
    while q:
        n = q.popleft()
        if n in ambiguous:        # never propagate a composed offset from an ambiguous node
            continue
        for (m, delta) in adj.get(n, []):
            cand = offset[n] + delta
            if m in offset:
                if abs(offset[m] - cand) > tol_ft:
                    ambiguous.add(m)
                continue
            offset[m] = cand
            q.append(m)
    return {s: o for s, o in offset.items() if s != anchor_sheet and s not in ambiguous}


def exact_cross_sheet_departures(graph: FrameGraph, anchor_sheet: int, term_ft: float,
                                 far_lines_by_sheet: Dict[int, Sequence[str]],
                                 profile) -> List[RA.Departure]:
    """SINGLE-HOP cross-sheet run-callout departures at the terminal node, enumerated by
    EXACT FRAME-PROVEN station translation (no proximity, no raw-number equality): for
    each far sheet, translate the node (anchor frame -> far frame) through a SAFE edge; if
    it translates, enumerate the shipped run_callout_departures at the EXACT translated
    station. A sheet with no safe edge translates to None and is skipped (abstain)."""
    out: List[RA.Departure] = []
    for far, lines in far_lines_by_sheet.items():
        far_ft = FR.translate_between_sheets(graph, anchor_sheet, far, term_ft)
        if far_ft is None or far_ft < 0:
            continue
        out.extend(RA.run_callout_departures({far: lines}, feet_to_station(far_ft), profile))
    return out


def exact_cross_sheet_departures_component(graph: FrameGraph, anchor_sheet: int,
                                           term_ft: float,
                                           lines_by_sheet: Dict[int, Sequence[str]],
                                           profile) -> Tuple[List[RA.Departure], Dict[int, float]]:
    """MULTI-HOP variant over the WHOLE safe-edge component (safe_component_offsets):
    translate the node into EVERY unambiguously-reachable far frame and enumerate the
    EXACT-station run-callout departures there. Returns (departures, component_offsets).
    Equally zero-false as the single-hop form -- each composed offset is a chain of
    HIGH-confidence safe edges, abstaining on any offset-inconsistent node."""
    comp = safe_component_offsets(graph, anchor_sheet)
    out: List[RA.Departure] = []
    for far, off in sorted(comp.items()):
        lines = lines_by_sheet.get(far)
        if lines is None:
            continue
        far_ft = term_ft - off
        if far_ft < 0:
            continue
        out.extend(RA.run_callout_departures({far: lines}, feet_to_station(far_ft), profile))
    return out, comp


def edge_far_partner_stations(graph: FrameGraph, anchor_sheet: int, far_sheet: int) -> Set[str]:
    """The FAR-side raw station(s) of the safe matchline edge(s) directly connecting
    ``anchor_sheet`` and ``far_sheet`` -- i.e. the matchline boundary station ON the far
    sheet. A callout printed AT one of these is the matchline-crossing continuation, not
    a node-anchored departure."""
    out: Set[str] = set()
    for e in graph.edges:
        fs, ts = _sheet_of(e.from_frame), _sheet_of(e.to_frame)
        if fs == anchor_sheet and ts == far_sheet and e.b_raw:
            out.add(e.b_raw)
        elif ts == anchor_sheet and fs == far_sheet and e.a_raw:
            out.add(e.a_raw)
    return out


def near_callouts_diag(graph: FrameGraph, anchor_sheet: int, term_ft: float,
                       far_lines_by_sheet: Dict[int, Sequence[str]], profile,
                       window_ft: float = DIAG_WINDOW_FT) -> List[dict]:
    """DIAGNOSTIC-ONLY (never a verdict gate): every far-sheet run callout whose station
    translates BACK to within ``window_ft`` of the node. Used only to PROVE the
    EXACT-zero is not a rounding artifact and to CHARACTERISE any matchline-boundary
    callout (``at_matchline_boundary`` == it begins exactly at the safe edge's far-side
    station). Proximity is forbidden, so this never counts toward a competing departure."""
    sta_re = re.compile(profile.station_line_re)
    out: List[dict] = []
    for far, lines in far_lines_by_sheet.items():
        partners = edge_far_partner_stations(graph, anchor_sheet, far)
        for ln in lines:
            s = ln.strip()
            m = sta_re.match(s)
            if not m or profile.run_callout_marker not in s:
                continue
            back = FR.translate_between_sheets(graph, far, anchor_sheet, parse_station(m.group(1)))
            if back is None:
                continue
            if abs(back - term_ft) <= window_ft:
                out.append({"far_sheet": far, "far_station": m.group(1),
                            "back_ft": back, "delta_ft": round(abs(back - term_ft), 2),
                            "at_matchline_boundary": m.group(1) in partners, "line": s})
    return out


def anchor_frame_equations(plan, anchor_sheet: int, offset: int) -> List[dict]:
    """The raw frame equations parsed on the anchor sheet's PDF page (read-only) -- to
    GROUND the sub-gap narrative (e.g. an equation suppressed for being MULTI-linked, not
    absent). page_index == sheet + offset - 1 (inverse of frames.frame_for_sheet)."""
    idx = anchor_sheet + offset - 1
    if idx < 0 or idx >= plan.page_count:
        return []
    text = " ".join(ln for ln in plan.text_by_index(idx).splitlines() if ln.strip())
    return [{"source": eq.source, "confidence": str(eq.confidence),
             "kind": str(eq.kind), "linked_frames": eq.linked_frames,
             "has_matchline": eq.has_matchline} for eq in FR.parse_frame_equations(text)]


def decide_verdict(blocked: bool, mechanism_safe: bool) -> str:
    """The verdict token from the measured booleans -- all three branches reachable:
    BLOCKED if a junction bore carries a contradiction (cannot trust the cross-sheet
    question until an owner reread); else FEASIBLE if a safe frame-equivalence relation
    exists (>=1 junction terminal frame reachable + sound non-vacuous enumerator); else
    HONEST_NEGATIVE if NO terminal frame is reachable."""
    if blocked:
        return BLOCKED_NEEDS_SOURCE_REREAD
    if mechanism_safe:
        return SAFE_FRAME_GRAPH_EXTENSION_FEASIBLE
    return HONEST_NEGATIVE_FRAME_GRAPH_INSUFFICIENT


def _synthetic_enumerator_check(profile) -> dict:
    """NON-VACUOUS proof that the enumerator is real: a 1-edge graph (sheet 900 <-> 901,
    offset 742) + a far callout at the EXACT translated node station -> 1 departure; a
    decoy at the SAME RAW node station -> 0 (proves it is NOT raw-number equality); a
    near-miss 3 ft off -> 0 (no proximity); an isolated anchor -> 0 (abstain)."""
    g = FrameGraph(edges=[FrameEdge(from_frame=FR.frame_for_sheet(900),
                                    to_frame=FR.frame_for_sheet(901),
                                    offset_ft=742.0, confidence=ParseConfidence.HIGH)])
    node_ft = 1000.0
    far_sta = feet_to_station(node_ft - 742.0)            # 258.0 -> "2+58"
    raw_sta = feet_to_station(node_ft)                    # "10+00" (the raw decoy)
    miss_sta = feet_to_station(node_ft - 742.0 + 3.0)     # 3 ft off the translated node
    hit = exact_cross_sheet_departures(
        g, 900, node_ft, {901: [f"STA {far_sta} TO STA 4+00 - 1.25\" HDPE"]}, profile)
    decoy = exact_cross_sheet_departures(
        g, 900, node_ft, {901: [f"STA {raw_sta} TO STA 4+00 - 1.25\" HDPE"]}, profile)
    miss = exact_cross_sheet_departures(
        g, 900, node_ft, {901: [f"STA {miss_sta} TO STA 4+00 - 1.25\" HDPE"]}, profile)
    isolated = exact_cross_sheet_departures(
        g, 555, node_ft, {901: [f"STA {far_sta} TO STA 4+00 - 1.25\" HDPE"]}, profile)
    return {"positive_hit": len(hit), "raw_equality_decoy": len(decoy),
            "near_miss_3ft": len(miss), "isolated_anchor": len(isolated),
            "translated_station": far_sta, "raw_decoy_station": raw_sta}


def main() -> int:
    kmz_path, kmz_how = resolve_kmz()
    corpus_dir, how = resolve_corpus()
    print(f"[m9.5] kmz   : {kmz_path}  ({kmz_how})")
    print(f"[m9.5] corpus: {corpus_dir}  ({how})")
    if not os.path.isfile(kmz_path) or not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m9.5] STOP: inputs missing")
        return 2
    paths = enumerate_corpus(corpus_dir)
    if len(paths) != EXPECTED_COUNT:
        print(f"[m9.5] STOP: corpus drift ({len(paths)})")
        return 3
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = True

    model = read_kmz(kmz_path, BRENHAM_KMZ_DIALECT)
    plan = PlanPdf(PDF)
    results: List[TA.BoreTerminusResult] = []
    lines_by_id: Dict[str, dict] = {}
    bore_sheets: Dict[str, list] = {}
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        for p in paths:
            try:
                bore = load_borelog(str(p))
            except Exception:
                continue
            refs = sorted(set(bore.sheet_refs))
            lbs = {s: plan.lines(s, offset) for s in refs}
            lines_by_id[bore.bore_id] = lbs
            bore_sheets[bore.bore_id] = refs
            results.append(TA.attribute_bore(
                bore.bore_id, feet_to_station(bore.station_start_ft),
                feet_to_station(bore.station_end_ft), lbs, BRENHAM_TERMINUS_PROFILE,
                kmz_model=model, source_contradiction=(bore.bore_id == "log44")))

        by_id = {r.bore_id: r for r in results}
        junctions = TA.resolve_junctions(results)
        graph = FR._build_plan_frame_graph(plan, offset)

        # per-terminal live measurement (single-hop AND full multi-hop component)
        per_terminal: Dict[int, dict] = {}
        for j in junctions:
            ap = j["terminal_ap"]; end_bore = j["end_bore_owner"]; start_bore = j["start_bore"]
            term_sta = by_id[end_bore].end_station
            term_ft = parse_station(term_sta)
            note, _ = TA.detect_endpoint_note(lines_by_id[end_bore], term_sta, BRENHAM_TERMINUS_PROFILE)
            anchor = note.sheet if note else None
            reach = safe_far_reach(graph, anchor) if anchor is not None else set()
            comp = safe_component_offsets(graph, anchor) if anchor is not None else {}
            far_lines = {f: plan.lines(f, offset) for f in sorted(reach)}
            comp_lines = {f: plan.lines(f, offset) for f in sorted(comp)}
            exact = exact_cross_sheet_departures(graph, anchor, term_ft, far_lines,
                                                 BRENHAM_TERMINUS_PROFILE) if anchor is not None else []
            comp_exact, _ = exact_cross_sheet_departures_component(
                graph, anchor, term_ft, comp_lines, BRENHAM_TERMINUS_PROFILE) if anchor is not None else ([], {})
            near = near_callouts_diag(graph, anchor, term_ft, comp_lines,
                                      BRENHAM_TERMINUS_PROFILE) if anchor is not None else []
            start_refs = set(bore_sheets.get(start_bore, []))
            per_terminal[ap] = {
                "end_bore": end_bore, "start_bore": start_bore, "terminal_station": term_sta,
                "anchor_sheet": anchor, "safe_far_reach": sorted(reach),
                "component_reach": sorted(comp),
                "exact_cross_sheet_departures": [d.to_dict() for d in exact],
                "exact_cross_sheet_departures_component": [d.to_dict() for d in comp_exact],
                "near_callouts_diag": near,
                "near_all_on_start_bore_sheets": all(n["far_sheet"] in start_refs for n in near),
                "near_all_at_matchline_boundary": all(n["at_matchline_boundary"] for n in near),
                "start_bore_sheets": sorted(start_refs),
                "anchor_frame_equations": anchor_frame_equations(plan, anchor, offset) if anchor is not None else [],
            }

        # the shipped extractor -- outcomes must be UNCHANGED
        evidence = RA.extract_run_assembly(results, lines_by_id, BRENHAM_TERMINUS_PROFILE)
        ev_by_pair = {(e.end_bore, e.start_bore): e for e in evidence}
        candidates = {(e.end_bore, e.start_bore) for e in evidence if e.is_continuation_candidate}
        drops = {(e.end_bore, e.start_bore) for e in evidence if e.is_drop_branch}
        disp_census = collections.Counter(e.disposition for e in evidence)

        # ---- GATES -----------------------------------------------------------
        got_junctions = {(j["start_bore"], j["terminal_ap"], j["end_bore_owner"]) for j in junctions}
        g1 = (len(model.structures) == EXPECT_STRUCTURES and len(model.routes) == EXPECT_ROUTES
              and got_junctions == EXPECT_JUNCTIONS and len(graph.edges) > 0)
        print(f"[m9.5] {'PASS' if g1 else 'FAIL'}  G1 inputs + 3 junctions + safe graph built "
              f"({len(graph.edges)} safe edges, {len(graph.conflicts)} conflicts)")
        ok &= g1

        got_anchor = {ap: per_terminal[ap]["anchor_sheet"] for ap in per_terminal}
        g2 = got_anchor == EXPECT_ANCHOR_SHEET
        print(f"[m9.5] {'PASS' if g2 else 'FAIL'}  G2 terminal-note anchor sheets {got_anchor} "
              f"(derived from the note frame, not assumed)")
        ok &= g2

        got_reach = {ap: set(per_terminal[ap]["safe_far_reach"]) for ap in per_terminal}
        got_comp = {ap: set(per_terminal[ap]["component_reach"]) for ap in per_terminal}
        g3 = got_reach == EXPECT_FAR_REACH and got_comp == EXPECT_COMPONENT_REACH
        print(f"[m9.5] {'PASS' if g3 else 'FAIL'}  G3 frame-evidence map: single-hop "
              f"{ {k: sorted(v) for k, v in sorted(got_reach.items())} } | multi-hop component "
              f"{ {k: sorted(v) for k, v in sorted(got_comp.items())} }")
        ok &= g3

        # G4: frame-PROVEN, not raw-number equality, and abstain-first on no edge.
        t117 = FR.translate_between_sheets(graph, 24, 25, 1000.0)   # node 10+00 -> sheet 25
        t163 = FR.translate_between_sheets(graph, 10, 9, 451.0)     # node 4+51  -> sheet 9
        t152 = FR.translate_between_sheets(graph, 15, 25, 730.0)    # isolated anchor -> None
        g4 = (t117 is not None and feet_to_station(t117) != "10+00"
              and t163 is not None and feet_to_station(t163) != "4+51"
              and t152 is None)
        print(f"[m9.5] {'PASS' if g4 else 'FAIL'}  G4 frame-proven (not raw equality): "
              f"AP-117 10+00->{feet_to_station(t117) if t117 is not None else None}, "
              f"AP-163 4+51->{feet_to_station(t163) if t163 is not None else None}; "
              f"isolated sheet 15 -> {t152} (abstain, never raw fallback)")
        ok &= g4

        g5 = all(not per_terminal[ap]["exact_cross_sheet_departures"] for ap in per_terminal)
        print(f"[m9.5] {'PASS' if g5 else 'FAIL'}  G5 EXACT single-hop cross-sheet departures "
              f"= 0 at all 3 terminals: "
              f"{ {ap: len(per_terminal[ap]['exact_cross_sheet_departures']) for ap in sorted(per_terminal)} }")
        ok &= g5

        # G6: any diagnostic near-miss callout (a) lies on the START bore's OWN sheet AND
        # (b) begins EXACTLY at the matchline partner station -> it is the matchline-
        # crossing continuation on the departing bore's own sheet, never a NEW foreign
        # competitor (counting it would need a forbidden proximity tolerance).
        g6 = all(per_terminal[ap]["near_all_on_start_bore_sheets"]
                 and per_terminal[ap]["near_all_at_matchline_boundary"] for ap in per_terminal)
        near_summary = {ap: per_terminal[ap]["near_callouts_diag"] for ap in sorted(per_terminal)
                        if per_terminal[ap]["near_callouts_diag"]}
        print(f"[m9.5] {'PASS' if g6 else 'FAIL'}  G6 every diagnostic near-miss is the matchline-"
              f"crossing continuation on the START bore's own sheet (not a competitor): {near_summary or 'none'}")
        ok &= g6

        # G7: AP-152 frame-insufficiency NAMED + GROUNDED (isolated terminal frame = the
        # sub-gap; its only matchline equation is MULTI-linked -> MEDIUM, builds no edge).
        eqs152 = per_terminal[152]["anchor_frame_equations"]
        multilinked = [e for e in eqs152 if len(e["linked_frames"]) >= 2]
        log27_refs = set(bore_sheets.get("log27", []))
        sheet16_isolated = safe_far_reach(graph, 16) == set()
        g7 = (per_terminal[152]["safe_far_reach"] == [] and per_terminal[152]["component_reach"] == []
              and per_terminal[152]["anchor_sheet"] == 15 and multilinked and sheet16_isolated
              and 16 in log27_refs)
        print(f"[m9.5] {'PASS' if g7 else 'FAIL'}  G7 AP-152 sub-gap: sheet 15 isolated, its only "
              f"matchline eq multi-linked {[e['source'] for e in multilinked]} (MEDIUM, no edge); "
              f"departing log27's sheet 16 also isolated -> target = a UNIQUELY-linked HIGH edge "
              f"on sheets 15/16")
        ok &= g7

        # G8: log65 stays a drop -> non-promotable (independent of cross-sheet analysis).
        dep65 = RA.departure_run_class(lines_by_id["log65"], by_id["log65"].start_station,
                                       BRENHAM_TERMINUS_PROFILE)
        g8 = (dep65 == RA.DEP_DROP and ev_by_pair[("log7", "log65")].disposition == RA.JUNCTION_DROP_BRANCH)
        print(f"[m9.5] {'PASS' if g8 else 'FAIL'}  G8 log65 departure_run_class={dep65} -> "
              f"JUNCTION_DROP_BRANCH (FOR FIBER DROP unaffected by cross-sheet analysis)")
        ok &= g8

        # G9: the 3 known outcomes are UNCHANGED through the shipped extractor.
        g9 = (candidates == EXPECT_CANDIDATES and drops == EXPECT_DROPS
              and dict(disp_census) == {RA.RUN_ASSEMBLY_REVIEW_CANDIDATE: 2, RA.JUNCTION_DROP_BRANCH: 1}
              and all(e.competing_departures == 1 for e in evidence))
        print(f"[m9.5] {'PASS' if g9 else 'FAIL'}  G9 outcomes UNCHANGED: 2 candidates + 1 drop, "
              f"competing_departures==1 for all: {dict(sorted(disp_census.items()))}")
        ok &= g9

        # G10: the enumerator is NON-VACUOUS (a synthetic real cross-sheet competitor IS
        # caught; the raw-equality decoy + 3 ft near-miss + isolated anchor all -> 0).
        syn = _synthetic_enumerator_check(BRENHAM_TERMINUS_PROFILE)
        g10 = (syn["positive_hit"] == 1 and syn["raw_equality_decoy"] == 0
               and syn["near_miss_3ft"] == 0 and syn["isolated_anchor"] == 0)
        print(f"[m9.5] {'PASS' if g10 else 'FAIL'}  G10 enumerator non-vacuous: synthetic "
              f"positive={syn['positive_hit']}, raw-decoy={syn['raw_equality_decoy']}, "
              f"near-miss={syn['near_miss_3ft']}, isolated={syn['isolated_anchor']}")
        ok &= g10

        # G11: read-only posture -- no PNG; this proof modifies no core (it imports
        # run_assembly/terminus/frames read-only and invokes NO placement path).
        g11 = not list(OUT_DIR.glob("*.png"))
        print(f"[m9.5] {'PASS' if g11 else 'FAIL'}  G11 read-only: no PNG under OUT_DIR; "
              f"proof composes the SHIPPED frame graph + run-assembly facts, places nothing")
        ok &= g11

        # G12: the zero is robust to FULL multi-hop reach (not a single-hop artifact) --
        # EXACT departures = 0 over the WHOLE safe-edge component at every terminal.
        g12 = all(not per_terminal[ap]["exact_cross_sheet_departures_component"] for ap in per_terminal)
        print(f"[m9.5] {'PASS' if g12 else 'FAIL'}  G12 EXACT multi-hop component cross-sheet "
              f"departures = 0 at all 3 terminals: "
              f"{ {ap: len(per_terminal[ap]['exact_cross_sheet_departures_component']) for ap in sorted(per_terminal)} }")
        ok &= g12

        # G13: scope boundary NAMED -- the 4 clean END-of-feed terminals with no junction
        # (AP-105/121/148/157) are out of scope (off-frame-only departures there would
        # never form a JUNCTION_ORIGIN, so never reach this junction-based search).
        junction_terminals = {j["terminal_ap"] for j in junctions}
        clean_end_terminals = set(EXPECT_CLEAN_END.values())
        deadend = clean_end_terminals - junction_terminals
        g13 = deadend == EXPECT_DEADEND_TERMINALS
        print(f"[m9.5] {'PASS' if g13 else 'FAIL'}  G13 scope boundary: junction terminals "
              f"{sorted(junction_terminals)}; dead-end clean-END terminals {sorted(deadend)} "
              f"(off-frame-only departures there are a distinct, un-tested question)")
        ok &= g13

        # ---- verdict (DERIVED from the gates, never hardcoded) ----------------
        junction_bores = {b for j in junctions for b in (j["start_bore"], j["end_bore_owner"]) if b}
        blocked = any(by_id[b].disposition in (TA.PDF_KMZ_CONTRADICTION, TA.SOURCE_CONTRADICTION)
                      for b in junction_bores if b in by_id)
        mechanism_safe = any(per_terminal[ap]["safe_far_reach"] for ap in per_terminal) and g4 and g10
        zero_yield = g5 and g12
        outcomes_unchanged = g9
        log65_drop = g8
        verdict = decide_verdict(blocked, mechanism_safe)
        g14 = (verdict == SAFE_FRAME_GRAPH_EXTENSION_FEASIBLE and not blocked
               and zero_yield and outcomes_unchanged and log65_drop)
        print(f"[m9.5] {'PASS' if g14 else 'FAIL'}  G14 verdict={verdict} "
              f"(blocked={blocked}, mechanism_safe={mechanism_safe}, zero_yield={zero_yield}, "
              f"outcomes_unchanged={outcomes_unchanged}, log65_drop={log65_drop})")
        ok &= g14
    finally:
        plan.close()

    report = {
        "milestone": ("truelinev2 M9.5 Phase 0 -- CROSS_SHEET_COMPETING frame-graph "
                      "feasibility (proof-only/read-only; no core/service shipped; zero bores moved)"),
        "kmz_path": kmz_path, "corpus_dir": corpus_dir, "plan_pdf": PDF,
        "verdict": verdict if ok else "FAILURE",
        "feasibility_verdict": verdict,
        "blocked_by_source_contradiction": blocked,
        "safe_frame_graph": {"safe_edges": len(graph.edges), "conflicts": len(graph.conflicts),
                             "edges": [{"from": _sheet_of(e.from_frame), "to": _sheet_of(e.to_frame),
                                        "offset_ft": e.offset_ft, "confidence": str(e.confidence),
                                        "source": e.source} for e in graph.edges]},
        "per_terminal": {str(k): v for k, v in sorted(per_terminal.items())},
        "synthetic_non_vacuous_check": syn,
        "outcomes_unchanged": outcomes_unchanged,
        "log65_stays_drop": log65_drop,
        "zero_cross_sheet_yield_single_hop_and_multi_hop": zero_yield,
        "ap152_sub_gap": ("sheet 15's only matchline equation (STA 4+02/4+16) is MULTI-linked "
                          "(SEE SHEET 7 AND 14 -> MEDIUM, builds NO safe edge); both the anchor "
                          "sheet 15 and the departing bore log27's other sheet 16 are isolated in "
                          "the safe graph. Missing evidence target = a UNIQUELY-linked HIGH-"
                          "confidence matchline edge connecting the AP-152 frame neighbourhood "
                          "(sheets 15/16) to any other sheet. (log10's other sheet 7 has edges, but "
                          "the node is not on sheet 7.)"),
        "ap117_near_miss": ("the lone diagnostic near-miss (sheet 25 'STA 2+61 TO STA 4+73') begins "
                            "EXACTLY at the matchline partner station 2+61 (the b-side of edge "
                            "'STA 10+03/2+61'), 3 ft past the node, on the START bore log39's own "
                            "sheet [24,25] -- the matchline-crossing continuation, UNCOUNTED by the "
                            "M9.4.1 in-frame guard and never a NEW foreign competitor; counting it "
                            "would require a forbidden 3 ft proximity tolerance."),
        "deadend_clean_end_terminals_out_of_scope": sorted(deadend),
        "multi_hop_scope": ("the proof enumerates BOTH single-hop (G5) and the full multi-hop safe-"
                            "edge component (G12, abstain-first composed offsets); both yield 0. The "
                            "shipped translate_between_sheets is single-hop; multi-hop here is a proof "
                            "diagnostic, not a shipped capability."),
        "recommendation": (
            "DEFER any core widen. The frame-graph cross-sheet competing-departure mechanism is "
            "SAFE and feasible (frame-proven translation, never proximity, never raw equality; the "
            "enumerator is non-vacuous), but it surfaces ZERO additional departures on the current "
            "corpus (single-hop AND full multi-hop component) and changes none of the three outcomes; "
            "AP-152's terminal frame is unreachable. A zero-yield, partial extension is a named, "
            "justified capability awaiting a corpus that presents a frame-linked cross-sheet "
            "competitor -- never a silent widen now. The M9.4.1/M9.4.2 frame-scoped competing guard "
            "stays exactly as shipped."),
        "core_changed": False, "service_changed": False, "bores_moved": 0,
        "read_only": True, "auto": False, "geometry": None,
    }
    (OUT_DIR / "cross_sheet_competing_phase0.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")

    print(f"\n[m9.5] verdict: {report['verdict']}")
    print(f"[m9.5] single-hop far-reach: "
          f"{ {ap: per_terminal[ap]['safe_far_reach'] for ap in sorted(per_terminal)} }")
    print(f"[m9.5] multi-hop component:  "
          f"{ {ap: per_terminal[ap]['component_reach'] for ap in sorted(per_terminal)} }")
    print(f"[m9.5] exact cross-sheet departures (single/multi): "
          f"{ {ap: (len(per_terminal[ap]['exact_cross_sheet_departures']), len(per_terminal[ap]['exact_cross_sheet_departures_component'])) for ap in sorted(per_terminal)} }")
    print(f"[m9.5] report -> {OUT_DIR / 'cross_sheet_competing_phase0.json'}")
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
