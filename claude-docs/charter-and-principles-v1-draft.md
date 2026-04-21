# Firefly Corner — Charter (L0) + Principles (L1) v1 DRAFT

- **Status:** v1 draft — Agnes to iterate solo before Claire review
- **Date:** 2026-04-21
- **Authors:** Agnes (primary), Claude (consolidator)
- **Sources:** 3 brainstorm docs with Claire (2025-10-27 workshop, 2025-11-06 meeting, undated brainstorming doc). Significant redundancy across the three — consolidated below.

This document establishes the top-level governance layers the ADRs sit beneath. ADRs resolve *how* we build; the Charter says *why we're building at all*; the Principles say *what we refuse to compromise on*.

---

## Consolidated themes from source brainstorms

Every theme below appeared in ≥2 of the 3 source documents.

### Vision themes
- **Climate-resilient, sustainable food system** — adapts to fast-evolving climate (Mediterranean ↔ subtropical mix, less rain than true subtropical).
- **Four-way autonomy** — food, water, energy, economic.
- **Contribution beyond the farm** — food-system resiliency + climate adaptation/mitigation as a public good.

### Approach themes
- **Scientific + evidence-based methodology** — structured observations, hypothesis-driven design, feedback analysis, course-correction.
- **Syntropic agroforestry as core philosophy** — Ernst Götsch, biodiversity as the primary input (Scott Hall), keyline water management (P. A. Yeomans), Aboriginal ecological knowledge, Bill Mollison permaculture, Claire's soil science foundation.
- **Connect with aligned communities** — academia, experts, other farmers, government entities. Not a closed system.
- **Knowledge as IP** — systematic documentation → intellectual property → credentials for Claire + teaching material + academic contribution.

### People themes
- **Agnes + Claire partnership** — AI/technology ↔ agricultural expertise synergy.
- **Claire's professional development** — independent consultant credentials grow out of farm work.
- **WWOOFer + volunteer integration** — 2-5 permanent WWOOFers as operational + teaching backbone.

### Operations themes
- **Two-year land goals:** Paddock 1 regenerated with year-round cultivation; Paddock 2 functioning syntropic system with alternating tree/bush zones.
- **Water:** complete P2 circuits, restore Dam 2 with keyline + creek integration, construct Dam 3 (swim-capable).
- **Campground:** fully operational for WWOOFers + Hipcamp paid listings when WWOOFers absent.
- **Data system:** full plant life-cycle tracking (seeding → planting → managing → harvesting); farmOS as source of truth; asset + log model.

### Business themes
- **Diverse revenue** — direct sales + nursery + workshops + campground — resilience through diversity, same principle as the ecosystem.
- **Minimise investment, maximise ROI on existing assets** — bootstrap mentality.
- **Feed ourselves first, then sell surplus** — sequencing priority.
- **Education as multiplier** — workshops are both revenue and teaching.

---

## Charter (L0) — v1 draft

### Why Firefly Corner exists

Firefly Corner is a 25-hectare regenerative farm near Krambach, NSW. We exist to prove that small-scale syntropic agroforestry, run as an evidence-based scientific practice, can produce food, water, and energy autonomy while contributing useful knowledge to the broader effort of climate adaptation.

We are not a hobby farm, a commercial monoculture, or a research station. We are a working farm that treats every planting decision as a hypothesis, every harvest as data, and every WWOOFer walk as observation — producing food, producing knowledge, producing the evidence base for how farms like this one can survive the next fifty years.

### What we build

- **A living system** on the land: syntropic rows in two paddocks, water infrastructure tying paddocks to dams, a nursery feeding the rows, a campground housing the people who work it.
- **A knowledge system** alongside it: structured observations → evidence → publications → intellectual property that underwrites Claire's consulting credentials and Agnes's systems work, and seeds other farms.
- **A community footprint**: WWOOFers pass through and take practice elsewhere; workshops bring paying learners; open publications reach farmers we'll never meet.

### Who we are

- **Agnes** — co-owner, CTO/architect. Builds the digital systems that capture the farm's evidence and make decisions legible.
- **Claire** — agronomist, scientific lead. Designs the syntropic rows, supervises plant-level decisions, owns the methodology.
- **James** — co-owner, infrastructure + marketing. Runs irrigation, machines, social presence.
- **Olivier** — compost + cooking + occasional systems user.
- **WWOOFers + volunteers** — rotating hands + eyes, the majority of per-day observational input.

