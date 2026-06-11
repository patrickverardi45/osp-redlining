r"""M8.14.b.2 -- structure symbol POSITION resolution (pure; uniqueness-mandatory).

Resolves the DRAWN symbol position of a structure whose IDENTITY is already
bound by printed evidence (M8.14.b.1). The r3 lesson is law here: labels are
leader-offset -- a stroke may NEVER be drawn to a label centroid. The only
honest position is the symbol the label's own LEADER LINE points at.

Chain of custody (every hop uniqueness-mandatory; 0 or >= 2 -> named abstain):

  identity-bound label TEXT
    -> the unique positioned word carrying that text
    -> the unique same-layer LABEL BOX drawing containing the word
    -> the unique same-layer LEADER LINE exiting that box (box edges have both
       endpoints on the box and are excluded by construction)
    -> the unique SYMBOL CLUSTER (symbol-layer drawings grouped by proximity)
       at the leader tip
    -> symbol CLASS check: the cluster's fill must match the expected class
       color (e.g. Brenham: red = INSTALLER HH, blue = TERMINAL PORT HH)

Layer names and class colors are PLAN-DIALECT facts (Brenham/NEXTLINK table
below) -- they live here in extract/ (the convention seam), never in core.
No v1 import; no rendering; no engine wiring.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

POSITION_BOUND = "STRUCTURE_POSITION_BOUND"
LABEL_WORD_NOT_UNIQUE = "LABEL_WORD_NOT_UNIQUE"
LABEL_BOX_NOT_UNIQUE = "LABEL_BOX_NOT_UNIQUE"
LEADER_NOT_UNIQUE = "LEADER_NOT_UNIQUE"
SYMBOL_NOT_UNIQUE = "SYMBOL_NOT_UNIQUE"
SYMBOL_CLASS_MISMATCH = "SYMBOL_CLASS_MISMATCH"

# Probe-calibrated geometry constants (2026-06-10 sheet-10 probe). Widening is
# forbidden; tightening is a future named decision.
BOX_MIN_W = 10.0        # label boxes are ~51x15 pt; glyph fills are ~3x4 pt
BOX_MIN_H = 6.0
BOX_MARGIN = 6.0        # endpoint-inside-box tolerance for leader attachment
LEADER_MIN_LEN = 8.0    # shorter same-layer strokes are glyph work, not leaders
CLUSTER_RADIUS = 8.0    # symbol-block drawings sit within ~2 pt of each other
TIP_TOL = 8.0           # leader tip -> symbol cluster center
FILL_TOL = 0.06         # per-channel RGB tolerance for the class color check

# Brenham/NEXTLINK dialect table: structure class -> (label TEXT layer,
# symbol layer, class fill RGB). Dialect facts, allowed in extract/ only.
# flower_pot (M8.14.b.4): own symbol layer; the symbol block's class fill is
# black (probe-verified uniform across all sheet-8 clusters) -- the LAYER is
# the primary class discriminator, the fill check stays belt-and-braces.
BRENHAM_STRUCTURE_LAYERS: Dict[str, Tuple[str, str, Tuple[float, float, float]]] = {
    "installer_hh": ("INSTALLER HH - TEXT", "NEXTLINK", (1.0, 0.0, 0.0)),
    "terminal_port_hh": ("PORT HH - TEXT", "NEXTLINK", (0.15294, 0.46275, 0.73333)),
    "flower_pot": ("FLOWER POT - TEXT", "FLOWER POT", (0.0, 0.0, 0.0)),
}

# Brenham dialect table (M8.14.b.8, re-homed from the b.6 proof): bore-callout
# conduit text -> CAD conduit layer. Another plan set configures BOTH tables;
# the topology laws in extract/conduit_topology.py never name a layer.
BRENHAM_CONDUIT_LAYERS: Dict[str, str] = {"VACANT HDPE": "BORE - VACANT PIPE"}


@dataclass(frozen=True)
class SymbolCluster:
    x: float
    y: float
    drawings: int
    fills: Tuple[Tuple[float, float, float], ...] = ()


@dataclass(frozen=True)
class StructurePositionVerdict:
    """Typed answer. ``symbol_xy`` is non-None ONLY for POSITION_BOUND; drawing
    a stroke endpoint from any other verdict is forbidden."""
    label_text: str
    structure_class: str
    result: str
    symbol_xy: Optional[Tuple[float, float]] = None
    word_xy: Optional[Tuple[float, float]] = None
    label_box: Optional[Tuple[float, float, float, float]] = None
    leader: Optional[Tuple[float, float, float, float]] = None
    rival_cluster_xys: Tuple[Tuple[float, float], ...] = ()
    named_missing_relationship: Optional[str] = None
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "label_text": self.label_text,
            "structure_class": self.structure_class,
            "result": self.result,
            "symbol_xy": ([round(v, 1) for v in self.symbol_xy]
                          if self.symbol_xy else None),
            "word_xy": ([round(v, 1) for v in self.word_xy] if self.word_xy else None),
            "label_box": ([round(v, 1) for v in self.label_box]
                          if self.label_box else None),
            "leader": ([round(v, 1) for v in self.leader] if self.leader else None),
            "rival_cluster_xys": [[round(x, 1), round(y, 1)]
                                  for x, y in self.rival_cluster_xys],
            "named_missing_relationship": self.named_missing_relationship,
            "detail": self.detail,
        }


def find_label_box(drawings: Sequence[dict], layer: str,
                   word_xy: Tuple[float, float]) -> List[dict]:
    """Same-layer drawings big enough to be a LABEL BOX whose bbox contains the
    identity word's center. Glyph fills fail the size floor by construction."""
    out = []
    for d in drawings:
        if d.get("layer") != layer:
            continue
        if (d["x1"] - d["x0"]) < BOX_MIN_W or (d["y1"] - d["y0"]) < BOX_MIN_H:
            continue
        if d["x0"] <= word_xy[0] <= d["x1"] and d["y0"] <= word_xy[1] <= d["y1"]:
            out.append(d)
    return out


