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
    """A name-free synthetic plan: a station-tick row (10+00..16+00) + a red drawn run over ~11+50..13+50,
    plus a little base linework so the confidence reflects real rival-run competition. NO named-dialect text."""
    doc = fitz.open()
    page = doc.new_page(width=792, height=612)            # landscape, plan-like
    # NOTE: deliberately avoid 'STA <a> TO STA <b>' and 'DIR(ECTIONAL) BORE' text — those trigger the named
    # Brenham/ODOT detectors. A generic firm's title block carries neither, so this stays unrecognized.
    page.insert_text((60, 70), "PROJECT PLAN & PROFILE  -  ALIGNMENT 10+00 thru 16+00 (demo)", fontsize=11)
    # station ticks along an axis: x=120..720 -> stations 1000..1600 ft (station_at(x) = x + 880)
    for i, ft in enumerate(range(1000, 1601, 100)):
        x = 120 + i * 100
        sta = "%d+%02d" % (ft // 100, ft % 100)
        page.draw_line((x, 360), (x, 372), color=(0, 0, 0), width=0.8)   # tick mark
        page.insert_text((x - 12, 388), sta, fontsize=8)
    # base linework near the alignment (realistic rivals): the survey baseline + an existing utility
    page.draw_line((120, 366), (720, 366), color=(0, 0, 0), width=0.6)
    page.draw_line((120, 330), (720, 332), color=(0.2, 0.5, 0.9), width=0.8)
    # the PROPOSED bore run (red), a single elongated run over x 270..470 -> stations ~1150..1350; its
    # midpoint sits on the bore span midpoint, so the extent decider selects it over the full-length rivals.
    page.draw_line((270, 352), (470, 352), color=(1, 0, 0), width=1.8)
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
