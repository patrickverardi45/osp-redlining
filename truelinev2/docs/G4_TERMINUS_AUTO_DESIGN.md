# G4 — Cold-Package Source-Backed AUTO Gate (DESIGN ONLY)

> **Status: design only. Nothing here is implemented.** No `_cap_review` edit, no AUTO promotion, no
> placement/status/renderer change. This document is the proof-bed plan a future G4 implementation must satisfy
> before any AUTO code lands.
>
> **Hard rule preserved throughout:** AUTO must never rest on inferred endpoints, guessed geometry, fake
> coordinates, or recognized-corpus knowledge.

## Summary

Today the cold (generic) lane is **REVIEW by construction** and is structurally isolated from the named /
deterministic AUTO path. G4 would add a **separate, default-OFF, post-placement promotion gate** that can flip a
generic REVIEW to a *new* `SOURCE_BACKED_TERMINUS_AUTO` status **only** when both bore endpoints are independently
source-bound by printed plan evidence **and** the drawn geometry is unambiguously the line between those two
endpoints. The gate *adds* an exception; it never weakens the REVIEW default and never touches the named path.
The redline geometry is unchanged — only the status/provenance label changes.

The single deepest insight: **source-bound endpoints prove the endpoints, not the line between them.** The generic
detector fragments all plan linework, so even with two correct printed endpoints, several drawn lines can span
them. AUTO therefore requires *both* a terminus-evidence gate *and* a strict geometry-uniqueness gate.

## 1. `_cap_review()` interaction — current block & smallest safe change

**How generic AUTO is blocked today (precise, grounded in the code):**

- `_place_generic` (`truelinev2/contracts/uploaded_corpus_engine_handoff.py:331`) constructs the `Placement`
  **directly** with `status=PlacementStatus.REVIEW`. The generic lane never emits `AUTO_SELECT`.
- `_cap_review` (`uploaded_corpus_engine_handoff.py:168`) is a **defensive invariant guard**, currently invoked
  **only by tests** (`test_generic_geometry_review.py:107,126`). It forces any stray `AUTO_SELECT` generic
  placement back to `REVIEW` and tags `GENERIC_GEOMETRY_REVIEW` / `GENERIC_CAP_REVIEW`.
- The candidate→tier map (`review_acceptance.py:243`) sets `TIER_AUTO` **only** when
  `placement_status == AUTO_SELECT.value`. Generic ⇒ `REVIEW` ⇒ `TIER_REVIEW`.
- The named (Brenham/ODOT) path reaches `AUTO_SELECT` via the engine's own source-tight evidence (the
  `DETERMINISTIC_AUTO=49` / `50/58` frontier). The generic lane **never fires for a recognized plan**
  (`uploaded_corpus_engine_handoff.py:450-451`), so the two paths are isolated.

**Smallest safe future change:** do **not** edit `_cap_review` and do **not** edit `_place_generic`'s hardcoded
`REVIEW`. Add a *new* module `terminus_auto_gate.py` consulted **after** the generic REVIEW placement is built,
behind a default-OFF flag (e.g. `TL2_TERMINUS_AUTO_OPTIN`). It:

- runs **only** on `dialect == generic` placements (the named path literally cannot enter it);
- consults source-backed terminus evidence for the **same** plan + reviewed-bore-log;
- can **only promote** REVIEW→AUTO, never the reverse, and only when every condition in §4 holds;
- emits a **distinct** provenance `SOURCE_BACKED_TERMINUS_AUTO` (not `DETERMINISTIC_AUTO`, not the generic REVIEW
  provenance) so the "generic-inference confidence is capped at MEDIUM" story stays literally true — the AUTO rests
  on **terminus source-binding**, not on raising `_GENERIC_MAX_CONF`.

This guarantees: default generic placements stay REVIEW; only proven source-backed cases are *considered*; the
named/deterministic path is untouched (it never enters this gate); low-confidence/correction cases are excluded by
the geometry gate in §4.

