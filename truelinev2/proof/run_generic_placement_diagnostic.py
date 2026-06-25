r"""LOCAL diagnostic (gitignored output): build a REALISTIC non-recognized plan (a tight proposed-bore run
amid full-sheet survey baseline + existing utilities + a profile grid) and SHOW, as annotated proof images,
exactly what the generic-geometry lane detects and selects:

  1_source_plan.png      — the raw plan page
  2_detected_ticks.png   — every station tick (red dots) + the DENSEST tick row (green) used for the axis
  3_candidate_runs.png   — every run-like extent the dialect emits (orange) + the SELECTED one (blue) + the
                           bore-log span band (yellow)
  4_rendered_stroke.png  — the actual rendered REVIEW stroke crop (what the owner sees)

Prints the selection + confidence so a wrong pick / overstated confidence is caught visually AND in data.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_generic_placement_diagnostic
"""
from __future__ import annotations

import io
import os

import fitz
from PIL import Image, ImageDraw

from truelinev2.config import _REPO_ROOT
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.extract.generic_geometry import GenericGeometryDialect, _densest_tick_row
from truelinev2.extract.station_axis import fit_axis, parse_tick
from truelinev2.contracts.uploaded_corpus_engine_handoff import _place_generic, _confidence
from truelinev2.render.crop import render_redline_stroke
from truelinev2.schema.models import Bore

OUT = _REPO_ROOT / "data" / "outputs" / "truelinev2" / "generic_placement_diagnostic"

# Axis: x=120..720 -> stations 1000..1600 (station_at(x) = x + 880). Bore span 11+75..13+25 = x 295..445.
_TICK_Y = 400.0


