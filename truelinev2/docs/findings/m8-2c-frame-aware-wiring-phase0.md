# M8.2c Phase 0 — frame-aware chain-assembly wiring (read-only diagnosis)

**Status:** planning only. No engine change, no tests, no placement change. Coverage
remains **23/58**. This doc decides the *smallest safe* way to use the M8.2b frame
model/parser foundation inside chain assembly without altering existing placements or
creating false positives.

## Executive summary

`build_chains` links callouts by **raw feet** and ignores each callout's **sheet**, so it
is frame-blind in both directions: it can falsely link two callouts that share a raw
station number across a matchline, and it misses the *true* continuation when a matchline
resets the frame (the log11 case: sheet 5 `STA 3+23` ≡ sheet 17 `STA 0+69`, raw 323 ≠ 69 →
no link today). The M8.2b foundation can translate a station across a **safe** frame edge,
which is exactly what is missing.

The important finding for scope: **the frame-blindness is not confined to `build_chains`.**
`score_chain` also compares raw `from_ft`/`to_ft` against the bore's stationing, so a
cross-frame chain that `build_chains` *could* form would still be **mis-scored** unless its
endpoints are first translated into one common frame. So a correct decision-affecting wire
touches the link test (`chains.py`) **and** the endpoint deltas (`score.py`) — and any change
to which chains exist can regress a current placement *in either direction* through the
`decide()` ambiguity gate. The recommendation is therefore an **isolated, default-OFF
optional helper**, activated only behind a corpus no-regression gate, with log11's actual
promotion deferred (anchor identity is a separate axis from frame identity).

## Current chain-builder behavior

`run_match` (`match/engine.py:26`) footage mode:

1. Extract callouts from every `bore.sheet_refs` (`engine.py:27-29`); each `Callout`
   carries its `sheet`, `page`, `from_ft`, `to_ft`, `footage` (all per-sheet local).
2. `chains = build_chains(callouts, bore.station_start_ft, bore.station_end_ft)`
   (`engine.py:51`) — **no frame context passed**.
3. `score_chain` each chain → `decide(scored, span_ft)` → AUTO_SELECT / REVIEW / ABSTAIN.

`build_chains` (`match/chains.py:13-32`):
- **start match (line 17):** `abs(c.from_ft - bore_start_ft) <= start_tol` — raw feet.
- **link test (line 27):** `abs(last.to_ft - c.from_ft) <= link_tol and c.to_ft > last.to_ft`
  — **raw feet, `sheet` ignored.** This is the frame-blind seam.

`score_chain` (`match/score.py:9-26`): `start_delta = abs(chain[0].from_ft - bore_start_ft)`,
`end_delta = abs(chain[-1].to_ft - bore_end_ft)` — **raw feet across frames**; `foot_delta`
(summed footage) and `sheets`/`multi_sheet` are frame-independent.

`decide` (`match/decide.py:29-68`): ranks acceptable chains; **≥2 co-equal candidates
(penalty within 5.0, different signatures) → `ABSTAIN GE_2_COEQUAL_CANDIDATES_NO_TIEBREAKER`
(lines 44-50)**; unique + tight → AUTO; unique + caveated → REVIEW. *This co-equal gate is the
anchor-identity safety and must stay exactly as-is.*

## Proposed safe wiring shape

Additive and OFF by default:

1. **Frame identity = `Callout.sheet`** via `match.frames.frame_for_sheet(c.sheet)`. **No
   `Callout`/schema change** — the minimal frame identity already exists; the builder just
   ignores it.
2. **Build the FrameGraph once per plan** (read-only) from per-sheet plan text using the
   M8.2b parser (`parse_frame_equations` → `build_frame_edges(from_frame=frame_for_sheet(s))`
   → `build_frame_graph`). Only HIGH-confidence, unique, conflict-free edges survive.
3. **Thread it as an OPTIONAL parameter** — `build_chains(..., frame_graph: FrameGraph | None = None)`
   and `score_chain(..., frame_graph=None)` (or normalize endpoints before scoring). Pass it from
   `run_match`. **Never a module-global** (would break the no-global-state guard and change
   behavior implicitly).
4. **Link rule when a graph is provided:**
   - same sheet → raw-feet link (unchanged);
   - different sheet → translate `c.from_ft` from `frame_for_sheet(c.sheet)` into
     `frame_for_sheet(last.sheet)` via `translate_station_ft`; link only if it returns a value
     within `link_tol`. **`None` (no safe edge) → no cross-frame link** (raw equality across
     frames is never accepted).
5. **Score rule when a graph is provided:** translate the chain's first/last endpoints into the
   bore's frame before computing `start_delta`/`end_delta`, so a cross-frame chain is evaluated
   on a common frame (otherwise step 4's correct chains are mis-scored).

A small pure predicate (e.g. `match.frames.link_feet(graph, from_sheet, to_sheet, feet)`) keeps
the new logic in the M8.2b core; `chains.py`/`score.py` only call it.

## Required frame context inputs

- The `FrameGraph` for the plan (safe edges + recorded conflicts), built from per-sheet text.
- The mapping `sheet → FrameId` (already provided by `frame_for_sheet`).
- The bore's own frame for the endpoint-delta translation in scoring (the bore's stationing
  frame; for single-frame bores this is identity).
- Nothing else — no PDF re-parse inside `build_chains` (the graph is built once, upstream).

## Backward-compatibility rule

`frame_graph is None` (the default) ⇒ `build_chains` and `score_chain` execute their **current
raw-feet code path, byte-identical**. The new branch is reachable only when a graph is explicitly
passed **and** a link/endpoint crosses sheets. Flag/param OFF ⇒ M7 behavior is preserved exactly;
all current tests and the 23/58 sweep are unaffected.

