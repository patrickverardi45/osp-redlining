r"""M9.2 Phase 0 -- KMZ_MATCHLINE_SUBSTITUTE feasibility audit (proof-only; READ-ONLY).

Decides whether the no-equation cross-sheet class can SAFELY use the KMZ as a
matchline substitute by requiring TWO independently bound terminal anchors via
the SHIPPED M9.1 KMZ_AP_STRUCTURE_JOIN -- one at the bore's START endpoint and a
DISTINCT one at its END endpoint -- plus admissible KMZ route continuity between
them, with no PDF/source contradiction. Phase 0 PROVES the law boundary; it does
NOT ship an extractor and moves NO bore.

LAW BOUNDARY (all must hold for a KMZ matchline substitute):
  1. both endpoints independently bind via the two-field AP+splice-loc join;
  2. each join is unique and class-scoped (terminal_class only);
  3. KMZ route evidence supports continuity between the two anchors;
  4. PDF has no contradiction;
  5. source row/log context is compatible;
  6. no equal competing endpoint/route survives.
FORBIDDEN as evidence (asserted, not used): proximity alone, AP-only, splice-only,
Vacant-Pipe count alone, route geometry to INFER a missing endpoint identity, KMZ
overriding a PDF/source contradiction, customer literals in shared match/ core.

WHAT THIS PHASE-0 ACTUALLY TESTS (so the verdict is not overstated):
  * The disposition is decided by the FIRST unmet condition. For this class that
    is CONDITION 1 (two-endpoint terminal binding) for every bore -- so the
    negative rests on condition 1 alone and conditions 3/4/6 are not independently
    exercised per bore. Specifically:
      - condition 2 (uniqueness, class-scoped) is enforced inside the M9.1 join
        itself: a non-unique terminus returns JOIN_AMBIGUOUS (not a bind), and
        only terminal_class structures are candidates;
      - condition 3 (route continuity) is measured ONCE, globally, as a source
        fact (G5): the KMZ has zero non-geometric route<->structure linkage;
      - condition 4 (no PDF/source contradiction) is a BANKED input from
        M8.16/M8.25 (this class has none -- the missing matchline equation is the
        GAP, not a contradiction); it is not recomputed here;
      - condition 6 (no equal competitor) is enforced at the ENDPOINT level by the
        join's JOIN_AMBIGUOUS refusal; the route-competition half is moot because
        no admissible route binding exists.

WHY THE BINDING FAILS (measured, per bore -- not assumed):
  The M9.1 join binds ONLY terminal_class (terminal_port_hh) by a PRINTED AP+splice
  pair ATTRIBUTED to a bore endpoint. An endpoint's AP+splice is read from the
  PROVEN end-structure note grammar (extract.structure_anchor.bind_end_structure_note)
  at the bore's start_ft and end_ft -- NOT from a flat sheet scan (which over-
  collects neighbouring bores' terminals and tags nothing start/end). For this
  class the endpoints, where printed, are NON-TERMINAL drop structures (FLOWER POT
  / INSTALLER HH) that carry NO AP+splice id (pair_kind NO_ID), or no structure
  note prints at the station at all -- so the two-field terminal join has no key.
  This is unsatisfiable FROM THE CURRENT PRINTED GRAMMAR, a named unmodeled
  relationship (see named_evidence_targets) -- NOT a permanent impossibility.

ROUTE CONTINUITY (condition 3, structural). KMZ routes carry NO id/length/endpoint
  text -- a route is reachable only via its endpoint coordinates (extract.kmz
  docstring; M9.0 audit). So "a route connects anchor A and anchor B" can be
  asserted ONLY by coordinate proximity, which the law forbids. Requirement 3 is
  therefore structurally unmet from this KMZ; G5 asserts the source has zero
  non-geometric route<->structure linkage. This is a STANDING blocker (it would
  bind a future bore that first cleared condition 1); it is never the operative
  per-bore blocker here because no bore clears condition 1.

PROOF-ONLY: no placement change, no engine wiring, no stroke/PNG/segment, no
AUTO, no tolerance/budget change. Consults the SHIPPED M9.0 reader + M9.1 join +
M8.10/M8.11 reviewer contract + the M8.14.c symbol_conduit lane WITHOUT altering
any. The M9.1 join is UNWIRED and stays so (this runner imports + calls it from
proof/ only). All-58 census + product lanes + M9.0 dispositions frozen.

CANDIDATE VERIFICATION (do NOT trust the wiki prose): the M9.0 next_law NAMES the
class "log68 + log10/14/61/62/67/68/70" (7), but the M8.16/M8.17 probe's GATED
predicate ("prints no equation at this boundary") matches only SIX --
log14/61/62/67/68/70 -- and classifies log10 as a DIFFERENT sub-class ("printed-
identity matchline path, no shared boundary callouts"). This runner re-derives the
class LIVE (G2) and treats log10 as NOT_IN_CLASS for the strict matchline-sub law.

Exit codes (house convention): 0 PASS, 2 inputs missing, 3 corpus drift, 4 gate
FAILURE.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_kmz_matchline_substitute_phase0
"""
from __future__ import annotations

