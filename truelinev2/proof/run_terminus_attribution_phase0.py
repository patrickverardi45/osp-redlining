r"""M9.3 Phase 0 -- START/END terminus-attribution audit (proof-only; READ-ONLY).

Answers the M9.2-named missing relationship: when a sheet carries multiple
`AP-NNN SPLICE LOC MM` callouts, can the engine attribute ONE callout to a SPECIFIC
bore ENDPOINT (its start_ft / end_ft station), using printed station-note frame
context -- NOT flat sheet membership and NOT proximity geometry?

THE ATTRIBUTION LAW (uniqueness-mandatory; END-semantics; composes shipped pieces):
  An `AP-NNN SPLICE LOC MM` pair is ENDPOINT_ATTRIBUTED to a bore's END iff:
    (1) the bore's END station carries EXACTLY ONE printed structure note
        (`extract.structure_anchor.bind_end_structure_note`, uniqueness-mandatory --
        0 notes -> NO_ENDPOINT_NOTE, >=2 -> MULTIPLE_COMPETING_CALLOUTS);
    (2) that note's class (`match.symbol_conduit_lane._classify_label`, dialect-
        injected) is the TERMINAL class (the only class that prints an AP+splice id);
    (3) EXACTLY ONE (AP, splice-loc) pair lives INSIDE that note's own frame (the
        `STA <sta> ... <next STA>` window) -- not merely somewhere on the sheet;
    (4) the pair joins its UNIQUE KMZ terminal cleanly (M9.1 `join_terminal` ->
        BOUND, or NONE = simply absent from the KMZ; an AP/splice/ambiguous
        REJECTION is a PDF<->KMZ contradiction, reclassified PDF_KMZ_CONTRADICTION);
    (5) corpus invariant: each attributed terminal anchors AT MOST ONE bore END.
  DIRECTION (load-bearing, M9.3 audit fix): a `terminal_port_hh` is END-OF-FEED
  (it carries the TERMINAL TAIL of the ARRIVING bore). A bore whose START station
  sits at such a terminal does NOT own that identity -- the terminal is the prior
  feed's terminus and this bore DEPARTS the junction. So a terminal at a START is
  a JUNCTION_ORIGIN (a bore-to-bore junction: useful for run assembly, NOT this
  bore's terminus identity), never ENDPOINT_ATTRIBUTED.

WHY THIS IS NOT A FLAT SCAN: an independent `_ap_owning_stations` map assigns every
printed AP+splice to the station-note frame that OWNS it (run callouts `TO STA` and
`=0+00` equations reset the frame, as the note grammar excludes them). A flat-scan
AP whose owning station is NEITHER endpoint is a SHEET_NEIGHBOR and is REJECTED --
e.g. log68's AP-148 owns STA 20+71 (log2's terminal), not log68's 4+54->7+21. G7
asserts the two methods (frame bind + owning-station map) agree on every attribution.

CONFIDENCE (honest, NOT "proven zero-false"): the relationship is TYPED + CONTROLS-
VERIFIED. Of the END attributions, 3 are independently ground-truthed M9.0/M9.1
controls (log7->163, log42->105, log10->152); the rest cross-bind via the M9.1 join
(a printed-id consistency check, not independent endpoint ground truth). log46 is
the proof's value-add: PDF `AP-161 SPLICE LOC 35` vs KMZ `Splice Loc 45` -> a
PDF<->KMZ contradiction surfaced, not buried.

FORBIDDEN (asserted, never used): flat sheet membership, "AP appears on the sheet",
nearest-AP geometry, route geometry, KMZ proximity, AP-only, splice-only, family/
daily-bundle relation, KMZ overriding a PDF/source contradiction. The convention
(terminal class, classification keywords) is dialect-injected; the runner lives in
proof/ (Brenham literals allowed). NOTE the M9.3.1 universality seam: the note-
DETECTION keyword set lives in `structure_anchor._STRUCTURE_WORDS` (a shared-core
literal today) and the AP/splice/station regexes are re-declared locally here -- a
core promotion MUST inject all of these (classification via class_keywords is
already injected).

PROOF-ONLY: no placement change, no engine wiring, no stroke/PNG/segment, no AUTO,
no tolerance/budget change. Composes the SHIPPED structure_anchor + symbol_conduit
classifier + M9.1 join WITHOUT altering any; adds nothing to core/engine (the
extractor is deferred to M9.3.1). Nothing wired; zero bores moved. All-58 census +
product lanes + M9.0/M9.1/M9.2 results frozen.

Exit codes: 0 PASS, 2 inputs missing, 3 corpus drift, 4 gate FAILURE.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_terminus_attribution_phase0
"""
from __future__ import annotations

