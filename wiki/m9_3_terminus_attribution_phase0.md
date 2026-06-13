# M9.3 Phase 0: START/END terminus-attribution — feasibility proof (POSITIVE)

Status: **PROOF-ONLY / READ-ONLY; no extractor shipped; zero bores moved;
adversarially audited (defects fixed pre-commit).** Answers the M9.2-named missing
relationship — attribute a printed `AP-NNN SPLICE LOC MM` callout to a SPECIFIC bore
ENDPOINT, not just a sheet. The M8.27 census, product lanes, and M9.0/M9.1/M9.2
results are untouched.

Runner: `truelinev2/proof/run_terminus_attribution_phase0.py` (G1–G11 PASS)
Tests: `truelinev2/tests/test_terminus_attribution_phase0.py` (11; offline pure +
posture; live facts gated in the runner)
Report (gitignored, regenerable):
`data/outputs/terminus_attribution_phase0/terminus_attribution_phase0.{json,md}`

## The attribution law

An `AP-NNN SPLICE LOC MM` pair is **ENDPOINT_ATTRIBUTED** to a bore's END iff:
1. the bore's END station carries exactly one structure note
   (`structure_anchor.bind_end_structure_note`, uniqueness-mandatory);
2. that note's class (`_classify_label`, dialect-injected) is the terminal class;
3. exactly one AP+splice pair is **inside that note's own frame** (not merely on the
   sheet);
4. the pair cross-checks through the shipped M9.1 join cleanly (BOUND / NONE; a
   rejection → `PDF_KMZ_CONTRADICTION`);
5. corpus invariant: each terminal anchors **at most one** bore END.

**DIRECTION (the M9.3-audit fix, load-bearing):** a `terminal_port_hh` is
**end-of-feed** (it carries the arriving bore's TERMINAL TAIL). A terminal at a bore
**START** is the *prior* feed's terminus — the bore departs that junction — so it is
a **`JUNCTION_ORIGIN`**, never the START bore's identity.

**Not a flat scan:** an independent `_ap_owning_stations` map assigns every printed
AP to the note frame that owns it (run-callout / equation lines reset the frame). A
flat-scan AP owned by neither endpoint is a **`SHEET_NEIGHBOR_REJECTED`**. G7 asserts
the frame-bind and the owning-station map **agree** on every attribution.

## Result (all-58, read-only)

Endpoint census (start+end): **7 ENDPOINT_ATTRIBUTED / 3 JUNCTION_ORIGIN / 1
PDF_KMZ_CONTRADICTION / 31 NO_AP_SPLICE_PAIR / 70 NO_ENDPOINT_NOTE**.
Bore disposition: **7 attributed / 3 junction / 1 PDF↔KMZ contradiction / 1
source-contradiction (log44) / 44 sheet-neighbour-rejected.**

**7 clean terminal-END attributions — each KMZ-join BOUND to a unique terminal:**
log42→AP-105, log72→AP-117, log12→AP-121, log2→AP-148, log10→AP-152, log57→AP-157,
log7→AP-163. (log7/log10/log42 are the M9.0/M9.1 ground-truth controls; the other
four cross-bind BOUND via the two-field join.)

**3 bore-to-bore junctions** (a START at a prior feed's terminus — useful for a
future run-assembly lane, but *not* the START bore's identity): log27 START @ AP-152
(owned by log10's END), log39 START @ AP-117 (owned by log72's END), log65 START @
AP-163 (owned by log7's END).

**1 PDF↔KMZ contradiction surfaced (the proof's value-add):** log46 END prints
`AP-161 SPLICE LOC 35`, but the KMZ terminal AP-161 carries `Splice Loc 45`
(`JOIN_AP_ONLY_REJECTED`). Not a safe anchor → owner source re-read.

**Targets:** log10 END = positive single-anchor (AP-152, BOUND); log68 = the
sheet-neighbour rejection (its flat-scan AP-148 owns STA 20+71 — log2's terminal —
not log68's 4+54→7+21); log7/log42 = controls preserved; log44 = source-contradiction
(banked M8.25/M9.0, not re-derived).

## Confidence (honest)

**Typed + controls-verified, NOT "proven zero-false."** 3 of the 7 clean ENDs are
independently ground-truthed; all 7 cross-bind BOUND through the M9.1 two-field join
(a printed-id consistency check — the splice-loc agreement is the load-bearing
zero-false discriminator — but not, by itself, independent endpoint ground truth).
The uniqueness invariant (G8) + the two-method agreement (G7) close the double-booking
and proximity gaps.

## Ship recommendation — DEFER to M9.3.1

Phase 0 proves the law boundary; it does not ship (matching M9.0→M9.1). The
relationship is sound where it counts. Before promotion, the M9.3.1 **core** module
MUST inject the **note-detection keyword set** (`structure_anchor._STRUCTURE_WORDS`
is a shared-core literal today — the one universality blocker) and the
AP/splice/station grammars (the runner re-declares them locally in `proof/`);
classification via `class_keywords` is already injected. Promote the **END-direction
rule** and the **one-terminal-per-END uniqueness invariant** as core gates.

## Named evidence targets

1. **M9.3.1** — a convention-agnostic core attribution module (inject the note
   keywords + grammars; END-direction rule; uniqueness invariant).
2. A **run-assembly lane** that consumes the 3 junctions (e.g. log10 END = log27
   START at terminal AP-152 proves bore-to-bore continuity).
3. Owner source re-reads: **log46** (AP-161 PDF SPLICE LOC 35 vs KMZ 45) and
   **log44** (325′ source-vs-plan, M8.25) before any KMZ anchor.

## Adversarial audit

5 refutation lenses (false-positive, false-negative, join-consistency,
guards/drift/universality, overclaim). The first pass **refuted the initial draft**:
3 START-side terminal bindings were false positives (the direction defect), log46 was
silently tallied despite a join rejection, and G7 was vacuous. All fixed pre-commit;
the corrected model re-passes G1–G11 and the false-negative/guard lenses confirmed no
missed attributions and a clean read-only posture.
