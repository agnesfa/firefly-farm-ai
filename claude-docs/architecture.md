# Firefly Corner — Technical Architecture

> Current prototype state as of March 11, 2026.

---

## System Overview

```
                                    ┌─────────────────────────┐
                                    │      farmOS (Drupal)     │
                                    │  margregen.farmos.net    │
                                    │                          │
                                    │  Source of truth for:    │
                                    │  - Plant assets (414)    │
                                    │  - Land assets (93)      │
                                    │  - Logs (1033+)          │
                                    │  - Plant types (223)     │
                                    │  - Inventory (computed)  │
                                    └──────────┬───────────────┘
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
          │  13 tools         │    │  export_farmos.py     │    │  Direct access    │
          │  5 resources      │    │  import_fieldsheets   │    │  (Agnes only)     │
          │  3 prompts        │    │  import_historical    │    │                   │
          │                   │    │  import_plants        │    └───────────────────┘
          │  Deployed to:     │    │                       │
          │  - Agnes (macOS)  │    │  Runs in: main venv   │
          │  - Claire (Win)   │    │  (Python 3.13 +       │
          │  - James (macOS)  │    │   farmOS.py/pydantic  │
          │                   │    │   v1)                 │
          │  Runs in: mcp     │    │                       │
          │  venv (pydantic   │    └───────────┬───────────┘
          │  v2, raw HTTP)    │                │
          └────────┬──────────┘                │
                   │                           │
            Claude Desktop              ┌──────▼──────┐
            (STDIO transport)           │ sections    │
                   │                    │ .json       │
          ┌────────▼──────────┐         │ (generated) │
          │  Claude AI        │         └──────┬──────┘
          │                   │                │
          │  Agnes: Claude    │         ┌──────▼──────────────┐
          │    Code + Desktop │         │  generate_site.py   │
          │  Claire: Desktop  │         │  + plant_types.csv  │
          │  James: Desktop   │         │  (enrichment)       │
          │                   │         └──────┬──────────────┘
          │  "Claude IS       │                │
          │   the UI"         │         ┌──────▼──────┐
          └───────────────────┘         │  75 HTML    │
                                        │  pages      │
                                        │  (static)   │
                                        └──────┬──────┘
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
                                    ┌────────▼─────────┐
                                    │  Google Apps      │
                                    │  Script (Code.gs) │
                                    │                   │
                                    │  fireflyagents.   │
                                    │  com account      │
                                    │                   │
                                    │  doPost: append   │
                                    │  doGet: read/list │
                                    └───────┬───────────┘
                                            │
                              ┌─────────────┼─────────────┐
                              │                           │
                    ┌─────────▼─────────┐      ┌──────────▼──────────┐
                    │  Google Sheet      │      │  Google Drive       │
                    │                    │      │                     │
                    │  "Firefly Corner   │      │  "Firefly Corner    │
                    │   - Field          │      │   AI Observations"  │
                    │   Observations"    │      │                     │
                    │                    │      │  Raw JSON per       │
                    │  1 row per plant   │      │  submission +       │
                    │  observation       │      │  photos (base64)    │
                    │                    │      │                     │
                    │  Status workflow:  │      │  Folder structure:  │
                    │  pending →         │      │  /{date}/{section}/ │
                    │  reviewed →        │      │                     │
                    │  approved →        │      └─────────────────────┘
                    │  imported          │
                    │                    │
                    └────────────────────┘
```

---

## Component Details

### 1. farmOS — Source of Truth

| Aspect | Detail |
|---|---|
| **Platform** | Drupal 10 + farmOS 3.x |
| **Hosting** | farmOS.net managed hosting |
| **URL** | https://margregen.farmos.net |
| **API** | JSON:API (Drupal core) |
| **Auth** | OAuth2 password grant |
| **Users** | Agnes (farm_manager scope) |

