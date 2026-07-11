"""PRODUCT READINESS BRIDGE — run the shipped read-only readiness / REVIEW-candidate spine on a product job's
UPLOADED files (name-free; harness-only; no product/store/api/render coupling).

The readiness spine (span extractor -> endpoint binder -> route verifier -> readiness classifier ->
``review_candidate``) consumes a PACKAGE FOLDER shaped ``<pkg>/package.json`` + ``<pkg>/uploads/<filename>`` (the
same shape ``complete_package_qa.build_complete_package`` produces). The product store lays a job's uploads out
differently (``<job_dir>/uploads/<upload_id>/payload<ext>`` recorded in the job JSON). This bridge is the thin,
read-only adapter between the two: it MATERIALIZES an ephemeral spine-shaped package view from a job's real
uploaded bytes, runs the shipped spine VERBATIM (``run_package_route_readiness`` + the gated
``build_review_candidate``), and returns a product-safe result dict for the API to serve.

It invents nothing and decides nothing: every readiness status is COMPUTED by the real observers, and a REVIEW
candidate visual is drawn ONLY through ``review_candidate.build_review_candidate`` and ONLY when the status is
exactly ``READY_FOR_REVIEW_REDLINE`` (every refusal draws zero artifacts). It performs no AUTO, no final placement,
and no status promotion. It imports only stdlib + the read-only harness spine (which itself lazily imports only the
read-only dialect selector + plan reader + fitz); it imports NOTHING from render / placement / api / store /
contracts / match / web.

The ephemeral view is built under a caller-supplied (or temp) work dir and DELETED after the run; the REVIEW
candidate PNGs (when READY) are written into a separate caller-supplied ``artifact_dir`` (the API points this at a
gitignored, job-scoped store dir — never committed). Uploaded filenames are sanitized before entering the view, and
every ``source_file`` echoed back is reduced to a basename so no absolute/temp path leaks to the client.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Upload kinds carried into the spine package view. PLAN_PDF + BORE_LOG are consumed by the spine; GIS_ROUTE is
# carried but provably INERT to the readiness spine (a .kml/.kmz is not a span-source kind). PHOTO / unknown kinds
# are skipped. These mirror the product upload_pipeline ACCEPTED_KINDS and the spine's expected manifest kinds.
_PLAN_KIND = "PLAN_PDF"
_BORELOG_KIND = "BORE_LOG"
_GIS_KIND = "GIS_ROUTE"
_VIEW_KINDS = (_PLAN_KIND, _BORELOG_KIND, _GIS_KIND)

_MANIFEST_FILENAME = "package.json"
_UPLOADS_SUBDIR = "uploads"
_PROVENANCE_CLASS = "PRODUCT_UPLOAD"

_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")

# The single readiness status that gates a REVIEW candidate (kept in sync with review_readiness via the spine).
READY_STATUS = "READY_FOR_REVIEW_REDLINE"
_REVIEW_CANDIDATE_NOTICE = ("REVIEW candidate — human-reviewable; NOT AUTO, NOT final placement, "
                            "NOT a status promotion")

# --- Slice 3: sheet derivation (print-ref -> engineering sheet -> resolved PDF page) -------------------- #
# ``sheet_context.source`` values — HOW the evaluated sheet was chosen:
SHEET_SOURCE_EXPLICIT = "EXPLICIT_PLAN_SHEET"                    # caller passed plan_sheet (raw-page semantics)
SHEET_SOURCE_SHEET_REF = "BORE_LOG_SHEET_REF_TITLE_BLOCK_RESOLVED"   # bore-log print ref + title-block index
SHEET_SOURCE_DEFAULT = "DEFAULT_PLAN_SHEET"                      # no print/sheet ref -> the prior default (1)
# Named refusals (result ``readiness_status`` values at this bridge level, like NO_SPINE_INPUT): the run is
# REFUSED rather than evaluated on a guessed page.
SHEET_REF_UNRESOLVED = "SHEET_REF_UNRESOLVED"                    # ref exists; title block cannot place it
MULTI_SHEET_REFS_UNSUPPORTED = "MULTI_SHEET_REFS_UNSUPPORTED"    # >1 distinct ref; the spine is single-sheet/run
_DEFAULT_PLAN_SHEET = 1


def _sheet_context(engineering_sheet, pdf_page, source, sheet_refs, print_refs, refusal, reason) -> Dict[str, Any]:
    """The result's ``sheet_context``: WHICH engineering sheet was chosen, WHICH PDF page backs it, and WHY —
    the two axes are carried SEPARATELY (engineering sheet identity is never redefined by page resolution).
    ``sheet_offset`` is the PlanPdf.page_index offset (pdf_page - engineering_sheet), None when unresolved."""
    return {"engineering_sheet": engineering_sheet, "pdf_page": pdf_page,
            "sheet_offset": (None if engineering_sheet is None or pdf_page is None
                             else int(pdf_page) - int(engineering_sheet)),
            "source": source, "sheet_refs": [int(r) for r in sheet_refs],
            "print_refs": [str(p) for p in print_refs], "refusal": refusal, "reason": reason}


def _derive_sheet_context(pkg, plan_path) -> Dict[str, Any]:
    """Derive the sheet to evaluate from the package's OWN bore-log print/sheet references (the Slice-2
    ``SpanRow.sheet_refs``/``print_raw`` fields), resolving the engineering sheet to its PDF page through the
    plan's title-block index — the SAME Slice 1'/C2 rule the uploaded-corpus render and matchline use.

    Honest by construction: NO refs -> the prior default (sheet 1, raw semantics) so ref-less packages behave
    byte-identically; MULTIPLE distinct refs -> the named MULTI_SHEET_REFS_UNSUPPORTED refusal (this spine
    evaluates one sheet per run); ONE ref that the title block cannot place (or no readable/titled plan) ->
    the named SHEET_REF_UNRESOLVED refusal. A sheet ref is NEVER treated as a raw page index and a page is
    never guessed. Read-only; the extraction re-run is the same deterministic reader the spine itself uses."""
    from truelinev2.harness.span_extractor import extract_spans_from_folder

    extraction = extract_spans_from_folder(str(pkg))
    refs: List[int] = []
    prints: List[str] = []
    for s in extraction.spans:
        for r in s.sheet_refs:
            if int(r) not in refs:
                refs.append(int(r))
        if s.print_raw and s.print_raw not in prints:
            prints.append(s.print_raw)

    if not refs:
        return _sheet_context(
            _DEFAULT_PLAN_SHEET, _DEFAULT_PLAN_SHEET, SHEET_SOURCE_DEFAULT, [], prints, None,
            "the bore-log rows carry no print/sheet reference; evaluating plan sheet %d (the prior default)"
            % _DEFAULT_PLAN_SHEET)
    if len(refs) > 1:
        return _sheet_context(
            None, None, None, refs, prints, MULTI_SHEET_REFS_UNSUPPORTED,
            "the bore-log rows reference %d distinct plan sheets (%s); this lane evaluates ONE sheet per "
            "run — split the bore log by sheet or run with an explicit plan_sheet"
            % (len(refs), ", ".join(str(r) for r in refs)))

    ref = refs[0]
    resolved = None
    if plan_path:
        try:
            from truelinev2.ingest.pdf import PlanPdf
            from truelinev2.ingest.sheet_label_index import build_sheet_index

            plan = PlanPdf(str(plan_path))
            try:
                resolved = build_sheet_index(plan).resolve_construction_sheet(ref)
            finally:
                plan.close()
        except Exception:  # noqa: BLE001 — an unreadable plan resolves nothing; refuse below, never guess
            resolved = None
    if resolved is None:
        return _sheet_context(
            ref, None, None, refs, prints, SHEET_REF_UNRESOLVED,
            "the bore log references plan sheet %d but the plan's title-block index could not resolve it to "
            "a PDF page; verify the plan set's sheet labels or run with an explicit plan_sheet — refusing "
            "rather than guessing a page" % ref)
    return _sheet_context(
        ref, int(resolved), SHEET_SOURCE_SHEET_REF, refs, prints, None,
        "bore-log print/sheet reference %d resolved to PDF page %d by the plan's title-block index"
        % (ref, int(resolved)))


def _safe_view_name(original_filename: Any, upload_id: str, ext: str) -> str:
    """A filesystem-safe basename for the ephemeral view, derived from the (untrusted) uploaded filename. Strips any
    directory component, collapses unsafe characters, and forces the stored extension so the spine's extension-based
    span discovery still recognizes the file kind. Falls back to the content-addressed upload_id when nothing safe
    remains."""
    base = Path(str(original_filename or "")).name
    base = _SAFE_CHARS.sub("_", base).strip("._-")
    if not base:
        base = str(upload_id)
    if ext and not base.lower().endswith(ext.lower()):
        base = base + ext
    return base


def _copy_payload(src: Path, dst: Path) -> None:
    """Place the uploaded payload into the view. Prefer a hardlink (cheap, same-volume); fall back to a byte copy
    across volumes. Read-only wrt the source payload."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(str(src), str(dst))
    except OSError:
        shutil.copyfile(str(src), str(dst))


