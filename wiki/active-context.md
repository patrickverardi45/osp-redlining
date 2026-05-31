# Active Context (load this FIRST — keeps /start-session cheap)

> Compact session bootstrap. Read this before hot.md/current-sprint/log/current-bugs.
> Those big logs are historical truth — open them only when a specific question needs them.

## Repo state
- Branch: `pdf-ap-route-shadow`
- `origin/main` = `ed0f40c` (local HEAD tracks it). PDF-extraction chain shipped: Targets #18–#39 pushed. **#37 = first extractor fix: Primitive-A phantom-competitor gate → AP-164 PROMOTE_TRUSTED + AP-155 recovered; 9 confirmed endpoints, precision 1.00, recall 0.90.** **#38/#39 = bore_log57: terminus UNIQUELY AP-157 (alt resolver, no .FS), but placement HARD_BLOCKED on geometry (route_465 741ft vs bore 413ft) — frontier = 1 placeable bore (bore_log7).** #35 AP-160 KEEP_TRUSTED_REVIEW.
- Tree: tracked clean; untracked diagnostics live in `scripts/` (offline probes, *_replay.py, bore_log7_*).

## Mission (non-negotiable)
Deterministic auto-placement of **ALL** redlines from source files. Manual placement is NOT the product.
**DO-NOT-WIDEN**: never place a wrong redline. Abstention = interim safety state + a *named* extraction
target. Drive abstentions to zero by EXTRACTING the missing relationship from the source files — not by
guessing, and **not by asking a human to decide from vibes**. Human review is FINAL AUDIT ONLY; the
PDFs/maps/KMZ/bore-logs are the authority.

## Last shipped
- **Target #14 `20cb32f`** — `TRUELINE_TERMINAL_TAIL_PLACEMENT` (default-OFF). First redline-moving
  proof: bore_log7 moves route_477 → route_469 when ON; only bore_log7 changes; counts + trust ledger
  (34/30/0/0/5) identical OFF and ON; adversarial SAFE.
- **Target #15 `42f58f6`** — docs-only GAC review packet `gac/bore_log7_ground_truth_review.md`.

## Active flags — ALL default-OFF, NONE flipped on Render
`TRUELINE_TERMINAL_TAIL_PLACEMENT` (requires `TRUELINE_TERMINUS_TYPE_SHADOW`), `TRUELINE_TERMINUS_TYPE_SHADOW`,
`TRUELINE_MRQ_PLACEMENT_PROOF`, `TRUELINE_BACKBONE_CHAIN_SHADOW`, `TRUELINE_PDF_AP_TOPOLOGY_V2`,
`TRUELINE_PDF_AP_EXTRACT_V2`, `TRUELINE_MRQ_PLAN_SHEET_GRAPH_EVIDENCE`.

## Forbidden lanes (this mission)
Do NOT: widen `TRUELINE_TERMINAL_TAIL_PLACEMENT`; flip any Render flag; clean Render storage (unless
uploads are actively blocked); drift into auth, UI, broad PDF interpreter, KMZ Stage B3, densification
near-ties, or screenshot-tooling plumbing.

