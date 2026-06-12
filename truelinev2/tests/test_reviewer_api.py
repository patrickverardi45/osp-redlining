"""Offline tests for the default-OFF, read-only reviewer API handoff."""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from starlette.requests import Request

from truelinev2.api import reviewer_routes
from truelinev2.api.app import create_app
from truelinev2.config import Settings
from truelinev2.proof.export_design_stroke_artifacts_served import (
    build_served_export,
)

SHA = "fcba5a8ad4f0a8710df4eae2e350d3c5fd5e4941"
ASSET = "log65_lane_s9_redline_stroke.png"


def _settings(tmp_path: Path, *, enabled: bool) -> Settings:
    return dataclasses.replace(
        Settings.for_proof(),
        artifact_root=tmp_path / "artifacts",
        cards_dir=tmp_path / "cards",
        db_path=tmp_path / "truelinev2.db",
        reviewer_api_optin=enabled,
        design_stroke_dir=tmp_path / "strokes",
    )


def _request(app, path: str = "/v2/reviewer/bundle") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
            "app": app,
        }
    )


def _bundle_export() -> dict:
    return {
        "export_schema_version": "truelinev2-web-reviewer-bundle-export-1",
        "source": {
            "engine": "truelinev2",
            "source_git_head": SHA,
            "service": "ReviewerBundleService",
            "run_mode": "default_baseline",
            "bundle_schema_version": "truelinev2-reviewer-bundle-1",
            "payload_schema_version": "truelinev2-reviewer-lanes-1",
        },
        "bundle": {
            "bundle_schema_version": "truelinev2-reviewer-bundle-1",
            "payload_schema_version": "truelinev2-reviewer-lanes-1",
            "project_id": "brenham-ph5",
            "run_mode": "default_baseline",
            "flag_state": {},
            "status_counts": {},
            "lane_counts": {},
            "payloads": [],
            "source": {},
        },
        "group_review": {
            "schema_version": "truelinev2-shared-alignment-group-review-1",
            "service": "GroupReviewService",
            "cards": [
                {
                    "schema_version": "truelinev2-shared-alignment-group-review-1",
                    "group_lane": "SHARED_ALIGNMENT_MULTI_DROP_REVIEW",
                    "law": "SHARED_ALIGNMENT_MULTI_DROP",
                    "mode": "REVIEW_ONLY",
                    "review_only": True,
                    "auto": False,
                    "has_geometry": False,
                    "has_strokes": False,
                    "label": "SUGGESTION_NOT_PLACEMENT",
                    "human_action": "CONFIRM_OR_REJECT_MULTI_DROP_GROUPING",
                    "shared_origin": "NEXTLINK@378,409",
                    "boundaries": ["1+76", "1+77"],
                    "members": [
                        {
                            "bore_id": "log8",
                            "boundary_raw": "1+76",
                            "per_bore_status": "STRUCTURE_IDENTITY_BINDING_REQUIRED",
                            "chain_hops": [
                                ["0+00", "1+10", 110.0],
                                ["1+10", "1+76", 66.0],
                            ],
                            "conduit_evidence_count": 2,
                            "origin_multiport": True,
                        },
                        {
                            "bore_id": "log32",
                            "boundary_raw": "1+77",
                            "per_bore_status": "STRUCTURE_IDENTITY_BINDING_REQUIRED",
                            "chain_hops": [
                                ["0+00", "1+30", 130.0],
                                ["1+30", "1+77", 47.0],
                            ],
                            "conduit_evidence_count": 2,
                            "origin_multiport": True,
                        },
                    ],
                    "detail": "two distinct printed runs share one proven origin",
                }
            ],
        },
    }


def _base_manifest() -> dict:
    return {
        "export_schema_version": "truelinev2-web-design-stroke-artifacts-1",
        "source": {
            "engine": "truelinev2",
            "source_git_head": SHA,
            "card_contract": "truelinev2-design-stroke-card-1",
            "lane": "symbol_conduit_matchline",
            "served": False,
        },
        "artifacts": [
            {
                "source_bore_id": "log65",
                "lane_status": "STROKE_ELIGIBLE_REVIEW",
                "design_grade": "PASS_ACCEPTED",
                "sheets": [9],
                "artifact_refs": [ASSET],
            }
        ],
    }


def _paths(app) -> set[str]:
    return {
        route.path
        for route in app.routes
        if isinstance(route, APIRoute)
    }


def test_settings_default_off_and_env_paths(monkeypatch):
    monkeypatch.delenv("TL2_REVIEWER_API_OPTIN", raising=False)
    monkeypatch.delenv("TL2_DESIGN_STROKE_DIR", raising=False)
    default = Settings.from_env()
    assert default.reviewer_api_optin is False
    assert default.design_stroke_dir.name == "symbol_conduit_lane_sweep"

    monkeypatch.setenv("TL2_REVIEWER_API_OPTIN", "1")
    monkeypatch.setenv("TL2_DESIGN_STROKE_DIR", "C:/tmp/strokes")
    enabled = Settings.from_env()
    assert enabled.reviewer_api_optin is True
    assert enabled.design_stroke_dir == Path("C:/tmp/strokes")


def test_flag_off_routes_are_dormant(tmp_path):
    app = create_app(_settings(tmp_path, enabled=False))
    assert not any(path.startswith("/v2/reviewer") for path in _paths(app))


