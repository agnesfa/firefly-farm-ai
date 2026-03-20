# Firefly Corner — Technical Architecture

> Updated March 20, 2026. Reflects Phase 1b remote MCP on Railway, all 4 machines migrated, Phase KB quick wins deployed.

---

## System Overview

```
                                    ┌─────────────────────────────┐
                                    │      farmOS (Drupal 3.x)     │
                                    │  margregen.farmos.net        │
                                    │  Hosted on Farmier ($75/yr)  │
                                    │                              │
                                    │  Source of truth for:        │
                                    │  - Plant assets (441)        │
                                    │  - Land assets (96)          │
                                    │  - Structure assets (37)     │
                                    │  - Material assets (14)      │
                                    │  - Group assets (11)         │
                                    │  - Logs (1,173)              │
                                    │  - Plant types (224)         │
                                    │  - Inventory (computed)      │
                                    └──────────┬───────────────────┘
                                               │
                                          JSON:API
                                          OAuth2
                                               │
                    ┌──────────────────────────┼──────────────────────────┐
                    │                          │                          │
          ┌─────────▼─────────┐    ┌───────────▼──────────┐    ┌─────────▼─────────┐
          │  MCP Server       │    │  Python Scripts       │    │  farmOS Web UI    │
          │  (FastMCP/STDIO)  │    │  (import/export)      │    │  (Drupal admin)   │
          │                   │    │                       │    │                   │
          │  23 tools         │    │  export_farmos.py     │    │  Direct access    │
          │  5 resources      │    │  import_fieldsheets   │    │  (Agnes only)     │
          │  3 prompts        │    │  import_historical    │    │                   │
          │                   │    │  import_plants        │    └───────────────────┘
          │  Deployed to:     │    │                       │
          │  - Agnes (macOS)  │    │  Runs in: main venv   │
          │  - Claire (Win)   │    │  (Python 3.13 +       │
          │  - James (macOS)  │    │   farmOS.py/pydantic  │
          │  - Olivier (Win)  │    │   v1)                 │
          │                   │    │                       │
          │  Runs in: mcp     │    └───────────┬───────────┘
          │  venv (pydantic   │                │
          │  v2, raw HTTP)    │                │
          └────────┬──────────┘         ┌──────▼──────┐
                   │                    │ sections    │
            Claude Desktop              │ .json       │
            (STDIO transport)           │ (generated) │
                   │                    └──────┬──────┘
          ┌────────▼──────────┐                │
          │  Claude AI        │         ┌──────▼──────────────┐
          │                   │         │  generate_site.py   │
          │  Agnes: Claude    │         │  + plant_types.csv  │
          │    Code + Desktop │         │  (enrichment)       │
          │  Claire: Desktop  │         └──────┬──────────────┘
          │  James: Desktop   │                │
          │  Olivier: Desktop │         ┌──────▼──────┐
          │                   │         │  75 HTML    │
          │  "Claude IS       │         │  pages (P2) │
          │   the UI"         │         │  (static)   │
          └───────────────────┘         └──────┬──────┘
                                               │
                                          GitHub Pages
                                     (auto-deploy on push)
                                               │
                              ┌────────────────┼────────────────┐
                              │                │                │
                    ┌─────────▼───┐   ┌────────▼────┐   ┌──────▼──────┐
                    │ QR View     │   │ QR Observe  │   │ Index Page  │
                    │ Pages (37)  │   │ Pages (37)  │   │             │
                    │             │   │             │   │ Paddock     │
                    │ What's      │   │ Log field   │   │ overview    │
                    │ planted     │   │ observations│   │             │
                    │ here?       │   │             │   └─────────────┘
                    │             │   │ POST to     │
                    │ Visitors    │   │ Apps Script  │
                    │ Farmhands   │   │             │
                    └─────────────┘   └──────┬──────┘
                                             │
                                        HTTPS POST
                                     (Content-Type:
                                      text/plain to
                                      avoid CORS)
                                             │
                    ┌────────────────────────────────────────────┐
                    │       Google Apps Script Endpoints          │
                    │       (fireflyagents.com account)           │
                    │                                            │
                    │  1. Observation Code.gs (v3)               │
                    │     → Field Observations Sheet + Drive     │
                    │                                            │
                    │  2. TeamMemory.gs (bound to Sheet)         │
                    │     → Team Memory Sheet                    │
                    │                                            │
                    │  3. PlantTypes.gs (bound to Sheet)         │
                    │     → Plant Types v7 Sheet                 │
                    └────────────────────────────────────────────┘
```

