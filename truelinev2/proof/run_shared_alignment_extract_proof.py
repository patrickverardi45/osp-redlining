r"""M8.20 -- shipped engine extractor proof (proof-only verification).

Proves the shipped, convention-agnostic ``match.shared_alignment_extract``
reproduces the proof-only M8.18/M8.19 extraction and feeds Law 1 + the group
card, over the WHOLE corpus, without importing proof code into the engine:

  G1  extract_group_claims over all 58 bores -> EXACTLY the log8/log32 claims
      (survivor NEXTLINK@378,409, boundaries {1+76,1+77}, conduit + multi-port
      evidence, M8.19 join PROVEN), banked-value pinned;
  G2  log42 yields NO claim (0 survivors -- never promoted);
  G3  the shipped claims drive shared_alignment_verdict -> V_REVIEW and
      build_group_review_card -> the group card (members/origin/boundaries);
  G4  per-bore resolve_bore is UNCHANGED (the trio stays blocked);
  G5  the shipped extractor's claims EQUAL the proof-of-concept law-probe
      claims (faithful promotion);
  G6  the engine module imports NO proof code;
  G7  nothing is rendered.

Outputs (gitignored): data/outputs/shared_alignment_extract_proof/
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_shared_alignment_extract_proof
"""
from __future__ import annotations