def _in_box(pt: Tuple[float, float], box: Tuple[float, float, float, float],
            m: float = BOX_MARGIN) -> bool:
    return (box[0] - m <= pt[0] <= box[2] + m
            and box[1] - m <= pt[1] <= box[3] + m)


def find_leaders(drawings: Sequence[dict], layer: str,
                 box: Tuple[float, float, float, float]
                 ) -> List[Tuple[float, float, float, float]]:
    """Same-layer line items with EXACTLY ONE endpoint at the box (xor): box
    edges/diagonals have both endpoints on the box and never qualify; glyph
    strokes fail the length floor. Returned oriented (box end first)."""
    out: List[Tuple[float, float, float, float]] = []
    for d in drawings:
        if d.get("layer") != layer:
            continue
        for (ax, ay, bx, by) in d.get("lines") or ():
            a_in, b_in = _in_box((ax, ay), box), _in_box((bx, by), box)
            if not (a_in ^ b_in):
                continue
            if math.hypot(bx - ax, by - ay) < LEADER_MIN_LEN:
                continue
            out.append((ax, ay, bx, by) if a_in else (bx, by, ax, ay))
    return out


def cluster_symbols(drawings: Sequence[dict], layer: str,
                    radius: float = CLUSTER_RADIUS) -> List[SymbolCluster]:
    """Greedy proximity clustering of symbol-layer drawing centers. Symbol
    blocks are tight (~2 pt spread); distinct structures sit tens of points
    apart, so the radius is not a tuning knob in practice."""
    groups: List[List[dict]] = []
    for d in drawings:
        if d.get("layer") != layer:
            continue
        for g in groups:
            if math.hypot(d["xc"] - g[0]["xc"], d["yc"] - g[0]["yc"]) <= radius:
                g.append(d)
                break
        else:
            groups.append([d])
    out = []
    for g in groups:
        fills = tuple(sorted({tuple(round(c, 5) for c in d["fill"])
                              for d in g if d.get("fill")}))
        out.append(SymbolCluster(x=sum(d["xc"] for d in g) / len(g),
                                 y=sum(d["yc"] for d in g) / len(g),
                                 drawings=len(g), fills=fills))
    return out


def _fill_matches(cluster: SymbolCluster,
                  expected: Tuple[float, float, float]) -> bool:
    return any(all(abs(c - e) <= FILL_TOL for c, e in zip(f, expected))
               for f in cluster.fills)


