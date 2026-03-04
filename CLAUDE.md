# CLAUDE.md — Firefly Corner Farm AI System

> This is the complete project context for Claude Code. Read this file on every session.
> It contains everything you need to work effectively on this project: the farm, the people,
> the architecture decisions, the domain knowledge, the current state, and the conventions.

---

## 1. THE FARM

### Identity

**Firefly Corner Farm** is a 25-hectare regenerative agriculture property near **Krambach, NSW** on Australia's Mid North Coast. The farm practices **syntropic agroforestry** — a Brazilian-originated approach that mimics natural forest ecosystems through strategic layering of plants. The goal is building a productive food forest that regenerates degraded land while producing diverse harvests.

The farm is at an early stage (planted from April 2025). It has two main cultivated paddocks with multiple syntropic rows, a plant nursery, seed bank, water infrastructure (dams, keyline trenches), and camping facilities for volunteers and visitors.

### Physical Layout

```
Farm (~25 hectares)
├── Paddock 1 (P1) — 5 cultivated rows (R1–R5), mainly annuals and pioneer species
├── Paddock 2 (P2) — 5 cultivated rows (R1–R5), syntropic tree rows with perennials
│   ├── P2R1 — ~22m, under renovation
│   ├── P2R2 — ~46m, 7 sections (0-3, 3-7, 7-16, 16-23, 23-26, 28-37, 37-46)
│   ├── P2R3 — ~63m, 7 sections (0-3, 3-9, 9-14, 14-21, 21-26, 26-37, 41-63)
│   ├── P2R4 — ~44m
│   └── P2R5 — being established
├── Plant Nursery — shelves, ground areas, seed bank (fridge)
├── Water Infrastructure — 2+ dams, keyline trenches, irrigation
├── Campground — 3 registered Hipcamp sites for guests
└── Common areas, infrastructure, bush
```

### Climate & Conditions

- **Climate:** Subtropical with Mediterranean, hot temperate, and humid influences. Can experience frost.
- **Soil:** Clay soil, being regenerated through organic matter addition and syntropic practices
- **Rainfall:** Moderate, supplemented by dam/keyline water management
- **Challenges:** Drought periods, clay compaction, frost risk, pest pressure from adjacent cleared land

### Online Presence

- **farmOS instance:** https://margregen.farmos.net/
- **WWOOF profile:** https://wwoof.com.au/members/fireflycorner/
- **Hipcamp listing:** https://www.hipcamp.com/en-AU/land/new-south-wales-firefly-corner-88lhv5p7
- **GitHub repo:** firefly-farm-ai (this repository)

---

## 2. THE PEOPLE

### Agnes — CTO & Architect (you work with her directly in Claude Code)

Agnes is the technical co-owner. She designs and builds the digital systems. Her background is in technology and she's the bridge between the farm's operational needs and the AI/software solutions. She works with Claude Code for development, Claude.ai for strategic thinking, and manages the GitHub repo. She has strong opinions about architecture and wants things built right, not hacked together.

**What Agnes cares about:** Long-term foundations, commercialisation potential, data-driven decisions, IP creation, enabling Claire and James without requiring them to be technical.

### Claire — Agronomist & Field Operations

Claire is the farming expert. She designs the syntropic rows, decides what to plant where, manages volunteers, and does hands-on field work daily. She currently tracks everything in **Excel spreadsheets** — inventory counts, planting records, renovation plans. Her spreadsheets are the *actual operational system* of the farm today.

**Claire's spreadsheet format (critical to understand):**
Each spreadsheet covers one paddock row. Tabs are named by section (e.g., "P2R3.0-3", "P2R3.3-9"). Each tab has:
- Row 1: Section identifier (e.g., "P2 — R3 — Section 0-3")
- Row 2: Metadata (length, WITH/NO TREES, first planted date)
- Row 4: Column headers (Strata | Species | Notes | Planted | Inventory date | TODAY | New Plants | New Seeds | TOTAL NEW | Comments)
- Row 5+: Plant data grouped by strata (Emergent → High → Medium → Low)
- Column E (Inventory): Last counted number of plants
- Column F (TODAY): Field for new count during walk
- Column G (New Plants): Transplants added
- Column H (New Seeds): Seeds sown
- Column J (Comments): Field observations

