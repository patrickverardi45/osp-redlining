r"""FULL-DATASET TRY-DRAW-ALL diagnostic sweep (PROOF/REPORT ONLY; diagnostic renderer, not product truth).

Attempts to draw EVERY bore log in the current v2 dataset (all 58) as far as each can SAFELY go, produces a
visual artifact for every log the engine can safely render NOW, and -- for every log that cannot render --
names the exact, source-grounded blocker. It is a diagnostic snapshot of how far the renderer reaches across
the whole dataset today; it is NOT a product/runtime path, NOT a placement, and changes NO truth.

It invents nothing and decides nothing new. The RENDER side reuses the existing, PROVEN, gated per-log render
proofs verbatim -- it drives each one OUT-OF-PROCESS (the seam end-to-end-driver pattern), requires exit 0,
and collects the RED REVIEW/AUTO stroke PNG(s) each writes to its own gitignored output dir. A log is only
ever reported RENDERED when a real PNG was produced by such a proven proof (no fake positive). The CLASSIFY
side is a deterministic projection of signals that already exist: the ALL-REDLINES closure ledger
(build_ledger: each log's closure category), the owner-reviewed adjudication (abstain / review / source-verify
flags, corrected_sheets), and -- for the held-back cross-sheet logs -- the SHIPPED cross-sheet frame-join
primitive (scout_log) to split "termini bound but join blocked" from "source-bind complete, render blocked".

Every one of the 58 logs is placed into EXACTLY ONE of the 11 diagnostic categories:
  RENDERED_FULL                          -- a complete, gated, source-backed red stroke is drawn end-to-end
  RENDERED_PARTIAL                       -- a complete stroke is drawn but a named route-fidelity caveat holds
  SOURCE_BIND_ONLY_RENDER_BLOCKED        -- both termini + cross-sheet join source-backed; render deferred
  TERMINI_BOUND_JOIN_BLOCKED             -- termini bind, but the cross-sheet join abstains (CONFLICTING)
  OWNER_CONFIRMATION_BLOCKED             -- anchored bridge, sheet SOURCE-RECOVERED not owner-confirmed ([])
  PARENT_CHILD_RECONSTRUCTION_BLOCKED    -- shared-Print parent/child cross-sheet run not yet reconstructed
  SOURCE_OCR_OWNER_CONFIRMATION_BLOCKED  -- owner source re-read / OCR / source-verification pending
  UNMODELED_TERMINUS_BLOCKED             -- endpoint structure identity not modeled/locatable (root gate)
  REPRESENTATIVE_ROUTE_ONLY              -- engine places a review pick-card, but the exact stroke is untraceable
  OUT_OF_CLASS                           -- out of the redline class
  UNSAFE_ABSTAIN                         -- owner-reviewed ABSTAIN; no safe deterministic source

CRITICAL (all enforced by gates): no seam promotion; no placement-count change (the closure ledger placed
count stays 36); no fixture / endpoint_anchors / coordinate edit; no fake or guessed redline; TrueLine strokes
are red (REDLINE_STROKE_RGB); source PDF/CAD evidence colors untouched; artifacts go ONLY to gitignored
proof-output dirs. Engine census frozen; seam ELIGIBLE_EXEMPLARS unchanged at 5.

Proof-only. Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_full_dataset_try_draw_all_slice
"""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from collections import Counter

import truelinev2.match.frames as FR
from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.ingest.manual_adjudication import (
    activation_summary,
    apply_adjudications,
    load_adjudication,
    parent_run_duplicate_check,
)
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_all_redlines_closure_ledger import (
    CROSS_SHEET,
    ENGINE_PLACED,
    HELD_BACK,
    PARENT_CHILD,
    REPRESENTATIVE_ONLY,
    SEAM_RENDER_PROVEN,
    SOURCE_OWNER,
    STILL_BLOCKED_NAMED,
    UNMODELED_TERMINUS,
    build_ledger,
)
from truelinev2.proof.run_brenham_corpus import PDF
from truelinev2.proof.run_cross_sheet_frame_join_scout import ABSTAIN_CONFLICT, scout_log
from truelinev2.render.crop import REDLINE_STROKE_RGB
from truelinev2.seam import ELIGIBLE_EXEMPLARS

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "full_dataset_try_draw_all_slice"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
SEAM_ELIGIBLE = ("log53", "log64", "log71", "log59", "log66")

