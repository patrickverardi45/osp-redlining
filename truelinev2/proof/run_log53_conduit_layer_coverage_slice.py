r"""OWNER-PACKET-2 -- log53 conduit-layer coverage slice (PROOF for the conduit-coverage impl).

After the start NEXTLINK HH bound (POSITION_BOUND), the matchline / reverse-chain proofs still
saw NO conduit seed because log53's drawn conduit is the HH-HH LATERAL run, not the modeled
mainline (BORE - VACANT PIPE / BORE - PORT). This proves whether the ADDITIVE coverage layer
``BRENHAM_LATERAL_CONDUIT_LAYERS`` (BORE - LATERAL) makes the v2 conduit-chain seams see a
source-backed conduit graph-connected to the bound start symbol -- WITHOUT touching the frozen
base conduit table, the renderer, or the engine census.

Chain of evidence (all from real PDF/CAD extraction; no screenshot pixels, no invented coords):
  1. re-bind the start via resolve_nextlink_hh_callout -> source symbol center;
  2. BORE - LATERAL exists on sheet 5 and is graph-connected to that symbol (<= MAX_DASH_GAP);
  3. a connected_chain over base|lateral from the start footprint reaches toward the 24+11
     matchline (lower y) where base-only does NOT -> a chain SEED now exists;
  4. BORE - PATH is NOT connected to the start (> MAX_DASH_GAP) -> excluded as unproven coverage;
  5. census safety: BRENHAM_CONDUIT_LAYERS is byte-identical (frozen); the new coverage is a
     SEPARATE additive constant; flag-OFF/ON counts unchanged; no PNG / no stroke / no placement.

Proof-only; artifacts gitignored. Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log53_conduit_layer_coverage_slice
"""
from __future__ import annotations

import json
import math
import os

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
    BRENHAM_LATERAL_CONDUIT_LAYERS,
    POSITION_BOUND,
    resolve_nextlink_hh_callout,
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

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log53_conduit_layer_coverage_slice"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
CALLOUT_LAYER, SYMBOL_LAYER = "ANNOTATION", "NEXTLINK"
FROZEN_BASE_CONDUIT = {"VACANT HDPE": "BORE - VACANT PIPE", "TERMINAL TAIL": "BORE - PORT"}
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")

R_CONFIRMED = "CONDUIT_LAYER_COVERAGE_CONFIRMED"
R_PARTIAL = "CONDUIT_LAYER_PARTIAL_COVERAGE_CONFIRMED"
R_TOO_BROAD = "BLOCKED_LAYER_TOO_BROAD"
R_NOT_CONNECTED = "BLOCKED_LAYER_NOT_CONNECTED_TO_START"
R_AMBIGUOUS = "BLOCKED_LAYER_AMBIGUOUS"
R_NO_SEED = "BLOCKED_NO_SAFE_CONDUIT_SEED"
ALLOWED = {R_CONFIRMED, R_PARTIAL, R_TOO_BROAD, R_NOT_CONNECTED, R_AMBIGUOUS, R_NO_SEED}


