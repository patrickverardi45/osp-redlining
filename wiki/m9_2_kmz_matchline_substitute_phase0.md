# M9.2 Phase 0: KMZ_MATCHLINE_SUBSTITUTE — feasibility audit (HONEST NEGATIVE)

Status: **PROOF-ONLY / READ-ONLY; no extractor shipped; zero bores moved.**
Decides whether the no-equation cross-sheet class can safely use the KMZ as a
matchline substitute. **It cannot, from the current printed evidence** — proven
per-bore, adversarially audited. The M8.27 truth table, the all-58 census, the
product lanes, and the M9.0 dispositions are untouched.

Runner: `truelinev2/proof/run_kmz_matchline_substitute_phase0.py` (G1–G7 PASS)
Tests: `truelinev2/tests/test_kmz_matchline_substitute_phase0.py` (14; offline
pure + posture; live facts gated in the runner)
Report (gitignored, regenerable):
`data/outputs/kmz_matchline_substitute_phase0/kmz_matchline_substitute_phase0.{json,md}`

## The law boundary tested

A KMZ matchline substitute is admissible ONLY if all hold: (1) both endpoints
bind via the two-field AP+splice-loc M9.1 join; (2) each join is unique +
class-scoped; (3) KMZ route evidence supports continuity between the two anchors;
(4) no PDF/source contradiction; (5) source context compatible; (6) no equal
competitor. The disposition is decided by the **first unmet condition** — for this
class that is **condition 1** for every bore, so conditions 3/4/6 are not
independently exercised per bore (2 is enforced inside the join; 3 is a global
source fact via G5; 4 is a banked M8.16/M8.25 input; 6's endpoint half is the
join's `JOIN_AMBIGUOUS` refusal).

## Candidate list verification (do not trust the prose)

The M9.0 next_law names the class `log68 + log10/14/61/62/67/68/70` (7). Re-derived
**live** from the M8.16 probe's gated needle:

- **Strict no-equation class = 6 bores**: `log14, log61, log62, log67, log68,
  log70` (each carries "prints no equation at this boundary").
- **`log10` is a 1-bore superset edge → `NOT_IN_CLASS`**: its needle is "run
  callouts sharing one boundary" (a *printed-identity matchline path*, start bound
  via reset equation `STA 0+58=0+00`), a different lane — not equation-absent.

The task's 7-bore list is therefore **verified-exact against the named scope but a
superset of the strict predicate.**

## Result — per-bore (endpoint-attributed, never the flat sheet scan)

Endpoint AP+splice is read from the proven end-structure note grammar
(`structure_anchor.bind_end_structure_note`) at the bore's start_ft / end_ft — NOT
a flat sheet scan (which over-collects neighbours).

| disposition | bores |
|---|---|
| `ENDPOINT_PAIR_MISSING` | log14, log61, log62, log67, log68, log70 (the 6 strict) |
| `NOT_IN_CLASS` | log10 |
| `TWO_ENDPOINTS_BOUND` | **none** |

For the 6 strict bores the endpoints, where printed, are **non-terminal drop
structures** (FLOWER POT / INSTALLER HH) carrying **no AP+splice id** (`NO_ID`), or
no note prints at the station — so the terminal_class join has no key. `log68`'s
flat-scan `AP-148 SPLICE LOC 34` prints at `STA 20+71` (a different run on shared
sheet 19), **not** log68's `4+54→7+21` span — it is *not* endpoint-attributable.
This **sharpens** M9.0's "one endpoint AP-148 confirmed" (which was a sheet-level
hit) without changing log68's disposition (still SOURCE_OR_KMZ_REQUIRED, unmoved).

`log10` (outside the strict class) is the one candidate whose **END** binds a
unique terminal (`AP-152 / SPLICE LOC 35`); its START is unprinted → a future
**single-anchor / endpoint-bridge** candidate (KMZ_ENDPOINT_BRIDGE-style, like
log44), **not** a matchline substitute.

## Two blockers (one operative, one standing)

- **(A, operative) two-endpoint terminal binding is unsatisfiable** from the
  current printed grammar — the cross-sheet endpoints are non-AP drop structures;
  the M9.1 join binds only terminal_class.
- **(B, standing) condition 3 is structurally unmet** — every Vacant Pipe route
  carries only `Connection Type` + empty `Note`; **0/58** carry a non-geometric
  AP/id link, so route↔structure continuity can only be asserted by forbidden
  coordinate proximity. (B) would bind a future bore that first cleared (A).

Both are **named unmodeled relationships, not permanent impossibilities.**

## Controls + posture (unchanged)

M9.1 controls re-bind through this harness (`log7`→AP-163, `log42`→AP-105 →
`JOIN_BOUND`), proving 0/6 is a measured negative, not a rigged predicate. The
M9.1 join + M9.0 reader stay **UNWIRED** (no engine/lane/service import); no PNG,
no segment, no AUTO, no tolerance change. M8.11 `fullest_safe_review` lanes
`30/16/6/4/2` and the 7 bores' M8.27 buckets are unchanged. Full v2 suite
**689 passed**.

## Named evidence targets (forward levers, ranked)

1. A **START/END terminus attribution** model — bind a printed `AP-NNN SPLICE LOC
   MM` line to a specific bore's start_ft vs end_ft (today only the structure
   *label* is start/end-aware, never the AP/splice id; the flat scan over-collects
   neighbours). This is the gate for both the substitute and any endpoint-bridge.
2. A **printed terminal identity for the cross-sheet endpoints** (currently flower
   pot / installer HH, no AP+splice) — M8.26 already showed no zero-false
   end-identity gate exists from the current grammar.
3. A **non-geometric KMZ route↔structure linkage** (absent in this source), OR a
   *separately-gated* geometric route-corroboration law with its own zero-false
   proof — never proximity-as-identity, and not this milestone.

## Adversarial audit

5 refutation lenses (false-negative binding, route-linkage, candidate-class,
read-only/guards/drift, overclaim/honesty). The structural honest-negative was
**confirmed sound**; the audit caught 3 prose/precision defects (a copy-paste
blocker string false for log61's printed endpoints; an "all six conditions
checked" overclaim vs. first-unmet-condition reality; "impossible" not scoped to
"current printed evidence") + a dead import — **all fixed pre-commit.** Per-bore
blockers are now built from the actual endpoint evidence.
