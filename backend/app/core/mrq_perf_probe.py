"""Build-scoped, default-OFF render telemetry probe for the MRQ pdf_first evidence build.

Answers the granular perf questions the coarse per-log timing (pdf_first_adapter) cannot:
fitz.open count/time, page get_pixmap rasterization count/time, duplicate (page, clip-bbox)
rasterizations, per-render-stage timings (crop / resolver / redline overlay / seam+connector),
and a cheap process-RSS sample — all flushed as ``mrq_pf.*`` rows via the SAME observer the
coarse layer uses (so they land in performance_audit.jsonl under TRUELINE_PERF_AUDIT).

BEHAVIOR-NEUTRAL: when ``observer`` is None (the default, and whenever PERF_AUDIT is off) every
hook is a cheap no-op and the build is byte-identical — no fitz wrapping, no timing, no records.
It only MEASURES: no draw / selector / correctness / cache-strategy change. NEVER raises into the
build (every hook is wrapped). Thread-safety: metrics are recorded into a thread-local context, and
the global fitz wrappers are reference-counted (installed once, restored when the last probe exits),
so concurrent builds each record into their own context. The current build is single-threaded.
"""
from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Mapping, Optional

_LOCAL = threading.local()
_INSTALL_LOCK = threading.Lock()
_install_count = 0
_orig_open: Any = None
_orig_pixmap: Any = None


def _ctx() -> Optional[Dict[str, Any]]:
    return getattr(_LOCAL, "ctx", None)


def record(stage: str, ms: float = 0.0, count: int = 1) -> None:
    """Accumulate a per-stage timing/count into the active probe (no-op when inactive)."""
    ctx = _ctx()
    if ctx is None:
        return
    try:
        s = ctx["stages"].setdefault(stage, {"ms": 0.0, "count": 0})
        s["ms"] += float(ms)
        s["count"] += int(count)
    except Exception:
        pass


@contextmanager
def timed(stage: str):
    """Time a block and record it under ``stage`` (cheap no-op when inactive)."""
    if _ctx() is None:
        yield
        return
    _t0 = time.perf_counter()
    try:
        yield
    finally:
        record(stage, (time.perf_counter() - _t0) * 1000.0)


def _install_fitz_wrappers() -> None:
    global _install_count, _orig_open, _orig_pixmap
    with _INSTALL_LOCK:
        if _install_count == 0:
            try:
                import fitz  # PyMuPDF

                _orig_open = fitz.open
                _orig_pixmap = fitz.Page.get_pixmap

                def _w_open(*a: Any, **k: Any) -> Any:
                    _t0 = time.perf_counter()
                    try:
                        return _orig_open(*a, **k)
                    finally:
                        c = _ctx()
                        if c is not None:
                            fo = c["fitz_open"]
                            fo["count"] += 1
                            fo["ms"] += (time.perf_counter() - _t0) * 1000.0

                def _w_pixmap(self: Any, *a: Any, **k: Any) -> Any:
                    _t0 = time.perf_counter()
                    try:
                        return _orig_pixmap(self, *a, **k)
                    finally:
                        c = _ctx()
                        if c is not None:
                            r = c["raster"]
                            r["count"] += 1
                            r["ms"] += (time.perf_counter() - _t0) * 1000.0
                            try:  # best-effort duplicate (page, clip-bbox) detection
                                clip = k.get("clip")
                                key = (
                                    getattr(self, "number", -1),
                                    tuple(round(float(x), 1) for x in clip) if clip is not None else None,
                                )
                                if key in c["_seen"]:
                                    r["dup"] += 1
                                else:
                                    c["_seen"].add(key)
                            except Exception:
                                pass

                fitz.open = _w_open
                fitz.Page.get_pixmap = _w_pixmap
            except Exception:
                _orig_open = None  # fitz unavailable / unpatchable -> stage timers still work
                _orig_pixmap = None
        _install_count += 1


def _restore_fitz_wrappers() -> None:
    global _install_count, _orig_open, _orig_pixmap
    with _INSTALL_LOCK:
        _install_count = max(0, _install_count - 1)
        if _install_count == 0 and _orig_open is not None:
            try:
                import fitz

                fitz.open = _orig_open
                fitz.Page.get_pixmap = _orig_pixmap
            except Exception:
                pass
            _orig_open = None
            _orig_pixmap = None


def _rss_kb() -> Optional[Dict[str, int]]:
    """Cheap RSS sample from /proc/self/status (Linux / Render). None elsewhere (e.g. Windows)."""
    try:
        out: Dict[str, int] = {}
        with open("/proc/self/status", "r") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    out["rss_kb"] = int(line.split()[1])
                elif line.startswith("VmHWM:"):
                    out["peak_kb"] = int(line.split()[1])
        return out or None
    except Exception:
        return None


@contextmanager
def perf_build_probe(observer: Optional[Callable[[Mapping[str, Any]], None]]):
    """Install the build-scoped probe when ``observer`` is set; else a zero-overhead no-op.

    Wraps fitz.open / Page.get_pixmap for the build's duration (count + time + duplicate
    detection), lets call sites ``record``/``timed`` per-stage work, samples RSS, and flushes
    one ``mrq_pf.*`` row per metric via ``observer`` on exit. Reentrancy-safe (a nested call is
    a no-op so counters are never double-installed). NEVER raises into the build."""
    if observer is None or _ctx() is not None:
        yield
        return
    ctx: Dict[str, Any] = {
        "stages": {},
        "fitz_open": {"count": 0, "ms": 0.0},
        "raster": {"count": 0, "ms": 0.0, "dup": 0},
        "_seen": set(),
    }
    _LOCAL.ctx = ctx
    _install_fitz_wrappers()
    try:
        yield
    finally:
        _restore_fitz_wrappers()
        _LOCAL.ctx = None
        try:
            fo = ctx["fitz_open"]
            observer({"stage": "mrq_pf.fitz_open", "elapsed_ms": round(fo["ms"], 1),
                      "output_count": fo["count"]})
            r = ctx["raster"]
            observer({"stage": "mrq_pf.rasterize", "elapsed_ms": round(r["ms"], 1),
                      "output_count": r["count"], "detail": "pixmaps=%d;dup=%d" % (r["count"], r["dup"])})
            observer({"stage": "mrq_pf.rasterize_dup", "elapsed_ms": 0.0, "output_count": r["dup"]})
            for _st, s in ctx["stages"].items():
                observer({"stage": "mrq_pf." + _st, "elapsed_ms": round(s["ms"], 1),
                          "output_count": s["count"]})
            mem = _rss_kb()
            if mem:
                observer({"stage": "mrq_pf.memory", "elapsed_ms": 0.0,
                          "detail": "rss_kb=%s;peak_kb=%s" % (mem.get("rss_kb"), mem.get("peak_kb"))})
        except Exception:
            pass
