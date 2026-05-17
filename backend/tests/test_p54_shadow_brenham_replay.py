"""Fixture-gated Brenham replay harness for the P5.4 shadow A3 boost.

Loads the real Brenham engineering-plan PDFs, parses topology, then runs
compute_plan_aware_footage_boost against the P0 lockdown's bore-log group
+ rankings fixtures. Emits both JSON and markdown reports describing what
the hypothetical A3 boost would do.

Skips entirely when fixtures are absent. Never mutates runtime truth;
the rebuild pipeline is not invoked.

ARTIFACT OUTPUT
---------------
    backend/tests/output/p54_shadow/brenham_p54_shadow_report.json
    backend/tests/output/p54_shadow/brenham_p54_shadow_report.md

The output/ directory is gitignored (backend/tests/output/ exclusion rule).
The reports describe per-group hypothetical reorders, aggregate stats,
and overall reorder counts — useful for human review before any active
P5.4 boost is enabled.

FIXTURE RESOLUTION
------------------
PDFs:                    $TRUELINE_PLAN_FIXTURE_DIR
                         or C:\\Nova\\knowledge\\TrueLine-Wiki\\raw\\trueline\\engineering-plans\\brenham\\
P0 lockdown fixtures:    backend/tests/fixtures/engineering_plans/brenham/

COMMAND
-------
    python -m pytest backend/tests/test_p54_shadow_brenham_replay.py -v
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

os.environ.setdefault("TRUELINE_JWT_SECRET", "p54-brenham-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "p54-brenham-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

import main  # noqa: E402
from app.services import engineering_plan_parser as pp  # noqa: E402


_PDF_FIXTURE_DEFAULT = Path(
    r"C:\Nova\knowledge\TrueLine-Wiki\raw\trueline\engineering-plans\brenham"
)
_P0_FIXTURE_DIR = (
    _BACKEND_DIR / "tests" / "fixtures" / "engineering_plans" / "brenham"
)
_OUTPUT_DIR = _BACKEND_DIR / "tests" / "output" / "p54_shadow"


def _resolve_pdf_dir() -> Optional[Path]:
    env = os.environ.get("TRUELINE_PLAN_FIXTURE_DIR", "").strip()
    if env:
        p = Path(env)
        if p.is_dir():
            return p
    if _PDF_FIXTURE_DEFAULT.is_dir():
        return _PDF_FIXTURE_DEFAULT
    return None


_PDF_DIR = _resolve_pdf_dir()


def _list_pdfs(directory: Path) -> List[Path]:
    try:
        return sorted(p for p in directory.iterdir() if p.suffix.lower() == ".pdf")
    except Exception:
        return []


def _load_p0_fixture(name: str) -> Dict[str, Any]:
    path = _P0_FIXTURE_DIR / name
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _build_topology_from_pdfs(pdf_dir: Path) -> Dict[int, Dict[str, Any]]:
    pdfs = _list_pdfs(pdf_dir)
    if not pdfs:
        return {}
    all_matchlines: List[Dict[str, Any]] = []
    all_callouts: List[Dict[str, Any]] = []
    for p in pdfs:
        try:
            all_matchlines.extend(pp.extract_matchlines(p) or [])
            all_callouts.extend(pp.extract_station_callouts(p) or [])
        except Exception:
            continue
    try:
        return pp.derive_sheet_station_origins(all_matchlines, all_callouts)
    except Exception:
        return {}


def _replay_group(
    group: Dict[str, Any],
    rankings: List[Dict[str, Any]],
    sheet_origins: Dict[int, Dict[str, Any]],
    print_to_sheets: Dict[str, List[int]],
    sheet_to_route_ids: Dict[int, List[str]],
) -> Dict[str, Any]:
    """Run the compute helper for a single (group, rankings) pair.
    Returns a structured per-group report entry.
    """
    pre_top_id = ""
    pre_top_name = ""
    pre_top_score = 0.0
    if rankings:
        pre_top_id = str(rankings[0].get("route_id") or "")
        pre_top_name = str(rankings[0].get("route_name") or "")
        try:
            pre_top_score = float(
                rankings[0].get("combined_score") or rankings[0].get("score") or 0.0
            )
        except Exception:
            pre_top_score = 0.0

    hypothetical, meta = pp.compute_plan_aware_footage_boost(
        rankings, group, sheet_origins,
        print_to_sheets=print_to_sheets,
        sheet_to_route_ids=sheet_to_route_ids,
    )

    post_top_id = ""
    post_top_name = ""
    post_top_score = 0.0
    if hypothetical:
        post_top_id = str(hypothetical[0].get("route_id") or "")
        post_top_name = str(hypothetical[0].get("route_name") or "")
        try:
            post_top_score = float(
                hypothetical[0].get("combined_score") or hypothetical[0].get("score") or 0.0
            )
        except Exception:
            post_top_score = 0.0

    return {
        "group_id": str(group.get("group_id") or ""),
        "span_ft": group.get("span_ft"),
        "print_tokens": list(group.get("print_tokens") or []),
        "candidate_count": len(rankings),
        "pre_top": {
            "route_id": pre_top_id,
            "route_name": pre_top_name,
            "score": pre_top_score,
        },
        "post_top": {
            "route_id": post_top_id,
            "route_name": post_top_name,
            "score": post_top_score,
        },
        "applied_hypothetically": bool(meta.get("applied")),
        "would_reorder": bool(meta.get("would_reorder")),
        "skipped_reason": meta.get("skipped_reason"),
        "evidence": dict(meta.get("evidence") or {}),
        "hint_route_ids": list(meta.get("hint_route_ids") or []),
        "boosted_route_ids": list(meta.get("boosted_route_ids") or []),
        "top_score_gap_before": float(meta.get("top_score_gap_before") or 0.0),
        "top_score_gap_after": float(meta.get("top_score_gap_after") or 0.0),
        "per_ranking_deltas": list(meta.get("per_ranking_deltas") or []),
    }


def _build_report(
    pdf_dir: Path,
    pdfs: List[Path],
    sheet_origins: Dict[int, Dict[str, Any]],
    per_group: List[Dict[str, Any]],
) -> Dict[str, Any]:
    applied = [g for g in per_group if g["applied_hypothetically"]]
    reorders = [g for g in per_group if g["would_reorder"]]
    skipped = [g for g in per_group if not g["applied_hypothetically"]]
    ambiguous_evidence = [
        g for g in per_group
        if g.get("evidence", {}).get("classification") in {"partial_consistent",
                                                            "uncertain", "no_data"}
    ]

    skip_reasons: Dict[str, int] = {}
    for g in skipped:
        r = g.get("skipped_reason") or "<none>"
        skip_reasons[r] = skip_reasons.get(r, 0) + 1

    sheet_origin_summary = {
        str(k): {
            "length_ft": v.get("length_ft"),
            "method": v.get("method"),
            "confidence": v.get("confidence"),
            "has_reset_boundary": v.get("has_reset_boundary"),
        }
        for k, v in sorted(sheet_origins.items())
    }

    return {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "phase": "P5.4 shadow",
        "pdf_directory": str(pdf_dir),
        "pdf_count": len(pdfs),
        "pdf_files": [p.name for p in pdfs],
        "sheet_origin_count": len(sheet_origins),
        "sheet_origin_summary": sheet_origin_summary,
        "group_count": len(per_group),
        "groups_applied_hypothetically": len(applied),
        "groups_would_reorder": len(reorders),
        "groups_skipped": len(skipped),
        "groups_ambiguous_evidence": len(ambiguous_evidence),
        "skip_reason_breakdown": skip_reasons,
        "per_group": per_group,
        "boost_per_entry_cap": pp._FOOTAGE_BOOST_MAX_PER_ENTRY,
        "reorder_gap": pp._FOOTAGE_BOOST_REORDER_GAP,
    }


def _render_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# P5.4 Shadow Replay Report — Brenham")
    lines.append("")
    lines.append(f"**Generated:** {report['generated_at_utc']}")
    lines.append(f"**Phase:** {report['phase']}")
    lines.append("")
    lines.append("## Inputs")
    lines.append("")
    lines.append(f"- PDF directory: `{report['pdf_directory']}`")
    lines.append(f"- PDFs ingested: {report['pdf_count']}")
    for n in report["pdf_files"]:
        lines.append(f"  - `{n}`")
    lines.append(f"- Sheets with derived topology: {report['sheet_origin_count']}")
    lines.append("")

    lines.append("## Aggregate counts")
    lines.append("")
    lines.append(f"- Groups evaluated: **{report['group_count']}**")
    lines.append(f"- Groups where boost WOULD apply: **{report['groups_applied_hypothetically']}**")
    lines.append(f"- Groups where boost WOULD reorder the top: **{report['groups_would_reorder']}**")
    lines.append(f"- Groups skipped (no boost): **{report['groups_skipped']}**")
    lines.append(f"- Groups with ambiguous-class evidence: **{report['groups_ambiguous_evidence']}**")
    lines.append("")

    lines.append("## Skip-reason breakdown")
    lines.append("")
    if not report["skip_reason_breakdown"]:
        lines.append("_(no skips)_")
    else:
        for reason, count in sorted(report["skip_reason_breakdown"].items()):
            lines.append(f"- `{reason}`: {count}")
    lines.append("")

    lines.append("## Sheet topology summary")
    lines.append("")
    lines.append("| Sheet | length_ft | method | confidence | reset? |")
    lines.append("|---|---|---|---|---|")
    for sheet, entry in sorted(
        report["sheet_origin_summary"].items(),
        key=lambda kv: int(kv[0]) if str(kv[0]).isdigit() else 999999,
    ):
        lines.append(
            f"| {sheet} | {entry.get('length_ft')} | "
            f"{entry.get('method')} | {entry.get('confidence')} | "
            f"{entry.get('has_reset_boundary')} |"
        )
    lines.append("")

    lines.append("## Per-group decisions")
    lines.append("")
    for g in report["per_group"]:
        lines.append(f"### {g['group_id']}")
        lines.append("")
        lines.append(f"- span_ft: {g['span_ft']}")
        lines.append(f"- print_tokens: {g['print_tokens']}")
        lines.append(f"- candidate_count: {g['candidate_count']}")
        lines.append(f"- pre_top: `{g['pre_top']['route_id']}` "
                     f"({g['pre_top']['route_name']}, score "
                     f"{g['pre_top']['score']:.4f})")
        lines.append(f"- post_top: `{g['post_top']['route_id']}` "
                     f"({g['post_top']['route_name']}, score "
                     f"{g['post_top']['score']:.4f})")
        lines.append(f"- applied_hypothetically: **{g['applied_hypothetically']}**")
        lines.append(f"- would_reorder: **{g['would_reorder']}**")
        if g.get("skipped_reason"):
            lines.append(f"- skipped_reason: `{g['skipped_reason']}`")
        ev = g.get("evidence") or {}
        if ev:
            lines.append(f"- evidence.classification: `{ev.get('classification')}`")
            lines.append(f"- evidence.confidence: `{ev.get('confidence')}`")
            lines.append(f"- evidence.consistency_ratio: "
                         f"{ev.get('consistency_ratio')}")
            lines.append(f"- evidence.covered_sheets: {ev.get('covered_sheets')}")
            lines.append(f"- evidence.missing_sheets: {ev.get('missing_sheets')}")
            lines.append(f"- evidence.has_reset_boundary: "
                         f"{ev.get('has_reset_boundary')}")
        if g.get("hint_route_ids"):
            lines.append(f"- hint_route_ids: {g['hint_route_ids']}")
        if g.get("boosted_route_ids"):
            lines.append(f"- boosted_route_ids: {g['boosted_route_ids']}")
        lines.append(f"- top_score_gap_before: {g['top_score_gap_before']:.4f}")
        lines.append(f"- top_score_gap_after: {g['top_score_gap_after']:.4f}")
        if g.get("per_ranking_deltas"):
            lines.append("- per_ranking_deltas:")
            for d in g["per_ranking_deltas"]:
                lines.append(
                    f"    - `{d['route_id']}`: "
                    f"score {d['score_before']:.4f} -> {d['score_after']:.4f} "
                    f"(boost +{d['boost']:.4f}, eligible={d['was_eligible']})"
                )
        lines.append("")

    lines.append("## Cap parameters")
    lines.append("")
    lines.append(f"- boost_per_entry_cap: **{report['boost_per_entry_cap']}**")
    lines.append(f"- reorder_gap: **{report['reorder_gap']}**")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("_P5.4 SHADOW phase: these are hypothetical decisions only. "
                 "Runtime ranking, route selection, and render gates are "
                 "unchanged. No production behavior was altered to produce "
                 "this report._")
    return "\n".join(lines)


_SKIP_REASON_FOR_NO_PDFS = (
    "Brenham engineering-plan PDFs not found "
    f"(set TRUELINE_PLAN_FIXTURE_DIR or place at {_PDF_FIXTURE_DEFAULT})"
)


@unittest.skipIf(_PDF_DIR is None, _SKIP_REASON_FOR_NO_PDFS)
class BrenhamShadowReplay(unittest.TestCase):
    """End-to-end shadow replay against Brenham fixtures + P0 lockdown
    bore-log groups. Generates artifact reports as a side effect.

    All assertions are observational — the test confirms the harness
    runs, the reports are written, and the shadow path does not raise.
    Runtime truth is untouched.
    """

    @classmethod
    def setUpClass(cls) -> None:
        assert _PDF_DIR is not None
        cls.pdf_dir = _PDF_DIR
        cls.pdfs = _list_pdfs(_PDF_DIR)
        cls.sheet_origins = _build_topology_from_pdfs(_PDF_DIR)

        normalized = _load_p0_fixture("normalized_groups.json")
        rankings_input = _load_p0_fixture("rankings_input.json")
        cls.groups = list(normalized.get("groups") or [])
        cls.rankings_by_group: Dict[str, List[Dict[str, Any]]] = {
            scen.get("group_id"): list(scen.get("rankings") or [])
            for scen in (rankings_input.get("scenarios") or [])
        }

        cls.print_to_sheets = main._print_to_sheets_from_packet_index()
        cls.sheet_to_route_ids = main._sheet_to_route_ids_from_packet_index()

        per_group: List[Dict[str, Any]] = []
        for group in cls.groups:
            gid = str(group.get("group_id") or "")
            rankings = cls.rankings_by_group.get(gid, [])
            per_group.append(_replay_group(
                group, rankings, cls.sheet_origins,
                cls.print_to_sheets, cls.sheet_to_route_ids,
            ))
        cls.per_group = per_group

        cls.report = _build_report(_PDF_DIR, cls.pdfs, cls.sheet_origins, per_group)

        # Write artifacts.
        try:
            _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            (_OUTPUT_DIR / "brenham_p54_shadow_report.json").write_text(
                json.dumps(cls.report, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            (_OUTPUT_DIR / "brenham_p54_shadow_report.md").write_text(
                _render_markdown(cls.report),
                encoding="utf-8",
            )
        except Exception:
            pass

    def test_pdfs_were_found(self) -> None:
        self.assertGreater(len(self.pdfs), 0,
                           "expected at least one Brenham PDF")

    def test_topology_was_derived(self) -> None:
        # The Brenham AutoCAD plan set has matchlines; topology should be
        # non-empty when fixtures present.
        self.assertGreater(len(self.sheet_origins), 0,
                           "expected non-empty sheet_origins from Brenham PDFs")

    def test_p0_fixtures_loaded(self) -> None:
        self.assertGreater(len(self.groups), 0)
        self.assertGreater(len(self.rankings_by_group), 0)

    def test_every_group_has_a_per_group_entry(self) -> None:
        self.assertEqual(len(self.per_group), len(self.groups))

    def test_no_exceptions_in_replay(self) -> None:
        # If setUpClass had raised, this test wouldn't run. The fact that
        # we got here is the proof. Re-assert that every entry has the
        # required schema fields anyway.
        for entry in self.per_group:
            for key in (
                "group_id", "applied_hypothetically", "would_reorder",
                "evidence", "skipped_reason", "per_ranking_deltas",
            ):
                self.assertIn(key, entry)

    def test_runtime_truth_unaffected(self) -> None:
        # The compute helper is pure; rankings_by_group should still match
        # the fixture exactly after the replay.
        fixture = _load_p0_fixture("rankings_input.json")
        fixture_rankings = {
            scen.get("group_id"): list(scen.get("rankings") or [])
            for scen in (fixture.get("scenarios") or [])
        }
        for gid, rankings in self.rankings_by_group.items():
            self.assertEqual(rankings, fixture_rankings.get(gid, []))

    def test_aggregate_counts_consistent(self) -> None:
        applied = sum(1 for g in self.per_group if g["applied_hypothetically"])
        reorders = sum(1 for g in self.per_group if g["would_reorder"])
        skipped = sum(1 for g in self.per_group if not g["applied_hypothetically"])
        self.assertEqual(applied + skipped, len(self.per_group))
        # reorders must be a subset of applied
        self.assertLessEqual(reorders, applied)

    def test_artifact_reports_written(self) -> None:
        json_path = _OUTPUT_DIR / "brenham_p54_shadow_report.json"
        md_path = _OUTPUT_DIR / "brenham_p54_shadow_report.md"
        self.assertTrue(json_path.is_file(),
                        f"JSON report missing at {json_path}")
        self.assertTrue(md_path.is_file(),
                        f"Markdown report missing at {md_path}")
        # JSON must round-trip
        loaded = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertIn("per_group", loaded)
        self.assertEqual(len(loaded["per_group"]), len(self.per_group))


if __name__ == "__main__":
    unittest.main()
