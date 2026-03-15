# Firefly Corner — Farm Intelligence Team Briefing

> Read this document to understand how we work together, what the system does,
> and how your interactions with Claude make the farm smarter every day.

---

## Quick Definitions

**A session** is simply a Claude conversation — it starts when you open the chat and ends when you close it. Each conversation is one session.

**QR code scans are separate** — they bypass Claude entirely and submit observations straight to the Google Sheet. You don't need to be in a Claude session to use them.

---

## What We've Built

Every person at Firefly Corner now has their own Claude — an AI assistant connected to farmOS (our farm database) and to each other through a shared memory system.

When you tell your Claude something — "I planted 5 tagasaste in P2R3 today" or "the pigeon peas in Row 2 look frost-damaged" — it doesn't just listen. It records that knowledge in farmOS, where it becomes part of the farm's permanent intelligence. And through the Team Memory, everyone else's Claude can see what you did.

**The system has three layers:**

1. **farmOS** — the source of truth. Every plant, every observation, every activity is recorded here. Your Claude reads from and writes to farmOS on your behalf.

2. **Observation Sheet** — field workers submit observations via QR code pages on section poles. These land in a Google Sheet for review before being imported to farmOS.

3. **Team Memory** — a shared log where each person's Claude writes session summaries. This is how the team stays in sync without meetings.

---

## The Knowledge Loop

This is the core idea: every interaction with the farm and with Claude makes the system smarter.

```
You work in the field / nursery / seed bank
        ↓
You tell Claude what happened (or scan a QR code)
        ↓
Claude records it in farmOS + writes a session summary
        ↓
Other team members' Claudes can read what you did
        ↓
The farm intelligence grows — better decisions next time
        ↓
You benefit from what everyone else has recorded
```

**The more you tell Claude, the smarter the farm gets.** Not just WHAT happened, but WHY. "I planted tagasaste here because the soil needs nitrogen" is far more valuable than just "I planted tagasaste."

---

## How to Work With Your Claude

### Talk naturally

You don't need special commands. Just tell Claude what you did, what you see, or what you need:

- "I planted 12 tagasaste in P2R3.9-14 today as nitrogen fixers"
- "The pigeon peas in P2R2.3-7 — 3 have died, probably frost"
- "What's planted in Row 3?"
- "Show me what the team has been doing this week"
- "I counted the basil seeds — about 50g left, packet from Eden Seeds 2024"

### Include the WHY

Claude captures what you say in farmOS notes. The reasoning is gold:
- "Chose tagasaste over pigeon pea because it handles frost better" → future decision-making
- "This section gets waterlogged in winter" → infrastructure knowledge
- "Seeds look degraded, low germination expected" → quality intelligence

### Session summaries — the closing ritual

Before you close a Claude conversation, ask Claude to save a summary. Just say:

> "Write a session summary of what we did."

Claude will save it and confirm with a message like "Session summary written successfully." **That's it — you're done.** If you're unsure whether it worked, just ask: "Did that get saved?"

If you close the conversation without writing a summary, that session's knowledge is lost to the team. Make it a habit: **summary before closing.**

The summary captures:
- **Topics** — what you worked on
- **Decisions** — choices made and why
- **farmOS changes** — what was recorded
- **Questions** — anything unresolved or needing attention

### Check what others did

You can ask:
- "What has the team been working on?" → shows recent summaries from everyone
- "What did Claire do yesterday?" → filtered to one person
- "Search team memory for seed bank" → find past decisions on a topic

---

## The QR Code System

Every section pole in Paddock 2 has a QR code. Scanning it shows:
- **What's planted** — species, counts, strata, botanical names
- **Record observation** button — submit field observations

**Anyone can use the QR pages** — no login needed. Observations go to the Google Sheet for review. Claire reviews them for accuracy, then they get imported to farmOS.

---

## What's Happening Now (March 2026)

Three parallel tracks running simultaneously:

### 1. P2 Autumn Planting (Claire leads)
New trees and green manure mixes going into Paddock 2 for autumn/winter. Claire uses QR observe pages and Claude to record everything. New species get added to the plant type database as needed.

### 2. Seed Bank Inventory (Olivier leads)
Complete count of all seed packets — species, quantities, conditions, sources. This data will become farmOS Seed assets, enabling the full seed-to-field lifecycle tracking.

