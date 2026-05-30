# TrueLine — GAC Demo: What To Say / What Not To Say

> **The promise:** TrueLine only draws a redline when it can show its work. When it can't, it stays silent. That silence is a feature, not a gap — and it's the thing that earns trust on a real job.

---

## 1. What is proven (Brenham, today)

On the Brenham PH5 corpus — **58 bore logs** — the current production engine places **36 of 58 logs**:

- **36 logs placed** → **334 station points** across **286 redline segments**.
- **22 logs abstain** — deliberately *not* drawn, because the evidence didn't clear the bar.

**Lead with this:** the engine **abstains rather than guesses**. Every one of those 36 placements carries a proof record — which route it landed on and what evidence put it there. It is not "36 out of 58, the rest failed." It is "36 we can stand behind, 22 we refuse to fake."

The placement engine works from **KMZ geometry** plus a **calibrated Brenham print-to-sheet index** (sheets 1–30). For each placed log we can name the route and the evidence chain.

**Say this:** *"On this job, we place 36 of 58 bore logs, each with a traceable proof record. The other 22 we leave alone on purpose — the tool will not draw a line it can't defend."*

---

## 2. What PDF evidence did (the honest PDF story)

We added a second, independent evidence path: a **PDF route resolver** that reads the engineering plan itself — the sheet **"N OF M"** numbering and the **AP-#### tags** — and crosses those tags to the KMZ's **Terminal Port Handhole** nodes to derive the route. It does not trust the index; it reads the plan.

**What it proved — exactly two logs:**

- **bore_log71 and bore_log72 (LAWNDALE).** The hardcoded print index had **mis-transcribed sheets 23/24/25**, sending both logs to **route_478 (~1,021 ft away)**. The **PDF evidence corrected them onto route_477 (~94 ft)** — the right route.
- **bore_log72 is the headline case:** the geometry engine had marked its placement **"proven" — and it was wrong.** The PDF evidence **overrode a confident-but-incorrect result** and fixed it.

**State it precisely:** *"PDF evidence is validated on **2 logs**, including **1 the geometry engine got wrong and was sure about**."*

**Do not generalize past those two.** Two corrected logs is a real, demonstrable win — and it is also the entire validated record.

---

## 3. Why some logs abstain

Abstention is the integrity mechanism, and **bore_log39 (CHERI LN)** is the cleanest example.

CHERI LN **does not appear anywhere in the Brenham plan set.** The resolver could have force-placed it onto the LAWNDALE sheets its print tokens happen to point at — and it **refuses**. It returns "this street is absent from the plan set" and draws nothing.

**Frame it as integrity, not failure:** a tool that places a log onto the wrong street because some index pointed there is worse than useless on a live job — it produces a confident lie. TrueLine is built to **decline** in exactly that situation.

**Say this:** *"When a bore log's street isn't in the plans, we don't guess a nearby one — we abstain. CHERI Lane is the proof: the tool had a tempting wrong answer available and turned it down."*

---

## 4. What is NOT yet proven (do not claim)

- ❌ **Corpus-wide PDF authority.** PDF evidence is validated on **2 of 58 logs.** It stays gated to the validated slice.
- ❌ **"The PDF understands any plan set."** It reads a specific structure (sheet numbering + AP tags + handhole nodes). Not general plan comprehension.
- ❌ **Non-Brenham auto-placement.** The print index is **Brenham-calibrated.** On a different job it will not resolve out of the box.
- ❌ **Sub-foot route precision.** We say "~94 ft route vs. ~1,021 ft route" — right route vs. wrong route. We do **not** claim sub-foot accuracy.

> **Internal honesty check (don't show the owner, but know it):** across the corpus the PDF path **agrees** with the current placement on only **2 of 31** logs where it has an opinion, and would **flip 29** (28 unvalidated; 17 near-ties). That's why it stays gated. We have **ground truth on 2 of 58 logs** — and we will not market past it.

---

## 5. Why we need their sample data

- **The print index is Brenham-calibrated.** A GAC job needs **either** recalibration **or** the PDF path proven directly on **their** plans. Neither is done yet.
- **We can only measure accuracy against verified routes — and we have 2.** To honestly state an accuracy number on GAC's work we need ~**10–15 human-verified correct routes** as ground truth.
- **None of the Brenham paperwork counts as GAC validation.** Any MATSEL/Brenham documents are still *Brenham*. Generalization is **unproven until they give us their data.**

**Say this:** *"To tell you how well this does on **your** jobs, we need a sample: one or two plan sets plus 10–15 routes your team has already verified by hand. Give us that, and we'll show you measured numbers on your own work."*

---

## 6. The 60–90 second honest script

> *"Here's what TrueLine does today, on a real job — Brenham, 58 bore logs.*
>
> *It places 36 of them automatically, and every placement comes with a proof record: which route, and what evidence put it there. The other 22 it deliberately leaves alone — because the evidence wasn't strong enough, and this tool will not draw a line it can't defend.*
>
> *Let me show you the part I'm proudest of. On two of these logs — on Lawndale — the system's internal index was wrong. It would have placed them about a thousand feet off. But TrueLine also reads the engineering plan PDF directly, and the plan corrected it onto the right route, about ninety feet out. One of those two, the geometry engine was completely sure it had right — and it didn't. The plan caught it.*
>
> *Now I'll be straight with you. That PDF correction is proven on two logs. Two. It's real, and you just saw it — but I'm not going to tell you it understands every plan set, because I haven't proven that, and you'd catch me the first time it didn't.*
>
> *And here's the other side of the honesty: there's a bore log on Cheri Lane the tool refuses to place — because Cheri Lane isn't in the plans at all. It had a wrong answer available and turned it down. That's the behavior you want on your jobs.*
>
> *So this is my ask. The engine is tuned to Brenham right now. To show you real numbers on **your** work, I need a sample — a plan set or two, and ten to fifteen routes your crew has already verified. Then I come back with measured accuracy on your jobs, not somebody else's. That's the deal: I'll only ever tell you what I can prove."*

---

## 7. NEVER SAY (the trust-breakers)

- ❌ **"It places all 58 logs."** — It places **36**; 22 abstain by design.
- ❌ **"It's 100% accurate / never gets it wrong."** — The geometry engine was *confidently wrong* on bore_log72. We **show** that.
- ❌ **"The PDF reads and understands any engineering plan."** — Validated on **2 logs**, specific structure only.
- ❌ **"It works out of the box on your jobs."** — Index is **Brenham-calibrated**; non-Brenham is **unproven**.
- ❌ **"PDF evidence is the new source of truth across the board."** — Would flip **29 placements**, 28 unvalidated. Stays **gated to the 2 proven logs.**
- ❌ **"Accurate to within X feet/inches."** — We claim **right route vs. wrong route**, not sub-foot precision.
- ❌ **"We validated this against GAC / MATSEL data."** — That paperwork is **Brenham.** **Zero** GAC validation until they share data.
- ❌ **"22 logs failed."** — They **abstained.** Failure is a wrong line; abstaining is the safety feature.
- ❌ **Any specific accuracy percentage for GAC's jobs.** — Ground truth on **2 of 58 logs.** No hit rate is honest until their data is in.
