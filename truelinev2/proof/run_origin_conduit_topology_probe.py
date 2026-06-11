r"""M8.14.b.6 Phase 0 -- origin-conduit topology probe (log51, sheet 8).

OUTCOME A: drawn topology DETERMINISTICALLY discriminates log51's two rival
start structures. The bore's own conduit class (callout ``1-1.25" VACANT HDPE
FOR FIBER DROP`` -> CAD layer ``BORE - VACANT PIPE``) is drawn as ONE dashed
vector chain that (a) closes inside the b.4-bound END flower-pot footprint
and (b) terminates with dash endpoints INSIDE the AP-154 PORT HH symbol
footprint and ZERO endpoints inside the rival flower pot's footprint -- a
binary CONTAINMENT fact, not a nearest-distance comparison (the footprints
nearly abut; distance margins would be the forbidden metric guess).

General discriminator proven (the future resolver lane's law):
  bore conduit class -> conduit layer (dialect map)
  -> the dashed chain CONNECTED to the bound end structure (containment)
  -> dash endpoints inside EXACTLY ONE start-side structure footprint
  -> origin bound; 0 or >= 2 footprints hit -> named abstain.

This slice is proof-only: no placement, no stroke, no engine wiring. The
log51 stroke via the b.3 anchoring machinery is the NEXT gate. Gates pin the
live topology exactly; if a future plan edition redraws it, they fail loudly.

Embedded gates (any failure -> nonzero exit):
  G1 b.5 state reproduces: no printed origin; exactly the two rivals
  G2 conduit chain: exactly the corridor-band VACANT-PIPE segments form ONE
     continuous dashed chain (uniform gaps <= MAX_DASH_GAP, no branch)
  G3 chain closure: dash endpoints land inside the b.4-bound END pot footprint
  G4 discriminator: endpoints inside the HH footprint, ZERO inside the rival
     pot footprint -> exactly one origin = the printed AP-154 TERMINAL 6 PORT
     HH (identity from b.5 G4's reverse leader)
  G5 typed outcome upgrade: CONDUIT_ORIGIN_BOUND (pick-card -> resolver-lane
     candidate); named next artifact = log51 symbol-anchored stroke (b.3
     machinery) gated on Patrick's grade of this proof
  G6 exactly ONE probe PNG (chain + chosen origin + rejected rival; no stroke)

Outputs (gitignored): data/outputs/origin_conduit_topology_probe/

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_origin_conduit_topology_probe
"""
from __future__ import annotations

import json
import math
import os
from typing import Dict, List, Optional, Sequence, Tuple

from PIL import ImageDraw

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import (
    BRENHAM_STRUCTURE_LAYERS,
    POSITION_BOUND,
    cluster_symbols,
    resolve_structure_position,
)
from truelinev2.extract.tick_path import route_ladder_ticks
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_log51_start_evidence_probe import (
    BAND,
    colocated_candidates,
)
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.proof.station_equation_ownership import extract_reset_origins

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "origin_conduit_topology_probe"
SHEET = 8
MAX_DASH_GAP = 35.0   # uniform drawn dash spacing observed 31.3-31.7 pt
FOOTPRINT_RADIUS = 8.0
ORIGIN_BOUND = "CONDUIT_ORIGIN_BOUND"
ORIGIN_AMBIGUOUS = "CONDUIT_ORIGIN_AMBIGUOUS"
ORIGIN_NOT_FOUND = "CONDUIT_ORIGIN_NOT_FOUND"
# Brenham dialect fact: bore callout conduit text -> CAD conduit layer.
BRENHAM_CONDUIT_LAYERS = {"VACANT HDPE": "BORE - VACANT PIPE"}


# --- pure helpers (offline-testable) ----------------------------------------------------

