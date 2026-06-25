r"""LOCAL seed (gitignored store): stand up a GENERAL uploaded-project demo job whose plan matches NO named
dialect, so a running backend genuinely routes it through the name-free generic-geometry fallback (REVIEW
candidate + graded confidence). Used by the browser smoke + gated staging.

It builds two name-free synthetic inputs in-process:
  * a plan PDF with a station-tick axis + a red drawn 'run' (NO 'DIRECTIONAL BORE' / 'DIR. BORE' / 'STA..TO
    STA' text, so select_dialect returns None -> generic fallback),
  * a Brenham-flat bore-log xlsx (station/depth/print) whose span sits under the drawn run.
Then it creates the customer project + job, uploads both, and passes the reviewed-bore-log gate to
engine_ready. It does NOT generate the candidate, so the workspace 'Generate' button exercises the real
generic lane live.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.seed_general_upload_demo
Then serve THIS store:
  $env:TL2_ALLOWED_ORIGINS="http://127.0.0.1:3000,http://localhost:3000"
  $env:TL2_PRODUCT_PIPELINE_API_OPTIN="1"
  $env:TL2_PRODUCT_STORE_ROOT="<printed store path>"
  .\venv\Scripts\python.exe -m uvicorn truelinev2.api.app:create_app --factory --host 127.0.0.1 --port 8100
"""
from __future__ import annotations

import io
import shutil

import fitz
import openpyxl

from truelinev2.config import _REPO_ROOT
from truelinev2.contracts.customer_project import create_customer_project
from truelinev2.contracts.processing_job import create_job
from truelinev2.contracts.upload_pipeline import accept_upload
from truelinev2.contracts.extracted_row import CONFIRMED, MANUAL_ENTRY, new_extracted_row
from truelinev2.contracts.reviewed_bore_log import (
    GROUPING_CONFIRMED, SEPARATE_BORE, add_extracted_rows, create_reviewed_bore_log,
    define_segment_group, review_row_in_log, set_grouping_status,
)

STORE = _REPO_ROOT / "data" / "outputs" / "truelinev2" / "general_upload_demo" / "product_store"
TENANT = "general-demo"
JOB = "job-general-demo"
RBL = "rbl-main"
AT, BY = "2026-06-24T00:00:00Z", "seed"


def _plan_pdf_bytes() -> bytes:
    """A name-free REALISTIC synthetic plan: a profile grid + station-tick row (10+00..16+00) + a full-sheet
    survey baseline + two existing utilities (full-sheet, the classic wrong picks) + the PROPOSED bore drawn
    red, TIGHTLY spanning the bore-log range 11+75..13+25 (x 295..445). The bore-aware generic selector must
    pick the red per-bore run over the full-sheet baselines, and clip the stroke to the bore span. NO
    named-dialect text ('STA <a> TO STA <b>' / 'DIR(ECTIONAL) BORE' trigger the Brenham/ODOT detectors)."""
    doc = fitz.open()
    page = doc.new_page(width=792, height=612)            # landscape, plan-like
    page.insert_text((60, 60), "PLAN & PROFILE  -  ALIGNMENT 10+00 thru 16+00 (demo)", fontsize=11)
    # profile grid (light gray) — realistic background noise
    for gx in range(120, 721, 50):
        page.draw_line((gx, 300), (gx, 360), color=(0.8, 0.8, 0.8), width=0.4)
    for gy in range(300, 361, 20):
        page.draw_line((120, gy), (720, gy), color=(0.8, 0.8, 0.8), width=0.4)
    # station ticks + labels (the axis row): x=120..720 -> stations 1000..1600 (station_at(x) = x + 880)
    for ft in range(1000, 1601, 100):
        x = 120 + (ft - 1000) / 100 * 100
        page.draw_line((x, 400), (x, 412), color=(0, 0, 0), width=0.8)
        page.insert_text((x - 12, 426), "%d+%02d" % (ft // 100, ft % 100), fontsize=8)
    # full-sheet survey baseline + existing utilities (rivals the selector must NOT mistake for the bore)
    page.draw_line((120, 400), (720, 400), color=(0, 0, 0), width=0.7)
    page.draw_line((120, 372), (720, 372), color=(0.2, 0.5, 0.9), width=0.8)   # blue utility
    page.draw_line((120, 388), (720, 388), color=(0.1, 0.6, 0.2), width=0.8)   # green utility
    # the PROPOSED BORE — red run TIGHTLY spanning the bore-log range 11+75..13+25 (x 295..445)
    page.draw_line((295, 384), (445, 384), color=(1, 0, 0), width=1.8)
    out = io.BytesIO()
    doc.save(out)
    doc.close()
    return out.getvalue()


def _borelog_xlsx_bytes() -> bytes:
    """A Brenham-flat bore-log: span 11+75 -> 13+25 (150 ft) on plan sheet 1 — sits under the drawn red run."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["station", "depth", "print", "notes"])
    ws.append(["11+75", 5.0, "1", "demo bore start"])
    ws.append(["13+25", 5.0, "1", "demo bore end"])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def main() -> int:
    if STORE.exists():
        shutil.rmtree(STORE)
    STORE.mkdir(parents=True, exist_ok=True)
    create_customer_project(STORE, TENANT, "General upload demo", AT)
    create_job(STORE, TENANT, JOB, AT, BY)

    accept_upload(STORE, TENANT, JOB, kind="PLAN_PDF", filename="project_plan.pdf",
                  content=_plan_pdf_bytes(), stored_at=AT)
    up = accept_upload(STORE, TENANT, JOB, kind="BORE_LOG", filename="bore_log.xlsx",
                       content=_borelog_xlsx_bytes(), stored_at=AT)

    create_reviewed_bore_log(STORE, TENANT, JOB, up["upload_id"], RBL, at=AT, by=BY)
    row = new_extracted_row("row-1", up["upload_id"], raw={"src": "bore_log.xlsx"},
                            normalized={"src": "bore_log.xlsx"}, extraction_method=MANUAL_ENTRY, at=AT, by=BY)
    add_extracted_rows(STORE, TENANT, JOB, RBL, [row], at=AT, by=BY)
    review_row_in_log(STORE, TENANT, JOB, RBL, "row-1", CONFIRMED, at=AT, by=BY)
    define_segment_group(STORE, TENANT, JOB, RBL, "g-1", ["row-1"], SEPARATE_BORE, at=AT, by=BY)
    set_grouping_status(STORE, TENANT, JOB, RBL, "g-1", GROUPING_CONFIRMED, at=AT, by=BY)

    print("[seed] store:  %s" % STORE)
    print("[seed] tenant: %s" % TENANT)
    print("[seed] job:    %s" % JOB)
    print("[seed] ready: upload a plan that matches NO named dialect -> generic REVIEW candidate on Generate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
