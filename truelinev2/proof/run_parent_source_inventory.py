r"""ORIGINAL_HANDWRITTEN_PARENT_SOURCE_MODEL -- Phase 0 inventory (read-only; temp).

Reads every active corpus bore_log*.xlsx and reconstructs the original-handwritten parent/child families
from each file's NOTES provenance ('Segment X split from bore_logNN.xlsx. Source: <handwritten scan>'),
cross-referenced with the engine truth table (source_family) + the owner adjudication (parent). No writes.
"""
from __future__ import annotations
import glob, json, os, re
import openpyxl
from truelinev2.config import _REPO_ROOT
from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus

TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / "final_engine_truth_table.json"


def _num(stem):
    m = re.search(r"(\d+)", stem)
    return int(m.group(1)) if m else 0


def read_xlsx(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    header = [str(c).strip().lower() if c is not None else "" for c in rows[0]]
    def col(name):
        return header.index(name) if name in header else None
    ci = {k: col(k) for k in ("station", "print", "notes", "crew", "date")}
    data = []
    for r in rows[1:]:
        if not any(c not in (None, "") for c in r):
            continue
        data.append({k: (r[ci[k]] if ci[k] is not None and ci[k] < len(r) else None) for k in ci})
    stations = [str(d["station"]).strip() for d in data if d["station"] not in (None, "")]
    notes = next((str(d["notes"]) for d in data if d["notes"]), "") if data else ""
    prints = sorted({str(d["print"]).strip() for d in data if d["print"] not in (None, "")})
    crews = sorted({str(d["crew"]).strip() for d in data if d["crew"] not in (None, "")})
    return {"n_rows": len(data), "stations": stations,
            "span": (f"{stations[0]}->{stations[-1]}" if stations else None),
            "prints": prints, "crews": crews, "notes": notes}


def main() -> int:
    cd, how = resolve_corpus()
    truth = {r["bore_id"]: r for r in json.loads(TRUTH.read_text(encoding="utf-8"))["rows"]}
    adj = {r["log_id"]: r for r in load_adjudication()["logs"]}
    files = sorted(glob.glob(os.path.join(cd, "bore_log*.xlsx")),
                   key=lambda p: int(re.search(r"bore_log(\d+)", p).group(1)))
    print(f"corpus: {cd} ({how}); {len(files)} files\n")

    families = {}   # source_parent (from 'split from' note or Source) -> [child stems]
    sources = {}    # handwritten Source string -> [child stems]
    rows = []
    for f in files:
        stem = os.path.splitext(os.path.basename(f))[0]   # bore_logNN
        nn = re.search(r"bore_log(\d+)", stem).group(1)
        info = read_xlsx(f)
        note = info["notes"]
        m_split = re.search(r"split from (bore_log\d+)", note)
        m_src = re.search(r"Source:\s*([^.;\n]+)", note)
        split_parent = m_split.group(1) if m_split else None
        source = m_src.group(1).strip() if m_src else None
        # cross-ref: truth source_family + adjudication parent for logNN
        lid = f"log{nn}"
        trow = truth.get(lid, {})
        arow = adj.get(lid, {})
        rows.append({
            "file": stem, "log": lid, "span": info["span"], "n_rows": info["n_rows"],
            "prints": info["prints"], "crews": info["crews"],
            "split_from": split_parent, "source": source,
            "truth_family": trow.get("source_family"), "truth_span": trow.get("span"),
            "truth_sheets": trow.get("sheets"),
            "adj_parent": arow.get("parent"), "adj_status": arow.get("status"),
            "adj_corr_span": (f"{arow.get('corrected_start')}->{arow.get('corrected_end')}"
                              if arow.get("corrected_start") else None),
            "note": note[:140],
        })
        fam_key = split_parent or trow.get("source_family") or stem
        families.setdefault(fam_key, []).append(stem)
        if source:
            sources.setdefault(source, []).append(stem)

    # families with >1 member = real split groups
    multi = {k: v for k, v in families.items() if len(v) > 1}
    print(f"=== FAMILIES (source_parent -> children); {len(families)} total, {len(multi)} multi-child ===")
    for k, v in sorted(multi.items(), key=lambda kv: -len(kv[1])):
        kids = ", ".join(sorted(v, key=_num))
        print(f"  {k:<14} ({len(v)}): {kids}")
    print(f"\n=== HANDWRITTEN SOURCES (Source: -> children); {len(sources)} sources, "
          f"{sum(1 for v in sources.values() if len(v)>1)} multi ===")
    for k, v in sorted(sources.items(), key=lambda kv: -len(kv[1])):
        if len(v) > 1:
            kids = ", ".join(sorted(v, key=_num))
            print(f"  {k:<32} ({len(v)}): {kids}")
    print("\n=== PER-FILE ===")
    print(json.dumps(rows, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