---

## Component Details

### 1. farmOS — Source of Truth

| Aspect | Detail |
|---|---|
| **Platform** | Drupal 10 + farmOS 3.x |
| **Hosting** | Farmier managed hosting ($75/year) |
| **URL** | https://margregen.farmos.net |
| **API** | JSON:API (Drupal core) |
| **Auth** | OAuth2 password grant |
| **Users** | Agnes (farm_manager scope) |

**Data model (March 17, 2026):**
- **Assets**: Plant (441), Land (96), Structure (37), Material (14), Group (11), Water (11), Equipment (3), Compost (5)
- **Logs**: Observation (772), Transplanting (307), Activity (78), Seeding (8), Harvest (8)
- **Taxonomy**: plant_type (224 terms with syntropic metadata in descriptions)
- **Inventory**: Computed attribute on assets, derived from Quantity entities on logs

**Land hierarchy:**
```
Farm
├── Paddock 1 (P1)
│   ├── P1R1 (Row 1) — 6 sections: .0-5, .5-9, .9-19, .19-29, .29-39, .39-42
│   ├── P1ED1.0-5 (Drain-end section, under P1 + P1R1)
│   ├── P1R3 (Row 3) — 5 sections: .0-3, .3-13, .13-23, .23-33, .33-42
│   └── P1R5 (Row 5) — 4 sections: .0-10, .10-20, .20-30, .30-35
├── Paddock 2 (P2)
│   ├── P2R1–P2R5 (Rows 1–5) — 37 sections total (4+7+8+11+9)
│   └── P2T1–P2T3 (Transects)
└── Edible Forest
```

**Nursery hierarchy (Structure assets):**
```
Plant Nursery
├── NURS.SH1-1 through NURS.SH1-4 (Shelf 1, 4 positions)
├── NURS.SH2-1 through NURS.SH2-4 (Shelf 2, 4 positions)
├── NURS.SH3-1 through NURS.SH3-4 (Shelf 3, 4 positions)
├── NURS.BCK (Back area)
├── NURS.FRT (Front area)
├── NURS.GR (Ground area)
├── NURS.GL (Ground level)
├── NURS.HILL (Hill area)
├── NURS.STRB (Strawberry area)
├── NURS.FRDG (Fridge — SEED BANK location)
├── NURS.FRZR (Freezer)
├── Special Cares Area (greenhouse)
└── Incubator Chamber (greenhouse)
```

**Key design choices:**
- Plant type descriptions embed syntropic data (strata, succession, functions) as text until Phase 4 custom module
- Inventory uses `inventory_adjustment: "reset"` on observation logs for absolute counts
- Plant asset naming: `{date} - {species} - {section_id}`
- Observation log naming: `Observation {section} — {species} — {date}` (date suffix added March 17 to prevent dedup collisions)
- Seed bank is a structure asset (NURS.FRDG) — Seed assets will be located here

### 2. MCP Server — AI ↔ farmOS Bridge

| Aspect | Detail |
|---|---|
| **Framework** | FA MCP Framework (TypeScript) — Phase 1b on Railway |
| **Transport** | Remote HTTP (StreamableHTTP + SSE fallback) — all 4 users via `npx mcp-remote` |
| **Language** | TypeScript (production), Python 3.13 (Agnes STDIO fallback) |
| **Hosting** | Railway ($5/mo Hobby plan), self-ping keep-alive (4-min interval) |
| **Auth** | Per-user API keys via credentials.json; farmOS creds from env vars |
| **Python fallback** | `mcp-server/` with FastMCP/STDIO, separate venv (pydantic v2) |

**Phase 1b milestones:**
- March 19: Deployed to Railway, 29 tools, 98 tests, 3 production fixes (auth, Apps Script redirect, cold start)
- March 20: All 4 team machines migrated from local Python STDIO to remote `npx mcp-remote`

**Tools (29):**