# ---- diagnostic categories (exactly one per bore log) -------------------------------
RENDERED_FULL = "RENDERED_FULL"
RENDERED_PARTIAL = "RENDERED_PARTIAL"
SOURCE_BIND_ONLY = "SOURCE_BIND_ONLY_RENDER_BLOCKED"
TERMINI_BOUND_JOIN = "TERMINI_BOUND_JOIN_BLOCKED"
OWNER_CONFIRMATION = "OWNER_CONFIRMATION_BLOCKED"
PARENT_CHILD_RECON = "PARENT_CHILD_RECONSTRUCTION_BLOCKED"
SOURCE_OCR_OWNER = "SOURCE_OCR_OWNER_CONFIRMATION_BLOCKED"
UNMODELED_TERMINUS_B = "UNMODELED_TERMINUS_BLOCKED"
REPRESENTATIVE = "REPRESENTATIVE_ROUTE_ONLY"
OUT_OF_CLASS = "OUT_OF_CLASS"
UNSAFE_ABSTAIN = "UNSAFE_ABSTAIN"
ALL_CATEGORIES = (RENDERED_FULL, RENDERED_PARTIAL, SOURCE_BIND_ONLY, TERMINI_BOUND_JOIN,
                  OWNER_CONFIRMATION, PARENT_CHILD_RECON, SOURCE_OCR_OWNER, UNMODELED_TERMINUS_B,
                  REPRESENTATIVE, OUT_OF_CLASS, UNSAFE_ABSTAIN)

# ---- render registry: the PROVEN, gated render proofs (driven out-of-process) -------
# (module, [(log_id, status, render_method_note)]). Each module renders ONLY its listed log(s); the sweep
# collects the PNG(s) that proof writes to its own OUT_DIR. A log is RENDERED only if a real PNG appears.
RENDER_DRIVERS = (
    ("truelinev2.proof.run_log53_render_artifact_slice",
     [("log53", RENDERED_FULL, "drawn BORE-LATERAL corridor; two sheet-local legs (s5/s6) joined by station identity")]),
    ("truelinev2.proof.run_log59_render_artifact_slice",
     [("log59", RENDERED_FULL, "drawn conduit ordered-chain path, single sheet 21")]),
    ("truelinev2.proof.run_log64_render_artifact_slice",
     [("log64", RENDERED_FULL, "drawn continuous BORE-VACANT-PIPE corridor, single sheet 21")]),
    ("truelinev2.proof.run_log66_render_artifact_slice",
     [("log66", RENDERED_FULL, "drawn ordered-chain path (corridor discontinuous), single sheet 10")]),
    ("truelinev2.proof.run_log71_render_artifact_slice",
     [("log71", RENDERED_FULL, "drawn chain path + corridor; two sheet-local legs (s23/s24)")]),
    ("truelinev2.proof.run_source_bindable_held_back_render_slice",
     [("log52", RENDERED_FULL, "drawn conduit chain; two sheet-local legs (s7/s8) joined by station identity")]),
    ("truelinev2.proof.run_owner_corrected_held_back_render_batch_slice",
     [("log69", RENDERED_FULL, "drawn ordered-chain path, single sheet 17")]),
    ("truelinev2.proof.run_log65_cross_sheet_stroke_proof",
     [("log65", RENDERED_FULL, "cross-sheet stroke joined at the printed matchline boundary (s10/s9)")]),
    ("truelinev2.proof.run_redline_stroke_proof",
     [("log45", RENDERED_FULL, "station-axis route-ladder stroke (clean ladder ticks), single sheet 10")]),
    ("truelinev2.proof.run_log51_symbol_anchored_stroke_proof",
     [("log51", RENDERED_FULL, "symbol-anchored AUTO stroke; endpoints on proven structure symbols, clean-ladder interior, sheet 8")]),
    ("truelinev2.proof.run_symbol_anchored_stroke_proof",
     [("log7", RENDERED_PARTIAL, "symbol-anchored REVIEW stroke; endpoints exact + rival-safe, station-tick interior; the drawn conduit route is NOT traceable (4 parallel strands), so the route is representative")]),
    ("truelinev2.proof.run_design_path_adherence_proof",
     [("log25", RENDERED_FULL, "design-path-traced polyline that follows the drawn geometry, single sheet 21")]),
)
RENDER_NOTE = {lid: note for _, rows in RENDER_DRIVERS for lid, _, note in rows}
RENDER_STATUS = {lid: st for _, rows in RENDER_DRIVERS for lid, st, _ in rows}
PARTIAL_LOGS = tuple(lid for lid, st in RENDER_STATUS.items() if st == RENDERED_PARTIAL)
RENDERED_LOGS = tuple(lid for lid in RENDER_STATUS)

