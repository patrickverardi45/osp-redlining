# Gate 1 — Fiber-Backbone Tracer DESIGN SPRINT (DESIGN/PROOF ONLY)

**Status:** design only. No render, no engine commit, no flag, no fixture/census change, nothing placed.
Branch `feat/truelinev2` @ `2de1f18`. This packet answers the nine design questions and names the
smallest safe implementation slice. Read-only evidence; everything below is source-measured or cited to
an existing proof module.

> Doctrine: ALL-REDLINES (place every redline; abstain = a *named* missing relationship, never a manual
> fallback) **coexisting with** DO-NOT-WIDEN (never place a wrong redline). The fiber tracer must reduce
> abstains by *extracting* the bounded run, not by loosening a tolerance or snapping to the nearest blob.

---

## 0. Headline finding (it reshapes the lane)

The engine **already contains** the two hardest pieces of this design, built proof-only and deliberately
**not wired** to a placement lane:

- **`truelinev2/extract/corridor_prune.py` (M8.21)** — `corridor_bound()` + `prune_pieces()`: a
  length-law piece filter that finishes the dense walk that otherwise dies `DESIGN_PATH_SEARCH_EXHAUSTED`.
  Its docstring names *"the banked log42 state"* as the motivating case. It emits a **distinct certificate
  class** `LENGTH_ADMISSIBLE_CORRIDOR` and states outright that **Law 1's gate does NOT accept
  corridor-class survivors** and *"any future wiring toward a placement lane requires a fresh adversarial
  judgment of the semantics shift."*
- **`truelinev2/proof/run_station_corridor_route_solver_slice.py`** — the station-ladder bounded corridor
  in full: `build_rows → bind_row → position_on_row` (END positioned on the ladder, **no endpoint search**)
  `→ constrain_corridor` (monotonic band) `→ end_is_drawn_terminus` (the anti-overtrace gate). It already
  runs log42 + log57 and **correctly abstains both**.

So this sprint is **not** "design from scratch." It is: (a) confirm the two existing corridors cover the
SPRAWL wall, (b) design the **one genuinely-missing primitive — the junction-bridge** for the DISCONNECT
wall, (c) re-triage the lane against source, (d) define the smallest proof slice + the semantics-shift
guard that any eventual wiring must clear.

---

## 1. Logs inspected (read-only)

log42 (proof case), then log16/log3/log49/log4/log15/log57 as read-only comparison. Evidence from
`truelinev2/proof/run_fiber_lane_survey_probe.py` (new, read-only, gitignored), the three log42 probes
(`run_log42_fiber_probe/_trace/_components.py`), `run_split_log_corridor_probe.py` (M8.21), and
`run_station_corridor_route_solver_slice.py`.

### Survey table — where the generic `BORE` layer (the fiber-sprawl problem) actually lives

| log | span | stations | sheets | generic-`BORE` (outside BASE_CONDUIT) | verdict |
|---|---|---|---|---|---|
| **log42** | 287' | 0+00→2+87 | 1,2 | sheet 1: **195 segs, 1 comp, ~4677', w1079×h309 (BLOB)**; sheet 2: 21 segs strip ~1623' h=5 | fiber member (contested identity) |
| **log16** | 879' | 31+00→39+79 | 8,9,10 | sheet 9: **159 segs, 1 comp, ~3128', w583×h353 (BLOB)**; sheets 8,10: **0** | fiber member (cleanest) |
| **log3** | 900' | 12+63→21+63 | 2,3,4,5 | sheet 2 strip ~1623' h=5; sheet 3 strip ~522' h=1; sheets 4,5: **0** | partial (cross-sheet-first) |
| **log4** | 650' | 15+13→21+63 | 3,4,5 | sheet 3 strip ~522' h=1; sheets 4,5: **0** | partial (sibling of log3) |
| **log49** | **44'** | 44+89→45+33 | 10,11,12 | **0 on every sheet** | **NOT fiber — re-triage** |
| **log15** | 693' | 24+07→31+00 | 6,7,8 | **0 on every sheet** | **NOT fiber — re-triage** |
| **log57** | 413' | 0+00→4+13 | 8,10,13 | **0 on every sheet** | **NOT fiber — re-triage (drop)** |

