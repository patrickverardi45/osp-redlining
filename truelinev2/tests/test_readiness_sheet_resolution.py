"""Slice 3 (Print-Reference audit): the readiness / REVIEW-candidate lane derives its plan sheet from the
bore log's OWN print/sheet reference and the plan's title-block index — never a blind ``plan_sheet=1``.

Pre-slice the product readiness lane was print-ref-BLIND: the run endpoint's ``plan_sheet`` defaulted to 1
and the spine bound/verified on that RAW page index, so a package whose bore log says "Print # 2" — with the
plan's front matter putting construction sheet 2 at PDF page 3 — was evaluated on the WRONG page (the cover)
and blocked. Slice 2 made the generic extractor carry ``sheet_refs``/``print_raw``; this slice makes the
readiness lane CONSUME them: derive the engineering sheet from the extraction's sheet refs, resolve it to
its PDF page through the SAME title-block index rule as Slice 1'/C2/matchline, and evaluate + render there.

Axes stay separate (engineering sheet identity vs resolved PDF page, reported in ``sheet_context``); nothing
is guessed: no refs -> the prior default (sheet 1) is preserved; an unresolvable ref -> the NAMED refusal
``SHEET_REF_UNRESOLVED`` (never a silent page-1 fallback); multiple distinct refs -> the NAMED refusal
``MULTI_SHEET_REFS_UNSUPPORTED`` (the spine is single-sheet per run). An EXPLICIT ``plan_sheet`` keeps its
raw-page semantics byte-identically. Rendering / thresholds / AUTO / recognized replay / manual anchor /
the uploaded-corpus lane are untouched.

Fixtures are generic + synthetic (tmp_path only); the READY page reuses the QA harness recipe (two station
labels + a clean route line between their word centres). The target construction sheet is a 2:1 page while
front matter is 1.5:1 — so a rendered overlay PNG's aspect ratio PROVES which PDF page was rasterized
(the Slice 1' dimensional-discriminator technique). No customer/person/place names.
"""
from __future__ import annotations

from pathlib import Path

import fitz
from PIL import Image

from truelinev2.harness import product_readiness_bridge as bridge
from truelinev2.harness.product_readiness_bridge import run_job_readiness
from truelinev2.ingest.pdf import PlanPdf

_LABELS = [("11+75", 120.0, 150.0), ("13+25", 360.0, 150.0)]   # on the 600x300 construction sheet
_FRONT = (300.0, 200.0)     # cover + construction sheet 1 (aspect 1.5): the WRONG pages
_TARGET = (600.0, 300.0)    # construction sheet 2 (aspect 2.0): where the bore actually lives


def _plan_bytes(tmp_path: Path, *, titled: bool = True) -> bytes:
    """3-page front-matter plan: p1 cover (no title block), p2 construction "1 OF 2" (text only),
    p3 construction "2 OF 2" carrying the READY content (station labels + a clean route line drawn
    terminus-to-terminus at the label word-centres, probe-read so font metrics are never guessed).
    ``titled=False`` omits every title-block label -> nothing resolvable."""
    probe = tmp_path / "probe.pdf"
    doc = fitz.open()
    page = doc.new_page(width=_TARGET[0], height=_TARGET[1])
    for text, x, y in _LABELS:
        page.insert_text((x, y), text, fontsize=8)
    doc.save(str(probe))
    doc.close()
    plan = PlanPdf(str(probe))
    try:
        centers = {w["text"]: (float(w["xc"]), float(w["yc"])) for w in plan.words(1, 0)}
    finally:
        plan.close()

    doc = fitz.open()
    cover = doc.new_page(width=_FRONT[0], height=_FRONT[1])
    cover.insert_text((30, 40), "PLAN SET COVER / INDEX", fontsize=10)
    s1 = doc.new_page(width=_FRONT[0], height=_FRONT[1])
    s1.insert_text((30, 40), "ROUTE SEGMENT A", fontsize=10)
    if titled:
        s1.insert_text((230, 190), "1 OF 2", fontsize=8)
    s2 = doc.new_page(width=_TARGET[0], height=_TARGET[1])
    for text, x, y in _LABELS:
        s2.insert_text((x, y), text, fontsize=8)
    (ax, ay), (bx, by) = centers["11+75"], centers["13+25"]
    s2.draw_line(fitz.Point(ax, ay), fitz.Point(bx, by), color=(0, 0, 0), width=1)
    if titled:
        s2.insert_text((520, 290), "2 OF 2", fontsize=8)
    out = tmp_path / "plan.pdf"
    doc.save(str(out))
    doc.close()
    return out.read_bytes()