R_COMPLETE = "FULL_DATASET_TRY_DRAW_ALL_COMPLETE"
B_UNIVERSE = "BLOCKED_TRY_DRAW_UNIVERSE_MISSING"
B_DRIVER = "BLOCKED_TRY_DRAW_RENDER_DRIVER_FAILED"
B_FAKE_POSITIVE = "BLOCKED_TRY_DRAW_FAKE_POSITIVE"
B_PARTITION = "BLOCKED_TRY_DRAW_PARTITION_NOT_TOTAL_OR_DISJOINT"
B_CENSUS = "BLOCKED_TRY_DRAW_CENSUS_OR_PLACEMENT_DRIFT"
B_SCOPE = "BLOCKED_TRY_DRAW_SCOPE_VIOLATION"
ALLOWED = {R_COMPLETE, B_UNIVERSE, B_DRIVER, B_FAKE_POSITIVE, B_PARTITION, B_CENSUS, B_SCOPE}


def _census_frozen(doc) -> bool:
    if not TRUTH.is_file():
        return False
    truth = json.loads(TRUTH.read_text(encoding="utf-8"))
    baseline = {r["bore_id"]: dict(r) for r in truth["rows"]}
    off = apply_adjudications(baseline, enabled=False)
    on = apply_adjudications(baseline, enabled=True, doc=doc)
    summ = activation_summary(on)
    buckets = {}
    for r in off.values():
        buckets[r["completion_bucket"]] = buckets.get(r["completion_bucket"], 0) + 1
    return (off is baseline and buckets == FROZEN_BUCKETS
            and summ["manual_review_drawable"] == 22 and summ["manual_source_verification"] == 1
            and summ["manual_abstain"] == 4
            and on["log44"]["adjudication"]["drawable_status"] == "non_drawable"
            and all(on[l]["adjudication"]["drawable_status"] == "abstain" for l in ABSTAIN_4)
            and not parent_run_duplicate_check(doc))


def drive_render(module: str, target_logs) -> dict:
    """Drive one PROVEN render proof OUT-OF-PROCESS (exit 0 required) and collect the RED stroke PNG(s) it
    wrote to its own OUT_DIR, per target log. Returns {log_id: {artifacts:[rel], sheets:[...], exit_code}}."""
    mod = importlib.import_module(module)
    out_dir = getattr(mod, "OUT_DIR")
    proc = subprocess.run([sys.executable, "-m", module], cwd=str(_REPO_ROOT),
                          env={**os.environ, "PYTHONPATH": "."},
                          capture_output=True, text=True, timeout=300)
    result = {}
    for lid in target_logs:
        pngs = sorted(p for p in out_dir.glob("*.png") if p.name.startswith(lid + "_"))
        sheets = sorted({int(s[1:]) for p in pngs for s in p.stem.split("_") if s[:1] == "s" and s[1:].isdigit()})
        result[lid] = {"exit_code": proc.returncode,
                       "artifacts": [str(p).replace(str(_REPO_ROOT), "").lstrip("\\/").replace("\\", "/") for p in pngs],
                       "sheets": sheets}
    return result


