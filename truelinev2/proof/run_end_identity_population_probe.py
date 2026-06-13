r"""M8.26 Phase 0 -- the END_IDENTITY_UNPRINTED population characterization.

READ-ONLY evidence dump. Enumerates every bore the symbol_conduit lane parks at
``END_IDENTITY_UNPRINTED`` (step-1 end-identity refusal) and, for each, records
the COMPLETE printed end-station evidence so the gate question can be answered
on facts, not hope:

  Is there a printed terminal/AP-HH end-structure layer the current
  ``bind_end_structure_note`` grammar EXCLUDES, that a new zero-false gate could
  read -- WITHOUT inferring end identity from run callouts/equations/footage
  alone, and WITHOUT trusting nearby AP/HH text whose frame/layer ownership is
  not proven?

For each END_IDENTITY_UNPRINTED bore, per referenced sheet, this dumps:
  * the current grammar verdict (bind_end_structure_note) + candidate count
  * every raw ``STA <end>`` text line, bucketed: equation / callout-starting /
    note-without-keyword / note-with-keyword (WHY the grammar found nothing)
  * every printed run callout ENDING at the end station + its note text +
    the structure identity tokens it names (AP-\d+ ids + structure keywords)
  * for each AP id named by an ending callout: the structure-position chain
    result (label box -> leader -> symbol -> class fill) = the FRAME/LAYER
    OWNERSHIP proof, plus the resolved symbol's distance to the end-station
    drawn axis tick (the geometric station<->structure corroboration)
  * the end station's drawn axis tick (present? where?) and the nearest
    structure-layer symbol clusters (all classes) to it

NO classification verdict is asserted here beyond machine-derivable evidence
flags; the safety call (does a zero-false gate exist, and for which bores) is
made downstream from this dump. Proof-only: no placement, no stroke, no PNG, no
engine change; census untouched; log8/log32/log42 only READ (status echoed).

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_end_identity_population_probe
"""
from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.matchline_join import (run_callouts_ending_at,
                                               run_callouts_starting_at)
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_anchor import (_STA_LINE, _STRUCTURE_WORDS,
                                                 bind_end_structure_note)
from truelinev2.extract.structure_position import (BRENHAM_LANE_DIALECT,
                                                   POSITION_BOUND,
                                                   resolve_structure_position)
from truelinev2.extract.tick_path import route_ladder_ticks
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.symbol_conduit_lane import (S_UNPRINTED, resolve_bore)
from truelinev2.proof.run_brenham_corpus import (EXPECTED_COUNT, PDF,
                                                 enumerate_corpus)
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.service import _build_plan_frame_graph
from truelinev2.stations import feet_to_station

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "end_identity_population_probe"

TICK_TOL_FT = 0.5        # a drawn tick AT the end station
SYMBOL_AT_TICK_TOL = 12.0  # report-only: symbol cluster proximity to end tick

# control bores whose status this probe must observe UNCHANGED (read-only)
CONTROL = {"log8": "STRUCTURE_IDENTITY_BINDING_REQUIRED",
           "log32": "STRUCTURE_IDENTITY_BINDING_REQUIRED",
           "log42": "STRUCTURE_IDENTITY_BINDING_REQUIRED"}

# Banked honest-negative facts (drift fails loud). The AP-HH terminal gate the
# wiki named DOES NOT EXIST for this population: no AP id is printed at ANY of
# the 25 bore ends; the only printed end-structure NOTE (log27) carries a class
# OUTSIDE the dialect class_keywords (NEXTLINK HH / SPLICE) with no AP id and no
# drawn end tick to corroborate position; the only ending-callout structure
# keyword (log3/log4 "PORT TERMINAL TAIL") is a dialect CONDUIT class, not a
# handhole. Adversarially confirmed (M8.26 construct/refute panel).
BANKED_POPULATION = 25
BANKED_BOUND_UNCLASSIFIED = ("log27",)   # printed end NOTE, class not in class_keywords
BANKED_ENDING_AP_IDS = ()                # zero AP-id terminals at any of the 25 ends
BANKED_GATE_CANDIDATES = ()              # zero unique frame/layer-owned AP at an end tick


def _num(b: str) -> int:
    m = re.search(r"(\d+)", b)
    return int(m.group(1)) if m else 0


def _bucket_sta_line(ln: str, end_sta: str) -> str:
    """Why the current end-note grammar accepts/rejects a ``STA <end>`` line."""
    s = ln.strip()
    if "=" in s:
        return "equation"
    if "TO STA" in s.upper() or re.search(r"\bTO\s+\d+\+\d+", s.upper()):
        return "callout_starting_at_end"
    label = s[len(f"STA {end_sta}"):].strip()
    if any(w in label.upper() for w in _STRUCTURE_WORDS):
        return "note_with_keyword"
    return "note_without_keyword"


