# M8.24: log42 START Origin Identity — NOT Bindable (formal ABSTAIN + reframe)

Status: **SAFE ABSTAIN.** log42's START origin identity cannot be bound by any
lane-accepted printed path; its only printed-bound structure is its END
terminal. log42 stays `STRUCTURE_IDENTITY_BINDING_REQUIRED`; census frozen
`25/13/5/5/4/3/1/2 = 58`; proof-only; **NOT a REVIEW candidate**.

Probe: `truelinev2/proof/run_origin_identity_abstain_probe.py` (G1–G7 PASS)
Tests: `truelinev2/tests/test_origin_identity_abstain_probe.py` (6)
Panel: 4-lens adversarial review, all SOUND_WITH_HARDENINGS, 0 blocking.

## 1. START origin identity is NOT bindable (the answer)

The dominant shipped-lane abstain is the `cross_sheet_origin` corroboration-
band refusal: the far segment is PROVEN (0+00→2+70, 270', closure ok) but **11
sheet-2 structures reach the shared matchline and 0 corroborate** — the START
structure identity can't be uniquely bound. Corroborating that, the 0+00
origin is printed-**UNIDENTIFIED** four ways:
- `bind_origin_by_parent_station(0.0)` = REQUIRED (no `=0+00` equation has
  parent==0; M8.6 "0+00 is frame-local");
- `bind_end_structure_note(0.0, sheet2)` = REQUIRED (no `STA 0+00 <structure>`);
- no AP at the origin (only AP-106/AP-107, 338/370 pt away);
- the origin NEXTLINK symbol @(819,351) is unidentified by **both**
  discriminators — label (only conduit annotations near it) **and** fill
  (None/white/black, neither installer-red nor terminal-blue).

## 2. Reframe: the bound structure is the END terminal

log42's ONLY printed-bound structure is its END TERMINAL — `TERMINAL 6 PORT HH
AP-105` at 2+87 (M8.23). The run is `E/W PORT TERMINAL TAIL`; the 0+00 origin
is printed-unidentified. **This is NOT a universal "terminal tails are
free-origin" law** — log8/log32 share the same unidentified-origin situation
(`bind_end_structure_note(0.0, sheet18)` = REQUIRED), and their M8.20 group
card is REVIEW-only precisely because their origin identity is likewise unbound
(the M8.20 multi-drop survivor is a POSITION, not a lane-accepted identity).
The "bind the origin" approach M8.21/M8.22/M8.23 circled is the wrong frame.

## 3. Owner Segment-B answer: callout-frame origin

Segment B's 0+00 = the callout-frame ORIGIN, not the installer reset. Forced by
log42's declared span (287 = 270+17) + the printed-bound END terminal at 2+87 +
the interiority of the installer reset (`STA 0+46=0+00`, M8.21
INTERIOR_RESET_NOT_ORIGIN). **Not** read from the log41 44-vs-46 hand digit,
which stays the separate `SOURCE_DIGIT_REREAD_REQUIRED` (M8.21 §4). This
finding IS the cheap answer to the owner bore_log13 re-read.

## 4. Named next capability (interpretive direction only — ships no code)

An **ORIGIN-SYMBOL-IDENTITY binder**: bind the far-sheet origin structure
symbol (an x,y on sheet 2) from the bound END terminal via a LANE-ACCEPTED,
uniqueness-mandatory frame relationship the M8.2f transition classifier
currently rejects as ambiguous on the (1,2) hop. Net-new work; requires its own
adversarial review. Explicitly **NOT**:
- **M8.5 `reverse_anchor`** — a footage START-POSITION solver in `run_match`,
  identity-agnostic, never composed into `resolve_bore`; it would NOT satisfy
  `STRUCTURE_IDENTITY_BINDING_REQUIRED` (so log42 is not "one opt-in away");
- **`station_axis`** — FRAME_OR_SHEET_CONFLICT on raw 2+87;
- **M8.22 directional filter** — proof-only, barred from Law-1/M8.18/M8.19.

All three already refuse log42.

**Latent hazard named for that future work** (does not affect log42): START-
identity step 3 runs `bind_end_structure_note` over every referenced sheet incl.
the END sheet with no frame-ownership check. For log42 the *only* thing
preventing a cross-frame false START bind to sheet-1's unrelated `STA 0+00 …
NEXTLINK HH … SPLICE` note is that `_classify_label` returns None on it. The
terminal-tail capability must gate the start-note match by FRAME OWNERSHIP.

## 5. Boundary

Proof-only; census frozen; log8/log32 + the M8.20 group review untouched
(re-proven); no stroke/PNG/segment, no AUTO, no tolerance/budget change, no
REVIEW promotion; the M8.22 directional survivor stays barred. Outcome: SAFE
ABSTAIN (the evidence says there IS no origin identity) + a sharply-specified
named next capability.
