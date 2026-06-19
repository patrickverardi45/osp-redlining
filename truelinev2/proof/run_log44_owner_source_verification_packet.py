r"""LOG44 OWNER SOURCE VERIFICATION PACKET builder (read-only; renders NO redline;
investigation only -- the minimum owner-input artifact needed to unlock log44).

log44 (= bore_log17 Segment B) is the last *close* source-gated bore on the
frontier. Corpus says print 18, 0+00->3+25 (325'); sheet 18 has NO matching run
(engine-confirmed by run_log17_family_abstain_probe: chain 0+00->3+25 =
CALLOUT_CHAIN_NONE, ends_at_3+25 = 0). The continued-31 adjudication trace points
instead to a sheet-13 Woodson Ln drop (AP-158 TERMINAL 8 PORT HH @ STA 2+45 ->
FLOWER POT @ STA 3+23, 1404 Woodson Ln) fed by a sheet-10 high-station chain
(39+79 -> 43+36). This packet puts the three locations side by side so the owner
can answer ONE question that either unlocks a render or names the missing source.

Builds (gitignored, helper-color overlays ONLY -- NO red TrueLine stroke):
  1. log44_panel_sheet18_corpus.png   -- corpus print-18 location: the only 0+00
     runs are 3 short E/W PORT TERMINAL TAIL drops (AP-145/146/147); no 3+25,
     no 325', no Woodson  (MAGENTA = corpus claim, no matching run)
  2. log44_panel_sheet13_candidate.png-- sheet 13: AP-158 TERMINAL 8 PORT HH
     (STA 2+45, candidate START) -> FLOWER POT (STA 3+23, candidate END),
     1404 Woodson Ln  (GREEN start / LIME end / CYAN address)
  3. log44_panel_sheet10_chain.png    -- sheet 10: 39+79 -> 43+36 high-station
     chain; 43+36 = adjudication-proposed upstream cross-sheet point feeding the
     Woodson run  (ORANGE chain point / CYAN corridor)
  4. log44_owner_questions.png        -- the 3 verbatim owner questions + legend
  5. log44_engine_action_per_answer.png-- expected engine action for each answer
  6. log44_owner_source_verification_contact.png -- all of the above stacked
  + log44_owner_source_verification_packet.json   -- machine-readable sidecar

NO stroke placed; NO census/corpus/fixture mutation; NO AUTO; nothing rendered;
the ONLY colors are diagnostic helpers (red is reserved for committed redlines
and none is drawn here). Output dir gitignored.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log44_owner_source_verification_packet
"""
from __future__ import annotations

import json

from PIL import Image, ImageDraw

from truelinev2.config import _REPO_ROOT
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import PDF
# reuse the proven log61 review-pack visual helpers (helper colors; no red)
from truelinev2.proof.run_log61_review_pack import (CYAN, GREEN, LIME, MAGENTA,
                                                    ORANGE, annotated, banner,
                                                    contact, font)

OUT = _REPO_ROOT / "data" / "outputs" / "log44_owner_source_verification_packet"

# ---- verbatim owner questions (also printed on the PNG + JSON) --------------
QUESTIONS = [
    "Q1. Is log44 actually the SHEET-13 WOODSON LN run "
    "(AP-158 TERMINAL 8 PORT HH -> FLOWER POT), not the corpus print-18 entry?",
    "Q2. What is the correct START: the sheet-10 43+36 chain point (cross-sheet), "
    "the AP-158 terminal HH (local STA 2+45), or a local 0+00?",
    "Q3. Is the END the STA 3+23 FLOWER POT on 1404 Woodson Ln?",
]

# ---- expected engine action per possible answer (printed + JSON) ------------
ENGINE_ACTIONS = [
    ("A1  start = AP-158 terminal HH (local 2+45),  end = 3+23 FLOWER POT",
     "Render the LOCAL sheet-13 drop AP-158 TERMINAL 8 PORT HH -> 3+23 FLOWER "
     "POT (~78' local). End binds by printed AP-158 / flower-pot identity -- the "
     "clean single-sheet case (renders like log42's AP-105 terminal). SAFE once "
     "owner confirms identity; source supplies the coordinates."),
    ("A2  start = sheet-10 43+36 chain point (cross-sheet)",
     "Assemble the cross-sheet route sheet10 (...->43+36) + SEE-SHEET -> sheet13 "
     "Woodson (2+45 -> 3+23). Render ONLY if (a) the 43+36<->sheet-13 matchline "
     "join is SOURCE-PRINTED (no invented coords) AND (b) the assembled route is "
     "non-overlapping with already-drawn bores. If the join is not printed -> "
     "stays abstained pending the matchline source."),
    ("A3  corpus print 18 (0+00 -> 3+25) is correct",
     "No 325' / 3+25 run exists on sheet 18 (engine-confirmed). Owner must point "
     "to the actual sheet-18 run/source (which structure, which 0+00, the true "
     "end). Until supplied, log44 stays END_IDENTITY_UNPRINTED ABSTAIN -- the "
     "current correct, zero-false state."),
]

