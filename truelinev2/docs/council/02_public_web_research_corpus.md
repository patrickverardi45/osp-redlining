# Public Web Research Corpus — HDD / Fiber Plan-Set Patterns for the v2 Placement Engine

> **Role of this document.** A synthesis of PUBLIC, legally-fetched government / agency / railroad
> standards and a small number of real public permit plan sets, distilled into patterns, a placement
> evidence checklist, synthetic-test rules, and name-free engine heuristics.
>
> **What this is NOT.** This corpus informs *patterns and tests*, never customer-specific geometry.
> Public HDD construction guidance describes how bores are *documented and drawn*; it is **not redline
> placement truth** for any TrueLine customer. Nothing here changes the deterministic 50/58 frontier,
> the renderer, fixtures, anchors/coordinates, the backend truth path, or origin/main. Treat every
> learning below as a *prior / confidence signal / test generator*, not as an auto-placement source.
>
> **Provenance honesty.** Every row in the source table below was `fetched=true` in the upstream
> research session. Sources marked `fetched=false` were **dropped** (see "Dropped sources").
> "HTTP 200 is not proof" — these were text-extracted and the cited evidence is quoted/paraphrased
> from the extracted bytes.

---

## 0. Corpus at a glance

| Metric | Value |
|---|---|
| Categories researched | 5 (caltrans-hdd, state-fiber-broadband, usace-federal-boring, railroad-hdd, municipal-hdd-standards, planprofile-borelog) |
| Sources fetched (`fetched=true`) | 21 |
| Sources dropped (`fetched=false` in JSON) | 1 (Caltrans PPM ch2 sect2-5 — honest self-disclosure: not re-verified live) |
| Sources noted unreachable in research (never cited; not in JSON rows) | USACE sample bore plan (403/Akamai), USFWS HDD (ECONNREFUSED), Lake Wales FL (no extractable text in one category), CSX template (403), Dallas drafting std (TLS), FHWA WFL sample sheet (ECONNREFUSED), USDA RUS 1753F-150 (403), UPRR HDD as-built (scanned, no text), Austin HDD checklist (404) |
| Usable as **fixtures** (public-record pattern/structure) | 6 |
| **reference_only** | 15 |

**Cross-source invariant (the single most important finding):** across DOT, federal, municipal,
railroad, and broadband sources, a bore/trench/conduit segment is universally a tuple of
**(begin/entry endpoint, end/exit endpoint, side-or-offset, install method, length)** documented as a
**plan view + profile view pair**. Bore START/END are *named, located endpoints* (entry pit / exit
pit, bore pit / receiving pit, Entry Station / Exit Station, Begin Station / End Station) — **not**
inferred line ends. This is the cleanest possible signal for an evidence-based placement engine and
directly corroborates the v2 "entry/exit + low-point" binding model already in use.

---

## 1. Sourced source table (every FETCHED source)

Legend — Usability: **fixture** = public-record document usable as a pattern/structure test fixture
(extract generic conventions only; never reuse named parties or redistribute drawings);
**reference_only** = legal to read/summarize but copyrighted, template-only, or no worked numeric
example — informs terminology/rules, not a drop-in fixture.

### 1.1 caltrans-hdd

