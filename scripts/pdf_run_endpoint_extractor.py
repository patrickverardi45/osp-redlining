"""Target #27 — PDF spatial run-endpoint extractor SHADOW (default-OFF, read-only).

Primitive A from Target #26, implemented: derive structure-side run endpoints from the
plan-sheet LAYOUT (positioned text + char geometry), not from linear text order.

Per detailed sheet:
  STA callout (x,y)  ->  nearest structure-type label (TERMINAL/PORT/FLOWER/SPLICE)
                     ->  for an AP-class structure, the UNIQUE valid-AP digit-cluster
                         nearest that label (validated against the known AP id set so
                         dimensions/addresses/footages are rejected; abstain on tie)
  => record {sheet, station_ft, structure_type, ap_id|None, confidence, evidence}

`extract_run_endpoints_from_layout` is PURE (positioned words + chars in -> records out;
deterministic; never raises; abstains with reason on ambiguity — NO guessing). `main` does
the read-only PDF I/O for sheets 8 & 10 and grades the output against the hand table.

ISOLATION: lives in scripts/ only. NOT imported by the engine; no flag; no STATE; never
feeds resolve / selection / scoring / placement / geometry. Placement-free, read-only.
"""
from __future__ import annotations

import json
import math
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
    os.environ.setdefault(k, "t27")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

SCHEMA_VERSION = "pdf-run-endpoint-shadow-1"
PLAN_PDF = Path(r"C:/Nova/knowledge/TrueLine-Wiki/raw/trueline/engineering-plans/brenham/Brenham - Phase 5_07-15-25.pdf")
INDEX_JSON = ROOT / "scripts" / "ap_structure_index.json"
PAGE_OFFSET = 13

STA_RE = re.compile(r"^\d{1,3}\+\d{2}$")
# Structure-type keyword -> normalized type. TERMINAL/PORT => AP-class terminal port handhole.
STRUCT_KW = {"TERMINAL": "ap", "PORT": "ap", "FLOWER": "flower_pot", "SPLICE": "splice"}

# Tunables (documented, not fit-to-case): from Target #26 the STA<->structure gap measured
# 13-16 px; AP digit-cluster sat 6-35 px from the structure label.
STA_TO_STRUCT_TOL = 28.0
AP_NEAR_STRUCT_TOL = 45.0
AP_UNIQUE_MARGIN = 1.4    # nearest AP cluster must be < this * 2nd-nearest, else ambiguous


def _sta_ft(txt: str) -> Optional[float]:
    m = re.match(r"^(\d{1,3})\+(\d{2})$", txt)
    return float(m.group(1)) * 100 + float(m.group(2)) if m else None


def _c(o: Dict[str, Any]) -> Dict[str, Any]:
    o["cx"] = (o["x0"] + o["x1"]) / 2.0
    o["cy"] = (o["top"] + o["bottom"]) / 2.0
    return o


