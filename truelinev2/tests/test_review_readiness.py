"""Proof for the read-only SOURCE-COMPLETENESS / REVIEW-REDLINE-READINESS classifier (the intake traffic
controller in truelinev2/harness/review_readiness.py).

It routes the read-only Track B stage evidence for an uploaded package to ONE readiness status and names the
next productive step. It draws nothing, places nothing, promotes nothing. This test:

  * exercises every one of the 9 readiness statuses;
  * reproduces the four public cold-package findings as name-free evidence fixtures (the package ids are
    anonymized runtime data, never customer/person/place names):
        public-cold-001 -> PACKAGE_RECOGNIZED_CONTROL   (recognized: the deterministic control lane)
        public-cold-002 -> ANCHOR_BLOCKED               (span present, route-attached anchors do not resolve)
        public-cold-009 -> MISSING_BORE_SPAN_SOURCE     (plan-only; no source file confirms the span) plus a
                                                         NO_SOURCE_CONFIRMED_SPAN contributing reason, even
                                                         though its anchors WOULD resolve
        public-cold-011 -> KEEP_BLOCKED                 (owner/adversarial terminal reclassification)
  * proves the doctrine invariant: the classifier NEVER promotes a package to KEEP_BLOCKED on its own — even a
    double structural block is only an advisory candidate for an OWNER reclassification;
  * test-locks the classifier's PASS status sets against the real observer constants so they cannot drift.
"""
from __future__ import annotations

from truelinev2.extract.plan_view_anchor_resolver import (
    ANCHOR_RESOLVED_TO_LEADER_TIP,
    ANCHOR_RESOLVED_TO_ROUTE_ENDPOINT,
    ANCHOR_RESOLVED_TO_SYMBOL,
    AMBIGUOUS_ANCHOR,
    LABEL_ONLY_NO_ANCHOR,
    NO_SUPPORTED_ANCHOR,
)
from truelinev2.extract.plan_view_run_observer import PLAN_VIEW_RUN_CONNECTED
from truelinev2.extract.route_main_run import MAIN_ROUTE_DISCRIMINATED, NO_MAIN_ROUTE
from truelinev2.harness.review_readiness import (
    ALL_STATUSES,
    ANCHOR_BLOCKED,
    ANCHOR_PASS_STATUSES,
    AnchorEvidence,
    KEEP_BLOCKED,
    MISSING_BORE_SPAN_SOURCE,
    NO_SOURCE_CONFIRMED_SPAN,
    PACKAGE_RECOGNIZED_CONTROL,
    PACKAGE_UNUSABLE_OCR_REQUIRED,
    READY_FOR_REVIEW_REDLINE,
    ROUTE_BLOCKED,
    ROUTE_PASS_STATUSES,
    ReviewReadinessEvidence,
    RouteEvidence,
    SPAN_SOURCE_FOUND,
    SpanSourceEvidence,
    anchor_resolved,
    classify_review_readiness,
    format_report,
    route_verified,
)


# ----------------------------------------------------------------------------------------------------------- #
# Builders (name-free; package ids are anonymized runtime data).
# ----------------------------------------------------------------------------------------------------------- #
def _ev(package_id, *, plan_readable=True, recognized=False, keep_blocked=False, keep_blocked_reason="",
        span=None, anchor=None, route=None, detail=None):
    return ReviewReadinessEvidence(
        package_id=package_id, plan_readable=plan_readable, recognized=recognized,
        keep_blocked=keep_blocked, keep_blocked_reason=keep_blocked_reason,
        span=span, anchor=anchor, route=route, detail=detail or {})


def _confirmed_span(**kw):
    kw.setdefault("bore_span_source_files", ("BORE_LOG",))
    kw.setdefault("plan_span_layer_inspected", True)
    kw.setdefault("source_confirmed_span_count", 1)
    return SpanSourceEvidence(**kw)


# ----------------------------------------------------------------------------------------------------------- #
# The four public cold-package findings, reproduced as evidence.
# ----------------------------------------------------------------------------------------------------------- #
def test_public_cold_001_recognized_is_control_lane():
    """Recognized by a named dialect -> deterministic control lane, out of the cold REVIEW pipeline."""
    r = classify_review_readiness(_ev("public-cold-001", recognized=True))
    assert r.status == PACKAGE_RECOGNIZED_CONTROL
    assert r.is_control is True and r.ready is False
    assert r.recommended_next_input is None            # nothing to collect: not a cold-lane package
    assert r.draws_anything is False and r.performs_placement is False


