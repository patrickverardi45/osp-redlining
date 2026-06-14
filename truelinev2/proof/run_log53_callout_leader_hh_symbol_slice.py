r"""OWNER-PACKET-2 -- log53 callout-leader / HH-HH conduit source-coverage slice (PROOF ONLY).

Patrick's screenshot points at the log53 START feature on sheet 5: the
"STA 21+63=0+00 ... NEXTLINK HH ... PROP. SPLICE POINT 32" callout -> leader -> small
square HH symbol -> HH-HH / 2-1.25" HDPE conduit. This proof VERIFIES, against the actual
PDF/CAD source items (NEVER screenshot pixels), whether each element is drawn -- to settle
whether the prior blockers were DIALECT/LOCATOR/LAYER-COVERAGE gaps rather than missing
source.

Verifies (anchored on EXTRACTED TEXT, not screenshot coords):
  1. callout text tokens present (21+63=0+00 / NEXTLINK / HH / SPLICE / 32) -> centroid;
  2. the enclosing callout BOX layer (is it a modeled structure-text layer, or generic?);
  3. a LEADER from that box toward the symbol (existing find_leaders seam);
  4. the square HH SYMBOL near the leader tip and WHICH layer carries it;
  5. the conduit near the symbol and WHICH layers (modeled vs unmodeled);
  6. symbol<->conduit connectivity (existing bbox-gap seam).

Typed result (a refusal is valid; success is never forced):
  CALLOUT_LEADER_BINDS_HH_SYMBOL / ..._REACHES_HH_SYMBOL_BUT_CONDUIT_LAYER_UNMODELED /
  CALLOUT_TEXT_FOUND_LEADER_NOT_FOUND / CALLOUT_AND_SYMBOL_FOUND_BUT_NOT_UNIQUE /
  HH_HH_CONDUIT_LAYER_FOUND_BUT_NOT_CONNECTED / SOURCE_FEATURE_PRESENT_DIALECT_GAP_CONFIRMED /
  SOURCE_FEATURE_NOT_MACHINE_RECOVERABLE

No production placement, no renderer output, no stroke, no PNG, no dialect wiring, no
screenshot-pixel geometry, no invented coordinates. Proof-only; artifacts gitignored.
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log53_callout_leader_hh_symbol_slice
"""
from __future__ import annotations

