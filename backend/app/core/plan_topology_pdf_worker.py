"""PE.3 worker — per-page bounded parser signal extraction.

Spawned by `_extract_pdf_signals_per_page_bounded` in `backend/main.py`
with a hard per-page wallclock timeout enforced via
`subprocess.run(timeout=...)`. The worker contains no in-process
timeout logic — that responsibility lives in the orchestrator, because
pdfminer's C-extension code path may hold the GIL indefinitely and
only an OS-level kill can reclaim a hung worker.

Two modes (mirrors `scripts/pe1_page_probe_worker.py` precedent):

  ``count <pdf_path>``
      Emits ``{"ok": true, "page_count": int}`` and exits 0.

  ``extract_page <pdf_path> <page_index>``
      Opens the PDF, extracts text from one 0-indexed page only, runs
      the production parser's matchline + station-callout regexes on
      that text, and emits
      ``{"ok": true, "matchlines": [...], "callouts": [...],
         "text_len": int, "elapsed_ms": int, "peak_kb": int}``.
      Records preserve the production parser's 1-indexed ``page`` field
      (page_index 0 -> page 1) so downstream
      ``derive_sheet_station_origins`` consumes them unchanged.

On exception:
    ``{"ok": false, "error": "<ExcType>: <msg>", "elapsed_ms": int}``
    + exit code 1.

Imports only `app.services.engineering_plan_parser` (for regex
constants + helpers — public module-level symbols) + stdlib. Does
NOT import `backend.main`. Production-safe: no STATE access, no
env-flag side effects, no network, no Render dependency.

PE.2 → PE.3 migration:
- PE.2's whole-PDF ``main()`` is removed; the per-page worker plus
  ``count`` mode is the only invocation surface.
- The orchestrator (PE.3 ``_extract_pdf_signals_per_page_bounded``)
  is responsible for the page loop + PDF-level circuit breaker.
- Records emitted by the worker preserve the same shape that
  ``extract_matchlines`` / ``extract_station_callouts`` produce so
  ``derive_sheet_station_origins`` (the topology builder) requires
  no change.

Note on OK-with-0-chars: a successful page run with empty matchlines
and empty callouts (text_len=0) is a valid outcome (the page is
image-only or non-text). The orchestrator distinguishes this from
timeout/error via the ``ok`` flag, NOT by counting matchlines /
callouts.
"""

from __future__ import annotations

import gc
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

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


def _import_parser():
    """Import the production parser module. Returns the module or emits an
    error and exits 1 on failure."""
    try:
        from app.services import engineering_plan_parser as pp  # type: ignore
        return pp
    except Exception as e:
        _emit({"ok": False, "error": f"{type(e).__name__}: parser import failed: {e}"}, 1)
        return None  # unreachable; _emit exits


def _mode_count(pdf_path_str: str) -> None:
    pdf_path = Path(pdf_path_str)
    if not pdf_path.is_file():
        _emit({"ok": False, "error": f"FileNotFoundError: {pdf_path_str}"}, 1)
        return
    pp = _import_parser()
    try:
        with pp._safe_pdf(pdf_path) as pdf:  # type: ignore[attr-defined]
            if pdf is None:
                _emit({"ok": False, "error": "RuntimeError: _safe_pdf returned None"}, 1)
                return
            page_count = len(pdf.pages)
        _emit({"ok": True, "page_count": int(page_count)}, 0)
    except Exception as e:
        _emit({"ok": False, "error": f"{type(e).__name__}: {e}"}, 1)


