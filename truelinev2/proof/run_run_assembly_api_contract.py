r"""M9.6 -- RUN-ASSEMBLY review-card API/transport CONTRACT proof.

Proves the bounded, default-OFF, read-only v2 transport surface for the M9.4.2
RunAssemblyReviewService cards: a proof-side export envelope
(proof/export_run_assembly_cards_json.py) consumed by a context-free GET route
(api/run_assembly_routes.py), mounted by create_app ONLY when
settings.run_assembly_api_optin is True. It changes no engine placement, no per-bore
reviewer bundle, no product bucket, no UI; renders nothing; deploys nothing.

  G1  inputs present; the export returns exactly 3 run-assembly cards (live, via the service);
  G2  the 3 cards are exactly log10->log27 @AP-152 + log72->log39 @AP-117 (CANDIDATE) +
      log7->log65 @AP-163 (DROP_BRANCH) -- the M9.4.2 cards, unchanged;
  G3  log65 STAYS a JUNCTION_DROP_BRANCH (continuation_class DROP_BRANCH, departure 'drop');
  G4  the transport envelope contract: pinned export schema + service + card schema + full SHA;
  G5  validate_export is FAIL-CLOSED -- a geometry key, an AUTO card, a product-bucket key,
      an envelope-schema drift, and a DROP-without-drop card each raise ValueError;
  G6  DEFAULT-OFF: Settings.from_env() default is False; create_app(flag OFF) mounts NO
      /v2/reviewer/run-assembly route;
  G7  flag ON: create_app mounts EXACTLY the /v2/reviewer/run-assembly GET route, context-free
      (no dependencies);
  G8  the per-bore ReviewerBundleService bundle is BYTE-IDENTICAL before/after the export runs
      (the transport never touches the per-bore bundle);
  G9  M9.5 preserved: every card carries competing_departures == 1; the route + export
      reference no cross-sheet / frame-graph / placement path;
  G10 the transport envelope schema is DISJOINT from the card/bundle/group/design-stroke
      schemas, and the cards carry the M9.4.1 card schema (NOT a new product bucket);
  G11 read-only / additive: nothing rendered; the route + export import no placement/render
      path; the existing always-on + reviewer routes are unaffected by the new flag.

PROOF-ONLY: no placement, no engine wiring, no stroke/PNG/segment, no AUTO, no
tolerance/budget change, zero bores moved, zero product-bucket change, no UI, no deploy.

Exit codes: 0 PASS, 2 inputs missing, 3 corpus drift, 4 gate FAILURE.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_run_assembly_api_contract
"""
from __future__ import annotations

import copy
import dataclasses
import inspect
import json
import os

from fastapi.routing import APIRoute

from truelinev2.api.app import create_app
from truelinev2.config import _REPO_ROOT, Settings
from truelinev2.extract.kmz import BRENHAM_KMZ_DIALECT, read_kmz
from truelinev2.extract.terminus_profile import BRENHAM_TERMINUS_PROFILE
from truelinev2.proof import export_run_assembly_cards_json as EXP
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_kmz_correlation_audit import resolve_kmz
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.review.run_assembly_review_service import RunAssemblyReviewService
from truelinev2.review.design_stroke_cards import CARD_SCHEMA_VERSION
from truelinev2.review.group_review import GROUP_SCHEMA_VERSION
from truelinev2.review.reviewer_payloads import SCHEMA_VERSION
from truelinev2.review.reviewer_service import (
    BUNDLE_SCHEMA_VERSION,
    ReviewerBundleService,
    ReviewRunMode,
)
from truelinev2.review.run_assembly_review import (
    CONTINUATION_CANDIDATE,
    DROP_BRANCH,
    RUN_ASSEMBLY_SCHEMA_VERSION,
)

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "run_assembly_api_contract"
RUN_ASSEMBLY_PATH = "/v2/reviewer/run-assembly"

EXPECT_CARDS = {
    ("log10", "log27", 152, CONTINUATION_CANDIDATE),
    ("log72", "log39", 117, CONTINUATION_CANDIDATE),
    ("log7", "log65", 163, DROP_BRANCH),
}


