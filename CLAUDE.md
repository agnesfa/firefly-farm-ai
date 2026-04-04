# CLAUDE.md — Firefly Corner Farm AI System

> Lean context file. Stable domain knowledge lives here. Volatile data lives in farmOS — query it.
> Session history: `claude-docs/session-history.md`. Design docs: `claude-docs/`.

---

## 1. THE FARM

**Firefly Corner Farm** is a 25-hectare regenerative agriculture property near **Krambach, NSW** on Australia's Mid North Coast. Practices **syntropic agroforestry** — mimicking natural forest ecosystems through strategic plant layering. Early stage (planted from April 2025).

### Physical Layout

```
Farm (~25 hectares)
├── Paddock 1 (P1) — 5 cultivated rows (R1–R5), mainly annuals and pioneer species
├── Paddock 2 (P2) — 5 cultivated rows (R1–R5), syntropic tree rows with perennials
│   ├── P2R1 — ~22m, 4 sections    ├── P2R4 — ~77m, 8 sections
│   ├── P2R2 — ~46m, 7 sections    └── P2R5 — ~77m, 7 sections
│   └── P2R3 — ~63m, 7 sections
├── Plant Nursery — shelves, ground areas, seed bank (fridge)
├── Water Infrastructure — 2+ dams, keyline trenches, irrigation
├── Campground — 3 registered Hipcamp sites
└── Common areas, infrastructure, bush
```

### Climate
Subtropical with Mediterranean influences. Clay soil being regenerated. Frost risk. Drought periods.

### Online Presence
- **farmOS:** https://margregen.farmos.net/
- **GitHub Pages:** https://agnesfa.github.io/firefly-farm-ai/ (QR code landing pages)
- **GitHub repo:** https://github.com/agnesfa/firefly-farm-ai
- **Drone tiles:** https://github.com/agnesfa/farm-tiles

---

## 2. THE PEOPLE

**Agnes** — CTO & Architect. You work with her directly in Claude Code. Designs the digital systems. Strong opinions about architecture. Cares about: long-term foundations, commercialisation potential, data-driven decisions, enabling others without requiring them to be technical.

**Claire** — Agronomist & Field Operations. Designs syntropic rows, manages volunteers. Tracks in Excel spreadsheets. Her spreadsheet format: tabs per section, rows grouped by strata (Emergent → High → Medium → Low), columns for species/count/notes/planted date.

**James** — Co-owner, Infrastructure & Marketing. Handles irrigation, machines, social media, investor relations. Uses Claude.ai for content.

**Olivier** — Compost & cooking. Occasional system user.

**WWOOFers** — Volunteers. Execute field tasks. Interact via QR code landing pages.

### Access Model

| Role | Who | Interface |
|------|-----|-----------|
| **Manager** | Agnes, Claire, James | Claude Desktop/Code, farmOS UI |
| **Farmhand** | WWOOFers | QR pages, observation forms |
| **Visitor** | Hipcamp, Landcare | QR code landing pages (public, no auth) |

---

## 3. SYNTROPIC AGRICULTURE — Domain Knowledge

### Core Concept
Syntropic agroforestry (Ernst Götsch, Brazil) builds productive ecosystems by mimicking natural forest succession. Plant **stacked polycultures** where every species has a role. The system evolves through **succession stages**.

Key principle: **Every plant serves the system.** A pigeon pea fixes nitrogen, produces edible seeds, creates biomass for mulching, provides shade, and when it dies, its root channels become pathways for water and successor roots.

### Strata (Vertical Layers)

| Strata | Height | Role | Examples |
|--------|--------|------|----------|
| **Emergent** | 20m+ | Permanent canopy, wind protection, wildlife | Forest Red Gum, Tallowood, Ice Cream Bean |
| **High** | 8–20m | Main production, fruit/nut trees | Macadamia, Apple, Pigeon Pea, Mulberry |
| **Medium** | 2–8m | Understorey production, citrus | Jaboticaba, Tea Tree, Lemon, Chilli |
| **Low** | 0–2m | Groundcover, herbs, root crops | Comfrey, Sweet Potato, Turmeric, Garlic |

