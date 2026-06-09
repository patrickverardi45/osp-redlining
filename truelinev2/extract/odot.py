"""ODOT plan dialect (positional), with alignment gating + legend exclusion.

ODOT disaggregates bore evidence; the reliable explicit signal is the authored
phrase ``DIRECTIONAL BORE``. For each adjacent ``DIRECTIONAL`` ``BORE`` word pair
we KEEP it as a real alignment bore note only if BOTH hold:
  * Gate A — alignment association (req 4): a station tick lies within a generous
    neighborhood. Legend keys / title blocks sit away from the alignment, so this
    is the authoritative include test.
  * Gate B — not inside a detected legend/key block (req 1/3).
The surviving anchor's x is projected onto the station axis -> a POINT-extent
canonical Callout. match_mode="containment": a bore log places at the
directional-bore anchor within its span (location-only REVIEW). No real,
alignment-associated anchor in span -> abstain.
"""
from __future__ import annotations

from typing import List

from truelinev2.extract.legend import detect_legend_block, point_in_bbox
from truelinev2.extract.station_axis import fit_axis, parse_tick
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.schema.models import Callout
from truelinev2.stations import feet_to_station

# Gate A neighborhood (display pts): a real alignment callout has a station tick
# nearby; legend/title corners do not. Generous so real bore notes survive.
_TICK_DX = 450.0
_TICK_DY = 350.0


class OdotDialect:
    name = "odot"
    match_mode = "containment"

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
        if not words:
            return []
        tick_words = [w for w in words if parse_tick(w["text"]) is not None]
        axis = fit_axis([(w["xc"], parse_tick(w["text"])) for w in tick_words])
        if axis is None:
            return []
        legend = detect_legend_block(words)  # tightened key block, may be None

        callouts: List[Callout] = []
        for i in range(len(words) - 1):
            if words[i]["text"].upper() != "DIRECTIONAL" or words[i + 1]["text"].upper() != "BORE":
                continue
            w0, w1 = words[i], words[i + 1]
            cx = (w0["xc"] + w1["xc"]) / 2.0
            cy = (w0["yc"] + w1["yc"]) / 2.0
            # Gate A: alignment association (authoritative include test)
            near_tick = any(abs(t["xc"] - cx) <= _TICK_DX and abs(t["yc"] - cy) <= _TICK_DY
                            for t in tick_words)
            if not near_tick:
                continue
            # Gate B: legend/key exclusion
            if legend is not None and point_in_bbox(cx, cy, legend, pad=8.0):
                continue
            sta = axis.station_at(cx)
            label = feet_to_station(sta)
            qualifier = words[i - 1]["text"] if i > 0 else ""
            bbox = [min(w0["x0"], w1["x0"]), min(w0["y0"], w1["y0"]),
                    max(w0["x1"], w1["x1"]), max(w0["y1"], w1["y1"])]
            callouts.append(Callout(
                sheet=sheet, page=sheet + offset, from_sta=label, to_sta=label,
                from_ft=round(sta, 1), to_ft=round(sta, 1), footage=0.0,
                conduit=None, vacant=False, footage_verified=False,
                text=f"{qualifier} DIRECTIONAL BORE @ ~{label} (ODOT)".strip(),
                bbox=bbox, dialect="odot"))
        return callouts
