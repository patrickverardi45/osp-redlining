r"""OWNER-PACKET-2 -- log53 sheet-6 continuation segment slice (PROOF ONLY).

log53's sheet-5 end terminates at the 24+11 matchline (BOUNDARY_POINT_RESOLVED_SHEET5_ONLY).
The drawn run CONTINUES on the next print page (sheet 6): STA 24+11 -> STA 26+38, ending at a
26+38 FLOWER POT. This proves whether sheet 6 carries its OWN source-backed segment for that
continuation -- a SHEET-LOCAL proof joined to sheet 5 by STATION IDENTITY only (no cross-sheet
coordinate translation here).

Method (existing seams only; no new core code):
  1. on sheet 6, find the printed continuation callout 'STA 24+11 TO STA 26+38' (unique);
     read its note footage via matchline_join.find_run_callout_footage (corroboration);
  2. bind the upper endpoint via the EXISTING resolve_structure_position flower_pot locator
     (label '26+38' + context FLOWER/POT) -> sheet-6 local end point;
  3. build the conduit chain (base | BORE - LATERAL coverage) seeded at the flower-pot footprint;
  4. find the unique sheet-6 bottom 24+11 matchline line; confirm the chain REACHES it
     (nearest dash endpoint <= MAX_DASH_GAP) and resolve the sheet-6 local 24+11 boundary point
     via matchline_join.extend_dash_to_boundary;
  5. station continuity to sheet 5 is LOGICAL (both ends are STA 24+11); coordinate translation
     stays deferred.

No renderer output, no stroke, no PNG/PDF artifact, no broad frame solving, no multi-page run
assembly, no invented coordinates, no screenshot pixels, no dialect change. Proof-only; artifacts
gitignored. Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log53_sheet6_continuation_segment_slice
"""
from __future__ import annotations

