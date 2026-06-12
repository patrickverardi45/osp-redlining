# v2 → Web Wiring-Readiness Audit

**Status:** AUDIT / DESIGN ONLY. No code wired. No engine, web, or mobile behavior changed.
**Date:** 2026-06-11 · v2 HEAD `23ad22c` (M8.19 pushed) · web HEAD `8dd88dc` (contract parity check)
**Scope:** can the v2 reviewer-card / proof outputs be wired into the `trueline-web-experience` command-center UI, and what is the smallest safe boundary.

Repos:
- v2 engine — `C:\Nova\projects\TrueLine\TrueLine_Beta` (branch `feat/truelinev2`)
- web app — `C:\Nova\projects\trueline-web-experience` (Next.js 16 / React 19 / TS, mock-data-only)
- mobile — `C:\Nova\projects\trueline-field-mobile` (read-only; contract-parity mirror of web)

---

## 1. Current v2 readiness summary

v2 already emits three **validated, JSON-serializable** reviewer contracts (pydantic = the contract) plus a static demo. All are **proof-runner-only**: no FastAPI route, no DB, no env reads, no engine wiring; everything is `model_dump(mode="json")`-clean.

| Contract | Schema string | File | Shape | Status |
|---|---|---|---|---|
| **Reviewer payload** (per bore) | `truelinev2-reviewer-lanes-1` | [reviewer_payloads.py](../truelinev2/review/reviewer_payloads.py) | one `ReviewerPayload` per bore in exactly one of 6 lanes | **ready as data** |
| **Reviewer bundle** (per project) | `truelinev2-reviewer-bundle-1` | [reviewer_service.py](../truelinev2/review/reviewer_service.py) | `ReviewerBundleService.generate(mode)` → all 58 payloads + counts + flag state + corpus source | **ready as data** |
| **Design-stroke cards** | `truelinev2-design-stroke-card-1` | [design_stroke_cards.py](../truelinev2/review/design_stroke_cards.py) | 9 cards (4 stroke-review + 5 pick) with verbatim geometry / evidence chain / grade provenance / artifact refs | **ready as data** |
| **Static demo sidecar** | `truelinev2-reviewer-demo-1` | [run_reviewer_demo_artifact.py](../truelinev2/proof/run_reviewer_demo_artifact.py) | `{bundles, visuals, sheet_renders, design_cards}` + a self-contained `file://` viewer | **reference UI** |

**What the engine actually places today (the truth surface):**
- `default_baseline` mode: **24 placed** (AUTO 14 / REVIEW 10), 32 abstain, 2 error.
- `fullest_safe_review` mode: **30 placed** (the two zero-false opt-ins M8.5+M8.8). REVIEW-only; **not activated** on any deployment.
- Design-stroke cards: **4 graded-PASS strokes** (log25/51/59/65) + 5 end-anchored pick suggestions.
- All-58 census (banked, G2-pinned): 4 stroke-eligible / 5 pick-card / 1 design-not-traceable / 3 structure-identity-required / 13 cross-sheet / 5 end-position / 25 end-unprinted / 2 source-error.

**Honesty invariants already enforced by the models (must survive any wiring):**
- suggestions carry the frozen literal `SUGGESTION_NOT_PLACEMENT` ([reviewer_payloads.py:33,83-89](../truelinev2/review/reviewer_payloads.py)); a suggestion can never carry stroke geometry ([design_stroke_cards.py:128-141](../truelinev2/review/design_stroke_cards.py)).
- **no numeric confidence anywhere** — confidence is a closed CLASS enum (`AUTO_EXACT_MATCH` / `REVIEW_CAVEATED` / `REVIEW_OPTIN_SOLVER`), and only the placed lane may carry it ([reviewer_payloads.py:45-50,151-152](../truelinev2/review/reviewer_payloads.py)).
- every drawn stroke is RED by the canonical test-locked `REDLINE_STROKE_RGB` (memory `trueline-red-stroke-law`).
- design-stroke geometry is VERBATIM from the lane and `PASS_ACCEPTED` only when the banked grade record backs it ([design_stroke_cards.py:170-174](../truelinev2/review/design_stroke_cards.py)).
- the bundle validator recomputes all counts and pins flag-state to a closed mode table — a bundle can't claim a mode it wasn't built under ([reviewer_service.py:145-181](../truelinev2/review/reviewer_service.py)).

