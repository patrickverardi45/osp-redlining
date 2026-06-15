r"""OWNER-PACKET-2 -- log64 sheet-21 SOURCE BIND slice (PROOF ONLY; no render).

After 47f36b1 encoded log64's endpoint-anchor IDENTITY, this binds that identity to REAL sheet-21
PDF/CAD source with the SAME primitives log53 used (printed labels -> label box -> leader ->
modeled symbol; modeled conduit chain) -- never screenshot pixels, never invented coordinates,
never a fallback/nearest snap. It renders nothing, draws no stroke, writes no PNG.

What it proves on sheet 21 (single sheet; no cross-sheet solving):
  1. START installer HH binds: the owner reset token 'STA 3+69 = 0+00' (label '3+69=0+00') ->
     INSTALLER HH - TEXT label box -> leader -> NEXTLINK symbol (red installer-HH fill);
  2. END flower pot binds: label '1+00' + context ('FLOWER','POT') -> FLOWER POT - TEXT box ->
     leader -> FLOWER POT symbol (black flower-pot fill);
  3. the owner 'STA 0+00 TO STA 1+00 ... DIR. BORE (100')' callout is present + unique;
  4. a MODELED base conduit chain (BORE - VACANT PIPE / BORE - PORT) is graph-connected to BOTH
     bound symbols AND forms a CONTINUOUS direct corridor between them (every consecutive dash gap
     <= MAX_DASH_GAP) -- a source-backed route, no lateral layer needed, no invented vertex.

All endpoint coordinates are produced by the EXISTING extractor (resolve_structure_position); this
slice synthesizes none. Census stays frozen (no artifact change; flag-OFF 31/6/1/17/3, flag-ON
22/1/4). A render is the separately-authorized next step, NOT done here.

Proof-only; the JSON report is written under the gitignored data/outputs path.
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log64_sheet21_source_bind_slice
"""
from __future__ import annotations

import json
import os
import re

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.conduit_topology import (
    MAX_DASH_GAP,
    connected_chain,
    dash_endpoints,
    symbol_footprint,
)
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import (
    BRENHAM_CONDUIT_LAYERS,
    BRENHAM_STRUCTURE_LAYERS,
    POSITION_BOUND,
    resolve_structure_position,
)
from truelinev2.ingest.manual_adjudication import (
    activation_summary,
    apply_adjudications,
    load_adjudication,
    parent_run_duplicate_check,
)
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log64_sheet21_source_bind_slice"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
SHEET = 21
INSTALLER_SYMBOL_LAYER = "NEXTLINK"   # installer_hh shares the NEXTLINK symbol layer (dialect)
CORRIDOR_HALF = 40.0                   # corridor band half-width about the start->end centerline
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
# owner callout grammar (tolerant of the extractor joining 'STA1+00'); footage = the 100' bore
_SEG_RE = re.compile(r"0\+00\s*TO\s*(?:STA\s*)?1\+00", re.I)
_FOOTAGE_RE = re.compile(r"DIR\.?\s*BORE\s*\(100'\)", re.I)

R_CONFIRMED = "LOG64_SHEET21_SOURCE_BIND_CONFIRMED"
R_PARTIAL = "LOG64_PARTIAL_SOURCE_BIND_CONFIRMED"
B_START_LABEL = "BLOCKED_LOG64_START_LABEL_NOT_FOUND"
B_START_SYMBOL = "BLOCKED_LOG64_START_SYMBOL_NOT_FOUND"
B_END_LABEL = "BLOCKED_LOG64_END_LABEL_NOT_FOUND"
B_END_SYMBOL = "BLOCKED_LOG64_END_SYMBOL_NOT_FOUND"
B_CALLOUT_NOT_FOUND = "BLOCKED_LOG64_CALLOUT_NOT_FOUND"
B_CALLOUT_AMBIGUOUS = "BLOCKED_LOG64_CALLOUT_AMBIGUOUS"
B_CONDUIT_SEED = "BLOCKED_LOG64_CONDUIT_SEED_NOT_FOUND"
B_ROUTE = "BLOCKED_LOG64_ROUTE_NOT_SOURCE_BACKED"
B_AMBIGUOUS = "BLOCKED_LOG64_SOURCE_BIND_AMBIGUOUS"
ALLOWED = {R_CONFIRMED, R_PARTIAL, B_START_LABEL, B_START_SYMBOL, B_END_LABEL, B_END_SYMBOL,
           B_CALLOUT_NOT_FOUND, B_CALLOUT_AMBIGUOUS, B_CONDUIT_SEED, B_ROUTE, B_AMBIGUOUS}