`BASE_CONDUIT = {BORE - VACANT PIPE, BORE - PORT, BORE - LATERAL}`. A run on those classes is already
chainable by the shipped solver; the fiber problem is specifically a run on the **generic `BORE`** layer
*outside* BASE_CONDUIT. The survey shows that is only **log42, log16** (true blobs) and **log3, log4**
(thin strips). **log49/log15/log57 have no generic-`BORE` run at all** → the fiber tracer would not touch
them; their abstains are other lanes.

---

## 2. Fiber source patterns

1. **Generic-`BORE`-layer backbone (the lane).** The 2-1.25" 288ct fiber backbone is drawn on the generic
   `BORE` layer, *outside* the modeled BASE_CONDUIT classes. On a dense sheet the whole sheet's fiber net
   is **one connected component** (sheet 1: 195 segs / 4677' / 1079pt wide; sheet 9: 159 segs / 3128').
   `connected_chain` from a start symbol grabs the entire sheet-wide net → no isolable run (the SPRAWL
   wall). Confirmed: BASE_CONDUIT on sheet 1 = 3 segs; the backbone is **not** in it.
2. **Shared / multi-bore backbone.** The backbone is a *shared* printed run (sheet 1: `STA 0+00 TO 5+16
   (516') 2-1.25" 288CT FIBER`); a single bore is a sub-portion. So a bore's run is **not** the whole
   component even after isolation — it is a length-bounded sub-arc with a printed start frame.
2b. **Terminal-tail tap, drawn on BASE_CONDUIT but DISCONNECTED.** The terminal tail (`STA 2+70 TO 2+87
   PORT TERMINAL TAIL (17') 1-1.25"`) is drawn on `BORE - PORT` (BASE_CONDUIT, 2 segs, ~16 drawn-ft ≈ the
   17') ending at the identity-bound `AP-105 TERMINAL 6-PORT HH` (84.6,419.4). It is **65.1–67.7 pt from
   the nearest generic-`BORE` backbone seg** — > 2× MAX_DASH_GAP (35). `order_chain_route(start→AP-105)`
   returns EMPTY in every layer set (the DISCONNECT wall).
3. **Strip vs blob.** log3/log4 ride a *thin straight* generic-`BORE` strip (h ≤ 5pt) plus BASE_CONDUIT on
   the remaining sheets — much milder sprawl than the blob, but spread over 4 sheets (cross-sheet assembly
   is their dominant gate, not sprawl).
4. **Endpoint identity is NOT the blocker.** log42 binds cleanly: start `SPLICE POINT 13 / NEXTLINK HH`
   (804.6,340.4), end `AP-105 6-PORT HH` (84.6,419.4). The walls are geometry (sprawl, disconnect), not
   identity.

---

## 3. Station / callout evidence — can printed callouts bound a sub-run?

**Yes — two independent, already-built bounding mechanisms, and they are complementary:**

- **Length-law corridor (`corridor_prune`).** A printed footage × the coherent ladder scale gives an
  ellipse bound `bound = exp·(1+DESIGN_LENGTH_REL_TOL) + 2·(jump_cap+TRIM_RADIUS)`; keep a piece iff a
  vertex `v` has `d(start,v)+d(v,end) ≤ bound`. By the triangle inequality this removes only
  provably-gate-failing geometry. On log42 this **finished** the dense sheet search (banked
  `DESIGN_PATH_SEARCH_EXHAUSTED`) to a pinned taxonomy {8 chord-infeasible, 1 out-of-tolerance, 2
  AMBIGUOUS, 1 no-chain, **1 survivor**}.
- **Station-ladder corridor (`run_station_corridor_route_solver_slice`).** `build_rows` recovers the drawn
  running-station ladder rows by scale-consistent mutual-best-match linking (rejects cross-ladder hijacks);
  `bind_row` binds the bore's reset to exactly one row; `position_on_row(parent+span)` places the END as
  **one point on the ladder** (kills the old `END_BRANCH_AMBIGUOUS_AT_SPAN` flood: 10–52 rival ends → 1);
  `constrain_corridor` keeps only dashes within `CORRIDOR_HALF_PT` perpendicular and `[parent, parent+span]`
  station; `route_is_monotonic` forbids station reversal.

**Crucial frame caution (the M8.21 refutation, pinned).** A printed footage's *frame* must be proven
before a corridor survivor is read as an origin identity. On log42 the unique length-corridor survivor
(`NEXTLINK@818,419`) traced 225.2' = **footage − 46**, i.e. it is the printed **INTERIOR reset** at
callout-frame 0+46, **not** log42's origin (`callout_frame_owner` law; verdict
`INTERIOR_RESET_NOT_ORIGIN`, five independent measurements). So a corridor can yield a *unique* survivor
that is still the *wrong* structure → frame-ownership is a mandatory gate, not optional.

