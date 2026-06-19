"""Phase-2B unified-50 render + publish runner -- FEASIBILITY GATE (STOPS when unsafe).

Goal (when possible): render the current 50 DRAWN logs into ONE authoritative directory and
run the Phase-2A publisher to emit a real manifest (mock_example:false, real sha256/bytes).

This runner is a HARD GATE: it refuses to render/publish unless ALL 50 drawn logs have a
single authoritative render path. It will NOT publish a partial set as if it were 50, and it
changes NO geometry / solver / fixtures (those are forbidden). The drawn-log TRUTH is read
from the committed manifest -- never inferred from PNG filenames.

CURRENT DETERMINATION = STOP. The 37 `NEW_TARGETS` render authoritatively via the callout
route-assembly sweep, but the 13 `ALREADY_DRAWN` logs are EXPLICITLY EXCLUDED from that sweep
(`ALREADY_DRAWN` skip in `_is_target`) and render only through scattered, heterogeneous
per-log proofs (multi-candidate outputs; `log50` is not wired into any unified registry).
Bringing them into one authoritative path requires changing the solver (forbidden) or
non-source artifact selection (forbidden). See wiki/trueline_v2_redline_manifest_contract.md
(Phase 2B). In the STOP state this runner renders NOTHING and publishes NOTHING.

    python -m truelinev2.proof.run_redline_manifest_unified50_render_publish
"""
from __future__ import annotations

import json
import os
import re

REPO = os.getcwd()
EXAMPLE = os.path.join("truelinev2", "contracts", "examples",
                       "brenham_50_of_58_redline_manifest.example.json")
SWEEP_SRC = os.path.join("truelinev2", "proof", "run_callout_route_assembly_sweep.py")
SWEEP_DIR = os.path.join("data", "outputs", "callout_route_assembly_sweep")
TARGET_OUT = os.path.join("data", "outputs", "redline_manifest_publish",
                          "brenham_c19b565_unified50")


def _drawn_truth():
    m = json.load(open(EXAMPLE, encoding="utf-8"))
    drawn = {l["log_id"] for l in m["logs"] if l["drawn"]}
    already = {l["log_id"] for l in m["logs"] if l.get("drawn_lane") == "ALREADY_DRAWN"}
    new_targets = {l["log_id"] for l in m["logs"] if l.get("drawn_lane") == "NEW_TARGETS"}
    return drawn, already, new_targets


def _sweep_already_drawn():
    """Read the callout sweep's ALREADY_DRAWN tuple from source (no heavy import)."""
    txt = open(SWEEP_SRC, encoding="utf-8").read()
    m = re.search(r"ALREADY_DRAWN\s*=\s*\(([^)]*)\)", txt, re.DOTALL)
    return set(re.findall(r"log\d+", m.group(1))) if m else set()


def main():
    drawn, already, new_targets = _drawn_truth()
    sweep_excluded = _sweep_already_drawn()

    # The 13 ALREADY_DRAWN are exactly the logs the authoritative sweep skips.
    consistent = (already == sweep_excluded)
    sweep_renders = new_targets                     # only NEW_TARGETS get rendered by the sweep
    unified_path_for_all_50 = drawn <= sweep_renders  # would the one authoritative dir cover all 50?

    print("== Phase-2B unified-50 render + publish runner (FEASIBILITY GATE) ==\n")
    print("  drawn logs (truth, from manifest):      %d" % len(drawn))
    print("  authoritative sweep renders (NEW_TARGETS): %d" % len(new_targets))
    print("  excluded by sweep (ALREADY_DRAWN):      %d" % len(already))
    print("  manifest vs sweep ALREADY_DRAWN match:  %s" % consistent)
    print("  single authoritative path covers all 50: %s" % unified_path_for_all_50)

    if unified_path_for_all_50 and consistent:
        # Reserved for when a unified all-50 render path exists. Not reachable today.
        print("\nFEASIBLE: a unified all-50 render path exists -> render + publish would proceed.")
        print("(Wire the render+publish here once that path lands. Not implemented in the STOP state.)")
        return 0

    blocked = sorted(already, key=lambda s: int(s[3:]))
    print("\nVERDICT: STOP -- a unified, authoritative all-50 render is NOT possible without")
    print("changing geometry/solver/fixtures or making non-source artifact selections.\n")
    print("  READY (37 NEW_TARGETS): authoritative per-sheet artifacts co-located in")
    print("    %s, 1:1 with the sweep report verdicts[*].artifacts (Phase 2A.5)." % SWEEP_DIR)
    print("  BLOCKED (13 ALREADY_DRAWN): %s" % blocked)
    print("    - excluded from the callout sweep by design (ALREADY_DRAWN skip in _is_target);")
    print("    - render only via scattered, heterogeneous per-log proofs with multiple candidate")
    print("      PNGs per log (Phase 2A.5: log65=9, log51=5, log59=4, log25=3); log7 is a")
    print("      PARTIAL/representative stroke; log50 has no unified render driver.")
    print("\n  To unblock (each needs SEPARATE authorization, OUT OF SCOPE here):")
    print("    (a) an authorized unified solver pass that renders all 50 into one dir, OR")
    print("    (b) owner-confirmed canonical-artifact selection for each of the 13.")
    print("\n  NO render performed. NO manifest published. NO partial-37-as-50 claim.")
    print("  (intended publish target, NOT created: %s)" % TARGET_OUT)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