def start_label_text(start_anchor: dict) -> str:
    """The bindable START label is the owner reset token '<station>=0+00' (log64's start is a
    STATION_RESET_SEGMENT_BOUNDARY at the installer HH; owner_note_text records 'STA 3+69 = 0+00').
    Derived from the encoded anchor -- never invented."""
    return f"{start_anchor.get('station')}=0+00"


def corridor_band(chain_eps, s_xy, e_xy, half: float = CORRIDOR_HALF):
    """Sorted unique dash-endpoint y's lying in the direct start->end corridor band (x within
    ``half`` of the start/end centerline, y between the endpoints). Pure."""
    xc = (s_xy[0] + e_xy[0]) / 2.0
    ylo, yhi = min(s_xy[1], e_xy[1]), max(s_xy[1], e_xy[1])
    ys = sorted({round(p[1], 2) for p in chain_eps
                 if abs(p[0] - xc) <= half and (ylo - 5) <= p[1] <= (yhi + 5)})
    return ys, ylo, yhi


def corridor_is_continuous(band_ys, ylo: float, yhi: float, max_gap: float = MAX_DASH_GAP) -> bool:
    """A direct corridor is source-backed when the band reaches both endpoints and no consecutive
    dash gap exceeds ``max_gap`` (the same dash-chain law used elsewhere). Pure."""
    if not band_ys:
        return False
    if min(band_ys) > ylo + max_gap or max(band_ys) < yhi - max_gap:
        return False
    return all((band_ys[i + 1] - band_ys[i]) <= max_gap for i in range(len(band_ys) - 1))