---

## 4. Proposed bounded-corridor trace (exact algorithm)

Compose the two existing corridors; invent nothing new for the SPRAWL wall.

```
INPUT: bore (start identity, end identity, span_ft, printed run frame), sheet, drawn items
1.  BIND endpoints by identity (existing _bind / resolve_structure_position). 0 or ≥2 → abstain. Never nearest.
2.  COHERENT SCALE: coherent_ladder_scale(cluster_ladders(route_ladder_ticks)). None → abstain
    (LADDER_SCALE_NOT_COHERENT — a fallback scale is a guess).
3.  PIECES: conduit_pieces(drawings, layers = generic-BORE ∪ BASE_CONDUIT for THIS lane only).
4.  STATION-LADDER CORRIDOR: build_rows → bind_row(start) (unique row, else abstain) →
    position_on_row(parent+span) for the END point (else END_NOT_COVERED_BY_LADDER) →
    constrain_corridor(monotonic band [parent, parent+span]). Severs laterals/branch spurs/foreign resets.
5.  LENGTH CORRIDOR: chord_infeasible(start,end,bound) → typed pre-walk kill; else prune_pieces(...,bound).
    (Belt-and-suspenders with step 4; the two corridors bound orthogonally — band vs length.)
6.  WALK: walk_design_path(pruned_pieces, start, end) over the welded pieces (UNCHANGED budget + jump cap).
    TRACED (1 jitter group) → candidate; AMBIGUOUS → abstain (named: strand discriminator); EXHAUSTED →
    abstain (the bound was not load-bearing — never raise the budget).
7.  FRAME OWNERSHIP: callout_frame_owner must confirm the survivor's start is the callout-frame ORIGIN, not
    an interior reset (survivor path ≈ footage, not footage−reset). Else INTERIOR_RESET_NOT_ORIGIN abstain.
8.  END TERMINUS: end_is_drawn_terminus (identity-bound structure ≤ STRUCT_TOL_PT, OR matchline, OR conduit
    dead-end). A run continuing PAST the end station has no terminus there → abstain (the drop false positive).
9.  CLOSURE + HONESTY: route length within DESIGN_LENGTH_REL_TOL of span·scale; route_edges_source_backed;
    interior vertices are real dash endpoints; not self-crossing. Any fail → abstain.
PROVENANCE: every survivor carries uniqueness_universe = LENGTH_ADMISSIBLE_CORRIDOR (NOT full-universe).
```

This trace, **without** a junction-bridge, handles the SPRAWL wall. It does **not** cross the DISCONNECT.

---

## 5. Proposed junction-bridge rule (the one genuinely-new primitive)

