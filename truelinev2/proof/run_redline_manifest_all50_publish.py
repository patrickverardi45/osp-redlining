r"""Phase-2D all-50 real redline manifest publish (PUBLISHER/MANIFEST ONLY; no render, no solver).

Assembles ONE real manifest for the current 50 drawn logs by merging the two authoritative
artifact sources produced earlier -- the 37 NEW_TARGETS from the callout sweep report's
`verdicts[*].artifacts` and the 13 ALREADY_DRAWN from the Phase-2C canonical render report --
then runs the Phase-2A publisher to emit `mock_example:false` with real `sha256`/`bytes`.

It renders nothing, touches no solver/geometry/fixture/census/parent-model, and reads no stale
model field. Drawn-log TRUTH and status/provenance/coverage/blocker/warning semantics come from
the committed example manifest; the two reports supply only the real artifact PATHS for the
already-known-drawn logs (status is never inferred from PNG filenames). PARTIAL/representative
logs (log7) are flagged from the canonical report, not hardcoded.

Output (all gitignored, NOT committed):
  data/outputs/redline_manifest_publish/brenham_c19b565_all50_real_manifest/
    redline_manifest.json            (the real published manifest)
    artifacts/<log>/*.png            (published stroke copies)
    _publish_input_manifest.json     (the assembled publisher input)
    _phase2d_publish_report.json     (benchmark + validation summary)

    python -m truelinev2.proof.run_redline_manifest_all50_publish
"""
from __future__ import annotations

import copy
import json
import os
import time
from pathlib import Path

from truelinev2.contracts.redline_manifest_publisher import (
    load_schema,
    publish_manifest,
    reconciliation_errors,
    validate_manifest,
)

REPO = Path(__file__).resolve().parents[2]
BASE = REPO / "truelinev2" / "contracts" / "examples" / \
    "brenham_50_of_58_redline_manifest.example.json"
SWEEP_REPORT = REPO / "data" / "outputs" / "callout_route_assembly_sweep" / \
    "callout_route_assembly_sweep.json"
CANONICAL_ROOT = REPO / "data" / "outputs" / "redline_manifest_publish" / "already_drawn13_canonical"
CANONICAL_REPORT = CANONICAL_ROOT / "already_drawn13_canonical_render_report.json"
PUBLISH_ROOT = REPO / "data" / "outputs" / "redline_manifest_publish"
RUN_LABEL = "brenham_c19b565_all50_real_manifest"
FINAL_KIND = "FINAL_REDLINE_PNG"

PARTIAL_WARNING = (
    "PARTIAL / representative render: the symbol-anchored stroke has exact, source-backed "
    "endpoints but a representative interior route (parallel strands not individually traceable); "
    "treat the interior path as representative, not surveyed."
)


# --------------------------------------------------------------------------- #
# Pure assembler helpers (unit-testable with synthetic inputs; no real artifacts).
# --------------------------------------------------------------------------- #
def _verdict_paths(arts):
    out = []
    for a in arts or []:
        if isinstance(a, str):
            out.append(a)
        elif isinstance(a, dict):
            for k in ("path", "artifact", "file", "png"):
                if isinstance(a.get(k), str):
                    out.append(a[k]); break
    return out


def build_artifact_paths(sweep_report, canonical_report, canonical_root):
    """Merge the two authoritative reports into {log_id: [repo-relative source path, ...]}.

    37 NEW_TARGETS from sweep `verdicts[*].artifacts`; 13 ALREADY_DRAWN from the canonical
    report's per-log `artifacts[*].rel` under canonical_root.
    """
    paths = {}
    for log, v in (sweep_report.get("verdicts") or {}).items():
        paths[log] = list(_verdict_paths(v.get("artifacts")))
    croot = str(canonical_root).replace("\\", "/")
    for row in canonical_report.get("render") or []:
        log = row["log_id"]
        paths.setdefault(log, [])
        for a in row.get("artifacts") or []:
            paths[log].append(croot + "/" + a["rel"])
    return paths


def partial_logs_from_canonical(canonical_report):
    return {row["log_id"] for row in canonical_report.get("render") or []
            if row.get("render_status") == "PARTIAL"}


def build_publish_input(base_manifest, artifact_paths, partial_logs):
    """Return a real publisher INPUT: drawn logs get one FINAL_REDLINE_PNG record per real
    source path; covered/blocked logs keep empty artifacts; PARTIAL logs gain a warning.
    Status / provenance / coverage / blocker / counts are left untouched."""
    m = copy.deepcopy(base_manifest)
    missing = []
    for log in m["logs"]:
        lid = log["log_id"]
        if log["drawn"]:
            srcs = artifact_paths.get(lid, [])
            if not srcs:
                missing.append(lid)
            log["artifacts"] = [
                {"kind": FINAL_KIND, "path": p, "sha256": None, "example_placeholder": True}
                for p in srcs
            ]
            if lid in partial_logs and not any(PARTIAL_WARNING in w for w in log["warnings"]):
                log["warnings"] = list(log["warnings"]) + [PARTIAL_WARNING]
        else:
            log["artifacts"] = []  # covered/blocked never carry artifacts
    if missing:
        raise ValueError("drawn logs missing real artifacts: %s" % sorted(missing, key=lambda s: int(s[3:])))
    return m