The "farmOS Log Mapping" tab in each spreadsheet documents how columns map to farmOS log types.

**What Claire cares about:** Practical tools that work in the field, accurate plant data, volunteer management, harvest tracking, and seeing her farm knowledge properly documented.

### James — Co-owner, Infrastructure & Marketing

James handles physical infrastructure (irrigation, machines, fencing), marketing, social media, and investor relations. He's a former marketing executive. He uses Claude.ai for content creation, reports, and farm storytelling.

**What James cares about:** Farm story, brand, revenue streams, investor pitches, making the farm's work visible to the outside world.

### Olivier — Compost & Cooking

Handles compost production and cooking for the farm. Occasional system user.

### WWOOFers (Farmhands/Workers)

Volunteers who stay on the farm through the WWOOF programme (Willing Workers on Organic Farms). They take instructions from Claire, execute field tasks, and report back. Currently use Claire's spreadsheets. They do NOT have farmOS accounts. In the future, they'll interact via QR code landing pages or simple Claude chat interfaces.

### Visitors

Landcare group members, Hipcamp camping guests, farm tour participants. They access public content only. No farmOS accounts, no Claude accounts. They experience the farm through QR code landing pages on row section poles.

---

## 3. THE THREE ROLES (Access Model)

| Role | Who | Access | Interface |
|------|-----|--------|-----------|
| **Manager** | Agnes, Claire, James | Full farmOS, Claude, GitHub | Claude.ai, Claude Code (Agnes), farmOS UI |
| **Farmhand** | WWOOFers, helpers | Task lists, observation logging, plant DB queries | QR pages, potentially simplified Claude chat |
| **Visitor** | Landcare, Hipcamp, tours | Public content only | QR code landing pages (static, no auth) |

---

## 4. SYNTROPIC AGRICULTURE — Domain Knowledge

This section is essential for understanding WHAT the farm does and WHY the data is structured the way it is.

### Core Concept

Syntropic agroforestry (developed by Ernst Götsch in Brazil) builds productive ecosystems by mimicking natural forest succession. Instead of clearing land for monocultures, you plant **stacked polycultures** where every species has a role. The system evolves over time through **succession stages**, with fast pioneer species building soil for long-lived climax species.

Key principle: **Every plant serves the system.** Nothing is planted for a single purpose. A pigeon pea fixes nitrogen, produces edible seeds, creates biomass for mulching, provides shade for understory seedlings, and when it dies, its root channels become pathways for water and successor roots.

### Strata (Vertical Layers)

Plants are classified by their mature height into canopy layers. A healthy syntropic row has all layers filled:

| Strata | Height | Role | Examples at Firefly Corner |
|--------|--------|------|---------------------------|
| **Emergent** | 20m+ | Permanent canopy, wind protection, wildlife habitat | Forest Red Gum, Tallowood, Carob, Ice Cream Bean |
| **High** | 8–20m | Main production canopy, fruit/nut trees | Macadamia, Apple, Mulberry, Pigeon Pea, Quince |
| **Medium** | 2–8m | Understorey production, citrus, coffee | Jaboticaba, Tea Tree, Lemon, Chilli, Capsicum |
| **Low** | 0–2m | Groundcover, herbs, root crops, soil protection | Comfrey, Sweet Potato, Turmeric, Garlic, Yarrow |

### Succession Stages (Temporal)

Plants are classified by their role in the system's evolution over time:

| Stage | Lifespan | Role | Examples |
|-------|----------|------|----------|
| **Pioneer** | 0–5 years | Fast growth, soil building, nitrogen fixation, biomass | Pigeon Pea, Tagasaste, Banagrass, Cootamundra Wattle, Sunn Hemp |
| **Secondary** | 3–15 years | Fill canopy as pioneers decline, main production | Mulberry, Quince, Apple, Lemon, Tea Tree |
| **Climax** | 15+ years | Permanent forest structure, long-term value | Macadamia, Eucalypts, Jaboticaba, Longan, Carob |

### Plant Functions

Every plant is tagged with its ecosystem roles. Standard function tags used across the project:

`nitrogen_fixer` `biomass_producer` `nutrient_accumulator` `edible_fruit` `edible_nut` `edible_greens` `edible_root` `edible_seed` `aromatic` `medicinal` `timber` `fodder` `living_mulch` `pest_management` `beneficial_insects` `erosion_control` `windbreak` `nectar_source` `native_habitat` `companion_plant` `green_manure` `oil_production`