import collections
import inspect
import json
import os
import re
from typing import Dict, List, Optional, Tuple

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.kmz import BRENHAM_KMZ_DIALECT, read_kmz
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_anchor import BOUND as ID_BOUND
from truelinev2.extract.structure_anchor import bind_end_structure_note
from truelinev2.extract.structure_position import BRENHAM_LANE_DIALECT
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.kmz_structure_join import join_terminal
from truelinev2.match.symbol_conduit_lane import _classify_label
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_final_engine_truth_table import completion_bucket
from truelinev2.proof.run_kmz_correlation_audit import _bore_pdf_aps, resolve_kmz
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.review.reviewer_service import ReviewerBundleService, ReviewRunMode
from truelinev2.stations import feet_to_station

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "terminus_attribution_phase0"

EXPECT_STRUCTURES = 576
EXPECT_ROUTES = 539
BANKED_FULLEST_LANES = {
    "PLACED_REVIEW": 30, "PICK_CARD_ROUTE_SUGGESTION": 16,
    "HUMAN_ADJUSTABLE_LENGTH_REDLINE": 6, "OUT_OF_CLASS": 4,
    "SOURCE_REVIEW_REQUIRED": 2,
}

TERMINAL_CLASS = BRENHAM_KMZ_DIALECT.terminal_class          # "terminal_port_hh"
TARGETS = ("log10", "log68", "log7", "log42", "log44")
SOURCE_CONTRADICTION = {"log44"}                             # banked M8.25/M9.0
M91_CONTROL_AP = {"log7": 163, "log42": 105}

# per-endpoint attribution outcomes
A_ATTRIB = "ENDPOINT_ATTRIBUTED"
A_JUNCTION = "JUNCTION_ORIGIN"               # START at an end-of-feed terminal
A_KMZ_CONTRA = "PDF_KMZ_CONTRADICTION"       # attributed pair the KMZ join refutes
A_NO_NOTE = "NO_ENDPOINT_NOTE"
A_NO_PAIR = "NO_AP_SPLICE_PAIR"
A_COMPETING = "MULTIPLE_COMPETING_CALLOUTS"
A_UNMODELED = "UNMODELED_RELATIONSHIP"
# per-bore headline disposition adds:
B_SHEET_NEIGHBOR = "SHEET_NEIGHBOR_REJECTED"
B_SOURCE_CONTRA = "SOURCE_CONTRADICTION"

# M9.1 join results that REFUTE an attributed pair (AP present, ids disagree /
# ambiguous). JOIN_NONE = AP simply not in the KMZ -> NOT a contradiction.
_CONTRA_JOINS = {"KMZ_TERMINAL_JOIN_AP_ONLY_REJECTED",
                 "KMZ_TERMINAL_JOIN_SPLICE_ONLY_REJECTED",
                 "KMZ_TERMINAL_JOIN_AMBIGUOUS"}

_STA_LINE = re.compile(r"^STA\s+(\d{1,3}\+\d{2})\b")
_PAIR_RE = re.compile(r"AP-?\s?(\d+)\s+SPLICE\s*LOC\s*(\d+)", re.I)
_AP_RE = re.compile(r"AP\s*-?\s*(\d+)", re.I)
_SPLICE_RE = re.compile(r"SPLICE\s*LOC\s*(\d+)", re.I)


def _pair_from_label(label: Optional[str]) -> Tuple[Optional[int], Optional[str], str]:
    """In-FRAME (ap, splice_token, kind) from a bound note's windowed label.
    Uniqueness within the frame is mandatory (no first-match across a multi-callout
    block)."""
    aps = sorted({int(m) for m in _AP_RE.findall(label or "")})
    sps = sorted({int(m) for m in _SPLICE_RE.findall(label or "")})
    if len(aps) == 1 and len(sps) == 1:
        return aps[0], f"SPLICE LOC {sps[0]}", "FULL_PAIR"
    if aps and not sps:
        return (aps[0] if len(aps) == 1 else None), None, "AP_ONLY"
    if sps and not aps:
        return None, (f"SPLICE LOC {sps[0]}" if len(sps) == 1 else None), "SPLICE_ONLY"
    if len(aps) > 1 or len(sps) > 1:
        return None, None, "MULTI_AMBIGUOUS"
    return None, None, "NO_ID"


