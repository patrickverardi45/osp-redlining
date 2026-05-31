# Target #23 — Remaining route_480-Bucket Proof Sweep (57, 29, 31, 46, 47, 58) — READ-ONLY

**Question:** can any of the 6 still-unproven route_480-bucket logs become PROVEN from
existing source evidence, or is a specific artifact missing per log?

**VERDICT: 0 / 6 provable. All 6 BLOCKED. With this, the ENTIRE 14-log route_480 bucket
is fully classified — every residual abstention now has a named missing artifact, and no
bucket log is provable from the files we have.**

> Read-only. No placement, no geometry, no flag, no engine/STATE change. In-repo
> run-endpoint table + matchline station graph + read-only bore xlsx.
> Probe: `scripts/route480_remaining_proof_sweep.py` → `.out`.

---

## 1. Method (three lanes, one deterministic probe)

A focused probe encodes all three lanes the goal named — deterministic > parallel agents
here, because the proof gate is a table lookup, not a judgement call:
- **L1 bore facts** — prints, station min/max/span, rows, notes (real xlsx).
- **L2 run/matchline** — every `BRENHAM_PH5_RUN_ENDPOINTS` terminus within 15 ft of the
  bore END station on its print sheets, + `brenham_plan_sheet_graph` corridor context.
- **L3 KMZ/route** — a KMZ binding is reachable ONLY if L2 yields a UNIQUE, unambiguous
  named-AP terminus (the exact mechanism that proved bore_log7).