def materialize_package_view(uploads: Sequence[Dict[str, Any]], job_files_root, work_dir, *,
                             allowed_upload_ids: Optional[Sequence[str]] = None) -> Optional[str]:
    """Build an ephemeral spine-shaped package view under ``work_dir`` from a job's upload records + on-disk
    payloads. Returns the package folder path, or None when no spine-relevant upload (PLAN_PDF / BORE_LOG /
    GIS_ROUTE) with an existing payload is present. Writes only into ``work_dir``; reads the payloads read-only.

    ``allowed_upload_ids`` (additive; default ``None`` preserves EXACT prior behavior byte-identically):
    when given, ONLY uploads whose ``upload_id`` is in this set are considered — every other upload (even a
    spine-relevant kind) is excluded from the view, as if it were never on the job. This is the Phase-2
    source-route-adoption seam's requirement that the readiness spine run ONLY over the caller-selected plan
    upload + the caller-selected reviewed-bore-log's BORE_LOG source upload, never the job's full upload set."""
    job_files_root = Path(job_files_root)
    pkg = Path(work_dir) / "package_view"
    (pkg / _UPLOADS_SUBDIR).mkdir(parents=True, exist_ok=True)
    allowed = set(allowed_upload_ids) if allowed_upload_ids is not None else None

    manifest_uploads: List[Dict[str, str]] = []
    used_names: set = set()
    for u in uploads or ():
        kind = u.get("kind")
        if kind not in _VIEW_KINDS:
            continue
        if allowed is not None and u.get("upload_id") not in allowed:
            continue
        stored_path = u.get("stored_path") or ""
        src = job_files_root / stored_path
        if not stored_path or not src.is_file():
            continue
        ext = Path(stored_path).suffix
        name = _safe_view_name(u.get("original_filename"), str(u.get("upload_id") or "upload"), ext)
        if name in used_names:                                 # dedupe: content-address on collision
            name = "%s-%s" % (u.get("upload_id") or "upload", name)
        used_names.add(name)
        _copy_payload(src, pkg / _UPLOADS_SUBDIR / name)
        manifest_uploads.append({"kind": kind, "filename": name})

    if not manifest_uploads:
        return None

    package_id = Path(job_files_root).name or "package"        # runtime data (the job dir name), never hardcoded
    (pkg / _MANIFEST_FILENAME).write_text(
        json.dumps({"package_id": package_id, "provenance_class": _PROVENANCE_CLASS,
                    "uploads": manifest_uploads, "bores": []}),
        encoding="utf-8")
    return str(pkg)