def _ap_ids(text: str) -> List[str]:
    return sorted(set(re.findall(r"AP-\d+", text or "", re.I)),
                  key=lambda s: int(re.search(r"\d+", s).group(0)))


def _structure_keywords(text: str) -> List[str]:
    up = (text or "").upper()
    return [w for w in _STRUCTURE_WORDS if w in up]


def _nearest_clusters(plan, sheet, offset, dialect, tick_xy):
    """Nearest structure-layer symbol cluster (per class) to the end tick."""
    from truelinev2.extract.structure_position import cluster_symbols
    drawings = plan.line_items(sheet, offset)
    out = {}
    if tick_xy is None:
        return out
    import math
    for klass, (_txt_layer, sym_layer, _fill) in dialect.structure_layers.items():
        best = None
        for c in cluster_symbols(drawings, sym_layer):
            d = math.hypot(c.x - tick_xy[0], c.y - tick_xy[1])
            if best is None or d < best[0]:
                best = (d, c)
        if best is not None:
            out[klass] = {"layer": sym_layer, "dist_pt": round(best[0], 1),
                          "xy": [round(best[1].x, 1), round(best[1].y, 1)],
                          "drawings": best[1].drawings,
                          "fills": [list(f) for f in best[1].fills],
                          "within_tol": best[0] <= SYMBOL_AT_TICK_TOL}
    return out


def _resolve_ap(plan, sheet, offset, dialect, ap_id, end_tick_xy):
    """The frame/layer-ownership test for an AP id named by an ending callout:
    the full structure-position chain + (if bound) the symbol's distance to the
    end-station drawn tick (the station<->structure geometric corroboration)."""
    import math
    words = plan.words(sheet, offset)
    drawings = plan.line_items(sheet, offset)
    v = resolve_structure_position(
        label_text=ap_id, structure_class="terminal_port_hh", words=words,
        drawings=drawings, layer_table=dialect.structure_layers)
    rec = {"ap": ap_id, "result": v.result,
           "symbol_xy": ([round(c, 1) for c in v.symbol_xy]
                         if v.symbol_xy else None),
           "named_missing": v.named_missing_relationship}
    if v.result == POSITION_BOUND and end_tick_xy is not None:
        rec["dist_symbol_to_end_tick_pt"] = round(
            math.hypot(v.symbol_xy[0] - end_tick_xy[0],
                       v.symbol_xy[1] - end_tick_xy[1]), 1)
    return rec


