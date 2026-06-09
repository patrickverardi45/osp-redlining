r"""M5 proof: Brenham 58-log coverage sweep — v2 ONLY, MEASUREMENT FIRST.

Runs the shipped v2 pipeline over the full Brenham corpus (Adapter #1) and reports,
per bore: status / matched sheet / station span / artifact / reason+caveat / a
PROVISIONAL miss class. Brenham is an ADAPTER, not the product — this harness adds
NO Brenham logic to the core; it only reads results. Engine code is untouched, so
coverage is measured on the shipped build (M1/M2/M3).

Honesty contract:
- `miss_class_provisional` = the pipeline STAGE where the engine stopped, derived
  mechanically from the reason code. It is NOT a verdict of fault. Distinguishing an
  adapter/extract gap from genuinely-absent source, or a true honest-abstain, requires
  EVIDENCE review — the FINAL `miss_class` is filled during grading.
- Zero false placements is the hard bar, verified by VISUALLY grading the placements
  against the plan/known answers — NOT by this script.
- No count-patching: gaps are classified and handed off, never silenced here.

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_brenham_corpus
"""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from truelinev2.config import Settings, _REPO_ROOT
from truelinev2.context import require_context
from truelinev2.schema.models import Bore, Placement, PlacementStatus
from truelinev2.service import RedlineService
from truelinev2.store.artifacts import ArtifactStore
from truelinev2.store.db import ReviewStore

CORPUS_DIR = os.getenv("TL2_BRENHAM_CORPUS",
                       r"C:\Users\Patrick\OneDrive\Attachments\Desktop\excel bore logs")
EXCLUDE_SUBDIR = "combined_originals_DO_NOT_IMPORT"
PDF = os.getenv("TL2_PROOF_PDF",
                str(_REPO_ROOT / "data" / "uploads" / "Brenham_Tx" /
                    "NEXTLINK - Brenham - Phase 5_07-15-25.pdf"))
EXPECTED_COUNT = 58
TENANT = "proof-tenant"
OUT_DIR = _REPO_ROOT / "data" / "outputs" / "truelinev2" / "m5_brenham"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "brenham_known_answers.json"

REQUIRED_ROW_KEYS = (
    "bore_id", "source_file", "status", "tier", "reason", "caveats",
    "sheets", "station_span", "span_ft", "sheet_refs",
    "footage", "footage_delta", "start_delta", "end_delta",
    "artifact", "artifact_path", "grading_copy",
    "miss_class_provisional", "miss_class", "old_engine", "agreement",
    "grade", "grade_notes",
)


def enumerate_corpus(corpus_dir) -> List[Path]:
    """Top-level ``bore_log*.xlsx`` ONLY (``glob`` is non-recursive, so the
    DO_NOT_IMPORT subfolder is excluded by construction). Sorted by log number."""
    d = Path(corpus_dir)
    files = [p for p in d.glob("bore_log*.xlsx")
             if p.is_file() and p.parent == d and EXCLUDE_SUBDIR not in p.parts]

    def _num(p: Path) -> int:
        m = re.search(r"(\d+)", p.stem)
        return int(m.group(1)) if m else 0

    return sorted(files, key=_num)


def classify(status_str: str, reason: Optional[str]) -> str:
    """PROVISIONAL miss class from the engine's mechanical stop-stage (NOT a fault
    verdict). The FINAL adapter-vs-core-vs-source-vs-honest call is made by grading."""
    if status_str in ("AUTO_SELECT", "REVIEW"):
        return "none_placed"
    if status_str == "ERROR":
        return "adapter_parser_gap"
    r = (reason or "").upper()
    if "NO_DIALECT" in r or "NO_CALLOUTS_EXTRACTED" in r:
        return "adapter_parser_gap"
    if "NO_AUTHORED_BOX_MATCH" in r or "COEQUAL" in r or "TIEBREAKER" in r:
        return "generic_match_scoring_gap"
    return "honest_abstain"


