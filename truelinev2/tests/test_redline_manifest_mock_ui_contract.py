"""Phase-1 redline-manifest MOCK UI contract test (no browser, no engine).

SUPERSEDED / HISTORICAL FIXTURE ONLY. The mock UI under truelinev2/contracts/mock_ui/ is retired as a
product direction (lane TRUELINE_V2_UI_FABLE_PRESERVE_AND_MOCK_UI_RETIRE, 2026-06-19); the authoritative
v2 UI base is the preserved Fable repo trueline-web-experience (see wiki/ui/fable_v2_ui_bones.md and
truelinev2/contracts/mock_ui/_DEPRECATED.md). This test is kept ONLY as a historical contract fixture:
its value now is cross-checking the example manifest's truth (log3/log14/blocked/warnings/placeholders),
not endorsing the mock as the UI. Do not extend the mock UI to satisfy new product needs.

Verifies the static mock UI under truelinev2/contracts/mock_ui/ is manifest-driven
and honors the contract: it references the example manifest, excludes forbidden/stale
sources, carries the required contract-only labels, implements the filter/status
controls, and surfaces the special cases (log3 owner-confirmed, log14 covered-by-log10,
blocked unlock requirements, advisory warnings). The UI's special-case logic is
cross-checked against the ACTUAL example manifest values, so this test fails if either
the UI or the manifest drifts. Pure stdlib; imports no truelinev2 module.
"""
from __future__ import annotations

import json
from pathlib import Path

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"
MOCK_DIR = CONTRACTS / "mock_ui"
HTML = MOCK_DIR / "redline_manifest_mock.html"
CSS = MOCK_DIR / "redline_manifest_mock.css"
JS = MOCK_DIR / "redline_manifest_mock.js"
EXAMPLE = CONTRACTS / "examples" / "brenham_50_of_58_redline_manifest.example.json"

HTML_T = HTML.read_text(encoding="utf-8")
CSS_T = CSS.read_text(encoding="utf-8")
JS_T = JS.read_text(encoding="utf-8")
UI_FILES = {"html": HTML_T, "css": CSS_T, "js": JS_T}
UI_ALL = HTML_T + "\n" + CSS_T + "\n" + JS_T

MANIFEST = json.loads(EXAMPLE.read_text(encoding="utf-8"))
LOGS = {lg["log_id"]: lg for lg in MANIFEST["logs"]}

FORBIDDEN = [
    "parent_source_model",
    "placement_status",
    "data/outputs/callout_route_assembly_sweep",
]
REQUIRED_LABELS = [
    "Contract mock only",
    "No live engine wiring",
    "Example manifest",
    "Artifact paths are placeholders unless checksum is present",
]
FILTER_KEYS = ["all", "drawn", "covered", "blocked", "warnings"]
STATUS_ENUM = [
    "DRAWN_REDLINE",
    "COVERED_BY_EXISTING_REDLINE",
    "OWNER_LOCKED_ABSTAIN",
    "SOURCE_GAP_BLOCKED",
    "MISSING_SOURCE_SHEET_BLOCKED",
]


# --------------------------------------------------------------------------- #
# Presence + data source
# --------------------------------------------------------------------------- #
def test_mock_ui_files_present():
    for p in (HTML, CSS, JS):
        assert p.is_file(), p
    assert HTML_T.strip() and CSS_T.strip() and JS_T.strip()


def test_mock_references_the_example_manifest_path():
    # The UI intentionally fetches the committed example manifest (single source).
    assert "brenham_50_of_58_redline_manifest.example.json" in JS_T
    resolved = (MOCK_DIR / "../examples/brenham_50_of_58_redline_manifest.example.json").resolve()
    assert resolved == EXAMPLE.resolve()
    assert EXAMPLE.is_file()


# --------------------------------------------------------------------------- #
# Forbidden / stale sources excluded from the authored UI files
# --------------------------------------------------------------------------- #
def test_mock_excludes_forbidden_sources():
    for name, text in UI_FILES.items():
        low = text.lower()
        for token in FORBIDDEN:
            assert token not in low, "%s leaks forbidden source %r" % (name, token)