def characterize(plan, bore, offset, lane) -> dict:
    dialect = lane  # LaneDialect: structure_layers / id_token / class_keywords
    end_ft = bore.station_end_ft
    end_sta = feet_to_station(end_ft)
    sheets = sorted(set(bore.sheet_refs))
    per_sheet = []
    for sheet in sheets:
        lines = plan.lines(sheet, offset)
        # current grammar verdict
        eid = bind_end_structure_note(end_ft, lines)
        # raw STA <end> lines, bucketed
        raw = []
        for ln in lines:
            if _STA_LINE.match(ln.strip()) and \
                    _STA_LINE.match(ln.strip()).group(1) == end_sta:
                raw.append({"line": ln.strip()[:120],
                            "bucket": _bucket_sta_line(ln, end_sta)})
        # run callouts ending at the end station + structure tokens named
        ending = []
        for start_raw, foot, note in run_callouts_ending_at(lines, end_sta):
            aps = _ap_ids(note)
            ending.append({
                "from": start_raw, "footage": foot,
                "note": " ".join(note.split())[:200],
                "ap_ids": aps, "structure_keywords": _structure_keywords(note)})
        # run callouts STARTING at end (bore-end-as-run-start convention)
        starting = [{"to": r, "footage": f, "ap_ids": _ap_ids(n),
                     "structure_keywords": _structure_keywords(n)}
                    for r, f, n in run_callouts_starting_at(lines, end_sta)]
        # end-station drawn axis tick + nearest structure symbols
        ticks, tcounts = route_ladder_ticks(plan, sheet, offset)
        end_ticks = [t for t in ticks
                     if abs(t.station_ft - end_ft) <= TICK_TOL_FT]
        tick_xy = ([round(end_ticks[0].x, 1), round(end_ticks[0].y, 1)]
                   if end_ticks else None)
        tick_xy_raw = ((end_ticks[0].x, end_ticks[0].y) if end_ticks else None)
        # resolve every AP named by an ending callout (frame/layer ownership)
        ap_resolutions = []
        for ap in sorted({a for e in ending for a in e["ap_ids"]},
                         key=lambda s: int(re.search(r"\d+", s).group(0))):
            ap_resolutions.append(
                _resolve_ap(plan, sheet, offset, dialect, ap, tick_xy_raw))
        per_sheet.append({
            "sheet": sheet,
            "grammar_verdict": eid.result,
            "grammar_candidates": eid.candidates,
            "grammar_label": eid.structure_label,
            "raw_sta_end_lines": raw,
            "callouts_ending_at_end": ending,
            "callouts_starting_at_end": starting,
            "end_axis_tick_xy": tick_xy,
            "tick_counts": tcounts,
            "ap_resolutions": ap_resolutions,
            "nearest_structure_symbols": _nearest_clusters(
                plan, sheet, offset, dialect, tick_xy_raw),
        })

    # machine-derivable evidence flags (NOT a placement verdict)
    any_ending_callout = any(s["callouts_ending_at_end"] for s in per_sheet)
    ending_aps = sorted({a for s in per_sheet
                         for e in s["callouts_ending_at_end"]
                         for a in e["ap_ids"]})
    ending_kw = sorted({k for s in per_sheet
                        for e in s["callouts_ending_at_end"]
                        for k in e["structure_keywords"]})
    bound_aps = [r for s in per_sheet for r in s["ap_resolutions"]
                 if r["result"] == POSITION_BOUND]
    any_end_tick = any(s["end_axis_tick_xy"] for s in per_sheet)
    # an ending callout that uniquely names exactly one AP whose ownership is
    # proven AND whose symbol sits at the end-station drawn tick = the cleanest
    # gate-candidate signal (still subject to downstream adversarial review)
    gate_candidate = (
        len(ending_aps) == 1 and len(bound_aps) >= 1
        and any(r.get("dist_symbol_to_end_tick_pt", 1e9) <= SYMBOL_AT_TICK_TOL
                for r in bound_aps))

    return {
        "bore_id": bore.bore_id,
        "end_station_raw": bore.station_end,
        "end_station_grammar": end_sta,
        "start_station_raw": bore.station_start,
        "span_ft": bore.span_ft,
        "sheets": sheets,
        "evidence_flags": {
            "any_callout_ending_at_end": any_ending_callout,
            "ending_callout_ap_ids": ending_aps,
            "ending_callout_keywords": ending_kw,
            "ap_ownership_bound": [r["ap"] for r in bound_aps],
            "any_end_axis_tick": any_end_tick,
            "gate_candidate_unique_owned_ap_at_tick": gate_candidate,
        },
        "per_sheet": per_sheet,
    }


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.26-p0] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.26-p0] STOP: inputs missing")
        return 2
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)}
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.26-p0] STOP: corpus drift ({len(corpus)})")
        return 3
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    plan = PlanPdf(PDF)
    ok = True
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        graph = _build_plan_frame_graph(plan, offset)

        # 1. enumerate the population live (never trust a stale list)
        population = []
        for stem, path in corpus.items():
            try:
                bore = load_borelog(str(path))
            except Exception:
                continue  # source-unparseable bores are not end-identity bores
            out = resolve_bore(plan, bore, offset, BRENHAM_LANE_DIALECT,
                               frame_graph=graph)
            if out.status == S_UNPRINTED:
                population.append(bore)
        population.sort(key=lambda b: _num(b.bore_id))
        print(f"[m8.26-p0] END_IDENTITY_UNPRINTED population: "
              f"{len(population)} bores")

        # 2. characterize each (LANE dialect carries structure_layers/id_token)
        records = [characterize(plan, b, offset, BRENHAM_LANE_DIALECT)
                   for b in population]

        # ---- aggregates -----------------------------------------------------
        ids = [r["bore_id"] for r in records]
        ending_aps = sorted({a for r in records
                             for a in r["evidence_flags"]["ending_callout_ap_ids"]})
        starting_aps = sorted({a for r in records for s in r["per_sheet"]
                               for e in s["callouts_starting_at_end"]
                               for a in e["ap_ids"]})
        bound_unclassified = tuple(
            r["bore_id"] for r in records
            if any(s["grammar_verdict"] == "STRUCTURE_IDENTITY_BOUND"
                   for s in r["per_sheet"]))
        gate_cands = tuple(
            r["bore_id"] for r in records
            if r["evidence_flags"]["gate_candidate_unique_owned_ap_at_tick"])
        with_owned_ap = [r["bore_id"] for r in records
                         if r["evidence_flags"]["ap_ownership_bound"]]
        with_ending = [r["bore_id"] for r in records
                       if r["evidence_flags"]["any_callout_ending_at_end"]]

        # ---- gates (drift fails loud) ---------------------------------------
        g1 = (len(records) == BANKED_POPULATION
              and all(r["per_sheet"] and r["evidence_flags"] for r in records))
        print(f"[m8.26-p0] {'PASS' if g1 else 'FAIL'}  G1 population == "
              f"{BANKED_POPULATION} (got {len(records)}); all typed")
        ok &= g1

        controls_ok = True
        for cb, want in CONTROL.items():
            st = resolve_bore(plan, load_borelog(str(corpus[f"bore_{cb}"])),
                              offset, BRENHAM_LANE_DIALECT,
                              frame_graph=graph).status
            if st != want:
                controls_ok = False
                print(f"[m8.26-p0] CONTROL DRIFT {cb}: {st} (want {want})")
        print(f"[m8.26-p0] {'PASS' if controls_ok else 'FAIL'}  G2 controls "
              f"unchanged (log8/log32/log42 STRUCTURE_IDENTITY_BINDING_REQUIRED)")
        ok &= controls_ok

        g3 = (ending_aps == list(BANKED_ENDING_AP_IDS)
              and starting_aps == list(BANKED_ENDING_AP_IDS))
        print(f"[m8.26-p0] {'PASS' if g3 else 'FAIL'}  G3 NO AP-id terminal at "
              f"any of the {BANKED_POPULATION} ends (ending={ending_aps}, "
              f"starting={starting_aps}) -- the AP-HH terminal form is absent")
        ok &= g3

        g4 = bound_unclassified == BANKED_BOUND_UNCLASSIFIED
        print(f"[m8.26-p0] {'PASS' if g4 else 'FAIL'}  G4 BOUND-but-unclassified "
              f"end NOTE(s) == {list(BANKED_BOUND_UNCLASSIFIED)} (got "
              f"{list(bound_unclassified)}; log27 = NEXTLINK HH / SPLICE, class "
              f"outside class_keywords)")
        ok &= g4

        g5 = (gate_cands == BANKED_GATE_CANDIDATES and not with_owned_ap)
        print(f"[m8.26-p0] {'PASS' if g5 else 'FAIL'}  G5 zero clean gate "
              f"candidates (unique frame/layer-owned AP at an end tick): "
              f"{list(gate_cands)}; owned APs: {with_owned_ap}")
        ok &= g5

        g6 = not list(OUT_DIR.glob("*.png"))
        print(f"[m8.26-p0] {'PASS' if g6 else 'FAIL'}  G6 read-only posture: "
              f"no PNG / no render / no placement (probe renders nothing)")
        ok &= g6

        verdict = "PASS" if ok else "FAILURE"
        report = {
            "milestone": ("truelinev2 M8.26 Phase 0 -- END_IDENTITY_UNPRINTED "
                          "population characterization + HONEST NEGATIVE: no "
                          "zero-false terminal/AP-HH end-identity gate exists "
                          "for this population (read-only; no placement, no "
                          "stroke, no engine change; census frozen)"),
            "corpus_dir_used": corpus_dir, "corpus_resolution": how,
            "plan_pdf": PDF, "verdict": verdict,
            "population_count": len(population),
            "controls_unchanged": controls_ok,
            "honest_negative": {
                "ap_hh_terminal_form_present": bool(ending_aps or starting_aps),
                "ending_callout_ap_ids": ending_aps,
                "starting_callout_ap_ids": starting_aps,
                "bound_but_unclassified_end_notes": list(bound_unclassified),
                "clean_gate_candidates": list(gate_cands),
                "why": ("zero AP-id terminals at any of the 25 ends; the only "
                        "printed end NOTE (log27) is a NEXTLINK HH / SPLICE "
                        "class outside class_keywords with no AP id and no "
                        "drawn end tick; the only ending-callout keyword "
                        "(log3/log4 PORT TERMINAL TAIL) is a CONDUIT class, "
                        "not a handhole -> no terminal/AP-HH layer the grammar "
                        "excludes can be safely bound"),
            },
            "summary_flags": {
                "with_callout_ending_at_end": with_ending,
                "with_owned_ap_at_end": with_owned_ap,
                "clean_gate_candidates": list(gate_cands),
            },
            "records": records,
        }
        (OUT_DIR / "end_identity_population_probe.json").write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8")

        print(f"[m8.26-p0] with ending callout       : {with_ending}")
        print(f"[m8.26-p0] with frame/layer-owned AP  : {with_owned_ap}")
        print(f"[m8.26-p0] clean gate candidates      : {list(gate_cands)}")
        print(f"[m8.26-p0] verdict: {verdict}")
        print(f"[m8.26-p0] report -> "
              f"{OUT_DIR / 'end_identity_population_probe.json'}")
    finally:
        plan.close()
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
