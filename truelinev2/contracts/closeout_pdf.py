"""Closeout PDF lane — server-rendered, trusted-data-only closeout packet (a real PDF; contract-only).

Renders a customer-readable closeout PACKET PDF from a job's EXISTING trusted output — the SAME trusted
sources ``export_bundle.py`` uses (the validated redline bundle + its manifest, the closeout / export-package
/ KMZ-export records, the reviewed-bore-log metadata, and the server-computed billing summary when present).
It draws the PDF with PyMuPDF (``fitz``, already a v2 dependency) and EMBEDS the sha256-VERIFIED
FINAL_REDLINE_PNG bytes as real image XObjects. It INVENTS nothing, FAKES no billing dollars, and FAKES no
KMZ coordinates.

This brings forward v1's customer-readable closeout-packet STRUCTURE (a FieldRoute header, numbered
sections, a readiness gate WITH reasons, an evidence-forward redline section, an honest disclaimer) WITHOUT
v1's unsafe client-side billing/rate math: every value here is server-derived from trusted records, and
dollar amounts appear ONLY when ``billing_summary.status`` is server-COMPUTED/FINAL from configured server
cost rules — otherwise the billing section honestly states it is omitted (no operator-typed dollars, ever).

Honesty / boundaries (mirrors export_bundle):
  * Embedded images come ONLY from the durable bundle store, resolved by manifest path + sha256 (the read
    consumer re-verifies the checksum) — never an on-disk scan, never a re-render.
  * Reads ONLY trusted slots/records — never ``job["uploads"]`` raw files, never the engine.
  * No dollars unless billing is server-COMPUTED/FINAL; no faked KMZ; pixel-only KMZ stated honestly.
  * No new manifest enum, no schema change, no engine/renderer/fixture/coordinate change.
  * A job with no validated redline bundle raises ``NoCloseoutPdfError`` (→ the route returns a SPECIFIC
    not-ready 409) — never a fake packet, never a fake redline image.
"""
from __future__ import annotations

import re

import fitz  # PyMuPDF — standard PDF engine (infrastructure, not TrueLine code)

from truelinev2.contracts.customer_project import validate_customer_project_id
from truelinev2.contracts.processing_job import job_dir, load_job, validate_job_id
from truelinev2.contracts.manifest_handoff import ARTIFACT_BUNDLE_SLOT, BUNDLE_STORE_SUBDIR
from truelinev2.contracts.published_bundle_consumer import StaticBundleConsumer
from truelinev2.contracts.closeout_review import (
    CloseoutNotFoundError, closeout_summary, load_closeout_review,
)
from truelinev2.contracts.export_package import (
    ExportPackageNotFoundError, export_package_view, load_export_package,
)
from truelinev2.contracts.extracted_row import CONFIRMED, CORRECTED
from truelinev2.contracts.kmz_export import EXPORTABLE as KMZ_EXPORTABLE_STATUS, evaluate_export
from truelinev2.contracts.reviewed_bore_log import list_reviewed_bore_logs
from truelinev2.contracts.export_bundle import placement_candidate_summary
from truelinev2.contracts.billing_summary import (
    COMPUTED as BILLING_COMPUTED, FINAL as BILLING_FINAL,
    BillingSummaryNotFoundError, billing_summary_view, load_billing_summary,
)
from truelinev2.contracts.job_pricing import PRICING_DISCLAIMER, pricing_view

PDF_MEDIA_TYPE = "application/pdf"
PDF_FILENAME = "closeout_packet_%s.pdf"

# A textual marker stamped into the PDF so tooling/tests can assert the document identity without OCR.
PDF_TITLE = "FieldRoute — Closeout Packet"
DISCLAIMER = "Generated from source evidence; review required before construction/use."

# Bundle origins that mean the redline came through the engine REVIEW lane (human accept/reject), vs the
# recognized deterministic lane. Derived from the published manifest (trusted) — no extra record reads.
_REVIEW_LANE_ORIGIN = "UPLOADED_CORPUS_ENGINE"
_DETERMINISTIC_LANE_ORIGINS = ("DETERMINISTIC_RECOGNIZED_CORPUS",)


class CloseoutPdfError(ValueError):
    """Base closeout-PDF error."""


class NoCloseoutPdfError(CloseoutPdfError):
    """The job has no validated redline bundle, so no closeout packet can be rendered (not ready)."""


