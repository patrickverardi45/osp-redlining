r"""M8.2l -- OFF vs ON sweep for the default-OFF reset-collision gate.

Runs the REAL engine over the full 58-log corpus twice:
  OFF: ``run_match(...)`` exactly as the default (no gate injected), and
  ON:  ``run_match(..., collision_gate=...)`` with the gate built from the plan's
       parsed frame equations + the banked M8.2j human grades.

PASS requires ALL of:
  * OFF distribution == AUTO_SELECT=14 REVIEW=9 ABSTAIN=33 ERROR=2 PLACED=23 (default unchanged)
  * ON  distribution == AUTO_SELECT=11 REVIEW=11 ABSTAIN=34 ERROR=2 PLACED=22
  * the changed set is EXACTLY log42 (AUTO->REVIEW), log57 (AUTO->REVIEW), log65 (AUTO->ABSTAIN)
  * zero promotions anywhere (no status may move toward AUTO)
  * the SERVICE flag path (Settings.reset_collision_optin=True) reproduces log42 -> REVIEW
Any other change -> verdict FAILURE and a nonzero exit. Frame translation stays
INACTIVE in BOTH runs (frame_graph=None); M8.2d's blanket opt-in is not re-attempted.

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_reset_collision_optin_sweep
"""
from __future__ import annotations

import dataclasses
import json
import os
from typing import Any, Dict, List

from truelinev2.config import Settings, _REPO_ROOT
from truelinev2.context import require_context
from truelinev2.extract.registry import select_dialect
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.collision_gate import CollisionGate, collect_equations, load_human_grades
from truelinev2.match.engine import run_match
from truelinev2.proof.run_brenham_corpus import CORPUS_DIR, EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.service import RedlineService
from truelinev2.store.artifacts import ArtifactStore
from truelinev2.store.db import ReviewStore

OUT_JSON = _REPO_ROOT / "data" / "outputs" / "reset_collision_optin_sweep.json"
OUT_MD = _REPO_ROOT / "data" / "outputs" / "reset_collision_optin_sweep.md"

EXPECTED_OFF = {"AUTO_SELECT": 14, "REVIEW": 9, "ABSTAIN": 33, "ERROR": 2, "PLACED": 23}
EXPECTED_ON = {"AUTO_SELECT": 11, "REVIEW": 11, "ABSTAIN": 34, "ERROR": 2, "PLACED": 22}
EXPECTED_CHANGES = {"log42": ("AUTO_SELECT", "REVIEW"),
                    "log57": ("AUTO_SELECT", "REVIEW"),
                    "log65": ("AUTO_SELECT", "ABSTAIN")}
_RANK = {"ABSTAIN": 0, "ERROR": 0, "REVIEW": 1, "AUTO_SELECT": 2}


def _counts(statuses: List[str]) -> Dict[str, int]:
    c = {k: statuses.count(k) for k in ("AUTO_SELECT", "REVIEW", "ABSTAIN", "ERROR")}
    c["PLACED"] = c["AUTO_SELECT"] + c["REVIEW"]
    return c


