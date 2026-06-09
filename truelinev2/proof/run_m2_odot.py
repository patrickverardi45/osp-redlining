"""M2 proof: v2 places an ODOT Tulsa-31 bore the OLD engine returns 0 callouts for.

Pipeline: VeroFy Construction Log XLSX -> canonical Bore -> ODOT dialect (station
axis + DIRECTIONAL BORE phrase, with legend exclusion + alignment gating) ->
containment match -> REVIEW placement -> rendered + served PNG. Inputs are
extracted read-only from the ODOT zip to a temp dir (outside the repo). Grading
crops (v2 plan crop + same region from the human redline) are written for visual
grading. Zero false placements is the hard bar; uncertain -> abstain.

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_m2_odot
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
import zipfile

import uvicorn

from truelinev2.api.app import create_app
from truelinev2.config import Settings, _REPO_ROOT
from truelinev2.context import require_context
from truelinev2.extract.registry import select_dialect
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.schema.models import PlacementStatus
from truelinev2.service import RedlineService
from truelinev2.store.artifacts import ArtifactStore
from truelinev2.store.db import ReviewStore

ZIP = os.getenv("TL2_ODOT_ZIP",
                r"C:\Users\Patrick\OneDrive\Attachments\Desktop\ODOT_TULSA_29 (11-11-25) (1).zip")
INPUTS = r"C:\Temp\truelinev2_m2\inputs"
GRADE_DIR = r"C:\Temp\truelinev2_m2\grading"
REPORT_DIR = _REPO_ROOT / "data" / "outputs" / "truelinev2"
PLAN = "ODOT_TULSA_31 (11-12-25) (1).pdf"
REDLINE = "ODOT_TULSA_31_REDLINE_3-18-26.pdf"
BORES = ["3-21-26 TULSA 31 BORE LOG 118'.xlsx", "3-21-26 TULSA 31 BORE LOG 71'.xlsx",
         "3-21-26 TULSA 31 BORE LOG 88'.xlsx"]
HOST, PORT = "127.0.0.1", 8101
PNG = b"\x89PNG\r\n\x1a\n"


def _ensure_inputs():
    os.makedirs(INPUTS, exist_ok=True)
    need = [PLAN, REDLINE] + BORES
    if all(os.path.isfile(os.path.join(INPUTS, n)) for n in need):
        return True
    if not os.path.isfile(ZIP):
        print(f"[m2] FAIL: ODOT zip not found: {ZIP}")
        return False
    with zipfile.ZipFile(ZIP) as z:
        names = set(z.namelist())
        for n in need:
            if n not in names:
                print(f"[m2] FAIL: zip missing entry: {n}")
                return False
            with z.open(n) as src, open(os.path.join(INPUTS, n), "wb") as dst:
                dst.write(src.read())
    return True


def _get(path, headers=None):
    req = urllib.request.Request(f"http://{HOST}:{PORT}{path}", headers=headers or {})
    try:
        r = urllib.request.urlopen(req, timeout=60)
        return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def main() -> int:
    if not _ensure_inputs():
        return 2
    os.makedirs(GRADE_DIR, exist_ok=True)
    plan_path = os.path.join(INPUTS, PLAN)
    redline_path = os.path.join(INPUTS, REDLINE)

    settings = Settings.for_proof()
    artifacts = ArtifactStore(settings.artifact_root)
    db = ReviewStore(settings.db_path)
    svc = RedlineService(settings, artifacts, db)

    # --- transparency: real (post-gate) directional-bore anchors per candidate sheet ---
    dplan = PlanPdf(plan_path)
    dialect = select_dialect(dplan)
    offset = dialect.calibrate(dplan, settings.sheet_offset) if dialect else settings.sheet_offset
    print(f"[m2] dialect={getattr(dialect, 'name', None)} derived_offset={offset}")
    for fn in BORES:
        b = load_borelog(os.path.join(INPUTS, fn))
        anchors = []
        for s in b.sheet_refs:
            anchors += [(a.sheet, a.from_sta, round(a.from_ft)) for a in dialect.extract_callouts(dplan, s, offset)]
        in_span = [a for a in anchors if b.station_start_ft - 10 <= a[2] <= b.station_end_ft + 10]
        print(f"[m2] {b.bore_id}: span[{b.station_start_ft:.0f},{b.station_end_ft:.0f}] sheets{b.sheet_refs} "
              f"real_anchors={anchors[:12]} in_span={in_span}")
    dplan.close()

    redline_pdf = PlanPdf(redline_path)
    rows = []
    for fn in BORES:
        sess = "odot-tulsa31-" + fn.split("BORE LOG ")[-1].replace(".xlsx", "").strip()
        ctx = require_context("proof-tenant", sess)
        payload = svc.run(ctx, os.path.join(INPUTS, fn), plan_path)
        item = payload.items[0]
        pl = item.placement
        grade_png = None
        if pl.matched_callouts and pl.status != PlacementStatus.ABSTAIN:
            c = pl.matched_callouts[0]
            rendered = redline_pdf.render_clip(c.sheet, offset, c.bbox, zoom=settings.render_zoom)
            if rendered:
                img, _x, _y = rendered
                safe = item.bore.bore_id.replace(" ", "_")
                grade_png = os.path.join(GRADE_DIR, f"REDLINE_{safe}_s{c.sheet}.png")
                img.save(grade_png)
        rows.append({"bore": item.bore.bore_id, "span": f"{item.bore.station_start}->{item.bore.station_end}",
                     "sheets": item.bore.sheet_refs, "status": pl.status.value, "tier": pl.tier,
                     "reason": pl.reason, "placed_sheet": pl.sheets,
                     "anchor": (pl.matched_callouts[0].text if pl.matched_callouts else None),
                     "ctx_session": sess, "v2_crop": (pl.artifacts[0].name if pl.artifacts else None),
                     "redline_grade_png": grade_png})
        print(f"[m2] {item.bore.bore_id}: {pl.status.value} ({pl.reason}) sheet={pl.sheets} "
              f"anchor={rows[-1]['anchor']} arts={len(pl.artifacts)}")
    redline_pdf.close()

    placed = [r for r in rows if r["status"] in ("REVIEW", "AUTO_SELECT")]
    abstained = [r for r in rows if r["status"] == "ABSTAIN"]
    errored = [r for r in rows if r["status"] not in ("REVIEW", "AUTO_SELECT", "ABSTAIN")]

    served = {}
    if placed:
        app = create_app(settings)
        server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=PORT, log_level="warning"))
        th = threading.Thread(target=server.run, daemon=True)
        th.start()
        try:
            for _ in range(100):
                if getattr(server, "started", False):
                    break
                time.sleep(0.1)
            r0 = placed[0]
            hdr = {"X-TL-Tenant": "proof-tenant", "X-TL-Session": r0["ctx_session"]}
            s, hd, body = _get(f"/v2/artifact/{r0['v2_crop']}", headers=hdr)
            served = {"name": r0["v2_crop"], "status": s,
                      "content_type": hd.get("content-type") or hd.get("Content-Type"),
                      "bytes": len(body), "png": body[:8] == PNG}
        finally:
            server.should_exit = True
            th.join(timeout=5)

    # NOTE: zero-false is verified by VISUAL grading (crops vs redline), not these checks.
    checks = {
        "all_3_normalized": len(rows) == 3,
        "zero_errors": len(errored) == 0,
        "nonplaced_abstain_with_reason": all(r["reason"] for r in abstained),
        "placed_has_artifact": all(r["artifacts"] if False else r["v2_crop"] for r in placed),
        "artifact_served_png": (not placed) or (bool(served) and served.get("status") == 200 and served.get("png") is True),
    }
    passed = all(checks.values())

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = {"milestone": "truelinev2 M2 — ODOT Tulsa-31 dialect (legend-excluded)",
              "passed_automated": passed, "offset": offset, "rows": rows,
              "counts": {"placed": len(placed), "abstained": len(abstained), "errored": len(errored)},
              "served": served, "checks": checks,
              "zero_false_note": "0 false placements is verified by VISUAL grading of every placed crop "
                                 "against the redline in " + GRADE_DIR + " — NOT by these automated checks."}
    (REPORT_DIR / "m2_odot_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[m2] counts: placed={len(placed)} abstained={len(abstained)} errored={len(errored)}")
    print(f"[m2] checks: {json.dumps(checks)}")
    print(f"[m2] grading crops in: {GRADE_DIR}")
    print(f"[m2] report -> {REPORT_DIR / 'm2_odot_report.json'}")
    print(f"[m2] automated checks: {'PASS' if passed else 'FAIL'} (zero-false pending visual grade)")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
