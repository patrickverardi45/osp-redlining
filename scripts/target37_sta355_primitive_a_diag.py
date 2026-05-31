"""READ-ONLY Target #37 diagnostic — WHY does Primitive A abstain at STA 355 (AP-164), sheet 12?

Instruments the PURE Primitive-A internals (pdf_run_endpoint_extractor) on sheet 12 to surface the
exact abstention point for the STA 3+55 callout, and contrasts it with the STA 3+50 -> AP-167
callout that Primitive A confirms. Pure diagnosis; no code change here; no flag/STATE/placement.
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "backend")); sys.path.insert(0, str(ROOT / "scripts"))
for k in ("TRUELINE_JWT_SECRET", "TRUELINE_AUTH_JWT_SECRET"):
    os.environ.setdefault(k, "t37")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

import pdf_run_endpoint_extractor as A

PLAN_PDF = A.PLAN_PDF
PAGE_OFFSET = 13
SHEET = 12


def main() -> None:
    valid = set(A._load_valid_aps())
    import pdfplumber
    with pdfplumber.open(str(PLAN_PDF)) as pdf:
        page = pdf.pages[SHEET + PAGE_OFFSET - 1]
        words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
        chars = list(page.chars)

    W = [A._c(dict(w)) for w in words]
    C = [A._c(dict(c)) for c in chars]
    sta_words = [w for w in W if A.STA_RE.match(str(w.get("text", "")))]
    struct_words = [w for w in W if str(w.get("text", "")).upper() in A.STRUCT_KW]
    num_clusters = A._cluster_digit_numbers(C)

    print("=" * 88)
    print("Target #37 diag — Primitive-A abstention at STA 355 (AP-164), sheet 12")
    print("=" * 88)
    print(f"STA_TO_STRUCT_TOL={A.STA_TO_STRUCT_TOL}  AP_NEAR_STRUCT_TOL={A.AP_NEAR_STRUCT_TOL}  "
          f"AP_UNIQUE_MARGIN={A.AP_UNIQUE_MARGIN}")
    print(f"sheet-12 STA callouts found = {sorted(A._sta_ft(w['text']) for w in sta_words)}")
    print(f"sheet-12 structure-kw words = {[(w['text'], round(w['cx'],0), round(w['cy'],0)) for w in struct_words]}")

    # localized AP clusters near the 350/355 region (for context)
    near_clusters = [(t, round(cx, 0), round(cy, 0)) for (t, cx, cy) in num_clusters
                     if t.isdigit() and int(t) in valid]
    print(f"valid-AP digit clusters on sheet (id, cx, cy) = {sorted(near_clusters, key=lambda z: z[0])}")

    for target_sta in (350.0, 355.0):
        print("\n" + "-" * 88)
        print(f"[STA {target_sta:.0f}]")
        cands = [w for w in sta_words if A._sta_ft(w["text"]) == target_sta]
        if not cands:
            print(f"   NO STA callout word matches {target_sta:.0f} (STA_RE / text-flow miss)")
            continue
        for sw in cands:
            print(f"   STA word '{sw['text']}' @ ({sw['cx']:.0f},{sw['cy']:.0f})")
            # step 1: nearest structure label
            best = None
            ranked = sorted(((st, A._dist(sw["cx"], sw["cy"], st["cx"], st["cy"])) for st in struct_words),
                            key=lambda t: t[1])
            best = ranked[0] if ranked else None
            print(f"      nearest 3 struct labels = "
                  f"{[(s['text'], round(d,1)) for s,d in ranked[:3]]}")
            if best is None or best[1] > A.STA_TO_STRUCT_TOL:
                print(f"      => ABSTAIN at STA->struct step: nearest struct {best[1]:.1f}px "
                      f"> tol {A.STA_TO_STRUCT_TOL} (no run-endpoint record emitted)")
                continue
            st_word, st_d = best
            stype = A.STRUCT_KW[str(st_word["text"]).upper()]
            print(f"      chosen struct '{st_word['text']}' @ ({st_word['cx']:.0f},{st_word['cy']:.0f}) "
                  f"d={st_d:.1f}px type={stype}")
            if stype != "ap":
                print(f"      => non-AP structure ({stype}); not an AP endpoint")
                continue
            # step 2: _recover_ap
            ev = A._recover_ap(st_word["cx"], st_word["cy"], num_clusters, valid, station_val=int(target_sta))
            print(f"      _recover_ap -> ap_id={ev.get('ap_id')} reason={ev.get('reason')} "
                  f"candidates={ev.get('candidates')}")
    print("\n[done]")


if __name__ == "__main__":
    main()