def _bind_blocker(result: str, label_b: str, symbol_b: str) -> str:
    return symbol_b if "SYMBOL" in result else label_b


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()  # no render/stroke lane: a PNG must never exist

    doc = load_adjudication()
    rec = {r["log_id"]: r for r in doc["logs"]}
    ea = (rec.get("log64") or {}).get("endpoint_anchors") or {}
    start_a, end_a = ea.get("start") or {}, ea.get("end") or {}
    gates, ev = [], {"sheet": SHEET}

    # ---- frozen ENGINE census (this slice changes no artifact) --------------------
    if TRUTH.is_file():
        truth = json.loads(TRUTH.read_text(encoding="utf-8"))
        baseline = {r["bore_id"]: dict(r) for r in truth["rows"]}
        off_rows = apply_adjudications(baseline, enabled=False)
        on_rows = apply_adjudications(baseline, enabled=True, doc=doc)
        summ = activation_summary(on_rows)

        def buckets(rows):
            c = {}
            for r in rows.values():
                c[r["completion_bucket"]] = c.get(r["completion_bucket"], 0) + 1
            return c
        gates.append(("G1 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                      off_rows is baseline and buckets(off_rows) == FROZEN_BUCKETS
                      and summ["manual_review_drawable"] == 22
                      and summ["manual_source_verification"] == 1 and summ["manual_abstain"] == 4
                      and on_rows["log44"]["adjudication"]["drawable_status"] == "non_drawable"
                      and all(on_rows[l]["adjudication"]["drawable_status"] == "abstain" for l in ABSTAIN_4)
                      and not parent_run_duplicate_check(doc), None))
    else:
        gates.append(("G1 truth table present (census-safety baseline)", False, str(TRUTH)))

    # ---- consume the encoded identity (47f36b1) ----------------------------------
    gates.append(("G2 log64 encoded anchors consumed (installer_hh @3+69 -> flower_pot @1+00)",
                  start_a.get("structure_class") == "installer_hh" and start_a.get("station") == "3+69"
                  and end_a.get("structure_class") == "flower_pot" and end_a.get("station") == "1+00",
                  {"start": start_a.get("station"), "end": end_a.get("station")}))

    result = B_ROUTE
    if not os.path.isfile(PDF):
        gates.append(("G3 plan PDF present", False, f"missing {PDF}"))
        return _emit(gates, B_ROUTE, ev)
    corpus_dir, _ = resolve_corpus()
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)} if os.path.isdir(corpus_dir) else {}
    gates.append(("G3 plan PDF + corpus present",
                  os.path.isfile(PDF) and len(corpus) == EXPECTED_COUNT,
                  {"pdf": os.path.isfile(PDF), "corpus": len(corpus)}))

    plan = PlanPdf(PDF)
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        words = plan.words(SHEET, offset)
        draw = plan.line_items(SHEET, offset)
        lines = plan.lines(SHEET, offset)

        # (1) START installer HH (owner reset token '<sta>=0+00')
        s_label = start_label_text(start_a)
        sv = resolve_structure_position(label_text=s_label, structure_class="installer_hh",
                                        words=words, drawings=draw,
                                        layer_table=BRENHAM_STRUCTURE_LAYERS)
        ev["start_label_text"] = s_label
        ev["start_bind_result"] = sv.result
        s_bound = sv.result == POSITION_BOUND and sv.symbol_xy
        ev["start_symbol_xy"] = [round(c, 2) for c in sv.symbol_xy] if sv.symbol_xy else None
        gates.append(("G4 START installer_hh binds to source (label box -> leader -> NEXTLINK symbol)",
                      bool(s_bound), sv.result))
        if not s_bound:
            return _emit(gates, _bind_blocker(sv.result, B_START_LABEL, B_START_SYMBOL), ev)
        s_xy = tuple(sv.symbol_xy)

        # (2) END flower pot (label '1+00' + FLOWER/POT context)
        pv = resolve_structure_position(label_text=end_a.get("station"), structure_class="flower_pot",
                                        words=words, drawings=draw,
                                        layer_table=BRENHAM_STRUCTURE_LAYERS,
                                        context_texts=("FLOWER", "POT"))
        ev["end_bind_result"] = pv.result
        e_bound = pv.result == POSITION_BOUND and pv.symbol_xy
        ev["end_symbol_xy"] = [round(c, 2) for c in pv.symbol_xy] if pv.symbol_xy else None
        gates.append(("G5 END flower_pot binds to source (label+context -> leader -> FLOWER POT symbol)",
                      bool(e_bound), pv.result))
        if not e_bound:
            return _emit(gates, _bind_blocker(pv.result, B_END_LABEL, B_END_SYMBOL), ev)
        e_xy = tuple(pv.symbol_xy)

        # (3) the owner 0+00 -> 1+00 / 100' direct-bore callout, present + unique
        seg = [ln for ln in lines if _SEG_RE.search(ln)]
        foot = [ln for ln in lines if _FOOTAGE_RE.search(ln)]
        ev["callout_segment_lines"] = seg[:4]
        ev["callout_footage_lines"] = foot[:4]
        if not seg or not foot:
            return _emit(gates, B_CALLOUT_NOT_FOUND, ev)
        if len(seg) > 1:
            return _emit(gates, B_CALLOUT_AMBIGUOUS, ev)
        gates.append(("G6 owner callout present + unique ('STA 0+00 TO STA 1+00 DIR. BORE (100')')",
                      len(seg) == 1 and len(foot) >= 1, {"seg": len(seg), "footage": len(foot)}))

        # (4) MODELED base conduit corridor: connected to BOTH symbols + continuous between them
        base = set(BRENHAM_CONDUIT_LAYERS.values())
        fp = symbol_footprint(draw, INSTALLER_SYMBOL_LAYER, s_xy)
        chain = connected_chain([x for x in draw if x.get("layer") in base], fp) if fp else []
        eps = dash_endpoints(chain)
        ev["conduit_layers"] = sorted(base)
        ev["chain_segs"] = len(chain)
        if not chain:
            return _emit(gates, B_CONDUIT_SEED, ev)
        reach_end = min((((p[0] - e_xy[0]) ** 2 + (p[1] - e_xy[1]) ** 2) ** 0.5 for p in eps), default=None)
        reach_start = min((((p[0] - s_xy[0]) ** 2 + (p[1] - s_xy[1]) ** 2) ** 0.5 for p in eps), default=None)
        ev["chain_to_end_symbol_pt"] = round(reach_end, 2) if reach_end is not None else None
        ev["chain_to_start_symbol_pt"] = round(reach_start, 2) if reach_start is not None else None
        band, ylo, yhi = corridor_band(eps, s_xy, e_xy)
        continuous = corridor_is_continuous(band, ylo, yhi)
        ev["corridor_band_points"] = len(band)
        ev["corridor_max_gap_pt"] = round(max((band[i + 1] - band[i] for i in range(len(band) - 1)),
                                              default=0.0), 2)
        ev["corridor_continuous"] = continuous
        both_connected = (reach_end is not None and reach_end <= MAX_DASH_GAP
                          and reach_start is not None and reach_start <= MAX_DASH_GAP)
        gates.append(("G7 base conduit chain connects BOTH bound symbols (<= MAX_DASH_GAP)",
                      both_connected, {"to_end": ev["chain_to_end_symbol_pt"],
                                       "to_start": ev["chain_to_start_symbol_pt"]}))
        gates.append(("G8 direct start->end corridor is a continuous source dash chain",
                      continuous, {"band_pts": len(band), "max_gap": ev["corridor_max_gap_pt"]}))

        if both_connected and continuous:
            result = R_CONFIRMED
        elif reach_end is not None and reach_end <= MAX_DASH_GAP:
            result = R_PARTIAL  # endpoints bind + chain reaches, but no clean direct corridor
        else:
            result = B_ROUTE
    finally:
        plan.close()

    return _emit(gates, result, ev)


