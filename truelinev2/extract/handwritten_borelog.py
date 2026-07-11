"""Phase-1 handwritten/scanned bore-log extraction -- the seam between an untrusted upload's BYTES and the
Wave-1 contract (``contracts/handwritten_extraction.py``: Cell / HandwrittenPageExtraction / SpanProposal /
spans_from_page / rbl_fanout_plan -- composed here, never redesigned).

Owns, purely from ``(upload_bytes, filename)`` -- no store I/O, no engine/renderer import:
  1. PAGE ITERATION -- a text-layer PDF becomes one page per PDF page (PyMuPDF text); an image upload
     (.jpg/.jpeg/.png) becomes ONE pseudo-page (page_index 0, no text layer -- there is nothing else to
     read from a bare photo). ``rasterize_page`` is the shared PNG-raster helper (also used by the
     flag-gated source-page byte-serving route, so the review UI can show the SAME page image this module
     read/attempted).
  2. TEXT_LAYER PARSING -- a tolerant regex reader over a text-layer page's own extracted text: header
     fields (DATE / CREW / Job Name / Print #, "SATION" tolerated as a STATION column misprint) + up to 4
     printed STATION|DEPTH|BOC column groups per printed row ("STA " prefix and foot-tick ("'") suffixes
     normalized away into ``Cell.value``, the raw text kept verbatim in ``Cell.verbatim``). Deterministic;
     never guesses -- an unmatched line simply contributes no reading.
  3. VISION-PROVIDER SEAM -- a page with NO usable text layer (a scanned/photographed page, or a bare image
     upload) needs a provider. The registry is a plain ``name -> callable(page_png_bytes, context) ->
     HandwrittenPageExtraction`` dict and ships EMPTY in this wave (no network code, no vendor/model name
     anywhere in this seam) -- an unset/unknown provider name always refuses honestly with
     ``HANDWRITTEN_VISION_PROVIDER_NOT_CONFIGURED``. A configured provider call is wrapped in a hard
     threading-based timeout (``HANDWRITTEN_EXTRACTION_TIMEOUT``) and its output is re-validated through
     ``validate_page_extraction`` before being trusted (``HANDWRITTEN_PROVIDER_OUTPUT_INVALID`` otherwise).
     Tests inject a private fake provider via the ``providers=`` parameter; production callers never pass
     it, so the registry stays empty end-to-end.
  4. PAGE LEDGER -- ``build_page_ledger`` guarantees EVERY physical page is accounted for exactly once
     (EXTRACTED / REFUSED / NO_USABLE_STATION_RUN), including a page whose only station runs were too
     short to normalize into a span (those runs' warnings are folded into the ledger entry itself, not left
     to vanish when the page produces zero proposals to carry them).
  5. ``extract_handwritten`` -- the pure top-level entry point: builds every page, runs
     ``spans_from_page`` over each (Wave-1, untouched), and returns ``{"pages", "proposals",
     "page_ledger"}``.

Naming: "provider"/"extractor" are opaque runtime data (a deployment-supplied label), never a hardcoded
vendor/model name. No engine, renderer, dialect registry, or AI/OCR network call lives here.
"""
from __future__ import annotations

import hashlib
import io
import re
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from truelinev2.contracts.handwritten_extraction import (
    EXTRACTED,
    HandwrittenExtractionError,
    MEDIUM,
    NOT_PRESENT,
    PAGE_RECORD_FORMAT,
    READ,
    REFUSED,
    TEXT_LAYER,
    VISION_OCR,
    spans_from_page,
    validate_page_extraction,
)
from truelinev2.stations import parse_station, strip_station_label

DEFAULT_TIMEOUT_SECONDS = 90

# Named refusal reason codes (this module's own; distinct from the Wave-1 contract's page_status/refusal
# SHAPE, which this module fills in). Kept local -- never leaked as a raw exception string, never a
# filesystem path.
HANDWRITTEN_VISION_PROVIDER_NOT_CONFIGURED = "HANDWRITTEN_VISION_PROVIDER_NOT_CONFIGURED"
HANDWRITTEN_EXTRACTION_TIMEOUT = "HANDWRITTEN_EXTRACTION_TIMEOUT"
HANDWRITTEN_PROVIDER_OUTPUT_INVALID = "HANDWRITTEN_PROVIDER_OUTPUT_INVALID"
# Raised by extract/borelog_rows.py's third tier when the handwritten extractor ran but found zero usable
# proposals across every page (defined HERE, imported there, so the reason code has one home).
HANDWRITTEN_NO_USABLE_ROWS = "HANDWRITTEN_NO_USABLE_ROWS"