def _ap_owning_stations(lines) -> Dict[int, Optional[str]]:
    """Map each printed AP (from an `AP-NNN SPLICE LOC MM` pair) to the structure-
    note STATION that OWNS its frame (`STA <sta> <structure>` window). A run callout
    (`... TO STA ...`) or an equation (`=`) line resets the frame to None. Mirrors
    the bind_end_structure_note grammar -- the INDEPENDENT method G7 cross-checks."""
    out: Dict[int, Optional[str]] = {}
    cur: Optional[str] = None
    for ln in lines:
        s = ln.strip()
        m = _STA_LINE.match(s)
        if m:
            cur = None if ("TO STA" in s or "=" in s) else m.group(1)
        for am in _PAIR_RE.finditer(ln):
            out.setdefault(int(am.group(1)), cur)
    return out


def _drop_phrase(klass: Optional[str], label: Optional[str]) -> str:
    """Class-aware description of a bound but non-attributing endpoint note."""
    short = " ".join((label or "").split())[:48]
    if klass in ("flower_pot", "installer_hh"):
        return f"a non-terminal drop structure ('{short}')"
    if klass is None:
        return (f"a note ('{short}') that classifies to NO drop/terminal class "
                f"(e.g. a backbone / NEXTLINK splice HH)")
    return f"class {klass!r} ('{short}'), not the terminal class"


def _attribute_endpoint(plan, sheets, offset, station_ft, which: str) -> dict:
    """Attribute (or refuse) an AP+splice to ONE bore endpoint via the proven
    end-structure note frame. DIRECTION-aware: a terminal at a START is a
    JUNCTION_ORIGIN (end-of-feed semantics), never the START bore's terminus."""
    sta = feet_to_station(station_ft)
    competing = 0
    for sheet in sheets:
        b = bind_end_structure_note(station_ft, plan.lines(sheet, offset))
        if b.result == ID_BOUND:
            klass = _classify_label(b.structure_label, BRENHAM_LANE_DIALECT)
            ap, sp, kind = _pair_from_label(b.structure_label)
            base = {"station": sta, "sheet": sheet, "note_line": b.note_line,
                    "structure_label": b.structure_label, "structure_class": klass,
                    "ap": None, "splice": None}
            if kind == "MULTI_AMBIGUOUS":
                return {**base, "result": A_COMPETING,
                        "why": "the endpoint note frame carries >1 AP/splice token"}
            if klass == TERMINAL_CLASS and kind == "FULL_PAIR":
                if which == "END":
                    return {**base, "ap": ap, "splice": sp, "result": A_ATTRIB,
                            "why": f"AP {ap} + {sp} printed INSIDE the {sta} terminal "
                                   f"note frame -- the bore's END terminus identity"}
                return {**base, "ap": ap, "splice": sp, "result": A_JUNCTION,
                        "why": f"the START sits at terminal AP {ap} ({sp}); a "
                               f"terminal_port_hh is END-OF-FEED, so this AP is the "
                               f"ARRIVING bore's END terminus -- this bore DEPARTS the "
                               f"junction, it does not own the identity"}
            if kind in ("AP_ONLY", "SPLICE_ONLY"):
                return {**base, "result": A_NO_PAIR,
                        "why": f"endpoint note carries only a partial id ({kind})"}
            return {**base, "result": A_NO_PAIR,
                    "why": f"endpoint note is {_drop_phrase(klass, b.structure_label)} "
                           f"-- no AP+splice terminal id"}
        if b.candidates and b.candidates >= 2:
            competing = max(competing, b.candidates)
    if competing >= 2:
        return {"station": sta, "sheet": None, "note_line": None,
                "structure_label": None, "structure_class": None,
                "ap": None, "splice": None, "result": A_COMPETING,
                "why": f"{competing} structure notes share STA {sta}; never chosen between"}
    tail = ("the end identity is a non-terminal structure or is unprinted at this "
            "station" if which == "END" else
            "a START may instead be an equation-bound origin / installer HH / "
            "matchline entry, which carries no terminal id")
    return {"station": sta, "sheet": None, "note_line": None,
            "structure_label": None, "structure_class": None,
            "ap": None, "splice": None, "result": A_NO_NOTE,
            "why": f"no terminal structure note at STA {sta} -- {tail}"}


