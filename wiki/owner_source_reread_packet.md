# Owner Source Re-Read Packet (OWNER-PACKET-1)

**Branch:** `feat/truelinev2` · **Engine HEAD:** `5f077fe` · **Date:** 2026-06-13
**Status:** owner-action packet · documentation only · no engine code · no deploy
**Scope:** the Brenham Phase 5 corpus (58 production bore logs, `log2..log72`)

---

## Executive summary

The TrueLine v2 engine has extracted every redline it can deterministically
place from the **printed** Brenham plan evidence, under strict zero-false rules
(it never places a redline it cannot prove, and it never guesses). Of the 58
bore logs:

- **30** place a product redline now (`DRAWABLE_REVIEW`).
- **23** more are review-ready today as pick-cards or length-adjustable redlines
  (**53 review-ready in total**).
- **5** are genuinely held pending owner/source work (the source/KMZ/owner set).
- **0** are blocked on missing engine doctrine at the product level.

Three consecutive engine investigations (M8.26 end-identity, M9.5 cross-sheet,
M9.8 structure-identity) each concluded the same way: **the printed evidence is
near-exhausted for new automatic solvers.** The remaining gap is not an engine
gap — it is a small set of **missing or contradictory source facts** that only
the owner can resolve.

This packet lists those facts, grouped by source issue. Each ask names exactly
what is missing, what the engine would do if the owner answers it, and what
would still require human review afterward. **Answering these asks is how we keep
driving the remaining abstentions and manual-review states toward deterministic
placement** — consistent with the all-redlines standard (manual placement is not
the product) and the do-not-widen rule (we never invent an answer to force a
placement).

---

## Why this packet exists

TrueLine's standard is that **every** redline from the source files should
ultimately be placed automatically. When the engine abstains or hands a human a
review card, that is a **safe interim state**, not the finished product — and
every such state is supposed to become a **named extraction target** until
placement is deterministic.

At the same time, the engine must **never place a wrong redline**. Where the
printed plan does not contain enough evidence to identify a bore's frame, end
structure, or sheet — or where two sources disagree — the engine correctly
abstains rather than guess.

The only honest way to convert those remaining abstentions into placements is to
recover the missing relationship. For the items in this packet, that
relationship lives in the **original bore-log source** or in an **owner
decision about which source is authoritative** — not in any new engine code.
Three recent engine studies confirmed this directly:

- **M8.26** — the 25 "end-identity-unprinted" bores were exhaustively probed;
  **no** zero-false end-identity gate exists in the printed plan, and **zero**
  bores moved. Honest negative.
- **M9.5** — a cross-sheet competing-departure mechanism was proven **feasible**
  but produced **zero** additional results on this corpus. Honest negative.
- **M9.8** — a structure-identity binder was proven **feasible**
  (`STRUCTURE_IDENTITY_BINDER_FEASIBLE_YIELD_1`), but its only result was the
  positive control (log12), `product_yield = 0`, and **zero bores promoted**.
  Effectively another honest negative for broad review reduction.

So the next yield comes from the owner side, not a new solver. That is what this
packet asks for.

---

## What "owner re-read" means

"Owner re-read" means: **go back to the original bore-log source document** (the
field/as-built bore log, not the engineering plan PDF or the KMZ) and confirm,
for the named bores, the facts the engine could not derive from the printed
plan:

- the **stations** (start and end) the run was actually drilled to,
- the **endpoints** (where the run begins and terminates),
- the **length** of the run,
- the **sheet / print reference** the run belongs to, and
- where a **plan and KMZ disagree**, which one is **authoritative**.

It does **not** mean re-drawing or hand-placing redlines. It means supplying the
missing or corrected source fact so the engine can place — or so the review card
can be confirmed — deterministically. Where the owner has no new fact to give,
that is a valid answer too: it tells us the item correctly stays a review item
rather than an engine target.

---

## Table of owner asks