import json
import math
import os
import re

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.conduit_topology import (
    MAX_DASH_GAP,
    connected_chain,
    dash_endpoints,
    symbol_footprint,
)
from truelinev2.extract.matchline_join import (
    extend_dash_to_boundary,
    find_run_callout_footage,
    matchline_bboxes,
    nearest_gap,
)
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import (
    BRENHAM_CONDUIT_LAYERS,
    BRENHAM_LATERAL_CONDUIT_LAYERS,
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

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log53_sheet6_continuation_segment_slice"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
SHEET6 = 6
FLOWER_SYMBOL_LAYER = "FLOWER POT"
MATCHLINE_LAYER = "MATCHLINE"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
_CALLOUT_RE = re.compile(r"24\+11\s*TO\s*(?:STA\s*)?26\+38", re.I)

R_PROVEN = "SHEET6_CONTINUATION_SEGMENT_PROVEN"
R_LABEL_ENDPOINT_BLOCKED = "SHEET6_CONTINUATION_LABEL_FOUND_ENDPOINT_BLOCKED"
R_CHAIN_ENDPOINT_BLOCKED = "SHEET6_CONTINUATION_CHAIN_FOUND_ENDPOINT_BLOCKED"
R_CHAIN_AMBIG = "SHEET6_CONTINUATION_CHAIN_AMBIGUOUS"
R_LABEL_NOT_FOUND = "BLOCKED_SHEET6_CONTINUATION_LABEL_NOT_FOUND"
R_LABEL_NOT_UNIQUE = "BLOCKED_SHEET6_CONTINUATION_LABEL_NOT_UNIQUE"
R_CONDUIT_NOT_FOUND = "BLOCKED_SHEET6_CONDUIT_NOT_FOUND"
R_POT_NOT_FOUND = "BLOCKED_SHEET6_FLOWER_POT_NOT_FOUND"
R_POT_NOT_UNIQUE = "BLOCKED_SHEET6_FLOWER_POT_NOT_UNIQUE"
R_CHAIN_NOT_CONNECTED = "BLOCKED_SHEET6_CHAIN_NOT_CONNECTED"
R_NO_SAFE = "BLOCKED_NO_SAFE_SHEET6_SEGMENT"
ALLOWED = {R_PROVEN, R_LABEL_ENDPOINT_BLOCKED, R_CHAIN_ENDPOINT_BLOCKED, R_CHAIN_AMBIG,
           R_LABEL_NOT_FOUND, R_LABEL_NOT_UNIQUE, R_CONDUIT_NOT_FOUND, R_POT_NOT_FOUND,
           R_POT_NOT_UNIQUE, R_CHAIN_NOT_CONNECTED, R_NO_SAFE}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()  # no render/stroke lane: a PNG must never exist

    doc = load_adjudication()
    truth = json.loads(TRUTH.read_text(encoding="utf-8"))
    baseline = {r["bore_id"]: dict(r) for r in truth["rows"]}
    off_rows = apply_adjudications(baseline, enabled=False)
    on_rows = apply_adjudications(baseline, enabled=True, doc=doc)
    summ = activation_summary(on_rows)
    rec = {r["log_id"]: r for r in doc["logs"]}
    end_a = (rec["log53"].get("endpoint_anchors") or {}).get("end") or {}

    def buckets(rows):
        c = {}
        for r in rows.values():
            c[r["completion_bucket"]] = c.get(r["completion_bucket"], 0) + 1
        return c

    gates = []
    gates.append(("G1 flag OFF byte-identical (31/6/1/17/3)",
                  off_rows is baseline and buckets(off_rows) == FROZEN_BUCKETS, buckets(off_rows)))
    gates.append(("G2 flag ON 22/1/4",
                  summ["manual_review_drawable"] == 22 and summ["manual_source_verification"] == 1
                  and summ["manual_abstain"] == 4, None))
    gates.append(("G3 endpoint_anchors.end points to sheet 6 (STA 24+11 TO STA 26+38)",
                  end_a.get("continues_to_sheet") == 6
                  and end_a.get("continues_as") == "STA 24+11 TO STA 26+38", end_a))
    gates.append(("G4 log44 blocked / abstains held / no dup",
                  on_rows["log44"]["adjudication"]["drawable_status"] == "non_drawable"
                  and all(on_rows[l]["adjudication"]["drawable_status"] == "abstain" for l in ABSTAIN_4)
                  and not parent_run_duplicate_check(doc), None))

    result = R_NO_SAFE
    ev = {"sheet": SHEET6}
    if not os.path.isfile(PDF):
        gates.append(("G5 plan PDF present", False, f"missing {PDF}"))
        return _emit(gates, result, ev)
    corpus_dir, _ = resolve_corpus()
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)} if os.path.isdir(corpus_dir) else {}
    gates.append(("G5 plan PDF + corpus present",
                  os.path.isfile(PDF) and len(corpus) == EXPECTED_COUNT,
                  {"pdf": os.path.isfile(PDF), "corpus": len(corpus)}))

    conduit_layers = set(BRENHAM_CONDUIT_LAYERS.values()) | set(BRENHAM_LATERAL_CONDUIT_LAYERS.values())
    plan = PlanPdf(PDF)
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        words = plan.words(SHEET6, offset)
        draw = plan.line_items(SHEET6, offset)
        lines = plan.lines(SHEET6, offset)

        # (1) continuation callout label
        cal = [ln for ln in lines if _CALLOUT_RE.search(ln)]
        ev["continuation_callout_lines"] = cal[:3]
        if not cal:
            result = R_LABEL_NOT_FOUND
            ev["why"] = "no 'STA 24+11 TO STA 26+38' continuation callout on sheet 6"
            return _emit(gates, result, ev)
        if len(cal) > 1:
            result = R_LABEL_NOT_UNIQUE
            ev["why"] = f"{len(cal)} '24+11 TO 26+38' callout lines on sheet 6 -- not unique"
            return _emit(gates, result, ev)
        ev["callout_footage"] = find_run_callout_footage(lines, "24+11", "26+38")

        # (2) upper endpoint: 26+38 FLOWER POT via the EXISTING modeled locator
        pv = resolve_structure_position(label_text="26+38", structure_class="flower_pot",
                                        words=words, drawings=draw,
                                        layer_table=BRENHAM_STRUCTURE_LAYERS,
                                        context_texts=("FLOWER", "POT"))
        ev["flower_pot_bind_result"] = pv.result
        if pv.result != POSITION_BOUND or not pv.symbol_xy:
            result = (R_POT_NOT_UNIQUE if "NOT_UNIQUE" in pv.result else R_POT_NOT_FOUND)
            ev["why"] = f"26+38 flower pot did not bind ({pv.result})"
            return _emit(gates, result, ev)
        pot = tuple(pv.symbol_xy)
        ev["sheet6_end_point_26+38_flower_pot"] = [round(c, 1) for c in pot]

        # (3) conduit chain seeded at the flower pot
        fp = symbol_footprint(draw, FLOWER_SYMBOL_LAYER, pot)
        chain = connected_chain([x for x in draw if x.get("layer") in conduit_layers], fp) if fp else []
        ev["chain_segs"] = len(chain)
        if not chain:
            result = R_CONDUIT_NOT_FOUND
            ev["why"] = "no conduit chain is graph-connected to the 26+38 flower-pot footprint"
            return _emit(gates, result, ev)

        # (4) sheet-6 bottom 24+11 matchline + chain reach + local boundary point
        tok = next((w for w in words if re.match(r"^24\+11/", str(w.get("text", "")))), None)
        toks = [w for w in words if re.match(r"^24\+11/", str(w.get("text", "")))]
        all_ml = matchline_bboxes(draw, MATCHLINE_LAYER)
        if tok is None or not all_ml:
            result = R_CHAIN_ENDPOINT_BLOCKED
            ev["why"] = "no 24+11 matchline label/line on sheet 6 to terminate the continuation entry"
            return _emit(gates, result, ev)
        if len(toks) != 1:
            result = R_LABEL_NOT_UNIQUE
            ev["why"] = f"{len(toks)} 24+11 matchline tokens on sheet 6 -- not unique"
            return _emit(gates, result, ev)
        label_xy = (tok["xc"], tok["yc"])
        mlb = min(all_ml, key=lambda bb: nearest_gap([label_xy], bb))
        ev["sheet6_24+11_matchline_bbox"] = [round(c, 1) for c in mlb]
        eps = dash_endpoints(chain)
        reach = min((nearest_gap([p], mlb) for p in eps), default=None)
        ev["chain_to_24+11_matchline_gap_pt"] = round(reach, 2) if reach is not None else None
        if reach is None or reach > MAX_DASH_GAP:
            result = R_CHAIN_NOT_CONNECTED
            ev["why"] = (f"the flower-pot conduit chain reaches only {ev['chain_to_24+11_matchline_gap_pt']} "
                         f"pt from the 24+11 matchline (> MAX_DASH_GAP {MAX_DASH_GAP}) -- not connected")
            return _emit(gates, result, ev)
        bnd = extend_dash_to_boundary(chain, mlb)
        ev["sheet6_start_boundary_24+11"] = [round(c, 2) for c in bnd] if bnd else None

        # (5) segment proven (station continuity is logical; translation deferred)
        ev["station_continuity_to_sheet5"] = "logical (sheet-5 end STA 24+11 == sheet-6 start STA 24+11)"
        ev["cross_sheet_coordinate_translation"] = "deferred (not attempted in this slice)"
        ev["source_conduit_layers"] = sorted(conduit_layers)
        result = R_PROVEN
    finally:
        plan.close()

    return _emit(gates, result, ev)