| # | URL | Source type | Evidence (key) | Stationing style | Plan/profile layout | HDD/bore terminology | Route geometry | Callout patterns | How a human infers start/end | What the engine should learn | Usability | License / public note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | dot.ca.gov …/trenchless-booklet-a11y.pdf | Caltrans Encroachment Permits "Guidelines & Specs for Trenchless Technology Projects" (Aug 2018) | Numbered HDD plan-set submittal list: entry/exit point, drill path alignment (plan & profile), depth of cover, utility-crossing elevations/clearances, reamer dia. Recommended-min-cover table by product dia (2–6"→4ft; 8–14"→6ft; 15–24"→10ft; 25–48"→15ft). ≥30" = "tunnel". Requires as-built of installed pipe. | Centerline "Survey Grid Line"; corings 25–100 ft along alignment; bore length in feet; station implied along alignment (not printed 0+00 here) | Requires **both** plan view + profile view; profile carries cover + crossing elevations | pilot bore, back-reaming, reamer dia, pullback, entry/exit pit, bore pit/receiving pit, casing vs carrier, bentonite slurry, frac-out, dog-legs, depth of cover, line & grade | Linear bore entry→exit on a designed H+V alignment; jack&bore = straight transverse encased crossing | entry/exit labels, depth-of-cover note, crossing-clearance notes, pit-offset notes (≥10 ft rural / ≥5 ft urban beyond curb) | START = entry point/bore pit, END = exit point/receiving pit; confirm via plan alignment crossing road + profile cover dip; pits pinned by offset from pavement edge | Treat entry/exit (HDD) and bore/receiving pit (jack&bore) as canonical START/END anchors; cross-validate cover by diameter; use plan-set element list as the "what evidence is present" checklist; ABSTAIN = "which element is unmodeled" | **fixture** | Public CA DOT guidance, dot.ca.gov; US state-gov work. Patterns in own words; short quotes only. |
| 2 | dot.ca.gov …/202601-gm-trenchlessconstruction_a11y.pdf | Caltrans Geotechnical Manual "Trenchless Construction" module (Jan 2026) | Method-by-diameter Table 1 (jack&bore 8–60"; microtunneling 10–120"; HDD 2–48"; pipe jacking 42–120"); geotech borings "one near each end" (+ median on divided hwy); ≥30" Cal OSHA "tunnel" | Positional ("near each end", "median"); no printed 0+00 | Geotech reporting doc, not a drafting standard; defers profile to nSSP / shop drawings | jack&bore, microtunneling, HDD, pipe jacking, EPBM, pipe ramming, pilot tube, invert, crown, casing dia | Single under-highway crossing; settlement profile is Contractor's | method-vs-diameter and method-vs-soil tables; boring-placement rules | Crossing extent inferred from two end borings + invert profile | Use diameter ranges per method to classify trenchless dialect; "one boring near each end (+median)" = structural prior for endpoints / # legs; ≥30" = reclassification gate | **reference_only** | Public Caltrans GM, dot.ca.gov; third-party table cited as labeled excerpt only. |
| 3 | dnr.wisconsin.gov …/1072_HorizDirectionalDrilling_10-2022.pdf | Wisconsin DNR Technical Standard 1072 HDD (Oct 2022) | "drill path segment" vs "HDD project"; Small/Med/Large by dia AND "station distance"; min-cover table near-identical to Caltrans; large-bore profile must carry "Specific station and elevation data" + "Vertical tolerance" | **Explicit "station distance"** = drill-path length in horizontal plane; large-bore profile = station+elevation pairs | Strong explicit plan + profile separation | drill path/segment, entry/exit point, pilot hole, reaming, pullback, station distance, min cover, inadvertent release (IR)/frac-out, bore logs, as-built | Surface-launched arc entry→under→exit; cover-controlled low point; vertical-tolerance band | profile: ground-surface lines, station+elevation ticks, vertical-tolerance band, cover dim; plan: entry/exit, staging, crossing labels | START at entry-point label, END at exit-point label; confirm via profile station/elevation; length = exit sta − entry sta | Adopt **station distance (exit − entry) as canonical bore-length**; parse entry/exit station+elevation pairs from profile; Small/Med/Large as complexity grader; near-identical cover table = cross-source corroboration | **reference_only** | Public WI DNR std, dnr.wisconsin.gov; figures in attachments not fetched. |
| 4 | ftp.dot.state.tx.us …/specs/2014/standard/s476.pdf | TxDOT Item 476 "Jacking, Boring, or Tunneling Pipe or Box" (2014) | work shaft/jacking pit, jacking head, backstop/thrust block; Pilot Hole Method (2" pilot = centerline); hard tolerance "must not vary from line & grade … by more than 1 in. in 10 ft."; allowable-bore-dia table; carrier vs casing | Bore extent = "line and grade shown on the plans"; measured "by the foot between the ends … along the flow line"; no 0+00 in spec | References plan+profile elsewhere; spec presumes a plan sheet | casing/encasement, carrier pipe, liner, 2" pilot hole, auger/cutter head, work shaft, jacking head, backstop/thrust block, flow line, line & grade | Straight encased crossing on fixed line+grade; jacked from low/downstream end; monotonic grade with defined up/downstream sense | pay-item callouts, conduit-bore-dia table, tolerance note (1"/10 ft), grout note, parallel-bore separation (3 ft or 2× dia) | Two pipe ends on plan (work-shaft=start, opposite=exit); direction from flow-line arrow; length = footage along flow line | Model jack/bore as **single straight fixed-grade segment** with explicit flow-line direction; apply **1"/10 ft tolerance as a placement-validation envelope**; conduit→casing-dia table; bore length = end-to-end footage along flow line | **reference_only** | Public TxDOT std spec, ftp.dot.state.tx.us; retrieved via curl after TLS error; 3-pp PDF verified. |

### 1.2 state-fiber-broadband

| # | URL | Source type | Evidence (key) | Stationing style | Plan/profile layout | HDD/bore terminology | Route geometry | Callout patterns | How a human infers start/end | What the engine should learn | Usability | License / public note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 5 | dot.ca.gov …/encroachment-permits/mmbn-0448-a11y.pdf | Caltrans Middle-Mile Broadband Network (MMBN) encroachment special provisions | The placement RULESET: trench-location preferences vs ROW/edge-of-pavement; "no-fiber zone" <4 ft from EP; depth by method (trench ≥42", HDD 4–10 ft); VAULT taxonomy: PULL vault/hand hole vs SPLICE vault (spool-length demarcation); FHWA vaults = Maintenance Access Points | No printed STA; geometry as offsets ("4 ft from EP", vault "5 ft from EP") | Written companion to a plan/profile set; refs detail sheet MMBND-4 | HDD, trench method, directional boring (off-bridge); stream/canal crossings | Centerline-offset doctrine: "straight where possible", "consistent offset from centerline", traveled-lane conduit at center of outside lane | PULL VAULT/hand hole, SPLICE VAULT, MAP, TRENCH vs HDD method, detail token MMBND-4 | Not read from this doc; gives RULES: pull vault at structure end = bore terminus; splice vault at spool-length = segment boundary | Encode method-dependent depth/offset priors + vault taxonomy: PULL=continuity point, SPLICE=trunk boundary, vault-at-structure-end=bore endpoint; "straight consistent offset" = default highway geometry — **priors, never auto-placement** | **reference_only** | Footer "© 2025 California DOT. All Rights Reserved." Public but copyrighted — summarize, do NOT bulk-copy. |
| 6 | dot.ca.gov …/bridgestandarddetails/chap-20/xs20-010-ug-a11y.pdf | Caltrans Bridge Standard Detail user guide (Sec 20 comm conduit on structures, MMBN) | Standard bundle "3 × 2" conduits"; alt "single 4"/5" + 4-cell fabric innerduct"; bridge-mount risk table; "discuss directional boring with District" for off-bridge | None (detail/typical); defines conduit BUNDLE a plan then routes/stations | Catalog of XS detail sheets (cross-section typicals), not plan-and-profile | directional boring (off-bridge low-risk alt) | Vertical/elevation routing across a structure (girders, box-girder openings, barrier) | sheet tokens xs20-010-N; bundle shorthand "3×2"", "4"/5"+4-cell innerduct" | n/a to start/end; identifies conduit cross-section persisting across a crossing | Normalize conduit-bundle callouts (count×size + innerduct cells) as a structured attribute; recognize bridge crossings as a distinct route mode (elevation change) | **reference_only** | Caltrans bridge details, dot.ca.gov; copyrighted (per companion © line). Reference only. |
| 7 | cityofconcord.org …/View/339/Fiber-Optic-Project-PDF | City of Concord Fiber Optic Project special provisions (Aug 2017) | "directional drilling or jacking and boring"; bends ≤180°, enter pull box within ±30° vertical; trench ≥24"; Sch80 HDPE; pull-box/vault catalog (No.6E, N48); 3-cell innerduct; slack 15 ft/box, 100 ft mid-span splice; **Test Plan lists each segment's start/end "by intersection name, facility name, stationing, or other means"** | Stationing is ONE of several accepted endpoint references (named structure/intersection equally valid) | Refs "Project Plans" for geometry; spec is textual companion | directional drilling, jacking & boring, trenching, "pothole" (verb) | Street-section routing; home-run conduits; tracer wire intersection-to-intersection | box/vault tokens No.6E, N48, 24×36, 17×30; material tokens Sch80 HDPE, GRS, PVC Sch40; lids "inscribed" | Endpoints from sanctioned anchors: bounding intersection, named facility, and/or station; splice vault = stronger boundary (100 ft slack) | **Accept named-structure endpoints as first-class, not only stations**; bend-budget (≤180°, ±30° vertical entry) = geometric sanity check; slack rule discriminates pass-through vs splice vault | **fixture** | City of Concord public DocumentCenter; gov public-record bid doc; no © line. Cite short snippets only. |
| 8 | engpermits.lacity.org …/CA002_…_BOE_Approved_Plans.pdf | LA City BOE-approved OSP construction plan set (4 sheets) | Real graphical plan. Legend: PROPOSED BORE / TRENCH / MICRO TRENCH / HAND HOLE / VAULT / BORE PIT / RISER POLE / POT HOLE; scope tally box; STA NN+NN callouts; offset callouts "<size>" <dist>' <N/S/E/W>/O CL"; CONDUIT CURVE DATA; "1-1.25" HDPE" | Engineering chainage STA NN+NN at structure ends; running grid stations along street; offset = distance + side-of-centerline | Plan over street base map + separate DETAIL sheet + vicinity map; profile data in curve-data/callouts | PROPOSED BORE, BORE PIT, "tunnel under existing curb"; open-cut = TRENCH / MICRO TRENCH (distinct method) | Linear route along street, conduit polyline offset a fixed distance from C/L; riser transition to aerial | symbolized legend; STA tags; footage tics (157', 32'…); conduit shorthand count-size-material; offset shorthand; vault note "4' BEHIND CURB" | Read bore extent from the two STA tags at endpoints (structure-to-structure); confirm length vs footage tic; lateral position from "<dir>/O CL"; linetype = install method | **The canonical drawn target**: parse legend → linetype+symbol → {method, structure}; read STA at endpoints, footage tics for length, offset for parallel position; one route alternates BORE/TRENCH/MICRO-TRENCH spans bounded by structures; scope tally = cross-check on summed lengths | **fixture** | LA City BOE permit portal; gov public record. Title block names a private OSP contractor — **runtime data, not reusable patterns**. Extract generic conventions only; do not redistribute drawings. |
| 9 | utilities.iowadot.gov …/77-0804-105_C.pdf | Iowa DOT federal-aid fiber/ITS plan set (27 sheets, plan-and-profile) | **Richest machine-readable**: "Begin Station / End Station / Side" table (e.g. +00.00 8+26.00 RT 870); separate pay items "2 INCH BORED" vs "2 INCH PLOWED"; handhole banks 1-4, Type IV handholes; mid-sheath splice at middle of slack; PLAN-AND-PROFILE color legend | Formal NN+NN.00 in tabular Begin/End ranges with Side (RT/LT) + quantity; the cleanest "how a doc states bore start/end" | True plan-AND-profile; legend Blue=proposed alignment/stationing/tics, Magenta=proposed profile; geometry deferred to "D-Sheets" | BORED vs PLOWED vs TRENCHED as first-class methods; duct-bank boring under interstate | Alignment-based; duct bank parallel, bore only at crossings; "centered on the alignment" for paired bores | pay-item ids; station-range rows; "HANDHOLE BANK 1-4", "Type IV"; layer-color legend; "D-Sheets" ref | Read start/end directly from Begin/End Station columns (+Side); corroborate vs plan tics + method note; bore terminates at handhole/bank or crossing | **Adopt (begin sta, end sta, side, install-method, length) as the canonical internal segment model**; install method is required and reconciles with summed pay-item LF; splice handhole = segment boundary; plan/profile color legend tells which layer carries stationing vs profile | **fixture** | Iowa DOT utilities portal; federal-aid public record. Named private parties = runtime data only. Extract generic conventions; don't redistribute or reuse named parties. |

### 1.3 usace-federal-boring

| # | URL | Source type | Evidence (key) | Stationing style | Plan/profile layout | HDD/bore terminology | Route geometry | Callout patterns | How a human infers start/end | What the engine should learn | Usability | License / public note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 10 | ferc.gov …/2020-04/guidance-natural-gas.pdf | FERC Staff Guidance: HDD Monitoring / IR Response / Contingency Plans (Oct 2019) | Mandates "HDD plan and profile drawing"; example tables with columns literally **"Entry (Station)", "Exit (Station)", "Approx. Entry/Exit Milepost", "Total Length (feet)"**, Depth of Cover, Horizontal Setback. Tables are blank TEMPLATES, no worked numbers | Dual: long pipelines by MILEPOST; resource crossings by STATION; length given directly as "Total Length (feet)" | Required plan + profile pairing; profile = drill alignment vs feature + cover | HDD, pilot hole, reaming, pullback, entry/exit workspaces, drill path, hydrofracture, IR, drilling mud, annular pressure | Designed vertical-plane curve; endpoints = entry/exit; setback measured to each endpoint | tabular per-crossing: dia, Entry/Exit MP/Sta, Total Length, Depth of Cover, Elev Diff, Setback, HDD ID, Crossing Name | START = Entry (Station/Milepost), END = Exit (Station/Milepost), read directly from crossing table; Total Length confirms span; profile confirms which end is entry | Treat bore as two-endpoint object: START=Entry sta/MP, END=Exit sta/MP; **length = corroborating check, not free input**; prefer parsing explicit Entry/Exit+length over inferring; recognize milepost AND station as position systems | **reference_only** | US federal gov work (FERC), public domain; templates only (no worked numbers). |
| 11 | ferc.gov …/2020-05/Appendix-G_1.pdf | FERC Appendix G: HDD Contingency Plan for a NGA pipeline (Apr 2015) | "alignment drawings show the entry and exit locations and staging areas"; contingency = "changing of the drill profile (depth of hole)", relocate entry/exit; stationed sheets live in a separate exhibit | No station numbers; defers to separate alignment drawings | References external alignment (plan) + "drill profile (depth of hole)" | HDD, entry/exit points, staging areas, drill path, drill profile, drilling mud, returns, IR, depth clearance | Depth-controlled profile under sensitive features; entry/exit are relocatable endpoints | prose: "entry and exit locations", "staging areas", "depth clearance", "drill profile" | Reader pointed to alignment drawings; start/end = entry/exit bracketing the feature, deeper mid-path on profile | Reinforces entry/exit as canonical endpoints + complementary plan(horizontal)/profile(depth) sheets; expect stationed numbers on the ALIGNMENT sheet, not narrative; don't treat narrative as a geometry source | **reference_only** | US federal gov filing exhibit, public domain. Narrative only. |
| 12 | lakewalesfl.gov …/View/383/Directional-Bore-Standards-PDF | City of Lake Wales FL Directional Bore Standards (rev 06/15/20) | "show the directional bore in profile view … as it should be installed"; entry angle 12–14° (max 15°), exit 6–12°; "ideally … in a vertical plane"; min cover 36"; min radius of curvature listed; refs Appendix C "Directional Bore Log" | No sample station numbers; fixes existing utilities in 3D; as-built bore log carries the logged path | **Profile-centric** (bore is a vertical-plane curve); plan-view utility location implied | directional bore, HDD, carrier pipe, pilot bore, entry/exit pit, entry/exit angle, min radius of curvature, max pull strength, bore path, as-built, Directional Bore Log | Shallow vertical-plane curve: entry tangent 12–14°, long-radius sag, exit tangent 6–12°, min 36" cover | pipe size/material, casing vs carrier, max pull, min radius, entry/exit angles, cover (36"), clearance (18"), as-built path | Entry pit (12–14°) one side, exit pit (6–12°) other; profile shows pipe dip; as-built log records realized path | **Model bore geometry parametrically** = two endpoints + entry/exit tangent angles + sag radius + cover, NOT an arbitrary polyline; as-built bore log = corroborating evidence artifact; carrier vs casing matters for what the redline represents | **reference_only** | Public municipal std, lakewalesfl.gov; standards text fetched, not a filled plan sheet. |
| 13 | fdotwww.blob…/specbooks/july2015/files/555-715.pdf | FDOT Standard Specs §555 "Directional Bore" (Jul 2015) | Directional bore = HDD multi-stage (pilot bore along predetermined path); plans include "roadway plan and profile, cross-section, boring location, subsurface"; elevations tied to "permanent FDOT feature"; pits entry/exit/recovery/slurry sump; tracking (clock&pitch, depth, position x,y, azimuth); location = "Contract plans station number or reference to a permanent structure"; as-built offset from product center to permanent feature | **Civil stationing anchored to a permanent feature**; as-built = offset-from-permanent-feature + (x,y) + depth + azimuth along alignment | Plan + profile + cross-section required; elevations tied to a permanent feature | directional bore/HDD, pilot bore, carrier pipe, conduit/casing/duct, entry/exit/recovery/sump pit, bore path/alignment, failed bore path, tracking, As-Built Plans Package | "Predetermined path" tracked point-by-point by (x,y), depth, azimuth — a sequence of located stations anchored to a permanent feature | station-or-permanent-structure; offset from product center; top elev+dia+material of crossings; (x,y)/depth/azimuth at alignment points | Start/end = entry/exit pits + bore-alignment stationing/offsets to permanent feature; first/last logged alignment point = start/end | Reconstruct endpoints + path from station-or-permanent-feature + offset + (x,y)/depth/azimuth samples; **map "offset from permanent fixed feature" to the anchor model**; pit vocab (entry/exit/recovery/sump) distinguishes endpoints from ancillary excavations | **reference_only** | Public FDOT spec, FDOT Azure blob; gov std, fully text-extractable. |

### 1.4 railroad-hdd

| # | URL | Source type | Evidence (key) | Stationing style | Plan/profile layout | HDD/bore terminology | Route geometry | Callout patterns | How a human infers start/end | What the engine should learn | Usability | License / public note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 14 | bnsf.com …/about-bnsf/utility.pdf | BNSF Utility Accommodation Policy (Jan 2026) + AREMA-derived HDD plan-view exhibit (p.27, Fig 1-5-15) | **DUAL stationing on every labeled point**: "ENTRY BORE PIT / BORING STA. 6+20.83 / TRACK STA 8038+88.60 / MP 55.95" → "RECEIVING BORE PIT / BORING STA 10+00 / TRK STA 8042+15.01 / MP 56.02"; 90° angle at C/L; pits ≥30 ft from track center; jack/dry bore 8'-3" below base of rail + 6' below ditch flowline; HDD 12' below base of rail; crossings ≥45° | DUAL: bore-axis BORING STA n+nn (begins at entry pit) **and** railroad TRK STA NNNN+NN.NN (crossed track) on same label; anchored to MP | Two-view exhibit: PLAN VIEW (Fig 1-5-15, bore at 90°, pits, ROW, offsets) + separate profile/section | HDD, PROPOSED DIRECTIONAL BORE, jack-and-bore/dry boring, ENTRY BORE PIT, RECEIVING BORE PIT, base of rail, top of tie, flowline, casing/carrier, "wet bores not permitted" | Near-straight perpendicular crossing of track ROW; single line entry pit→receiving pit; track-crossing point mid-span; pits ≥30 ft from track C/L | leader lines to stacked multi-line labels (role + BORING STA + TRK STA + MP); angle "XX°" at C/L; offset dims (5.0' MIN) perpendicular to ROW | START = ENTRY BORE PIT (lowest BORING STA), END = RECEIVING BORE PIT (highest); direction = increasing boring sta; crossed track id'd by TRK STA+MP; depth from profile base-of-rail cover | **Model a bore endpoint as carrying TWO stations** (bore-local n+nn AND host-feature TRK STA) + a milepost; the track is a separate stationed reference frame the bore CROSSES, not the bore's own axis; ENTRY/SENDING=start, RECEIVING/EXIT=end; read angle from C/L "NN°"; read depth/length from profile cover dims | **reference_only** (exhibit credited to AREMA — reproduce PATTERN, not the figure) | Public bnsf.com, robots-permitted; embedded exhibit credited to AREMA Fig 1-5-15 (paywalled — only the generic pattern reused). |
| 15 | cn.ca …/utility-crossing-encroachment-application-packet.pdf | Canadian National utility crossing packet + clean schematic Example Plan View / Example Profile | Enumerated plan-view + profile requirements; **"Distance from Railroad Mile Post … plus feet beyond (EX. MP 2 + 1,200 ft.)"**; angle ≥45°; depth tables (Dry Jack&Bore base-of-rail 6 ft, Directional 15 ft); excavation ≥25 ft from track C/L; Example Plan View (red bore crossing CN MAIN + INDUSTRY TRACK, hatched entry/receiving pit boxes); Example Profile (ZONE OF INFLUENCE slopes, BORE PIT DEPTH dims) | **MILEPOST-PLUS-OFFSET in feet** ("MP 2 + 1,200 ft.") — most directly parseable convention | Mandated PLAN VIEW + PROFILE pair, each a separate sheet; plan = top-down schematic, profile = section with bore beneath stacked features | dry directional bore, dry jack & bore, boring, Bore pit (entry), Receiving pit (exit), base of rail, flowline ditch, zone of influence, cased/uncased, carrier/casing, METHOD OF INSTALLATION | Single straight bore ≥45° crossing full ROW; pits at ROW edges / ≥25–30 ft from track; multiple parallel tracks crossed in one run | leader-line labels per pit + warning marker; angle dim; perpendicular distance dims; title block (method + utility); required-notes block; explicit graphic-scale requirement | START = "Bore pit" (entry, one ROW edge), END = "Receiving pit" (other edge); crossed tracks named on plan; location = MP + feet; depth from profile + min-depth table by method | Support a **second stationing dialect: milepost-integer + feet-offset**; Bore pit=start, Receiving pit=end; read crossing angle + per-track points from plan; method selects the min-depth-below-base-of-rail row; expect paired plan+profile + graphic scale; clean schematic ≈ a synthetic test image | **fixture** | Public cn.ca; robots-permitted "/-/media/files/"; Example drawings are CN's own GENERIC templates (placeholder labels), suitable as schematic reference fixture. |
| 16 | txdot.gov …/exhibit_a_design-i1005859.html | TxDOT Railroad Operations "Exhibit A Design" manual page | "Plan view of conduits/pipes/culverts under track"; conduits ≥5 ft below top of rail; top of pipe ≥5 ft below top of tie + 5 ft below ditch bottom; "Boring pits located ≥30 ft from track center"; "Wet boring not permitted"; Cooper E-80 loading; RMC | Refs tie-to-fixed-object + milepost/valuation-station practice; this page emphasizes depth/offset over a worked station | Requires plan view of under-track utility; depth/cover dims imply a profile/section | boring, boring pits, wet boring not permitted, casing, carrier, top of rail/tie, base of rail, Cooper E-80 | Under-track crossing; pits ≥30 ft from track center; casing across ROW; perpendicular | depth-of-cover callouts to top of rail/tie/ditch bottom; offset "pits ≥30 ft from track center"; casing-extent across ROW | Crossing extent inferred from pit locations (≥30 ft each side) + casing run across ROW; depth from "X ft below top of rail/tie/ditch" | Confirms **cross-vendor invariants**: pits ≥30 ft, cover to top-of-rail/tie/ditch, perpendicular, dry boring only; good for validating parsed depth/offset ranges; neutral DOT uses same vocabulary | **reference_only** | Public TxDOT online manual, txdot.gov; gov work, plain-text reference. |
| 17 | up.com …/pipeline/pipeline-procedure | Union Pacific public pipeline-crossing procedure page | Governed by "AREMA … Vol 1, Ch 1, Part 5: Utilities"; tie to "Fixed Object Identity"; standardized Exhibit A forms; ~30–45 day processing; (companion: track bores ≥60" below base of rail; wet bores not permitted) | Defers to AREMA engineering-station + milepost; emphasizes tie-to-Fixed-Object | Procedure-level, not a drawing; Exhibit A plan tied to mapping | pipeline crossing, casing, carrier pipe, bore (60" below base of rail), wet bore not permitted, Fixed Object Identity, Exhibit A | Crossing enters one ROW side, exits other "in as near a straight line as possible" = straight perpendicular crossing | Exhibit A form fields; ties location to MP/fixed object | Start/end = where straight crossing enters/exits ROW, tied to MP/fixed object; depth from AREMA/Exhibit-A rule | Reinforces "tie crossing to fixed object + milepost" + crossing-vs-encroachment distinction (straight ROW-to-ROW crossing vs parallel longitudinal run) = a classification the engine can mirror; wet bores disallowed (don't synthesize them) | **reference_only** | Public up.com, "© 2026 Union Pacific All Rights Reserved." Plain-text reference; AREMA NOT fetched/reproduced. |

### 1.5 municipal-hdd-standards

| # | URL | Source type | Evidence (key) | Stationing style | Plan/profile layout | HDD/bore terminology | Route geometry | Callout patterns | How a human infers start/end | What the engine should learn | Usability | License / public note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 18 | salina-ks.gov …/505-Directional-Boring_08-02-2023.pdf | City of Salina KS §505 Directional Boring (8-2-2023) | Bore-log fields (position, roll, tilt, **depth every 10 ft**, pullback force, fluid pressure); H tol ±1 ft, V tol ±0.5 ft; min cover 54"; entry 12–14° (max 20°), exit 6–12°; abandoned pipe shown on as-built | No station numbering; alignment = approved plan/profile + chained depth/location log sampled every 10 ft (distance-from-rig) | Refs horizontal alignment + "plan and profile document"; as-built = both H + profile views | directional bore, pilot/tool head, pullback, breakaway, launching/receiving end, entry/exit angle, carrier pipe, tracer wire, as-built variance | Single segment launch(entry)→receiving(exit); ideally vertical-plane; sag by entry angle/max depth/exit angle | tolerance callouts (±1 ft, ±0.5 ft); cover ("min 54""); angle callouts; tracer-wire color | START = entry/launch end, END = receiving/exit end; 10-ft depth log gives path between | Model HDD as ENTRY→EXIT with explicit angles + a **10-ft-sampled depth profile**; as-built = authoritative actual-vs-designed incl abandoned; **expect tolerance bands (~1 ft H / 0.5 ft V) so small deltas are NOT errors** | **fixture** | Public City of Salina std, salina-ks.gov; for public use. (Near-verbatim derived from Lakeland — template FAMILY; never reuse city names as ids.) |
| 19 | filetransfer.nashville.gov …/sec3305023.pdf | Metro Nashville/Davidson §330523 Guidelines for Utility HDD | Existing utilities in BOTH plan + profile; engineer computes descending/ascending angle per bore pit + exact setback; min 8 ft H sep (abs min 5 ft), 3 ft V sep, **12 ft max bore depth threshold**; relief pits at run midpoints; as-built with highlighted changes; GIS digital w/ GPS on benchmarks/manholes; SUE Quality Levels A–D | No station numbering; pits by calculated setback/exact location; elevations interpolated along corridor; angle-and-separation driven | Explicit dual-view ("both plan view and profile view of all existing utilities"); detail sheets = trench cross-sections | horizontal directional boring, slurry vs auger, bore pit, relief pit, descending/ascending angle, potholing, SUE, utility window | Continuous-corridor run broken into **pull-to-pull segments joined at pits**; relief pits at midpoints; conflict points at crossings | separation callouts (8 ft / abs 5 ft H; 3 ft V); depth threshold (12 ft); pit-size callouts; as-built highlighted changes | Each bore PIT = a node; bore starts at a pit (descending) and ends at next pit/relief pit (ascending); long corridor = chain of pit-to-pit legs; depths from profile elevs | **Long bores decompose into pit-to-pit segments (chain of legs joined at pits)** — directly relevant to multi-leg / cross-sheet assembly; bore PITS = start/end anchors; as-builts may carry GIS/GPS-tagged endpoints (benchmarks/manholes) usable as anchors | **fixture** | Public Metro Nashville gov, nashville.gov filetransfer; public-works guideline. |
| 20 | rtcws.rtcsnv.com …/Specifications/Adobe/216.pdf | RTC Southern Nevada §216 HDD | **TABLE 216-1 Submittal: "Bore Plan/Profile", "Bore Data", "As-Built Survey" as distinct documents**; surface survey elevs at ≤10 ft; Bore Plan/Profile = scaled plan+profile w/ dimensioned clearances; Bore Data = rod/joint # + depth + pitch per locate reading; As-Built Survey ±0.3 ft to benchmarks; white-paint depth ticks ≤10 ft | Per-rod chained-distance model: rod/joint # with depth+pitch; surveyed elevs along alignment ≤10 ft; as-built tied to benchmarks (not printed station ticks) | Explicit "scaled plan and profile drawing of the proposed pilot bore" + clearances + existing utilities | pilot hole, reaming/back reamer, pullback, bore-tracking pit (entry/exit/slurry sump), critical structure, MGS/gyro, product pipe, sectional vs non-sectional | Single pilot-bore entry→exit as rod-indexed (depth,pitch) series; reamed hole = 1.5× product OD; measure by lineal foot along centerline | submittal-table labels; clearance callouts; accuracy callouts (±0.3 ft, ±0.02 ft V); white-paint ticks ≤10 ft; locating accuracy ±2% of distance | START = entry pit (rod 0), END = exit pit; Bore Data table walks depth+pitch entry→exit; As-Built Survey gives surveyed coords | Treat a completed bore as a **rod-indexed (rod#, depth, pitch) sequence** between entry/exit; the **"Bore Plan/Profile + Bore Data + As-Built Survey" triplet = canonical evidence set**; benchmarks/manhole IDs = anchors; expect ~10-ft / per-rod sampling | **fixture** | Public RTC Southern Nevada std, rtcsnv.com; public agency construction standard. |
| 21 | lakelandgov.net …/directional-bore-spec-manual-6-11-2018.pdf | City of Lakeland FL Water Utilities Directional Bore Standards (2018-06-11) | "show the directional bore in PROFILE view … as installed", with max pull + min radius; signed/sealed As-Built incl abandoned-in-place bores; min cover 36" (≥18" V clearance); tool head logged every 10 ft (position, roll, tilt, depth, pullback, fluid pressure); variance ±1 ft V / ±1 ft H; **multi-pull bores joined at a dug pit "as if it were a continuous pull-in"**; Appendix C "Directional Bore Log"; Appendix A pullback/curvature equations | No printed station chain; profile + 10-ft-interval location/depth log; reference = distance-along-bore from rig | Explicit profile-view-on-the-plans; as-built = both H + profile; profile shows sag with entry/exit + existing utilities | directional bore, HDPE carrier, breakaway/pulling eye, entry/exit pit, pullback, butt fusion/electrofusion, pull-nose, abandoned-in-place bore, as-built | "Bore lies in a vertical plane passing through the beginning and ending points"; long installs split into pulls joined at a dug pit → continuous; valve at each end | cover (36"); clearance (18"); tolerance (±1 ft H/V); plan design values (max pull, min radius); pipe color coding | Beginning/ending points read from profile (bore in a vertical plane through them); start=entry pit, end=exit/receiving; multi-pull intermediate dug pits are joints; Appendix C log walks 10-ft steps | **Profile-view geometry is source-of-truth for the sag path**; "vertical plane through beginning/ending points" = clean 2-point geometric prior; **multi-pull = segments joined at pits into one continuous run** (multi-leg analog); ingest a structured 10-ft bore log; support showing/flagging an abandoned alternate path | **fixture** | Public City of Lakeland FL std, lakelandgov.net; for engineers/developers. (Salina §505 is derived — template FAMILY; never reuse city names as ids.) |

### Dropped sources (`fetched=false`)

- **1 dropped row in the JSON**: Caltrans PPM ch2 sect2-5 (`dot.ca.gov …/ppm-text-ch2-sect2-5-a11y.pdf`) was self-disclosed `fetched=false` — its content was retrieved via a cached copy but the live URL was not re-verified this session, so it is **excluded from the source table and from fixture eligibility**. (Its substance is fully covered by Source #1, the Caltrans Trenchless booklet, which WAS independently fetched.)
- **Never-cited unreachable sources** (noted in research summaries, never in JSON rows): USACE sample bore plan (HTTP 403/Akamai), USFWS HDD process (ECONNREFUSED), Lake Wales FL in the municipal pass (no extractable text — note: Lake Wales WAS separately fetched cleanly in the USACE category as Source #12), CSX bore-plan template (403), Dallas pipeline drafting std (TLS first-cert error), FHWA Western Federal Lands sample plan/profile (repeated ECONNREFUSED), USDA RUS 1753F-150 (403), UPRR HDD as-built (scanned, no extractable text), Austin HDD checklist (404). **Next research step to obtain a true visual fixture**: retrieve the USACE/USFWS/FHWA-WFL sample plan IMAGES via an interactive browser path — those show an actual drawn, stationed bore.

---

## 2. Pattern library (recurring HDD / fiber plan patterns)

**P1 — Plan + Profile pair.** Every dialect documents a bore as a *plan view* (top-down horizontal
alignment) over/beside a *profile view* (vertical section). The plan locates the route horizontally;
the profile carries depth-of-cover, entry/exit angles, and the sag low point. (Sources 1,3,9,10,12,13,
14,15,18,19,20,21.)

**P2 — Named, located endpoints.** Bore START/END are *named features*, not inferred line ends:
entry point / exit point (HDD), bore pit / receiving pit (jack&bore, railroad), Entry Station / Exit
Station (FERC), Begin Station / End Station (Iowa DOT), launching / receiving end (Salina). (All
sources.)

**P3 — Stationing is the 1-D coordinate, in several dialects.** (a) Engineering chainage `STA NN+NN`
(= NN×100 + NN ft) printed at endpoints (LA BOE, Iowa DOT, FDOT-via-PPM, BNSF). (b) **Station distance**
= exit station − entry station = bore length (Wisconsin, TxDOT "footage along the flow line"). (c)
**Milepost + feet offset** `MP 2 + 1,200 ft` (CN). (d) **Station + perpendicular offset from
centerline** (`<dist>' <N/S/E/W>/O CL`) for lateral position (LA BOE; FHWA boring log "station and
offset"). (e) **Offset from a permanent fixed feature** when no station is printed (FDOT, UP "Fixed
Object Identity"). (f) **Named-structure endpoints** (intersection / facility name) accepted as
first-class alongside stations (Concord).

**P4 — Dual / cross-referenced stationing.** A railroad bore endpoint carries simultaneously its own
**bore-axis station** (BORING STA, starts at entry pit) and the **host-feature station** of the crossed
track (TRK STA) plus a milepost (BNSF Fig 1-5-15). The crossed feature is a *separate reference frame*,
not the bore's own axis.

**P5 — Install method is a first-class attribute that changes everything.** BORE vs TRENCH vs MICRO
TRENCH vs PLOW (LA BOE, Iowa DOT) selects the linetype/symbol, the depth/cover rule, the pay quantity,
and (railroad) the min-depth-below-base-of-rail row. The engine must carry method per segment.

**P6 — Parametric bore geometry, not a freehand polyline.** A bore = two endpoints + entry tangent
angle (≈12–14°) + sag (min radius of curvature) + exit tangent angle (≈6–12°) + depth of cover. "Bore
lies in a vertical plane passing through the beginning and ending points." (Lake Wales, Salina,
Lakeland, FERC.)

**P7 — Depth-of-cover by product diameter (cross-source agreement).** Two independent standards give a
near-identical cover table (Caltrans HDD and Wisconsin DNR): 2–6"→4 ft; 8–15"→6 ft; 16–24"→10 ft;
>24"→15 ft. Railroads override with base-of-rail cover (jack&bore ~8'3", HDD ~12–15", UP ≥60").

**P8 — Method-by-diameter classification.** jack&bore 8–60", microtunneling 10–120", HDD 2–48", pipe
jacking 42–120" (Caltrans GM Table 1); ≥30" = "tunnel" (Cal OSHA). Diameter constrains which dialect a
bore plausibly is.

**P9 — 10-ft / per-rod longitudinal sampling.** As-built bore logs sample depth+pitch every 10 ft or
every rod length (Salina, Lakeland, RTC, Caltrans). 10 ft (or per-rod) is the canonical tick spacing.

**P10 — Tolerance bands (small deltas are NOT errors).** As-built vs design tolerance ~±1 ft H /
±0.5–1 ft V (Salina, Lakeland), ±0.3 ft surveyed (RTC), 1"/10 ft line-and-grade (TxDOT). The engine
should treat sub-tolerance deviation as agreement, not error.

**P11 — Multi-pull / multi-leg assembly joined at pits.** Long runs decompose into pull-to-pull
segments joined at a dug pit / relief pit / handhole bank "as if it were a continuous pull-in"
(Lakeland 2.6, Nashville relief pits, Iowa handhole banks). **Direct analog to the v2 cross-sheet /
SEE-SHEET / multi-leg bore-assembly model.**

**P12 — Structure semantics discriminate endpoints.** PULL vault / hand hole = cable-pulling
*continuity* point; SPLICE vault = spool-length *demarcation* = trunk-segment *boundary*; slack rule
(15 ft pass-through vs 100 ft mid-span splice) distinguishes them (Caltrans MMBN, Concord). Splice
handholes / mid-sheath splice kits mark segment boundaries (Iowa).

**P13 — Plan-and-profile color/layer legend.** Layer color tells which view carries which truth: Blue =
proposed alignment + stationing + tic marks; Magenta = proposed profile (Iowa DOT). Parse the legend to
route attention.

**P14 — Crossing vs encroachment.** A bore is either a *crossing* (straight, ROW-to-ROW, often
perpendicular ≥45°, crosses a feature) or an *encroachment / longitudinal run* (parallel, consistent
centerline offset) (UP, Caltrans MMBN). The two have different geometry priors.

**P15 — Bend / approach-angle budget.** Conduit runs ≤180° total bends and enter a pull box within
±30° of vertical (Concord); entry/exit angles bounded (12–14° / 6–12°). A candidate path violating the
budget is geometrically suspect.

**P16 — Scope tally / pay-quantity cross-check.** A scope-of-work tally box or pay-item LF (TRENCH FT,
MICRO TRENCH, TOTAL CONDUIT FT; BORED LF vs PLOWED LF) is an *independent* check on summed segment
lengths (LA BOE, Iowa DOT).

**P17 — Sheet extent ≠ project extent.** A sheet's drawn extent = its min/max labeled stations; the
route continues to the adjacent sheet at the MATCH LINE STA (FDOT PPM, BEGIN/END PROJECT, MATCH LINE).
Corroborates the v2 SEE-SHEET matchline equation model.

---

## 3. Placement evidence checklist (HIGH / MEDIUM / LOW-correction / ABSTAIN)

Maps onto the v2 confidence model (HIGH ≥0.75 / MEDIUM 0.5–0.75 / LOW <0.5) in
`GENERAL_PLACEMENT_DESIGN_WIP.md`. **All of this is REVIEW-tier evidence; none of it ever gates AUTO**
(AUTO stays the deterministic drawn-geometry recognizer). The deterministic 50/58 frontier is untouched.

### HIGH (≥0.75) — both endpoints independently located, geometry corroborated
- Both endpoints are **named, located features** (entry/exit pit, bore/receiving pit, OR Begin/End
  Station rows) (P2).
- Endpoints carry an **explicit station / milepost+offset / station+offset** that resolves to plan
  coordinates (P3), OR a clean **offset-from-a-named-permanent-feature** (P3e).
- **Length corroborates**: |exit sta − entry sta| ≈ stated Total Length / footage / pay-item LF within
  tolerance (P7/P10/P16), AND KMZ total route length agrees (per WIP confidence input).
- Plan + profile **both present** and consistent (P1); install method explicit (P5); diameter
  consistent with the method's range and the cover table (P7/P8).
- Many station anchors near the span + high axis linearity (low Theil-Sen residual, per WIP).

### MEDIUM (0.5–0.75) — endpoints located but corroboration partial
- Endpoints named but **only one stationing dialect** present, length check within a *looser* band, OR
  profile present without plan (or vice versa).
- Station anchors present but sparse near one endpoint (one endpoint interpolated, the other near the
  edge of the anchor set).
- Install method inferred from linetype/legend rather than stated; diameter/cover not independently
  confirmed.
- A single corroboration source (length OR KMZ OR scope tally) agrees, not all.

### LOW (<0.5) — produce candidate but flag ASSISTED_CORRECTION_SUGGESTED
- One endpoint requires **extrapolation** beyond the station-anchor set (flag + cap per WIP invariant).
- Axis residual high (route not linear/monotonic where the model assumes it), or anchors conflict.
- Method ambiguous; length disagrees with stated/pay-item beyond tolerance (possible wrong leg or
  parallel-run mix-up — see P14, and the v2 parallel-run discriminator doctrine).
- Multi-pull run where a joining pit is unmodeled (P11) — show the best continuous candidate, flag the
  unresolved joint.

### ABSTAIN — insufficient evidence; emit a specific missing-evidence target
Per the v2 evidence-seeking doctrine, ABSTAIN = "unmodeled relationship", not "impossible". State
which checklist element is missing and the next artifact that would resolve it:
- No station anchors and no named endpoints on the relevant sheet → "need plan-view station labels or a
  named entry/exit/pit token."
- No bore-log span (no `[start_ft, end_ft]`) to interpolate → "need a reviewed bore-log row."
- Endpoint named but unanchorable (no station, no offset-to-permanent-feature, no KMZ tie) → "need a
  position reference for endpoint X (station / offset-to-feature / intersection name)."
- Method/diameter unknown AND geometry ambiguous between crossing vs longitudinal (P14) → "need install
  method or crossing classification."

---

## 4. Synthetic test-plan generator rules (realistic but synthetic — NO customer geometry)

Goal: generate plan-set-shaped test inputs that exercise the placement/parse logic **without any real
customer route, coordinate, name, or drawing**. All values are randomly synthesized within
public-pattern-derived ranges.

**R1 — Names are synthetic tokens only.** Streets, structures, utilities, projects, and parties are
generated placeholders (`STREET_A`, `HH-01`, `VAULT_S2`, `PROJECT_TEST_03`). NEVER use a customer,
person, place, or demo name, and never reuse a fetched document's named parties (LA BOE contractor,
Iowa DOT utilities, city names) — those are runtime data, not patterns. Enforce with the existing
name-free naming guards (NAME_TOKENS env + AST identity-no-default).

**R2 — Stationing.** Emit `STA NN+NN.cc` with an alignment origin at a random `0+00`; place running grid
stations at fixed intervals; tag each endpoint with a station. Optionally emit a *second* dialect on
the same fixture (milepost+feet, or station+offset) to test multi-dialect parsing (P3/P4). Bore length
must equal `exit_sta − entry_sta` exactly (P3b) so the length-corroboration check is satisfiable.

**R3 — Plan + profile pair (P1).** Generate a plan polyline (mostly straight, consistent centerline
offset for longitudinal runs per P14; a single perpendicular crossing ≥45° for crossing runs) and a
matching profile sag (entry angle 12–14°, exit 6–12°, min-radius sag, depth of cover from the P7 table
by the synthetic product diameter).

**R4 — Method + diameter consistency (P5/P8).** Pick an install method, then a product diameter inside
that method's valid range (HDD 2–48", jack&bore 8–60", …); pick depth of cover from the P7 table for
that diameter; choose the linetype/symbol that matches the method. Generate at least one fixture per
method (BORE / TRENCH / MICRO TRENCH / PLOW).

**R5 — Endpoints as named, located features (P2).** Every segment terminates in a generated structure
token (entry/exit pit, bore/receiving pit, hand hole, splice vault). Encode splice vs pull semantics
(P12) so the endpoint-identity logic can be tested (splice vault = boundary; pull vault = continuity).

**R6 — Multi-leg / multi-pull (P11/P17).** Generate a long run split across ≥2 sheets joined at a
MATCH LINE STA, and a single run split into pulls joined at a dug pit, so cross-sheet and pit-join
assembly are both exercised. Include a parallel second run (P14) to test the parallel-run
discriminator (two distinct bores, not one) without mixing them.

**R7 — Tolerance & noise (P10).** Inject sub-tolerance jitter (±1 ft H / ±0.5 ft V, ±2% locating) into
"as-built" variants so the engine's tolerance bands are tested to treat small deltas as agreement, and
super-tolerance deltas as a correction signal.

**R8 — Cross-check artifacts (P16).** Emit a scope tally / pay-item LF and a synthetic KMZ route length
that *agree* with summed segment lengths for the HIGH fixtures, and *disagree* beyond tolerance for the
LOW/correction fixtures, so the corroboration confidence inputs are exercised in both directions.

**R9 — Negative / ABSTAIN fixtures.** Generate plans that are *missing* one checklist element each
(no stations; named endpoint with no position reference; no bore-log span; ambiguous method) so the
engine's specific missing-evidence ABSTAIN messages are testable. Also generate an unrecognized-dialect
plan to confirm the deterministic engine still abstains cleanly (B1) and the evidence-based REVIEW lane
(B2) picks it up.

**R10 — Provenance & honesty invariants.** Synthetic fixtures are labelled SYNTHETIC and may only feed
the REVIEW/test lane; they must never produce AUTO/FINAL, never inject coordinates into the
deterministic frontier, and never touch fixtures/anchors used by the 50/58 recognized path.

---

## 5. Generic engine heuristics (name-free)

All heuristics are **REVIEW-tier priors / confidence signals / validators** — they never auto-place and
never override a banked human grade. Phrased name-free.

**H1 — Endpoints first, length as a check.** Parse a bore as `{start_anchor, end_anchor}` from named
located features (entry/exit pit, bore/receiving pit, Begin/End Station). Treat stated length / footage
/ pay-item LF as a *corroborating* check, never a free input (P2/P3b/P10). Prefer explicit Entry/Exit +
length over inferring endpoints from a drawn line.

**H2 — Multi-dialect stationing resolver.** Accept and normalize: engineering `NN+NN`; station distance
(exit−entry); milepost+feet (`MP n + ffff ft`); station+perpendicular-offset (`<dist>' <dir>/O CL`);
offset-from-a-named-permanent-feature; and **named-structure endpoints** (intersection/facility). Emit
the same internal `(begin, end, side/offset, method, length)` tuple regardless of dialect (P3, Iowa
schema).

**H3 — Crossed-feature is a separate frame.** When an endpoint carries a host-feature station (e.g. a
crossed-axis station) distinct from the bore-axis station, model them as two frames; the host feature is
crossed, not the bore's own axis (P4). Read crossing angle from a centerline angle callout.

**H4 — Method-and-diameter sanity gate.** Carry install method per segment (P5). Validate diameter ∈
method range and depth-of-cover ≈ the cover-by-diameter table (P7/P8); ≥30" reclassifies toward
tunnel/large-bore. A mismatch lowers confidence; it does not auto-correct geometry.

**H5 — Parametric profile prior.** Where a profile exists, model the bore as two endpoints + entry/exit
tangent angles + sag (min radius) + cover, in a vertical plane through the endpoints (P6). Use it to
sanity-check (not set) a plan-view candidate; a candidate violating the bend/approach-angle budget (P15)
is flagged.

**H6 — Tolerance-aware comparison.** Compare as-built vs designed (and candidate vs corroboration)
inside tolerance bands (~±1 ft H / ±0.5–1 ft V; 1"/10 ft line-and-grade). Sub-tolerance = agreement
(raise/keep confidence); super-tolerance = correction signal (lower confidence, flag) (P10).

**H7 — Structure-semantics endpoint identity.** Score endpoints by structure type: splice vault /
mid-sheath splice / spool-length demarcation = strong segment boundary; pull vault / hand hole =
continuity point; slack 100 ft ⇒ splice, 15 ft ⇒ pass-through (P12). Feed into the existing
endpoint-identity reasoning, never override a banked grade.

**H8 — Multi-leg assembly = chain joined at pits / match lines.** Decompose long runs into legs joined
at pits / relief pits / handhole banks / MATCH LINE STA "as if a continuous pull-in" (P11/P17). Use
end-continuity to decide same-run vs distinct parallel-run (P14) — corroborates the v2 through-continuity
/ parallel-run discriminator.

**H9 — Crossing vs longitudinal classifier.** Classify a candidate as a crossing (straight, ROW-to-ROW,
perpendicular ≥45°, crosses a feature) or a longitudinal run (parallel, consistent centerline offset);
apply the matching geometry prior (P14). A clean perpendicular crossing should sit near 90° at the
crossed centerline.

**H10 — Legend-driven attention.** Where a legend/symbol table or color-layer legend exists, parse it
first to map linetype+symbol → {method, structure} and color → {plan alignment / profile} (P13), then
route extraction accordingly.

**H11 — Independent quantity cross-check.** Reconcile summed segment lengths against any scope tally /
pay-item LF and KMZ route length (P16). Agreement raises confidence; disagreement beyond tolerance is a
correction signal. (KMZ corroborates length only; it never sets PDF pixel coordinates — per the WIP
KMZ-as-backbone invariant.)

**H12 — ABSTAIN = name the missing element.** When evidence is insufficient, emit the specific missing
checklist element + the next artifact that resolves it (Section 3 ABSTAIN list), per the v2
evidence-seeking doctrine — never a silent or generic abstain.

**Honesty guardrails on all heuristics:** no fake AUTO/FINAL/confidence; no invented coordinates (every
vertex derives from a real station label / anchor; extrapolation flagged + capped); no fake street names
(only KMZ/PDF-found names); no fake billing. These public patterns are PRIORS and TESTS, not
customer-specific placement truth.

---

## 6. Public-reference test cases — fixtures vs reference-only

### 6a. Usable as FIXTURES (public-record; extract generic conventions only; never reuse named parties or redistribute drawings)
| Source | Why fixture-grade | What it tests |
|---|---|---|
| #1 Caltrans Trenchless booklet | Enumerated HDD plan-set element list = the "what evidence is present" checklist; cover-by-diameter table; entry/exit + pit-offset rules | Checklist completeness, ABSTAIN-element naming, cover/diameter sanity gate (H4), pit-offset endpoint bounding |
| #7 Concord Fiber spec | Sanctions named-structure endpoints + bend budget + slack-discriminates-splice | Multi-dialect resolver (H2 named endpoints), bend budget (P15), splice-vs-pull (H7) |
| #8 LA BOE OSP plan set | Real legend (BORE/TRENCH/MICRO/HH/VAULT/PIT), STA tags, footage tics, offset-from-CL, scope tally | The canonical drawn target: legend parse (H10), STA-endpoint read (H1), method linetype (P5), quantity cross-check (H11) |
| #9 Iowa DOT fiber plan | Begin/End Station + Side + method pay-items + plan-and-profile color legend | Canonical segment tuple (H2), BORED/PLOWED method attribute (P5), color-legend attention (H10), pay-item cross-check (H11), multi-leg handhole banks (H8) |
| #15 CN crossing packet | CN's own GENERIC schematic Example Plan + Example Profile (placeholder labels, no real project) | Plan+profile pair (P1), milepost+feet dialect (H2), bore-pit/receiving-pit endpoints (H1), per-track crossing + angle (H3/H9), method→min-depth row (H4); closest thing to a synthetic test image |
| #18 Salina / #19 Nashville / #20 RTC / #21 Lakeland (municipal HDD specs) | Public specs giving concrete angles, 10-ft logging, tolerance bands, multi-pull-joined-at-pit, Bore Plan/Profile+Bore Data+As-Built triplet | Parametric profile (H5), 10-ft sampling (P9), tolerance bands (H6), multi-leg pit-join assembly (H8), evidence-triplet fusion |

> Fixture caveat: use these to validate *parse/structure/heuristic* logic and to seed SYNTHETIC test
> generators (Section 4). Do NOT treat any fetched drawing's geometry as a customer redline truth, and
> do NOT redistribute the source drawings. The municipal specs #18/#21 are a near-verbatim TEMPLATE
> FAMILY — treat as one pattern source, never reuse the city names as identifiers.

### 6b. REFERENCE-ONLY (legal to read/summarize; copyrighted, template-only, or no worked numeric example)
| Source | Why reference-only |
|---|---|
| #2 Caltrans GM Trenchless module | Method-by-diameter + boring-placement rules; reference rules, not a drawn plan |
| #3 Wisconsin DNR 1072 | Precise profile-content spec + station-distance definition, but a standard, not a drawn plan; figures not fetched |
| #4 TxDOT Item 476 | Terminology + line-and-grade tolerance + carrier/casing rules; no drawing |
| #5 Caltrans MMBN provisions | Placement RULESET + vault taxonomy; **© 2025 Caltrans — summarize, do NOT bulk-copy** |
| #6 Caltrans Bridge details guide | Conduit-bundle conventions; copyrighted; cross-section typicals not plan/profile |
| #10 FERC HDD Guidance | Entry/Exit/Total-Length table TEMPLATES (blank cells, no worked numbers) |
| #11 FERC Appendix G | Narrative contingency plan; defers geometry to a separate exhibit |
| #12 Lake Wales Directional Bore Standards | Concrete angles/cover/bore-log form, but standards text, not a filled plan sheet |
| #13 FDOT §555 | Station-or-permanent-feature + as-built (x,y)/depth/azimuth schema; spec, no drawing |
| #14 BNSF UAP | Dual-stationing exhibit is credited to **AREMA Fig 1-5-15 (paywalled)** — reproduce the generic PATTERN only, not the figure |
| #16 TxDOT Exhibit A page | Cross-vendor invariants (pits ≥30 ft, dry boring); plain-text reference |
| #17 UP pipeline procedure | Fixed-Object + crossing-vs-encroachment principle; AREMA paywalled, not fetched |

> Hard license notes carried forward: the two **Caltrans MMBN/bridge** docs (#5, #6) carry an explicit
> "© 2025 California DOT. All Rights Reserved." — public/published but copyrighted, **reference-only,
> summarize in our own words, do not bulk-copy**. The **BNSF/UP/AREMA** material (#14, #17) reproduces
> **AREMA** conventions; the AREMA manual itself is **copyrighted/paywalled and was NOT fetched or
> reproduced** — only the generic stationing/callout PATTERN is reused. FERC/FHWA-NHI/FDOT/Caltrans
> non-MMBN/TxDOT/Iowa/state-and-municipal docs are US government public-record works, legal to read and
> summarize; drawings are not redistributed and named parties are runtime data only.

---

## 7. Honesty & scope footer (hard rules restated)

- This corpus is **patterns and tests, not customer geometry**. Public HDD guidance ≠ redline placement
  truth for any TrueLine customer.
- Everything here feeds the **REVIEW / evidence-based (Tier B2) lane and the synthetic test generator** —
  **never AUTO/FINAL**, never the deterministic recognizer.
- **Untouched:** the deterministic 50/58 frontier, the renderer, fixtures / anchors / coordinates, the
  backend truth path, origin/main, and deploy. No engine/renderer/fixture/coordinate change is implied.
- No fake AUTO, no fake FINAL, no fake confidence, no fake map geometry, no fake street names, no
  invented coordinates, no fake billing, no hidden uncertainty. Every drawn vertex must derive from a
  real anchor; extrapolation is flagged and capped; ABSTAIN names its missing evidence.