| # | Issue group | Affected logs | Current engine status | Missing / contradictory source evidence | Exact owner action requested | What unlocks if answered | What still remains review-by-design |
|---|---|---|---|---|---|---|---|
| 1 | Unparseable bore source | log37, log38 | `SOURCE_REVIEW_REQUIRED` (`BORE_SOURCE_UNPARSEABLE`) — not yet placeable | The bore log itself has **no parseable stations**; no join key to plan or KMZ | Re-key / confirm the original bore logs' stations, endpoints, and length | A parseable source lets the engine attempt the normal disposition (placement or a review lane per the printed evidence) | Nothing engine-specific — once parseable, these flow through the normal lanes |
| 2 | bore_log17 source-vs-plan / printed void | log43, log44 | `OUT_OF_CLASS` → `SOURCE_OR_KMZ_REQUIRED` (`END_IDENTITY_UNPRINTED`) | log43: drawn axis stops at 45+33; **45+33→59+19 is a 1386-ft printed void**. log44: **325-ft span matches no print-18 run** (source-vs-plan mismatch) | Re-read the original bore_log17 source; confirm intended stations, length, and source context (single vs multi-drive; which print the run belongs to) | log44 could become a KMZ endpoint-bridge candidate (its terminals exist in the KMZ); log43's end could become locatable once the void/multi-drive question is resolved — candidate paths, not guaranteed placement | If the corrected source still leaves the end unlocatable on the plan, the KMZ-corroboration (geo) lane is next — not manual placement |
| 3 | PDF ↔ KMZ contradiction | log46 | `PICK_CARD_REVIEW` (review-eligible now) | The PDF prints **`AP-161 SPLICE LOC 35`**; the KMZ records **`Splice Loc 45`** for the same terminal — two authoritative sources disagree | Confirm which source is authoritative for log46's terminal (35 or 45). The engine **cannot choose between conflicting sources without owner/source authority** | A confirmed splice-loc would let the KMZ terminal join bind log46's end to a unique terminal → frame ownership → the pick-card could then resolve toward deterministic placement (candidate path, not a guarantee) | If the corrected splice-loc still does not bind a unique terminal, the frame tie stays a pick-card |
| 4 | Missing matchline equation / no safe frame bridge | log68 | `OUT_OF_CLASS` → `SOURCE_OR_KMZ_REQUIRED` (`CROSS_SHEET_CONTINUATION_REQUIRED`) | The bore's sheets print **no matchline frame equation**; the trunk ladder reaches only to 6+79 but the computed start is 4+54, and no sheet shares a boundary tick to continue the axis. KMZ endpoints are non-terminal (no AP+splice id), so geo can't bridge either | Confirm the matchline equation, reference sheet, or source sheet needed to bridge log68's two frames safely | A uniquely-linked matchline equation would let the frame-equation graph translate stations across sheets safely → path continuity → could enable placement (candidate path, not a guarantee) | Without a printed equation or a terminal-bound endpoint, this stays a geo/KMZ-corroboration or pick-card lane |
| 5 | Sheets 19/20/21 print-column mis-scope | log52, log67, log69, log70 | `HUMAN_ADJUSTABLE_REVIEW` (length certain, frame/sheet placement ambiguous) | log69: proven path lives **entirely on sheet 21** but the print column references **19/20** (off-print). log67 & log70: the raw end also appears in **sheet 21's** ladder. log52: recorded rival is **sheet 10**, not 21 (see note) | Confirm whether these rows should reference **sheet 21 / off-print completion**, or provide the corrected sheet references | A confirmed print-scope value would enable the engine to place the redline on the correct sheet deterministically instead of holding it as human-adjustable (candidate path pending owner confirmation) | If a row genuinely spans sheets with no structure identity, the human-adjustable lane is correct until a structure identity is found |
| 6 | Contested-frame / containment-only end | log29, log31, log47, log53, log71 | `PICK_CARD_REVIEW` (review-eligible now) | In each, the bore's **raw END station number recurs in one or more other frame ladders**, so a raw number alone cannot pick the frame (no positive end evidence in the supported frame itself) | Identify the exact missing endpoint/source evidence (an end-structure identity, or a corrected print reference) for each, to make the placement deterministic | A printed end identity for any of these could resolve the frame tie → deterministic placement instead of a pick-card (candidate path pending owner clarification) | Where no end identity is printed and the source can't supply one, the pick-card (human picks the frame) is correct zero-false behavior |
| 7 | Doctrine-irreducible / review-by-design | log48, log54, group card log8+log32 | log48 `PICK_CARD_REVIEW`; log54 `HUMAN_ADJUSTABLE_REVIEW`; log8 & log32 **already place** their redline (`DRAWABLE_REVIEW`) + a separate group card | Not a missing datum — a genuine **printed fork** (log48: two real parallel runs), an **irreducibly ambiguous frame** (log54: end recurs in 7 ladders), or an **owner adjudication** (log8/log32 multi-drop grouping) | For log48/log54: supply a decisive end-structure identity **if one exists** in the source. For log8/log32: make the multi-drop grouping decision (confirm/reject) | A decisive new source fact could collapse log48/log54 to deterministic placement; the log8/log32 grouping is unlocked by the owner's decision, not the engine | Absent a new decisive fact, these correctly remain review-by-design — not a manual fallback, not an engine bug |