**Data model:**
- **Assets**: Plant (414), Land (93), Structure (17), Water (11), Equipment (3), Compost (5)
- **Logs**: Observation (~650), Transplanting (~238), Activity (63), Seeding (8)
- **Taxonomy**: plant_type (223 terms with syntropic metadata in descriptions)
- **Inventory**: Computed attribute on assets, derived from Quantity entities on logs

**Key design choices:**
- Plant type descriptions embed syntropic data (strata, succession, functions) as text until Phase 4 custom module
- Inventory uses `inventory_adjustment: "reset"` on observation logs for absolute counts
- Land asset hierarchy: Paddock → Row → Section (e.g., P2 → P2R3 → P2R3.14-21)
- Plant asset naming: `{date} - {species} - {section_id}`

### 2. MCP Server — AI ↔ farmOS Bridge

| Aspect | Detail |
|---|---|
| **Framework** | FastMCP (Python MCP SDK) |
| **Transport** | STDIO (local process per machine) |
| **Language** | Python 3.13 |
| **Venv** | Separate from main project (`mcp-server/venv/`) |
| **Why separate?** | pydantic v2 (FastMCP) conflicts with pydantic v1 (farmOS.py) |
| **HTTP client** | Raw `requests` library (not farmOS.py) |

**Tools (13):**

| Category | Tool | Purpose |
|---|---|---|
| Read | `query_plants` | Search plants by section, species, or status |
| Read | `query_sections` | List sections with plant counts |
| Read | `get_plant_detail` | Full plant info + all associated logs |
| Read | `query_logs` | Search logs by type, section, or species |
| Read | `get_inventory` | Current plant counts for section/species |
| Read | `search_plant_types` | Search plant type taxonomy |
| Write | `create_observation` | Log inventory count for a plant |
| Write | `create_activity` | Log field activity (watering, weeding, etc.) |
| Write | `update_inventory` | Reset inventory count on a plant |
| Write | `create_plant` | Create new plant asset in a section |
| Observe | `list_observations` | Fetch observations from Google Sheet |
| Observe | `update_observation_status` | Update review status on Sheet |
| Observe | `import_observations` | Pull approved observations into farmOS |

**Deployment:**
- Agnes: `mcp-server/` in repo, venv at `mcp-server/venv/`
- James: `~/firefly-mcp/` on macOS, local venv
- Claire: `C:\firefly-mcp\` on Windows, local venv
- Env vars passed via Claude Desktop config `env` block (no .env files on remote machines)

### 3. Python Scripts — Data Pipeline

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

### 4. QR Landing Pages — Visitor/Farmhand Interface

| Aspect | Detail |
|---|---|
| **Hosting** | GitHub Pages (auto-deploy via `.github/workflows/deploy-pages.yml`) |
| **URL** | https://agnesfa.github.io/firefly-farm-ai/ |
| **Pages** | 75 total: 37 view + 37 observe + 1 index |
| **Design** | Mobile-first (430px), botanical field guide aesthetic |
| **Fonts** | Playfair Display (headings), DM Sans (body) |
| **Colors** | Forest green palette, strata-coded (emergent→low: dark→light green) |

**View pages** show: section header, row navigation bar, plants grouped by strata, expandable cards with botanical details, function tags, succession indicators, log timelines.

**Observe pages** provide: Quick Report (condition per plant), Full Inventory (new counts), Section Comment, Add New Plant (222 species search + Unknown option).

### 5. Observation System — Field Data Capture

| Aspect | Detail |
|---|---|
| **Frontend** | `observe.js` — vanilla JS, no framework |
| **Backend** | Google Apps Script (`Code.gs`) on fireflyagents.com account |
| **Storage** | Google Sheet (structured) + Google Drive (raw JSON + photos) |
| **Auth** | None (anonymous POST, text/plain to avoid CORS preflight) |
| **Photo handling** | Client-side compression (1200px, 0.7 JPEG), base64 in payload |

**Data flow:**
```
Worker scans QR → observe page → fills form → POST to Apps Script
    → Sheet row created (1 per plant observation)
    → Drive JSON saved (1 per submission)
    → Photos saved to Drive folder

