"""ALL-REDLINES closure ledger -- offline tests.

Locks the ledger's pure laws: the result + category enums; the deterministic closure-category function
over synthetic records; the partition is TOTAL (58, exactly one per log) and DISJOINT (placed +
non-placed); NO FAKE POSITIVE (placed only via engine can_draw_now or render-proven seam exemplar);
every non-placed log names a next blocker; the category counts reconcile with the canonical cohort
classifier (a refinement, not a re-classification); the highest-leverage non-placed class is
CROSS_SHEET_FRAME_JOIN_NEEDED (8); and -- the structural guard the proof cannot self-check -- the
proof reuses the canonical classifier and imports no render/PDF/product lane. No PDF parse here.
"""
from pathlib import Path

from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_log53_primitives_cohort_replay import classify_record
from truelinev2.proof.run_all_redlines_closure_ledger import (
    ALL_CATEGORIES,
    ALLOWED,
    CROSS_SHEET,
    ENGINE_PLACED,
    HELD_BACK,
    NEXT_BLOCKER,
    NONPLACED_CATEGORIES,
    PARENT_CHILD,
    PLACED_CATEGORIES,
    R_COMPLETE,
    SEAM_RENDER_PROVEN,
    SOURCE_OWNER,
    STILL_BLOCKED_NAMED,
    UNMODELED_TERMINUS,
    build_ledger,
    closure_category,
)
from truelinev2.config import _REPO_ROOT
import json

DOC = load_adjudication()
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / "final_engine_truth_table.json"
ROWS = json.loads(TRUTH.read_text(encoding="utf-8"))["rows"]
LEDGER = build_ledger(ROWS, DOC)


def test_result_and_category_enums():
    assert R_COMPLETE == "ALL_REDLINES_CLOSURE_LEDGER_COMPLETE"
    assert R_COMPLETE in ALLOWED
    assert len(ALL_CATEGORIES) == 9                  # 2 placed + 7 non-placed closure-target categories
    assert set(PLACED_CATEGORIES).isdisjoint(NONPLACED_CATEGORIES)
    assert set(NEXT_BLOCKER) == set(NONPLACED_CATEGORIES)   # every non-placed category names a blocker


def test_partition_is_total_and_disjoint():
    assert len(LEDGER) == 58
    assert all(v["category"] in ALL_CATEGORIES for v in LEDGER.values())
    placed = [b for b, v in LEDGER.items() if v["placed"]]
    nonplaced = [b for b, v in LEDGER.items() if not v["placed"]]
    assert len(placed) + len(nonplaced) == 58 and set(placed).isdisjoint(nonplaced)


def test_placement_counts():
    counts = {c: sum(1 for v in LEDGER.values() if v["category"] == c) for c in ALL_CATEGORIES}
    assert counts[SEAM_RENDER_PROVEN] == 5
    assert counts[ENGINE_PLACED] == 31
    assert sum(counts[c] for c in PLACED_CATEGORIES) == 36
    assert sum(counts[c] for c in NONPLACED_CATEGORIES) == 22
    assert counts[CROSS_SHEET] == 6                  # log52/log58 bridged out -> HELD_BACK
    assert counts[HELD_BACK] == 3                    # log36 + log52 + log58 (anchored-but-held-back)
    assert counts[UNMODELED_TERMINUS] == 6           # ENDPOINT_IDENTITY_NOT_MODELED is the root gate
    assert counts[PARENT_CHILD] == 0                 # the owner review recorded all per-column sheets


def test_no_fake_positive():
    # placed only when the engine can_draw_now (engine-placed) or it is a render-proven seam exemplar;
    # every non-placed log is one the engine itself does NOT claim placeable (can_draw_now False)
    for b, v in LEDGER.items():
        if v["category"] == ENGINE_PLACED:
            assert v["can_draw_now"] is True and v["completion_bucket"] == "DRAWABLE_REVIEW"
        if not v["placed"]:
            assert v["can_draw_now"] is False
    # log36 (anchored bridge) is held back -- NOT claimed placed
    assert LEDGER["log36"]["category"] == HELD_BACK and LEDGER["log36"]["placed"] is False


