# F7f Known Source-Side Anomalies — Rationale

## Purpose

This directory's `f7f_known_anomalies.json` declares per-fixture source-side
quirks that are documented-pre-existing and NOT TrueLine fidelity regressions.
The F7f harness (`backend/tests/test_f7f_export_fidelity.py`) reads this file
and treats listed items as suppressed (PASS) unless:

- A NEW anomaly appears beyond the documented set → harness emits **FAIL**.
- A previously-listed anomaly is resolved at the source → harness emits **WARN**
  prompting the operator to remove the now-resolved entry from this file.

This avoids forever-WARN noise on pre-existing upstream issues while preserving
regression-detection signal.

## Schema (`f7f-known-anomalies-1`)

```jsonc
{
  "schema_version": "f7f-known-anomalies-1",
  "generated_for": "...",                   // free-text provenance label
  "fixtures": {
    "<fixture_filename>.kmz": {
      "source_unresolvable_hrefs": [        // exact href strings as emitted in source KML
        "files/i20_01.png"
      ],
      "rationale": "Required..."            // REQUIRED — loader fails if absent or empty
    }
  }
}
```

The `rationale` field is **required** for every fixture entry. The harness's
loader (`_load_known_anomalies` in `test_f7f_export_fidelity.py`) raises a
`ValueError` if any entry omits or empty-strings it. This keeps the
known-anomalies registry from drifting into a silent suppression list.

## Current entries

### `brenham_phase5_source_truth.kmz` — 5 unresolved icon hrefs

| Source `<href>` value | Source archive contains instead |
|---|---|
| `files/i20_01.png` | `files/i20_01_2.png` |
| `files/i46.png` | `files/i46_6_0.png`, `files/i46_8_0.png` |
| `files/i47.png` | `files/i47_12.png` |
| `files/i51.png` | `files/i51_18.png` |
| `files/i61.png` | `files/i61_22.png` |

**Why pre-existing:** the upstream source-authoring tool emits bare filenames
in the KML (`<href>files/iNN.png</href>`) but ZIPs only the suffixed variants
into the archive. This produces yellow-pushpin renderings in Google Earth for
those 5 features in the *source itself*, before any TrueLine processing.

**Why not a TrueLine regression:** TrueLine cannot synthesize icons the source
omits. The fix belongs upstream in the source-authoring tool's href-emission
logic. F7f's gates would never legitimately PASS on these unless the upstream
tool ships a correction.

**Update policy:** if any of these hrefs later resolve in the source archive
(e.g., a future Brenham re-export from a fixed authoring tool), remove the
resolved entries from `f7f_known_anomalies.json`. The harness will WARN on
the next run that known anomalies have been fixed, prompting the update.

## Adding entries for new fixtures

When a new fixture (e.g., the v2 minimal synthetic, edge-cases adversarial,
or any future per-firm engineering KMZ) is added, append a new entry to
`fixtures` in the JSON file. Always include:

- The exact unresolvable href list (string-match against KML `<href>` emission).
- A rationale explaining why it's acceptable. For an adversarial fixture this
  rationale may state "INTENTIONAL — fixture deliberately breaks G3 to verify
  the harness detects it" — that is itself a valid rationale.

## What this file is NOT

- ❌ A general suppression list for any failing test.
- ❌ A place to silence TrueLine emitter bugs (those need code fixes).
- ❌ A backdoor to lower the harness's standards.

If you find yourself wanting to add an entry to silence a failure, ask:
**is the failure upstream-of-TrueLine source-quality drift, or is it a
TrueLine regression?** Only the former belongs here.

## v2 update — propagation to export side

F7f v2 (2026-05-22) ported the production exporter's icon-href preservation
and asset-embedding behavior into the Python harness emitter (mirroring
`RedlineMap.tsx:2781-2792` per-feature `<Style><IconStyle><Icon><href>`
emission + `RedlineMap.tsx:3154-3162` source asset bytes embedding).
Consequence: documented source-side anomalies now **propagate to the
export side at the same rate**, exactly as they do in production.

Specifically for `brenham_phase5_source_truth.kmz`:
- Of the 5 documented unresolvable source hrefs, only **1** (`files/i46.png`)
  is actually referenced by a placemark via the source's `<Style>` chain.
  The other 4 (`files/i20_01.png`, `files/i47.png`, `files/i51.png`,
  `files/i61.png`) are declared in source `<Style>` blocks but never
  referenced by any `<Placemark>` `<styleUrl>` — dead style declarations.
  The harness's v2 emitter only emits per-feature styles for actually-used
  icon_hrefs, so only the 1 used-and-broken href propagates to the export.

Gate behavior under v2:
- `G3_icon_resolution_source` — unchanged delta-based check against the
  documented known-anomalies set. Brenham: PASS (5/5 documented).
- `G3_icon_resolution_export` — v2 delta-based against the **source's**
  unresolvable set. PASS if `export_unresolvable ⊆ source_unresolvable`
  (faithful propagation, not regression). FAIL if NEW unresolvable hrefs
  appear in export beyond source's set (catches port regressions or
  asset-embedding bugs). Brenham: PASS (1 unresolvable in export, also
  unresolvable in source).

This means the v2 harness can stop relying on visual-only Google Earth
validation for the icon-href fidelity axis. Production behavior is now
mirrored by the harness and structurally verified per run.
