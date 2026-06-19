# log3 / log14 — owner adjudication packet (2026-06-18, continued 32 follow-on)

**Read-only source investigation. NO render, NO census/corpus/fixture mutation, NO commit of engine code.**
Branch `feat/truelinev2`. Both logs are in the remaining-9 frontier (49/58 drawn). This packet records the
source evidence + owner verdicts that explain their abstains and re-name their targets.

Probes used (read-only, repo venv + `PYTHONPATH=.`):
- `truelinev2.proof.run_log14_endpoint_probe` (solve_log + s7 source dump)
- inline s3 / s2 source dumps via `PlanPdf` + `select_dialect(...).calibrate(plan, 13)`

---

## log14 — VERDICT: DUPLICATE of drawn log10 (owner-confirmed). Keep abstained; NOT a missing redline.

Fixture: standalone `bore_log14`, span `0+00->4+18` (418'), `sheet_context [7]`, `placement_status
BLOCKED_OR_UNATTEMPTED`. The "different sheets vs log10 (s15)" framing was a red herring — **log10 physically
starts on sheet 7** and crosses to s15.

Source evidence (sheet 7):
- Reset token **`STA 0+58=0+00`** @ (553,323) with context `STA | 0+58=0+00 | HDPE` — this is log10's `00+58`
  origin (log10 fixture span `00+58->07+30`). log10 was drawn via `OWNER_APPROVED_SPAN_PROMOTIONS`.
- Run callout **`STA 0+00 TO STA 4+16`** on s7 — log10's first leg, ending at the `4+16` SEE-SHEET-15 matchline.
- log14's corpus END **`4+18`: 0 hits on s7** (the end station is not printed anywhere on the sheet).
- `solve_log(log14)` → **BLOCKED: "endpoints not resolvable (no anchors and no parseable reset/corrected
  stations)"** — log14 has no independently bindable source endpoints.

Conclusion: log14's only bindable interpretation on s7 is the `0+58=0+00 / 0+00->4+16` run, which **log10
already drew**. Drawing log14 would re-stroke log10's s7 leg at 0.0 ft (DO-NOT-WIDEN duplicate). log14 is a
corpus double-entry of log10's s7 leg, **not** a missing redline.

**Owner decision (2026-06-18): CONFIRM DUPLICATE.** Keep abstained; annotate as resolved-duplicate.
**Frontier-accounting note (proposal only — census is FROZEN, not changed here):** the 58-entry denominator
contains this duplicate, so effective placeable corpus ~57; frontier 49/58 reads as 49/57 once log14 is
acknowledged as a duplicate. No census/fixture edit made.

---

## log3 — VERDICT: DISTINCT longer bore than log4 (NOT a duplicate). Reclassify: source+solver gap, keep abstained.

Fixture: standalone `bore_log3`, span `12+63->21+63`, `sheet_context [3,4,5]`, BLOCKED. Drawn sibling `log4`
(`bore_log4`, `15+13->21+63`, sheets [3,4,5], rendered `f75c5c6`) is geographically CONTAINED by log3
(shared end `21+63`, shared `15+13->21+63` path).

The original "12+66 is a non-structure run-start / 12+63 unprinted" framing was **incomplete**. Source shows:

Sheet 3:
- Reset **`STA 15+13=0+00`** @ (848,236) with a **NEXTLINK HH** @ (872,239) — this is log4's bound origin
  (so log3's `15+13->21+63` span *is* drawn log4; the 15+13 HH is log3's INTERMEDIATE, not its start).
- **`12+66` is a MATCHLINE**, not a dead-end: `MATCHLINE STA 5+26/12+66 - SEE SHEET 2` @ right edge (x~1150).
- Run `STA 12+66 TO STA 15+13` (247', `2-1.25" HDPE`) — feeds the 15+13 HH from the s2/s3 matchline.
- log3's recorded start `12+63`: **0 hits on s3.**

Sheet 2 (the reciprocal side, `SEE SHEET 3`):
- **`12+63` IS printed here** — as a non-structure bore station: `DIR. STA 12+63 BORE TO (3') STA 12+66` @
  (131,275). So `12+63` is 3' before the matchline, NOT a structure terminus.
- Upstream feed: **`STA 9+75 TO STA 12+63`** — the bore continues upstream past 12+63.
- Reciprocal matchline run **`STA 0+00 TO STA 5+26`** + `MATCHLINE STA 5+26/12+66 - SEE SHEET 3`.
- s2 reset tokens are `7+40=0+00` NEXTLINK HH (log42's start) and `0+46=0+00` POTHOLE (log41's start) —
  **neither is log3's**. The matchline zone also carries a parallel **1-1.25"** bore (`0+00->5+26`, 526',
  AP-107 TERMINAL) distinct from log3's 2-1.25" continuation → origin needs disambiguation.