## log11-specific expected behavior

- bore_log11 references sheets 5 and 17; the probe found the safe edge `sheet 5 STA 3+23 ≡ sheet
  17 STA 0+69` (offset 254 ft, HIGH, unique, no conflict).
- With the graph, `build_chains` can translate sheet-5 `3+23` → sheet-17 `0+69` and **form the true
  cross-frame chain** that raw-feet linking misses; `score_chain` (frame-aware) evaluates it on the
  bore frame.
- **But the `decide()` co-equal gate still applies.** The probe also flagged anchor ambiguity
  (`zero_anchor_counts_by_sheet`): if ≥2 co-equal `0+00` anchors remain, `decide` returns
  `ABSTAIN GE_2_COEQUAL_CANDIDATES_NO_TIEBREAKER` — **frame-awareness resolves the cross-frame LINK,
  not the ANCHOR identity.** Expected: log11 may move from "no chain forms" to "a correct chain
  forms but is still gated by anchor ambiguity," i.e. it does **not** auto-promote to AUTO/REVIEW
  unless the anchor is independently unique. **No tolerance change, no gate weakening.**

## Regression-risk analysis

- **Bidirectional risk through `decide()`:** adding a translated chain can introduce a **co-equal
  rival** to a currently-unique placement → flips it to ambiguity-ABSTAIN; removing a raw
  cross-frame link can drop a chain a current placement depends on → ABSTAIN (no acceptable chain).
  Either way a current placement could be lost.
- **Who is at risk:** single-sheet placements (e.g. log60/55/56/61) have no cross-frame link and are
  unaffected. The currently-placed **multi-sheet** bores (log57 [8,10,13], log62 [5,6], log65 [9,10])
  place *today* via raw-feet chaining, which means their sheet stationing is already **continuous
  (no matchline reset)** — those sheet pairs are not frame-equation resets, so adding safe-edge
  translation should not alter them. The frame-equation/reset cases are the ones that currently FAIL
  (log11), which is where the gain is.
- **`score.py` exposure:** because endpoint deltas are raw-feet, the decision math is part of the
  blast radius for cross-frame chains — larger than "just `build_chains`."
- **Mitigation = a mandatory corpus no-regression gate:** run the M5 sweep with the graph enabled and
  assert `PLACED == 23` **and** every per-log status (AUTO/REVIEW/ABSTAIN/ERROR) is identical to the
  9be32b9 golden, *before* the path may be enabled by default. Any per-log delta is a finding to
  resolve, not to ship.

## Test plan (for the implementation phase, not now)

1. `build_chains(frame_graph=None)` produces chains **identical** to today (fixture golden).
2. With a safe edge, `build_chains` forms the translated cross-frame chain (synthetic log11:
   sheet-5 `3+23` + sheet-17 `0+69`).
3. Cross-sheet pair with **no** safe edge → no translated link (raw equality not treated as proof).
4. Same-sheet linking unchanged when a graph is present.
5. `score_chain` frame-aware endpoints: a cross-frame chain scores on the bore frame (deltas correct).
6. `decide` co-equal gate still abstains on ambiguous anchors even when a frame chain exists.
7. **Corpus golden:** sweep with graph ON ⇒ `PLACED == 23`, per-log status unchanged.
8. M8.2b tests, the M8.2a probe, and all three drift guards still pass; no convention names in core;
   no new global state.

## Files that would need implementation

- `match/chains.py` — optional `frame_graph` param + cross-sheet translated link (call a core helper).
- `match/score.py` — optional frame-aware endpoint translation for cross-frame chains.
- `match/frames.py` (M8.2b core) — **add** a pure `link_feet` / endpoint-translate helper + a
  per-plan FrameGraph builder from per-sheet text (additive; existing functions unchanged).
- `match/engine.py` — build the graph once and pass it into `build_chains`/`score_chain`.
- `truelinev2/tests/test_chains_frame_aware.py` (new) + a corpus no-regression golden.

## Files that must remain untouched

- `match/decide.py` (the co-equal / tiering gate — **do not weaken**), `match/overlap.py`,
  `match/assembly.py`, `schema/models.py` (no `Callout` change), `schema/hierarchy.py`,
  `stations.py`, `schema/frames.py` (M8.2b types — additive only if at all), the M8.2a probe,
  all `backend/`, `web/`, `main`, production, Render, Vercel.

## Recommendation

**Implement as an isolated, default-OFF optional helper — in two gated steps; do not wire into the
decision path yet beyond a proven-neutral scaffold.**

- **Step 1 (safe, do first):** add the per-plan FrameGraph builder + the `match.frames` link/endpoint
  helper + thread an optional `frame_graph=None` through `build_chains`/`score_chain`/`run_match`,
  proven **behavior-neutral** (default path byte-identical; corpus PLACED==23, per-log status
  unchanged with the param wired but inert). This lands the plumbing with zero placement change.
- **Step 2 (gated):** enable cross-frame translation behind the SAME default-OFF flag and prove on the
  corpus golden that **no** current placement changes (this is a false-positive-prevention +
  correct-linking layer, **not** a coverage-increase step).
- **log11 promotion to REVIEW/AUTO: needs more evidence.** The frame edge resolves the link, but the
  anchor-identity ambiguity (`decide` co-equal gate) is unresolved; promoting it requires separate,
  explicit evidence and must not loosen tolerances or the ambiguity gate.

Net: the foundation is ready and the wiring point is precise, but the *decision-affecting* surface is
`chains.py` **+** `score.py` (both frame-blind), so the smallest truly-safe move is the default-OFF
scaffold + a corpus no-regression gate — not a direct behavior change.