def _dist(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(ax - bx, ay - by)


def _cluster_digit_numbers(chars: Sequence[Dict[str, Any]]) -> List[Tuple[str, float, float]]:
    """Group positioned digit chars into numbers by same-line x-adjacency. Pure."""
    digs = sorted((c for c in chars if str(c.get("text", "")).isdigit()),
                  key=lambda d: (round(d["cy"] / 6.0), d["x0"]))
    out: List[Tuple[str, float, float]] = []
    cur: List[Dict[str, Any]] = []
    for d in digs:
        if cur and abs(d["cy"] - cur[-1]["cy"]) < 4 and (d["x0"] - cur[-1]["x1"]) < 6:
            cur.append(d)
        else:
            if cur:
                out.append(("".join(x["text"] for x in cur),
                            sum(x["cx"] for x in cur) / len(cur),
                            sum(x["cy"] for x in cur) / len(cur)))
            cur = [d]
    if cur:
        out.append(("".join(x["text"] for x in cur),
                    sum(x["cx"] for x in cur) / len(cur),
                    sum(x["cy"] for x in cur) / len(cur)))
    return out


def _recover_ap(struct_x: float, struct_y: float, num_clusters, valid_ap_ids,
                station_val: Optional[int] = None) -> Dict[str, Any]:
    """Nearest UNIQUE valid-AP digit cluster to the structure label. Abstains on tie.
    Excludes the station's own value (station-digits are not an AP — a collision when the
    station number happens to lie in the AP id range, e.g. STA 1+60 vs AP-160)."""
    cand = []
    for (txt, cx, cy) in num_clusters:
        if txt.isdigit() and int(txt) in valid_ap_ids and int(txt) != station_val:
            cand.append((int(txt), _dist(struct_x, struct_y, cx, cy)))
    cand.sort(key=lambda t: t[1])
    if not cand:
        return {"ap_id": None, "reason": "no_valid_ap_cluster_near_structure", "candidates": []}
    near = cand[0]
    if near[1] > AP_NEAR_STRUCT_TOL:
        return {"ap_id": None, "reason": f"nearest_ap_{near[0]}_beyond_tol_{near[1]:.0f}px",
                "candidates": cand[:3]}
    if len(cand) >= 2 and cand[1][1] < AP_UNIQUE_MARGIN * near[1]:
        return {"ap_id": None, "reason": f"ambiguous_ap_{near[0]}_vs_{cand[1][0]}",
                "candidates": cand[:3]}
    return {"ap_id": near[0], "reason": "unique", "candidates": cand[:3], "dist_px": round(near[1], 1)}


def extract_run_endpoints_from_layout(
    *,
    sheet: int,
    words: Sequence[Dict[str, Any]],
    chars: Sequence[Dict[str, Any]],
    valid_ap_ids: Sequence[int],
) -> List[Dict[str, Any]]:
    """PURE: positioned words+chars -> deduped run-endpoint records for one sheet."""
    valid = {int(a) for a in valid_ap_ids}
    W = [_c(dict(w)) for w in words]
    C = [_c(dict(c)) for c in chars]
    sta_words = [w for w in W if STA_RE.match(str(w.get("text", "")))]
    struct_words = [w for w in W if str(w.get("text", "")).upper() in STRUCT_KW]
    num_clusters = _cluster_digit_numbers(C)

    seen: Dict[Tuple[float, str, Optional[int]], Dict[str, Any]] = {}
    for sw in sta_words:
        station = _sta_ft(sw["text"])
        if station is None:
            continue
        if station == 0.0:
            continue  # 0+00 is a run START, not an endpoint (direction needs Primitive B)
        # nearest structure-type label
        best = None
        for st in struct_words:
            d = _dist(sw["cx"], sw["cy"], st["cx"], st["cy"])
            if best is None or d < best[1]:
                best = (st, d)
        if best is None or best[1] > STA_TO_STRUCT_TOL:
            continue
        st_word, st_d = best
        stype = STRUCT_KW[str(st_word["text"]).upper()]
        ap_id = None
        ap_ev: Dict[str, Any] = {}
        conf = "medium"
        if stype == "ap":
            ap_ev = _recover_ap(st_word["cx"], st_word["cy"], num_clusters, valid,
                                station_val=int(station))
            ap_id = ap_ev.get("ap_id")
            conf = "high" if (ap_id is not None and st_d <= 20 and ap_ev.get("reason") == "unique") else \
                   ("low" if ap_id is None else "medium")
        else:
            conf = "high" if st_d <= 16 else "medium"
        key = (station, stype, ap_id)
        rec = {
            "sheet": sheet, "station_ft": station, "structure_type": stype,
            "ap_id": ap_id, "confidence": conf,
            "evidence": {
                "sta_xy": [round(sw["cx"], 1), round(sw["cy"], 1)],
                "struct_label": st_word["text"], "struct_dist_px": round(st_d, 1),
                "ap_recovery": ap_ev or None,
            },
        }
        # keep the highest-confidence record per (station, type, ap)
        prev = seen.get(key)
        rank = {"high": 3, "medium": 2, "low": 1}
        if prev is None or rank[conf] > rank[prev["confidence"]]:
            seen[key] = rec
    return sorted(seen.values(), key=lambda r: (r["station_ft"], r["structure_type"], r["ap_id"] or -1))


# ── read-only I/O + validation gate ──────────────────────────────────────────

def _load_valid_aps() -> List[int]:
    if INDEX_JSON.exists():
        d = json.load(open(INDEX_JSON))
        return sorted(int(a) for a in d.get("aps", {}))
    return list(range(105, 169))  # fallback: known Brenham AP numeric range


def main() -> None:
    from backend.app.core import pdf_ap_route_resolver as R
    out: List[str] = []
    def p(s: str = "") -> None:
        out.append(s)

    valid_aps = _load_valid_aps()
    p("=" * 80)
    p("Target #27 — PDF spatial run-endpoint extractor (read-only; nothing placed)")
    p("=" * 80)
    p(f"schema={SCHEMA_VERSION}  valid AP universe={len(valid_aps)} (from Target #25 index)")

    try:
        import pdfplumber
    except Exception as e:
        p(f"!! pdfplumber unavailable: {e!r}"); _flush(out); return

    all_records: List[Dict[str, Any]] = []
    with pdfplumber.open(str(PLAN_PDF)) as pdf:
        for sheet in (8, 10):
            page = pdf.pages[sheet + PAGE_OFFSET - 1]
            words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
            chars = list(page.chars)
            recs = extract_run_endpoints_from_layout(
                sheet=sheet, words=words, chars=chars, valid_ap_ids=valid_aps)
            all_records.extend(recs)
            p(f"\n[SHEET {sheet}] {len(recs)} run-endpoint records:")
            for r in recs:
                p(f"   STA {r['station_ft']:.0f} -> {r['structure_type']:<10} "
                  f"ap={r['ap_id']}  conf={r['confidence']}  "
                  f"(struct '{r['evidence']['struct_label']}' @{r['evidence']['struct_dist_px']}px)")

    # ── validation gate vs hand table ────────────────────────────────────────
    hand = [(s, sta, k, a) for (s, sta, k, a) in R.BRENHAM_PH5_RUN_ENDPOINTS if s in (8, 10)]
    hand_ap = {(s, sta, a) for (s, sta, k, a) in hand if k == "ap"}
    auto_ap = {(r["sheet"], r["station_ft"], r["ap_id"]) for r in all_records
               if r["structure_type"] == "ap" and r["ap_id"] is not None}

    p("\n" + "-" * 80)
    p("VALIDATION GATE vs BRENHAM_PH5_RUN_ENDPOINTS (sheets 8 & 10, AP rows)")
    p("-" * 80)
    gate = [("sheet 10 STA 451 -> AP-163", (10, 451.0, 163)),
            ("sheet 8 STA 413 -> AP-157", (8, 413.0, 157))]
    for label, key in gate:
        p(f"   [{'PASS' if key in auto_ap else 'FAIL'}] {label}")
    reproduced = sorted(hand_ap & auto_ap)
    missed = sorted(hand_ap - auto_ap)
    extra = sorted(auto_ap - hand_ap)
    p(f"\n   hand AP rows (sh 8/10) = {len(hand_ap)}; auto AP rows = {len(auto_ap)}")
    p(f"   REPRODUCED = {reproduced}")
    p(f"   MISSED     = {missed}")
    p(f"   EXTRA      = {extra}")
    abst = [r for r in all_records if r["structure_type"] == "ap" and r["ap_id"] is None]
    p(f"   ABSTAINED (ap structure, no unique AP) = "
      f"{[(r['sheet'], r['station_ft'], r['evidence']['ap_recovery'].get('reason') if r['evidence']['ap_recovery'] else None) for r in abst]}")

    json_path = ROOT / "scripts" / "pdf_run_endpoint_extractor.json"
    json_path.write_text(json.dumps({"schema_version": SCHEMA_VERSION,
                                     "records": all_records}, indent=2), encoding="utf-8")
    _flush(out)
    print(f"[wrote {json_path}]")


def _flush(out: List[str]) -> None:
    out_path = ROOT / "scripts" / "pdf_run_endpoint_extractor.out"
    out_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))
    print(f"[wrote {out_path}]")