# --------------------------------------------------------------------------- #
# Minimal, dependency-free PDF layout helper over fitz (auto-paginating cursor).
# --------------------------------------------------------------------------- #
_PAGE_W, _PAGE_H = 612.0, 792.0       # US Letter, points
_MARGIN = 54.0
_CONTENT_W = _PAGE_W - 2 * _MARGIN
_BOTTOM = _PAGE_H - _MARGIN

_BLACK = (0.0, 0.0, 0.0)
_GRAY = (0.40, 0.40, 0.40)
_RED = (0.70, 0.12, 0.12)
_GREEN = (0.05, 0.45, 0.20)
_BLUE = (0.10, 0.25, 0.55)


class _Pdf:
    def __init__(self):
        self.doc = fitz.open()
        self._new_page()

    def _new_page(self):
        self.page = self.doc.new_page(width=_PAGE_W, height=_PAGE_H)
        self.y = _MARGIN

    @staticmethod
    def _wrap(text, font, size, max_w):
        out = []
        for raw in str(text).split("\n"):
            words, cur = raw.split(), ""
            for w in words:
                trial = (cur + " " + w).strip()
                if not cur or fitz.get_text_length(trial, fontname=font, fontsize=size) <= max_w:
                    cur = trial
                else:
                    out.append(cur)
                    cur = w
            out.append(cur)
        return out or [""]

    def _ensure(self, h):
        if self.y + h > _BOTTOM:
            self._new_page()

    def text(self, s, size=10.0, font="helv", color=_BLACK, gap_after=3.0, indent=0.0):
        x = _MARGIN + indent
        max_w = _CONTENT_W - indent
        line_h = size * 1.4
        for line in self._wrap(s, font, size, max_w):
            self._ensure(line_h)
            self.page.insert_text((x, self.y + size), line, fontsize=size, fontname=font, color=color)
            self.y += line_h
        self.y += gap_after

    def title(self, s):
        self.text(s, size=18.0, font="hebo", color=_BLUE, gap_after=2.0)

    def heading(self, s, color=_BLACK):
        self.y += 8.0
        self._ensure(20.0)
        self.text(s, size=12.5, font="hebo", color=color, gap_after=2.0)
        self._rule()

    def _rule(self, color=(0.80, 0.80, 0.80)):
        self._ensure(6.0)
        self.page.draw_line((_MARGIN, self.y), (_PAGE_W - _MARGIN, self.y), color=color, width=0.6)
        self.y += 6.0

    def kv(self, key, value, color=_BLACK):
        """A label + value line; label in bold, value in regular (wrapped under if long)."""
        label = "%s: " % key
        lw = fitz.get_text_length(label, fontname="hebo", fontsize=10.0)
        self._ensure(14.0)
        self.page.insert_text((_MARGIN, self.y + 10.0), label, fontsize=10.0, fontname="hebo", color=_BLACK)
        # value on the same line if it fits, else wrap as its own indented block
        if fitz.get_text_length(str(value), fontname="helv", fontsize=10.0) <= _CONTENT_W - lw:
            self.page.insert_text((_MARGIN + lw, self.y + 10.0), str(value),
                                  fontsize=10.0, fontname="helv", color=color)
            self.y += 14.0
        else:
            self.y += 14.0
            self.text(str(value), size=10.0, color=color, indent=12.0, gap_after=1.0)

    def bullet(self, s, color=_BLACK):
        self.text("• " + str(s), size=9.5, color=color, indent=8.0, gap_after=1.0)

    def small(self, s, color=_GRAY, font="helv"):
        self.text(s, size=8.0, font=font, color=color, gap_after=2.0)

    def image(self, png_bytes, caption=None):
        """Embed a PNG as a real image XObject, scaled to content width (own page if tall). If the bytes
        cannot be decoded, draw an HONEST note instead of crashing — never a fake/substitute image."""
        try:
            pix = fitz.Pixmap(png_bytes)
            iw, ih = float(pix.width), float(pix.height)
            if iw <= 0 or ih <= 0:
                raise ValueError("empty image")
            scale = _CONTENT_W / iw
            draw_w, draw_h = _CONTENT_W, ih * scale
            max_h = _BOTTOM - _MARGIN
            if draw_h > max_h:
                scale = max_h / ih
                draw_w, draw_h = iw * scale, max_h
            if self.y + draw_h > _BOTTOM:
                self._new_page()
            rect = fitz.Rect(_MARGIN, self.y, _MARGIN + draw_w, self.y + draw_h)
            self.page.insert_image(rect, stream=png_bytes)
            self.y += draw_h + 3.0
        except Exception:
            self.small("[redline image could not be embedded — see artifact detail below]", color=_RED)
        if caption:
            self.small(caption)

    def to_bytes(self):
        # Deterministic-ish: no timestamps embedded by us; scrub fitz's date/producer noise.
        self.doc.set_metadata({
            "title": PDF_TITLE, "author": "FieldRoute", "subject": "Closeout packet",
            "creator": "FieldRoute closeout_pdf", "producer": "FieldRoute closeout_pdf",
            "keywords": "", "creationDate": "", "modDate": "",
        })
        return self.doc.tobytes()


