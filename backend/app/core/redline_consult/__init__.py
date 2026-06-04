"""Default-OFF redline consult package (matchline / station-frame resolver + source-station
corrections + BOC placement-proof). Vendored from the clean-room scratch lane; consulted by
``app.core.pdf_first_adapter`` ONLY behind ``TRUELINE_MATCHLINE_FRAME_RESOLVER``. With the flag
unset nothing here is imported and the adapter envelope is byte-identical.

Owner-reviewed ledgers live under ``app/core/_redline_data`` (frame_resolutions / corrections /
boc_evidence). The orchestration entry points are in :mod:`.consult`."""
from .consult import apply_corrections, apply_resolver, classify, open_document

__all__ = ["apply_corrections", "apply_resolver", "classify", "open_document"]
