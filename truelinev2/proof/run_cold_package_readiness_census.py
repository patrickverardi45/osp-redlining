r"""READ-ONLY cold-package readiness CENSUS over the public cold corpus.

Measures every ``public-cold-*`` package under the (gitignored) cold-packages root through the SHIPPED
read-only readiness spine -- span extractor -> endpoint binder -> route verifier -> readiness classifier
(``run_package_route_readiness``, ``allow_live=False``: product parity, never the recognized-CONTROL lane) --
plus a cheap NO-OCR text-layer probe (max chars over the first 3 pages). It answers, per package, exactly one
doctrine question: is this package complete enough to attempt a REVIEW redline candidate, and if not, which
named source evidence is missing?

Hard properties:
  * READ-ONLY wrt the corpus: a manifest-less plan-only folder is run through a TEMP VIEW (a minimal
    name-free ``package.json`` + a hardlink/copy of the plan) mirroring what the product bridge materializes
    for a job -- the package folder itself is never written.
  * plan_sheet = the package manifest's bore sheet when present, else 1 (plan-only packages refuse upstream
    at SPAN_SOURCE, where the sheet is irrelevant).
  * DRAWS NOTHING and generates NO artifact ever -- statuses only. When a package classifies
    READY_FOR_REVIEW_REDLINE the census PRINTS the existing gated follow-up command
    (``python -m truelinev2.harness.review_candidate <package_dir> <artifact_dir>``) and stops there.
  * No AUTO, no placement, no promotion, no OCR, no invented evidence, no customer/project/person/place name.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_cold_package_readiness_census
Report: data/outputs/truelinev2/cold_census/report.json (gitignored) + the printed table.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import fitz

from truelinev2.config import _REPO_ROOT
from truelinev2.harness.route_verification import run_package_route_readiness

COLD_ROOT = _REPO_ROOT / "data" / "outputs" / "truelinev2" / "cold_packages"
OUT_DIR = _REPO_ROOT / "data" / "outputs" / "truelinev2" / "cold_census"
READY = "READY_FOR_REVIEW_REDLINE"


def _text_probe(pdf: Path):
    """(page_count, max text chars over the first 3 pages). NO OCR -- a text-layer readability probe only."""
    try:
        doc = fitz.open(str(pdf))
        pages = doc.page_count
        chars = max(len(doc[i].get_text() or "") for i in range(min(3, pages)))
        doc.close()
        return pages, chars
    except Exception:
        return None, None


def _manifest_sheet(pkg: Path) -> int:
    mf = pkg / "package.json"
    if mf.exists():
        try:
            m = json.loads(mf.read_text(encoding="utf-8"))
            sheets = sorted({int(b.get("sheet", 1)) for b in (m.get("bores") or [])})
            if sheets:
                return sheets[0]
        except Exception:
            pass
    return 1


def _temp_view(pkg: Path, work: Path) -> Path:
    """Product-parity minimal view for a manifest-less folder (the bridge materializes the same shape)."""
    view = work / pkg.name
    if view.exists():
        shutil.rmtree(view)
    (view / "uploads").mkdir(parents=True)
    src, dst = pkg / "uploads" / "plan.pdf", view / "uploads" / "plan.pdf"
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)
    (view / "package.json").write_text(json.dumps({
        "package_id": pkg.name, "provenance_class": "FRESH_NONRECOGNIZED",
        "uploads": [{"kind": "PLAN_PDF", "filename": "plan.pdf"}]}, indent=1), encoding="utf-8")
    return view


def census_package(pkg: Path, work: Path) -> dict:
    pages, chars = _text_probe(pkg / "uploads" / "plan.pdf")
    sheet = _manifest_sheet(pkg)
    has_manifest = (pkg / "package.json").exists()
    run_dir = pkg if has_manifest else _temp_view(pkg, work)
    row = {"package": pkg.name, "plan_pages": pages, "text_chars_first3": chars,
           "plan_sheet_used": sheet, "has_span_source_file": (pkg / "uploads" / "bore-log.xlsx").exists(),
           "via_temp_view": not has_manifest, "status": None, "stage": None,
           "recommended_next_input": None, "confirmed_spans": 0, "span_refusals": [],
           "anchor_refusals": [], "route_refusals": [], "error": None}
    try:
        rr = run_package_route_readiness(run_dir, plan_sheet=sheet, allow_live=False)
        if rr is None:
            row["status"] = "NO_SPINE_RESULT"
            return row
        row["status"] = getattr(rr.report, "status", None)
        row["stage"] = getattr(rr.report, "stage", None)
        row["recommended_next_input"] = getattr(rr.report, "recommended_next_input", None)
        if rr.extraction is not None:
            row["confirmed_spans"] = int(getattr(rr.extraction, "source_confirmed_span_count", 0) or 0)
            row["span_refusals"] = sorted({getattr(r, "reason", None)
                                           for r in (getattr(rr.extraction, "refusals", ()) or ())
                                           if getattr(r, "reason", None)})
        row["anchor_refusals"] = sorted({getattr(b, "refusal", None)
                                         for b in (getattr(rr.bindings, "bindings", ()) or ())
                                         if getattr(b, "refusal", None)})
        row["route_refusals"] = sorted({getattr(v, "refusal", None)
                                        for v in (getattr(rr.routes, "verifications", ()) or ())
                                        if getattr(v, "refusal", None)})
    except Exception as exc:  # census must survive one bad package and report it honestly
        row["error"], row["status"] = "%s: %s" % (type(exc).__name__, exc), "RUNNER_ERROR"
    finally:
        if not has_manifest:
            shutil.rmtree(work / pkg.name, ignore_errors=True)
    return row


def main(argv=None) -> int:
    root = Path(argv[0]) if argv else COLD_ROOT
    packages = sorted(root.glob("public-cold-*"))
    if not packages:
        print("no public-cold-* packages under", root)
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    work = OUT_DIR / "views"
    results, histogram = [], {}
    for pkg in packages:
        r = census_package(pkg, work)
        results.append(r)
        histogram[r["status"]] = histogram.get(r["status"], 0) + 1
        print("%-18s pages=%-4s chars=%-6s sheet=%-3s src=%s spans=%s  %-28s next=%s"
              % (r["package"], r["plan_pages"], r["text_chars_first3"], r["plan_sheet_used"],
                 "Y" if r["has_span_source_file"] else "-", r["confirmed_spans"],
                 r["status"], r["recommended_next_input"]))
        if r["status"] == READY:
            print("  ^ READY: run the gated candidate builder yourself -->")
            print("    python -m truelinev2.harness.review_candidate %s <artifact_dir>" % pkg)
    shutil.rmtree(work, ignore_errors=True)
    report = {"census_parameters": {"allow_live": False, "plan_sheet": "manifest bore sheet else 1",
                                    "text_probe": "max chars over first 3 pages (NO OCR)"},
              "histogram": histogram, "packages": results}
    out = OUT_DIR / "report.json"
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print("\nstatus histogram:", json.dumps(histogram))
    print("report:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or None))
