---
name: process-transcript
description: Process a WWOOFer or team member field walk audio transcript into structured farmOS observations. Resolves species against taxonomy, traces source origins, detects missing transplanting logs, cross-references against existing farmOS data, and creates observation logs with pending review tasks. Use when someone provides a voice transcript describing what they see in a paddock section.
argument-hint: [transcript text or "review" to check pending]
---

# Process Field Walk Transcript

You are processing an audio transcript from a field walk at Firefly Corner Farm.
The transcript describes plants observed in one or more paddock sections.
Your job is to turn speech into verified, structured farmOS data.

## Overview

A field walk transcript is raw, unstructured audio. The speaker names plants using
colloquial terms, gives approximate counts, and may not know section boundaries
precisely. Your job is to:

1. Parse the transcript into section-by-section observations
2. Resolve every species mention against the farmOS plant_type taxonomy
3. Cross-reference against current farmOS inventory for each section
4. Trace likely source origin for each plant (nursery transplant, seed, self-seeded)
5. Detect missing transplanting logs for tree species in unexpected locations
6. Create farmOS entries with appropriate confidence levels
7. Flag everything for human review

## Step 1: Parse Transcript into Sections

Listen for section boundary markers in the transcript:
- "paddock 2, row 5, 0 through 8" → P2R5.0-8
- "now I'm in section..." → new section starts
- "that brings us to the end of this section" → section ends

Build a list of `{section_id, raw_observations: [{species_term, count, notes}]}`.

Handle ambiguity:
- "a few" = ~3
- "lots of" = ~10+
- "some" = ~3-5
- Exact numbers when given: "3 wattles total" = 3

## Step 2: Entity Resolution — Resolve Species Against Taxonomy

For EACH species term the speaker uses, resolve to a `farmos_name`:

1. Call `search_plant_types(query="{term}")` to find matches
2. Apply these common mappings:
   - "wattle" / "waddle" → Wattle - Cootamundra (Baileyana) (most common on farm)
   - "mulberry" → Mulberry (White) (default variety)
   - "basil" → Basil - Perennial (Thai) (most common on farm)
   - "pumpkin" → Pumpkin (Generic, unless variety specified)
   - "parsley" → check section — could be Italian or Moss Curled
   - "eucalypt" / "eucalyptus" / "gum tree" → check section for specific species (Tallowood, Forest Red Gum, Rough Barked Apple)
   - "papaya" / "pawpaw" → Papaya
   - "potato" → likely Sweet Potato (regular potatoes not grown on this farm)
3. If the speaker says "I can't identify" — note physical description and check what species
   farmOS has in that section that the speaker might not recognize. Common misses:
   - "long narrow leaves" → likely Banagrass (Cenchrus purpureus, high strata pioneer)
   - "tree I don't know" → check emergent/high strata species in section: Tallowood, Prickly-leaved Paperbark, Rough Barked Apple
   - Pigeon Pea is frequently missed by new WWOOFers
4. If no match at all → log as "Unknown species" with physical description

Present entity resolution as a table:

```
| Transcript term | Resolved farmos_name | Confidence | Notes |
|-----------------|---------------------|------------|-------|
| "waddle" x3 | Wattle - Cootamundra (Baileyana) | HIGH | phonetic match |
| "long narrow leaves tree" | Banagrass | MEDIUM | matches description, needs field ID |
| "potato" | Sweet Potato | MEDIUM | regular potato not grown here |
```

## Step 3: Cross-Reference Against farmOS

For EACH section, call `farm_context(section="{section_id}")` to get the full picture:

