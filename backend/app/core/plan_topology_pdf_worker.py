"""PE.2 worker — bounded per-PDF parser signal extraction.

Spawned by `_build_plan_topology_for_session_with_outcomes` in
`backend/main.py` with a hard wallclock timeout enforced via
`subprocess.run(timeout=...)`. The worker contains no in-process
timeout logic — that responsibility lives in the orchestrator,
because pdfminer's C-extension code path may hold the GIL indefinitely
and only an OS-level kill can reclaim a hung worker.

Imports only `app.services.engineering_plan_parser` + stdlib. Does NOT
import `backend.main`. Production-safe: no STATE access, no env-flag
side effects, no network, no Render dependency.

Usage
-----
    python plan_topology_pdf_worker.py <pdf_path>

Output (final line of stdout, single JSON object)
-------------------------------------------------
    Success:  {"ok": true,
               "matchlines": [...], "callouts": [...],
               "elapsed_ms": int, "peak_kb": int}
    Failure:  {"ok": false, "error": "<ExcType>: <msg>",
               "elapsed_ms": int}

Exit codes
----------
    0 on successful extraction
    1 on any error (missing file, parser exception, etc.)

Note on OK-with-0-chars: a successful run with empty matchlines and
empty callouts is a valid outcome (the PDF page was image-only or
non-text). The orchestrator distinguishes this from timeout/error via
the `ok` flag, NOT by counting matchlines/callouts.
"""

from __future__ import annotations

import gc
import json
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any, Dict


_THIS = Path(__file__).resolve()
# This file is at backend/app/core/plan_topology_pdf_worker.py
# backend/ is _THIS.parents[2]
_BACKEND_DIR = _THIS.parents[2]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


def _emit(payload: Dict[str, Any], exit_code: int) -> None:
    sys.stdout.write(json.dumps(payload, default=str) + "\n")
    sys.stdout.flush()
    sys.exit(exit_code)


def main() -> None:
    if len(sys.argv) < 2:
        _emit({"ok": False, "error": "usage: plan_topology_pdf_worker.py <pdf_path>"}, 1)
        return

    pdf_path_str = sys.argv[1]
    pdf_path = Path(pdf_path_str)

    # Fail-fast on missing file before importing the heavy parser module.
    if not pdf_path.is_file():
        _emit({"ok": False, "error": f"FileNotFoundError: {pdf_path_str}"}, 1)
        return

    try:
        from app.services import engineering_plan_parser as pp  # type: ignore
    except Exception as e:
        _emit({"ok": False, "error": f"{type(e).__name__}: parser import failed: {e}"}, 1)
        return

    gc.collect()
    tracemalloc.start()
    t0 = time.perf_counter()
    try:
        matchlines = pp.extract_matchlines(pdf_path) or []
        callouts = pp.extract_station_callouts(pdf_path) or []
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        _emit({
            "ok": True,
            "matchlines": matchlines,
            "callouts": callouts,
            "elapsed_ms": elapsed_ms,
            "peak_kb": peak_bytes // 1024,
        }, 0)
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        try:
            tracemalloc.stop()
        except Exception:
            pass
        _emit({
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
            "elapsed_ms": elapsed_ms,
        }, 1)


if __name__ == "__main__":
    main()
