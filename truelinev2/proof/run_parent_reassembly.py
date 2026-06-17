r"""PHASE_2_3_PARENT_REASSEMBLY_WITH_BACKUP -- backup the active corpus, then build a CLEAN canonical
parent-source dataset in a NEW (non-active) folder. NON-DESTRUCTIVE: the active corpus is only READ +
COPIED; it is never moved, deleted, or modified. The loader is NOT repointed; census/frontier unchanged.

Phases:
  0  BACKUP FIRST  -> brenham_backup_<ts>/ (all 58 child xlsx + manifest with md5/size/mtime); verify; ABORT on fail.
  1  scaffold      -> brenham_parent_reassembly_<ts>/{parents,children_archive,manifests,README.md}
  2/3 reassemble   -> one canonical parents/<source_parent_id>.json per parent (13 split families + 26 standalone),
                      children grouped underneath with the full schema (segment/role/span/sheets/provenance/...)
  4  archive       -> COPY the old split-child xlsx into children_archive/ (marked deprecated; active corpus untouched)
  5  self-validate -> 39 parents / 13 families / 32 children / 58 entries; log48 gate; all child ids preserved;
                      active corpus byte-identical to the pre-run inventory
  7  log48 check   -> is bore_log20 Segment A sourceable now? (report only; NO render)

build_parent_records() is PURE (model -> records) so the repo can test it without disk/corpus/PDF.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_parent_reassembly
"""
from __future__ import annotations

import datetime
import glob
import hashlib
import json
import os
import re
import shutil

from truelinev2.ingest import parent_source as ps
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus


def _num(s):
    m = re.search(r"(\d+)", str(s))
    return int(m.group(1)) if m else 0