- Current inventory (what farmOS thinks is there)
- Recent logs (when was this section last visited)
- Pending tasks (any open work items)
- Data integrity (any claimed changes that didn't land)

Then build a comparison table per section:

```
| Species | Transcript count | farmOS count | Delta | Action |
|---------|-----------------|--------------|-------|--------|
| Wattle  | 3               | 1            | +2    | UPDATE count |
| Pigeon Pea | not mentioned | 3           | ?     | FLAG for recount |
| Sunflower | 1             | not tracked  | NEW   | CREATE asset |
```

Categories:
- **CONSISTENT**: transcript count ≈ farmOS count → no action needed
- **UPDATE**: transcript count differs from farmOS → create observation with new count
- **NEW**: species in transcript not in farmOS → create plant asset
- **MISSING**: species in farmOS not mentioned in transcript → flag for recount (do NOT assume dead)
- **FLAG**: ambiguous or needs human verification

## Step 4: Source Origin Tracing

For each NEW species (not currently in farmOS for that section), determine likely origin:

**Self-seeded / volunteer:**
- Pumpkin, Sunflower, Sweet Potato, Basil — these spread aggressively via seeds, runners, or compost
- Look for the species in adjacent sections or same row
- Check team memory for recent seeding activities (winter garden mix, green manure)

**Nursery transplant (possibly unlogged):**
- Tree species (Mulberry, Jacaranda, Banagrass, Papaya, Eucalypt) do NOT self-seed to visible size in months
- Check nursery inventory for these species: `get_inventory(section_prefix="NURS")`
- Check team memory for transplant plans: `search_team_memory("{species} transplant")`
- If nursery stock exists and someone planned to transplant → **missing transplanting log**

**Direct seeding:**
- Okra, Radish, Lettuce — typically direct-seeded, not transplanted
- Check seed bank for these species
- Check team memory for seeding activities

**Unknown origin:**
- Species appears with no plausible source → flag for investigation

Present source analysis:

```
| Species | Origin | Evidence | Missing log? |
|---------|--------|----------|-------------|
| Pumpkin | Self-seeded | Compost/scattered seeds, Pumpkin in adjacent P2R5.14-22 | No |
| Mulberry | Nursery transplant? | Tree species, NURS has Mulberry stock | YES — possible |
| Okra | Direct seeding | EDEN Seeds source, established with fruit | YES — seeding log |
```

## Step 5: Create farmOS Entries

### For sections WITH existing farmOS data:

**Count updates** (transcript count ≠ farmOS):
```
create_observation(
  plant_name="{existing asset name}",
  count={transcript_count},
  notes="{Observer} field walk transcript {date}: counted {n} (farmOS had {m}). Pending {reviewer} verification."
)
```

**New species** in tracked sections:
```
create_plant(
  species="{farmos_name}",
  section_id="{section_id}",
  count={count},
  notes="{Observer} transcript {date}. {source_origin}. Pending {reviewer} verification."
)
```

### For GAP sections (farmOS has 0 plants):

**If the user says to wait for verified recount:** Create NO plant assets. Instead create a single
pending review task describing everything the observer saw.

**If the user says to create assets:** Create plant assets with today's date and notes indicating
source is transcript (approximate counts, pending verification).

### For ALL sections:

Create a pending review activity for the section owner (usually James):

```
create_activity(
  section_id="{section_id}",
  activity_type="review",
  status="pending",
  notes="JAMES — review {observer}'s transcript observations ({date}):
    1. {species}: {action needed}
    2. {species}: {action needed}
    ..."
)
```

## Step 6: Present Summary

Final output format:

```
## {Observer}'s Field Walk — Transcript Processing

**Observer:** {name} (WWOOFer/team member)
**Date:** {date}
**Sections walked:** {list}
**Method:** Audio transcript

### Section {id} — farmOS: {n} plants

| # | Transcript term | Resolved species | Count | farmOS | Delta | Source | Confidence |
|---|-----------------|-----------------|-------|--------|-------|--------|------------|
| 1 | ... | ... | ... | ... | ... | ... | HIGH/MEDIUM/LOW |

**Missing from transcript** (in farmOS but not mentioned): {species list}
**Systematic gaps found:** {e.g., "Sunflower has 0 assets in entire farmOS"}

### farmOS Actions Taken
- Created: {n} plant assets, {n} observation logs
- Updated: {n} inventory counts
- Pending review: {n} tasks for {reviewer}

### Open Questions for {reviewer}
1. {question}
2. {question}

### Knowledge Gaps Detected
- {Observer} couldn't identify: {species list} — needs species ID guide for this row
- Missing KB entries: {species without tutorials/SOPs}
```

## Important Rules

1. **NEVER assume a plant is dead** just because the observer didn't mention it. Low/ground species are routinely missed in walk-throughs. Flag as "recount needed", don't update to 0.

2. **Tree species in unexpected locations need investigation.** Trees don't self-seed to visible size in months. If a tree appears where farmOS has no record, either: the original planting was never registered, OR a nursery transplant was never logged. Both are data integrity issues.

3. **Pioneer species (Pigeon Pea, Wattle, Tagasaste) may legitimately be gone.** Check if winter prep (chop-and-drop) was done recently. Search team memory for the section.

4. **Always flag for human review.** Transcript observations are approximate. Create pending tasks for the section owner to verify every significant change.

5. **Use farm_context** for each section to get the full five-layer picture before making any farmOS changes. The data integrity gate will warn you if there are existing discrepancies.

6. **Phonetic variations are common:** "waddle" = wattle, "pawpaw" = papaya, "kumquat" = cumquat. Resolve patiently.

7. **Counts from transcripts are estimates.** When the speaker says "5 or 10 sunflowers", use the midpoint or lower bound and note the uncertainty.
