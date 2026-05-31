# bore_log7 — Deterministic Route Adjudication (route_469 vs route_477)

**Question:** Do the *source files* (engineering PDF + KMZ + bore log) deterministically prove that
bore_log7's redline belongs on **route_469** (the Terminal Tail to AP-163) or **route_477** (the E Tom
Green backbone) — or do they expose an extraction gap?

**VERDICT: `route_469` is PROVEN by source evidence. There is NO extraction gap.**
route_477 is **not** supported by any source file — it is selected only by a hardcoded print-sheet index.
Human review is final audit of this proof, not the oracle.

> Nothing was placed, no flag was flipped, no engine/backend/web/data file was changed. This is an
> evidence adjudication. `route_469`/`route_477` are the route-catalog ids `_build_route_catalog`
> assigns to this KMZ's Terminal Tail at AP-163 and its E Tom Green underground-cable backbone.

---

## 1. The three source files agree (triangulated, raw-source verified)

| Source | File (read) | Literal evidence | Says |
|---|---|---|---|
| **Engineering PDF** | `…/raw/trueline/engineering-plans/brenham/Brenham - Phase 5_07-15-25.pdf`, **sheet 10 = page idx 22, title "10 OF 30"** | `STA 0+00 TO STA 4+51` · `DIR. BORE (451') 1-1.25" HDPE` · `E/W PORT TERMINAL TAIL` · `TERMINAL 6 PORT HH` · `AP-163 SPLICE LOC 46` · `TERMINAL TAIL = 750'` · `1009 E TOM GREEN ST` | bore_log7's 451' directional bore is an **E/W PORT TERMINAL TAIL terminating at AP-163** |
| **Bore log** | `…/Desktop/excel bore logs/bore_log7.xlsx` (cols: station/depth/boc/date/crew/print/notes) | station **0+55 → 4+51** (max 4+51); **print = 10** (all rows); crew tx1-4; 2026-01-06 | binds bore_log7 to **sheet 10**, end station **4+51** |
| **KMZ** | `…/Desktop/Brenham, TX - Phase 5_Design Team.kmz` (1116 placemarks) | AP-163 = `Nodes/Terminal Port Handhole` name `163` @ **30.15916283, -96.38572984**; the **only** AP-163 line matching the run = `Connections/Terminal Tail` **459.21 ft, endpoint 0.51 ft** from the node | the geometry of the 451' run to AP-163 = **route_469** (the Terminal Tail) |

**Binding chain (each link deterministic, no guessing):**
`bore_log7 (print 10, end STA 4+51)` → `sheet 10, the unique 451' DIR. BORE run` → `terminates at TERMINAL 6 PORT HH AP-163` → `KMZ AP-163 node` → `unique length+endpoint-matched Terminal Tail = route_469`.

---

## 2. Why route_469 is unique (not ambiguous)

- **Unique on the PDF sheet:** 451' is the only run of that footage on sheet 10 (the 16 run footages are 50/52/54/75/136/139/140/160/160/162/166/167/190/191/**451**/518). The 4+51 node is the AP-163 6-port handhole, **not** a flower pot. (A *different* vacant-HDPE drop run *begins* at 4+51 and runs away to its own flower pot — it does not end at AP-163.)
- **Unique in the KMZ:** of the 6 lines touching AP-163 (≤15 ft), only the **Terminal Tail (459 ft ≈ 451 ft)** matches the run length. The others are a 194 ft Vacant Pipe and four 47–78 ft House Drops — wrong type and length. The shipped `resolve_terminal_tail_route_for_ap` (uniqueness-mandatory, returns None on 0/≥2) resolves exactly one: route_469.
- **Computed placement geometry** (offline probe, real KMZ): start (STA 0+55) `30.1594514, -96.3844975` → end (STA 4+51) `30.1591615, -96.3857295` — **0.5 ft from the AP-163 node.**

---

## 3. route_477 is NOT source-supported (hardcode artifact)

The engine draws bore_log7 on route_477 today for **two engine-policy reasons, neither of which is source evidence:**