def resolve_structure_position(*, label_text: str, structure_class: str,
                               words: Sequence[dict],
                               drawings: Sequence[dict],
                               layer_table: Dict[str, Tuple[str, str, Tuple[float, float, float]]],
                               context_texts: Tuple[str, ...] = (),
                               ) -> StructurePositionVerdict:
    """Full chain: word -> label box -> leader -> symbol cluster -> class check.
    ``words`` is ``PlanPdf.words`` output; ``drawings`` is ``PlanPdf.line_items``
    output. The class's layer/color expectations come from ``layer_table`` (a
    dialect fact, injected -- this solver holds no convention defaults).

    ``context_texts`` (M8.14.b.4, additive): when the identity text is not
    sheet-unique (e.g. a station like ``2+99`` printed both in a structure note
    and in a run callout), the label box must ALSO contain one word for EACH
    context text (e.g. ``("FLOWER", "POT")``). Without context, duplicated
    identity text still abstains -- the b.2 contract is unchanged."""
    base = dict(label_text=label_text, structure_class=structure_class)
    if structure_class not in layer_table:
        return StructurePositionVerdict(
            **base, result=SYMBOL_CLASS_MISMATCH,
            named_missing_relationship=(
                f"structure class {structure_class!r} has no layer/color entry in "
                f"the dialect table -- position resolution is not modeled for it"))
    text_layer, symbol_layer, expected_fill = layer_table[structure_class]

    hits = [w for w in words if w["text"] == label_text]
    if not hits or (len(hits) > 1 and not context_texts):
        return StructurePositionVerdict(
            **base, result=LABEL_WORD_NOT_UNIQUE,
            named_missing_relationship=(
                f"{len(hits)} positioned words carry the identity text "
                f"{label_text!r} on this sheet -- exactly one is required to "
                f"locate the label (no disambiguating context given); guessing "
                f"is forbidden"),
            detail={"word_hits": len(hits)})

    def _contains(b: dict, w: dict) -> bool:
        return b["x0"] <= w["xc"] <= b["x1"] and b["y0"] <= w["yc"] <= b["y1"]

    pairs = []  # (box drawing, identity word hit)
    for h in hits:
        for b in find_label_box(drawings, text_layer, (float(h["xc"]), float(h["yc"]))):
            if all(any(w["text"] == c and _contains(b, w) for w in words)
                   for c in context_texts):
                pairs.append((b, h))
    if len(pairs) != 1:
        return StructurePositionVerdict(
            **base, result=LABEL_BOX_NOT_UNIQUE,
            named_missing_relationship=(
                f"{len(pairs)} {text_layer!r} label boxes contain the identity "
                f"word{' plus the context words ' + repr(list(context_texts)) if context_texts else ''} "
                f"-- exactly one is required; the label-box geometry does not "
                f"isolate this identity"),
            detail={"box_hits": len(pairs), "word_hits": len(hits)})
    box_d, hit = pairs[0]
    word_xy = (float(hit["xc"]), float(hit["yc"]))
    box = (box_d["x0"], box_d["y0"], box_d["x1"], box_d["y1"])

    leaders = find_leaders(drawings, text_layer, box)
    if len(leaders) != 1:
        return StructurePositionVerdict(
            **base, result=LEADER_NOT_UNIQUE, word_xy=word_xy, label_box=box,
            named_missing_relationship=(
                f"{len(leaders)} same-layer leader lines exit the label box -- "
                f"exactly one is required to point at the drawn symbol; never "
                f"chosen between"),
            detail={"leader_hits": len(leaders)})
    leader = leaders[0]
    tip = (leader[2], leader[3])

    clusters = cluster_symbols(drawings, symbol_layer)
    at_tip = [c for c in clusters
              if math.hypot(c.x - tip[0], c.y - tip[1]) <= TIP_TOL]
    rivals = tuple((c.x, c.y) for c in clusters
                   if math.hypot(c.x - tip[0], c.y - tip[1]) > TIP_TOL)
    if len(at_tip) != 1:
        return StructurePositionVerdict(
            **base, result=SYMBOL_NOT_UNIQUE, word_xy=word_xy, label_box=box,
            leader=leader, rival_cluster_xys=rivals,
            named_missing_relationship=(
                f"{len(at_tip)} {symbol_layer!r} symbol clusters sit at the "
                f"leader tip (tol {TIP_TOL} pt) -- exactly one is required; the "
                f"drawn symbol cannot be isolated"),
            detail={"clusters_at_tip": len(at_tip),
                    "clusters_total": len(clusters)})
    sym = at_tip[0]

    if not _fill_matches(sym, expected_fill):
        return StructurePositionVerdict(
            **base, result=SYMBOL_CLASS_MISMATCH, word_xy=word_xy, label_box=box,
            leader=leader, rival_cluster_xys=rivals,
            named_missing_relationship=(
                f"the symbol at the leader tip does not carry the expected "
                f"{structure_class!r} class fill {expected_fill} (found "
                f"{list(sym.fills)}) -- identity and drawn class disagree; "
                f"binding is refused"),
            detail={"fills_found": [list(f) for f in sym.fills]})

    return StructurePositionVerdict(
        **base, result=POSITION_BOUND, symbol_xy=(sym.x, sym.y), word_xy=word_xy,
        label_box=box, leader=leader, rival_cluster_xys=rivals,
        detail={"cluster_drawings": sym.drawings,
                "fills_found": [list(f) for f in sym.fills]})


def corroborate_pair_scale(start_xy: Tuple[float, float],
                           end_xy: Tuple[float, float], span_ft: float,
                           ladder_scale: float, rel_tol: float = 0.25) -> dict:
    """Belt-and-braces gate: the resolved symbol-pair distance over the bore
    span must agree with the sheet's clean-ladder pts/ft scale. Evidence is
    reported exactly; the tolerance is consulted only for the boolean."""
    dist = math.hypot(end_xy[0] - start_xy[0], end_xy[1] - start_xy[1])
    pair_scale = dist / span_ft if span_ft else 0.0
    ok = (ladder_scale > 0
          and abs(pair_scale - ladder_scale) / ladder_scale <= rel_tol)
    return {"pair_distance_pt": round(dist, 1), "span_ft": span_ft,
            "pair_scale_pt_per_ft": round(pair_scale, 4),
            "ladder_scale_pt_per_ft": round(ladder_scale, 4),
            "rel_tol": rel_tol, "consistent": ok}
