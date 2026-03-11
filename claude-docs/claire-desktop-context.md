# Firefly Corner Farm — Claire's Project Context

> This is the shared project context for Claire's Claude Desktop.
> It provides farm knowledge, observation review workflow, and farmOS MCP access.

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

Each row has alternating **tree sections** (full strata: emergent → high → medium → low) and
**open cultivation sections** (no trees, annuals and vegetables).

### Section IDs

Format: `P{paddock}R{row}.{start}-{end}` — metres from row origin.
Example: `P2R3.15-21` means Paddock 2, Row 3, from 15m to 21m mark.

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
- Sub-type + variety: `Basil - Sweet (Classic)`, `Basil - Perennial (Thai)`

---

## Field Observation Review Workflow

Workers submit observations via QR code pages in the field.
Observations land in a Google Sheet and need to be reviewed before import to farmOS.

### Status Flow

```
pending → reviewed → imported
```

- **pending**: Worker submitted from the field (untouched)
- **reviewed**: You confirmed the observation is accurate
- **imported**: Data has been pushed to farmOS
- **rejected**: Observation was incorrect (wrong species, bad count, etc.)

### How to Review

Ask Claude to "show me pending observations" or "review today's observations".

Claude will:
1. Fetch pending observations using `list_observations(status="pending")`
2. Group them by section and submission
3. Cross-reference with current farmOS data using `get_inventory`
4. Present a summary with any flagged discrepancies
5. Let you confirm, modify, or reject each submission

### What to Look For

- **Count changes**: Did plants actually die or were they miscounted?
- **Species identification**: Is the observer using the correct plant name?
- **New plants**: Were new plants actually transplanted, or was it an error?
- **Missing plants**: In full inventory mode, unlisted plants may be dead
- **Strata accuracy**: Is the plant classified at the right height layer?

### After Review

Once you've reviewed observations, you can:
1. **Review**: `update_observation_status(submission_id, "reviewed", "Claire")`
2. **Import to farmOS**: `import_observations(submission_id, "Claire")` — this creates farmOS logs and updates inventory
3. **Reject**: `update_observation_status(submission_id, "rejected", "Claire", "reason")`

Use `dry_run=true` with `import_observations` to preview what will happen before committing.

---

## Common Tasks

- "What's planted in P2R3.15-21?" — shows all plants in that section
- "How many pigeon peas do we have?" — searches across all sections
- "Show me the recent logs for P2R2.0-3" — activity history for a section
- "What species is this?" — search the plant type taxonomy
- "What's in Row 3?" — overview of all sections in the row
- "Show me pending observations" — list unreviewed field submissions
- "Review observations for P2R3" — filter to a specific section
- "Import the reviewed observations" — push confirmed data to farmOS
- "Log that I planted 5 comfrey in P2R2.0-3" — create a new plant record
- "Update pigeon pea count in P2R3.15-21 to 3" — adjust inventory

---

## Important Notes

- farmOS is always the source of truth. Observations are proposals until imported.
- Plant types must match the farmOS taxonomy exactly (223 species).
- Dead plants (count=0) stay in the system as records — they're not deleted.
- Some sections have gap areas with green manure only (no individual plants tracked).
- Photos from observations are saved in Google Drive, not in farmOS yet.
- Always use `dry_run=true` first when importing, to preview the changes.