> **Note on log52 (Group 5):** the engine's recorded competing frame for log52
> is **sheet 10**, not sheet 21. It is grouped here because it is the same class
> of question — a length-certain redline whose sheet/frame placement needs a
> print-scope confirmation. If the owner believes log52 also completes off-print
> on sheet 21, that is exactly the source clarification this ask is requesting;
> if not, the corrected sheet reference resolves it.

---

## Issue groups in detail

### 1 — log37 / log38 · unparseable bore source

**Engine status:** both are `SOURCE_REVIEW_REQUIRED` with stroke status
`BORE_SOURCE_UNPARSEABLE` — the two SOURCE_REVIEW_REQUIRED bores in the corpus.

**What the engine sees:** the bore log has **no parseable stations**. There is
nothing for the engine to attempt — no station chain, no endpoints, and no key
to join the run to the plan or the KMZ.

**Owner ask:** re-key or confirm, from the **original** bore logs, the run's
start/end **stations**, its **endpoints**, and its **length**.

**What unlocks:** with a parseable source, the engine can run log37/log38 through
the same pipeline as every other bore and reach whatever disposition the printed
evidence supports (a placement, a pick-card, or a length-adjustable redline). We
do **not** assume the result will be an automatic placement — only that the run
becomes evaluable.

**Remaining review-by-design:** none specific to these two — they are purely
source-blocked today.

---

### 2 — log43 / log44 · bore_log17 source-vs-plan / printed void

Both are children of the same source family (`bore_log17`); both are
`OUT_OF_CLASS` → `SOURCE_OR_KMZ_REQUIRED` (stroke status
`END_IDENTITY_UNPRINTED`). They abstain for **different** reasons:

- **log43 (print 10, 40+00 → 59+19) — long-span / printed void.** The drawn axis
  on print 10 stops at **45+33**. The stretch **45+33 → 59+19 is a 1386-ft
  printed void**: the bore end 59+19 is neither a drawn axis tick (the nearest
  tick is 1386 ft away) nor inside any drawn tick ladder on the bore's sheets.
  The reading that log43 "continues bore_log16" does not hold (log16 ends 39+79),
  which points to a **discontinuous / multi-drive source**.
- **log44 (print 18, 0+00 → 3+25, 325 ft) — source-vs-plan mismatch.** The
  **325-ft span matches no print-18 run**. The end falls inside two
  distinct-class intervals (a 503-ft 1-1.25" run and a 68-ft 2-1.25" run), so
  coverage alone cannot pick one.

**Owner ask:** re-read the **original bore_log17 source** and confirm the
intended **stations**, the **length**, and the **source context** — in
particular whether this was a single continuous drive or a multi-drive, and
which print each segment belongs to.

**What unlocks:** for **log44**, a corrected source would make it a viable **KMZ
endpoint-bridge candidate** (its terminals are present in the KMZ); for
**log43**, a corrected source would resolve the 1386-ft void / multi-drive
question so the end could be located. This is a candidate path — neither
guarantees automatic placement until the relationship is actually extracted.

**Remaining review-by-design:** if a corrected source still leaves the end
unlocatable on the plan, the next route is **KMZ/geo corroboration**, not manual
placement.

---

### 3 — log46 · PDF ↔ KMZ contradiction

**Engine status:** `PICK_CARD_REVIEW` (review-eligible now). The bore's raw end
5+34 also appears in another frame's ladder (sheet 15), so one frame supports the
span but the end has no positive evidence of its own — a frame tie.

**The contradiction:** when the engine tried to break that tie using the KMZ
terminal join, it found that the two sources **disagree about the same
terminal**:

