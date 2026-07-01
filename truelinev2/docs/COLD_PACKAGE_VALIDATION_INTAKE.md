# Cold-Package Validation Intake — Contract + Owner Collection Checklist

> **Read-only. No placement. No promotion. No generalization claim.**
> This document describes how to assemble and run a **real / fresh, non-recognized** package through the
> read-only validation intake path `truelinev2/harness/package_validation.py`. Running an eligible package
> produces an **observer report only** — it does **not** place a redline, does **not** change any status, and
> does **not** unblock G4/AUTO. No real-world generalization is claimed until an eligible real/fresh package is
> actually run, and **even then** AUTO stays blocked (see §11).

Source of truth: `truelinev2/harness/package_validation.py` (verified against the implementation; the contract
is test-locked by `truelinev2/tests/test_package_validation.py`). Upload kinds come from
`truelinev2/harness/fixtures.py:UPLOAD_KINDS`. If the code and this doc ever disagree, the **code wins** — file
a fix to this doc.

---

## 1. What this path is for

The Track B observer stack (terminus source-binding, branch-uniqueness, station-x tightness, 2-D endpoint
tightness, leader-traced provenance) is currently proven **only against synthetic/adversarial harnesses**. The
named missing blocker is a **real / fresh cold package** to validate against. This intake path is the bridge:
drop a `package.json` + the real source files, run one command, get an honest read-only report that says whether
the package is **eligible** as cold proof and what the observers found.

It answers two questions and nothing else:

1. **Is this package eligible to serve as real cold proof?** (a genuinely non-recognized, complete, fresh project)
2. **What do the read-only observers see** at each bore's endpoints? (source-bound? unique branch? tight? drawn
   coordinate? — all advisory, all non-promoting)

---

## 2. Exact package folder structure

Place a real package in the **gitignored** drop-zone so real customer files are never committed:

```
data/outputs/truelinev2/cold_packages/<package-id>/
├── package.json                 # the manifest (schema in §3)
└── uploads/
    ├── plan.pdf                 # PLAN_PDF   — REQUIRED (the construction plan set)
    ├── bore-log.xlsx            # BORE_LOG   — REQUIRED (the bore-log workbook)
    ├── route.kmz                # GIS_ROUTE  — optional
    └── site-photo.jpg           # PHOTO      — optional
```

- `<package-id>` is your choice (generic, e.g. `cold-pkg-001`). It becomes the report `package_id` unless the
  manifest sets `package_id` explicitly.
- **All upload bytes live under `uploads/`.** The manifest references each file by `filename` (basename only);
  the loader looks for `uploads/<filename>`.
- `data/` is gitignored (`.gitignore:30`), so a real package — which contains **real customer PDFs/bore logs** —
  stays out of git. **Do not** commit a real package or its files. **Do not** put real names anywhere in code,
  routes, schema, or this doc — real names belong only in the package files themselves, which stay uncommitted.

---

## 3. Exact `package.json` schema

```json
{
  "package_id": "cold-pkg-001",
  "provenance_class": "FRESH_NONRECOGNIZED",
  "uploads": [
    { "kind": "PLAN_PDF", "filename": "plan.pdf" },
    { "kind": "BORE_LOG", "filename": "bore-log.xlsx" }
  ],
  "bores": [
    { "bore_label": "bore-1", "sheet": 1, "start_ft": 1175.0, "end_ft": 1325.0 }
  ]
}
```

| Field              | Type            | Required | Notes |
|--------------------|-----------------|----------|-------|
| `package_id`       | string          | optional | Defaults to the folder name if omitted. Identity only — keep it generic. |
| `provenance_class` | string          | **yes**  | One of the four values in §6. **Advisory** — source evidence overrides it. |
| `uploads`          | array of object | **yes**  | Each `{ "kind": <UPLOAD_KIND>, "filename": <basename under uploads/> }`. See §4. |
| `bores`            | array of object | **yes**  | Each bore `{ bore_label, sheet, start_ft, end_ft }`. See §5. |

