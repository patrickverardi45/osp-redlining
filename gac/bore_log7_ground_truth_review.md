# bore_log7 — Ground-Truth Review Packet (Terminal-Tail Placement)

**Prepared for:** GAC / Hector (operator review)
**Prepared by:** TrueLine engineering
**Purpose:** Decide, with a single yes/no, whether bore_log7's redline should be drawn on
the **Terminal-Tail route_469 ending at AP-163** instead of the **E Tom Green backbone route_477**.
**Scope:** ONE bore log (bore_log7). This packet proves a single review candidate — it does **not**
claim anything about the other redlines.

> **This packet changes nothing.** It is documentation only. No engine code was touched, no
> production flag was flipped, and no redline moves on the live site as a result of reading this.

---

## 1. Repo / commit / flag state

| Item | Value |
|---|---|
| Repository | `TrueLine_Beta` |
| Branch | `pdf-ap-route-shadow` |
| Commit (`origin/main`) | `20cb32f` (`20cb32fd3031457188a56b2a6af49019002489c2`) |
| Feature flag | `TRUELINE_TERMINAL_TAIL_PLACEMENT` |
| Flag default | **OFF** |
| Flag on Render (production) | **OFF — not flipped** |
| Requires (gate) | `TRUELINE_TERMINUS_TYPE_SHADOW=1` must also be on |

When the flag is OFF (the only state ever shipped to production), TrueLine behaves exactly as it
did before — bore_log7 is drawn on route_477. The new behavior below is reachable **only** when an
operator deliberately turns the flag on in a test environment.

---

## 2. What we know about bore_log7 (the evidence)

| Fact | Value | Source |
|---|---|---|
| Station range | **55 → 451** (verified live: min 55.0 / max 451.0) | bore_log7.xlsx (read by the rebuild) |
| Print token | **10** | bore_log7.xlsx |
| Access point reached | **AP-163** (a KMZ "Terminal Port Handhole" node) | KMZ + PDF plan |
| PDF plan run (sheet 10) | `STA 0+00 → 4+51 DIR. BORE (451') … TERMINAL 6 PORT HH AP-163 SPLICE LOC 46 … TERMINAL TAIL = 750'` | Brenham PH5 plan sheet 10 |
| AP-163 location (KMZ node) | `30.1591628, -96.3857298` | KMZ Terminal Port Handhole #163 |

**Plain reading of the plan sheet:** bore_log7 drilled a **451-foot directional bore that ends at
AP-163** — and on the plan, that 451-foot run is the *terminal tail* into AP-163, not a length of
the E Tom Green main line. The bore IS the tail.

---

## 3. OFF placement — route_477 (the legacy/today behavior)

| Item | Value |
|---|---|
| Route chosen | **route_477** (E Tom Green St backbone corridor) |
| Rendered start (lat, lon) | **30.152204, -96.380851** |
| Rendered end (lat, lon) | **30.151547, -96.381279** |
| Station points / segments | 10 / 9 |

**Why the engine picks route_477 today (two independent reasons, both in code):**

1. **The hardcoded print-sheet index** maps print token `10` to the E Tom Green corridor:
   `"10": {"sheet": 10, "streets": ["E TOM GREEN ST"], "route_ids": ["route_477"]}`
   — [backend/main.py:883](backend/main.py:883) (table `CURRENT_PACKET_PRINT_SHEET_INDEX`, lines 861–904).
2. **The PDF-evidence resolver is restricted to "backbone" routes only.** It deliberately
   **excludes Terminal Tails** from the routes it is allowed to choose:
   *"Terminal tails physically touch the AP terminal (~0 ft) but are short stubs, not the bored
   main line — so they are reported for transparency but are NOT chosen."*
   — [backend/app/core/pdf_ap_route_resolver.py:69](backend/app/core/pdf_ap_route_resolver.py:69) (and the backbone-only selection at lines 461–467).

So even though the plan shows bore_log7 ending at AP-163 on a tail, the engine's backbone-only rule
forbids the tail and falls back to the E Tom Green backbone.

---

## 4. ON placement — route_469 (the gated proof)