- the **PDF** prints **`AP-161 SPLICE LOC 35`**, while
- the **KMZ** records **`Splice Loc 45`**.

The engine surfaces this as a source contradiction and **abstains from choosing**
— it has no authority to decide which source is correct, and guessing would risk
binding the wrong terminal.

**Owner ask:** confirm which source is authoritative for log46's terminal — the
PDF's **SPLICE LOC 35** or the KMZ's **Splice Loc 45**. (Stated plainly: the
engine cannot choose between two conflicting sources without an owner/source
ruling.)

**What unlocks:** a confirmed splice-loc would let the KMZ terminal join bind
log46's end to a **unique** terminal, which would give the frame ownership the
pick-card is missing — moving log46 toward deterministic placement. This is a
candidate path, not a guarantee.

**Remaining review-by-design:** if the corrected splice-loc still does not bind a
unique terminal, the frame tie remains a pick-card (human picks the frame).

---

### 4 — log68 · missing matchline equation / no safe frame bridge

**Engine status:** `OUT_OF_CLASS` → `SOURCE_OR_KMZ_REQUIRED` (stroke status
`CROSS_SHEET_CONTINUATION_REQUIRED`) — the third SOURCE_OR_KMZ bore.

**What the engine sees:** the bore's path is discontinuous across sheets. The
trunk tick ladder containing the end reaches down only to **6+79**, but the
computed start is **4+54**, and **no sheet shares a boundary tick** to continue
the axis. The bore's sheets print **no matchline frame equation** (the printed
"STA a = b, SEE SHEET N" datum that lets the engine translate stations from one
sheet to another). The KMZ endpoints here are non-terminal drop structures (a
flower pot / installer HH with no AP+splice id), so the geo substitute cannot
bridge the gap either.

**Owner ask:** confirm the **matchline equation**, the **reference sheet**, or
the **source sheet** that bridges log68's two frames safely.

**What unlocks:** a uniquely-linked matchline equation would let the
frame-equation graph (the mechanism proven feasible in M9.5) translate stations
across sheets **safely** — by the exact printed offset, never by raw-number
guessing — to provide path continuity. This is a candidate path for placement,
not a guaranteed automatic placement.

**Remaining review-by-design:** without a printed equation or a terminal-bound
endpoint, log68 stays a geo/KMZ-corroboration or pick-card lane.

---

### 5 — sheets 19 / 20 / 21 · print-column mis-scope (log52 / log67 / log69 / log70)

All four are `HUMAN_ADJUSTABLE_REVIEW`: the redline **footage and station
interval are certain**, but the **sheet/frame placement** is ambiguous. The
shared concern is that rows referencing sheets 19/20 appear to complete on the
adjacent off-print **sheet 21**.

- **log69 — the canonical off-print case.** The proven path lives **entirely on
  sheet 21**, but the bore log's **print column references sheets 19/20**. The
  engine flags this as an off-print claim and abstains rather than place without
  print-scope evidence (a corrected print value, or a structure identity that
  owns the frame). Footage 454 ft; one frame plausible.
- **log67 — sheet-21 rival.** The raw end **4+14 also appears in sheet 21's
  ladder**. Footage 414 ft; two frames plausible.
- **log70 — sheet-21 rival.** The raw end **2+15 also appears in sheet 21's
  ladder**. Footage 215 ft; two frames plausible.
- **log52 — frame conflict, recorded rival sheet 10.** The raw end **4+50
  appears in sheet 10's ladder** (not sheet 21). Footage 352 ft; two frames
  plausible. It is grouped here because it is the same kind of
  print-scope/frame-disambiguation question; see the note below the table.

**Owner ask:** confirm whether these rows should reference **sheet 21 / off-print
completion**, or provide the **corrected sheet references**.

**What unlocks:** a confirmed print-scope value would enable the engine to place
each redline on the **correct sheet deterministically** instead of holding it as
a human-adjustable redline — a candidate path pending the owner's confirmation.

**Remaining review-by-design:** where a row genuinely spans sheets without a
printed structure identity, the human-adjustable lane is the correct behavior
until such an identity is supplied.

---

### 6 — log29 / log31 / log47 / log53 / log71 · contested-frame / containment-only end

