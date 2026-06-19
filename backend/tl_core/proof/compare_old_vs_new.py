"""Old-vs-new behavioral comparison for the SAME real bore.

OLD path  = the engine called directly (what main.py's adapter does today):
            redline_pdf_first.select_redline + crop_renderer.render_and_attach.
NEW path  = the tl_core RedlineService (engine behind a port + scoped store).

Because tl_core REUSES the same engine, the SELECTION must be identical; the new
path only adds tenant scoping + safe serving. This harness asserts equivalence on
the engine-observable fields and writes a comparison report.

Run (repo root, root venv):
  $env:PYTHONPATH = "backend"
  .\venv\Scripts\python.exe -m tl_core.proof.compare_old_vs_new
"""
from __future__ import annotations

import json
import os
import sys

from tl_core.adapters.artifact_fs import FilesystemArtifactStore
from tl_core.adapters.engine_pdf_first import PdfFirstEngine
from tl_core.config import Settings, _ENGINE_ROOT_DEFAULT, _REPO_ROOT
from tl_core.context import require_context
from tl_core.services.redline_service import RedlineService

DEFAULT_BORE = r"C:\Users\Patrick\OneDrive\Attachments\Desktop\excel bore logs\bore_log51.xlsx"
DEFAULT_PDF = str(_REPO_ROOT / "data" / "uploads" / "Brenham_Tx"
                  / "NEXTLINK - Brenham - Phase 5_07-15-25.pdf")
REPORT_DIR = _REPO_ROOT / "data" / "outputs" / "tl_core"
_FIELDS = ["status", "tier", "sheets", "station", "footage", "png"]


def _old_path(bore: str, pdf: str, out_dir: str) -> dict:
    root = str(_ENGINE_ROOT_DEFAULT)
    if root not in sys.path:
        sys.path.insert(0, root)
    import redline_pdf_first as eng
    from redline_pdf_first.render import crop_renderer
    res = eng.select_redline(bore, pdf, sheet_offset=13)
    os.makedirs(out_dir, exist_ok=True)
    crop_renderer.render_and_attach(res, pdf, out_dir=out_dir, sheet_offset=13)
    seg = (res.selected_segments or [None])[0]
    png = None
    for art in res.render_artifacts or []:
        refs = (getattr(art, "payload", {}) or {}).get("render_artifact_ref")
        if not refs and getattr(art, "ref", None):
            refs = [art.ref]
        if refs:
            png = os.path.basename(refs[0])
            break
    span = getattr(seg, "station_span", None) if seg else None
    return {
        "status": res.status,
        "tier": getattr(seg, "tier", None),
        "sheets": list(getattr(seg, "sheets", []) or []) if seg else None,
        "station": (f"{span.start}->{span.end}" if span else None),
        "footage": getattr(seg, "footage", None),
        "png": png,
    }


def _new_path(bore: str, pdf: str) -> dict:
    settings = Settings.for_proof(artifact_root=REPORT_DIR / "artifacts")
    engine = PdfFirstEngine(settings.engine_root, settings.sheet_offset, True,
                            out_dir=REPORT_DIR / "_new_cards")
    store = FilesystemArtifactStore(settings.artifact_root)
    svc = RedlineService(engine, store)
    outcome = svc.run_for_bore(require_context("compare-tenant", "compare-session"), bore, pdf)
    p = (outcome.result.placements or [None])[0]
    return {
        "status": outcome.result.status,
        "tier": getattr(p, "tier", None),
        "sheets": list(getattr(p, "sheets", []) or []) if p else None,
        "station": (f"{p.station_start}->{p.station_end}" if p and p.station_start else None),
        "footage": getattr(p, "footage", None),
        "png": outcome.stored_artifacts[0].name if outcome.stored_artifacts else None,
    }


def main() -> int:
    bore = os.getenv("TL_CORE_PROOF_BORE", DEFAULT_BORE)
    pdf = os.getenv("TL_CORE_PROOF_PDF", DEFAULT_PDF)
    missing = [p for p in (bore, pdf) if not os.path.isfile(p)]
    if missing:
        print(f"[compare] FAIL: missing real input(s): {missing}")
        return 2

    old = _old_path(bore, pdf, str(REPORT_DIR / "_old_cards"))
    new = _new_path(bore, pdf)
    diffs = {f: {"old": old[f], "new": new[f]} for f in _FIELDS if old[f] != new[f]}
    equivalent = not diffs

    print(f"[compare] OLD: {old}")
    print(f"[compare] NEW: {new}")
    print(f"[compare] equivalent={equivalent} diffs={diffs}")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    rp = REPORT_DIR / "m1_old_vs_new_report.json"
    rp.write_text(json.dumps(
        {"equivalent": equivalent, "old": old, "new": new, "diffs": diffs,
         "note": "Same reused engine -> identical selection; new path only adds "
                 "tenant scoping + safe artifact serving."},
        indent=2), encoding="utf-8")
    print(f"[compare] report -> {rp}")
    print(f"[compare] {'EQUIVALENT' if equivalent else 'DIVERGENT'}")
    return 0 if equivalent else 1


if __name__ == "__main__":
    raise SystemExit(main())