# --------------------------------------------------------------------------- #
# Trusted-data gather (mirrors export_bundle) + render.
# --------------------------------------------------------------------------- #
def _open_bundle(store_root, customer_project_id, job_id):
    """Open the job's attached, validated redline bundle (read-only consumer). Raises NoCloseoutPdfError if
    the job has no validated artifact_bundle slot (set ONLY by a SUCCEEDED handoff)."""
    job = load_job(store_root, customer_project_id, job_id)
    slot = (job.get("slots") or {}).get(ARTIFACT_BUNDLE_SLOT)
    if not slot:
        raise NoCloseoutPdfError(
            "job '%s' has no validated redline bundle — not ready for a closeout packet "
            "(generate the redline and assemble closeout/export first)" % job_id)
    bundle_store = job_dir(store_root, customer_project_id, job_id) / BUNDLE_STORE_SUBDIR
    return job, StaticBundleConsumer(bundle_store, enable=True).open_bundle(slot["ref"]["bundle_id"])


def _drawn_footage(manifest):
    """Sum trusted drawn footage from per-log closure.drawn_ft over DRAWN logs; None if no log carries it
    (e.g. pixel-only renders have closure=None — footage is then honestly unavailable, never invented)."""
    total, seen = 0.0, False
    for log in manifest.get("logs", []) or []:
        closure = log.get("closure")
        if log.get("drawn") and isinstance(closure, dict) and closure.get("drawn_ft") is not None:
            try:
                total += float(closure["drawn_ft"])
                seen = True
            except (TypeError, ValueError):
                continue
    return round(total, 1) if seen else None


# Case-insensitive field aliases for pulling a reviewed row's own bore-log values, reimplemented LOCALLY
# (never imported from render/) so this contract-only PDF module stays render-import-free — mirrors the
# SAME alias-tolerance idea already used by ``render.station_dots.resolve_bore_fields`` and
# ``contracts.reviewed_bore_adapter._FIELD_ALIASES``: a free-form extractor may spell a column
# ``footage``/``footage_ft``, ``depth``/``depth_min_ft``, etc., and every spelling must resolve identically.
_ROW_NUM_RE = re.compile(r"[-+]?\d*\.?\d+")
_ROW_FIELD_ALIASES = {
    "start_station": ("start_station", "start_sta", "from_station", "sta_start", "start"),
    "end_station": ("end_station", "end_sta", "to_station", "sta_end", "end"),
    "footage": ("footage_ft", "footage", "ft", "feet", "length", "bore_footage"),
    "depth": ("depth_min_ft", "depth", "bore_depth"),
    "boc": ("boc_min_ft", "boc", "bottom_of_conduit"),
}


def _row_norm_key(k) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(k).strip().lower()).strip("_")


def _row_effective_values(row) -> dict:
    """Effective bore-log values for ONE extracted row by precedence raw < normalized < review.corrected
    (human CORRECTED wins last) -- the SAME precedence ``render.station_dots.resolve_bore_fields`` and
    ``contracts.reviewed_bore_adapter._effective_values`` already use, reimplemented here so this module
    imports neither. Keys folded via ``_row_norm_key`` for alias matching."""
    merged: dict = {}
    for layer in (row.get("raw"), row.get("normalized"), (row.get("review") or {}).get("corrected_values")):
        if isinstance(layer, dict):
            for k, v in layer.items():
                merged[_row_norm_key(k)] = v
    return merged


def _row_pick(merged, aliases):
    for a in aliases:
        if a in merged and merged[a] not in (None, ""):
            return merged[a]
    return None


