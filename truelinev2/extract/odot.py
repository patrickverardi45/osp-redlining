"""ODOT plan dialect — CAD-layer vector extent (the approved Path B realization).

The legend-style approach was abandoned: the proposed bore on the alignment is
drawn in generic black, not isolable by style. Instead we use the PDF's CAD
layers (OCGs), which ``get_drawings()`` tags per path. The proposed directional-
bore RUN sits on a layer whose name indicates a proposed directional bore
(e.g. tokens "DIRECTIONAL BORE", or "PROPOSED" + "DB"). We:
  1. select vector paths on bore-name layers,
  2. keep only those in the alignment band (near the station-tick row) — this
     drops the legend SAMPLE (which lives off-alignment, even though it is on a
     bore-named layer), satisfying "exclude legend even if on the bore layer",
  3. exclude any path inside a detected legend block (defense in depth),
  4. project endpoints onto the station axis -> per-segment drawn extents.
Emitted as extent Callouts; match_mode="extent" (span coverage, AUTO only when
the drawn extent tightly and uniquely matches the bore-log span).
"""
from __future__ import annotations

import re
from typing import List

from truelinev2.extract.legend import detect_legend_block, point_in_bbox
from truelinev2.extract.station_axis import fit_axis, parse_tick
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.schema.models import Callout
from truelinev2.stations import feet_to_station

_ALIGN_BAND = 220.0  # display pts around the station-tick row = the alignment band


def is_bore_layer(name) -> bool:
    """A layer whose NAME indicates a proposed directional bore. Pattern-based
    (no coordinates, no per-project lookup)."""
    u = (name or "").upper()
    if "DIRECTIONAL BORE" in u:
        return True
    tokens = re.split(r"[^A-Z]+", u)
    return "PROPOSED" in u and "DB" in tokens


class OdotDialect:
    name = "odot"
    match_mode = "extent"

    def detect(self, plan: PlanPdf) -> bool:
        for idx in range(plan.page_count):
            if "DIRECTIONAL BORE" in plan.text_by_index(idx).upper():
                return True
        return False

    def calibrate(self, plan: PlanPdf, default_offset: int) -> int:
        from truelinev2.extract.sheet_map import derive_offset
        off, _ev = derive_offset(plan)
        return off if off is not None else default_offset

    def extract_callouts(self, plan: PlanPdf, sheet: int, offset: int) -> List[Callout]:
        words = plan.words(sheet, offset)
        tick_words = [w for w in words if parse_tick(w["text"]) is not None]
        axis = fit_axis([(w["xc"], parse_tick(w["text"])) for w in tick_words])
        if axis is None or not tick_words:
            return []
        tick_y = sum(w["yc"] for w in tick_words) / len(tick_words)
        legend = detect_legend_block(words)

        callouts: List[Callout] = []
        for s in plan.vector_segments(sheet, offset):
            if not is_bore_layer(s["layer"]):
                continue
            if abs(s["yc"] - tick_y) > _ALIGN_BAND:          # alignment-band gate (drops legend sample)
                continue
            if legend is not None and point_in_bbox(s["xc"], s["yc"], legend, pad=8.0):
                continue                                      # legend-block exclusion (defense)
            sa, sb = axis.station_at(s["x0"]), axis.station_at(s["x1"])
            f0, f1 = (sa, sb) if sa <= sb else (sb, sa)
            callouts.append(Callout(
                sheet=sheet, page=sheet + offset,
                from_sta=feet_to_station(f0), to_sta=feet_to_station(f1),
                from_ft=round(f0, 1), to_ft=round(f1, 1), footage=round(f1 - f0, 1),
                conduit=None, vacant=False, footage_verified=False,
                text=f"DRAWN DIRECTIONAL BORE {feet_to_station(f0)}->{feet_to_station(f1)} [layer {s['layer']}]",
                bbox=[s["x0"], s["y0"], s["x1"], s["y1"]], dialect="odot"))
        return callouts