All five are `PICK_CARD_REVIEW` (review-eligible now). In each, the bore's **raw
END station number recurs across more than one frame ladder**, so a raw station
number cannot, by itself, pick the correct frame — the engine surfaces a
pick-card rather than guess:

- **log29** — end **4+15** also lies in frames 11 and 12; the supported frame
  holds the span, but the end has no positive evidence of its own
  (containment-only end).
- **log31** — end **2+60** also lies in frames 11, 12, and 13 (containment-only
  end).
- **log47** — the supported frame (sheet 10) is **contested** by rival frames 11
  (axis tick 5+00), 12, and 15; end **4+94** appears in four other ladders.
- **log53** — the supported frame (sheet 5) is **contested** by rival sheet 6
  (axis tick 24+11); end **24+11**.
- **log71** — the supported frame (sheet 23) is **contested** by rival sheet 24
  (axis tick 6+94); end **6+95**.

**Owner ask:** for each, identify the exact missing endpoint/source evidence — a
**printed end-structure identity** (a terminal / AP / splice at the end), or a
**corrected print reference** — that would let the engine pick the correct frame
deterministically.

**What unlocks:** a printed end identity for any of these could resolve the frame
tie and enable deterministic placement instead of a pick-card — a candidate path
pending the owner's source clarification.

**Remaining review-by-design:** where no end identity is printed and the source
cannot supply one, the pick-card (a human picks the frame) is the correct
zero-false outcome.

---

### 7 — log48 / log54 / group card log8+log32 · doctrine-irreducible (review-by-design)

These are **not engine bugs and not parser failures.** The engine has read the
printed evidence correctly; what remains is a genuine printed fork, an
irreducible ambiguity, or an owner adjudication that — **by design** — a human
resolves, unless the owner has a **decisive new source fact** to supply.

- **log48 — a real printed fork.** `PICK_CARD_REVIEW`. There are **two
  physically real PRINTED parallel runs** at the end; the run-identity
  tiebreaker is `NOT_READY` and a **banked human grade holds**. The end 5+09 also
  lies in frames 11 and 12. This is a true fork between two printed runs, not a
  missing datum. A decisive owner end-structure identity could break it;
  otherwise it correctly stays a pick-card (a human picks the run).
- **log54 — irreducibly ambiguous frame.** `HUMAN_ADJUSTABLE_REVIEW`. The
  **footage (314 ft) and interval are certain**, but the raw end **3+14 recurs in
  seven other frame ladders** (2, 5, 7, 17, 20, 21, 22) — the frame is maximally
  ambiguous. The redline length is known; the human adjusts the frame. A decisive
  owner end-structure identity would collapse it; otherwise it stays
  human-adjustable.
- **log8 + log32 — multi-drop grouping adjudication.** Both bores **already place
  their product redline** (`DRAWABLE_REVIEW`). The remaining review item is the
  separate **group card** (`truelinev2-shared-alignment-group-review-1`): two
  distinct printed runs over one drawn alignment, sharing the origin
  `NEXTLINK@378,409`, boundaries `1+76` / `1+77`. The owner **confirms or rejects
  the multi-drop / shared-origin grouping** — there is no source fact that
  auto-resolves it; it is an owner decision by design. (Separately, the
  proof-only route-following **stroke** for log8/log32 awaits an
  origin/structure-identity binder — that is **engine doctrine**, not an owner
  source ask, and it does **not** block their redline placement.)

**Owner ask:** for log48 / log54, supply a decisive **end-structure identity** if
one exists in the source (if none exists, these correctly remain review items);
for log8 / log32, make the **multi-drop grouping decision** (confirm or reject).

**What unlocks:** a decisive new source fact could collapse log48 / log54 to
deterministic placement; the log8 / log32 grouping is unlocked by the **owner's
adjudication**, not by the engine.

**Remaining review-by-design:** absent a new decisive fact, these remain
review-by-design — correct zero-false behavior, **not** a manual fallback and
**not** a sign the engine has stopped trying.

---

## Owner-facing checklist

Work through these in any order; each is independent. Where you have no new
source fact, mark it "no change" — that is a valid, useful answer.

- [ ] **log37, log38** — re-key the original bore logs: confirm start/end
  stations, endpoints, and length (they currently have no parseable stations).
- [ ] **log43** — confirm whether 40+00 → 59+19 is one continuous drive or a
  multi-drive; clarify the 45+33 → 59+19 stretch (currently a 1386-ft printed
  void).