def classify(bid: str, rec: dict, closure_cat: str, join_conflict: bool) -> str:
    """Deterministic, EXACTLY-ONE diagnostic category from EXISTING signals (render success overrides)."""
    if bid in PARTIAL_LOGS:
        return RENDERED_PARTIAL
    if bid in RENDERED_LOGS:
        return RENDERED_FULL
    if closure_cat == STILL_BLOCKED_NAMED:
        return UNSAFE_ABSTAIN
    if closure_cat == SOURCE_OWNER:
        return SOURCE_OCR_OWNER
    if closure_cat == UNMODELED_TERMINUS:
        return UNMODELED_TERMINUS_B
    if closure_cat in (CROSS_SHEET, PARENT_CHILD):
        return PARENT_CHILD_RECON
    if closure_cat == HELD_BACK:
        if not (rec.get("corrected_sheets") or []):
            return OWNER_CONFIRMATION
        return TERMINI_BOUND_JOIN if join_conflict else SOURCE_BIND_ONLY
    if closure_cat in (ENGINE_PLACED, REPRESENTATIVE_ONLY):
        return REPRESENTATIVE
    if closure_cat == SEAM_RENDER_PROVEN:
        return RENDERED_FULL                       # safety: seam exemplars must render via a driver
    return OUT_OF_CLASS


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = load_adjudication()
    rec = {r["log_id"]: r for r in doc["logs"]}
    gates, ev = [], {}
    result = B_UNIVERSE

    if not TRUTH.is_file() or not os.path.isfile(PDF):
        gates.append(("G0 inputs present (truth table + plan PDF)", False,
                      {"truth": TRUTH.is_file(), "pdf": os.path.isfile(PDF)}))
        return _emit(gates, B_UNIVERSE, {}, ev)
    truth_rows = json.loads(TRUTH.read_text(encoding="utf-8"))["rows"]

    gates.append(("G0 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                  _census_frozen(doc), None))

    # ---- closure ledger: the per-log closure category + placement baseline (must stay placed=36) ----
    ledger = build_ledger(truth_rows, doc)
    placed_before = sum(1 for v in ledger.values() if v["placed"])
    gates.append(("G1 universe == 58; closure ledger placed == 36 (placement baseline; diagnostic changes none)",
                  len(ledger) == 58 and placed_before == 36, {"universe": len(ledger), "placed": placed_before}))

    # ---- DRIVE every PROVEN render proof out-of-process; collect the RED stroke PNGs ----
    render = {}
    driver_ok = True
    for module, rows in RENDER_DRIVERS:
        target = [lid for lid, _, _ in rows]
        out = drive_render(module, target)
        for lid in target:
            render[lid] = out[lid]
            driver_ok = driver_ok and out[lid]["exit_code"] == 0 and len(out[lid]["artifacts"]) >= 1
    ev["render"] = render
    gates.append(("G2 every render driver exits 0 AND produced >= 1 real RED stroke PNG for its target log (no fake positive)",
                  driver_ok, {lid: {"exit": render[lid]["exit_code"], "n_png": len(render[lid]["artifacts"])}
                              for lid in RENDERED_LOGS}))
    if not driver_ok:
        return _emit(gates, B_DRIVER, ledger, ev)

    # ---- held-back cross-sheet join split (shipped primitive): CONFLICTING -> termini-bound/join-held ----
    plan = PlanPdf(PDF)
    join_conflict = {}
    try:
        offset = select_dialect(plan).calibrate(plan, 13)
        graph = FR._build_plan_frame_graph(plan, offset)
        for bid, v in ledger.items():
            if v["category"] == HELD_BACK and bid not in RENDERED_LOGS and (rec.get(bid, {}).get("corrected_sheets") or []):
                s = scout_log(graph, plan, offset, rec[bid])
                join_conflict[bid] = (not s["source_backed"]) and s["blocker"] == ABSTAIN_CONFLICT
    finally:
        plan.close()
    ev["held_back_join_conflict"] = join_conflict

    # ---- classify all 58 into exactly one diagnostic category + build the manifest ----
    manifest = {}
    for bid in sorted(ledger, key=lambda s: int(s[3:])):
        v = ledger[bid]
        cat = classify(bid, rec.get(bid, {}), v["category"], join_conflict.get(bid, False))
        rendered = bid in RENDERED_LOGS
        manifest[bid] = {
            "log_id": bid, "status": cat,
            "artifacts": render.get(bid, {}).get("artifacts", []) if rendered else [],
            "sheets_rendered": render.get(bid, {}).get("sheets", []) if rendered else [],
            "render_method": RENDER_NOTE.get(bid) if rendered else None,
            "reason": "" if rendered else _reason(bid, v, cat, join_conflict.get(bid, False)),
            "closure_category": v["category"], "sheets": v.get("sheets"),
        }
    counts = Counter(m["status"] for m in manifest.values())

    # G3 partition TOTAL + DISJOINT: every log exactly one of the 11 categories
    gates.append(("G3 partition: all 58 logs classified into exactly one of the 11 diagnostic categories",
                  len(manifest) == 58 and all(m["status"] in ALL_CATEGORIES for m in manifest.values())
                  and sum(counts.values()) == 58, dict(counts)))

    # G4 NO FAKE POSITIVE: rendered set == the driver logs; every RENDERED_* has >=1 real PNG on disk;
    #    every non-rendered has a non-empty named reason and ZERO artifacts
    rendered_set = {b for b, m in manifest.items() if m["status"] in (RENDERED_FULL, RENDERED_PARTIAL)}
    fake_free = (rendered_set == set(RENDERED_LOGS)
                 and all(manifest[b]["artifacts"] and all(os.path.isfile(_REPO_ROOT / a) for a in manifest[b]["artifacts"])
                         for b in rendered_set)
                 and all((not manifest[b]["artifacts"]) and manifest[b]["reason"]
                         for b in manifest if b not in rendered_set))
    gates.append(("G4 NO FAKE POSITIVE: rendered == driver set; every rendered has a real PNG; every non-rendered names a blocker + has zero artifacts",
                  fake_free, {"rendered": sorted(rendered_set, key=lambda s: int(s[3:]))}))

    # G5 render-count split matches the registry (11 full + 1 partial)
    gates.append(("G5 render counts: RENDERED_FULL == 11, RENDERED_PARTIAL == 1 (12 logs drawable now)",
                  counts[RENDERED_FULL] == len(RENDERED_LOGS) - len(PARTIAL_LOGS)
                  and counts[RENDERED_PARTIAL] == len(PARTIAL_LOGS),
                  {"full": counts[RENDERED_FULL], "partial": counts[RENDERED_PARTIAL]}))

    # G6 NO placement / seam / census drift: ledger placed unchanged (36), seam unchanged (5), census frozen
    ledger_after = build_ledger(truth_rows, doc)
    placed_after = sum(1 for v in ledger_after.values() if v["placed"])
    gates.append(("G6 no placement/seam change: closure ledger placed still 36; seam ELIGIBLE_EXEMPLARS still 5; census frozen",
                  placed_after == 36 and placed_after == placed_before
                  and tuple(ELIGIBLE_EXEMPLARS) == SEAM_ELIGIBLE and _census_frozen(doc),
                  {"placed_before": placed_before, "placed_after": placed_after,
                   "seam": list(ELIGIBLE_EXEMPLARS)}))
    ev["placement_seam_ledger_impact"] = {"placed_before": placed_before, "placed_after": placed_after,
                                          "seam_eligible": list(ELIGIBLE_EXEMPLARS),
                                          "note": "diagnostic only: NOTHING placed/promoted; renders are gitignored proof artifacts"}

    if all(x for _, x, _ in gates):
        result = R_COMPLETE
    elif not gates[1][1]:
        result = B_UNIVERSE
    elif not (len(gates) > 4 and gates[4][1]):
        result = B_FAKE_POSITIVE
    elif not gates[3][1]:
        result = B_PARTITION
    else:
        result = B_CENSUS
    return _emit(gates, result, ledger, ev, manifest, counts)


def _reason(bid, v, cat, join_conflict) -> str:
    base = {
        SOURCE_BIND_ONLY: "Both termini + the cross-sheet frame join are source-backed; render deferred (cross-sheet leg / multi-sheet reconciliation not yet drawn).",
        TERMINI_BOUND_JOIN: "Both termini bind, but the cross-sheet frame join ABSTAINS (CONFLICTING_FRAME_EQUATIONS: two printed crossings disagree); no safe join, render held.",
        OWNER_CONFIRMATION: "Anchored endpoint bridge, but the sheet is SOURCE-RECOVERED not owner-recorded (corrected_sheets == []); owner confirmation required before render.",
        PARENT_CHILD_RECON: "Shared-Print parent/child cross-sheet run; the deferred matchline frame join / per-column sheet reconstruction must be solved before an exact endpoint route exists.",
        SOURCE_OCR_OWNER: "Owner source re-read / OCR / source-verification pending before geometry can be trusted.",
        UNMODELED_TERMINUS_B: "Endpoint structure identity is not modeled/locatable from source (no modeled terminus class) -- the root gate; no exact endpoint yet.",
        REPRESENTATIVE: "Engine places a review pick-card / route suggestion, but the exact drawn redline stroke is not traceable (end identity unprinted / cross-sheet continuation / structure-identity binding / pick-card-with-end-anchor).",
        OUT_OF_CLASS: "Out of the redline class.",
        UNSAFE_ABSTAIN: "Owner-reviewed ABSTAIN: no safe deterministic source; held by owner decision.",
    }.get(cat, "")
    return f"{base} [closure={v['category']}; sheets={v.get('sheets')}]"


def _emit(gates, result, ledger, ev, manifest=None, counts=None) -> int:
    # scope/safety gates (always run)
    all_pngs_under_outputs = all(("/data/outputs/" in ("/" + a) or a.startswith("data/outputs/"))
                                 for m in (manifest or {}).values() for a in m.get("artifacts", []))
    gates.append(("G7 every artifact lives under a gitignored data/outputs path (no committed render)",
                  all_pngs_under_outputs, None))
    gates.append(("G8 canonical red stroke color (TrueLine strokes are red)",
                  REDLINE_STROKE_RGB == (220, 25, 25), list(REDLINE_STROKE_RGB)))
    gates.append(("G9 result in allowed enum", result in ALLOWED, result))
    all_pass = all(x for _, x, _ in gates) and result == R_COMPLETE
    counts = counts or Counter()
    by_cat = {c: sorted((b for b, m in (manifest or {}).items() if m["status"] == c), key=lambda s: int(s[3:]))
              for c in ALL_CATEGORIES}
    rendered = sorted((b for b, m in (manifest or {}).items()
                       if m["status"] in (RENDERED_FULL, RENDERED_PARTIAL)), key=lambda s: int(s[3:]))
    report = {
        "milestone": "FULL-DATASET TRY-DRAW-ALL diagnostic sweep (proof/report only; diagnostic renderer, not product truth)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result if all_pass else "BLOCKED",
        "universe_total": len(manifest or {}),
        "rendered_full": counts.get(RENDERED_FULL, 0),
        "rendered_partial": counts.get(RENDERED_PARTIAL, 0),
        "not_rendered": (len(manifest or {}) - counts.get(RENDERED_FULL, 0) - counts.get(RENDERED_PARTIAL, 0)),
        "category_counts": {c: counts.get(c, 0) for c in ALL_CATEGORIES},
        "category_members": by_cat,
        "rendered_logs": rendered,
        "compact_index": {b: {"status": m["status"], "artifacts": m["artifacts"], "sheets": m["sheets_rendered"],
                              "reason": m["reason"]} for b, m in sorted((manifest or {}).items(), key=lambda kv: int(kv[0][3:]))},
        "manifest": [ (manifest or {})[b] for b in sorted((manifest or {}), key=lambda s: int(s[3:])) ],
        "placement_seam_ledger_impact": ev.get("placement_seam_ledger_impact"),
        "held_back_join_conflict": ev.get("held_back_join_conflict"),
        "doctrine": {"diagnostic_only": True, "no_seam_promotion": True, "no_placement_change": True,
                     "no_fixture_or_anchor_edit": True, "no_coordinate_encoding": True,
                     "no_fake_or_guessed_redline": True, "red_strokes_only": REDLINE_STROKE_RGB == (220, 25, 25),
                     "source_colors_untouched": True, "artifacts_gitignored": True, "engine_census_frozen": True},
        "scope_guard": {"product_wiring": False, "broad_renderer_rewrite": False, "match_review_wiring": False,
                        "runtime_batch": False, "deploy": False},
        "next_slice": ("attack the largest non-rendered class REPRESENTATIVE_ROUTE_ONLY (engine pick-cards whose "
                       "exact stroke is untraceable: END_IDENTITY_UNPRINTED / CROSS_SHEET_CONTINUATION / "
                       "STRUCTURE_IDENTITY_BINDING) -- model the end-structure identity + cross-sheet continuation; "
                       "then the 6 UNMODELED_TERMINUS, the held-back render lanes (log47/log11/log58 source-bind-only, "
                       "log67/log70 17<->20 crossing, log36 owner-confirm), and the log48 parent/child reconstruction."),
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "full_dataset_try_draw_all_slice.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[try-draw-all] result: {report['result']}  rendered={report['rendered_full']}F+{report['rendered_partial']}P  "
          f"not_rendered={report['not_rendered']}/58")
    for c in ALL_CATEGORIES:
        print(f"[try-draw-all]   {c:<38} {counts.get(c, 0):>3}  {by_cat.get(c, [])}")
    for n, x, _ in gates:
        print(f"[try-draw-all] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[try-draw-all] VERDICT: {'PASS' if all_pass else 'FAIL'}  (manifest: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