def test_every_nonplaced_names_a_blocker():
    for b, v in LEDGER.items():
        if v["placed"]:
            assert v["next_blocker"] is None
        else:
            assert v["next_blocker"] and v["next_blocker"] == NEXT_BLOCKER[v["category"]]


def test_reconciles_with_cohort_classifier_as_refinement():
    from collections import Counter
    cohort = Counter(classify_record(r)["classification"] for r in DOC["logs"])
    counts = Counter(v["category"] for v in LEDGER.values())
    assert counts[SEAM_RENDER_PROVEN] + counts[HELD_BACK] == cohort["SOURCE_BINDABLE_NOW"]
    assert counts[SOURCE_OWNER] == cohort["HUMAN_REVIEW_REQUIRED"]
    assert counts[STILL_BLOCKED_NAMED] == cohort["STILL_BLOCKED"]
    assert (counts[PARENT_CHILD] + counts[CROSS_SHEET] + counts[UNMODELED_TERMINUS]
            + sum(1 for v in LEDGER.values() if v["category"] == "REPRESENTATIVE_ROUTE_ONLY")
            ) == cohort["PARTIAL_SOURCE_BINDABLE"] + cohort["REPRESENTATIVE_ROUTE_CANDIDATE"]


def test_blocker_assignment_is_the_true_gating_one():
    # regression lock (an adversarial review found the cascade once mislabeled 5 logs): the root gate is
    # ENDPOINT_IDENTITY_NOT_MODELED -- a multi-sheet log with no modeled terminus (log54/68) is UNMODELED,
    # NOT cross-sheet; a shared-print child with its sheet already recorded (log6/46/63) is UNMODELED,
    # NOT parent-child. Every category member must satisfy its DEFINING predicate.
    adj = {r["log_id"]: r for r in DOC["logs"]}
    for b, v in LEDGER.items():
        if v["category"] == CROSS_SHEET:
            c = classify_record(adj[b])
            assert c["signals"]["has_modeled_terminus"] and c["signals"]["n_sheets"] >= 2
            assert "ENDPOINT_IDENTITY_NOT_MODELED" not in c["blockers"]
        if v["category"] == UNMODELED_TERMINUS:
            assert "ENDPOINT_IDENTITY_NOT_MODELED" in classify_record(adj[b])["blockers"]
        if v["category"] == PARENT_CHILD:
            assert adj[b].get("shared_print_child") and not adj[b].get("corrected_sheets")
    # the specific logs the review flagged are now correctly routed
    for b in ("log54", "log68", "log6", "log46", "log63", "log41"):
        assert LEDGER[b]["category"] == UNMODELED_TERMINUS


def test_closure_category_function_is_deterministic_on_synthetic():
    # a seam exemplar -> render-proven; an engine row (not in adj) -> engine-placed
    assert closure_category("log64", True, DOC["logs"][0], classify_record(
        next(r for r in DOC["logs"] if r["log_id"] == "log64"))) == SEAM_RENDER_PROVEN
    assert closure_category("log2", False, {}, {"classification": None, "blockers": []}) == ENGINE_PLACED
    # an abstain problem log -> still-blocked-named
    log5 = next(r for r in DOC["logs"] if r["log_id"] == "log5")
    assert closure_category("log5", True, log5, classify_record(log5)) == STILL_BLOCKED_NAMED


def test_proof_reuses_canonical_classifier_and_no_render_pdf_lane():
    # the structural guard the proof cannot self-check (its own check strings would self-reference):
    # the ledger proof must import the canonical classifier, define no classifier, draw nothing.
    src = (Path(__file__).resolve().parent.parent / "proof" / "run_all_redlines_closure_ledger.py").read_text(encoding="utf-8")
    assert "from truelinev2.proof.run_log53_primitives_cohort_replay import" in src
    top_defs = {ln.split("(")[0].strip() for ln in src.splitlines() if ln.startswith("def ")}
    assert "def classify_record" not in top_defs
    assert "def derive_signals" not in top_defs
    assert "from truelinev2.render" not in src
    assert "import truelinev2.render" not in src
    assert "ingest.pdf" not in src
    assert "render_redline_stroke" not in src
