r"""Phase-2C authoritative render registry for the 13 ALREADY_DRAWN logs (PROOF/PLUMBING ONLY).

The 13 ALREADY_DRAWN logs are excluded from the callout route-assembly sweep and were drawn by
heterogeneous prior render lanes scattered across many output dirs (Phase 2A.5 / 2B). This module
pins ONE canonical existing render entrypoint per log, so each can be RE-RENDERED (not picked from
old PNGs by filename) into a single clean directory and later combined with the 37 NEW_TARGETS.

It is NOT a new solver, NOT new placement, and changes NO geometry. Each registry target is an
existing, proven, gated render proof driven OUT-OF-PROCESS (exit 0 required); the canonical final
redline stroke(s) it writes to its OWN gitignored output dir are then copied into the unified dir.
Drawn-log TRUTH comes from the committed manifest (never from PNG filenames); the filename filter
below only separates final STROKES from helper crops within a known-drawn log's render output.

    python -m truelinev2.proof.run_already_drawn13_canonical_render_registry            # inventory only
    python -m truelinev2.proof.run_already_drawn13_canonical_render_registry --render   # re-render the 13

Renders nothing in inventory mode. In --render mode, attempts EXACTLY the 13 targets and writes
artifacts only under data/outputs/redline_manifest_publish/already_drawn13_canonical/.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXAMPLE = REPO / "truelinev2" / "contracts" / "examples" / \
    "brenham_50_of_58_redline_manifest.example.json"
UNIFIED = REPO / "data" / "outputs" / "redline_manifest_publish" / "already_drawn13_canonical"

# log_id -> (canonical render entrypoint module, render_status, note). One path per log.
# 12 are the proven drivers from run_full_dataset_try_draw_all_slice; log50 is added explicitly
# (Phase 2B found it standalone, not wired into the old diagnostic registry).
REGISTRY = {
    "log7":  ("truelinev2.proof.run_symbol_anchored_stroke_proof", "PARTIAL",
              "symbol-anchored REVIEW stroke; endpoints exact, interior route representative (4 parallel strands)"),
    "log25": ("truelinev2.proof.run_design_path_adherence_proof", "FULL",
              "design-path-traced polyline following the drawn geometry, sheet 21"),
    "log45": ("truelinev2.proof.run_redline_stroke_proof", "FULL",
              "station-axis route-ladder stroke, sheet 10"),
    "log50": ("truelinev2.proof.run_log50_splice46_route_assembly_slice", "FULL",
              "splice-46 cross-sheet two-leg (s10/s11), joined by printed station identity"),
    "log51": ("truelinev2.proof.run_log51_symbol_anchored_stroke_proof", "FULL",
              "symbol-anchored AUTO stroke, sheet 8"),
    "log52": ("truelinev2.proof.run_source_bindable_held_back_render_slice", "FULL",
              "conduit chain, two sheet-local legs s7/s8"),
    "log53": ("truelinev2.proof.run_log53_render_artifact_slice", "FULL",
              "bore-lateral corridor, two sheet-local legs s5/s6"),
    "log59": ("truelinev2.proof.run_log59_render_artifact_slice", "FULL",
              "conduit ordered-chain path, sheet 21"),
    "log64": ("truelinev2.proof.run_log64_render_artifact_slice", "FULL",
              "continuous bore-vacant-pipe corridor, sheet 21"),
    "log65": ("truelinev2.proof.run_log65_cross_sheet_stroke_proof", "FULL",
              "cross-sheet stroke joined at the printed matchline boundary (s10/s9)"),
    "log66": ("truelinev2.proof.run_log66_render_artifact_slice", "FULL",
              "ordered-chain path, sheet 10"),
    "log69": ("truelinev2.proof.run_owner_corrected_held_back_render_batch_slice", "FULL",
              "ordered-chain path, sheet 17"),
    "log71": ("truelinev2.proof.run_log71_render_artifact_slice", "FULL",
              "chain path + corridor, two sheet-local legs s23/s24"),
}

PER_PROOF_TIMEOUT_S = 600


def _module_file(module: str) -> Path:
    return REPO / (module.replace(".", "/") + ".py")


def _out_dir(module: str):
    """Resolve a proof module's OUT_DIR (lazy import; engine loads only when needed)."""
    mod = importlib.import_module(module)
    out = getattr(mod, "OUT_DIR", None)
    return Path(out) if out is not None else None


def _drawn_already_set():
    """The ALREADY_DRAWN lane set from the committed manifest (status truth, not filenames)."""
    m = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    return {l["log_id"] for l in m["logs"] if l.get("drawn_lane") == "ALREADY_DRAWN"}, \
           {l["log_id"]: l for l in m["logs"]}


def _stroke_pngs(out_dir: Path, log: str):
    """Final redline stroke PNGs for `log` in its proof's OUT_DIR (excludes helper crops)."""
    if out_dir is None or not out_dir.is_dir():
        return [], []
    allp = sorted(p for p in out_dir.glob(log + "_*.png"))
    strokes = [p for p in allp if "stroke" in p.name.lower()]
    others = [p for p in allp if "stroke" not in p.name.lower()]
    return strokes, others


