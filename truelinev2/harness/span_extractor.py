"""Seams 3+4+5 of the source-span extractor: the normalized SPAN-ROW CONTRACT, the STATION-PAIR / span-row
PARSER, and the BRIDGE that feeds ``ReviewReadinessEvidence``. Read-only, name-free, harness-only.

A source-confirmed span row means a source file EXPLICITLY tied two stations together as one bore — via explicit
start/end table columns, labeled start/end rows, or an inline name-free station-pair callout (``a+bb TO c+dd`` /
dash range). Bare station rulers and two unrelated standalone station labels are REFUSED. Nothing is invented:
every station is parsed by the canonical ``truelinev2.stations`` parser; footage is the printed value when
present, else the labeled `COMPUTED_FROM_STATIONS` difference of the two source stations; pairs come only from an
explicit source relationship (never proximity, never nearest, never min/max of an unlabeled column).

It draws nothing, places nothing, promotes nothing, and imports nothing from render / placement / api / store /
contracts / product runtime. It reuses the proven name-free grammar in ``extract.callout_anchor.span_callouts``
(which deliberately skips the named ``STA a TO STA b`` / ``DIR BORE`` dialect, so ``select_dialect`` is never
weakened). ``span_source_evidence_from_extraction`` feeds the review-readiness classifier; drawing is NOT wired.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from truelinev2.extract.callout_anchor import span_callouts
from truelinev2.harness.review_readiness import SpanSourceEvidence
from truelinev2.harness.span_source import (
    SourceDocument,
    discover_span_sources,
    documents_from_csv,
    documents_from_file,
    documents_from_pdf,
    documents_from_text,
    documents_from_xlsx,
)
from truelinev2.stations import feet_to_station, parse_station, strip_station_label

# --- span-row status + refusal vocabulary --------------------------------------------------------------- #
SPAN_ROW_CONFIRMED = "SPAN_ROW_CONFIRMED"                 # the only positive
NO_SOURCE_SPAN_FILE = "NO_SOURCE_SPAN_FILE"              # no candidate source file at all
# per-document refusals (a source WAS inspected but confirmed no span):
NO_TABLE_SPAN_COLUMNS = "NO_TABLE_SPAN_COLUMNS"
STATION_RULER_ONLY = "STATION_RULER_ONLY"
UNRELATED_STANDALONE_STATIONS = "UNRELATED_STANDALONE_STATIONS"
NO_STATION_SPAN_TEXT = "NO_STATION_SPAN_TEXT"
UNREADABLE_SOURCE = "UNREADABLE_SOURCE"

# --- confidence bands ----------------------------------------------------------------------------------- #
CONF_HIGH = "HIGH"          # explicit start/end columns or labeled start/end rows
CONF_MEDIUM = "MEDIUM"      # inline station-pair callout

# --- name-free column synonyms (lower-cased header cells) ------------------------------------------------ #
_START_COLS = {"start", "start_station", "start_sta", "from", "from_station", "from_sta", "begin", "entry",
               "sta_start", "startstation", "start station", "from station"}
_END_COLS = {"end", "end_station", "end_sta", "to", "to_station", "to_sta", "finish", "exit", "sta_end",
             "endstation", "end station", "to station"}
_STATION_COLS = {"station", "sta", "stationing", "station_ft"}
_FOOTAGE_COLS = {"footage", "footage_ft", "length", "length_ft", "span", "span_ft", "feet", "ft", "lf",
                 "bore_length", "bore_length_ft"}
_ROLE_COLS = {"notes", "note", "type", "point", "role", "position", "label", "endpoint"}
_ID_COLS = {"bore_id", "bore", "id", "bore_no", "bore_number", "bore_ref", "run", "run_id"}
_START_STRUCT_COLS = {"start_structure", "from_structure", "start_struct", "from_struct"}
_END_STRUCT_COLS = {"end_structure", "to_structure", "end_struct", "to_struct"}
_START_ROLE_WORDS = {"start", "begin", "entry", "from", "entrance"}
_END_ROLE_WORDS = {"end", "finish", "exit", "to"}

# Unlimited leading digits (matching the canonical stations.parse_station) + digit boundaries so a longer
# number is never re-anchored to a trailing substring (e.g. "1000+00" is one token, never "000+00").
_STATION_TOKEN_RE = re.compile(r"(?<!\d)\d+\+\d{2}(?:\.\d+)?(?!\d)")


# ======================================================================================================== #
# Seam 4 — the normalized span-row contract.
# ======================================================================================================== #
@dataclass(frozen=True)
class SpanRow:
    span_id: str
    source_file: str
    source_page: Optional[int]
    source_kind: str
    start_station: str
    end_station: str
    footage: Optional[float]
    start_structure: Optional[str]
    end_structure: Optional[str]
    status: str
    confidence: str
    citation: str
    bbox: Optional[Tuple[float, float, float, float]]
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["bbox"] = list(self.bbox) if self.bbox else None
        d["detail"] = dict(self.detail)
        return d


@dataclass(frozen=True)
class SpanRefusal:
    source_file: str
    source_page: Optional[int]
    reason: str
    detail: str


@dataclass(frozen=True)
class SpanExtraction:
    spans: Tuple[SpanRow, ...]
    refusals: Tuple[SpanRefusal, ...]
    source_files_seen: Tuple[str, ...]
    detail: Dict[str, Any] = field(default_factory=dict)

    @property
    def source_confirmed_span_count(self) -> int:
        return len(self.spans)

    @property
    def has_source_confirmed_span(self) -> bool:
        return bool(self.spans)

    def to_dict(self) -> dict:
        return {
            "spans": [s.to_dict() for s in self.spans],
            "refusals": [r.__dict__ for r in self.refusals],
            "source_files_seen": list(self.source_files_seen),
            "source_confirmed_span_count": self.source_confirmed_span_count,
            "detail": dict(self.detail),
        }


# ======================================================================================================== #
# Seam 3 — the parser.
# ======================================================================================================== #
def _find_col(header: Sequence[str], syn: set) -> Optional[int]:
    for i, h in enumerate(header):
        if h in syn:
            return i
    return None


def _cell(row: Sequence[str], i: Optional[int]) -> str:
    if i is None or i < 0 or i >= len(row):
        return ""
    return "" if row[i] is None else str(row[i]).strip()


def _station_from_cell(cell: str) -> Optional[Tuple[str, float]]:
    if not cell:
        return None
    ft = parse_station(strip_station_label(str(cell).strip()))
    if ft is None:
        return None
    return feet_to_station(ft), ft


def _num(cell: str) -> Optional[float]:
    try:
        return float(str(cell).strip())
    except (TypeError, ValueError):
        return None


def _make_span(doc: SourceDocument, idx: int, s: Tuple[str, float], e: Tuple[str, float],
               printed_footage: Optional[float], start_struct: Optional[str], end_struct: Optional[str],
               bore_ref: Optional[str], *, citation: str, confidence: str, grammar: str) -> SpanRow:
    start_sta, start_ft = s
    end_sta, end_ft = e
    if end_ft < start_ft:                                 # normalize low -> high (both are source stations)
        start_sta, start_ft, end_sta, end_ft = end_sta, end_ft, start_sta, start_ft
        start_struct, end_struct = end_struct, start_struct
    computed = round(abs(end_ft - start_ft), 4)
    if printed_footage is not None:
        footage, footage_source = printed_footage, "PRINTED"
    else:
        footage, footage_source = computed, "COMPUTED_FROM_STATIONS"
    detail: Dict[str, Any] = {"start_ft": start_ft, "end_ft": end_ft, "footage_source": footage_source,
                              "computed_footage": computed, "span_grammar": grammar}
    if bore_ref:
        detail["source_bore_ref"] = str(bore_ref)
    return SpanRow(span_id="span-%03d" % (idx + 1), source_file=doc.source_file, source_page=doc.source_page,
                   source_kind=doc.source_kind, start_station=start_sta, end_station=end_sta, footage=footage,
                   start_structure=(start_struct or None), end_structure=(end_struct or None),
                   status=SPAN_ROW_CONFIRMED, confidence=confidence, citation=citation[:200], bbox=None,
                   detail=detail)


def _parse_table(doc: SourceDocument, id_offset: int) -> List[SpanRow]:
    header = doc.table.header
    start_i, end_i = _find_col(header, _START_COLS), _find_col(header, _END_COLS)
    foot_i = _find_col(header, _FOOTAGE_COLS)
    ss_i, es_i = _find_col(header, _START_STRUCT_COLS), _find_col(header, _END_STRUCT_COLS)
    id_i = _find_col(header, _ID_COLS)
    out: List[SpanRow] = []

    if start_i is not None and end_i is not None:         # shape A: explicit start + end columns
        for row in doc.table.rows:
            s, e = _station_from_cell(_cell(row, start_i)), _station_from_cell(_cell(row, end_i))
            if not s or not e or abs(s[1] - e[1]) < 1e-9:
                continue
            printed = _num(_cell(row, foot_i)) if foot_i is not None else None
            out.append(_make_span(
                doc, id_offset + len(out), s, e, printed,
                _cell(row, ss_i) or None, _cell(row, es_i) or None, _cell(row, id_i) or None,
                citation=" | ".join(c for c in row if c), confidence=CONF_HIGH,
                grammar="EXPLICIT_START_END_COLUMNS"))
        return out

    sta_i, role_i = _find_col(header, _STATION_COLS), _find_col(header, _ROLE_COLS)
    if sta_i is not None and role_i is not None:          # shape B: single station col + labeled start/end rows
        starts, ends = [], []
        for row in doc.table.rows:
            st = _station_from_cell(_cell(row, sta_i))
            if not st:
                continue
            words = set(_cell(row, role_i).lower().split())
            if words & _START_ROLE_WORDS:
                starts.append((st, row))
            elif words & _END_ROLE_WORDS:
                ends.append((st, row))
        if len(starts) == 1 and len(ends) == 1 and abs(starts[0][0][1] - ends[0][0][1]) >= 1e-9:
            out.append(_make_span(
                doc, id_offset, starts[0][0], ends[0][0], None, None, None,
                _cell(starts[0][1], id_i) or None if id_i is not None else None,
                citation="labeled start/end rows", confidence=CONF_HIGH, grammar="LABELED_START_END_ROWS"))
        return out

    return []                                             # no span-bearing columns


def _rows_from_callouts(doc: SourceDocument, id_offset: int) -> List[SpanRow]:
    out: List[SpanRow] = []
    seen: set = set()
    for c in span_callouts(doc.text_lines):
        key = (c.from_sta, c.to_sta)
        if key in seen:
            continue
        seen.add(key)
        out.append(_make_span(doc, id_offset + len(out), (c.from_sta, c.from_ft), (c.to_sta, c.to_ft),
                              None, None, None, None, citation=c.text, confidence=CONF_MEDIUM,
                              grammar="INLINE_STATION_PAIR_CALLOUT"))
    return out


def _distinct_station_count(lines: Sequence[str]) -> int:
    seen: set = set()
    for ln in lines:
        for m in _STATION_TOKEN_RE.finditer(ln):
            ft = parse_station(m.group(0))
            if ft is not None:
                seen.add(ft)
    return len(seen)


def _spans_from_document(doc: SourceDocument, id_offset: int) -> Tuple[List[SpanRow], Optional[SpanRefusal]]:
    if doc.detail.get("unreadable"):
        return [], SpanRefusal(doc.source_file, doc.source_page, UNREADABLE_SOURCE, str(doc.detail["unreadable"]))
    if doc.table is not None:
        rows = _parse_table(doc, id_offset)
        if rows:
            return rows, None
        return [], SpanRefusal(doc.source_file, doc.source_page, NO_TABLE_SPAN_COLUMNS,
                               "no start/end span columns and no labeled start/end rows")
    rows = _rows_from_callouts(doc, id_offset)
    if rows:
        return rows, None
    n = _distinct_station_count(doc.text_lines)
    if n >= 3:
        reason = STATION_RULER_ONLY
    elif n == 2:
        reason = UNRELATED_STANDALONE_STATIONS
    else:
        reason = NO_STATION_SPAN_TEXT
    return [], SpanRefusal(doc.source_file, doc.source_page, reason,
                           "%d station token(s), no source-tied span" % n)


def extract_spans_from_documents(docs: Sequence[SourceDocument]) -> SpanExtraction:
    spans: List[SpanRow] = []
    refusals: List[SpanRefusal] = []
    files: List[str] = []
    for doc in docs:
        if doc.source_file and doc.source_file not in files:
            files.append(doc.source_file)
        doc_spans, refusal = _spans_from_document(doc, len(spans))
        spans.extend(doc_spans)
        if refusal is not None:
            refusals.append(refusal)
    return SpanExtraction(spans=tuple(spans), refusals=tuple(refusals), source_files_seen=tuple(files),
                          detail={"inspected": bool(docs), "documents": len(docs)})


# ======================================================================================================== #
# Composers (one per input kind).
# ======================================================================================================== #
def extract_spans_from_text(text: str, *, source_file: str = "text-input") -> SpanExtraction:
    return extract_spans_from_documents(documents_from_text(text, source_file=source_file))


def extract_spans_from_csv(path: str) -> SpanExtraction:
    return extract_spans_from_documents(documents_from_csv(path))


def extract_spans_from_xlsx(path: str) -> SpanExtraction:
    return extract_spans_from_documents(documents_from_xlsx(path))


def extract_spans_from_pdf(path: str) -> SpanExtraction:
    return extract_spans_from_documents(documents_from_pdf(path))


def extract_spans_from_folder(folder: str) -> SpanExtraction:
    sources = discover_span_sources(folder)
    if not sources:
        return SpanExtraction((), (SpanRefusal("", None, NO_SOURCE_SPAN_FILE,
                                               "no bore-log / schedule / span-table source file present"),),
                              (), {"inspected": False, "documents": 0})
    docs: List[SourceDocument] = []
    for path, kind in sources:
        docs.extend(documents_from_file(path, kind))
    return extract_spans_from_documents(docs)


# ======================================================================================================== #
# Seam 5 — the bridge to the review-readiness classifier (feeds ReviewReadinessEvidence; never draws).
# ======================================================================================================== #
def span_source_evidence_from_extraction(extraction: SpanExtraction, *,
                                         plan_span_layer_inspected: bool = False) -> SpanSourceEvidence:
    """Map a ``SpanExtraction`` onto the classifier's ``SpanSourceEvidence`` so it feeds
    ``ReviewReadinessEvidence.span``. The count drives SPAN_SOURCE_FOUND; a seen-but-unconfirmed source drives
    NO_SOURCE_CONFIRMED_SPAN; no source file at all drives MISSING_BORE_SPAN_SOURCE. Draws nothing."""
    return SpanSourceEvidence(
        bore_span_source_files=tuple(extraction.source_files_seen),
        plan_span_layer_inspected=plan_span_layer_inspected,
        source_confirmed_span_count=extraction.source_confirmed_span_count,
        detail={"span_refusal_reasons": sorted({r.reason for r in extraction.refusals})})


def format_extraction(extraction: SpanExtraction) -> str:
    return json.dumps(extraction.to_dict(), indent=2, sort_keys=True)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Harness-only diagnostic CLI: ``python -m truelinev2.harness.span_extractor <file-or-folder>``. Reads a
    source file or a package folder, prints the extracted span rows + refusals as JSON. Writes nothing, draws
    nothing."""
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        sys.stderr.write("usage: span_extractor <file-or-folder>\n")
        return 2
    target = Path(args[0])
    if target.is_dir():
        extraction = extract_spans_from_folder(str(target))
    else:
        extraction = extract_spans_from_documents(documents_from_file(str(target)))
    print(format_extraction(extraction))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
