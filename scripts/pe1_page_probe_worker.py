"""PE.1 worker — single-page parser extraction subprocess.

Designed to be spawned by `pe1_page_probe.py` with a hard wallclock
timeout enforced from the outside. The worker itself contains no
timeout logic — that responsibility lives in the orchestrator, because
in-process timeouts cannot interrupt pdfminer's C-extension code path
that may hold the GIL indefinitely.

The worker emits exactly one JSON object on the FINAL line of stdout
and exits with code 0 on success / 1 on any error. Anything before the
final line is informational and ignored by the orchestrator.

Modes
-----
    count   <pdf_path>                  → emit {"ok": true, "page_count": N}
    extract <pdf_path> <page_index>     → emit {"ok": true, "text_len": L,
                                                 "elapsed_ms": M, "peak_kb": K}

On exception:
    emit {"ok": false, "error": "<ExcType>: <msg>"}

PE.1 scope: scripts-only. No backend imports. No production runtime impact.
"""

from __future__ import annotations

import gc
import json
import sys
import time
import tracemalloc
from typing import Any, Dict


def _emit(payload: Dict[str, Any], exit_code: int) -> None:
    sys.stdout.write(json.dumps(payload, default=str) + "\n")
    sys.stdout.flush()
    sys.exit(exit_code)


def _mode_count(pdf_path: str) -> None:
    try:
        import pdfplumber  # type: ignore
    except Exception as e:
        _emit({"ok": False, "error": f"{type(e).__name__}: pdfplumber import failed: {e}"}, 1)
        return
    try:
        with pdfplumber.open(pdf_path) as pdf:
            page_count = len(pdf.pages)
        _emit({"ok": True, "page_count": page_count}, 0)
    except Exception as e:
        _emit({"ok": False, "error": f"{type(e).__name__}: {e}"}, 1)


def _mode_extract(pdf_path: str, page_index: int) -> None:
    try:
        import pdfplumber  # type: ignore
    except Exception as e:
        _emit({"ok": False, "error": f"{type(e).__name__}: pdfplumber import failed: {e}"}, 1)
        return
    gc.collect()
    tracemalloc.start()
    t0 = time.perf_counter()
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if page_index < 0 or page_index >= len(pdf.pages):
                tracemalloc.stop()
                _emit({"ok": False, "error": f"IndexError: page_index {page_index} out of range (pdf has {len(pdf.pages)} pages)"}, 1)
                return
            page = pdf.pages[page_index]
            text = page.extract_text() or ""
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        _emit({
            "ok": True,
            "text_len": len(text),
            "elapsed_ms": elapsed_ms,
            "peak_kb": peak_bytes // 1024,
        }, 0)
    except Exception as e:
        try:
            tracemalloc.stop()
        except Exception:
            pass
        _emit({"ok": False, "error": f"{type(e).__name__}: {e}"}, 1)


def main() -> None:
    argv = sys.argv[1:]
    if len(argv) < 2:
        _emit({"ok": False, "error": "usage: count <pdf_path> | extract <pdf_path> <page_index>"}, 1)
        return
    mode = argv[0]
    pdf_path = argv[1]
    if mode == "count":
        _mode_count(pdf_path)
    elif mode == "extract":
        if len(argv) < 3:
            _emit({"ok": False, "error": "extract mode requires <page_index>"}, 1)
            return
        try:
            page_index = int(argv[2])
        except ValueError:
            _emit({"ok": False, "error": f"invalid page_index: {argv[2]!r}"}, 1)
            return
        _mode_extract(pdf_path, page_index)
    else:
        _emit({"ok": False, "error": f"unknown mode: {mode!r}"}, 1)


if __name__ == "__main__":
    main()