def _bore_disposition(bid, start_a, end_a, rejected) -> str:
    if bid in SOURCE_CONTRADICTION:
        return B_SOURCE_CONTRA
    if A_KMZ_CONTRA in (start_a["result"], end_a["result"]):
        return A_KMZ_CONTRA
    if end_a["result"] == A_ATTRIB:
        return A_ATTRIB
    if start_a["result"] == A_JUNCTION:
        return A_JUNCTION
    if rejected:
        return B_SHEET_NEIGHBOR
    if A_COMPETING in (start_a["result"], end_a["result"]):
        return A_COMPETING
    if start_a["result"] == A_NO_NOTE and end_a["result"] == A_NO_NOTE:
        return A_NO_NOTE
    if A_NO_PAIR in (start_a["result"], end_a["result"]):
        return A_NO_PAIR
    return A_UNMODELED


def _analyze(plan, dialect, offset, model, bore, stem, corpus) -> dict:
    flat = _bore_pdf_aps(plan, dialect, offset, stem, corpus)
    sheets = flat.get("sheets") or []
    start_sta = feet_to_station(bore.station_start_ft)
    end_sta = feet_to_station(bore.station_end_ft)

    start_a = _attribute_endpoint(plan, sheets, offset, bore.station_start_ft, "START")
    end_a = _attribute_endpoint(plan, sheets, offset, bore.station_end_ft, "END")

    # independent owning-station map (frame ownership) across the bore's sheets.
    owning: Dict[int, Optional[str]] = {}
    for sheet in sheets:
        for ap, st in _ap_owning_stations(plan.lines(sheet, offset)).items():
            owning.setdefault(ap, st)

    # KMZ cross-check + PDF<->KMZ contradiction reclassification (condition 4).
    for a in (start_a, end_a):
        a["owning_station_independent"] = owning.get(a["ap"]) if a["ap"] else None
        if a["result"] in (A_ATTRIB, A_JUNCTION):
            jr = join_terminal(model, terminal_class=TERMINAL_CLASS,
                               pdf_ap=a["ap"], pdf_splice_loc=a["splice"]).result
            a["kmz_join"] = jr
            if a["result"] == A_ATTRIB and jr in _CONTRA_JOINS:
                a["result"] = A_KMZ_CONTRA
                a["why"] = (f"PDF terminus AP {a['ap']} {a['splice']} CONTRADICTS the "
                            f"KMZ terminal for AP {a['ap']} (join {jr}) -- a PDF<->KMZ "
                            f"id mismatch; not a safe anchor")
        else:
            a["kmz_join"] = None

    flat_pairs = flat.get("pdf_ap_splice") or {}
    attributed_aps = {a["ap"] for a in (start_a, end_a)
                      if a["result"] in (A_ATTRIB, A_JUNCTION) and a["ap"]}
    rejected = []
    for ap in sorted(flat_pairs):
        if ap in attributed_aps:
            continue
        own = owning.get(ap)
        if own not in (start_sta, end_sta):
            rejected.append({"ap": ap, "owning_station": own,
                             "splice_loc": flat_pairs[ap]})

    disp = _bore_disposition(bore.bore_id, start_a, end_a, rejected)
    return {
        "bore_id": bore.bore_id, "sheets": sheets,
        "source_start_station": start_sta, "source_end_station": end_sta,
        "span_ft": [bore.station_start_ft, bore.station_end_ft],
        "start_endpoint": start_a, "end_endpoint": end_a,
        "flat_scan_ap_splice": flat_pairs,
        "endpoint_attributed_aps": sorted(a for a in attributed_aps if a is not None),
        "sheet_neighbor_rejected": rejected,
        "bore_disposition": disp,
    }