def test_public_cold_002_span_present_but_anchors_unresolved_is_anchor_blocked():
    """A span exists (HDD entry/exit) but the route-attached anchors do not resolve (all AMBIGUOUS_ANCHOR);
    the route is not even evaluated because the anchors failed -> ANCHOR_BLOCKED (a single-stage blocker)."""
    r = classify_review_readiness(_ev(
        "public-cold-002",
        span=_confirmed_span(bore_span_source_files=("BORE_LOG",), source_confirmed_span_count=1),
        anchor=AnchorEvidence(start_status=AMBIGUOUS_ANCHOR, end_status=AMBIGUOUS_ANCHOR),
        route=None))
    assert r.status == ANCHOR_BLOCKED
    assert r.double_structural_block is False           # route not independently blocked -> not a double block
    assert r.keep_blocked_candidate is False
    assert r.recommended_next_input is not None


def test_public_cold_009_plan_only_no_source_span_despite_resolvable_anchors():
    """009 is the one probed cold plan whose anchors DO bind (STA -> symbol / route endpoint), yet no source
    file confirms a span and the plan alone confirms none -> MISSING_BORE_SPAN_SOURCE (needs a bore log), with
    NO_SOURCE_CONFIRMED_SPAN as a contributing reason. The blocker is upstream of the anchors."""
    r = classify_review_readiness(_ev(
        "public-cold-009",
        span=SpanSourceEvidence(bore_span_source_files=(),          # no bore-log / bore-schedule file
                                plan_span_layer_inspected=True,       # the plan WAS scanned for a printed span
                                source_confirmed_span_count=0),       # zero spans tied as one bore
        anchor=AnchorEvidence(start_status=ANCHOR_RESOLVED_TO_SYMBOL,
                              end_status=ANCHOR_RESOLVED_TO_ROUTE_ENDPOINT)))
    assert r.status == MISSING_BORE_SPAN_SOURCE
    assert NO_SOURCE_CONFIRMED_SPAN in r.contributing_reasons
    assert MISSING_BORE_SPAN_SOURCE in r.contributing_reasons
    assert r.stage == "SPAN_SOURCE"
    # the anchors would resolve -> the report proves the blocker is the source span, not the anchors
    assert r.detail.get("anchors_would_resolve") is True
    assert r.recommended_next_input == "BORE_LOG_OR_BORE_SCHEDULE_NAMING_ONE_SPAN"
    assert r.draws_anything is False and r.performs_placement is False


def test_public_cold_011_owner_reclassified_keep_blocked():
    """011 was reclassified by the owner (two independent structural blockers: fragmented route + off-route
    labels). The classifier honors that terminal reclassification -> KEEP_BLOCKED."""
    r = classify_review_readiness(_ev(
        "public-cold-011", keep_blocked=True,
        keep_blocked_reason="two independent structural blockers: fragmented route + off-route labels",
        span=SpanSourceEvidence(bore_span_source_files=(), plan_span_layer_inspected=True,
                                source_confirmed_span_count=0),
        anchor=AnchorEvidence(start_status=NO_SUPPORTED_ANCHOR, end_status=NO_SUPPORTED_ANCHOR),
        route=RouteEvidence(status=NO_MAIN_ROUTE)))
    assert r.status == KEEP_BLOCKED
    assert r.stage == "KEEP_BLOCKED"
    assert "structural" in r.reason
    assert r.draws_anything is False and r.performs_placement is False


# ----------------------------------------------------------------------------------------------------------- #
# The remaining statuses.
# ----------------------------------------------------------------------------------------------------------- #
def test_ready_when_span_anchors_and_route_all_clear():
    r = classify_review_readiness(_ev(
        "pkg-ready",
        span=_confirmed_span(),
        anchor=AnchorEvidence(start_status=ANCHOR_RESOLVED_TO_SYMBOL, end_status=ANCHOR_RESOLVED_TO_LEADER_TIP),
        route=RouteEvidence(status=MAIN_ROUTE_DISCRIMINATED)))
    assert r.status == READY_FOR_REVIEW_REDLINE
    assert r.ready is True and r.stage == "READY"
    assert r.recommended_next_input is None
    assert r.draws_anything is False and r.performs_placement is False   # READY still draws nothing


