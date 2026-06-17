r"""ORIGINAL_HANDWRITTEN_PARENT_SOURCE_MODEL -- Phase 1/2 builder (read-only over the corpus; WRITES the
canonical model JSON into the REPO only -- does NOT touch the user's dataset).

Reconstructs, from each corpus child's NOTES provenance ('Segment X split from bore_logNN.xlsx.
Source: <handwritten scan>') + the engine truth table + the owner adjudication, a canonical model where the
ORIGINAL HANDWRITTEN bore log is the parent and the split rows are grouped children. The committed model
(truelinev2/ingest/parent_source/parent_source_model.json) is self-contained: the resolver/guard consume it
WITHOUT needing the user's dataset, and it is the source-of-truth for "a child may render ONLY through its
parent group". NO corpus mutation, NO loader change, NO census change.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_build_parent_source_model
"""
from __future__ import annotations
import glob, json, os, re
import openpyxl
from truelinev2.config import _REPO_ROOT
from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus

TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / "final_engine_truth_table.json"
OUT = _REPO_ROOT / "truelinev2" / "ingest" / "parent_source" / "parent_source_model.json"

# the deterministically-DRAWN frontier (32/58) -- placement_status per child entry
ALREADY_DRAWN = {"log7", "log25", "log45", "log51", "log52", "log53", "log59",
                 "log64", "log65", "log66", "log69", "log71", "log50"}
SWEEP_PRIOR = {"log6", "log11", "log12", "log29", "log36", "log41", "log46",
               "log47", "log54", "log58", "log63", "log67", "log68"}
PROMOTED = {"log9", "log10", "log23", "log37", "log39", "log72"}
RENDERED = ALREADY_DRAWN | SWEEP_PRIOR | PROMOTED
HELD = {"log48"}   # parent/child split -- held in DUPLICATE_OF_DRAWN


def _num(s):
    m = re.search(r"(\d+)", str(s))
    return int(m.group(1)) if m else 0


def read_child(path):
    ws = openpyxl.load_workbook(path, data_only=True).active
    rows = list(ws.iter_rows(values_only=True))
    hdr = [str(c).strip().lower() if c is not None else "" for c in rows[0]]
    ci = {k: (hdr.index(k) if k in hdr else None) for k in ("station", "print", "notes", "crew", "date")}
    data = [r for r in rows[1:] if any(c not in (None, "") for c in r)]

    def cells(k):
        i = ci[k]
        return [r[i] for r in data if i is not None and i < len(r) and r[i] not in (None, "")]
    stations = [str(s).strip() for s in cells("station")]
    note = str(cells("notes")[0]) if cells("notes") else ""
    return {"stations": stations, "n_rows": len(data),
            "start_station": stations[0] if stations else None,
            "end_station": stations[-1] if stations else None,
            "prints": sorted({str(p).strip() for p in cells("print")}),
            "crews": sorted({str(c).strip() for c in cells("crew")}),
            "dates": sorted({str(d)[:10] for d in cells("date")}),
            "note": note}