### 3. Operational Flow Design (James leads)
James reviews what Claire and Olivier are doing and designs repeatable workflows. The goal: when new WWOOFers arrive after March 22, they can follow these flows without expert guidance.

---

## The Roles

### Agnes — The Architect

Agnes designs and builds the technical system. She works with Claude Code (the developer tool) to build scripts, MCP servers, and data pipelines. She doesn't work in the field — she makes sure the system captures what everyone else does.

**Agnes's Claude** (Claude Code) orchestrates the other Claudes' understanding. When your Claude flags a question or a missing feature in a session summary, Agnes's Claude reads it and Agnes builds what's needed.

**How to signal Agnes:** When something doesn't work, is missing, or could be better — tell your Claude. It goes into the session summary's "questions" field. Agnes will see it and act on it. You don't need to track her down.

### Claire — The Field Expert

Claire is the farm's agronomic brain. She knows which species work together, what the soil needs, which plants are struggling and why. She designs the syntropic rows and manages planting campaigns.

**Claire's mission with Claude:** Capture field knowledge. Every observation, every planting decision, every piece of expertise that lives in her head — get it into the system. After March 22, this knowledge needs to be accessible to whoever is managing the farm.

**What Claire does:**
- Records plantings and observations via QR pages and Claude chat
- Adds new plant types when she introduces species
- Reviews field observations from the Google Sheet
- Shares agronomic reasoning with her Claude (the WHY behind decisions)

### James — The Knowledge Crystallizer

James owns the farm's continuity. He's responsible for making sure the systems work for everyone — especially WWOOFers who arrive knowing nothing about this specific farm.

**James's mission with Claude:** Design operational flows. Take what Claire and Olivier produce and ask: "How does a new person follow this? What instructions do they need? What could go wrong?" James's Claude helps him read team activity, review data quality, and document workflows.

**What James does:**
- Reads team memory daily — stays informed about what Claire and Olivier are doing
- Designs the seed bank → nursery → paddock operational flow
- Reviews observation data quality (are species names correct? are counts plausible?)
- Documents decisions and workflows that need to survive after March 22
- Thinks about WWOOFer onboarding and autonomy

### Olivier — The Practical Reporter

Olivier handles compost, cooking, and is currently leading the seed bank inventory. His role is hands-on and precise.

**Olivier's mission with Claude:** Record accurately and report clearly. Every seed packet counted, every compost bay monitored — structured data that James can review and design workflows around.

**What Olivier does:**
- Counts and records seed bank inventory (species, quantities, conditions, sources)
- Logs compost activities (turning, temperature, maturity)
- Supports Claire in the field and nursery as directed
- Writes session summaries so James knows what was counted/done

---

## Key Concepts (Quick Reference)

### Section IDs
Format: `P2R3.15-21` = Paddock 2, Row 3, from 15m to 21m mark.

### Plant Strata (height layers)
- **Emergent** (20m+): Forest Red Gum, Tallowood, Ice Cream Bean
- **High** (8-20m): Macadamia, Apple, Pigeon Pea, Tagasaste
- **Medium** (2-8m): Jaboticaba, Tea Tree, Lemon, Chilli
- **Low** (0-2m): Comfrey, Sweet Potato, Turmeric, Yarrow

### Succession (lifecycle role)
- **Pioneer** (0-5yr): Fast growth, nitrogen fixing, biomass — designed to die and make way. Pigeon pea losses are EXPECTED.
- **Secondary** (3-15yr): Fill canopy as pioneers decline
- **Climax** (15+yr): Permanent forest structure

### Important rules
- farmOS is always the source of truth
- Include the WHY, not just the WHAT
- Dead plants stay as records — never deleted
- When unsure about species names, ask Claude to search the taxonomy
- When unsure about agronomic decisions, Claire decides
- When unsure about workflow design, James decides
- When something technical doesn't work, flag it for Agnes

---

## The March 22 Deadline

Claire and Olivier leave on March 22. Everything they know about this farm needs to be captured before then — in farmOS, in the Team Memory, and in the workflows James designs. Every session summary, every observation, every piece of reasoning matters.

This isn't about creating perfect documentation. It's about making sure the farm intelligence has enough knowledge that James (with new WWOOFers and Claude) can keep the farm's operations running and growing.

**The farm intelligence is only as good as what you feed it. Feed it well.**