# ---------------------------------------------------------------------------------------------------------------- #
# Read-only, UI-friendly table rows (the same coordinate-free shape complete_package_qa.ui_summary exposes, so a
# later web table matches the QA harness). Every source_file is reduced to a basename (no absolute/temp path leak).
# ---------------------------------------------------------------------------------------------------------------- #
def _basename(value: Any) -> Any:
    return Path(str(value)).name if value else value


def _span_rows(extraction) -> List[dict]:
    return [{"span_id": s.span_id, "start_station": s.start_station, "end_station": s.end_station,
             "footage": s.footage, "start_structure": s.start_structure, "end_structure": s.end_structure,
             "source_file": _basename(s.source_file), "source_page": s.source_page,
             "source_kind": s.source_kind, "confidence": s.confidence, "citation": s.citation}
            for s in extraction.spans]


def _anchor_bindings(bindings) -> List[dict]:
    return [{"span_id": b.span_id, "start_station": b.start_station, "end_station": b.end_station,
             "bound": b.bound, "refusal": b.refusal,
             "start_anchor": {"status": b.start_anchor_status, "method": b.start_anchor_method,
                              "xy": (list(b.start_anchor_xy) if b.start_anchor_xy else None)},
             "end_anchor": {"status": b.end_anchor_status, "method": b.end_anchor_method,
                            "xy": (list(b.end_anchor_xy) if b.end_anchor_xy else None)}}
            for b in bindings.bindings]


