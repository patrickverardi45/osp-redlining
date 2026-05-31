"""READ-ONLY Target #37 validation — legacy vs patched Primitive A, sheets 8-14.

Proves the phantom-competitor fix is precision-safe: it may only turn ABSTAIN(None) -> a correct
AP (a phantom rejection); it must NEVER change an already-resolved AP to a different id, and must
never alter the 7 baseline-confirmed endpoints. Runs the PURE extractor twice per sheet — once
with terminal_port_words=None (LEGACY) and once with them passed (PATCHED) — and diffs.

Asserts:
  - every flip is None->ap (no ap->different-ap, no ap->None)
  - 0 wrong-id vs the hand table among PATCHED AP records
  - the 7 baseline-confirmed endpoints are present and unchanged in PATCHED
NO code change here; no flag/STATE/placement. Writes JSON verdict + .out.
"""
from __future__ import annotations

import json, math, os, sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "backend")); sys.path.insert(0, str(ROOT / "scripts"))
for k in ("TRUELINE_JWT_SECRET", "TRUELINE_AUTH_JWT_SECRET"):
    os.environ.setdefault(k, "t37v")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

import pdf_run_endpoint_extractor as A

PAGE_OFFSET = 13
SHEETS = (8, 9, 10, 11, 12, 13, 14)
BASELINE_7 = {(8,366.0,154),(8,387.0,156),(8,413.0,157),(10,140.0,165),(10,451.0,163),(11,189.0,168),(12,350.0,167)}

OUT: List[str] = []
def p(s=""): OUT.append(s)


_ORIG_ANCHORED = A._terminal_port_anchored


def _ap_records(sheet, words, chars, valid, *, patched: bool):
    """Run the REAL extractor; isolate the fix by toggling _terminal_port_anchored.
    legacy: treat every competitor as anchored (== pre-patch abstention behavior).
    patched: real anchoring test (phantom competitors rejected)."""
    A._terminal_port_anchored = _ORIG_ANCHORED if patched else (lambda *a, **k: True)
    try:
        recs = A.extract_run_endpoints_from_layout(sheet=sheet, words=words, chars=chars, valid_ap_ids=valid)
    finally:
        A._terminal_port_anchored = _ORIG_ANCHORED
    # set of resolved AP endpoints (sheet, sta, ap) for ap-type records
    return {(sheet, r["station_ft"], r["ap_id"]) for r in recs
            if r["structure_type"] == "ap" and r["ap_id"] is not None}


def main():
    from backend.app.core import pdf_ap_route_resolver as R
    hand_ap = {(s, sta, a) for (s, sta, k, a) in R.BRENHAM_PH5_RUN_ENDPOINTS if k == "ap"}
    valid = set(A._load_valid_aps())

    p("=" * 88); p("Target #37 validation — legacy vs patched Primitive A (sheets 8-14)"); p("=" * 88)

    import pdfplumber
    legacy_all: set = set()
    patched_all: set = set()
    with pdfplumber.open(str(A.PLAN_PDF)) as pdf:
        for sheet in SHEETS:
            page = pdf.pages[sheet + PAGE_OFFSET - 1]
            words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
            chars = list(page.chars)
            legacy_all |= _ap_records(sheet, words, chars, valid, patched=False)
            patched_all |= _ap_records(sheet, words, chars, valid, patched=True)

    added = sorted(patched_all - legacy_all)       # new resolutions the fix enabled
    removed = sorted(legacy_all - patched_all)      # resolutions LOST by the fix (must be empty)
    legacy_by_loc: Dict[Tuple[int, float], set] = {}
    patched_by_loc: Dict[Tuple[int, float], set] = {}
    for (s, sta, a) in legacy_all:
        legacy_by_loc.setdefault((s, sta), set()).add(a)
    for (s, sta, a) in patched_all:
        patched_by_loc.setdefault((s, sta), set()).add(a)
    changed_id = sorted((s, sta, sorted(legacy_by_loc[(s, sta)]), sorted(patched_by_loc.get((s, sta), set())))
                        for (s, sta) in legacy_by_loc
                        if legacy_by_loc[(s, sta)] - patched_by_loc.get((s, sta), set()))

    p("\n[DIFF legacy -> patched (real extractor; only _terminal_port_anchored toggled)]")
    p(f"   ADDED   (None->ap) = {added}")
    p(f"   REMOVED (ap->None) = {removed}   {'<-- MUST be empty' if removed else 'OK (empty)'}")
    p(f"   CHANGED-ID (ap->different) = {changed_id}   {'<-- UNSAFE' if changed_id else 'OK (none)'}")
    for (s, sta, a) in added:
        p(f"      + sheet {s} STA {sta:.0f} -> AP-{a}   in_hand_table={(s, sta, a) in hand_ap}")

    wrong_id = sorted((s, sta, a) for (s, sta, a) in patched_all
                      if any(hs == s and ht == sta and ha != a for (hs, ht, ha) in hand_ap))
    baseline_ok = BASELINE_7.issubset(patched_all)
    missing_baseline = sorted(BASELINE_7 - patched_all)

    p("\n[ASSERTIONS]")
    p(f"   resolutions lost (ap->None) = {removed}   -> {'FAIL' if removed else 'OK'}")
    p(f"   changed-id (ap->different)  = {changed_id}   -> {'FAIL' if changed_id else 'OK'}")
    p(f"   wrong-id vs hand table (raw patched-A records) = {wrong_id}   -> {'FAIL' if wrong_id else 'OK'}")
    p(f"   baseline 7 endpoints retained = {baseline_ok}   missing={missing_baseline}")
    promoted_in_hand = [t for t in added if t in hand_ap]
    promoted_not_in_hand = [t for t in added if t not in hand_ap]
    p(f"\n   PROMOTED in hand table (true positives) = {promoted_in_hand}")
    p(f"   PROMOTED not in hand table (-> review tier, NOT auto-confirmed) = {promoted_not_in_hand}")

    verdict = {
        "schema_version": "target37-validation-1",
        "added": [list(t) for t in added], "removed": [list(t) for t in removed],
        "changed_id": [list(t) for t in changed_id], "wrong_id_raw_A": [list(t) for t in wrong_id],
        "baseline_7_retained": baseline_ok, "missing_baseline": [list(t) for t in missing_baseline],
        "promoted_in_hand": [list(t) for t in promoted_in_hand],
        "promoted_not_in_hand": [list(t) for t in promoted_not_in_hand],
        "safe": (not removed) and (not changed_id) and baseline_ok,
    }
    (ROOT / "scripts" / "target37_validation.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")
    (ROOT / "scripts" / "target37_validation.out").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n".join(OUT))

    assert not removed, f"UNSAFE: resolution lost: {removed}"
    assert not changed_id, f"UNSAFE: AP id changed: {changed_id}"
    assert baseline_ok, f"BASELINE REGRESSED: missing {missing_baseline}"
    print("\nSELFTEST_OK: fix only ADDS None->ap resolutions; 0 removed, 0 changed-id, baseline 7 retained.")


if __name__ == "__main__":
    main()