def realistic_plan_bytes() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=792, height=612)
    page.insert_text((60, 60), "PLAN & PROFILE  -  ALIGNMENT 10+00 thru 16+00 (demo)", fontsize=11)
    # profile grid (light gray) — realistic background noise
    for gx in range(120, 721, 50):
        page.draw_line((gx, 300), (gx, 360), color=(0.8, 0.8, 0.8), width=0.4)
    for gy in range(300, 361, 20):
        page.draw_line((120, gy), (720, gy), color=(0.8, 0.8, 0.8), width=0.4)
    # station ticks + labels (the axis row)
    for ft in range(1000, 1601, 100):
        x = 120 + (ft - 1000) / 100 * 100
        page.draw_line((x, _TICK_Y), (x, _TICK_Y + 12), color=(0, 0, 0), width=0.8)
        page.insert_text((x - 12, _TICK_Y + 26), "%d+%02d" % (ft // 100, ft % 100), fontsize=8)
    # survey BASELINE — full-sheet black line on the tick row (the classic wrong pick)
    page.draw_line((120, _TICK_Y), (720, _TICK_Y), color=(0, 0, 0), width=0.7)
    # existing utilities — full-sheet, near the alignment band
    page.draw_line((120, 372), (720, 372), color=(0.2, 0.5, 0.9), width=0.8)   # blue
    page.draw_line((120, 388), (720, 388), color=(0.1, 0.6, 0.2), width=0.8)   # green
    # PROPOSED BORE — a red run TIGHTLY spanning the bore-log range 11+75..13+25 (x 295..445)
    page.draw_line((295, 384), (445, 384), color=(1, 0, 0), width=1.8)
    out = io.BytesIO()
    doc.save(out)
    doc.close()
    return out.getvalue()


def _bore() -> Bore:
    return Bore(bore_id="b-1", sheet_refs=[1], station_start="11+75", station_end="13+25",
                station_start_ft=1175.0, station_end_ft=1325.0, span_ft=150.0)


def _page_img(plan: PlanPdf, zoom=1.5) -> Image.Image:
    png = plan.render_page_png(1, 0, zoom=zoom)
    return Image.open(io.BytesIO(png)).convert("RGB"), zoom


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    pdf_path = str(OUT / "plan.pdf")
    open(pdf_path, "wb").write(realistic_plan_bytes())
    plan = PlanPdf(pdf_path)
    bore = _bore()
    try:
        # 1. source
        img, zoom = _page_img(plan)
        img.save(OUT / "1_source_plan.png")

        # 2. ticks + densest row
        words = plan.words(1, 0)
        ticks = [(w, parse_tick(w["text"])) for w in words if parse_tick(w["text"]) is not None]
        row, tick_y = _densest_tick_row(words)
        img2 = img.copy(); d2 = ImageDraw.Draw(img2)
        for w, ft in ticks:
            d2.ellipse([w["xc"]*zoom-4, w["yc"]*zoom-4, w["xc"]*zoom+4, w["yc"]*zoom+4], outline=(220, 0, 0), width=2)
        for w, ft in row:
            d2.ellipse([w["xc"]*zoom-6, w["yc"]*zoom-6, w["xc"]*zoom+6, w["yc"]*zoom+6], outline=(0, 160, 0), width=3)
        axis = fit_axis([(w["xc"], ft) for w, ft in row])
        d2.text((10, 10), "ticks=%d densest_row=%d axis_resid=%.2fft" % (len(ticks), len(row),
                 axis.residual_ft if axis else -1), fill=(0, 0, 0))
        img2.save(OUT / "2_detected_ticks.png")

        # 3. candidate runs + BORE-AWARE selection (the shipped _place_generic path) + clipped stroke
        d = GenericGeometryDialect()
        all_runs = d.extract_callouts(plan, 1, 0)            # for display (every run)
        placement, sig = _place_generic(bore, plan, d, 0)    # the real placement (mutates d: sets clipped stroke)
        winner = placement.matched_callouts[0] if placement else None
        clipped = d.centerline_for(winner) if winner else None
        conf = _confidence(placement, winner, bore, d.signals_for(winner)) if winner else None
        img3 = img.copy(); d3 = ImageDraw.Draw(img3)
        if axis:
            xs = (1175.0 - axis.b) / axis.a; xe = (1325.0 - axis.b) / axis.a
            d3.rectangle([min(xs, xe)*zoom, 360*zoom, max(xs, xe)*zoom, 410*zoom], outline=(230, 200, 0), width=3)
        for c in all_runs:
            x0, y0, x1, y1 = [v*zoom for v in c.bbox]
            same = winner is not None and c.bbox == winner.bbox
            d3.rectangle([x0-3, y0-3, x1+3, y1+3], outline=(0, 80, 220) if same else (240, 140, 0),
                         width=4 if same else 2)
        if clipped and len(clipped) >= 2:                    # the CLIPPED stroke (what gets drawn) in magenta
            d3.line([(p[0]*zoom, p[1]*zoom) for p in clipped], fill=(220, 0, 220), width=4)
        d3.text((10, 10), "runs=%d  selected=%s->%s  conf=%s(%.2f)" % (
            len(all_runs), winner.from_sta if winner else None, winner.to_sta if winner else None,
            conf["band"] if conf else "-", conf["score"] if conf else 0.0), fill=(0, 0, 0))
        img3.save(OUT / "3_candidate_runs.png")

        # 4. the ACTUAL rendered REVIEW stroke crop (what the owner sees)
        if winner and clipped:
            png = render_redline_stroke(plan, bore_id="demo", sheet=int(winner.sheet), offset=0,
                                        stroke_points=[(p[0], p[1]) for p in clipped],
                                        status=placement.status.value, reason=placement.reason,
                                        out_dir=str(OUT))
            if png and os.path.exists(png):
                os.replace(png, str(OUT / "4_rendered_stroke.png"))

        print("=== REALISTIC PLAN DIAGNOSTIC (bore-aware placement) ===")
        print("bore span: %s->%s (%.0fft)" % (bore.station_start, bore.station_end, bore.span_ft))
        print("runs detected:", len(all_runs))
        for c in all_runs:
            s = d.signals_for(c)
            print("  run %7s->%-8s len=%4.0fft red=%-5s full_sheet=%s" % (
                c.from_sta, c.to_sta, s.get("run_extent_ft", 0), s.get("is_red"), s.get("full_sheet")))
        print("SELECTED:", (winner.from_sta, winner.to_sta) if winner else None,
              "| reason", placement.reason if placement else None)
        print("selection signals:", sig)
        print("CONFIDENCE:", conf)
        bore_run = next((c for c in all_runs if abs(c.from_ft-1175) < 30 and abs(c.to_ft-1325) < 30), None)
        print("selected IS the tight bore run:",
              winner is not None and bore_run is not None and winner.bbox == bore_run.bbox)
        if clipped:
            print("clipped stroke x-span ft: %.0f -> %.0f (bore 1175->1325)" % (
                axis.station_at(clipped[0][0]), axis.station_at(clipped[-1][0])))
        print("proof images ->", OUT)
    finally:
        plan.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
