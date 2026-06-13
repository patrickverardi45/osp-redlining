"""M9.6 -- offline tests for the default-OFF, read-only RUN-ASSEMBLY API transport.

Pure + posture only -- no PDF, no fixtures. Synthetic valid cards drive the envelope
contract (validate_export / build_export) and a monkeypatched export drives the route
(mount gating, memoization, 503). The LIVE Brenham 3-card facts are gated INSIDE the
proof (run_run_assembly_api_contract, G1-G11).
"""
from __future__ import annotations

import copy
import dataclasses
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from starlette.requests import Request

from truelinev2.api import run_assembly_routes
from truelinev2.api.app import create_app
from truelinev2.config import Settings
from truelinev2.proof.export_run_assembly_cards_json import (
    EXPORT_SCHEMA_VERSION,
    build_export,
    validate_export,
)
from truelinev2.review.run_assembly_review import (
    CONTINUATION_CANDIDATE,
    DROP_BRANCH,
    RunAssemblyReviewCard,
)

SHA = "a" * 40
RA_PATH = "/v2/reviewer/run-assembly"


def _settings(tmp_path: Path, *, enabled: bool) -> Settings:
    return dataclasses.replace(
        Settings.for_proof(),
        artifact_root=tmp_path / "artifacts",
        cards_dir=tmp_path / "cards",
        db_path=tmp_path / "truelinev2.db",
        run_assembly_api_optin=enabled,
    )


def _request(app, path: str = RA_PATH) -> Request:
    return Request({"type": "http", "method": "GET", "path": path,
                    "headers": [], "app": app})


def _cards():
    return [
        RunAssemblyReviewCard(
            end_bore="log10", start_bore="log27", terminal_ap=152,
            splice_loc="SPLICE LOC 35", end_station="7+30", start_station="0+00",
            continuation_class=CONTINUATION_CANDIDATE, departure_run_class="trunk",
            competing_departures=1, detail="candidate"),
        RunAssemblyReviewCard(
            end_bore="log7", start_bore="log65", terminal_ap=163,
            splice_loc="SPLICE LOC 46", end_station="4+51", start_station="0+00",
            continuation_class=DROP_BRANCH, departure_run_class="drop",
            competing_departures=1, detail="drop"),
    ]


def _valid_export() -> dict:
    return build_export(_cards(), SHA)


def _paths(app) -> set[str]:
    return {r.path for r in app.routes if isinstance(r, APIRoute)}


# ---- settings / mount gating ------------------------------------------------

def test_settings_default_off_and_env(monkeypatch):
    monkeypatch.delenv("TL2_RUN_ASSEMBLY_API_OPTIN", raising=False)
    assert Settings.from_env().run_assembly_api_optin is False
    monkeypatch.setenv("TL2_RUN_ASSEMBLY_API_OPTIN", "1")
    assert Settings.from_env().run_assembly_api_optin is True


def test_flag_off_route_is_dormant(tmp_path):
    app = create_app(_settings(tmp_path, enabled=False))
    assert RA_PATH not in _paths(app)


def test_flag_on_mounts_only_get_context_free_route(tmp_path):
    app = create_app(_settings(tmp_path, enabled=True))
    routes = [r for r in app.routes if isinstance(r, APIRoute) and r.path == RA_PATH]
    assert len(routes) == 1
    assert routes[0].methods == {"GET"}
    assert not routes[0].dependant.dependencies


def test_run_assembly_flag_does_not_mount_reviewer_bundle_routes(tmp_path):
    # the two flags are independent: enabling run-assembly does NOT mount the bundle routes.
    app = create_app(_settings(tmp_path, enabled=True))
    assert RA_PATH in _paths(app)
    assert "/v2/reviewer/bundle" not in _paths(app)


# ---- route behavior (monkeypatched export, no PDF) --------------------------

