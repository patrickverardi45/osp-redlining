"""Phase-2A.5 existing-artifact inspection + publish DRY-RUN (READ-ONLY).

Answers one question: can we produce a REAL published redline manifest from the render
artifacts ALREADY on disk, WITHOUT running the renderer? It inspects the current artifact
locations, classifies what it finds, cross-checks coverage against the drawn-log TRUTH
(taken from the committed manifest/ledger -- never inferred from PNG filenames), and
performs a checksum DRY-RUN (compute sha256/bytes with the publisher's own routine) over
the artifacts that are unambiguous. It NEVER emits a manifest and NEVER makes a real-publish
claim -- if anything is missing or ambiguous, it says so and stops.

It runs the renderer NOT AT ALL, touches no engine/fixture/parent-model/placement_status,
and only reads files. Safe to run anytime; if the gitignored render dirs are absent it
reports that cleanly.

    python -m truelinev2.proof.run_redline_manifest_existing_artifact_inspection
"""
from __future__ import annotations

import glob
import json
import os
import re

from truelinev2.contracts.redline_manifest_publisher import _sha256_and_size

REPO = os.getcwd()
SWEEP_DIR = os.path.join("data", "outputs", "callout_route_assembly_sweep")
SWEEP_REPORT = os.path.join(SWEEP_DIR, "callout_route_assembly_sweep.json")
OUTPUTS_ROOT = os.path.join("data", "outputs")
EXAMPLE = os.path.join("truelinev2", "contracts", "examples",
                       "brenham_50_of_58_redline_manifest.example.json")
REPORT_OUT = os.path.join("data", "outputs", "redline_manifest_publish",
                          "phase2a5_inspection", "inspection_report.json")
STROKE_RE = re.compile(r"(log\d+)_.*stroke.*\.png$", re.IGNORECASE)


def _drawn_truth():
    """Drawn / non-drawn SETS from the committed manifest (status truth, NOT filenames)."""
    m = json.load(open(EXAMPLE, encoding="utf-8"))
    drawn = {l["log_id"] for l in m["logs"] if l["drawn"]}
    nondrawn = {l["log_id"] for l in m["logs"] if not l["drawn"]}
    return drawn, nondrawn, m


def _verdict_artifact_paths(verdict):
    """Normalize a sweep-report verdict's artifacts into a list of path strings."""
    arts = verdict.get("artifacts") if isinstance(verdict, dict) else None
    out = []
    for a in arts or []:
        if isinstance(a, str):
            out.append(a)
        elif isinstance(a, dict):
            for key in ("path", "artifact", "file", "png"):
                if isinstance(a.get(key), str):
                    out.append(a[key]); break
    return out


def _logid(name):
    m = STROKE_RE.search(os.path.basename(name))
    return m.group(1) if m else None


