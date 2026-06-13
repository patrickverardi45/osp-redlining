r"""M9.1 -- KMZ_AP_STRUCTURE_JOIN extractor proof (shipped law; zero placements).

Proves the shipped ``match/kmz_structure_join`` two-field terminal-join law is
zero-false and universal: the core holds no plan-set literals (Brenham is only a
PROFILE/FIXTURE supplied via the dialect); the two-field (AP id + splice-loc id)
join binds the controls; and AP-only / splice-only / proximity-only / missing-id
/ cross-structure-mixed inputs are REFUSED. No bore is moved; the M8.27 truth
table, the all-58 census, and the M8.10/M8.11/M8.15/M8.20/M9.0 contracts are
untouched (this proof adds files only and consults the UNWIRED extractor).

Controls: log7 (PDF 'AP-163 SPLICE LOC 46') and log42 ('AP-105 SPLICE LOC 25').

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_kmz_structure_join_proof
"""
from __future__ import annotations

import inspect
import json
import math
import os
import re
from types import SimpleNamespace
from typing import Optional, Tuple

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.kmz import BRENHAM_KMZ_DIALECT, KmzStructure, read_kmz
from truelinev2.match import kmz_structure_join as J
from truelinev2.match.kmz_structure_join import (join_terminal,
                                                 parse_terminus_pair,
                                                 terminal_anchors)
from truelinev2.proof.run_kmz_correlation_audit import resolve_kmz

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "kmz_structure_join_proof"

# the same customer-name regex the core drift-guard enforces (G1 self-check)
FORBIDDEN = re.compile(r"(?i)\b(brenham|odot|tulsa|creek|nextlink|verofy)\b")

# PDF terminus (AP id, SPLICE-LOC token). The splice-loc is an OPAQUE token, not
# an int (M9.1 audit fix: a trailing-int reduction would erase a zone/alpha id).
CONTROLS = {"log7": (163, "Splice Loc 46"), "log42": (105, "Splice Loc 25")}
# targets whose KMZ terminus anchors the join can REPORT (read-only); moving
# them stays blocked by source/matchline gates (M9.0) -- this proof moves none.
TARGET_TERMINI = {
    "log44": [(145, "Splice Loc 34")],   # one of its E/W terminals
}


