# M9.1: KMZ_AP_STRUCTURE_JOIN — shipped cross-source terminal-join law

Status: **SHIPPED (engine; UNWIRED / default-off); adversarially audited.**
Promotes the M9.0 audited primitive from proof into convention-agnostic engine
code. **Zero bores moved**; the M8.27 truth table, the all-58 census, and the
M8.10/M8.11/M8.15/M8.20/M9.0 contracts are untouched.

Extractor: `truelinev2/match/kmz_structure_join.py` (universal core, zero
customer literals — drift-guard-enforced)
Profile: `truelinev2/extract/kmz.py` `BRENHAM_KMZ_DIALECT.terminal_class` (the
Brenham profile/fixture)
Proof: `truelinev2/proof/run_kmz_structure_join_proof.py` (G1–G10 PASS)
Tests: `truelinev2/tests/test_kmz_structure_join.py` (12; synthetic non-Brenham
model + tracked fixture controls)

## The law

`join_terminal(model, *, terminal_class, pdf_ap, pdf_splice_loc)` binds a PDF
terminus callout to **exactly one** terminal-class KMZ structure carrying **both**
ids:

> PDF `AP-NNN SPLICE LOC MM` ↔ KMZ `terminal_class{ AP=NNN, splice_loc≈MM }`

Typed outcomes: `JOIN_BOUND` · `JOIN_AMBIGUOUS` · `JOIN_AP_ONLY_REJECTED` ·
`JOIN_SPLICE_ONLY_REJECTED` · `JOIN_AP_MISSING` · `JOIN_SPLICE_MISSING` ·
`JOIN_NONE` · `JOIN_NO_TERMINAL_CLASS`. Every non-bind names the missing
relationship.

Zero-false guarantees (gated):
- **two-field mandatory** — AP-only and splice-only are refused, never downgraded.
- **class-scoped** — only the profile's `terminal_class` is a candidate (the
  same-AP `splice_hh` twin, 28–181 m away, is never bound).
- **no proximity** — the binding decision reads no coordinate (`.lon`/`.lat`
  absent from `join_terminal`); geometry is carried only as metadata.
- **uniqueness-mandatory** — 0 / ≥2 candidates → typed refusal; self-duplicated
  AP ids collapse to one candidate (never spurious ambiguity).

## Universal core vs profile

The core holds **zero** plan-set literals (CORE_DIRS drift guard). Everything
customer-specific is injected: `terminal_class` (the bore-terminus class) and the
`ap_re`/`splice_re` callout grammars (used only by the `parse_terminus_pair`
helper). Brenham is **only a profile/fixture**. Universality is proven on a
**synthetic non-Brenham model** (a different terminal class + zone/alpha ids).

### M9.1 audit fix (the splice-token correction)

The first draft reduced the splice-loc to a trailing integer (`_last_int`). The
adversarial audit demonstrated a **live false bind** on a zone-prefixed profile
(`SPLICE A-12` and `SPLICE B-12` both collapsed to `12` → wrong-closure bind) and
a **whole-plan abstain** for non-integer ids (`Loc 5A` → dropped). Brenham masked
both (its splice ids are bare integers — verified 0 collisions). **Fix:** the
splice-loc is now compared as a **whole normalized opaque token** (upper +
whitespace-collapsed), preserving every discriminating character. Result: zone
`A-12` ≠ `B-12` (no cross-bind), `Loc 5A` is bindable, and Brenham binding is
byte-identical. The AP/splice **grammars** (raw string → id) remain a profile
property; the law itself imposes no integer assumption (G10 regression).

## Controls + verification

| control | PDF callout | result |
|---|---|---|
| log7 | `AP-163 SPLICE LOC 46` | `JOIN_BOUND` → terminal 163 |
| log42 | `AP-105 SPLICE LOC 25` | `JOIN_BOUND` → terminal 105 |

Corpus: 64 terminal anchors, **0 `(ap,splice)` collisions**, self-bind bijection
0 failures. Default-baseline / census / M8.27 / M9.0 unchanged; full v2 suite
**675 passed**.

## Boundary + next step

**UNWIRED**: no `resolve_bore` / sweep / reviewer service / `run_match` consults
the extractor; it places nothing, draws nothing, emits no AUTO/stroke/segment/PNG,
moves no bore, changes no product bucket. It returns a typed, evidence-carrying
anchor (or a typed refusal) for a future, separately-gated lane.

**Next KMZ engine step:** `KMZ_MATCHLINE_SUBSTITUTE` for the no-equation
cross-sheet class (log68 + log10/14/61/62/67/68/70) — consume two BOUND terminal
anchors (start + end) to bridge a missing matchline equation when the PDF has no
contradiction; and route-stroke geometry support for log8/log32/log42 via their
KMZ AP terminals. log44's endpoint bridge stays gated on the 325′ source fix.
