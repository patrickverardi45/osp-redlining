"""Offline tests for the real M8.20 GROUP REVIEW service path."""
from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

from truelinev2.match.shared_alignment import (
    BoreClaim,
    shared_alignment_verdict as real_verdict,
)
from truelinev2.review.group_review import (
    build_group_review_card as real_build_card,
)
from truelinev2.review.group_review_service import (
    GroupReviewService,
    _claim_context,
)

H8 = (("0+00", "1+10", 110.0), ("1+10", "1+76", 66.0))
H32 = (("0+00", "1+30", 130.0), ("1+30", "1+77", 47.0))


def _claim(bore_id, boundary, hops):
    return BoreClaim(
        bore_id=bore_id, survivor_id="NEXTLINK@378,409",
        boundary_raw=boundary, chain_unique=True, join_proven=True,
        chain_hops=hops, walk_points=((0.0, 0.0), (1.0, 0.0)),
        boundary_xy=(1.0, 0.0), conduit_count=2, origin_multiport=True)


class _Plan:
    def close(self):
        pass


class _Dialect:
    def calibrate(self, plan, sheet_offset):
        return sheet_offset


def test_real_service_composes_extractor_law_and_card(monkeypatch):
    import truelinev2.review.group_review_service as service

    calls = []
    bores = {
        "bore_log8": SimpleNamespace(
            bore_id="log8", sheet_refs=[18, 22], station_start_ft=0.0),
        "bore_log32": SimpleNamespace(
            bore_id="log32", sheet_refs=[18, 22], station_start_ft=0.0),
        "bore_log42": SimpleNamespace(
            bore_id="log42", sheet_refs=[1, 2], station_start_ft=0.0),
    }
    claims = [_claim("log8", "1+76", H8), _claim("log32", "1+77", H32)]

    monkeypatch.setattr(service, "PlanPdf", lambda _: _Plan())
    monkeypatch.setattr(service, "select_dialect", lambda _: _Dialect())
    monkeypatch.setattr(service, "_build_plan_frame_graph", lambda *_: object())
    monkeypatch.setattr(
        service, "load_borelog",
        lambda path: bores[Path(path).stem])

    def extract(*_):
        calls.append("extract_group_claims")
        return claims

    def resolve(_plan, bore, *_args, **_kwargs):
        return SimpleNamespace(
            status="STRUCTURE_IDENTITY_BINDING_REQUIRED",
            detail={"far_sheet": 18 if bore.bore_id != "log42" else 2})

    def universe(*_):
        calls.append("origin_chain_boundaries")
        return frozenset({"1+76", "1+77"})

    def verdict(*args, **kwargs):
        calls.append("shared_alignment_verdict")
        return real_verdict(*args, **kwargs)

    def build(*args, **kwargs):
        calls.append("build_group_review_card")
        return real_build_card(*args, **kwargs)

    monkeypatch.setattr(service, "extract_group_claims", extract)
    monkeypatch.setattr(service, "resolve_bore", resolve)
    monkeypatch.setattr(service, "origin_chain_boundaries", universe)
    monkeypatch.setattr(service, "shared_alignment_verdict", verdict)
    monkeypatch.setattr(service, "build_group_review_card", build)

    output = GroupReviewService(
        corpus_dir="X:/corpus", plan_pdf_path="X:/plan.pdf",
        bore_log_paths=[Path(f"{name}.xlsx") for name in bores],
        lane_dialect=_Dialect()).generate()

    assert calls == [
        "extract_group_claims", "origin_chain_boundaries",
        "shared_alignment_verdict", "build_group_review_card"]
    assert len(output) == 1
    card = output[0]
    assert card.schema_version == "truelinev2-shared-alignment-group-review-1"
    assert sorted(m.bore_id for m in card.members) == ["log32", "log8"]
    assert card.shared_origin == "NEXTLINK@378,409"
    assert sorted(card.boundaries) == ["1+76", "1+77"]
    assert card.review_only is True and card.auto is False
    assert card.has_geometry is False and card.has_strokes is False
    assert "log42" not in {m.bore_id for m in card.members}


def test_claim_context_requires_one_far_and_one_end_sheet():
    bore = SimpleNamespace(sheet_refs=[18, 22], station_start_ft=0.0)
    out = SimpleNamespace(detail={"far_sheet": 18})
    assert _claim_context(bore, out) == (18, 22, "0+00")
    assert _claim_context(bore, SimpleNamespace(detail={})) is None
    assert _claim_context(
        SimpleNamespace(sheet_refs=[18, 22, 23], station_start_ft=0.0),
        out) is None


def test_group_service_imports_no_proof_or_rendering_and_per_bore_is_untouched():
    import truelinev2.review.group_review_service as service
    from truelinev2.review.reviewer_service import ReviewerBundleService

    src = inspect.getsource(service)
    assert "truelinev2.proof" not in src and ".proof." not in src
    assert "truelinev2.render" not in src
    assert "render_redline" not in src
    assert "KMZ" not in src and "kmz" not in src

    per_bore = inspect.getsource(ReviewerBundleService.generate)
    assert "group_review" not in per_bore
    assert "GroupReviewService" not in per_bore
