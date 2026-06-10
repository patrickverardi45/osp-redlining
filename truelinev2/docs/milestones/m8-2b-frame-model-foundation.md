# M8.2b — frame model / parser foundation

**Status:** foundation only. **No placement decisions changed. No coverage increase
expected (placements remain 23/58).** Not wired into `run_match`.

## What this is

A small, isolated shared-core foundation for **station-frame modeling** and
**frame-equation parsing**, promoting the pure helpers proven read-only by the M8.2a
probe (`truelinev2/proof/run_frame_aware_probe.py`) into typed, reusable core modules.

A plan sheet defines a **station frame** (stationing local to that sheet). A matchline
carries a **frame equation** like `MATCH LINE STA 3+23 / 0+69 - SEE SHEET 17`, meaning
*this frame's STA 3+23 is the same physical point as sheet 17's STA 0+69* — a frame
translation of 254 ft. Linking callouts by **raw** station number across that matchline
is wrong (`0+69` here is not `0+69` there). M8.2a proved these equations are extractable
from the real plan text (83/83 candidates parseable, 24 unique cross-sheet edges, and
the log11 smoking gun `sheet 5 STA 3+23 ≡ sheet 17 STA 0+69`, HIGH/unique/no-conflict),
**and** that the corpus contains ambiguity (26 multi-link equations, 2 pair conflicts).
This milestone gives that evidence a typed home and a **safe** translation primitive.

## What was added

- **`truelinev2/schema/frames.py`** — types only (pydantic, `NewType` ids, `str` enums;
  convention-neutral): `FrameId`, `SheetFrame`, `StationValue`, `FrameEquation`,
  `FrameEdge`, `FrameGraph`, `ParseConfidence`, `EquationKind`, `FrameConflict`.
- **`truelinev2/match/frames.py`** — pure parser / normalizer / edge helpers (no IO, no
  global state, no convention names), reusing the single existing station parser
  `truelinev2.stations.parse_station`:
  - `parse_frame_equations(text)` — `STA a = b` / `STA a / b` → typed `FrameEquation`s,
    each classified by nearby `SEE SHEET N` + `MATCH LINE` context.
  - `build_frame_edges` / `detect_conflicts` / `safe_edges` / `build_frame_graph`.
  - `translate_station_ft(graph, from_frame, to_frame, feet)` — translate through a
    **safe** edge, or return `None` (abstain) when no safe edge connects the pair.
- **`truelinev2/tests/test_frames.py`** — the foundation's behavior contract.

## Eligibility & abstention rules (the safety contract)

- **Only HIGH-confidence, unique, conflict-free edges are eligible** to translate
  through. HIGH = an explicit matchline marker **and** exactly one linked frame.
- **Ambiguous or conflicting frame evidence must abstain.** Multi-link equations
  (≥2 `SEE SHEET` targets) build no edge; frame pairs with disagreeing offsets are
  recorded as `FrameConflict` and excluded from the translatable graph.
- **Raw equal station values across different frames are never proof.**
  `translate_station_ft` returns `None` for an unknown pair — the caller must abstain
  and must **never** fall back to the raw value.

## Relationship to existing modules

- `schema/hierarchy.py` already models Run/Segment with `frame` tags and the
  `ContiguityEvidenceKind.FRAME_EQUATION_RESET` / `MATCHLINE_CONTINUITY` kinds, and
  `match/assembly.py` already **refuses** to compose geometry across mismatched frames.
  M8.2b supplies the missing **translation** between frames — but wires nothing.
- The M8.2a probe is left **unchanged** (it still passes its own tests). To avoid any
  drift in its frozen read-only output, its dict-based helpers are not refactored onto
  the new typed core; `match/frames.py` is the canonical home going forward. *Tradeoff:*
  the equation grammar is intentionally re-stated in the core; converging the probe onto
  it is deferred to M8.2c.

## Not in scope

- No placement / matcher behavior change; no coverage change (stays 23/58).
- No tolerance widening; no ABSTAIN→REVIEW/AUTO promotion.
- No wiring into `run_match` / `chains` / `engine` / `decide` / `assembly`.

## Future (M8.2c, not started)

M8.2c **may** wire safe frame edges into chain assembly: translate a candidate
callout's station from its sheet frame into a neighbor's frame **before** testing
contiguity, so a proven cross-frame join (e.g. log11's two sheets) can compose —
strictly gated by the same abstain-first rules (HIGH / unique / conflict-free only).
