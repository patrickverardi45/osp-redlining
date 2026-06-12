# M8.20 Fable Packet: Shared Origin / Start Collision

Purpose: adjudicate the smallest evidence law for the `log8` / `log32` /
`log42` start-origin blocker. This packet is analysis-only. Do not implement,
wire a lane, place a stroke, or broaden engine doctrine while reading it.

## 1. Current Git Truth

| Field | Value |
|---|---|
| Branch | `feat/truelinev2` |
| HEAD | `fadf97900551d649c672d7b4100e623e51cd3117` |
| Upstream | `origin/feat/truelinev2` |
| Ahead / behind | `0 / 0` at packet creation |
| Tracked tree | Clean before this docs-only packet |
| Untracked tree | Existing untracked paths preserved; do not clean |

Relevant commits, newest first:

| Commit | Meaning |
|---|---|
| `fadf979` | Current docs/test cleanup checkpoint |
| `23ad22c` | M8.19 session-state documentation |
| `972b834` | M8.19 path-length cross-sheet join proof |
| `d47744a` | M8.18 session-state documentation |
| `b7410a5` | M8.18 ladder discriminator proof seam |
| `7b66c39` | M8.17 session-state documentation |
| `bb78140` | M8.17 segmented callout-chain assembly |
| `78bf5a2` | M8.15/M8.16 session-state documentation |
| `b86e68f` | M8.16 cross-sheet origin discovery law |

## 2. Blocker

The three bores share the start-origin adjudication frontier, but the exact
evidence corrects the shorthand that all three collide on one node: M8.18 and
M8.19 prove that `log8` and `log32` both narrow to
`NEXTLINK@378,409`, while `log42` has zero traceable survivors and does not
bind that node. M8.19's path-length join proves the `log8` and `log32`
cross-sheet geometry without widening the unchanged 5% join tolerance. The
unresolved question for those two is whether the shared node is a valid
shared-origin/multi-drop terminal or a false collision requiring a per-bore
discriminator; `log42` remains a formal abstain pending a uniquely traceable
sheet-2 design path.

## 3. Exact Status

All three remain in lane `symbol_conduit_matchline`, mode `REVIEW_ONLY`, with
zero segments and status `STRUCTURE_IDENTITY_BINDING_REQUIRED`.

| Bore | Current lane/status | Sheets | Chain stations | Path-length / chord verdict | Candidate structure | Current blocker |
|---|---|---|---|---|---|---|
| `log8` | `REVIEW_ONLY` / `STRUCTURE_IDENTITY_BINDING_REQUIRED` | far `18`, end `22` | `0+00 -> 1+10 -> 1+76`; then `1+76 -> 3+90` | chord refuses `1.360/1.178`; path proves `1.508/1.554` | one in-bore survivor: `NEXTLINK@378,409`; shared with `log32` | shared-origin/multi-drop law or bore-specific discriminator |
| `log32` | `REVIEW_ONLY` / `STRUCTURE_IDENTITY_BINDING_REQUIRED` | far `18`, end `22` | `0+00 -> 1+30 -> 1+77`; then `1+77 -> 2+13` | chord refuses `1.352/1.420`; path proves `1.499/1.441` | one in-bore survivor: `NEXTLINK@378,409`; shared with `log8` | shared-origin/multi-drop law or bore-specific discriminator |
| `log42` | `REVIEW_ONLY` / `STRUCTURE_IDENTITY_BINDING_REQUIRED` | far `2`, end `1` | direct `0+00 -> 2+70`; then `2+70 -> 2+87` | no join verdict: design-path discriminator yields 0 traceable survivors | none | uniquely traceable drawn path through dense sheet-2 network |

## 4. Evidence Pointers

Read only these first. The companion manifest is the hard file boundary.

| Milestone / concern | File | Function, probe, or field |
|---|---|---|
| M8.16 discovery | `truelinev2/proof/run_cross_sheet_continuation_probe.py` | `main`, gates G1-G6 |
| M8.16 evidence | `data/outputs/cross_sheet_continuation_probe/cross_sheet_continuation_probe.json` | `bores[*].named_missing`, `evidence_chain` |
| M8.16 doc | `HANDOFF.md` | `M8.16 - cross-sheet continuation law` |
| M8.17 chain | `truelinev2/proof/run_cross_sheet_continuation_probe.py` | G7, `EXPECT_STATUS` |
| M8.17 chain law | `truelinev2/extract/matchline_join.py` | `assemble_callout_chain` |
| M8.17 doc | `HANDOFF.md` | `M8.17 - segmented far-sheet callout chains` |
| M8.18 probe | `truelinev2/proof/run_ladder_discriminator_probe.py` | `_far_segment`, `_discriminate`, `_join_refuses`, `main` |
| M8.18 evidence | `data/outputs/ladder_discriminator_probe/ladder_discriminator_probe.json` | `bores`, `survivors`, `join_refusal_reason` |
| M8.18 doc | `HANDOFF.md` | `M8.18 - proof-only ladder discriminator seam` |
| M8.19 probe | `truelinev2/proof/run_path_length_join_probe.py` | `design_path_implied_scale`, `_side`, `_proven`, `main` |
| M8.19 evidence | `data/outputs/path_length_join_probe/path_length_join_probe.json` | `law`, `blocker`, `cases` |
| M8.19 doc | `HANDOFF.md` | `M8.19 - path-length cross-sheet join Phase 0/1` |
| Join law | `truelinev2/extract/matchline_join.py` | `cross_sheet_join_verdict`, `joined_segments_verdict`, `JOIN_SCALE_REL_TOL` |
| Ladder law | `truelinev2/extract/ladder_cluster.py` | `cluster_ladders`, `coherent_ladder_scale` |
| Path law | `truelinev2/extract/design_path.py` | `walk_design_path`, `path_length`, `DESIGN_LENGTH_REL_TOL` |
| Current lane | `truelinev2/match/symbol_conduit_lane.py` | `discover_cross_sheet_start`, `_cross_sheet_segments`, `resolve_bore` |
| All-58 runner | `truelinev2/proof/run_symbol_conduit_lane_sweep.py` | `main`, gates G1-G7 |
| All-58 output | `data/outputs/symbol_conduit_lane_sweep/symbol_conduit_lane_sweep.json` | `census`, three bore rows |
| Card proof | `truelinev2/proof/run_design_stroke_cards_proof.py` | `main`, `ELIGIBLE`, `PICKS` |
| Card output | `data/outputs/design_stroke_cards/design_stroke_cards_proof.json` | confirms none of these three has an M8.15 card |