def main() -> int:
    cd, how = resolve_corpus()
    truth = {r["bore_id"]: r for r in json.loads(TRUTH.read_text(encoding="utf-8"))["rows"]}
    adj = {r["log_id"]: r for r in load_adjudication()["logs"]}
    files = sorted(glob.glob(os.path.join(cd, "bore_log*.xlsx")), key=_num)

    parents = {}   # source_parent_id -> parent record
    for f in files:
        stem = os.path.splitext(os.path.basename(f))[0]
        lid = f"log{_num(stem)}"
        info = read_child(f)
        note = info["note"]
        m_split = re.search(r"split from (bore_log\d+)", note)
        m_src = re.search(r"Source:\s*([^.;\n]+)", note)
        parent_id = m_split.group(1) if m_split else stem      # standalone -> its own parent
        source = m_src.group(1).strip() if m_src else None
        trow, arow = truth.get(lid, {}), adj.get(lid, {})
        ea = arow.get("endpoint_anchors") or {}
        is_split = bool(m_split)
        entry = {
            "source_entry_id": stem,
            "log_id": lid,
            "entry_role": ("child_segment" if is_split else "standalone_bore"),
            "entry_span": (f"{info['start_station']}->{info['end_station']}"
                           if info["start_station"] else None),
            "start_station": info["start_station"],
            "end_station": info["end_station"],
            "start_structure": (ea.get("start") or {}).get("structure_class"),
            "end_structure": (ea.get("end") or {}).get("structure_class"),
            # union of engine-truth sheets + owner-corrected sheets: truth can carry the source-derived
            # sheet the owner omitted (log41 renders on s2, owner said [1]) while corrected carries the
            # OCR fix the truth lacks (log68 -> [17,20], truth [19,20]); the sheet check is a soft
            # corroboration -- the span/sibling check is the real anti-mixup gate.
            "sheet_context": sorted(set(trow.get("sheets") or []) | set(arow.get("corrected_sheets") or [])),
            "truth_sheets": trow.get("sheets"),
            "corrected_sheets": arow.get("corrected_sheets"),
            "matchline_context": [m for m in re.findall(r"SEE SHEET \d+|MATCHLINE[^.;]*", note)][:4],
            "prints": info["prints"], "crews": info["crews"], "dates": info["dates"],
            "truth_span": trow.get("span"),
            "adj_status": arow.get("status"),
            "adj_corrected_span": (f"{arow.get('corrected_start')}->{arow.get('corrected_end')}"
                                   if arow.get("corrected_start") else None),
            "placement_status": ("RENDERED" if lid in RENDERED else
                                 "HELD_PARENT_CHILD" if lid in HELD else
                                 "BLOCKED_OR_UNATTEMPTED"),
            "provenance_note": note[:240],
        }
        p = parents.setdefault(parent_id, {
            "source_parent_id": parent_id, "source_file": source, "source_page": None,
            "is_split_family": False, "sibling_group_id": parent_id, "run_group_id": parent_id,
            "entries": [],
        })
        if source and not p["source_file"]:
            p["source_file"] = source
        if is_split:
            p["is_split_family"] = True
        p["entries"].append(entry)

    # finalize: segment_order by start station; ownership_disambiguation + renderable list
    for pid, p in parents.items():
        ents = sorted(p["entries"], key=lambda e: (_num(e["start_station"] or "0"),
                                                   _num((e["start_station"] or "0+0").split("+")[-1])))
        for i, e in enumerate(ents):
            e["segment_order"] = i
            others = [o for o in ents if o is not e]
            # what distinguishes this child from its siblings: span + sheet set (the discriminators that
            # MUST agree before a child may claim a route -- prevents the log48<-log50 mixup)
            e["sibling_group_id"] = pid
            e["run_group_id"] = pid
            e["ownership_disambiguation"] = {
                "by_span": e["entry_span"],
                "by_sheets": e["sheet_context"],
                "distinct_from_siblings": [
                    {"sibling": o["source_entry_id"], "span": o["entry_span"], "sheets": o["sheet_context"]}
                    for o in others],
                "span_collision_with_sibling": [
                    o["source_entry_id"] for o in others
                    if o["start_station"] == e["start_station"]],   # same start = the dangerous case
            }
        p["entries"] = ents
        p["renderable_child_entries"] = [e["source_entry_id"] for e in ents
                                         if e["placement_status"] == "RENDERED"]
        if p["is_split_family"]:
            for e in p["entries"]:
                if e["entry_role"] == "standalone_bore":
                    e["entry_role"] = "sibling_bore"

    model = {
        "model": "ORIGINAL_HANDWRITTEN_PARENT_SOURCE_MODEL",
        "doctrine": ("Original handwritten bore logs are the canonical PARENT truth. Split rows are children/"
                     "siblings/segments grouped under their parent. A child entry may be placed/rendered ONLY "
                     "through its parent group, which must disambiguate ownership (span + sheets) so a child "
                     "cannot claim a sibling's route (the log48<-log50 failure). Additive grouping layer over "
                     "the existing 58-child ingestion -- census frozen; corpus + loader unchanged."),
        "corpus_dir": cd, "corpus_resolved": how,
        "counts": {
            "parents_total": len(parents),
            "split_families": sum(1 for p in parents.values() if p["is_split_family"]),
            "standalone_parents": sum(1 for p in parents.values() if not p["is_split_family"]),
            "child_entries_total": sum(len(p["entries"]) for p in parents.values()),
        },
        "parents": [parents[k] for k in sorted(parents, key=_num)],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(model, indent=2, default=str), encoding="utf-8")
    print(f"[parent-source] wrote {OUT}")
    print(f"[parent-source] parents={model['counts']['parents_total']} "
          f"split_families={model['counts']['split_families']} "
          f"standalone={model['counts']['standalone_parents']} "
          f"children={model['counts']['child_entries_total']}")
    # show the proof family
    for p in model["parents"]:
        if p["source_parent_id"] == "bore_log20":
            print("[parent-source] bore_log20 family (the log48/log50 proof case):")
            for e in p["entries"]:
                print(f"    {e['source_entry_id']:<12} {e['log_id']:<6} span={e['entry_span']:<14} "
                      f"sheets={e['sheet_context']} status={e['placement_status']} "
                      f"span_collision={e['ownership_disambiguation']['span_collision_with_sibling']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