def test_mock_does_not_infer_status_from_png_filenames():
    # No status should be derived from a ".png" string match; the UI reads
    # log.status / log.drawn / etc. The only .png references are artifact PATHS,
    # which come from the manifest at runtime (not hardcoded in the UI).
    assert ".png" not in JS_T
    assert ".png" not in HTML_T


# --------------------------------------------------------------------------- #
# Required contract labels
# --------------------------------------------------------------------------- #
def test_required_contract_labels_present():
    for label in REQUIRED_LABELS:
        assert label in UI_ALL, "missing required label: %r" % label


# --------------------------------------------------------------------------- #
# Filters + status handling
# --------------------------------------------------------------------------- #
def test_filter_controls_present():
    for key in FILTER_KEYS:
        assert ('data-filter="%s"' % key) in HTML_T, "missing filter button: %s" % key
        assert ('"%s"' % key) in JS_T, "JS does not handle filter: %s" % key
    # The matcher implements drawn/covered/blocked/warnings predicates.
    for token in ("log.drawn", "log.covered", "log.blocked", "log.warnings"):
        assert token in JS_T, token


def test_status_summary_handling():
    for status in STATUS_ENUM:
        assert status in JS_T, "UI missing status handling: %s" % status
    # Counts come from the manifest's status_counts, not recomputed from disk.
    assert "status_counts" in JS_T
    for field in ("drawn_count", "covered_count", "blocked_count", "frontier"):
        assert field in JS_T, field


def test_header_is_manifest_driven():
    for field in ("project_name", "render_commit", "schema_version", "summary"):
        assert field in JS_T, field


# --------------------------------------------------------------------------- #
# Special-case surfacing (UI logic cross-checked against real manifest values)
# --------------------------------------------------------------------------- #
def test_surfaces_log3_owner_confirmed_not_auto():
    # UI logic: special handling for the owner-confirmed-geometry provenance.
    assert "OWNER_CONFIRMED_HUMAN_ADJUSTABLE" in JS_T
    assert "not deterministic auto" in JS_T.lower()
    # Manifest truth this is meant to surface: exactly log3 carries that provenance.
    geom = [k for k, lg in LOGS.items() if lg["provenance"] == "OWNER_CONFIRMED_HUMAN_ADJUSTABLE"]
    assert geom == ["log3"]
    assert LOGS["log3"]["provenance"] != "DETERMINISTIC_AUTO"


def test_surfaces_log14_covered_by_log10_no_duplicate():
    # UI logic: render coverage.covered_by and call out "no duplicate artifact".
    assert "covered_by" in JS_T
    assert "Covered by" in JS_T
    assert "duplicate artifact" in JS_T.lower()
    # Manifest truth: log14 is covered by log10 with no artifact.
    assert LOGS["log14"]["coverage"]["covered_by"] == "log10"
    assert LOGS["log14"]["artifacts"] == []


def test_surfaces_blocker_unlock_requirements():
    # UI logic: render blocker.unlock_requirement as an action item.
    assert "unlock_requirement" in JS_T
    assert "action needed" in JS_T.lower()
    # Manifest truth: every blocked log carries a non-empty unlock requirement.
    blocked = [lg for lg in LOGS.values() if lg["blocked"]]
    assert len(blocked) == 7
    for lg in blocked:
        assert lg["blocker"] and lg["blocker"]["unlock_requirement"].strip(), lg["log_id"]


def test_surfaces_warnings_as_advisory_not_truth():
    # UI logic: render warnings, labeled advisory / not placement truth.
    assert "warnings" in JS_T
    assert "advisory" in JS_T.lower()
    assert "not placement truth" in JS_T.lower()
    # Manifest truth: the stored-anchor-debt logs carry warnings to surface.
    for k in ("log48", "log70"):
        assert LOGS[k]["warnings"], k


def test_artifacts_placeholder_vs_checksum_handling():
    # UI distinguishes placeholder artifacts (no checksum) from published ones.
    assert "checksum" in JS_T.lower()
    assert "a.sha256" in JS_T  # decision is driven by the manifest field
    # Manifest truth: this mock's artifacts are placeholders (sha256 null).
    for lg in LOGS.values():
        for art in lg["artifacts"]:
            assert art["sha256"] is None and art["example_placeholder"] is True