## 5. Key Extracted Facts

- Chord failure: the curved end-sheet drop routes make straight
  structure-to-matchline chords shorter than the drawn routes. That produces
  disagreeing implied scales and the unchanged 5% b.9 join refuses.
- Path-length success: `walk_design_path` plus `path_length` measures the
  drawn route, then feeds the unchanged `cross_sheet_join_verdict` at
  `JOIN_SCALE_REL_TOL == 0.05`. `log65` remains proven by both measurements.
- `log8`: far chain `110 + 66 = 176 ft`; end segment `214 ft`; total
  `390 ft`; one M8.18 survivor at `NEXTLINK@378,409`.
- `log32`: far chain `130 + 47 = 177 ft`; end segment `36 ft`; total
  `213 ft`; one M8.18 survivor at `NEXTLINK@378,409`.
- `log42`: direct far callout `270 ft`; end segment `17 ft`; total `287 ft`.
  Per-ladder scale is coherent, but the dense sheet-2 design-path search
  yields zero traceable survivors. It has no proven collision with
  `NEXTLINK@378,409`.
- Exact M8.19 wording: "the cross-bore collision STANDS: log8 and log32 both
  bind NEXTLINK@378,409." Source:
  `data/outputs/path_length_join_probe/path_length_join_probe.json`,
  field `blocker`.
- The survivor identifier is emitted by M8.18 as
  `<layer>@<rounded-x>,<rounded-y>`; the source row is in
  `run_ladder_discriminator_probe.py::_discriminate`.
- Current all-58 census remains
  `25/13/5/5/4/3/1/2 = 58`; these three occupy the structure-required count.
- All three have `segments: []`. None appears in the 9-card M8.15
  design-stroke/pick-card packet.

## 6. Evidence Laws To Adjudicate

Fable must specify or reject these laws. Do not code them in this task.

1. **Valid shared-origin/multi-drop terminal law**
   - What source evidence proves that one physical port HH legitimately
     originates multiple distinct bore runs?
   - The fact that two bores select the same survivor is not itself proof.
   - State required positive evidence, uniqueness scope, and abstain behavior.
2. **False-collision rejection law**
   - When must a cross-bore shared survivor invalidate both candidates?
   - State whether rejection is pairwise, structure-wide, or corpus-wide.
   - Preserve a typed refusal and exact missing evidence target.
3. **Intermediate-station discriminator law**
   - Can printed intermediate stations `1+10` and `1+30` bind each bore to a
     distinct structure-side route without inventing identity?
   - State the necessary chain-to-geometry relationship, uniqueness gate,
     adversarial collision test, and abstain outcome.

`log42` requires a separate evidence-law statement for a uniquely traceable
sheet-2 path; it cannot be promoted by a law written only for the
`log8`/`log32` collision.

## 7. No-Go Rules

- No tolerance widening.
- No fake uniqueness, tie-breaking, nearest-candidate guessing, or owner-vibe
  substitution for source evidence.
- No route suggestion, pick card, or reviewer suggestion represented as a
  placement.
- No UI, web, or mobile work.
- No production `main`, merge, deploy, push, or remote changes.
- No geometry override without identity proof.
- No change to accepted grades, reviewer semantics, confidence classes,
  redline geometry, or existing proof doctrine.

## 8. Minimal Commands

Run from repository root. The first three are proof/report regeneration only.

```powershell
$env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_ladder_discriminator_probe
$env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_path_length_join_probe
$env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_symbol_conduit_lane_sweep
```

Only after an explicitly authorized code change:

```powershell
$env:PYTHONPATH="."; .\venv\Scripts\python.exe -m pytest truelinev2/tests -q
```

## 9. Definition Of Done

M8.20 analysis ends with exactly one of:

1. A proven REVIEW-only placement law with explicit positive evidence,
   uniqueness, adversarial rejection, and typed abstain behavior.
2. A formal abstain naming the exact missing extraction target.
3. A new evidence-law specification that is narrow enough for a later,
   separately authorized implementation and proof task.

No implementation, lane wiring, geometry generation, grade change, or
production action is part of this packet.