### Succession Stages

| Stage | Lifespan | Role | Examples |
|-------|----------|------|----------|
| **Pioneer** | 0–5 yr | Fast growth, soil building, N-fixation | Pigeon Pea, Tagasaste, Banagrass |
| **Secondary** | 3–15 yr | Fill canopy as pioneers decline | Mulberry, Quince, Apple, Lemon |
| **Climax** | 15+ yr | Permanent forest structure | Macadamia, Eucalypts, Jaboticaba |

### Plant Functions
`nitrogen_fixer` `biomass_producer` `nutrient_accumulator` `edible_fruit` `edible_nut` `edible_greens` `edible_root` `edible_seed` `aromatic` `medicinal` `timber` `fodder` `living_mulch` `pest_management` `beneficial_insects` `erosion_control` `windbreak` `nectar_source` `native_habitat` `companion_plant` `green_manure` `oil_production`

### Row Design
Each row alternates **tree sections** (full strata) and **open cultivation sections** (no trees, annuals/vegetables). Creates diverse microclimates along a single row.

### Key Practices
- **Chop-and-drop:** Cut pioneers, leave as mulch. Feeds soil, suppresses weeds.
- **Succession management:** As pioneers die (by design), secondary species fill the space.
- **Consortium design:** Groups planted together — N-fixers next to heavy feeders, deep roots near shallow.

---

## 4. farmOS — The Platform

**farmOS** is an open-source, Drupal-based farm management web app with JSON:API. Docs: https://farmos.org/

- **Instance:** https://margregen.farmos.net/ (hosted on Farmier, $75/yr)
- **Auth:** OAuth2 password grant (credentials in .env)

### Data Model
- **Assets:** Things that exist (plants, land, equipment, structures). Hierarchically located.
- **Logs:** Events (seeding, transplanting, harvesting, observations, activities). Reference assets.
- **Taxonomy:** Vocabularies (`plant_type`, `unit`, `log_category`).
- **Inventory:** Tracked via Quantity records on Logs, NOT fields on assets. `inventory_adjustment: "reset"` sets absolute count.
- **JSON:API:** `/api/asset/{type}`, `/api/log/{type}`, `/api/taxonomy_term/{vocabulary}`. Filter: `?filter[status]=active`.

### Native Seed→Plant Workflow
```
Seed Asset → Seeding Log (decrements seed) → Plant Asset → Transplanting Log (moves to field)
```

### Current State — QUERY DYNAMICALLY
**Do not hardcode counts here.** Use these queries at session start:

```
get_farm_overview()                          — asset/log/taxonomy counts
farm_context(topic="overview")               — farm-wide health + gaps
read_team_activity(days=7)                   — what team has been doing
query_logs(status="pending")                 — outstanding TODO tasks
get_inventory(section_prefix="NURS")         — nursery inventory
reconcile_plant_types()                      — CSV vs farmOS drift
```

---

## 5. MCP TOOLS — The Interface Layer

Two MCP server implementations, both with identical tool sets:

| Server | Location | Transport | Deployment |
|--------|----------|-----------|------------|
| **Python** (Phase 1a) | `mcp-server/` | STDIO | Agnes's local fallback |
| **TypeScript** (Phase 1b) | `mcp-server-ts/` | HTTP | Railway ($5/mo), all 4 users via `npx mcp-remote` |

### Tool Categories
- **farmOS read:** query_plants, query_sections, get_plant_detail, query_logs, get_inventory, search_plant_types, get_all_plant_types
- **farmOS write:** create_observation, create_activity, complete_task, update_inventory, create_plant, archive_plant
- **Intelligence:** farm_context (five-layer cross-reference: farmOS + KB + plant types + team memory + semantics)
- **Observations:** list_observations, update_observation_status, import_observations
- **Team memory:** write_session_summary, read_team_activity, search_team_memory, acknowledge_memory
- **Plant types:** add_plant_type, update_plant_type, reconcile_plant_types
- **Knowledge base:** search_knowledge, list_knowledge, add_knowledge, update_knowledge
- **Site:** regenerate_pages
- **TypeScript only:** hello, get_farm_overview