- [ ] **log44** — confirm the intended run for the 325-ft span (it matches no
  print-18 run as drawn); confirm stations and which print it belongs to.
- [ ] **log46** — rule which source is authoritative: PDF **SPLICE LOC 35** vs
  KMZ **Splice Loc 45**.
- [ ] **log68** — provide the matchline equation / reference sheet / source sheet
  that bridges its two frames (its sheets print no matchline equation).
- [ ] **log52, log67, log69, log70** — confirm whether these reference sheet 21 /
  off-print completion, or provide corrected sheet references (log69 in
  particular: path proven on sheet 21, print column says 19/20).
- [ ] **log29, log31, log47, log53, log71** — supply an end-structure identity or
  corrected print reference at the bore end where one exists (each has a raw end
  station shared across multiple frames).
- [ ] **log48** — supply a decisive end identity if the source distinguishes the
  two parallel runs; otherwise confirm it remains a human pick.
- [ ] **log54** — supply a decisive end identity if one exists; otherwise confirm
  it remains a human-adjustable redline.
- [ ] **log8 + log32** — make the multi-drop / shared-origin grouping decision
  (confirm or reject). Their redlines already place; this is the grouping card
  only.

---

## Internal proof references / traceability notes

Every status, station, and number in this packet is transcribed from the current
shipped truth surfaces at engine HEAD `5f077fe` — no value is inferred or
invented, and no owner answer is assumed.

- **Per-bore product status, buckets, and missing-evidence strings** —
  `wiki/m8_27_final_engine_truth_table.md` and the full 58-row table
  `data/outputs/final_engine_truth_table/final_engine_truth_table.md` (proof
  `truelinev2/proof/run_final_engine_truth_table.py`, G1–G15 PASS; adversarially
  audited FAITHFUL). Buckets: 30 `DRAWABLE_REVIEW` / 17 `PICK_CARD_REVIEW` / 6
  `HUMAN_ADJUSTABLE_REVIEW` / 3 `SOURCE_OR_KMZ_REQUIRED` / 2
  `SOURCE_REVIEW_REQUIRED` (+ 1 group card).
- **Per-bore abstain reasons** (rival frames, contested frames, the log69
  off-print string, the log43 1386-ft void, the log44 two-interval split) —
  `data/outputs/station_axis_interval_containment.md` (M8.7) and
  `data/outputs/station_axis_interval_optin_sweep.md` (M8.8).
- **log43 / log44 source-quality closure** —
  `wiki/m8_25_log17_family_abstain.md` (proof
  `run_log17_family_abstain_probe.py`, G1–G7 PASS).
- **End-identity honest-negative (Groups 5–7 context)** —
  `wiki/m8_26_end_identity_population_honest_negative.md` (proof
  `run_end_identity_population_probe.py`, G1–G6 PASS); the per-bore
  missing-evidence list is in
  `data/outputs/end_identity_population_probe/end_identity_population_probe.json`.
- **log46 PDF↔KMZ contradiction and log68 no-equation rejection** — M9.3 /
  M9.3.1 terminus attribution (`wiki/m9_3_terminus_attribution_phase0.md`,
  `wiki/m9_3_1_terminus_attribution_extractor.md`); log46 = PDF `AP-161 SPLICE
  LOC 35` vs KMZ `Splice Loc 45`.
- **Cross-sheet feasibility, zero yield (why a new solver is not the answer)** —
  `wiki/m9_5_cross_sheet_competing_phase0.md` (`SAFE_FRAME_GRAPH_EXTENSION_FEASIBLE`,
  zero corpus yield).
- **Structure-identity binder feasibility (engine headroom near-exhausted)** —
  `wiki/m9_8_structure_identity_binder_phase0.md`
  (`STRUCTURE_IDENTITY_BINDER_FEASIBLE_YIELD_1`, `product_yield = 0`, zero bores
  promoted).
- **Blocker-class rollup** — `HANDOFF.md` (Remaining Blocker Classes).

**Boundary.** This packet changed no engine code, no contracts, no buckets, no
census (frozen `25/13/5/5/4/3/1/2 = 58`), and no flags. It is owner-facing
documentation only. It does not place, draw, or move any redline; it names the
source facts required before deterministic placement.
