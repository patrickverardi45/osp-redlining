# QA fixtures

These are synthetic, committed-safe placeholder files used by the
TrueLine QA harness. They contain **no real customer data** and are
re-generatable from source via `_generators/build_fixtures.py`.

## Files

| File | Bytes | What it is | Used by |
|---|---|---|---|
| `sample-design.kmz` | ~550 | KMZ zip containing a single `doc.kml` with one Folder→LineString route and one Folder→Point placemark. Fake coordinates near (0, 0). Folders + placemarks are named so KMZ semantic parsing has something to read. | `tests/workflows/uploads.spec.ts` (KMZ upload test) |
| `sample-engineering-plan.pdf` | ~600 | Hand-crafted single-page PDF 1.4 with the text "QA Engineering Plan Fixture". Valid xref, valid `%%EOF` trailer. | `tests/workflows/uploads.spec.ts` (engineering plan upload test) |
| `sample-station-photo.jpg` | ~280 | 16×16 RGB mid-grey JPEG. Encoded by Pillow so all JPEG markers, quantization, and Huffman tables are guaranteed valid. No EXIF. | `tests/workflows/uploads.spec.ts` (station photo upload test) |
| `sample-bore-log.csv` | ~100 | Five rows of synthetic bore-log data in the `station,depth,boc` schema the backend expects (see `backend/app/api/bore_rows.py`). Station values are normalized `NN+NN`. | Reserved for future bore-log upload test. |

## Regenerate

```powershell
cd C:\Nova\projects\TrueLine\TrueLine_Beta\qa\fixtures\_generators
python build_fixtures.py
```

Requires Python 3.10+ and Pillow. (Pillow ships in our standard Python
env; if it is missing in a stripped-down environment, install it with
`pip install Pillow`.)

## What these are NOT

- **Not** acceptance-test inputs. The QA harness only asserts that the
  upload endpoints respond with well-formed JSON (never HTML, never 5xx).
  It does not assert that the backend's downstream parser accepts the
  file as a real plan/photo/route.
- **Not** representative of real telecom OSP designs. Treat them as
  shape-only stand-ins.
- **Not** committed if you ignore them via local gitignore overrides —
  the harness will then skip the upload tests with `fixture-missing`,
  which is fine for read-only runs.

## Mutation-gate reminder

Even with all four fixtures present, the upload workflow tests still
skip unless `QA_ALLOW_MUTATION=true` is set in the environment. This is
deliberate — uploads against production must be opt-in.