# A structured page-ledger "run skipped" reason (mirrors, in a stable machine-readable code, the human
# message spans_from_page folds into every proposal's warnings for a run with < 2 usable stations).
TOO_FEW_USABLE_STATIONS = "TOO_FEW_USABLE_STATIONS"

# Vision-provider registry: name -> callable(page_png_bytes: bytes, context: dict) -> HandwrittenPageExtraction.
# EMPTY in this wave -- no network provider is wired. Production callers never pass ``providers=`` to
# ``extract_handwritten``/``_vision_page``, so this module-level registry (never mutated at runtime) is
# what they always get: every vision-needing page refuses HANDWRITTEN_VISION_PROVIDER_NOT_CONFIGURED.
_PROVIDERS: Dict[str, Callable[[bytes, dict], dict]] = {}

_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")

_NUM_RE = re.compile(r"[-+]?\d*\.?\d+")
# One printed STATION | DEPTH | BOC triple: an optional "STA"/"STA."/"STA:" label, a station in A+BB
# notation, then two foot-ish numbers (an optional trailing "'" tick mark tolerated on either).
_TRIPLE_RE = re.compile(
    r"(?P<sta_label>STA[.:]?\s+)?(?P<station>\d+\+\d+(?:\.\d+)?)\s+"
    r"(?P<depth>\d+(?:\.\d+)?)\s*'?\s+(?P<boc>\d+(?:\.\d+)?)\s*'?",
    re.IGNORECASE,
)

# Header label -> the sequence of bare (punctuation-stripped) UPPERCASE tokens that spells it out ("Job
# Name" prints as two words; the other three are one). Positional, not regex-over-text: a real form's
# label and its value are often SEPARATE text runs that PyMuPDF's plain "text" mode does not concatenate
# onto one line -- see ``_parse_header_positional`` below.
_HEADER_LABEL_TOKENS = {
    "date": ("DATE",),
    "crew": ("CREW",),
    "job_name": ("JOB", "NAME"),
    "print_raw": ("PRINT",),
}
# Bounded search geometry (PDF points) for locating a label's VALUE by position -- fail-closed: anything
# outside these bounds is simply not found (NOT_PRESENT), never guessed.
_VALUE_RIGHT_MAX_GAP = 220.0     # max horizontal gap from the label's right edge to the FIRST value word
_VALUE_RIGHT_INTERNAL_GAP = 40.0  # max gap BETWEEN consecutive value words (stops before sweeping the next field)
_VALUE_RIGHT_MAX_SPAN = 260.0    # max total width a same-line value may span from the label's right edge
_VALUE_BELOW_Y_TOL = 1.8         # multiples of label height -- max vertical drop to a below-label value
_VALUE_BELOW_X_TOL = 40.0        # max horizontal drift of a below-label value's left edge from the label's


# --------------------------------------------------------------------------- #
# Page iteration -- text extraction + rasterization, both operating on in-memory BYTES (no temp files).
# --------------------------------------------------------------------------- #
def _pdf_page_texts(pdf_bytes: bytes) -> List[str]:
    """Per-page extracted text of a PDF (PyMuPDF -- the repo's only PDF engine), one entry per page in
    order. An unreadable/corrupt PDF yields an empty list (the caller then produces zero pages -- an
    honest, if unusual, outcome; never raises past this seam)."""
    import fitz  # lazy: keeps this module importable with only stdlib until actually used

    try:
        doc = fitz.open(stream=bytes(pdf_bytes), filetype="pdf")
    except Exception:  # noqa: BLE001 - not a readable PDF -> zero pages, never a raised exception here
        return []
    try:
        return [(doc[i].get_text("text") or "") for i in range(doc.page_count)]
    finally:
        doc.close()