def _nearest_gap_to_layer(draw, layer, pt):
    segs = [x for x in draw if x.get("layer") == layer]
    if not segs:
        return None, 0
    return min(math.hypot(x["xc"] - pt[0], x["yc"] - pt[1]) for x in segs), len(segs)


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
    start_a = (rec["log53"].get("endpoint_anchors") or {}).get("start") or {}

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
    gates.append(("G3 base conduit table FROZEN (census-safe)",
                  dict(BRENHAM_CONDUIT_LAYERS) == FROZEN_BASE_CONDUIT, dict(BRENHAM_CONDUIT_LAYERS)))
    gates.append(("G4 lateral coverage is a SEPARATE additive set (BORE - LATERAL only)",
                  dict(BRENHAM_LATERAL_CONDUIT_LAYERS) == {"LATERAL HDPE": "BORE - LATERAL"},
                  dict(BRENHAM_LATERAL_CONDUIT_LAYERS)))
    gates.append(("G5 log44 blocked / abstains held / no dup",
                  on_rows["log44"]["adjudication"]["drawable_status"] == "non_drawable"
                  and all(on_rows[l]["adjudication"]["drawable_status"] == "abstain" for l in ABSTAIN_4)
                  and not parent_run_duplicate_check(doc), None))

    result = R_NO_SEED
    ev = {}
    if not os.path.isfile(PDF):
        gates.append(("G6 plan PDF present", False, f"missing {PDF}"))
        return _emit(gates, result, ev)
    corpus_dir, _ = resolve_corpus()
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)} if os.path.isdir(corpus_dir) else {}
    gates.append(("G6 plan PDF + corpus present",
                  os.path.isfile(PDF) and len(corpus) == EXPECTED_COUNT,
                  {"pdf": os.path.isfile(PDF), "corpus": len(corpus)}))

    base_layers = set(BRENHAM_CONDUIT_LAYERS.values())
    lateral_layers = set(BRENHAM_LATERAL_CONDUIT_LAYERS.values())
    plan = PlanPdf(PDF)
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        words = plan.words(5, offset)
        draw = plan.line_items(5, offset)

        # (1) re-bind the start symbol via the committed locator
        v = resolve_nextlink_hh_callout(station_sta=start_a.get("station"), words=words,
                                        drawings=draw, callout_layer=CALLOUT_LAYER,
                                        symbol_layer=SYMBOL_LAYER)
        ev["start_bind_result"] = v.result
        if v.result != POSITION_BOUND or not v.symbol_xy:
            result = R_NO_SEED
            ev["why"] = "start symbol did not re-bind; cannot anchor a conduit seed"
            return _emit(gates, result, ev)
        start = tuple(v.symbol_xy)
        ev["bound_start_symbol"] = [round(c, 1) for c in start]
        fp = symbol_footprint(draw, SYMBOL_LAYER, start)

        # (2) layer existence + connectivity to the bound start
        lat_gap, lat_n = _nearest_gap_to_layer(draw, "BORE - LATERAL", start)
        path_gap, path_n = _nearest_gap_to_layer(draw, "BORE - PATH", start)
        ev["bore_lateral"] = {"count": lat_n, "nearest_to_start_pt": round(lat_gap, 1) if lat_gap else None}
        ev["bore_path"] = {"count": path_n, "nearest_to_start_pt": round(path_gap, 1) if path_gap else None}
        lat_exists = lat_n > 0
        lat_connected = lat_gap is not None and lat_gap <= MAX_DASH_GAP
        path_connected = path_gap is not None and path_gap <= MAX_DASH_GAP

        # (3) seed: chain over base|lateral reaches toward the 24+11 matchline (lower y)
        def chain_min_y(layers):
            segs = [x for x in draw if x.get("layer") in layers]
            eps = dash_endpoints(connected_chain(segs, fp)) if fp else []
            return (min(p[1] for p in eps), len(connected_chain(segs, fp))) if eps else (None, 0)
        base_min_y, base_segs = chain_min_y(base_layers)
        ext_min_y, ext_segs = chain_min_y(base_layers | lateral_layers)
        ev["base_chain"] = {"segs": base_segs, "min_y": base_min_y}
        ev["base_plus_lateral_chain"] = {"segs": ext_segs, "min_y": ext_min_y}
        # a seed "where previous proofs could not see one" = lateral extends the chain
        # meaningfully toward the matchline (lower y) beyond base-only
        seed_added = (ext_min_y is not None and
                      (base_min_y is None or ext_min_y < base_min_y - MAX_DASH_GAP))
        ev["seed_added_toward_matchline"] = seed_added

        # (4) classify
        if not lat_exists:
            result = R_NO_SEED
            ev["why"] = "BORE - LATERAL has no segments on sheet 5"
        elif not lat_connected:
            result = R_NOT_CONNECTED
            ev["why"] = (f"BORE - LATERAL nearest segment is {round(lat_gap,1)} pt from the bound "
                         f"start symbol (> MAX_DASH_GAP {MAX_DASH_GAP}) -- not connected")
        elif not seed_added:
            result = R_NO_SEED
            ev["why"] = "BORE - LATERAL is connected but adds no chain reach toward the matchline"
        else:
            # LATERAL is the proven, necessary layer. Is PATH also connected (-> full) or not?
            if path_connected:
                result = R_CONFIRMED
                ev["why"] = "both BORE - LATERAL and BORE - PATH connect to the bound start"
            else:
                result = R_PARTIAL
                ev["why"] = (
                    f"BORE - LATERAL is source-proven and graph-connected to the bound start "
                    f"({round(lat_gap,1)} pt) and seeds a chain reaching y={ext_min_y} toward the "
                    f"24+11 matchline (base-only reached y={base_min_y}); it is ADDED. BORE - PATH "
                    f"is NOT connected to the start ({round(path_gap,1) if path_gap else None} pt > "
                    f"{MAX_DASH_GAP}), so it is EXCLUDED as unproven over-coverage. Partial, bounded "
                    f"coverage confirmed; the frozen base conduit table is unchanged.")
    finally:
        plan.close()

    return _emit(gates, result, ev)


def _emit(gates, result, ev) -> int:
    gates.append(("G7 result in allowed enum", result in ALLOWED, result))
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G8 zero PNG / zero stroke (no render lane)", len(pngs) == 0, {"pngs": pngs}))
    all_pass = all(x for _, x, _ in gates)
    report = {
        "milestone": "OWNER-PACKET-2 -- log53 conduit-layer coverage slice (proof for impl)",
        "verdict": "PASS" if all_pass else "FAIL",
        "target": "log53", "sheet": 5,
        "question": ("does the additive BORE - LATERAL coverage give the v2 conduit-chain seams a "
                     "source-backed seed connected to the bound start, without census drift?"),
        "conduit_coverage_result": result,
        "layers_added": ["BORE - LATERAL"] if result in (R_CONFIRMED, R_PARTIAL) else [],
        "layers_excluded": ["BORE - PATH"] if result == R_PARTIAL else [],
        "base_conduit_table_frozen": dict(BRENHAM_CONDUIT_LAYERS) == FROZEN_BASE_CONDUIT,
        "evidence": ev,
        "no_screenshot_pixels": True,
        "no_render": True,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "log53_conduit_layer_coverage_slice.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[log53-cond] conduit_coverage_result: {result}")
    for k in ("bound_start_symbol", "bore_lateral", "bore_path", "base_chain",
              "base_plus_lateral_chain", "seed_added_toward_matchline"):
        if k in ev:
            print(f"[log53-cond]   {k}: {ev[k]}")
    if ev.get("why"):
        print(f"[log53-cond]   why: {ev['why'][:200]}")
    for n, x, _ in gates:
        print(f"[log53-cond] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[log53-cond] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
