r"""Handwritten bore-log corpus ACCEPTANCE HARNESS -- a generic, offline-testable CLI that runs Phase-1
handwritten extraction (``truelinev2/extract/handwritten_borelog.py::extract_handwritten``) over EVERY
``.pdf``/``.jpg``/``.jpeg``/``.png`` file in a caller-supplied corpus directory and produces decision-grade
statistics + two HARD safety checks, never a store write and never a network call.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.qa.run_handwritten_corpus_acceptance \
      --corpus <dir> --out <dir> [--provider <dotted.module.path>] [--fixtures <dir>] [--timeout-s N]

Three run modes (same command, only ``--provider``/``--fixtures`` change):
  (a) no ``--provider``     -- keyless, works today: text-layer PDF pages extract; every image/scanned
                                page honestly refuses ``HANDWRITTEN_VISION_PROVIDER_NOT_CONFIGURED``.
  (b) ``--provider truelinev2.extract.vision_providers.fake --fixtures <dir>`` -- deterministic,
                                fixture-driven vision-provider run (see that module's own docstring for
                                its fixture-file naming: ``<sha256>-p<page_index>.json``).
  (c) ``--provider <a real adapter's dotted module path>`` -- the POST-CREDENTIAL validation run, once an
                                owner opts a real vendor adapter in. This harness never names, imports, or
                                references that module path anywhere -- ``--provider`` is opaque runtime
                                data, exactly like the seam it drives.

Two HARD checks (either failing means exit code 2, never a silent report):
  RECONCILIATION -- every physical page of every file (recounted independently of the extraction seam's
    own page iteration, straight off the file bytes) appears in that file's page_ledger EXACTLY once.
  NO-FABRICATION SCAN -- walks every page + proposal this run produced: a Cell-shaped dict may never carry
    a non-null value on a non-READ status, and a Cell/proposal confidence may never be HIGH (Phase-1 reads
    are LOW/MEDIUM only); every proposal's footage_ft is independently RECOMPUTED from its start/end
    station and must match exactly, with footage_derivation == "DERIVED_FROM_STATIONS"; every proposal
    field that carries a value must have a corresponding ``cell_evidence`` entry. This scan is DEFENSE IN
    DEPTH -- ``extract_handwritten``'s own ``validate_page_extraction`` already enforces the value/status
    invariant on every record it returns, so this only fires if that invariant were ever bypassed
    (a differently-wired provider, a future refactor, ...); the harness never trusts the seam blindly.

Both checks are HARD: a failure is reported by name (which file, which field) and the process exits 2.
Refusals (any named reason code, on any page) are FINE -- they are honest outcomes, not harness failures,
and never affect the exit code on their own.

Naming: no corpus path, customer/person/project/location name, or file count is ever hardcoded here --
the corpus directory, output directory, provider module path, and fixtures directory are all caller-
supplied. Report content never carries an absolute path -- only relative file names (posix, relative to
the corpus root) and sha256 hex digests.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from truelinev2.contracts.handwritten_extraction import DERIVED_FROM_STATIONS, READ
from truelinev2.extract.handwritten_borelog import DEFAULT_TIMEOUT_SECONDS, extract_handwritten
from truelinev2.stations import parse_station, strip_station_label

REPORT_RECORD_FORMAT = "trueline-handwritten-corpus-acceptance-report-1"

# This harness's own file-type scope -- the same set extract_handwritten distinguishes between (a
# text-layer-capable PDF vs an image that always needs a vision provider).
_SUPPORTED_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png")

# The fake vision provider's OWN env var (see extract/vision_providers/fake.py's module docstring) --
# named HERE only because this harness is the one caller allowed to drive it deterministically for a
# reproducible QA run; the extraction seam itself never names it. Not the real vendor adapter's env var
# (that module is never named anywhere in this file -- see the module docstring, mode (c)).
_FAKE_PROVIDER_FIXTURES_ENV = "TL2_HANDWRITTEN_FAKE_FIXTURES"

_CELL_KEYS = frozenset({"value", "verbatim", "status", "confidence", "region"})
_PROPOSAL_EVIDENCE_FIELDS = ("start_station", "end_station", "print_raw", "date", "crew", "depth_ft", "boc_ft")

_WARNING_NUM_RE = re.compile(r"\d+")


class HarnessError(RuntimeError):
    """A harness-level failure (bad corpus/out directory, ...) -- distinct from a reconciliation/
    fabrication FINDING, which is reported in report.json rather than raised. Maps to exit code 1."""


# --------------------------------------------------------------------------- #
# Corpus enumeration + per-file processing.
# --------------------------------------------------------------------------- #
def _collect_corpus_files(corpus_dir: Path) -> List[Path]:
    """Every supported file under ``corpus_dir`` (recursive), sorted by its path RELATIVE to the corpus
    root for a deterministic, machine-portable order (never by absolute path)."""
    return sorted(
        (p for p in corpus_dir.rglob("*") if p.is_file() and p.suffix.lower() in _SUPPORTED_EXTENSIONS),
        key=lambda p: p.relative_to(corpus_dir).as_posix(),
    )


def _independent_page_count(data: bytes, ext: str) -> int:
    """Page count recounted INDEPENDENTLY of ``extract_handwritten``'s own page iteration -- straight off
    the file bytes via PyMuPDF for a PDF, or 1 for a single-frame image upload (the extraction seam's own
    "one pseudo-page per image" rule). An unreadable PDF recounts as 0 (honest -- extract_handwritten
    itself then produces zero pages for it, so reconciliation still agrees)."""
    if ext != ".pdf":
        return 1
    import fitz  # lazy, mirrors handwritten_borelog.py's own lazy-fitz convention

    try:
        doc = fitz.open(stream=bytes(data), filetype="pdf")
    except Exception:  # noqa: BLE001 - unreadable PDF -> honest 0, never a raised exception here
        return 0
    try:
        return doc.page_count
    finally:
        doc.close()


def _process_file(data: bytes, file_name: str, *, provider_name: Optional[str], timeout_s: float) -> dict:
    """Run one corpus file's bytes through the real extraction seam and package the result with the
    independent page recount. ``extract_handwritten`` is called as a MODULE-LEVEL NAME on purpose (not a
    bound/aliased local) so a test can monkeypatch ``run_handwritten_corpus_acceptance.extract_handwritten``
    to simulate a poisoned/tampered extraction result without needing a real poisoned upload."""
    sha256 = hashlib.sha256(data).hexdigest()
    ext = Path(file_name).suffix.lower()
    page_count_recount = _independent_page_count(data, ext)
    upload_id = "qa-%s" % sha256[:16]  # deterministic, sha-derived -- never a Date.now-style value
    result = extract_handwritten(data, file_name, upload_id=upload_id,
                                 provider_name=provider_name, timeout_s=timeout_s)
    return {
        "file_name": file_name, "sha256": sha256, "extension": ext,
        "page_count_recount": page_count_recount,
        "pages": result["pages"], "proposals": result["proposals"], "page_ledger": result["page_ledger"],
    }


# --------------------------------------------------------------------------- #
# HARD CHECK 1 -- reconciliation: every physical page appears in the ledger exactly once.
# --------------------------------------------------------------------------- #
def _reconcile(file_record: dict) -> List[dict]:
    expected = file_record["page_count_recount"]
    indices = [entry["page_index"] for entry in file_record["page_ledger"]]
    if len(indices) == expected and sorted(indices) == list(range(expected)):
        return []
    return [{
        "file_name": file_record["file_name"], "sha256": file_record["sha256"],
        "expected_page_count": expected, "ledger_page_indices": sorted(indices),
        "detail": "page ledger does not account for every physical page exactly once",
    }]


# --------------------------------------------------------------------------- #
# HARD CHECK 2 -- no-fabrication scan.
# --------------------------------------------------------------------------- #
def _walk_cells(obj: Any, path: str) -> Iterator[Tuple[str, dict]]:
    """Yield ``(path, cell)`` for every Cell-SHAPED dict (exact key match -- ``cell_evidence`` entries have
    a different, 4-key shape and are never mistaken for one) reachable from ``obj`` by recursive
    dict/list descent. A Cell dict is a leaf -- it is never itself descended into further."""
    if isinstance(obj, dict):
        if set(obj.keys()) == _CELL_KEYS:
            yield path, obj
            return
        for key, value in obj.items():
            yield from _walk_cells(value, "%s.%s" % (path, key))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            yield from _walk_cells(item, "%s[%d]" % (path, i))


def _scan_fabrication(file_record: dict) -> List[dict]:
    failures: List[dict] = []
    root = {"pages": file_record["pages"], "proposals": file_record["proposals"]}
    for cell_path, cell in _walk_cells(root, file_record["file_name"]):
        if cell.get("value") is not None and cell.get("status") != READ:
            failures.append({
                "file_name": file_record["file_name"], "field": cell_path,
                "detail": "non-null value on a cell whose status is %r (only READ cells may carry a "
                         "value)" % cell.get("status"),
            })
        if cell.get("confidence") == "HIGH":
            failures.append({
                "file_name": file_record["file_name"], "field": cell_path,
                "detail": "cell confidence is HIGH -- Phase-1 reads are never trusted above MEDIUM",
            })

    for i, proposal in enumerate(file_record["proposals"]):
        prop_path = "%s.proposals[%d]" % (file_record["file_name"], i)
        if proposal.get("confidence") == "HIGH":
            failures.append({
                "file_name": file_record["file_name"], "field": prop_path + ".confidence",
                "detail": "proposal confidence is HIGH -- Phase-1 reads are never trusted above MEDIUM",
            })

        derivation = proposal.get("footage_derivation")
        if derivation != DERIVED_FROM_STATIONS:
            failures.append({
                "file_name": file_record["file_name"], "field": prop_path + ".footage_derivation",
                "detail": "footage_derivation is %r, expected %r" % (derivation, DERIVED_FROM_STATIONS),
            })
        else:
            start_feet = _safe_parse_station(proposal.get("start_station"))
            end_feet = _safe_parse_station(proposal.get("end_station"))
            if start_feet is None or end_feet is None:
                failures.append({
                    "file_name": file_record["file_name"], "field": prop_path + ".footage_ft",
                    "detail": "could not recompute footage from start_station/end_station",
                })
            else:
                recomputed = abs(end_feet - start_feet)
                if proposal.get("footage_ft") != recomputed:
                    failures.append({
                        "file_name": file_record["file_name"], "field": prop_path + ".footage_ft",
                        "detail": "footage_ft=%r does not equal the recomputed station delta %r"
                                 % (proposal.get("footage_ft"), recomputed),
                    })

        cell_evidence = proposal.get("cell_evidence") or {}
        for field in _PROPOSAL_EVIDENCE_FIELDS:
            if proposal.get(field) is not None and field not in cell_evidence:
                failures.append({
                    "file_name": file_record["file_name"], "field": "%s.%s" % (prop_path, field),
                    "detail": "value present with no corresponding cell_evidence entry",
                })
    return failures


def _safe_parse_station(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return parse_station(strip_station_label(str(value)))
    except Exception:  # noqa: BLE001 - a malformed station string recomputes to "unable", never raises here
        return None


# --------------------------------------------------------------------------- #
# Stats.
# --------------------------------------------------------------------------- #
def _warning_bucket(warning: str) -> str:
    """Fold a warning's embedded row/column numbers away so the histogram groups by warning KIND, not by
    every distinct number that happened to appear in it."""
    return _WARNING_NUM_RE.sub("#", warning)


def _compute_stats(file_records: List[dict]) -> dict:
    files_by_type: Counter = Counter()
    pages_by_outcome: Counter = Counter()
    proposals_per_file: Dict[str, int] = {}
    proposals_by_method: Counter = Counter()
    field_status: Dict[str, Counter] = defaultdict(Counter)
    confidence_distribution: Counter = Counter()
    warnings_histogram: Counter = Counter()

    for fr in file_records:
        files_by_type[fr["extension"]] += 1
        proposals_per_file[fr["file_name"]] = len(fr["proposals"])

        for entry in fr["page_ledger"]:
            outcome = entry["refusal"]["code"] if entry["status"] == "REFUSED" else entry["status"]
            pages_by_outcome[outcome] += 1
            for warning in entry.get("warnings") or []:
                warnings_histogram[_warning_bucket(warning)] += 1

        page_method_by_index = {page["source"]["page_index"]: page["method"] for page in fr["pages"]}
        for page in fr["pages"]:
            for field in ("date", "crew", "job_name", "print_raw"):
                cell = page["header"][field]
                field_status["header.%s" % field][cell["status"]] += 1
                if cell["confidence"] is not None:
                    confidence_distribution[cell["confidence"]] += 1
            for reading in page["readings"]:
                for field in ("station", "depth_ft", "boc_ft"):
                    cell = reading[field]
                    field_status["reading.%s" % field][cell["status"]] += 1
                    if cell["confidence"] is not None:
                        confidence_distribution[cell["confidence"]] += 1

        for proposal in fr["proposals"]:
            method = page_method_by_index.get(proposal["source"]["page_index"], "UNKNOWN")
            proposals_by_method[method] += 1
            if proposal.get("confidence") is not None:
                confidence_distribution[proposal["confidence"]] += 1

    return {
        "files_by_type": dict(files_by_type),
        "pages_by_outcome": dict(pages_by_outcome),
        "proposals_per_file": proposals_per_file,
        "proposals_by_method": dict(proposals_by_method),
        "field_status_distribution": {k: dict(v) for k, v in field_status.items()},
        "confidence_distribution": dict(confidence_distribution),
        "warnings_histogram": dict(warnings_histogram),
    }


# --------------------------------------------------------------------------- #
# Report rendering.
# --------------------------------------------------------------------------- #
def _file_summary(file_record: dict) -> dict:
    return {
        "file_name": file_record["file_name"], "sha256": file_record["sha256"],
        "extension": file_record["extension"], "page_count": file_record["page_count_recount"],
        "page_ledger": file_record["page_ledger"],
        "proposal_count": len(file_record["proposals"]), "proposals": file_record["proposals"],
    }


def _headline(stats: dict) -> str:
    total_pages = sum(stats["pages_by_outcome"].values())
    parts = ["%d %s" % (count, outcome)
            for outcome, count in sorted(stats["pages_by_outcome"].items(), key=lambda kv: (-kv[1], kv[0]))]
    return "%d pages processed: %s." % (total_pages, ", ".join(parts) if parts else "none")


def _md_table(headers: List[str], rows: List[List[Any]]) -> str:
    if not rows:
        return "_(none)_\n"
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(lines) + "\n"


def _render_markdown(report: dict) -> str:
    stats = report["stats"]
    reconciliation_ok = not report["reconciliation_failures"]
    fabrication_ok = not report["fabrication_failures"]
    lines = [
        "# Handwritten bore-log corpus acceptance report",
        "",
        _headline(stats),
        "",
        "Provider: %s" % (report["provider"] or "(none -- keyless run)"),
        "Files processed: %d" % report["corpus_file_count"],
        "",
        "## Verdict",
        "",
        "- RECONCILIATION: %s" % ("PASS (every physical page accounted for exactly once)" if reconciliation_ok
                                  else "FAIL (%d mismatch(es) -- see reconciliation_failures)"
                                       % len(report["reconciliation_failures"])),
        "- NO-FABRICATION SCAN: %s" % ("PASS (no fabricated values, footage recomputation matched, "
                                       "no HIGH confidence)" if fabrication_ok
                                       else "FAIL (%d issue(s) -- see fabrication_failures)"
                                            % len(report["fabrication_failures"])),
        "",
        "## Files by type",
        "",
        _md_table(["extension", "count"], sorted(stats["files_by_type"].items())),
        "## Pages by outcome",
        "",
        _md_table(["outcome", "count"],
                  sorted(stats["pages_by_outcome"].items(), key=lambda kv: (-kv[1], kv[0]))),
        "## Proposals per file",
        "",
        _md_table(["file_name", "proposal_count"], sorted(stats["proposals_per_file"].items())),
        "## Proposals by method",
        "",
        _md_table(["method", "count"], sorted(stats["proposals_by_method"].items())),
        "## Field status distribution",
        "",
        _md_table(["field", "status", "count"],
                  [[field, status, count]
                   for field, counts in sorted(stats["field_status_distribution"].items())
                   for status, count in sorted(counts.items())]),
        "## Confidence distribution",
        "",
        _md_table(["confidence", "count"], sorted(stats["confidence_distribution"].items())),
        "## Warnings histogram",
        "",
        _md_table(["warning", "count"], sorted(stats["warnings_histogram"].items())),
    ]
    if not reconciliation_ok:
        lines += ["## Reconciliation failures", "",
                 _md_table(["file_name", "expected_page_count", "ledger_page_indices", "detail"],
                          [[f["file_name"], f["expected_page_count"], f["ledger_page_indices"], f["detail"]]
                           for f in report["reconciliation_failures"]])]
    if not fabrication_ok:
        lines += ["## Fabrication failures", "",
                 _md_table(["file_name", "field", "detail"],
                          [[f["file_name"], f["field"], f["detail"]] for f in report["fabrication_failures"]])]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Top-level run + CLI.
# --------------------------------------------------------------------------- #
def run(*, corpus_dir: Path, out_dir: Path, provider_name: Optional[str] = None,
       fixtures_dir: Optional[Path] = None, timeout_s: float = DEFAULT_TIMEOUT_SECONDS) -> int:
    """Run the full acceptance harness once. Returns the process exit code (0 clean, 2 a reconciliation/
    fabrication finding). Raises ``HarnessError`` for a harness-level problem (caller/CLI maps that to
    exit code 1). Writes ONLY ``report.json``/``report.md`` under ``out_dir`` -- never a product store,
    never a network call."""
    corpus_dir = Path(corpus_dir)
    out_dir = Path(out_dir)
    if not corpus_dir.is_dir():
        raise HarnessError("corpus directory does not exist or is not a directory")
    out_dir.mkdir(parents=True, exist_ok=True)

    restore_env: Optional[Tuple[bool, Optional[str]]] = None
    if fixtures_dir is not None:
        restore_env = (_FAKE_PROVIDER_FIXTURES_ENV in os.environ, os.environ.get(_FAKE_PROVIDER_FIXTURES_ENV))
        os.environ[_FAKE_PROVIDER_FIXTURES_ENV] = str(Path(fixtures_dir))
    try:
        files = _collect_corpus_files(corpus_dir)
        file_records = []
        for path in files:
            rel_name = path.relative_to(corpus_dir).as_posix()
            data = path.read_bytes()
            file_records.append(_process_file(data, rel_name, provider_name=provider_name, timeout_s=timeout_s))
    finally:
        if restore_env is not None:
            had_old, old_value = restore_env
            if had_old:
                os.environ[_FAKE_PROVIDER_FIXTURES_ENV] = old_value  # type: ignore[assignment]
            else:
                os.environ.pop(_FAKE_PROVIDER_FIXTURES_ENV, None)

    reconciliation_failures: List[dict] = []
    fabrication_failures: List[dict] = []
    for fr in file_records:
        reconciliation_failures.extend(_reconcile(fr))
        fabrication_failures.extend(_scan_fabrication(fr))

    stats = _compute_stats(file_records)
    verdict = "CLEAN" if not reconciliation_failures and not fabrication_failures else "FAILED"
    exit_code = 0 if verdict == "CLEAN" else 2

    report = {
        "record_format": REPORT_RECORD_FORMAT,
        "corpus_file_count": len(file_records),
        "provider": provider_name,
        "timeout_s": timeout_s,
        "files": [_file_summary(fr) for fr in file_records],
        "stats": stats,
        "reconciliation_failures": reconciliation_failures,
        "fabrication_failures": fabrication_failures,
        "verdict": verdict,
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (out_dir / "report.md").write_text(_render_markdown(report), encoding="utf-8")
    return exit_code


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m truelinev2.qa.run_handwritten_corpus_acceptance",
        description="Run the handwritten bore-log extraction lane over a corpus directory; emit "
                    "report.json/report.md with decision-grade statistics, reconciliation, and a "
                    "no-fabrication scan. Never writes to a product store, never calls a network.")
    parser.add_argument("--corpus", required=True, help="Directory of .pdf/.jpg/.jpeg/.png files.")
    parser.add_argument("--out", required=True, help="Directory to write report.json/report.md into.")
    parser.add_argument("--provider", default=None,
                        help="Dotted module path for a vision provider. Omit to run keyless: every "
                             "image/scanned page then honestly refuses provider-not-configured.")
    parser.add_argument("--fixtures", default=None,
                        help="Fixtures directory for the deterministic fake vision provider.")
    parser.add_argument("--timeout-s", dest="timeout_s", type=float, default=DEFAULT_TIMEOUT_SECONDS,
                        help="Per-page vision-provider timeout, in seconds.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    try:
        return run(corpus_dir=Path(args.corpus), out_dir=Path(args.out), provider_name=args.provider,
                  fixtures_dir=Path(args.fixtures) if args.fixtures else None, timeout_s=args.timeout_s)
    except HarnessError as exc:
        print("harness error: %s" % exc, file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - any other harness-level failure -> exit 1, never a fake 0/2
        print("harness error: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
