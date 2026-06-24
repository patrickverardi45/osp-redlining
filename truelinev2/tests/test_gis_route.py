"""Phase 11 — generic GIS route reader tests (dialect-free; real WGS84 only; honest empty states).

Parses uploaded KMZ/KML into real LineString/Point/Polygon coords + bbox; reads ONLY the stored GIS_ROUTE
upload; invents nothing; reports NAMED states for no-upload / missing / unparseable / no-coordinates.
Self-contained + name-free.
"""
from __future__ import annotations

import io
import zipfile

from truelinev2.contracts.customer_project import create_customer_project
from truelinev2.contracts.processing_job import create_job
from truelinev2.contracts.upload_pipeline import accept_upload
from truelinev2.contracts.gis_route import (
    GIS_ROUTE_FILE_MISSING, GIS_ROUTE_NOT_PARSEABLE, NO_COORDINATES_FOUND, NO_GIS_ROUTE_UPLOADED,
    load_job_gis_route, parse_gis_route,
)

AT, BY, CP, JOB = "2026-06-24T00:00:00Z", "op-1", "cp-0001", "job-0001"

_KML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
    '<Placemark><name>Main Route</name>'
    '<LineString><coordinates>-96.10,30.10,0 -96.20,30.20,0 -96.30,30.15,0</coordinates></LineString>'
    '</Placemark>'
    '<Placemark><name>Vault</name>'
    '<Point><coordinates>-96.15,30.12,0</coordinates></Point>'
    '</Placemark>'
    '</Document></kml>'
).encode("utf-8")


def _kmz(kml: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("doc.kml", kml)
    return buf.getvalue()


def test_parse_kml_linestring_and_point():
    r = parse_gis_route(_KML)
    assert r["present"] is True and r["reason"] is None
    assert r["feature_count"] == 2
    types = sorted(f["type"] for f in r["features"])
    assert types == ["LineString", "Point"]
    line = next(f for f in r["features"] if f["type"] == "LineString")
    assert line["name"] == "Main Route"
    assert line["coordinates"][0] == [-96.10, 30.10]      # [lon, lat], altitude dropped
    assert len(line["coordinates"]) == 3
    # bbox = [min_lon, min_lat, max_lon, max_lat] over all coords
    assert r["bbox"] == [-96.30, 30.10, -96.10, 30.20]


def test_parse_kmz_zip_member():
    r = parse_gis_route(_kmz(_KML))
    assert r["present"] is True and r["feature_count"] == 2
    assert r["bbox"] == [-96.30, 30.10, -96.10, 30.20]


def test_parse_drops_out_of_range_and_handles_no_coords():
    bad = (
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark>'
        '<LineString><coordinates>999,999 -96.5,30.5</coordinates></LineString>'
        '</Placemark></Document></kml>'
    ).encode("utf-8")
    r = parse_gis_route(bad)
    assert r["feature_count"] == 1 and r["features"][0]["coordinates"] == [[-96.5, 30.5]]   # 999,999 dropped

    empty = '<kml xmlns="http://www.opengis.net/kml/2.2"><Document></Document></kml>'.encode("utf-8")
    r2 = parse_gis_route(empty)
    assert r2["present"] is True and r2["reason"] == NO_COORDINATES_FOUND and r2["features"] == []


def test_load_job_gis_route_present(tmp_path):
    create_customer_project(tmp_path, CP, "Label", AT)
    create_job(tmp_path, CP, JOB, AT, BY)
    accept_upload(tmp_path, CP, JOB, kind="GIS_ROUTE", filename="route.kmz", content=_kmz(_KML), stored_at=AT)
    r = load_job_gis_route(tmp_path, CP, JOB)
    assert r["present"] is True and r["feature_count"] == 2
    assert r["upload"]["kind"] == "GIS_ROUTE" and r["upload"]["filename"] == "route.kmz"
    assert r["bbox"] == [-96.30, 30.10, -96.10, 30.20]


def test_load_job_gis_route_absent_is_honest(tmp_path):
    create_customer_project(tmp_path, CP, "Label", AT)
    create_job(tmp_path, CP, JOB, AT, BY)
    # only a PLAN_PDF, no GIS_ROUTE
    accept_upload(tmp_path, CP, JOB, kind="PLAN_PDF", filename="plan.pdf", content=b"%PDF-1.7\n", stored_at=AT)
    r = load_job_gis_route(tmp_path, CP, JOB)
    assert r["present"] is False and r["reason"] == NO_GIS_ROUTE_UPLOADED
    assert r["features"] == [] and r["bbox"] is None and r["upload"] is None


def test_load_job_gis_route_unparseable_is_honest_not_raised(tmp_path):
    create_customer_project(tmp_path, CP, "Label", AT)
    create_job(tmp_path, CP, JOB, AT, BY)
    accept_upload(tmp_path, CP, JOB, kind="GIS_ROUTE", filename="broken.kml", content=b"<<<not xml>>>", stored_at=AT)
    r = load_job_gis_route(tmp_path, CP, JOB)
    assert r["present"] is True and r["reason"] == GIS_ROUTE_NOT_PARSEABLE   # honest, no exception/500
    assert r["features"] == []