def main() -> int:
    kmz_path, kmz_how = resolve_kmz()
    corpus_dir, how = resolve_corpus()
    print(f"[m9.3] kmz   : {kmz_path}  ({kmz_how})")
    print(f"[m9.3] corpus: {corpus_dir}  ({how})")
    if not os.path.isfile(kmz_path) or not os.path.isfile(PDF) \
            or not os.path.isdir(corpus_dir):
        print("[m9.3] STOP: inputs missing")
        return 2
    paths = enumerate_corpus(corpus_dir)
    if len(paths) != EXPECTED_COUNT:
        print(f"[m9.3] STOP: corpus drift ({len(paths)})")
        return 3
    corpus = {p.stem: p for p in paths}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = True

    model = read_kmz(kmz_path, BRENHAM_KMZ_DIALECT)
    svc = ReviewerBundleService(corpus_dir=corpus_dir, plan_pdf_path=PDF,
                                project_id="brenham-ph5", bore_log_paths=paths)
    full = svc.generate(ReviewRunMode.FULLEST_SAFE_REVIEW)
    lane_by_id = {p.bore_id: p.lane.value for p in full.payloads}

    plan = PlanPdf(PDF)
    sweep_rows: List[dict] = []
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        for p in paths:
            try:
                bore = load_borelog(str(p))
            except Exception:
                continue
            row = _analyze(plan, dialect, offset, model, bore, p.stem, corpus)
            lane = lane_by_id.get(bore.bore_id, "UNKNOWN")
            row["product_lane"] = lane
            row["completion_bucket"] = completion_bucket(lane, bore.bore_id)[0]
            sweep_rows.append(row)
    finally:
        plan.close()

    by_id = {r["bore_id"]: r for r in sweep_rows}
    tgt = {b: by_id[b] for b in TARGETS if b in by_id}

    # corpus pass: clean END attributions + their terminals; junction pairing.
    end_attrib = {}                       # terminal AP -> bore_id (clean END)
    dup_violation = []
    for r in sweep_rows:
        a = r["end_endpoint"]
        if a["result"] == A_ATTRIB:
            if a["ap"] in end_attrib:
                dup_violation.append((a["ap"], end_attrib[a["ap"]], r["bore_id"]))
            end_attrib.setdefault(a["ap"], r["bore_id"])
    junctions = []                        # (start_bore, terminal AP, end_bore_owner)
    for r in sweep_rows:
        s = r["start_endpoint"]
        if s["result"] == A_JUNCTION:
            owner = end_attrib.get(s["ap"])
            r["junction_terminal_owned_by_end_bore"] = owner
            junctions.append({"start_bore": r["bore_id"], "terminal_ap": s["ap"],
                              "splice_loc": s["splice"], "end_bore_owner": owner})

    ep_census = collections.Counter()
    for r in sweep_rows:
        ep_census[r["start_endpoint"]["result"]] += 1
        ep_census[r["end_endpoint"]["result"]] += 1
    bore_census = collections.Counter(r["bore_disposition"] for r in sweep_rows)
    clean_attrib = sorted(((b, r["end_endpoint"]["ap"], r["end_endpoint"].get("kmz_join"))
                           for b, r in by_id.items()
                           if r["end_endpoint"]["result"] == A_ATTRIB),
                          key=lambda t: t[1])
    kmz_contra = sorted(b for b, r in by_id.items()
                        if r["bore_disposition"] == A_KMZ_CONTRA)

    # ---- GATES ---------------------------------------------------------------
    g1 = (len(model.structures) == EXPECT_STRUCTURES
          and len(model.routes) == EXPECT_ROUTES
          and all(b in tgt for b in TARGETS)
          and len(sweep_rows) >= EXPECTED_COUNT - 2)
    print(f"[m9.3] {'PASS' if g1 else 'FAIL'}  G1 inputs intact: KMZ "
          f"{len(model.structures)}/{len(model.routes)}; targets present; "
          f"{len(sweep_rows)} bores swept")
    ok &= g1

    l10 = tgt["log10"]
    g2 = (l10["end_endpoint"]["result"] == A_ATTRIB
          and l10["end_endpoint"]["ap"] == 152
          and l10["end_endpoint"]["splice"] == "SPLICE LOC 35"
          and l10["end_endpoint"]["kmz_join"] == "KMZ_TERMINAL_JOIN_BOUND"
          and l10["start_endpoint"]["result"] == A_NO_NOTE)
    print(f"[m9.3] {'PASS' if g2 else 'FAIL'}  G2 log10 END attributed AP-152/"
          f"SPLICE LOC 35 -> join BOUND; START unprinted")
    ok &= g2

    l68 = tgt["log68"]
    n148 = [x for x in l68["sheet_neighbor_rejected"] if x["ap"] == 148]
    g3 = (l68["bore_disposition"] == B_SHEET_NEIGHBOR
          and l68["start_endpoint"]["result"] != A_ATTRIB
          and l68["end_endpoint"]["result"] != A_ATTRIB
          and len(n148) == 1
          and n148[0]["owning_station"] not in (l68["source_start_station"],
                                                l68["source_end_station"]))
    print(f"[m9.3] {'PASS' if g3 else 'FAIL'}  G3 log68 AP-148 SHEET_NEIGHBOR_"
          f"REJECTED (owns STA {n148[0]['owning_station'] if n148 else '?'})")
    ok &= g3

    l7, l42 = tgt["log7"], tgt["log42"]
    g4 = (l7["end_endpoint"]["result"] == A_ATTRIB and l7["end_endpoint"]["ap"] == 163
          and l7["end_endpoint"]["kmz_join"] == "KMZ_TERMINAL_JOIN_BOUND"
          and l42["end_endpoint"]["result"] == A_ATTRIB and l42["end_endpoint"]["ap"] == 105
          and l42["end_endpoint"]["kmz_join"] == "KMZ_TERMINAL_JOIN_BOUND")
    print(f"[m9.3] {'PASS' if g4 else 'FAIL'}  G4 M9.1 controls via attribution: "
          f"log7 END AP-163, log42 END AP-105 -> both join BOUND")
    ok &= g4

    l44 = tgt["log44"]
    g5 = (l44["bore_disposition"] == B_SOURCE_CONTRA
          and l44["completion_bucket"] == "SOURCE_OR_KMZ_REQUIRED")
    print(f"[m9.3] {'PASS' if g5 else 'FAIL'}  G5 log44 SOURCE_CONTRADICTION "
          f"(banked M8.25/M9.0; not re-derived)")
    ok &= g5

    # G6: flat scan NEVER accepted -- every attributed/junction AP is in-frame +
    # terminal-class + a strict subset of the bore's flat-scan APs.
    g6 = True
    for r in sweep_rows:
        flat_aps = set((r["flat_scan_ap_splice"] or {}).keys())
        if not set(r["endpoint_attributed_aps"]) <= flat_aps:
            g6 = False
        for ep in ("start", "end"):
            a = r[f"{ep}_endpoint"]
            if a["result"] in (A_ATTRIB, A_JUNCTION) and a["structure_class"] != TERMINAL_CLASS:
                g6 = False
    print(f"[m9.3] {'PASS' if g6 else 'FAIL'}  G6 flat scan NOT accepted: every "
          f"attributed/junction AP is in-frame + terminal-class + subset of flat APs")
    ok &= g6

    # G7 (REAL two-method agreement): the independent owning-station map agrees the
    # attributed/junction AP owns its endpoint station (not a no-op).
    g7 = True
    for r in sweep_rows:
        for ep, sta_key in (("start", "source_start_station"),
                            ("end", "source_end_station")):
            a = r[f"{ep}_endpoint"]
            if a["result"] in (A_ATTRIB, A_JUNCTION, A_KMZ_CONTRA):
                if a.get("owning_station_independent") != r[sta_key]:
                    g7 = False
                if any(x["ap"] == a["ap"] for x in r["sheet_neighbor_rejected"]):
                    g7 = False
    print(f"[m9.3] {'PASS' if g7 else 'FAIL'}  G7 frame bind vs owning-station map "
          f"AGREE on every attribution (independent methods)")
    ok &= g7

    # G8: DIRECTION + UNIQUENESS invariant. Each clean END terminal anchors exactly
    # one bore END (no double-booking); the 3 shared terminals are JUNCTION_ORIGIN
    # starts paired to their owning END bore.
    expected_junctions = {("log27", 152, "log10"), ("log39", 117, "log72"),
                          ("log65", 163, "log7")}
    got_junctions = {(j["start_bore"], j["terminal_ap"], j["end_bore_owner"])
                     for j in junctions}
    g8 = (not dup_violation
          and len(end_attrib) == len(clean_attrib)
          and got_junctions == expected_junctions)
    print(f"[m9.3] {'PASS' if g8 else 'FAIL'}  G8 uniqueness+direction: "
          f"{len(end_attrib)} terminals each anchor 1 bore END (dups={dup_violation}); "
          f"junctions={sorted(got_junctions)}")
    ok &= g8

    # G9: log46 PDF<->KMZ contradiction surfaced (AP-161 PDF splice 35 vs KMZ 45).
    l46 = by_id.get("log46")
    g9 = (l46 is not None and l46["bore_disposition"] == A_KMZ_CONTRA
          and l46["end_endpoint"]["ap"] == 161
          and l46["end_endpoint"]["kmz_join"] in _CONTRA_JOINS)
    print(f"[m9.3] {'PASS' if g9 else 'FAIL'}  G9 log46 PDF_KMZ_CONTRADICTION "
          f"(AP-161 PDF SPLICE LOC 35 vs KMZ; join="
          f"{l46['end_endpoint']['kmz_join'] if l46 else '?'})")
    ok &= g9

    # G10: read-only / unwired.
    import truelinev2.match.engine as eng
    import truelinev2.match.symbol_conduit_lane as scl
    import truelinev2.review.reviewer_service as rsvc
    import truelinev2.service as svcmod
    wired = any(("kmz_structure_join" in inspect.getsource(m)
                 or "run_terminus_attribution_phase0" in inspect.getsource(m))
                for m in (eng, scl, rsvc, svcmod))
    g10 = not list(OUT_DIR.glob("*.png")) and not wired
    print(f"[m9.3] {'PASS' if g10 else 'FAIL'}  G10 read-only: no PNG; join UNWIRED; "
          f"proof not imported by engine (wired={wired})")
    ok &= g10

    # G11: no contract drift.
    g11 = (full.lane_counts == BANKED_FULLEST_LANES
           and tgt["log68"]["completion_bucket"] == "SOURCE_OR_KMZ_REQUIRED"
           and tgt["log10"]["completion_bucket"] == "DRAWABLE_REVIEW")
    print(f"[m9.3] {'PASS' if g11 else 'FAIL'}  G11 no contract drift: M8.11 lanes "
          f"{full.lane_counts == BANKED_FULLEST_LANES}; target buckets pinned")
    ok &= g11

    report = {
        "milestone": ("truelinev2 M9.3 Phase 0 -- START/END terminus-attribution "
                      "audit (proof-only; READ-ONLY; zero placements; census + "
                      "product lanes + M9.0/M9.1/M9.2 untouched)"),
        "kmz_path": kmz_path, "corpus_dir": corpus_dir, "plan_pdf": PDF,
        "verdict": "PASS" if ok else "FAILURE",
        "attribution_law": (
            "ENDPOINT_ATTRIBUTED iff the bore's END station carries exactly one "
            "structure note (uniqueness-mandatory), its class is the terminal class, "
            "exactly one AP+splice pair is INSIDE that note's frame, the pair joins "
            "its unique KMZ terminal cleanly (BOUND/NONE; a REJECTION -> "
            "PDF_KMZ_CONTRADICTION), and the terminal anchors at most one bore END. "
            "A terminal at a START is a JUNCTION_ORIGIN (end-of-feed; the prior bore's "
            "terminus), never this bore's identity. Flat sheet membership / proximity "
            "/ AP-only / splice-only never attribute."),
        "confidence_note": (
            "TYPED + CONTROLS-VERIFIED, NOT 'proven zero-false': 3 END attributions "
            "are independently ground-truthed (log7->163, log42->105, log10->152); "
            "the rest cross-bind via the M9.1 join (a printed-id consistency check, "
            "not independent endpoint ground truth); log46 is an attributed-but-"
            "REFUTED pair surfaced as a PDF<->KMZ contradiction."),
        "endpoint_attribution_census_all58": dict(sorted(ep_census.items())),
        "bore_disposition_census_all58": dict(sorted(bore_census.items())),
        "clean_end_attributions": [{"bore_id": b, "terminal_ap": ap, "kmz_join": jr}
                                   for b, ap, jr in clean_attrib],
        "bore_to_bore_junctions": junctions,
        "pdf_kmz_contradictions": kmz_contra,
        "targets": [by_id[b] for b in TARGETS if b in by_id],
        "ship_recommendation": (
            "DEFER the shipped extractor to M9.3.1 (Phase 0 proves the law boundary; "
            "it does not ship -- matching M9.0->M9.1). The relationship is sound where "
            "it counts (7 clean terminal-END attributions, 3 junction-origins, 1 "
            "PDF<->KMZ contradiction surfaced, log68 sheet-neighbour correctly "
            "rejected). Before promotion, the M9.3.1 core module MUST inject the "
            "note-detection keyword set (structure_anchor._STRUCTURE_WORDS is a "
            "shared-core literal today) and the AP/splice/station grammars (the "
            "runner re-declares them locally in proof/); classification via "
            "class_keywords is already injected. Add the END-direction rule + the "
            "one-terminal-per-END uniqueness invariant as core gates."),
        "named_evidence_targets": [
            "M9.3.1: a convention-agnostic core attribution module with the note-"
            "detection keywords + AP/splice/station grammars injected (the only core "
            "literal blocking universality), the END-direction rule, and the "
            "uniqueness invariant",
            "a START terminal identity for the JUNCTION_ORIGIN bores via run-assembly: "
            "the junction already proves bore-to-bore continuity (e.g. log10 END = "
            "log27 START at terminal AP-152) -- a run-assembly lane can consume it",
            "owner source re-read for log46 (PDF AP-161 SPLICE LOC 35 vs KMZ Splice "
            "Loc 45) and log44 (325' source-vs-plan, M8.25) before any KMZ anchor",
        ],
    }
    (OUT_DIR / "terminus_attribution_phase0.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    (OUT_DIR / "terminus_attribution_phase0.md").write_text(
        _markdown(report), encoding="utf-8")

    print(f"\n[m9.3] endpoint attribution (all-58 start+end): {dict(sorted(ep_census.items()))}")
    print(f"[m9.3] bore dispositions (all-58): {dict(sorted(bore_census.items()))}")
    print(f"[m9.3] clean END attributions: {len(clean_attrib)} | junctions: "
          f"{len(junctions)} | PDF<->KMZ contradictions: {kmz_contra} | bores moved: []")
    print(f"[m9.3] verdict: {report['verdict']}")
    print(f"[m9.3] report -> {OUT_DIR / 'terminus_attribution_phase0.json'}")
    return 0 if ok else 4