Later:
Claude (MCP) → list_observations → review in chat → update_observation_status
    → import_observations → farmOS logs created → Sheet status updated
```

### 6. Knowledge Base

| File | Purpose | Records |
|---|---|---|
| `knowledge/plant_types.csv` | Master plant database | 218 species |
| `knowledge/seed_bank.csv` | Seed inventory | 244 records |
| `knowledge/plant_type_name_mapping.csv` | v6→v7 migration map | 237 rows |

`plant_types.csv` columns: common_name, variety, farmos_name, botanical_name, crop_family, origin, description, lifespan_years, lifecycle_years, maturity_days, strata, succession_stage, plant_functions, harvest_days, germination_time, transplant_days, source.

---

## Data Flow Summary

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Claire's     │     │ QR Observe   │     │ Claude       │
│ Spreadsheets │     │ Pages        │     │ Desktop      │
│ (.xlsx)      │     │ (observe.js) │     │ (MCP tools)  │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │ import             │ POST               │ API
       │ scripts            │                    │ calls
       │                    ▼                    │
       │            ┌──────────────┐             │
       │            │ Google Sheet │             │
       │            │ (staging)    │             │
       │            └──────┬───────┘             │
       │                   │ import              │
       │                   │ (via MCP)           │
       ▼                   ▼                     ▼
┌─────────────────────────────────────────────────────┐
│                  farmOS (source of truth)            │
│                  margregen.farmos.net                │
└──────────────────────────┬──────────────────────────┘
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

**Key principle:** All data flows INTO farmOS. Everything generated (pages, QR codes, reports) flows OUT of farmOS. farmOS is never bypassed.

---

## Authentication & Access

| System | Auth Method | Who Has Access |
|---|---|---|
| farmOS API | OAuth2 password grant | Agnes (direct), MCP server (programmatic) |
| farmOS Web UI | Username/password | Agnes |
| MCP Server | Env vars (FARMOS_URL, _USERNAME, _PASSWORD) | Agnes, Claire, James (local) |
| Apps Script | Anonymous POST (no auth) | Anyone with URL |
| Google Sheet | Google account sharing | Agnes (fireflyagents.com) |
| GitHub repo | Git SSH key | Agnes |
| GitHub Pages | Public (no auth) | Everyone |

**Security notes:**
- farmOS credentials stored as env vars in Claude Desktop config (not .env files on remote machines)
- Apps Script endpoint is unauthenticated — relies on obscurity of URL
- James and Claire farmOS passwords need rotation (exposed during setup)

---

## Technology Stack

| Layer | Technology | Version/Notes |
|---|---|---|
| Farm management | farmOS (Drupal) | 3.x, managed hosting |
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
| Backend (observe) | Google Apps Script | fireflyagents.com account |
| Storage (observe) | Google Sheets + Drive | Structured + raw JSON |
| Hosting (pages) | GitHub Pages | Auto-deploy via GitHub Actions |
| Version control | Git/GitHub | agnesfa/firefly-farm-ai |

---

## Known Limitations

1. **MCP transport is local STDIO** — each user needs files copied to their machine; updates require manual deployment
2. **No offline support** for observe pages — localStorage queue exists but media stripped when offline
3. **No auth on observe endpoint** — anyone with the Apps Script URL can submit observations
4. **Site regeneration is manual** — requires running export + generate + git push
5. **Syntropic metadata in descriptions** — text-based, not structured farmOS fields (until Phase 4)
6. **Single farmOS user** — all API access uses one credential set (Agnes's farm_manager account)
7. **No photo integration with farmOS** — photos go to Google Drive only
8. **farmOS.py pagination cap** — unreliable beyond ~250 entries; scripts use raw HTTP workaround
9. **OAuth2 tokens expire** — MCP server now raises errors (fixed March 11) but requires restart
10. **No P1 data** — Paddock 1 not tracked yet