import collections
import inspect
import json
import os
import re
from typing import List, Optional, Tuple

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.kmz import BRENHAM_KMZ_DIALECT, read_kmz
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_anchor import BOUND as ID_BOUND
from truelinev2.extract.structure_anchor import bind_end_structure_note
from truelinev2.extract.structure_position import BRENHAM_LANE_DIALECT
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.kmz_structure_join import join_terminal
from truelinev2.match.symbol_conduit_lane import S_CROSS_SHEET, resolve_bore as stroke_resolve
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_final_engine_truth_table import completion_bucket
from truelinev2.proof.run_kmz_correlation_audit import _bore_pdf_aps, resolve_kmz
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.review.reviewer_service import ReviewerBundleService, ReviewRunMode
from truelinev2.match.frames import _build_plan_frame_graph

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "kmz_matchline_substitute_phase0"

# Banked KMZ taxonomy (must match M9.0; drift fails loud).
EXPECT_STRUCTURES = 576
EXPECT_ROUTES = 539
# Banked M8.11 fullest_safe_review product lanes (must match M8.27; no drift).
BANKED_FULLEST_LANES = {
    "PLACED_REVIEW": 31, "PICK_CARD_ROUTE_SUGGESTION": 16,   # RECON-2A: +log37
    "HUMAN_ADJUSTABLE_LENGTH_REDLINE": 6, "OUT_OF_CLASS": 5,  # +log38; SOURCE_REVIEW 2->0
}

# The NAMED scope (M9.0 next_law / m9_0+m9_1 wiki). Verified against repo truth.
NAMED_SCOPE = ("log10", "log14", "log61", "log62", "log67", "log68", "log70")
# The STRICT mechanical class (the M8.16 probe's gated "prints no equation at this
# boundary" needle). Re-derived LIVE in G2; this is the banked expectation.
STRICT_NO_EQUATION = {"log14", "log61", "log62", "log67", "log68", "log70"}
NO_EQ_NEEDLE = "prints no equation at this boundary"
LOG10_NEEDLE = "sharing one boundary"     # log10's distinct printed-identity needle

# M9.1 controls (the shipped two-field binds; PROVE the join is unchanged).
CONTROLS = {"log7": (163, "SPLICE LOC 46"), "log42": (105, "SPLICE LOC 25")}

# Per-bore PDF/source contradiction (BANKED input from M8.16/M8.25 -- NOT recomputed
# here). For the no-equation class the missing matchline equation is the GAP, not a
# contradiction, so condition 4 holds for all; only ever consulted on the (unreached)
# both-endpoints-bound branch.
PDF_CONTRADICTION = {b: False for b in NAMED_SCOPE}

# Phase-0 dispositions (the allowed taxonomy).
D_TWO_BOUND = "TWO_ENDPOINTS_BOUND"
D_ONE_ONLY = "ONE_ENDPOINT_ONLY"
D_PAIR_MISSING = "ENDPOINT_PAIR_MISSING"
D_NO_ROUTE = "NO_KMZ_ROUTE_SUPPORT"
D_PDF_CONTRA = "PDF_CONTRADICTION"
D_SOURCE_ONLY = "SOURCE_REVIEW_ONLY"
D_NOT_IN_CLASS = "NOT_IN_CLASS"

