# M8.2c Step 2 Phase 0 — activating frame translation (read-only plan)

**Status:** planning only. No engine change, no tests, no placement change. Default
behavior stays byte-identical; coverage stays **23/58**. This decides the safest minimal
way to *activate* frame translation — but only when an explicit `frame_graph` is supplied.

## Executive summary

Step 1 threaded an inert, keyword-only `frame_graph=None` into `build_chains`
(`chains.py:19`), `score_chain` (`score.py:14`), and `run_match` (`engine.py`). Step 2
makes that parameter *do something* — but ONLY when a graph is passed. The two frame-blind
seams are the link test (`chains.py:34`) and the endpoint deltas (`score.py:17-18,23-24`).
The safe activation: same-sheet links stay raw; **cross-sheet** links and endpoint deltas
go through a **safe frame edge** via the M8.2b `translate_station_ft`; if no safe edge
connects the two sheets, **no link / no score** (abstain — raw equality is never proof).
`frame_graph=None` keeps both seams byte-identical, and `decide.py` is never touched, so the
anchor-ambiguity gate still blocks log11. Because the translation can be proven entirely
with synthetic fixtures while every *real* caller keeps passing `None`, Step 2 changes
nothing on the corpus — the real-graph wiring is a separate, later, opt-in step.

## Current inert plumbing state

- `build_chains(..., *, frame_graph=None)` — `chains.py:16-19`; param never read; raw link at `chains.py:34`.
- `score_chain(..., *, frame_graph=None)` — `score.py:12-14`; param never read; raw deltas at `score.py:17-18,23-24`.
- `run_match(..., *, frame_graph=None)` forwards it to both (`engine.py`); all real callers pass nothing ⇒ `None`.
- `match.frames` (M8.2b) provides: `frame_for_sheet(sheet)→FrameId`, `build_frame_graph(edges)→FrameGraph`
  (keeps only HIGH/unique/conflict-free **safe** edges), and `translate_station_ft(graph, from_frame, to_frame, feet)→Optional[float]`
  (same-frame identity; safe forward/reverse edge; **None** when no safe edge — caller must abstain).
- `Callout.sheet` is the frame identity (`schema/models.py`) — no model change needed.

## Proposed translation rule

A single pure helper added to `match.frames` (additive; M8.2b stays unchanged):

```
translate_between_sheets(graph, from_sheet:int, to_sheet:int, feet:float) -> Optional[float]
    = translate_station_ft(graph, frame_for_sheet(from_sheet), frame_for_sheet(to_sheet), feet)
```

Returns the feet value re-expressed in `to_sheet`'s frame, or **None** when no SAFE edge
connects the two sheets. `from_sheet == to_sheet` ⇒ identity. This is the only new logic;
`chains.py`/`score.py` call it, keeping the frame math in the foundation.

## `build_chains` plan (the link test, `chains.py:34`)

Replace the single raw test with a graph-gated branch (the `None` branch is the verbatim
current line, so default is byte-identical):

```
if frame_graph is None:
    linkable = abs(last.to_ft - c.from_ft) <= link_tol and c.to_ft > last.to_ft   # current, unchanged
elif last.sheet == c.sheet:
    linkable = abs(last.to_ft - c.from_ft) <= link_tol and c.to_ft > last.to_ft   # same frame -> raw
else:
    cf = translate_between_sheets(frame_graph, c.sheet, last.sheet, c.from_ft)
    ct = translate_between_sheets(frame_graph, c.sheet, last.sheet, c.to_ft)
    linkable = (cf is not None and ct is not None
                and abs(last.to_ft - cf) <= link_tol and ct > last.to_ft)         # cross frame -> safe edge only
```

The start match (`chains.py:24`) stays raw: the start anchors near `0+00` in both the bore
frame and the start sheet's frame, and there is no "bore-frame ↔ sheet" edge to translate
through. Frame-awareness is confined to the cross-sheet **link**.

## `score_chain` plan (the deltas, `score.py:17-18,23-24`)