def _load_fixture() -> Dict:
    try:
        return json.loads(FIXTURE.read_text(encoding="utf-8")).get("answers", {})
    except Exception:
        return {}


def _agreement(v2_status: str, old: Optional[Dict]) -> str:
    if not old:
        return "old_unknown"
    old_placed = str(old.get("status", "")).upper() in (
        "AUTO_SELECT", "REVIEW", "PLACED", "PLACED_VALIDATED")
    v2_placed = v2_status in ("AUTO_SELECT", "REVIEW")
    if v2_placed and old_placed:
        return "agree_placed"
    if not v2_placed and not old_placed:
        return "agree_abstain"
    return "v2_only_place" if v2_placed else "old_only_place"


def build_row(bore: Optional[Bore], pl: Optional[Placement], source_file: str,
              status_str: str, artifact: Optional[str], artifact_path: Optional[str],
              grading_copy: Optional[str], old: Optional[Dict], error: Optional[str]) -> Dict:
    reason = (pl.reason if pl else None) or (pl.abstain_reason if pl else None) or error
    return {
        "bore_id": bore.bore_id if bore else Path(source_file).stem,
        "source_file": source_file,
        "status": status_str,
        "tier": pl.tier if pl else None,
        "reason": reason,
        "caveats": list(pl.caveats) if pl else [],
        "sheets": list(pl.sheets) if pl else [],
        "station_span": (pl.station_span if (pl and pl.station_span) else
                         (f"{bore.station_start}->{bore.station_end}" if bore else None)),
        "span_ft": bore.span_ft if bore else None,
        "sheet_refs": list(bore.sheet_refs) if bore else [],
        "footage": pl.footage if pl else None,
        "footage_delta": pl.footage_delta if pl else None,
        "start_delta": pl.start_delta if pl else None,
        "end_delta": pl.end_delta if pl else None,
        "artifact": artifact,
        "artifact_path": artifact_path,
        "grading_copy": grading_copy,
        "miss_class_provisional": classify(status_str, reason),
        "miss_class": "pending_grade",
        "old_engine": old or "unknown",
        "agreement": _agreement(status_str, old),
        "grade": "pending",
        "grade_notes": "",
        "error": error,
    }


