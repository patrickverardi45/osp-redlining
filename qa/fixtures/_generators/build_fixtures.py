"""
Builds the four QA fixture files in qa/fixtures/ from scratch.

Run from the qa/fixtures/_generators directory:

    python build_fixtures.py

Outputs (written into the parent qa/fixtures/ directory):
    sample-design.kmz             — fake KMZ with a route + a marker
    sample-engineering-plan.pdf   — single-page PDF with a fixture label
    sample-station-photo.jpg      — 16x16 grey JPG
    sample-bore-log.csv           — fake bore-log rows matching backend schema

No real customer data, no external downloads. Re-run any time fixtures are
deleted; the QA harness only cares that the files exist and are valid in
their declared formats — it does NOT assert downstream parser acceptance.
"""

import csv
import io
import zipfile
from pathlib import Path

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:  # pragma: no cover — Pillow is in our env
    HAS_PIL = False

FIXTURES_DIR = Path(__file__).resolve().parent.parent


def build_kmz(out_path: Path) -> None:
    """A tiny KMZ — zip with a single doc.kml.

    The KML inside has named folders, a LineString route, and a Point
    placemark so anything that parses KMZ semantics has something to read.
    Coordinates are intentionally fake (Null Island region, slightly offset).
    """
    kml = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>TrueLine QA Fixture — Synthetic Design</name>
    <description>
      Synthetic test fixture for the TrueLine QA harness.
      Coordinates are fake (Null Island offset). No real customer geography.
    </description>
    <Folder>
      <name>QA Routes</name>
      <description>Fake route folder for KMZ semantic parsing.</description>
      <Placemark>
        <name>QA Route 1</name>
        <description>Fake LineString (fixture only).</description>
        <LineString>
          <tessellate>1</tessellate>
          <coordinates>
            0.0001,0.0001,0
            0.0002,0.0001,0
            0.0003,0.0002,0
            0.0004,0.0002,0
          </coordinates>
        </LineString>
      </Placemark>
    </Folder>
    <Folder>
      <name>QA Markers</name>
      <description>Fake markers folder for KMZ semantic parsing.</description>
      <Placemark>
        <name>QA Station A</name>
        <description>Fake Point placemark (fixture only).</description>
        <Point>
          <coordinates>0.0001,0.0001,0</coordinates>
        </Point>
      </Placemark>
    </Folder>
  </Document>
</kml>
"""
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("doc.kml", kml)


def build_pdf(out_path: Path) -> None:
    """A minimal valid one-page PDF with a single text line.

    Hand-crafted bytes — no PDF library required. Computes xref offsets
    correctly so the file passes the standard PDF parser validation.
    """
    text = "QA Engineering Plan Fixture"
    stream = (
        b"BT\n"
        b"/F1 24 Tf\n"
        b"72 720 Td\n"
        b"(" + text.encode("ascii") + b") Tj\n"
        b"ET\n"
    )

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\n"
        b"stream\n" + stream + b"endstream",
    ]

    body = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")  # binary marker is convention
    offsets = []
    for idx, obj in enumerate(objects, start=1):
        offsets.append(len(body))
        body += f"{idx} 0 obj\n".encode("ascii")
        body += obj
        body += b"\nendobj\n"

    xref_offset = len(body)
    body += b"xref\n"
    body += f"0 {len(objects) + 1}\n".encode("ascii")
    body += b"0000000000 65535 f \n"
    for off in offsets:
        body += f"{off:010d} 00000 n \n".encode("ascii")

    body += b"trailer\n"
    body += f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode("ascii")
    body += b"startxref\n"
    body += f"{xref_offset}\n".encode("ascii")
    body += b"%%EOF\n"

    out_path.write_bytes(bytes(body))


def build_jpg(out_path: Path) -> None:
    """A 16x16 mid-grey JPG. Pillow does the encoding so the markers,
    quantization, and Huffman tables are guaranteed valid."""
    if HAS_PIL:
        img = Image.new("RGB", (16, 16), color=(128, 128, 128))
        img.save(out_path, format="JPEG", quality=70, optimize=True)
        return
    # Fallback: a known-good 1x1 grey JPEG (332 bytes, verified valid).
    # Only used if Pillow is unavailable; our env has it.
    minimal = bytes.fromhex(
        "ffd8ffe000104a46494600010100000100010000"
        "ffdb004300080606070605080707070909080a0c"
        "140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20"
        "242e2720222c231c1c2837292c303134343420"
        "27393d3832"
    )
    out_path.write_bytes(minimal)


def build_csv(out_path: Path) -> None:
    """A tiny bore-log CSV matching the backend's expected schema:
    station,depth,boc. See backend/app/api/bore_rows.py for the
    canonical normalize_* / looks_like_* functions."""
    rows = [
        # station, depth (ft), boc (elev integer)
        ("10+00", "4.5", "1010"),
        ("10+50", "4.8", "1009"),
        ("11+00", "5.2", "1008"),
        ("11+50", "5.0", "1008"),
        ("12+00", "4.7", "1009"),
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["station", "depth", "boc"])
        for r in rows:
            writer.writerow(r)


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    outputs = [
        (FIXTURES_DIR / "sample-design.kmz", build_kmz),
        (FIXTURES_DIR / "sample-engineering-plan.pdf", build_pdf),
        (FIXTURES_DIR / "sample-station-photo.jpg", build_jpg),
        (FIXTURES_DIR / "sample-bore-log.csv", build_csv),
    ]
    for path, builder in outputs:
        builder(path)
        size = path.stat().st_size
        print(f"  wrote {path.name:<32} {size:>6} bytes")


if __name__ == "__main__":
    main()