### Two-year commitments

- **Paddock 1** regenerated, cultivated rows producing year-round vegetables.
- **Paddock 2** functioning syntropic system with all five tree rows + open cultivation zones active.
- **Water** circuits complete in P2; Dam 2 restored; Dam 3 constructed.
- **Campground** fully operational for 2–5 permanent WWOOFers with Hipcamp overlay.
- **Data system** — full plant life-cycle tracking live in farmOS; ≥3 plant families fully documented across life cycle with publishable traces.

### Why it matters

Every year the climate delivers a different growing season. Most farms will adapt by accident, incident, or failure. We are trying to adapt on purpose — observing carefully, publishing what works, saving the result for ourselves and anyone else building the same thing.

---

## Principles (L1) — v1 draft

Operating principles for every decision at Firefly Corner. If a choice violates one of these, pause and justify.

1. **Evidence beats assertion.** Every substantive decision is traced to an observation, a reference, or a recorded hypothesis. "We've always done it this way" is not a reason.

2. **Syntropic logic first.** Every planting, every row modification, every harvest is evaluated against its role in the stacked polyculture — succession, strata, consortium. If a choice wins short-term but breaks the system logic, the system wins.

3. **Document or it didn't happen.** Every field event lands in farmOS; every decision lands in an ADR or team memory; every durable insight lands in the knowledge base. If it's only in someone's head, it's lost.

4. **Autonomy over convenience.** Food, water, energy, and economic autonomy are the north stars. We will take slower, cheaper, more self-sufficient paths over faster, dependency-creating ones — even when the faster path looks attractive in the moment.

5. **Share what works, share what didn't.** Publications, blog posts, workshops, academic contributions. Negative results are knowledge too. We don't build a private empire of insight.

6. **Bootstrap.** Minimise new investment; maximise ROI on existing assets — the nursery, the infrastructure James built, the land itself. Buy nothing we can grow; grow nothing we can't maintain.

7. **Diversity for resilience.** Diverse species in rows, diverse revenue streams, diverse knowledge traditions (syntropic, permaculture, Aboriginal, soil science, keyline). Monoculture is fragile — in plants, in business, in ideas.

8. **Non-technical users are not second-class.** The people doing most of the farm work (Claire, James, WWOOFers, visitors) don't read code or git. The system must serve them directly through Claude + QR pages + spoken transcripts, not through paperwork or training overhead.

9. **Feed ourselves first.** Commercial output is the surplus. We don't sell food we need, grow plants we can't eat, or hollow the farm out for commercial optics.

10. **Technology serves agriculture — not the reverse.** AI and software exist to make the farming easier, the knowledge durable, the observations reliable. If a digital system starts shaping farm decisions for its own convenience, that's a bug.

11. **Scientific method applies to farm operations.** Plan from references → form hypothesis → act → observe → measure → adjust → publish. This is not academic; it is the daily operational loop.

12. **Protect the research thread.** Claire's work here needs to read as credentialable consulting experience to external eyes. That means rigor, traceability, and published outcomes — not just doing good work in private.

---

## What this document is *not*

- Not an ADR. Charter/Principles sit above ADRs; ADRs resolve specific decisions in light of these.
- Not a business plan. Business models appear in both source documents but need their own doc when we get there.
- Not a governance process doc. How we ratify things, who signs off, lifecycle — separate L2.
- Not final. v1 specifically means "Agnes iterates solo; Claire reviews later; both then publish as v2".

## Open iteration items for Agnes

These are places where my consolidation had to guess:

- **Tone of the Charter.** I leaned declarative + outward-facing (publishable). If you want something more inward-facing (just for the team), the same content shrinks 30%.
- **Whether Principles 10 and 11 collapse.** "Technology serves agriculture" and "Scientific method applies daily" are distinct but adjacent — one voice might merge them.
- **Principle 8's framing.** It's derived from your "no farm user is technical except me" constraint from today's session. If you want that more or less prominent, adjust.
- **Two-year commitments specificity.** Source docs didn't set numerical targets (e.g. "N kg of food produced" / "N species documented"). v2 after Claire review might add these.
- **Mission vs Vision split.** The current "Why we exist / What we build / Who we are / Two-year commitments / Why it matters" structure is fine but unorthodox. Agnes may prefer the classic Vision / Mission / Values layout.