The DISCONNECT wall (log42: BORE-PORT terminal tail 65–68pt from the backbone) is what neither existing
corridor solves. `order_chain_route` returns EMPTY because no dash bridges the void; the log59/log66
precedent (thread real dashes across a 35.6–36.4pt gap) **does not apply** — there is no alternate dashed
path, it is a true void.

**Rule `junction_bridge` (pure, gated, NEVER changes MAX_DASH_GAP):** add **at most one** bridge edge
between two corridor-terminal points iff ALL hold:

1. **Exactly one** disconnect in the bounded corridor (the corridor is otherwise continuous within
   MAX_DASH_GAP). ≥ 2 voids → abstain (`MULTI_DISCONNECT_NOT_BRIDGEABLE`). One bridge, never a chain of jumps.
2. **Identity anchor.** One side is the identity-bound printed terminus structure (e.g. `AP-105 6-PORT HH`)
   or a printed junction station shared by both sides (e.g. backbone-end and tail-end both at STA 2+70).
   The bridge connects *named/stationed* endpoints — never the geometrically-nearest seg (no nearest-snap).
3. **Footage corroboration.** The bridge + the traced run close the **printed** span within
   DESIGN_LENGTH_REL_TOL. A bridge whose length is not accounted by printed footage (e.g. log42's 65pt ≈
   45 drawn-ft against a 17' printed tail and a 0' station gap at 2+70=2+70) → abstain
   (`BRIDGE_FOOTAGE_UNCORROBORATED`). **This gate currently fails log42** — its disconnect is not
   footage-explained, which is itself evidence the run identity is unresolved.
4. **Bounded, local tolerance.** The bridge has its own cap `JUNCTION_BRIDGE_MAX` (a *named, test-locked*
   constant, derived from a printed-junction tolerance — NOT MAX_DASH_GAP and NOT applied to the walk).
   It is consumed only here, at the one proven junction; the global dash-gap law is untouched.
5. **Single class transition.** The bridge crosses exactly one layer boundary (generic-`BORE` backbone ↔
   BASE_CONDUIT tail) at the printed tap; it never bridges two generic-`BORE` blobs (that would re-open the
   sprawl).

If any gate fails → abstain with the typed reason. The bridge is the *evidence-anchored* exception, never
a tolerance relaxation.

---

## 6. Rejection gates (mandatory)

- `ENDPOINT_IDENTITY_AMBIGUOUS` — 0 or ≥2 identity binds (never nearest).
- `LADDER_SCALE_NOT_COHERENT` — no coherent ladder scale (no fallback scale).
- `LADDER_BIND_FAILED` / `AMBIGUOUS_LADDER_BIND` — reset not on exactly one row.
- `END_NOT_COVERED_BY_LADDER` — ladder does not bracket parent+span.
- `LENGTH_INFEASIBLE_CHORD` — straight chord already exceeds the bound.
- `DESIGN_PATH_AMBIGUOUS` — ≥2 physically distinct in-corridor paths (distinct geometry is NEVER
  tiebroken; named missing = strand discriminator).
- `DESIGN_PATH_SEARCH_EXHAUSTED` — bound not load-bearing; **forbidden to fix by raising the budget**.
- `INTERIOR_RESET_NOT_ORIGIN` — survivor is a printed interior reset, not the origin (frame-ownership).
- `ROUTE_OK_BUT_END_NOT_A_DRAWN_TERMINUS` — conduit runs past the end (the drop/backbone false positive).
- `STATION_REVERSED` / `PATH_LENGTH_OUT_OF_TOLERANCE` / not source-backed / self-crossing.
- `MULTI_DISCONNECT_NOT_BRIDGEABLE` / `BRIDGE_FOOTAGE_UNCORROBORATED` / `BRIDGE_NO_IDENTITY_ANCHOR`.
- `CORRIDOR_CLASS_NOT_PLACEMENT_ELIGIBLE` — corridor survivor reaching the placement gate without the
  fresh adversarial semantics-shift judgment (Law 1 already refuses corridor-class survivors).

