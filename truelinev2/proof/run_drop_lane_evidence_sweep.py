r"""M8.14.b.8 -- drop-lane evidence sweep (log5/30/48/50/65; sheet-honest).

Runs the proven b.4 (flower-pot end binding) + b.6 (conduit-origin topology)
chain across the five drop-lane bores. ZERO-FALSE FIRST: a stroke renders
ONLY when every gate passes; this sweep's honest result is **zero strokes**
and a typed classification per bore, each abstain carrying its exact missing
evidence artifact. The b.7-graded chain is applied, never widened.

Per-bore law (all general; layers/colors injected from the dialect tables):
  1. END identity: printed ``STA <end> FLOWER POT`` note on a referenced
     sheet (b.1 grammar) -> b.4 position binding (context-disambiguated
     label box -> leader -> symbol cluster, black class fill).
  2. START origin: conduit segments (callout conduit class -> dialect conduit
     layer) graph-connected to the bound end footprint (orientation-free
     ``connected_chain``) -> dash endpoints inside EXACTLY ONE start-side
     structure footprint.
  3. SPAN corroboration (the multi-drive trap gate, proven live on log50):
     the bound start/end pair distance over the BORE span must agree with the
     sheet's clean-ladder scale. A real drawn conduit run that is only PART
     of the bore (cross-sheet multi-drive) fails this and is REFUSED.

Classification taxonomy:
  CONDUIT_ORIGIN_BOUND        end + origin + span all bound -> stroke eligible
  PICK_CARD_WITH_END_ANCHOR   end bound; an origin CANDIDATE exists but is
                              refused by a gate (reviewer picks/confirms)
  POSITION_BOUND_END_ONLY     end bound; NO on-sheet origin candidate (chain
                              exits the sheet)
  END_IDENTITY_UNPRINTED      no printed end note on any referenced sheet

Expected (pinned by gates; a future plan edition that prints more evidence
fails them LOUDLY and upgrades the lane):
  log5/30/48 -> END_IDENTITY_UNPRINTED
  log50      -> PICK_CARD_WITH_END_ANCHOR (end pot 5+14 bound on s11; the
                AP-168 HH at printed STA 1+89 is conduit-connected but the
                1+89->5+14 chain is 325 ft vs the bore's 514 ft -> span
                REFUSED; the bore's 0+00 lies up-chain, cross-sheet)
  log65      -> POSITION_BOUND_END_ONLY (end pot 6+50 bound on s9; the s9
                conduit is the 39-ft stub exiting toward sheet 10)
Named missing capability for both blocked starts (ONE general artifact):
**matchline-joined cross-sheet conduit chain assembly**.

Outputs (gitignored): data/outputs/drop_lane_evidence_sweep/ (JSON only;
structurally ZERO stroke PNGs).

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_drop_lane_evidence_sweep
"""
from __future__ import annotations

import json
import math
import os
from typing import Optional, Sequence

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.conduit_topology import (
    ORIGIN_BOUND,
    connected_chain,
    dash_endpoints,
    discriminate_origin,
    ladder_scale_for_band,
    symbol_footprint,
)
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_anchor import BOUND, bind_end_structure_note
from truelinev2.extract.structure_position import (
    BRENHAM_CONDUIT_LAYERS,
    BRENHAM_STRUCTURE_LAYERS,
    POSITION_BOUND,
    cluster_symbols,
    corroborate_pair_scale,
    resolve_structure_position,
)
from truelinev2.extract.tick_path import route_ladder_ticks
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "drop_lane_evidence_sweep"
SWEEP = ("bore_log5", "bore_log30", "bore_log48", "bore_log50", "bore_log65")

C_BOUND = "CONDUIT_ORIGIN_BOUND"
C_PICK = "PICK_CARD_WITH_END_ANCHOR"
C_END_ONLY = "POSITION_BOUND_END_ONLY"
C_UNPRINTED = "END_IDENTITY_UNPRINTED"
CROSS_SHEET = ("matchline-joined cross-sheet conduit chain assembly (the "
               "drawn conduit continues beyond this sheet; joining chains "
               "across the matchline is the named missing capability)")

EXPECTED = {
    "log5": C_UNPRINTED, "log30": C_UNPRINTED, "log48": C_UNPRINTED,
    "log50": C_PICK, "log65": C_END_ONLY,
}


