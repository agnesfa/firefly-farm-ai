# Firefly Corner — Weekly Priorities (March 17–22, 2026)

> This document is for each team member's Claude to read alongside their role context file.
> It provides the concrete plan for this final week before Claire and Olivier's departure.

---

## The Deadline

**Claire and Olivier leave Saturday March 22.** Everything they know that isn't captured in farmOS or Team Memory is lost after that. This week is about extraction — getting knowledge out of their heads and into the system.

---

## Claire — Priority List

Claire's knowledge is the most critical asset at risk. Her Claude should help her work through this list in order.

### Priority 1: Review P1 Planting Data (Monday)

Agnes has analysed Claire's P1 spreadsheets and found data that needs clarification before it can be imported into farmOS. Claire needs to answer these questions — her Claude should walk her through them one by one:

**Species identification questions:**
1. **"Vince tomato" / "VINCE 2 12-13"** — What variety is this? Is "Vince" a person who provided seedlings? Or a variety name? (Appears in P1R1.9-19, P1R1.19-29, P1R3.3-13, P1R3.23-33)
2. **"ABBO" eggplant** — What does "ABBO 12-13" mean? Is this a nursery tray reference?
3. **"lemon-scented tea tree"** (P1R5.0-10 existing) — Is this Melaleuca alternifolia or Leptospermum petersonii?
4. **"Citrus seedling"** (P1R3.33-42) — Which citrus species?
5. **Marigold** — French Marigold or generic? The database has both.
6. **Lavender cutting** — French or True Lavender?

**Composite entries that need splitting:**
7. **"Tomatoes OXHEART + VINCE 2 12-13" = 21** — How many of each?
8. **"Tomatoes Rouge de Marmande + Money Maker" = 19** — How many of each?
9. **"Onions and chives" = 30** (P1R3.3-13) — How many onions, how many chives?
10. **"dill sweet basil" = 9** (P1R5.0-10) — How many dill, how many basil?
11. **"Basil sweet + Thai" = 1** (P1R3.3-13) — 1 of each or 1 total?

**Data quality questions:**
12. **P1R1.5-9** — Several plants listed with qty=0. Were these planned but not planted?
13. **P1R1.29-39** — Seed quantities missing (FFC beans, corn, etc.). Broadcast-seeded without measuring?
14. **P1R5 dead plants** — Calendula "all dead" in 3 sections. Should these still be imported as assets with count=0?
15. **P1ED1.0-5** — This drain-end section sits between P1R1.5-9 and P1R1.9-19. Should it be a separate farmOS land asset, or part of P1R1?
16. **Clover "red persian"** — Is Persian Clover (Trifolium resupinatum) a different species from Red Clover (T. pratense)?

**Claire's Claude should:**
- Walk through each question, record Claire's answer
- Use `add_plant_type` for any new species confirmed (Chilli Big Jim, Eggplant Long Purple, Bean Dwarf Borlotti, etc.)
- Write a session summary with all answers so Agnes can proceed with the import

### Priority 2: Nursery Inventory (Monday–Tuesday)

Claire knows what's in the nursery right now — seedlings ready for transplant, plants that need care, propagation in progress. This knowledge must be recorded before she leaves.

**Claire's Claude should help her:**
- Walk through each nursery zone (Shelf 1, Shelf 2, Ground, Propagation area)
- For each plant: species, quantity, readiness (ready to transplant / needs more time / needs care), destination (which paddock section)
- Use `create_plant` or `create_observation` to record in farmOS with location set to nursery
- Note any plants that are earmarked for specific sections

### Priority 3: Autumn Planting Plan (Tuesday–Wednesday)

Claire has a plan for what gets planted in P2 for autumn/winter 2026. This plan needs to be documented before she leaves.

**Claire's Claude should capture:**
- Which sections are getting new plantings and what species
- Green manure mixes planned for each section
- Timing (which month, what triggers planting)
- Reasoning — WHY these species in these locations (frost tolerance, nitrogen needs, soil conditions)
- Any species that need to be sourced (not in seed bank)

### Priority 4: Agronomic Knowledge Dump (Wednesday–Thursday)

The most irreplaceable knowledge Claire carries. Her Claude should interview her section by section:

- Which sections are doing well and why
- Which sections are struggling and why
- Irrigation notes (which sections need more/less water, seasonal changes)
- Soil observations (compaction, drainage, organic matter)
- Pest/disease patterns she's noticed
- Chop-and-drop timing — when to cut what and why
- Species combinations that work well together
- Species that have failed and shouldn't be replanted

Record as farmOS observations and activities with rich notes.

### Priority 5: Ongoing Field Logging (All Week)

Continue logging daily work — plantings, observations, any field activities. Every interaction is knowledge captured.

---

## James — Priority List

### Priority 1: Daily Team Activity Review (Every Morning)

```
read_team_activity(days=1)
```

Check what Claire and Olivier logged yesterday. Flag anything that looks incomplete, unclear, or needs follow-up. This is James's core review function.

### Priority 2: Knowledge Transfer Participation (All Week)

