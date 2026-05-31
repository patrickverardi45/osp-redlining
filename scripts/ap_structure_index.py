"""Target #25 — AP / structure-index SHADOW (default-OFF by construction; read-only).

Assembles the source facts the Brenham corpus DOES contain into ONE deterministic,
reusable per-AP index, so that the moment a future bore->AP (or bore->structure) clue
appears, it resolves to geometry WITHOUT re-mining the corpus. It does NOT place any
redline and proves nothing about bore<->structure (Target #24 settled that the join key
is absent) — it only pre-joins the structure-SIDE facts that already exist.

Per-AP fields assembled (each from an existing source, never invented):
  fs_page      AP -> Fiber-Schematic page         (Fieldwire punch-list register)
  wp_page      AP -> Work-Package page            (Fieldwire register)
  station_ft   AP -> DIR.BORE run-terminus station (BRENHAM_PH5_RUN_ENDPOINTS)
  print_sheet  sheet that run terminus is on       (BRENHAM_PH5_RUN_ENDPOINTS)
  latlon       AP -> Terminal Port HH lat/lon      (design KMZ point node)
  tail_route   AP -> unique Terminal Tail route    (resolve_terminal_tail_route_for_ap)

`build_ap_structure_index` is PURE (inputs -> dict, never raises, deterministic). `main`
does the read-only I/O and writes scripts/ap_structure_index.json + .out.

ISOLATION: lives in scripts/ only. NOT imported by the engine; no flag; no production
behavior; never feeds resolve / selection / scoring / placement / geometry. Placement-free.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "backend"))
for k in ("TRUELINE_JWT_SECRET", "TRUELINE_AUTH_JWT_SECRET"):
    os.environ.setdefault(k, "t25")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

SCHEMA_VERSION = "ap-structure-index-1"

RAW = Path(r"C:/Nova/knowledge/TrueLine-Wiki/raw/trueline/engineering-plans/brenham")
FIELDWIRE_PDF = RAW / "BRENHAM_PHASE_5_New_report_2026-03-23_1774300147.pdf"
KMZ = ROOT / "backend" / "tests" / "fixtures" / "brenham_phase5_source_truth.kmz"
ROUTE_CTX = ROOT / "backend" / "uploads" / "project_route_context" / "brenham-phase-5.json"


# ── PURE INDEX BUILDER (no I/O) ──────────────────────────────────────────────

def build_ap_structure_index(
    *,
    run_endpoints: Sequence[Tuple[int, float, str, Optional[int]]],
    point_features: Sequence[Dict[str, Any]],
    route_catalog: Sequence[Dict[str, Any]],
    ap_fs: Dict[int, int],
    ap_wp: Optional[Dict[int, int]] = None,
    tail_resolver=None,
) -> Dict[str, Any]:
    """Pure: assemble the per-AP structure index from already-loaded sources.

    ``tail_resolver`` is an optional callable ``(ap_id, point_features, route_catalog)
    -> route_id|None`` (i.e. ``resolve_terminal_tail_route_for_ap`` bound without
    run-length). Kept injectable so this function has no engine import. Deterministic;
    never raises. Returns {schema_version, generated_from, aps: {str(ap): record}, ...}.
    """
    ap_wp = ap_wp or {}

    # AP -> (sheet, station) from the run-endpoint table (named-AP run termini only)
    ap_station: Dict[int, Tuple[int, float]] = {}
    for (sheet, sta, kind, ap) in run_endpoints:
        if kind == "ap" and ap is not None and int(ap) not in ap_station:
            ap_station[int(ap)] = (int(sheet), float(sta))

    # AP -> KMZ Terminal Port Handhole node (numeric-named point in a 'terminal port' folder)
    ap_node: Dict[int, Dict[str, Any]] = {}
    for pf in (point_features or []):
        nm = str(pf.get("name") or "").strip()
        folder = str(pf.get("folder_path") or "").lower()
        if nm.isdigit() and "terminal port" in folder:
            ap = int(nm)
            if ap not in ap_node:
                try:
                    ap_node[ap] = {
                        "feature_id": pf.get("feature_id"),
                        "folder_path": pf.get("folder_path"),
                        "latlon": [float(pf["lat"]), float(pf["lon"])],
                    }
                except (KeyError, TypeError, ValueError):
                    pass

    # Universe of APs = union across every source
    universe = sorted(set(ap_station) | set(ap_node) | set(ap_fs) | set(ap_wp))

    records: Dict[str, Any] = {}
    for ap in universe:
        st = ap_station.get(ap)
        node = ap_node.get(ap)
        tail = None
        if tail_resolver is not None and node is not None:
            try:
                tail = tail_resolver(ap, point_features, route_catalog)
            except Exception:
                tail = None
        rec = {
            "ap": ap,
            "fs_page": ap_fs.get(ap),
            "wp_page": ap_wp.get(ap),
            "station_ft": st[1] if st else None,
            "print_sheet": st[0] if st else None,
            "latlon": node["latlon"] if node else None,
            "kmz_feature_id": node["feature_id"] if node else None,
            "kmz_folder": node["folder_path"] if node else None,
            "tail_route": tail,
        }
        coverage = {
            "fs": rec["fs_page"] is not None,
            "station": rec["station_ft"] is not None,
            "latlon": rec["latlon"] is not None,
            "tail": rec["tail_route"] is not None,
        }
        rec["coverage"] = coverage
        rec["sources"] = [k for k, v in (("fieldwire_fs", coverage["fs"]),
                                         ("plan_run_endpoint", coverage["station"]),
                                         ("kmz_node", coverage["latlon"]),
                                         ("kmz_tail", coverage["tail"])) if v]
        # geometry-ready = has a KMZ lat/lon anchor (the load-bearing field for resolution)
        rec["geometry_anchor_ready"] = coverage["latlon"]
        rec["complete_all_fields"] = all(coverage.values())
        records[str(ap)] = rec

    return {
        "schema_version": SCHEMA_VERSION,
        "ap_count": len(universe),
        "aps": records,
    }


# ── READ-ONLY I/O + COVERAGE (main) ──────────────────────────────────────────

def _parse_fieldwire_registers(pdf_path: Path) -> Tuple[Dict[int, int], Dict[int, int]]:
    fs: Dict[int, int] = {}
    wp: Dict[int, int] = {}
    if not pdf_path.exists():
        return fs, wp
    try:
        import pdfplumber
    except Exception:
        return fs, wp
    fs_re = re.compile(r"AP-?(\d{2,3})\s+\.FS\s+(\d{1,3})", re.I)
    wp_re = re.compile(r"AP-?(\d{2,3})\s+\.WP\s+(\d{1,3})", re.I)
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            t = page.extract_text(use_text_flow=True) or ""
            for m in fs_re.finditer(t):
                fs.setdefault(int(m.group(1)), int(m.group(2)))
            for m in wp_re.finditer(t):
                wp.setdefault(int(m.group(1)), int(m.group(2)))
    return fs, wp


def main() -> None:
    from backend import main as M
    from backend.app.core import pdf_ap_route_resolver as R

    out: List[str] = []
    def p(s: str = "") -> None:
        out.append(s)

    kmz_ref = M._build_kmz_reference(KMZ.read_bytes(), KMZ.name)
    point_features = kmz_ref.get("point_features") or []
    route_catalog = json.load(open(ROUTE_CTX)).get("route_catalog") or []
    ap_fs, ap_wp = _parse_fieldwire_registers(FIELDWIRE_PDF)

    def tail_resolver(ap, pfs, rc):
        return R.resolve_terminal_tail_route_for_ap(ap, pfs, rc)

    index = build_ap_structure_index(
        run_endpoints=R.BRENHAM_PH5_RUN_ENDPOINTS,
        point_features=point_features,
        route_catalog=route_catalog,
        ap_fs=ap_fs, ap_wp=ap_wp,
        tail_resolver=tail_resolver,
    )

    aps = index["aps"]
    n = index["ap_count"]
    cov = lambda f: sum(1 for r in aps.values() if r["coverage"][f])
    full = [int(a) for a, r in aps.items() if r["complete_all_fields"]]
    geo = [int(a) for a, r in aps.items() if r["geometry_anchor_ready"]]

    p("=" * 78)
    p("Target #25 — AP / structure-index shadow (read-only; nothing placed)")
    p("=" * 78)
    p(f"schema={index['schema_version']}  AP universe={n}")
    p("\n[SOURCE COVERAGE]")
    p(f"  AP -> .FS page (Fieldwire)      : {cov('fs')}/{n}")
    p(f"  AP -> station (plan run-end)    : {cov('station')}/{n}")
    p(f"  AP -> lat/lon (KMZ node)        : {cov('latlon')}/{n}")
    p(f"  AP -> terminal-tail route       : {cov('tail')}/{n}")
    p(f"  geometry-anchor-ready (latlon)  : {len(geo)}/{n}")
    p(f"  ALL FOUR fields present         : {len(full)}/{n} -> {sorted(full)}")
    p("\n[GAP PROFILE] APs by which fields they have:")
    from collections import Counter
    combo = Counter(tuple(sorted(r["sources"])) for r in aps.values())
    for c, k in sorted(combo.items(), key=lambda kv: -kv[1]):
        p(f"  {k} : {c} APs")
    p("\n[SAMPLE RECORDS]")
    for a in (sorted(full)[:1] + [aps_key for aps_key in ("157", "168", "155") if aps_key in aps]):
        a = str(a)
        if a in aps:
            p(f"  AP-{a}: {json.dumps(aps[a], default=str)}")

    json_path = ROOT / "scripts" / "ap_structure_index.json"
    json_path.write_text(json.dumps(index, indent=2, default=str), encoding="utf-8")
    out_path = ROOT / "scripts" / "ap_structure_index.out"
    out_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))
    print(f"\n[wrote {json_path}]\n[wrote {out_path}]")


def _selftest() -> None:
    """Deterministic unit check of the PURE builder (no corpus needed)."""
    run_endpoints = ((8, 413.0, "ap", 157), (9, 3810.0, "ap", 155), (10, 451.0, "ap", 163),
                     (8, 299.0, "flower_pot", None))
    points = [
        {"feature_id": "p1", "name": "157", "folder_path": "Nodes / Terminal Port Handhole",
         "lat": 30.1, "lon": -96.3},
        {"feature_id": "p2", "name": "999", "folder_path": "Nodes / Flower Pot",  # not terminal port
         "lat": 30.2, "lon": -96.4},
    ]
    idx_a = build_ap_structure_index(run_endpoints=run_endpoints, point_features=points,
                                     route_catalog=[], ap_fs={157: 8, 163: 10}, ap_wp={157: 5},
                                     tail_resolver=None)
    idx_b = build_ap_structure_index(run_endpoints=run_endpoints, point_features=points,
                                     route_catalog=[], ap_fs={157: 8, 163: 10}, ap_wp={157: 5},
                                     tail_resolver=None)
    assert idx_a == idx_b, "builder is not deterministic"
    assert idx_a["schema_version"] == SCHEMA_VERSION
    aps = idx_a["aps"]
    # universe = union of station APs {157,155,163}, fs APs {157,163}; node APs {157} (999 excluded)
    assert set(aps) == {"157", "155", "163"}, set(aps)
    assert aps["157"]["latlon"] == [30.1, -96.3] and aps["157"]["geometry_anchor_ready"] is True
    assert aps["157"]["station_ft"] == 413.0 and aps["157"]["fs_page"] == 8 and aps["157"]["wp_page"] == 5
    assert aps["155"]["latlon"] is None and aps["155"]["geometry_anchor_ready"] is False  # no node
    assert aps["163"]["tail_route"] is None  # tail_resolver=None -> always None (placement-free)
    assert all(r["tail_route"] is None for r in aps.values())
    # flower-pot node (name 999, wrong folder) must NOT enter the index
    assert "999" not in aps
    print("SELFTEST_OK: deterministic, schema-correct, abstain-safe, terminal-port-only.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        _selftest()
    else:
        main()
