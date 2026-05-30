# GAC Pilot — Data Request

**Prepared for:** GAC engineering / drafting
**Purpose:** Run one of your real OSP jobs through TrueLine and measure how accurately it redlines *your* bore data against *your* design.
**Effort:** A single engineer can pull all of this from one finished (or near-finished) job in an afternoon.

---

## 1. The goal

Give us **one real, recent OSP job** — the design files plus the field bore logs — so we can show TrueLine drawing the as-built redlines on **your** data and report **graded accuracy** against answers you already trust. This is a pilot to prove the tool on your work, not a demo on canned data.

---

## 2. File 1 — Design KMZ / KML

The map of the planned network. Export it straight from your design tool (Google Earth, AutoCAD/Civil 3D KMZ export, etc.).

**Must contain:**
- **Route LineStrings inside named folders.** Each corridor is a line, organized in the folder structure you already use. The folder/layer name is what tells us what each route *is*.
- **Backbone corridors identifiable as underground cable.** The bored main line we match against is read from routes whose source folder name contains **"underground cable."** House-drop / single-residence drop lines are deliberately ignored for route-matching, so it's fine if they're in there — just keep them in their own folder.

**Strongly recommended — unlocks the PDF-evidence route-correction feature:**
- **Numbered "Terminal Port Handhole" nodes.** Point placemarks in a folder whose name contains **"terminal port,"** where each placemark's **name is just the AP number** (e.g. `115`, `117`, `119` — numeric only, not "AP-115" and not "Handhole 115"). These let us tie a plan-sheet AP tag to a real lat/long and snap the bore to the correct corridor.

**What degrades without the handhole nodes:** route correction falls back to geometry + bore-log print-sheet matching only. It still works, but we lose the strongest signal for disambiguating two parallel/overlapping corridors.

---

## 3. File 2 — Bore logs (`.xlsx`)

The field crew's measured bore data. **One spreadsheet per bore run.** Name them simply and sequentially, e.g. `bore_log01.xlsx`, `bore_log02.xlsx`, … `bore_logNN.xlsx`.

**Required columns** (header row, lowercased + trimmed; the file is **rejected outright** if any of these three headers is missing):

| Column | Meaning |
|---|---|
| `station` | Survey stationing, e.g. `0+00`, `1+50`, `12+75`. The spine — any row whose station can't be read as stationing is silently dropped, so this must be real `+`-format stationing. |
| `depth` | Bore/product depth at that station. |
| `boc` | Bottom-of-conduit (or your equivalent) at that station. |

> `depth` and `boc` only need to **exist as columns** — blank/odd values are tolerated. `station` is the one whose *content* matters.

**High-value optional columns** (sharply improve route selection — include if your template has them):

| Column | Why it matters |
|---|---|
| `print` | The plan **sheet number(s)** this bore appears on (e.g. `5`, or `5, 6`). Biggest lever for picking the right route when corridors overlap; links the bore to the PDF plan sheet. |
| `notes` | Free text with **street / cross-street / context** (e.g. `LAWNDALE AVE`). Street names here are matched against the plans to confirm — or safely *reject* — a route guess. |
| `date` | Bore date. Splits distinct runs that share a file. |
| `crew` | Crew ID. Also splits distinct runs. |

Extra columns are harmless. If a file is missing one of the three required columns, only that file is rejected (the rest of the job still runs).

---

## 4. File 3 — Plan sheets (engineering PDF)

The detailed construction/design sheets for this job.

**Must be digital, text-based PDF** (exported from your CAD/plan tool — you can select/highlight the text in a viewer). We read three things from the **text layer**:
- **"Sheet N OF M" title blocks** — each sheet's own number and the total (e.g. `5 OF 42`).
- **`AP-####` tags** — the access-point labels printed on each sheet (e.g. `AP-115`).
- **Street labels** — street names printed on the sheets.

**Critical:** this must be **real PDF text, not a scan/photo.** There is **no OCR** — a scanned/image-only PDF yields zero text and can't drive route correction. If all you have is a scan, send it anyway; we'll use it as a **reference overlay**, but it can't be route truth.

> Quick self-check: open the PDF and try to select the text "AP-" with your cursor. If it highlights, it's good. If it doesn't, it's a scan.

---

## 5. File 4 — Ground truth (the critical ask)

The one piece we can't derive — and what turns the pilot from "looks plausible" into **graded accuracy on your data.**

**Pick 10–15 of the bore logs from File 2 and tell us the human-verified correct route each belongs to.** A plain table is perfect:

| Bore log file | Correct route / street it belongs on |
|---|---|
| `bore_log01.xlsx` | LAWNDALE AVE — backbone (underground cable) |
| `bore_log02.xlsx` | CHERI LN — terminal tail to AP-117 |
| … | … |

Your engineer's known-correct answer for each, in whatever wording matches the design (street name, route name, or the AP it ties to). If you can note *why* (e.g. "obvious — only corridor on that street" vs. "tricky — two parallel runs"), even better, but optional.

**Why this matters, plainly:** TrueLine produces a route choice for every bore log. To report *accuracy*, we compare its choice to a known-correct answer. Right now we have verified answers for only **2** bore logs — so any accuracy number we'd show is mostly inference. With **10–15 confirmed answers on your job**, we can give you a real graded scorecard ("X of 15 correct, here are the misses and why").

---

## 6. Optional — closeout / billing example

So our redline output matches what you hand the customer:
- **One past job's redline deliverable** (the marked-up KMZ/PDF/map you submitted at closeout), and
- **How you bill it** — e.g. footage tallied per route / per sheet. One example invoice or footage summary is plenty.

This lets us shape TrueLine's output to drop into your existing closeout/billing flow.

---

## How to send

- **One zip per job.** Keep everything for a single job together.
- **Keep the file types together** inside that zip: design KMZ/KML, the `bore_logNN.xlsx` files, the plan-sheet PDF, and the ground-truth table.
- **Label it with the town and phase** (e.g. `Brenham_PH5.zip`).

If any single piece is hard to pull (especially the terminal-port handhole layer or the ground-truth table), send what you have and flag the gap — we'd rather start with a partial real job than a complete fake one.
