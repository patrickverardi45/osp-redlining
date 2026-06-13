# M8.21 Adjudication: log42 Split-Log / Corridor-Pruned Trace / Frame Ownership

Status: **ADJUDICATED BY EXTRACTION — log42 remains a typed abstain with a
sharper named target; the corridor capability SHIPPED proof-only.** The lane
is unchanged; log41/log42/log8/log32 statuses and the all-58 census are
unchanged; zero strokes; no tolerance widened; the walk budget untouched.

Probe: `truelinev2/proof/run_split_log_corridor_probe.py` (G1–G9 PASS)
Module: `truelinev2/extract/corridor_prune.py` (proof-consumed only; UNWIRED)
Report: `data/outputs/split_log_corridor_probe/split_log_corridor_probe.json`
Tests: `truelinev2/tests/test_corridor_prune.py` +
`test_split_log_corridor_probe.py` (27)

## 1. The owner correction, verified and refined (G2/G3)

The printed parent chain is REAL — all three fragments print verbatim and
engine-parse:

| Fragment | Sheet | Class | Printed text (load-bearing part) |
|---|---|---|---|
| `0+00 → 2+70` (270') | 2 | PORT TERMINAL TAIL | `STA 0+00 TO STA 2+70 E/W PORT TERMINAL TAIL @ 24-36" MIN. DEPTH DIR. BORE (270') 1-1.25" HDPE` |
| `2+70 → 2+87` (17') | 1 | PORT TERMINAL TAIL | `STA 2+70 TO STA 2+87 ... DIR. BORE (17') 1-1.25" HDPE` |
| `2+87 → 5+19` (232') | 1 | **VACANT** | `STA 2+87 TO STA 5+19 DIR. BORE (232') 1-1.25" VACANT HDPE FOR FIBER DROP` |

Chain crossing: reciprocal `MATCHLINE STA 2+70/5+16` on both sheets.
Closure: **270 + 17 = 287 = log42's span EXACTLY** (the 17' fragment is
log42's own end segment, not a missing bridge). The 232' fragment is an
authored CLASS-DISTINCT adjacent run (`ADJACENT_PRINT_CONTEXT_NOT_CLAIMED`):
the sheet-1 quantity table books 17 under PORT TERMINAL and 232 under
VACANT separately, and **no corpus bore claims it** (sheet-1 claimants =
{log41, log42}, measured). `519` is never printed — it is arithmetic
(270+17+232) plus station `5+19`. Split provenance (both children name
`bore_log13.xlsx`, same photo/date/crew/print) is consumed as **WEAK
grouping evidence only** (run-segment-hierarchy §8); the parent file in
`combined_originals_DO_NOT_IMPORT` is **never read** (negative-I/O gate).

## 2. Corridor-pruned unique tracing SHIPPED (the M8.20 named target) (G5/G6)

`extract/corridor_prune.py`: the corridor is the EXISTING length law as a
piece filter — `bound = footage·scale·(1+DESIGN_LENGTH_REL_TOL) +
2·(jump_cap+TRIM_RADIUS)`, all imported banked constants, zero new tunables,
budget and jump cap UNCHANGED. Keep rule is VERTEX containment; `trim_to_
anchors` makes anchors literal path endpoints, so a piece whose vertices all
exceed the bound cannot appear in any path the existing gate could accept.
One-sided guarantee (test-pinned): pruning can only LOSE completions
(conservative abstain), never create them.

**Semantics (deliberate, test-pinned, provenance-tagged):** a finished
corridor search certifies uniqueness among LENGTH-ADMISSIBLE-CAPABLE
geometry only — a DIFFERENT certificate class from M8.18's full-universe
survivorship. Complete in-corridor paths are never post-filtered by length
(an inadmissible in-corridor rival still kills via `AMBIGUOUS` — measured
twice on log42). Every corridor record carries
`uniqueness_universe: LENGTH_ADMISSIBLE_CORRIDOR`. **Law 1
(`SHARED_ALIGNMENT_MULTI_DROP`) gate 1 means full-universe survivorship and
does not accept corridor-class survivors** (test: the shared-alignment stack
contains no corridor reference). Any future lane wiring of corridor results
requires a fresh adversarial judgment.

Controls: log8/log32 pruned vs unpruned **byte-identical** (survivor
`NEXTLINK@378,409`, plen 265.7, stroke points equal, paths_found/path_groups
equal; per-candidate elimination-type shifts typed and pinned).