| Category | Tool | Purpose |
|---|---|---|
| Read | `query_plants` | Search plants by section, species, or status |
| Read | `query_sections` | List sections with plant counts |
| Read | `get_plant_detail` | Full plant info + all associated logs |
| Read | `query_logs` | Search logs by type, section, or species |
| Read | `get_inventory` | Current plant counts for section/species |
| Read | `search_plant_types` | Search plant type taxonomy |
| Read | `get_all_plant_types` | Full taxonomy dump with 5-min cache |
| Write | `create_observation` | Log inventory count for a plant |
| Write | `create_activity` | Log field activity (watering, weeding, etc.) |
| Write | `update_inventory` | Reset inventory count on a plant |
| Write | `create_plant` | Create new plant asset in a section |
| Write | `archive_plant` | Mark a plant as archived/removed |
| Observe | `list_observations` | Fetch observations from Google Sheet |
| Observe | `update_observation_status` | Update review status on Sheet |
| Observe | `import_observations` | Pull approved observations into farmOS |
| Memory | `write_session_summary` | Save session summary to Team Memory |
| Memory | `read_team_activity` | Read recent team summaries |
| Memory | `search_team_memory` | Search across all summaries |
| Plant Type | `add_plant_type` | Add new species (dual-write: farmOS + Sheet) |
| Plant Type | `update_plant_type` | Update species metadata (dual-write) |
| Plant Type | `reconcile_plant_types` | Compare Sheet vs farmOS, report drift |
| Site | `regenerate_pages` | Re-export + regenerate HTML (Agnes only) |
| Site | `get_farm_overview` | Farm overview stats |
| Knowledge | `search_knowledge` | Search KB by query + optional category |
| Knowledge | `list_knowledge` | Browse KB entries by category |
| Knowledge | `add_knowledge` | Add new KB entry (tutorial, guide, SOP, etc.) |
| Knowledge | `update_knowledge` | Update existing KB entry |

**Source files (TypeScript — `mcp-server-ts/`):**
- `src/tools/` — Tool definitions grouped by domain (read, write, observe, memory, plant-types, knowledge, site)
- `src/clients/` — FarmOSClient (native fetch, OAuth2), AppsScriptClient base + 4 subclasses
- `src/helpers.ts` — Date parsing, formatters, name builders, metadata parsers

**Python fallback source files (`mcp-server/`):**
- `server.py` — FastMCP server, tool definitions, orchestration logic
- `farmos_client.py` — farmOS JSON:API HTTP client (OAuth2, pagination, CONTAINS filters)
- `observe_client.py`, `memory_client.py`, `plant_types_client.py` — Apps Script HTTP clients
- `helpers.py` — Date parsing, formatters, name builders, metadata parsers

**Deployment (March 20 — all remote):**

| User | OS | Connection | Notes |
|---|---|---|---|
| Agnes | macOS | `npx mcp-remote` → Railway | Also has Python STDIO fallback in repo |
| Claire | Windows | `npx mcp-remote` → Railway | No local Python/venv needed |
| James | macOS | `npx mcp-remote` → Railway | No local Python/venv needed |
| Olivier | Windows | `npx mcp-remote` → Railway | No local Python/venv needed |

**No file copying needed for updates** — deploy to Railway and all users get new tools immediately.

**Env vars (on Railway — 9 total):**
- FARMOS_URL, FARMOS_USERNAME, FARMOS_PASSWORD
- OBSERVE_ENDPOINT, MEMORY_ENDPOINT, PLANT_TYPES_ENDPOINT, KNOWLEDGE_ENDPOINT
- NODE_ENV, CREDENTIALS_PATH

### 3. Apps Script Endpoints

Four Google Apps Script deployments, all on fireflyagents.com account:

| Endpoint | Type | Sheet | Purpose |
|---|---|---|---|
| **Observation Code.gs** (v3) | Standalone | "Firefly Corner - Field Observations" | Field observation capture + review workflow |
| **TeamMemory.gs** | Bound | "Firefly Corner - Team Memory" | Session summaries, priorities, team coordination |
| **PlantTypes.gs** | Bound | "Firefly Corner - Plant Types v7" | Plant taxonomy sync, dual-write target |
| **KnowledgeBase.gs** | Bound | "Firefly Corner - Knowledge Base" | Farm knowledge library (tutorials, guides, SOPs) |

**Key patterns:**
- All use `Content-Type: text/plain` for POST (avoids CORS preflight)
- Observation Code.gs is STANDALONE (uses `openById()`) — others are BOUND (use `getActiveSpreadsheet()`)
- fireflycorner.com.au Workspace account returns 403 for anonymous POST — all deployed on fireflyagents.com

### 4. Python Scripts — Data Pipeline

All scripts run in the main project venv (`venv/` at repo root) with Python 3.13 + farmOS.py + pydantic v1.