ROUTE_CLASS = BRENHAM_KMZ_DIALECT.route_folders["Vacant Pipe"]   # "bore_vacant_pipe"
_AP_RE = re.compile(r"AP\s*-?\s*(\d+)", re.I)
_SPLICE_RE = re.compile(r"SPLICE\s*LOC\s*(\d+)", re.I)


def _pair_from_label(label: Optional[str]) -> Tuple[Optional[int], Optional[str], str]:
    """Endpoint-attributed (ap, splice_token, kind) from a BOUND end-structure
    note's windowed label. A clean endpoint pair requires EXACTLY ONE AP and
    EXACTLY ONE splice-loc in the note (uniqueness within the endpoint -- no
    first-match guessing across a multi-callout block)."""
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


def _bind_endpoint(plan, sheets, offset, station_ft) -> dict:
    """The bore's printed terminus identity at one endpoint, via the PROVEN
    end-structure note grammar (structure_anchor). Scans the bore's own sheets;
    returns the first BOUND note + any clean AP+splice pair it carries."""
    for sheet in sheets:
        b = bind_end_structure_note(station_ft, plan.lines(sheet, offset))
        if b.result == ID_BOUND:
            ap, sp, kind = _pair_from_label(b.structure_label)
            return {"identity_bound": True, "sheet": sheet,
                    "note_line": b.note_line, "label": b.structure_label,
                    "ap": ap, "splice": sp, "pair_kind": kind}
    return {"identity_bound": False, "sheet": None, "note_line": None,
            "label": None, "ap": None, "splice": None,
            "pair_kind": "NO_STRUCTURE_NOTE"}


def _ep_phrase(ep: dict, which: str) -> str:
    """An accurate, PER-BORE description of why an endpoint did not yield a
    bindable terminal AP+splice pair (built from the actual evidence -- never a
    blanket assumption)."""
    if not ep["identity_bound"]:
        return (f"{which} identity is unprinted (no 'STA <sta> <structure>' note "
                f"at the station)")
    short = " ".join((ep["label"] or "").split())[:46]
    pk = ep["pair_kind"]
    if pk == "FULL_PAIR":
        return f"{which} carries a full AP+splice pair ({short})"
    if pk == "NO_ID":
        return (f"{which} binds a PRINTED structure note ('{short}') that carries "
                f"NO AP+splice id -- a non-terminal drop structure, not terminal_class")
    if pk == "AP_ONLY":
        return f"{which} note ('{short}') has an AP but no splice-loc (AP-only refused)"
    if pk == "SPLICE_ONLY":
        return f"{which} note ('{short}') has a splice-loc but no AP (splice-only refused)"
    if pk == "MULTI_AMBIGUOUS":
        return f"{which} note ('{short}') carries multiple AP/splice tokens (ambiguous)"
    return f"{which}: {pk}"


def _disposition(in_strict_class: bool, source_parseable: bool,
                 start_ep: dict, end_ep: dict, start_join, end_join,
                 route_admissible: bool, contradiction: bool) -> Tuple[str, str]:
    """Decided by the FIRST unmet condition. The reason is built from the actual
    per-bore endpoint evidence -- not a hardcoded narrative."""
    if not source_parseable:
        return D_SOURCE_ONLY, "source unparseable -> no sheets/AP refs -> no join key"
    if not in_strict_class:
        return (D_NOT_IN_CLASS,
                "in the M9.0 NAMED scope but NOT the strict no-equation predicate "
                "(printed-identity matchline path; evaluate under a different lane)")
    sb, eb = start_join.bound, end_join.bound
    distinct = bool(sb and eb and start_join.anchor and end_join.anchor
                    and start_join.anchor.name != end_join.anchor.name)
    if sb and eb and distinct:
        if contradiction:                                       # condition 4
            return D_PDF_CONTRA, "both endpoints bound but a PDF/source contradiction blocks it"
        if route_admissible:                                    # condition 3
            return D_TWO_BOUND, "both endpoints independently bound + admissible KMZ route continuity"
        return (D_NO_ROUTE,
                "both endpoints bound, but the KMZ provides NO admissible route-"
                "continuity evidence (route<->structure linkage is geometric-only; "
                "proximity forbidden by law)")
    if sb or eb:
        which = "START" if sb else "END"
        other = _ep_phrase(end_ep if sb else start_ep, "the other endpoint")
        return (D_ONE_ONLY,
                f"only the {which} endpoint binds a unique terminal via AP+splice; "
                f"{other} -> cannot bridge the matchline (single-anchor at most)")
    return (D_PAIR_MISSING,
            f"no endpoint-attributed AP+splice terminal pair: {_ep_phrase(start_ep, 'START')}; "
            f"{_ep_phrase(end_ep, 'END')} -- the M9.1 two-field terminal_class join has "
            f"no key from the current printed grammar")