import json
import math
import os

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.conduit_topology import MAX_DASH_GAP, bbox_gap
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import (
    BRENHAM_CONDUIT_LAYERS,
    BRENHAM_STRUCTURE_LAYERS,
    cluster_symbols,
    find_label_box,
    find_leaders,
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

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log53_callout_leader_hh_symbol_slice"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
NEXTLINK_SYMBOL_LAYER = "NEXTLINK"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
TIP_NEAR = 16.0   # leader tip -> symbol cluster window (2x the binder's TIP_TOL)
# callout identity tokens (the start NEXTLINK HH note) -- located by CONTENT, not pixels
CALLOUT_TOKENS = ("21+63=0+00", "NEXTLINK", "HH", "SPLICE", "32")
MODELED_STRUCT_TEXT_LAYERS = {v[0] for v in BRENHAM_STRUCTURE_LAYERS.values()}
MODELED_CONDUIT_LAYERS = set(BRENHAM_CONDUIT_LAYERS.values())

R_BINDS = "CALLOUT_LEADER_BINDS_HH_SYMBOL"
R_REACHES_CONDUIT_UNMODELED = "CALLOUT_LEADER_REACHES_HH_SYMBOL_BUT_CONDUIT_LAYER_UNMODELED"
R_LEADER_NOT_FOUND = "CALLOUT_TEXT_FOUND_LEADER_NOT_FOUND"
R_NOT_UNIQUE = "CALLOUT_AND_SYMBOL_FOUND_BUT_NOT_UNIQUE"
R_CONDUIT_NOT_CONNECTED = "HH_HH_CONDUIT_LAYER_FOUND_BUT_NOT_CONNECTED"
R_DIALECT_GAP = "SOURCE_FEATURE_PRESENT_DIALECT_GAP_CONFIRMED"
R_NOT_RECOVERABLE = "SOURCE_FEATURE_NOT_MACHINE_RECOVERABLE"
ALLOWED = {R_BINDS, R_REACHES_CONDUIT_UNMODELED, R_LEADER_NOT_FOUND, R_NOT_UNIQUE,
           R_CONDUIT_NOT_CONNECTED, R_DIALECT_GAP, R_NOT_RECOVERABLE}


def _callout_centroid(words):
    """Centroid + member points of the start-callout identity tokens (content-located,
    not pixels): the reset token's neighbourhood, isolating THIS note from other SPLICE/HH
    notes elsewhere on the sheet."""
    anchor = next((w for w in words if w.get("text") == "21+63=0+00"), None)
    if anchor is None:
        return None, []
    ax, ay = anchor["xc"], anchor["yc"]
    near = [(w["xc"], w["yc"]) for w in words if w.get("text") in CALLOUT_TOKENS
            and math.hypot(w["xc"] - ax, w["yc"] - ay) <= 40.0]
    cx = sum(p[0] for p in near) / len(near)
    cy = sum(p[1] for p in near) / len(near)
    return (cx, cy), near


def _callout_box_layer(draw, near_pts):
    """The smallest box that encloses ALL callout tokens. Requiring full enclosure
    isolates the framing callout box from map-geometry polygons (e.g. a building outline
    that merely overlaps the text but stops short of the NEXTLINK/HH tokens)."""
    boxes = [d for d in draw if d.get("type") in ("s", "fs")
             and (d["x1"] - d["x0"]) >= 20 and 8 <= (d["y1"] - d["y0"]) <= 80
             and all(d["x0"] - 2 <= px <= d["x1"] + 2 and d["y0"] - 2 <= py <= d["y1"] + 2
                     for px, py in near_pts)]
    if not boxes:
        return None, None
    b = min(boxes, key=lambda d: (d["x1"] - d["x0"]) * (d["y1"] - d["y0"]))
    return b.get("layer"), (b["x0"], b["y0"], b["x1"], b["y1"])


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
    gates.append(("G3 endpoint_anchors.start consumed (NEXTLINK HH @ 21+63)",
                  start_a.get("structure_class") == "nextlink_hh"
                  and start_a.get("structure_label") == "NEXTLINK HH", start_a))
    gates.append(("G4 log44 blocked / abstains held / no dup",
                  on_rows["log44"]["adjudication"]["drawable_status"] == "non_drawable"
                  and all(on_rows[l]["adjudication"]["drawable_status"] == "abstain" for l in ABSTAIN_4)
                  and not parent_run_duplicate_check(doc), None))

    result = R_NOT_RECOVERABLE
    ev = {}
    if not os.path.isfile(PDF):
        gates.append(("G5 plan PDF present", False, f"missing {PDF}"))
        return _emit(gates, result, ev)
    corpus_dir, _ = resolve_corpus()
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)} if os.path.isdir(corpus_dir) else {}
    gates.append(("G5 plan PDF + corpus present",
                  os.path.isfile(PDF) and len(corpus) == EXPECTED_COUNT,
                  {"pdf": os.path.isfile(PDF), "corpus": len(corpus)}))

    plan = PlanPdf(PDF)
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        words = plan.words(5, offset)
        draw = plan.line_items(5, offset)

        # (1) callout text present?
        centroid, near_pts = _callout_centroid(words)
        ev["callout_tokens_found"] = len(near_pts)
        if centroid is None or len(near_pts) < 2:
            result = R_NOT_RECOVERABLE
            ev["why"] = "the STA 21+63=0+00 NEXTLINK HH callout tokens were not found in the text layer"
            return _emit(gates, result, ev)
        ev["callout_centroid"] = [round(centroid[0], 1), round(centroid[1], 1)]

        # (2) callout box layer
        box_layer, box = _callout_box_layer(draw, near_pts)
        ev["callout_box_layer"] = box_layer
        ev["callout_box_on_modeled_structure_text_layer"] = box_layer in MODELED_STRUCT_TEXT_LAYERS

        # (3) leader on the box's layer toward the symbol
        leaders = find_leaders(draw, box_layer, box) if box_layer and box else []
        ev["leaders_found"] = len(leaders)

        # (4) HH symbol near a leader tip, and its layer
        clusters = cluster_symbols(draw, NEXTLINK_SYMBOL_LAYER)
        tips = [(l[2], l[3]) for l in leaders]
        sym = None
        n_at_tip = 0
        if tips:
            for c in clusters:
                if any(math.hypot(c.x - t[0], c.y - t[1]) <= TIP_NEAR for t in tips):
                    n_at_tip += 1
                    sym = c if sym is None else sym
        ev["hh_symbol_layer"] = NEXTLINK_SYMBOL_LAYER if sym else None
        ev["hh_symbols_at_leader_tip"] = n_at_tip
        ev["hh_symbol_on_modeled_layer"] = NEXTLINK_SYMBOL_LAYER in {
            v[1] for v in BRENHAM_STRUCTURE_LAYERS.values()}

        # (5) conduit near the symbol + which layers
        conduit_near = {}
        if sym:
            sb = {"x0": sym.x - 4, "y0": sym.y - 4, "x1": sym.x + 4, "y1": sym.y + 4}
            for d in draw:
                L = d.get("layer")
                if L and L.upper().startswith("BORE"):
                    g = bbox_gap(d, sb)
                    if g <= MAX_DASH_GAP and (L not in conduit_near or g < conduit_near[L]):
                        conduit_near[L] = round(g, 1)
        ev["conduit_layers_near_symbol"] = conduit_near
        unmodeled_conduit = sorted(set(conduit_near) - MODELED_CONDUIT_LAYERS)
        modeled_conduit = sorted(set(conduit_near) & MODELED_CONDUIT_LAYERS)
        ev["unmodeled_conduit_layers_near"] = unmodeled_conduit
        ev["modeled_conduit_layers_near"] = modeled_conduit

        # (6) classify
        if not leaders:
            result = R_LEADER_NOT_FOUND
            ev["why"] = (f"callout text found (box layer {box_layer!r}) but no leader on that "
                         f"layer points to a symbol")
        elif sym is None:
            result = R_NOT_RECOVERABLE
            ev["why"] = "leader found but no NEXTLINK symbol cluster sits at its tip"
        elif n_at_tip >= 2:
            result = R_NOT_UNIQUE
            ev["why"] = f"{n_at_tip} NEXTLINK symbol clusters sit at the leader tip -- not unique"
        elif not conduit_near:
            result = R_CONDUIT_NOT_CONNECTED
            ev["why"] = "HH symbol found but no BORE conduit layer is within MAX_DASH_GAP of it"
        else:
            # all present + connected. Decide which dialect gap (if any) blocked binding.
            box_modeled = box_layer in MODELED_STRUCT_TEXT_LAYERS
            conduit_modeled = bool(modeled_conduit) and not unmodeled_conduit
            if box_modeled and conduit_modeled:
                result = R_BINDS
                ev["why"] = "callout/leader/symbol/conduit all on modeled layers -- would bind today"
            elif box_modeled and unmodeled_conduit:
                result = R_REACHES_CONDUIT_UNMODELED
                ev["why"] = (f"callout->leader->symbol bind on modeled layers, but the conduit at "
                             f"the symbol is on UNMODELED layer(s) {unmodeled_conduit}")
            else:
                result = R_DIALECT_GAP
                ev["why"] = (
                    f"every element of log53's start evidence is DRAWN in source, but on layers "
                    f"the dialect does not model for binding: the identity callout+leader are on "
                    f"{box_layer!r} (not a modeled structure-text layer "
                    f"{sorted(MODELED_STRUCT_TEXT_LAYERS)}), and the conduit at the symbol is on "
                    f"{unmodeled_conduit or 'modeled layers'} "
                    f"(modeled conduit layers: {sorted(MODELED_CONDUIT_LAYERS)}). The HH symbol "
                    f"itself IS on the modeled {NEXTLINK_SYMBOL_LAYER!r} layer. The prior blockers "
                    f"were dialect/locator/layer-coverage gaps, NOT missing source.")
                ev["dialect_gaps"] = {
                    "identity_callout_layer_unmodeled": (box_layer, "not in structure_layers text"),
                    "conduit_layers_unmodeled": unmodeled_conduit,
                    "symbol_layer_modeled_ok": NEXTLINK_SYMBOL_LAYER,
                }
    finally:
        plan.close()

    return _emit(gates, result, ev)


