# Firefly Corner — Roadmap & Plan

> Updated March 20, 2026. Reflects Phase 1b remote deployment, all 4 machines migrated, Phase KB quick wins, Claire/Olivier departure.

---

## Completed Phases

### Phase 0: Landcare Demo (March 7–10, 2026) ✅
- 75 HTML pages (37 view + 37 observe + 1 index) for all 5 paddock 2 rows
- QR codes generated and printed for all 37 sections
- Live farmOS import: 404 plant assets, 442 observation logs, 0 failures
- Pipeline: fieldsheets → parse → sections.json → generate → GitHub Pages

### Phase 0.5: Plant Types Foundation (March 5–6, 2026) ✅
- plant_types.csv v7: 218 records, 17 columns, `farmos_name` as canonical key
- farmOS taxonomy: 224 plant types (218 CSV + 6 additions from field observations and team work)
- v6→v7 migration: 16 renames, 15 archives, 157 creates
- Google Sheet "Firefly Corner - Plant Types v7" shared with Claire
- Plant Types Apps Script endpoint for dual-write (farmOS + Sheet)

### Phase A: Field Observation System (March 7–9, 2026) ✅
- observe.js: vanilla JS forms (Quick Report, Full Inventory, Section Comment, Add New Plant)
- Apps Script backend (Code.gs v3): Sheet append + Drive JSON save + delete/media handlers
- 86+ real field observations from Claire, James, Hadrien
- 131 approved → imported to farmOS (64 inventory updates, 11 new plants, 5 new types)
- Review workflow: pending → reviewed → approved → imported (+ rejected)

### Phase H1: Historical Log Import (March 9, 2026) ✅
- 422 backdated logs from Claire's renovation spreadsheets
- R1-R3: 392 logs | R4/R5: 30 logs
- 201 dead/removed plants identified (no farmOS assets yet — Phase H2)

### Phase 1a: farmOS MCP Server — Local STDIO (March 9–17, 2026) ✅
- **23 tools** (7 read + 5 write + 3 observation + 3 memory + 3 plant type mgmt + 2 site)
- 5 resources, 3 prompts
- Deployed to **all 4 users**: Agnes (macOS), Claire (Windows), James (macOS), Olivier (Windows)
- Error handling: raises on auth failures (fixed March 11)
- Duplicate observation bug: fixed March 17 (log names now include date)
- Dynamic priorities system via Team Memory (no file changes needed for priority updates)
- Dual-write plant types to farmOS + Google Sheet
- `get_all_plant_types` with 5-min cache (solves batch lookup bottleneck)
- `archive_plant` and `reconcile_plant_types` tools

### P1 + Nursery Foundation (March 16–17, 2026) ✅
- **P1 land assets created in farmOS**: 15 sections across P1R1 (6), P1R3 (5), P1R5 (4)
- **P1ED1.0-5** drain-end section created as land asset under both P1 and P1R1
- **Nursery fully zoned in farmOS**: 20 new structure assets (NURS.*)
  - 3 shelves × 4 positions (NURS.SH1-1 through NURS.SH3-4)
  - Ground areas: NURS.BCK, NURS.FRT, NURS.GR, NURS.GL, NURS.HILL, NURS.STRB
  - **Seed bank = NURS.FRDG** (old fridge for sealed dry seed storage)
  - NURS.FRZR (freezer)
  - Special Cares Area, Incubator Chamber (greenhouse type)
- Approved by team, all assets live in farmOS

### Team Rollout (March 11–14, 2026) ✅
- All 4 users operational with Claude Desktop + MCP server
- Team context files with dynamic priorities (pull from Team Memory at session start)
- Team briefing document created and distributed
- Windows MSIX sandbox issue resolved (`winget install Anthropic.Claude`)

### Team Memory System (March 13–15, 2026) ✅
- Apps Script backend (TeamMemory.gs) on fireflyagents.com
- 3 tools: `write_session_summary`, `read_team_activity`, `search_team_memory`
- Dynamic priorities via `user="Priorities"` entries
- Active use by all 4 team members

