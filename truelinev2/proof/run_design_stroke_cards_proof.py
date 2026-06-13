r"""M8.15 -- design-stroke reviewer-card bridge proof (9 cards; unwired).

The first reviewer-card payload integration slice: the 4 accepted design-path
strokes (log25/51/59/65, Patrick PASS 2026-06-11) and the 5 end-anchored pick
candidates (log2/9/23/50/57) bridged into the new design-stroke card contract
(schema ``truelinev2-design-stroke-card-1``). The banked M8.10/M8.11 reviewer
contracts are NOT touched, NOT widened, NOT consumed differently.

Embedded gates (any failure -> nonzero exit):
  G1 the lane reproduces the 9 targeted outcomes and the packet builds with
     kind_counts {DESIGN_STROKE_REVIEW: 4, DESIGN_PICK_CARD: 5}, zero
     refusals among the targets
  G2 GEOMETRY VERBATIM + PURE: every stroke card's segments equal the lane
     outcome's serialized segments EXACTLY; building cards does not mutate
     any outcome (to_dict before == after)
  G3 grade provenance honest: all 4 stroke cards are PASS_ACCEPTED and the
     packet's provenance record backs each; with an EMPTY grades record the
     same outcomes map to UNGRADED (a card can never claim an ungiven grade)
  G4 masquerade refusals LIVE: a pick card carrying stroke segments is
     REJECTED by the validator; a packet whose stroke card claims
     PASS_ACCEPTED without provenance is REJECTED
  G5 evidence survives verbatim: every card's evidence_chain equals the lane
     outcome's component reports; artifact refs follow the lane sweep's PNG
     naming convention exactly (existence reported, not gated -- artifacts
     are gitignored regenerables)
  G6 UNWIRED: no engine/service/lane source references the bridge; the
     bridge imports nothing from proof/

Outputs (gitignored): data/outputs/design_stroke_cards/

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_design_stroke_cards_proof
"""
from __future__ import annotations

import inspect
import json
import os

