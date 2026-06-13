"""M9.4.2 -- RUN-ASSEMBLY review service tests (offline; composition + posture).

Pin the SHIPPED RunAssemblyReviewService on a SYNTHETIC junction (monkeypatched I/O):
it composes attribute_bore -> extract_run_assembly -> build_run_assembly_cards for
REAL (only PlanPdf / select_dialect / load_borelog / TA.attribute_bore are faked), and
the per-bore bundle is never touched. The LIVE Brenham reproduction (the 3 cards,
log65 drop, byte-identical per-bore bundle, banked lanes) is gated INSIDE the proof
(run_run_assembly_review_service_proof, G1-G10).
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path
from types import SimpleNamespace

from truelinev2.extract.terminus_profile import TerminusProfile
from truelinev2.match import terminus_attribution as TA
from truelinev2.review import run_assembly_review as RV
from truelinev2.review import run_assembly_review_service as service
from truelinev2.review.run_assembly_review_service import RunAssemblyReviewService

PKG = Path(service.__file__).resolve().parents[1]
BOUND = "KMZ_TERMINAL_JOIN_BOUND"

# a non-Brenham profile with an injected drop marker ("LATERAL TAP").
SYN = TerminusProfile(
    station_line_re=r"^STA\s+(\d{1,3}\+\d{2})\b",
    run_callout_marker="TO STA", equation_marker="=", note_window=4,
    note_keywords=("WIDGET TERMINUS",),
    class_keywords=(("widget_terminus", ("WIDGET TERMINUS",)),),
    terminal_class="widget_terminus",
    ap_token=r"NODE\s*-?\s*(\d+)", splice_token=r"PORT\s*LOC\s*\d+",
    pair_re=r"NODE-?\s?(\d+)\s+PORT\s*LOC\s*(\d+)",
    drop_markers=("LATERAL TAP",),
)


def _ep(side, result, ap=None, splice=None, kmz_join=None, station=None):
    return TA.EndpointAttribution(side=side, station=station,
                                  result=result, ap=ap, splice=splice,
                                  kmz_join=kmz_join, note_line=f"note-{side}")


def _bore_result(bid, *, start_station, end_station, end_result=TA.NO_ENDPOINT_NOTE,
                 end_ap=None, end_splice=None, end_join=None,
                 start_result=TA.NO_ENDPOINT_NOTE, start_ap=None, start_splice=None):
    return TA.BoreTerminusResult(
        bore_id=bid, start_station=start_station, end_station=end_station,
        start=_ep("START", start_result, start_ap, start_splice, station=start_station),
        end=_ep("END", end_result, end_ap, end_splice, end_join, station=end_station),
        sheet_neighbors=())


class _FakeDialect:
    def calibrate(self, plan, sheet_offset):
        return sheet_offset


def _make_fake_plan(lines_by_sheet):
    class _FakePlan:
        def __init__(self, _path):
            pass

        def lines(self, sheet, _offset):
            return lines_by_sheet.get(sheet, [])

        def close(self):
            pass
    return _FakePlan


def test_service_composes_pipeline_and_surfaces_drop_card(monkeypatch):
    # ender owns terminal AP-9 at its END (KMZ-BOUND, sheet 1); starter departs it as a
    # drop (sheet 2 prints the injected LATERAL TAP run callout at the shared node 4+51).
    bores = {
        "ender": SimpleNamespace(bore_id="ender", sheet_refs=[1],
                                 station_start_ft=0.0, station_end_ft=451.0),
        "starter": SimpleNamespace(bore_id="starter", sheet_refs=[2],
                                   station_start_ft=451.0, station_end_ft=999.0),
    }
    results = {
        "ender": _bore_result("ender", start_station="0+00", end_station="4+51",
                              end_result=TA.ENDPOINT_ATTRIBUTED, end_ap=9,
                              end_splice="PORT LOC 3", end_join=BOUND),
        "starter": _bore_result("starter", start_station="4+51", end_station="9+99",
                                start_result=TA.JUNCTION_ORIGIN, start_ap=9,
                                start_splice="PORT LOC 3"),
    }
    lines_by_sheet = {2: ["STA 4+51 TO STA 6+00 RUN LATERAL TAP"]}   # drop at the node

    monkeypatch.setattr(service, "PlanPdf", _make_fake_plan(lines_by_sheet))
    monkeypatch.setattr(service, "select_dialect", lambda _p: _FakeDialect())
    monkeypatch.setattr(service, "load_borelog",
                        lambda path: bores[Path(path).stem])
    monkeypatch.setattr(service, "feet_to_station",
                        lambda ft: "4+51" if ft in (451.0,) else "0+00")
    monkeypatch.setattr(service.TA, "attribute_bore",
                        lambda bid, *a, **k: results[bid])

    cards = RunAssemblyReviewService(
        corpus_dir="X:/corpus", plan_pdf_path="X:/plan.pdf",
        bore_log_paths=[Path("ender.xlsx"), Path("starter.xlsx")],
        kmz_model=SimpleNamespace(structures=()), terminus_profile=SYN).generate()

    assert len(cards) == 1
    card = cards[0]
    assert (card.end_bore, card.start_bore) == ("ender", "starter")
    assert card.terminal_ap == 9
    assert card.continuation_class == RV.DROP_BRANCH         # printed LATERAL TAP -> drop
    assert card.departure_run_class == "drop"
    assert card.competing_departures == 1                    # frame-scoped guard preserved
    assert card.review_only is True and card.auto is False
    assert card.has_geometry is False and card.has_strokes is False
    assert card.label == "SUGGESTION_NOT_PLACEMENT"
    assert card.schema_version == RV.RUN_ASSEMBLY_SCHEMA_VERSION


def test_service_emits_candidate_when_departure_non_drop(monkeypatch):
    # same junction but the node prints no drop marker -> a continuation candidate.
    bores = {
        "ender": SimpleNamespace(bore_id="ender", sheet_refs=[1],
                                 station_start_ft=0.0, station_end_ft=451.0),
        "starter": SimpleNamespace(bore_id="starter", sheet_refs=[2],
                                   station_start_ft=451.0, station_end_ft=999.0),
    }
    results = {
        "ender": _bore_result("ender", start_station="0+00", end_station="4+51",
                              end_result=TA.ENDPOINT_ATTRIBUTED, end_ap=9,
                              end_splice="PORT LOC 3", end_join=BOUND),
        "starter": _bore_result("starter", start_station="4+51", end_station="9+99",
                                start_result=TA.JUNCTION_ORIGIN, start_ap=9,
                                start_splice="PORT LOC 3"),
    }
    monkeypatch.setattr(service, "PlanPdf", _make_fake_plan({}))   # no callouts anywhere
    monkeypatch.setattr(service, "select_dialect", lambda _p: _FakeDialect())
    monkeypatch.setattr(service, "load_borelog", lambda path: bores[Path(path).stem])
    monkeypatch.setattr(service, "feet_to_station",
                        lambda ft: "4+51" if ft == 451.0 else "0+00")
    monkeypatch.setattr(service.TA, "attribute_bore", lambda bid, *a, **k: results[bid])

    cards = RunAssemblyReviewService(
        corpus_dir="X:/corpus", plan_pdf_path="X:/plan.pdf",
        bore_log_paths=[Path("ender.xlsx"), Path("starter.xlsx")],
        kmz_model=SimpleNamespace(structures=()), terminus_profile=SYN).generate()
    assert len(cards) == 1
    assert cards[0].continuation_class == RV.CONTINUATION_CANDIDATE
    assert cards[0].departure_run_class == "unknown"


def test_blocker_junction_yields_no_card(monkeypatch):
    # a junction whose END is not KMZ-corroborated is a blocker -> the service emits NO card.
    bores = {"ender": SimpleNamespace(bore_id="ender", sheet_refs=[1],
                                      station_start_ft=0.0, station_end_ft=451.0),
             "starter": SimpleNamespace(bore_id="starter", sheet_refs=[2],
                                        station_start_ft=451.0, station_end_ft=999.0)}
    results = {
        "ender": _bore_result("ender", start_station="0+00", end_station="4+51",
                              end_result=TA.ENDPOINT_ATTRIBUTED, end_ap=9,
                              end_splice="PORT LOC 3", end_join="KMZ_TERMINAL_JOIN_NONE"),
        "starter": _bore_result("starter", start_station="4+51", end_station="9+99",
                                start_result=TA.JUNCTION_ORIGIN, start_ap=9,
                                start_splice="PORT LOC 3"),
    }
    monkeypatch.setattr(service, "PlanPdf", _make_fake_plan({}))
    monkeypatch.setattr(service, "select_dialect", lambda _p: _FakeDialect())
    monkeypatch.setattr(service, "load_borelog", lambda path: bores[Path(path).stem])
    monkeypatch.setattr(service, "feet_to_station",
                        lambda ft: "4+51" if ft == 451.0 else "0+00")
    monkeypatch.setattr(service.TA, "attribute_bore", lambda bid, *a, **k: results[bid])

    cards = RunAssemblyReviewService(
        corpus_dir="X:/corpus", plan_pdf_path="X:/plan.pdf",
        bore_log_paths=[Path("ender.xlsx"), Path("starter.xlsx")],
        kmz_model=SimpleNamespace(structures=()), terminus_profile=SYN).generate()
    assert cards == []


def test_unparseable_bore_is_ignored(monkeypatch):
    def _load(path):
        if Path(path).stem == "bad":
            raise ValueError("unparseable bore source")
        return SimpleNamespace(bore_id="ender", sheet_refs=[1],
                               station_start_ft=0.0, station_end_ft=451.0)
    monkeypatch.setattr(service, "PlanPdf", _make_fake_plan({}))
    monkeypatch.setattr(service, "select_dialect", lambda _p: _FakeDialect())
    monkeypatch.setattr(service, "load_borelog", _load)
    monkeypatch.setattr(service, "feet_to_station", lambda ft: "0+00")
    monkeypatch.setattr(service.TA, "attribute_bore",
                        lambda bid, *a, **k: _bore_result(bid, start_station="0+00",
                                                          end_station="4+51"))
    cards = RunAssemblyReviewService(
        corpus_dir="X:/corpus", plan_pdf_path="X:/plan.pdf",
        bore_log_paths=[Path("bad.xlsx"), Path("ender.xlsx")],
        kmz_model=SimpleNamespace(structures=()), terminus_profile=SYN).generate()
    assert cards == []                # the one good bore forms no junction alone; no crash


# ---- posture: additive, unwired, literal-free, no placement path ------------

def test_service_imports_no_proof_or_render_and_per_bore_untouched():
    from truelinev2.review.reviewer_service import ReviewerBundleService
    src = inspect.getsource(service)
    assert "truelinev2.proof" not in src and ".proof." not in src
    assert "truelinev2.render" not in src and "render_redline" not in src
    per_bore = inspect.getsource(ReviewerBundleService.generate)
    assert "run_assembly" not in per_bore
    assert "RunAssemblyReviewService" not in per_bore


def test_service_does_not_call_placement_path():
    # scan the CLASS body (not the module docstring, which honestly names what is avoided).
    src = inspect.getsource(RunAssemblyReviewService)
    assert "resolve_bore" not in src and "run_match" not in src and "sweep" not in src
    # no cross-sheet / M9.2 frame-graph widen (the named M9.4.1 limitation is preserved):
    # the frame-graph builder the M8.20/M9.2 path uses is never imported or called here.
    assert "_build_plan_frame_graph" not in src and "matchline" not in src \
        and "cross_sheet" not in src


def test_service_holds_no_convention_literal():
    src = inspect.getsource(service)
    assert not re.search(r"(?i)\b(brenham|odot|tulsa|creek|nextlink|verofy)\b", src)
    for vocab in ("FOR FIBER DROP", "terminal_port_hh", "SPLICE LOC", "log44"):
        assert vocab not in src, vocab


def test_service_unwired_from_placement_path():
    for rel in ("match/engine.py", "match/symbol_conduit_lane.py",
                "review/reviewer_service.py", "service.py"):
        text = (PKG / rel).read_text(encoding="utf-8")
        assert "run_assembly_review_service" not in text, rel
        assert "RunAssemblyReviewService" not in text, rel