def _job(tmp_path: Path, plan: bytes, bore_csv: str):
    """Fake product-job upload records + files root in the exact shape materialize_package_view consumes."""
    root = tmp_path / "jobroot"
    uploads = []
    p = root / "uploads" / "u-plan" / "payload.pdf"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(plan)
    uploads.append({"kind": "PLAN_PDF", "stored_path": "uploads/u-plan/payload.pdf",
                    "original_filename": "plan.pdf", "upload_id": "u-plan"})
    b = root / "uploads" / "u-bore" / "payload.csv"
    b.parent.mkdir(parents=True, exist_ok=True)
    b.write_bytes(bore_csv.encode("utf-8"))
    uploads.append({"kind": "BORE_LOG", "stored_path": "uploads/u-bore/payload.csv",
                    "original_filename": "bore-log.csv", "upload_id": "u-bore"})
    return uploads, root


# --------------------------------------------------------------------------------------------------- #
# (1) THE slice: print ref 2 + front matter -> readiness evaluates AND renders on the RESOLVED PDF
# page 3 (not raw page 2, not default page 1), with both axes reported separately.
# --------------------------------------------------------------------------------------------------- #
def test_readiness_uses_resolved_pdf_page_from_print_ref(tmp_path):
    uploads, root = _job(tmp_path, _plan_bytes(tmp_path), "start,end,print\n11+75,13+25,2\n")
    art = tmp_path / "art"
    result = run_job_readiness(uploads, root, plan_sheet=None, artifact_dir=art)

    ctx = result["sheet_context"]
    assert ctx["engineering_sheet"] == 2           # the bore log's own print reference
    assert ctx["pdf_page"] == 3                    # title-block resolution (front matter skipped)
    assert ctx["source"] == bridge.SHEET_SOURCE_SHEET_REF
    assert ctx["sheet_refs"] == [2] and ctx["refusal"] is None

    # The spine ran on the resolved page: the READY recipe lives ONLY on PDF p3.
    assert result["readiness_status"] == "READY_FOR_REVIEW_REDLINE"
    assert result["review_candidate_status"] == "REVIEW_CANDIDATE_READY"
    assert result["generated_visual"] is True and len(result["artifacts"]) == 2

    # Dimensional proof the OVERLAY rasterized the resolved page too: p3 is 2:1; every wrong page is 1.5:1.
    for name in result["artifacts"]:
        img = Image.open(art / name)
        assert abs(img.width / img.height - 2.0) < 0.01, (
            "overlay %s is %dx%d — rendered on a front-matter page, not the resolved construction sheet"
            % (name, img.width, img.height))


def test_explicit_plan_sheet_keeps_raw_semantics(tmp_path):
    # An EXPLICIT plan_sheet is honored verbatim (raw page semantics, offset 0) — the pre-slice behavior,
    # unchanged. Sheet 1 backs the COVER here, so the run is honestly blocked (labels aren't there).
    uploads, root = _job(tmp_path, _plan_bytes(tmp_path), "start,end,print\n11+75,13+25,2\n")
    result = run_job_readiness(uploads, root, plan_sheet=1, artifact_dir=tmp_path / "art")
    ctx = result["sheet_context"]
    assert ctx["source"] == bridge.SHEET_SOURCE_EXPLICIT
    assert ctx["engineering_sheet"] == 1 and ctx["pdf_page"] == 1
    assert result["readiness_status"] != "READY_FOR_REVIEW_REDLINE"
    assert result["artifacts"] == []