def main() -> int:
    if not os.path.isfile(PDF):
        print(f"[m5] STOP: canonical PDF not found: {PDF}")
        return 2
    if not os.path.isdir(CORPUS_DIR):
        print(f"[m5] STOP: corpus dir not found: {CORPUS_DIR}")
        return 2
    corpus = enumerate_corpus(CORPUS_DIR)
    print(f"[m5] corpus dir : {CORPUS_DIR}")
    print(f"[m5] canonical PDF: {PDF}")
    print(f"[m5] enumerated {len(corpus)} top-level bore_log*.xlsx (excluding {EXCLUDE_SUBDIR}/)")
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m5] STOP: expected exactly {EXPECTED_COUNT}, got {len(corpus)} — corpus drift, not running.")
        print(f"[m5] files: {[p.name for p in corpus]}")
        return 3
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    settings = Settings.for_proof()
    svc = RedlineService(settings, ArtifactStore(settings.artifact_root), ReviewStore(settings.db_path))
    old_answers = _load_fixture()

    rows: List[Dict] = []
    for p in corpus:
        session = "brenham-" + p.stem
        old = old_answers.get(p.stem)
        try:
            ctx = require_context(TENANT, session)
            item = svc.run(ctx, str(p), PDF).items[0]
            bore, pl = item.bore, item.placement
            status_str = pl.status.value
            artifact = pl.artifacts[0].name if pl.artifacts else None
            artifact_path = grading_copy = None
            if artifact:
                disk = settings.artifact_root / TENANT / session / artifact
                artifact_path = str(disk)
                if disk.is_file():
                    tag = ("_s%s" % pl.sheets[0]) if pl.sheets else ""
                    gp = OUT_DIR / f"{p.stem}__{status_str}{tag}.png"
                    try:
                        shutil.copyfile(disk, gp)
                        grading_copy = str(gp)
                    except Exception:
                        grading_copy = None
            row = build_row(bore, pl, p.name, status_str, artifact, artifact_path, grading_copy, old, None)
        except Exception as e:  # ingest/parse failure — record, do not crash the sweep
            row = build_row(None, None, p.name, "ERROR", None, None, None, old, f"{type(e).__name__}: {e}")
        rows.append(row)
        print(f"[m5] {row['bore_id']:>12}  {row['status']:<11} "
              f"sheets={row['sheets']} span={row['station_span']} "
              f"prov={row['miss_class_provisional']}  reason={row['reason']}")

    def cnt(s: str) -> int:
        return sum(1 for r in rows if r["status"] == s)

    placed = [r for r in rows if r["status"] in ("AUTO_SELECT", "REVIEW")]
    miss_breakdown: Dict[str, int] = {}
    for r in rows:
        if r["status"] in ("AUTO_SELECT", "REVIEW"):
            continue
        k = r["miss_class_provisional"]
        miss_breakdown[k] = miss_breakdown.get(k, 0) + 1
    agreement_counts = {a: sum(1 for r in rows if r["agreement"] == a)
                        for a in sorted({r["agreement"] for r in rows})}

    summary = {
        "auto_select": cnt("AUTO_SELECT"), "review": cnt("REVIEW"),
        "abstain": cnt("ABSTAIN"), "errored": cnt("ERROR"),
        "placed": len(placed),
        "false_placements": "pending_visual_grade",
        "miss_breakdown_provisional": miss_breakdown,
        "vs_baseline": {
            "note": ("v2 is PDF-FIRST (ingests NO KMZ); the old Brenham engine placed via KMZ "
                     "geometry + PDF anchors. This is a rough yardstick, not strict equivalence."),
            "old_placed_documented": "~34-36 of 58 (wiki PDF-AP Sprint 2.5 + trust_ledger_replay)",
            "v2_placed": len(placed),
            "agreement_counts": agreement_counts,
        },
    }
    report = {
        "milestone": "truelinev2 M5 — Brenham 58-log coverage sweep (measurement-first)",
        "framing": ("Brenham = Adapter #1, not the product. NO Brenham logic added to core; "
                    "engine untouched; coverage measured on the shipped build. "
                    "miss_class_provisional = engine stop-stage (NOT a fault verdict); FINAL miss_class "
                    "is filled by evidence grading. Zero-false is verified by grading, not this file."),
        "corpus_dir": CORPUS_DIR, "pdf": PDF,
        "enumerated": len(corpus), "excluded_subdir": EXCLUDE_SUBDIR,
        "summary": summary, "rows": rows,
    }
    (OUT_DIR / "m5_brenham_coverage.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    txt = "\n".join([
        f"M5 Brenham coverage sweep — {len(corpus)} logs (Adapter #1 measurement)",
        f"  AUTO_SELECT={summary['auto_select']}  REVIEW={summary['review']}  "
        f"ABSTAIN={summary['abstain']}  ERROR={summary['errored']}  PLACED={summary['placed']}",
        f"  provisional miss-stage breakdown (NOT a fault verdict): {miss_breakdown}",
        f"  agreement vs documented baseline: {agreement_counts}",
        f"  old baseline (PDF-first vs KMZ caveat): ~34-36 placed ; v2_placed={len(placed)}",
        f"  false_placements: PENDING VISUAL GRADE (zero-false is the hard bar)",
    ])
    (OUT_DIR / "m5_brenham_summary.txt").write_text(txt + "\n", encoding="utf-8")
    print("\n" + txt)
    print(f"[m5] report -> {OUT_DIR / 'm5_brenham_coverage.json'}")
    print(f"[m5] grading crops -> {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
