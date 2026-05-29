"""Trust Ledger end-to-end replay — corpus-parameterized, read-only, in-memory.

Rebuilds a corpus (KMZ design + bore-log *.xlsx set) with the production 7-flag
matching set, then runs the live trust-ledger assembler and prints the
proof/abstain/missing_proof verdict counts.

Read-only. In-memory only (STATE.clear()/update; never writes session_store.db,
never makes a production/network call). Mirrors the deterministic seed/rebuild
pattern of collision_window_v2_replay.py.

Default (no args) = Brenham PH5 known-good corpus, asserting the current-HEAD
headline 34 proven / 30 abstained / 0 missing_proof / 0 silent / 5 psg of 64.
Pass --kmz / --bore-dir to audit any other corpus the moment its data exists;
custom corpora run WITHOUT Brenham-specific assertions unless you pass --expect-*.

Usage:
  # Brenham known-good (default; asserts 34/30/0/silent 0/psg 5):
  python scripts/trust_ledger_replay.py

  # New corpus, print-only (no assertions):
  python scripts/trust_ledger_replay.py --kmz path/to/design.kmz --bore-dir path/to/bore_logs

  # New corpus with explicit expectations (asserts only what you provide):
  python scripts/trust_ledger_replay.py --kmz d.kmz --bore-dir logs \\
      --expect-proven 12 --expect-abstained 4 --expect-missing-proof 0

  # Default corpus but skip the known-good assertion (print-only):
  python scripts/trust_ledger_replay.py --no-count-assertions
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

os.environ["TRUELINE_JWT_SECRET"] = "trust-ledger-replay"
os.environ["TRUELINE_AUTH_JWT_SECRET"] = "trust-ledger-replay-auth"
os.environ["TRUELINE_ALLOWED_ORIGINS"] = "http://localhost:3000"

# Production matching flag set (all 7 ON) — matching POLICY, not corpus-specific.
os.environ["TRUELINE_ABSTAIN_ON_LOCATION_MISMATCH"] = "1"
os.environ["TRUELINE_AUTO_CANDIDATE_EXPANSION"] = "1"
os.environ["TRUELINE_ABSTAIN_ON_ROUTE_COLLISION"] = "1"
os.environ["TRUELINE_ROUTE_COLLISION_ALTERNATE_SEARCH"] = "1"
os.environ["TRUELINE_EXPANDED_CANDIDATE_MATRIX"] = "1"
os.environ["TRUELINE_LOCATION_MISMATCH_MATRIX_RESCUE"] = "1"
os.environ["TRUELINE_SAME_ROUTE_WINDOW_OWNERSHIP"] = "1"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from backend import main as M  # noqa: E402
from backend.app.core.rebuild_scope import RebuildScope  # noqa: E402

# Brenham PH5 known-good defaults (used only when --kmz / --bore-dir are omitted).
BRENHAM_KMZ = ROOT / "backend" / "tests" / "fixtures" / "brenham_phase5_source_truth.kmz"
BRENHAM_EXCEL_DIR = Path(r"C:/Users/Patrick/OneDrive/Attachments/Desktop/excel bore logs")
# Current-HEAD Brenham known-good ledger counts (see wiki log 2026-05-29).
BRENHAM_EXPECT = {"proven": 34, "abstained": 30, "missing_proof": 0, "silent": 0, "psg": 5}

# Brenham teaching rows for the spot-check block (only shown on the default corpus).
BRENHAM_SPOT_FILES = (
    "bore_log16.xlsx",
    "bore_log39.xlsx",
    "bore_log71.xlsx",
    "bore_log72.xlsx",
    "bore_log9.xlsx",
)


def parse_args(argv):
    p = argparse.ArgumentParser(
        description="Trust Ledger end-to-end replay (read-only, in-memory).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--kmz",
        default=None,
        help="Path to the KMZ/KML design file (default: Brenham PH5 fixture).",
    )
    p.add_argument(
        "--bore-dir",
        default=None,
        help="Directory of bore-log *.xlsx files (default: Brenham OneDrive dir).",
    )
    p.add_argument("--expect-proven", type=int, default=None)
    p.add_argument("--expect-abstained", type=int, default=None)
    p.add_argument("--expect-missing-proof", type=int, default=None)
    p.add_argument("--expect-silent", type=int, default=None)
    p.add_argument("--expect-psg", type=int, default=None)
    p.add_argument(
        "--no-count-assertions",
        action="store_true",
        help="Print counts only; skip every expectation check (even default Brenham).",
    )
    return p.parse_args(argv)


def _seed(kmz_path: Path, excel_dir: Path) -> int:
    """Load raw KMZ + bore-log *.xlsx into in-memory STATE. Returns the bore-log
    file count seeded. Pure in-memory; never writes to disk/DB."""
    rows = []
    xlsx_files = sorted(excel_dir.glob("*.xlsx"))
    for path in xlsx_files:
        try:
            file_rows = M._read_bore_log_rows(path.read_bytes(), path.name)
        except Exception:
            continue
        for r in file_rows:
            r["source_file"] = path.name
        rows.extend(file_rows)
    kmz_bytes = kmz_path.read_bytes()
    M.STATE.clear()
    M.STATE.update({
        "committed_rows": list(rows),
        "route_catalog": M._build_route_catalog(kmz_bytes, kmz_path.name),
        "address_points": M.parse_address_points_from_kml(kmz_bytes, kmz_path.name),
        "_session_id_hint": f"trust_ledger_replay_{uuid.uuid4().hex[:10]}",
        "engineering_plans": [],
    })
    return len(xlsx_files)


def _resolve_expectations(args, is_default_corpus: bool) -> dict:
    """Decide which count assertions apply.
    - --no-count-assertions  -> none (print-only)
    - any explicit --expect-* -> assert only those provided
    - default Brenham corpus  -> the Brenham known-good headline
    - custom corpus, no expects -> none (print-only; nothing to compare against)
    """
    if args.no_count_assertions:
        return {}
    explicit = {
        "proven": args.expect_proven,
        "abstained": args.expect_abstained,
        "missing_proof": args.expect_missing_proof,
        "silent": args.expect_silent,
        "psg": args.expect_psg,
    }
    provided = {k: v for k, v in explicit.items() if v is not None}
    if provided:
        return provided
    if is_default_corpus:
        return dict(BRENHAM_EXPECT)
    return {}


def main(argv=None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    is_default_corpus = args.kmz is None and args.bore_dir is None
    kmz_path = Path(args.kmz) if args.kmz else BRENHAM_KMZ
    excel_dir = Path(args.bore_dir) if args.bore_dir else BRENHAM_EXCEL_DIR

    # Fail clearly on missing inputs — never fabricate a corpus.
    if not kmz_path.exists():
        print(f"ERROR: KMZ/KML not found: {kmz_path}")
        return 2
    if not excel_dir.is_dir():
        print(f"ERROR: bore-log directory not found: {excel_dir}")
        return 2
    if not sorted(excel_dir.glob("*.xlsx")):
        print(f"ERROR: no *.xlsx bore logs in: {excel_dir}")
        return 2

    n_files = _seed(kmz_path, excel_dir)
    M._rebuild_field_data_outputs(scope=RebuildScope.FULL)

    diag = list(M.STATE.get("pipeline_diag") or [])
    route_catalog = list(M.STATE.get("route_catalog") or [])
    coverage_sanity = M.STATE.get("coverage_sanity")

    print("=== CORPUS ===")
    print(f"  mode     : {'default Brenham PH5' if is_default_corpus else 'custom'}")
    print(f"  kmz      : {kmz_path}")
    print(f"  bore-dir : {excel_dir}")
    print(f"  bore xlsx: {n_files} files")
    print()

    # 1) additive _diag field population check (on a placed entry)
    placed = [d for d in diag if d.get("render_allowed") is True and d.get("selected_route_id")]
    sample = placed[0] if placed else {}
    print("=== ADDITIVE _diag FIELD POPULATION (sample placed entry) ===")
    print(f"  source_file            : {sample.get('source_file')}")
    print(f"  group_id present       : {sample.get('group_id') is not None}")
    print(f"  selected_combined_score: {sample.get('selected_combined_score')}")
    print(f"  mapping_summary keys   : {sorted((sample.get('mapping_summary') or {}).keys())}")
    print(f"  candidate_rankings_top : {len(sample.get('candidate_rankings_top') or [])} entries")
    n_with_mapping = sum(1 for d in placed if (d.get('mapping_summary') or {}).get('anchored_start_ft') is not None)
    n_with_crt = sum(1 for d in placed if d.get('candidate_rankings_top'))
    print(f"  placed entries         : {len(placed)}")
    print(f"  ...with mapping anchor : {n_with_mapping}")
    print(f"  ...with candidate top  : {n_with_crt}")
    print()

    # 2) live trust-ledger assembler over real STATE
    psg_inputs = None
    try:
        psg_inputs = M._gather_mrq_plan_sheet_graph_inputs(diag, M.STATE.get("committed_rows") or [])
    except Exception as exc:
        print(f"  (PSG gather failed: {exc!r})")

    ledger = M._assemble_trust_ledger(
        diag,
        route_catalog=route_catalog,
        coverage_sanity=coverage_sanity,
        plan_sheet_graph_inputs=psg_inputs,
    )

    actual = {
        "proven": ledger["counts"]["proven"],
        "abstained": ledger["counts"]["abstained"],
        "missing_proof": ledger["counts"]["missing_proof"],
        "silent": ledger["silent_placement_count"],
        "psg": ledger["psg_warning_count"],
    }

    print("=== TRUST LEDGER COUNTS ===")
    print(f"  schema_version         : {ledger['schema_version']}")
    print(f"  row_count (groups)     : {ledger['row_count']}")
    print(f"  proven                 : {actual['proven']}")
    print(f"  abstained              : {actual['abstained']}")
    print(f"  missing_proof          : {actual['missing_proof']}")
    print(f"  silent_placement_count : {actual['silent']}")
    print(f"  psg_warning_count      : {actual['psg']}")
    cs = ledger.get("coverage_sanity_summary") or {}
    print(f"  cov placed/abstained   : {cs.get('placed_group_count')} / {cs.get('abstained_group_count')}")
    print()

    # 3) spot-check rows (Brenham teaching rows on default; first 5 by file otherwise)
    by_sf = {}
    for r in ledger["rows"]:
        sf = r.get("source_file")
        if sf and sf not in by_sf:
            by_sf[sf] = r
    spot_files = BRENHAM_SPOT_FILES if is_default_corpus else tuple(list(by_sf.keys())[:5])
    print("=== SPOT CHECKS ===")
    for sf in spot_files:
        r = by_sf.get(sf) or {}
        psg = r.get("psg_warning") or {}
        verdict = (r.get("route_index_evidence") or {}).get("verdict")
        print(f"  {str(sf):>18} | proof={str(r.get('proof_status')):<13} "
              f"| route_idx={str(verdict):<11} "
              f"| psg={psg.get('status')}")
    print()

    # 4) expectations
    expect = _resolve_expectations(args, is_default_corpus)
    if not expect:
        print("=== EXPECTATIONS: none applied (print-only) ===")
        return 0
    mismatches = {k: (expect[k], actual[k]) for k in expect if actual.get(k) != expect[k]}
    label = "/".join(f"{k}={expect[k]}" for k in expect)
    if mismatches:
        for k, (exp, act) in mismatches.items():
            print(f"  MISMATCH {k}: expected {exp}, got {act}")
        print(f"=== EXPECTATIONS ({label}): FAIL ===")
        return 2
    print(f"=== EXPECTATIONS ({label}): PASS ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