Translate the chain's far endpoint into the chain's ANCHOR frame (`chain[0].sheet`) before
computing `end_delta`, so a cross-frame chain is measured on one frame:

```
chain_start = chain[0].from_ft                          # anchor frame
if frame_graph is None or chain[-1].sheet == chain[0].sheet:
    chain_end = chain[-1].to_ft                         # current path (unchanged when None / single sheet)
else:
    chain_end = translate_between_sheets(frame_graph, chain[-1].sheet, chain[0].sheet, chain[-1].to_ft)
    if chain_end is None:                               # cross-frame but not translatable to the anchor
        # mark unscoreable so decide() rejects it (no false placement) -- e.g. a large end_delta sentinel
        ...
```

`summed_ft`/`foot_delta` (footage) are frame-independent and unchanged; `sheets`/`multi_sheet`
unchanged. Only `end_delta` (and never `start_delta`, anchored at `chain[0]`) consults the graph.

**Multi-hop caveat:** `translate_station_ft` walks **direct** safe edges only. A chain
spanning A→B→C links pairwise (single hops) in `build_chains`, but scoring C into A's frame
needs an A↔C edge that may not exist ⇒ `translate_between_sheets` returns `None` ⇒ the chain
is marked unscoreable ⇒ `decide()` rejects it. So Step 2 safely supports SINGLE cross-frame
hops (the log11 case) and **abstains** on multi-hop until a later composition step. No
truncation, no false placement.

## Same-sheet behavior

Identical to today. `last.sheet == c.sheet` ⇒ raw link; `chain[0].sheet == chain[-1].sheet`
⇒ raw `end_delta`. The graph is never consulted for single-frame chains, so every current
single-sheet placement is untouched even when a graph is supplied.

## Cross-sheet behavior

A cross-sheet link forms **only** through a safe edge translation. Cross-sheet raw-foot
coincidence (two callouts that share a raw station number across a matchline) is **no longer
linked** when a graph is supplied — exactly the frame-blind false positive Step 2 removes —
and the true continuation (translated) is found instead.

## Ambiguity / conflict behavior

Automatic from M8.2b: `build_frame_graph` keeps only `safe_edges` (HIGH confidence, unique
link, conflict-free); ambiguous (multi-link / non-HIGH) and conflicting edges are recorded in
`graph.conflicts` but never in `graph.edges`. So `translate_station_ft`/`translate_between_sheets`
return `None` for them ⇒ **no link, no score, abstain**. Ambiguous/conflicting/missing frame
evidence can never create a link.

## log11 expected behavior