def _emit(gates, result, ev) -> int:
    gates.append(("G6 result in allowed enum", result in ALLOWED, result))
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G7 zero PNG / zero stroke (no render lane)", len(pngs) == 0, {"pngs": pngs}))
    all_pass = all(x for _, x, _ in gates)
    report = {
        "milestone": "OWNER-PACKET-2 -- log53 callout-leader / HH-HH conduit source-coverage (proof only)",
        "verdict": "PASS" if all_pass else "FAIL",
        "target": "log53", "sheet": 5,
        "question": ("is log53's start evidence (callout -> leader -> HH symbol -> conduit) drawn in "
                     "source on layers the dialect doesn't model, i.e. were the prior blockers "
                     "dialect/locator/layer-coverage gaps rather than missing source?"),
        "source_coverage_result": result,
        "evidence": ev,
        "no_screenshot_pixels_used": True,
        "no_coordinates_invented": True,
        "dialect_wired": False,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "log53_callout_leader_hh_symbol_slice.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[log53-callout] source_coverage_result: {result}")
    if ev.get("why"):
        print(f"[log53-callout] why: {ev['why'][:220]}")
    for k in ("callout_box_layer", "leaders_found", "hh_symbol_layer",
              "conduit_layers_near_symbol", "unmodeled_conduit_layers_near"):
        if k in ev:
            print(f"[log53-callout]   {k}: {ev[k]}")
    for n, x, _ in gates:
        print(f"[log53-callout] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[log53-callout] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