def _pdf_page_words(pdf_bytes: bytes) -> List[List[dict]]:
    """Per-page WORD tokens with DISPLAY-space bboxes (PyMuPDF ``get_text('words')``), one list per page in
    order. Positional counterpart to ``_pdf_page_texts``: lets the header parser locate a printed label's
    value by PROXIMITY instead of assuming the label and its value share one extracted text line (a real
    form's actual failure mode -- the label and value are often separate text runs)."""
    import fitz  # lazy

    try:
        doc = fitz.open(stream=bytes(pdf_bytes), filetype="pdf")
    except Exception:  # noqa: BLE001 - unreadable PDF -> zero pages, never a raised exception here
        return []
    try:
        out: List[List[dict]] = []
        for i in range(doc.page_count):
            words = []
            for w in doc[i].get_text("words") or ():
                x0, y0, x1, y1, text = float(w[0]), float(w[1]), float(w[2]), float(w[3]), w[4]
                words.append({"text": text, "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                             "yc": (y0 + y1) / 2.0, "height": max(y1 - y0, 1.0)})
            out.append(words)
        return out
    finally:
        doc.close()


def rasterize_page(pdf_bytes: bytes, page_index: int, *, zoom: float = 2.0) -> Optional[bytes]:
    """Full-page PNG raster of ONE 0-based PDF page (the source AS-IS -- no overlay, no redline). Shared by
    the vision-provider seam (a page with no text layer) and the flag-gated source-page byte-serving route
    (so the review UI can show the SAME page image). Returns None if the PDF is unreadable or the page
    index is out of range. Writes nothing to disk."""
    import fitz  # lazy: mirrors ingest/pdf.py's own lazy-fitz convention

    try:
        doc = fitz.open(stream=bytes(pdf_bytes), filetype="pdf")
    except Exception:  # noqa: BLE001 - unreadable PDF -> honest None, never a raised exception here
        return None
    try:
        if not (0 <= page_index < doc.page_count):
            return None
        page = doc[page_index]
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csRGB, alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()


def _image_to_png_bytes(raw: bytes) -> bytes:
    """Normalize a stored image upload's bytes (JPEG or PNG) to PNG bytes for the vision-provider callable
    contract (``page_png_bytes``). Pillow is an already-pinned dependency."""
    from PIL import Image  # lazy

    img = Image.open(io.BytesIO(bytes(raw)))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Cell builders (local -- Wave-1's contract validates cells, it does not build them).
# --------------------------------------------------------------------------- #
def _empty_cell() -> dict:
    return {"value": None, "verbatim": None, "status": NOT_PRESENT, "confidence": None, "region": None}


def _read_cell(value, *, verbatim: Optional[str] = None, confidence=MEDIUM) -> dict:
    return {"value": value, "verbatim": verbatim if verbatim is not None else (str(value) if value is not None else None),
           "status": READ, "confidence": confidence, "region": None}


def _blank_header() -> dict:
    return {"date": _empty_cell(), "crew": _empty_cell(), "job_name": _empty_cell(), "print_raw": _empty_cell()}


# --------------------------------------------------------------------------- #
# TEXT_LAYER parsing -- positional header capture (word bboxes) + a tolerant ladder-row regex reader over
# the page's own extracted text.
# --------------------------------------------------------------------------- #
def _norm_label_token(text: str) -> str:
    """Fold one word token to bare uppercase letters (drops attached punctuation like "DATE:"/"PRINT#:")."""
    return re.sub(r"[^A-Za-z]", "", text or "").upper()


def _find_label_span(words: List[dict], tokens: Tuple[str, ...]) -> Optional[List[int]]:
    """First run of consecutive word INDICES whose normalized text exactly spells ``tokens`` in order
    (e.g. ("JOB","NAME") matches word tokens "Job" "Name:"). None if no such run exists."""
    n = len(tokens)
    for i in range(len(words) - n + 1):
        if all(_norm_label_token(words[i + j]["text"]) == tokens[j] for j in range(n)):
            return list(range(i, i + n))
    return None


def _value_words_right(words: List[dict], label_words: List[dict], exclude: set) -> List[dict]:
    """Bounded rightward search: word(s) on the SAME printed line (y-overlap within the label's own height)
    strictly right of the label, stopping at the first internal gap that looks like the start of the NEXT
    field. Fail-closed -- returns [] rather than guessing when nothing qualifies within the bounds."""
    end_x = max(w["x1"] for w in label_words)
    yc = sum(w["yc"] for w in label_words) / len(label_words)
    tol = max(w["height"] for w in label_words) * 0.9
    candidates = [w for i, w in enumerate(words)
                 if i not in exclude and w["x0"] > end_x and abs(w["yc"] - yc) <= tol
                 and (w["x0"] - end_x) <= _VALUE_RIGHT_MAX_GAP]
    candidates.sort(key=lambda w: w["x0"])
    out: List[dict] = []
    prev_x1: Optional[float] = None      # None -> the NEXT check is the label-to-first-word gap (generous)
    for w in candidates:
        gap = (w["x0"] - end_x) if prev_x1 is None else (w["x0"] - prev_x1)
        limit = _VALUE_RIGHT_MAX_GAP if prev_x1 is None else _VALUE_RIGHT_INTERNAL_GAP
        if gap > limit:
            break
        if w["x1"] - end_x > _VALUE_RIGHT_MAX_SPAN:
            break
        out.append(w)
        prev_x1 = w["x1"]
    return out


def _value_words_below(words: List[dict], label_words: List[dict], exclude: set) -> List[dict]:
    """Bounded downward search (forms vary: a value printed on the line BELOW its label instead of beside
    it) -- the nearest line under the label whose left edge roughly aligns with the label's own left edge.
    Fail-closed -- [] when nothing qualifies within the bounds."""
    x0 = min(w["x0"] for w in label_words)
    y1 = max(w["y1"] for w in label_words)
    h = max(w["height"] for w in label_words)
    candidates = [w for i, w in enumerate(words)
                 if i not in exclude and w["yc"] > y1 and (w["yc"] - y1) <= h * _VALUE_BELOW_Y_TOL
                 and abs(w["x0"] - x0) <= _VALUE_BELOW_X_TOL]
    if not candidates:
        return []
    candidates.sort(key=lambda w: (w["yc"], w["x0"]))
    first_yc = candidates[0]["yc"]
    same_line = sorted((w for w in candidates if abs(w["yc"] - first_yc) < h * 0.6), key=lambda w: w["x0"])
    return same_line


# Own-label-prefix stripper (see ``_strip_label_prefix``): matches the field's OWN label spelling at the
# start of a captured VALUE string, requiring a boundary (colon/whitespace/end -- never mid-word, e.g.
# "DATEX ..." must NOT strip to "X ...") after it so an unrelated value that happens to start with the same
# letters is left untouched.
_LABEL_PREFIX_RE = {
    "date": re.compile(r"(?i)^\s*DATE(?=$|[\s:])\s*:?\s*"),
    "crew": re.compile(r"(?i)^\s*CREW(?=$|[\s:])\s*:?\s*"),
    "job_name": re.compile(r"(?i)^\s*JOB\s+NAME(?=$|[\s:])\s*:?\s*"),
    "print_raw": re.compile(r"(?i)^\s*PRINT(?=$|[\s:#])\s*#?\s*:?\s*"),
}


def _strip_label_prefix(field: str, text: str) -> Optional[str]:
    """If a captured header VALUE begins with its OWN field's label token (label+value merged into one
    captured run -- e.g. a same-run "DATE: 2/11/2026" whose value search picked up "DATE:" along with the
    date -- rather than a genuinely separate label/value pair), strip that prefix from the NORMALIZED
    value. ``verbatim`` (built separately by the caller from the full captured run) is UNTOUCHED -- it stays
    the complete evidence regardless. A value that legitimately starts with unrelated text (not this
    field's own label, word-boundary-checked) is left unchanged. Returns None when nothing remains after
    stripping -- an empty value is NOT_PRESENT, never an empty string."""
    pattern = _LABEL_PREFIX_RE.get(field)
    stripped = pattern.sub("", text, count=1) if pattern is not None else text
    stripped = stripped.strip(" :#-\t")
    return stripped or None


def _parse_header_positional(words: List[dict]) -> dict:
    """Locate each of the 4 header labels by TEXT (not position) then its value by POSITION: nearest word
    run to the label's right (same printed line), else the nearest line below, within bounded distances.
    A label not found, or found with no value within bounds, stays NOT_PRESENT -- fail-closed, never a
    fuzzy guess beyond this positional rule. A captured value that itself begins with the SAME field's own
    label (a merged label+value run) has that prefix stripped -- see ``_strip_label_prefix``."""
    header = _blank_header()
    if not words:
        return header
    spans: Dict[str, List[int]] = {}
    for field, tokens in _HEADER_LABEL_TOKENS.items():
        span = _find_label_span(words, tokens)
        if span is not None:
            spans[field] = span
    label_idx_set = {i for span in spans.values() for i in span}   # a label's own tokens are never a value
    for field, idxs in spans.items():
        label_words = [words[i] for i in idxs]
        value_words = _value_words_right(words, label_words, label_idx_set)
        if not value_words:
            value_words = _value_words_below(words, label_words, label_idx_set)
        if not value_words:
            continue
        text = " ".join(w["text"] for w in value_words).strip(" :#-\t")
        if not text:
            continue
        text = _strip_label_prefix(field, text)
        if not text:
            continue
        verbatim = (" ".join(w["text"] for w in label_words) + " "
                   + " ".join(w["text"] for w in value_words)).strip()
        header[field] = _read_cell(text, verbatim=verbatim)
    return header


def _parse_ladder(lines: List[str]) -> List[dict]:
    """Every printed STATION|DEPTH|BOC triple across up to 4 column groups per physical row. A text LINE is
    one printed row; every triple matched on that line is one column group (column_index = its left-to-right
    order on the line), so multiple bores side-by-side on one row are preserved as separate columns (the
    Wave-1 run-splitter then treats each column's own station sequence independently)."""
    readings: List[dict] = []
    row_index = 0
    for line in lines:
        matches = list(_TRIPLE_RE.finditer(line))
        if not matches:
            continue
        for column_index, m in enumerate(matches):
            sta_text = (m.group("sta_label") or "") + m.group("station")
            station_value = strip_station_label(sta_text).strip()
            depth_text, boc_text = m.group("depth"), m.group("boc")
            readings.append({
                "station": _read_cell(station_value, verbatim=sta_text.strip()),
                "depth_ft": _read_cell(float(depth_text), verbatim=depth_text + ("'" if "'" in m.group(0) else "")),
                "boc_ft": _read_cell(float(boc_text), verbatim=boc_text),
                "column_index": column_index,
                "row_index": row_index,
            })
        row_index += 1
    return readings


def _text_layer_page(source: dict, text: str, words: Optional[List[dict]] = None, *,
                     extractor: str = "text_layer_parser") -> dict:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    record = {
        "record_format": PAGE_RECORD_FORMAT,
        "source": source,
        "method": TEXT_LAYER,
        "extractor": extractor,
        "header": _parse_header_positional(words or []),
        "readings": _parse_ladder(lines),
        "page_status": EXTRACTED,
        "refusal": None,
        "warnings": [],
        "audit": [],
    }
    validate_page_extraction(record)
    return record


# --------------------------------------------------------------------------- #
# Vision-provider seam -- registry lookup + hard timeout + output re-validation.
# --------------------------------------------------------------------------- #
def _refused_page(source: dict, *, code: str, reason: str, extractor: str) -> dict:
    record = {
        "record_format": PAGE_RECORD_FORMAT,
        "source": source,
        "method": VISION_OCR,
        "extractor": extractor,
        "header": _blank_header(),
        "readings": [],
        "page_status": REFUSED,
        "refusal": {"code": code, "reason": reason},
        "warnings": [],
        "audit": [],
    }
    validate_page_extraction(record)
    return record


def _run_provider_with_timeout(fn, page_png_bytes: bytes, context: dict, timeout_s: float
                               ) -> Tuple[Optional[dict], Optional[str]]:
    """Run ONE provider callable in a daemon worker thread with a hard join timeout. Returns
    ``(record, error_code)``: ``error_code`` is None on a schema-valid success, else
    HANDWRITTEN_EXTRACTION_TIMEOUT (still running past the deadline) or HANDWRITTEN_PROVIDER_OUTPUT_INVALID
    (the call raised, or its output failed ``validate_page_extraction``)."""
    box: Dict[str, Any] = {}

    def _run() -> None:
        try:
            box["result"] = fn(page_png_bytes, context)
        except Exception as exc:  # noqa: BLE001 - any provider failure -> an honest named refusal, never a 500
            box["error"] = exc

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        return None, HANDWRITTEN_EXTRACTION_TIMEOUT
    if "error" in box:
        return None, HANDWRITTEN_PROVIDER_OUTPUT_INVALID
    record = box.get("result")
    try:
        validate_page_extraction(record)
    except HandwrittenExtractionError:
        return None, HANDWRITTEN_PROVIDER_OUTPUT_INVALID
    return record, None


def _vision_page(source: dict, page_png_bytes: bytes, *, provider_name: Optional[str],
                 providers: Optional[Dict[str, Callable]], timeout_s: float) -> dict:
    """Resolve one page that needs a vision provider (no usable text layer): registry lookup -> timeout-
    wrapped call -> re-validated output, or an honest named refusal at any step."""
    registry = _PROVIDERS if providers is None else providers
    fn = registry.get(provider_name) if provider_name else None
    if fn is None:
        return _refused_page(
            source, code=HANDWRITTEN_VISION_PROVIDER_NOT_CONFIGURED,
            reason="no vision provider is configured for handwritten bore-log extraction",
            extractor=provider_name or "unconfigured")
    context = {"upload_id": source["upload_id"], "file_name": source["file_name"],
              "page_index": source["page_index"], "page_count": source["page_count"]}
    record, err = _run_provider_with_timeout(fn, page_png_bytes, context, timeout_s)
    if err == HANDWRITTEN_EXTRACTION_TIMEOUT:
        return _refused_page(
            source, code=HANDWRITTEN_EXTRACTION_TIMEOUT,
            reason="the vision provider did not return a result within %s seconds" % timeout_s,
            extractor=provider_name)
    if err == HANDWRITTEN_PROVIDER_OUTPUT_INVALID:
        return _refused_page(
            source, code=HANDWRITTEN_PROVIDER_OUTPUT_INVALID,
            reason="the vision provider's output failed schema/honesty validation",
            extractor=provider_name)
    return record


# --------------------------------------------------------------------------- #
# Page ledger -- every physical page accounted for exactly once (MUST-FIX: short/descending runs' warnings
# must appear here, never vanish when a page produces zero proposals to carry them).
# --------------------------------------------------------------------------- #
def _reading_station_feet(reading: dict) -> Optional[float]:
    cell = reading["station"]
    if cell["status"] != READ or cell["value"] is None:
        return None
    value = cell["value"]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return parse_station(strip_station_label(str(value)))


def _runs_from_readings(readings: List[dict]) -> List[List[dict]]:
    """MIRROR of ``handwritten_extraction.spans_from_page``'s run-splitting, reimplemented locally so the
    page ledger can report STRUCTURED run boundaries (first/last row_index) -- spans_from_page itself only
    returns human-readable warning strings folded into proposals, never a run's row-index span. Produces
    the IDENTICAL partition spans_from_page computes internally; never influences it (read-only, additive)."""
    usable = []
    for reading in sorted(readings, key=lambda r: (r["column_index"], r["row_index"])):
        feet = _reading_station_feet(reading)
        if feet is not None:
            usable.append((feet, reading))
    runs: List[List[dict]] = []
    current: List[Tuple[float, dict]] = []
    for feet, reading in usable:
        if current and feet <= current[-1][0]:
            runs.append([r for _, r in current])
            current = []
        current.append((feet, reading))
    if current:
        runs.append([r for _, r in current])
    return runs


def build_page_ledger(pages: List[dict], proposals_by_page: Dict[int, List[dict]]) -> List[dict]:
    """Every physical page, exactly once, in page_index order: ``{page_index, status, refusal, warnings,
    proposal_count, runs_skipped}``. ``status`` is EXTRACTED (>=1 proposal), REFUSED (the page itself
    refused -- refusal carries the named code/reason), or NO_USABLE_STATION_RUN (the page read fine but
    every station run was too short to normalize -- their warnings are captured HERE via ``runs_skipped``,
    never left to vanish because no proposal exists to carry them)."""
    ledger = []
    for page in sorted(pages, key=lambda p: p["source"]["page_index"]):
        idx = page["source"]["page_index"]
        proposals = proposals_by_page.get(idx, [])
        if page["page_status"] == REFUSED:
            ledger.append({
                "page_index": idx, "status": REFUSED,
                "refusal": dict(page["refusal"]), "warnings": list(page.get("warnings") or []),
                "proposal_count": 0, "runs_skipped": [],
            })
            continue
        runs_skipped = []
        warnings = list(page.get("warnings") or [])
        for run in _runs_from_readings(page["readings"]):
            if len(run) < 2:
                reading = run[0]
                msg = ("run at column %d row %d has fewer than 2 usable station readings; skipped"
                      % (reading["column_index"], reading["row_index"]))
                warnings.append(msg)
                runs_skipped.append({"reason": TOO_FEW_USABLE_STATIONS,
                                     "first_row_index": reading["row_index"],
                                     "last_row_index": reading["row_index"]})
        status = EXTRACTED if proposals else "NO_USABLE_STATION_RUN"
        ledger.append({
            "page_index": idx, "status": status, "refusal": None, "warnings": warnings,
            "proposal_count": len(proposals), "runs_skipped": runs_skipped,
        })
    return ledger


# --------------------------------------------------------------------------- #
# Top-level entry point -- pure over (upload_bytes, filename); no store I/O.
# --------------------------------------------------------------------------- #
def extract_handwritten(upload_bytes: bytes, filename: str, *, upload_id: str,
                        provider_name: Optional[str] = None,
                        timeout_s: float = DEFAULT_TIMEOUT_SECONDS,
                        providers: Optional[Dict[str, Callable]] = None) -> dict:
    """Extract one uploaded BORE_LOG file's bytes into ``{"pages": [...], "proposals": [...],
    "page_ledger": [...]}``. A text-layer PDF page parses deterministically (TEXT_LAYER); a page with no
    usable text layer (a scanned PDF page, or any image upload -- one pseudo-page) is resolved through the
    vision-provider seam (empty registry in production -> an honest named refusal). Pure: no store I/O, no
    engine/renderer import, no network call. ``providers``/non-default ``provider_name`` are for TEST
    injection only -- production callers never populate the registry."""
    data = bytes(upload_bytes)
    sha = hashlib.sha256(data).hexdigest()
    ext = Path(str(filename)).suffix.lower()

    pages: List[dict] = []
    if ext == ".pdf":
        texts = _pdf_page_texts(data)
        words_by_page = _pdf_page_words(data)
        page_count = len(texts) or 1
        for idx, text in enumerate(texts):
            source = {"upload_id": upload_id, "sha256": sha, "file_name": str(filename),
                     "page_index": idx, "page_count": page_count}
            if text.strip():
                page_words = words_by_page[idx] if idx < len(words_by_page) else []
                pages.append(_text_layer_page(source, text, page_words))
            else:
                png = rasterize_page(data, idx) or b""
                pages.append(_vision_page(source, png, provider_name=provider_name,
                                          providers=providers, timeout_s=timeout_s))
    else:
        source = {"upload_id": upload_id, "sha256": sha, "file_name": str(filename),
                 "page_index": 0, "page_count": 1}
        png = _image_to_png_bytes(data) if ext in _IMAGE_EXTENSIONS else data
        pages.append(_vision_page(source, png, provider_name=provider_name,
                                  providers=providers, timeout_s=timeout_s))

    proposals: List[dict] = []
    proposals_by_page: Dict[int, List[dict]] = {}
    for page in pages:
        page_proposals = spans_from_page(page)
        proposals_by_page[page["source"]["page_index"]] = page_proposals
        proposals.extend(page_proposals)

    return {"pages": pages, "proposals": proposals,
           "page_ledger": build_page_ledger(pages, proposals_by_page)}
