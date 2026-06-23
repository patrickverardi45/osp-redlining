"""Phase 9 — binary KMZ writer + structural validator tests.

Proves the KMZ MACHINERY is real and Google-Earth-loadable WITHOUT faking coordinates:
  * build_kmz_bytes packs verified KML into a valid .kmz (zip{doc.kml}); deterministic; round-trips.
  * validate_kmz_bytes structurally validates (zip + KML parse + Placemarks + WGS84 coordinate ranges) and
    rejects junk / out-of-range coordinates.
  * On REAL WGS84 coordinates from the shipped design KMZ (extract.kmz.read_kmz), the writer produces a
    structurally-valid KMZ — the honest basis for the 'Google Earth can load this' claim. (Skips if the
    design KMZ is not present in this checkout.)

The product redline path itself stays honest elsewhere: a pixel-only redline manifest is BLOCKED
(UNSUPPORTED_PIXEL_ONLY) by evaluate_export and never reaches this writer.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from truelinev2.contracts.kmz_export import (
    KMZ_KML_MEMBER, build_kml, build_kmz_bytes, validate_kmz_bytes,
)

_DESIGN_KMZ = Path("data/uploads/Brenham, TX - Phase 5_Design Team.kmz")


def _feature(feature_id, coords):
    """A build_kml feature carrying a verified geospatial LineString (lon,lat pairs, EPSG:4326)."""
    return {"feature_id": feature_id, "source_manifest_id": "m-1", "source_artifact_bundle_id": "b-1",
            "source_log_id": feature_id, "status": "DRAWN_REDLINE", "length_ft": 100.0,
            "geometry": {"crs": "EPSG:4326", "datum": "WGS84", "units": "degrees", "kind": "LineString",
                         "coordinates": [list(c) for c in coords], "source": "FIELD_GPS",
                         "confidence": "HIGH"},
            "blockers": [], "warnings": []}


def _kml(coords):
    return build_kml([_feature("feat-1", coords)], source_manifest_id="m-1",
                     source_artifact_bundle_id="b-1")


def test_build_kmz_is_valid_zip_with_doc_kml():
    kml = _kml([(-96.388252, 30.152542), (-96.387000, 30.153000)])
    data = build_kmz_bytes(kml)
    zf = zipfile.ZipFile(__import__("io").BytesIO(data))
    assert KMZ_KML_MEMBER in zf.namelist()
    assert zf.read(KMZ_KML_MEMBER).decode("utf-8").startswith("<?xml")


def test_validate_kmz_passes_on_real_range_coords():
    data = build_kmz_bytes(_kml([(-96.388252, 30.152542), (-96.387000, 30.153000)]))
    v = validate_kmz_bytes(data)
    assert v["valid"] is True and not v["errors"]
    assert v["kml_member"] == KMZ_KML_MEMBER
    assert v["placemark_count"] == 1
    assert "LineString" in v["geometry_kinds"]
    assert v["coordinate_count"] == 2


def test_build_kmz_is_deterministic():
    kml = _kml([(-96.388252, 30.152542), (-96.387000, 30.153000)])
    assert build_kmz_bytes(kml) == build_kmz_bytes(kml)            # byte-stable (fixed member + 1980 date)


def test_validate_rejects_non_zip():
    v = validate_kmz_bytes(b"not a zip at all")
    assert v["valid"] is False and "not a valid zip archive" in v["errors"]


def test_validate_rejects_out_of_range_coords():
    # 999,999 is not a valid lon/lat — the validator must catch it (no silent pass).
    data = build_kmz_bytes(_kml([(999.0, 999.0), (-96.387, 30.153)]))
    v = validate_kmz_bytes(data)
    assert v["valid"] is False
    assert any("out of WGS84 range" in e for e in v["errors"])


def test_build_kmz_rejects_empty_kml():
    with pytest.raises(ValueError):
        build_kmz_bytes("")


@pytest.mark.skipif(not _DESIGN_KMZ.is_file(), reason="design KMZ not present in this checkout")
def test_writer_is_valid_on_real_design_kmz_coordinates():
    """REAL WGS84 coordinates from the shipped design KMZ -> a structurally valid KMZ. This is the honest
    basis for the Google-Earth-loadable claim (real coordinates, never invented)."""
    from truelinev2.extract.kmz import BRENHAM_KMZ_DIALECT, read_kmz
    model = read_kmz(str(_DESIGN_KMZ), BRENHAM_KMZ_DIALECT)
    route = next((r for r in model.routes if len(r.vertices) >= 2), None)
    assert route is not None, "design KMZ has at least one route polyline"
    data = build_kmz_bytes(_kml(list(route.vertices)))
    v = validate_kmz_bytes(data)
    assert v["valid"] is True and not v["errors"]
    assert v["coordinate_count"] == len(route.vertices)
    assert "LineString" in v["geometry_kinds"]
