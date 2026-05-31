# Target #20 — DROP-Lane Flower-Pot Identity Extraction (SHADOW investigation, READ-ONLY)

**Question (from Target #19):** can the source files uniquely bind each DROP bore
(bore_log5/30/48/50/65) to a specific KMZ flower-pot node / drop route — i.e. extract a
*drop identity key* — or is a named artifact missing?

**VERDICT: BLOCKED for all 5. No unique drop-identity key exists in the current files.**
But the investigation found a **real, previously-unused data source** (the KMZ `<description>`
HTML tables, which the production parser drops) and proves *exactly why* it still doesn't
close the gap. This sharpens the missing artifact and gives a ready helper design for when it
arrives.

> Read-only. No redline placed, no geometry moved, no flag flipped, no engine/STATE change.
> Probes: `scripts/drop_identity_probe.py`, `drop_identity_desc.py`, `drop_identity_geom.py`,
> `drop_pdf_terminus_probe.py`.

---

## 1. NEW FINDING — the KMZ carries rich `<description>` metadata the parser discards

The production `_build_kmz_reference` keeps only `{feature_id,name,folder_path,role,lat,lon}`,
but every placemark's raw KML `<description>` is an HTML key/value table. Extracted fields:

| structure | count | description fields | uniquely-identifying field? |
|---|---|---|---|
| **House** (point) | 290 | AP Number, **Address**, Street Name/Number, Splice Location, … | **Address (290 distinct)**, AP Number (64 distinct) |
| **Terminal Port HH** (point) | 64 | **AP Number**, Note, Scid, HH Sizes | **AP Number (64 distinct)** |
| **Flower Pot** (point) | 158 | Flower Pot Size, Node Type, Internal Note(empty) | **NONE** (Size = 1 distinct "11x11x12"; Scid empty for 157/158) |
| House Drop (line) | 422 | Connection Type, Note(empty) | NONE |
| Vacant Pipe (line) | 58 | Connection Type, Note(empty) | NONE |
| Terminal Tail (line) | 51 | Connection Type, Fiber Size(empty), Note(empty) | NONE |

**The pattern is consistent with field reality:** Houses and APs are *committed* structures, so
they carry an Address / AP Number. A **Flower Pot is a VACANT future-drop terminus** — it has
no resident, no address, no unit id yet. So the drop terminus layer is **identity-less by design**,
not by a parsing bug.

---

## 2. Per-bore evidence

| bore | print/sheet | end STA | PDF terminus | KMZ candidate | binding |
|---|---|---|---|---|---|
| bore_log5 | 12 | 500 | flower_pot @ 507 & 510 (sheet 12) — **non-unique on PDF** | 158 unnamed pots; pot→drop-route 2–6 each | **BLOCKED** |
| bore_log30 | 10,12 | 500 | flower_pot @ 507 & 510 (sheet 12) — non-unique | same | **BLOCKED** |
| bore_log48 | 10,11,12 | 509 | flower_pot @ 510, 507, 514 (sheets 11/12) — non-unique | same | **BLOCKED** |
| bore_log50 | 10,11,12 | 514 | flower_pot @ 514 (sheet 11) — **PDF-unique** | but pot node has no station/id/latlon bridge | **BLOCKED** |
| bore_log65 | 9,10 | 650 | flower_pot @ 650 (sheet 9) — **PDF-unique** | same | **BLOCKED** |

Two of five (bore_log50, bore_log65) are even **PDF-unique** at the run-endpoint level — yet still
BLOCKED, because the **KMZ side cannot convert a (sheet, station) terminus into one specific
flower-pot node**: the 158 pots are unnamed, carry no station, and no key joins PDF→pot.

---

## 3. Every candidate key tested — and why each fails

1. **Flower-pot own id (name / SCID / description):** absent. Name = "Unnamed Feature" ×158;
   description = "Flower Pot Size 11x11x12" (1 distinct); Scid populated on 1/158. **No id to join.**
2. **Street address printed on the PDF:** the sheets *do* print addresses (e.g. sheet 11
   "1205/1207/1209 E TOM GREEN ST"; sheet 12 "1206 LEDBETTER LN", "1004 BEN DR"…), **but they do
   not attach to a specific flower-pot callout** — the `FLOWER POT STA n+nn` callouts carry no
   address and no unit number (`numeric token after 'FLOWER POT' = NONE`). And the **KMZ flower
   pots have no Address field** (only Houses do). So there is no PDF-address ↔ KMZ-pot join.
3. **Nearest parent AP via geometry:** Houses carry AP Number, but a flower pot is not a house;
   flower-pot → nearest-house distance is min 41 ft / median 63 ft / max 369 ft. Geometry to a
   parent AP is **not clean** (and a pot doesn't carry the AP anyway).
4. **Nearby drop-route endpoint:** each flower pot sits within 10 ft of **2–6 drop routes**
   (distribution: 1 route→2 pots, 2→15, 3→53, 4→71, 5→11, 6→3). **Not a unique pot→route map.**
5. **Route description/folder metadata:** drop routes carry only "Connection Type" (House
   Drop / Vacant Pipe) — no name, station, or address. **No id.**
6. **Station-distance on the PDF run / local adjacency to a proven path:** the bores are
   continuous **multi-drive** (print spans 10/11/12) and several flower pots are co-located at near
   stations on the same sheet (sheet 12: STA 4+45, 5+07, 5+10). The bore records only an *end*
   station; without the drive decomposition, the true terminus pot is not isolable.

**Root cause (one sentence):** the drop terminus is a *vacant* structure with no identity in any
provided file, and the join that a committed structure would have (Address/AP) does not exist for
vacant pots — so PDF station → specific pot is irreducibly ambiguous from current data.

---

## 4. Exact missing artifact (name it for the next step)

One of these (any single one closes the gap), in increasing order of effort:

1. **A populated flower-pot identity in the KMZ** — a SCID / unit-id / served-address on each
   `Nodes / Flower Pot` placemark (the field exists in the schema; it is empty for 157/158 pots).
   Smallest fix; lives in the design KMZ.
2. **The `.FS` Fiber-Schematic / drive-decomposition sheet** (named absent in Targets #8/#9/#10) —
   maps each bore's station sub-ranges → drive → specific structure. Resolves both the multi-drive
   ambiguity *and* the pot identity.
3. **A served-structure column in the bore-log xlsx** (address or pot/SCID) — a direct join key;
   currently the bore log has only station/depth/boc/date/crew/print/notes.

This is **not** "ask a human to guess" — it is a specific data field that the design tool (or the
field crew) records but that is absent from the files we were given.

---

## 5. Pure read-only helper design (for when a key exists) — `resolve_flowerpot_drop_identity(...)`

Designed but **NOT implemented** (no placement code this target). Mirrors the proven
`resolve_terminal_tail_route_for_ap` shape: two deterministic stages, uniqueness-mandatory,
returns `None` on 0/≥2 (no guessing). Shadow today (always abstains → flag-OFF byte-identical);
resolves the moment artifact #1 or #3 is present.

```
def resolve_flowerpot_drop_identity(
    *, bore_end_station_ft, print_tokens,
    run_endpoints=BRENHAM_PH5_RUN_ENDPOINTS,
    flower_pot_nodes,            # KMZ pots: {lat,lon, scid|None, address|None}
    drop_routes,                 # Vacant Pipe / House Drop routes (coords)
    drop_identity_key=None,      # the missing key: served address OR pot scid OR (parent_ap, drive_seq)
    endpoint_tol_ft=15.0,
) -> Optional[dict]:             # {flower_pot_latlon, drop_route_id, evidence} or None
    # STAGE 1 (PDF, available today): unique flower_pot run terminus at the end station
    #   across the print sheets. 0 or >=2 -> None ('pdf_terminus_nonunique').
    # STAGE 2 (KMZ identity, the gap): map that terminus -> ONE flower-pot node.
    #   Requires drop_identity_key:
    #     - scid:      pick the pot whose KMZ Scid == key            (unique)
    #     - address:   pick the pot/house whose Address == key       (unique; needs pot Address)
    #     - (ap,seq):  walk the parent AP's terminal tail to drive seq's vacant-HDPE pot
    #   If drop_identity_key is None OR resolves to !=1 pot -> None ('flowerpot_node_identity').
    # STAGE 3: the unique drop route is the Vacant Pipe whose endpoint == that pot (<=tol).
```

Properties: pure, never raises, order-independent, no new matching math beyond the shipped
haversine + run-endpoint table; attaches read-only under a future default-OFF
`TRUELINE_DROP_IDENTITY_SHADOW`; flag-OFF byte-identical. **DO-NOT-WIDEN: it abstains until a real
key is supplied.**

---

## 6. Next redline action
- **Acquire artifact #1 (smallest): a flower-pot SCID/address in the KMZ**, or #2 the `.FS`
  sheet. Then implement `resolve_flowerpot_drop_identity` as a default-OFF shadow and prove a
  unique pot per drop bore (as bore_log7 was proven) **before** any placement.
- Until then the 5 drops correctly **abstain** (interim safety state + this named target).
- The proven lane remains **bore_log7 → route_469** (Targets #14/#16/#18).

## 7. Files read
- KMZ (read-only, fixture md5-identical to design KMZ): point features + raw `<description>` tables
  for Flower Pot / House / Terminal Port HH / House Drop / Vacant Pipe / Terminal Tail.
- PDF `Brenham - Phase 5_07-15-25.pdf` sheets 8–14 (page idx 20–26): flower-pot callouts + addresses.
- Engine (no change): `BRENHAM_PH5_RUN_ENDPOINTS`, `_haversine_ft`, route catalog/ref builders.