### Phase 1b: Remote MCP Server — Railway (March 19–20, 2026) ✅
- Ported all tools from Python to TypeScript FA Framework plugin architecture
- **29 tools**, 98 tests (<1.1s), deployed to Railway ($5/mo Hobby plan)
- 3 production fixes: farmOS auth (env vars), Apps Script redirect (native fetch), cold start keep-alive (4-min self-ping)
- **March 20: All 4 team machines migrated** from local Python STDIO to remote `npx mcp-remote`
- Per-user API keys via credentials.json; no local Python/venv needed on client machines
- Deploy once to Railway → all users get updates immediately
- Python MCP server kept as Agnes's local STDIO fallback

### Phase KB Quick Wins (March 20, 2026) ✅
- Knowledge Base Apps Script endpoint (KnowledgeBase.gs) deployed
- 4 KB tools: `search_knowledge`, `list_knowledge`, `add_knowledge`, `update_knowledge`
- `topics` field added to KB schema (farm domain filter: nursery, compost, irrigation, etc.)
- `query_sections` enhanced to return all location types (nursery, compost, structures)
- Full design: `claude-docs/phase-kb-knowledge-crossref.md`

### Claire & Olivier Departure (March 21, 2026)
- Last working day: March 19 (Friday)
- Claire departing March 21 (Saturday) — agronomic knowledge captured in farmOS + Team Memory
- Olivier departing March 21 (Saturday) — tutorial pipeline established, compost docs handed to James
- Post-departure: Agnes + James continue with remote MCP (no local machine dependencies)

---

## Current State — What Works Today (March 20, 2026)

| Capability | Status | How |
|---|---|---|
| View planted sections (P2) | ✅ Working | QR code → GitHub Pages landing page |
| Log field observations | ✅ Working | QR observe page → Apps Script → Google Sheet |
| Query farmOS (plants, sections, logs) | ✅ Working | Claude Desktop + remote MCP (29 tools, 4 users via Railway) |
| Create observations/activities in farmOS | ✅ Working | Claude Desktop + remote MCP |
| Review & import observations to farmOS | ✅ Working | Claude Desktop + MCP tools |
| Generate pages from farmOS | ✅ Working | export_farmos.py → generate_site.py |
| Manage plant types (add/update/reconcile) | ✅ Working | MCP tools, dual-write to farmOS + Google Sheet |
| Team coordination | ✅ Working | Team Memory (write summaries, read activity, search) |
| Knowledge capture (field tutorials) | ✅ Working | Olivier's workflow: phone → Dropbox → Whisper → Claude → PDF |
| Farm knowledge library | ✅ Working | Knowledge Base (search, browse, add, update) via MCP + Apps Script |

### farmOS Data Snapshot (March 17, 2026)

| Entity | Count | Notes |
|--------|-------|-------|
| Plant assets | 441 | +37 since March 9 (field obs imports + team work) |
| Land assets | 96 | +3: P1 sections (15), P1ED1, P2 transects |
| Structure assets | 37 | +20: nursery zones (NURS.*) |
| Material assets | 14 | New category |
| Group assets | 11 | New category |
| Observation logs | 772 | +120: ongoing field observations |
| Transplanting logs | 307 | +69 |
| Activity logs | 78 | +15 |
| Plant types | 224 | +1 since March 9 |
| Total logs | 1,173 | Up from ~1,033 |
| Sections (land) | 54 | 37 P2 + 15 P1 + P1ED1 + new P2 |

---

## This Week — March 17–22 (Claire & Olivier Departure Week)

> Claire and Olivier depart March 21 (Saturday). Last working day was March 19.

