r"""Phase-2F one-command local redline-manifest pipeline runner (PROOF ONLY).

Chains the proven contract pipeline end-to-end, locally:
  1. verify the 37 NEW_TARGET sweep artifacts exist (never re-runs the heavy sweep here),
  2. verify (or, behind an explicit flag, re-render) the 13 ALREADY_DRAWN canonical artifacts,
  3. assemble the all-50 input manifest (Phase 2D assembler),
  4. publish artifacts through the Phase-2A publisher,
  5. validate the published bundle through the Phase-2E bundle validator,
  6. emit one final run report.

DEFAULT mode is no-render / validate-existing. Rendering the 13 happens ONLY behind the explicit
`--render-already-drawn13` flag and is announced loudly. The 37-log heavy sweep is NEVER invoked
here. Blocked/covered logs are never rendered or given artifacts. No solver/geometry/fixture change,
no web/backend wiring, no deploy. Generated output stays under gitignored data/outputs.

    python -m truelinev2.proof.run_redline_manifest_local_pipeline --validate-existing
    python -m truelinev2.proof.run_redline_manifest_local_pipeline --publish-existing-artifacts
    python -m truelinev2.proof.run_redline_manifest_local_pipeline --render-already-drawn13   # render!
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

from truelinev2.contracts.published_bundle import (
    INDEX_FILENAME,
    MANIFEST_FILENAME,
    build_bundle_index,
    validate_bundle,
    write_bundle_index,
)
from truelinev2.contracts.redline_manifest_publisher import publish_manifest
from truelinev2.proof.run_redline_manifest_all50_publish import (
    build_artifact_paths,
    build_publish_input,
    partial_logs_from_canonical,
)

REPO = Path(__file__).resolve().parents[2]
BASE = REPO / "truelinev2" / "contracts" / "examples" / \
    "brenham_50_of_58_redline_manifest.example.json"
SWEEP_REPORT = REPO / "data" / "outputs" / "callout_route_assembly_sweep" / \
    "callout_route_assembly_sweep.json"
CANONICAL_ROOT = REPO / "data" / "outputs" / "redline_manifest_publish" / "already_drawn13_canonical"
CANONICAL_REPORT = CANONICAL_ROOT / "already_drawn13_canonical_render_report.json"
PUBLISH_ROOT = REPO / "data" / "outputs" / "redline_manifest_publish"
EXISTING_BUNDLE = PUBLISH_ROOT / "brenham_c19b565_all50_real_manifest"
DEFAULT_RUN_LABEL = "brenham_c19b565_all50_pipeline"

BLOCKED_IDS = ("log5", "log31", "log38", "log43", "log15", "log16", "log57")


def git_head():
    try:
        b = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(REPO),
                           capture_output=True, text=True, timeout=10)
        h = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(REPO),
                           capture_output=True, text=True, timeout=10)
        if b.returncode == 0 and h.returncode == 0:
            return b.stdout.strip(), h.stdout.strip()
    except Exception:
        pass
    return None, None


def verify_artifacts_exist(paths_by_log, repo_root):
    """Return (count, missing). Each path may be repo-relative or absolute."""
    count = 0
    missing = []
    for lid, paths in paths_by_log.items():
        for p in paths:
            count += 1
            if not ((Path(repo_root) / p).is_file() or Path(p).is_file()):
                missing.append("%s: %s" % (lid, p))
    return count, missing


def check_semantics(manifest):
    """Preservation checks; None for any log absent from this manifest (tolerant for fixtures)."""
    by = {l["log_id"]: l for l in manifest["logs"]}

    def blocked_ok():
        if not all(b in by for b in BLOCKED_IDS):
            return None
        return all(not by[b]["artifacts"] and by[b]["blocked"]
                   and by[b]["blocker"]["unlock_requirement"].strip() for b in BLOCKED_IDS)

    return {
        "blocked_preserved": blocked_ok(),
        "covered_log14_preserved": (
            by["log14"]["status"] == "COVERED_BY_EXISTING_REDLINE" and not by["log14"]["artifacts"]
            and by["log14"]["coverage"]["covered_by"] == "log10") if "log14" in by else None,
        "log3_owner_confirmed": (
            by["log3"]["provenance"] == "OWNER_CONFIRMED_HUMAN_ADJUSTABLE") if "log3" in by else None,
        "log7_partial_warning": (
            any("PARTIAL" in w or "representative" in w for w in by["log7"]["warnings"]))
        if "log7" in by else None,
    }


def assemble_and_publish(base, sweep, canon, canonical_root, publish_root, run_label, repo_root):
    paths = build_artifact_paths(sweep, canon, canonical_root)
    partials = partial_logs_from_canonical(canon)
    drawn = [l["log_id"] for l in base["logs"] if l["drawn"]]
    _, missing = verify_artifacts_exist({k: paths.get(k, []) for k in drawn}, repo_root)
    if missing:
        raise FileNotFoundError("missing source artifacts for drawn logs: %s" % missing[:5])
    inp = build_publish_input(base, paths, partials)
    amap = {}
    for lid in drawn:
        for p in paths[lid]:
            amap[p] = str(Path(repo_root) / p) if (Path(repo_root) / p).is_file() else p
    publish_dir = Path(publish_root) / run_label
    publish_dir.mkdir(parents=True, exist_ok=True)
    inp_path = publish_dir / "_publish_input_manifest.json"
    inp_path.write_text(json.dumps(inp, indent=2) + "\n", encoding="utf-8")
    return publish_manifest(inp_path, repo_root, publish_root, run_label, artifact_map=amap)


def _bundle_report(bundle_root, t):
    rep = validate_bundle(bundle_root)
    t["bundle_validate"] = round(time.perf_counter() - t.pop("_mark"), 4)
    manifest = json.loads((Path(bundle_root) / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    # Ensure an index exists (validate-existing also validates/writes the index).
    if not (Path(bundle_root) / INDEX_FILENAME).is_file():
        write_bundle_index(bundle_root, build_bundle_index(bundle_root, rep))
    return rep, manifest


def run(mode, run_label, bundle_arg):
    branch, head = git_head()
    timings = {"inspect": 0.0, "render": None, "assemble": 0.0, "publish": 0.0, "bundle_validate": 0.0}
    t0 = time.perf_counter()
    render_used = False
    source_dirs = []

    if mode == "validate-existing":
        bundle_root = Path(bundle_arg) if bundle_arg else EXISTING_BUNDLE
        source_dirs = [str(bundle_root)]
        timings["_mark"] = time.perf_counter()
        rep, manifest = _bundle_report(bundle_root, timings)
        out_dir = bundle_root
    else:  # publish-existing-artifacts (optionally after rendering the 13)
        if mode == "render-already-drawn13":
            print("!! RENDER AUTHORIZATION USED: re-rendering the 13 ALREADY_DRAWN canonical lanes "
                  "(NEW_TARGET sweep NOT run; blocked/covered logs NOT rendered).")
            from truelinev2.proof.run_already_drawn13_canonical_render_registry import main as reg_main
            tr = time.perf_counter()
            rc = reg_main(["--render"])
            timings["render"] = round(time.perf_counter() - tr, 4)
            if rc != 0:
                raise RuntimeError("already-drawn13 render registry failed (rc=%d)" % rc)
            render_used = True

        ti = time.perf_counter()
        base = json.loads(BASE.read_text(encoding="utf-8"))
        sweep = json.loads(SWEEP_REPORT.read_text(encoding="utf-8"))
        canon = json.loads(CANONICAL_REPORT.read_text(encoding="utf-8"))
        source_dirs = [str(SWEEP_REPORT.parent), str(CANONICAL_ROOT)]
        # Verify both artifact sources exist before publishing.
        sweep_paths = {l: [a for a in (v.get("artifacts") or [])] for l, v in sweep["verdicts"].items()}
        sweep_n, sweep_missing = verify_artifacts_exist(sweep_paths, REPO)
        can_paths = {r["log_id"]: [str(CANONICAL_ROOT / a["rel"]) for a in r["artifacts"]]
                     for r in canon["render"]}
        can_n, can_missing = verify_artifacts_exist(can_paths, REPO)
        timings["inspect"] = round(time.perf_counter() - ti, 4)
        if sweep_missing or can_missing:
            raise FileNotFoundError("source artifacts missing: sweep=%s canonical=%s"
                                    % (sweep_missing[:3], can_missing[:3]))

        ta = time.perf_counter()
        paths = build_artifact_paths(sweep, canon, CANONICAL_ROOT)
        partials = partial_logs_from_canonical(canon)
        inp = build_publish_input(base, paths, partials)
        timings["assemble"] = round(time.perf_counter() - ta, 4)

        tp = time.perf_counter()
        drawn = [l["log_id"] for l in base["logs"] if l["drawn"]]
        amap = {p: str(REPO / p) for lid in drawn for p in paths[lid]}
        publish_dir = PUBLISH_ROOT / run_label
        publish_dir.mkdir(parents=True, exist_ok=True)
        inp_path = publish_dir / "_publish_input_manifest.json"
        inp_path.write_text(json.dumps(inp, indent=2) + "\n", encoding="utf-8")
        result = publish_manifest(inp_path, REPO, PUBLISH_ROOT, run_label, artifact_map=amap)
        timings["publish"] = round(time.perf_counter() - tp, 4)
        out_dir = Path(result["publish_dir"])

        timings["_mark"] = time.perf_counter()
        rep, manifest = _bundle_report(out_dir, timings)

    timings["total"] = round(time.perf_counter() - t0, 4)
    timings.pop("_mark", None)
    sem = check_semantics(manifest)
    report = {
        "run_mode": mode, "branch": branch, "head": head,
        "source_artifact_dirs": source_dirs,
        "output_bundle_root": str(out_dir),
        "manifest_path": str(Path(out_dir) / MANIFEST_FILENAME),
        "manifest_sha256": rep["manifest_sha256"],
        "artifact_count": rep["artifact_count"], "total_bytes": rep["total_bytes"],
        "mock_example_false": manifest.get("mock_example") is False,
        "schema_validation": "PASS" if not rep["schema_errors"] else "FAIL",
        "bundle_validation": "VALID" if rep["valid"] else "INVALID",
        "static_serving_safe": rep["static_serving_safe"],
        "render_used": render_used,
        "benchmark_s": timings,
        "semantics": sem,
    }
    return report, rep["valid"]


def main(argv=None):
    ap = argparse.ArgumentParser(description="One-command local redline-manifest pipeline (proof).")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--validate-existing", action="store_true",
                   help="validate the existing Phase-2D/2E bundle (default; no render, no republish)")
    g.add_argument("--publish-existing-artifacts", action="store_true",
                   help="assemble + publish a fresh all-50 bundle from existing artifacts (no render)")
    g.add_argument("--render-already-drawn13", action="store_true",
                   help="EXPLICIT: re-render the 13 ALREADY_DRAWN, then publish + validate")
    ap.add_argument("--run-label", default=DEFAULT_RUN_LABEL, help="publish run label / output dir name")
    ap.add_argument("--bundle", default=None, help="bundle root for --validate-existing")
    args = ap.parse_args(argv)

    if args.render_already_drawn13:
        mode = "render-already-drawn13"
    elif args.publish_existing_artifacts:
        mode = "publish-existing-artifacts"
    else:
        mode = "validate-existing"

    report, ok = run(mode, args.run_label, args.bundle)
    print("== Phase-2F local pipeline (%s) ==" % mode)
    for k in ("branch", "head", "output_bundle_root", "manifest_sha256", "artifact_count",
              "total_bytes", "mock_example_false", "schema_validation", "bundle_validation",
              "static_serving_safe", "render_used"):
        print("  %-22s %s" % (k, report[k]))
    print("  benchmark_s            %s" % report["benchmark_s"])
    print("  semantics              %s" % report["semantics"])
    if mode != "validate-existing":
        (Path(report["output_bundle_root"]) / "_phase2f_pipeline_report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8")
    print("  RESULT: %s" % ("OK" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