def _haversine_m(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    R = 6371000.0
    (lo1, la1), (lo2, la2) = a, b
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = math.radians(la2 - la1), math.radians(lo2 - lo1)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def main() -> int:
    kmz_path, how = resolve_kmz()
    print(f"[m9.1] kmz: {kmz_path}  ({how})")
    if not os.path.isfile(kmz_path):
        print("[m9.1] STOP: KMZ missing")
        return 2
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = True

    model = read_kmz(kmz_path, BRENHAM_KMZ_DIALECT)
    tc = BRENHAM_KMZ_DIALECT.terminal_class      # the PROFILE supplies the class

    def jn(ap, sp):
        return join_terminal(model, terminal_class=tc, pdf_ap=ap,
                             pdf_splice_loc=sp)

    # G1: universal core -- no plan-set literal in the shipped join module.
    core_src = inspect.getsource(J)
    leaks = [ln.strip()[:70] for ln in core_src.splitlines() if FORBIDDEN.search(ln)]
    g1 = not leaks
    print(f"[m9.1] {'PASS' if g1 else 'FAIL'}  G1 universal core: no customer "
          f"literal in match/kmz_structure_join (leaks={leaks})")
    ok &= g1

    # G2: Brenham is only a PROFILE -- the class string comes from the dialect,
    # not the core; the core binds purely on it.
    g2 = (tc == "terminal_port_hh"
          and "terminal_port_hh" not in core_src     # not hardcoded in the law
          and "structures" in inspect.getsource(terminal_anchors))
    print(f"[m9.1] {'PASS' if g2 else 'FAIL'}  G2 profile-injected terminal "
          f"class {tc!r} (core does not hardcode it)")
    ok &= g2

    # G3: two-field join binds the controls (unique terminal, class-scoped).
    join_proof = {}
    g3 = True
    for bid, (ap, sp) in CONTROLS.items():
        r = jn(ap, sp)
        join_proof[bid] = r.to_dict()
        g3 &= (r.bound and r.anchor.kmz_class == tc
               and r.anchor.ap_id == ap
               and r.anchor.splice_loc == J._norm_token(sp))
    print(f"[m9.1] {'PASS' if g3 else 'FAIL'}  G3 two-field join BOUND on "
          f"controls: { {b: join_proof[b]['result'] for b in CONTROLS} }")
    ok &= g3

    # G4: AP-only is REFUSED (AP matches, splice-loc disagrees).
    ap_only = jn(163, "Splice Loc 99")
    g4 = ap_only.result == J.JOIN_AP_ONLY_REJECTED and ap_only.anchor is None
    print(f"[m9.1] {'PASS' if g4 else 'FAIL'}  G4 AP-only refused: {ap_only.result}")
    ok &= g4

    # G5: splice-only is REFUSED (splice matches, AP disagrees).
    spl_only = jn(99999, "Splice Loc 46")
    g5 = spl_only.result == J.JOIN_SPLICE_ONLY_REJECTED and spl_only.anchor is None
    print(f"[m9.1] {'PASS' if g5 else 'FAIL'}  G5 splice-only refused: {spl_only.result}")
    ok &= g5

    # G6: missing-id is REFUSED (no AP-only fallback when splice-loc is absent).
    miss_sp = jn(163, None)
    miss_ap = jn(None, "Splice Loc 46")
    g6 = (miss_sp.result == J.JOIN_SPLICE_MISSING
          and miss_ap.result == J.JOIN_AP_MISSING)
    print(f"[m9.1] {'PASS' if g6 else 'FAIL'}  G6 missing-id refused: "
          f"splice_missing={miss_sp.result}, ap_missing={miss_ap.result}")
    ok &= g6

    # G7: NO proximity / cross-structure mixing. Take two terminals differing in
    # BOTH ids and cross them: (t1.ap, t2.splice) must NOT bind (no single
    # structure carries both -> AP-only refusal). And the binding decision reads
    # NO coordinate (lon/lat appear only as carried metadata, never in the law).
    anchors = terminal_anchors(model, tc)
    t1 = anchors[0]
    t2 = next(a for a in anchors
              if a.ap_id != t1.ap_id and a.splice_loc != t1.splice_loc)
    crossed = jn(t1.ap_id, t2.splice_loc)
    jsrc = inspect.getsource(join_terminal)
    g7 = (crossed.result == J.JOIN_AP_ONLY_REJECTED and not crossed.bound
          and ".lon" not in jsrc and ".lat" not in jsrc)   # no coord in the law
    print(f"[m9.1] {'PASS' if g7 else 'FAIL'}  G7 no proximity/cross-mix: "
          f"(t1.ap={t1.ap_id}, t2.splice={t2.splice_loc}) -> {crossed.result}; "
          f"no coordinate read in join_terminal")
    ok &= g7

    # G8: non-co-location banked -- the same-AP splice twin is a DIFFERENT
    # structure tens-to-hundreds of m from the bound terminal (controls).
    spl_pts = {}
    for s in model.structures:
        if s.kmz_class == "splice_hh":
            for ap in s.ap_ids:
                spl_pts[ap] = (s.lon, s.lat)
    twin = {}
    for bid, (ap, sp) in CONTROLS.items():
        a = jn(ap, sp).anchor
        if a and ap in spl_pts:
            twin[bid] = round(_haversine_m((a.lon, a.lat), spl_pts[ap]), 1)
    g8 = all(twin.get(b, 0) > 25.0 for b in CONTROLS)
    print(f"[m9.1] {'PASS' if g8 else 'FAIL'}  G8 same-AP splice twin NOT "
          f"co-located: {twin} m")
    ok &= g8

    # G9: UNWIRED -- no placement-path module imports the join extractor; this
    # proof renders nothing and moves no bore.
    import truelinev2.match.engine as eng
    import truelinev2.match.symbol_conduit_lane as scl
    import truelinev2.review.reviewer_service as rsvc
    import truelinev2.service as svc
    wired = any("kmz_structure_join" in inspect.getsource(m)
                for m in (eng, scl, rsvc, svc))
    g9 = (not wired and not list(OUT_DIR.glob("*.png")))
    print(f"[m9.1] {'PASS' if g9 else 'FAIL'}  G9 UNWIRED (wired={wired}); "
          f"nothing rendered; zero bores moved")
    ok &= g9

    # G10 (M9.1 audit fix): UNIVERSALITY. The law compares opaque splice TOKENS,
    # so a non-Brenham profile with ZONE / ALPHA splice ids neither cross-binds
    # nor vanishes. Synthetic Company-Z model -- a different terminal class, a
    # different id grammar; no plan-set literal lives here.
    z = SimpleNamespace(structures=(
        KmzStructure("term_x", "ZA", (70,), "ZONE A-12", 0.0, 0.0),
        KmzStructure("term_x", "ZB", (80,), "ZONE B-12", 1.0, 1.0),
        KmzStructure("term_x", "AL", (90,), "Loc 5A", 2.0, 2.0)))

    def jz(ap, sp):
        return join_terminal(z, terminal_class="term_x", pdf_ap=ap,
                             pdf_splice_loc=sp)
    z_bind = jz(70, "Zone A-12").bound
    z_cross = jz(80, "Zone A-12").result        # AP-80 lives at B-12: no false bind
    z_alpha = jz(90, "Loc 5A").bound            # alpha id: bindable, not dropped
    g10 = (z_bind and z_cross == J.JOIN_AP_ONLY_REJECTED and z_alpha)
    print(f"[m9.1] {'PASS' if g10 else 'FAIL'}  G10 universality: zone A-12 binds "
          f"({z_bind}); cross-zone (80,'A-12')={z_cross}; alpha 'Loc 5A' binds "
          f"({z_alpha})")
    ok &= g10

    # read-only report: the join WORKS on a real target's terminus (KMZ
    # corroborates) -- but the target is NOT moved (still gated by M9.0).
    target_report = {}
    for bid, pairs in TARGET_TERMINI.items():
        target_report[bid] = [jn(ap, sp).to_dict() for ap, sp in pairs]

    report = {
        "milestone": ("truelinev2 M9.1 -- KMZ_AP_STRUCTURE_JOIN shipped "
                      "extractor (two-field terminal join; universal core + "
                      "profile; UNWIRED; zero placements)"),
        "kmz_path": kmz_path, "verdict": "PASS" if ok else "FAILURE",
        "terminal_class_from_profile": tc,
        "controls": join_proof,
        "rejections": {"ap_only": ap_only.result, "splice_only": spl_only.result,
                       "splice_missing": miss_sp.result,
                       "ap_missing": miss_ap.result,
                       "cross_structure_mix": crossed.result},
        "splice_twin_distance_m": twin,
        "target_terminus_anchors_readonly": target_report,
        "bores_moved": [],
        "unwired": not wired,
    }
    (OUT_DIR / "kmz_structure_join_proof.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\n[m9.1] controls BOUND; rejections all typed; twin {twin} m; "
          f"unwired={not wired}; moved=[]")
    print(f"[m9.1] verdict: {report['verdict']}")
    print(f"[m9.1] report -> {OUT_DIR / 'kmz_structure_join_proof.json'}")
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