def _extract_one_page_signals(pp: Any, page: Any, one_indexed_page: int) -> Dict[str, Any]:
    """Mirror the per-page slice of ``extract_matchlines`` +
    ``extract_station_callouts``. Returns ``{matchlines, callouts, text_len}``.

    Uses public-but-underscored parser module-level helpers
    (``_safe_page_text`` / ``_MATCHLINE_RE`` / ``_STATION_RANGE_RE`` /
    ``_STATION_EQ_RE`` / ``_STATION_RE`` / ``_format_station`` /
    ``_station_to_ft``). This is intentional re-use, not a parser
    rewrite: the worker does not modify any parser code, regex, or
    helper. The same constants drive both the production parser and
    the PE.3 worker so per-page output is bit-identical to per-PDF
    output filtered to the same page."""
    text = pp._safe_page_text(page)  # type: ignore[attr-defined]
    matchlines: List[Dict[str, Any]] = []
    callouts: List[Dict[str, Any]] = []
    if not text:
        return {"matchlines": matchlines, "callouts": callouts, "text_len": 0}

    # Matchlines (mirrors extract_matchlines per-page block at line 333-348).
    for m in pp._MATCHLINE_RE.finditer(text):  # type: ignore[attr-defined]
        primary_n, primary_p = int(m.group(1)), int(m.group(2))
        record: Dict[str, Any] = {
            "page": one_indexed_page,
            "station": pp._format_station(primary_n, primary_p),  # type: ignore[attr-defined]
            "station_ft": pp._station_to_ft(primary_n, primary_p),  # type: ignore[attr-defined]
            "references_sheet": int(m.group(5)),
            "second_station": None,
            "second_station_ft": None,
            "raw_text": m.group(0),
        }
        if m.group(3) and m.group(4):
            sec_n, sec_p = int(m.group(3)), int(m.group(4))
            record["second_station"] = pp._format_station(sec_n, sec_p)  # type: ignore[attr-defined]
            record["second_station_ft"] = pp._station_to_ft(sec_n, sec_p)  # type: ignore[attr-defined]
        matchlines.append(record)

    # Station callouts (mirrors extract_station_callouts per-page block at
    # line 369-409: range -> equation -> single, with consumed-range dedup).
    consumed: List[tuple] = []

    for m in pp._STATION_RANGE_RE.finditer(text):  # type: ignore[attr-defined]
        s1n, s1p, s2n, s2p = (int(g) for g in m.groups())
        callouts.append({
            "page": one_indexed_page,
            "kind": "range",
            "station": pp._format_station(s1n, s1p),  # type: ignore[attr-defined]
            "station_ft": pp._station_to_ft(s1n, s1p),  # type: ignore[attr-defined]
            "second_station": pp._format_station(s2n, s2p),  # type: ignore[attr-defined]
            "second_station_ft": pp._station_to_ft(s2n, s2p),  # type: ignore[attr-defined]
            "raw_text": m.group(0),
        })
        consumed.append((m.start(), m.end()))

    for m in pp._STATION_EQ_RE.finditer(text):  # type: ignore[attr-defined]
        s1n, s1p, s2n, s2p = (int(g) for g in m.groups())
        callouts.append({
            "page": one_indexed_page,
            "kind": "equation",
            "station": pp._format_station(s1n, s1p),  # type: ignore[attr-defined]
            "station_ft": pp._station_to_ft(s1n, s1p),  # type: ignore[attr-defined]
            "second_station": pp._format_station(s2n, s2p),  # type: ignore[attr-defined]
            "second_station_ft": pp._station_to_ft(s2n, s2p),  # type: ignore[attr-defined]
            "raw_text": m.group(0),
        })
        consumed.append((m.start(), m.end()))

    for m in pp._STATION_RE.finditer(text):  # type: ignore[attr-defined]
        if any(s <= m.start() < e for s, e in consumed):
            continue
        sn, sp = int(m.group(1)), int(m.group(2))
        callouts.append({
            "page": one_indexed_page,
            "kind": "single",
            "station": pp._format_station(sn, sp),  # type: ignore[attr-defined]
            "station_ft": pp._station_to_ft(sn, sp),  # type: ignore[attr-defined]
            "second_station": None,
            "second_station_ft": None,
            "raw_text": m.group(0),
        })

    return {"matchlines": matchlines, "callouts": callouts, "text_len": len(text)}


def _mode_extract_page(pdf_path_str: str, page_index: int) -> None:
    pdf_path = Path(pdf_path_str)
    if not pdf_path.is_file():
        _emit({"ok": False, "error": f"FileNotFoundError: {pdf_path_str}"}, 1)
        return
    pp = _import_parser()

    gc.collect()
    # PE.4: tracemalloc removed — it added ~13x wall-clock overhead on
    # vector-heavy engineering pages (e.g. Brenham), causing per-page
    # subprocess timeouts and per-PDF budget exhaustion. peak_kb is
    # retained in the payload as 0 for schema back-compat; no production
    # consumer reads the field (orchestrator uses text_len + elapsed_ms).
    t0 = time.perf_counter()
    try:
        with pp._safe_pdf(pdf_path) as pdf:  # type: ignore[attr-defined]
            if pdf is None:
                _emit({"ok": False, "error": "RuntimeError: _safe_pdf returned None"}, 1)
                return
            if page_index < 0 or page_index >= len(pdf.pages):
                _emit({
                    "ok": False,
                    "error": (
                        f"IndexError: page_index {page_index} out of range "
                        f"(pdf has {len(pdf.pages)} pages)"
                    ),
                }, 1)
                return
            page = pdf.pages[page_index]
            extracted = _extract_one_page_signals(pp, page, page_index + 1)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        _emit({
            "ok": True,
            "matchlines": extracted["matchlines"],
            "callouts": extracted["callouts"],
            "text_len": extracted["text_len"],
            "elapsed_ms": elapsed_ms,
            "peak_kb": 0,
        }, 0)
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        _emit({
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
            "elapsed_ms": elapsed_ms,
        }, 1)


def main() -> None:
    argv = sys.argv[1:]
    if len(argv) < 2:
        _emit({
            "ok": False,
            "error": (
                "usage: count <pdf_path> "
                "| extract_page <pdf_path> <page_index>"
            ),
        }, 1)
        return
    mode = argv[0]
    if mode == "count":
        _mode_count(argv[1])
    elif mode == "extract_page":
        if len(argv) < 3:
            _emit({"ok": False, "error": "extract_page mode requires <page_index>"}, 1)
            return
        try:
            page_index = int(argv[2])
        except ValueError:
            _emit({"ok": False, "error": f"invalid page_index: {argv[2]!r}"}, 1)
            return
        _mode_extract_page(argv[1], page_index)
    else:
        _emit({"ok": False, "error": f"unknown mode: {mode!r}"}, 1)


if __name__ == "__main__":
    main()
