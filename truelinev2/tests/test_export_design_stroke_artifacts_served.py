"""Offline contract tests for the Slice 2b served design-stroke export + copy."""
from __future__ import annotations

import copy

import pytest

from truelinev2.api.reviewer_routes import reviewer_asset_url
from truelinev2.match.symbol_conduit_lane import LANE_NAME, S_ELIGIBLE
from truelinev2.proof.export_design_stroke_artifacts_served import (
    ARTIFACT_SUBDIR,
    EXPORT_SCHEMA_VERSION,
    WEB_PUBLIC_ENV,
    build_served_export,
    copy_artifacts,
    resolve_web_public_dir,
    served_url,
    validate_served_export,
)
from truelinev2.review.design_stroke_cards import GRADE_ACCEPTED, GRADE_UNGRADED

SHA = "667ccb78dd2bd80b5f97910b44a7e124898ff110"


def _base() -> dict:
    """A valid Slice 2a refs-only manifest (served=false), as build_export emits."""
    return {
        "export_schema_version": EXPORT_SCHEMA_VERSION,
        "source": {
            "engine": "truelinev2",
            "source_git_head": SHA,
            "card_contract": "truelinev2-design-stroke-card-1",
            "lane": LANE_NAME,
            "served": False,
        },
        "artifacts": [
            {
                "source_bore_id": "log65",
                "lane_status": S_ELIGIBLE,
                "design_grade": GRADE_ACCEPTED,
                "sheets": [10, 9],
                "artifact_refs": [
                    "log65_lane_s10_redline_stroke.png",
                    "log65_lane_s9_redline_stroke.png",
                ],
            }
        ],
    }


def test_served_export_flips_flag_and_adds_one_url_per_ref():
    served = build_served_export(_base())

    assert served["source"]["served"] is True
    row = served["artifacts"][0]
    # Reviewer-truth fields carried verbatim.
    assert row["artifact_refs"] == [
        "log65_lane_s10_redline_stroke.png",
        "log65_lane_s9_redline_stroke.png",
    ]
    assert row["sheets"] == [10, 9]
    # One site-absolute, SHA-namespaced URL per ref, in order.
    assert row["artifact_urls"] == [
        f"/{ARTIFACT_SUBDIR}/{SHA}/log65_lane_s10_redline_stroke.png",
        f"/{ARTIFACT_SUBDIR}/{SHA}/log65_lane_s9_redline_stroke.png",
    ]
    # No geometry ever crosses.
    assert "segments" not in str(served)
    assert "stroke_points" not in str(served)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda e: e["source"].update({"served": False}), "served=true"),
        (
            lambda e: e["artifacts"][0]["artifact_refs"].__setitem__(0, "../x.png"),
            "bare filename",
        ),
        (
            lambda e: e["artifacts"][0]["artifact_urls"].__setitem__(
                0, "https://evil.test/x.png"
            ),
            "served url",
        ),
        (
            lambda e: e["artifacts"][0]["artifact_urls"].__setitem__(
                0, f"/{ARTIFACT_SUBDIR}/{SHA}/log65_lane_s9_redline_stroke.png"
            ),
            "match source sha",  # url points at the wrong ref
        ),
        (
            lambda e: e["artifacts"][0]["artifact_urls"].__setitem__(
                0,
                "/engine-artifacts/0000000000000000000000000000000000000000/"
                "log65_lane_s10_redline_stroke.png",
            ),
            "match source sha",  # url sha != source sha
        ),
        (lambda e: e["artifacts"][0].pop("artifact_urls"), "artifact fields drift"),
        (
            lambda e: e["artifacts"][0]["artifact_urls"].append("extra"),
            "one served url per artifact ref",
        ),
        (
            lambda e: e["artifacts"][0].update(
                {"stroke_points": [[1, 2], [3, 4]]}
            ),
            "artifact fields drift",
        ),
    ],
)
def test_served_validator_rejects_unsafe_manifests(mutate, message):
    served = build_served_export(_base())
    mutate(served)
    with pytest.raises(ValueError, match=message):
        validate_served_export(served)


def test_served_validator_rejects_binary_and_non_pass():
    served = build_served_export(_base())

    binary = copy.deepcopy(served)
    binary["artifacts"][0]["artifact_refs"][0] = b"\x89PNG"
    with pytest.raises(ValueError, match="bare filename"):
        validate_served_export(binary)

    ungraded = copy.deepcopy(served)
    ungraded["artifacts"][0]["design_grade"] = GRADE_UNGRADED
    with pytest.raises(ValueError, match="only graded-PASS"):
        validate_served_export(ungraded)


def _seed_sweep(tmp_path, names, *, content=b"\x89PNG\r\n\x1a\n"):
    sweep = tmp_path / "sweep"
    sweep.mkdir()
    for name in names:
        (sweep / name).write_bytes(content)
    return sweep