def _selftest() -> None:
    """Deterministic check of the PURE extractor on synthetic positioned input."""
    # STA '4+51' near a 'PORT' label, with digit cluster '163' next to it; '99' dimension noise.
    words = [
        {"text": "4+51", "x0": 100, "x1": 120, "top": 100, "bottom": 110},
        {"text": "PORT", "x0": 100, "x1": 130, "top": 112, "bottom": 122},
    ]
    chars = ([{"text": d, "x0": 100 + i * 6, "x1": 106 + i * 6, "top": 113, "bottom": 123}
              for i, d in enumerate("163")]
             + [{"text": d, "x0": 400 + i * 6, "x1": 406 + i * 6, "top": 500, "bottom": 510}
                for i, d in enumerate("99")])
    recs = extract_run_endpoints_from_layout(sheet=10, words=words, chars=chars,
                                             valid_ap_ids=[163, 157])
    assert len(recs) == 1, recs
    r = recs[0]
    assert (r["station_ft"], r["structure_type"], r["ap_id"]) == (451.0, "ap", 163), r
    assert r["confidence"] == "high", r
    # determinism
    recs2 = extract_run_endpoints_from_layout(sheet=10, words=words, chars=chars, valid_ap_ids=[163, 157])
    assert recs == recs2
    # abstain when two valid APs equidistant from the PORT label (cx~115, cy~117):
    # 163 to the left and 157 to the right, both ~26px away -> ambiguous.
    chars_amb = ([{"text": d, "x0": 78 + i * 6, "x1": 84 + i * 6, "top": 121, "bottom": 131} for i, d in enumerate("163")]
                 + [{"text": d, "x0": 134 + i * 6, "x1": 140 + i * 6, "top": 121, "bottom": 131} for i, d in enumerate("157")])
    amb = extract_run_endpoints_from_layout(sheet=10, words=words, chars=chars_amb, valid_ap_ids=[163, 157])
    assert amb and amb[0]["ap_id"] is None and "ambiguous" in amb[0]["evidence"]["ap_recovery"]["reason"], amb
    print("SELFTEST_OK: deterministic, validates AP, rejects noise, abstains on tie.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        _selftest()
    else:
        main()