---

## 7. Eligible vs still-blocked

A DESIGN sprint renders nothing, so no log is "eligible to render" today. After the tracer is *built and
proven*, eligibility by source shape:

- **Tracer-addressable, best PROOF case — log16.** Single-hypothesis generic-`BORE` blob on sheet 9
  (3128'); endpoints + disconnect need their own per-log measurement (named follow-up). The cleanest first
  target.
- **Tracer-addressable but needs OWNER source first — log42.** Two walls handled by the corridors, BUT (a)
  its run identity is **contested across proof generations** (M8.21 reads it as sheet-2 270' + sheet-1 17'
  tail; continued-29 reads it as a 0+00→2+87 sub-portion of sheet-1's 516' shared run) and (b) the M8.21
  corridor survivor is an INTERIOR RESET, not the origin, and (c) its 65pt disconnect is
  footage-uncorroborated. The tracer alone will not safely place it — it needs owner frame resolution
  (bore_log13 block semantics + the log41 end-digit conflict).
- **Cross-sheet-assembly-first, tracer-second — log3, log4** (siblings: both end 21+63, sheets 3/4/5). The
  generic-`BORE` is thin strips; the dominant gate is the 4-/3-sheet assembly, not sprawl.
- **Re-triage OUT of the fiber lane — log49, log15, log57.** No generic-`BORE` run on any referenced sheet;
  the fiber tracer is the wrong tool. log57 is a DROP bore (station-corridor solver: true terminus = an
  unnamed pot on another sheet; route480 multi-corridor over-claim). log49 (span 44') and log15 are
  BASE_CONDUIT runs whose abstains belong to the cross-sheet / drop-identity / stored-anchor lanes. **Net:
  the fiber milestone is ~2 clean + 2 partial, not 7.**

---

## 8. Smallest safe implementation slice

**A new PROOF-ONLY slice on log16 — no lane wiring, renders nothing.**

1. Target **log16 only** (cleanest single-hypothesis blob).
2. Reuse verbatim: `corridor_prune.{corridor_bound,prune_pieces,chord_infeasible}`,
   `design_path.{conduit_pieces,walk_design_path,…}`, and the station-corridor helpers
   (`build_rows/bind_row/position_on_row/constrain_corridor/route_is_monotonic/end_is_drawn_terminus`).
   Budget, jump cap, DESIGN_LENGTH_REL_TOL, MAX_DASH_GAP — all imported UNCHANGED.
3. Add **one** new pure module `truelinev2/extract/junction_bridge.py` implementing §5 (gated, one bridge,
   identity + footage anchored, own named cap). Pure functions; no layer/company strings; nothing rendered.
4. Emit a typed verdict + provenance JSON to a gitignored `data/outputs/` path (TRACED-in-corridor /
   named abstain). **No stroke, card, PNG, AUTO; census + lane statuses untouched.**
5. Carry `uniqueness_universe = LENGTH_ADMISSIBLE_CORRIDOR` on every survivor. **Do NOT wire to placement**
   — that is a separate step requiring the fresh adversarial semantics-shift judgment `corridor_prune`
   mandates.

Only after this proof passes (and an owner authorizes) does a render slice + the placement-class judgment
follow — first for log16, never for log42 until its source frame is owner-resolved.

---

## 9. Required tests (prove DO-NOT-WIDEN)

- **Constants unchanged:** assert `MAX_DASH_GAP == 35.0`, `DESIGN_LENGTH_REL_TOL == 0.25`,
  `MAX_WALK_EXPANSIONS == 20000` (the slice raises none of them).
- **Bound is load-bearing, budget is not:** on the full sheet-9 blob an unbounded walk EXHAUSTS; the
  bounded corridor FINISHES with the same survivor — i.e. the win came from the bound, not a budget raise
  (margin-stability check, as M8.21 G6).
- **Junction-bridge gating:** exactly one disconnect → one bridge; a synthetic ≥2-void case → abstain
  (`MULTI_DISCONNECT_NOT_BRIDGEABLE`); a bridge to the geometrically-nearest-but-not-printed-terminus →
  refused (`BRIDGE_NO_IDENTITY_ANCHOR`); a footage-unaccounted bridge → `BRIDGE_FOOTAGE_UNCORROBORATED`
  (this case **must reject log42's 65pt gap**).
- **Anti-overtrace:** a candidate whose corridor route runs past the end station / whose end is not a drawn
  terminus → abstain (`end_is_drawn_terminus`); two parallel in-corridor runs → `parallel_strand_guard`
  refuses (no nearest pick).
- **Frame ownership:** the interior-reset survivor (log42-class) → `INTERIOR_RESET_NOT_ORIGIN`, never a
  placement.
- **Certificate-class guard:** a corridor-class survivor presented to the Law-1 placement gate is REFUSED
  (`CORRIDOR_CLASS_NOT_PLACEMENT_ELIGIBLE`) until the semantics-shift judgment exists.
- **Controls byte-identical:** the banked log8/log32 survivors reproduce pruned == unpruned, byte-identical
  stroke points (extend M8.21 G5).
- **Census frozen / posture:** OFF 31/6/1/17/3, ON 22/1/4, log44 + abstains held; flag-OFF byte-identical;
  no new production flag; red strokes only; no PNG written by the proof.

---

## 10. Risk / blast radius

- **This DESIGN sprint: ~zero.** Read-only probes + this doc. No engine/render/fixture/census/flag/backend/
  web/runtime/main/deploy touch. Reversible by deleting two untracked files.
- **The eventual junction-bridge is the highest-risk new primitive.** A too-loose bridge re-introduces the
  nearest-snap / route_480-backbone false positive DO-NOT-WIDEN forbids — hence the exactly-one + identity
  + footage + own-named-cap gating, and the §9 refutation tests.
- **Certificate-class shift is the second risk.** The corridor certifies *length-admissible-capable*
  uniqueness, a strictly weaker class than full-universe; `corridor_prune` itself mandates a fresh
  adversarial judgment before any placement wiring. The proof slice must keep that wall (Law 1 refuses
  corridor-class survivors) until that judgment is made.
- **log42 carries a source-identity risk independent of geometry** — do not place it on a corridor survivor
  until the contested run frame is owner-resolved.

---

## 11. Recommendation

1. **Build the smallest proof slice on log16 first** (§8) — cleanest single-hypothesis blob; proves the
   corridor + junction-bridge end-to-end with no render and no lane wiring.
2. **Hold log42** for owner frame-resolution (contested run identity + interior-reset survivor +
   footage-uncorroborated disconnect). The tracer is necessary but not sufficient for it.
3. **Re-triage log49 / log15 / log57 OUT of the fiber lane** — they have no generic-`BORE` run; redirect to
   the drop-identity (log57), cross-sheet, and stored-anchor lanes. This shrinks the fiber milestone to
   ~2 clean + 2 partial.
4. **Treat log3 / log4 as cross-sheet-assembly-first**, tracer-second.
5. **Do not wire any corridor survivor to placement** until the junction-bridge proof AND the
   corridor-class semantics-shift adversarial judgment are both done.

## Files
- New (read-only, untracked): `truelinev2/proof/run_fiber_lane_survey_probe.py`.
- Existing modules cited: `truelinev2/extract/corridor_prune.py`, `truelinev2/extract/design_path.py`,
  `truelinev2/extract/conduit_topology.py`, `truelinev2/proof/run_split_log_corridor_probe.py`,
  `truelinev2/proof/run_station_corridor_route_solver_slice.py`, the three `run_log42_fiber_*.py` probes.
- Related: `gac/drop_lane_source_adjudication.md` (the log57/drop identity gap, legacy-engine evidence).
