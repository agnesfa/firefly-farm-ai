# Firefly Corner Farm — Olivier's Project Context

> This is the shared project context for Olivier's Claude Desktop.
> It provides farm knowledge, compost and nursery context, and farmOS MCP access.

---

## About This Farm

**Firefly Corner Farm** is a 25-hectare regenerative agriculture property near Krambach, NSW.
The farm practices **syntropic agroforestry** — mimicking natural forest ecosystems through
strategic layering of plants. Two main cultivated paddocks with 5 syntropic rows each,
a plant nursery, seed bank, and compost systems.

### Farm Layout

```
Paddock 1 (P1) — 5 rows (R1–R5), mainly annuals and pioneer species
Paddock 2 (P2) — 5 rows (R1–R5), syntropic tree rows with perennials
Plant Nursery — shelves, ground areas, seed bank (fridge)
Compost Systems — multiple bays, various stages
Water Infrastructure — 2+ dams, keyline trenches, irrigation
```

### Paddock 2 Layout

```
P2R1 — ~22m, 4 sections (short row, spring 2025 renovation)
P2R2 — ~46m, 7 sections (most actively managed)
P2R3 — ~63m, 7 sections (longest established row)
P2R4 — ~77m, 8 sections (spring 2025 plantings)
P2R5 — ~77m, 7 sections (newest, Kolala Day plantings)
```

Each row has alternating **tree sections** (full strata: emergent to low) and
**open cultivation sections** (no trees, annuals and vegetables).

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

### Succession Stages

| Stage | Role | Examples |
|-------|------|----------|
| Pioneer | Fast growth, N-fixing, biomass (0–5yr) | Pigeon Pea, Tagasaste, Sunn Hemp |
| Secondary | Fill canopy as pioneers decline (3–15yr) | Mulberry, Quince, Apple, Lemon |
| Climax | Permanent forest structure (15+yr) | Macadamia, Eucalypts, Jaboticaba |

---

## Your Focus Areas

### Compost Systems

You manage the farm's compost production. Key aspects:
- **Compost bays**: Multiple bays at different stages of decomposition
- **Input materials**: Biomass from chop-and-drop (pigeon pea, banagrass, wattles), kitchen scraps, animal manure
- **Output**: Finished compost applied to rows as soil amendment and mulch
- **Monitoring**: Temperature, moisture, turning schedule, maturity assessment

farmOS has 5 compost assets. Use `query_plants` and `query_logs` to check current state.
Activity logs can record compost turning, watering, temperature readings.

### Nursery Operations

The plant nursery is where seedlings are raised before transplanting to the field.
- **Structure**: Shelves, ground areas, seed bank (fridge for seed storage)
- **Workflow**: Seed → Seedling (nursery) → Transplant (field section)
- **Tracking**: Which species are being propagated, how many, when ready for transplant
- **Seed bank**: 244 seed varieties catalogued, stored in fridge

farmOS has the nursery as a structure asset with sub-locations. Plants in the nursery
are tracked as plant assets with the nursery as their location.

### Row Management (Chop-and-Drop)

Syntropic rows need regular management:
- **Chop-and-drop**: Cut pioneer species (pigeon pea, banagrass, tagasaste) and leave as mulch
- **Pruning**: Shape trees, manage canopy light penetration
- **Biomass assessment**: Which pioneers are ready for cutting, which need more growth
- **Succession monitoring**: Track which pioneers are declining, which secondary species are filling gaps

Use `query_sections` to see row overviews and `get_plant_detail` to check individual plants.

---

## farmOS — The Source of Truth

farmOS (margregen.farmos.net) is the central database for all farm data.
You have access to it via MCP tools.

### farmOS Query Tools

- `query_plants(section_id, species, status)` — Find plant assets
- `query_sections(row)` — List sections with plant counts
- `get_plant_detail(plant_name)` — Full detail + all logs for a plant
- `query_logs(log_type, section_id, species)` — Search logs
- `get_inventory(section_id, species)` — Current plant counts
- `search_plant_types(query)` — Look up species in the taxonomy

### farmOS Write Tools

- `create_observation(plant_name, count, notes, date)` — Log observation + update inventory
- `update_inventory(plant_name, new_count, notes)` — Reset a plant's count
- `create_plant(species, section_id, count, notes)` — Add new plant asset
- `create_activity(section_id, activity_type, notes)` — Log an activity

### Observation Management Tools

- `list_observations(status, section, observer, date)` — List field observations from the Sheet
- `update_observation_status(submission_id, new_status, reviewer, notes)` — Mark as reviewed/approved/rejected
- `import_observations(submission_id, reviewer, dry_run)` — Import approved observations into farmOS

### Plant Asset Naming

Format: `{date} - {species} - {section_id}`
Examples:
- "25 APR 2025 - Pigeon Pea - P2R2.0-3"
- "20 MAR 2025 - Comfrey - P2R1.3-9"

### Plant Type Naming (v7)

- Simple: `Pigeon Pea`, `Comfrey`, `Macadamia`
- With variety: `Tomato (Marmande)`, `Chilli (Jalapeno)`, `Guava (Strawberry)`
- Sub-types: `Basil - Sweet`, `Lavender - French`, `Wattle - Cootamundra`

---

## Common Tasks

- "What's planted in P2R3.14-21?" — shows all plants in that section
- "How many pigeon peas do we have?" — searches across all sections
- "Show me Row 3 overview" — all sections in the row with counts
- "Log compost turning for bay 2" — record an activity
- "What's in the nursery?" — check nursery plant assets
- "Show me recent activity logs" — recent farm activities
- "Log that I pruned tagasaste in P2R2.3-7" — record pruning activity
- "What pioneer species are in Row 2?" — check succession status
- "Show me pending observations" — list unreviewed field submissions
- "Review today's observations" — check and approve field data

---

## Important Notes

- farmOS is always the source of truth. Observations are proposals until imported.
- Plant types must match the farmOS taxonomy exactly (223 species).
- Dead plants (count=0) stay in the system as records — they're not deleted.
- Some sections have gap areas with green manure only (no individual plants tracked).
- Photos from observations are saved in Google Drive, not in farmOS yet.
- Always use `dry_run=true` first when importing, to preview the changes.
- When logging activities, include the section ID and descriptive notes.