import inspect
import json
import os

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import BRENHAM_LANE_DIALECT
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match import shared_alignment_extract as extract
from truelinev2.match.shared_alignment import V_REVIEW, shared_alignment_verdict
from truelinev2.match.shared_alignment_extract import (
    extract_group_claims,
    origin_chain_boundaries,
)
from truelinev2.match.symbol_conduit_lane import S_STRUCTURE_REQUIRED, resolve_bore
from truelinev2.proof.run_brenham_corpus import PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.proof.run_shared_alignment_law_probe import _claim as _probe_claim
from truelinev2.proof.run_shared_origin_adjudication_probe import TARGETS
from truelinev2.review.group_review import build_group_review_card
from truelinev2.service import _build_plan_frame_graph

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "shared_alignment_extract_proof"


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.20-extract] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.20-extract] STOP: inputs missing")
        return 2
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUT_DIR / "shared_alignment_extract_proof.json"
    report_path.unlink(missing_ok=True)

    plan = PlanPdf(PDF)
    ok = True
    try:
        dialect = select_dialect(plan)
        off = dialect.calibrate(plan, 13)
        graph = _build_plan_frame_graph(plan, off)

        # Load ALL 58 bores (skip the banked adapter-gap source errors).
        bores = []
        for path in sorted(corpus.values()):
            try:
                bores.append(load_borelog(str(path)))
            except Exception:
                continue
        claims = extract_group_claims(plan, off, graph, BRENHAM_LANE_DIALECT, bores)
        by = {c.bore_id: c for c in claims}

        # G1 -- corpus-wide, EXACTLY the two log8/log32 claims, banked values.
        c8, c32 = by.get("log8"), by.get("log32")
        g1 = (sorted(by) == ["log32", "log8"]
              and c8 and c32
              and c8.survivor_id == c32.survivor_id == "NEXTLINK@378,409"
              and {c8.boundary_raw, c32.boundary_raw} == {"1+76", "1+77"}
              and c8.join_proven and c32.join_proven
              and c8.conduit_count >= 1 and c32.conduit_count >= 1
              and c8.origin_multiport and c32.origin_multiport
              and c8.chain_hops == (("0+00", "1+10", 110.0), ("1+10", "1+76", 66.0))
              and c32.chain_hops == (("0+00", "1+30", 130.0), ("1+30", "1+77", 47.0)))
        print(f"[m8.20-extract] {'PASS' if g1 else 'FAIL'}  G1 all-58 -> 2 claims "
              f"{sorted(by)}; survivor {c8.survivor_id if c8 else None}; "
              f"join_proven {c8.join_proven if c8 else None}/"
              f"{c32.join_proven if c32 else None}")
        ok &= g1

        # G2 -- log42 yields no claim.
        g2 = "log42" not in by
        print(f"[m8.20-extract] {'PASS' if g2 else 'FAIL'}  G2 log42 excluded "
              f"(no claim): {g2}")
        ok &= g2

        # G3 -- shipped claims drive the law + the group card.
        uni = origin_chain_boundaries(plan, off, graph, BRENHAM_LANE_DIALECT,
                                      18, 22, "0+00")
        verdict = shared_alignment_verdict(list(claims),
                                           origin_chain_boundaries=uni)
        statuses = {b.bore_id: resolve_bore(plan, b, off, BRENHAM_LANE_DIALECT,
                                            frame_graph=graph).status
                    for b in bores if b.bore_id in ("log8", "log32", "log42")}
        card = build_group_review_card(verdict, list(claims), statuses)
        g3 = (verdict["verdict"] == V_REVIEW and card is not None
              and sorted(m.bore_id for m in card.members) == ["log32", "log8"]
              and card.shared_origin == "NEXTLINK@378,409"
              and sorted(card.boundaries) == ["1+76", "1+77"])
        print(f"[m8.20-extract] {'PASS' if g3 else 'FAIL'}  G3 law+card from "
              f"shipped claims: {verdict['verdict']}, members "
              f"{sorted(m.bore_id for m in card.members) if card else None}")
        ok &= g3

        # G4 -- per-bore resolve_bore UNCHANGED (the trio stays blocked).
        g4 = all(statuses.get(b) == S_STRUCTURE_REQUIRED
                 for b in ("log8", "log32", "log42"))
        print(f"[m8.20-extract] {'PASS' if g4 else 'FAIL'}  G4 resolve_bore "
              f"unchanged: {statuses}")
        ok &= g4

        # G5 -- the shipped extractor EQUALS the proof-of-concept law-probe claim
        # (faithful promotion of the proof-only extraction into the engine).
        by_target = {t[0]: t for t in TARGETS}
        eq = True
        for bid, c in (("log8", c8), ("log32", c32)):
            pc = _probe_claim(plan, off, graph, *by_target[bid])
            eq &= (pc.survivor_id == c.survivor_id
                   and pc.boundary_raw == c.boundary_raw
                   and pc.chain_hops == c.chain_hops
                   and pc.conduit_count == c.conduit_count
                   and pc.origin_multiport == c.origin_multiport
                   and pc.walk_points == c.walk_points
                   and pc.boundary_xy == c.boundary_xy)
        print(f"[m8.20-extract] {'PASS' if eq else 'FAIL'}  G5 shipped == "
              f"proof-of-concept law-probe claims (faithful promotion)")
        ok &= eq

        # G6 -- the engine module imports NO proof code.
        src = inspect.getsource(extract)
        g6 = "truelinev2.proof" not in src and ".proof." not in src
        print(f"[m8.20-extract] {'PASS' if g6 else 'FAIL'}  G6 engine module "
              f"imports no proof")
        ok &= g6

        # G7 -- nothing rendered.
        g7 = not list(OUT_DIR.glob("*.png"))
        print(f"[m8.20-extract] {'PASS' if g7 else 'FAIL'}  G7 no artifact rendered")
        ok &= g7

        report = {
            "milestone": ("truelinev2 M8.20 -- shipped engine extractor "
                          "(extract_group_claims; proof-only verification)"),
            "corpus_dir_used": corpus_dir, "corpus_resolution": how,
            "plan_pdf": PDF, "verdict": "PASS" if ok else "FAILURE",
            "claims": [{"bore_id": c.bore_id, "survivor_id": c.survivor_id,
                        "boundary_raw": c.boundary_raw,
                        "join_proven": c.join_proven,
                        "conduit_count": c.conduit_count,
                        "origin_multiport": c.origin_multiport,
                        "chain_hops": c.chain_hops} for c in claims],
            "lane_statuses": statuses,
        }
        report_path.write_text(json.dumps(report, indent=2, default=str),
                               encoding="utf-8")
        print(f"[m8.20-extract] report -> {report_path}")
    finally:
        plan.close()

    print(f"[m8.20-extract] {'PASS' if ok else 'FAILURE'}")
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
