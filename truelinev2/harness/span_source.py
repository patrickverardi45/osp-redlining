"""Seams 1+2 of the source-span extractor: SOURCE-FILE DISCOVERY + TEXT/TABLE EXTRACTION (read-only, name-free).

Turns an uploaded bore-log / bore-schedule / span-table source file — or a package folder of them — into a
normalized ``SourceDocument`` (text lines for inline station-pair grammar, and/or a ``SourceTable`` of rows) that
the parser (``span_extractor``) consumes. It only READS files; it draws nothing, places nothing, and imports
nothing from render / placement / api / store / contracts / product runtime. Spreadsheet + PDF readers are
lazy-imported so the module loads with only stdlib.

Supported MVP inputs: plain text / markdown (inline callouts + simple pipe tables), CSV span tables (stdlib
``csv``), XLSX span tables (``openpyxl`` — the repo convention), and text-extractable PDF bore logs / schedules
(``ingest.pdf.PlanPdf`` text). Discovery is manifest-driven for a package folder (BORE_LOG-kind uploads, so the
PLAN pdf is never mistaken for a span source) with an extension-based fallback for loose table/text files.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from truelinev2.harness.package_validation import load_package_manifest

# --- source kinds --------------------------------------------------------------------------------------- #
KIND_TEXT = "TEXT"
KIND_MARKDOWN_TABLE = "MARKDOWN_TABLE"
KIND_CSV_TABLE = "CSV_TABLE"
KIND_XLSX_TABLE = "XLSX_TABLE"
KIND_PDF_BORE_LOG = "PDF_BORE_LOG"

# upload kinds (declared in a package.json) that may carry a bore/span source
SPAN_SOURCE_UPLOAD_KINDS = ("BORE_LOG", "BORE_SCHEDULE", "SPAN_TABLE")

_TABLE_EXTS = {".csv": KIND_CSV_TABLE, ".xlsx": KIND_XLSX_TABLE, ".xls": KIND_XLSX_TABLE}
_TEXT_EXTS = {".txt": KIND_TEXT, ".md": KIND_TEXT}


@dataclass(frozen=True)
class SourceTable:
    """A tabular source (CSV / XLSX / markdown pipe table). ``header`` is lower-cased; ``rows`` are raw strings."""
    header: Tuple[str, ...]
    rows: Tuple[Tuple[str, ...], ...]


@dataclass(frozen=True)
class SourceDocument:
    """One page/sheet of a source file, normalized. ``text_lines`` feeds inline station-pair parsing; ``table``
    (when present) feeds the table parser. No name, no coordinate, no drawn stroke."""
    source_file: str
    source_kind: str
    text_lines: Tuple[str, ...]
    table: Optional[SourceTable]
    source_page: Optional[int]
    detail: Dict[str, Any] = field(default_factory=dict)


# ======================================================================================================== #
# Seam 2 — text / table extraction into SourceDocument(s).
# ======================================================================================================== #
def _rows_to_table(rows: List[Tuple[str, ...]]) -> Optional[SourceTable]:
    rows = [r for r in rows if any(str(c).strip() for c in r)]
    if len(rows) < 2:
        return None
    header = tuple(str(c).strip().lower() for c in rows[0])
    data = tuple(tuple(str(c).strip() for c in r) for r in rows[1:])
    return SourceTable(header=header, rows=data)


def _maybe_pipe_table(lines: Tuple[str, ...]) -> Optional[SourceTable]:
    """Parse a simple markdown/pipe table; return None if the text is not a pipe table."""
    pipe_lines = [ln for ln in lines if "|" in ln]
    if len(pipe_lines) < 2:
        return None
    parsed: List[Tuple[str, ...]] = []
    for ln in pipe_lines:
        cells = tuple(c.strip() for c in ln.strip().strip("|").split("|"))
        if cells and all(c and set(c) <= set("-: ") for c in cells):
            continue                                    # separator row (---|---)
        parsed.append(cells)
    return _rows_to_table(parsed)


def documents_from_text(text: str, *, source_file: str = "text-input",
                        source_kind: str = KIND_TEXT) -> List[SourceDocument]:
    """Normalize plain text / markdown into one SourceDocument. If it is a pipe table, expose it as a table;
    otherwise expose the raw lines for inline station-pair parsing."""
    lines = tuple(text.splitlines())
    table = _maybe_pipe_table(lines)
    kind = KIND_MARKDOWN_TABLE if table is not None else source_kind
    return [SourceDocument(source_file=source_file, source_kind=kind,
                           text_lines=() if table is not None else lines, table=table, source_page=None)]


def documents_from_csv(path: str) -> List[SourceDocument]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = [tuple(cell for cell in row) for row in csv.reader(f)]
    table = _rows_to_table(rows)
    return [SourceDocument(source_file=Path(path).name, source_kind=KIND_CSV_TABLE,
                           text_lines=(), table=table, source_page=None)]


def documents_from_xlsx(path: str) -> List[SourceDocument]:
    import openpyxl  # lazy: the repo XLSX convention; not needed to import this module
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        ws = wb.worksheets[0]
        rows = [tuple("" if c is None else c for c in r) for r in ws.iter_rows(values_only=True)]
    finally:
        wb.close()
    table = _rows_to_table(rows)
    return [SourceDocument(source_file=Path(path).name, source_kind=KIND_XLSX_TABLE,
                           text_lines=(), table=table, source_page=None)]


def documents_from_pdf(path: str) -> List[SourceDocument]:
    """Read a text-extractable PDF bore log / schedule as one SourceDocument PER PAGE (inline text lines). The
    caller asserts this PDF is a bore-log source (discovery does so via the manifest BORE_LOG kind)."""
    from truelinev2.ingest.pdf import PlanPdf  # lazy read-only reader
    plan = None
    docs: List[SourceDocument] = []
    try:
        plan = PlanPdf(str(path))
        for idx in range(int(plan.page_count)):
            try:
                text = plan.text_by_index(idx) or ""
            except Exception:
                text = ""
            lines = tuple(ln for ln in text.splitlines() if ln.strip())
            docs.append(SourceDocument(source_file=Path(path).name, source_kind=KIND_PDF_BORE_LOG,
                                       text_lines=lines, table=None, source_page=idx + 1))
    finally:
        try:
            if plan is not None:
                plan.close()
        except Exception:
            pass
    return docs


def documents_from_file(path: str, kind: Optional[str] = None) -> List[SourceDocument]:
    """Dispatch a file to the right loader by kind (or by extension when kind is None). Unreadable files yield
    an empty-content SourceDocument rather than raising, so extraction can refuse honestly."""
    p = Path(path)
    kind = kind or _kind_for_ext(p.suffix.lower())
    try:
        if kind == KIND_CSV_TABLE:
            return documents_from_csv(str(p))
        if kind == KIND_XLSX_TABLE:
            return documents_from_xlsx(str(p))
        if kind == KIND_PDF_BORE_LOG:
            return documents_from_pdf(str(p))
        return documents_from_text(p.read_text(encoding="utf-8"), source_file=p.name)
    except Exception as exc:
        return [SourceDocument(source_file=p.name, source_kind=kind or KIND_TEXT, text_lines=(), table=None,
                               source_page=None, detail={"unreadable": str(exc)})]


def _kind_for_ext(ext: str) -> str:
    return _TABLE_EXTS.get(ext) or _TEXT_EXTS.get(ext) or (KIND_PDF_BORE_LOG if ext == ".pdf" else KIND_TEXT)


# ======================================================================================================== #
# Seam 1 — package/source discovery.
# ======================================================================================================== #
def discover_span_sources(folder: str) -> List[Tuple[str, str]]:
    """Return [(path, source_kind)] for the bore/span source files in a package folder. Manifest-driven first
    (only BORE_LOG-kind uploads, so the PLAN pdf is never treated as a span source), then an extension-based
    fallback for loose table/text files under the folder root and ``uploads/`` (PDFs are only picked up via the
    manifest). Read-only; opens nothing heavy."""
    folder_p = Path(folder)
    out: List[Tuple[str, str]] = []
    seen: set = set()

    manifest = load_package_manifest(folder_p) if folder_p.is_dir() else None
    if manifest:
        for u in (manifest.get("uploads") or []):
            if u.get("kind") in SPAN_SOURCE_UPLOAD_KINDS:
                fp = folder_p / "uploads" / str(u.get("filename", ""))
                if fp.is_file() and str(fp) not in seen:
                    seen.add(str(fp))
                    out.append((str(fp), _kind_for_ext(fp.suffix.lower())))

    for base in (folder_p, folder_p / "uploads"):
        if not base.is_dir():
            continue
        for fp in sorted(base.iterdir()):
            if not fp.is_file() or str(fp) in seen:
                continue
            k = _TABLE_EXTS.get(fp.suffix.lower()) or _TEXT_EXTS.get(fp.suffix.lower())
            if k:                                        # loose CSV/XLSX/TXT/MD only (never a bare .pdf)
                seen.add(str(fp))
                out.append((str(fp), k))
    return out