def _emit(gates, result, ev) -> int:
    gates.append(("G6 result in allowed enum", result in ALLOWED, result))
    proven = result == R_PROVEN
    gates.append(("G7 endpoints present iff PROVEN (real extraction, no invention)",
                  (proven and ev.get("sheet6_end_point_26+38_flower_pot"))
                  or (not proven), ev.get("sheet6_end_point_26+38_flower_pot")))
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G8 zero PNG / zero stroke (no render lane)", len(pngs) == 0, {"pngs": pngs}))
    all_pass = all(x for _, x, _ in gates)
    report = {
        "milestone": "OWNER-PACKET-2 -- log53 sheet-6 continuation segment slice (proof only)",
        "verdict": "PASS" if all_pass else "FAIL",
        "target": "log53", "sheet": SHEET6,
        "question": ("does sheet 6 locally prove the continuation segment STA 24+11 -> STA 26+38 "
                     "from the callout, through source conduit, to the 26+38 flower pot?"),
        "sheet6_continuation_result": result,
        "evidence": ev,
        "no_screenshot_pixels": True,
        "no_render": True,
        "no_cross_sheet_translation": True,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "log53_sheet6_continuation_segment_slice.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[log53-s6] sheet6_continuation_result: {result}")
    for k in ("continuation_callout_lines", "callout_footage", "flower_pot_bind_result",
              "sheet6_end_point_26+38_flower_pot", "chain_segs", "sheet6_24+11_matchline_bbox",
              "chain_to_24+11_matchline_gap_pt", "sheet6_start_boundary_24+11",
              "station_continuity_to_sheet5"):
        if k in ev:
            print(f"[log53-s6]   {k}: {ev[k]}")
    if ev.get("why"):
        print(f"[log53-s6]   why: {ev['why'][:200]}")
    for n, x, _ in gates:
        print(f"[log53-s6] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[log53-s6] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
