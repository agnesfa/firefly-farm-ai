# Firefly Corner — Roadmap & Plan

> As of March 11, 2026. Agnes: annotate this doc and bring back to discuss.

---

## Completed Phases

### Phase 0: Landcare Demo (March 7–10, 2026) ✅
- 75 HTML pages (37 view + 37 observe + 1 index) for all 5 paddock 2 rows
- QR codes generated and printed for all 37 sections
- Live farmOS import: 404 plant assets, 442 observation logs, 0 failures
- Pipeline: fieldsheets → parse → sections.json → generate → GitHub Pages

### Phase 0.5: Plant Types Foundation (March 5–6, 2026) ✅
- plant_types.csv v7: 218 records, 17 columns, `farmos_name` as canonical key
- farmOS taxonomy: 223 plant types (218 CSV + 5 field observation additions)
- v6→v7 migration: 16 renames, 15 archives, 157 creates

### Phase A: Field Observation System (March 7–9, 2026) ✅
- observe.js: vanilla JS forms (Quick Report, Full Inventory, Section Comment, Add New Plant)
- Apps Script backend: Sheet append + Drive JSON save
- 86 real field observations from Claire, James, Hadrien
- 131 approved and imported to farmOS (64 inventory updates, 11 new plants, 5 new types)
- Review workflow: pending → reviewed → approved → imported (+ rejected)

### Phase H1: Historical Log Import (March 9, 2026) ✅
- 422 backdated logs from Claire's renovation spreadsheets
- R1-R3: 392 logs | R4/R5: 30 logs
- 201 dead/removed plants identified (no farmOS assets yet — Phase H2)

### Phase 1a: farmOS MCP Server — Local STDIO (March 9–11, 2026) ✅
- 13 tools (6 read + 4 write + 3 observation management)
- 5 resources, 3 prompts
- Deployed to Agnes (macOS), Claire (Windows), James (macOS)
- Error handling fix March 11: raises on auth failures instead of silent empty results

### Section ID Verification (March 11, 2026) ✅
- All 37 active farmOS section IDs match QR page IDs exactly
- Data integrity verified: 414 plants + 1033 logs, 0 mismatches
- No QR reprinting needed

---

## Current State — What Works Today

| Capability | Status | How |
|---|---|---|
| View planted sections | ✅ Working | QR code → GitHub Pages landing page |
| Log field observations | ✅ Working | QR observe page → Apps Script → Google Sheet |
| Query farmOS (plants, sections, logs) | ✅ Working | Claude Desktop + MCP server (local) |
| Create observations/activities in farmOS | ✅ Working | Claude Desktop + MCP server |
| Review & import observations to farmOS | ✅ Working | Claude Desktop + MCP tools |
| Generate pages from farmOS | ✅ Working | export_farmos.py → generate_site.py |

---

## Next Priorities — Short Term

### 1. MCP Server Deployment to Claire & James
- [ ] Copy updated `farmos_client.py` to both machines (error handling fix)
- [ ] James: `~/firefly-mcp/` on Mac
- [ ] Claire: `C:\firefly-mcp\` on Windows
- [ ] Both restart Claude Desktop after update
- **Notes/Questions:**

### 2. Password Rotation
- [ ] Rotate James's farmOS password (exposed during setup)
- [ ] Rotate Claire's farmOS password (exposed during setup)
- [ ] Update env vars in their Claude Desktop configs
- **Notes/Questions:**

### 3. Media Management Strategy
- [ ] Photos currently go to Google Drive only (not farmOS)
- [ ] Decision needed: farmOS file upload? Keep Drive? Both?
- [ ] farmOS supports binary POST for file uploads (image field on all assets/logs)
- [ ] Architecture question: photos on observations → which farmOS log?
- **Notes/Questions:**

---

## Medium Term — Weeks 2–4

### Phase 1b: MCP Server HTTP Transport
- [ ] Move from local STDIO to remote HTTP server
- [ ] Removes need to copy files to each machine
- [ ] Single server, all users connect remotely
- [ ] API key or OAuth2 auth for MCP connections
- [ ] Where to host? (VPS, Cloudflare Worker, farm server?)
- **Notes/Questions:**

### Phase B: Observe Page Enhancements
- [ ] Photo compression improvements (currently 1200px max, 0.7 JPEG)
- [ ] Audio recording for voice observations
- [ ] Offline queue with IndexedDB (currently localStorage, media stripped offline)
- **Notes/Questions:**

### Phase H2: Dead Plant Assets
- [ ] Create farmOS assets for 201 historical dead/removed plants
- [ ] These exist in renovation spreadsheets but have no farmOS representation
- [ ] Low priority — historical completeness, not operational need
- **Notes/Questions:**

### Phase 2: Claire's First Real Log
- [ ] Claire uses Claude + MCP in natural language to log a field activity
- [ ] "I watered P2R3 today" → activity log in farmOS
- [ ] "P2R2.3-9 pigeon pea now has 3, lost 2 to frost" → observation log
- [ ] Validates the "Claude IS the UI" architecture decision
- **Notes/Questions:**

---

## Longer Term — Months 2–3

### Phase 3: Nursery & Seed Bank
- [ ] Import 244 seed records from seed_bank.csv as farmOS Seed assets
- [ ] Implement native Seed→Plant lifecycle workflow
- [ ] Nursery shelf location tracking (Structure assets exist: 17)
- [ ] Seed germination tracking
- **Notes/Questions:**

### Site Regeneration Automation
- [ ] Currently manual: run export → generate → push
- [ ] Could be triggered by farmOS webhook or scheduled task
- [ ] Or run on-demand via Claude when data changes
- **Notes/Questions:**

### Harvest Tracking
- [ ] 2–3 months of WhatsApp harvest data (summer 2025/2026)
- [ ] Parse: "3kg tomatoes from P1R1" → farmOS harvest log
- [ ] Need WhatsApp export or structured capture going forward
- **Notes/Questions:**

---

## Long Term — Month 3+

### Phase 4: farm_syntropic Drupal Module
- [ ] Custom farmOS module with proper fields on plant_type taxonomy
- [ ] Strata, succession_stage, plant_functions as structured data (not in descriptions)
- [ ] New taxonomies: strata, succession_stage, plant_function
- [ ] New asset types: Consortium
- [ ] New log types: Pruning, Biomass
- [ ] Data migration from current description text to structured fields
- **Notes/Questions:**

### Phase 5: Multi-User & Advanced AI
- [ ] Shared Claude Project for the team (when available)
- [ ] Voice input for field use
- [ ] Live site updates from farmOS data changes
- [ ] Knowledge base evolution (which consortiums work, yield patterns)
- [ ] WhatsApp integration for harvest logs
- **Notes/Questions:**

---

## Not Planned / Deferred

| Item | Why Deferred |
|---|---|
| Custom mobile app | Claude mobile IS the app |
| Multi-agent orchestration | One good agent first |
| Custom farmOS dashboards | Use API, not UI |
| Weather integration | Nice-to-have, not critical |
| Automated notifications | Need use cases first |
| P1 (Paddock 1) data | Focus on P2 first |

---

## Open Questions

1. **HTTP transport hosting** — Where should the central MCP server live?
2. **Media strategy** — Google Drive vs farmOS vs both for photos?
3. **Site regeneration trigger** — Manual, webhook, or scheduled?
4. **P1 data** — When do we start tracking Paddock 1?
5. **Volunteer access** — How do WWOOFers interact beyond QR pages?
6. **Harvest capture** — WhatsApp parsing vs structured input form?

---

*Annotate this document and bring back to discuss priorities and decisions.*
