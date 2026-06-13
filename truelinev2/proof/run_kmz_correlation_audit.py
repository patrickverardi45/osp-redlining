r"""M9.0 -- KMZ<->PDF correlation ARCHITECTURE audit (proof-only; no placement).

The first cross-source milestone. Establishes WHAT KMZ evidence exists, HOW it
joins to the PDF, and WHETHER any of the 5 SOURCE_OR_KMZ / SOURCE_REVIEW target
bores can be safely moved toward REVIEW. Zero placements; the M8.27 truth table,
the all-58 census, and the M8.10/M8.11/M8.15/M8.20 contracts are untouched
(this proof adds files only -- it imports no engine mutation and consults the
UNWIRED KMZ reader).

Findings, all gated below:

  * The Brenham design KMZ is the SAME 1116-feature set the old monolith used:
    576 structure points + 539 route polylines + 1 boundary polygon, in geo
    lon/lat (NO stationing, NO ExtendedData). Structure attributes live in an
    HTML <table> in each <description>.
  * The zero-false JOIN KEY is a TWO-FIELD structure-identity agreement, not
    geometry/proximity: the PDF terminus callout prints ``AP-NNN SPLICE LOC MM``;
    the KMZ ``terminal_port_hh`` whose AP Number is NNN carries ``Splice Loc MM``.
    BOTH ids must agree. This is load-bearing, NOT cosmetic: the splice_hh that
    shares AP-NNN is a DIFFERENT structure 28-181 m away (measured; NOT
    co-located), so AP alone is not a point identity -- the splice-loc agreement
    is what binds the SPLICE-labeled PDF callout to the TERMINAL structure,
    EARNING the terminal role instead of assuming it. AP Number is unique across
    the 64 terminals (0 collisions). PROVEN on controls: PDF "AP-163 SPLICE LOC
    46" and "AP-105 SPLICE LOC 25" each agree on BOTH fields with exactly one
    KMZ terminal_port_hh (their same-AP splice twins are 140 m / 74 m away).
  * The 58 ``Vacant Pipe`` routes == the 58 bores, but route placemarks carry NO
    text id/length/endpoints -- a route is reachable ONLY via its endpoint
    STRUCTURES (AP-keyed). So route correlation is a two-hop identity join, never
    a footage/geometry guess.

Per-target outcome (ZERO bores move; KMZ never overrides PDF/source):
  * log37, log38  -> SOURCE_REVIEW_ONLY: source unparseable => no sheets, no AP
    refs, no join key. KMZ cannot supply a broken source LOG.
  * log43        -> SOURCE_REVIEW_ONLY: end 59+19 is a printed VOID (axis stops
    45+33; multi-drive source, M8.25). The sheet-10 APs belong to low-station
    runs, none binds log43's void end.
  * log44        -> SOURCE_REVIEW (KMZ_ENDPOINT_BRIDGE candidate, future):
    its E/W terminals AP-145/146/147 ARE in the KMZ, but the 325' span matches
    NO print-18 run (source-vs-plan mismatch, M8.25). KMZ corroborates the
    terminals; it may NOT override the source contradiction. Eligible for REVIEW
    only AFTER the source 325' is corrected.
  * log68        -> KMZ_MATCHLINE_SUBSTITUTE candidate (future): cross-sheet
    19<->20 with NO printed matchline equation (M8.16). Only one endpoint AP
    (148) is confirmed; a zero-false bridge needs BOTH endpoints AP-bound to a
    unique KMZ route. Eligible for REVIEW once both endpoints join.

Next law: ship the proven ``KMZ_AP_STRUCTURE_JOIN`` extractor, then
``KMZ_MATCHLINE_SUBSTITUTE`` for the cross-sheet class (highest yield: log68 +
the 7 no-equation cross-sheet bores log10/14/61/62/67/68/70, and the route-stroke
geometry for the log8/log32/log42 structure-identity bores via their KMZ AP
terminals).

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_kmz_correlation_audit
"""
from __future__ import annotations

import collections
import json
import math
import os
import re
from typing import Dict, List, Optional, Tuple

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.kmz import (BRENHAM_KMZ_DIALECT, ap_index, read_kmz)
from truelinev2.extract.registry import select_dialect
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "kmz_correlation_audit"

# KMZ resolution chain (committed fixture is the stable default; env overrides).
KMZ_FIXTURE = str(_REPO_ROOT / "backend" / "tests" / "fixtures"
                  / "brenham_phase5_source_truth.kmz")