def _route_verifications(routes) -> List[dict]:
    return [{"span_id": v.span_id, "route_ready": v.route_ready, "evaluated": v.evaluated,
             "refusal": v.refusal, "route_observer_status": v.route_observer_status,
             "route_isolation_status": v.route_isolation_status, "route_run_status": v.route_run_status,
             "main_run_status": v.main_run_status, "gap_bridge_status": v.gap_bridge_status}
            for v in routes.verifications]


def _candidate_dict(candidate_report, artifact_dir: Optional[Path]) -> Tuple[Optional[dict], List[str]]:
    """Serialize the single READY candidate (or None on refusal), relativizing its absolute artifact paths to
    basenames under ``artifact_dir`` so the API can map them to served URLs without leaking a filesystem path.
    Returns (candidate_dict_or_None, [artifact_basenames])."""
    if not candidate_report.candidates:
        return None, []
    cand = candidate_report.candidates[0].to_dict()
    cand["source_file"] = _basename(cand.get("source_file"))
    names: List[str] = []
    for key in ("artifact_before", "artifact_after"):
        p = cand.get(key)
        if p:
            name = Path(p).name
            cand[key] = name                                   # basename only (API maps to a served URL)
            names.append(name)
    return cand, names


def _remove_pngs(artifact_dir: Optional[Path]) -> None:
    """Drop any (possibly partially-written) overlay PNGs so a failed render never leaves a stray artifact the API
    would serve. Best-effort; the readiness dir holds only this lane's artifacts."""
    if artifact_dir is None:
        return
    try:
        for p in Path(artifact_dir).glob("*.png"):
            p.unlink()
    except OSError:
        pass


# The invariants of this lane, asserted as literals so the honest labelling holds even on a render failure: it is
# ALWAYS a REVIEW candidate lane and NEVER performs AUTO / final placement / a status promotion.
_LANE_INVARIANTS = {"is_review_candidate": True, "performs_auto": False,
                    "performs_placement": False, "promotes_status": False}


