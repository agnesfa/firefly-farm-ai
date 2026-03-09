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

## farmOS — The Source of Truth

farmOS (margregen.farmos.net) is the central database for all farm data.
You have access to it via MCP tools (prefixed `mcp__farmos__`).

### Key MCP Tools

**Querying:**
- `query_plants(section_id, species, status)` — Find plant assets
- `query_sections(row)` — List sections with plant counts
- `get_plant_detail(plant_name)` — Full detail + all logs for a plant
- `query_logs(log_type, section_id, species)` — Search logs
- `get_inventory(section_id, species)` — Current plant counts
- `search_plant_types(query)` — Look up species in the taxonomy

**Writing (requires approval):**
- `create_observation(plant_name, count, notes, date)` — Log observation + update inventory
- `update_inventory(plant_name, new_count, notes)` — Reset a plant's count
- `create_plant(species, section_id, count, notes)` — Add new plant asset
- `create_activity(section_id, activity_type, notes)` — Log an activity

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
pending → reviewed (Claire confirms accuracy) → approved (Agnes imports to farmOS)
```

### How to Review

Use the `/review-observations` skill or ask to "review field observations".

The system will:
1. Fetch pending observations from the observation sheet
2. Group them by section and submission
3. Cross-reference with current farmOS data
4. Present a summary with flagged discrepancies
5. Let you confirm, modify, or reject each observation

### What to Look For

- **Count changes**: Did plants actually die or were they miscounted?
- **Species identification**: Is the observer using the correct plant name?
- **New plants**: Were new plants actually transplanted, or was it an error?
- **Missing plants**: In full inventory mode, unlisted plants may be dead
- **Strata accuracy**: Is the plant classified at the right height layer?

### After Review

Once you've reviewed and confirmed observations:
- Agnes will approve them in a separate session
- Approved observations get imported to farmOS (inventory updates, new assets, etc.)

---

## Common Questions Claire Might Ask

- "What's planted in P2R3.14-21?" → Use `query_plants(section_id="P2R3.14-21")`
- "How many pigeon peas do we have?" → Use `get_inventory(species="Pigeon Pea")`
- "Show me the recent logs for section P2R2.0-3" → Use `query_logs(section_id="P2R2.0-3")`
- "What species is this?" → Use `search_plant_types(query="...")`
- "What's in Row 3?" → Use `query_sections(row="P2R3")`
- "Review the field observations" → Use `/review-observations`

---

## Important Notes

- farmOS is always the source of truth. Observations are proposals until imported.
- Plant types must match the farmOS taxonomy exactly (219 species).
- Dead plants (count=0) stay in the system as records — they're not deleted.
- Some sections have gap areas with green manure only (no individual plants tracked).
- Photos from observations are saved in Google Drive, not in farmOS yet.