def test_copy_copies_only_manifest_refs_not_strays(tmp_path):
    served = build_served_export(_base())
    sweep = _seed_sweep(
        tmp_path,
        [
            "log65_lane_s10_redline_stroke.png",
            "log65_lane_s9_redline_stroke.png",
            "log99_lane_s1_redline_stroke.png",  # eligible-but-ungraded stray
        ],
    )
    public = tmp_path / "public"
    public.mkdir()

    copied = copy_artifacts(served, sweep, public)

    dest = public / ARTIFACT_SUBDIR / SHA
    on_disk = sorted(p.name for p in dest.glob("*.png"))
    assert copied == [
        "log65_lane_s10_redline_stroke.png",
        "log65_lane_s9_redline_stroke.png",
    ]
    assert on_disk == copied  # the stray was NOT copied
    assert not (dest / "log99_lane_s1_redline_stroke.png").exists()


def test_copy_clears_stale_pngs_in_sha_leaf(tmp_path):
    served = build_served_export(_base())
    sweep = _seed_sweep(
        tmp_path,
        ["log65_lane_s10_redline_stroke.png", "log65_lane_s9_redline_stroke.png"],
    )
    public = tmp_path / "public"
    dest = public / ARTIFACT_SUBDIR / SHA
    dest.mkdir(parents=True)
    (dest / "stale_lane_s1_redline_stroke.png").write_bytes(b"old")

    copy_artifacts(served, sweep, public)

    assert not (dest / "stale_lane_s1_redline_stroke.png").exists()
    assert sorted(p.name for p in dest.glob("*.png")) == [
        "log65_lane_s10_redline_stroke.png",
        "log65_lane_s9_redline_stroke.png",
    ]


def test_copy_fails_closed_when_source_png_missing(tmp_path):
    served = build_served_export(_base())
    sweep = _seed_sweep(tmp_path, ["log65_lane_s10_redline_stroke.png"])  # s9 absent
    public = tmp_path / "public"
    public.mkdir()
    with pytest.raises(FileNotFoundError, match="missing/empty"):
        copy_artifacts(served, sweep, public)


def test_copy_fails_closed_on_empty_source_png(tmp_path):
    served = build_served_export(_base())
    sweep = _seed_sweep(
        tmp_path,
        ["log65_lane_s10_redline_stroke.png", "log65_lane_s9_redline_stroke.png"],
        content=b"",
    )
    public = tmp_path / "public"
    public.mkdir()
    with pytest.raises(FileNotFoundError, match="missing/empty"):
        copy_artifacts(served, sweep, public)


def test_copy_refuses_non_bare_ref_smuggled_past_validation(tmp_path):
    # Defense in depth: even if a traversal ref reached copy_artifacts directly,
    # it must never be joined into a path.
    served = build_served_export(_base())
    served["artifacts"][0]["artifact_refs"][0] = "../escape.png"
    sweep = _seed_sweep(tmp_path, ["log65_lane_s9_redline_stroke.png"])
    public = tmp_path / "public"
    public.mkdir()
    with pytest.raises(ValueError, match="non-bare filename"):
        copy_artifacts(served, sweep, public)


def test_resolve_web_public_dir_requires_existing_public(tmp_path, monkeypatch):
    not_public = tmp_path / "static"
    not_public.mkdir()
    monkeypatch.setenv(WEB_PUBLIC_ENV, str(not_public))
    with pytest.raises(ValueError, match="must point at a web 'public' dir"):
        resolve_web_public_dir()

    monkeypatch.setenv(WEB_PUBLIC_ENV, str(tmp_path / "public"))  # absent
    with pytest.raises(FileNotFoundError, match="web public dir not found"):
        resolve_web_public_dir()

    real = tmp_path / "public"
    real.mkdir()
    monkeypatch.setenv(WEB_PUBLIC_ENV, str(real))
    assert resolve_web_public_dir() == real


def test_served_url_shape():
    assert served_url(SHA, "log65_lane_s9_redline_stroke.png") == (
        f"/{ARTIFACT_SUBDIR}/{SHA}/log65_lane_s9_redline_stroke.png"
    )


def test_static_and_live_manifest_url_policies_require_full_source_sha():
    static = build_served_export(_base())
    validate_served_export(static)
    assert static["artifacts"][0]["artifact_urls"][0].startswith(
        f"/{ARTIFACT_SUBDIR}/{SHA}/"
    )

    live = build_served_export(_base(), url_for=reviewer_asset_url)
    validate_served_export(live, url_for=reviewer_asset_url)
    assert live["artifacts"][0]["artifact_urls"][0] == (
        "/v2/reviewer/design-stroke/asset/"
        "log65_lane_s10_redline_stroke.png"
    )

    for manifest, url_for in (
        (static, served_url),
        (live, reviewer_asset_url),
    ):
        manifest["source"]["source_git_head"] = "fcba5a8"
        with pytest.raises(ValueError, match="full Git SHA"):
            validate_served_export(manifest, url_for=url_for)
