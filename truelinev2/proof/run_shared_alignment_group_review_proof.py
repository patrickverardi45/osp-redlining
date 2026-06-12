r"""M8.20 section 7 -- GROUP review extraction + contract proof (proof-only).

The corpus/group extraction pass: it consumes the existing M8.18/M8.19/Law 1
proof outputs OUTSIDE the per-bore lane (reusing the law probe's extractors and
``shared_alignment_verdict``), builds the standalone GROUP review card
(``review.group_review``), validates it, and proves:

  G1  the per-bore lane is UNCHANGED (all three bores stay blocked);
  G2  a GROUP card EXISTS for the proven log8/log32 multi-drop;
  G3  it references exactly the member bores, the shared origin, and the
      distinct boundaries;
  G4  REVIEW-only: no AUTO, no geometry, no strokes, SUGGESTION_NOT_PLACEMENT,
      group-confirm action;
  G5  every member carries its UNCHANGED per-bore blocked status (per-bore
      truth is never overwritten);
  G6  log42 is NOT a member, and a non-proven verdict yields NO card;
  G7  the group schema is a NEW version, DISJOINT from the per-bore
      M8.10/M8.11/M8.15 schemas (it cannot alter their counts);
  G8  nothing is rendered.

Proof-only: the group module is imported by this proof + tests only; it is NOT
wired into ``resolve_bore`` / the sweep / the reviewer service, so the all-58
census and the per-bore contracts are unchanged. No stroke/card/PNG/AUTO.

Outputs (gitignored): data/outputs/shared_alignment_group_review_proof/
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_shared_alignment_group_review_proof
"""
from __future__ import annotations

