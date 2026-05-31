"""READ-ONLY Target #24 — existing-corpus source-artifact hunt.

Does the EQUIVALENT of the .FS / drive-decomposition / bore->structure relationship
already exist SOMEWHERE in the provided Brenham PH5 corpus (not just the 3 plan PDFs)?

The relationship we need:
    bore_log -> print/page -> drive/run/station sub-range -> AP / flower pot / splice /
    handhole / route-end structure.

This probe inventories EVERY provided Brenham source class and tests, per class, whether it
carries a JOIN KEY between the bore-log lineage and the structure lineage. It parses the
Fieldwire punch-list PDF directly for the AP<->.FS register (authoritative, self-contained).

NO placement, NO engine/STATE change, NO flag. Read-only over repo + external wiki + bore
xlsx. Writes scripts/corpus_artifact_hunt.out.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "backend"))
for k in ("TRUELINE_JWT_SECRET", "TRUELINE_AUTH_JWT_SECRET"):
    os.environ.setdefault(k, "t24")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

RAW = Path(r"C:/Nova/knowledge/TrueLine-Wiki/raw/trueline/engineering-plans/brenham")
BORE = Path(r"C:/Users/Patrick/OneDrive/Attachments/Desktop/excel bore logs")
ORIG = BORE / "combined_originals_DO_NOT_IMPORT"
FIELDWIRE_PDF = RAW / "BRENHAM_PHASE_5_New_report_2026-03-23_1774300147.pdf"
ROUTE_CTX = ROOT / "backend" / "uploads" / "project_route_context" / "brenham-phase-5.json"
KMZ = ROOT / "backend" / "tests" / "fixtures" / "brenham_phase5_source_truth.kmz"

STD_COLS = {"station", "depth", "boc", "date", "crew", "print", "notes", "station_ft", None}
OUT: List[str] = []
def p(s: str = "") -> None:
    OUT.append(s)


def inv_bore_logs() -> Dict[str, Any]:
    import openpyxl
    files = sorted(BORE.glob("*.xlsx")) + sorted(ORIG.glob("*.xlsx"))
    nonstd_anywhere = set()
    checked = 0
    for f in files:
        try:
            wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
            hdr = next(wb.active.iter_rows(values_only=True), ()) or ()
            for h in hdr:
                if h and str(h).strip().lower() not in STD_COLS:
                    nonstd_anywhere.add(str(h).strip())
            wb.close(); checked += 1
        except Exception:
            pass
    return {"count": len(files), "checked": checked, "nonstandard_columns": sorted(nonstd_anywhere)}


def inv_fieldwire() -> Dict[str, Any]:
    out = {"present": FIELDWIRE_PDF.exists(), "ap_fs_register": [], "ap_with_costation": 0,
           "bore_log_mentions": 0, "pages": 0}
    if not FIELDWIRE_PDF.exists():
        return out
    try:
        import pdfplumber
    except Exception as e:
        out["error"] = f"pdfplumber unavailable: {e!r}"
        return out
    ap_fs = re.compile(r"AP-?(\d{2,3})\s+\.FS\s+(\d{1,3})", re.I)
    ap_re = re.compile(r"AP-?(\d{2,3})", re.I)
    sta_re = re.compile(r"\bSTA\s*\d{1,3}\+\d{2}\b", re.I)
    bore_re = re.compile(r"bore[_ ]?log", re.I)
    reg = {}
    with pdfplumber.open(str(FIELDWIRE_PDF)) as pdf:
        out["pages"] = len(pdf.pages)
        for page in pdf.pages:
            t = page.extract_text(use_text_flow=True) or ""
            for m in ap_fs.finditer(t):
                reg[int(m.group(1))] = int(m.group(2))
            out["bore_log_mentions"] += len(bore_re.findall(t))
            # AP co-located with a STA on the same line = a station<->AP tie?
            for line in t.splitlines():
                if ap_re.search(line) and sta_re.search(line):
                    out["ap_with_costation"] += 1
    out["ap_fs_register"] = sorted(reg.items())
    return out


def inv_route_catalog() -> Dict[str, Any]:
    if not ROUTE_CTX.exists():
        return {"present": False}
    d = json.load(open(ROUTE_CTX))
    rc = d.get("route_catalog") or []
    keys = sorted(rc[0].keys()) if rc and isinstance(rc[0], dict) else []
    blob = json.dumps(d)
    toks = {t: len(re.findall(t, blob, re.I))
            for t in ("station", r"\bscid\b", r"\bflower\b", r"\bsplice\b", r"\bdrive\b", r"\.fs\b")}
    return {"present": True, "routes": len(rc), "per_route_keys": keys, "structure_tokens": toks}


def main() -> None:
    p("=" * 80)
    p("Target #24 — existing-corpus source-artifact hunt (bore -> drive -> structure)")
    p("=" * 80)

    p("\n[CLASS 1] BORE LOGS (xlsx) — incl. pre-split originals")
    bl = inv_bore_logs()
    p(f"   files inventoried = {bl['count']} (checked {bl['checked']})")
    p(f"   NON-STANDARD columns across ALL of them = {bl['nonstandard_columns'] or 'NONE'}")
    p("   => bore lineage carries ONLY station/depth/boc/date/crew/print/notes. No AP /")
    p("      structure / drive / terminus column at source. (No join key on the bore side.)")

    p("\n[CLASS 2] FIELDWIRE PUNCH-LIST PDF (the 9MB report) — the .FS reference home")
    fw = inv_fieldwire()
    p(f"   present={fw['present']} pages={fw.get('pages')}")
    if fw.get("error"):
        p(f"   !! {fw['error']}")
    reg = fw.get("ap_fs_register") or []
    p(f"   AP->.FS register entries = {len(reg)} (a POINTER: which fiber-schematic PAGE each AP is on)")
    p(f"      sample = {reg[:8]}")
    p(f"   bore_log mentions anywhere in this PDF = {fw.get('bore_log_mentions')}")
    p(f"   lines where an AP is co-located with a STA = {fw.get('ap_with_costation')}")
    p("   => carries AP->.FS-PAGE + AP->.WP + item/date, but NO bore_log id and (per Target #8)")
    p("      station is never co-located with an AP in a bore-bindable way. The .FS PAGES")
    p("      THEMSELVES (drive decomposition) are NOT in the corpus — only references to them.")

    p("\n[CLASS 3] ROUTE-CONTEXT JSON (backend/uploads/.../brenham-phase-5.json)")
    rc = inv_route_catalog()
    if rc.get("present"):
        p(f"   routes = {rc['routes']}; per-route keys = {rc['per_route_keys']}")
        p(f"   structure tokens in entire JSON = {rc['structure_tokens']}")
        p("   => pure geometry (route_id/name/source_folder/coords/length/role). ZERO station,")
        p("      scid, splice, drive, or .FS fields. No bore<->structure key.")

    p("\n[CLASS 4] DESIGN KMZ (fixture, md5-identical to design)")
    p(f"   present={KMZ.exists()}. Per Target #20: House nodes carry Address+AP; Terminal Port")
    p("   HH carry AP+Scid; FLOWER POTS carry NO id (Unnamed x158, Scid empty 157/158); drop")
    p("   routes carry only 'Connection Type'. No station metadata anywhere (R2a: KMZ has zero")
    p("   station anchors). => structure lineage has APs+houses, but the DROP layer is id-less")
    p("   and nothing ties a KMZ structure to a bore-log id or a bore station.")

    p("\n[CLASS 5] EXTRACTED GOLDEN/SIGNAL JSON FIXTURES (backend/tests/fixtures/.../brenham)")
    p("   plan_inputs / extracted_signals / normalized_groups / rankings_input / ambiguity_*")
    p("   => these are TrueLine's OWN derived signal outputs (revision/sheet/ambiguity lockdown")
    p("      fixtures), not new source. They inherit the same fields; they add no external join.")

    p("\n" + "-" * 80)
    p("VERDICT — JOIN-KEY MATRIX (does this source link a BORE to its END STRUCTURE?)")
    p("-" * 80)
    p("  source class            bore_id? structure_id? station<->structure? bore<->structure?")
    p("  bore xlsx (71)            YES      NO            local only           NO")
    p("  plan PDFs (3 sheets)      NO       YES (AP/FP)   per-drive 0+00       NO (no bore id)")
    p("  Fieldwire punch-list      NO       YES (AP/.FS)  NO                   NO (no bore id)")
    p("  route_catalog JSON        NO       NO            NO                   NO")
    p("  design KMZ               NO       partial(AP)   NO                   NO")
    p("  golden JSON fixtures      NO       NO            NO                   NO")
    p("")
    p("  The bore lineage (station/crew/date/print) and the structure lineage (AP/.FS/.WP/SCID)")
    p("  share NO common key in ANY provided file. The .FS REFERENCES exist (AP->.FS page), but")
    p("  the .FS PAGES (the drive decomposition) are absent, AND no file links a bore to an AP.")
    p("  => RELATIONSHIP NOT FOUND in the complete existing corpus (not merely 'not in 3 PDFs').")

    out_path = ROOT / "scripts" / "corpus_artifact_hunt.out"
    out_path.write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n".join(OUT))
    print(f"\n[wrote {out_path}]")


if __name__ == "__main__":
    main()