**Artifacts (images):** generated only by proof runners, **gitignored**, referenced by NAME (never embedded).
- evidence crops `data/outputs/reviewer_demo/visuals/crops/*.png`, full-sheet context `…/visuals/sheets/sheet_<n>.png`, design strokes `…/visuals/strokes/<bore>_lane_s<sheet>_redline_stroke.png`.
- canonical stroke name = `{bore_id}_lane_s{sheet}_redline_stroke.png` ([design_stroke_cards.py:58-61](../truelinev2/review/design_stroke_cards.py)).
- **lazy by design:** the M8.13 viewer sets evidence-crop `<img loading="lazy">`; the M8.15 design-stroke tab assigns each stroke image `src` only on `<details>` open (true on-demand) — the card LIST renders first, the artifact loads on click.

---

## 2. Current web readiness summary

(Full recon citations live in the web repo; key facts below.)

- **Single integration seam.** `TrueLineApi` interface ([`src/lib/api/types.ts:26-82`]) bound by one line `export const api: TrueLineApi = mockApi` ([`src/lib/api/index.ts:8`]). Swapping the engine in = changing that one assignment. **Read-only; zero mutation methods.** No `fetch`, no `/api` routes, no auth, no engine imports.
- **Contract source of truth** = `src/contracts/index.ts` (plain TS interfaces, **no zod, no runtime schema, no `schemaVersion` field**). Contract parity = a byte-for-byte `Buffer.equals` of web vs mobile `src/contracts/index.ts` (`scripts/check-contract-parity.mjs`). Parity checks **only** web↔mobile file identity — nothing about the engine.
- **Review model is run-scoped and thin.** The web-local `ReviewItem` (`src/app/redlines/review-types.ts:14-34`) is assembled per **Run** from `Run + FieldTicket + PlanSheet + Crew + RedlinePath`. Statuses = `ReviewStatus` (`draft → submitted → in-review → changes-requested → approved`). Decision actions are **approve / request-changes only**, local React state, **no persistence**.
- **No engine vocabulary exists.** Grep-clean on `confidence`, `reason`, `pick-card`, `source-review`, `blocker`, `abstain`, `suggestion`, `lane`. The only pre-wired nod is the unused `SourceRef.type = 'engine-import'`.
- **No image pipeline at all.** Plan sheets + Hero Map are **hand-drawn SVG** (`viewBox 0 0 1000 700`). No `next/image`, no `<img>`, `public/` empty. `FieldPhoto.thumbUrl?` is declared but read by nothing; photos render as `PhotoPlaceholder`. The only progressive pattern is **SVG reveal sliders** (geometry-driven, not raster).
- **Coordinate spaces:** `RedlinePath.points: [number,number][]` in "surface coord space"; `SheetPin.{x,y}` in sheet space `0–1000 × 0–700`. Renderer-agnostic by design.

---

## 3. The core mismatch (why this is "design," not "just transport")

| Axis | v2 engine | web app | Gap |
|---|---|---|---|
| **Granularity** | per **bore log** (one card/bore) | per **Run** (a segment with from/to stations) | bore ≈ run-ish, not 1:1; need a bore→run identity map |
| **Review vocabulary** | 6 reviewer lanes + 6 human actions + design-stroke cards | 5 `ReviewStatus` + approve/request-changes | no web home for pick-card / source-review / out-of-class / unsafe-abstain / adjustable-redline |
| **Confidence** | closed CLASS enum (no numbers) | **not modeled** | add as closed enum (never a %), placed-lane only |
| **Reason / why** | `reason_code` + `named_missing_relationship` + `caveats` | free-text `ticketNotes` only | add structured reason fields |
| **Geometry** | per-sheet **PDF display-space** `stroke_points` | `RedlinePath.points` surface space + `SheetPin` `0–1000×0–700` | needs a PDF→sheet coordinate transform |
| **Images** | PNG crops / stroke renders (file paths, lazy) | **none** (SVG only) | need a URL contract + a lazy image component |
| **Schema id** | `truelinev2-*` version strings on every object | no `schemaVersion` field; parity = web↔mobile byte-identity | engine card type can't enter the parity-checked contract without mobile mirroring it |
| **Mutation** | none (M8.11 is a generation seam; no route) | none (read-only mock) | review write-back is unbuilt on BOTH sides |