import dataclasses
import json
import os

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import BRENHAM_LANE_DIALECT
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.shared_alignment import V_REVIEW, shared_alignment_verdict
from truelinev2.match.symbol_conduit_lane import (
    S_STRUCTURE_REQUIRED,
    resolve_bore,
)
from truelinev2.proof.run_brenham_corpus import PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.proof.run_shared_alignment_law_probe import (
    _claim,
    _matchline_boundary_stations,
    _origin_chain_boundaries,
)
from truelinev2.proof.run_shared_origin_adjudication_probe import TARGETS
from truelinev2.review.group_review import (
    GROUP_HUMAN_ACTION,
    GROUP_LANE,
    GROUP_SCHEMA_VERSION,
    MEMBER_BLOCKED_STATUS,
    build_group_review_card,
)
from truelinev2.service import _build_plan_frame_graph

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "shared_alignment_group_review_proof"


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.20-group] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.20-group] STOP: inputs missing")
        return 2
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUT_DIR / "shared_alignment_group_review_proof.json"
    report_path.unlink(missing_ok=True)

    by_id = {t[0]: t for t in TARGETS}
    plan = PlanPdf(PDF)
    ok = True
    try:
        dialect = select_dialect(plan)
        off = dialect.calibrate(plan, 13)
        graph = _build_plan_frame_graph(plan, off)

        # G1 -- the per-bore lane is UNCHANGED (all three blocked); capture the
        # live per-bore statuses to carry into the card verbatim.
        statuses = {}
        for bid, _f, _e, _s, _r in TARGETS:
            out = resolve_bore(plan, load_borelog(str(corpus[f"bore_{bid}"])),
                               off, BRENHAM_LANE_DIALECT, frame_graph=graph)
            statuses[bid] = out.status
            if out.segments:
                ok = False
                print(f"[m8.20-group] FAIL  {bid} emitted segments -- forbidden")
        g1 = all(s == S_STRUCTURE_REQUIRED for s in statuses.values())
        print(f"[m8.20-group] {'PASS' if g1 else 'FAIL'}  G1 lane unchanged: "
              f"{statuses}")
        ok &= g1

        # Corpus/group extraction: claims + bijection universe -> law -> card.
        c8 = _claim(plan, off, graph, *by_id["log8"])
        c32 = _claim(plan, off, graph, *by_id["log32"])
        claims = [c8, c32]
        far = by_id["log8"][1]
        universe = _origin_chain_boundaries(
            plan.lines(far, off), "0+00",
            _matchline_boundary_stations(graph, far, by_id["log8"][2]))
        verdict = shared_alignment_verdict(claims,
                                           origin_chain_boundaries=universe)
        card = build_group_review_card(verdict, claims, statuses)

        # G2 -- a group card EXISTS for the proven multi-drop.
        g2 = card is not None and verdict["verdict"] == V_REVIEW
        print(f"[m8.20-group] {'PASS' if g2 else 'FAIL'}  G2 group card built "
              f"from {verdict['verdict']}")
        ok &= g2

        # G3 -- references: member bores, shared origin, distinct boundaries.
        member_ids = sorted(m.bore_id for m in card.members)
        g3 = (member_ids == ["log32", "log8"]
              and card.shared_origin == "NEXTLINK@378,409"
              and sorted(card.boundaries) == ["1+76", "1+77"]
              and sorted(m.boundary_raw for m in card.members) == ["1+76", "1+77"])
        print(f"[m8.20-group] {'PASS' if g3 else 'FAIL'}  G3 references: members "
              f"{member_ids}, origin {card.shared_origin}, boundaries "
              f"{sorted(card.boundaries)}")
        ok &= g3

        # G4 -- REVIEW-only: no AUTO, no geometry, no strokes, frozen label/action.
        g4 = (card.review_only is True and card.auto is False
              and card.mode == "REVIEW_ONLY"
              and card.has_geometry is False and card.has_strokes is False
              and card.label == "SUGGESTION_NOT_PLACEMENT"
              and card.human_action == GROUP_HUMAN_ACTION
              and card.group_lane == GROUP_LANE
              and "stroke_points" not in json.dumps(card.model_dump())
              and "segments" not in json.dumps(card.model_dump()))
        print(f"[m8.20-group] {'PASS' if g4 else 'FAIL'}  G4 REVIEW-only "
              f"(auto={card.auto}, geometry={card.has_geometry}, "
              f"strokes={card.has_strokes}, label={card.label})")
        ok &= g4

        # G5 -- every member carries its UNCHANGED per-bore blocked status.
        g5 = all(m.per_bore_status == MEMBER_BLOCKED_STATUS == statuses[m.bore_id]
                 for m in card.members)
        print(f"[m8.20-group] {'PASS' if g5 else 'FAIL'}  G5 members stay "
              f"per-bore blocked: "
              f"{[(m.bore_id, m.per_bore_status) for m in card.members]}")
        ok &= g5

        # G6 -- log42 is NOT a member; a non-proven verdict yields NO card.
        rejected = shared_alignment_verdict(
            [dataclasses.replace(c8, conduit_count=0), c32],
            origin_chain_boundaries=universe)
        no_card = build_group_review_card(rejected, claims, statuses)
        g6 = ("log42" not in member_ids and no_card is None
              and rejected["verdict"] != V_REVIEW)
        print(f"[m8.20-group] {'PASS' if g6 else 'FAIL'}  G6 log42 excluded "
              f"({'log42' not in member_ids}); rejected verdict -> "
              f"card={no_card}")
        ok &= g6

        # G7 -- the group schema is NEW and DISJOINT from the per-bore schemas
        # (so it can never alter the M8.10/M8.11/M8.15 counts).
        from truelinev2.review.design_stroke_cards import CARD_SCHEMA_VERSION
        from truelinev2.review.reviewer_payloads import (
            SCHEMA_VERSION as LANES_SCHEMA)
        g7 = (card.schema_version == GROUP_SCHEMA_VERSION
              and GROUP_SCHEMA_VERSION not in (LANES_SCHEMA, CARD_SCHEMA_VERSION))
        print(f"[m8.20-group] {'PASS' if g7 else 'FAIL'}  G7 disjoint schema "
              f"{GROUP_SCHEMA_VERSION} (vs {LANES_SCHEMA} / {CARD_SCHEMA_VERSION})")
        ok &= g7

        # G8 -- nothing rendered.
        g8 = not list(OUT_DIR.glob("*.png"))
        print(f"[m8.20-group] {'PASS' if g8 else 'FAIL'}  G8 no artifact rendered")
        ok &= g8

        report = {
            "milestone": ("truelinev2 M8.20 section 7 -- shared-alignment GROUP "
                          "review card (REVIEW-only; per-bore truth unchanged)"),
            "corpus_dir_used": corpus_dir, "corpus_resolution": how,
            "plan_pdf": PDF, "verdict": "PASS" if ok else "FAILURE",
            "lane_statuses": statuses,
            "group_card": card.model_dump() if card else None,
            "rejected_verdict_makes_no_card": no_card is None,
        }
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[m8.20-group] report -> {report_path}")
    finally:
        plan.close()

    print(f"[m8.20-group] {'PASS' if ok else 'FAILURE'}")
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