## 2. Per-source-type confidence table

| terminus `source_type` | AUTO-eligible? | Rationale |
|---|---|---|
| `PRINTED_STRUCTURE_LABEL` | **YES** (the only one the extractor binds today) | Printed per-bore structure identity at the exact endpoint station; uniqueness-gated; refuses proximity/ambiguous (proven by term-005/006/007). |
| `PRINTED_STA_CALLOUT` | **FUTURE-YES** (not bound yet) | A printed run callout bracketing the span is per-bore printed evidence, but **no binder exists**; eligible only once a uniqueness-gated binder + tests land. |
| `MATCHLINE_BOUNDARY_STATION` | **FUTURE-YES** (not bound yet) | A bilateral printed matchline equation is strong cross-sheet evidence; today only a read-only *caveat* (`MATCHLINE_CONTINUATION_*`), **not an endpoint binder**. Eligible only with both-sides-print-same-boundary verification. |
| `BORE_LOG_ROW` | **NEVER** | Gives the station *value*, not per-bore printed identity. Already excluded from `SOURCE_BOUND_TYPES`. This exclusion is the whole point of the gate. |
| `KMZ_ROUTE_VERTEX` | **NEVER** (until true georef) | A GIS vertex is not calibrated to the plan's station axis; no source linkage to the drawn run. REVIEW-only evidence at most. |
| `INFERRED_FROM_GEOMETRY` | **NEVER** | This *is* what the generic lane does — the exact thing AUTO must not rest on. |
| `ABSENT` | **NEVER** | No value. |

`AUTO_ELIGIBLE = {PRINTED_STRUCTURE_LABEL}` **today**; widens to add `PRINTED_STA_CALLOUT` and
`MATCHLINE_BOUNDARY_STATION` only once their binders + tests exist. AUTO requires **both** endpoints in
`AUTO_ELIGIBLE`. A single non-eligible endpoint ⇒ REVIEW. The generic *geometry* confidence
(`_GENERIC_MAX_CONF=0.70`) is separate and is **not** raised for AUTO — AUTO comes from terminus source-binding
being independent of the geometry guess.

## 3. Blocker truth table (per-endpoint state → outcome)

| Endpoint state | AUTO? | REVIEW? | ABSTAIN? | Blocker / caveat code |
|---|---|---|---|---|
| **bound** (eligible source type) | ✅ (only if *both* + geometry gate) | ✅ fallback | — | — |
| **missing** | ❌ | ✅ | — | `NO_PRINTED_{START,END}_STRUCTURE` |
| **ambiguous** (≥2 rivals same station) | ❌ | ✅ | maybe (if both ambiguous) | `AMBIGUOUS_{START,END}_STRUCTURE` |
| **conflicting** (two source types disagree on the station) | ❌ | ❌ | ✅ required | *new* `CONFLICTING_{START,END}_TERMINUS` |
| **unreviewed bore-log row** | ❌ | ❌ (engine-ready gate blocks first) | — | `NO_ENGINE_READY_REVIEWED_BORE_LOG` |
| **sheet mismatch** (bound on sheet ≠ placement sheet) | ❌ | ✅ | — | *new* `TERMINUS_SHEET_MISMATCH` |
| **station mismatch** (printed note station ≠ bore-log endpoint) | ❌ | ✅ | — | already never binds → `NO_PRINTED_*` (proven by term-007) |
| **matchline unresolved** | ❌ | ✅ | — | `MATCHLINE_CONTINUATION_UNVERIFIED` |
| **unsupported source type** (KMZ/inferred/absent) | ❌ | ✅ or ABSTAIN per geometry | — | *new* `UNSUPPORTED_TERMINUS_SOURCE_FOR_AUTO` |

Whole-bore rule: **AUTO only if start AND end are both `bound`+eligible AND no endpoint is in the "conflicting"
class.** Any "conflicting" → ABSTAIN (a contradiction in source evidence is never silently resolved). Everything
else that isn't both-bound → REVIEW.

