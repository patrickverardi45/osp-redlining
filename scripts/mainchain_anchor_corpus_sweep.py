"""READ-ONLY Target #22 (continuation) — high-station anchor corpus sweep.

Hardens the Target #22 "station-anchor absent" verdict by scanning the TWO Brenham
PDFs NOT used by the matchline graph for the EXACT missing edge: a NAMED structure
(AP-NNN / SPLICE) stationed in the main-chain high range 4000-5950 ft, co-located on
the same page so it could anchor absolute chainage to a KMZ-locatable feature.

Files swept (external TrueLine-Wiki raw intake, read-only):
  - BRENHAM PH5 - 18-02-2026.pdf                       (small; Target #8: 3 extra plan sheets)
  - BRENHAM_PHASE_5_New_report_2026-03-23_...pdf       (large; Target #8: Fieldwire punch-list)
The 43-page plan set (Brenham - Phase 5_07-15-25.pdf) is ALREADY distilled into
brenham_plan_sheet_graph.py and is not re-swept here.

NO placement, NO engine/STATE change, NO flag. Writes scripts/mainchain_anchor_corpus_sweep.out.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
RAW = Path(r"C:/Nova/knowledge/TrueLine-Wiki/raw/trueline/engineering-plans/brenham")
PDFS = [
    "BRENHAM PH5 - 18-02-2026.pdf",
    "BRENHAM_PHASE_5_New_report_2026-03-23_1774300147.pdf",
]
# High main-chain range from Target #22: bore_log16/43 stations 4000-5950 ft.
LO, HI = 4000.0, 5950.0

_STA_RE = re.compile(r"\b(\d{2,3})\+(\d{2})\b")          # NN+NN  -> feet = NN*100+NN
_AP_RE = re.compile(r"\bAP[-\s]?(\d{2,3})\b", re.IGNORECASE)
_SPLICE_RE = re.compile(r"\bSPLICE\b", re.IGNORECASE)

OUT: List[str] = []
def p(s: str = "") -> None:
    OUT.append(s)


def _sta_ft(m: re.Match) -> float:
    return float(m.group(1)) * 100.0 + float(m.group(2))


def main() -> None:
    p("=" * 78)
    p("Target #22 continuation — high-station anchor corpus sweep (4000-5950 ft)")
    p("=" * 78)
    try:
        import pdfplumber  # noqa: F401
    except Exception as e:  # pragma: no cover
        p(f"!! pdfplumber unavailable: {e!r} — cannot sweep; verdict UNCHANGED (graph-based).")
        _flush()
        return

    import pdfplumber

    grand_hits: List[Tuple[str, int, float, str]] = []
    for fn in PDFS:
        path = RAW / fn
        p(f"\n[{fn}]  exists={path.exists()}  size={path.stat().st_size if path.exists() else 0}")
        if not path.exists():
            continue
        try:
            pdf = pdfplumber.open(str(path))
        except Exception as e:
            p(f"   !! open failed: {e!r}")
            continue
        npages = len(pdf.pages)
        high_sta_pages = 0
        ap_costation_pages = 0
        for i, page in enumerate(pdf.pages):
            try:
                txt = page.extract_text(use_text_flow=True) or ""
            except Exception:
                txt = page.extract_text() or ""
            stas = [(_sta_ft(m)) for m in _STA_RE.finditer(txt)]
            high = sorted({s for s in stas if LO <= s <= HI})
            if not high:
                continue
            high_sta_pages += 1
            aps = sorted({int(m.group(1)) for m in _AP_RE.finditer(txt)})
            has_splice = bool(_SPLICE_RE.search(txt))
            # ANCHOR candidate = a high station AND a named AP/splice on the SAME page.
            if aps or has_splice:
                ap_costation_pages += 1
                for s in high:
                    grand_hits.append((fn, i + 1, s, f"APs={aps} splice={has_splice}"))
        p(f"   pages={npages}  pages_with_high_STA(4000-5950)={high_sta_pages}  "
          f"high_STA_pages_also_naming_AP/SPLICE={ap_costation_pages}")
        pdf.close()

    p("\n[RESULT]")
    if not grand_hits:
        p("   ZERO pages carry a high-range STA (4000-5950) co-located with a named AP/SPLICE.")
        p("   => NO main-chain high-station anchor in either unchecked PDF.")
        p("   Target #22 verdict CONFIRMED + HARDENED: the station<->geometry anchor is")
        p("   ABSENT across ALL provided Brenham sources (3 PDFs + KMZ); no .FS sheet exists.")
        p("   bore_log16/43 stay BLOCKED (data-absence, not extraction). DO-NOT-WIDEN intact.")
    else:
        p(f"   {len(grand_hits)} co-location candidate(s) — REVIEW (may upgrade the verdict):")
        for fn, pg, s, info in grand_hits[:40]:
            p(f"     {fn} p{pg}: STA {s:.0f} ft  {info}")
        p("   NOTE: co-location on a page is necessary but NOT sufficient — a true anchor")
        p("   also needs the AP/splice to be a KMZ node AND tied to THAT station + direction.")
    _flush()


def _flush() -> None:
    out_path = ROOT / "scripts" / "mainchain_anchor_corpus_sweep.out"
    out_path.write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n".join(OUT))
    print(f"\n[wrote {out_path}]")


if __name__ == "__main__":
    main()
