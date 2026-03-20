# James's Solo Operations Guide

> Agnes, Claire, and Olivier are away. You've got this.
> Claude is your co-pilot — just talk to it in plain English.

---

## 1. Daily Routine Checklist

### Morning

- [ ] **Water the nursery** — all shelves and ground areas, twice a day in warm weather. If nettle mulch on pots looks dry and pale, they definitely need water.
- [ ] **Walk the nursery** — look for wilting, pests, or anything unusual. Bird eye chilli pots: check for rat damage (cover if needed). Scan any shelf QR code to record observations directly on each plant card — just type what you see and hit Save.
- [ ] **Check transplant readiness** — nursery pages show which plants are ready to transplant (green "Ready" badge with dates). Prioritise these for field planting.
- [ ] **Check paddock rows** if time allows — scan for stressed plants, frost damage, or irrigation issues.

### During the Day

- [ ] **Record harvests** — scan the Harvest QR code at the scales in the nursery. Enter species, weight, and location.
- [ ] **Log anything notable** — plant deaths, pest sightings, weather events, irrigation issues. Just tell Claude.

### End of Day

- [ ] **Tell Claude what happened** — open Claude Desktop and say something like: *"Write a session summary. Today I watered the nursery, harvested 1.5kg tomatoes from P1R1, noticed yellow leaves on pigeon peas in P2R2."* Claude saves this so the team stays informed.

---

## 2. What Claude Can Do For You

Open Claude Desktop and type (or paste) any of these. Claude talks to farmOS for you.

### Nursery

| What you want | What to say |
|---|---|
| See what's on a shelf | *"What plants are on Shelf 1-1?"* |
| Check all nursery inventory | *"Show me nursery inventory"* |
| Care advice for a plant | *"The lemon cuttings on Shelf 3-1 — how should I care for them?"* |
| Log watering | *"I watered all the nursery shelves this morning"* |
| Report plant deaths | *"3 passionfruit seedlings died on Shelf 1-2"* |
| Report a new observation | *"The mint on Shelf 2-1 has white spots on the leaves"* |

### Paddock Rows

| What you want | What to say |
|---|---|
| See what's in a section | *"What's planted in P2R3.15-21?"* |
| Check a whole row | *"Give me an overview of P2R2"* |
| Log a harvest | *"I harvested 2kg of tomatoes from P1R1"* |
| Report a problem | *"The pigeon peas in P2R2.3-7 look stressed, yellow leaves"* |
| Log an activity | *"I did a round of weeding in P1R3 this morning"* |

### Knowledge and Tutorials

| What you want | What to say |
|---|---|
| How to do cuttings | *"How do I take cuttings?"* |
| Seedling separation technique | *"How do I separate seedlings into individual pots?"* |
| Nettle mulch technique | *"What's the nettle technique for nursery pots?"* |
| Browse all nursery knowledge | *"Show me everything about the nursery"* |
| Waste management for WWOOFers | *"What are the waste management instructions?"* |
| Find info on a specific plant | *"Tell me about comfrey — how to propagate it and where it's planted"* |

### Farm Overview

| What you want | What to say |
|---|---|
| Big picture status | *"Give me a farm overview"* |
| What the team has been doing | *"Show me recent team activity"* |
| Check submitted observations | *"Are there any pending observations?"* |
| Review and approve observations | *"List pending observations and let me review them"* |

---

## 3. QR Code Pages

Scan these with your phone camera — no login needed.

| QR Code | Where | What it does |
|---|---|---|
| **Paddock sections** (53) | On poles along each row | Shows what's planted, species details, plant counts |
| **Nursery zones** (18) | On nursery shelves/areas | Shows inventory per zone + inline observation fields per plant |
| **Seed Bank** (1) | On the fridge in nursery | Search seeds, record seed usage |
| **Harvest Station** (1) | Next to scales in nursery | Record harvest weight and species |

---

## 4. If Something Goes Wrong

| Problem | Solution |
|---|---|
| Claude isn't responding | Quit and reopen Claude Desktop |
| Tools timeout / error messages | Restart Claude Desktop — the remote server occasionally needs reconnection |
| Plant is dying, don't know what to do | Ask Claude — it has all of Olivier's nursery tutorials and care knowledge |
| Something is broken or urgent | Text/call Agnes — she can help remotely via Claude Code |
| WWOOFer asks something you can't answer | Ask Claude together — it knows the farm data, plant types, and procedures |

---

## 5. What NOT to Worry About

- **Data entry** — Claude handles all farmOS updates. Just tell it what happened in plain English.
- **Website/QR pages** — they update when Agnes runs the pipeline. No action needed from you. The index page at the farm guide URL shows all locations (Seed Bank, Nursery, Paddocks, Harvest) with collapsible drill-down.
- **Technical details** — you never need to know about APIs, scripts, or databases. Claude is the interface.
- **Getting it perfect** — logging approximate info is better than logging nothing. Claude can always be corrected later.
- **Pigeon pea deaths** — they're pioneers, designed to die and make way for other species. That's succession working, not a failure.

---

## 6. Nursery QR Pages — How Inline Observations Work

Each nursery zone page now has observation fields built into every plant card. No need to navigate to a separate page.

1. **Scan the QR code** on any nursery shelf or zone
2. **Enter your name** at the top (saved for next time)
3. For each plant, you'll see:
   - **"What do you see?"** — type any observation (health, pests, growth)
   - **"What did you do?"** — type any action taken (watered, pruned, moved)
   - **"Update count"** — tap to expand if the plant count changed (has a confirmation prompt)
   - **Save** — sends the observation to the team
4. **Transplant timing** — plants with known transplant windows show:
   - 🟢 **Ready** — transplant window has arrived
   - 🟡 **Window open** — in the transplant window now
   - ⏳ **Waiting** — not ready yet, shows expected date
5. **RTT badge** — shows how many plants are "Ready To Transplant" to the field

---

## Quick Reference: Nursery Golden Rules (from Olivier)

1. Water immediately after potting — every time
2. Straw on top of every pot — humidity, shade, microorganisms
3. Label every pot — species, source, date
4. Nodes in soil = roots, nodes above = stems and leaves
5. Never leave cuttings without water
6. Clean table between species — wet soil on leaves = disease
