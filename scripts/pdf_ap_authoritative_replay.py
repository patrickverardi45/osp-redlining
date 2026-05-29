"""READ-ONLY e2e replay for the PDF-AP AUTHORITATIVE override (Brenham PH5).

Seeds the real PH5 corpus into in-memory STATE (Desktop KMZ + 58 bore logs +
the local PDF-bearing session 0c0c9310 whose engineering-plan index points at
the 3 PH5 PDFs), runs the production matching flag set, and rebuilds TWICE:
AUTHORITATIVE OFF (baseline) then ON. Prints bore_log71/72/39/4 selection so
the override can be verified end-to-end.

NO disk/DB writes (STATE.clear()/update + in-memory rebuild). Run:
    venv/Scripts/python.exe scripts/pdf_ap_authoritative_replay.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

# Production-equivalent matching flags + the shadow flag (authoritative toggled below).
os.environ["TRUELINE_JWT_SECRET"] = "pdf-ap-auth-replay"
os.environ["TRUELINE_AUTH_JWT_SECRET"] = "pdf-ap-auth-replay-auth"
os.environ["TRUELINE_ALLOWED_ORIGINS"] = "http://localhost:3000"
for _f in (
    "TRUELINE_ABSTAIN_ON_LOCATION_MISMATCH",
    "TRUELINE_AUTO_CANDIDATE_EXPANSION",
    "TRUELINE_ABSTAIN_ON_ROUTE_COLLISION",
    "TRUELINE_ROUTE_COLLISION_ALTERNATE_SEARCH",
    "TRUELINE_EXPANDED_CANDIDATE_MATRIX",
    "TRUELINE_LOCATION_MISMATCH_MATRIX_RESCUE",
    "TRUELINE_SAME_ROUTE_WINDOW_OWNERSHIP",
    "TRUELINE_PDF_AP_ROUTE_SHADOW",
):
    os.environ[_f] = "1"

from backend import main as M  # noqa: E402
from backend.app.core.rebuild_scope import RebuildScope  # noqa: E402

DESKTOP = Path(r"C:\Users\Patrick\OneDrive\Attachments\Desktop")
KMZ = DESKTOP / "Brenham, TX - Phase 5_Design Team.kmz"
BORE = DESKTOP / "excel bore logs"
# Local session whose engineering-plan index points at the 3 PH5 PDFs on disk.
SID = "0c0c9310680442f1a14d4d5e5c23749e"
TARGETS = ["bore_log71.xlsx", "bore_log72.xlsx", "bore_log39.xlsx", "bore_log4.xlsx"]


def seed() -> None:
    rows = []
    for p in sorted(BORE.glob("*.xlsx")):
        try:
            fr = M._read_bore_log_rows(p.read_bytes(), p.name)
        except Exception:
            continue
        for r in fr:
            r["source_file"] = p.name
        rows.extend(fr)
    kb = KMZ.read_bytes()
    M.STATE.clear()
    M.STATE.update({
        "committed_rows": list(rows),
        "route_catalog": M._build_route_catalog(kb, KMZ.name),
        "address_points": M.parse_address_points_from_kml(kb, KMZ.name),
        "kmz_reference": M._build_kmz_reference(kb, KMZ.name),
        "_session_id_hint": SID,
        "engineering_plans": [],
    })


def run(tag: str) -> dict:
    seed()
    M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
    diag = list(M.STATE.get("pipeline_diag") or [])
    cov = M.STATE.get("coverage_sanity") or {}
    by = {d.get("source_file"): d for d in diag}
    print(f"\n===== {tag} =====")
    print(f"  coverage placed/abstained: {cov.get('placed_group_count')}/{cov.get('abstained_group_count')}  "
          f"schema={cov.get('schema')}")
    out = {}
    for sf in TARGETS:
        d = by.get(sf) or {}
        auth = d.get("pdf_ap_route_authoritative")
        shadow = d.get("pdf_ap_route_shadow") or {}
        print(f"  {sf:18s} selected={d.get('selected_route_id')!s:10s} "
              f"stopped_at={d.get('stopped_at')!s:36s} render={d.get('render_allowed')!s:5s} "
              f"segs={d.get('segments_returned')!s:5s} auth={'Y' if auth else '-'} "
              f"pdf_allowed={shadow.get('pdf_allowed_route_ids')}")
        out[sf] = d
    return out


off = (os.environ.__setitem__("TRUELINE_PDF_AP_ROUTE_AUTHORITATIVE", "0"), run("AUTHORITATIVE OFF (baseline)"))[1]
on = (os.environ.__setitem__("TRUELINE_PDF_AP_ROUTE_AUTHORITATIVE", "1"), run("AUTHORITATIVE ON"))[1]

print("\n===== VERDICT =====")
b71_off = (off.get("bore_log71.xlsx") or {}).get("selected_route_id")
b71_on = (on.get("bore_log71.xlsx") or {})
b39_on = (on.get("bore_log39.xlsx") or {})
print(f"  bore_log71 selected: OFF={b71_off}  ON={b71_on.get('selected_route_id')} "
      f"(render={b71_on.get('render_allowed')}, segs={b71_on.get('segments_returned')})")
print(f"  bore_log39 ON: selected={b39_on.get('selected_route_id')} stopped_at={b39_on.get('stopped_at')}")
ok71 = b71_on.get("selected_route_id") == "route_477"
ok39 = not b39_on.get("selected_route_id")
print(f"  bore_log71 -> route_477 : {'PASS' if ok71 else 'FAIL'}")
print(f"  bore_log39 abstains     : {'PASS' if ok39 else 'FAIL'}")