---

## 4. Field-mapping table (v2 → web)

Direction: **v2 `ReviewerPayload` → web review surface**. "Web target" is the existing field if one fits, else `NEW` (proposed adapter/contract field).

| v2 field (`ReviewerPayload`) | Type | Web target | Adaptation |
|---|---|---|---|
| `bore_id` | str | `ReviewItem.runId` (via map) | needs bore→run id map; until then carry as `engineBoreId` (NEW) |
| `lane` | enum(6) | **NEW** `EngineLane` enum | direct copy; closed union |
| `human_action` | enum(6) | **NEW** `EngineAction` enum, OR derive web buttons | map to web action set; pick-card/source-review have no buttons yet |
| `reason_code` | str | **NEW** `reasonCode` | direct |
| `confidence_class` | enum(3)/None | **NEW** `confidenceClass` (closed enum) | **never** render as a number |
| `sheets` | int[] | `ReviewItem.sheetCode` (one) / **NEW** `sheets[]` | web shows one sheet code; engine may span several |
| `station_start_sta` / `_end_sta` | str | `fromStationCode` / `toStationCode` | direct (string codes) |
| `station_start_ft` / `_end_ft` / `footage_ft` | float | `lengthFt` / **NEW** `footageFt` | direct |
| `evidence_summary` | str/None | **NEW** `evidenceSummary` | direct text; not a placement claim |
| `caveats` | str[] | **NEW** `caveats[]` | direct |
| `candidates[]` (`RouteCandidate`) | list | **NEW** `candidates[]` | each carries frozen `SUGGESTION_NOT_PLACEMENT` — must round-trip the label |
| `redline_spec` (`AdjustableRedlineSpec`) | obj/None | **NEW** `adjustableRedline?` | drag/snap/confirm spec; no geometry yet |
| `named_missing_relationship` | str/None | **NEW** `namedMissing` | the honest "what's missing" |
| `suspect_values` | dict/None | **NEW** `suspectValues` | source-review lane only |
| `next_named_solver` | str/None | **NEW** `nextSolver` | out-of-class lane only |
| `schema_version` | str | dropped at adapter / kept as `engineSchema` | web contract has no version field today |

**Design-stroke card (`DesignStrokeCard`) → web (later slice):** `bore_id`→run, `kind`(STROKE/PICK)→card kind, `lane_status`, `design_grade`(`PASS_ACCEPTED`/`UNGRADED`), `segments[].{sheet,start_ft,end_ft,stroke_points}`→ **needs PDF→sheet transform** before it can become `RedlinePath.points`, `artifact_refs`→ image URLs (image slice), `evidence_chain[]`, `suggestion_label`/`pick_candidate`/`end_anchor_xy`/`named_missing` for picks.

**Lane → web status/action suggestion** (closed mapping, adapter-owned):

| v2 lane | confidence | web status (display) | web action |
|---|---|---|---|
| `PLACED_REVIEW` | class | `in-review` | approve / request-changes (exists) |
| `PICK_CARD_ROUTE_SUGGESTION` | — | `needs-review` (NEW "pick") | pick-one / reject-all / draw (NEW) |
| `HUMAN_ADJUSTABLE_LENGTH_REDLINE` | — | `needs-review` (NEW "adjust") | drag/snap/confirm (NEW) |
| `SOURCE_REVIEW_REQUIRED` | — | `missing-evidence` (NEW "source") | fix-source (NEW) |
| `OUT_OF_CLASS` | — | `blocked` | route-to-solver (NEW) |
| `UNSAFE_ABSTAIN` | — | `blocked` | none / blocked (NEW) |

---

## 5. Missing fields / blockers