def _no_readiness_result(status: str, recommended: Optional[str], reason: str,
                         sheet_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """A refusal result for a package that never reached the classifier (no spine input / unresolved /
    sheet-ref refusal). ``sheet_context`` (Slice 3) records how far sheet derivation got before refusing."""
    return {**_LANE_INVARIANTS, "readiness_status": status, "stage": None, "ready": False,
            "recommended_next_input": recommended, "draws_anything": False,
            "review_candidate_status": "REVIEW_CANDIDATE_REFUSED", "generated_visual": False,
            "refusal_reason": reason, "candidate": None, "artifacts": [], "span_rows": [],
            "anchor_bindings": [], "route_verifications": [], "notice": _REVIEW_CANDIDATE_NOTICE,
            "sheet_context": sheet_context, "detail": {}}


def _result(readiness, review_status: str, generated: bool, refusal_reason: Optional[str],
            candidate: Optional[dict], artifact_names: Sequence[str], *, render_error: bool,
            sheet_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    report = readiness.report
    return {**_LANE_INVARIANTS,
            "readiness_status": report.status, "stage": report.stage, "ready": report.ready,
            "recommended_next_input": report.recommended_next_input,
            "draws_anything": report.draws_anything,                          # False (read-only classifier)
            "review_candidate_status": review_status, "generated_visual": generated,
            "refusal_reason": refusal_reason, "candidate": candidate, "artifacts": list(artifact_names),
            "span_rows": _span_rows(readiness.extraction),
            "anchor_bindings": _anchor_bindings(readiness.bindings),
            "route_verifications": _route_verifications(readiness.routes),
            "notice": _REVIEW_CANDIDATE_NOTICE,
            "sheet_context": sheet_context,
            "detail": ({"render_error": True} if render_error else {})}


def run_job_readiness(uploads: Sequence[Dict[str, Any]], job_files_root, *, plan_sheet: Optional[int] = None,
                      artifact_dir=None, allowed_upload_ids: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Run the shipped read-only readiness / REVIEW-candidate spine on a job's uploaded files and return a
    product-safe result dict.

    Materializes an ephemeral spine-shaped package view from the job's real uploads, runs
    ``run_package_route_readiness`` (allow_live=False — pure source-completeness, never the recognized-CONTROL
    lane), then builds a REVIEW candidate through the gated ``build_review_candidate`` (which draws before/after
    overlay PNGs into ``artifact_dir`` ONLY when the status is exactly READY_FOR_REVIEW_REDLINE; every refusal draws
    nothing). The ephemeral view is deleted afterwards. Read-only wrt the product: no AUTO, no placement, no status
    promotion, no store/render/api coupling.

    Sheet selection (Slice 3): ``plan_sheet=None`` (the default) derives the sheet from the bore log's OWN
    print/sheet references and resolves it to its PDF page through the plan's title-block index
    (``_derive_sheet_context`` — same rule as Slice 1'/C2); no refs -> the prior default (sheet 1) preserved;
    an unresolvable or multi-sheet ref -> a NAMED refusal (never a guessed page). An EXPLICIT ``plan_sheet``
    keeps the pre-slice raw-page semantics verbatim. Every result carries ``sheet_context`` (both axes:
    engineering sheet identity + resolved PDF page + source/refusal reason).

    ``artifact_dir`` (when given) is where the REVIEW candidate PNGs are written; the returned candidate's
    ``artifact_before`` / ``artifact_after`` are basenames under that dir (the API maps them to served URLs).

    ``allowed_upload_ids`` (additive; default ``None`` preserves EXACT prior behavior byte-identically): passed
    straight through to ``materialize_package_view`` to restrict the ephemeral view to specific uploads only."""
    from truelinev2.harness.readiness_source import discover_package
    from truelinev2.harness.review_candidate import build_review_candidate
    from truelinev2.harness.route_verification import run_package_route_readiness

    work_dir = tempfile.mkdtemp(prefix="tl2_readiness_")
    try:
        pkg = materialize_package_view(uploads, job_files_root, work_dir, allowed_upload_ids=allowed_upload_ids)
        if pkg is None:
            return _no_readiness_result(
                "NO_SPINE_INPUT", "upload a plan PDF and a bore log / span table",
                "no plan / bore-log / route upload with a stored payload to evaluate")

        source = discover_package(pkg)
        if plan_sheet is not None:                             # explicit caller choice: raw-page semantics, unchanged
            sheet_ctx = _sheet_context(int(plan_sheet), int(plan_sheet), SHEET_SOURCE_EXPLICIT, [], [], None,
                                       "explicit plan_sheet=%d (raw page semantics, caller-chosen)"
                                       % int(plan_sheet))
        else:
            sheet_ctx = _derive_sheet_context(pkg, source.plan_path)
            if sheet_ctx["refusal"]:
                recommended = ("split the bore log by plan sheet or run with an explicit plan_sheet"
                               if sheet_ctx["refusal"] == MULTI_SHEET_REFS_UNSUPPORTED
                               else "verify the plan's title-block sheet labels or run with an explicit "
                                    "plan_sheet")
                return _no_readiness_result(sheet_ctx["refusal"], recommended, sheet_ctx["reason"],
                                            sheet_context=sheet_ctx)

        readiness = run_package_route_readiness(pkg, plan_sheet=int(sheet_ctx["engineering_sheet"]),
                                                plan_sheet_offset=int(sheet_ctx["sheet_offset"] or 0))
        if readiness is None:                                  # defensive — a materialized view always has a manifest
            return _no_readiness_result(
                "SOURCE_UNRESOLVED", "verify the uploaded plan / bore-log are readable",
                "the uploaded package could not be resolved for readiness", sheet_context=sheet_ctx)

        art = Path(artifact_dir) if artifact_dir is not None else None
        try:
            # build_review_candidate self-gates on READY -> a non-READY status writes ZERO artifacts even with art
            # set; only a READY package renders the overlay (on the SAME resolved page the observers read —
            # readiness.routes.sheet + sheet_offset).
            candidate_report = build_review_candidate(readiness, plan_path=source.plan_path, artifact_dir=art)
            candidate, artifact_names = _candidate_dict(candidate_report, art)
            return _result(readiness, candidate_report.candidate_status, candidate_report.generated_visual,
                           candidate_report.refusal_reason, candidate, artifact_names, render_error=False,
                           sheet_context=sheet_ctx)
        except Exception:                                      # noqa: BLE001 — an overlay render failure is not a 500
            _remove_pngs(art)                                  # drop any partially-written overlay
            return _result(readiness, "REVIEW_CANDIDATE_REFUSED", False,
                           "the source package is READY, but the REVIEW candidate overlay could not be rendered "
                           "this run (try again)", None, [], render_error=True, sheet_context=sheet_ctx)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# ---------------------------------------------------------------------------------------------------------------- #
# Phase-2 SOURCE-ROUTE ADOPTION seam: a NEW, additive, artifact-free, upload-FILTERED variant. It is a separate
# function (not a behavior change to run_job_readiness above) that returns the RAW ``PackageRouteReadiness``
# dataclass (never a serialized API dict, never a PNG, never a store write) so the pure
# ``contracts.source_route_adoption`` derivation can read ``RouteVerification.route_geometry`` and its inherited
# ``detail["isolation"]["detail"]["reach_tol"]`` directly — neither is exposed by the serialized bridge result.
# ---------------------------------------------------------------------------------------------------------------- #
def run_job_route_readiness_raw(uploads: Sequence[Dict[str, Any]], job_files_root, *,
                                plan_sheet: Optional[int] = None,
                                allowed_upload_ids: Optional[Sequence[str]] = None
                                ) -> Tuple[Optional[Any], Dict[str, Any]]:
    """Run the SAME unchanged readiness spine (sheet derivation + ``run_package_route_readiness``) as
    ``run_job_readiness``, but: (1) the ephemeral package view is FILTERED to ``allowed_upload_ids`` ONLY
    (never the job's full upload set — the source-route-adoption join requires evaluating exactly the
    caller-selected plan + BORE_LOG uploads, nothing else); (2) it draws NO REVIEW-candidate overlay, writes
    NO PNG, and persists NOTHING to any store (purely in-memory dataclasses, deleted ephemeral work dir).

    Returns ``(readiness, sheet_context)``: ``readiness`` is the raw ``PackageRouteReadiness`` (``None`` when
    the spine refused before reaching the classifier — no spine input, or an unresolved/multi sheet ref);
    ``sheet_context`` always reports how far sheet derivation got (Slice 3 shape), including a refusal reason
    when ``readiness`` is ``None``. Read-only wrt the product: no AUTO, no placement, no status promotion, no
    output slot, no lifecycle transition, no artifact."""
    from truelinev2.harness.readiness_source import discover_package
    from truelinev2.harness.route_verification import run_package_route_readiness

    work_dir = tempfile.mkdtemp(prefix="tl2_route_adoption_")
    try:
        pkg = materialize_package_view(uploads, job_files_root, work_dir, allowed_upload_ids=allowed_upload_ids)
        if pkg is None:
            return None, _sheet_context(
                None, None, None, [], [], "NO_SPINE_INPUT",
                "no plan / bore-log upload with a stored payload to evaluate for this selection")

        source = discover_package(pkg)
        if plan_sheet is not None:
            sheet_ctx = _sheet_context(int(plan_sheet), int(plan_sheet), SHEET_SOURCE_EXPLICIT, [], [], None,
                                       "explicit plan_sheet=%d (raw page semantics, caller-chosen)"
                                       % int(plan_sheet))
        else:
            sheet_ctx = _derive_sheet_context(pkg, source.plan_path)
            if sheet_ctx["refusal"]:
                return None, sheet_ctx

        readiness = run_package_route_readiness(pkg, plan_sheet=int(sheet_ctx["engineering_sheet"]),
                                                plan_sheet_offset=int(sheet_ctx["sheet_offset"] or 0))
        return readiness, sheet_ctx
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