def test_flag_on_mounts_only_get_context_free_routes(tmp_path):
    app = create_app(_settings(tmp_path, enabled=True))
    routes = [
        route
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path.startswith("/v2/reviewer")
    ]
    assert {route.path for route in routes} == {
        "/v2/reviewer/bundle",
        "/v2/reviewer/design-stroke/manifest",
        "/v2/reviewer/design-stroke/asset/{name}",
    }
    assert all(route.methods == {"GET"} for route in routes)
    assert all(not route.dependant.dependencies for route in routes)


def test_bundle_route_validates_and_memoizes(tmp_path, monkeypatch):
    app = create_app(_settings(tmp_path, enabled=True))
    calls = 0

    def generate():
        nonlocal calls
        calls += 1
        return _bundle_export()

    monkeypatch.setattr(reviewer_routes, "generate_reviewer_bundle_export", generate)
    request = _request(app)

    first = reviewer_routes.get_reviewer_bundle(request)
    second = reviewer_routes.get_reviewer_bundle(request)

    assert first == _bundle_export()
    assert second == first
    assert calls == 1
    group = first["group_review"]["cards"][0]
    assert sorted(member["bore_id"] for member in group["members"]) == [
        "log32",
        "log8",
    ]
    assert group["auto"] is False
    assert "log42" not in str(first["group_review"])
    assert "segments" not in str(first)
    assert "stroke_points" not in str(first)


def test_bundle_invalid_mode_is_400(tmp_path):
    app = create_app(_settings(tmp_path, enabled=True))
    with pytest.raises(HTTPException) as exc:
        reviewer_routes.get_reviewer_bundle(_request(app), mode="fullest_safe_review")
    assert exc.value.status_code == 400


def test_bundle_unavailable_is_503(tmp_path, monkeypatch):
    app = create_app(_settings(tmp_path, enabled=True))

    def unavailable():
        raise FileNotFoundError("corpus missing")

    monkeypatch.setattr(
        reviewer_routes, "generate_reviewer_bundle_export", unavailable
    )
    with pytest.raises(HTTPException) as exc:
        reviewer_routes.get_reviewer_bundle(_request(app))
    assert exc.value.status_code == 503


def test_manifest_route_uses_api_relative_urls_and_has_no_geometry(
    tmp_path, monkeypatch
):
    app = create_app(_settings(tmp_path, enabled=True))
    monkeypatch.setattr(
        reviewer_routes, "generate_design_stroke_export", _base_manifest
    )

    manifest = reviewer_routes.get_design_stroke_manifest(
        _request(app, "/v2/reviewer/design-stroke/manifest")
    )

    assert manifest["source"]["served"] is True
    assert manifest["artifacts"][0]["artifact_urls"] == [
        f"/v2/reviewer/design-stroke/asset/{ASSET}"
    ]
    assert "segments" not in str(manifest)
    assert "stroke_points" not in str(manifest)


@pytest.mark.parametrize(
    "name",
    [
        "../escape.png",
        r"..\escape.png",
        r"C:\escape.png",
        "https://example.test/escape.png",
        "log65_lane_s9_redline_stroke.png/extra",
    ],
)
def test_asset_bad_name_and_traversal_rejected(tmp_path, name):
    app = create_app(_settings(tmp_path, enabled=True))
    with pytest.raises(HTTPException) as exc:
        reviewer_routes.get_design_stroke_asset(
            _request(app, "/v2/reviewer/design-stroke/asset/x"), name
        )
    assert exc.value.status_code == 400


def test_asset_not_in_approved_set_rejected(tmp_path, monkeypatch):
    app = create_app(_settings(tmp_path, enabled=True))
    monkeypatch.setattr(
        reviewer_routes, "generate_design_stroke_export", _base_manifest
    )
    with pytest.raises(HTTPException) as exc:
        reviewer_routes.get_design_stroke_asset(
            _request(app, "/v2/reviewer/design-stroke/asset/x"),
            "log99_lane_s1_redline_stroke.png",
        )
    assert exc.value.status_code == 404


def test_missing_approved_asset_is_404(tmp_path, monkeypatch):
    app = create_app(_settings(tmp_path, enabled=True))
    monkeypatch.setattr(
        reviewer_routes, "generate_design_stroke_export", _base_manifest
    )
    with pytest.raises(HTTPException) as exc:
        reviewer_routes.get_design_stroke_asset(
            _request(app, f"/v2/reviewer/design-stroke/asset/{ASSET}"), ASSET
        )
    assert exc.value.status_code == 404


def test_approved_asset_returns_png_file_response(tmp_path, monkeypatch):
    settings = _settings(tmp_path, enabled=True)
    settings.design_stroke_dir.mkdir()
    asset = settings.design_stroke_dir / ASSET
    asset.write_bytes(b"\x89PNG\r\n\x1a\n")
    app = create_app(settings)
    monkeypatch.setattr(
        reviewer_routes, "generate_design_stroke_export", _base_manifest
    )

    response = reviewer_routes.get_design_stroke_asset(
        _request(app, f"/v2/reviewer/design-stroke/asset/{ASSET}"), ASSET
    )

    assert response.media_type == "image/png"
    assert Path(response.path) == asset.resolve()


def test_served_helper_validates_api_relative_url_policy():
    manifest = build_served_export(
        _base_manifest(), url_for=reviewer_routes.reviewer_asset_url
    )
    assert manifest["artifacts"][0]["artifact_urls"][0].startswith(
        "/v2/reviewer/design-stroke/asset/"
    )