### Row Design Pattern

Each cultivated row alternates between **tree sections** (with full strata from emergent to low) and **open cultivation sections** (no trees, used for annuals and vegetables that need full sun). This creates diverse microclimates along a single row:

```
Row profile:
[🌳 Tree 3m][☀️ Open 4m][🌳 Tree 9m][☀️ Open 7m][🌳 Tree 3m][🌳 Tree 9m]...
```

Tree sections: Full syntropic stacking. Emergent eucalypts, high canopy fruit trees, medium understorey, low groundcover.
Open sections: No emergent/high trees. Mainly medium and low strata — vegetables, herbs, annual crops.

### Key Management Practices

- **Chop-and-drop:** Cut pioneer species (pigeon pea, banagrass, wattles) and leave biomass as mulch. This feeds the soil and suppresses weeds.
- **Succession management:** As pioneer species die (they're meant to), secondary species fill their space. The system evolves.
- **Consortium design:** Groups of species planted together that support each other — nitrogen fixers next to heavy feeders, deep-rooted accumulators near shallow-rooted crops.

### References

- agendagotsch.com — Ernst Götsch's original syntropic agriculture resource
- syntropia.com.au — Australian syntropic agriculture network
- Daleys Fruit Nursery (daleysfruit.com.au) — Primary source for fruit tree specifications and subtropical varieties

---

## 5. farmOS — The Platform

### What farmOS Is

farmOS is an **open-source, Drupal-based farm management web application**. It tracks farm assets (plants, land, equipment, structures), logs (activities, observations, harvests, seedings), and provides a JSON:API for programmatic access. Documentation: https://farmos.org/

### Our Instance

- **URL:** https://margregen.farmos.net/
- **Auth:** OAuth2 (credentials in .env, never in repo)
- **API base:** https://margregen.farmos.net/api

### Current State (as of March 2026)

| Entity | Count | Notes |
|--------|-------|-------|
| Land assets | 93 | Paddocks and rows fully mapped, including sections (P2R3.0-3, etc.) |
| Structure assets | 17 | Including nursery and sub-locations |
| Plant type taxonomy | ~80 | Imported Jan 2026; ~100 more in CSV to add |
| Plant assets | 2 | Minimal — most planting data still in Claire's spreadsheets |
| Seed assets | 0 | Not yet created |
| Activity logs | 55 | Various |
| Observation logs | 40 | Various |
| Seeding logs | 8 | Not using proper Seed→Plant workflow |
| Transplanting logs | 7 | Existing |
| Water assets | 11 | Dams, trenches |
| Equipment assets | 3 | |
| Compost assets | 5 | |

**Critical gaps:**
- ~100 plant types from the v6 masterfile still need importing
- No Seed assets exist (244 records in CSV ready)
- Plant assets barely started (2 total — the actual plantings are documented in spreadsheets, not farmOS)
- Seeding/transplanting logs don't use the native Seed→Plant workflow

### farmOS Data Model (Key Concepts)

**Assets** are things that exist on the farm: plants, land, equipment, structures. Assets have types (Plant, Land, Seed, etc.) and can be located hierarchically (a Plant asset is "in" a Land asset).

**Logs** are events that happen: seeding, transplanting, harvesting, observations, activities. Logs reference assets and locations.

**Taxonomy terms** are vocabularies: `plant_type` (species), `unit` (grams, plants), `log_category`, etc.

**Inventory** is tracked via Quantity records on Logs, NOT as fields on assets. A Seeding Log has a Quantity that decrements a Seed asset's inventory. An Observation Log can reset inventory with a count.

**JSON:API format:**
- Endpoints: `/api/asset/{type}`, `/api/log/{type}`, `/api/taxonomy_term/{vocabulary}`
- All relationships use UUID references
- Filter with query parameters: `?filter[status]=active&filter[type]=plant`

### Native Seed→Plant Workflow (The Right Way)

This is the farmOS-recommended approach we should use:

```
1. Seed Asset created → "Tomato Marmande Seeds"
   Location: Nursery - Seed Bank
   Inventory: 60g (via Quantity on Observation Log)

2. Seeding Log created →
   References Seed Asset (decrements inventory)
   Creates Plant Asset → "2026 Spring Tomato Marmande"
   Location: Nursery Shelf 1

3. Transplanting Log created →
   References Plant Asset
   Moves location to field → P2R3.14-21
```

### farmOS Python Library

Use `farmOS.py` for API interactions:
```python
from farmOS import farmOS
client = farmOS(hostname="https://margregen.farmos.net", ...)
client.authorize(username, password, scope="farm_manager")
plants = client.asset.get("plant")
client.log.send("activity", log_data)
```

---

## 6. DATA FILES

### Plant Types Master Database

**File:** `knowledge/plant_types.csv` (v6, 180 records)
**Columns:** common_name, botanical_name, crop_family, origin, description, lifespan, lifecycle, maturity_days, strata, succession_stage, plant_functions, harvest_days, germination_time, transplant_days, source

This is the farm's plant knowledge base. It grows as new species are introduced. Key stats:
- 8 emergent, 24+ high, 41+ medium, 67+ low strata species
- 16 Australian natives (eucalypts, wattles, melaleucas, finger lime, macadamia)
- Sources: EDEN Seeds, Daleys Fruit Nursery, Greenpatch Organic Seeds, FFC (farm-saved)

### Seed Bank Inventory

**File:** `knowledge/seed_bank.csv` (v2, 244 records)
**Two-quantity system:** `quantity_grams` (exact weight) + `stock_level` (0/0.5/1 indicative)
- 77% commercial seeds, 23% farm-saved (FFC)
- Top farm-saved: Vetch 466g, Pigeon Pea 328g, Okra 169g
- Two inventory sources: Claire's Dec 2024 count (109), Daniel's Jan 2026 count (135)

### Field Sheet Data

**Directory:** `fieldsheets/` (not committed to git — input data)
**Format:** Excel files per row, tabs per section
**Processing:** `scripts/parse_fieldsheets.py` → `site/src/data/sections.json`

Currently have P2R2 and P2R3 field sheets. Agnes will upload all P2 rows.

### Sections JSON (Generated)

**File:** `site/src/data/sections.json`
**Generated by:** parse_fieldsheets.py
**Structure:**
```json
{
  "sections": {
    "P2R3.14-21": {
      "id": "P2R3.14-21",
      "paddock": 2, "row": 3,
      "range": "14–21", "length": "7m",
      "has_trees": true,
      "first_planted": "April 2025",
      "inventory_date": "2025-11-12",
      "plants": [
        {"species": "Ice Cream Bean", "strata": "emergent", "count": 4, "notes": "3 original + 1 planted Nov 2025"},
        ...
      ]
    }
  },
  "rows": {
    "P2R3": { "paddock": "Paddock 2", "row": "Row 3", "sections": [...], "total_length": "63m" }
  }
}
```

---

## 7. REPO STRUCTURE

```
firefly-farm-ai/
├── CLAUDE.md                  ← THIS FILE. Read every session.
├── README.md                  ← Public repo README
├── .gitignore
├── .env.example               ← farmOS credentials template (never commit .env)
├── requirements.txt           ← Python dependencies
│
├── site/                      ← Public QR code landing pages (deployed to GitHub Pages)
│   ├── public/                ← Generated HTML pages + static assets
│   │   ├── index.html         ← Paddock overview entry point
│   │   ├── P2R3.14-21.html   ← Section landing page (one per section)
│   │   └── qrcodes/          ← Generated QR code images (gitignored)
│   └── src/
│       └── data/
│           └── sections.json  ← Generated intermediate data
│
├── scripts/                   ← Python data pipeline
│   ├── export_farmos.py       ← FOUNDATION: Export from farmOS → sections.json (Phase 1)
│   ├── import_fieldsheets.py  ← FOUNDATION: Import spreadsheets → farmOS (Phase 1)
│   ├── import_plants.py       ← Import plant types CSV → farmOS taxonomy (Phase 1)
│   ├── parse_fieldsheets.py   ← DEMO SHORTCUT: spreadsheets → sections.json (Phase 0 only)
│   ├── generate_site.py       ← sections.json + plant_types.csv → HTML pages
│   └── generate_qrcodes.py    ← Generate QR images from sections.json
│
├── knowledge/                 ← Farm knowledge base
│   ├── plant_types.csv        ← Master plant database (v6, 180 species)
│   └── seed_bank.csv          ← Seed inventory (to be added)
│
├── mcp-server/                ← farmOS MCP server (Phase 1, to be built)
│
├── skills/                    ← Claude Skills (to be developed)
│
├── docs/                      ← Architecture decisions, specs
│
└── .github/
    └── workflows/
        └── deploy-pages.yml   ← Auto-deploy site/public/ to GitHub Pages on push
```

---

## 8. THE DATA PIPELINE

### The Foundation Pipeline (Target Architecture)

farmOS is the **source of truth**. Everything flows through it. The pipeline is:

```
Claire's spreadsheets (.xlsx)
        │
        ▼
  IMPORT INTO farmOS  ←──────── scripts/import_fieldsheets.py
  (logs, assets, inventory)     scripts/import_plants.py
        │
        ▼
  farmOS (SOURCE OF TRUTH)  ←── margregen.farmos.net
        │
        ▼
  EXPORT FROM farmOS  ←──────── scripts/export_farmos.py
        │
        ▼
  site/src/data/sections.json
        │
        ▼
  generate_site.py  ◄────────── knowledge/plant_types.csv
        │                        (syntropic enrichment: botanical names,
        ▼                         functions, strata, descriptions)
  site/public/*.html
        │
        ▼
  GitHub Pages (auto-deployed)
        │
        ▼
  generate_qrcodes.py → QR codes for poles
```

This means:
- **Claire's spreadsheets are INPUT**, not the source. Data flows INTO farmOS from them.
- **farmOS export is what generates the site**, not the spreadsheets directly.
- **Plant types CSV enriches** the farmOS data with syntropic context (botanical names, descriptions, functions) that farmOS doesn't store yet (until the farm_syntropic module is built in Phase 4).
- **When farmOS data changes** (via UI, API, or MCP), re-export and regenerate. The pages always reflect farmOS state.

### The Demo Shortcut (Phase 0 Only)

For the Landcare demo on March 10, 2026, we use a temporary shortcut because the farmOS import pipeline isn't ready yet:

```
Claire's spreadsheets → parse_fieldsheets.py → sections.json → generate_site.py → pages
```

This is **explicitly temporary**. The parse_fieldsheets.py script exists to bridge the gap until Claire's data is properly in farmOS. Once farmOS has the planting data (via import scripts or MCP server), the spreadsheet parser becomes unnecessary and the export_farmos.py script takes its place as the data source.

### Pipeline Evolution

| Phase | Data source for site generation | Why |
|-------|-------------------------------|-----|
| Phase 0 (now) | Claire's spreadsheets (via parse_fieldsheets.py) | farmOS doesn't have planting data yet |
| Phase 1 | farmOS export (via export_farmos.py) | Planting data imported to farmOS |
| Phase 2+ | farmOS export via MCP server | Live queries, no manual export needed |
| Future | Real-time from farmOS API | Pages update automatically when farmOS changes |

### Run Commands

**Phase 0 (demo shortcut):**
```bash
python scripts/parse_fieldsheets.py --input fieldsheets/ --output site/src/data/
python scripts/generate_site.py --data site/src/data/sections.json --plants knowledge/plant_types.csv --output site/public/
python scripts/generate_qrcodes.py --base-url https://<github-pages-url>/
```

**Phase 1+ (foundation pipeline):**
```bash
python scripts/export_farmos.py --output site/src/data/sections.json
python scripts/generate_site.py --data site/src/data/sections.json --plants knowledge/plant_types.csv --output site/public/
```

**Key principles:**
- farmOS is the source of truth. Always.
- Never hand-code farm data into pages — always generate from structured data.
- The plant types CSV enriches but does not replace farmOS data.
- All scripts are idempotent — safe to re-run anytime.
- The demo shortcut is a bridge, not the architecture.

---

## 9. QR CODE LANDING PAGES

### Purpose

Every cultivated row section has a physical pole with a QR code. Scanning it takes you to a mobile-friendly page showing what's planted in that specific section.

### Design

- **Mobile-first** (430px max-width, touch targets)
- **Botanical field guide aesthetic** — NOT the Firefly Agents tech brand
- **Typography:** Playfair Display (headings), DM Sans (body) via Google Fonts
- **Colors:** Forest green palette, strata-coded accents
  - Emergent: #2d5016
  - High: #4a7c29
  - Medium: #6b9e3c
  - Low: #8bb85a
- **Tree sections:** Dark green gradient header
- **Open cultivation:** Light green gradient header

### Page Structure (Section Landing)

1. **Header:** Section range (e.g., "14–21m"), tree/open badge, stats (species count, plant count, length)
2. **Row bar:** Visual map of entire row showing all sections, current highlighted in orange. Tappable to navigate.
3. **Section tabs:** Horizontal scrollable tabs for all sections in the row
4. **Plant inventory:** Grouped by strata (Emergent → High → Medium → Low)
   - Each strata group has header with icon, height range, plant count badge
   - Plant cards show: common name, botanical name (italic), count badge, notes
   - Tap to expand: full description, family, origin, lifespan, succession stage, function tags
   - Dead/lost plants shown dimmed with ✝ marker
5. **Syntropic explainer:** Collapsible educational section
6. **Footer:** Inventory date, first planted date, farm attribution

### Function Tags (Visual)

Each plant function gets a colored pill with emoji:
- ⚡ nitrogen fixer (warm yellow)
- 🍎 edible fruit (pink)
- ♻️ biomass producer (blue)
- 🦎 native habitat (green)
- 🐝 nectar source (amber)
- 🛡️ pest management (purple)
- etc.

### Succession Indicators

- Pioneer: amber dot + description
- Secondary: blue dot + description
- Climax: dark green dot + description

---

## 10. ARCHITECTURE DECISIONS

These decisions have been made through extensive discussion. Don't revisit them unless Agnes explicitly asks.

1. **Single agent, not multi-agent.** Following Anthropic's principle: start with the simplest thing that works. One well-tooled Claude agent with the farmOS MCP server.

2. **farmOS MCP server in Python.** farmOS.py is the mature Python client. Python MCP SDK is official. No reason to use another language.

3. **Claude IS the UI** for non-technical users. Don't train Claire on farmOS's web interface. Let Claude translate natural language to API calls.

4. **GitHub is the single source of truth** for all code, scripts, knowledge, and documentation.

5. **Field operations before nursery/seeds.** Get paddock row tracking working first, then expand to nursery and seed bank.

6. **Defer custom Drupal module.** The farm_syntropic module (strata, succession, consortium fields as proper farmOS entities) is Phase 4. Current approach of embedding syntropic data in plant type descriptions works fine for months.

7. **Public landing pages for QR codes.** Visitors and farmhands can't log into farmOS. Static pages on GitHub Pages, generated from data, are the visitor/farmhand interface.

8. **Landcare demo is real Phase 0.** The first tangible output is working QR code pages for a Paddock 2 farm tour on March 10, 2026.

9. **Native farmOS Seed and Plant assets** over custom Material assets. This aligns with farmOS best practices and enables the built-in Seed→Plant lifecycle workflow.

10. **Plant types CSV is the master reference** until all data is properly in farmOS with custom fields. The CSV grows iteratively as new species are identified.

---

## 11. IMPLEMENTATION PHASES

### Phase 0: Landcare Demo (Current — by March 10, 2026)
- ✅ Parse P2R2 and P2R3 field sheets into sections.json
- ✅ Generate 14 section HTML pages + index
- ✅ Pipeline tested end-to-end
- ⬜ Upload and parse remaining P2 rows (R1, R4, R5)
- ⬜ Fresh farmOS export to verify/sync location assets
- ⬜ Push to GitHub, enable GitHub Pages
- ⬜ Generate QR codes, print for poles
- ⬜ Test visitor experience on phone

### Phase 1: farmOS MCP Server (Weeks 2–3)
Core tools to implement:
1. `query_assets` — Search assets by type, status, location
2. `get_locations` — Return location hierarchy
3. `get_plant_types` — Search/list plant type taxonomy
4. `create_log` — Create activity/observation/seeding/transplanting/harvest logs
5. `query_logs` — Search logs by date, type, asset, location
6. `create_asset` — Create plant or seed assets
7. `get_inventory` — Query seed stock levels

Resources: `farm://overview`, `farm://plants`, `farm://locations`, `farm://recent`
Prompts: `log-field-activity`, `record-seeding`, `transplant-to-paddock`

### Phase 2: Claire's First Real Log (Weeks 3–4)
Goal: Claire uses Claude + MCP to log a field activity in natural language, and it lands in farmOS correctly.

### Phase 3: Nursery & Seed Bank (Months 2–3)
- Import seed bank data as Seed assets
- Create Plant assets for tracked plantings
- Nursery inventory workflow
- Seed→Plant lifecycle tracking

### Phase 4: Custom farmOS Module (Month 3+)
`farm_syntropic` Drupal module adding:
- Proper fields: strata, succession_stage, plant_functions on plant_type taxonomy
- New taxonomies: strata, succession_stage, plant_function
- New asset types: Consortium
- New log types: Pruning, Biomass
- Data migration from descriptions to structured fields

### Phase 5: Multi-User & Advanced AI (Month 4+)
- Shared Claude Project for the team
- Voice input for field use
- Live site updates from farmOS data
- Knowledge base evolution (learning which consortiums work)
- WhatsApp harvest log parsing

---

## 12. NAMING CONVENTIONS

### Location IDs
Format: `P{paddock}R{row}.{start}-{end}` (metres from row origin)
Examples: `P2R3.0-3`, `P2R3.14-21`, `P1R1.0-10`
The dot separates the row from the section. The dash separates the start and end metre marks.

### Plant Type Names
- Common name is the primary key (must match farmOS taxonomy exactly)
- Varieties in parentheses: `Tomato (Marmande)`, `Chilli (Jalapeño)`, `Cherry Guava (Strawberry)`
- Generic cultivars: `Capsicum (Red)`, `Cabbage (Golden Acre)`
- No parentheses for single-variety types: `Pigeon Pea`, `Comfrey`, `Macadamia`

### File Naming
- Field sheets: `P{paddock}R{row}_Field_Sheets_v{version}.xlsx`
- Generated pages: `P{paddock}R{row}.{start}-{end}.html`
- Data files: descriptive, underscored, versioned: `firefly_plant_types_COMPLETE_v6.csv`

### farmOS Conventions
- Asset names for plants: `{Year} {Season} {Species} {Location or Batch}` — e.g., "2025 Spring Tomato Marmande P2R3"
- Seed asset names: `{Species} Seeds` — e.g., "Pigeon Pea Seeds"
- Log names: descriptive of the action — "Pruning pigeon pea in P2R3.14-21"

---

## 13. ENVIRONMENT SETUP

```bash
# Python dependencies
pip install -r requirements.txt
# (requests, openpyxl, pandas, jinja2, qrcode[pil], python-dotenv)

# farmOS credentials (create .env from .env.example, never commit .env)
FARMOS_URL=https://margregen.farmos.net
FARMOS_CLIENT_ID=farm
FARMOS_USERNAME=...
FARMOS_PASSWORD=...

# For local farmOS dev (future — Docker)
# docker-compose up -d
```

---

## 14. KEY SCRIPTS

### Foundation Pipeline Scripts

**export_farmos.py** (TO BE BUILT — Phase 1 priority)
Exports planting data from farmOS into sections.json format for site generation.
```bash
python scripts/export_farmos.py --output site/src/data/sections.json
```
This is the script that makes farmOS the source of truth for the site. It queries farmOS for assets, logs, and inventory by location, then structures the data the same way parse_fieldsheets.py does — so generate_site.py doesn't care where the data came from.

**import_fieldsheets.py** (TO BE BUILT — Phase 1)
Imports Claire's spreadsheet data INTO farmOS as proper logs and assets.
```bash
python scripts/import_fieldsheets.py --input fieldsheets/ --dry-run
python scripts/import_fieldsheets.py --input fieldsheets/
```
This is how spreadsheet data enters farmOS. Once data is in farmOS, the spreadsheets are no longer needed for that data.

**import_plants.py** (TO BE BUILT — Phase 1)
Imports plant types from the master CSV into farmOS taxonomy.
```bash
python scripts/import_plants.py --csv knowledge/plant_types.csv --dry-run
python scripts/import_plants.py --csv knowledge/plant_types.csv
```

### Demo Shortcut Scripts (Phase 0)

**parse_fieldsheets.py**
Converts Claire's Excel field sheets directly into sections.json, bypassing farmOS. This is the Phase 0 bridge — it will be replaced by export_farmos.py once planting data is in farmOS.
```bash
python scripts/parse_fieldsheets.py --input fieldsheets/ --output site/src/data/
```
Input: .xlsx files in fieldsheets/
Output: site/src/data/sections.json

### Site Generation Scripts (Permanent)

**generate_site.py**
Generates static HTML pages from sections.json + plant_types.csv. This script doesn't care whether sections.json came from farmOS export or spreadsheet parsing — same input format either way.
```bash
python scripts/generate_site.py
```
Input: site/src/data/sections.json, knowledge/plant_types.csv
Output: site/public/*.html

**generate_qrcodes.py**
Creates printable QR code images for section poles.
```bash
python scripts/generate_qrcodes.py --base-url https://<username>.github.io/firefly-farm-ai/
```
Input: site/src/data/sections.json
Output: site/public/qrcodes/*.png (one per section + index)

---

## 15. IMPORTANT RULES

1. **farmOS is the source of truth** for all farm data. Claire's spreadsheets are INPUT to farmOS, not the source. Pages are generated from farmOS EXPORT, not spreadsheets. The Phase 0 demo shortcut (spreadsheet → pages) is temporary.
2. **Data flows one direction:** Spreadsheets → farmOS → Export → Site. Never generate permanent outputs directly from spreadsheets. The parse_fieldsheets.py shortcut exists only until farmOS has the data.
3. **Never hardcode farm data** — always generate from structured data (sections.json).
4. **Plant common names must match farmOS taxonomy exactly** — this is the join key across all systems.
5. **All scripts must be idempotent** — safe to re-run without creating duplicates.
6. **Mobile-first for all visitor-facing pages** — people scan QR codes on phones.
7. **Honest about data** — always show inventory dates, mark dead/lost plants, don't hide failures.
8. **Keep it simple** — resist the urge to over-engineer. The farm moves fast. Working beats perfect.
9. **Test locally before production** — always test farmOS API changes against local dev instance first.
10. **Document decisions** — this file and docs/ are where architectural decisions live.

---

## 16. WHAT'S NOT BUILT YET (And Shouldn't Be Built Prematurely)

- Multi-agent systems (one good agent first)
- Custom farmOS views/dashboards (use the API, not the UI)
- Weather integration
- Photo/image logging
- Automated notifications
- Custom mobile app (Claude mobile IS the app)
- WhatsApp integration (harvest logs are there but parsing is Phase 5)
- farm_syntropic Drupal module (Phase 4 — current description-based approach works)

---

## 17. HARVEST DATA (Future Work)

The farm started recording harvests in summer 2025/2026 via the WhatsApp group. Format: produce name, weight, location (e.g., "3kg tomatoes from P1R1"). This chat history (2-3 months) needs to be parsed into farmOS harvest logs. Not urgent for Phase 0, but on the roadmap.

---

## 18. QUICK REFERENCE: Plants You'll See Most

These species appear across almost every row and are central to understanding the farm:

| Species | Strata | Succession | Why It's Important |
|---------|--------|------------|-------------------|
| Forest Red Gum | Emergent | Climax | Native NSW eucalypt, 50m. Wind protection, honey, wildlife. The permanent canopy. |
| Ice Cream Bean | Emergent | Pioneer | Fast N-fixer. Sweet pods. Critical shade tree in young syntropic systems. |
| Pigeon Pea | High | Pioneer | THE pioneer. Fast N-fixer, edible seeds, biomass. Short-lived by design — dies and makes way. Many losses expected. |
| Macadamia | High | Climax | Native nut tree. The farm's long-term investment. Slow but permanent. |
| Tagasaste | High | Pioneer | Tree lucerne. Extraordinary N-fixer and bee forage. Chop-and-mulch champion. |
| Tomato (Marmande) | High | Pioneer | French beefsteak. Staple summer harvest. Planted abundantly. |
| Apple | High | Secondary | Multiple varieties. Deciduous — lets winter light through. |
| Comfrey | Low | Secondary | Deep taproots mine subsoil minerals. Cut for instant mulch. "The permaculture plant." |
| Sweet Potato | Low | Pioneer | Vigorous groundcover + food. Living mulch that suppresses weeds. |

---

*Last updated: March 2026. This file should be updated as the project evolves.*