# --------------------------------------------------------------------------------------------------- #
# (2) No print/sheet ref -> the prior default (plan sheet 1) is PRESERVED, and says so.
# --------------------------------------------------------------------------------------------------- #
def test_no_print_ref_preserves_default_behavior(tmp_path):
    # Single-page-style package: the READY content on PDF p1 would need a 1-page plan; reuse the 3-page
    # plan but assert the derived run equals the explicit plan_sheet=1 run on every readiness field.
    uploads, root = _job(tmp_path, _plan_bytes(tmp_path), "start,end\n11+75,13+25\n")
    derived = run_job_readiness(uploads, root, plan_sheet=None, artifact_dir=tmp_path / "a1")
    explicit = run_job_readiness(uploads, root, plan_sheet=1, artifact_dir=tmp_path / "a2")

    ctx = derived["sheet_context"]
    assert ctx["source"] == bridge.SHEET_SOURCE_DEFAULT
    assert ctx["engineering_sheet"] == 1 and ctx["pdf_page"] == 1
    assert ctx["sheet_refs"] == [] and ctx["refusal"] is None
    # identical spine outcome to the pre-slice default (page-1 evaluation)
    for key in ("readiness_status", "stage", "ready", "review_candidate_status", "generated_visual"):
        assert derived[key] == explicit[key]


# --------------------------------------------------------------------------------------------------- #
# (3) Unresolvable ref -> NAMED refusal; the spine never runs on a guessed page (no page-1 fallback).
# --------------------------------------------------------------------------------------------------- #
def test_unresolvable_print_ref_refuses_named(tmp_path):
    uploads, root = _job(tmp_path, _plan_bytes(tmp_path), "start,end,print\n11+75,13+25,7\n")
    result = run_job_readiness(uploads, root, plan_sheet=None, artifact_dir=tmp_path / "art")
    assert result["readiness_status"] == bridge.SHEET_REF_UNRESOLVED
    assert result["ready"] is False and result["artifacts"] == []
    assert result["review_candidate_status"] == "REVIEW_CANDIDATE_REFUSED"
    assert result["span_rows"] == []                       # the spine did NOT run on a guessed page
    ctx = result["sheet_context"]
    assert ctx["refusal"] == bridge.SHEET_REF_UNRESOLVED
    assert ctx["sheet_refs"] == [7] and "7" in ctx["reason"]
    assert ctx["pdf_page"] is None                         # nothing resolved -> nothing claimed


def test_untitled_plan_with_print_ref_refuses_named(tmp_path):
    # The bore log names sheet 2 but the plan prints NO title-block labels: nothing resolvable -> the same
    # named refusal. Never "sheet 2 is probably raw page 2" (that guess is the bug family this arc kills).
    uploads, root = _job(tmp_path, _plan_bytes(tmp_path, titled=False), "start,end,print\n11+75,13+25,2\n")
    result = run_job_readiness(uploads, root, plan_sheet=None, artifact_dir=tmp_path / "art")
    assert result["readiness_status"] == bridge.SHEET_REF_UNRESOLVED
    assert result["sheet_context"]["refusal"] == bridge.SHEET_REF_UNRESOLVED
    assert result["artifacts"] == []


# --------------------------------------------------------------------------------------------------- #
# (4) Multiple distinct refs -> NAMED refusal (single-sheet spine); both sheets reported, none guessed.
# --------------------------------------------------------------------------------------------------- #
def test_multiple_print_refs_refuse_named(tmp_path):
    uploads, root = _job(tmp_path, _plan_bytes(tmp_path), 'start,end,print\n11+75,13+25,"2, 3"\n')
    result = run_job_readiness(uploads, root, plan_sheet=None, artifact_dir=tmp_path / "art")
    assert result["readiness_status"] == bridge.MULTI_SHEET_REFS_UNSUPPORTED
    assert result["ready"] is False and result["artifacts"] == []
    ctx = result["sheet_context"]
    assert ctx["refusal"] == bridge.MULTI_SHEET_REFS_UNSUPPORTED
    assert ctx["sheet_refs"] == [2, 3]
    assert ctx["engineering_sheet"] is None and ctx["pdf_page"] is None