def inventory():
    rows = []
    for log, (module, status, note) in REGISTRY.items():
        mf = _module_file(module)
        present = mf.is_file()
        out_dir = None
        err = None
        if present:
            try:
                out_dir = _out_dir(module)
            except Exception as exc:  # pragma: no cover - import diagnostics
                err = "%s: %s" % (type(exc).__name__, exc)
        rows.append({
            "log_id": log, "entrypoint": module, "render_status": status, "note": note,
            "entrypoint_present": present, "out_dir": str(out_dir) if out_dir else None,
            "import_error": err,
            "status": "ENTRYPOINT_PRESENT" if (present and out_dir and not err) else "ENTRYPOINT_MISSING",
        })
    return rows


def run_render():
    already, logs = _drawn_already_set()
    assert set(REGISTRY) == already, \
        "registry %r != manifest ALREADY_DRAWN %r" % (sorted(REGISTRY), sorted(already))
    # Safety: every target is drawn and none is covered/blocked.
    for log in REGISTRY:
        assert logs[log]["drawn"] is True and not logs[log]["blocked"] and not logs[log]["covered"], log

    UNIFIED.mkdir(parents=True, exist_ok=True)
    rows = []
    for log, (module, status, note) in REGISTRY.items():
        out_dir = _out_dir(module)
        print("[2c] rendering %-6s via %s ..." % (log, module))
        proc = subprocess.run([sys.executable, "-m", module], cwd=str(REPO),
                              env={**os.environ, "PYTHONPATH": "."},
                              capture_output=True, text=True, timeout=PER_PROOF_TIMEOUT_S)
        strokes, others = _stroke_pngs(out_dir, log)
        dest = UNIFIED / log
        copied = []
        if proc.returncode == 0 and strokes:
            if dest.exists():
                shutil.rmtree(dest)
            dest.mkdir(parents=True, exist_ok=True)
            for p in strokes:
                d = dest / p.name
                shutil.copyfile(p, d)
                copied.append({"name": p.name, "bytes": d.stat().st_size,
                               "rel": str(d.relative_to(UNIFIED)).replace("\\", "/")})
        ok = proc.returncode == 0 and len(strokes) >= 1
        rows.append({
            "log_id": log, "entrypoint": module, "render_status": status, "note": note,
            "exit_code": proc.returncode, "out_dir": str(out_dir),
            "stroke_count": len(strokes), "other_png_count": len(others),
            "artifacts": copied,
            "status": "RENDERED" if ok else "BLOCKED",
            "reason": "" if ok else ("nonzero exit %d" % proc.returncode if proc.returncode else
                                     "no final stroke PNG produced"),
        })
        print("[2c]   %-6s exit=%d strokes=%d -> %s" % (log, proc.returncode, len(strokes), rows[-1]["status"]))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", action="store_true", help="re-render the 13 into the unified dir")
    args = ap.parse_args(argv)

    inv = inventory()
    missing = [r["log_id"] for r in inv if r["status"] != "ENTRYPOINT_PRESENT"]
    print("== Phase-2C ALREADY_DRAWN canonical render registry ==")
    print("targets: %d | entrypoints present: %d | missing: %s"
          % (len(REGISTRY), len(inv) - len(missing), missing or "NONE"))
    for r in inv:
        print("  %-6s %-22s %s" % (r["log_id"], r["status"], r["entrypoint"]))

    report = {"phase": "2C", "target_count": len(REGISTRY), "inventory": inv}

    if not args.render:
        print("\n(inventory only; pass --render to re-render the 13 into %s)" % UNIFIED)
        report["mode"] = "inventory"
        report["all_13_entrypoints_present"] = not missing
        _write_report(report)
        return 0 if not missing else 2

    if missing:
        print("\nSTOP: missing canonical entrypoints for %s -> not rendering." % missing)
        report["mode"] = "render_aborted_missing_entrypoints"
        _write_report(report)
        return 2

    rows = run_render()
    rendered = [r["log_id"] for r in rows if r["status"] == "RENDERED"]
    blocked = [r["log_id"] for r in rows if r["status"] != "RENDERED"]
    report.update({"mode": "render", "render": rows,
                   "rendered": rendered, "blocked": blocked,
                   "all_13_rendered": len(rendered) == len(REGISTRY),
                   "total_stroke_artifacts": sum(r["stroke_count"] for r in rows),
                   "total_bytes": sum(a["bytes"] for r in rows for a in r["artifacts"])})
    _write_report(report)
    print("\nRESULT: rendered %d/13 | blocked: %s" % (len(rendered), blocked or "NONE"))
    print("unified dir: %s" % UNIFIED)
    if report["all_13_rendered"]:
        print("VERDICT: all 13 ALREADY_DRAWN re-rendered canonically into one authoritative dir.")
        return 0
    print("VERDICT: STOP -- not all 13 rendered canonically; see blocked above (do not publish 50).")
    return 2


def _write_report(report):
    UNIFIED.mkdir(parents=True, exist_ok=True)
    (UNIFIED / "already_drawn13_canonical_render_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