def _md5(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()


def build_parent_records(model: dict) -> list:
    """PURE: parent-source model -> clean canonical parent records (rich schema). No disk/corpus/PDF."""
    out = []
    for p in model["parents"]:
        seg_src = p.get("source_file")
        children = []
        for e in p["entries"]:
            note = e.get("provenance_note") or ""
            m_seg = re.search(r"Segment (\w+)\s*\(?(col\d+)?\)?", note)
            children.append({
                "child_log_id": e["log_id"],
                "old_split_file": f"{e['source_entry_id']}.xlsx",
                "segment_label": (f"Segment {m_seg.group(1)}" + (f" ({m_seg.group(2)})" if m_seg and m_seg.group(2) else "")) if m_seg else None,
                "entry_role": e["entry_role"],
                "span": e["entry_span"],
                "start_station": e["start_station"],
                "end_station": e["end_station"],
                "sheets": e["sheet_context"],
                "matchline_context": e.get("matchline_context"),
                "structure_context": {"start": e.get("start_structure"), "end": e.get("end_structure")},
                "sibling_group_id": e["sibling_group_id"],
                "run_group_id": e["run_group_id"],
                "render_status": e["placement_status"],
                "blocker": ("adjudication carries a SIBLING route -- held"
                            if e["placement_status"] == "HELD_PARENT_CHILD" else None),
                "adjudication_span": e.get("adj_corrected_span"),
                "adjudication_conflicts_corpus": bool(
                    e.get("adj_corrected_span") and e.get("adj_corrected_span") != e["entry_span"]),
                "span_collision_with_sibling": e["ownership_disambiguation"]["span_collision_with_sibling"],
                "provenance_note": note,
                "review_status": ("CORRUPTED_ADJUDICATION_REJECTED" if e["placement_status"] == "HELD_PARENT_CHILD"
                                  else "RENDERED" if e["placement_status"] == "RENDERED" else "OK"),
            })
        out.append({
            "source_parent_id": p["source_parent_id"],
            "source_file": f"{p['source_parent_id']}.xlsx (ORIGINAL handwritten parent -- split into children; not in corpus)"
                           if p["is_split_family"] else f"{p['source_parent_id']}.xlsx",
            "handwritten_source": seg_src,
            "source_scan_id": seg_src,
            "is_split_family": p["is_split_family"],
            "sibling_group_id": p["sibling_group_id"],
            "run_group_id": p["run_group_id"],
            "child_count": len(children),
            "children": sorted(children, key=lambda c: _num(c["child_log_id"])),
        })
    return sorted(out, key=_num)


def _phase0_backup(cd, files, backup_dir):
    os.makedirs(backup_dir, exist_ok=True)
    pre = {}
    manifest = []
    for f in files:
        name = os.path.basename(f)
        md5 = _md5(f)
        st = os.stat(f)
        pre[name] = md5
        dst = os.path.join(backup_dir, name)
        shutil.copy2(f, dst)
        manifest.append({"file": name, "original_path": f, "size": st.st_size,
                         "mtime": datetime.datetime.fromtimestamp(st.st_mtime).isoformat(),
                         "md5": md5, "backup_md5": _md5(dst)})
    (open(os.path.join(backup_dir, "backup_manifest.json"), "w", encoding="utf-8")
     .write(json.dumps({"source": cd, "count": len(manifest), "files": manifest}, indent=2)))
    # verify
    ok = (len(glob.glob(os.path.join(backup_dir, "bore_log*.xlsx"))) == len(files)
          and all(m["md5"] == m["backup_md5"] for m in manifest))
    return ok, pre, manifest


def main() -> int:
    cd, how = resolve_corpus()
    base = os.path.dirname(cd)
    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    files = sorted(glob.glob(os.path.join(cd, "bore_log*.xlsx")), key=_num)
    report = {"timestamp": ts, "active_corpus": cd, "how_resolved": how,
              "active_corpus_count_before": len(files)}

    # ---- PHASE 0: BACKUP FIRST (abort on failure) ----
    backup_dir = os.path.join(base, f"brenham_backup_{ts}")
    ok, pre_md5, bmanifest = _phase0_backup(cd, files, backup_dir)
    report["backup_path"] = backup_dir
    report["backup_verified"] = ok
    report["backup_file_count"] = len(bmanifest)
    if not ok:
        print(f"[reassembly] BACKUP FAILED -- aborting before any reassembly. dir={backup_dir}")
        return 2
    print(f"[reassembly] PHASE 0 backup OK: {len(bmanifest)} files -> {backup_dir}")

    # ---- PHASE 1: scaffold the clean reassembly dataset ----
    reasm = os.path.join(base, f"brenham_parent_reassembly_{ts}")
    for sub in ("parents", "children_archive", "manifests"):
        os.makedirs(os.path.join(reasm, sub), exist_ok=True)
    report["reassembly_path"] = reasm

    # ---- PHASE 2/3: build clean parent records ----
    model = ps.load_model()
    records = build_parent_records(model)
    for r in records:
        (open(os.path.join(reasm, "parents", f"{r['source_parent_id']}.json"), "w", encoding="utf-8")
         .write(json.dumps(r, indent=2, default=str)))
    report["parents_created"] = len(records)
    report["split_families"] = sum(1 for r in records if r["is_split_family"])
    report["standalone_parents"] = sum(1 for r in records if not r["is_split_family"])
    report["child_entries"] = sum(r["child_count"] for r in records)

    # ---- PHASE 4: archive old split children (COPY only; active corpus untouched) ----
    arch = []
    for f in files:
        name = os.path.basename(f)
        shutil.copy2(f, os.path.join(reasm, "children_archive", name))
        arch.append({"file": name, "md5": _md5(f),
                     "status": ["deprecated_as_canonical", "preserved_as_source_child_evidence",
                                "do_not_use_as_independent_truth"]})
    (open(os.path.join(reasm, "children_archive", "_DEPRECATED_README.json"), "w", encoding="utf-8")
     .write(json.dumps({"note": "Archived copies of the split-child xlsx -- source evidence ONLY, NOT canonical "
                                "truth. The active corpus is unchanged and still loaded by the engine.",
                        "files": arch}, indent=2)))
    report["children_archived"] = len(arch)

    # ---- PHASE 5: self-validate ----
    child_ids = {c["child_log_id"] for r in records for c in r["children"]}
    model_ids = {e["log_id"] for p in model["parents"] for e in p["entries"]}
    gate_ok = (not ps.child_owns_route("log48", 514.0, [10, 11])[0]) and ps.child_owns_route("log48", 509.0, [10])[0]
    post_md5 = {os.path.basename(f): _md5(f) for f in glob.glob(os.path.join(cd, "bore_log*.xlsx"))}
    corpus_untouched = (post_md5 == pre_md5)
    report["validation"] = {
        "parents_39": len(records) == 39,
        "split_families_13": report["split_families"] == 13,
        "split_children_32": sum(1 for r in records if r["is_split_family"] for _ in r["children"]) == 32,
        "child_entries_58": report["child_entries"] == 58,
        "all_child_ids_preserved": child_ids == model_ids and len(child_ids) == 58,
        "log48_log50_gate_holds": gate_ok,
        "active_corpus_byte_identical": corpus_untouched,
        "active_corpus_count_after": len(post_md5),
    }
    report["validation_all_pass"] = all(report["validation"].values())

    # ---- PHASE 7: log48 Segment A evidence check (report only; NO render) ----
    _, e48 = ps.entry("log48")
    l48 = next(c for r in records if r["source_parent_id"] == "bore_log20"
               for c in r["children"] if c["child_log_id"] == "log48")
    report["log48_segment_a"] = {
        "segment_label": l48["segment_label"], "corpus_span": l48["span"],
        "has_own_start_reset": False,   # bore-local 0+00 only; no mainline STA x+xx=0+00 in the child
        "has_own_end_identity": False,  # only station 5+09; no end-structure label
        "adjudication_conflicts_corpus": l48["adjudication_conflicts_corpus"],
        "sourceable_from_reassembled_children": False,
        "why": ("Reassembling the SPLIT CHILDREN cannot recover Segment A's own route: the children carry only "
                "bore-local stations + an uncertain shared print (10,11,12); log48's adjudication is corrupted "
                "with Segment C's trace. Segment A's start reset + end identity live ONLY in the ORIGINAL "
                "handwritten bore_log20 scan (Source 2025-12-18_222857 - Jimenez) -- they require OCR/re-extraction "
                "of that handwritten parent, which is an image, not a consumable dataset file. log48 stays ABSTAINED."),
    }

    # ---- README + manifest ----
    (open(os.path.join(reasm, "manifests", "reassembly_manifest.json"), "w", encoding="utf-8")
     .write(json.dumps(report, indent=2, default=str)))
    (open(os.path.join(reasm, "README.md"), "w", encoding="utf-8")
     .write(f"""# Clean canonical parent-source dataset (reassembly {ts})

Original handwritten bore logs are the canonical PARENTS. Split rows are children/siblings/segments grouped
underneath. Built NON-DESTRUCTIVELY from the pushed parent-source model + the active corpus (read-only).

- `parents/` : one canonical record per original parent ({len(records)} parents = {report['split_families']}
  split families + {report['standalone_parents']} standalone). Children grouped with span/sheets/role/provenance.
- `children_archive/` : COPIES of the {len(arch)} split-child xlsx -- source evidence ONLY, deprecated as canonical.
- `manifests/` : this reassembly manifest + (sibling) backup manifest.

NOT active: the engine still loads the original corpus at `{cd}`. The loader is NOT repointed; census/frontier
unchanged. log48 (Segment A of bore_log20) stays ABSTAINED -- its own route needs OCR of the original handwritten
bore_log20 scan (see manifest log48_segment_a). Backup of the original corpus: `{backup_dir}`.
"""))

    print(f"[reassembly] PHASE 1-4: {len(records)} parents, {report['child_entries']} child entries, "
          f"{len(arch)} archived -> {reasm}")
    print(f"[reassembly] PHASE 5 validation: {'ALL PASS' if report['validation_all_pass'] else 'FAIL'} {report['validation']}")
    print(f"[reassembly] PHASE 7 log48 Segment A sourceable: {report['log48_segment_a']['sourceable_from_reassembled_children']}")
    print(f"[reassembly] backup: {backup_dir}")
    print(f"[reassembly] reassembly: {reasm}")
    return 0 if report["validation_all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