**Hard blockers (cannot wire until resolved):**
1. **No engine card type in the web contract.** Adding lane/confidence/reason to `src/contracts/index.ts` **breaks web↔mobile byte-parity** unless mobile mirrors it. → First slice keeps the engine card **web-local** (outside the parity-checked file), or the owner decides to extend the shared contract + mirror to mobile.
2. **No image pipeline in web.** Exposing engine crops/strokes needs (a) a URL contract (static `public/` export vs an image route) and (b) a new lazy-loading component — none exists.
3. **Coordinate-space transform unbuilt.** Engine `stroke_points` are per-sheet PDF display coords; web sheet space is `0–1000×0–700`. No transform exists either side. Until built, **send no geometry**.
4. **bore↔run identity map is undefined.** v2 is bore-scoped, web is run-scoped; nothing maps `bore_log7` ↔ a web `Run.id`. The demo corpus (Brenham) has no web project today.
5. **No v2 API route.** M8.13.b (`/v2/reviewer/bundle`) was never built (needs an auth + httpx test-dep decision). So "live" wiring isn't possible yet — only a static export.
6. **No mutation/write-back on either side.** Review decisions are mock-only in web and absent in v2 — approve/reject can't persist anywhere. First slices are **read-only display**.

**Soft gaps (adapter can paper over):**
- web `ReviewItem` is run-scoped; the engine card is bore-scoped → adapter emits a parallel `engineCards[]` keyed by `engineBoreId`, not forced onto `ReviewItem`.
- web has no `confidenceClass`/`reasonCode`/`namedMissing` → adapter-added NEW fields, closed enums only.

---

## 6. Lazy artifact-loading requirements (carry these into web)

The M8.13/M8.15 demo already proves the right pattern; web must replicate it, not the v1 "load all PDFs" behavior:
- **Card list first.** Render card metadata (lane, status, reason, stations, footage) with **zero** image loads.
- **Artifact on request only.** A stroke image / evidence crop loads **only** when the reviewer opens that card (the M8.15 `<details>`-toggle pattern: assign `img.src` on first open). No eager fan-out.
- **Full sheet on request only.** The full-sheet context render loads on explicit "show sheet," never with the queue.
- **No preload-all.** The web `plans/page.tsx` already fans `Promise.all` over all sheets for SVG furniture (cheap today) — do **not** extend that pattern to raster engine artifacts.
- **Paths, not blobs.** Engine references artifacts by name; the adapter resolves them to URLs lazily; binaries never ride inside the JSON bundle.

---

## 7. Safest adapter boundary (recommended)

**Boundary = a versioned static JSON export, mapped web-side, behind the existing `api` seam. No engine import in web, no live route, no auth, no images in slice 1.**

```
v2 proof runner  ──emit──>  reviewer_bundle.v1.json   (M8.11 ReviewerBundle.model_dump)
   (default_baseline)                │  (+ optional design_stroke_cards.v1.json)
                                     │  static file, checked into web /public or /fixtures
                                     ▼
web  src/lib/api/adapters/v2Bundle.ts   (TS: bundle JSON → engineCards[] + ReviewItem overlay)
                                     │
                                     ▼
web  api.reviews.engineCards()   (NEW namespace on TrueLineApi; mock-by-default, feature-flagged)
                                     │
                                     ▼
web  /redlines  review queue + card detail   (renders lane/status/reason; NO geometry, NO images)
```

- **Direction of ownership:** the **engine emits its canonical bundle unchanged**; the **web owns the adapter** (the mapping/renaming). This keeps the v2 contract pure (engine = truth layer) and lets web absorb naming per its own contract doctrine.
- **Recommended API shape (web):** add ONE read-only namespace to `TrueLineApi`:
  - `reviews.queue(projectId): Promise<EngineCardSummary[]>` — list (lane, status, reason, stations, footage, confidenceClass) — **no geometry, no images**.
  - `reviews.card(boreId): Promise<EngineCard>` — full payload incl. candidates / redline_spec / named_missing.
  - `reviews.artifact(boreId, ref): Promise<string>` — resolves an artifact NAME → URL **on request** (slice 2+).
- **Card payload shape (web `EngineCard`):** the §4 NEW fields, all closed enums, `SUGGESTION_NOT_PLACEMENT` preserved verbatim, **no numeric confidence**, geometry optional and absent until slice 2.
- **Artifact/crop URL strategy:** slice 1 = none. Slice 2 = export the needed PNGs to web `public/engine/<project>/…` (or an image route), referenced by the engine's canonical name; `reviews.artifact()` returns the URL lazily.
- **Review action model:** display-only in slice 1 (`approve` / `needs-review` / `pick-card` / `source-review` / `blocker`), mapped per the §4 table; **no write-back** (matches both sides today).