def _emit(gates, result, ev) -> int:
    gates.append(("G9 result in allowed enum", result in ALLOWED, result))
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G10 zero PNG / zero stroke (no render lane)", len(pngs) == 0, {"pngs": pngs}))
    confirmed = result in (R_CONFIRMED, R_PARTIAL)
    all_pass = all(x for _, x, _ in gates) and confirmed
    report = {
        "milestone": "OWNER-PACKET-2 -- log64 sheet-21 source bind slice (proof only; no render)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result, "target": "log64", "sheet": SHEET,
        "question": ("does log64's encoded identity bind to real sheet-21 source -- installer-HH "
                     "start, flower-pot end, the 100' direct-bore callout, and a continuous modeled "
                     "conduit corridor between them?"),
        "evidence": ev,
        "future_render_ready": result == R_CONFIRMED,
        "no_render": True, "no_invented_coordinates": True, "no_screenshot_pixels": True,
        "no_cross_sheet": True, "coords_are_extractor_derived": True,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "log64_sheet21_source_bind_slice.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[log64-bind] result: {result}")
    for k in ("start_label_text", "start_bind_result", "start_symbol_xy", "end_bind_result",
              "end_symbol_xy", "callout_segment_lines", "callout_footage_lines", "chain_segs",
              "chain_to_start_symbol_pt", "chain_to_end_symbol_pt", "corridor_band_points",
              "corridor_max_gap_pt", "corridor_continuous"):
        if k in ev:
            print(f"[log64-bind]   {k}: {ev[k]}")
    for n, x, _ in gates:
        print(f"[log64-bind] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[log64-bind] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