LEGEND = [
    ("GREEN  = candidate START (AP-158 TERMINAL 8 PORT HH, STA 2+45)", GREEN),
    ("LIME   = candidate END (FLOWER POT, STA 3+23)", LIME),
    ("CYAN   = Woodson Ln corridor / 1404 address id", CYAN),
    ("ORANGE = sheet-10 chain / proposed cross-sheet point (43+36)", ORANGE),
    ("MAGENTA= corpus print-18 location with NO matching 325' run", MAGENTA),
    ("(NO RED: nothing is rendered -- awaiting the owner answer)", None),
]


def text_panel(title, rows, width=1040, title_bar=(18, 38, 86)):
    """rows: list of (text, swatch_color_or_None). Renders a clean text card."""
    f_t, f_b = font(30), font(23, bold=False)
    line_h, title_h, pad = 34, 50, 14
    tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))

    def wrap(s, maxw):
        words, lines, cur = s.split(" "), [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if tmp.textlength(t, font=f_b) <= maxw:
                cur = t
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines or [s]

    flat = []
    for text, color in rows:
        wrapped = wrap(text, width - 60)
        for i, ln in enumerate(wrapped):
            flat.append((ln, color if i == 0 else None))
    height = title_h + pad + line_h * len(flat) + pad
    canvas = Image.new("RGB", (width, height), (255, 255, 255))
    d = ImageDraw.Draw(canvas)
    d.rectangle((0, 0, width, title_h), fill=title_bar)
    d.text((14, 9), title, font=f_t, fill=(255, 255, 255))
    y = title_h + pad
    for ln, color in flat:
        if color:
            d.rectangle((16, y + 3, 32, y + 20), fill=color)
        d.text((42 if color else 18, y), ln, font=f_b, fill=(15, 15, 15))
        y += line_h
    return canvas


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for s in OUT.glob("*.png"):
        s.unlink()
    plan = PlanPdf(PDF)
    paths = {}
    try:
        off = select_off(plan)

        # ---- Panel 1: sheet 18 corpus claim (no matching run) --------------
        img18 = annotated(plan, off, 18, [
            ("AP-145", "AP-145 E/W PORT TERMINAL TAIL (0+00 drop, ~165')", MAGENTA),
            ("AP-146", "AP-146 E/W PORT TERMINAL TAIL (0+00 drop, ~130')", MAGENTA),
            ("AP-147", "AP-147 E/W PORT TERMINAL TAIL (0+00 drop, ~110')", MAGENTA),
        ], zoom=2.2, pad=70)
        if img18 is None:
            img18 = annotated(plan, off, 18, [("AP-145", "AP-145 0+00 tail", MAGENTA)])
        img18 = banner(img18, "CORPUS CLAIM (print 18): only 0+00 runs are short "
                              "E/W PORT TERMINAL TAIL drops -- NO 3+25 / 325' / "
                              "Woodson here", bar=(120, 0, 80))
        p1 = OUT / "log44_panel_sheet18_corpus.png"; img18.save(str(p1)); paths["sheet18"] = p1

        # ---- Panel 2: sheet 13 Woodson candidate ---------------------------
        img13 = annotated(plan, off, 13, [
            ("AP-158", "AP-158 TERMINAL 8 PORT HH = candidate START", GREEN),
            ("2+45", "STA 2+45 (AP-158 terminal HH station)", GREEN),
            ("3+23", "STA 3+23 FLOWER POT = candidate END", LIME),
            ("1404", "1404 WOODSON LN (address / corridor id)", CYAN),
        ], zoom=2.6, pad=64)
        if img13 is None:
            img13 = annotated(plan, off, 13, [("AP-158", "AP-158 terminal HH", GREEN),
                                              ("3+23", "STA 3+23 FLOWER POT", LIME)])
        img13 = banner(img13, "CANDIDATE (sheet 13, 1404 Woodson Ln): AP-158 "
                              "TERMINAL 8 PORT HH (2+45) -> FLOWER POT (3+23)",
                       bar=(0, 90, 130))
        p2 = OUT / "log44_panel_sheet13_candidate.png"; img13.save(str(p2)); paths["sheet13"] = p2

        # ---- Panel 3: sheet 10 chain context -------------------------------
        img10 = annotated(plan, off, 10, [
            ("39+79", "STA 39+79 (chain lower bound)", CYAN),
            ("43+36", "STA 43+36 = proposed upstream cross-sheet point", ORANGE),
            ("WOODSON", "WOODSON LN corridor continues on sheet 10", CYAN),
        ], zoom=2.0, pad=70)
        if img10 is None:
            img10 = annotated(plan, off, 10, [("43+36", "STA 43+36 chain point", ORANGE)])
        img10 = banner(img10, "CHAIN CONTEXT (sheet 10): 39+79 -> 43+36 high-"
                              "station chain; 43+36 = proposed cross-sheet point "
                              "feeding the Woodson run", bar=(150, 90, 0))
        p3 = OUT / "log44_panel_sheet10_chain.png"; img10.save(str(p3)); paths["sheet10"] = p3

        # ---- Panel 4: owner questions + legend -----------------------------
        q_rows = [(q, None) for q in QUESTIONS] + [("", None)] + LEGEND
        imgq = text_panel("OWNER QUESTIONS  (answer ONE of A1 / A2 / A3 below)", q_rows)
        p4 = OUT / "log44_owner_questions.png"; imgq.save(str(p4)); paths["questions"] = p4

        # ---- Panel 5: engine action per answer -----------------------------
        a_rows = []
        for head, body in ENGINE_ACTIONS:
            a_rows.append((head, GREEN))
            a_rows.append(("    -> " + body, None))
        imga = text_panel("EXPECTED ENGINE ACTION PER ANSWER", a_rows)
        p5 = OUT / "log44_engine_action_per_answer.png"; imga.save(str(p5)); paths["actions"] = p5

        # ---- Contact sheet (everything stacked) ----------------------------
        p6 = contact([
            (Image.open(str(p4)), "OWNER QUESTIONS + helper-color legend"),
            (Image.open(str(p1)), "1. CORPUS CLAIM -- sheet 18 (no 325' / 3+25 / Woodson run)"),
            (Image.open(str(p2)), "2. CANDIDATE -- sheet 13 Woodson (AP-158 2+45 -> FLOWER POT 3+23)"),
            (Image.open(str(p3)), "3. CHAIN CONTEXT -- sheet 10 (39+79 -> 43+36 cross-sheet point)"),
            (Image.open(str(p5)), "EXPECTED ENGINE ACTION PER ANSWER (A1 / A2 / A3)"),
        ], "LOG44 OWNER SOURCE VERIFICATION -- is log44 the sheet-13 Woodson run?  "
           "(NOT rendered; awaiting owner answer)",
           OUT / "log44_owner_source_verification_contact.png", panel_w=900)
        paths["contact"] = p6

        # ---- JSON sidecar --------------------------------------------------
        report = {
            "target": "log44 (= bore_log17 Segment B)",
            "purpose": ("minimum owner source-verification packet to unlock "
                        "log44; NOT a render"),
            "corpus_claim": {"print": 18, "span": "0+00 -> 3+25", "footage_ft": 325},
            "sheet18_evidence": {
                "result": "NO matching run at corpus location",
                "detail": ("the only 0+00 runs on sheet 18 are 3 short E/W PORT "
                           "TERMINAL TAIL drops to AP-145 (~165'), AP-147 (~110'), "
                           "AP-146 (~130'); 3+25 NOT FOUND, 3+23 NOT FOUND, "
                           "Woodson NOT FOUND"),
                "engine_confirmed": ("run_log17_family_abstain_probe G6: chain "
                                     "0+00->3+25 = CALLOUT_CHAIN_NONE; "
                                     "ends_at_3+25 = 0"),
            },
            "sheet13_candidate_evidence": {
                "address": "1404 Woodson Ln",
                "start": "AP-158 TERMINAL 8 PORT HH @ STA 2+45 (printed, unique)",
                "end": "FLOWER POT @ STA 3+23 (printed, unique)",
                "local_footage_ft": 78,
                "note": ("local drop 2+45->3+23 = 78' (NOT 325'); the corpus 325' "
                         "may be the full sheet-10-chain + sheet-13 run or a "
                         "mis-record -- which is exactly why the START (Q2) must "
                         "be owner-confirmed"),
                "flower_pot_anchor_caveat": ("generic 'FLOWER POT' search hits a "
                                             "different Woodson terminal first; "
                                             "anchored on the unique STA 3+23"),
            },
            "sheet10_chain_evidence": {
                "chain": "39+79 -> 43+36 (high-station, on the sheet-10 mainline)",
                "cross_sheet_point": ("43+36 = adjudication-proposed upstream "
                                      "point that would feed the sheet-13 Woodson "
                                      "drop (join NOT engine-found -> owner-gated)"),
                "corridor": "Woodson Ln also printed on sheet 10",
            },
            "owner_questions": QUESTIONS,
            "engine_action_per_answer": {
                "A1_local_terminal_to_flowerpot": ENGINE_ACTIONS[0][1],
                "A2_sheet10_4336_chain_point": ENGINE_ACTIONS[1][1],
                "A3_corpus_print18_correct": ENGINE_ACTIONS[2][1],
            },
            "posture": {
                "render_attempted": False,
                "red_stroke_drawn": False,
                "overlays": "helper colors only (green/lime/cyan/orange/magenta)",
                "census_frozen": True,
                "corpus_census_fixture_mutated": False,
                "origin_main_touched": False,
                "deploy": False,
            },
            "artifacts": {k: str(v) for k, v in paths.items()},
        }
        rp = OUT / "log44_owner_source_verification_packet.json"
        rp.write_text(json.dumps(report, indent=2), encoding="utf-8")
        paths["json"] = rp
    finally:
        plan.close()

    import os
    for k, v in paths.items():
        print(f"[log44-packet] {k}: {v}  ({os.path.getsize(v)} bytes)")
    return 0


def select_off(plan):
    from truelinev2.extract.registry import select_dialect
    return select_dialect(plan).calibrate(plan, 13)


if __name__ == "__main__":
    raise SystemExit(main())