def test_span_found_when_downstream_not_yet_evaluated():
    r = classify_review_readiness(_ev("pkg-span", span=_confirmed_span(), anchor=None, route=None))
    assert r.status == SPAN_SOURCE_FOUND
    assert r.recommended_next_input == "RUN_ANCHOR_AND_ROUTE_GATES"


def test_span_found_when_anchored_but_route_not_evaluated():
    r = classify_review_readiness(_ev(
        "pkg-span2", span=_confirmed_span(),
        anchor=AnchorEvidence(start_status=ANCHOR_RESOLVED_TO_SYMBOL, end_status=ANCHOR_RESOLVED_TO_SYMBOL),
        route=None))
    assert r.status == SPAN_SOURCE_FOUND and r.stage == "ANCHOR"


def test_no_source_confirmed_span_when_a_span_file_is_present_but_yields_nothing():
    """A bore-span source FILE is present but confirms no complete span -> NO_SOURCE_CONFIRMED_SPAN is primary
    (distinct from the plan-only MISSING_BORE_SPAN_SOURCE case)."""
    r = classify_review_readiness(_ev(
        "pkg-nospan",
        span=SpanSourceEvidence(bore_span_source_files=("BORE_LOG",), plan_span_layer_inspected=True,
                                source_confirmed_span_count=0)))
    assert r.status == NO_SOURCE_CONFIRMED_SPAN
    assert MISSING_BORE_SPAN_SOURCE not in r.contributing_reasons   # a source file WAS present


def test_missing_span_source_when_nothing_was_inspected():
    """Plan-only with no span source and no plan-span scan -> MISSING_BORE_SPAN_SOURCE."""
    r = classify_review_readiness(_ev("pkg-planonly", span=None))
    assert r.status == MISSING_BORE_SPAN_SOURCE
    assert r.recommended_next_input == "BORE_LOG_OR_BORE_SCHEDULE_NAMING_ONE_SPAN"


def test_route_blocked_when_anchored_but_route_unverifiable():
    r = classify_review_readiness(_ev(
        "pkg-route", span=_confirmed_span(),
        anchor=AnchorEvidence(start_status=ANCHOR_RESOLVED_TO_SYMBOL, end_status=ANCHOR_RESOLVED_TO_SYMBOL),
        route=RouteEvidence(status=NO_MAIN_ROUTE)))
    assert r.status == ROUTE_BLOCKED and r.stage == "ROUTE"
    assert r.recommended_next_input == "ROUTE_CONTINUITY_GATE"


def test_ocr_required_when_plan_has_no_text_layer():
    r = classify_review_readiness(_ev("pkg-scan", plan_readable=False))
    assert r.status == PACKAGE_UNUSABLE_OCR_REQUIRED
    assert r.recommended_next_input == "OCR_OR_RASTER_INGESTION"


# ----------------------------------------------------------------------------------------------------------- #
# Doctrine: the classifier never declares KEEP_BLOCKED on its own.
# ----------------------------------------------------------------------------------------------------------- #
def test_double_structural_block_is_only_an_advisory_not_auto_keep_blocked():
    """A package independently blocked at BOTH the anchor and route stages is a CANDIDATE for an owner
    KEEP_BLOCKED reclassification, but the classifier must NOT promote it to KEEP_BLOCKED by itself — it
    classifies by stage (ANCHOR first) and only flags the advisory."""
    r = classify_review_readiness(_ev(
        "pkg-double", keep_blocked=False,
        span=_confirmed_span(),
        anchor=AnchorEvidence(start_status=AMBIGUOUS_ANCHOR, end_status=LABEL_ONLY_NO_ANCHOR),
        route=RouteEvidence(status=NO_MAIN_ROUTE)))
    assert r.status == ANCHOR_BLOCKED               # NOT KEEP_BLOCKED
    assert r.double_structural_block is True
    assert r.keep_blocked_candidate is True         # advisory: an owner MAY reclassify


def test_owner_marker_forces_keep_blocked_even_on_a_single_blocker():
    """The owner marker is authoritative and short-circuits the whole ladder, even if only one stage is weak."""
    r = classify_review_readiness(_ev(
        "pkg-ownerkb", keep_blocked=True,
        span=_confirmed_span(),
        anchor=AnchorEvidence(start_status=ANCHOR_RESOLVED_TO_SYMBOL, end_status=ANCHOR_RESOLVED_TO_SYMBOL),
        route=RouteEvidence(status=MAIN_ROUTE_DISCRIMINATED)))
    assert r.status == KEEP_BLOCKED


