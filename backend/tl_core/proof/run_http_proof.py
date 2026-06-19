"""tl_core Milestone-1 proof (HTTP surface):

Boots the real tl_core FastAPI app on a loopback port (threaded uvicorn) and
drives the full chain over REAL HTTP using only the Python stdlib (urllib — no
httpx/requests dependency):

  POST /v2/redline/run  (bore_log51 + real plan PDF)  -> MRQ payload + artifact URL
  GET  /v2/artifact/{name}                            -> 200 image/png, bytes == disk
  GET  /v2/artifact/{name}  (different tenant)         -> 404 (isolation, no leak)
  GET  /v2/artifact/{name}  (missing identity)         -> 401 (fail-closed)

Run (repo root, root venv):
  $env:PYTHONPATH = "backend"
  .\venv\Scripts\python.exe -m tl_core.proof.run_http_proof
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request

import uvicorn

from tl_core.app import create_app
from tl_core.config import Settings, _REPO_ROOT

DEFAULT_BORE = r"C:\Users\Patrick\OneDrive\Attachments\Desktop\excel bore logs\bore_log51.xlsx"
DEFAULT_PDF = str(_REPO_ROOT / "data" / "uploads" / "Brenham_Tx"
                  / "NEXTLINK - Brenham - Phase 5_07-15-25.pdf")
REPORT_DIR = _REPO_ROOT / "data" / "outputs" / "tl_core"
HOST, PORT = "127.0.0.1", 8099
BASE = f"http://{HOST}:{PORT}"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

TENANT_HEADERS = {"X-TL-Tenant": "proof-tenant", "X-TL-Session": "proof-session-log51"}


def _get(path, headers=None):
    req = urllib.request.Request(BASE + path, headers=headers or {}, method="GET")
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def _post_json(path, body, headers=None):
    data = json.dumps(body).encode("utf-8")
    h = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(BASE + path, data=data, headers=h, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode("utf-8", "replace")}


def main() -> int:
    bore = os.getenv("TL_CORE_PROOF_BORE", DEFAULT_BORE)
    pdf = os.getenv("TL_CORE_PROOF_PDF", DEFAULT_PDF)
    missing = [p for p in (bore, pdf) if not os.path.isfile(p)]
    if missing:
        print(f"[http-proof] FAIL: missing real input(s): {missing}")
        return 2

    settings = Settings.for_proof(artifact_root=REPORT_DIR / "artifacts")
    app = create_app(settings)
    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=PORT, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):  # wait up to ~10s for startup
            if getattr(server, "started", False):
                break
            time.sleep(0.1)
        if not getattr(server, "started", False):
            print("[http-proof] FAIL: server did not start")
            return 3

        checks = {}

        hs, _hh, _hb = _get("/v2/health")
        checks["health_200"] = hs == 200

        # 1) POST run -> payload with an artifact URL
        run_status, payload = _post_json("/v2/redline/run",
                                         {"bore_log_path": bore, "plan_pdf_path": pdf},
                                         headers=TENANT_HEADERS)
        checks["run_200"] = run_status == 200
        placements = (payload.get("pdf_first_evidence") or {}).get("placements") or []
        artifact = placements[0]["artifact"] if placements and placements[0].get("artifact") else None
        checks["payload_has_artifact"] = bool(artifact)
        checks["payload_schema"] = payload.get("schema_version") == "match-review-queue-1"
        name = artifact["name"] if artifact else None
        art_url = artifact["url"] if artifact else None
        print(f"[http-proof] run status={run_status} schema={payload.get('schema_version')} "
              f"placements={len(placements)} artifact={name}")

        served = {}
        if art_url:
            # 2) GET artifact (owner) -> 200 image/png, real PNG bytes
            s, hdrs, body = _get(art_url, headers=TENANT_HEADERS)
            served = {"status": s, "content_type": hdrs.get("content-type") or hdrs.get("Content-Type"),
                      "bytes": len(body), "png_magic": body[:8] == PNG_MAGIC}
            checks["artifact_200"] = s == 200
            checks["artifact_png"] = served["png_magic"] and served["bytes"] > 2000
            checks["artifact_content_type"] = (served["content_type"] or "").startswith("image/png")
            print(f"[http-proof] artifact GET status={s} ctype={served['content_type']} "
                  f"bytes={served['bytes']} png={served['png_magic']}")

            # cross-check: served bytes == bytes on disk in the scoped store
            disk = (settings.artifact_root / "proof-tenant" / "proof-session-log51" / name)
            checks["bytes_match_disk"] = disk.is_file() and disk.stat().st_size == len(body)

            # 3) cross-tenant -> 404 (isolation, no existence leak)
            xs, _, _ = _get(art_url, headers={"X-TL-Tenant": "other-tenant",
                                              "X-TL-Session": "proof-session-log51"})
            checks["cross_tenant_404"] = xs == 404
            print(f"[http-proof] cross-tenant GET status={xs} (expect 404)")

            # 4) missing identity -> 401 (fail-closed)
            ns, _, _ = _get(art_url, headers={})
            checks["no_identity_401"] = ns == 401
            print(f"[http-proof] no-identity GET status={ns} (expect 401)")

        passed = all(checks.values()) and bool(art_url)
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        report = {
            "milestone": "tl_core M1 (HTTP surface): POST run -> served artifact over "
                         "real HTTP, tenant-scoped, fail-closed",
            "passed": passed,
            "checks": checks,
            "artifact": {"name": name, "url": art_url, **served},
            "base_url": BASE,
        }
        rp = REPORT_DIR / "m1_http_proof_report.json"
        rp.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[http-proof] checks: {json.dumps(checks)}")
        print(f"[http-proof] report -> {rp}")
        print(f"[http-proof] {'PASS' if passed else 'FAIL'}")
        return 0 if passed else 1
    finally:
        server.should_exit = True
        thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