| Item | Value |
|---|---|
| Route chosen | **route_469** (Connections / **Terminal Tail**) |
| Route length | ≈ 459.2 ft (matches the 451 ft plan run within ~2%) |
| Rendered start (lat, lon) | **30.159452, -96.384495** |
| Rendered end (lat, lon) | **30.159167, -96.385706** |
| End vs AP-163 node | within **~0.5 ft** of AP-163 (30.1591628, -96.3857298) |
| Station points / segments | 10 / 9 |

**Why route_469 is the chosen tail (deterministic, no guessing):**

- A pure helper `resolve_terminal_tail_route_for_ap` returns the **UNIQUE** Terminal-Tail route whose
  endpoint is **≤10 ft from the AP** *and* whose length is **within 10% of the 451 ft plan run**;
  it returns nothing (safe abstain) if **zero or two-or-more** routes match —
  [backend/app/core/pdf_ap_route_resolver.py:1014](backend/app/core/pdf_ap_route_resolver.py:1014).
- At AP-163 only **route_469** passes both tests. The other routes touching AP-163 are rejected:
  a **194 ft Vacant Pipe** (wrong length) and **47–78 ft House Drops** (wrong type and length).
- bore_log7 is classified `backbone_ap_bore` because its end station (451) matches a directional-bore
  run that **ends at the AP-163 terminal-port handhole** in the verified plan table
  `(sheet 10, 451 ft, "ap", AP-163)` — [backend/app/core/pdf_ap_route_resolver.py:995](backend/app/core/pdf_ap_route_resolver.py:995).
- The redline is then oriented so **station 451 lands at AP-163** and re-rendered onto route_469 by an
  isolated post-pass — [backend/main.py:11650](backend/main.py:11650) (`_apply_terminal_tail_placement_override`).

---

## 5. Plain-English summary (for GAC / Hector)

- **Today ("old engine"):** TrueLine draws bore_log7's redline on the **E Tom Green backbone
  (route_477)**, near `30.1522, -96.3809`.
- **New gated proof:** TrueLine can instead draw it on the **Terminal Tail (route_469) that ends right
  at AP-163**, near `30.1592, -96.3857` — matching the plan sheet that says bore_log7 is the 451-foot
  directional bore terminating at AP-163.
- **These are two different places on the map — roughly 3,000 feet (about half a mile) apart.** Only one
  of them is where the crew actually drilled.
- **We need you to confirm which one matches the real redline.** Everything else stays exactly as it is
  until you do.

---

## 6. Reviewer question (one binary decision)

> **Should bore_log7's redline be drawn on route_469, the Terminal Tail ending at AP-163, instead of
> route_477?**
>
> ☐ Yes — route_469 (Terminal Tail to AP-163) is correct
> ☐ No  — route_477 (E Tom Green backbone) is correct

---

## 7. Hard warning

**Do NOT flip `TRUELINE_TERMINAL_TAIL_PLACEMENT` on Render, and do NOT widen this rule to any other
bore log, until a human confirms the answer above.** The flag is default-OFF and is not set in
production. This packet authorizes a *decision*, not a deployment.

---

## 8. Reference: side-by-side

| | Flag OFF (today) | Flag ON (proposed) |
|---|---|---|
| Route | route_477 (E Tom Green backbone) | route_469 (Terminal Tail → AP-163) |
| Start lat,lon | 30.152204, -96.380851 | 30.159452, -96.384495 |
| End lat,lon | 30.151547, -96.381279 | 30.159167, -96.385706 |
| End at AP-163? | no (≈3,000 ft away) | yes (≈0.5 ft) |
| Station points / segments | 10 / 9 | 10 / 9 |

**Whole-job safety (measured, both states identical):** corpus total **34 logs placed**, **334 station
points**, **286 redline segments** — *unchanged* whether the flag is OFF or ON. The before/after proof
confirms **only bore_log7 moves**; every other redline and every count is byte-for-byte identical. The
trust-ledger replay is **34 / 30 / 0 / 0 / 5** in both states. (Verified by the committed proof script
`scripts/bore_log7_before_after.py` and the unit-test suite `backend/tests/test_terminal_tail_placement.py`;
an adversarial safety review of the change passed 6/6.)