## Exact next redline action
**bore_log7 = ADJUDICATED + SHIPPED-as-shadow.** route_469 PROVEN from source (`gac/bore_log7_route_adjudication.md`);
DrillPathFrame proof layer shipped default-OFF (Target #18 `93434cd`, `TRUELINE_DRILL_PATH_FRAME_SHADOW`).
Operator-side next (NOT this session): final-audit, then flip `TRUELINE_TERMINAL_TAIL_PLACEMENT`
(+`TRUELINE_TERMINUS_TYPE_SHADOW`) on Render — engine path already shipped, no code change.

**DROP lane (bore_log5/30/48/50/65) = BLOCKED, fully diagnosed (Target #20).** No unique drop-identity
key exists in the files: flower-pot KMZ nodes are vacant/identity-less (no name/SCID/address), drop routes
carry only "Connection Type", each pot touches 2–6 drop routes, PDF flower-pot callouts carry no unit id.
NEW finding: the KMZ `<description>` HTML (parser currently DROPS it) carries House Address + AP Number +
Terminal-Port-HH AP Number — rich, but does NOT bind vacant flower pots. Missing artifact (any one closes it):
flower-pot SCID/address in KMZ, OR the `.FS` drive-decomposition sheet, OR a served-address column in the
bore xlsx. Helper `resolve_flowerpot_drop_identity(...)` is DESIGNED (abstain-until-key), not built. Full:
`gac/drop_lane_flowerpot_identity.md`. DO-NOT-WIDEN: drops abstain until a key arrives.

DrillPathFrame bucket review (Target #19, `gac/drill_frame_bucket_review.md`): 1 PROVEN (bore_log7), 13
BLOCKED; overlap detector = 58 unproven_overlap pairs (print-index stacks 11 logs on route_477, 3 on route_478).

**MAIN-CHAIN lane (bore_log16/43) = BLOCKED, PARTIAL probe (Target #22).** Corrects Target #21 §5.1: the
matchline-equation network is ALREADY EXTRACTED (`brenham_plan_sheet_graph.py` — boundary STA equations
1625→3393, SEE-SHEET corridor graph), so it is NOT the missing piece. Real blocker = a **station↔geometry
anchor** at the bores' high stations (4000–5950): the graph is station-space only (zero lat/lon); the only
station→KMZ bridge is a named AP in `BRENHAM_PH5_RUN_ENDPOINTS`, whose max named-AP station is 3810 (max of
ALL table stations 4533) — far below the bore ends 5919/5950, so NO anchor exists. Self-validation: the
mechanism reproduces bore_log7 (sta 451→AP-163→route_469) but finds NONE near 5919/5950. Missing artifact
(absent, not un-extracted): one high-station named/identified structure that is also a KMZ node + a direction
datum (or the `.FS` sheet, or a start-structure xlsx column). Full: `gac/mainchain_matchline_chainage_probe.md`.
DO-NOT-WIDEN: bore_log16/43 abstain until an anchor arrives.

**REMAINING route_480 logs (57, 29/31/46/47/58) = BLOCKED, 0/6 provable (Target #23).** bore_log57 =
multi_drive_terminus_ambiguous (END 413 hits AP-157 sheet-8 AND a sheet-13 matchline@398; spans 2 corridors;
print mapping flagged uncertain). bore_log29/31/46/47/58 = no_run_terminus_match (continuous multi-drive bores;
END station hits no DIR.BORE run terminus within 15 ft; bore_log46's 534=AP-161 LABEL not a run terminus →
excluded). Missing artifact (all 6) = the **`.FS` Fiber-Schematic / drive-decomposition sheet** (absent from all
3 PDFs; re-confirmed by #22 sweep) OR a per-bore terminus/direction field. Full: `gac/route480_remaining_proof_sweep.md`.
**Bucket closeout: all 14 route_480 logs classified — 1 PROVEN (bore_log7), 13 BLOCKED on 3 acquisition artifacts
(flower-pot identity key / high-station anchor+direction / `.FS` drive-decomposition). No bucket log is provable
from current files.** DO-NOT-WIDEN intact.

**EXISTING-CORPUS HUNT (Target #24) — relationship NOT FOUND, full-inventory proof.** Reopened the "ask for files"
conclusion and searched the COMPLETE corpus (not just 3 PDFs): 6 source classes — **71 bore xlsx** (incl. 13
pre-split originals, all 0 non-standard columns), the **80-pg Fieldwire punch-list** (holds a **63-entry `AP→.FS`
page register** + `AP→.WP` + item/date, but **0 bore_log mentions, 0 AP↔STA lines**; the `.FS` PAGES themselves are
absent — only references), the **539-route context JSON** (pure geometry, 0 structure tokens), the design KMZ
(flower pots id-less, Target #20), and TrueLine's own golden fixtures. **Bore lineage (station/crew/date/print) and
structure lineage (AP/.FS/.WP/SCID) share NO join key in ANY file** — the single missing edge is `bore↔AP/structure`.
0/13 blocked logs gain an extractable relationship. No code target extracts these from current files. Full:
`gac/target24_existing_corpus_artifact_hunt.md`. DO-NOT-WIDEN intact.

**AP/STRUCTURE-INDEX SHADOW (Target #25) — BUILT, read-only, placement-free.** Pre-joined the structure-SIDE facts
we DO have into a deterministic reusable per-AP index (`scripts/ap_structure_index.py` pure helper +
`scripts/ap_structure_index.json` artifact; isolated in scripts/, no engine import, no flag). Coverage over **64 APs**:
lat/lon **64/64** (every AP geometry-anchor-ready), `.FS` page 63/64, terminal-tail route 48/64, station 10/64, all-four
**8/64** (154/156/157/164/165/166/167/168). Places NOTHING and makes no bore↔structure claim (Target #24 invariant
respected) — it's the catcher so the instant ONE bore→AP/structure clue arrives, that bore resolves to lat/lon (+tail
+station+.FS) with zero re-mining. Self-test `python scripts/ap_structure_index.py selftest` → SELFTEST_OK. Full:
`gac/target25_structure_index_shadow.md`. Next unlock still gated on the single bore→AP edge. DO-NOT-WIDEN intact.

**PDF VISUAL EXTRACTION PATH (Target #26) — POSITIVE: relationship IS in the PDF, was an extraction failure.** The
plan sheets (8–14, pdf pp.21–27) visually encode each DIR.BORE run→structure via positioned text + a dense VECTOR layer
(sheet 10: 3233 lines + 7874 curves = leader lines + bored-run polylines). A **position-aware spatial nearest-label join
auto-reproduces known run-endpoints**: `STA 4+51→TERMINAL PORT HH` (AP-163) @13px, `STA 4+13→PORT` (AP-157) @14px — i.e.
the hand `BRENHAM_PH5_RUN_ENDPOINTS` table is derivable, not missing. Current extractor misses it because linear
text-order flattens (x,y) adjacency, the leader/polyline VECTOR layer is never read, and AP-number glyphs scramble (need
Target #1 char-stream V2). Concrete validated path: bore_log57 end 413 → sheet-8 join '4+13'→'PORT'=AP-157 → Target #25
index → lat/lon + tail route_465. Multi-drive logs (29 end 415 has 0 '4+15' callouts) need per-DRIVE run grouping
(Primitive B). NEXT IMPL TARGET: default-OFF read-only `extract_run_endpoints_from_sheet(page)` (Primitive A: spatial join
+ char-stream AP recovery, gated by equality vs the hand table). Still placement-free. Full:
`gac/target26_pdf_visual_relationship_extraction.md`. DO-NOT-WIDEN intact.

**PDF RUN-ENDPOINT EXTRACTOR (Target #27) — Primitive A BUILT + validated.** Pure default-OFF/read-only
`scripts/pdf_run_endpoint_extractor.py::extract_run_endpoints_from_layout` derives structure-side run endpoints from
plan-sheet layout (positioned STA callouts → nearest structure label → unique valid-AP digit-cluster, excluding the
station's own value, abstain on tie/beyond-tol; skip 0+00 run-starts). **Validation gate PASSES both: sheet 10 STA 451→AP-163,
sheet 8 STA 413→AP-157.** vs hand `BRENHAM_PH5_RUN_ENDPOINTS` (sheets 8/10 AP rows): **5/6 REPRODUCED** (154/156/157/165/163),
1 MISS (10,136,166 — abstained, needs Primitive B leader-following), 1 EXTRA (8,308,110 — candidate hand-table omission,
flagged not asserted); 0 wrong AP ids (all uncertain cases abstain); flower-pot/splice rows typed id-less (correct).
Self-test `… selftest` → SELFTEST_OK. Isolated in scripts/, no engine import/flag/STATE; placement-free. Output
`scripts/pdf_run_endpoint_extractor.{json,out}`. NEXT: Primitive B (leader-line following) + MATCHLINE exclusion + extend to
sheets 8–14, then feed the Target #25 index. Full: `gac/target27_pdf_spatial_run_endpoint_shadow.md`. DO-NOT-WIDEN intact.

**PDF LEADER/RUN CONNECTIVITY (Target #28) — Primitive B BUILT: validation + false-positive rejection.** Feasibility probe
proved the vector layer is followable (NOT hatch soup: largest page component ~244 nodes; callouts reach structure labels via
small isolable components). Pure `scripts/pdf_leader_run_following.py` builds a union-find component graph over page.lines+curves
endpoints, then binds the AP number that lies in the STRUCTURE LABEL'S OWN connected component (not nearest text). vs hand table
(sheets 8/10): **both gate cases PASS (451→163, 413→157 confirmed); TRUSTED (A+B agree) = 5/6 hand rows, 100% precision (0 wrong)**;
MISS (10,136,166) ABSTAINS with geometry reason (STA 1+36's local structure is AP-125, not 166 — 166 is the run's far end, not a
single isolable polyline); EXTRA (8,308,110) REJECTED as false positive (no valid AP in its component). Geometry candidates
(10,136,125 conflict / 162 / 3890 matchline) surfaced for REVIEW, not asserted. Self-test → SELFTEST_OK. Isolated/placement-free.
NEXT: MATCHLINE exclusion + a gated run-polyline tracer (Primitive C) for multi-drive far-end APs, then extend 8–14 + feed Target
#25 index. Full: `gac/target28_pdf_leader_line_run_following.md`. DO-NOT-WIDEN intact.

**PDF RUN-POLYLINE TRACER (Target #29) — Primitive C: AP-166 NOT recoverable (glyph floor), honest abstain.** Pure
`scripts/pdf_run_polyline_tracer.py` traces a callout's vector component to a far-end AP + adds matchline-label exclusion +
run-role classification (run_start/matchline/run_end/run_end_unresolved_ap/unrelated). **Headline: (10,136,166) NOT RECOVERED** —
AP-166 IS on the page (page-concat V2 reads 163/165/166) but forms NO positioned digit cluster (glyphs scramble), so there is no
geometry target to trace to → abstain reason `target_ap_166_not_spatially_localizable_glyph_scramble` (NOT guessing). Gate kept:
(10,451,163)+(8,413,157) PASS; (8,308,110) REVIEW/REJECTED; TRUSTED=5/6 hand rows 100% precision (Target #27/#28 NOT degraded).
Matchline label-proximity exclusion is conservative (caught 0 at safe 36px — MATCHLINE words are sheet-edge; 162/3890 candidates
already out of trust via confirmed-only gate); robust matchline detection should use SEE-SHEET/boundary-STA (brenham_plan_sheet_graph).
Self-test → SELFTEST_OK. Isolated/placement-free. NEXT: positioned AP-glyph reconstruction (recover scrambled AP numbers WITH
positions to give the tracer a target — the 136→166 unlock). Full: `gac/target29_pdf_run_polyline_tracer.md`. DO-NOT-WIDEN intact.

**POSITIONED AP-GLYPH RECONSTRUCTION (Target #30) — AP-166 LOCALIZED; glyph floor cleared.** Forensic: AP-166's chars ARE
present + ordered (clean '166' triples); Target #29's "scramble" was Primitive A's greedy clusterer OVER-MERGING dense AutoCAD
digits. Pure `scripts/pdf_ap_glyph_reconstruct.py::reconstruct_positioned_aps` recovers positioned AP targets via valid-AP-3-digit-
subsequence + STRUCTURE ANCHORING (TERMINAL/PORT/HH/AP within 34px) + station/dimension exclusion + ambiguous-run abstain.
**AP-166 LOCALIZED centroid [793.8,161.4]**; regressions AP-163/157/165 still localized; 0 false clusters; self-test SELFTEST_OK.
Endpoint 136→166 STILL not auto-recovered but blocker ADVANCED: AP-166 now a valid target but 45px from STA 1+36 in a SEPARATE
vector component (local structure is AP-125) → binding 166 over 125 = guessing → abstain (trusts NEITHER). Target #27/#28/#29
endpoint TRUST untouched. NEXT: component-bridge/run-polyline span (connect STA callout to a close-but-separate-component AP only
when ONE bored-run polyline spans the gap) — the final 136→166 unlock. Full: `gac/target30_positioned_ap_glyph_reconstruction.md`.
DO-NOT-WIDEN intact.

**COMPONENT-BRIDGE RUN-SPAN TRACER (Target #31) — 136→166 geometry-unprovable on sheet 10; honest floor.** Pure
`scripts/pdf_component_bridge.py::attempt_bridge` connects a STA callout to a localized AP target (Target #30 universe) via two
paths: `same_component_direct` (trusted Prim-B cases) or `bridge_single_run` (cross-component, ONLY if a single bored-run polyline
spans the gap: spanning component + not-hatch-soup + long run segment + DIR.BORE label in gap). **(10,136,166) ABSTAIN** — gap is
hatch soup (104 curves/7 lines/86% short), 0 DIR.BORE labels, no spanning component → 3 machine-readable reasons; bridging = guessing.
Gate kept: (10,451,163)+(8,413,157) ACCEPT via same_component_direct; AP-125 does NOT steal 136 (canonical AP-125 is 206px away — the
Target #28 "125-in-136-component" was a loose-cluster artifact, now removed); (8,308,110) stays review/rejected. FINAL trusted=5/6
hand rows, 100% precision, Target #27/#28/#30 NOT degraded; 0 unsafe bridges. Self-test SELFTEST_OK. The 136→166 run is simply not
RENDERED as a followable polyline on sheet 10 (hand-table value stands as reference, not re-derivable without guessing). NEXT:
cross-sheet/matchline run reconstruction + apply A→B→C→reconstruct→bridge chain to sheets 8–14 (capture geometry-provable endpoints).
Full: `gac/target31_pdf_component_bridge_run_span.md`. DO-NOT-WIDEN intact.

**SHEETS 8–14 ENDPOINT TABLE (Target #32) — chain scales: 7/10 endpoints, 100% precision on AP-terminal sheets, 0 wrong IDs.**
Driver `scripts/pdf_endpoint_table_8_14.py` runs A→B across sheets 8–14, trust=B-confirmed & not-matchline. **AP-terminal sheets
8–12: TP=7 (154/156/157/165/163/168/167), extra=0, PRECISION=1.00, RECALL=0.70, WRONG-ID=0.** 3 misses (9:3810→155 high-station;
10:136→166 unbridgeable; 12:355→164 adjacent-pair contamination — abstain, no mis-bind). Boundary sheets 13/14 (0 hand AP rows)
OVER-GENERATE 5 false APs (matchline/cross-ref numbers; label-proximity filter insufficient) → quarantined, NOT trusted-clean.
**7/7 trusted APs geometry-anchor-ready in Target #25 index.** AP-166 cross-sheet: only `…→166` is (13,389,166) at a sheet-13
MATCHLINE station → rejected; no boundary equation → **(10,136,166) NOT RECOVERED, abstained + STOPPED** (no loop). Self-test
SELFTEST_OK. Zero degradation of #27–#31 trusted cases. NEXT: stronger matchline/boundary exclusion (boundary-STA eqns + SEE-SHEET)
to lift overall precision 0.58→1.00; adjacent-AP disambiguation; feed the 7-endpoint table into the #25 index as auto-derived truth.
Full: `gac/target32_pdf_endpoint_table_sheets_8_14.md`. DO-NOT-WIDEN intact.

**CLEAN ENDPOINT TABLE + PLACEMENT READINESS (Target #33) — 7 trusted endpoints, precision 1.00, 0 wrong-id; bore_log7
re-derived + bore_log57 surfaced.** `scripts/pdf_clean_endpoint_table.py` strengthens trust to 4 corroborating gates
(B-confirmed ∧ Target#30 structure-anchored reconstruction ∧ full TERMINAL+PORT+SPLICE phrase ∧ not-matchline/edge).
**TRUSTED-CONFIRMED = the 7** (8:154/156/157, 10:165/163, 11:168, 12:167); 4 sheet-13 false APs EXCLUDED (3 not-reconstruction-
corroborated @ matchline sta 389/390/398; 1 no-phrase AP-151/HDPE); 1 TRUSTED-REVIEW (13,359,160 geom-valid but absent from
reference — adjudicate, NOT placement-trusted). All 7 → lat/lon + tail_route via #25 index, geometry_ready. **PLACEMENT READINESS:
bore_log7 (end 451,print10)→(10,451,163)→route_469 = PLACEMENT_READY (auto-table independently re-derives the proven placement);
bore_log57 (end 413,prints 8/10/13)→(8,413,157) = CANDIDATE (endpoint clean now, but multi-drive/uncertain-print per #23 → needs
drive disambiguation).** No placement performed (DO-NOT-WIDEN). Self-test SELFTEST_OK. NEXT: adjudicate (13,359,160); bore_log57
drive-disambiguation; future default-OFF placement shadow for PLACEMENT_READY bores. Full: `gac/target33_clean_endpoint_table_placement_readiness.md`.
DO-NOT-WIDEN intact.

**bore_log57 PLACEMENT CANDIDATE (Target #34) — structure side READY, bore→drive binding UNRESOLVED → ABSTAIN; no
override (would guess); bore_log7 control unchanged.** First trusted PDF-derived placement attempt beyond bore_log7.
`scripts/target34_bore_log57_placement_candidate.py` adjudicates the Target #33 PLACEMENT_READY_CANDIDATEs against the
bore_log7 proof shape — 4 gates: **G1** structure-side-trusted (unique confirmed endpoint + #25 geometry-ready) **∧
G2** single-corridor **∧ G3** no-competing-terminus **∧ G4** print-mapping-certain. **bore_log57: G1=T, G2=F, G3=F,
G4=F → ABSTAIN.** Structure side IS clean & geometry-ready: end 413 → unique (8,413,**AP-157**) → **route_465** @
(30.15819527,−96.38598520), coverage fs/station/latlon/tail all ✓ (more complete than proven AP-163). Bore side
unresolved on 3 independent machine-readable counts: `multi_corridor_span` (corridors [3-9,23,24] via print 8 vs
[10,12,13,14] via 10/13), `competing_unnamed_terminus_within_tol` (sheet-13 matchline@398, |413−398|=15 — #33 removed
it from the TRUSTED AP table but it still physically sits by the END), `print_mapping_flagged_uncertain` (notes: split
from bore_log24, "print mapping uncertain — preserved full source print '8,10,13'"). Binding AP-157 over the sheet-13
corridor = guessing → wrong-redline risk. Missing artifact = `.FS` drive-decomposition sheet OR a per-bore
terminus/direction field (Target #23/#24; absent) — once acquired this adjudicator resolves bore_log57→AP-157→route_465
with zero re-mining (G1 already green; the artifact flips G2-G4). **CONTROL bore_log7 re-verified PLACEMENT_READY →
route_469 (all 4 gates pass) — proven lane NOT degraded; gate calibration confirmed.** No placement, no override, no
flag/STATE/geometry; read-only; self-test SELFTEST_OK. NEXT: adjudicate the TRUSTED-REVIEW (13,359,160) (pure
structure-side, no bore dependency). Full: `gac/target34_bore_log57_pdf_derived_placement_candidate.md`. DO-NOT-WIDEN intact.

**AP-160 TRUSTED-REVIEW ADJUDICATION (Target #35) — KEEP_TRUSTED_REVIEW; real node, promote-grade geometry, but
uncorroborated → NOT promoted; 7 confirmed + bore_log7 untouched.** Adjudicated the lone Target #33 TRUSTED-REVIEW
endpoint (sheet 13, STA 359, AP-160). `scripts/target35_ap160_adjudication.py` gathers 5 structure-side axes via
Primitive A/B/C + #30 reconstruction + #25 index: **E1** AP-160 IS a real KMZ Terminal Port HH node (lat/lon
30.158369,−96.384328) but tail/station/sheet = None; **E2** Primitive-C role=**run_end**; **E3** Primitive-B
verdict=**confirmed** (comp_ap 160); **E4** zero geometry-derived matchlines, none within 40 ft of STA 359; **E5**
absent from literal-quote-verified `BRENHAM_PH5_RUN_ENDPOINTS`, which lists **0 sheet-13 AP run-endpoints** (treats
sheet 13 as boundary). So the AUTOMATED chain is promote-grade, but it's **uncorroborated by the hand reference on a
boundary sheet AND has no independent station/tail binding** → **KEEP_TRUSTED_REVIEW** (not REJECT — structure is real;
not PROMOTE — would widen placement-grade table on an automated-only signal = wrong-redline risk). Machine reason:
`geometry_promote_grade_but_uncorroborated_by_hand_reference_on_boundary_sheet_and_no_independent_station_tail_binding`;
promotion blocked until (a) literal-quote run-END verification on sheet 13 OR (b) a verified station/tail binding for
AP-160. No promotion artifact updated (stays in `review`; `confirmed` 7 unchanged). CONTROL: 7/7 confirmed re-validated
this run (control_ok). Self-test SELFTEST_OK. Full: `gac/target35_ap160_trusted_review_adjudication.md`. DO-NOT-WIDEN intact.

**AP-164 ADJACENT-PAIR "MISS" GATE (Target #36) — HARD_MISS (B-recovered-only); #32 "adjacent-pair contamination"
label CORRECTED; 7 confirmed + bore_log7 untouched.** Auto-continued from #35: adjudicated the only non-AP-166
extraction-quality recall gap that is a real hand-table run-endpoint — (sheet 12, STA 355, AP-164), recall 0.70 miss.
`scripts/target36_ap164_adjacent_pair_gate.py`: AP-164/AP-167 reconstructed centroids are **489 px apart** (NOT a
label-adjacency collision — the "5 ft" was station values 350 vs 355). Real mechanism: **Primitive A ABSTAINED at STA
355 (A_ap=None)** while Primitive B **recovered** AP-164 (comp_ap 164, full TERMINAL+PORT+SPLICE phrase, role run_end,
reconstructed, real KMZ node route_468). A∧B disagree → verdict=`recovered` not `confirmed` → the #33 gate excludes it
**by design** (confirmed-only). So AP-164 = a Primitive-B-recovered-only review candidate (analogous to AP-160/#35).
Two named recovery paths, both out of scope for a no-widen gate: (a) a VALIDATED Primitive-A fix at STA 355, OR (b) an
AUTHORIZED B-recovered trust-tier change. Classification `HARD_MISS_NEEDS_GUESS`; no promotion; precision stays 1.00;
recall honestly 0.70. CONTROL: AP-167@350 re-validated confirmed (control_ok). Self-test SELFTEST_OK. Full:
`gac/target36_next_pdf_endpoint_quality_gate.md`. NEXT (when re-authorized): focused Primitive-A abstention diagnosis at
STA 355 → would lift AP-164 to confirmed + recall 0.80, validated vs the 7. DO-NOT-WIDEN intact.

**PRIMITIVE-A STA355 FIX → AP-164 PROMOTED, RECALL 0.70→0.90 (Target #37) — first extractor code fix; precision 1.00,
0 wrong-id, baseline 7 + bore_log7 intact.** Root-caused #36's AP-164 miss: Primitive A abstained on a PHANTOM competitor
— a stray "110" digit cluster (coincides with a valid AP id, sits 42px from any TERMINAL/PORT label near a FLOWER POT;
real AP-110 node is ~900ft south) fell inside A's 1.4× distance margin → false `ambiguous_164_vs_110`. FIX in
[scripts/pdf_run_endpoint_extractor.py](scripts/pdf_run_endpoint_extractor.py) `_recover_ap`: a within-margin competitor
only blocks if itself terminal-port-anchored (≤18px of a TERMINAL/PORT word; real APs sit ~6px). New helper
`_terminal_port_anchored`; call-site passes TERMINAL/PORT words; legacy-exact when None. **Precision-safe (proven by
`scripts/target37_validation.py` legacy-vs-patched diff over sheets 8-14): ADDED None→ap only = {(9,3810,155)✓hand,
(12,355,164)✓hand, (13,245,158)→review}; REMOVED=[]; CHANGED-ID=[]; baseline 7 retained.** #33 grade now: **9
TRUSTED-CONFIRMED** (7 + AP-155 + AP-164), WRONG-ID 0, **precision 1.00, recall 0.90** (was 0.70); review = AP-158@245 +
AP-160@359. **AP-164 = PROMOTE_TRUSTED**; AP-155 bonus TP; AP-158 new review. Placement block UNCHANGED (bore_log7→AP-163
ready, bore_log57→AP-157 candidate); the 2 new endpoints add NO new bore match → recall up, zero wrong-redline exposure.
Extractor is scripts/-only (backend imports none — verified); no flag/STATE/geometry/placement/test touched. Selftest
extended (phantom-reject + true-tie) SELFTEST_OK. Full: `gac/target37_primitive_a_sta355_recovery.md`. NEXT: bore→drive
binding for bore_log57 (the #34 placement blocker). DO-NOT-WIDEN intact; (10,136,166) AP-166 glyph floor still out of scope.

**bore_log57 BORE→DRIVE BINDING (Target #38) — HARD_BLOCKED; placement frontier characterized.** Auto-continued from
#37 toward placement. `scripts/target38_bore_log57_drive_binding.py` exhausts every repo-local disambiguation signal:
**S1** per-row print = uniform union `8,10,13` on ALL 10 rows (empirically dumped — NO per-row drive signal); **S2**
multi_corridor_span [3-9,23,24] vs [10,12,13,14]; **S3** sole confirmed REAL-structure terminus near END = AP-157 (the
`(13,398)` competitor is a MATCHLINE = sheet-continuation boundary, NOT a physical terminus — reclassified, removing
#34's 3rd blocker); **S4** multi-drive (413 is a run-end value, not a single 0+00→4+13 drive). Passes S3 only →
**HARD_BLOCKED**. Missing artifact = `.FS` drive-decomposition sheet, **proven absent (#23/#24 full-corpus sweep), no
extraction path** (bore xlsx has no terminus field; PDFs carry no bore_log id #8/#24). bore_log7 CONTROL = PLACEABLE
(single corridor/drive/terminus). **Placement frontier (honest, end-to-end): PDF-AP lane yields exactly 1
deterministically placeable bore = bore_log7 (shipped default-OFF #14); bore_log57 + 12 other route_480 logs blocked on
artifacts proven absent (#20 flower-pot identity / #22 high-station anchor / #23 .FS).** #37's 2 new endpoints added 0 new
bore matches → recall up, 0 wrong-redline exposure. Self-test SELFTEST_OK. Full: `gac/target38_bore_log57_drive_binding.md`.
**This is the FINISH-MODE hard blocker: the single unblocking artifact (.FS Fiber-Schematic) must be ACQUIRED — it exists
(Fieldwire register references it) but was not delivered.** DO-NOT-WIDEN intact.

**ALTERNATE bore→drive RESOLVER, no .FS (Target #39) — bore_log57 TERMINUS uniquely resolved to AP-157; placement still
HARD_BLOCKED on geometry (length gap), not terminus.** Built a deterministic constraint scorer
(`scripts/target39_alternate_bore_drive_resolver.py`) from delivered signals only (station/direction, prints→corridors,
AP endpoint table, matchline typing, KMZ terminal-tail geometry+LENGTH, sibling segments). Terminus score = station_exact
+ is_real_structure + corridor_in_prints + has_tail_route; matchlines excluded (a bore can't end at a sheet boundary).
**bore_log57: UNIQUE dominant terminus = AP-157** (score 4.0, exact STA 413, no competitor within margin; route_465 is the
sole tail ending 2.1ft from AP-157). Placement gates G1 unique ✓ but **G2 length_match ✗ (route_465=741.7ft vs bore
413ft, ratio 1.80 → bore is a SUB-SEGMENT of the tail, unknown start offset), G3 single_corridor ✗ (spans [3-9,23,24] +
[10,12,13,14]), G4 print_certain ✗** → **HARD_BLOCKED_NO_DISCRIMINATOR**. Missing discriminator = per-drive segmentation
OR a start-structure field OR a certain corridor-A-only print (NOT .FS-only). **CONTROL bore_log7 = PLACEABLE_BY_ALTERNATE_RESOLVER**
(re-derives AP-163→route_469 via the independent scorer, ratio 1.02 — proven lane not degraded). No placement; 9 endpoints
untouched. Self-test SELFTEST_OK. **Advance over #38: terminus now UNIQUELY AP-157; blocker narrowed from "unknown
terminus" to "unknown which 413ft sub-path of the 741ft tail."** Full: `gac/target39_alternate_bore_drive_resolver.md`.
NEXT (#40): apply resolver to the other 5 multi-drive route_480 logs (29/31/46/47/58). DO-NOT-WIDEN intact.

## Render disk caution
`/data` can fill → upload/session/audit failures. If uploads fail, operator runs `df -h /data` BEFORE
blaming code (B-WS-12 OOM fingerprint = bore-log upload 502 `<!DOCTYPE html>`). If tight: inspect/backup/
compact ONLY `session_store.db`. NEVER touch `auth.db`, `station_photos`, `engineering_plans`; never
blind-delete `session_store.db`. Storage is a pit stop, not the mission.

## Chrome / visual QA status
Claude-in-Chrome: intermittently NOT connected (`list_connected_browsers` → `[]`). Playwright: no Chrome
binary installed. Claude Preview: WORKS for local HTML (used for the bore_log7 satellite map at
`scripts/bore_log7_placement_map.html`). Visual proof SUPPORTS deterministic evidence; it never replaces it.

## Context budget rules
- No 193k bootstrap. Don't read full hot.md/current-sprint/log/current-bugs unless required.
- Trust commit/wiki summaries as history unless current code contradicts them.
- Before any broad expansion state: (1) question it answers, (2) files/sections, (3) why narrower is
  insufficient, (4) stop condition.
- Subagents: narrow lane each; report exactly what was read; no duplicate broad rereads.
