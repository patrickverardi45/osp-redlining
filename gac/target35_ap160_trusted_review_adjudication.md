# Target #35 — AP-160 trusted-review adjudication (default-OFF, read-only)

**Mission:** adjudicate the single TRUSTED-REVIEW endpoint Target #33 surfaced — **(sheet 13,
STA 359, AP-160)** — into one of PROMOTE_TRUSTED / REJECT_FALSE_POSITIVE / KEEP_TRUSTED_REVIEW,
structure-side only, without guessing and with zero wrong-redline risk.

**VERDICT: `KEEP_TRUSTED_REVIEW`.** AP-160 is a **real** KMZ Terminal Port HH structure and the
automated extraction chain rates it *promote-grade* (run_end role, leader-confirmed, reconstructed,
no nearby matchline). It is **not** promoted because that signal is **uncorroborated** by the
literal-quote-verified hand run-endpoint reference — which lists **zero** sheet-13 AP run-endpoints
and treats sheet 13's other stations as matchlines — and AP-160 carries **no independent
station/sheet/tail binding** that all 7 confirmed endpoints have. It is **not** rejected because the
structure unambiguously exists (KMZ node + lat/lon). Promoting on the automated signal alone, over a
reference that treats sheet 13 as a boundary sheet, would widen the placement-grade table without
ground confirmation. No promotion performed (DO-NOT-WIDEN); the 7 confirmed endpoints + bore_log7
lane are untouched.