Conclusion: `12+63` is **independently attested on s2** as a real upstream station (so it is NOT a
mis-transcription of log4's 15+13) → **log3 is a genuinely longer, distinct bore**, sharing log4's downstream
half and extending upstream across the `5+26/12+66 SEE SHEET 2` matchline onto sheet 2 toward an untraced
origin. It is a REAL additional redline, currently un-drawable because:
1. recorded start `12+63` is a non-structure, matchline-adjacent station → cannot bind a terminus;
2. log3's TRUE origin is further upstream on s2 (above `9+75->12+63`) and not yet cleanly identified /
   disambiguated from the parallel 1-1.25" bore at the shared matchline;
3. full route is a 4-sheet N-leg (s2->s3->s4->s5) — 2+ intermediate matchlines, exceeding current solver support.

**Owner decision (2026-06-18): NOT a duplicate — INVESTIGATE FURTHER.** Reclassified from "owner-adjudication
duplicate" → **source+solver gap**. Keep abstained (DO-NOT-WIDEN). 
**Named target:** identify log3's true origin structure upstream on sheet 2 (trace the chain above
`9+75->12+63`, disambiguated from the parallel 1-1.25" `0+00->5+26` bore), then add N-leg support for the
s2->s5 route. Only then can the new upstream content (`12+63->15+13` + s2 leg) draw as a back-extension
through log4's 15+13 NEXTLINK HH.

---

## log3 — s2 origin trace (COMPLETE, 2026-06-18 follow-on; read-only)

Owner asked to trace log3's true origin upstream of `9+75` on sheet 2. The full continuous-frame (12+xx)
conduit chain is now reconstructed from printed run callouts + structure tokens:

```
s2:  5+16  PROP. SPLICE POINT 25 (100' SLACK COIL)
      → 7+40   NEXTLINK HH                       (224')   [= log42's 7+40=0+00 origin]
      → 9+75   AP-106 TERMINAL 8 PORT HH, 13"X24"X24"   (235')
      → 12+63  D/W driveway boundary @ 1003-1005 E STONE ST   (288')   ← log3 recorded START
      → 12+66  MATCHLINE STA 5+26/12+66 - SEE SHEET 2          (3')
s3:  12+66 → 15+13  NEXTLINK HH                  (247')   [= log4's 15+13=0+00 origin]
      → 15+13 → 21+63                                     [= drawn log4]
```

Token evidence:
- **9+75** @ (430,295): `PLACE TERMINAL 8 PORT HH 13"X24"X24" E/W` + `AP-106 SPLICE LOC 25 & PORT` +
  `TERMINAL TAIL = 500'` — a real, bindable **AP-106 TERMINAL 8 PORT HH**.
- **12+63** @ (400,241): `CENA D/W STA 9+75 TO STA 12+63 DIR. BORE (288') 2-1.25" HDPE & E/W VACANT 288CT
  FIBER CONDUIT`, address `1003 E STONE ST / 1005 E` — a **driveway (D/W) run-segment boundary, NOT a
  structure.**
- **5+16** @ (993,290): `PROP. PLACE 100' SPLICE SLACK COIL POINT 25 STA 5+16 DIR. BORE TO (224') STA 7+40
  2-1.25" HDPE` — the upstream PROP. SPLICE POINT.

**Trace conclusion (definitive):** log3's recorded start `12+63` is a DRIVEWAY boundary 3' before the s2/s3
matchline — there is **no bindable structure at 12+63**. The conduit's nearest real structures are the 15+13
NEXTLINK HH (downstream = log4's origin / log3's intermediate) and the 9+75 AP-106 8-PORT HH (288' UPSTREAM,
**outside** log3's 12+63->21+63 span). The full source is now read; this is NOT a source-extraction gap — the
source simply has no structural origin at log3's recorded start.

**Forward paths for log3 (all OWNER span-correction decisions, none auto-drawable):**
1. **Confirm abstain (recommended):** 12+63 is genuinely unbindable (driveway); log3's only NEW content over
   drawn log4 is the `12+63->15+13` upstream segment with a non-structure origin → stays abstained. The
   "named missing-source target" is now resolved to: *the source provides no structural origin at 12+63.*
2. **Owner re-origin to 9+75 AP-106 8-PORT HH:** would change log3's span (12+63->21+63 ⇒ 9+75->21+63), pull
   in the 9+75->12+63 segment (may belong to another log), and require N-leg support (s2->s3->s4->s5). A
   corpus/span correction + solver work, not an auto-draw.
3. Matchline 12+66 is NOT a valid origin (conduit continues upstream through 9+75).

## Frontier impact (no census change — accounting note only)
- **log14**: confirmed duplicate of log10 → drop from "missing redline" accounting (effective 49/57).
- **log3**: confirmed DISTINCT (longer than log4) → stays a genuine not-yet-placed redline, moved from the
  "owner-adjudication, no-new-source" bucket into the "source+solver gap" bucket (traceable; named target above).
- Remaining-9 reframed: log14 resolved (duplicate); log3 reclassified (source+trace gap); still owner/source-
  gated: log5/31/38/43 (locked abstain), log15/16 (unprinted cuts), log57 (`.FS`).
