"""READ-ONLY replay proof for the PDF-AP Route Shadow Resolver (Brenham PH5).

Parses the REAL PH5 files, replicates main._build_route_catalog route-id
numbering EXACTLY (so route_ids match production, e.g. route_478), and runs the
pure resolver for the four proof-slice bore logs. Prints the target-log table.

NO writes, NO STATE, NO placement. Pure diagnostic. Run:

    venv/Scripts/python.exe scripts/pdf_ap_route_shadow_replay.py
"""
from __future__ import annotations

import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.core import pdf_ap_route_resolver as R  # noqa: E402  (backend on path)
import openpyxl  # noqa: E402

DESKTOP = Path(r"C:\Users\Patrick\OneDrive\Attachments\Desktop")
KMZ = DESKTOP / "Brenham, TX - Phase 5_Design Team.kmz"
PDFS = [DESKTOP / "Brenham - Phase 5_07-15-25.pdf", DESKTOP / "BRENHAM PH5 - 18-02-2026.pdf"]
BORE_DIR = DESKTOP / "excel bore logs"

# Hardcoded CURRENT_PACKET_PRINT_SHEET_INDEX subset (main.py:846-877) for the
# target prints — used ONLY to display the hardcoded comparison column.
HARDCODED = {
    "3": ["route_476"], "4": ["route_476", "route_479"], "5": ["route_479", "route_480"],
    "23": ["route_478"], "24": ["route_478"], "25": ["route_475"],
}
TARGETS = ["bore_log71", "bore_log72", "bore_log39", "bore_log4"]


def _strip_ns(xml_text: str) -> str:
    xml_text = re.sub(r'\sxmlns(:\w+)?="[^"]+"', "", xml_text)
    return re.sub(r"<(/?)\w+:", r"<\1", xml_text)


def _parse_coords(text: str):
    out = []
    for tok in (text or "").split():
        p = tok.split(",")
        if len(p) >= 2:
            try:
                out.append([float(p[1]), float(p[0])])  # [lat, lon]
            except ValueError:
                continue
    return out


def _dedupe(coords):
    out = []
    for c in coords:
        if not out or out[-1] != c:
            out.append(c)
    return out


def _infer_role(hint: str) -> str:
    h = hint.lower()
    if "house drop" in h:
        return "drop"
    if "terminal tail" in h:
        return "tail"
    if "underground cable" in h:
        return "backbone"
    if "vacant" in h:
        return "vacant"
    return ""


def build_catalog_and_points():
    """Replicates main._build_route_catalog id numbering + collects point nodes."""
    data = zipfile.ZipFile(KMZ).read(
        [n for n in zipfile.ZipFile(KMZ).namelist() if n.lower().endswith(".kml")][0]
    ).decode("utf-8", "replace")
    root = ET.fromstring(_strip_ns(data))
    pmap = {c: p for p in root.iter() for c in p}

    def folder_path(el):
        names, cur = [], el
        while cur is not None:
            tag = cur.tag.split("}")[-1]
            if tag in ("Folder", "Document"):
                nm = (cur.findtext("name") or "").strip()
                names.append(nm)
            cur = pmap.get(cur)
        return list(reversed(names))

    routes, points, counter = [], [], 0
    for pm in root.iter("Placemark"):
        name = (pm.findtext("name") or "").strip() or "Unnamed Route"
        fnames = folder_path(pm)
        source_folder = " / ".join(fnames[1:]) if len(fnames) > 1 else (fnames[0] if fnames else "")
        for ls in pm.iter("LineString"):
            coords = _dedupe(_parse_coords(ls.findtext("coordinates") or ""))
            if len(coords) < 2:
                continue
            counter += 1
            routes.append({
                "route_id": f"route_{counter}", "route_name": name, "source_folder": source_folder,
                "route_role": _infer_role(source_folder + " " + name), "coords": coords,
                "length_ft": 0.0, "point_count": len(coords),
            })
        for pt in pm.iter("Point"):
            cs = _parse_coords(pt.findtext("coordinates") or "")
            if cs:
                points.append({"name": name, "folder_path": source_folder,
                               "lat": cs[0][0], "lon": cs[0][1]})
    return routes, points, counter


def read_bore_log(stem: str):
    wb = openpyxl.load_workbook(BORE_DIR / (stem + ".xlsx"), data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    header = [str(c).strip().lower() if c is not None else "" for c in rows[0]]
    pi = header.index("print") if "print" in header else None
    ni = header.index("notes") if "notes" in header else None
    print_tokens, notes_parts = [], []
    for r in rows[1:]:
        if pi is not None and pi < len(r) and r[pi] is not None:
            for tok in re.split(r"[;,]", str(r[pi])):
                tok = tok.strip()
                if tok and tok not in print_tokens:
                    print_tokens.append(tok)
        if ni is not None and ni < len(r) and r[ni]:
            notes_parts.append(str(r[ni]))
    return print_tokens, " ".join(notes_parts)


def main():
    routes, points, total_lines = build_catalog_and_points()
    terminals = R.terminal_nodes_from_point_features(points)
    plan_pages = R.build_plan_pages_from_pdf_paths([str(p) for p in PDFS])
    sheets_resolved = sorted({p["sheet_number"] for p in plan_pages if p.get("sheet_number")})

    print(f"KMZ total LineStrings (route_counter) = {total_lines}  | routes={len(routes)}  "
          f"terminal_nodes={len(terminals)}")
    print(f"PDF plan pages parsed = {len(plan_pages)}  | sheet_numbers resolved = {sheets_resolved[:40]}")
    r478 = next((r for r in routes if r["route_id"] == "route_478"), None)
    if r478:
        print(f"route_478 identity: name='{r478['route_name']}' folder='{r478['source_folder']}' "
              f"role={r478['route_role']} pts={r478['point_count']}")
    print("=" * 120)
    hdr = ("source_file", "prints", "hardcoded", "pdf_allowed", "agreement", "reason")
    print("{:<14}{:<10}{:<26}{:<24}{:<16}{}".format(*hdr))
    print("-" * 120)

    for stem in TARGETS:
        pts, notes = read_bore_log(stem)
        hard = []
        for t in pts:
            hard.extend(HARDCODED.get(t, []))
        hard = sorted(set(hard))
        res = R.resolve_pdf_ap_routes(
            source_file=stem + ".xlsx", print_tokens=pts, notes_text=notes,
            plan_pages=plan_pages, terminal_nodes=terminals, route_catalog=routes,
            hardcoded_allowed_route_ids=hard,
        )
        print("{:<14}{:<10}{:<26}{:<24}{:<16}{}".format(
            stem, ",".join(pts), ",".join(hard) or "-",
            ",".join(res["pdf_allowed_route_ids"]) or "[]",
            res["agreement"], res["reason"]))
        nr = res.get("nearest_routes") or []
        if nr:
            top = nr[0]
            print(f"    nearest: {top['route_id']} '{top['route_name']}' [{top['source_folder']}] "
                  f"{top['dist_ft']} ft  | sheets={res.get('pdf_sheets')} aps={res.get('ap_ids_found')}")
        if res.get("notes_streets"):
            print(f"    notes_streets={res['notes_streets']}")
    print("=" * 110)
    print("NOTE: placement is UNCHANGED. This is shadow/diagnostic only.")


if __name__ == "__main__":
    main()