The manifest is parsed read-only by `load_package_manifest`. Malformed JSON, or a missing `package.json`, yields
`PACKAGE_UNREADABLE` (§7).

---

## 4. Required uploads and accepted kinds

Accepted `kind` values (`fixtures.py:UPLOAD_KINDS`):

| kind        | Required? | What it is |
|-------------|-----------|------------|
| `PLAN_PDF`  | **REQUIRED** | The construction plan set (the PDF the redline is drawn onto). |
| `BORE_LOG`  | **REQUIRED** | The bore-log workbook (`.xlsx`) listing the bores and their stations. |
| `GIS_ROUTE` | optional  | A route `.kmz`/`.kml` for context. Not needed for eligibility. |
| `PHOTO`     | optional  | Site photo(s). Not needed for eligibility. |

- At least **one `PLAN_PDF`** and **one `BORE_LOG`** must be present **and** the referenced bytes must exist
  under `uploads/`. Otherwise → `INCOMPLETE_UPLOAD`, with the missing kinds named in `source_files_missing`.
- An upload with a `kind` not in the table above is **ignored** (it does not satisfy a required kind).

---

## 5. Required per-bore fields

Each entry in `bores`:

| Field        | Type   | Enforced by completeness gate? | Meaning |
|--------------|--------|--------------------------------|---------|
| `bore_label` | string | No (defaults to `""`)          | A generic label for the bore, e.g. `bore-1`. **Always provide it** — it names the candidate in the report; omitting it yields a blank label. |
| `sheet`      | int    | **Yes**                        | The plan sheet the bore is drawn on (1-based as the package counts sheets). |
| `start_ft`   | float  | **Yes**                        | Bore start station in feet. |
| `end_ft`     | float  | **Yes**                        | Bore end station in feet. |

The completeness gate requires **at least one** bore carrying `sheet` + `start_ft` + `end_ft`. A package whose
`bores` is empty, or where no bore has all three, → `INCOMPLETE_UPLOAD` (`"no bore with sheet+start_ft+end_ft"`).
`bore_label` is part of the contract but is read with a default, so it is not part of the completeness gate.

---

## 6. `provenance_class` — what it is and why it is advisory only

`provenance_class` is **what you declare** about the package. It is **advisory**: the validator trusts the
**source evidence** over your declaration. The single most important rule:

> A plan that is recognized — by a named dialect (`select_dialect(plan) is not None`) **or** present in the
> recognized-corpus registry — is the **work corpus** and is **ineligible as cold proof, no matter what
> `provenance_class` says**.

Likewise, a package located under a synthetic root is treated as `SYNTHETIC_TEST_ONLY` even if it declares
`FRESH_NONRECOGNIZED`. You cannot upgrade a package's standing by declaring a friendlier class — only the source
evidence + completeness decide.

**Allowed `provenance_class` values** (`package_validation.py:_DECLARED_CLASSES`):

| Value                 | Meaning | Outcome (if source evidence agrees) |
|-----------------------|---------|-------------------------------------|
| `FRESH_NONRECOGNIZED` | A new/fresh project that no named dialect recognizes. | `ELIGIBLE_FRESH_NONRECOGNIZED` (real validation) — **this is the one you want**. |
| `RECOGNIZED_WORK`     | The existing recognized work corpus. | `INELIGIBLE_RECOGNIZED_WORK_CORPUS`. |
| `ACTIVE_FIELD`        | A reserved active-field user's corpus. | `INELIGIBLE_ACTIVE_FIELD_CORPUS`. |
| `SYNTHETIC`           | A manufactured test package. | `SYNTHETIC_TEST_ONLY` (observer runs, but `real_validation=False`). |

Any other string → `UNKNOWN_PROVENANCE_CLASS`.

The report also carries a derived `corpus_class`, which is one of `FRESH_NONRECOGNIZED` / `RECOGNIZED_WORK` /
`ACTIVE_FIELD` / `SYNTHETIC` / **`UNKNOWN`** (the extra `UNKNOWN` is used for the not-found / unreadable /
incomplete / unknown-class outcomes).

