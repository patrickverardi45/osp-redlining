"""M1 proof: v2's OWN pipeline reproduces the Brenham log51 placement
(AUTO_SELECT, sheet 8, 0+00->2+99, 299') and serves a real PNG over HTTP.

Graded against the KNOWN old-engine answer (not by calling it). Run:
  $env:PYTHONPATH = "."   # repo root
  .\venv\Scripts\python.exe -m truelinev2.proof.run_m1_brenham
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request

import uvicorn

from truelinev2.api.app import create_app
from truelinev2.config import Settings, _REPO_ROOT
from truelinev2.context import require_context
from truelinev2.service import RedlineService
from truelinev2.store.artifacts import ArtifactStore
from truelinev2.store.db import ReviewStore

BORE = r"C:\Users\Patrick\OneDrive\Attachments\Desktop\excel bore logs\bore_log51.xlsx"
PDF = str(_REPO_ROOT / "data" / "uploads" / "Brenham_Tx" / "NEXTLINK - Brenham - Phase 5_07-15-25.pdf")
REPORT_DIR = _REPO_ROOT / "data" / "outputs" / "truelinev2"
HOST, PORT = "127.0.0.1", 8100
PNG = b"\x89PNG\r\n\x1a\n"
H = {"X-TL-Tenant": "proof-tenant", "X-TL-Session": "brenham-log51"}
KNOWN_OLD_ENGINE = {"status": "AUTO_SELECT", "sheets": [8], "station_span": "0+00->2+99", "footage": 299.0}


def _get(path, headers=None):
    req = urllib.request.Request(f"http://{HOST}:{PORT}{path}", headers=headers or {})
    try:
        r = urllib.request.urlopen(req, timeout=60)
        return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def main() -> int:
    bore = os.getenv("TL2_PROOF_BORE", BORE)
    pdf = os.getenv("TL2_PROOF_PDF", PDF)
    missing = [p for p in (bore, pdf) if not os.path.isfile(p)]
    if missing:
        print(f"[m1] FAIL: missing real inputs: {missing}")
        return 2

    settings = Settings.for_proof()
    artifacts = ArtifactStore(settings.artifact_root)
    db = ReviewStore(settings.db_path)
    svc = RedlineService(settings, artifacts, db)
    ctx = require_context("proof-tenant", "brenham-log51")

    t0 = time.time()
    payload = svc.run(ctx, bore, pdf)
    el = time.time() - t0
    item = payload.items[0]
    pl = item.placement
    print(f"[m1] bore={item.bore.bore_id} span={item.bore.station_start}->{item.bore.station_end} "
          f"span_ft={item.bore.span_ft} print_sheets={item.bore.sheet_refs}")
    print(f"[m1] placement status={pl.status.value} tier={pl.tier} sheets={pl.sheets} "
          f"station={pl.station_span} footage={pl.footage} "
          f"delta(f/s/e)={pl.footage_delta}/{pl.start_delta}/{pl.end_delta} "
          f"artifacts={len(pl.artifacts)} ({el:.1f}s)")

    checks = {
        "status_AUTO_SELECT": pl.status.value == "AUTO_SELECT",
        "sheet_8": pl.sheets == [8],
        "station_0+00->2+99": pl.station_span == "0+00->2+99",
        "footage_299": abs((pl.footage or 0) - 299.0) <= 1.0,
        "artifact_rendered": len(pl.artifacts) >= 1,
    }

    app = create_app(settings)
    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=PORT, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    served = {}
    try:
        for _ in range(100):
            if getattr(server, "started", False):
                break
            time.sleep(0.1)
        hs, _h, _b = _get("/v2/health")
        checks["health_200"] = hs == 200
        if pl.artifacts:
            name = pl.artifacts[0].name
            s, hd, body = _get(f"/v2/artifact/{name}", headers=H)
            ct = hd.get("content-type") or hd.get("Content-Type")
            served = {"name": name, "status": s, "content_type": ct,
                      "bytes": len(body), "png": body[:8] == PNG}
            checks["artifact_200"] = s == 200
            checks["artifact_png"] = body[:8] == PNG and len(body) > 2000
            checks["artifact_ctype"] = (ct or "").startswith("image/png")
            disk = settings.artifact_root / "proof-tenant" / "brenham-log51" / name
            checks["bytes_match_disk"] = disk.is_file() and disk.stat().st_size == len(body)
            xs, _xh, _xb = _get(f"/v2/artifact/{name}",
                                headers={"X-TL-Tenant": "other", "X-TL-Session": "brenham-log51"})
            checks["cross_tenant_404"] = xs == 404
            ns, _nh, _nb = _get(f"/v2/artifact/{name}", headers={})
            checks["no_identity_401"] = ns == 401
        rv, _rh, _rb = _get("/v2/review", headers=H)
        checks["review_200"] = rv == 200
    finally:
        server.should_exit = True
        th.join(timeout=5)

    passed = all(checks.values())
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "milestone": "truelinev2 M1 — Brenham log51 via v2's own pipeline",
        "passed": passed,
        "elapsed_sec": round(el, 2),
        "bore": bore, "pdf": pdf,
        "result_vs_known_old_engine": {"expected": KNOWN_OLD_ENGINE,
                                       "got": {"status": pl.status.value, "sheets": pl.sheets,
                                               "station_span": pl.station_span, "footage": pl.footage}},
        "served": served,
        "checks": checks,
        "deferred_to_m2": "ODOT VeroFy bore-log ingestion + ODOT plan dialect (DB-NN convention).",
    }
    (REPORT_DIR / "m1_brenham_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[m1] checks: {json.dumps(checks)}")
    print(f"[m1] report -> {REPORT_DIR / 'm1_brenham_report.json'}")
    print(f"[m1] {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
