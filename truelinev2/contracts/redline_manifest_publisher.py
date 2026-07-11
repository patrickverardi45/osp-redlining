"""Phase-2A redline manifest artifact publisher (contract pipe, NOT the engine).

Takes a manifest-shaped input plus a directory of final redline artifacts and emits a
REAL manifest: artifacts copied to a stable publish directory, each record carrying a
real ``sha256`` + ``bytes`` + ``published: true`` + ``example_placeholder: false``, and
``mock_example`` flipped to ``false``. It validates input and output against
``redline_manifest.schema.json`` and fails loudly when a drawn log is missing a required
final artifact.

What it deliberately does NOT do: solve, render, read the parent source model, read any
stale model status field, infer status from PNG filenames, or fabricate artifacts for
covered/blocked logs. Status / provenance / coverage / blocker / warning fields are
carried through unchanged — publishing is an artifact step, not a placement step.

CLI:
    python -m truelinev2.contracts.redline_manifest_publisher \
        --manifest <in.json> --source-root <dir> --publish-root <dir> --run-label <id>

Programmatic (tests pass an explicit artifact map of {manifest_path: source_file}):
    from truelinev2.contracts.redline_manifest_publisher import publish_manifest
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

CONTRACTS_DIR = Path(__file__).resolve().parent
DEFAULT_SCHEMA_PATH = CONTRACTS_DIR / "redline_manifest.schema.json"
FINAL_KIND = "FINAL_REDLINE_PNG"
_CHUNK = 1024 * 256


class ManifestValidationError(ValueError):
    """Input or output manifest failed schema / reconciliation validation."""


class MissingArtifactError(FileNotFoundError):
    """A drawn log requires a final redline artifact that was not found."""


class ContractViolationError(ValueError):
    """A non-drawn (covered/blocked) log carried artifacts — they must not be faked."""


# --------------------------------------------------------------------------- #
# Dependency-free JSON-Schema validator (same subset the schema uses).
# --------------------------------------------------------------------------- #
def _type_ok(inst, t):
    if t == "object":
        return isinstance(inst, dict)
    if t == "array":
        return isinstance(inst, list)
    if t == "string":
        return isinstance(inst, str)
    if t == "integer":
        return isinstance(inst, int) and not isinstance(inst, bool)
    if t == "number":
        return isinstance(inst, (int, float)) and not isinstance(inst, bool)
    if t == "boolean":
        return isinstance(inst, bool)
    if t == "null":
        return inst is None
    raise AssertionError("schema uses unsupported type %r" % (t,))


def _walk(inst, schema, path, errors):
    if "const" in schema and inst != schema["const"]:
        errors.append("%s: expected const %r, got %r" % (path, schema["const"], inst))
    if "enum" in schema and inst not in schema["enum"]:
        errors.append("%s: %r not in enum %r" % (path, inst, schema["enum"]))
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_type_ok(inst, t) for t in types):
            errors.append("%s: %r is not of type %r" % (path, inst, types))
            return
    if isinstance(inst, dict):
        props = schema.get("properties", {})
        for req in schema.get("required", []):
            if req not in inst:
                errors.append("%s: missing required property %r" % (path, req))
        if schema.get("additionalProperties") is False:
            for key in inst:
                if key not in props:
                    errors.append("%s: additional property %r not allowed" % (path, key))
        for key, subschema in props.items():
            if key in inst:
                _walk(inst[key], subschema, "%s/%s" % (path, key), errors)
    if isinstance(inst, list):
        if "minItems" in schema and len(inst) < schema["minItems"]:
            errors.append("%s: %d items < minItems %d" % (path, len(inst), schema["minItems"]))
        item_schema = schema.get("items")
        if item_schema is not None:
            for i, el in enumerate(inst):
                _walk(el, item_schema, "%s[%d]" % (path, i), errors)
    if "minimum" in schema and isinstance(inst, (int, float)) and not isinstance(inst, bool):
        if inst < schema["minimum"]:
            errors.append("%s: %r < minimum %r" % (path, inst, schema["minimum"]))


def validate_manifest(manifest, schema):
    """Return a list of schema violations ([] when valid)."""
    errors = []
    _walk(manifest, schema, "$", errors)
    return errors


GEOMETRY_BASIS_ADOPTED = "OBSERVER_BACKBONE_HUMAN_ADOPTED"
GEOMETRY_BASIS_MANUAL = "HUMAN_CLICKED_POLYLINE"


def reconciliation_errors(manifest):
    """Return semantic accounting errors the schema cannot express ([] when consistent)."""
    errors = []
    logs = manifest.get("logs", [])
    status_tally = {}
    prov_tally = {}
    drawn = covered = blocked = 0
    for lg in logs:
        status_tally[lg["status"]] = status_tally.get(lg["status"], 0) + 1
        prov_tally[lg["provenance"]] = prov_tally.get(lg["provenance"], 0) + 1
        drawn += 1 if lg["drawn"] else 0
        covered += 1 if lg["covered"] else 0
        blocked += 1 if lg["blocked"] else 0
        if sum((bool(lg["drawn"]), bool(lg["covered"]), bool(lg["blocked"]))) != 1:
            errors.append("%s: exactly one of drawn/covered/blocked must be true" % lg["log_id"])
        # Mission 8: a log's EXPLICIT-CONFIRMATION provenance block must agree with its own geometry_basis,
        # and route_adoption/manual_route are MUTUALLY EXCLUSIVE on the same log -- the schema (additive
        # optional keys, additionalProperties:false) cannot express either rule, so both are checked here.
        has_adoption = lg.get("route_adoption") is not None
        has_manual = lg.get("manual_route") is not None
        basis = lg.get("geometry_basis")
        if has_adoption and has_manual:
            errors.append("%s: carries BOTH route_adoption and manual_route (mutually exclusive provenance)"
                         % lg["log_id"])
        if has_adoption and basis != GEOMETRY_BASIS_ADOPTED:
            errors.append("%s: carries route_adoption but geometry_basis=%r (expected %r)"
                         % (lg["log_id"], basis, GEOMETRY_BASIS_ADOPTED))
        if has_manual and basis != GEOMETRY_BASIS_MANUAL:
            errors.append("%s: carries manual_route but geometry_basis=%r (expected %r)"
                         % (lg["log_id"], basis, GEOMETRY_BASIS_MANUAL))
        if basis == GEOMETRY_BASIS_ADOPTED and not has_adoption:
            errors.append("%s: geometry_basis=%s but no route_adoption block" % (lg["log_id"], basis))
        if basis == GEOMETRY_BASIS_MANUAL and not has_manual:
            errors.append("%s: geometry_basis=%s but no manual_route block" % (lg["log_id"], basis))
    # Compare per key with a 0 default so explicit zero-count buckets (e.g. a project with no
    # covered logs) are NOT falsely rejected; real mismatches (incl. extra declared keys) still fail.
    declared_status = manifest.get("status_counts") or {}
    if any(status_tally.get(k, 0) != declared_status.get(k, 0)
           for k in set(status_tally) | set(declared_status)):
        errors.append("status_counts %r != per-log tally %r" % (declared_status, status_tally))
    declared_prov = manifest.get("provenance_counts") or {}
    if any(prov_tally.get(k, 0) != declared_prov.get(k, 0)
           for k in set(prov_tally) | set(declared_prov)):
        errors.append("provenance_counts %r != per-log tally %r" % (declared_prov, prov_tally))
    s = manifest.get("summary", {})
    if [s.get("total_logs"), s.get("drawn_count"), s.get("covered_count"), s.get("blocked_count")] != \
            [len(logs), drawn, covered, blocked]:
        errors.append("summary does not reconcile with per-log counts")
    return errors


def load_schema(schema_path=None):
    path = Path(schema_path) if schema_path else DEFAULT_SCHEMA_PATH
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Publishing
# --------------------------------------------------------------------------- #
def _sha256_and_size(p):
    h = hashlib.sha256()
    size = 0
    with open(p, "rb") as fh:
        while True:
            chunk = fh.read(_CHUNK)
            if not chunk:
                break
            size += len(chunk)
            h.update(chunk)
    return h.hexdigest(), size


def _resolve_source(artifact, source_root, artifact_map):
    """Locate the real source file for an artifact record.

    Resolution order (first existing wins):
      1. explicit artifact_map keyed by the manifest artifact path,
      2. <source_root>/<artifact path>,
      3. <source_root>/<basename of artifact path>.
    Returns (path, tried_list). path is None if nothing exists.
    """
    art_path = artifact["path"]
    tried = []
    if artifact_map and art_path in artifact_map:
        cand = Path(artifact_map[art_path])
        tried.append(str(cand))
        if cand.is_file():
            return cand, tried
    if source_root is not None:
        root = Path(source_root)
        for cand in (root / art_path, root / Path(art_path).name):
            tried.append(str(cand))
            if cand.is_file():
                return cand, tried
    return None, tried


def publish_manifest(manifest_path, source_artifact_root, publish_root, run_label,
                     *, artifact_map=None, schema_path=None):
    """Publish final redline artifacts and emit a real manifest.

    Returns {"manifest", "manifest_path", "publish_dir", "published_count"}.
    Raises ManifestValidationError / MissingArtifactError / ContractViolationError.
    """
    if not run_label or not str(run_label).strip():
        raise ValueError("run_label is required and must be non-empty")

    schema = load_schema(schema_path)
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))

    in_errs = validate_manifest(manifest, schema) + reconciliation_errors(manifest)
    if in_errs:
        raise ManifestValidationError("input manifest invalid:\n  " + "\n  ".join(in_errs))

    publish_dir = Path(publish_root) / str(run_label)
    artifacts_root = publish_dir / "artifacts"
    published_count = 0

    for log in manifest["logs"]:
        log_id = log["log_id"]
        arts = log.get("artifacts", [])

        if not log["drawn"]:
            # Covered/blocked logs must never carry or fake a final artifact.
            if arts:
                raise ContractViolationError(
                    "%s is %s (not drawn) but lists %d artifact(s); covered/blocked logs "
                    "must not have artifacts" % (log_id, log["status"], len(arts)))
            continue

        # Drawn logs require at least one final redline artifact record.
        finals = [a for a in arts if a["kind"] == FINAL_KIND]
        if not finals:
            raise MissingArtifactError(
                "drawn log %s has no %s artifact record to publish" % (log_id, FINAL_KIND))

        used = {}
        dest_dir = artifacts_root / log_id
        for art in arts:
            src, tried = _resolve_source(art, source_artifact_root, artifact_map)
            if src is None:
                raise MissingArtifactError(
                    "missing final artifact for drawn log %s (manifest path %r); tried: %s"
                    % (log_id, art["path"], ", ".join(tried) or "<none>"))

            name = Path(art["path"]).name
            if name in used:  # disambiguate same-basename collisions within a log
                used[name] += 1
                stem, dot, ext = name.partition(".")
                name = "%s__%d%s%s" % (stem, used[name], dot, ext)
            else:
                used[name] = 0

            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / name
            shutil.copyfile(src, dest)
            digest, size = _sha256_and_size(dest)

            art["path"] = dest.relative_to(publish_dir).as_posix()
            art["sha256"] = digest
            art["bytes"] = size
            art["published"] = True
            art["example_placeholder"] = False
            published_count += 1

    # Top-level: this is now a published manifest, not a mock.
    manifest["mock_example"] = False
    manifest["disclaimer"] = (
        "Published redline manifest (run label '%s'). %d final redline artifact(s) copied "
        "from '%s' into '%s' with sha256 checksums; mock_example=false. Status / provenance "
        "/ coverage / blocker / warning fields are carried through unchanged from the input "
        "manifest (publishing is an artifact step, not a placement step)."
        % (run_label, published_count, source_artifact_root, publish_dir)
    )
    manifest["engine"]["generated_from"] = "redline_manifest_publisher run '%s'" % run_label

    out_errs = validate_manifest(manifest, schema) + reconciliation_errors(manifest)
    if out_errs:
        raise ManifestValidationError("published manifest invalid:\n  " + "\n  ".join(out_errs))

    publish_dir.mkdir(parents=True, exist_ok=True)
    out_path = publish_dir / "redline_manifest.json"
    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    return {
        "manifest": manifest,
        "manifest_path": str(out_path),
        "publish_dir": str(publish_dir),
        "published_count": published_count,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Publish redline artifacts and emit a real manifest.")
    ap.add_argument("--manifest", required=True, help="input manifest JSON path")
    ap.add_argument("--source-root", required=True, help="root directory holding the source final artifacts")
    ap.add_argument("--publish-root", required=True, help="root directory to publish into")
    ap.add_argument("--run-label", required=True, help="deterministic run id / label")
    ap.add_argument("--schema", default=None, help="schema path (defaults to the bundled contract schema)")
    args = ap.parse_args(argv)
    result = publish_manifest(
        args.manifest, args.source_root, args.publish_root, args.run_label, schema_path=args.schema)
    print("published %d artifact(s) -> %s" % (result["published_count"], result["manifest_path"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
