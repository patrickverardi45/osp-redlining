"""Day-2 CLI for the PDF-first redline engine.

  python -m engine.redline_pdf_first.cli --pdf "files\\Brenham - Phase 5_07-15-25.pdf" \\
      --borelog "files\\excel bore logs\\bore_log51.xlsx" --out _analysis\\day2_log51_result.json
  python -m engine.redline_pdf_first.cli --batch-known-proof-set
  python -m engine.redline_pdf_first.cli --stub-log log51 --out _analysis\\stub.json   (Day-1 back-compat)
"""
from __future__ import annotations

import argparse
import json
import os

from .contracts import STATUS_ERROR
from .render import crop_renderer
from .render.evidence_card import attach_render_artifacts
from .rulebook import grouping
from .selector.pdf_first_selector import select
from .selector.stub_selector import run_stub

DEFAULT_PDF = os.path.join("files", "Brenham - Phase 5_07-15-25.pdf")
_BORELOG_DIR = os.path.join("files", "excel bore logs")
KNOWN_PROOF_SET = {  # log -> bore-log file; candidate sheets come from the log's print column
    "log51": "bore_log51.xlsx",
    "log2": "bore_log2.xlsx",
    "log14": "bore_log14.xlsx",
    "log39": "bore_log39.xlsx",
    "log5": "bore_log5.xlsx",
}

PATH12_PROOF_SET = ["log51", "log2", "log14", "log39", "log5",
                    "log9", "log19", "log7", "log46", "log65", "log3", "log4", "log53"]
PATH12_CLUSTERS = {"clusterC": ["log9", "log19"],
                   "clusterA": ["log7", "log46", "log65"],
                   "clusterB": ["log3", "log4", "log53"]}


def _borelog_path(log_id: str) -> str:
    return os.path.join(_BORELOG_DIR, "bore_" + log_id + ".xlsx")


def _write(result, out_path: str) -> str:
    out_path = os.path.abspath(out_path)
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(result.to_json())
    return out_path


def _brief(res) -> dict:
    items = list(res.selected_segments) + list(res.review_items)
    if items:
        s = items[0]
        return {"status": res.status, "tier": s.tier, "footage": s.footage, "sheets": s.sheets,
                "station": (f"{s.station_span.start}->{s.station_span.end}" if s.station_span else None),
                "n_callouts": len(s.callouts)}
    if res.fail_safe_items:
        return {"status": res.status, "tier": res.fail_safe_items[0].tier,
                "reason": res.fail_safe_items[0].reason}
    return {"status": res.status}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="engine.redline_pdf_first.cli",
                                description="PDF-first redline engine (Day-2)")
    p.add_argument("--pdf", default=None)
    p.add_argument("--borelog", default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--stub-log", default=None)
    p.add_argument("--batch-known-proof-set", action="store_true")
    p.add_argument("--batch-path12-proof-set", action="store_true")
    args = p.parse_args(argv)

    if args.batch_path12_proof_set:
        pdf = args.pdf or DEFAULT_PDF
        results = {}
        summary = {"logs": {}, "clusters": {}}
        for log_id in PATH12_PROOF_SET:
            res = select(_borelog_path(log_id), pdf)
            crop_renderer.render_and_attach(res, pdf)
            _write(res, os.path.join("_analysis", f"day3_{log_id}_result.json"))
            results[log_id] = res
            summary["logs"][log_id] = {**_brief(res), "contract_ok": not res.validate()}
            print(f"[{log_id}] {_brief(res)}")
        for cname, logs in PATH12_CLUSTERS.items():
            g = grouping.classify([results[l] for l in logs], group_id=cname)
            summary["clusters"][cname] = g
            print(f"[{cname}] kind={g['kind']} tier={g['group_tier']} "
                  f"shared={list(g['shared_boxes'].keys())[:3]} parallel={len(g['parallel_pairs'])} "
                  f"rels={g['span_relations'][:3]}")
        sp = _write_json(summary, os.path.join("_analysis", "day3_path12_proof_set_summary.json"))
        print(f"[engine] day3 summary -> {sp}")
        return 0

    if args.batch_known_proof_set:
        pdf = args.pdf or DEFAULT_PDF
        summary = {}
        for log_id, fn in KNOWN_PROOF_SET.items():
            res = select(os.path.join(_BORELOG_DIR, fn), pdf)
            attach_render_artifacts(res)
            outp = _write(res, os.path.join("_analysis", f"day2_{log_id}_result.json"))
            problems = res.validate()
            summary[log_id] = {**_brief(res), "out": os.path.basename(outp),
                               "contract_ok": not problems}
            print(f"[{log_id}] {_brief(res)} -> {outp}" + ("  !!CONTRACT" if problems else ""))
        sp = _write_json(summary, os.path.join("_analysis", "day2_proof_set_summary.json"))
        print(f"[engine] proof-set summary -> {sp}")
        return 0

    if args.pdf and args.borelog:
        res = select(args.borelog, args.pdf)
        attach_render_artifacts(res)
        outp = _write(res, args.out or os.path.join("_analysis", "day2_result.json"))
        print(f"[engine] {_brief(res)} -> {outp}")
        return 1 if res.status == STATUS_ERROR else 0

    if args.stub_log:
        res = run_stub(args.stub_log)
        attach_render_artifacts(res)
        outp = _write(res, args.out or os.path.join("_analysis", "stub_result.json"))
        print(f"[engine] {_brief(res)} -> {outp}")
        return 0

    p.error("provide --pdf + --borelog, or --batch-known-proof-set, or --stub-log")
    return 2


def _write_json(obj, out_path: str) -> str:
    out_path = os.path.abspath(out_path)
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2)
    return out_path


if __name__ == "__main__":
    raise SystemExit(main())