---

## 7. What makes a package ineligible (or non-promoting)

There are two layers: an **eligibility verdict** (can this be cold proof at all?) and **AUTO blockers** (named
reasons AUTO stays blocked even for an eligible package).

### 7a. Eligibility verdicts and their exact precedence

The validator returns the **first** verdict that applies, in this order (source evidence overrides declared class):

1. `PACKAGE_NOT_FOUND` — the package directory does not exist.
2. `PACKAGE_UNREADABLE` — no `package.json`, or it is malformed; **also** emitted later if the plan PDF cannot be
   read or the observer stack cannot read the package.
3. `INCOMPLETE_UPLOAD` — a required upload (`PLAN_PDF`/`BORE_LOG`) is missing, **or** no bore has
   `sheet`+`start_ft`+`end_ft`. (Checked **before** recognition.)
4. `INELIGIBLE_RECOGNIZED_WORK_CORPUS` — the plan is recognized by a named dialect **or** is in the recognized
   registry. (Overrides any declared class. `recognized=True`.)
5. `INELIGIBLE_ACTIVE_FIELD_CORPUS` — declared `ACTIVE_FIELD`.
6. `SYNTHETIC_TEST_ONLY` — declared `SYNTHETIC`, **or** the package is under a synthetic root. The observer runs,
   but `real_validation=False` — **never counted as real generalization.**
7. `INELIGIBLE_RECOGNIZED_WORK_CORPUS` — declared `RECOGNIZED_WORK` (without dialect/registry recognition firing).
8. `UNKNOWN_PROVENANCE_CLASS` — declared class is not one of the four allowed values.
9. `ELIGIBLE_FRESH_NONRECOGNIZED` — declared `FRESH_NONRECOGNIZED`, complete, and the plan is genuinely
   non-recognized. The observer runs and `real_validation=True`. **This is the target outcome.**

### 7b. AUTO blockers (non-promoting; present even when ELIGIBLE)

`auto_blockers` is a sorted, de-duplicated list. Eligibility ≠ AUTO: an `ELIGIBLE_FRESH_NONRECOGNIZED` package
still carries blockers, and AUTO is gated on **all** of them being absent — which is **not currently possible**
(`CLASS_VERIFICATION_MISSING` is always present).

| Blocker | Emitted when |
|---------|--------------|
| `CLASS_VERIFICATION_MISSING` | **Always**, whenever the observer runs (`class_verified` is always `False` — the cold lane has no generic CAD layer/class table). This alone keeps AUTO blocked. |
| `REAL_FRESH_PACKAGE_VALIDATION_PENDING` | Whenever the result is **not** real validation (synthetic, ineligible, incomplete, not-found, unreadable). |
| `INSUFFICIENT_TERMINUS_EVIDENCE` | A bore endpoint is **not** source-bound (no printed terminus the binders can attach to). |
| `NO_DRAWN_COORDINATE_EVIDENCE` | An endpoint has `NO_DRAWN_COORDINATE`, **or** the branch observer found `NO_SPANNING_RUN`. |
| `AMBIGUOUS_EVIDENCE` | The branch is `FORKED` / `RIVAL_RUNS`, **or** an endpoint coordinate is `AMBIGUOUS_DRAWN_COORDINATE`. |
| `CROSS_SHEET_UNRESOLVED` | **Reserved** in the blocker vocabulary but **not currently emitted** by the implementation. Documented for completeness; do not expect it in a report today. |

So the mapping of your deliverable's "what makes a package ineligible" list onto the code is:
recognized/work corpus → §7a(4)/(7); active-field → §7a(5); synthetic test-only → §7a(6); incomplete upload →
§7a(3); unknown provenance → §7a(8); package not found / unreadable → §7a(1)/(2); insufficient terminus
evidence / no drawn coordinate / ambiguous evidence → §7b; cross-sheet unresolved → §7b (reserved, not emitted).

### 7c. Source-completeness and REVIEW-readiness validation

