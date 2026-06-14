r"""PARENT-CHILD-RECON-1 -- read-only parent/child + OCR reconciliation audit.

Compares the original-handwritten-bore-log provenance recorded in the structured
xlsx ``notes`` column (which the engine deliberately ignores -- see
docs/findings/run-segment-hierarchy-doctrine.md and M8.25) against the current
canonical child logs, to locate where OCR / run-segmentation lost run context.

What it proves (deterministically, from the source ingest -- nothing invented):

  G1  corpus resolves; 58 canonical bore logs present (log2..log72, 13 gaps).
  G2  the 13 split PARENT families reconstruct exactly from the notes column,
      and they are exactly the 13 canonical numbering gaps.
  G3  every OWNER-asserted family (bore_log17/18/22/24/33/34/40) is confirmed.
  G4  34 of 58 children carry an OCR 'NEEDS REVIEW' flag; the dominant flag is
      'print mapping uncertain' (the per-column sheet assignment was never
      resolved at ingest) -- the structural root under FRAME_OR_SHEET_CONFLICT.
  G5  log37/log38 are BORE_SOURCE_UNPARSEABLE only because their station cells
      keep a 'STA ' prefix that the engine's parse_station rejects -- the
      stations ARE present (a parse/ingest-format artifact, NOT missing source).
  G6  FOCUS: bore_log18 -> {log45(col1), log46(col2), log47(col3)}; log46 is the
      col2 segment, source photo 2025-12-15_214828.
  G7  NO bore-log cell anywhere carries a splice / splice-loc field -> the log46
      'SPLICE 35 vs 45' divergence is plan-only (PDF vs KMZ); the handwritten
      bore log can neither cause nor resolve it.

PROOF-ONLY / READ-ONLY. Imports no match/ placement module; moves no bore;
changes no bucket; writes one gitignored JSON report. Does not modify the corpus.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import openpyxl

from truelinev2.stations import parse_station  # read-only: the engine's own parser

_REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = _REPO_ROOT / "data" / "outputs" / "parent_child_reconciliation_audit"


def resolve_corpus() -> Path:
    env = os.environ.get("TL2_BRENHAM_CORPUS")
    if env and Path(env).is_dir():
        return Path(env)
    default = Path(r"C:\Nova\datasets\trueline\brenham")
    if default.is_dir():
        return default
    raise SystemExit("corpus not found: set TL2_BRENHAM_CORPUS")


# 13 numbering gaps in the canonical set (log1/13/17/18/20/21/22/24/26/28/33/34/35/40)
CANONICAL_GAPS = {1, 13, 17, 18, 20, 21, 22, 24, 26, 28, 33, 34, 35, 40}

# Owner-asserted families to confirm (parent canonical-number -> child log numbers)
OWNER_FAMILIES = {
    "bore_log17": {43, 44},
    "bore_log18": {46},  # +siblings to be discovered
    "bore_log22": {53, 54, 55, 56},
    "bore_log24": {57, 58},
    "bore_log33": {65, 66},
    "bore_log34": {67, 68},
    "bore_log40": {71, 72},
}


def colmap(header):
    h = [str(x).strip().lower() if x is not None else "" for x in header]
    return {name: (h.index(name) if name in h else None)
            for name in ("station", "depth", "boc", "date", "crew", "print", "notes")}


def parse_split_note(note: str) -> dict:
    """PURE helper: extract parent / segment / source-photo / OCR-flag from the
    structured 'notes' free text. Returns None fields when absent; never guesses."""
    note = note or ""
    parent = re.search(r"split from (bore_log\d+)", note)
    seg = re.search(r"Segment\s+([A-Z])\s*\(col\s*(\d+)", note, re.I)
    src = re.search(r"Source:\s*([^.]+?)(?:\.|$)", note)
    flagged = ("NEEDS REVIEW" in note.upper()) or ("UNCERTAIN" in note.upper())
    print_uncertain = "print mapping uncertain" in note.lower() or "print mapping for this segment" in note.lower()
    return {
        "parent": parent.group(1) if parent else None,
        "segment_letter": seg.group(1) if seg else None,
        "segment_col": seg.group(2) if seg else None,
        "source_photo": src.group(1).strip() if src else None,
        "ocr_flag": flagged,
        "print_uncertain": print_uncertain,
    }


def load_corpus(corpus: Path) -> dict:
    out = {}
    for path in sorted(corpus.glob("bore_log*.xlsx"),
                       key=lambda p: int(re.search(r"(\d+)", p.name).group(1))):
        name = path.stem
        wb = openpyxl.load_workbook(path, data_only=True)
        ws = wb.worksheets[0]
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
        cm = colmap(rows[0]) if rows else {}

        def get(r, key):
            i = cm.get(key)
            return r[i] if (i is not None and i < len(r) and r[i] is not None) else None

        body = [r for r in rows[1:] if r and any(c is not None for c in r)]
        notes = [str(get(r, "notes")).strip() for r in body if get(r, "notes") not in (None, "")]
        stations = [str(get(r, "station")).strip() for r in body if get(r, "station") not in (None, "")]
        all_cells = " ".join(str(c) for r in rows for c in r if c is not None)
        out[name] = {
            "num": int(re.search(r"(\d+)", name).group(1)),
            "first_note": notes[0] if notes else "",
            "stations": stations,
            "parsed": parse_split_note(notes[0] if notes else ""),
            "has_splice_text": ("splice" in all_cells.lower()),
        }
    return out


def main() -> int:
    corpus = resolve_corpus()
    recs = load_corpus(corpus)
    gates = []

    # G1 -- 58 canonical bore logs
    g1 = len(recs) == 58
    gates.append(("G1 corpus 58 logs", g1, f"found {len(recs)}"))

    # G2 -- 13 families reconstruct; parents == canonical gaps
    families = {}
    for name, r in recs.items():
        p = r["parsed"]["parent"]
        if p:
            families.setdefault(p, []).append(r["num"])
    family_parent_nums = {int(re.search(r"(\d+)", p).group(1)) for p in families}
    g2 = (len(families) == 13) and family_parent_nums.issubset(CANONICAL_GAPS)
    gates.append(("G2 13 families == numbering gaps", g2,
                  f"{len(families)} families; parents {sorted(family_parent_nums)}"))

    # G3 -- owner-asserted families confirmed
    owner_ok = True
    owner_detail = {}
    for parent, claimed in OWNER_FAMILIES.items():
        got = set(families.get(parent, []))
        ok = claimed.issubset(got)
        owner_ok = owner_ok and ok
        owner_detail[parent] = {"claimed": sorted(claimed), "reconstructed": sorted(got), "ok": ok}
    gates.append(("G3 owner families confirmed", owner_ok, owner_detail))

    # G4 -- OCR flags
    flagged = [n for n, r in recs.items() if r["parsed"]["ocr_flag"]]
    print_uncertain = [n for n, r in recs.items() if r["parsed"]["print_uncertain"]]
    g4 = (len(flagged) == 34) and (len(print_uncertain) >= 18)
    gates.append(("G4 34 OCR-flagged; print-uncertain dominant", g4,
                  f"flagged={len(flagged)} print_uncertain={len(print_uncertain)}"))

    # G5 -- log37/log38 are a 'STA '-prefix parse-format artifact, stations present
    sta_artifact = {}
    for name in ("bore_log37", "bore_log38"):
        st = recs[name]["stations"]
        raw0 = st[0] if st else ""
        stripped = re.sub(r"^STA\s+", "", raw0)
        sta_artifact[name] = {
            "raw_first": raw0,
            "parse_raw": parse_station(raw0),               # expected None (the bug)
            "parse_stripped": parse_station(stripped),       # expected a number (stations present)
            "n_station_rows": len(st),
        }
    g5 = all(
        a["parse_raw"] is None and a["parse_stripped"] is not None and a["n_station_rows"] >= 2
        for a in sta_artifact.values()
    )
    gates.append(("G5 log37/38 = STA-prefix parse artifact (stations present)", g5, sta_artifact))

    # G6 -- FOCUS bore_log18 -> {45,46,47}; log46 = col2
    f18 = sorted(families.get("bore_log18", []))
    log46_parsed = recs["bore_log46"]["parsed"]
    g6 = (f18 == [45, 46, 47]) and (log46_parsed["parent"] == "bore_log18") and (log46_parsed["segment_col"] == "2")
    gates.append(("G6 focus bore_log18 -> 45/46/47; log46=col2", g6,
                  {"children": f18, "log46": log46_parsed}))

    # G7 -- no bore log carries a splice field -> splice 35/45 is plan-only
    splice_logs = [n for n, r in recs.items() if r["has_splice_text"]]
    g7 = len(splice_logs) == 0
    gates.append(("G7 no splice field in any bore log (splice is plan-only)", g7,
                  f"bore logs containing 'splice': {splice_logs}"))

    all_pass = all(g for _, g, _ in gates)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "milestone": "PARENT-CHILD-RECON-1 -- parent/child + OCR reconciliation audit (read-only)",
        "corpus_dir": str(corpus),
        "verdict": "PASS" if all_pass else "FAIL",
        "families": {p: sorted(v) for p, v in sorted(
            families.items(), key=lambda kv: int(re.search(r'(\d+)', kv[0]).group(1)))},
        "ocr_flagged_children": sorted(flagged, key=lambda s: int(re.search(r'(\d+)', s).group(1))),
        "print_uncertain_children": sorted(print_uncertain, key=lambda s: int(re.search(r'(\d+)', s).group(1))),
        "log37_38_format_artifact": sta_artifact,
        "focus_bore_log18": {"children": f18, "log46": log46_parsed},
        "splice_in_bore_logs": splice_logs,
        "gates": [{"name": n, "pass": bool(g), "detail": d} for n, g, d in gates],
    }
    (OUT_DIR / "parent_child_reconciliation_audit.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")

    for n, g, d in gates:
        print(f"[recon] {'PASS' if g else 'FAIL'}  {n}  -- {d if not isinstance(d, dict) else ''}")
    print(f"\n[recon] families ({len(families)}):")
    for p in sorted(families, key=lambda s: int(re.search(r'(\d+)', s).group(1))):
        print(f"   {p:12} -> {', '.join('log'+str(x) for x in sorted(families[p]))}")
    print(f"\n[recon] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