# --------------------------------------------------------------------------- #
# Post-publish validation (the mission's explicit checks).
# --------------------------------------------------------------------------- #
def validate_published(manifest, schema):
    errs = []
    errs += ["schema: " + e for e in validate_manifest(manifest, schema)]
    errs += ["reconcile: " + e for e in reconciliation_errors(manifest)]
    if manifest.get("mock_example") is not False:
        errs.append("mock_example is not False")
    s = manifest["summary"]
    if [s["total_logs"], s["drawn_count"], s["covered_count"], s["blocked_count"]] != [58, 50, 1, 7]:
        errs.append("summary counts != 58/50/1/7")
    by = {l["log_id"]: l for l in manifest["logs"]}
    for lid, lg in by.items():
        if lg["drawn"]:
            finals = [a for a in lg["artifacts"] if a["kind"] == FINAL_KIND]
            if not finals:
                errs.append("%s drawn but no FINAL_REDLINE_PNG" % lid)
            for a in lg["artifacts"]:
                if not (isinstance(a.get("sha256"), str) and len(a["sha256"]) == 64):
                    errs.append("%s artifact missing 64-hex sha256" % lid)
                if not (isinstance(a.get("bytes"), int) and a["bytes"] > 0):
                    errs.append("%s artifact missing positive bytes" % lid)
                if a.get("published") is not True or a.get("example_placeholder") is not False:
                    errs.append("%s artifact not marked published/non-placeholder" % lid)
        else:
            if lg["artifacts"]:
                errs.append("%s not drawn but has artifacts" % lid)
    if by["log14"]["artifacts"] or by["log14"]["status"] != "COVERED_BY_EXISTING_REDLINE" \
            or by["log14"]["coverage"]["covered_by"] != "log10":
        errs.append("log14 covered-by-log10/no-artifact invariant broken")
    for lid in ("log5", "log31", "log38", "log43", "log15", "log16", "log57"):
        if by[lid]["artifacts"] or not by[lid]["blocked"] or not by[lid]["blocker"]["unlock_requirement"].strip():
            errs.append("%s blocked invariant broken" % lid)
    if by["log3"]["provenance"] != "OWNER_CONFIRMED_HUMAN_ADJUSTABLE":
        errs.append("log3 provenance changed")
    if not any("PARTIAL" in w or "representative" in w for w in by["log7"]["warnings"]):
        errs.append("log7 missing PARTIAL/representative warning")
    for lid in ("log48", "log70"):
        if not any("B-DATA-LOG48-ADJ-1" in w for w in by[lid]["warnings"]):
            errs.append("%s stored-anchor-debt warning missing" % lid)
    return errs


def main():
    t0 = time.perf_counter()
    schema = load_schema()
    base = json.loads(BASE.read_text(encoding="utf-8"))
    sweep = json.loads(SWEEP_REPORT.read_text(encoding="utf-8"))
    canon = json.loads(CANONICAL_REPORT.read_text(encoding="utf-8"))

    paths = build_artifact_paths(sweep, canon, CANONICAL_ROOT)
    partials = partial_logs_from_canonical(canon)
    # Existence preflight: every real source path must be on disk before publishing.
    drawn = [l["log_id"] for l in base["logs"] if l["drawn"]]
    absent = [(lid, p) for lid in drawn for p in paths.get(lid, []) if not (REPO / p).is_file()]
    if absent:
        raise FileNotFoundError("source artifacts missing on disk: %s" % absent[:5])

    input_manifest = build_publish_input(base, paths, partials)
    artifact_map = {p: str(REPO / p) for lid in drawn for p in paths[lid]}
    t_assemble = time.perf_counter() - t0

    publish_dir = PUBLISH_ROOT / RUN_LABEL
    publish_dir.mkdir(parents=True, exist_ok=True)
    input_path = publish_dir / "_publish_input_manifest.json"
    input_path.write_text(json.dumps(input_manifest, indent=2) + "\n", encoding="utf-8")

    t1 = time.perf_counter()
    result = publish_manifest(input_path, REPO, PUBLISH_ROOT, RUN_LABEL, artifact_map=artifact_map)
    t_publish = time.perf_counter() - t1

    manifest = result["manifest"]
    t2 = time.perf_counter()
    errs = validate_published(manifest, schema)
    t_validate = time.perf_counter() - t2

    artifact_count = sum(len(l["artifacts"]) for l in manifest["logs"])
    total_bytes = sum(a["bytes"] for l in manifest["logs"] for a in l["artifacts"])
    report = {
        "phase": "2D", "run_label": RUN_LABEL, "ok": not errs,
        "manifest_path": result["manifest_path"], "publish_dir": result["publish_dir"],
        "artifact_count": artifact_count, "total_bytes": total_bytes,
        "drawn_with_artifacts": sum(1 for l in manifest["logs"] if l["drawn"] and l["artifacts"]),
        "partial_logs": sorted(partials),
        "benchmark_s": {"assemble": round(t_assemble, 4), "publish": round(t_publish, 4),
                        "validate": round(t_validate, 4), "total": round(time.perf_counter() - t0, 4)},
        "validation_errors": errs,
    }
    (publish_dir / "_phase2d_publish_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")

    print("== Phase-2D all-50 real manifest publish ==")
    print("  published manifest: %s" % result["manifest_path"])
    print("  mock_example: %s | counts 58/50/1/7: %s" % (
        manifest["mock_example"],
        [manifest["summary"][k] for k in ("total_logs", "drawn_count", "covered_count", "blocked_count")]))
    print("  artifacts: %d | total_bytes: %d | drawn_with_artifacts: %d/50"
          % (artifact_count, total_bytes, report["drawn_with_artifacts"]))
    print("  partial_logs: %s" % sorted(partials))
    print("  benchmark(s): %s" % report["benchmark_s"])
    if errs:
        print("  VALIDATION FAILED:")
        for e in errs:
            print("    - " + e)
        return 1
    print("  VALIDATION PASSED: schema-valid, 58/50/1/7, all drawn have published finals,")
    print("    log3 owner-confirmed, log7 PARTIAL, log14 covered, 7 blocked clean, debt warned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