Eligibility (this document) answers *“may this package serve as cold proof?”* A second, complementary read-only
layer answers the **product** question: *“is this package ready for REVIEW-redline generation, and if not, exactly
why — and what is the single next step?”* That is the **source-completeness / REVIEW-readiness traffic
controller** in `truelinev2/harness/review_readiness.py` (spec:
[`SOURCE_COMPLETENESS_REVIEW_READINESS.md`](SOURCE_COMPLETENESS_REVIEW_READINESS.md)).

The product rule it enforces: **FieldRoute can draw from complete source packages; it must refuse incomplete
ones; a plan-only package is not enough when no source file confirms the bore/span start and end stations.** It
routes a package's read-only Track B stage evidence to one of nine statuses — `PACKAGE_RECOGNIZED_CONTROL`,
`PACKAGE_UNUSABLE_OCR_REQUIRED`, `KEEP_BLOCKED`, `MISSING_BORE_SPAN_SOURCE`, `NO_SOURCE_CONFIRMED_SPAN`,
`SPAN_SOURCE_FOUND`, `ANCHOR_BLOCKED`, `ROUTE_BLOCKED`, `READY_FOR_REVIEW_REDLINE` — and names the next productive
input. Like eligibility, it draws nothing, places nothing, and promotes nothing; readiness is not AUTO. The
canonical `PACKAGE_009_NEEDS_BORE_LOG` decision is expressed there as `MISSING_BORE_SPAN_SOURCE` — a package can
have route-attached anchors and still be refused because **no source file confirms the span.**

---

## 8. What Patrick needs to collect from a real project

To build the **first** real/fresh validation package, gather, from a **genuinely new project that the engine does
NOT already recognize** (not the existing work corpus, not a reserved active-field corpus):

1. **The construction plan PDF** (the full sheet set) → `uploads/plan.pdf` (`PLAN_PDF`).
   - It must have **printed terminus evidence** on the plan (station callouts / structure labels / matchline
     boundary stations) so the binders can source-bind endpoints. Without printed evidence the bores will report
     `INSUFFICIENT_TERMINUS_EVIDENCE`.
2. **The bore-log workbook** (`.xlsx`) for that project → `uploads/bore-log.xlsx` (`BORE_LOG`).
3. **For each bore you want validated**, the four fields: a generic `bore_label`, the `sheet` it is drawn on, and
   its `start_ft` / `end_ft` stations (read from the plan/bore log).
4. *(Optional)* the route `.kmz`/`.kml` (`GIS_ROUTE`) and any site `PHOTO`s — context only, not needed for
   eligibility.
5. **Confirmation it is genuinely fresh** — i.e. it is a new project, not a re-upload of the recognized work
   corpus and not a reserved active-field corpus. (The CLI catches named-dialect recognition automatically; see
   the caveat in §9.)

Then write the `package.json` (§3) declaring `provenance_class: "FRESH_NONRECOGNIZED"`.

---

## 9. How to run the read-only validation

From the **repo root**, with the **repo-root venv** (Python 3.11.9) and `PYTHONPATH` set to the repo root:

**PowerShell (primary shell):**
```powershell
cd C:\Nova\projects\TrueLine\TrueLine_Beta
$env:PYTHONPATH = "C:\Nova\projects\TrueLine\TrueLine_Beta"
.\venv\Scripts\python.exe -m truelinev2.harness.package_validation data\outputs\truelinev2\cold_packages\cold-pkg-001
```

**Bash (alternate):**
```bash
cd /c/Nova/projects/TrueLine/TrueLine_Beta
PYTHONPATH="C:/Nova/projects/TrueLine/TrueLine_Beta" \
  ./venv/Scripts/python.exe -m truelinev2.harness.package_validation \
  data/outputs/truelinev2/cold_packages/cold-pkg-001
```

It prints the JSON report (`eligibility`, `eligibility_reason`, `corpus_class`, `recognized`, `real_validation`,
`source_files_present` / `source_files_missing`, per-bore `candidates` diagnostics, `auto_blockers`,
`placement_performed: false`, and the explicit no-placement `note`). It writes nothing and changes nothing.

