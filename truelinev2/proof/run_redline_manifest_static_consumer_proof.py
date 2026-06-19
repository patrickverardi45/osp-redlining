"""Phase-2J static-consumer proof (READ-ONLY): read the REAL durable bundle end-to-end.

Drives the read-only `StaticBundleConsumer` against the REAL Phase-2I durable store: follows
`latest_valid`, enforces the website read contract, loads the published manifest, and resolves ONE
real `FINAL_REDLINE_PNG` artifact end-to-end (bytes read + sha256/size verified vs the manifest). This
is the first website/backend integration proof for the durable redline-manifest bundle.

No engine, no renderer, no web/backend wiring, no deploy. The consumer is default-OFF; this proof
enables it explicitly (`enable=True`) -- the production gate stays OFF. Output is gitignored.

    python -m truelinev2.proof.run_redline_manifest_static_consumer_proof
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from truelinev2.contracts.published_bundle_store import WEBSITE_READ_CONTRACT
from truelinev2.contracts.published_bundle_consumer import (
    CONSUMER_OPTIN_ENV,
    StaticBundleConsumer,
    consumer_enabled,
    consumer_read_errors,
)
# Authoritative store location (DRY: same constant the Phase-2I durable-store proof writes to).
from truelinev2.proof.run_redline_manifest_durable_store_proof import STORE_ROOT


def main():
    if not (STORE_ROOT / "store_index.json").is_file():
        print("Durable store not present at %s" % STORE_ROOT)
        print("  (run truelinev2.proof.run_redline_manifest_durable_store_proof first)")
        return 2

    # The consumer is default-OFF; this offline proof enables it explicitly. Show the gate state.
    consumer = StaticBundleConsumer(STORE_ROOT, enable=True)
    bundle_id = consumer.latest_valid_id()
    rb = consumer.open_latest()
    payload = rb.manifest_payload()
    read_errs = consumer_read_errors(rb.bundle_root)

    finals = rb.final_artifacts()
    # Sum served (FINAL_REDLINE_PNG) sizes without reading the full 50 MB (read_bytes=False).
    served_bytes = sum(rb.resolve_artifact(a["path"], read_bytes=False)["bytes"] for _lid, a in finals)

    # End-to-end read of ONE real artifact: bytes read + sha256/size checksum-verified vs the manifest.
    sample_log, sample_art = finals[0]
    served = rb.resolve_artifact(sample_art["path"], read_bytes=True)
    sample_ok = (len(served["data"]) == served["bytes"]
                 and hashlib.sha256(served["data"]).hexdigest() == served["sha256"])

    s = payload.get("summary", {})
    print("== Phase-2J read-only static bundle consumer proof ==")
    print("  store root:           %s" % STORE_ROOT)
    print("  gate env:             %s (consumer_enabled()=%s; proof enabled explicitly)"
          % (CONSUMER_OPTIN_ENV, consumer_enabled()))
    print("  latest_valid:         %s" % bundle_id)
    print("  bundle root:          %s" % rb.bundle_root)
    print("  manifest sha256:      %s" % rb.manifest_sha256)
    print("  render commit:        %s (expect c19b565)"
          % payload.get("engine", {}).get("render_commit"))
    print("  mock_example:         %s (must be False)" % payload.get("mock_example"))
    print("  frontier / summary:   %s  (total=%s drawn=%s covered=%s blocked=%s)"
          % (s.get("frontier"), s.get("total_logs"), s.get("drawn_count"),
             s.get("covered_count"), s.get("blocked_count")))
    print("  FINAL_REDLINE_PNG:    %d artifact(s), %d bytes (website-rendered set)"
          % (len(finals), served_bytes))
    print("  read-contract errors: %s" % (read_errs or "none"))
    print("  --- end-to-end artifact read (sample) ---")
    print("    log:                %s" % sample_log)
    print("    path:               %s" % served["path"])
    print("    content_type:       %s" % served["content_type"])
    print("    bytes / sha256:     %d / %s" % (served["bytes"], served["sha256"]))
    print("    checksum-verified:  %s" % sample_ok)
    print("  --- website read contract (enforced) ---")
    for rule in WEBSITE_READ_CONTRACT:
        print("    - " + rule)

    # Diagnostic snapshot (gitignored under data/outputs/).
    (STORE_ROOT.parent / "_phase2j_static_consumer_proof.json").write_text(
        json.dumps({
            "store_root": str(STORE_ROOT), "bundle_id": bundle_id,
            "manifest_sha256": rb.manifest_sha256,
            "render_commit": payload.get("engine", {}).get("render_commit"),
            "mock_example": payload.get("mock_example"), "summary": s,
            "final_redline_png_count": len(finals), "final_redline_png_bytes": served_bytes,
            "read_contract_errors": read_errs,
            "sample_artifact": {k: served[k] for k in ("log_id", "path", "content_type",
                                                        "bytes", "sha256")},
            "sample_checksum_verified": sample_ok,
            "website_read_contract": WEBSITE_READ_CONTRACT,
        }, indent=2), encoding="utf-8")

    ok = (not read_errs and payload.get("mock_example") is False and sample_ok and len(finals) > 0)
    print("  RESULT: %s" % ("OK" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