def test_route_consumes_export_and_memoizes(tmp_path, monkeypatch):
    app = create_app(_settings(tmp_path, enabled=True))
    calls = 0

    def gen():
        nonlocal calls
        calls += 1
        return _valid_export()

    monkeypatch.setattr(run_assembly_routes, "generate_run_assembly_export", gen)
    req = _request(app)
    first = run_assembly_routes.get_run_assembly_cards(req)
    second = run_assembly_routes.get_run_assembly_cards(req)
    assert first == _valid_export()
    assert second == first
    assert calls == 1
    assert first["source"]["service"] == "RunAssemblyReviewService"
    assert [c["continuation_class"] for c in first["cards"]] == [
        CONTINUATION_CANDIDATE, DROP_BRANCH]
    assert "segments" not in str(first) and "stroke_points" not in str(first)
    assert "lane_counts" not in str(first)


def test_route_unavailable_is_503(tmp_path, monkeypatch):
    app = create_app(_settings(tmp_path, enabled=True))

    def unavailable():
        raise FileNotFoundError("corpus missing")

    monkeypatch.setattr(run_assembly_routes, "generate_run_assembly_export", unavailable)
    with pytest.raises(HTTPException) as exc:
        run_assembly_routes.get_run_assembly_cards(_request(app))
    assert exc.value.status_code == 503


# ---- envelope contract (build_export / validate_export) ----------------------

def test_build_export_round_trips_and_validates():
    export = _valid_export()
    assert export["export_schema_version"] == EXPORT_SCHEMA_VERSION
    assert export["source"]["card_schema_version"] == "truelinev2-run-assembly-review-1"
    assert len(export["cards"]) == 2
    validate_export(export)  # no raise


@pytest.mark.parametrize(
    "mutate",
    [
        lambda e: e["cards"][0].__setitem__("geometry", [[0, 0]]),         # geometry key
        lambda e: e["cards"][0].__setitem__("auto", True),                 # AUTO card
        lambda e: e.__setitem__("lane_counts", {"PLACED_REVIEW": 30}),     # product bucket (top level)
        lambda e: e["source"].__setitem__("source_git_head", "not-a-sha"), # bad SHA
        lambda e: e.__setitem__("export_schema_version", "other-1"),       # envelope schema drift
        lambda e: e["source"].__setitem__("extra", "x"),                   # source field drift
        lambda e: e["source"].__setitem__("service", "SomethingElse"),     # service drift
        lambda e: [c.__setitem__("departure_run_class", "trunk")           # DROP without drop
                   for c in e["cards"] if c["continuation_class"] == DROP_BRANCH],
        lambda e: e["cards"][0].__setitem__("terminal_ap", {"overlay.png": 1}),  # png as a dict KEY
        lambda e: e["cards"][0].__setitem__("detail", "see overlay.png"),   # png as a string VALUE
    ],
)
def test_validate_export_is_fail_closed(mutate):
    export = copy.deepcopy(_valid_export())
    mutate(export)
    with pytest.raises(ValueError):
        validate_export(export)


def test_route_poisoned_cache_is_503(tmp_path, monkeypatch):
    # a corrupted already-cached envelope must map to 503 (not a raw 500): the per-call
    # re-validation is inside the service-unavailable handler.
    app = create_app(_settings(tmp_path, enabled=True))
    monkeypatch.setattr(run_assembly_routes, "generate_run_assembly_export", _valid_export)
    req = _request(app)
    run_assembly_routes.get_run_assembly_cards(req)            # populate the cache
    poisoned = copy.deepcopy(_valid_export())
    poisoned["cards"][0]["geometry"] = [[0, 0]]               # corrupt the cached envelope
    setattr(app.state, run_assembly_routes._CACHE, poisoned)
    with pytest.raises(HTTPException) as exc:
        run_assembly_routes.get_run_assembly_cards(req)
    assert exc.value.status_code == 503


# ---- read-only / posture ----------------------------------------------------

def test_route_and_export_have_no_placement_or_render():
    import inspect

    from truelinev2.proof import export_run_assembly_cards_json as exp
    route_src = inspect.getsource(run_assembly_routes)
    exp_src = inspect.getsource(exp)
    for src in (route_src, exp_src):
        assert "truelinev2.render" not in src and "render_redline" not in src
        assert "resolve_bore" not in src and "run_match" not in src
        assert "_build_plan_frame_graph" not in src and "cross_sheet" not in src
    # the export consumes the SERVICE, it does not reimplement run-assembly logic
    assert "RunAssemblyReviewService" in exp_src
    assert "extract_run_assembly" not in exp_src
