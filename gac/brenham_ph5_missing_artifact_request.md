# Brenham PH5 — Missing Source-Artifact Request (to unlock the remaining redlines)

**Prepared for:** Hector / GAC engineering + drafting
**About:** Brenham Phase 5 (the job we already loaded — design KMZ + 14 bore logs + the plan PDFs)
**Ask in one line:** send us **one more file (the Fiber-Schematic / drive sheet)** and, if easy, **two small extra columns/fields** — that's what's blocking the rest of the redlines.
**Effort:** the main file already exists in your design tool; pulling it should be minutes, not days.

---

## 1. Where we are (plain English)

TrueLine read your Brenham PH5 design and bore logs and **proved one bore exactly from your
own files** — bore_log7's redline lands on its real corridor (a terminal tail ending right at
handhole **AP-163**, within half a foot). No guessing; the files said so.

The **other 13 bore logs in that same group can't be drawn yet — not because TrueLine is
weak, but because one specific piece of information isn't in any file you sent us.** Your bore
logs record *how far* each bore went (stationing like `0+00 → 4+15`), but **never record
*which structure* the bore ends at** (which handhole, which flower pot, which splice). The
plan PDFs and the map each hold half the answer, but **nothing in the delivered files joins a
bore to its end structure.** We refuse to guess — a wrong redline is worse than none — so
those 13 are parked, waiting on the data below.

This is **not** "the tool needs tuning." It's a named, missing data field. Once it arrives,
those redlines place automatically.

---

## 2. Highest-priority request — the **`.FS` Fiber-Schematic / drive-decomposition sheet**

**What we need:** the **Fiber-Schematic (`.FS`) sheet set for Brenham PH5** — the per-area
schematic pages your own punch-list already points at (we can see references like **`AP-155
.FS 9`** and **`AP-168 .FS 11`** in the Fieldwire export you sent, but the actual `.FS` sheets
themselves were **not** in the 3 PDFs). Equivalently: whatever document your drafters use that
**breaks each bore run into its individual drives and says what each drive connects to.**

**Why it's #1:** it single-handedly unblocks the largest group (the 6 "multi-drive" bores) and
also resolves the flower-pot ambiguity for the drop bores — one file, two problems solved.

### What the `.FS` should contain (the join we're missing)

For each bore / drive, a mapping of **station sub-ranges → the specific structure at that end**:

| we have (bore log) | we need (`.FS` adds) |
|---|---|
| `bore_log29`, station `0+00 → 4+15` | "this run is drive 1 `0+00→1+90` to **AP-168**, then drive 2 `1+90→4+15` to **flower pot SCID FP-0142**" |
| a long continuous bore across 3 plan sheets | which **drive** each station segment is, and the **AP / flower pot / splice point / handhole / route section / terminal structure** at the end of each |

In other words: **bore → drive → station sub-range → named end structure (AP #, flower-pot ID,
splice ID, handhole ID, or route section).** That single chain is the whole blocker.

---

## 3. Secondary requests (any one helps; all three would close everything)

These are smaller and partially overlap with the `.FS`. Send whichever is easiest to export.

1. **Flower-pot identity key** — a **SCID / unit-id / served street address on each flower-pot
   node in the design KMZ.** Right now all 158 flower pots come through as *"Unnamed Feature"*
   with an empty SCID and no address (unlike your **houses**, which *do* carry an address, and
   your **handholes**, which carry the AP number). One identifier per flower pot is enough.
   *Example:* the KMZ flower-pot placemark gets a name or `<Data name="scid">FP-0142</Data>`,
   or a served address like `1205 E TOM GREEN ST`.

2. **Bore-log start/end-structure or direction column** — one extra column in the bore `.xlsx`
   naming the structure each bore **starts at and/or ends at**, or a **direction/bearing**.
   *Example header:* `end_structure` = `AP-163`, or `FP-0142`, or `SPLICE-46`; or
   `direction` = `toward AP-163`. Today the bore logs carry only
   `station / depth / boc / date / crew / print / notes` — no structure field.

3. **High-station anchor for the 4000–5950 ft range** — for the two "main-line" bores
   (bore_log16, bore_log43), a single **named structure that is both stationed and on the map**
   somewhere in the **`40+00`–`59+50`** range, plus its **direction**. Everything your plans
   carry tops out around station `45+33` / `40+00`s; these two bores run to `59+19`/`59+50`,
   past the end of what the sheets pin to a location. One stationed handhole/splice up there
   (e.g. "`AP-1xx` at `STA 55+00`") + which way the bore heads is all we need.

---

## 4. What each blocked group needs (so you can prioritize)

| blocked group | bore logs | what's missing | the one fact that unlocks it |
|---|---|---|---|
| **DROP / flower-pot** | 5, 30, 48, 50, 65 | flower-pot **identity** | which **specific flower pot** each drop bore ends at (SCID / address / parent-AP) — request **§3.1** or **§2** |
| **Main-line high-station** | 16, 43 | a **station↔map anchor + direction** | one named, stationed, on-map structure in **4000–5950 ft** + which way the bore runs — request **§3.3** |
| **Multi-drive (no single end)** | 57, 29, 31, 46, 47, 58 | the **`.FS` drive-decomposition** | which **drive + end structure** each station segment maps to — request **§2** |

(The one already solved: **bore_log7 → its terminal tail at AP-163**, proven from your files,
no extra data needed.)

---

## 5. What we are **NOT** asking for

- **No screenshots / pictures of the map.** We need the underlying data field, not an image.
- **No hand-drawn or "draw it where you think it goes" redlines.** A human guess is exactly
  what TrueLine is built to replace; a guessed redline that's wrong is worse than an honest
  blank. We want the **source fact**, then the tool draws it deterministically.
- **No estimates / "it's probably near AP-155" / vibes.** If the structure isn't recorded, say
  so — we'd rather leave it blank than place it wrong.
- **No re-survey or new field work.** This data already exists in your design/schematic tool;
  we just need it exported. If a field genuinely was never recorded, that's a useful answer too.

---

## 6. Concrete examples GAC/Hector will recognize

- **The `.FS` file:** the **Fiber-Schematic pages** your Fieldwire punch-list cites as
  "`.FS 9`", "`.FS 11`", etc. — the per-AP schematic that shows the drives fanning out from
  each handhole to the flower pots/drops. That's the document; we just don't have it.
- **Flower-pot SCID:** the structure ID your design tool already assigns each flower pot
  internally (it's blank on 157 of 158 in the export you sent) — exporting it populated is the
  fix.
- **Bore end structure:** if the crew knows "`bore_log48` ended at the flower pot serving
  `1206 LEDBETTER LN`," that sentence **is** the missing data — as a column or a note.
- **High-station anchor:** any handhole/splice your plans place at, say, `STA 55+00` on the
  E Tom Green main line, with its AP number — that pins bore_log16/43.

**If you can only send ONE thing: send the `.FS` Fiber-Schematic / drive sheet for Brenham
PH5.** It unblocks the most redlines for the least effort.

---

## 7. Provenance (for our records)

This request is the acquisition summary of TrueLine's read-only proof work on Brenham PH5:
`gac/drop_lane_flowerpot_identity.md` (flower-pot identity absent), `gac/mainchain_matchline_chainage_probe.md`
(high-station anchor absent), `gac/remaining_bucket_target23_review.md` + `gac/route480_remaining_proof_sweep.md`
(the 6 multi-drive logs, 0/6 provable). All 14 route_480-bucket bores are classified: **1
proven from existing files, 13 blocked on the artifacts above.** No engine change unblocks
them — only the source data does.
