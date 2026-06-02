"""Clean-room PDF-first redline engine.

Invariants (enforced by tests): only ``.pdf`` imports ``fitz``; no TrueLine
``backend``/``main`` dependency; nothing raises to the caller (FAIL_SAFE/ERROR).

Day-2 public entrypoint: ``select_redline(bore_log_path, plan_pdf_path)`` runs the
real selector funnel. ``run_stub`` remains for fixtures/tests.
"""
from .contracts import EngineResult, ENGINE_VERSION, CONTRACT_VERSION  # noqa: F401
from .selector.stub_selector import run_stub  # noqa: F401  (pure; no fitz)


def select_redline(bore_log_path, plan_pdf_path, sheet_offset=13, anchor_tables=None,
                   trace_paths=False, dash_chain=False):
    """Real entrypoint (file-fed). Lazy import keeps fitz confined to the pdf
    subpackage and the top-level package import lightweight. ``anchor_tables``
    (optional, from :func:`load_anchor_tables`) enables Slice-B AP/structure-
    anchored geometry; when None the placement stays geometry-free. ``trace_paths``
    (default OFF) attaches page-space ``pdf_path_trace`` metadata; ``dash_chain``
    enables bounded dash-chain reconstruction as the BLOCKED fallback."""
    from .selector.pdf_first_selector import select
    return select(bore_log_path, plan_pdf_path, sheet_offset, anchor_tables=anchor_tables,
                  trace_paths=trace_paths, dash_chain=dash_chain)


def select_redline_from_rows(plan_pdf_path, rows, source_file=None, sheet_offset=13,
                             anchor_tables=None, trace_paths=False, dash_chain=False):
    """Row-fed entrypoint for the TrueLine adapter: run the REAL selector funnel
    over TrueLine-style ``committed_rows`` (no .xlsx needed), producing a result
    equivalent to ``select_redline`` on the same underlying log. Lazy import keeps
    fitz confined to the pdf subpackage. ``anchor_tables`` (optional) enables
    Slice-B AP/structure-anchored geometry. ``trace_paths`` (default OFF) attaches
    page-space ``pdf_path_trace`` metadata; ``dash_chain`` enables bounded dash-chain
    reconstruction as the BLOCKED fallback."""
    from .selector.pdf_first_selector import select_from_rows
    return select_from_rows(rows, plan_pdf_path, source_file=source_file,
                            sheet_offset=sheet_offset, anchor_tables=anchor_tables,
                            trace_paths=trace_paths, dash_chain=dash_chain)


def load_anchor_tables(analysis_dir):
    """Load the RESOLVED anchor tables (anchors.json / sheet_station_model.json)
    for Slice-B identity binding. Pure data; never raises (returns empty indexes
    on any error). Lazy import keeps the top-level package import lightweight."""
    from .geometry.identity_binder import load_tables
    return load_tables(analysis_dir)


__all__ = ["EngineResult", "select_redline", "select_redline_from_rows",
           "load_anchor_tables", "run_stub", "ENGINE_VERSION", "CONTRACT_VERSION"]
__version__ = ENGINE_VERSION