### Completed This Week
- [x] Fix duplicate observation log bug (server.py) ✅
- [x] Apply Claire's 9 pending inventory corrections ✅
- [x] Ship Phase 1b remote MCP on Railway ✅ (March 19)
- [x] All 4 team machines migrated to remote MCP ✅ (March 20)
- [x] Phase KB quick wins deployed ✅ (March 20: topics filter, query_sections all locations)
- [x] Knowledge Base Apps Script + 4 MCP tools ✅

### Agnes — Remaining
- [ ] Review Claire's P1 data answers → build P1 import pipeline
- [ ] Import P1 planting data to farmOS (once Claire answers 16 questions)
- [ ] Import nursery inventory from Claire's session data
- [ ] Import seed bank data as Seed assets (location: NURS.FRDG)
- [ ] Regenerate pages (P2 updates + P1 new pages)
- [ ] Review pending observations (29 pending from March 17-18)

### James — Remaining
- [ ] Daily team activity review
- [ ] Knowledge transfer sessions (Mon–Sat schedule)
- [ ] Operational flow documentation
- [ ] Post-March 22: primary non-technical farm operator

---

## Next Priorities — Short Term

### 1. ~~Phase 1b: Remote MCP Server~~ → COMPLETED March 20 ✅
- [x] Port Python MCP → TypeScript using FA Framework ✅
- [x] Deploy to Railway ($5/mo) ✅ (March 19)
- [x] All 4 users migrated to `npx mcp-remote` ✅ (March 20)
- [x] Per-user API keys, shared farmOS credentials on server ✅
- Stale session handling after deploys: workaround is restart Claude Desktop
- Full plan: `claude-docs/phase1b-plan-fa-framework.md`

### 2. P1 Data Import
- [ ] Parse P1 spreadsheets (P1R1, P1R3, P1R5 — 3 odd rows only)
- [ ] Handle P1ED1.0-5 drain-end section (land asset exists)
- [ ] Import plant assets to 15 P1 sections
- [ ] Generate QR landing pages for P1
- **Blocked by:** Claire's answers to 16 species/data questions

### 3. Nursery + Seed Bank Import
- [ ] Import nursery plants to NURS.* structure assets
- [ ] Create Seed assets from Olivier's inventory → location: NURS.FRDG
- [ ] Implement Seed→Plant lifecycle workflow
- **Foundation ready:** 20 nursery zones in farmOS, seed bank = NURS.FRDG