The handover week schedule:
- **Mon**: Farm walk P2 R1–R5 with Claire
- **Tue**: Nursery deep dive with Claire
- **Wed**: Compost systems with Olivier
- **Thu**: Row management — chop-and-drop with Claire
- **Fri**: Seed saving & autumn planting plan with Claire
- **Sat**: Hands-on practice day

**James's Claude should:**
- After each handover session, help James record what he learned
- Log activity observations in farmOS
- Write detailed session summaries capturing the procedural knowledge

### Priority 3: Operational Flow Documentation (Wednesday–Friday)

Using what he's learned from Claire and Olivier, James should document:
- **Seed bank management flow**: How to withdraw seeds, record it, track quantities
- **Nursery-to-field flow**: From sowing to transplanting, who does what when
- **Chop-and-drop protocol**: Which species, when, how to identify ready-to-chop
- **Compost management**: Turning schedule, temperature monitoring, application timing
- **WWOOFer day-one guide**: What a new arrival learns, what tools they use, what access they get

### Priority 4: Data Quality Review (Ongoing)

- Check recent field observations in the Sheet — are species names correct? Are counts plausible?
- Review any pending observations: `list_observations(status="pending")`
- Cross-check Claire's farmOS entries for completeness

---

## Olivier — Priority List

### Priority 1: Complete Seed Bank Inventory (Monday–Tuesday)

Finish counting all remaining seed packets. For each:
- Species name (check against taxonomy with `search_plant_types`)
- Quantity (grams if possible, stock level 0/0.5/1)
- Source (commercial supplier or FFC farm-saved)
- Condition (fresh, viable, degraded, expired)
- Any date on the packet (packed date, sow-by, harvest date)

Report findings to Claude after each shelf/section. Write session summaries.

### Priority 2: Compost Systems Documentation (Wednesday)

Record the current state of all compost bays:
- Which bays exist, their current stage (fresh, active, curing, finished)
- What inputs go where (kitchen scraps, chop-and-drop biomass, manure)
- Temperature observations
- Turning schedule and last turn dates
- What's ready to apply and where it should go

Log as farmOS activities with rich notes.

### Priority 3: Nursery Support (Thursday–Friday)

Support Claire's nursery inventory. Help with:
- Physical counts of seedlings on each shelf
- Watering and care routines that need to be documented
- Propagation techniques in use (what's being propagated, how, when started)

### Priority 4: Knowledge Transfer with James (All Week)

Participate in the handover sessions. When James asks questions about compost or seeds, provide detailed answers. Olivier's Claude should capture these interactions in session summaries.

---

## Agnes — Priority List (System Support)

### Monday
- Review Claire's P1 data answers (from her session summary)
- Add confirmed new plant types to CSV and farmOS
- Build P1 import pipeline (parse spreadsheets → farmOS)

### Tuesday–Wednesday
- Run P1 import into farmOS
- Regenerate P1 landing pages with actual plant data
- Ship Phase 1b remote MCP (Railway deployment) — critical for post-March 22

### Thursday–Friday
- Create nursery sections in farmOS (land assets for nursery zones)
- Import nursery inventory from Claire's session data
- Create Seed assets in farmOS from Olivier's inventory data
- Update QR pages if needed

### Saturday (March 22)
- Final farmOS export and page regeneration
- Verify all data is captured
- Confirm remote MCP works for James

---

## New Plant Types Needed

These need to be added to the plant type database. Claire should confirm strata and succession stage for each:

| Species | Strata (likely) | Succession | Notes |
|---------|----------------|------------|-------|
| Bean - Dwarf (Brown Beauty) | Low | Pioneer | New variety |
| Bean - Dwarf (Purple Beauty) | Low | Pioneer | New variety |
| Bean - Dwarf (Borlotti) | Low | Pioneer | New variety |
| Bean - Dwarf (Hawkesbury) | Low | Pioneer | New variety |
| Bean - Climbing (Blue Lake) | Low | Pioneer | New variety |
| Chilli (Big Jim) | Medium | Pioneer | New variety |
| Clover (Crimson) | Low | Pioneer | New variety |
| Okra (Royal Burgundy) | Medium | Pioneer | New variety |
| Eggplant (Long Purple) | Medium | Pioneer | New variety |
| Carrot (Baby Amsterdam) | Low | Pioneer | New variety |
| Carrot (All Year Round) | Low | Pioneer | New variety |
| Onion (Tropea Red) | Low | Pioneer | New variety |
| Tomato (Vince) | High | Pioneer | Needs Claire confirmation |

---

## Section Summary

| Who | Critical output this week | Risk if not done |
|-----|--------------------------|-----------------|
| **Claire** | P1 data review, nursery inventory, agronomic knowledge dump, autumn plan | Irreplaceable field knowledge lost |
| **James** | Daily reviews, handover participation, operational flows documented | Farm can't operate without expertise |
| **Olivier** | Seed bank complete, compost documented | Seed/compost data incomplete |
| **Agnes** | P1 import, remote MCP, nursery/seed farmOS setup | System can't support post-March 22 ops |

---

*Generated March 15, 2026. Updates will be reflected in Team Memory session summaries.*