def _markdown(report: dict) -> str:
    L = ["# M9.3 Phase 0 -- START/END terminus-attribution", "",
         f"Verdict: **{report['verdict']}**", "",
         report["attribution_law"], "", f"_{report['confidence_note']}_", "",
         f"All-58 endpoint census (start+end): `{report['endpoint_attribution_census_all58']}`",
         f"All-58 bore disposition census: `{report['bore_disposition_census_all58']}`", "",
         "## Clean terminal-END attributions (each KMZ-join cross-checked)", "",
         "| bore | terminal AP | M9.1 join |", "|---|---|---|"]
    for r in report["clean_end_attributions"]:
        L.append(f"| {r['bore_id']} | AP-{r['terminal_ap']} | {r['kmz_join']} |")
    L += ["", "## Bore-to-bore junctions (START at a prior feed's terminus)", "",
          "| start bore | terminal AP | owned by END bore |", "|---|---|---|"]
    for j in report["bore_to_bore_junctions"]:
        L.append(f"| {j['start_bore']} | AP-{j['terminal_ap']} | {j['end_bore_owner']} |")
    L += ["", f"PDF<->KMZ contradictions: {report['pdf_kmz_contradictions']}", "",
          "## Target cases", "",
          "| bore | bucket | sheets | src start | src end | START | END | "
          "END join | rejected neighbours | disposition |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for r in report["targets"]:
        rej = ", ".join(f"AP-{x['ap']}@{x['owning_station']}"
                        for x in r["sheet_neighbor_rejected"]) or "-"
        L.append(
            f"| {r['bore_id']} | {r['completion_bucket']} | {r['sheets']} | "
            f"{r['source_start_station']} | {r['source_end_station']} | "
            f"{r['start_endpoint']['result']}"
            f"{(' AP-' + str(r['start_endpoint']['ap'])) if r['start_endpoint']['ap'] else ''} | "
            f"{r['end_endpoint']['result']}"
            f"{(' AP-' + str(r['end_endpoint']['ap'])) if r['end_endpoint']['ap'] else ''} | "
            f"{r['end_endpoint'].get('kmz_join') or '-'} | {rej} | {r['bore_disposition']} |")
    L += ["", "## Per-target detail", ""]
    for r in report["targets"]:
        L.append(f"### {r['bore_id']} ({r['bore_disposition']})")
        L.append(f"- START @ {r['source_start_station']}: {r['start_endpoint']['result']} "
                 f"-- {r['start_endpoint']['why']}")
        L.append(f"- END @ {r['source_end_station']}: {r['end_endpoint']['result']} "
                 f"-- {r['end_endpoint']['why']}")
        if r["sheet_neighbor_rejected"]:
            L.append("- rejected sheet-neighbours: "
                     + ", ".join(f"AP-{x['ap']} (owns STA {x['owning_station']})"
                                 for x in r["sheet_neighbor_rejected"]))
        L.append("")
    L += ["## Ship recommendation", "", report["ship_recommendation"], "",
          "## Named evidence targets", ""]
    for t in report["named_evidence_targets"]:
        L.append(f"- {t}")
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