### 4. Shared Knowledge & Media System (PARTIALLY DONE)
- [x] Knowledge Base Apps Script + Google Sheet ✅ (March 17)
- [x] 4 MCP tools: search, list, add, update ✅
- [x] `topics` field for farm domain filtering ✅ (March 20)
- [ ] Consolidate: Dropbox (Olivier's tutorials), Google Drive (observations), GitHub (code/data)
- [ ] `farm_context` composite tool (cross-references farmOS + KB + plant types in one call)
- [ ] Topic-to-farmOS mapping config (topics resolve to farmOS section prefixes)
- [ ] Source-material category + Drive folder convention for raw materials
- **Design doc:** `claude-docs/phase-kb-knowledge-crossref.md`

### 5. Password Rotation
- [ ] Rotate James's farmOS password (exposed during setup)
- [ ] Rotate Claire's farmOS password (exposed during setup)
- [ ] Update env vars in their Claude Desktop configs

---

## Medium Term — Weeks 3–6

### Phase B: Observe Page Enhancements
- [ ] Photo compression improvements (currently 1200px max, 0.7 JPEG)
- [ ] Audio recording for voice observations
- [ ] Offline queue with IndexedDB (currently localStorage, media stripped offline)

### Phase H2: Dead Plant Assets
- [ ] Create farmOS assets for 201 historical dead/removed plants
- [ ] Low priority — historical completeness, not operational need

### Phase 2: Natural Language Farm Logging (VALIDATED)
- [x] Claire uses Claude + MCP to log field activities ✅ (already happening)
- [x] "P2R2.3-9 pigeon pea now has 3" → observation log ✅
- [x] Validates "Claude IS the UI" ✅
- [ ] Refine based on team usage patterns

### Media Management Strategy
- [ ] Photos currently go to Google Drive only (not farmOS)
- [ ] farmOS supports binary POST for file uploads (image field on all assets/logs)
- [ ] MCP server has upload_file client method (not yet wired to tools)
- [ ] Decision needed: farmOS file upload? Keep Drive? Both?

### Site Regeneration Automation
- [ ] Currently manual: run export → generate → push
- [ ] Auto-regenerate QR pages on farmOS data changes (webhook/cron trigger)
- [ ] Options: GitHub Actions workflow triggered by MCP tool, farmOS webhook, or scheduled cron task
- [ ] MCP `regenerate_pages` tool exists (Agnes only — needs git repo)

---

## Longer Term — Months 2–3

### Phase 3: Nursery & Seed Bank (foundation ready)
- [ ] Seed→Plant lifecycle: Seed asset (NURS.FRDG) → Seeding log → Plant asset (nursery shelf) → Transplanting log → Plant in field
- [ ] Nursery structure fully zoned (20 NURS.* assets ready)
- [ ] Seed germination tracking
- [ ] Propagation tracking (cuttings, division)

### Harvest Tracking
- [ ] 2–3 months of WhatsApp harvest data (summer 2025/2026)
- [ ] Parse: "3kg tomatoes from P1R1" → farmOS harvest log
- [ ] Need WhatsApp export or structured capture going forward

### Farm Knowledge Library
- [ ] Curated collection of tutorials, guides, SOPs from Olivier's + Claire's knowledge
- [ ] Accessible to WWOOFers and future farm workers
- [ ] Versioned, searchable, AI-accessible
- [ ] Possible: GitHub Pages section, or dedicated knowledge platform

---

## Long Term — Month 3+

### Phase 4: farm_syntropic Drupal Module
- [ ] Custom farmOS module with proper fields on plant_type taxonomy
- [ ] Strata, succession_stage, plant_functions as structured data (not in descriptions)
- [ ] New taxonomies: strata, succession_stage, plant_function
- [ ] New asset types: Consortium
- [ ] New log types: Pruning, Biomass
- [ ] Data migration from current description text to structured fields
- [ ] **Trigger:** Self-host farmOS on Hetzner + Coolify when this phase starts

### Phase 5: Multi-User & Advanced AI
- [ ] Shared Claude Project for the team (when available)
- [ ] Voice input for field use
- [ ] Live site updates from farmOS data changes
- [ ] Knowledge base evolution (which consortiums work, yield patterns)
- [ ] WhatsApp integration for harvest logs
- [ ] Claude mobile project with plant taxonomy for field queries

---

## Not Planned / Deferred

| Item | Why Deferred |
|---|---|
| Custom mobile app | Claude mobile IS the app |
| Multi-agent orchestration | One good agent first |
| Custom farmOS dashboards | Use API, not UI |
| Weather integration | Nice-to-have, not critical |
| Automated notifications | Need use cases first |
| farmOS self-hosting | Stay on Farmier until Phase 4 (custom Drupal modules) |

---

## Open Questions

1. **Shared knowledge/media system** — How to unify Dropbox (tutorials), Google Drive (observations), GitHub (code) into one coherent system accessible to both AI and humans?
2. **Media strategy** — Google Drive vs farmOS vs both for photos? MCP upload_file is ready but not wired.
3. **Site regeneration trigger** — Manual, webhook, GitHub Actions, or scheduled?
4. **Claude mobile for field workers** — How to give Olivier/WWOOFers plant taxonomy access on mobile?
5. **Volunteer access** — How do WWOOFers interact beyond QR pages?
6. **Harvest capture** — WhatsApp parsing vs structured input form?
7. **Post-March 22 operations** — James manages with remote MCP (no local machine dependencies). Agnes provides technical support remotely. Claire and Olivier departed March 21.

---

*Updated March 20, 2026.*