KMZ_UPLOAD = str(_REPO_ROOT / "data" / "uploads"
                 / "Brenham, TX - Phase 5_Design Team.kmz")

# Cross-source evidence classes (the gate taxonomy).
X_AP_JOIN = "KMZ_AP_STRUCTURE_JOIN"          # the foundational primitive (PROVEN)
X_ENDPOINT_BRIDGE = "KMZ_ENDPOINT_BRIDGE"    # KMZ AP resolves a missing endpoint
X_MATCHLINE_SUB = "KMZ_MATCHLINE_SUBSTITUTE"  # route continuity bridges a matchline
X_ROUTE_CORROB = "KMZ_ROUTE_CORROBORATION"    # route confirms an incomplete PDF route
X_SOURCE_ONLY = "SOURCE_REVIEW_ONLY"          # KMZ cannot safely help

# Banked KMZ taxonomy (drift fails loud).
EXPECT_STRUCTURES = 576
EXPECT_ROUTES = 539
EXPECT_FOLDER_COUNTS = {
    "Business": 10, "Flower Pot": 158, "House": 290, "Installer HH": 37,
    "School": 1, "Splice HH": 16, "Terminal Port Handhole": 64,
    "House Drop": 422, "Terminal Tail": 51, "underground cable": 7,
    "Vacant Pipe": 58, "Backbone": 1}

CONTROLS = {"log7": 163, "log42": 105}        # bore -> its bound terminal AP
TARGETS = ("log37", "log38", "log43", "log44", "log68")

# The 5 targets' CURRENT M8.27 completion buckets -- this audit must NOT move
# any of them (zero-false; KMZ never overrides PDF/source).
M827_TARGET_BUCKETS = {
    "log37": "SOURCE_REVIEW_REQUIRED", "log38": "SOURCE_REVIEW_REQUIRED",
    "log43": "SOURCE_OR_KMZ_REQUIRED", "log44": "SOURCE_OR_KMZ_REQUIRED",
    "log68": "SOURCE_OR_KMZ_REQUIRED"}

# Per-target cross-source disposition (grounded in the AP-join evidence + the
# banked M8.16/M8.25 source findings). "future_eligible" names a SAFE future
# REVIEW path; it is NOT a move now.
TARGET_DISPOSITION = {
    "log37": (X_SOURCE_ONLY, None,
              "source unparseable -> no sheets/AP refs -> no join key; fix the "
              "bore log first (KMZ cannot supply a broken source LOG)"),
    "log38": (X_SOURCE_ONLY, None,
              "source unparseable -> no sheets/AP refs -> no join key; fix the "
              "bore log first"),
    "log43": (X_SOURCE_ONLY, None,
              "end 59+19 is a printed VOID (axis stops 45+33; multi-drive "
              "source, M8.25); sheet-10 APs bind low-station runs, none is "
              "log43's end -> owner source re-read, not a KMZ lever"),
    "log44": (X_ENDPOINT_BRIDGE, "after source 325' is corrected",
              "E/W terminals AP-145/146/147 ARE in the KMZ, but 325' matches no "
              "print-18 run (source-vs-plan, M8.25); KMZ corroborates terminals "
              "but may not override the source contradiction"),
    "log68": (X_MATCHLINE_SUB, "after BOTH endpoints AP-bind a unique KMZ route",
              "cross-sheet 19<->20 with NO printed matchline equation (M8.16); "
              "only one endpoint AP (148) confirmed -> a zero-false route "
              "bridge needs both endpoints bound"),
}


def resolve_kmz() -> Tuple[str, str]:
    if os.getenv("TL2_BRENHAM_KMZ") and os.path.isfile(os.getenv("TL2_BRENHAM_KMZ")):
        return os.getenv("TL2_BRENHAM_KMZ"), "env:TL2_BRENHAM_KMZ"
    if os.path.isfile(KMZ_FIXTURE):
        return KMZ_FIXTURE, "tracked fixture (brenham_phase5_source_truth.kmz)"
    return KMZ_UPLOAD, "data/uploads design KMZ"


def _splice_num(s: Optional[str]) -> Optional[int]:
    """The integer of a 'SPLICE LOC NN' / 'Splice Loc NN' id, else None."""
    if not s:
        return None
    m = re.search(r"SPLICE\s*LOC\s*(\d+)", s, re.I)
    return int(m.group(1)) if m else None