## 4. Proposed AUTO eligibility rule (plain logic — NOT implemented)

```
SOURCE_BACKED_TERMINUS_AUTO  iff  ALL of:
  flag TL2_TERMINUS_AUTO_OPTIN is ON                         # default-OFF; ships inert
  a generic-lane placement exists (a drawn run was selected)
  dialect == "generic"                                       # named/deterministic path never enters here
  GEOMETRY IS UNAMBIGUOUS:
      cover        >= _GENERIC_HIGH_COVER (0.90)
      extent_fit   >= 0.90  and  end_fit >= 0.90
      full_sheet   == False
      fragments    == 0  and  competition == 0               # ZERO rival runs over the span
      run endpoints coincide (tight tol) with the source-bound endpoint positions   # not just stations
  TERMINUS IS SOURCE-BOUND:
      terminus.start.source_bound and terminus.end.source_bound
      terminus.start.source_type in AUTO_ELIGIBLE and terminus.end.source_type in AUTO_ELIGIBLE
      no ambiguity / conflict on either endpoint
      printed endpoint stations EQUAL the bore-log endpoint stations the placement used
      terminus binding sheet(s) == the placement's render sheet(s)            # no sheet/offset drift
  PROVENANCE / GATES:
      bore-log row is reviewed/confirmed (engine-ready rbl — already required)
      NO correction-required caveat  and  NO low-confidence generic warning
  ISOLATION:
      gate touches no named manifest; deterministic 50/58 + DETERMINISTIC_AUTO=49 unchanged
ELSE:
  REVIEW (default)   or   ABSTAIN (no placeable run, or a hard terminus conflict)
```

On promotion: render the **same** drawn stroke (no new geometry); status `AUTO_SELECT`; provenance
`SOURCE_BACKED_TERMINUS_AUTO` (distinct from `DETERMINISTIC_AUTO`); record which two printed notes bound the
endpoints (auditable).

## 5. Fixtures required before implementation (name-free synthetic first)

| Required class | Status | Action |
|---|---|---|
| both endpoints printed-bound, easy | ✅ `term-001` | reuse |
| one endpoint missing | ✅ `term-002` / `term-004` | reuse |
| ambiguous endpoint | ✅ `term-005` | reuse |
| bare station callout | ✅ `term-006` | reuse |
| false-positive nearby endpoint text | ✅ `term-007` | reuse |
| multi-sheet both-bound | ✅ `term-008` | reuse |
| **conflicting endpoint** (two source types disagree) | ❌ | **NEW** — full version needs the callout/matchline binders first; a single-type stand-in is possible |
| **matchline boundary case** (bilateral equation binds) | ❌ | **NEW** — needs the `MATCHLINE_BOUNDARY_STATION` binder |
| **reviewed vs unreviewed bore-log row** | partial (`pkg-011`) | **NEW** terminus pairing on the same plan |
| **correction-required generic placement + both-bound termini** | ❌ | **NEW (critical negative)** — proves geometry-uncertainty blocks AUTO even with bound endpoints |
| **low-confidence geometry + both-bound termini** | ❌ | **NEW (critical negative)** |
| **both-bound + sheet mismatch** | ❌ | **NEW (critical negative)** — binding sheet ≠ placement sheet ⇒ REVIEW |
| **the lone AUTO candidate**: both printed-bound + near-perfect geometry + zero rivals | ❌ | **NEW** — the single positive case |
| named-recognized regression guard | ✅ (frontier lock) | reuse the `50/58` lock |

## 6. Test plan for the future G4 implementation

- **Cold-package matrix before/after:** flag OFF ⇒ byte-identical 11/11; flag ON ⇒ **only** the lone proven
  candidate flips REVIEW→AUTO, every other fixture byte-identical (clear pass/fail).
- **Terminus evidence tests:** the existing terminus fixtures + new binders' own correctness suites (each new
  source-type binder uniqueness-gated like the structure note).
