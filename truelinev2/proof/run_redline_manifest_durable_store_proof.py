"""Phase-2I durable-store proof (READ/COPY-ONLY): store the real all-50 bundle, validate the store.

Copies the existing validated Phase-2D bundle into a durable, versioned, static-serving-safe store
layout under an immutable content-keyed id, re-points latest_valid, validates the whole store, and
confirms the website read contract. No render, no engine, no web/backend wiring; output is gitignored.

    python -m truelinev2.proof.run_redline_manifest_durable_store_proof
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from truelinev2.contracts.published_bundle_store import (
    WEBSITE_READ_CONTRACT,
    BUNDLES_SUBDIR,
    STORE_INDEX_FILENAME,
    store_bundle,
    validate_store,
    website_read_errors,
)

REPO = Path(__file__).resolve().parents[2]
SOURCE_BUNDLE = REPO / "data" / "outputs" / "redline_manifest_publish" / \
    "brenham_c19b565_all50_real_manifest"
STORE_ROOT = REPO / "data" / "outputs" / "redline_manifest_publish" / "durable_store_proof" / "store"


def main():
    if not (SOURCE_BUNDLE / "redline_manifest.json").is_file():
        print("Source bundle not present at %s" % SOURCE_BUNDLE)
        print("  (run truelinev2.proof.run_redline_manifest_all50_publish first)")
        return 2

    res = store_bundle(SOURCE_BUNDLE, STORE_ROOT,
                       created_at=datetime.now(timezone.utc).isoformat())
    bundle_id = res["bundle_id"]
    meta = res["meta"]
    store_rep = validate_store(STORE_ROOT)
    read_errs = website_read_errors(STORE_ROOT / BUNDLES_SUBDIR / bundle_id)

    print("== Phase-2I durable bundle store proof ==")
    print("  source bundle:        %s" % SOURCE_BUNDLE)
    print("  store root:           %s" % STORE_ROOT)
    print("  action:               %s" % res["action"])
    print("  immutable bundle id:  %s" % bundle_id)
    print("  layout:               %s/%s/%s/{redline_manifest.json, artifacts/<log>/<file>.png}"
          % (STORE_ROOT.name, BUNDLES_SUBDIR, bundle_id))
    print("  latest pointer:       %s -> %s" % (STORE_INDEX_FILENAME, store_rep["latest_valid"]))
    print("  manifest sha256:      %s" % meta["manifest_sha256"])
    print("  render commit:        %s (expect c19b565)" % meta["render_commit"])
    print("  artifact count/bytes: %d / %d" % (meta["artifact_count"], meta["total_bytes"]))
    print("  summary:              %s" % meta["summary"])
    print("  created_at:           %s" % meta["created_at"])
    print("  manifest entrypoint:  %s/%s/redline_manifest.json" % (BUNDLES_SUBDIR, bundle_id))
    print("  store valid:          %s (bundles=%d, latest_pointer_ok=%s, invalid=%s)" % (
        store_rep["valid"], store_rep["bundle_count"], store_rep["latest_pointer_ok"],
        store_rep["invalid_bundles"] or "none"))
    print("  website-readable:     %s %s" % ("YES" if not read_errs else "NO", read_errs or ""))
    print("  --- website read contract ---")
    for rule in WEBSITE_READ_CONTRACT:
        print("    - " + rule)

    # Diagnostic snapshot (gitignored).
    (STORE_ROOT.parent / "_phase2i_durable_store_proof.json").write_text(
        json.dumps({"bundle_id": bundle_id, "action": res["action"], "store_validation": store_rep,
                    "website_read_errors": read_errs, "meta": meta,
                    "website_read_contract": WEBSITE_READ_CONTRACT}, indent=2),
        encoding="utf-8")

    ok = store_rep["valid"] and not read_errs
    print("  RESULT: %s" % ("OK" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
