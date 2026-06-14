r"""PARENT-CHILD-RECON-2 Part B -- per-column print/sheet assignment audit (Phase 0).

For each of the 13 split parent families, decides -- WITHOUT guessing -- whether
each child segment can be assigned to a specific print sheet/frame from EXISTING
source + engine evidence. This is a read-only AUDIT/CLASSIFIER over already-shipped
evidence; it builds no new solver, places no bore, and moves no product bucket.

Evidence consumed (all ALLOWED):
  * the handwritten shared ``Print #`` + the xlsx ``notes``/column metadata
    (reconstructed from the corpus, the engine-ignored columns -- RECON-1);
  * each child's station range + current structured print;
  * the SHIPPED M8.7 station-axis evidence (``sheets_crossed`` the proven path
    lives on, ``rival_frames_containing_end``, the off-print verdict) -- read from
    the station-axis containment artifact;
  * the M8.27 truth-table lane + ``missing_evidence`` (printed-fork / source-quality).

FORBIDDEN evidence is never used: no proximity, no nearest-of-N, no length-only,
no column-order-as-assignment, no "probably sheet X", no owner assumption, no
invented OCR correction, and a shared ``Print # 10,13,14`` is NEVER treated as a
per-column assignment without proof.

Classification per child (the task's six labels):
  ASSIGNABLE_EXACTLY_ONE_PRINT_FRAME  -- engine already pins it to one sheet (placed).
  PARENT_RUN_MULTI_SHEET_REQUIRED     -- proven path needs >1 sheet / a missing
                                         sheet/matchline equation (discontinuity).
  UNASSIGNABLE_SHARED_PRINT_AMBIGUITY  -- the raw end recurs across frames and the
                                         one shared Print# never recorded the column.
  CONFLICTING_SOURCE_EVIDENCE          -- proven path lives off the referenced print
                                         (field-print vs plan-sheet).
  NEEDS_HUMAN_OCR_REREAD               -- source-quality / illegible-digit blocker.
  REVIEW_BY_DESIGN                     -- a genuine printed fork (banked human grade).

Read-only; writes one gitignored JSON. No PDF parse.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

import openpyxl

from truelinev2.config import _REPO_ROOT

CORPUS = os.environ.get("TL2_BRENHAM_CORPUS", r"C:\Nova\datasets\trueline\brenham")
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / "final_engine_truth_table.json"
CONTAIN = _REPO_ROOT / "data" / "outputs" / "station_axis_interval_containment.json"
OUT_DIR = _REPO_ROOT / "data" / "outputs" / "parent_child_print_assignment_phase0"

# The 13 split families (RECON-1, proof-reconstructed). Children in column order.
FAMILIES = {
    "bore_log13": ["log41", "log42"],
    "bore_log17": ["log43", "log44"],
    "bore_log18": ["log45", "log46", "log47"],
    "bore_log20": ["log48", "log49", "log50"],
    "bore_log21": ["log51", "log52"],
    "bore_log22": ["log53", "log54", "log55", "log56"],
    "bore_log24": ["log57", "log58"],
    "bore_log26": ["log59", "log60", "log61", "log62"],
    "bore_log28": ["log6", "log63", "log64"],
    "bore_log33": ["log65", "log66"],
    "bore_log34": ["log67", "log68"],
    "bore_log35": ["log69", "log70"],
    "bore_log40": ["log71", "log72"],
}

C_ASSIGN = "ASSIGNABLE_EXACTLY_ONE_PRINT_FRAME"
C_MULTI = "PARENT_RUN_MULTI_SHEET_REQUIRED"
C_AMBIG = "UNASSIGNABLE_SHARED_PRINT_AMBIGUITY"
C_CONFLICT = "CONFLICTING_SOURCE_EVIDENCE"
C_OCR = "NEEDS_HUMAN_OCR_REREAD"
C_REVIEW = "REVIEW_BY_DESIGN"


def _sheets_from_print(pv) -> List[int]:
    out: List[int] = []
    for n in re.findall(r"\d+", str(pv or "")):
        if int(n) not in out:
            out.append(int(n))
    return out


def load_corpus_meta() -> Dict[str, dict]:
    meta: Dict[str, dict] = {}
    for path in Path(CORPUS).glob("bore_log*.xlsx"):
        bid = path.stem.replace("bore_log", "log")
        wb = openpyxl.load_workbook(path, data_only=True)
        ws = wb.worksheets[0]
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
        header = [str(h).strip().lower() if h is not None else "" for h in rows[0]]
        ci = {n: (header.index(n) if n in header else None)
              for n in ("station", "print", "notes")}
        body = [r for r in rows[1:] if r and any(c is not None for c in r)]

        def get(r, key):
            i = ci.get(key)
            return r[i] if (i is not None and i < len(r) and r[i] is not None) else None

        stas = [str(get(r, "station")).strip() for r in body if get(r, "station") not in (None, "")]
        prints = sorted({str(get(r, "print")).strip() for r in body if get(r, "print") not in (None, "")})
        notes = [str(get(r, "notes")).strip() for r in body if get(r, "notes") not in (None, "")]
        note0 = notes[0] if notes else ""
        meta[bid] = {
            "shared_print_raw": prints[0] if prints else "",
            "shared_print_sheets": _sheets_from_print(prints[0] if prints else ""),
            "station_range": (f"{stas[0]}->{stas[-1]}" if stas else None),
            "note": note0,
            # An OCR flag that bears on the STATION/endpoint (hence sheet assignment),
            # NOT a BOC/depth ambiguity (which never changes the sheet). Requires the
            # word "station" near the ambiguity, or an explicit A+BB station token.
            "station_digit_flag": bool(
                re.search(r"station[^.]{0,40}(unclear|possible|could be|may read)", note0, re.I)
                or re.search(r"(unclear|possible)[^.]{0,15}\d+\+\d+", note0, re.I)),
        }
    return meta


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta = load_corpus_meta()
    truth = {r["bore_id"]: r for r in json.loads(TRUTH.read_text(encoding="utf-8"))["rows"]} \
        if TRUTH.is_file() else {}
    contain = {p["bore_id"]: p for p in json.loads(CONTAIN.read_text(encoding="utf-8")).get("proofs", [])} \
        if CONTAIN.is_file() else {}

    def classify(child: str) -> dict:
        m = meta.get(child, {})
        t = truth.get(child, {})
        c = contain.get(child, {})
        lane = t.get("product_lane")
        missing = (t.get("missing_evidence") or "")
        result = c.get("result")
        crossed = sorted({int(s) for s in c.get("sheets_crossed", [])})
        rivals = c.get("rival_frames_containing_end") or []
        sheet_refs = sorted({int(s) for s in (c.get("sheet_refs") or m.get("shared_print_sheets", []))})
        off_print = bool(crossed) and bool(sheet_refs) and not (set(crossed) & set(sheet_refs))

        single_child_print = len(sheet_refs) == 1
        fork_sig = bool(re.search(r"parallel run|tiebreaker|physically real", missing, re.I))
        # ---- classification over EXISTING evidence (no proximity/order/length) ----
        if lane == "PLACED_REVIEW":
            cls, why = C_ASSIGN, (f"engine already places it; the station-axis path pins "
                                  f"sheet(s) {t.get('sheets') or crossed}")
        elif fork_sig:
            cls, why = C_REVIEW, ("a genuine printed fork -- two physically real runs / a "
                                  "banked human grade; not a sheet-assignment gap")
        elif off_print:
            cls, why = C_CONFLICT, (f"the proven path lives on sheet(s) {crossed} but the field "
                                    f"print references {sheet_refs} -- field-print vs plan-sheet")
        elif result == "MULTIPLE_PATHS_PICK_CARD" and single_child_print \
                and re.search(r"matches no|source-vs-plan|no print", missing, re.I):
            cls, why = C_CONFLICT, ("already on one print, but the field span matches no run on "
                                    "that plan sheet -- field-source vs plan disagree")
        elif result == "STATION_TICK_NOT_FOUND" or "printed-evi" in missing \
                or m.get("station_digit_flag"):
            cls, why = C_OCR, ("source-quality / illegible-or-isolated STATION -- the end is not "
                               "locatable from the printed station evidence as transcribed")
        elif result == "PATH_DISCONTINUITY":
            cls, why = C_MULTI, ("the proven path needs a missing sheet's ticks or a matchline "
                                 "equation to continue -- a multi-sheet parent run")
        elif result == "FRAME_OR_SHEET_CONFLICT" and rivals:
            cls, why = C_AMBIG, (f"the raw end recurs in {len(rivals)} other frame ladder(s) "
                                 f"{[r.get('sheet') for r in rivals]}; the one shared Print# "
                                 f"never recorded which column owns which sheet")
        else:
            cls, why = C_AMBIG, ("shared single Print# across multiple columns; no engine "
                                 "evidence yet pins this child to one sheet")
        return {
            "child": child, "parent": None,
            "current_lane": lane, "completion_bucket": t.get("completion_bucket"),
            "shared_print": m.get("shared_print_raw"),
            "candidate_sheets": m.get("shared_print_sheets"),
            "current_child_print_sheets": sheet_refs,
            "station_range": m.get("station_range"),
            "note": m.get("note"),
            "engine_proven_sheets": crossed,
            "rival_frames": [r.get("sheet") for r in rivals],
            "station_axis_result": result,
            "off_print": off_print,
            "classification": cls,
            "why": why,
            "deterministic_extraction_target": cls in (C_ASSIGN, C_CONFLICT, C_MULTI),
            "owner_or_source_action_required": cls in (C_AMBIG, C_OCR, C_REVIEW, C_CONFLICT),
        }

    records: List[dict] = []
    for parent, kids in FAMILIES.items():
        for k in kids:
            rec = classify(k)
            rec["parent"] = parent
            records.append(rec)

    counts: Dict[str, int] = {}
    for r in records:
        counts[r["classification"]] = counts.get(r["classification"], 0) + 1

    # ---- gates ----
    gates = []
    g1 = len(records) == sum(len(v) for v in FAMILIES.values())
    gates.append(("G1 every child classified", g1, f"{len(records)} children"))
    # focus 1: log46 col2 is shared-print ambiguity, NOT decided by splice (splice plan-only)
    r46 = next(r for r in records if r["child"] == "log46")
    g2 = (r46["classification"] == C_AMBIG and "splice" not in r46["why"].lower())
    gates.append(("G2 log46 = shared-print ambiguity, splice not used", g2, r46["classification"]))
    # focus 3: log52 rival is sheet 10 (not 21); log69 is off-print->sheet 21
    r52 = next(r for r in records if r["child"] == "log52")
    r69 = next(r for r in records if r["child"] == "log69")
    g3 = (10 in (r52["rival_frames"] or []) and r69["off_print"]
          and 21 in r69["engine_proven_sheets"])
    gates.append(("G3 log52 rival=10 (not 21); log69 off-print to sheet 21", g3,
                  {"log52_rivals": r52["rival_frames"], "log69_proven": r69["engine_proven_sheets"]}))
    # no forbidden signal leaked into any 'why'
    forbidden = ("nearest", "proximity", "closest", "column order", "probably", "column-order")
    g4 = not any(any(f in r["why"].lower() for f in forbidden) for r in records)
    gates.append(("G4 no forbidden evidence in any classification rationale", g4, None))
    all_pass = all(g for _, g, _ in gates)

    report = {
        "milestone": "PARENT-CHILD-RECON-2 Part B -- per-column print/sheet assignment (Phase 0)",
        "verdict": "PASS" if all_pass else "FAIL",
        "evidence_artifacts": {"truth_table": str(TRUTH), "station_axis_containment": str(CONTAIN),
                               "present": {"truth": TRUTH.is_file(), "containment": CONTAIN.is_file()}},
        "classification_counts": counts,
        "families": FAMILIES,
        "children": records,
        "gates": [{"name": n, "pass": bool(g), "detail": d} for n, g, d in gates],
    }
    (OUT_DIR / "parent_child_print_assignment_phase0.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")

    print("[recon2.B] classification counts:", counts)
    for parent, kids in FAMILIES.items():
        print(f"  {parent}:")
        for k in kids:
            r = next(x for x in records if x["child"] == k)
            print(f"     {k:7} {r['current_lane'] or '?':<28} print={r['shared_print']:<14} "
                  f"-> {r['classification']}")
    for n, g, d in gates:
        print(f"[recon2.B] {'PASS' if g else 'FAIL'}  {n}")
    print(f"[recon2.B] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