def main() -> int:
    kmz_path, kmz_how = resolve_kmz()
    corpus_dir, how = resolve_corpus()
    print(f"[m9.2] kmz   : {kmz_path}  ({kmz_how})")
    print(f"[m9.2] corpus: {corpus_dir}  ({how})")
    if not os.path.isfile(kmz_path) or not os.path.isfile(PDF) \
            or not os.path.isdir(corpus_dir):
        print("[m9.2] STOP: inputs missing")
        return 2
    paths = enumerate_corpus(corpus_dir)
    corpus = {p.stem: p for p in paths}
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m9.2] STOP: corpus drift ({len(corpus)})")
        return 3
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = True

    model = read_kmz(kmz_path, BRENHAM_KMZ_DIALECT)
    tc = BRENHAM_KMZ_DIALECT.terminal_class

    # --- PRODUCT axis (M8.11 fullest_safe_review) -- for buckets + no-drift gate.
    svc = ReviewerBundleService(corpus_dir=corpus_dir, plan_pdf_path=PDF,
                                project_id="brenham-ph5", bore_log_paths=paths)
    full = svc.generate(ReviewRunMode.FULLEST_SAFE_REVIEW)
    lane_by_id = {p.bore_id: p.lane.value for p in full.payloads}

    # --- KMZ route linkage probe (condition 3): are bore routes id-linked? -------
    bore_routes = [r for r in model.routes if r.kmz_class == ROUTE_CLASS]
    routes_with_ap_field = sum(
        1 for r in bore_routes
        if any(_AP_RE.search(v or "") for v in r.fields.values()))
    routes_with_any_field = sum(1 for r in bore_routes if r.fields)
    route_linkage_admissible = routes_with_ap_field > 0   # non-geometric id link?

    plan = PlanPdf(PDF)
    rows: List[dict] = []
    control_rows: List[dict] = []
    strict_live: set = set()
    log10_needle_ok = False
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        graph = _build_plan_frame_graph(plan, offset)

        # M9.1 controls: prove the shipped join is unchanged through this harness.
        for bid, (ap, sp) in CONTROLS.items():
            r = join_terminal(model, terminal_class=tc, pdf_ap=ap,
                              pdf_splice_loc=sp)
            control_rows.append({
                "bore_id": bid, "pdf_ap": ap, "pdf_splice_loc": sp,
                "result": r.result, "bound": r.bound,
                "anchor": r.anchor.to_dict() if r.anchor else None})

        for bid in NAMED_SCOPE:
            stem = f"bore_{bid}"
            bore = load_borelog(str(corpus[stem]))
            stroke = stroke_resolve(plan, bore, offset, BRENHAM_LANE_DIALECT,
                                    frame_graph=graph)
            nm = stroke.named_missing or ""
            if NO_EQ_NEEDLE in nm:
                strict_live.add(bid)
            if bid == "log10":
                log10_needle_ok = (NO_EQ_NEEDLE not in nm and LOG10_NEEDLE in nm)

            flat = _bore_pdf_aps(plan, dialect, offset, stem, corpus)
            sheets = flat.get("sheets") or []
            in_strict = bid in STRICT_NO_EQUATION

            # endpoint-attributed termini (the M9.1 inputs), start + end.
            start_ep = _bind_endpoint(plan, sheets, offset, bore.station_start_ft)
            end_ep = _bind_endpoint(plan, sheets, offset, bore.station_end_ft)
            start_join = join_terminal(model, terminal_class=tc,
                                       pdf_ap=start_ep["ap"],
                                       pdf_splice_loc=start_ep["splice"])
            end_join = join_terminal(model, terminal_class=tc,
                                     pdf_ap=end_ep["ap"],
                                     pdf_splice_loc=end_ep["splice"])
            start_full = start_ep["pair_kind"] == "FULL_PAIR"
            end_full = end_ep["pair_kind"] == "FULL_PAIR"
            distinct = bool(start_join.bound and end_join.bound
                            and start_join.anchor and end_join.anchor
                            and start_join.anchor.name != end_join.anchor.name)
            both_unique = bool(start_join.bound and end_join.bound and distinct)
            one_only = bool(start_join.bound) ^ bool(end_join.bound)

            # supplementary: sheet-level flat scan joins (OVER-COLLECTS neighbours;
            # never used for the disposition -- shown to expose the attribution gap).
            flat_joins = []
            for ap, sp in (flat.get("pdf_ap_splice") or {}).items():
                jr = join_terminal(model, terminal_class=tc, pdf_ap=ap,
                                   pdf_splice_loc=f"SPLICE LOC {sp}")
                flat_joins.append({"pdf_ap": ap, "pdf_splice_loc": sp,
                                   "result": jr.result,
                                   "kmz_terminal": jr.anchor.name if jr.anchor else None})
            sheet_bound = sorted({j["kmz_terminal"] for j in flat_joins
                                  if j["kmz_terminal"]})

            disp, why = _disposition(
                in_strict, flat.get("source_parseable", True),
                start_ep, end_ep, start_join, end_join,
                route_linkage_admissible, PDF_CONTRADICTION.get(bid, False))

            lane = lane_by_id.get(bid, "UNKNOWN")
            bucket, oc = completion_bucket(lane, bid)
            rows.append({
                "bore_id": bid,
                "in_named_scope": True,
                "in_strict_no_equation_class": in_strict,
                "product_lane": lane,
                "completion_bucket": bucket,
                "completion_bucket_reason": oc,
                "stroke_status": stroke.status,
                "sheets": sheets,
                "span": flat.get("span"),
                "start_endpoint_evidence": {
                    "identity_bound": start_ep["identity_bound"],
                    "sheet": start_ep["sheet"], "note_line": start_ep["note_line"],
                    "structure_label": start_ep["label"],
                    "pair_kind": start_ep["pair_kind"]},
                "end_endpoint_evidence": {
                    "identity_bound": end_ep["identity_bound"],
                    "sheet": end_ep["sheet"], "note_line": end_ep["note_line"],
                    "structure_label": end_ep["label"],
                    "pair_kind": end_ep["pair_kind"]},
                "start_pdf_ap": start_ep["ap"],
                "start_pdf_splice_loc": start_ep["splice"],
                "end_pdf_ap": end_ep["ap"],
                "end_pdf_splice_loc": end_ep["splice"],
                "start_has_full_ap_splice_pair": start_full,
                "end_has_full_ap_splice_pair": end_full,
                "m91_join_start": start_join.result,
                "m91_join_end": end_join.result,
                "both_endpoints_bind_uniquely": both_unique,
                # one endpoint binds, the other does not -> a future SINGLE-ANCHOR
                # (KMZ_ENDPOINT_BRIDGE-style) candidate, NOT a matchline substitute.
                "future_single_anchor_candidate": one_only,
                "kmz_route_support": ("ADMISSIBLE" if route_linkage_admissible
                                      else "NO_ADMISSIBLE_LINKAGE (route<->structure "
                                      "is geometric-only; proximity forbidden)"),
                "pdf_contradiction": PDF_CONTRADICTION.get(bid, False),
                "phase0_disposition": disp,
                "blocker": why,
                # supplementary, NOT used for the disposition:
                "sheet_level_flat_ap_splice": flat.get("pdf_ap_splice"),
                "sheet_level_bound_terminals_NOT_endpoint_attributed": sheet_bound,
            })
    finally:
        plan.close()

    by_id = {r["bore_id"]: r for r in rows}
    disp_census = collections.Counter(r["phase0_disposition"] for r in rows)
    single_anchor = sorted(r["bore_id"] for r in rows
                           if r["future_single_anchor_candidate"])

    # ---- GATES ---------------------------------------------------------------
    g1 = (len(model.structures) == EXPECT_STRUCTURES
          and len(model.routes) == EXPECT_ROUTES
          and model.unclassified_placemarks == 0
          and len(rows) == len(NAMED_SCOPE)
          and all(r["phase0_disposition"] for r in rows))
    print(f"[m9.2] {'PASS' if g1 else 'FAIL'}  G1 inputs intact: KMZ "
          f"{len(model.structures)}/{len(model.routes)}; {len(rows)}/7 candidates "
          f"typed")
    ok &= g1

    g2 = (strict_live == STRICT_NO_EQUATION and log10_needle_ok
          and set(NAMED_SCOPE) == set(STRICT_NO_EQUATION) | {"log10"})
    print(f"[m9.2] {'PASS' if g2 else 'FAIL'}  G2 candidate list verified LIVE: "
          f"strict no-equation class={sorted(strict_live)}; log10 is a SUPERSET "
          f"member (distinct needle={log10_needle_ok})")
    ok &= g2

    g3 = all(c["bound"] and c["anchor"] and c["anchor"]["ap_id"] == CONTROLS[c["bore_id"]][0]
             for c in control_rows)
    print(f"[m9.2] {'PASS' if g3 else 'FAIL'}  G3 M9.1 controls UNCHANGED: "
          f"{ {c['bore_id']: c['result'] for c in control_rows} }")
    ok &= g3

    strict_rows = [r for r in rows if r["in_strict_no_equation_class"]]
    two_bound = [r["bore_id"] for r in strict_rows
                 if r["phase0_disposition"] == D_TWO_BOUND]
    g4 = (len(strict_rows) == 6 and not two_bound)
    print(f"[m9.2] {'PASS' if g4 else 'FAIL'}  G4 HONEST NEGATIVE: 0/6 strict-class "
          f"bores reach TWO_ENDPOINTS_BOUND; dispositions="
          f"{dict(sorted(collections.Counter(r['phase0_disposition'] for r in strict_rows).items()))}")
    ok &= g4

    g5 = (len(bore_routes) == 58 and not route_linkage_admissible
          and routes_with_ap_field == 0)
    print(f"[m9.2] {'PASS' if g5 else 'FAIL'}  G5 condition(3) structurally UNMET "
          f"(standing blocker): {len(bore_routes)} bore routes, {routes_with_ap_field} "
          f"carry a non-geometric AP/id link -> route continuity is geometric-only")
    ok &= g5

    # G6: read-only / unwired. The M9.1 join + M9.0 reader stay UNWIRED from every
    # placement path; this runner rendered nothing and moved no bore.
    import truelinev2.match.engine as eng
    import truelinev2.match.symbol_conduit_lane as scl
    import truelinev2.review.reviewer_service as rsvc
    import truelinev2.service as svcmod
    wired = any(("kmz_structure_join" in inspect.getsource(m)
                 or "extract.kmz" in inspect.getsource(m))
                for m in (eng, scl, rsvc, svcmod))
    g6 = (not list(OUT_DIR.glob("*.png")) and not wired
          and all(r["stroke_status"] == S_CROSS_SHEET for r in rows))
    print(f"[m9.2] {'PASS' if g6 else 'FAIL'}  G6 read-only: no PNG; join+reader "
          f"UNWIRED (wired={wired}); all 7 stroke_status==CROSS_SHEET (zero moved)")
    ok &= g6

    # G7: no contract drift. Product lanes reconcile with M8.11 fullest_safe_review;
    # the 7 keep their M8.27 completion buckets.
    g7 = (full.lane_counts == BANKED_FULLEST_LANES
          and by_id["log68"]["completion_bucket"] == "SOURCE_OR_KMZ_REQUIRED"
          and by_id["log10"]["completion_bucket"] == "DRAWABLE_REVIEW")
    print(f"[m9.2] {'PASS' if g7 else 'FAIL'}  G7 no contract drift: M8.11 lanes "
          f"{full.lane_counts == BANKED_FULLEST_LANES}; buckets pinned")
    ok &= g7

    report = {
        "milestone": ("truelinev2 M9.2 Phase 0 -- KMZ_MATCHLINE_SUBSTITUTE "
                      "feasibility audit (proof-only; READ-ONLY; zero placements; "
                      "M8.27 census + product lanes + M9.0 dispositions untouched)"),
        "kmz_path": kmz_path, "kmz_resolution": kmz_how,
        "corpus_dir": corpus_dir, "plan_pdf": PDF,
        "verdict": "PASS" if ok else "FAILURE",
        "law_boundary": [
            "1 both endpoints independently bind via two-field AP+splice-loc join",
            "2 each join unique + class-scoped (terminal_class only)",
            "3 KMZ route evidence supports continuity between the two anchors",
            "4 no PDF/source contradiction",
            "5 source row/log context compatible",
            "6 no equal competing endpoint/route survives",
        ],
        "what_phase0_tests": (
            "The disposition is decided by the FIRST unmet condition; for this class "
            "that is CONDITION 1 (two-endpoint terminal binding) for all 6 bores, so "
            "conditions 3/4/6 are not independently exercised per bore. Condition 2 "
            "(uniqueness) is enforced inside the M9.1 join (JOIN_AMBIGUOUS != bind); "
            "condition 3 is measured once globally (G5); condition 4 is a BANKED "
            "input (M8.16/M8.25: this class has none); condition 6's endpoint half is "
            "the join's uniqueness refusal, its route half is moot (no route binding)."),
        "candidate_list_verification": {
            "named_scope": list(NAMED_SCOPE),
            "strict_no_equation_class_live": sorted(strict_live),
            "log10_status": "NOT_IN_CLASS (printed-identity matchline path; the "
                            "named scope is a 1-bore superset of the strict class)",
            "verdict": ("named scope reproduced EXACTLY; strict mechanical class is "
                        "6 bores; log10 is the superset edge"),
        },
        "controls": control_rows,
        "kmz_route_linkage": {
            "bore_route_class": ROUTE_CLASS,
            "bore_routes": len(bore_routes),
            "routes_with_non_geometric_ap_id_field": routes_with_ap_field,
            "routes_with_any_field": routes_with_any_field,
            "admissible": route_linkage_admissible,
            "note": ("KMZ routes carry no id/length/endpoint text; the only "
                     "route<->structure tie is endpoint COORDINATE proximity, which "
                     "the law forbids -> condition 3 is unmet from this source. This "
                     "is a STANDING blocker (binds only a future bore that first "
                     "clears condition 1), never the operative per-bore blocker here."),
        },
        "disposition_census": dict(sorted(disp_census.items())),
        "future_single_anchor_candidates": single_anchor,
        "phase0_outcome": ("HONEST NEGATIVE: the no-equation cross-sheet class "
                           "cannot safely use the KMZ as a matchline substitute "
                           "FROM THE CURRENT PRINTED EVIDENCE. The OPERATIVE blocker "
                           "for all 6 strict-class bores is condition 1: no bore "
                           "binds a terminal at BOTH endpoints (the endpoints, where "
                           "printed, are non-terminal drop structures -- flower pot / "
                           "installer HH -- carrying no AP+splice id; the M9.1 join "
                           "binds only terminal_class). A SECOND, STANDING blocker "
                           "(condition 3) is that the KMZ has no admissible non-"
                           "geometric route<->structure linkage -- it would bind a "
                           "future bore that first cleared condition 1. Both are "
                           "named unmodeled relationships, NOT permanent "
                           "impossibilities. NO extractor shipped; zero bores moved. "
                           "(log10, outside the strict class, is the one candidate "
                           "whose END binds a unique terminal -> a future SINGLE-"
                           "ANCHOR / endpoint-bridge candidate, not a substitute.)"),
        "named_evidence_targets": [
            "a START/END terminus ATTRIBUTION model: associate a printed "
            "'AP-NNN SPLICE LOC MM' callout line with a specific bore's start_ft vs "
            "end_ft (today only the structure LABEL is start/end-aware, never the "
            "AP/splice id; the flat sheet scan over-collects neighbouring bores' "
            "terminals -- e.g. log68's sheet-19 AP-148 prints at STA 20+71, a "
            "different run, NOT log68's 4+54->7+21 span)",
            "a printed terminal identity for the cross-sheet endpoints, which today "
            "are non-terminal drop structures (flower pot / installer HH) carrying no "
            "AP+splice (M8.26 already proved no zero-false end-identity gate exists "
            "from the current grammar)",
            "a non-geometric KMZ route<->structure linkage (absent in this source -- "
            "every Vacant Pipe route carries only Connection Type + empty Note), OR a "
            "SEPARATELY-gated geometric route-corroboration law with its own zero-"
            "false proof (NOT this milestone; never proximity-as-identity)",
        ],
        "rows": rows,
    }
    (OUT_DIR / "kmz_matchline_substitute_phase0.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    (OUT_DIR / "kmz_matchline_substitute_phase0.md").write_text(
        _markdown(report), encoding="utf-8")

    print(f"\n[m9.2] dispositions: {dict(sorted(disp_census.items()))}")
    print(f"[m9.2] two-endpoints-bound: {two_bound or '[]'} | single-anchor: "
          f"{single_anchor or '[]'} | bores moved: []")
    print(f"[m9.2] verdict: {report['verdict']}")
    print(f"[m9.2] report -> {OUT_DIR / 'kmz_matchline_substitute_phase0.json'}")
    return 0 if ok else 4