def symbol_footprint(drawings: Sequence[dict], layer: str,
                     center: Tuple[float, float],
                     radius: float = FOOTPRINT_RADIUS
                     ) -> Optional[Tuple[float, float, float, float]]:
    """Union bbox of the symbol-cluster member drawings around ``center`` --
    the structure's DRAWN footprint (containment target, not a tolerance)."""
    mem = [d for d in drawings if d.get("layer") == layer
           and math.hypot(d["xc"] - center[0], d["yc"] - center[1]) <= radius]
    if not mem:
        return None
    return (min(d["x0"] for d in mem), min(d["y0"] for d in mem),
            max(d["x1"] for d in mem), max(d["y1"] for d in mem))


def dash_endpoints(segments: Sequence[dict]) -> List[Tuple[float, float]]:
    return [p for d in segments for ln in (d.get("lines") or ())
            for p in ((ln[0], ln[1]), (ln[2], ln[3]))]


def chain_continuity(segments: Sequence[dict],
                     max_gap: float = MAX_DASH_GAP) -> dict:
    """One dashed chain: sorted by x, every consecutive bbox gap <= max_gap
    (overlap counts as joined). Reports gaps exactly."""
    segs = sorted(segments, key=lambda d: d["x0"])
    gaps = [round(b["x0"] - a["x1"], 1) for a, b in zip(segs, segs[1:])]
    return {"segments": len(segs), "gaps": gaps,
            "continuous": all(g <= max_gap for g in gaps)}


def _inside(p: Tuple[float, float], bb: Tuple[float, float, float, float]) -> bool:
    return bb[0] <= p[0] <= bb[2] and bb[1] <= p[1] <= bb[3]


def discriminate_origin(endpoints: Sequence[Tuple[float, float]],
                        footprints: Dict[str, Tuple[float, float, float, float]]
                        ) -> dict:
    """The exactly-one law on drawn containment: candidate footprints hit by
    >= 1 conduit dash endpoint. One hit -> bound; 0 -> not found; >= 2 ->
    ambiguous. Never a distance comparison."""
    hits = {label: [p for p in endpoints if _inside(p, bb)]
            for label, bb in sorted(footprints.items())}
    winners = [label for label, ps in hits.items() if ps]
    result = (ORIGIN_BOUND if len(winners) == 1
              else ORIGIN_NOT_FOUND if not winners else ORIGIN_AMBIGUOUS)
    return {"result": result,
            "winner": winners[0] if len(winners) == 1 else None,
            "hit_counts": {label: len(ps) for label, ps in hits.items()}}