### Farm Intelligence Layer
Architecture: `knowledge/farm_ontology.yaml` (entity types, relationships) + `knowledge/farm_semantics.yaml` (metrics, thresholds). Code: `mcp-server/semantics.py` / `plugins/farm-plugin/src/helpers/semantics.ts`.

The `farm_context` tool provides:
- **Section mode:** health assessment, strata coverage, activity recency, pending tasks
- **Subject mode:** species distribution across farm, KB cross-reference, metadata
- **Topic mode:** domain overview (nursery/compost/paddock), transplant readiness
- **Data integrity gate:** cross-references team memory farmos_changes against actual farmOS logs

### Apps Script Backends (all bound scripts on fireflyagents.com)
- Observations.gs, TeamMemory.gs, KnowledgeBase.gs, PlantTypes.gs, SeedBank.gs, Harvest.gs
- All with UsageTracking.gs for quota monitoring + health endpoints
- Reference copies in `scripts/google-apps-script/`

---

## 6. DATA PIPELINE

```
farmOS (SOURCE OF TRUTH)
    ↓ export_farmos.py --sections-json
site/src/data/sections.json
    ↓ generate_site.py (+ knowledge/plant_types.csv for enrichment)
site/public/*.html
    ↓ GitHub Pages auto-deploy
QR code landing pages (live)
```

**Principles:**
- farmOS is the source of truth. Always.
- MCP tools are the only write path (bulk import scripts are deprecated).
- Pages are generated from farmOS export, never hand-coded.
- All scripts are idempotent.

---

## 7. REPO STRUCTURE

```
firefly-farm-ai/
├── CLAUDE.md                  ← THIS FILE
├── site/                      ← QR landing pages (GitHub Pages)
│   ├── public/                ← Generated HTML + static assets (~149 pages)
│   └── src/data/sections.json ← Generated intermediate data
├── scripts/                   ← Python data pipeline + Apps Script reference copies
│   └── google-apps-script/    ← 7 .gs files (Observations, SeedBank, TeamMemory, etc.)
├── knowledge/                 ← Farm knowledge base
│   ├── plant_types.csv        ← Master plant database (v7, ~273 species)
│   ├── seed_bank.csv          ← Seed inventory (263 records)
│   ├── farm_ontology.yaml     ← Intelligence Layer 1: entity types + relationships
│   └── farm_semantics.yaml    ← Intelligence Layer 3: metrics + thresholds
├── mcp-server/                ← Python MCP server (29 tools, STDIO)
├── mcp-server-ts/             ← TypeScript MCP server (31 tools, Railway HTTP)
├── claude-docs/               ← Design documents, session history, team context files
├── docs/farmos/               ← farmOS API reference
└── .github/workflows/         ← GitHub Pages auto-deploy
```

---

## 8. NAMING CONVENTIONS

### Location IDs
`P{paddock}R{row}.{start}-{end}` — e.g., `P2R3.15-21`, `P1R1.0-10`
Nursery: `NURS.SH1-1`, `NURS.GR`, `NURS.FRDG`. Compost: `COMP.BAY1`.

### Plant Type Names (`farmos_name` — the join key)
- `Common Name (Variety)` when variety exists: `Tomato (Marmande)`, `Guava (Strawberry)`
- Just `Common Name` otherwise: `Pigeon Pea`, `Comfrey`
- Dash for sub-types: `Basil - Sweet`, `Lavender - French`
- 7 retain `(Generic)`: Eucalypt-Gum, Melaleuca, Plum, Pumpkin, Radish, Spinach, Wattle

### farmOS Asset Names
Plants: `{date} - {farmos_name} - {section_id}` — e.g., `25 APR 2025 - Pigeon Pea - P2R2.0-3`
Seeds: `{Species} Seeds` — e.g., `Pigeon Pea Seeds`

---

## 9. ARCHITECTURE DECISIONS

Don't revisit unless Agnes explicitly asks.