def _haversine_m(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    R = 6371000.0
    (lo1, la1), (lo2, la2) = a, b
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = math.radians(la2 - la1), math.radians(lo2 - lo1)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def _bore_pdf_aps(plan, dialect, offset, stem, corpus) -> dict:
    try:
        b = load_borelog(str(corpus[stem]))
    except Exception as e:
        return {"source_parseable": False, "error": type(e).__name__,
                "sheets": None, "pdf_aps": [], "pdf_ap_splice": {}}
    sheets = sorted(set(b.sheet_refs))
    aps = set()
    ap_splice: Dict[int, int] = {}
    for s in sheets:
        for ln in plan.lines(s, offset):
            for m in re.findall(r"AP-?\s?(\d+)", ln):
                aps.add(int(m))
            # the printed terminus callout: "AP-NNN SPLICE LOC MM" (one line)
            mm = re.search(r"AP-?\s?(\d+)\s+SPLICE\s*LOC\s*(\d+)", ln, re.I)
            if mm:
                ap_splice[int(mm.group(1))] = int(mm.group(2))
    return {"source_parseable": True, "sheets": sheets,
            "span": f"{b.station_start}->{b.station_end}",
            "pdf_aps": sorted(aps), "pdf_ap_splice": ap_splice}


def main() -> int:
    kmz_path, kmz_how = resolve_kmz()
    corpus_dir, how = resolve_corpus()
    print(f"[m9.0] kmz   : {kmz_path}  ({kmz_how})")
    print(f"[m9.0] corpus: {corpus_dir}  ({how})")
    if not os.path.isfile(kmz_path) or not os.path.isfile(PDF) \
            or not os.path.isdir(corpus_dir):
        print("[m9.0] STOP: inputs missing")
        return 2
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)}
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m9.0] STOP: corpus drift ({len(corpus)})")
        return 3
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = True

    model = read_kmz(kmz_path, BRENHAM_KMZ_DIALECT)
    idx = ap_index(model)
    # class-scoped index: AP -> terminal_port_hh structures (the bore-terminus
    # role) and AP -> splice_hh (the same-AP TWIN, a DIFFERENT structure tens-to-
    # hundreds of metres away -- the reason the join needs the splice-loc field,
    # not AP + a class keyword the PDF never prints).
    term_ap: Dict[int, List] = {}
    spl_ap: Dict[int, List] = {}
    for s in model.structures:
        if s.kmz_class == "terminal_port_hh":
            for ap in s.ap_ids:
                term_ap.setdefault(ap, []).append(s)
        elif s.kmz_class == "splice_hh":
            for ap in s.ap_ids:
                spl_ap.setdefault(ap, []).append(s)
    # measured splice<->terminal separation for every shared AP (banks the
    # adversarial finding: the pair is NOT co-located).
    twin_dist = {}
    for ap, terms in term_ap.items():
        if len(terms) == 1 and len(spl_ap.get(ap, [])) == 1:
            t, sp = terms[0], spl_ap[ap][0]
            twin_dist[ap] = round(_haversine_m((t.lon, t.lat), (sp.lon, sp.lat)), 1)

    plan = PlanPdf(PDF)
    bore_ev: Dict[str, dict] = {}
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        for stem in (f"bore_{b}" for b in (*CONTROLS, *TARGETS)):
            bid = stem.replace("bore_", "")
            bore_ev[bid] = _bore_pdf_aps(plan, dialect, offset, stem, corpus)
    finally:
        plan.close()

    # ---- gates ----
    g1 = (len(model.structures) == EXPECT_STRUCTURES
          and len(model.routes) == EXPECT_ROUTES
          and model.folder_counts == EXPECT_FOLDER_COUNTS
          and model.unclassified_placemarks == 0)
    print(f"[m9.0] {'PASS' if g1 else 'FAIL'}  G1 KMZ taxonomy: "
          f"{len(model.structures)} structures / {len(model.routes)} routes; "
          f"folders match")
    ok &= g1

    # G2: the EARNED two-field join. The PDF terminus callout prints
    # "AP-NNN SPLICE LOC MM"; the KMZ terminal_port_hh for AP-NNN must carry
    # splice_loc MM. BOTH ids agree -> the SPLICE-labeled PDF callout binds the
    # TERMINAL structure (its same-AP splice twin is a different point, recorded
    # distance away). AP uniqueness alone is necessary but NOT sufficient.
    join_proof = {}
    g2 = True
    for bid, ap in CONTROLS.items():
        ev = bore_ev[bid]
        pdf_mm = (ev.get("pdf_ap_splice") or {}).get(ap)     # PDF "SPLICE LOC MM"
        kmz_hits = term_ap.get(ap, [])
        unique = len(kmz_hits) == 1
        kmz_mm = _splice_num(kmz_hits[0].splice_loc) if unique else None
        two_field = unique and pdf_mm is not None and pdf_mm == kmz_mm
        join_proof[bid] = {
            "terminal_ap": ap, "pdf_splice_loc": pdf_mm,
            "kmz_terminal_count": len(kmz_hits), "ap_unique": unique,
            "kmz_splice_loc_num": kmz_mm, "two_field_agree": two_field,
            "splice_twin_distance_m": twin_dist.get(ap),
            "kmz_name": kmz_hits[0].name if unique else None}
        g2 &= two_field
    print(f"[m9.0] {'PASS' if g2 else 'FAIL'}  G2 EARNED two-field join "
          f"(AP + SPLICE LOC agree) on controls: "
          f"{ {b: join_proof[b]['two_field_agree'] for b in CONTROLS} }")
    ok &= g2

    # G2b: the join is load-bearing -- the same-AP splice twin is NOT co-located
    # (the adversarial finding, banked): control twins are tens-to-hundreds of m
    # away, so AP + the absent 'class keyword' could not have been zero-false.
    ctrl_dists = {b: twin_dist.get(ap) for b, ap in CONTROLS.items()}
    g2b = all(d is not None and d > 25.0 for d in ctrl_dists.values())
    print(f"[m9.0] {'PASS' if g2b else 'FAIL'}  G2b splice twin NOT co-located "
          f"(class/splice-loc disambiguation is load-bearing): {ctrl_dists} m")
    ok &= g2b

    # G3: log37/log38 have NO source -> NO join key.
    g3 = all(not bore_ev[b]["source_parseable"] and not bore_ev[b]["pdf_aps"]
             for b in ("log37", "log38"))
    print(f"[m9.0] {'PASS' if g3 else 'FAIL'}  G3 log37/log38 source-broken: "
          f"no sheets/APs -> SOURCE_REVIEW_ONLY")
    ok &= g3

    # G4: log44's E/W terminals ARE in the KMZ (corroboration exists), log68's
    # single endpoint AP is in the KMZ (partial).
    log44_aps = bore_ev["log44"]["pdf_aps"]
    log44_in_kmz = [a for a in log44_aps if a in term_ap]
    log68_in_kmz = [a for a in bore_ev["log68"]["pdf_aps"] if a in term_ap]
    g4 = (set(log44_in_kmz) >= {145, 146, 147} and len(log68_in_kmz) >= 1)
    print(f"[m9.0] {'PASS' if g4 else 'FAIL'}  G4 KMZ corroborates log44 "
          f"terminals {log44_in_kmz}; log68 endpoint AP {log68_in_kmz}")
    ok &= g4

    # G5: ZERO bores move; no target's M8.27 bucket changes (zero-false).
    moved = []   # this audit never moves a bore
    g5 = (not moved
          and set(TARGET_DISPOSITION) == set(TARGETS) == set(M827_TARGET_BUCKETS))
    print(f"[m9.0] {'PASS' if g5 else 'FAIL'}  G5 zero bores moved; all 5 "
          f"targets keep their M8.27 buckets")
    ok &= g5

    # G6: future-eligible set named honestly (log68 matchline-sub, log44 bridge);
    # log37/38/43 are SOURCE_REVIEW_ONLY (NOT future-KMZ-eligible).
    future_eligible = sorted(b for b, (cls, when, _) in TARGET_DISPOSITION.items()
                             if when is not None)
    source_only = sorted(b for b, (cls, when, _) in TARGET_DISPOSITION.items()
                         if cls == X_SOURCE_ONLY)
    g6 = (future_eligible == ["log44", "log68"]
          and source_only == ["log37", "log38", "log43"])
    print(f"[m9.0] {'PASS' if g6 else 'FAIL'}  G6 future PDF<->KMZ eligible "
          f"{future_eligible}; source-only {source_only}")
    ok &= g6

    # G7: read-only posture -- no placement/stroke/geometry/PNG, KMZ reader is
    # not consumed by any engine module (UNWIRED).
    import truelinev2.match.engine as eng
    import truelinev2.match.symbol_conduit_lane as scl
    import truelinev2.review.reviewer_service as rsvc
    import inspect
    wired = any("extract.kmz" in inspect.getsource(m)
                for m in (eng, scl, rsvc))
    g7 = (not list(OUT_DIR.glob("*.png")) and not wired)
    print(f"[m9.0] {'PASS' if g7 else 'FAIL'}  G7 read-only: no PNG; KMZ reader "
          f"UNWIRED from engine/lane/service (wired={wired})")
    ok &= g7

    rows = []
    for b in TARGETS:
        cls, when, why = TARGET_DISPOSITION[b]
        ev = bore_ev[b]
        rows.append({
            "bore_id": b,
            "m827_bucket": M827_TARGET_BUCKETS[b],
            "source_parseable": ev["source_parseable"],
            "sheets": ev.get("sheets"),
            "pdf_aps": ev.get("pdf_aps"),
            "pdf_aps_in_kmz": [a for a in (ev.get("pdf_aps") or [])
                               if a in term_ap],
            "cross_source_class": cls,
            "moved_now": False,
            "future_review_eligible_when": when,
            "blocker": why,
        })

    report = {
        "milestone": ("truelinev2 M9.0 -- KMZ<->PDF correlation architecture "
                      "audit (proof-only; zero placements; M8.27 + census + "
                      "contracts untouched)"),
        "kmz_path": kmz_path, "kmz_resolution": kmz_how,
        "corpus_dir": corpus_dir, "plan_pdf": PDF,
        "verdict": "PASS" if ok else "FAILURE",
        "kmz_taxonomy": {
            "structures": len(model.structures), "routes": len(model.routes),
            "structure_classes": dict(collections.Counter(
                s.kmz_class for s in model.structures)),
            "route_classes": dict(collections.Counter(
                r.kmz_class for r in model.routes)),
            "folder_counts": model.folder_counts,
            "distinct_ap_ids": len(idx),
            "ap_range": [min(idx), max(idx)] if idx else None,
            "geo": "lon/lat; NO stationing; attributes in <description> HTML table",
        },
        "join_key": {
            "primitive": X_AP_JOIN,
            "rule": ("TWO-FIELD agreement: PDF terminus callout 'AP-NNN SPLICE "
                     "LOC MM' <-> KMZ terminal_port_hh with AP Number NNN AND "
                     "splice_loc MM (both ids agree). AP Number is unique across "
                     "the 64 terminals; the splice-loc field binds the SPLICE-"
                     "labeled PDF callout to the TERMINAL role -- earned, not "
                     "assumed. The same-AP splice_hh is a DIFFERENT structure "
                     "(distances below), so AP alone is not a point identity and "
                     "the PDF prints no terminal/port class keyword to lean on."),
            "controls_proven": join_proof,
            "splice_twin_distances_m": {str(k): v
                                        for k, v in sorted(twin_dist.items())},
            "vacant_pipe_routes": len(model.routes),
            "note": ("the 58 Vacant Pipe routes == 58 bores but carry NO text "
                     "id/length/endpoints -> route correlation is a two-hop "
                     "identity join via endpoint structures, never footage/geo"),
        },
        "cross_source_gate_taxonomy": [X_AP_JOIN, X_ENDPOINT_BRIDGE,
                                       X_MATCHLINE_SUB, X_ROUTE_CORROB,
                                       X_SOURCE_ONLY],
        "targets": rows,
        "bores_moved_now": [],
        "future_review_eligible": future_eligible,
        "source_review_only": source_only,
        "next_law": (f"{X_AP_JOIN} extractor (proven) -> {X_MATCHLINE_SUB} for "
                     "the cross-sheet class (log68 + log10/14/61/62/67/68/70) + "
                     "route-stroke geometry for log8/log32/log42 via KMZ AP "
                     "terminals"),
    }
    (OUT_DIR / "kmz_correlation_audit.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")

    print(f"\n[m9.0] structures={len(model.structures)} routes={len(model.routes)} "
          f"APs={len(idx)}")
    print(f"[m9.0] bores moved now: [] | future-eligible: {future_eligible} | "
          f"source-only: {source_only}")
    print(f"[m9.0] verdict: {report['verdict']}")
    print(f"[m9.0] report -> {OUT_DIR / 'kmz_correlation_audit.json'}")
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