**Caveat (be honest about the CLI's recognition check):** the bare CLI calls `validate_package` **without**
injecting the recognized-corpus registry or any synthetic roots. So the CLI detects recognition via
**named-dialect** matching only (`select_dialect`); it does **not** cross-check the plan's sha256 against the
registry, and it does **not** classify by synthetic location. For a genuinely fresh project this is exactly
correct (no dialect recognizes it). The registry-sha and synthetic-root overrides exist for programmatic callers
/ tests (see `validate_package(..., recognized_registry=..., synthetic_roots=...)`), and are what the test suite
uses to prove the override precedence. **You** are responsible for ensuring the package is genuinely fresh, not a
re-upload of the work corpus.

---

## 10. Name-free dummy manifest + plain-English checklist

### 10a. Copy-paste dummy `package.json` (generic placeholders only)

```json
{
  "package_id": "cold-pkg-001",
  "provenance_class": "FRESH_NONRECOGNIZED",
  "uploads": [
    { "kind": "PLAN_PDF",  "filename": "plan.pdf" },
    { "kind": "BORE_LOG",  "filename": "bore-log.xlsx" },
    { "kind": "GIS_ROUTE", "filename": "route.kmz" }
  ],
  "bores": [
    { "bore_label": "bore-1", "sheet": 1, "start_ft": 1175.0, "end_ft": 1325.0 },
    { "bore_label": "bore-2", "sheet": 2, "start_ft": 430.0,  "end_ft": 612.0 }
  ]
}
```

Replace the placeholder filenames, sheet numbers, and stations with the real project's values. Put the real
files under `uploads/`. Keep `package_id` / `bore_label` generic — **no customer/person/place names in the
manifest**.

### 10b. Plain-English checklist (do this before handing me a package)

- [ ] It is a **new/fresh project** the engine does not already recognize (not the work corpus, not a reserved
      active-field corpus).
- [ ] Created the folder `data/outputs/truelinev2/cold_packages/<package-id>/` (under gitignored `data/`).
- [ ] Created `uploads/` inside it.
- [ ] Dropped the **plan PDF** into `uploads/` (the plan has **printed station/structure/matchline evidence**).
- [ ] Dropped the **bore-log `.xlsx`** into `uploads/`.
- [ ] *(Optional)* dropped a route `.kmz`/`.kml` and/or photos into `uploads/`.
- [ ] Wrote `package.json` from the §10a template, with `provenance_class: "FRESH_NONRECOGNIZED"`.
- [ ] Listed **every bore** in `bores` with `bore_label` + `sheet` + `start_ft` + `end_ft`.
- [ ] Confirmed each `filename` in the manifest exactly matches a file in `uploads/`.
- [ ] Used **no real names** in `package.json` (only in the uploaded files, which stay uncommitted).
- [ ] Ran the §9 command and read the JSON report.

If the report says `ELIGIBLE_FRESH_NONRECOGNIZED` with `real_validation: true`, the package is the first real
cold-proof candidate — hand it over (or share the report) and we read the observer diagnostics together. Any
other eligibility verdict tells you (in `eligibility_reason` + `source_files_missing`) exactly what to fix.

---

## 11. Explicit limits — no placement, no promotion, no generalization

- **No placement.** `placement_performed` is always `False`. This path never draws or moves a redline.
- **No promotion.** It never changes a job/status, never writes to the store, never edits `_cap_review`, never
  touches the renderer.
- **No generalization claim.** `real_validation` is `True` **only** for an eligible fresh non-recognized package,
  and even then it means "the observer ran on a real package" — **not** that AUTO is safe. `class_verified` is
  always `False` and `CLASS_VERIFICATION_MISSING` is always a blocker, so **G4/AUTO remains blocked** regardless
  of this report. AUTO is unblocked only later, by a separately authorized gate (generic class verification +
  owner approval) — **not** by running this intake path.
- Until an eligible real/fresh package is actually run here, the entire Track B observer stack remains
  **synthetic-proven only**, and no real-world generalization is claimed.
