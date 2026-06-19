r"""Phase-2G render-phase benchmark (RENDER-GATED proof; measure timing, change no truth).

Drives the Phase-2F pipeline in explicit render mode (`--render-already-drawn13`): re-renders ONLY
the 13 ALREADY_DRAWN canonical lanes, then assembles + publishes + validates the all-50 bundle into
a FRESH benchmark dir, and records one consolidated benchmark report. It NEVER re-runs the 37
NEW_TARGET heavy sweep (those artifacts are reused), NEVER renders log14 or the 7 blocked logs, and
changes no geometry/solver/fixture/census/parent-model. Output stays under gitignored data/outputs.

    python -m truelinev2.proof.run_redline_manifest_render_benchmark
"""
from __future__ import annotations

import json
from pathlib import Path

from truelinev2.proof.run_redline_manifest_local_pipeline import (
    CANONICAL_REPORT,
    PUBLISH_ROOT,
    run,
)

BENCH_LABEL = "brenham_c19b565_pipeline_render13_benchmark"
BENCH_DIR = PUBLISH_ROOT / BENCH_LABEL


def main():
    report, ok = run("render-already-drawn13", BENCH_LABEL, None)

    # Render details come from the registry's regenerated canonical report.
    rows = json.loads(CANONICAL_REPORT.read_text(encoding="utf-8")).get("render", [])
    logs_rendered = [r["log_id"] for r in rows if r.get("status") == "RENDERED"]
    failures = [{"log_id": r["log_id"], "status": r.get("status"), "reason": r.get("reason", "")}
                for r in rows if r.get("status") != "RENDERED"]
    rendered_artifact_count = sum(r.get("stroke_count", 0) for r in rows)

    t = report["benchmark_s"]
    bench = {
        "phase": "2G", "benchmark_mode": "render-already-drawn13",
        "render_used": report["render_used"],
        "output_bundle_root": report["output_bundle_root"],
        "manifest_sha256": report["manifest_sha256"],
        "artifact_count_final_bundle": report["artifact_count"],
        "total_bytes": report["total_bytes"],
        "bundle_valid": ok,
        "logs_rendered": logs_rendered,
        "logs_rendered_count": len(logs_rendered),
        "rendered_artifact_count": rendered_artifact_count,
        "render_failures": failures,
        "timing_s": {
            "inspect_verify": t.get("inspect"),
            "render_already_drawn13": t.get("render"),
            "assemble": t.get("assemble"),
            "publish": t.get("publish"),
            "bundle_validate": t.get("bundle_validate"),
            "total": t.get("total"),
        },
        "semantics_preserved": report["semantics"],
        "schema_validation": report["schema_validation"],
        "static_serving_safe": report["static_serving_safe"],
    }
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    (BENCH_DIR / "_phase2g_render_benchmark.json").write_text(
        json.dumps(bench, indent=2), encoding="utf-8")

    print("== Phase-2G render-phase benchmark ==")
    print("  bundle valid:            %s" % ("YES" if ok else "NO"))
    print("  render used:             %s" % report["render_used"])
    print("  logs rendered:           %d  %s" % (len(logs_rendered), logs_rendered))
    print("  rendered artifact count: %d" % rendered_artifact_count)
    print("  render failures:         %s" % (failures or "NONE"))
    print("  final bundle artifacts:  %d" % report["artifact_count"])
    print("  total bytes:             %d" % report["total_bytes"])
    print("  manifest sha256:         %s" % report["manifest_sha256"])
    print("  schema / static-serving: %s / %s" % (report["schema_validation"], report["static_serving_safe"]))
    print("  semantics preserved:     %s" % report["semantics"])
    print("  --- timing (s) ---")
    for k, v in bench["timing_s"].items():
        print("    %-22s %s" % (k, v))
    print("  benchmark report: %s" % (BENCH_DIR / "_phase2g_render_benchmark.json"))
    return 0 if (ok and not failures) else 1


if __name__ == "__main__":
    raise SystemExit(main())