> Read-only; pure-helper reuse (Primitive A/B/C + Target #30 reconstruction + #25 index); isolated
> in `scripts/`; no engine import-as-production, no flag, no STATE, no placement.
> Probe `scripts/target35_ap160_adjudication.py` → `.json`/`.out`. Self-test `SELFTEST_OK`.

---

## 1. Adjudication diagnosis (5 evidence axes)

| axis | evidence | reading |
|---|---|---|
| **E1 KMZ identity** | AP-160 IS a `Nodes / Terminal Port Handhole` node; lat/lon **(30.158369, −96.384328)**; **tail_route = None, station_ft = None, print_sheet = None** | real structure, but NO run-terminus binding (the 7 confirmed all carry station+sheet+tail) |
| **E2 run-role (Primitive C)** | `classify_callout` → **role = run_end** | automated geometry treats STA 359 as a run terminus |
| **E3 leader verdict (Primitive B)** | **B_verdict = confirmed**, `component_ap = 160`, reconstructed = True | the AP-160 digits sit in the structure label's OWN vector component (not a nearest-label artifact) |
| **E4 boundary context** | sheet-13 **geometry-derived** matchline stations = `[]`; **no** matchline within 40 ft of STA 359 | STA 359 is not near a geometry-detected matchline |
| **E5 hand reference** | `(13, 359, 160)` ∉ `BRENHAM_PH5_RUN_ENDPOINTS`; sheet-13 AP run-endpoint rows = **NONE**; sheet-13 hand entries 308/389/390/398 are all typed `matchline` | the literal-quote-verified reference does not cover sheet-13 APs and treats the sheet as boundary |

## 2. Evidence for hand-omission vs subtle false positive

**Not a false positive.** AP-160 resolves to a genuine KMZ Terminal Port Handhole node with
coordinates; the on-sheet block carries the full `TERMINAL … PORT … SPLICE` phrase (Target #33 g3)
and the AP-160 digits are confirmed inside the structure's own leader component (Primitive B). This
is a real structure, not a misread matchline/cross-reference number (which is what disqualified the
other four sheet-13 candidates — AP-151/166/167/162 — in Target #33).

**But not a confirmed hand-omission either.** Three independent gaps block promotion:
1. **No hand-reference corroboration.** The hand run-endpoint table was built by Agent-A literal
   PDF-quote verification (Target #10). It lists **zero** AP run-endpoints on sheet 13 and types the
   neighbouring sheet-13 stations as matchlines — i.e. it treats sheet 13 as a boundary/continuation
   sheet. AP-160 @ 359 is absent from it.
2. **No independent binding.** AP-160 has `station=None, sheet=None, tail_route=None` in the #25
   index — it lacks the station/sheet/tail that every one of the 7 confirmed endpoints carries, so
   there is no second, independent source tying AP-160 to STA 359 / sheet 13.
3. **Automated-only signal on a boundary sheet.** The promote-grade verdict rests entirely on the
   automated A→B→C chain. Trusting it *over* the hand reference, on the exact sheet that reference
   treats differently, is precisely the widening DO-NOT-WIDEN forbids without ground confirmation.

This is the textbook definition of **trusted-review**: geometrically valid, real structure,
promote-grade automation — but not yet corroborated by an independent verified source.

## 3. Final classification

```
classification : KEEP_TRUSTED_REVIEW
```

## 4. Machine-readable reason

```json
{
  "target": {"sheet": 13, "sta": 359.0, "ap": 160},
  "classification": "KEEP_TRUSTED_REVIEW",
  "machine_reason": "geometry_promote_grade_but_uncorroborated_by_hand_reference_on_boundary_sheet_and_no_independent_station_tail_binding",
  "promotion_blocked_until": [
    "literal-quote verification that a 'STA 3+59 ... DIR. BORE ... TERMINAL n PORT HH AP-160' run-END block exists on sheet 13 (the Agent-A method that built the hand table)",
    "OR a station/sheet/tail binding for AP-160 in a verified source"
  ],
  "signals": ["kmz_terminal_port_hh_node_exists", "run_role=run_end", "leader_confirmed",
              "reconstructed", "no_geometry_matchline_within_40ft",
              "absent_from_literal_quote_verified_hand_run_endpoint_reference",
              "hand_reference_lists_zero_sheet13_ap_run_endpoints",
              "no_independent_station_sheet_tail_binding_in_index"]
}
```

## 5. Promotion artifact — NOT updated

Deliverable #5 ("if promoted, update only the default-OFF/read-only trusted endpoint shadow") is
**not triggered**. AP-160 stays in the `review` array of `scripts/pdf_clean_endpoint_table.json`;
the `confirmed` array (the 7 placement-grade endpoints) is **unchanged**. No shadow artifact widened.

## 6. Validation + non-regression

- `python -m py_compile scripts/target35_ap160_adjudication.py` → `PY_COMPILE_OK`.
- Probe run → classification `KEEP_TRUSTED_REVIEW`; `SELFTEST_OK`.
- **Control:** the 7 Target #33 confirmed endpoints were re-run through A→B this session and all
  **7/7 re-validated as `confirmed`** (`control_ok = True`) — no endpoint degraded.
- bore_log7 lane and `BRENHAM_PH5_RUN_ENDPOINTS` untouched (read-only).

## 7. Verdict + next target

AP-160 is a **real Terminal Port HH structure with promote-grade automated geometry**, held at
**KEEP_TRUSTED_REVIEW** pending one specific, addressable corroboration (a literal-quote run-END
verification on sheet 13, or an independent station/tail binding). This is the safe call: it neither
discards a real structure nor widens the placement-grade table on an uncorroborated automated signal.

Next (Target #36): the next safest pure structure-side endpoint-quality gate from the #32/#33
outputs — strengthen sheet-13/14 boundary handling so the four already-EXCLUDED sheet-13 candidates
(AP-151/166/167/162) and any future boundary cross-refs are quarantined by an explicit, durable rule
rather than incidental gate side-effects — keeping precision 1.00 and never touching the 7 confirmed.
No placement; DO-NOT-WIDEN intact; all flags default-OFF.

## 8. Files

- Read: `scripts/pdf_clean_endpoint_table.json` (#33), `scripts/ap_structure_index.json` (#25),
  `BRENHAM_PH5_RUN_ENDPOINTS` ([pdf_ap_route_resolver.py:989](backend/app/core/pdf_ap_route_resolver.py#L989)),
  Primitives A/B/C (`pdf_run_endpoint_extractor.py`, `pdf_leader_run_following.py`,
  `pdf_run_polyline_tracer.py`), `pdf_ap_glyph_reconstruct.py` (#30); `Brenham - Phase 5_07-15-25.pdf`
  sheets 8/10/11/12/13 (read-only).
- Wrote: `scripts/target35_ap160_adjudication.py` + `.json` + `.out`; this report.