def main() -> int:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    if not os.path.isfile(PDF) or not os.path.isdir(CORPUS_DIR):
        print(f"[m8.2l] STOP: inputs missing (pdf={os.path.isfile(PDF)} corpus={os.path.isdir(CORPUS_DIR)})")
        return 2
    corpus = enumerate_corpus(CORPUS_DIR)
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.2l] STOP: expected {EXPECTED_COUNT} logs, got {len(corpus)} -- corpus drift.")
        return 3

    settings = Settings.for_proof()
    assert settings.reset_collision_optin is False, "for_proof() must keep the flag OFF"
    plan = PlanPdf(PDF)
    dialect = select_dialect(plan)
    offset = dialect.calibrate(plan, settings.sheet_offset)
    human_grades = load_human_grades()

    rows: List[Dict[str, Any]] = []
    eq_cache: Dict[int, Any] = {}
    for p in corpus:
        rec: Dict[str, Any] = {"bore_id": p.stem.replace("bore_log", "log"), "file": p.name}
        try:
            bore = load_borelog(str(p))
        except Exception as e:
            rec.update({"off": "ERROR", "on": "ERROR", "error": f"{type(e).__name__}: {e}"})
            rows.append(rec)
            continue
        missing = [s for s in bore.sheet_refs if s not in eq_cache]
        if missing:
            eq_cache.update(collect_equations(plan, offset, missing))
        gate = CollisionGate(
            equations_by_sheet={s: eq_cache[s] for s in bore.sheet_refs if s in eq_cache},
            human_grades=human_grades)
        off = run_match(bore, plan, dialect, offset)
        on = run_match(bore, plan, dialect, offset, collision_gate=gate)
        rec.update({"bore_id": bore.bore_id, "off": off.status.value, "on": on.status.value,
                    "on_caveats": list(on.caveats)})
        rows.append(rec)

    off_counts = _counts([r["off"] for r in rows])
    on_counts = _counts([r["on"] for r in rows])
    changed = {r["bore_id"]: (r["off"], r["on"]) for r in rows if r["off"] != r["on"]}
    promotions = {r["bore_id"]: (r["off"], r["on"]) for r in rows
                  if _RANK[r["on"]] > _RANK[r["off"]]}

    # service-level flag smoke: the Settings flag path must reproduce log42 -> REVIEW
    service_smoke: Dict[str, Any] = {"ran": False}
    log42_path = next((p for p in corpus if p.stem == "bore_log42"), None)
    if log42_path is not None:
        on_settings = dataclasses.replace(settings, reset_collision_optin=True)
        svc = RedlineService(on_settings, ArtifactStore(on_settings.artifact_root),
                             ReviewStore(on_settings.db_path))
        item = svc.run(require_context("proof-tenant", "m82l-flag-smoke"),
                       str(log42_path), PDF).items[0]
        service_smoke = {"ran": True, "bore_id": item.bore.bore_id,
                         "status": item.placement.status.value,
                         "expected": "REVIEW",
                         "pass": item.placement.status.value == "REVIEW"}

    checks = {
        "off_matches_default": off_counts == EXPECTED_OFF,
        "on_matches_expected": on_counts == EXPECTED_ON,
        "changed_set_exact": changed == EXPECTED_CHANGES,
        "zero_promotions": not promotions,
        "service_flag_smoke": bool(service_smoke.get("pass")),
    }
    verdict = "PASS" if all(checks.values()) else "FAILURE"

    report = {
        "milestone": "truelinev2 M8.2l -- default-OFF reset-collision gate OFF vs ON sweep",
        "frame_translation_active": False,
        "off_counts": off_counts, "expected_off": EXPECTED_OFF,
        "on_counts": on_counts, "expected_on": EXPECTED_ON,
        "changed": changed, "expected_changes": EXPECTED_CHANGES,
        "promotions": promotions,
        "service_flag_smoke": service_smoke,
        "checks": checks, "verdict": verdict,
        "rows": rows,
    }
    OUT_JSON.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    lines = [
        "# M8.2l -- reset-collision gate OFF vs ON sweep",
        "",
        f"- OFF: {off_counts}  (expected {EXPECTED_OFF})",
        f"- ON : {on_counts}  (expected {EXPECTED_ON})",
        f"- changed: {changed}",
        f"- expected: {EXPECTED_CHANGES}",
        f"- promotions: {promotions or 'NONE'}",
        f"- service flag smoke: {service_smoke}",
        f"- checks: {checks}",
        "",
        f"## VERDICT: {verdict}",
        "",
        "_Frame translation INACTIVE in both runs; the gate is demote-only and fires only on_",
        "_runtime-detected on-crossing reset collisions backed by the banked M8.2j grades._",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"[m8.2l] OFF {off_counts}")
    print(f"[m8.2l] ON  {on_counts}")
    print(f"[m8.2l] changed={changed}")
    print(f"[m8.2l] promotions={promotions or 'NONE'}  service_smoke={service_smoke.get('pass')}")
    print(f"[m8.2l] VERDICT: {verdict}")
    print(f"[m8.2l] report -> {OUT_MD}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