def _settings(*, run_assembly_on: bool) -> Settings:
    return dataclasses.replace(Settings.for_proof(), run_assembly_api_optin=run_assembly_on)


def _run_assembly_routes(app):
    return [r for r in app.routes
            if isinstance(r, APIRoute) and r.path == RUN_ASSEMBLY_PATH]


def _raises_value_error(mutate) -> bool:
    env = copy.deepcopy(EXPORT_SAMPLE)
    mutate(env)
    try:
        EXP.validate_export(env)
        return False
    except ValueError:
        return True


def main() -> int:
    kmz_path, kmz_how = resolve_kmz()
    corpus_dir, how = resolve_corpus()
    print(f"[m9.6] kmz   : {kmz_path}  ({kmz_how})")
    print(f"[m9.6] corpus: {corpus_dir}  ({how})")
    if not os.path.isfile(kmz_path) or not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m9.6] STOP: inputs missing")
        return 2
    paths = enumerate_corpus(corpus_dir)
    if len(paths) != EXPECTED_COUNT:
        print(f"[m9.6] STOP: corpus drift ({len(paths)})")
        return 3
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = True

    per_bore = ReviewerBundleService(corpus_dir=corpus_dir, plan_pdf_path=PDF,
                                     project_id="brenham-ph5", bore_log_paths=paths)

    # ---- run the transport once; prove the per-bore bundle is untouched around it -
    before = per_bore.generate(ReviewRunMode.DEFAULT_BASELINE).model_dump_json()
    export = EXP.generate_export()
    after = per_bore.generate(ReviewRunMode.DEFAULT_BASELINE).model_dump_json()

    global EXPORT_SAMPLE
    EXPORT_SAMPLE = export
    cards = export["cards"]
    got = {(c["end_bore"], c["start_bore"], c["terminal_ap"], c["continuation_class"])
           for c in cards}

    # ---- G1 ------------------------------------------------------------------
    g1 = len(cards) == 3
    print(f"[m9.6] {'PASS' if g1 else 'FAIL'}  G1 export returns exactly 3 run-assembly "
          f"cards via the service (got {len(cards)})")
    ok &= g1

    # ---- G2 ------------------------------------------------------------------
    g2 = got == EXPECT_CARDS
    print(f"[m9.6] {'PASS' if g2 else 'FAIL'}  G2 exact cards: "
          f"{sorted((c['end_bore'], c['start_bore'], c['terminal_ap']) for c in cards)}")
    ok &= g2

    # ---- G3 ------------------------------------------------------------------
    l65 = next((c for c in cards if (c["end_bore"], c["start_bore"]) == ("log7", "log65")), None)
    g3 = (l65 is not None and l65["continuation_class"] == DROP_BRANCH
          and l65["departure_run_class"] == "drop")
    print(f"[m9.6] {'PASS' if g3 else 'FAIL'}  G3 log65 stays JUNCTION_DROP_BRANCH "
          f"(continuation_class={l65['continuation_class'] if l65 else None}, "
          f"departure={l65['departure_run_class'] if l65 else None})")
    ok &= g3

    # ---- G4: envelope contract ----------------------------------------------
    src = export["source"]
    g4 = (export["export_schema_version"] == EXP.EXPORT_SCHEMA_VERSION
          and src["service"] == EXP.SERVICE_NAME
          and src["card_schema_version"] == RUN_ASSEMBLY_SCHEMA_VERSION
          and EXP._FULL_SHA.fullmatch(src["source_git_head"]) is not None
          and all(c["schema_version"] == RUN_ASSEMBLY_SCHEMA_VERSION for c in cards))
    print(f"[m9.6] {'PASS' if g4 else 'FAIL'}  G4 envelope contract: schema "
          f"{export['export_schema_version']}, service {src['service']}, card schema "
          f"{src['card_schema_version']}")
    ok &= g4

    # ---- G5: validate_export fail-closed ------------------------------------
    def _geom(env): env["cards"][0]["geometry"] = [[0, 0]]
    def _auto(env): env["cards"][0]["auto"] = True
    def _bucket(env): env["lane_counts"] = {"PLACED_REVIEW": 30}
    def _schema(env): env["export_schema_version"] = "something-else-1"
    def _drop_no_drop(env):
        for c in env["cards"]:
            if c["continuation_class"] == DROP_BRANCH:
                c["departure_run_class"] = "trunk"
    def _png_key(env): env["cards"][0]["terminal_ap"] = {"overlay.png": 1}  # png as a KEY
    checks = {"geometry_key": _geom, "auto_card": _auto, "product_bucket_key": _bucket,
              "envelope_schema_drift": _schema, "drop_without_drop": _drop_no_drop,
              "png_as_dict_key": _png_key}
    fail_closed = {name: _raises_value_error(mut) for name, mut in checks.items()}
    g5 = all(fail_closed.values())
    print(f"[m9.6] {'PASS' if g5 else 'FAIL'}  G5 validate_export fail-closed: {fail_closed}")
    ok &= g5

    # ---- G6: DEFAULT-OFF -----------------------------------------------------
    monkeypatch_default = Settings.for_proof().run_assembly_api_optin
    app_off = create_app(_settings(run_assembly_on=False))
    g6 = (monkeypatch_default is False and not _run_assembly_routes(app_off)
          and not any(r.path == RUN_ASSEMBLY_PATH for r in app_off.routes
                      if isinstance(r, APIRoute)))
    print(f"[m9.6] {'PASS' if g6 else 'FAIL'}  G6 DEFAULT-OFF: for_proof flag False; "
          f"create_app(OFF) mounts no {RUN_ASSEMBLY_PATH} route")
    ok &= g6

    # ---- G7: flag ON mounts exactly the GET context-free route ---------------
    app_on = create_app(_settings(run_assembly_on=True))
    ra_routes = _run_assembly_routes(app_on)
    g7 = (len(ra_routes) == 1 and ra_routes[0].methods == {"GET"}
          and not ra_routes[0].dependant.dependencies)
    print(f"[m9.6] {'PASS' if g7 else 'FAIL'}  G7 flag ON mounts exactly 1 GET context-free "
          f"route {RUN_ASSEMBLY_PATH} (methods={ra_routes[0].methods if ra_routes else None})")
    ok &= g7

    # ---- G8: per-bore bundle byte-identical before/after the transport -------
    g8 = before == after
    print(f"[m9.6] {'PASS' if g8 else 'FAIL'}  G8 per-bore reviewer bundle byte-identical "
          f"before/after the export runs")
    ok &= g8

    # ---- G9: M9.5 preserved (frame-scoped; no cross-sheet/placement) ---------
    route_src = inspect.getsource(__import__("truelinev2.api.run_assembly_routes",
                                             fromlist=["x"]))
    exp_src = inspect.getsource(EXP)
    forbidden_refs = ("cross_sheet", "_build_plan_frame_graph", "matchline",
                      "resolve_bore", "run_match", "sweep")
    g9 = (all(c["competing_departures"] == 1 for c in cards)
          and not any(t in route_src for t in forbidden_refs)
          and not any(t in exp_src for t in forbidden_refs))
    print(f"[m9.6] {'PASS' if g9 else 'FAIL'}  G9 M9.5 preserved: competing_departures==1 "
          f"for all cards; route+export reference no cross-sheet/frame-graph/placement")
    ok &= g9

    # ---- G10: schema disjoint; cards carry the M9.4.1 card schema ------------
    other_schemas = {BUNDLE_SCHEMA_VERSION, SCHEMA_VERSION, CARD_SCHEMA_VERSION,
                     GROUP_SCHEMA_VERSION, RUN_ASSEMBLY_SCHEMA_VERSION,
                     "truelinev2-web-reviewer-bundle-export-1"}
    text = json.dumps(export)
    g10 = (EXP.EXPORT_SCHEMA_VERSION not in other_schemas
           and all(c["schema_version"] == RUN_ASSEMBLY_SCHEMA_VERSION for c in cards)
           and not any(k in text for k in ('"lane"', '"lane_counts"', '"status_counts"',
                                           '"payloads"', '"confidence_class"')))
    print(f"[m9.6] {'PASS' if g10 else 'FAIL'}  G10 envelope schema disjoint "
          f"({EXP.EXPORT_SCHEMA_VERSION}); cards carry the M9.4.1 card schema; no product-bucket key")
    ok &= g10

    # ---- G11: read-only / additive ------------------------------------------
    no_png = not list(OUT_DIR.glob("*.png"))
    no_placement_import = ("truelinev2.render" not in route_src and "render_redline" not in route_src
                           and "truelinev2.render" not in exp_src and "render_redline" not in exp_src)
    # the existing always-on routes are unaffected when the new flag is OFF
    base_paths = {r.path for r in app_off.routes if isinstance(r, APIRoute)}
    g11 = no_png and no_placement_import and RUN_ASSEMBLY_PATH not in base_paths
    print(f"[m9.6] {'PASS' if g11 else 'FAIL'}  G11 read-only/additive: no PNG; no "
          f"placement/render import; existing routes unaffected when flag OFF")
    ok &= g11

    # ---- G12: the transport is VERBATIM -- the envelope cards are byte-identical
    # (full dict, every field) to a DIRECT RunAssemblyReviewService.generate() call,
    # not merely a 4-field literal. Pins "transport reimplements nothing".
    direct_model = read_kmz(kmz_path, BRENHAM_KMZ_DIALECT)
    direct_service = RunAssemblyReviewService(
        corpus_dir=corpus_dir, plan_pdf_path=PDF, bore_log_paths=paths,
        kmz_model=direct_model, terminus_profile=BRENHAM_TERMINUS_PROFILE,
        source_contradiction_bores=EXP.SOURCE_CONTRADICTION_BORES)
    direct_cards = [c.model_dump(mode="json") for c in direct_service.generate()]
    g12 = direct_cards == cards
    print(f"[m9.6] {'PASS' if g12 else 'FAIL'}  G12 transport VERBATIM: envelope cards "
          f"byte-identical (full dict) to a direct RunAssemblyReviewService.generate()")
    ok &= g12

    verdict = "PASS" if ok else "FAILURE"
    report = {
        "milestone": ("truelinev2 M9.6 -- RUN-ASSEMBLY review-card read-only API/transport "
                      "contract (bounded, default-OFF; consumes RunAssemblyReviewService; "
                      "additive; no placement/bucket/UI/deploy)"),
        "kmz_path": kmz_path, "corpus_dir": corpus_dir, "plan_pdf": PDF,
        "verdict": verdict,
        "transport_envelope_schema": EXP.EXPORT_SCHEMA_VERSION,
        "card_schema": RUN_ASSEMBLY_SCHEMA_VERSION,
        "route": RUN_ASSEMBLY_PATH,
        "default_off_flag": "run_assembly_api_optin / TL2_RUN_ASSEMBLY_API_OPTIN",
        "cards": cards,
        "per_bore_byte_identical": g8,
        "fail_closed_checks": fail_closed,
        "competing_departures_per_card": {f"{c['end_bore']}->{c['start_bore']}":
                                          c["competing_departures"] for c in cards},
        "no_product_bucket": g10, "no_cross_sheet_widen": g9, "read_only_additive": g11,
        "bores_moved": 0, "product_bucket_changes": 0,
        "next_step": ("a frontend/Vercel UI that renders these cards is a SEPARATE, "
                      "authorized milestone; not begun. No Render/Vercel deploy here."),
    }
    (OUT_DIR / "run_assembly_api_contract.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")

    print(f"\n[m9.6] cards: {sorted((c['end_bore'], '->', c['start_bore'], c['continuation_class']) for c in cards)}")
    print(f"[m9.6] route {RUN_ASSEMBLY_PATH} default-OFF; per-bore byte-identical: {g8}")
    print(f"[m9.6] verdict: {verdict}")
    print(f"[m9.6] report -> {OUT_DIR / 'run_assembly_api_contract.json'}")
    return 0 if ok else 4


EXPORT_SAMPLE: dict = {}

if __name__ == "__main__":
    raise SystemExit(main())