| Script | Purpose | Input → Output |
|---|---|---|
| `export_farmos.py` | Export farmOS → sections.json | farmOS API → `site/src/data/sections.json` |
| `generate_site.py` | Generate HTML pages | sections.json + plant_types.csv → `site/public/*.html` |
| `generate_qrcodes.py` | Generate QR code images | sections.json → `site/public/qrcodes/*.png` |
| `import_fieldsheets.py` | Import spreadsheets → farmOS | sections.json → farmOS API |
| `import_plants.py` | Import plant types → farmOS | plant_types.csv → farmOS taxonomy |
| `import_historical.py` | Import backdated logs | renovation .xlsx → farmOS logs |
| `parse_fieldsheets.py` | Parse Claire's spreadsheets | .xlsx → sections.json (Phase 0 shortcut) |

**Foundation pipeline (current):**
```
farmOS → export_farmos.py --sections-json → sections.json
                                               ↓
                              plant_types.csv → generate_site.py → HTML pages
                                                                      ↓
                                                              git push → GitHub Pages
```

### 5. QR Landing Pages — Visitor/Farmhand Interface

| Aspect | Detail |
|---|---|
| **Hosting** | GitHub Pages (auto-deploy via `.github/workflows/deploy-pages.yml`) |
| **URL** | https://agnesfa.github.io/firefly-farm-ai/ |
| **Pages** | 75 total: 37 view + 37 observe + 1 index (P2 only, P1 pages pending) |
| **Design** | Mobile-first (430px), botanical field guide aesthetic |
| **Fonts** | Playfair Display (headings), DM Sans (body) |
| **Colors** | Forest green palette, strata-coded (emergent→low: dark→light green) |

### 6. Knowledge Capture Pipeline (NEW — Olivier, March 16)

| Aspect | Detail |
|---|---|
| **Capture** | Phone camera + voice recorder in field |
| **Sync** | Dropbox auto-sync to desktop, folders per activity |
| **Transcription** | Whisper (local, no cloud) — .m4a → .txt |
| **Processing** | Claude Desktop + reportlab → illustrated PDF tutorials |
| **Storage** | Olivier's Dropbox outputs folder (not yet centralized) |

**Tutorials produced:**
- Nursery Spiral Irrigation & Maintenance Guide (illustrated PDF)
- FFC Radio documentation (6 playlists, bilingual FR/EN PDF)
- Compost fundamentals (Berkeley method, 3 principles)

**Open question:** These tutorials need a shared, structured home accessible to both AI and humans. See "Shared Knowledge & Media System" in roadmap.

### 7. Knowledge Base (Files)

| File | Purpose | Records |
|---|---|---|
| `knowledge/plant_types.csv` | Master plant database | 218 species (v7) |
| `knowledge/seed_bank.csv` | Seed inventory | 244 records |
| `knowledge/plant_type_name_mapping.csv` | v6→v7 migration map | 237 rows |

### 8. Test Harness

| Aspect | Detail |
|---|---|
| **Tests** | 98 TypeScript tests (mcp-server-ts/) + 104 Python tests (mcp-server/) |
| **Runtime** | <1.1s (TS), <1s (Python), zero network calls |
| **TS layers** | helpers (34), farmos-client (18), tools-read (7), tools-write (12), import-workflow (11), client-factory (16) |
| **Python layers** | Unit (helpers) → HTTP-mocked (clients) → Integration (tools) |

---

## Data Flow Summary

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Claire's     │     │ QR Observe   │     │ Claude       │     │ Olivier's    │
│ Spreadsheets │     │ Pages        │     │ Desktop      │     │ Tutorials    │
│ (.xlsx)      │     │ (observe.js) │     │ (MCP tools)  │     │ (PDF/audio)  │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │ import             │ POST               │ API              │ future
       │ scripts            │                    │ calls            │ integration
       │                    ▼                    │                  │
       │            ┌──────────────┐             │                  │
       │            │ Google Sheet │◄────────────┤                  │
       │            │ (staging)    │             │                  │
       │            └──────┬───────┘             │                  │
       │                   │ import              │                  │
       │                   │ (via MCP)           │                  │
       ▼                   ▼                     ▼                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                      farmOS (source of truth)                           │
│                      margregen.farmos.net                               │
│                                                                        │
│  Plant types (224) ←→ Google Sheet (dual-write via Plant Types tool)    │
│  Team Memory Sheet ←→ Session summaries, priorities, coordination      │
└──────────────────────────┬──────────────────────────────────────────────┘
                           │ export
                           ▼
                   ┌──────────────┐
                   │ sections.json│
                   └──────┬───────┘
                          │ generate
                          ▼
                   ┌──────────────┐
                   │ HTML pages   │
                   └──────┬───────┘
                          │ git push
                          ▼
                   ┌──────────────┐
                   │ GitHub Pages │
                   │ (live site)  │
                   └──────────────┘
