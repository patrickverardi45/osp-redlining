r"""M8.11 -- reviewer service contract proof over the corrected Brenham corpus.

Proof only (no API route, no UI, no production change): exercises the M8.11
``ReviewerBundleService`` seam in BOTH modes and gates the results against the
banked M8.4->M8.10 facts. The fullest_safe_review mode composes M8.5 + M8.8 as
an EXPLICIT local generation mode -- no env flag is read or set, no default
changes, nothing is activated anywhere.

Embedded gates (any failure -> nonzero exit, no force-green):
  G1 corpus integrity: exactly 58 enumerated bore logs
  G2 default_baseline: status counts == AUTO 14 / REVIEW 10 / ABSTAIN 32 /
     ERROR 2 = 24 placed (the corrected-source baseline), 58/58 payloads
  G3 fullest_safe_review: 30 placed; lane breakdown EXACTLY
     PLACED_REVIEW 30 / PICK_CARD 16 / ADJUSTABLE 6 / OUT_OF_CLASS 4 /
     SOURCE_REVIEW 2 / UNSAFE 0 (58/58 actionable)
  G4 cross-mode increment: fullest placed-set minus default placed-set ==
     exactly {log7, log15, log16, log27, log45, log72} (M8.5 + M8.8, banked)
  G5 bundle validity: both bundles carry the pinned schema versions and their
     flag states match the closed mode table

OneDrive flake guard: the corpus path is resolved (and REPORTED) as
  1. ``TL2_BRENHAM_CORPUS`` env override, if set;
  2. else the pinned local copy ``data/outputs/corpus_pin/`` when it holds the
     full 58 (the B-TEST-CORPUS-ONEDRIVE-1 workaround);
  3. else the module default (OneDrive).

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_reviewer_service_contract
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Set, Tuple

from truelinev2.config import _REPO_ROOT
from truelinev2.proof.run_brenham_corpus import CORPUS_DIR, EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.review.reviewer_payloads import ReviewerLane
from truelinev2.review.reviewer_service import (
    MODE_FLAGS,
    ReviewerBundle,
    ReviewerBundleService,
    ReviewRunMode,
)

OUT_JSON = _REPO_ROOT / "data" / "outputs" / "reviewer_service_contract.json"
OUT_MD = _REPO_ROOT / "data" / "outputs" / "reviewer_service_contract.md"
PIN_DIR = _REPO_ROOT / "data" / "outputs" / "corpus_pin"

EXPECTED_DEFAULT = {"AUTO_SELECT": 14, "REVIEW": 10, "ABSTAIN": 32, "ERROR": 2,
                    "PLACED": 24}
EXPECTED_FULLEST_PLACED = 30
EXPECTED_FULLEST_LANES = {
    ReviewerLane.PLACED_REVIEW.value: 30,
    ReviewerLane.PICK_CARD_ROUTE_SUGGESTION.value: 16,
    ReviewerLane.HUMAN_ADJUSTABLE_LENGTH_REDLINE.value: 6,
    ReviewerLane.OUT_OF_CLASS.value: 4,
    ReviewerLane.SOURCE_REVIEW_REQUIRED.value: 2,
}
EXPECTED_INCREMENT = {"log7", "log15", "log16", "log27", "log45", "log72"}


def resolve_corpus() -> Tuple[str, str]:
    """(corpus_dir, how_resolved) per the OneDrive flake guard."""
    if os.getenv("TL2_BRENHAM_CORPUS"):
        return CORPUS_DIR, "env:TL2_BRENHAM_CORPUS override"
    if PIN_DIR.is_dir() and len(enumerate_corpus(PIN_DIR)) == EXPECTED_COUNT:
        return str(PIN_DIR), "pinned local copy (B-TEST-CORPUS-ONEDRIVE-1 guard)"
    return CORPUS_DIR, "module default (OneDrive)"


def placed_ids(bundle: ReviewerBundle) -> Set[str]:
    return {p.bore_id for p in bundle.payloads
            if p.lane is ReviewerLane.PLACED_REVIEW}


def main() -> int:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    corpus_dir, how = resolve_corpus()
    print(f"[m8.11] corpus dir : {corpus_dir}  ({how})")
    print(f"[m8.11] plan PDF   : {PDF}")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.11] STOP: inputs missing")
        return 2
    corpus = enumerate_corpus(corpus_dir)
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.11] STOP: corpus drift ({len(corpus)} != {EXPECTED_COUNT})")
        return 3

    svc = ReviewerBundleService(
        corpus_dir=corpus_dir, plan_pdf_path=PDF, project_id="brenham-ph5",
        bore_log_paths=corpus)
    bundles: Dict[str, ReviewerBundle] = {}
    for mode in (ReviewRunMode.DEFAULT_BASELINE, ReviewRunMode.FULLEST_SAFE_REVIEW):
        print(f"[m8.11] generating bundle: {mode.value} ...")
        bundles[mode.value] = svc.generate(mode)  # pydantic raises loudly on drift

    default = bundles[ReviewRunMode.DEFAULT_BASELINE.value]
    fullest = bundles[ReviewRunMode.FULLEST_SAFE_REVIEW.value]
    increment = placed_ids(fullest) - placed_ids(default)
    regressed = placed_ids(default) - placed_ids(fullest)

    gates: List[Tuple[str, bool, str]] = []

    def gate(name: str, ok: bool, detail: str) -> None:
        gates.append((name, ok, detail))
        print(f"[m8.11] {'PASS' if ok else 'FAIL'}  {name}: {detail}")

    gate("G1 corpus integrity", len(corpus) == EXPECTED_COUNT,
         f"{len(corpus)} bore logs")
    gate("G2 default baseline counts",
         default.status_counts == EXPECTED_DEFAULT
         and len(default.payloads) == EXPECTED_COUNT,
         f"{default.status_counts}, payloads {len(default.payloads)}/{EXPECTED_COUNT}")
    gate("G3 fullest-safe lanes",
         fullest.status_counts["PLACED"] == EXPECTED_FULLEST_PLACED
         and fullest.lane_counts == EXPECTED_FULLEST_LANES
         and fullest.lane_counts.get(ReviewerLane.UNSAFE_ABSTAIN.value, 0) == 0
         and len(fullest.payloads) == EXPECTED_COUNT,
         f"placed {fullest.status_counts['PLACED']}, lanes {fullest.lane_counts}")
    gate("G4 cross-mode increment",
         increment == EXPECTED_INCREMENT and not regressed,
         f"increment {sorted(increment)}, regressed {sorted(regressed)}")
    gate("G5 schema + mode-table pin",
         all(b.flag_state == MODE_FLAGS[b.run_mode] for b in bundles.values())
         and default.flag_state != fullest.flag_state,
         f"default {default.flag_state.model_dump()}, "
         f"fullest {fullest.flag_state.model_dump()}")
    all_ok = all(ok for _, ok, _ in gates)

    report = {
        "milestone": ("truelinev2 M8.11 -- reviewer service contract proof "
                      "(service seam only; no API route, no UI, no production change)"),
        "corpus_dir_used": corpus_dir,
        "corpus_resolution": how,
        "plan_pdf": PDF,
        "gates": [{"name": n, "ok": ok, "detail": d} for n, ok, d in gates],
        "verdict": "PASS" if all_ok else "FAILURE",
        "expected": {
            "default": EXPECTED_DEFAULT,
            "fullest_placed": EXPECTED_FULLEST_PLACED,
            "fullest_lanes": EXPECTED_FULLEST_LANES,
            "increment": sorted(EXPECTED_INCREMENT),
        },
        "note_default_lanes": (
            "the default_baseline LANE breakdown below is INFORMATIONAL (first "
            "measurement at this seam): only its status counts are a banked gate; "
            "the banked 58/58 lane breakdown gate applies to fullest_safe_review"),
        "bundles": {k: b.model_dump(mode="json") for k, b in bundles.items()},
    }
    OUT_JSON.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    L = ["# M8.11 -- reviewer service contract proof", "",
         f"- verdict: **{report['verdict']}**",
         f"- corpus: `{corpus_dir}` ({how})",
         f"- plan PDF: `{PDF}`", "",
         "## Gates", ""]
    for n, ok, d in gates:
        L.append(f"- {'PASS' if ok else 'FAIL'} -- {n}: {d}")
    for k, b in bundles.items():
        L += ["", f"## {k}", "",
              f"- flags: {b.flag_state.model_dump()}",
              f"- statuses: {b.status_counts}",
              f"- lanes: {b.lane_counts}"
              + ("  *(informational, not a banked gate)*"
                 if k == ReviewRunMode.DEFAULT_BASELINE.value else ""),
              f"- payloads: {len(b.payloads)} validated "
              f"({b.payload_schema_version} / {b.bundle_schema_version})"]
        by_lane: Dict[str, List[str]] = {}
        for p in b.payloads:
            by_lane.setdefault(p.lane.value, []).append(p.bore_id)
        for lane, ids in sorted(by_lane.items()):
            L.append(f"  - {lane} ({len(ids)}): " + ", ".join(sorted(ids)))
    L += ["", f"- cross-mode placed increment: {sorted(increment)}",
          f"- cross-mode placed regressions: {sorted(regressed)}", ""]
    OUT_MD.write_text("\n".join(L), encoding="utf-8")

    print(f"[m8.11] verdict: {report['verdict']}")
    print(f"[m8.11] report -> {OUT_MD}")
    return 0 if all_ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
