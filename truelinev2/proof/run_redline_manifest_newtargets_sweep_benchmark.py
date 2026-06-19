r"""Phase-2H NEW_TARGET sweep render benchmark (RENDER-GATED proof; measure timing, change no truth).

Times the existing callout-route-assembly sweep (the 37 NEW_TARGETS, single process), cross-checks
that it rendered ONLY the 37 (ALREADY_DRAWN / covered / blocked excluded by the sweep's own
`_is_target`), then re-validates the full all-50 bundle (publish + bundle-validate, NO render) so no
partial-37 result is left as a product. Changes no geometry/solver/fixture/census/parent-model; the
sweep + publish write only to gitignored data/outputs.

    python -m truelinev2.proof.run_redline_manifest_newtargets_sweep_benchmark
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from truelinev2.proof.run_redline_manifest_local_pipeline import PUBLISH_ROOT, run

REPO = Path(__file__).resolve().parents[2]
SWEEP_MODULE = "truelinev2.proof.run_callout_route_assembly_sweep"
SWEEP_DIR = REPO / "data" / "outputs" / "callout_route_assembly_sweep"
SWEEP_REPORT = SWEEP_DIR / "callout_route_assembly_sweep.json"
BASE = REPO / "truelinev2" / "contracts" / "examples" / \
    "brenham_50_of_58_redline_manifest.example.json"
BENCH_LABEL = "brenham_c19b565_newtargets_sweep_benchmark"
BENCH_DIR = PUBLISH_ROOT / BENCH_LABEL

# Phase-2G measured constants (for the full-frontier estimate).
RENDER13_S = 52.16
DOWNSTREAM_S = 0.13


def _lane_sets():
    m = json.loads(BASE.read_text(encoding="utf-8"))
    new = {l["log_id"] for l in m["logs"] if l.get("drawn_lane") == "NEW_TARGETS"}
    already = {l["log_id"] for l in m["logs"] if l.get("drawn_lane") == "ALREADY_DRAWN"}
    nondrawn = {l["log_id"] for l in m["logs"] if not l["drawn"]}
    return new, already, nondrawn


def main():
    new_targets, already, nondrawn = _lane_sets()

    # 1) Time the sweep (single process; renders the 37 NEW_TARGETS, wipes+rebuilds OUT_DIR).
    t0 = time.perf_counter()
    proc = subprocess.run([sys.executable, "-m", SWEEP_MODULE], cwd=str(REPO),
                          env={**os.environ, "PYTHONPATH": "."},
                          capture_output=True, text=True, timeout=1800)
    sweep_s = round(time.perf_counter() - t0, 3)

    rep = json.loads(SWEEP_REPORT.read_text(encoding="utf-8"))
    rendered = set(rep.get("newly_rendered_full", []))
    targets = set(rep.get("targets", []))
    blocked_count = len(targets - rendered)
    pngs = sorted(SWEEP_DIR.glob("*.png"))
    stroke_pngs = [p for p in pngs if "redline_stroke" in p.name.lower()]

    only_37_new = (rendered == new_targets) and (targets == new_targets)
    excluded_ok = not (rendered & (already | nondrawn))  # no ALREADY_DRAWN / covered / blocked
    strokes_only = (len(pngs) == len(stroke_pngs)) and len(pngs) > 0

    # 2) Re-validate the FULL all-50 (publish + bundle-validate, NO render) so no partial-37 lingers.
    rep50, ok50 = run("publish-existing-artifacts", BENCH_LABEL, None)
    pub_s = rep50["benchmark_s"].get("publish")
    val_s = rep50["benchmark_s"].get("bundle_validate")

    est_full = round(sweep_s + RENDER13_S + DOWNSTREAM_S, 2)
    bench = {
        "phase": "2H", "benchmark_mode": "callout_route_assembly_sweep (37 NEW_TARGETS, single process)",
        "sweep_output_dir": str(SWEEP_DIR),
        "sweep_exit_code": proc.returncode,
        "rendered_new_target_logs": sorted(rendered, key=lambda s: int(s[3:])),
        "rendered_new_target_count": len(rendered),
        "artifact_count": len(pngs),
        "stroke_artifact_count": len(stroke_pngs),
        "blocked_or_skipped_in_sweep": blocked_count,
        "only_37_new_targets": only_37_new,
        "already_drawn_covered_blocked_excluded": excluded_ok,
        "final_strokes_only_no_crops": strokes_only,
        "post_sweep_all50_bundle_valid": ok50,
        "post_sweep_all50_artifact_count": rep50["artifact_count"],
        "timing_s": {
            "newtargets_sweep_37": sweep_s,
            "already_drawn13_render_phase2g": RENDER13_S,
            "downstream_publish_validate": DOWNSTREAM_S,
            "estimated_full_frontier_refresh": est_full,
            "post_sweep_publish": pub_s,
            "post_sweep_bundle_validate": val_s,
        },
        "semantics_preserved_post_sweep": rep50["semantics"],
    }
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    (BENCH_DIR / "_phase2h_newtargets_sweep_benchmark.json").write_text(
        json.dumps(bench, indent=2), encoding="utf-8")

    print("== Phase-2H NEW_TARGET sweep render benchmark ==")
    print("  sweep exit code:           %d" % proc.returncode)
    print("  rendered NEW_TARGET logs:  %d (expected 37)" % len(rendered))
    print("  sweep artifact count:      %d (stroke-only: %s)" % (len(pngs), strokes_only))
    print("  blocked/skipped in sweep:  %d" % blocked_count)
    print("  only 37 NEW_TARGETS:       %s" % only_37_new)
    print("  ALREADY/covered/blocked excluded: %s" % excluded_ok)
    print("  post-sweep all-50 bundle:  %s (%d artifacts)" % (
        "VALID" if ok50 else "INVALID", rep50["artifact_count"]))
    print("  semantics preserved:       %s" % rep50["semantics"])
    print("  --- timing (s) ---")
    print("    37 NEW_TARGET sweep:           %s" % sweep_s)
    print("    13 ALREADY_DRAWN (Phase 2G):   %s" % RENDER13_S)
    print("    downstream publish/validate:   %s" % DOWNSTREAM_S)
    print("    estimated full frontier refresh: %s" % est_full)
    print("  benchmark report: %s" % (BENCH_DIR / "_phase2h_newtargets_sweep_benchmark.json"))
    ok = (proc.returncode == 0 and only_37_new and excluded_ok and strokes_only and ok50)
    print("  RESULT: %s" % ("OK" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