```

**Key principle:** All data flows INTO farmOS. Everything generated flows OUT of farmOS. farmOS is never bypassed. Google Sheets serve as staging (observations) and sync targets (plant types, team memory), not as sources of truth.

---

## Authentication & Access

| System | Auth Method | Who Has Access |
|---|---|---|
| farmOS API | OAuth2 password grant | Agnes (direct), MCP server (programmatic) |
| farmOS Web UI | Username/password | Agnes |
| MCP Server (Railway) | Per-user API keys via `npx mcp-remote` | Agnes, Claire, James, Olivier (remote HTTP) |
| Apps Script (3 endpoints) | Anonymous POST (no auth) | Anyone with URL |
| Google Sheets (3) | Google account sharing | Agnes (fireflyagents.com) |
| GitHub repo | Git SSH key | Agnes |
| GitHub Pages | Public (no auth) | Everyone |
| Team Memory | Via MCP tools (no direct access) | All 4 team members |

**Security notes:**
- farmOS credentials stored as env vars on Railway (not on client machines)
- Per-user API keys in credentials.json on Railway for MCP server access (Phase 1b — live March 19)
- Apps Script endpoints are unauthenticated — rely on obscurity of URL
- James and Claire farmOS passwords need rotation (exposed during setup)

---

## Technology Stack

| Layer | Technology | Version/Notes |
|---|---|---|
| Farm management | farmOS (Drupal) | 3.x, Farmier managed hosting |
| API | JSON:API | Drupal core, OAuth2 |
| MCP framework | FastMCP | Python SDK, pydantic v2 |
| AI interface | Claude Desktop | STDIO MCP transport |
| Development | Claude Code | Agnes's dev environment |
| Scripts | Python | 3.13 (NOT 3.14 — pydantic v1 compat) |
| farmOS client (scripts) | farmOS.py | pydantic v1, main venv |
| farmOS client (MCP) | Raw HTTP/requests | pydantic v2, separate venv |
| Site generation | Jinja2-style (inline) | Python string templates |
| Frontend (pages) | Vanilla HTML/CSS/JS | No framework, mobile-first |
| Frontend (observe) | Vanilla JS | localStorage, fetch API |
| Backend (endpoints) | Google Apps Script | 3 deployments on fireflyagents.com |
| Storage (observe) | Google Sheets + Drive | Structured + raw JSON + photos |
| Storage (memory) | Google Sheets | Team Memory + Plant Types |
| Hosting (pages) | GitHub Pages | Auto-deploy via GitHub Actions |
| Version control | Git/GitHub | agnesfa/firefly-farm-ai |
| Knowledge capture | Whisper + Claude Desktop | Local transcription → PDF |
| File sync | Dropbox | Olivier's tutorial pipeline |

---

## Known Limitations

1. ~~**MCP transport is local STDIO**~~ → **RESOLVED March 20**: Phase 1b deployed on Railway, all 4 users migrated to remote `npx mcp-remote`. Updates deploy once to Railway, no file copying.
2. **No offline support** for observe pages — localStorage queue exists but media stripped when offline
3. **No auth on observe endpoints** — anyone with the Apps Script URL can submit
4. **Site regeneration is manual** — requires running export + generate + git push
5. **Syntropic metadata in descriptions** — text-based, not structured farmOS fields (until Phase 4)
6. **Single farmOS user** — all API access uses one credential set (Agnes's farm_manager account)
7. **No photo integration with farmOS** — photos go to Google Drive only; upload_file client method exists but not wired to tools
8. **farmOS.py pagination cap** — unreliable beyond ~250 entries; scripts use raw HTTP workaround
9. **OAuth2 tokens expire** — MCP server raises errors (fixed March 11) but requires restart
10. **P1 pages not generated** — P1 land assets exist in farmOS but no plant data imported yet
11. **Knowledge docs fragmented** — Olivier's tutorials in Dropbox, observations in Drive, code in GitHub — no unified system
12. **No P1 QR codes** — P1 has physical poles but QR codes pending data import
13. **Team Memory unstructured** — no formal escalation mechanism, no acknowledgment workflow, variable summary quality