def _markdown(report: dict) -> str:
    L = ["# M9.2 Phase 0 -- KMZ_MATCHLINE_SUBSTITUTE feasibility", "",
         f"Verdict: **{report['verdict']}**", "",
         report["phase0_outcome"], "",
         "## Candidate list verification", "",
         f"- named scope: {report['candidate_list_verification']['named_scope']}",
         f"- strict no-equation class (live): "
         f"{report['candidate_list_verification']['strict_no_equation_class_live']}",
         f"- {report['candidate_list_verification']['log10_status']}",
         f"- future single-anchor candidates: {report['future_single_anchor_candidates']}",
         "", "## Disposition census", "", "| count | disposition |", "|---:|---|"]
    for k, v in report["disposition_census"].items():
        L.append(f"| {v} | `{k}` |")
    L += ["", "## Per-bore table", "",
          "| bore | strict? | product_lane | bucket | sheets | start id | "
          "end id | start pair | end pair | join start | join end | both? | "
          "route support | disposition |",
          "|---|:-:|---|---|---|---|---|---|---|---|---|:-:|---|---|"]
    for r in report["rows"]:
        L.append(
            f"| {r['bore_id']} | {'Y' if r['in_strict_no_equation_class'] else ''} "
            f"| {r['product_lane']} | {r['completion_bucket']} | {r['sheets']} | "
            f"{r['start_endpoint_evidence']['pair_kind']} | "
            f"{r['end_endpoint_evidence']['pair_kind']} | "
            f"{'Y' if r['start_has_full_ap_splice_pair'] else ''} | "
            f"{'Y' if r['end_has_full_ap_splice_pair'] else ''} | "
            f"{r['m91_join_start']} | {r['m91_join_end']} | "
            f"{'Y' if r['both_endpoints_bind_uniquely'] else ''} | "
            f"{'ADM' if r['kmz_route_support'].startswith('ADM') else 'none'} | "
            f"{r['phase0_disposition']} |")
    L += ["", "## Per-bore blocker", ""]
    for r in report["rows"]:
        L.append(f"- **{r['bore_id']}** ({r['phase0_disposition']}): {r['blocker']}")
    L += ["", "## Named evidence targets", ""]
    for t in report["named_evidence_targets"]:
        L.append(f"- {t}")
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