Result on log42's 13 banked candidates (vs 12×EXHAUSTED + 1 no-chain
unpruned): **8 LENGTH_INFEASIBLE_CHORD + 1 PATH_LENGTH_OUT_OF_TOLERANCE +
2 finished DESIGN_PATH_AMBIGUOUS + 1 NO_CONDUIT_CHAIN_TO_MATCHLINE +
1 SURVIVOR_IN_CORRIDOR (`NEXTLINK@818,419`, plen 324.2, kept 17/39 pieces,
margin-stable, slack never load-bearing)** — every elimination is now a
positive typed certificate instead of an uncertifiable budget death.

## 3. The frame-ownership law — the survivor is NOT the origin (G4/G7)

Adversarial review (5-lens panel; completeness critic) REFUTED the naive
reading "corridor survivor = origin". The probe now proves the refutation:

* Sheet 2 prints exactly 2 reset origins (M8.6 parser): `STA 7+40=0+00`
  (splice; positively excluded typed `ORIGIN_CLASS_UNMODELED`, never
  silently omitted) and **`STA 0+46=0+00` → `13"X24"X24" INSTALLER HH`**,
  whose label box contains BOTH the equation token and the label words;
  both b.2 locator forms bind it to symbol **(818.4, 419.0)** — the
  corridor survivor's own cluster.
* **Callout frame ownership** (new law, uniqueness-mandatory): the unique
  ladder with interior tick stations that places the printed boundary
  (`2+70`) at the physical boundary point within half its own tick step.
  Naive y-band/nearest selection is FORBIDDEN — two runs' ladders measured
  5.1 pt apart in y here (the M8.16 interleaved-band trap, recurring).
* In the owning frame: boundary at **269.8 ft ≈ 2+70**, installer at
  **45.9 ft ≈ printed 0+46**; survivor path **225.17 ft = footage − 46
  (+0.5%)**; printed `HH - HH = 46'` hop + path arc = **272.1 ≈ 270
  (+0.8%)**.

**Verdict `INTERIOR_RESET_NOT_ORIGIN`:** the installer HH is the printed
INTERIOR reset at callout-frame 0+46 (the banked M8.6 interior-boundary
case) — plausibly the 526-ft westward run's origin (its rejected ladder
back-projects its own 0+00 to the installer cluster, measured context).
log42's origin is the callout-frame 0+00 structure ≈46 run-ft upstream
(`NEXTLINK@819,351`), whose corridor verdict is **DESIGN_PATH_AMBIGUOUS
(4 complete paths, 2 jitter groups)** — distinct geometry is never
tiebroken. log42 therefore stays `STRUCTURE_IDENTITY_BINDING_REQUIRED`.

## 4. log41 — typed conflict enumeration, no preference (G8)

`SOURCE_DIGIT_REREAD_REQUIRED`: readings {`0+44` digitized, `0+50`
source-flagged alternative, `0+46` printed candidate (`STA 0+46=0+00` +
`HH - HH = 46'`)} — the record schema FORBIDS any preferred/selected/
corrected field (validator + test); engine binding for 44.0 and 50.0 both
refuse (no tolerance bridges to 46). Action: **owner re-read of source
photo `2025-12-03_212755 - Jimenez`** (bore_log41.xlsx row 2). log41 stays
`END_IDENTITY_UNPRINTED`.

## 5. Named targets after M8.21 (the sharpened log42 lane)

1. **Strand discriminator at the callout-frame origin** (`NEXTLINK@819,351`,
   2 jitter-distinct route groups) — the real log42 unlock.
2. **Owner source re-reads:** bore_log13 block semantics (is Segment B's
   0+00 the callout-frame origin or the installer reset?) + the log41 end
   digit (44/50 vs printed 46).
3. Deferred BY NAME: the bore_log17 family (log43/log44 — different prints
   10/18, unresolved source flags, print-18 adjacency to the frozen
   controls); regeneration of the stale
   `data/outputs/reviewer_payload_contract.json` (its log42 block still
   says PLACED_REVIEW from the pre-M8.14 text era — superseded, never
   consumed).

## 6. Boundary

Proof-only. `corridor_prune` is consumed by the M8.21 probe + tests only —
not by `resolve_bore`, the sweep, the Law-1 stack, or any reviewer surface
(test-enforced). No walk-budget raise, no tolerance change, no stroke, no
card, no census drift (G1 + full battery re-proven green). The M8.20
unpruned taxonomy remains the full-universe authority (cross-pinned).