**Proof gate (adversarial):** PROVABLE requires exactly ONE named-AP run terminus within
tol AND no competing terminus (named or unnamed matchline/splice) AND a single corridor AND
a non-flagged print mapping. A lone named-AP hit is NOT sufficient — a co-located matchline
or a multi-corridor span makes the END frame-ambiguous. *(First pass over-claimed bore_log57
PROVABLE on the bare AP-157 hit; the gate was corrected to catch the competing sheet-13
matchline + 2-corridor span — the same multi_drive_unknown ambiguity Target #10 found.)*

## 2. Per-log verdict table

| log | prints | sta (span) | END run-terminus hits (≤15 ft) | corridor | verdict | missing artifact |
|---|---|---|---|---|---|---|
| **bore_log57** | 8,10,13 | 0–413 (413) | AP-157@413 (sheet 8) **AND** matchline@398 (sheet 13) | spans 2 | **multi_drive_terminus_ambiguous** | `.FS` drive-decomposition (which drive/terminus; +print mapping flagged uncertain) |
| **bore_log29** | 10,12 | 0–415 (415) | NONE | {10,12,13,14} | **no_run_terminus_match** | `.FS` drive-decomposition OR bore-log terminus field |
| **bore_log31** | 10,12 | 0–260 (260) | NONE | {10,12,13,14} | **no_run_terminus_match** | `.FS` drive-decomposition OR bore-log terminus field |
| **bore_log46** | 10,13,14 | 0–534 (534) | NONE (AP-161@534 is a LABEL, not a run terminus — excluded per #10) | {10,12,13,14} | **no_run_terminus_match** | `.FS` drive-decomposition OR bore-log terminus field |
| **bore_log47** | 10,13,14 | 325–494 (169) | NONE | {10,12,13,14} | **no_run_terminus_match** | `.FS` drive-decomposition OR bore-log terminus field |
| **bore_log58** | 8,10,13 | 0–256 (256) | NONE | spans 2 | **no_run_terminus_match** | `.FS` drive-decomposition OR bore-log terminus field |

## 3. Source evidence per finding

- **bore_log57 (ambiguous, NOT provable):** END 413 is within tol of a NAMED terminus
  (AP-157 run end, sheet 8) AND an UNNAMED one (sheet-13 matchline @ 398, |413−398|=15).
  The bore spans two independent chainage corridors (`{3..9}` via print 8; `{10,12,13,14}`
  via 10/13) and its own notes flag *"print mapping uncertain — preserved full source print
  '8,10,13'"* (split from bore_log24, crew Jimenez). So the 413 terminus cannot be uniquely
  bound to AP-157 vs the matchline — exactly the Target #10 `multi_drive_unknown` call.
- **bore_log29/31/46/47/58 (no_run_terminus_match):** each is a continuous multi-drive bore
  (local 0+00 frame; 4 of 5 start at 0) whose END station hits NO `DIR.BORE` run terminus
  within 15 ft on its print sheets. The sheet-10/12 termini are at 136/140/189/350/355/451/
  507/510/514 (APs + flower pots) — none near 256/260/415/494/534. bore_log46's 534 matches
  AP-161 *as a label only*; AP-161 is not a run terminus (Target #10 anti-artifact rule),
  so it is correctly excluded. bore_log47/46 are Segment B/C splits of bore_log18; bore_log58
  is a Segment B split of bore_log24 — multi-drive provenance, not single-terminus drives.

## 4. The exact missing relationship (named; same class proven absent in #8/#10/#20)

For all 6: the **`.FS` Fiber-Schematic / drive-decomposition sheet** that maps each
continuous multi-drive bore's station sub-ranges → drive → terminating structure. The
Fieldwire register (Target #8) literally references it (`AP-155 .FS 9`, `AP-168 .FS 11`),
but the `.FS` sheet set is **ABSENT from all 3 provided Brenham PDFs** (re-confirmed by the
Target #22 corpus sweep — no `*fiber*`/`*schematic*`/`.FS` file anywhere in the wiki tree).
Equivalently, a **per-bore terminus-structure / AP / direction field** on the bore xlsx
would resolve it — but the xlsx carries only station/depth/boc/date/crew/print/notes (no
terminus column). bore_log57 additionally needs its print mapping disambiguated.

This is **not** "ask a human to guess" — it is a specific field the design tool / field crew
records that is missing from the delivered files.

## 5. Did any remaining log move closer to PROVEN?

**No.** 0/6. All stay correctly abstaining (interim safety state + named target). This
re-confirms the exhaustive Targets #8/#9/#10 conclusion at the per-log terminus level: the
bore-log lineage has no recorded join to the AP/drive lineage, and the `.FS` schematic that
would supply it is absent.

## 6. Bucket-level closeout (durable)

All 14 route_480-bucket logs are now accounted for, each with a named missing artifact:

| lane | logs | status | missing artifact |
|---|---|---|---|
| backbone-AP tail | bore_log7 | **PROVEN → route_469** | none (shipped Target #14/#16/#18) |
| DROP / flower-pot | 5,30,48,50,65 | BLOCKED | flower-pot identity key (Target #20) |
| main-chain high-station | 16,43 | BLOCKED | high-station station↔geometry anchor (Target #22) |
| multi-drive ambiguous | 57 | BLOCKED | `.FS` drive-decomposition + print disambiguation |
| no-run-terminus | 29,31,46,47,58 | BLOCKED | `.FS` drive-decomposition / bore terminus field |

The bucket's residual abstentions reduce to **three acquisition artifacts**: (a) flower-pot
identity key, (b) a high-station anchor + direction, (c) the `.FS` drive-decomposition sheet
(which also covers the 6 here). No route_480 log is provable from the current files.

## 7. Next blocker

Acquire the **`.FS` Fiber-Schematic / drive-decomposition sheet** for Brenham PH5 (the
single highest-leverage artifact — it unblocks the 6 here AND the 5 DROP logs' multi-drive
ambiguity). Until then these 6 abstain. No code helper falls out (a shadow would abstain on
100% of inputs — same as Targets #20/#22). DO-NOT-WIDEN intact; proven lane unchanged
(bore_log7 → route_469); all flags default-OFF.

## 8. Files read
- `BRENHAM_PH5_RUN_ENDPOINTS` ([pdf_ap_route_resolver.py:989](backend/app/core/pdf_ap_route_resolver.py#L989)) — run-endpoint table (read).
- [brenham_plan_sheet_graph.py](backend/app/core/brenham_plan_sheet_graph.py) — matchline corridor graph (read).
- bore xlsx 57/29/31/46/47/58 (read-only) via `_read_bore_log_rows` / `_parse_print_tokens`.
- Prior: `gac/mainchain_high_station_adjudication.md` (#21), Target #10 terminus probe.
- Probe: `scripts/route480_remaining_proof_sweep.py` → `.out`.
