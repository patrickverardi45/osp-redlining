"""PDF page → PNG raster renderer for the Visual Overlay sprint (VO.2a).

Pure helper: no STATE, no env reads, no caching (caller manages cache),
no parser invocation, no main-module dependency.  Single public surface:

    render_plan_page_to_png_bytes(pdf_path, page_index, dpi) -> bytes

Authoritative design:
    wiki/sprints/visual-overlay/vo-2-pdf-image-overlay-design-packet.md §3.3

PyMuPDF (``import fitz``) is imported LAZILY inside the function so that
flag-off import of the module remains cheap and so test environments
that do not install PyMuPDF can still import this module.  The lazy
import surfaces as a ``PlanPageRenderError`` if the dependency is
missing, which the route handler translates to a 500 response.

Hard sanity floors enforced at the helper layer (defense in depth — the
route handler validates first):

    48 <= dpi <= 300
    page_index >= 0
    rendered PNG <= 10 MB
"""

from __future__ import annotations

from pathlib import Path
from typing import Final


_MIN_DPI: Final[int] = 48
_MAX_DPI: Final[int] = 300
_MAX_BYTES: Final[int] = 10 * 1024 * 1024  # 10 MB ceiling per rendered file


class PlanPageRenderError(Exception):
    """Raised on any rendering failure or sanity-violation.

    Caller (route handler) catches this and converts to a 500 response.
    Internal detail (PyMuPDF exception type / message) is logged but NOT
    surfaced to clients.
    """


def render_plan_page_to_png_bytes(
    pdf_path: Path,
    page_index: int,
    dpi: int,
) -> bytes:
    """Render one PDF page to PNG bytes via PyMuPDF.

    Args:
        pdf_path:    on-disk path to the source PDF.  Must exist + be readable.
        page_index:  0-based page index.  Must be < the PDF's page_count.
        dpi:         render DPI, must be in [48, 300].

    Returns:
        PNG bytes (encoded image, ready to write to a file or HTTP body).

    Raises:
        PlanPageRenderError on any failure:
            - PDF file missing or unreadable
            - page_index out of range or not an int
            - dpi out of range or not an int
            - rendered output exceeds 10 MB cap
            - PyMuPDF internal exception
            - PyMuPDF (``fitz``) not installed

    Pure: no side effects; no env reads; no STATE; never writes to disk.
    """
    if not isinstance(pdf_path, Path):
        pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise PlanPageRenderError(f"PDF not found: {pdf_path}")

    if not isinstance(page_index, int) or isinstance(page_index, bool) or page_index < 0:
        raise PlanPageRenderError(
            f"page_index must be non-negative int; got {page_index!r}"
        )

    if not isinstance(dpi, int) or isinstance(dpi, bool) or dpi < _MIN_DPI or dpi > _MAX_DPI:
        raise PlanPageRenderError(
            f"dpi must be int in [{_MIN_DPI},{_MAX_DPI}]; got {dpi!r}"
        )

    # Lazy import: keeps flag-off code path free of the PyMuPDF cost and
    # lets tests that do not install PyMuPDF still import this module.
    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise PlanPageRenderError(f"PyMuPDF unavailable: {e}") from e

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        raise PlanPageRenderError(
            f"failed to open PDF: {type(e).__name__}: {e}"
        ) from e

    try:
        page_count = int(getattr(doc, "page_count", 0) or 0)
        if page_index >= page_count:
            raise PlanPageRenderError(
                f"page_index {page_index} out of range (page_count={page_count})"
            )
        try:
            page = doc.load_page(page_index)
        except Exception as e:
            raise PlanPageRenderError(
                f"failed to load page {page_index}: {type(e).__name__}: {e}"
            ) from e
        try:
            pix = page.get_pixmap(dpi=dpi)
            png_bytes: bytes = pix.tobytes("png")
        except Exception as e:
            raise PlanPageRenderError(
                f"failed to render page {page_index}: {type(e).__name__}: {e}"
            ) from e
    finally:
        try:
            doc.close()
        except Exception:
            pass

    if len(png_bytes) > _MAX_BYTES:
        raise PlanPageRenderError(
            f"rendered PNG size {len(png_bytes)} exceeds {_MAX_BYTES} bytes cap"
        )

    return png_bytes