log11 references sheets 5 and 17; the probe's safe edge is `sheet 5 STA 3+23 ≡ sheet 17 STA
0+69` (offset 254 ft, HIGH, unique, no conflict). With a graph containing it:
- **Link:** a sheet-5 callout ending at `3+23` (323 ft) links to a sheet-17 callout starting
  at `0+69` — `translate_between_sheets(g, 17, 5, 69) = 69 + 254 = 323 ≈ last.to_ft` ⇒ the
  true cross-frame chain forms (raw 323≠69 never would).
- **Anchor ambiguity is NOT bypassed.** `decide()` (`decide.py:44-50`) still abstains on ≥2
  co-equal candidates. The probe flagged log11's `0+00` anchor ambiguity; the frame edge
  resolves the *link*, not the *anchor*. Expected: log11 may form the correct chain yet still
  ABSTAIN on anchor ambiguity — **frame translation must not promote it.**
- **In Step 2 (synthetic-only), the real corpus passes `frame_graph=None`, so log11 stays
  ABSTAIN and coverage stays 23/58.** Promotion is out of scope here and forbidden.

## Regression risks

- **Default path: none.** `frame_graph=None` ⇒ both seams are the verbatim current code
  (byte-identical). The corpus sweep and `run_match`'s real callers pass `None`, so 23/58 is
  unchanged in Step 2.
- **When a real graph is later supplied (deferred step), risk is bidirectional via `decide()`:**
  a translated chain can become a co-equal rival → flip a current unique placement to
  ambiguity-ABSTAIN; removing raw cross-frame links can drop a chain a placement relied on.
  This is why real-corpus activation must be gated by a per-log no-regression golden — and is
  **not** part of Step 2.
- **Unscoreable cross-frame chains** must reject cleanly (sentinel `end_delta`), never coerce
  to a small delta — otherwise a false placement. Covered by the test plan.

## Test plan (synthetic fixtures only — no PDF / no corpus)

1. `frame_graph=None` ⇒ `build_chains`/`score_chain` byte-identical (re-assert Step 1 contract).
2. Same-sheet chain + a populated graph ⇒ identical to raw (graph not consulted for one frame).
3. Cross-sheet + safe edge ⇒ link forms; `end_delta` computed in the anchor frame (synthetic log11).
4. Cross-sheet + **no** safe edge ⇒ no link (raw equality not proof).
5. Cross-sheet + ambiguous/conflicting edges (absent from `safe_edges`) ⇒ no link.
6. Multi-hop cross-frame (no direct anchor edge) ⇒ unscoreable ⇒ `decide()` rejects (abstain).
7. **Anchor-ambiguity preserved:** feed `decide()` synthetic scored chains incl. the translated
   one plus a co-equal rival ⇒ still ABSTAIN (`GE_2_COEQUAL_CANDIDATES_NO_TIEBREAKER`),
   proving translation does not bypass the gate (read-only use of `decide`, no edit).
8. **Corpus sweep with `frame_graph=None` (default) ⇒ PLACED=23 / 14 / 9 / 33 / 2 unchanged.**
9. Drift guards + standalone import isolation + M8.2a probe unchanged; no convention names in core.

**Answer to "can Step 2 be tested entirely with synthetic fixtures?" — YES.** Every rule
above is exercised with synthetic `Callout`s + synthetic `FrameGraph`s; the only real run is
the `None`-default corpus sweep proving non-regression.

## Exact files likely to change if implemented

- `match/chains.py` — graph-gated link branch at the seam (`:34`).
- `match/score.py` — graph-gated anchor-frame `end_delta` (`:18,:24`).
- `match/frames.py` — **add** `translate_between_sheets` (thin wrapper over `translate_station_ft` +
  `frame_for_sheet`); M8.2b functions unchanged.
- `truelinev2/tests/test_frame_translation.py` — **new**, synthetic.
- (this doc.)

## Files that must remain untouched

- **`match/decide.py`** — the anchor-ambiguity gate; **never edited** (the whole safety argument).
- `match/engine.py` (already threads `frame_graph`; real callers keep passing `None`),
  `match/overlap.py`, `match/assembly.py`, `schema/hierarchy.py`, `schema/models.py`,
  `schema/frames.py` (types; additive only if ever needed), `stations.py`, the M8.2a probe,
  the corpus harness `proof/run_brenham_corpus.py` (keeps passing `None` — no real-graph
  activation in Step 2), every `extract/`/`ingest/` adapter, all `backend/`, `web/`, `main`,
  Render, Vercel.

## Recommendation

**Implement now as synthetic-fixture-only behavior.**

Activate the translation in `build_chains`/`score_chain` (consulted ONLY when `frame_graph`
is supplied) plus the one `match.frames` helper, and prove it **entirely with synthetic
fixtures** — safe-edge link, no-edge / ambiguous / conflict no-link, multi-hop abstain, and
(critically) anchor-ambiguity-still-abstains-through-`decide()`. Keep **every real caller
(`run_match` in the corpus sweep) passing `frame_graph=None`**, so default behavior and the
23/58 corpus stay byte-identical and `decide.py` is untouched.

**Defer** the real-corpus graph wiring (building a `FrameGraph` from the plan and passing it
into `run_match`) to a separate, explicitly-opted-in step gated by a per-log no-regression
golden — that is where the bidirectional `decide()` regression risk and any log11 promotion
question live, and it must not be entered here. This keeps Step 2 small, fully provable
offline, zero-regression by construction, and honors every guardrail (no `decide` edit, no
tolerance widening, no ABSTAIN→REVIEW/AUTO promotion, no default-behavior change).