from pydantic import ValidationError

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import BRENHAM_LANE_DIALECT
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.symbol_conduit_lane import resolve_bore
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_design_path_adherence_proof import PATRICK_DESIGN_GRADES
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.review.design_stroke_cards import (
    GRADE_ACCEPTED,
    GRADE_UNGRADED,
    KIND_PICK,
    KIND_STROKE,
    DesignStrokeCard,
    DesignStrokeCardPacket,
    artifact_ref,
    build_card_packet,
    card_from_outcome,
)
from truelinev2.match.frames import _build_plan_frame_graph

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "design_stroke_cards"
SWEEP_PNG_DIR = _REPO_ROOT / "data" / "outputs" / "symbol_conduit_lane_sweep"
ELIGIBLE = ("bore_log25", "bore_log51", "bore_log59", "bore_log65")
PICKS = ("bore_log2", "bore_log9", "bore_log23", "bore_log50", "bore_log57")


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.15] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.15] STOP: inputs missing")
        return 2
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)}
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.15] STOP: corpus drift ({len(corpus)})")
        return 3
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    plan = PlanPdf(PDF)
    ok = True
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        graph = _build_plan_frame_graph(plan, offset)
        outcomes = []
        before = {}
        for stem in ELIGIBLE + PICKS:
            bore = load_borelog(str(corpus[stem]))
            out = resolve_bore(plan, bore, offset, BRENHAM_LANE_DIALECT,
                               frame_graph=graph)
            outcomes.append(out)
            before[out.bore_id] = json.dumps(out.to_dict(), sort_keys=True,
                                             default=str)

        packet, refusals = build_card_packet(outcomes, PATRICK_DESIGN_GRADES)
        g1 = (packet.kind_counts == {KIND_STROKE: 4, KIND_PICK: 5}
              and not refusals and len(packet.cards) == 9)
        print(f"[m8.15] {'PASS' if g1 else 'FAIL'}  G1 packet: "
              f"{packet.kind_counts}, refusals={refusals}")
        ok &= g1

        by_id = {c.bore_id: c for c in packet.cards}
        out_by_id = {o.bore_id: o for o in outcomes}
        g2 = all(json.dumps(out_by_id[b].to_dict(), sort_keys=True, default=str)
                 == before[b] for b in before)
        for stem in ELIGIBLE:
            bid = stem.replace("bore_", "")
            card, out = by_id[bid], out_by_id[bid]
            want = [s.to_dict() for s in out.segments]
            got = [{"sheet": s.sheet, "start_ft": s.start_ft,
                    "end_ft": s.end_ft,
                    "stroke_points": [list(p) for p in s.stroke_points]}
                   for s in card.segments]
            g2 &= got == want
        print(f"[m8.15] {'PASS' if g2 else 'FAIL'}  G2 geometry VERBATIM + "
              f"outcomes unmutated")
        ok &= g2

        g3 = all(by_id[s.replace('bore_', '')].design_grade == GRADE_ACCEPTED
                 for s in ELIGIBLE)
        ungraded_packet, _ = build_card_packet(
            [out_by_id["log25"]], {})  # empty provenance -> UNGRADED
        g3 &= ungraded_packet.cards[0].design_grade == GRADE_UNGRADED
        print(f"[m8.15] {'PASS' if g3 else 'FAIL'}  G3 grade provenance: 4x "
              f"{GRADE_ACCEPTED} backed by the banked record; empty record "
              f"-> {GRADE_UNGRADED}")
        ok &= g3

        # G4 masquerade refusals, live
        pick_card = by_id["log50"]
        stroke_card = by_id["log25"]
        try:
            DesignStrokeCard(**{**pick_card.model_dump(),
                                "segments": stroke_card.model_dump()["segments"],
                                "artifact_refs": ()})
            g4a = False
        except ValidationError:
            g4a = True
        try:
            DesignStrokeCardPacket(
                kind_counts={KIND_STROKE: 1}, accepted_grades={},
                cards=(stroke_card,))
            g4b = False
        except ValidationError:
            g4b = True
        g4 = g4a and g4b
        print(f"[m8.15] {'PASS' if g4 else 'FAIL'}  G4 masquerade refused: "
              f"suggestion+geometry={g4a}, unbacked-accepted-claim={g4b}")
        ok &= g4

        g5 = True
        for c in packet.cards:
            out = out_by_id[c.bore_id]
            g5 &= ([e.model_dump() for e in c.evidence_chain]
                   == [e.to_dict() for e in out.evidence])
        ref_report = {}
        for stem in ELIGIBLE:
            bid = stem.replace("bore_", "")
            for seg, ref in zip(by_id[bid].segments, by_id[bid].artifact_refs):
                g5 &= ref == artifact_ref(bid, seg.sheet)
                ref_report[ref] = (SWEEP_PNG_DIR / ref).is_file()
        print(f"[m8.15] {'PASS' if g5 else 'FAIL'}  G5 evidence verbatim + "
              f"artifact refs canonical (on disk: {ref_report})")
        ok &= g5

        import truelinev2.match.engine as engine_mod
        import truelinev2.match.symbol_conduit_lane as lane_mod
        import truelinev2.review.design_stroke_cards as bridge_mod
        import truelinev2.service as service_mod
        bridge_src = inspect.getsource(bridge_mod)
        g6 = (all("design_stroke_cards" not in inspect.getsource(m)
                  for m in (engine_mod, service_mod, lane_mod))
              and "truelinev2.proof" not in bridge_src)
        print(f"[m8.15] {'PASS' if g6 else 'FAIL'}  G6 bridge UNWIRED "
              f"(engine/service/lane never import it; bridge imports no proof)")
        ok &= g6

        report = {
            "milestone": ("truelinev2 M8.15 -- design-stroke reviewer-card "
                          "bridge proof (9 cards; unwired)"),
            "corpus_dir_used": corpus_dir, "corpus_resolution": how,
            "plan_pdf": PDF, "verdict": "PASS" if ok else "FAILURE",
            "honesty": ("cards carry lane geometry/evidence VERBATIM; "
                        "suggestions can never masquerade as placements "
                        "(validator-live-tested); grades only from the banked "
                        "provenance record; REVIEW-only; the M8.10/M8.11 "
                        "reviewer contracts are untouched; the bridge is "
                        "consumed by this proof only"),
            "kind_counts": packet.kind_counts,
            "refusals": refusals,
            "packet": packet.model_dump(),
        }
        (OUT_DIR / "design_stroke_cards_proof.json").write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"[m8.15] verdict: {report['verdict']}")
        print(f"[m8.15] report -> {OUT_DIR / 'design_stroke_cards_proof.json'}")
    finally:
        plan.close()
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
