# Target #43 — ambiguity-resolution input seam for blocked bores (default-OFF, read-only)

**Mission:** stop mining the same corpus. Build the default-OFF data seam that lets the engine consume
an **office-provided start structure** for an unresolved bore, then deterministically place the
redline — and, since bore_log57's real start is not known, build the **schema + validator + candidate
list + integration seam** without inventing a value.

**VERDICT: seam BUILT and proven; no ground truth invented.** A pure resolver
(`resolve_placement_with_start`) consumes a per-bore override (`bore_log_id` + `route_id` +
`end_structure` + `start_structure` + notes), validates the start lies on the route, computes the
exact sub-route segment, checks length tolerance, and emits a default-OFF placement candidate or a
machine blocker. **The bore_log7 control re-derives its proven placement** (start = SPLICE LOC 46, end
= AP-163 → end_latlon `30.1591628,-96.3857298`, the known AP-163 node). For bore_log57 the candidate
enumeration shows **no mapped structure on route_465 is 413 ft from AP-157**, so the seam tells the
office exactly what to supply (an unmapped pit coordinate or a route offset) — and the resolver
**deterministically places once that one field is given** (demonstrated). Nothing invented, nothing
placed in production.

> Read-only; `scripts/` only; pure resolver; no flag wired, no Render/auth/UI, no STATE/geometry write,
> no production placement. `scripts/target43_ambiguity_resolution.py` (+ `.json`/`.out`) and the
> template `scripts/bore_ambiguity_overrides.sample.json`. Self-test `SELFTEST_OK`.

---

## 1. Input schema (per-bore ambiguity-resolution override)

```json
{
  "bore_log_id": "bore_log57",
  "route_id": "route_465",
  "end_structure":  {"type": "ap", "id": "157"},
  "start_structure": <EXACTLY ONE OF>
      {"type": "kmz_node",     "name": "<KMZ node name>"},
      {"type": "route_offset", "offset_ft": <number, measured from the END terminus>},
      {"type": "coordinate",   "lat": <f>, "lon": <f>},
  "notes": "office provenance"
}
```
Template committed at `scripts/bore_ambiguity_overrides.sample.json` (bore_log57 only; `start_structure`
is a clearly-marked PLACEHOLDER, not ground truth). **The office NAMES the start; the engine draws the
geometry** — no manual drawing.

## 2. Resolver (deterministic, validated)

`resolve_placement_with_start(...)`:
1. orient the route so the END terminus is offset 0;
2. resolve the start point coords from `start_structure` (node / offset / coordinate);
3. **validate** the start projects onto the route (≤20 ft) — else `BLOCKED:start_not_on_route`;
4. segment = route[0 .. start_offset]; `seg_len = start_offset`;
5. **validate** `|seg_len − bore_len| ≤ 10%` — else `BLOCKED:segment_len_..._outside_10pct`;
6. emit `PLACEMENT_CANDIDATE` {start_latlon, end_latlon, segment_coords} (default-OFF) or the blocker.

## 3. bore_log57 candidate enumeration (the office decision surface)

| start structure on route_465 | offset from AP-157 | segment → AP-157 | matches 413 ft? |
|---|---|---|---|
| AP-157 (Terminal Port HH) | 0 ft | 0 ft | no |
| Flower Pot | 288.7 ft | 288.7 ft | no |
| Installer HH | 690.0 ft | 690.0 ft | no |
| SPLICE LOC 45 (Splice HH) | 741.7 ft | 741.7 ft | no |

**No mapped KMZ structure on route_465 is 413 ft from AP-157.** The honest implication (not an
invention): the start is most likely an **unmapped pit at ~413 ft** from AP-157 along route_465 — so
the office must supply its `coordinate` (or a `route_offset`), or confirm a node from their records.

## 4. Resolver demonstration (mechanism only — inputs are office-supplied, not invented)

| office input (start_structure) | resolver output |
|---|---|
| `kmz_node "SPLICE LOC 45"` | **BLOCKED** — segment 741.7 ft ≠ 413 ft (start inconsistent with bore length) |
| `route_offset 288.7` (Flower Pot) | **BLOCKED** — segment 288.7 ft ≠ 413 ft |
| `route_offset 413` (the #41 open-space point) | **PLACEMENT_CANDIDATE** — start `30.159037,-96.385587` → end AP-157 `30.158195,-96.385985`, seg 414.3 ft |

This proves the seam: a *correct* start (one that yields a 413 ft segment to AP-157) places
deterministically; a *wrong-length* start is rejected, not drawn. The `route_offset 413` value is the
engine-computed open-space point from #41 and is explicitly **NOT confirmed ground truth** — it
demonstrates the mechanism and tells the office precisely where to look.

## 5. Control — bore_log7 not degraded

`start = SPLICE LOC 46, end = AP-163, route_469` → **PLACEMENT_CANDIDATE**, segment 459.2 ft (≈ bore
451 ft), `end_latlon 30.1591628,-96.3857298` = the proven AP-163 node (#14). The seam reproduces the
known-correct bore_log7 placement, confirming correct calibration.

## 6. Integration seam (default-OFF; NOT wired this session)

Mirror the shipped **Target #14** pattern (`_apply_terminal_tail_placement_override` behind
`TRUELINE_TERMINAL_TAIL_PLACEMENT`): a new default-OFF flag **`TRUELINE_AMBIGUITY_START_OVERRIDE`**
would, for bores present in the office-provided overrides JSON, call `resolve_placement_with_start`
in an **isolated post-rebuild pass** and re-render **only those bores**. Flag-OFF ⇒ byte-identical to
today. Wiring it into `backend/main.py` is the named next step and requires explicit re-authorization
(no production code changed here).

A minimal UI affordance (later, separately authorized): on `/match-review`, a per-blocked-bore
"set start structure" control writing one override record. The data seam (this schema + resolver) is
the prerequisite, and is now built.

## 7. Validation

- `py_compile` OK; `SELFTEST_OK`: control places (459.2 ft ≈ 451); `route_offset 413` places;
  wrong-length mapped starts (SPLICE LOC 45 / Flower Pot) correctly BLOCK; **no ground truth invented**
  (`ground_truth_invented: false` in the JSON).
- 9 endpoints, bore_log7 lane, and the existing resolver are untouched (pure `scripts/` module).

## 8. Verdict + next

The ambiguity-resolution input path exists and is proven end-to-end: **give the seam one start
structure for bore_log57 and it deterministically draws the redline; give it a wrong-length start and
it refuses.** The single remaining input is the office's start-pit value for bore_log57 (and, in the
same shape, the 56 no-terminus bores once their terminus is named). Next steps, each separately
authorized: (a) office fills `bore_ambiguity_overrides.json` for bore_log57; (b) wire
`TRUELINE_AMBIGUITY_START_OVERRIDE` into `backend/main.py` as an isolated post-rebuild pass; (c)
optional `/match-review` "set start structure" UI. DO-NOT-WIDEN intact; all flags default-OFF.

## 9. Files

- New: `scripts/target43_ambiguity_resolution.py` (+ `.json`/`.out`),
  `scripts/bore_ambiguity_overrides.sample.json` (template); this report.
- Read: KMZ route catalog + point features, the #39/#41 resolver outputs, bore_log57/7 xlsx.
