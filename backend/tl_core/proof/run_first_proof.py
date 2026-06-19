"""tl_core Milestone-1 proof (backend chain, through-disk):

  one REAL bore log -> reused engine select_redline() -> real clip-bounded PNG
  via crop_renderer -> tenant-scoped artifact store -> traversal-safe retrieval
  -> cross-tenant access is denied.

NOT synthetic. Uses ``bore_log51`` (the engine's committed AUTO_SELECT bore, per
the Stream-2 contract read + stub_selector fixture) and the real Brenham Phase-5
plan PDF. Writes a JSON proof report under ``data/outputs/tl_core/``.

Run (from repo root, with the root venv):
  $env:PYTHONPATH = "backend"
  .\venv\Scripts\python.exe -m tl_core.proof.run_first_proof

The HTTP serve + Match-Review payload assertion is layered on top of this in the
API milestone; this script proves the engine -> PNG -> scoped-store -> safe-read
core that the endpoint will expose.
"""
from __future__ import annotations

import json
import os
import time

from tl_core.adapters.artifact_fs import FilesystemArtifactStore
from tl_core.adapters.engine_pdf_first import PdfFirstEngine
from tl_core.config import Settings, _REPO_ROOT
from tl_core.context import IsolationError, require_context
from tl_core.services.redline_service import RedlineService

# Reachable real inputs (Stream-5 verified). Overridable via env.
DEFAULT_BORE = r"C:\Users\Patrick\OneDrive\Attachments\Desktop\excel bore logs\bore_log51.xlsx"
DEFAULT_PDF = str(_REPO_ROOT / "data" / "uploads" / "Brenham_Tx"
                  / "NEXTLINK - Brenham - Phase 5_07-15-25.pdf")
REPORT_DIR = _REPO_ROOT / "data" / "outputs" / "tl_core"

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def main() -> int:
    bore = os.getenv("TL_CORE_PROOF_BORE", DEFAULT_BORE)
    pdf = os.getenv("TL_CORE_PROOF_PDF", DEFAULT_PDF)

    print(f"[proof] bore = {bore}")
    print(f"[proof] pdf  = {pdf}")
    missing = [p for p in (bore, pdf) if not os.path.isfile(p)]
    if missing:
        print(f"[proof] FAIL: missing real input(s): {missing}")
        print("[proof] (no synthetic fallback by design — see hard rules)")
        return 2

    settings = Settings.for_proof(artifact_root=REPORT_DIR / "artifacts")
    engine = PdfFirstEngine(engine_root=settings.engine_root,
                            sheet_offset=settings.sheet_offset,
                            render_crops=True,
                            out_dir=REPORT_DIR / "_engine_cards")
    if not engine.available():
        print("[proof] FAIL: engine did not import (reuse-by-import broken)")
        return 3

    store = FilesystemArtifactStore(root=settings.artifact_root)
    service = RedlineService(engine=engine, artifacts=store)
    ctx = require_context(tenant="proof-tenant", session_id="proof-session-log51")

    t0 = time.time()
    outcome = service.run_for_bore(ctx, bore, pdf)
    elapsed = time.time() - t0
    result = outcome.result

    print(f"[proof] engine status={result.status} elapsed={elapsed:.1f}s "
          f"placements={len(result.placements)} reviews={len(result.review_items)} "
          f"fail_safe={len(result.fail_safe)} stored={len(outcome.stored_artifacts)}")
    for p in result.placements + result.review_items:
        print(f"[proof]   seg={p.segment_id} tier={p.tier} sheets={p.sheets} "
              f"sta={p.station_start}->{p.station_end} ft={p.footage} "
              f"geom={p.geometry_status} arts={len(p.artifacts)}")
    for w in result.warnings:
        print(f"[proof]   warning: {w}")

    # Verify each stored artifact is retrievable via the traversal-safe store.
    served = []
    for ref in outcome.stored_artifacts:
        data = store.read_bytes(ctx, ref.name)
        served.append({"name": ref.name, "bytes": len(data),
                       "png_magic": data[:8] == _PNG_MAGIC,
                       "sheet": ref.sheet, "segment_id": ref.segment_id})
        print(f"[proof]   served {ref.name}: {len(data)} bytes "
              f"png_magic={data[:8] == _PNG_MAGIC}")

    # Cross-tenant isolation: a different tenant must NOT read this artifact.
    isolation_ok = False
    if served:
        other = require_context(tenant="other-tenant", session_id="proof-session-log51")
        try:
            store.read_bytes(other, served[0]["name"])
        except (IsolationError, FileNotFoundError):
            isolation_ok = True
    print(f"[proof] cross-tenant denied = {isolation_ok}")

    real_png = [s for s in served if s["png_magic"] and s["bytes"] > 2000]
    passed = (result.status in ("OK", "FAIL_SAFE_GLOBAL")
              and len(real_png) >= 1 and isolation_ok)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "milestone": "tl_core M1 (backend chain): real bore -> engine -> PNG -> "
                     "scoped store -> traversal-safe serve -> cross-tenant denied",
        "passed": passed,
        "bore": bore,
        "pdf": pdf,
        "engine_status": result.status,
        "elapsed_sec": round(elapsed, 2),
        "placements": len(result.placements),
        "reviews": len(result.review_items),
        "fail_safe": len(result.fail_safe),
        "stored_artifacts": served,
        "cross_tenant_denied": isolation_ok,
        "warnings": result.warnings,
        "drawn_vs_recorded": (
            "The highlight-crop PNG of the matched plan region is DRAWN+RENDERED "
            "(real, clip-bounded). The geometric redline overlay is a SEPARATE "
            "flag-gated path (TRUELINE_AP_ANCHORED_GEOMETRY + TRUELINE_PDF_REDLINE_RENDER) "
            "and is NOT asserted by this milestone."),
    }
    rp = REPORT_DIR / "m1_proof_report.json"
    rp.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[proof] report -> {rp}")
    print(f"[proof] {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