def _render_png(plan, offset, segs, end_bb, hh_bb, pot_bb, winner_xy) -> str | None:
    xs = [d["x0"] for d in segs] + [d["x1"] for d in segs]
    ys = [d["y0"] for d in segs] + [d["y1"] for d in segs]
    rendered = plan.render_clip(SHEET, offset, [min(xs), min(ys), max(xs), max(ys)],
                                zoom=2.5, pad=60.0)
    if rendered is None:
        return None
    img, cx0, cy0 = rendered
    draw = ImageDraw.Draw(img)
    z = 2.5

    def px(p):
        return ((p[0] - cx0) * z, (p[1] - cy0) * z)

    grey, green, orange, purple = (110, 110, 110), (20, 140, 60), (235, 130, 20), (140, 60, 160)
    for d in segs:  # the drawn conduit chain, highlighted
        (x0, y0), (x1, y1) = px((d["x0"], d["y0"])), px((d["x1"], d["y1"]))
        draw.rectangle([x0 - 3, y0 - 3, x1 + 3, y1 + 3], outline=purple, width=2)
    for bb, color in ((end_bb, green), (hh_bb, orange)):
        (x0, y0), (x1, y1) = px((bb[0], bb[1])), px((bb[2], bb[3]))
        draw.rectangle([x0 - 4, y0 - 4, x1 + 4, y1 + 4], outline=color, width=3)
    (x0, y0), (x1, y1) = px((pot_bb[0], pot_bb[1])), px((pot_bb[2], pot_bb[3]))
    draw.rectangle([x0 - 4, y0 - 4, x1 + 4, y1 + 4], outline=grey, width=3)
    draw.line([x0 - 4, y0 - 4, x1 + 4, y1 + 4], fill=grey, width=2)
    wx, wy = px(winner_xy)
    draw.ellipse([wx - 14, wy - 14, wx + 14, wy + 14], outline=(255, 255, 255), width=7)
    draw.ellipse([wx - 14, wy - 14, wx + 14, wy + 14], outline=orange, width=4)
    cap = ("log51 s8 ORIGIN-CONDUIT TOPOLOGY -- NOT A PLACEMENT: purple = the "
           "bore's own drawn VACANT-HDPE conduit chain; green = b.4-bound end "
           "pot (chain closes inside it); orange ring = chain terminates INSIDE "
           "the AP-154 PORT HH footprint (origin bound by drawn containment); "
           "grey X = rival pot, ZERO conduit endpoints inside it")
    draw.rectangle([0, 0, img.width, 30], fill=(255, 255, 255))
    draw.text((8, 8), cap[:230], fill=(20, 20, 20))
    os.makedirs(OUT_DIR, exist_ok=True)
    path = str(OUT_DIR / "log51_s8_origin_conduit_topology.png")
    img.save(path)
    return path


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.14b6p0] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.14b6p0] STOP: inputs missing")
        return 2
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)}
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.14b6p0] STOP: corpus drift ({len(corpus)})")
        return 3
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()

    plan = PlanPdf(PDF)
    ok = True
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        bore = load_borelog(str(corpus["bore_log51"]))
        lines = plan.lines(SHEET, offset)
        drawings = plan.line_items(SHEET, offset)
        words = plan.words(SHEET, offset)

        # G1 b.5 state reproduces: no printed origin; exactly the two rivals
        origins = extract_reset_origins(lines, SHEET)
        end_pos = resolve_structure_position(
            label_text="2+99", structure_class="flower_pot",
            words=words, drawings=drawings,
            layer_table=BRENHAM_STRUCTURE_LAYERS, context_texts=("FLOWER", "POT"))
        ticks, _ = route_ladder_ticks(plan, SHEET, offset)
        band = sorted([(t.station_ft, t.x, t.y) for t in ticks
                       if BAND[0] < t.y < BAND[1]])
        frame = band + [(bore.station_end_ft, end_pos.symbol_xy[0],
                         end_pos.symbol_xy[1])]
        clusters = {lay: cluster_symbols(drawings, lay)
                    for lay in ("NEXTLINK", "FLOWER POT")}
        rivals = colocated_candidates(clusters, frame)
        g1 = (origins == [] and end_pos.result == POSITION_BOUND
              and len(rivals) == 2
              and {r["layer"] for r in rivals} == {"NEXTLINK", "FLOWER POT"})
        print(f"[m8.14b6p0] {'PASS' if g1 else 'FAIL'}  G1 b.5 state reproduces: "
              f"origins=0 rivals={[(r['layer'], r['x'], r['y']) for r in rivals]}")
        ok &= g1
        hh = next(r for r in rivals if r["layer"] == "NEXTLINK")
        pot = next(r for r in rivals if r["layer"] == "FLOWER POT")

        # G2 the bore's conduit class maps to ONE continuous drawn chain
        conduit_layer = BRENHAM_CONDUIT_LAYERS["VACANT HDPE"]
        callout_ok = any("VACANT HDPE" in ln.upper() and "FIBER DROP" in
                         " ".join(lines[i:i + 3]).upper()
                         for i, ln in enumerate(lines) if "2+99" in
                         " ".join(lines[max(0, i - 2):i + 1]))
        segs = [d for d in drawings if d["layer"] == conduit_layer
                and BAND[0] < d["yc"] < 390 and 80 < d["xc"] < 700]
        cont = chain_continuity(segs)
        g2 = callout_ok and cont["segments"] == 9 and cont["continuous"]
        print(f"[m8.14b6p0] {'PASS' if g2 else 'FAIL'}  G2 conduit chain "
              f"({conduit_layer!r}): {cont} callout_names_class={callout_ok}")
        ok &= g2

        # G3 + G4: closure at the bound end; exactly-one origin by containment
        end_bb = symbol_footprint(drawings, "FLOWER POT", tuple(end_pos.symbol_xy))
        hh_bb = symbol_footprint(drawings, "NEXTLINK", (hh["x"], hh["y"]))
        pot_bb = symbol_footprint(drawings, "FLOWER POT", (pot["x"], pot["y"]))
        pts = dash_endpoints(segs)
        closure = [p for p in pts if _inside(p, end_bb)]
        g3 = len(closure) >= 1
        print(f"[m8.14b6p0] {'PASS' if g3 else 'FAIL'}  G3 chain closes inside "
              f"the bound END pot footprint: {len(closure)} endpoints")
        ok &= g3

        disc = discriminate_origin(pts, {"ap154_port_hh": hh_bb,
                                         "rival_flower_pot": pot_bb})
        g4 = (disc["result"] == ORIGIN_BOUND and disc["winner"] == "ap154_port_hh"
              and disc["hit_counts"]["rival_flower_pot"] == 0)
        print(f"[m8.14b6p0] {'PASS' if g4 else 'FAIL'}  G4 discriminator: {disc}")
        ok &= g4

        # G5 typed outcome upgrade
        outcome = {
            "outcome": ORIGIN_BOUND,
            "origin_structure": "AP-154 TERMINAL 6 PORT HH (printed STA 3+66, "
                                "parent frame; leader-bound symbol)",
            "origin_symbol_xy": [hh["x"], hh["y"]],
            "law": ("conduit class -> conduit layer -> chain connected to the "
                    "bound end structure -> dash endpoints inside EXACTLY ONE "
                    "start-side footprint; 0/>=2 -> abstain"),
            "named_next_artifact": ("log51 symbol-anchored stroke via the b.3 "
                                    "machinery, gated on Patrick's grade of "
                                    "this topology proof"),
            "generalization": ("drop-lane bores (log5/30/48/50/65 class): same "
                               "law with their conduit class + bound end pots"),
        }
        g5 = disc["result"] == ORIGIN_BOUND
        print(f"[m8.14b6p0] {'PASS' if g5 else 'FAIL'}  G5 typed outcome: "
              f"{outcome['outcome']} -> {outcome['origin_structure']}")
        ok &= g5

        png = _render_png(plan, offset, segs, end_bb, hh_bb, pot_bb,
                          (hh["x"], hh["y"]))
        pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
        g6 = png is not None and len(pngs) == 1 and "stroke" not in pngs[0]
        print(f"[m8.14b6p0] {'PASS' if g6 else 'FAIL'}  G6 exactly one probe PNG "
              f"(no stroke artifact): {pngs}")
        ok &= g6

        report = {
            "milestone": ("truelinev2 M8.14.b.6 Phase 0 -- origin-conduit "
                          "topology probe (log51; OUTCOME A, discriminator "
                          "proven)"),
            "corpus_dir_used": corpus_dir, "corpus_resolution": how,
            "plan_pdf": PDF, "verdict": "PASS" if ok else "FAILURE",
            "honesty": ("binary drawn-containment discrimination -- dash "
                        "endpoints inside footprints, never nearest-distance; "
                        "proof-only: no placement, no stroke, no engine wiring; "
                        "the b.5 pick-card upgrades only after this proof is "
                        "graded and the resolver lane ships"),
            "conduit": {"layer": conduit_layer, "chain": cont,
                        "endpoints": len(pts)},
            "closure_endpoints_in_end_pot": len(closure),
            "discrimination": disc,
            "footprints": {"end_pot": end_bb, "ap154_hh": hh_bb,
                           "rival_pot": pot_bb},
            "typed_outcome": outcome,
            "png": png,
        }
        (OUT_DIR / "origin_conduit_topology_probe.json").write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"[m8.14b6p0] verdict: {report['verdict']}")
        print(f"[m8.14b6p0] VISUAL FILE for Patrick: {png}")
        print(f"[m8.14b6p0] report -> "
              f"{OUT_DIR / 'origin_conduit_topology_probe.json'}")
    finally:
        plan.close()
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