1. **Hardcoded print index** — `CURRENT_PACKET_PRINT_SHEET_INDEX["10"] = {sheet:10, streets:["E TOM GREEN ST"], route_ids:["route_477"]}` ([backend/main.py:883](backend/main.py:883); route_477 = "E Tom Green St corridor", comment :869). This is a Brenham-era backbone-by-street index; it has no notion of terminal tails.
2. **Backbone-only resolver exclusion** — `_BACKBONE_FOLDER_SUBSTRINGS = ("underground cable",)` and the comment *"Terminal tails physically touch the AP terminal (~0 ft) but are short stubs… NOT chosen as pdf_allowed_route_ids"* ([pdf_ap_route_resolver.py:69-72](backend/app/core/pdf_ap_route_resolver.py:69)); `pdf_allowed` is built from `ranked_backbone` only ([:461-467](backend/app/core/pdf_ap_route_resolver.py:461)).

**The KMZ refutes route_477 for this bore:** there is no LineString named "E Tom Green" (it appears only as house street-addresses); the nearest underground-cable/backbone vertex is **362.72 ft** from AP-163. The backbone does not reach AP-163, but bore_log7's plan run explicitly ends *at* AP-163. So route_477 contradicts the source; route_469 matches it.

This is exactly the *"legacy Brenham-era hardcode may be bypassed when source evidence contradicts it"* case from the operating rule — and Target #14's `TRUELINE_TERMINAL_TAIL_PLACEMENT` is the scoped, default-OFF mechanism that already does so (only bore_log7 moves; counts + trust-ledger 34/30/0/0/5 identical OFF/ON).

> **Reconciliation with Target #13:** #13's `BLOCKED_CHAIN_OR_ROUTE_MISMATCH` was measured *against the shipped backbone-only invariant*, not against the source files. Under source-evidence adjudication (this packet), that "conflict" resolves: the invariant is the thing that is wrong for tail bores; the source proves route_469.

---

## 4. Adversarial checks (no residual gap)

- **Start offset (0+55 vs 0+00):** the bore log records 0+55→4+51; the designed run is 0+00→4+51. The **end** (4+51 = AP-163) is the load-bearing anchor and is exact; the 55 ft head is just where logging began. Not an ambiguity.
- **"TERMINAL TAIL = 750'" vs 451'/459':** 750' is the designed terminal-tail cable allotment (incl. coil/slack); the *bore* is 451' and the KMZ tail *path* is 459 ft (within 2%). Consistent, not contradictory.
- **Committed table matches raw PDF:** `BRENHAM_PH5_RUN_ENDPOINTS` row `(10, 451.0, "ap", 163)` ([pdf_ap_route_resolver.py:995](backend/app/core/pdf_ap_route_resolver.py:995)) equals the independently re-extracted sheet-10 text; no flower_pot at 451 on sheet 10 → unique.

---

## 5. Exact next redline action

1. **bore_log7 is adjudicated — route_469, proven from source.** No further evidence is needed; no human "vibe" decision is required. The remaining step is operator **final audit** of this proof, then (operator-side, not this session) flip `TRUELINE_TERMINAL_TAIL_PLACEMENT` (+ its `TRUELINE_TERMINUS_TYPE_SHADOW` gate) on Render to activate the already-shipped, already-safe route_469 placement. No code change is required — the engine path exists (Target #14).
2. **Next lane (same method):** apply this deterministic terminus adjudication to the **flower-pot DROP lane** (bore_log5/30/48/50/65). The PDF run→endpoint table already carries their flower-pot termini (e.g. sheet 9 `650 → flower_pot`, sheet 11 `514 → flower_pot`); prove each drop bore terminates at its flower-pot node and place it on its short VACANT-HDPE drop geometry instead of the route_480 backbone — under a scoped, default-OFF override, DO-NOT-WIDEN intact.

---

## 6. Files read for this adjudication
- `backend/app/core/pdf_ap_route_resolver.py` — `BRENHAM_PH5_RUN_ENDPOINTS` (:989-1006), `_BACKBONE_FOLDER_SUBSTRINGS` (:69-72), `pdf_allowed` selection (:461-467), `resolve_terminal_tail_route_for_ap` (:1014).
- `backend/main.py` — `CURRENT_PACKET_PRINT_SHEET_INDEX` token "10" (:883) + route_477 calibration comment (:869).
- `scripts/bore_log7_placement_diag.py` (ran; real KMZ) — route_469 geometry + AP-163 gap.
- Raw source (subagent, read-only): `Brenham - Phase 5_07-15-25.pdf` sheet 10; `Brenham, TX - Phase 5_Design Team.kmz`; `bore_log7.xlsx`.
