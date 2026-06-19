"""Phase-2E proof: validate the real Phase-2D published bundle + emit its index (READ-ONLY).

Validates the Phase-2D output directory as a published run bundle (schema-valid manifest, every
artifact a safe in-root relative path that exists + matches sha256/bytes + published/non-placeholder,
static-serving compatible), then writes `_published_bundle_index.json` into the (gitignored) bundle.
Reads only; copies nothing into the repo; runs no render/engine.

    python -m truelinev2.proof.run_redline_manifest_published_bundle_validation
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from truelinev2.contracts.published_bundle import (
    build_bundle_index,
    validate_bundle,
    write_bundle_index,
)

REPO = Path(__file__).resolve().parents[2]
BUNDLE = REPO / "data" / "outputs" / "redline_manifest_publish" / "brenham_c19b565_all50_real_manifest"


def main():
    if not (BUNDLE / "redline_manifest.json").is_file():
        print("Phase-2D bundle not present at %s" % BUNDLE)
        print("  (run truelinev2.proof.run_redline_manifest_all50_publish first)")
        return 2

    report = validate_bundle(BUNDLE)
    index = build_bundle_index(BUNDLE, report,
                               generated_at=datetime.now(timezone.utc).isoformat())
    index_path = write_bundle_index(BUNDLE, index)

    print("== Phase-2E published-bundle validation ==")
    print("  bundle root:        %s" % BUNDLE)
    print("  bundle valid:       %s" % ("YES" if report["valid"] else "NO"))
    print("  manifest sha256:    %s" % report["manifest_sha256"])
    print("  artifact count:     %d" % report["artifact_count"])
    print("  total bytes:        %d" % report["total_bytes"])
    print("  checksum mismatches:%d  %s" % (len(report["checksum_mismatches"]), report["checksum_mismatches"][:3]))
    print("  missing files:      %d  %s" % (len(report["missing_files"]), report["missing_files"][:3]))
    print("  unsafe paths:       %d  %s" % (len(report["unsafe_paths"]), report["unsafe_paths"][:3]))
    print("  schema errors:      %d  %s" % (len(report["schema_errors"]), report["schema_errors"][:3]))
    print("  structure errors:   %d  %s" % (len(report["structure_errors"]), report["structure_errors"][:3]))
    print("  static-serving safe:%s" % ("YES" if report["static_serving_safe"] else "NO"))
    print("  bundle index:       %s" % index_path)
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