1. **Single agent, not multi-agent orchestration.** Sub-agents for delegation within a session are fine.
2. **farmOS MCP server: Python (STDIO) + TypeScript (Railway HTTP).** Python is Agnes's local fallback.
3. **Claude IS the UI** for non-technical users.
4. **GitHub is the single source of truth** for code, scripts, knowledge, documentation.
5. **Native farmOS Seed and Plant assets** over custom Material assets.
6. **Plant types CSV is the master reference** until farm_syntropic Drupal module (Phase 4).
7. **Stay on Farmier** for farmOS hosting until Phase 4 requires custom Drupal modules.
8. **Test first, smart coverage.** 3-layer test harness: pure functions, HTTP-mocked clients, tool orchestration. Fast (<2s), zero network, catch regressions.
9. **Knowledge Base taxonomy: category + topics + tags.** Category = content type, topics = farm domains, tags = free-form.
10. **Cross-referencing via join keys.** `farmos_name` (species), section IDs (locations), `topics` (farm domains). `farm_context` tool does cross-referencing in code, not AI reasoning.
11. **Pagination: offset-based for all collection fetches.** farmOS `links.next` unreliable beyond ~250 results. Use `page[offset]` with stable `sort`. Write existence checks use `fetchByName` (direct, never paginated).
12. **MCP tools are the only write path.** Import scripts deprecated. All data entry through MCP tools.
13. **Public QR pages via GitHub Pages.** Visitors and farmhands can't log into farmOS.
14. **Defer farm_syntropic Drupal module** to Phase 4. Description-based approach works.

---

## 10. IMPORTANT RULES

1. **farmOS is the source of truth** for all farm data.
2. **Data flows one direction:** Input → farmOS → Export → Site.
3. **Never hardcode farm data** — always generate from structured data.
4. **Plant names must match farmOS taxonomy exactly** — this is the join key.
5. **All scripts must be idempotent** — safe to re-run.
6. **Mobile-first** for visitor-facing pages.
7. **Honest about data** — show inventory dates, mark dead plants, don't hide failures.
8. **Keep it simple** — working beats perfect.
9. **Test locally before production.**

---

## 11. QR CODE LANDING PAGES

- **Mobile-first** (430px max-width), botanical field guide aesthetic
- **Typography:** Playfair Display (headings), DM Sans (body)
- **Colors:** Forest green palette, strata-coded: Emergent #2d5016, High #4a7c29, Medium #6b9e3c, Low #8bb85a
- **Page types:** Section view (visitor), Section observe (worker form), Nursery, Seed Bank, Harvest, Amenities, Index
- Plants grouped by strata, expand for detail (description, family, origin, succession, function tags)
- Dead/lost plants dimmed with marker. Uninventoried plants show "—" badge.

---

## 12. ENVIRONMENT SETUP

```bash
# Python 3.13 (NOT 3.14 — pydantic v1 incompatible)
python3.13 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# MCP server has SEPARATE venv (pydantic v2 for FastMCP)
cd mcp-server && python3.13 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# farmOS credentials (.env from .env.example, never commit)
FARMOS_URL=https://margregen.farmos.net
FARMOS_CLIENT_ID=farm
FARMOS_USERNAME=...
FARMOS_PASSWORD=...
```

---

## 13. SESSION START — Dynamic Context

Run these at the beginning of each session to understand current state instead of relying on stale documentation:

```python
# Farm overview — live asset/log/taxonomy counts
get_farm_overview()

# Recent team activity — what happened since last session
read_team_activity(days=7, only_fresh_for="Agnes")

# Outstanding tasks
query_logs(status="pending")

# Specific area deep-dive (use as needed)
farm_context(section="P2R3.15-21")   # section health assessment
farm_context(subject="Pigeon Pea")    # species distribution
farm_context(topic="nursery")         # domain overview

# Data health
reconcile_plant_types()               # CSV vs farmOS drift
```

For session history and past decisions, check:
- `read_team_activity(days=30)` or `search_team_memory(query="...")`
- `claude-docs/session-history.md` — full session log archive (March–April 2026)
- `git log --oneline -20` — recent commit trajectory

---

*This file was redesigned April 4, 2026. Previously 1602 lines; now ~200. Volatile data replaced with dynamic queries via MCP tools. Session log archived to claude-docs/session-history.md.*