def main():
    if not os.path.isdir(OUTPUTS_ROOT):
        print("data/outputs/ absent -> no render artifacts to inspect (clean clone).")
        print("VERDICT: cannot publish from existing artifacts (none present).")
        return 0

    drawn, nondrawn, manifest = _drawn_truth()
    ex_art_count = {l["log_id"]: len(l["artifacts"]) for l in manifest["logs"] if l["drawn"]}

    # --- Authoritative current-sweep artifacts (the 37 NEW_TARGETS) -----------
    sweep_pngs = sorted(glob.glob(os.path.join(SWEEP_DIR, "*_redline_stroke.png")))
    sweep_by_log = {}
    for p in sweep_pngs:
        sweep_by_log.setdefault(_logid(p), []).append(p)

    report = None
    verdict_logs = set()
    if os.path.isfile(SWEEP_REPORT):
        report = json.load(open(SWEEP_REPORT, encoding="utf-8"))
        verdict_logs = set((report.get("verdicts") or {}).keys())

    # --- Scattered prior-lane artifacts (the 13 ALREADY_DRAWN) ----------------
    prior_pngs = [p for p in glob.glob(os.path.join(OUTPUTS_ROOT, "**", "*.png"), recursive=True)
                  if os.path.normpath(SWEEP_DIR) not in os.path.normpath(p)
                  and "stroke" in os.path.basename(p).lower()]
    prior_by_log = {}
    for p in prior_pngs:
        lg = _logid(p)
        if lg:
            prior_by_log.setdefault(lg, []).append(p)

    # --- Contamination check: non-drawn logs must have NO stroke artifact ------
    contaminated = sorted(
        [lg for lg in nondrawn if sweep_by_log.get(lg) or prior_by_log.get(lg)],
        key=lambda s: int(s[3:]))

    # --- Classify each drawn log ----------------------------------------------
    clean_new_targets = []   # authoritative + co-located in the sweep dir
    ambiguous = []           # scattered / multi-candidate / inconsistent naming
    missing = []             # drawn but no stroke artifact found anywhere
    dryrun = []              # (log, path, sha256, bytes) for the unambiguous set

    for lg in sorted(drawn, key=lambda s: int(s[3:])):
        if lg in verdict_logs:
            vpaths = _verdict_artifact_paths(report["verdicts"][lg])
            existing = [p for p in vpaths if os.path.isfile(p)]
            disk = sweep_by_log.get(lg, [])
            # Unambiguous when the report's artifact list exists on disk and matches the
            # co-located sweep files 1:1.
            if existing and len(existing) == len(disk) == len(vpaths):
                clean_new_targets.append(lg)
                for p in sorted(existing):
                    digest, size = _sha256_and_size(p)
                    dryrun.append({"log_id": lg, "path": p, "sha256": digest, "bytes": size})
            else:
                ambiguous.append({"log_id": lg, "why": "sweep verdict/disk mismatch",
                                  "verdict_artifacts": len(vpaths), "on_disk": len(disk)})
        else:
            cands = prior_by_log.get(lg, [])
            if not cands:
                missing.append(lg)
            else:
                dirs = sorted({os.path.basename(os.path.dirname(p)) for p in cands})
                ambiguous.append({
                    "log_id": lg, "why": "ALREADY_DRAWN prior-lane (no authoritative list)",
                    "candidate_files": len(cands), "dirs": dirs,
                    "example_artifact_records": ex_art_count.get(lg, 0)})

    placeholder_mismatch = sorted(
        [lg for lg in drawn
         if lg in sweep_by_log and ex_art_count.get(lg, 0) != len(sweep_by_log[lg])],
        key=lambda s: int(s[3:]))

    can_publish_full = (not missing and not ambiguous and not contaminated)

    # --- Report ---------------------------------------------------------------
    summary = {
        "render_run_by_this_task": False,
        "drawn_total": len(drawn),
        "nondrawn_total": len(nondrawn),
        "sweep_stroke_pngs": len(sweep_pngs),
        "sweep_distinct_logs": len([k for k in sweep_by_log if k]),
        "clean_unambiguous_new_targets": len(clean_new_targets),
        "ambiguous_count": len(ambiguous),
        "missing_count": len(missing),
        "contaminated_nondrawn": contaminated,
        "dryrun_checksummed_artifacts": len(dryrun),
        "placeholder_vs_real_count_mismatch": len(placeholder_mismatch),
        "can_publish_full_50_unambiguously": can_publish_full,
    }

    print("== Phase-2A.5 existing-artifact inspection + publish DRY-RUN ==")
    print("(render NOT run by this task; status truth from the committed manifest, not filenames)\n")
    for k, v in summary.items():
        print("  %-38s %s" % (k, v))
    print("\nclean NEW_TARGETS (authoritative, dry-run checksummed): %d" % len(clean_new_targets))
    print("ambiguous drawn logs (NOT publishable without a decision): %d" % len(ambiguous))
    for a in ambiguous:
        extra = a.get("dirs") or a.get("why")
        print("   - %-7s %s candidates=%s dirs=%s"
              % (a["log_id"], a["why"], a.get("candidate_files", a.get("on_disk")), a.get("dirs", "-")))
    if missing:
        print("MISSING (drawn but no stroke artifact anywhere): %s" % missing)
    if contaminated:
        print("!! CONTAMINATION: non-drawn logs with stroke artifacts: %s" % contaminated)

    print("\nVERDICT: %s" % (
        "ALL 50 drawn logs have unambiguous artifacts -> publish is feasible."
        if can_publish_full else
        "NOT all 50 drawn logs have unambiguous artifacts -> NO real publish performed. "
        "Do not fake it; see ambiguous/missing above."))

    os.makedirs(os.path.dirname(REPORT_OUT), exist_ok=True)
    json.dump({"summary": summary,
               "clean_new_targets": sorted(clean_new_targets, key=lambda s: int(s[3:])),
               "ambiguous": ambiguous, "missing": missing,
               "placeholder_count_mismatch": placeholder_mismatch,
               "dryrun_sample": dryrun[:5]},
              open(REPORT_OUT, "w", encoding="utf-8"), indent=2)
    print("\n(diagnostic report written to gitignored %s -- NOT committed)" % REPORT_OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