def _row_num(value):
    """Coerce a numeric-ish cell ("42", "42 ft", 42, 42.0) to float; None when absent/non-numeric --
    never a fabricated 0."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = _ROW_NUM_RE.search(str(value))
    return float(m.group(0)) if m else None


def _row_summary_line(row) -> str:
    """One human-readable closeout line for a CONFIRMED/CORRECTED reviewed row: station span + footage
    ALWAYS, depth/BOC appended ONLY when the source actually carries them (effective corrected > normalized
    > raw value) -- never an invented placeholder for a row with no depth/BOC column at all."""
    v = _row_effective_values(row)
    start = _row_pick(v, _ROW_FIELD_ALIASES["start_station"])
    end = _row_pick(v, _ROW_FIELD_ALIASES["end_station"])
    footage = _row_num(_row_pick(v, _ROW_FIELD_ALIASES["footage"]))
    depth = _row_num(_row_pick(v, _ROW_FIELD_ALIASES["depth"]))
    boc = _row_num(_row_pick(v, _ROW_FIELD_ALIASES["boc"]))
    span = "%s -> %s" % (start or "?", end or "?")
    parts = [span]
    if footage is not None:
        parts.append("%s ft" % footage)
    if depth is not None:
        parts.append("depth %s ft" % depth)
    if boc is not None:
        parts.append("BOC %s ft" % boc)
    return ", ".join(parts)


def build_closeout_pdf(store_root, customer_project_id, job_id) -> tuple:
    """Render the job's closeout packet PDF from EXISTING trusted output. Returns (pdf_bytes, filename).
    Raises NoCloseoutPdfError if the job has no validated redline bundle yet (not ready)."""
    validate_customer_project_id(customer_project_id)
    validate_job_id(job_id)
    job, bundle = _open_bundle(store_root, customer_project_id, job_id)
    manifest = bundle.manifest_payload()
    summary = manifest.get("summary", {}) or {}
    engine = manifest.get("engine", {}) or {}
    origin = manifest.get("bundle_origin")

    kmz = evaluate_export(store_root, customer_project_id, job_id)
    try:
        co = load_closeout_review(store_root, customer_project_id, job_id)
        closeout = {"record": co, "summary": closeout_summary(co)}
    except CloseoutNotFoundError:
        closeout = None
    try:
        ep = load_export_package(store_root, customer_project_id, job_id)
        export_pkg = export_package_view(ep)
    except ExportPackageNotFoundError:
        export_pkg = None
    try:
        bill = load_billing_summary(store_root, customer_project_id, job_id)
        billing = {"record": bill, "view": billing_summary_view(bill)}
    except BillingSummaryNotFoundError:
        billing = None
    op_pricing = pricing_view(store_root, customer_project_id, job_id)   # operator-entered (unverified)
    rbls = list_reviewed_bore_logs(store_root, customer_project_id, job_id)
    candidates = placement_candidate_summary(store_root, customer_project_id, job_id, manifest)

    d = _Pdf()

    # Header + disclaimer
    d.title(PDF_TITLE)
    d.small(DISCLAIMER, color=_RED, font="hebo")

    # REVIEW-candidate banner — prominent + honest when this packet carries general-upload REVIEW candidates
    # that are not all accepted (never shown for a recognized deterministic package, which has no candidates).
    if candidates["candidate_count"] and candidates["review_required"]:
        d.heading("REVIEW REQUIRED — candidate placement from uploaded project evidence", color=_RED)
        d.text("This packet includes %d REVIEW placement candidate(s) (%d accepted) generated from uploaded "
               "project evidence. They are NOT deterministic AUTO/FINAL truth: each carries a confidence band "
               "and must be reviewed/accepted (and corrected if needed) before construction or billing use."
               % (candidates["candidate_count"], candidates["accepted_count"]), color=_RED)

    # 1. Job / project summary
    d.heading("1. Job / Project Summary")
    d.kv("Project", manifest.get("project_id") or customer_project_id)
    d.kv("Job", job_id)
    d.kv("Job status", job.get("status"))
    d.kv("Redline lane (bundle origin)", origin)
    if engine.get("render_commit"):
        d.kv("Render commit", engine.get("render_commit"))

    # 2. Closeout status & gate result
    d.heading("2. Closeout Status & Gate")
    if closeout is None:
        d.text("No closeout_review has been evaluated for this job yet.", color=_GRAY)
    else:
        cs = closeout["summary"]
        status = cs.get("status")
        d.kv("Closeout status", status, color=(_GREEN if not cs.get("is_blocked") else _RED))
        d.kv("Hard blockers", cs.get("hard_blocker_count", 0))
        d.kv("Warnings", cs.get("warning_count", 0))
        for code in cs.get("hard_blocker_codes", []) or []:
            d.bullet("BLOCKER: %s" % code, color=_RED)
        for code in cs.get("warning_codes", []) or []:
            d.bullet("warning: %s" % code, color=_GRAY)

    # 3. Deliverable quantity summary (engine-derived; NO dollars)
    d.heading("3. Deliverable Quantities")
    artifacts = [(log_id, art) for log_id, art in bundle.final_artifacts()]
    rbl_row_count = sum(len(r.get("rows") or []) for r in rbls)
    footage = _drawn_footage(manifest)
    d.kv("Logs drawn / total", "%s / %s" % (summary.get("drawn_count"), summary.get("total_logs")))
    d.kv("Logs covered", summary.get("covered_count"))
    d.kv("Logs blocked", summary.get("blocked_count"))
    d.kv("Frontier (this bundle)", summary.get("frontier"))
    d.kv("Redline PNG artifacts", len(artifacts))
    d.kv("Reviewed bore-log rows", rbl_row_count)
    d.kv("Drawn footage", ("%s ft" % footage) if footage is not None else "not available (no trusted closure footage)")

    # 4. Redline evidence — embed the sha256-verified PNG(s)
    d.heading("4. Redline Evidence")
    if not artifacts:
        d.text("No FINAL_REDLINE_PNG artifacts in the validated bundle.", color=_RED)
    for log_id, art in artifacts:
        desc = bundle.resolve_artifact(art["path"], read_bytes=True)   # sha256-verified bytes
        sheet = art.get("sheet")
        cap = "%s  %s  sha256:%s" % (
            art.get("path"), ("sheet %s" % sheet) if sheet is not None else "", (art.get("sha256") or "")[:16] + "…")
        d.image(desc["data"], caption=cap)

    # 5. Artifact metadata (kind / sheet / sha256 / provenance + status)
    d.heading("5. Artifact Detail")
    for log in manifest.get("logs", []) or []:
        prov = log.get("provenance")
        lstatus = log.get("status")
        d.kv("Log %s" % log.get("log_id"), "%s  (provenance %s)" % (lstatus, prov))
        for art in log.get("artifacts", []) or []:
            sheet = art.get("sheet")
            line = "%s  %s  %s  sha256 %s" % (
                art.get("kind"), art.get("path"),
                ("sheet %s" % sheet) if sheet is not None else "(no sheet)",
                (art.get("sha256") or "")[:24] + "…")
            d.bullet(line, color=_GRAY)
        # Phase-2 SOURCE-ROUTE ADOPTION (T31 Q5) + Mission 8 manual-route: wording discriminated by the log's
        # ACTUAL provenance block (Sol Q4/Q9 -- NEVER a bare truthy ``geometry_basis`` check, since a manual
        # v2 record ALSO carries geometry_basis now). Every other log (deterministic, recognized, uploaded-
        # engine, and a plain pre-Mission-8 manual v1 record) carries NEITHER block and this executes NOTHING
        # for it — output stays byte-identical.
        if log.get("route_adoption") is not None:
            ra = log.get("route_adoption") or {}
            d.bullet("Geometry: source-backed observer backbone — %s adoption"
                     % (log.get("confirmation_state") or "HUMAN_REVIEWED"), color=_BLACK)
            sheet_bits = []
            if ra.get("engineering_sheet") is not None:
                sheet_bits.append("engineering sheet %s" % ra["engineering_sheet"])
            if ra.get("pdf_page") is not None:
                sheet_bits.append("PDF page %s" % ra["pdf_page"])
            if sheet_bits:
                d.bullet("Source sheet: %s" % ", ".join(sheet_bits), color=_GRAY)
            if ra.get("proposal_hash"):
                d.bullet("Proposal hash: %s" % ra["proposal_hash"], color=_GRAY)
            for w in (ra.get("warnings") or []):
                d.bullet("caution: %s" % w, color=_RED)
        elif log.get("manual_route") is not None:
            mr = log.get("manual_route") or {}
            rep_status = mr.get("representative_status")
            if rep_status == "MANUAL_POLYLINE_CONFIRMED":
                wording = "Geometry: manual polyline confirmed by reviewer"
            else:
                wording = "Geometry: representative straight segment accepted by reviewer"
            confirmer = mr.get("confirmed_by")
            if confirmer:
                wording += " (%s)" % confirmer
            d.bullet(wording, color=_BLACK)
            reported = mr.get("reported_route_search") or {}
            if reported.get("code"):
                line = "reported route-search refusal: %s" % reported["code"]
                if reported.get("upstream_reason_code"):
                    line += " (upstream %s)" % reported["upstream_reason_code"]
                d.bullet(line, color=_GRAY)

    # 6. Reviewed bore-log summary
    d.heading("6. Reviewed Bore-Log Summary")
    if not rbls:
        d.text("No reviewed bore-logs recorded for this job.", color=_GRAY)
    for r in rbls:
        rid = r.get("reviewed_bore_log_id") or r.get("id")
        rows = r.get("rows") or []
        groups = r.get("groups") or []
        ready = r.get("engine_ready")
        d.kv("Reviewed bore-log %s" % rid,
             "%d row(s), %d group(s), engine_ready=%s" % (len(rows), len(groups), ready))
        # Additive per-row line for every human-REVIEWED row (CONFIRMED/CORRECTED -- the same states that
        # make a row a placement candidate, extracted_row.REVIEW_PASS_STATUSES): station span + footage
        # always, depth/BOC appended ONLY when the source actually carries them. UNREVIEWED/REJECTED rows
        # are not yet trusted customer-facing facts and are intentionally left out of this listing.
        for row in rows:
            if (row.get("review") or {}).get("status") in (CONFIRMED, CORRECTED):
                d.bullet(_row_summary_line(row), color=_GRAY)

    # 7. Engine path / REVIEW status (only when relevant)
    if origin == _REVIEW_LANE_ORIGIN:
        d.heading("7. Engine REVIEW Status")
        d.text("This redline came through the engine REVIEW lane: an engine-generated candidate that a human "
               "ACCEPTED before publishing (never auto-promoted). Provenance is carried per-log in the "
               "manifest above.", color=_BLACK)
        for c in candidates["candidates"]:
            state_color = _GREEN if c["state"] == "ACCEPTED" else (_RED if c["state"] == "REJECTED" else _GRAY)
            basis = ("generic-geometry fallback" if c.get("generic_fallback")
                     else (c.get("dialect") or "engine"))
            d.kv("Candidate %s" % c["log_id"],
                 "%s · confidence %s%s · %s" % (
                     c["state"], c.get("confidence") or "ungraded",
                     (" (%.2f)" % c["confidence_score"]) if c.get("confidence_score") is not None else "",
                     basis),
                 color=state_color)
            for r in (c.get("reasons") or []):
                d.bullet("why: %s" % r, color=_GRAY)
            for w in (c.get("warnings") or []):
                d.bullet("caution: %s" % w, color=_RED)
            if c.get("rejection_reason"):
                d.bullet("rejected: %s" % c["rejection_reason"], color=_RED)
    elif origin in _DETERMINISTIC_LANE_ORIGINS:
        d.heading("7. Engine Path")
        d.text("Recognized deterministic package: the system served the EXISTING proven engine redline for "
               "the matched log(s) — engine-derived, not hand-drawn, no human acceptance gate.", color=_BLACK)

    # 8. Blockers / abstains (only when relevant)
    blocked_logs = [l for l in (manifest.get("logs") or []) if l.get("blocked")]
    hard_codes = (closeout["summary"].get("hard_blocker_codes") if closeout else []) or []
    if blocked_logs or hard_codes:
        d.heading("8. Blockers / Abstains", color=_RED)
        for l in blocked_logs:
            d.bullet("log %s blocked: %s" % (l.get("log_id"), l.get("blocker")), color=_RED)
        for code in hard_codes:
            d.bullet("closeout blocker: %s" % code, color=_RED)

    # 9. Export package contents
    d.heading("9. Export Package Contents")
    if export_pkg is None:
        d.text("No export_package descriptor has been assembled for this job yet.", color=_GRAY)
    else:
        d.kv("Export status", export_pkg.get("status"))
        d.kv("Included sections", ", ".join(export_pkg.get("included_sections", []) or []) or "(none)")
        d.kv("Omitted sections", ", ".join(export_pkg.get("omitted_sections", []) or []) or "(none)")

    # 10. KMZ / geospatial export (honest; never faked)
    d.heading("10. KMZ / Geospatial Export")
    if kmz.get("status") == KMZ_EXPORTABLE_STATUS:
        d.text("KMZ is exportable from verified geospatial geometry.", color=_GREEN)
    else:
        codes = ", ".join(sorted({b.get("code") for b in (kmz.get("blockers") or [])})) or "BLOCKED"
        d.kv("KMZ status", "%s (%s)" % (kmz.get("status"), kmz.get("geometry_basis")), color=_GRAY)
        d.text("KMZ/KML is NOT included: %s. The system refuses to fake geographic coordinates for "
               "pixel-space redlines." % codes, color=_GRAY)

    # 11. Billing — QUANTITIES already shown in §3; dollars ONLY when server-computed/final.
    d.heading("11. Billing Summary")
    if billing is None:
        d.text("Billing summary omitted — no server cost rules configured.", color=_GRAY)
        d.small("Deliverable quantities are in section 3. No operator-entered or client-side dollar amounts "
                "are ever shown.")
    else:
        bview = billing["view"]
        bstatus = bview.get("status")
        if bstatus in (BILLING_COMPUTED, BILLING_FINAL):
            d.kv("Billing status", bstatus, color=_GREEN)
            d.kv("Currency", bview.get("currency"))
            cur_id = billing["record"].get("current_revision_id")
            rev = next((rv for rv in (billing["record"].get("revisions") or [])
                        if rv.get("revision_id") == cur_id), None)
            for line in ((rev or {}).get("charge_lines") or []):
                d.bullet("%s — %s %s @ rule %s = %s" % (
                    line.get("label"), line.get("quantity"), line.get("unit"),
                    line.get("rule_ref"), line.get("amount")))
            totals = bview.get("totals") or {}
            if totals:
                d.kv("Final total", "%s %s" % (totals.get("final_total"), bview.get("currency")))
        else:
            d.kv("Billing status", bstatus, color=_GRAY)
            d.text("Billing dollars omitted — billing is not server-finalized (status %s). Deliverable "
                   "quantities are in section 3; no client-side dollars are shown." % bstatus, color=_GRAY)

    # 12. Operator-entered pricing — the operator's OWN provisional rates, explicitly UNVERIFIED and kept
    # DISTINCT from §11 (the server-authoritative billing). Shown only when the operator entered something.
    has_op_pricing = bool(op_pricing.get("cost_per_foot") is not None or op_pricing.get("exceptions"))
    if has_op_pricing:
        d.heading("12. Operator-Entered Pricing (UNVERIFIED)")
        d.small(PRICING_DISCLAIMER, color=_RED, font="hebo")
        cur = op_pricing.get("currency") or "USD"
        if op_pricing.get("footage") is not None:
            d.kv("Footage (server-computed)", "%s ft" % op_pricing.get("footage"))
        else:
            d.kv("Footage (server-computed)", "not available yet", color=_GRAY)
        d.kv("Cost per foot (operator-entered)",
             ("%s %s" % (op_pricing.get("cost_per_foot"), cur)) if op_pricing.get("cost_per_foot") is not None
             else "not entered", color=(_GRAY if op_pricing.get("cost_per_foot") is None else None))
        if op_pricing.get("base_total") is not None:
            d.kv("Base total (footage × rate)", "%s %s" % (op_pricing.get("base_total"), cur))
        for ex in (op_pricing.get("exceptions") or []):
            amt = ("%s %s" % (ex.get("amount"), cur)) if ex.get("amount") is not None else "—"
            d.bullet("%s — %s%s" % (ex.get("label"), amt,
                                    (" (%s)" % ex.get("note")) if ex.get("note") else ""))
        d.kv("Exception total", "%s %s" % (op_pricing.get("exception_total"), cur))
        if op_pricing.get("final_total") is not None:
            d.kv("Final total (operator-entered, unverified)", "%s %s" % (op_pricing.get("final_total"), cur))
        elif op_pricing.get("totals_note"):
            d.text(op_pricing.get("totals_note"), color=_GRAY)

    # Footer disclaimer
    d.y += 10.0
    d._rule()
    d.small(DISCLAIMER, color=_RED, font="hebo")
    d.small("FieldRoute closeout packet — assembled from trusted server-side records and sha256-verified "
            "redline artifacts. No coordinates, dollars, or evidence are invented.")

    return d.to_bytes(), PDF_FILENAME % job_id