---

## 8. Wiring-readiness gates (a card may surface only if ALL hold)

1. its bundle **passed M8.11 validation** (counts recomputed, flag-state pinned, every bore in exactly one lane).
2. **no fake placements:** only `PLACED_REVIEW` (or a graded-PASS design-stroke card) may render as placed; everything else renders as suggestion/abstain.
3. **suggestions cannot masquerade as placed:** every candidate carries `SUGGESTION_NOT_PLACEMENT`; pick/abstain cards carry **no** stroke geometry (validator-enforced).
4. **redline stroke always red** (`REDLINE_STROKE_RGB`) — any future drawn overlay uses the canonical constant.
5. **confidence is a closed class, never a number.**
6. **artifact refs resolve** to a real file before the URL is exposed (the demo's G4 gate).
7. **every card has an honest lane/status + reason** (`reason_code` / `named_missing_relationship` present).
8. **full sheet + artifacts load only on request** (§6).
9. (geometry slices) **stroke geometry is verbatim + grade-backed**; coordinate transform is loss-checked before a stroke is drawn.

---

## 9. What is explicitly NOT ready

- **The cross-sheet strokes for log8/log32/log42** — M8.19 proved the path-length join is valid but they are **not placed** (cross-bore collision unresolved). Do not surface as placements.
- **Any activation beyond the 4 graded-PASS strokes + the 24 default placements** — the 30-placed `fullest_safe_review` set is REVIEW-only and **not owner-activated**.
- **Live API wiring** — no v2 route exists (M8.13.b unbuilt; needs auth + httpx decision).
- **Images in web** — no pipeline; `thumbUrl` unread; `public/` empty.
- **Geometry overlays** — no PDF→sheet transform exists.
- **Review write-back / mutation** — neither side persists decisions.
- **Mobile** — out of scope except that any shared-contract change must mirror to keep parity green.
- **bore↔run mapping for a real project** — the only corpus is Brenham demo data, which has no web `Project`.

---

## 10. Next 3 implementation slices

### Slice 1 — Static bundle export + web adapter (read-only, no images, no geometry)
**Smallest safe wire.** v2 proof runner emits `reviewer_bundle.v1.json` (M8.11 `default_baseline` dump). Web adds `src/lib/api/adapters/v2Bundle.ts` mapping it to a **web-local** `EngineCard[]` (kept OUT of the parity-checked `src/contracts/index.ts` to preserve web↔mobile byte-parity), exposed behind a NEW `api.reviews.*` namespace, **feature-flagged, mock-by-default**. Renders lane/status/reason/stations in the `/redlines` queue. No geometry, no images, no write-back.
**Gates:** §8 1-3, 5, 7; parity check stays green (contract file untouched).
**Model:** **Codex** (mechanical TS adapter + type mapping + a JSON fixture; well-specified, low ambiguity). Opus only if the bore→run mapping needs design.

### Slice 2 — Design-stroke card surfacing (geometry + lazy artifact)
Expose the **4 graded-PASS** design-stroke cards (log25/51/59/65) with their stroke geometry and lazy stroke image. Requires: the **PDF→sheet coordinate transform** (loss-checked), an **image URL contract** (export PNGs to web `public/engine/…`), and a **lazy image component** copying the M8.15 `<details>`-on-open pattern. Strokes render RED via the web's SVG layer (renderer-agnostic `RedlinePath.points`).
**Gates:** §8 all, incl. 4 (red), 6 (refs resolve), 9 (verbatim geometry + transform loss-check).
**Model:** **Opus** (coordinate transform correctness + a brand-new image pipeline + honesty review; design-sensitive, must stay zero-false).

### Slice 3 — Local v2 API route replacing the static export (M8.13.b)
Build the local `/v2/reviewer/bundle` FastAPI route on the existing v2 scaffold (the deferred M8.13.b: needs the **auth boundary** + **httpx test-dep** decision), then point the web adapter at it instead of the static JSON (still read-only). Optionally add an artifact image route.
**Gates:** §8 all + auth/tenant isolation (do not regress the monolith's open auth findings) + no engine truth-path dependency on the route.
**Model:** **Opus** (auth boundary + route + test-dep decision; the owner-deferred call). **Fable not required** — no geometry-law wall; escalate only if the auth design needs deep multi-file reasoning.

**Model summary:** Slice 1 → **Codex/Opus**, Slice 2 → **Opus**, Slice 3 → **Opus**. **Fable is not warranted** for any slice — none hits an engine-geometry-law wall; the hard parts are TS mapping (Codex), a coordinate transform + image pipeline (Opus), and an auth/route decision (Opus + owner).

---

## 11. Top blockers before any wiring (ranked)

1. **Owner decision: shared contract vs web-local engine card.** Extending `src/contracts/index.ts` breaks web↔mobile parity unless mobile mirrors. Recommend **web-local for slice 1**, revisit for slice 2+.
2. **No image pipeline in web** — blocks every artifact/crop/stroke render until slice 2 builds it.
3. **No PDF→sheet coordinate transform** — blocks all geometry overlays.
4. **bore↔run identity map** for a real project — Brenham demo has no web `Project`; needs either a demo project seeded in web or a mapping decision.
5. **No v2 API route + no mutation** — keeps everything read-only/static until slice 3.

---

## 12. Slice 1 shipped + Slice 2 split (2026-06-12)

### Slice 1 — shipped (read-only reviewer cards)
- v2 `truelinev2/proof/export_reviewer_bundle_json.py` (pushed `b107e28`) emits `reviewer_bundle.v1.json` (M8.11 `default_baseline` dump under a versioned envelope `truelinev2-web-reviewer-bundle-export-1` recording the source Git SHA). Its validator **forbids geometry/artifact keys** (`segments`/`stroke_points`/`artifact_refs`) and pins confidence to the closed class — so the reviewer bundle carries **no images and no geometry by construction**.
- web branch `codex/v2-reviewer-bundle-adapter` (`8aabf73`): `src/lib/api/adapters/v2Bundle.ts` maps it to a **web-local** `EngineCard[]` (lane/status/reason/confidence-class/stations/candidates) — kept OUT of the parity-checked `src/contracts/index.ts`; the adapter ALSO runs `assertNoGeometry`. `/redlines` shows it read-only behind `api.reviews.engineBundle()`. Every card is `runMapping: 'unmapped'`, `runId: null`. Parity stayed green.

**Consequence for Slice 2:** design-stroke ARTIFACTS live in a different contract (`truelinev2-design-stroke-card-1`) that the Slice 1 export deliberately excludes. Slice 2 needs its own path.

### Slice 2 split into 2a (availability, shipped) + 2b (served geometry, blocked)
The original "Slice 2 — geometry + lazy artifact" was too big and the artifacts can't be safely served (the 4 graded-PASS stroke PNGs are gitignored ~0.2–1.1 MB regenerables under the engine's `data/outputs/symbol_conduit_lane_sweep/`; auto-copying large files is forbidden). It splits:

**Slice 2a — design-stroke artifact AVAILABILITY (shipped, web-local placeholder).** web commit `e0ab766`:
- `src/lib/api/fixtures/design_stroke_artifacts.v1.json` — the 4 graded-PASS cards' artifact-ref **filenames only** (`log25_lane_s21_…`, `log51_lane_s8_…`, `log59_lane_s21_…`, `log65_lane_s10/s9_…`), `served:false`, NO geometry/binaries/paths. Hand-derived from the banked M8.15 packet (provenance recorded in the fixture).
- `src/lib/api/adapters/v2Artifacts.ts` — strict web-local adapter: refs must be **bare engine filenames** (`^[a-z0-9_]+_redline_stroke\.png$`, never a path/URL), grade a closed class, `served` must be false, geometry keys rejected.
- `api.reviews.engineDesignStrokeArtifacts()` (read-only) + `EngineArtifactPanel` — a `<details>`-gated availability list; **never an `<img>`**, zero network requests, each ref tagged "not served."
- Checks: `contracts:check` PASS, `tsc --noEmit` clean, `eslint` clean, `next build` prerenders `/redlines`.

**Slice 2b — SERVED stroke images + geometry overlay (NOT started; blocked).** Still needs the PDF→sheet coordinate transform, an artifact serving strategy (decision below), and a lazy image component — see §5/§13.

### bore→run mapping recommendation
1. **Keep `sourceBoreId` primary + `runMapping: 'unmapped'`** (already true). The web `Run.boreLogRef.refId` (e.g. `bl-a12`) IS the natural join key, but the web demo project is fictional "Cedar Ridge" while the engine cards are Brenham (`brenham-ph5`) — **there is genuinely no overlap**, so `unmapped` is the honest state. Do not invent run ids.
2. **Path to mapping = a temporary Brenham project container, web-local.** Seed a web `Project` (`p-brenham-ph5`) whose `Run`s carry `boreLogRef.refId == <v2 bore_id>` (`log7`, `log25`, …). Then the join is `boreLogRef.refId === sourceBoreId`, computed in the adapter, with `runMapping: 'mapped'`/`'unmapped'` per-card. This is fixture-only and changes no shared contract.
3. **Do NOT** author a bare `bore→run` map fixture against the fictional Cedar Ridge runs — it would fabricate placements onto unrelated runs. The project-container route keeps provenance honest.
4. Keep the explicit `unmapped` status whenever a bore has no `boreLogRef` match (already enforced).

### artifact / lazy-loading recommendation
- **Availability first, pixels later (done in 2a):** show the engine's canonical filenames + grade with zero fetches; the card list renders before any artifact work.
- **Never auto-copy the PNGs.** They are gitignored regenerables; a build that copies them bloats the web repo and drifts from engine truth.
- **For 2b, decide a serving strategy (owner):** (a) a v2 export runner that writes a manifest **and** copies just the graded PNGs into a gitignored `web/public/engine/<sha>/…` on demand (explicit, not automatic); or (b) a local v2 image route (Slice 3 territory; needs auth). Either way the web component sets `img.src` only on `<details>` open (the M8.15 pattern) — **one image per opened card, never a preload**.
- **Generate the manifest from the engine** (a tiny v2 export, like Slice 1's) so 2a's hand-derived fixture stops being hand-maintained.

---

## 13. Remaining blockers before REAL (served) Slice 2b

1. **No artifact serving path decided** — the PNGs can't be auto-copied; owner must pick manifest-export+on-demand-copy vs an image route.
2. **No PDF→sheet coordinate transform** — required before any stroke geometry can become `RedlinePath.points`; deferred out of 2a.
3. **Manifest is hand-derived** — 2a's fixture should be replaced by an engine-generated export before it's trusted as truth.
4. **bore→run still unmapped** — needs the temporary Brenham project container (above) before a card can attach to a web run.
5. **No lazy image component yet** — 2a renders placeholders only; the on-open `img.src` loader is unbuilt.

### Next recommended prompts
- **Slice 2a-follow (Codex):** add a v2 export runner `export_design_stroke_artifacts_json.py` (refs-only manifest, geometry-forbidden validator like the Slice 1 exporter) so the web fixture is engine-generated + SHA-pinned; regenerate `design_stroke_artifacts.v1.json` from it. Small, two-repo, no UI change.
- **bore→run mapping (Codex/Opus):** seed a web-local `p-brenham-ph5` project container + runs keyed by `boreLogRef.refId == sourceBoreId`; adapter computes `runMapping`. Fixture-only; no shared contract.
- **Slice 2b (Opus):** owner picks the serving strategy; then build the lazy on-open image loader + the PDF→sheet transform (loss-checked) to render the 4 graded strokes RED on the SVG layer. Design-sensitive, zero-false.

---

*Slice 1 + Slice 2a code lives in the named commits; this doc is planning only. Sources inspected this round (Slice 2a): v2 `proof/export_reviewer_bundle_json.py`, `review/design_stroke_cards.py`, the banked `design_stroke_cards_proof.json`; web `src/lib/api/adapters/v2Bundle.ts`, `src/app/redlines/{page,EngineReviewPanel}.tsx`, `src/lib/api/{client,types,index}.ts`, `src/lib/api/mock/fixtures.ts`. Original audit sources: v2 `review/{reviewer_payloads,reviewer_service,design_stroke_cards}.py`, `proof/run_reviewer_demo_artifact.py`; web `src/contracts/index.ts`, `src/lib/api/{types,index,client}.ts`, `src/app/redlines/*`, `scripts/check-contract-parity.mjs`, `docs/*`, `README.md`.*
