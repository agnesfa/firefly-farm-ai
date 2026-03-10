# Firefly Corner Farm — James's Project Context

> This is the shared project context for James's Claude Desktop.
> It provides farm overview, farmOS access, and observation review capabilities.

---

## About This Farm

**Firefly Corner Farm** is a 25-hectare regenerative agriculture property near Krambach, NSW.
The farm practices **syntropic agroforestry** — mimicking natural forest ecosystems through
strategic layering of plants. Two main cultivated paddocks with 5 syntropic rows each.

### Paddock 2 Layout

```
P2R1 — ~22m, 4 sections (short row, spring 2025 renovation)
P2R2 — ~46m, 7 sections (most actively managed)
P2R3 — ~63m, 7 sections (longest established row)
P2R4 — ~77m, 8 sections (spring 2025 plantings)
P2R5 — ~77m, 7 sections (newest, Kolala Day plantings)
```

### Section IDs

Format: `P{paddock}R{row}.{start}-{end}` — metres from row origin.
Example: `P2R3.14-21` means Paddock 2, Row 3, from 14m to 21m mark.

### Strata (Vertical Layers)

| Strata | Height | Examples |
|--------|--------|----------|
| Emergent | 20m+ | Forest Red Gum, Tallowood, Ice Cream Bean, Carob |
| High | 8–20m | Macadamia, Apple, Pigeon Pea, Mulberry, Tagasaste |
| Medium | 2–8m | Jaboticaba, Tea Tree, Lemon, Chilli, Eggplant |
| Low | 0–2m | Comfrey, Sweet Potato, Turmeric, Blueberry, Tansy |

---

## farmOS — The Source of Truth

farmOS (margregen.farmos.net) is the central database for all farm data.
You have access to it via MCP tools.

### Available Tools

**Farm Data:**
- `query_plants(section_id, species, status)` — Find plant assets
- `query_sections(row)` — List sections with plant counts
- `get_plant_detail(plant_name)` — Full detail + all logs for a plant
- `query_logs(log_type, section_id, species)` — Search logs
- `get_inventory(section_id, species)` — Current plant counts
- `search_plant_types(query)` — Look up species in the taxonomy

**Recording:**
- `create_observation(plant_name, count, notes, date)` — Log observation + update inventory
- `create_plant(species, section_id, count, notes)` — Add new plant asset
- `create_activity(section_id, activity_type, notes)` — Log an activity (watering, weeding, etc.)
- `update_inventory(plant_name, new_count, notes)` — Reset a plant's count

**Observation Management:**
- `list_observations(status, section, observer, date)` — List field observations from the Sheet
- `update_observation_status(submission_id, new_status, reviewer, notes)` — Mark as reviewed/approved/rejected
- `import_observations(submission_id, reviewer, dry_run)` — Import approved observations into farmOS

---

## Observation Review

Workers submit observations via QR code pages. Observations land in a Google Sheet.

### Quick Review Workflow

1. "Show me pending observations" — see what workers have submitted
2. Review each submission for accuracy
3. "Mark submission X as reviewed" — confirm it's correct
4. "Import submission X to farmOS" — push the data (use `dry_run=true` first)

### Status Flow

`pending` → `reviewed` → `imported` (or `rejected`)

---

## Common Tasks

**Farm Overview:**
- "Give me a summary of Row 3" — section-by-section overview
- "How many species do we have across the farm?" — diversity stats
- "What's the current state of P2R2?" — all sections in a row
- "Show me all macadamia trees" — find a species across sections

**Reporting:**
- "What was planted this month?" — recent transplanting logs
- "Which sections have the most plant losses?" — declining counts
- "List all the fruit trees we have" — species by function
- "Show me the observation history for P2R3.14-21" — log timeline

**Recording:**
- "Log that we watered Row 2 today" — activity log
- "I planted 3 new comfrey in P2R2.0-3" — new plant record
- "Review today's field observations" — review workflow

---

## Important Notes

- farmOS is always the source of truth. Observations are proposals until imported.
- Plant types must match the farmOS taxonomy exactly (223 species).
- Dead plants (count=0) stay in the system as records — they're not deleted.
- Use `dry_run=true` with `import_observations` to preview before committing.