# --- pure classification (offline-testable) ---------------------------------------------

def classify_drop_bore(*, end_bound: bool, origin_result: Optional[str],
                       span_consistent: Optional[bool]) -> str:
    """The sweep taxonomy. A bore is stroke-eligible ONLY when end + origin +
    span are all bound; an origin candidate refused by any gate is a pick-card
    (the candidate is shown, never placed); no candidate -> end-only."""
    if not end_bound:
        return C_UNPRINTED
    if origin_result == ORIGIN_BOUND:
        return C_BOUND if span_consistent else C_PICK
    return C_END_ONLY


def sweep_bore(plan: PlanPdf, bore, offset: int) -> dict:
    row: dict = {"bore_id": bore.bore_id,
                 "span": f"{bore.station_start}->{bore.station_end}",
                 "span_ft": bore.station_end_ft - bore.station_start_ft,
                 "sheets_checked": sorted(set(bore.sheet_refs))}
    end_sheet = end_pos = None
    for sheet in sorted(set(bore.sheet_refs)):
        lines = plan.lines(sheet, offset)
        end_id = bind_end_structure_note(bore.station_end_ft, lines)
        if end_id.result != BOUND or "FLOWER" not in (end_id.structure_label or "").upper():
            continue
        pos = resolve_structure_position(
            label_text=end_id.end_station, structure_class="flower_pot",
            words=plan.words(sheet, offset),
            drawings=plan.line_items(sheet, offset),
            layer_table=BRENHAM_STRUCTURE_LAYERS, context_texts=("FLOWER", "POT"))
        if pos.result == POSITION_BOUND:
            end_sheet, end_pos = sheet, pos
            row["end"] = {"sheet": sheet, "note": end_id.note_line,
                          "structure": end_id.structure_label,
                          "symbol_xy": [round(v, 1) for v in pos.symbol_xy]}
            break
    if end_pos is None:
        row["classification"] = classify_drop_bore(
            end_bound=False, origin_result=None, span_consistent=None)
        row["named_missing"] = (
            f"printed end-structure note 'STA "
            f"{bore.station_end} <structure>' on sheets "
            f"{sorted(set(bore.sheet_refs))} -- the end identity is unprinted; "
            f"no end anchor can exist (b.4 law)")
        return row

    drawings = plan.line_items(end_sheet, offset)
    conduit_layer = BRENHAM_CONDUIT_LAYERS["VACANT HDPE"]
    end_bb = symbol_footprint(drawings, "FLOWER POT", tuple(end_pos.symbol_xy))
    segs = [d for d in drawings if d["layer"] == conduit_layer]
    chain = connected_chain(segs, end_bb)
    pts = dash_endpoints(chain)
    cands = {}
    for lay in ("NEXTLINK", "FLOWER POT"):
        for c in cluster_symbols(drawings, lay):
            if math.hypot(c.x - end_pos.symbol_xy[0],
                          c.y - end_pos.symbol_xy[1]) <= 8:
                continue  # the end pot itself is never a start candidate
            bb = symbol_footprint(drawings, lay, (c.x, c.y))
            if bb:
                cands[f"{lay}@{c.x:.0f},{c.y:.0f}"] = bb
    disc = discriminate_origin(pts, cands)
    row["conduit"] = {"layer": conduit_layer, "chain_segments": len(chain),
                      "discrimination": disc["result"], "winner": disc["winner"]}

    span_ok = None
    if disc["result"] == ORIGIN_BOUND:
        win_bb = cands[disc["winner"]]
        win_xy = ((win_bb[0] + win_bb[2]) / 2.0, (win_bb[1] + win_bb[3]) / 2.0)
        ticks, _ = route_ladder_ticks(plan, end_sheet, offset)
        scale = ladder_scale_for_band(ticks, end_pos.symbol_xy[1] - 30.0,
                                      end_pos.symbol_xy[1] + 30.0)
        if scale:
            corr = corroborate_pair_scale(win_xy, tuple(end_pos.symbol_xy),
                                          row["span_ft"], scale)
            span_ok = corr["consistent"]
            row["span_corroboration"] = corr
        else:
            span_ok = False
            row["span_corroboration"] = {"consistent": False,
                                         "reason": "no ladder band scale"}
        row["origin_candidate"] = {"label": disc["winner"],
                                   "symbol_xy": [round(v, 1) for v in win_xy]}

    row["classification"] = classify_drop_bore(
        end_bound=True, origin_result=disc["result"], span_consistent=span_ok)
    if row["classification"] == C_PICK:
        row["named_missing"] = (
            f"the conduit-connected candidate {disc['winner']} is REFUSED by "
            f"span corroboration (the on-sheet chain covers only part of the "
            f"bore); {CROSS_SHEET}")
    elif row["classification"] == C_END_ONLY:
        row["named_missing"] = CROSS_SHEET
    return row


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.14b8] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.14b8] STOP: inputs missing")
        return 2
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)}
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.14b8] STOP: corpus drift ({len(corpus)})")
        return 3
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    plan = PlanPdf(PDF)
    rows = []
    ok = True
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        for stem in SWEEP:
            bore = load_borelog(str(corpus[stem]))
            row = sweep_bore(plan, bore, offset)
            rows.append(row)
            want = EXPECTED[bore.bore_id]
            g = row["classification"] == want
            ok &= g
            print(f"[m8.14b8] {'PASS' if g else 'FAIL'}  {bore.bore_id:>6} "
                  f"{row['span']:>14} -> {row['classification']} (want {want})")
            if row.get("named_missing"):
                print(f"[m8.14b8]          missing: {row['named_missing'][:120]}")

        # structural zero-false gates
        strokes = sorted(p.name for p in OUT_DIR.glob("*.png"))
        g_zero = (strokes == []
                  and not any(r["classification"] == C_BOUND for r in rows))
        print(f"[m8.14b8] {'PASS' if g_zero else 'FAIL'}  ZERO strokes rendered "
              f"(no bore passed every gate): pngs={strokes}")
        ok &= g_zero
        # the two bound end anchors are pinned exactly (b.4 law, new positions)
        by_id = {r["bore_id"]: r for r in rows}
        g_ends = (by_id["log50"]["end"]["symbol_xy"] == [601.9, 351.9]
                  and by_id["log50"]["end"]["sheet"] == 11
                  and by_id["log65"]["end"]["symbol_xy"] == [1085.2, 356.1]
                  and by_id["log65"]["end"]["sheet"] == 9)
        print(f"[m8.14b8] {'PASS' if g_ends else 'FAIL'}  end anchors pinned: "
              f"log50 s11 {by_id['log50'].get('end', {}).get('symbol_xy')} / "
              f"log65 s9 {by_id['log65'].get('end', {}).get('symbol_xy')}")
        ok &= g_ends
        # log50's refused candidate is the printed AP-168 HH at STA 1+89
        g_50 = (by_id["log50"]["conduit"]["winner"] == "NEXTLINK@134,352"
                and by_id["log50"]["span_corroboration"]["consistent"] is False)
        print(f"[m8.14b8] {'PASS' if g_50 else 'FAIL'}  log50 candidate AP-168 "
              f"HH refused by span: {by_id['log50'].get('span_corroboration')}")
        ok &= g_50

        report = {
            "milestone": ("truelinev2 M8.14.b.8 -- drop-lane evidence sweep "
                          "(zero strokes; typed classifications + named "
                          "missing artifacts)"),
            "corpus_dir_used": corpus_dir, "corpus_resolution": how,
            "plan_pdf": PDF, "verdict": "PASS" if ok else "FAILURE",
            "honesty": ("the b.4+b.6+b.7 chain applied unwidened; strokes only "
                        "on full-gate pass (none qualified); every abstain "
                        "names its exact missing evidence; the log50 span gate "
                        "proves the multi-drive trap is caught structurally; "
                        "new banked positions: two end anchors + the AP-168 "
                        "candidate"),
            "classifications": {r["bore_id"]: r["classification"] for r in rows},
            "rows": rows,
        }
        (OUT_DIR / "drop_lane_evidence_sweep.json").write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"[m8.14b8] verdict: {report['verdict']}")
        print(f"[m8.14b8] report -> {OUT_DIR / 'drop_lane_evidence_sweep.json'}")
    finally:
        plan.close()
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