# ----------------------------------------------------------------------------------------------------------- #
# Precedence.
# ----------------------------------------------------------------------------------------------------------- #
def test_recognition_wins_over_every_other_signal():
    r = classify_review_readiness(_ev("pkg-rec", recognized=True, plan_readable=False, keep_blocked=True))
    assert r.status == PACKAGE_RECOGNIZED_CONTROL


def test_keep_blocked_wins_over_span_stage():
    r = classify_review_readiness(_ev("pkg-kb-first", keep_blocked=True, span=None))
    assert r.status == KEEP_BLOCKED               # not MISSING_BORE_SPAN_SOURCE


def test_ocr_wins_over_keep_blocked_and_span():
    r = classify_review_readiness(_ev("pkg-ocr-first", plan_readable=False, keep_blocked=True, span=None))
    assert r.status == PACKAGE_UNUSABLE_OCR_REQUIRED


# ----------------------------------------------------------------------------------------------------------- #
# Invariants + coverage + anti-drift.
# ----------------------------------------------------------------------------------------------------------- #
def _every_status_fixture():
    return [
        classify_review_readiness(_ev("s1", recognized=True)),
        classify_review_readiness(_ev("s2", plan_readable=False)),
        classify_review_readiness(_ev("s3", keep_blocked=True)),
        classify_review_readiness(_ev("s4", span=None)),
        classify_review_readiness(_ev("s5", span=SpanSourceEvidence(
            bore_span_source_files=("BORE_LOG",), plan_span_layer_inspected=True,
            source_confirmed_span_count=0))),
        classify_review_readiness(_ev("s6", span=_confirmed_span())),
        classify_review_readiness(_ev("s7", span=_confirmed_span(),
            anchor=AnchorEvidence(start_status=AMBIGUOUS_ANCHOR, end_status=AMBIGUOUS_ANCHOR))),
        classify_review_readiness(_ev("s8", span=_confirmed_span(),
            anchor=AnchorEvidence(start_status=ANCHOR_RESOLVED_TO_SYMBOL, end_status=ANCHOR_RESOLVED_TO_SYMBOL),
            route=RouteEvidence(status=NO_MAIN_ROUTE))),
        classify_review_readiness(_ev("s9", span=_confirmed_span(),
            anchor=AnchorEvidence(start_status=ANCHOR_RESOLVED_TO_SYMBOL, end_status=ANCHOR_RESOLVED_TO_SYMBOL),
            route=RouteEvidence(status=MAIN_ROUTE_DISCRIMINATED))),
    ]


def test_all_nine_statuses_are_reachable():
    produced = {r.status for r in _every_status_fixture()}
    assert produced == set(ALL_STATUSES), "unreached statuses: %s" % (set(ALL_STATUSES) - produced)


def test_no_report_ever_draws_or_places():
    for r in _every_status_fixture():
        assert r.draws_anything is False
        assert r.performs_placement is False
        assert "no" in r.note.lower() and "placement" in r.note.lower()


def test_non_ready_non_control_statuses_name_a_next_step():
    for r in _every_status_fixture():
        if r.ready or r.is_control:
            assert r.recommended_next_input is None
        else:
            assert r.recommended_next_input, "%s must name a next productive input" % r.status


def test_pass_status_sets_match_the_real_observers():
    """Anti-drift: the classifier's PASS sets must equal the real read-only observer PASS constants, so a
    change to an observer's vocabulary cannot silently desync this traffic controller."""
    assert ANCHOR_PASS_STATUSES == {
        ANCHOR_RESOLVED_TO_SYMBOL, ANCHOR_RESOLVED_TO_LEADER_TIP, ANCHOR_RESOLVED_TO_ROUTE_ENDPOINT}
    assert ROUTE_PASS_STATUSES == {MAIN_ROUTE_DISCRIMINATED, PLAN_VIEW_RUN_CONNECTED}
    # the observers' reject statuses must never count as PASS
    for reject in (AMBIGUOUS_ANCHOR, NO_SUPPORTED_ANCHOR, LABEL_ONLY_NO_ANCHOR):
        assert not anchor_resolved(reject)
    assert not route_verified(NO_MAIN_ROUTE)


def test_report_is_json_serializable():
    r = classify_review_readiness(_ev("pkg-json", span=_confirmed_span()))
    text = format_report(r)
    assert '"status"' in text and '"draws_anything"' in text