- **AUTO-candidate tests:** the proven case promotes; provenance `SOURCE_BACKED_TERMINUS_AUTO`; render artifacts
  identical to the REVIEW render (same geometry).
- **Negative battery (the heart of it):** one-bound, ambiguous, conflicting, bare-callout, offset/false-positive,
  KMZ/inferred/absent, partial-geometry, sheet-mismatch, low-confidence — each **stays REVIEW/ABSTAIN** with the
  flag ON.
- **Frontier lock:** `50/58` + `DETERMINISTIC_AUTO=49` green with the flag ON (named path provably untouched;
  byte-identity assertion on the named manifests).
- **Full v2 suite** green.
- **Guardrails:** no recognized/work corpus as proof; no Hector active corpus; name-free guards (`NAME_TOKENS` +
  AST) extended to any new module; **no renderer/georef/map-overlay change** (AUTO is the same stroke with a
  different status label); default-OFF flag mounting test.

## Highest-risk areas

1. **Geometry-vs-endpoint gap (deepest):** two source-bound endpoints prove the endpoints, not that the selected
   polyline *is* the bore. Mitigation = the strict geometry gate (zero rivals, near-perfect coverage, run endpoints
   coincide with the bound endpoint *positions*) — but this is the riskiest leap and the reason the generic lane
   caps at MEDIUM today.
2. **Single-source-type fragility:** the extractor binds only `PRINTED_STRUCTURE_LABEL` now. "Both source-bound"
   rests on one evidence type until the callout/matchline binders exist — each of which can itself mis-bind.
3. **Observer-only guarantee removal:** G4 is the first time terminus evidence affects placement; the
   forbidden-import test gets replaced by a narrow, flag-gated, heavily-tested seam. The safety model changes.
4. **Sheet/offset drift:** the extractor reads `plan.lines(sheet, 0)` (offset 0) while placement uses the dialect's
   calibrated offset — a mismatch could bind an endpoint on the wrong page. The `TERMINUS_SHEET_MISMATCH` gate must
   reconcile this explicitly.
5. **Deterministic-frontier regression:** must be *provably* isolated to `dialect == generic`; a byte-identity test
   on named manifests with the flag ON.
6. **Single-corpus thresholds:** `_GENERIC_MAX_CONF` is self-described "PROVISIONAL — validated on one corpus
   (ODOT)." Any AUTO geometry threshold inherits that fragility.
7. **Synthetic-only evidence:** the terminus fixtures are synthetic and clean; real plans are messy (the reason for
   the MEDIUM cap). AUTO validated only on synthetic fixtures would be unsafe.

## Recommendation: NOT safe to implement G4 yet — more fixture/binder work first

The design is sound and the gate is narrow, but two preconditions are unmet:

1. "Both source-bound" currently means a *single* evidence type (`PRINTED_STRUCTURE_LABEL`); either scope the first
   slice explicitly to that one type **or** build the callout/matchline binders first.
2. The geometry-vs-endpoint gap is the core safety risk, and it does **not show up on synthetic plans** — it only
   appears on real, messy linework. AUTO must not be trusted until validated on real, diverse, name-free-able
   plans, plus the critical negative fixtures (both-bound + uncertain geometry / sheet-mismatch / conflicting) that
   prove the geometry and sheet gates actually block AUTO when endpoints are bound.

Suggested safe path: (1) add the critical negative fixtures and the lone positive candidate fixture (the G4
preflight bed); (2) validate the geometry-tightness gate on real plans (read-only, observer); (3) optionally build
one additional binder (callout or matchline) so "both source-bound" isn't single-type; (4) only then implement the
gate behind a default-OFF flag with the full negative battery + frontier byte-identity proof; (5) have the gate
spec adversarially reviewed before the flag is ever turned on.

---

*Parked separately — Hector v1-parity feedback (not part of this design):* v1-style redline info; depth and BOC
missing; stations clickable like v1; station-click full details. Build only on explicit owner hotfix.
