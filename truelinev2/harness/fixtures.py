"""Cold-package fixture model + on-disk loader.

A fixture is one arbitrary package + its expected decision. It lives in a gitignored directory:

    <fixtures_root>/<fixture_id>/
        fixture.json          # id, description, uploads, bore_rows, expected {status, blockers}
        uploads/<filename>    # the real input bytes (plan PDF, bore-log xlsx, optional kmz)

Everything is name-free: ids are generic (pkg-001-...), descriptions are domain-generic, and no real
customer/project/location name appears. The loader performs no engine work — it only reads the spec.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# The four product upload kinds (mirrors upload_pipeline.ACCEPTED_KINDS; the harness asserts against the
# contract at runtime rather than hardcoding a divergent copy).
UPLOAD_KINDS = ("PLAN_PDF", "BORE_LOG", "GIS_ROUTE", "PHOTO")

# Expected decision statuses the harness can score against (mirrors product_workflow PATH_* outcomes).
STATUS_RECOGNIZED = "RECOGNIZED_DETERMINISTIC"
STATUS_REVIEW = "UPLOADED_REVIEW"
STATUS_AUTO = "UPLOADED_AUTO"
STATUS_ABSTAIN = "ABSTAIN"
EXPECTED_STATUSES = (STATUS_RECOGNIZED, STATUS_REVIEW, STATUS_AUTO, STATUS_ABSTAIN)


@dataclass(frozen=True)
class UploadSpec:
    kind: str
    filename: str
    path: Path

    def read_bytes(self) -> bytes:
        return self.path.read_bytes()


@dataclass(frozen=True)
class Fixture:
    fixture_id: str            # generic id, e.g. "pkg-001-tight-red-run"
    description: str           # domain-generic, no real names
    uploads: tuple             # tuple[UploadSpec, ...]
    bore_rows: tuple           # tuple[dict, ...]; each {row_id, raw, normalized}
    expected_status: str       # one of EXPECTED_STATUSES
    expected_blockers: tuple   # tuple[str, ...]; expected named blocker codes (empty for REVIEW/AUTO)

    @property
    def bore_log_upload(self):
        for u in self.uploads:
            if u.kind == "BORE_LOG":
                return u
        return None


def _coerce_fixture(fixture_dir: Path, spec: dict) -> Fixture:
    fixture_id = spec["fixture_id"]
    uploads_dir = fixture_dir / "uploads"
    uploads = []
    for u in spec.get("uploads", []):
        kind = u["kind"]
        if kind not in UPLOAD_KINDS:
            raise ValueError("fixture %s: unknown upload kind %r" % (fixture_id, kind))
        path = uploads_dir / u["filename"]
        if not path.is_file():
            raise FileNotFoundError("fixture %s: missing upload bytes %s" % (fixture_id, path))
        uploads.append(UploadSpec(kind=kind, filename=u["filename"], path=path))
    expected = spec.get("expected", {})
    status = expected.get("status")
    if status not in EXPECTED_STATUSES:
        raise ValueError("fixture %s: expected.status must be one of %r (got %r)"
                         % (fixture_id, EXPECTED_STATUSES, status))
    rows = tuple(spec.get("bore_rows", []))
    return Fixture(
        fixture_id=fixture_id,
        description=spec.get("description", ""),
        uploads=tuple(uploads),
        bore_rows=rows,
        expected_status=status,
        expected_blockers=tuple(expected.get("blockers", []) or []),
    )


def load_fixture(fixture_dir) -> Fixture:
    """Load one fixture directory (fixture.json + uploads/)."""
    fixture_dir = Path(fixture_dir)
    spec_path = fixture_dir / "fixture.json"
    if not spec_path.is_file():
        raise FileNotFoundError("no fixture.json in %s" % fixture_dir)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    return _coerce_fixture(fixture_dir, spec)


def load_fixtures(fixtures_root) -> list:
    """Load every fixture directory under a root, sorted by id (stable order for the matrix)."""
    root = Path(fixtures_root)
    out = []
    if not root.is_dir():
        return out
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        if (child / "fixture.json").is_file():
            out.append(load_fixture(child))
    return out
