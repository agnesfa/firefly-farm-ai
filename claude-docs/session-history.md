## 20. SESSION LOG

### March 4, 2026 — Repo Bootstrap & Foundation
- Consolidated repo from 3 sources (archive, old FireflyAgents dir, farm-tiles reference)
- Created GitHub repo, enabled GitHub Pages, deployed site
- Migrated export_farmos.py and import_plants.py with credential cleanup (hardcoded → .env)
- Fresh farmOS export: 156 assets, 126 logs, 104 taxonomy terms
- Generated 32 QR codes from live farmOS data
- Discovered: Jan 5 farmOS document had stale section IDs for P2R3
- Discovered: P2R2 section mismatch between farmOS and fieldsheets (later verified March 11: sections now aligned)
- Discovered: 126 plant types still need importing (23 name mismatches)
- Added Phase 0.5 (Plant Types Foundation) to roadmap
- Created claude-docs/ with design-and-roadmap.md

### March 5–6, 2026 — Plant Types v7 Migration (Phase 0.5 Complete)
- Redesigned plant_types.csv: v6 (180 records) → v7 (213 records, 17 columns)
- Introduced `farmos_name` as canonical key: `Common Name (Variety)` convention
- Built plant_type_name_mapping.csv: 237 rows mapping v6 → v7 with actions
- Created clean_plant_types_v7.py for the v6→v7 CSV transformation
- Built migrate_plant_types.py for farmOS taxonomy migration
- Executed migration: 16 renames, 15 archives, 48 description updates, 157 creates
- Fixed: `harvest_days` is not a valid farmOS plant_type field; zero values rejected
- Hit farmOS.py `iterate()` pagination bug: unreliable with 200+ terms
- Built fix_taxonomy.py with raw HTTP pagination to reliably verify/repair
- Final state: 213/213 v7 plant types verified in farmOS, 0 duplicates
- Created Google Sheet "Firefly Corner - Plant Types v7" for Claire
- Updated generate_site.py and import_plants.py for v7 column names

**Key learning:** farmOS.py's `client.term.iterate()` has unreliable pagination with 200+ terms. Use raw HTTP with `page[limit]=50` and follow `links.next` for complete results. Pattern captured in fix_taxonomy.py's `fetch_all_terms()`.

### March 7, 2026 — Spreadsheet Parsing + farmOS Import Script (All 3 Rows)
- Rewrote parse_fieldsheets.py to handle both v2 format (P2R2, P2R3) and P2R1 format
- Parsed all 3 field sheets: 18 sections (4 R1 + 7 R2 + 7 R3), 245 plant entries, 90 unique species
- Built species name normalization with explicit mapping dict + suffix stripping
- Added 2 missing plant types to CSV and farmOS: Citrus (Yuzu), Hyssop → total 215
- Updated date extraction: v2 uses D3 exact date, P2R1 parses "2025-MARCH-20" from merged A1
- Generated 18 HTML pages + index with all plant data
- Built complete import_fieldsheets.py script for farmOS import:
  - Creates Plant assets, Quantity entities (inventory counts), Observation logs (movement)
  - Uses per-name API queries for reliable idempotent existence checks
  - Features: `--dry-run`, `--row` filter, pre-validates plant types + sections
  - Plant naming: `{planted_date_label} - {farmos_name} - {section_id}`
- Dry-run success: 245 plants, 77 species, 18 sections, 0 failures
- Ran import_plants.py: created Citrus (Yuzu) + Hyssop in farmOS (2 created, 213 unchanged)
- Agnes printing QR codes and testing pages for Landcare demo

**Key learnings:**
- farmOS.py quantities: no `client.quantity.send()` method. Must use raw HTTP POST to `/api/quantity/standard`.
- farmOS.py `send()` auto-wraps in `{"data": ...}`. Raw HTTP `http_request(method="POST")` does NOT — must include wrapper.
- Plant unit UUID: `2371b79e-a87b-4152-b6e4-ea6a9ed37fd0`
- `inventory_adjustment: "reset"` sets absolute count on a plant asset.

### March 7, 2026 (continued) — All 5 Rows Live + Field Observation System

**Session 2: Observation System + R4/R5**

Part 1 — Field Observation System (Phase A):
- Built `site/public/observe.js` — vanilla JS form logic, localStorage observer name, Google Apps Script POST
- Built `Code.gs` reference for Google Apps Script backend (doPost handler, Sheet append, Drive save)
- Added `render_observe_page()` to generate_site.py — two-mode form (Quick Report + Full Inventory)
- Added floating action button (FAB) "📋 Record Observation" to all view pages
- Added `--observe-endpoint` CLI argument to generate_site.py
- Generated 18 observe pages alongside view pages
- Committed: "Add field observation system: observe pages, JS form logic, Apps Script backend" (42 files, 10181 insertions)

Part 2 — R4 and R5 Spreadsheets:
- Copied P2R4 and P2R5 spreadsheets from Agnes's Downloads
- P2R4 format: v2-like with dual count columns (Col E vs Col F), multiple inventory dates, GREENMANURE strata, copy-paste bug in A1 cell of last tab
- P2R5 format: "registration" format — Plant/Seed distinction in Col E, per-plant dates in Col H, inventory in Col I, native Kolala day plantings
- Added `parse_r4_section()` and `parse_r5_section()` to parse_fieldsheets.py
- Added ~25 new species name overrides for R4/R5 naming conventions
- Added 2 new plant types: Barley, Dianella → CSV now 217 records
- Parsed: 33 sections, 109 species, 109/109 matched — zero unmapped
- Fixed generate_site.py: handle count=None (uninventoried) plants with "—" badge
- Generated 67 pages (33 view + 33 observe + index)
- Committed: "Add P2R4 (8 sections) and P2R5 (7 sections) to site — all 5 rows now live"

Part 3 — farmOS Import:
- Imported Barley + Dianella to farmOS taxonomy (219 total plant types)
- Live import R4: 109 plants, 31 species, 8 sections, 0 failures
- Live import R5: 50 plants, 19 species, 6 sections (P2R5.38-44 skipped — not inventoried), 0 failures
- Final farmOS state: 219 plant types, 404 plant assets, 442 observation logs

**Key learnings:**
- R4 tab names are authoritative for section IDs — A1 cell has copy-paste errors
- R5 P/S column distinguishes plants from seeds; only "P" entries go to landing pages
- `p.get("count", 0)` returns None when key exists with value None — use `p.get("count") or 0`
- Plants with count=None (not yet inventoried) are distinct from count=0 (dead) — show with "—" badge
- Strata fill-in: when strata is None in parsed data, look up from plant_db (plant_types.csv)

### March 8, 2026 — Apps Script Deployment + QR Code Cleanup

- Updated CLAUDE.md and MEMORY.md with all March 7 session progress
- Regenerated QR codes from current sections.json (33 codes, matching all pages)
- Removed 24 stale QR codes from old farmOS export (different section boundaries)
- Agnes deployed Code.gs to fireflycorner.com.au Apps Script account (later switched to fireflyagents.com — see March 9)
- Regenerated all 33 observe pages with live Apps Script endpoint baked in
- Pushed to GitHub Pages — observation forms now wired to real backend

**Apps Script deployment details:**
- Account: fireflyagents.com (switched from fireflycorner.com.au due to 403 on anonymous POST)
- Endpoint: `https://script.google.com/macros/s/AKfycbxwWorskdbg8ZFpkYAzpo4ILGUNRhTi7HtQbxtYI38ws9vKSIlASAZHvpGIPrbHVBVY/exec`
- Sheet: "Firefly Corner - Field Observations" (ID: 1wLAIxcSE_DNWjZdhlmPtQacvxg1VxHkA70hvX6nGqRs)
- Drive: "Firefly Corner AI Observations" (ID: 1WE1eMNEn--xW6RT7lAGnh0MFfJh4WCPX)

### March 9, 2026 — Observation Fix + Gap Sections + Historical Import + MCP Server

**Session 1: Observation endpoint fix + gap sections**
- Fixed Apps Script 403: fireflycorner.com.au Workspace account blocked anonymous POST → switched all 37 observe pages to fireflyagents.com account endpoint
- Added 4 gap sections (P2R4.2-6, P2R4.14-20, P2R5.8-14, P2R5.22-29) with green manure data
- Added Broad Bean to plant_types.csv (218 total in CSV)
- Green manure boxes now display on 19 sections across R1-R5
- 37 total sections, 110 species, 75 pages generated
- Committed: "Add 4 gap sections" and "Switch observe pages to fireflyagents.com endpoint"

**Session 2: Phase H1 — Historical log import**
- Built `scripts/import_historical.py` — imports backdated transplanting + observation logs from Claire's renovation spreadsheets
- Handles 4 spreadsheet formats (r1, r2, r3, r3_shifted) across 17 renovation tabs
- Maps historical section boundaries to current farmOS sections
- R1-R3: 392 logs (122 planted, 137 inventory, 133 renovation), 201 unmatched dead plants
- Extended for R4/R5: 30 more logs (25 R4 spring, 5 R5 Kolala Day)
- Committed: "Add historical log importer" and "Extend with R4/R5 data"

**Session 3: Field observations analyzed**
- 14 field observations received from Claire (7) and James (7) — first real field data!
- James found species identification issues (app misidentifying Tallowood as Walnut)
- James noted observation form requires plant selection — requested general section comments
- Claire used both Quick Report and Full Inventory modes

**Session 4: Phase 1 — farmOS MCP Server built**
- Built `mcp-server/farmos_client.py` — raw HTTP client with OAuth2 password grant
  - Initially used farmOS.py, but pydantic v1/v2 conflict forced rewrite to raw HTTP
  - Created separate venv at `mcp-server/venv/` with pydantic v2 for FastMCP
- Built `mcp-server/helpers.py` — date parsing, response formatters
- Built `mcp-server/server.py` — FastMCP server with 10 tools, 5 resources, 3 prompts
- Fixed Markdown bold marker stripping: `.replace("**", "")` not `.strip("*")`
- Fixed log query returning 32/39 instead of 39 for P2R2.0-3: implemented `_fetch_logs_contains()` using farmOS CONTAINS filter to push filtering server-side, bypassing pagination cap
- All 10 tools tested against live farmOS — all passing
- NOT YET COMMITTED — waiting for Agnes to test with Claude Desktop

**Key learnings:**
- pydantic v1/v2 conflict: farmOS.py needs v1, FastMCP needs v2 — separate venvs is the cleanest solution
- farmOS CONTAINS filter: `filter[name][operator]=CONTAINS&filter[name][value]=X` — essential for querying 400+ logs
- farmOS pagination caps at ~250 entries — `fetch_all_paginated` is unreliable for large collections
- Markdown bold `**` in farmOS descriptions must be stripped with `.replace("**", "")` not `.strip("*")`
- Google Workspace accounts (fireflycorner.com.au) return 403 for anonymous POST to Apps Script — use personal account (fireflyagents.com) instead

### March 9, 2026 (continued) — Observation Review + farmOS Import + Page Regeneration

**Session 5: End-to-end observation review and import**
- Built `/review-observations` skill for Claire's review workflow
- Processed 86 field observations from March 9 field test
- 131 approved → imported to farmOS (64 inventory updates, 11 new plant assets, 5 new types)
- 4 rejected (invalid species, wrong section, zero counts)
- New plant types added: Davidson Plum, Pear (Flordahome), Pear (Nashi), Pluot (Black Adder), Chilli (Devil's Brew)
- Rose Apple reclassified from archived to active
- Code.gs v2 deployed with review/approval workflow

**Session 6: Page regeneration from farmOS (Phase 1 pipeline)**
- Built enriched export: `export_farmos.py --sections-json` — queries live farmOS per-section
  - Each plant enriched with first_planted (from earliest transplanting log), log history, farmOS inventory counts
  - Uses CONTAINS filter + pagination for 412 plants, 924 logs across 37 sections
  - farmOS inventory is a computed attribute on assets — no separate Quantity API calls needed
- Updated `generate_site.py`: first_planted dates, log timelines in expanded cards
  - First planted date shown in collapsed view below botanical name
  - Log timeline in expanded detail: 🌱 Transplanting, 📊 Observation, 🔧 Activity with dates
- Updated `observe.js`: Section Comment mode, Add New Plant (222 species search), Unknown Plant option
- Regenerated 75 pages from live farmOS data
- Fixed planted date confusion: use earliest transplanting log date, not asset name date
- Pushed to GitHub Pages: commits `a34337f` and `48bf235`

**Key learnings:**
- farmOS inventory is computed on assets: `plant['attributes']['inventory']` — no separate API calls needed
- farmOS JSON:API returns ISO timestamps (not Unix) when using raw HTTP — handle both in parsers
- first_planted should come from earliest transplanting log, NOT the asset name date (renovation plants had wrong dates)
- farmOS file upload: binary POST to `/api/log/{type}/{uuid}/image` with Content-Disposition header (not base64)
- All assets and logs have `image` and `file` relationship fields as base fields

### March 10–11, 2026 — MCP Observation Tools + Claire & James Claude Desktop Setup

**Session 1 (March 10): Observation management tools added to MCP server**
- Built `mcp-server/observe_client.py` — HTTP client for Google Apps Script observation endpoint
- Added 3 observation tools to `mcp-server/server.py`: `list_observations`, `update_observation_status`, `import_observations`
- `import_observations` is a composite tool: fetches from Sheet, validates, creates farmOS logs (activity/plant/observation), updates Sheet status
- All 13 tools tested against live farmOS and observation Sheet
- Built setup scripts: `scripts/setup-claude-desktop-mac.sh`, `scripts/setup-claude-desktop-win.ps1`
- Created `claude-docs/james-desktop-context.md` — role-specific context for James
- Updated `claude-docs/claire-desktop-context.md` — added observation management tools
- Committed: `46f7669` — pushed to origin

**Session 2 (March 11): Claire & James Claude Desktop setup**
- Set up James's Mac:
  - Installed Claude Desktop (DMG mount issue resolved)
  - Installed Python 3.13 alongside existing 3.14 via python.org installer
  - Copied 6 MCP server files to `~/firefly-mcp/`, created venv, installed deps
  - Created `claude_desktop_config.json` with farmOS credentials in env block
  - Config gotcha: must merge `preferences` and `mcpServers` in one JSON object (not two)
  - Created "Firefly Corner Farm" project with james-desktop-context.md
  - Tested: P2R5.55-66 query returned plants successfully ✅
- Set up Claire's Windows PC (AMD64):
  - Installed Claude Desktop for Windows
  - Installed Python 3.13 via python.org Windows installer (64-bit), ticked "Add to PATH"
  - Copied MCP files to `C:\firefly-mcp\`, created venv with `python -m venv venv`
  - Config at `%APPDATA%\Claude\claude_desktop_config.json` (Windows paths with double backslashes)
  - Same config merge gotcha — single JSON object required
  - Config file location: Claude Desktop must be opened once first to create the folder
  - Created project with claire-desktop-context.md
  - Tested: farmOS queries working ✅
- Section ID alignment verified March 11: all 37 active farmOS section IDs match QR page IDs exactly (414 plants, 1033 logs, 0 mismatches). Earlier concern was based on stale March 4 export.

**Key learnings:**
- Claude Desktop config must be ONE JSON object — two separate `{}` blocks cause parse errors
- Python 3.13 and 3.14 coexist fine — use `python3.13` explicitly for venv creation
- Windows: `venv\Scripts\python.exe` (not `venv/bin/python`), double backslashes in JSON paths
- `%APPDATA%\Claude` folder only exists after Claude Desktop has been opened at least once
- Env vars in Claude Desktop config `env` block work cleanly — `load_dotenv()` is a no-op when vars already set

### March 13, 2026 — Agnes Architecture Review + MCP Sprint (6 Improvements) + Olivier Setup

**Session 1: Seed bank spreadsheet for Claire**
- Created `Downloads/Seed bank inventory - MARCH2026.xlsx` — pre-filled plant type taxonomy columns from plant_types.csv
- Applied styled header row: bold white text on dark green (#2d5016) background, 40px height, centered alignment

**Session 2: Olivier Claude Desktop setup**
- Installed on Olivier's Windows PC (Claire's old PC, user `C:\Users\Claire`)
- Hit MSIX sandbox blocker — Microsoft Store/MSIX install blocks MCP process spawning
- Extensive troubleshooting: direct Python path, .bat wrapper, config in sandbox path — none worked
- **Solution**: `winget install Anthropic.Claude` installs non-sandboxed version
- MCP at `C:\firefly-mcp\`, Python 3.13, context file: `claude-docs/olivier-desktop-context.md`
- **All 4 users now equipped**: Agnes (macOS), Claire (Windows), James (macOS), Olivier (Windows)

**Session 3: Agnes review analysis + MCP server sprint**
- Analyzed Agnes's 3 review documents (roadmap, architecture, shared intelligence options)
- Consolidated priorities driven by March 22 hard deadline (Claire/Olivier departure)
- Agnes approved and explicitly requested implementing 6 MCP server improvements:

**MCP Server Sprint — 6 improvements (code complete, not yet committed):**

1. **Shared Intelligence (Option A)**: New `memory_client.py` + 3 tools in server.py
   - `write_session_summary`, `read_team_activity`, `search_team_memory`
   - Needs: Apps Script Code.gs for "Firefly Corner - Team Memory" Sheet + MEMORY_ENDPOINT env var

2. **Import preserves raw data**: `_build_import_notes()` helper builds rich farmOS log notes
   - Includes: reporter, timestamp, mode, condition, section/plant notes, count changes
   - Replaces sparse notes in all 3 import cases (section comment, new plant, inventory update)

3. **Plant type management**: 2 new tools (`add_plant_type`, `update_plant_type`)
   - `farmos_client.py`: `_patch()`, `create_plant_type()`, `update_plant_type()`
   - `helpers.py`: `build_plant_type_description()`, `parse_plant_type_metadata()`
   - Validates name doesn't exist before create, merges metadata on update

4. **Sheet cleanup after import**: `observe_client.delete_imported(submission_id)`
   - Called automatically in import_observations after successful status update
   - Needs: Apps Script `delete_imported` handler in observation Code.gs

5. **Media to farmOS logs**: `observe_client.get_media()` + `farmos_client.upload_file()`
   - Client methods implemented, media fetch+upload loop in import_observations NOT YET CODED
   - Needs: Apps Script `get_media` handler in observation Code.gs

6. **Auto-regenerate after import**: At end of import_observations
   - Checks `_MAIN_VENV_PYTHON` (only on Agnes's machine with git repo)
   - If exists: calls `regenerate_pages(push_to_github=True)`
   - Other machines: returns "Pages need regeneration" message

**Key learnings:**
- Windows MSIX/Microsoft Store Claude Desktop install runs in a sandboxed environment that blocks process spawning (Python, MCP servers)
- Standard .exe download from claude.ai can ALSO install as MSIX on some machines
- `winget install Anthropic.Claude` is the reliable non-sandboxed install method
- Known bug (GitHub issue #26073): MSIX "Edit Config" opens wrong file path (real vs virtualized %APPDATA%)
- `harvest_days` is NOT a valid farmOS plant_type field — causes 422. Only `maturity_days` and `transplant_days` work.

### March 13, 2026 (continued) — TDD Test Harness

**Session: Test harness for MCP server**
- Designed 3-layer test architecture: unit (helpers.py), client (HTTP mocks), integration (tool orchestration)
- Built complete test harness: 86 tests across 7 test files, all passing in 0.82s
- Layer 1 (`test_helpers.py`, 29 tests): parse_date (7 formats), format_planted_label, build_asset_name, name parsing edge cases (species with dashes like "Basil - Sweet (Classic)"), inventory extraction, plant_type metadata roundtrip, _build_import_notes, format_timestamp
- Layer 2 (`test_farmos_client.py`, 15 tests): OAuth2 connect/fail/missing-vars, 401/500/422 error handling, single/multi-page pagination with dedup, CONTAINS filter URL construction, quantity merging, entity creation payload verification
- Layer 2 (`test_observe_client.py`, 8 tests + `test_memory_client.py`, 6 tests): connect/missing-env, payload/param verification, error propagation
- Layer 3 (`test_tools_write.py`, 10 tests): create_observation happy/not-found/idempotency, create_activity happy/not-found, create_plant happy/type-not-found/idempotency, update_inventory delegation
- Layer 3 (`test_tools_read.py`, 6 tests): query_plants, get_plant_detail found/not-found, get_inventory grouping, query_sections grouping, search_plant_types case-insensitive
- Layer 3 (`test_import_workflow.py`, 12 tests): Case A/B/C routing, inferred new plant, status validation, sheet lifecycle, dry run, error resilience, auto-regen gating
- Coverage: 79% total (helpers 77%, farmos_client 52%, server 59%, observe_client 94%, memory_client 100%)
- Added architecture principle #11: "Test first, smart coverage, intelligent testing"
- Zero network calls — all mocked with `responses` library or `MagicMock`
- Dependencies added: pytest>=8.0.0, responses>=0.25.0, pytest-cov>=5.0.0

### March 18, 2026 — Knowledge Base Taxonomy & Cross-Referencing Design (Phase KB)

**Session 1: Team activity review + Knowledge Base architecture**
- Reviewed team memory: James (1 summary), Olivier (14 summaries over 3 days)
- **James's finding**: Knowledge Base category schema mismatch — Olivier's Claude saved tutorials with `category="nursery"` (topic) instead of `category="tutorial"` (content type). Search by category failed.
- **Olivier's finding**: `query_sections` only returns paddock sections, not nursery zones (NURS.*). Compiled full list of 17 nursery section IDs. Updated both tutorials with related_sections.
- **Olivier's productivity**: Built complete tutorial production pipeline (audio → Whisper → Claude → PDF → KB). 14 team memory entries, 2 tutorials, 1 reference, FFC Radio documentation.
- Listed Knowledge Base contents: 4 entries (Tutorial 01 Cuttings, Tutorial 02 Seedling Separation, Nursery Section IDs Reference, WWOOFer Waste Management Guide)

**Architecture design session — Knowledge Base taxonomy:**
- Designed 3 orthogonal metadata dimensions: `category` (content type: tutorial/sop/guide/reference/recipe/observation/source-material), `topics` (farm domains: nursery/compost/irrigation/syntropic/seeds/harvest/paddock/equipment/cooking/infrastructure/camp), `tags` (free-form keywords)
- Designed cross-referencing architecture with 3 join keys: `farmos_name` (species), section IDs (locations), `topics` (farm domains)
- Designed `farm_context` composite MCP tool for reliable cross-referencing in code
- Designed topic-to-farmOS mapping config (topics resolve to farmOS section prefixes)
- Designed raw materials indexing: `source-material` KB entries + Drive folder convention
- Designed Farm Intelligence Layer vision: context engine that assembles farmOS + KB + plant types + temporal context

**Implementation plan (6 items):**
1. Add `topics` field to KB schema (Apps Script + MCP tools)
2. Build `farm_context` composite MCP tool
3. Add `source-material` category + Drive folder convention
4. Add topic-to-farmOS mapping config
5. Enhance `query_sections` for all location types (Olivier's request)
6. Update all 4 Claude system prompts

**Documents created:**
- Added architecture decisions #13 (KB taxonomy), #14 (cross-referencing), #15 (Drive convention) to CLAUDE.md
- Added Phase KB to implementation phases in CLAUDE.md
- Created `claude-docs/phase-kb-knowledge-crossref.md` — full design + implementation plan

**Strategic note:** Agnes decided to implement quick wins (Items 1, 3, 5, 6) in Python first, then Phase 1b remote server, then add farm_context (Items 2, 4) to remote server. "Can always enhance the MCP tools once the MCP server is remote — won't need to update their laptops."

### March 19, 2026 — Phase 1b Deployed to Railway + 3 Production Fixes

**Session: Railway deployment debugging + fixes**
- Deployed TypeScript MCP server to Railway (all 29 tools, 98 tests)
- Hit 3 production issues, all fixed and deployed:

**Fix 1 — farmOS auth (commit `7bf4496`):**
- All farmOS tools returned "FarmOS credentials not found in auth context"
- Root cause: FA Framework only populates `extra.authInfo` when a platform OAuth handler is configured. Our FarmOSClient does its own OAuth2, so `authInfo` was always undefined.
- Additionally, code used `extra.auth` (wrong path) instead of `extra.authInfo`
- Fix: Read FARMOS_URL/USERNAME/PASSWORD from env vars (shared account). Auth context only for user identity.
- Added 16 client-factory tests (98 total, was 82)

**Fix 2 — Apps Script redirect (commit `a0cb4a8`):**
- Team memory, observations, knowledge, plant types all returned Google sign-in HTML
- Root cause: AxiosHttpClient doesn't follow Google Apps Script's 302 redirect chain (script.google.com → script.googleusercontent.com)
- Fix: Replaced AxiosHttpClient with native `fetch` + `redirect: 'follow'` in AppsScriptClient base class. Added JSON parse validation with clear error for non-JSON responses.

**Fix 3 — Cold start keep-alive (commit `197b8c5`):**
- First request after inactivity timed out (Railway sleeps containers)
- Fix: Self-ping to `/health` every 4 minutes keeps container warm
- Note: Stale session issue after deploys remains — `mcp-remote` retries expired session IDs. Lesley investigating.

**Additional:**
- Knowledge endpoint env var was truncated on Railway (Agnes fixed manually)
- Created FA MCP Framework skill: `skills/fa-mcp-framework.md` — 10-section reference guide
- Created feedback memory: `feedback_fa_framework_auth.md`
- Updated MEMORY.md with deployment checklist (9 env vars)

**Key learnings:**
- FA Framework `extra.authInfo` requires platform OAuth handler — use env vars for shared backend creds
- AxiosHttpClient breaks on Google's redirect chain — use native fetch for Apps Script
- `mcp-remote` doesn't cleanly reconnect after server restart (stale session ID → 404 loop)
- Railway Hobby plan sleeps containers after ~15 min inactivity — self-ping prevents this
- Railway boots Node.js container in ~1 second — cold start itself isn't the issue, stale sessions are

### March 20, 2026 — Team Migration to Remote MCP + Phase KB Quick Wins + Page Regeneration

**Session 1: Team machine migration to Railway remote MCP**
- Migrated all 4 team machines from local Python MCP to remote Railway server via `npx mcp-remote`
- James (Mac): `npx` directly in Claude Desktop config — worked immediately
- Olivier (Windows): Node installed via `winget install OpenJS.NodeJS.LTS`. npx in PATH but Claude Desktop couldn't find it. Solved with .bat wrapper at `C:\firefly-mcp\mcp-remote.bat` containing `"C:\Program Files\nodejs\npx.cmd" %*`
- Claire (Windows): Same .bat wrapper approach as Olivier
- Old local Python MCP files (`C:\firefly-mcp\` venv, server.py, .env) can be deleted — only .bat file needed
- Hit `forkpty: Resource temporarily unavailable` on James's Mac — too many Terminal sessions, restart fixed it
- Team memory update posted about MCP timeout workaround (restart Claude Desktop after deploys)

**Session 2: Phase KB quick wins deployed**
- Added `topics` parameter to `search_knowledge` and `list_knowledge` (TypeScript + Python)
- Updated `knowledge-client.ts` to pass topics in query params
- Enhanced `query_sections`: when called with no filter, returns ALL location types (paddock + nursery + compost) instead of just paddock
- Added `source-material` to add_knowledge source_type descriptions
- Updated all 3 team context files (Claire, James, Olivier) with topics param and query_sections docs
- Updated Apps Script `KnowledgeBase.gs` with topics filtering in handleList and handleSearch
- Agnes redeployed Apps Script — verified working end-to-end
- 99 TypeScript tests passing (was 98), 117 Python tests passing
- Committed: `00b100f` (MCP tools) + `a62351f` (Apps Script)

**Session 3: QR page regeneration**
- Ran full pipeline: export_farmos.py → generate_site.py → git push
- 53 sections, 631 plants, 1234 logs exported from live farmOS
- 107 pages generated (53 view + 53 observe + index)
- Includes all of Claire's P2R3 end-of-season imports
- Committed: `7ad6f99` — live on GitHub Pages

**Key learnings:**
- Windows Claude Desktop doesn't inherit system PATH for child processes — even with non-sandboxed winget install. The .bat wrapper with full path to `npx.cmd` is the reliable solution.
- `forkpty: Resource temporarily unavailable` = Mac out of pseudo-TTY slots. Close terminals or restart.
- Phase KB topics filter works end-to-end: MCP tool → Apps Script → filtered results. No client machine updates needed since it's the remote server.

### March 20, 2026 (continued) — Seed Bank System + Plant Type Corrections + Documentation Overhaul

**Session: Claire's seed bank review + plant type corrections + tooling**
- Reviewed Claire's corrected 27-column seed bank inventory (263 rows) — combined plant_types.csv (17 cols) + seed_bank.csv (10 cols)
- Found 71 differences from repo plant_types.csv: 5 strata, 3 botanical names, 1 crop family, 1 succession stage, 52 source changes
- Applied 32 field corrections to `knowledge/plant_types.csv` across 12 species (strata, botanical names, descriptions)
- Fixed `import_plants.py` comparison bug: was checking `if "Syntropic Agriculture Data" in current_value` (skipped ALL updates); now compares full description text
- Synced 26 taxonomy updates to live farmOS (271/271 in sync)
- Built `scripts/google-apps-script/SeedBank.gs` — rewritten for Claire's actual 27-column layout
- Built `scripts/google-apps-script/UsageTracking.gs` — shared quota monitoring (daily counters, 80% warnings, 7-day history)
- Enriched `site/public/seedbank.js` — collapsible detail panels with strata colors, germination time, transplant days, function pills
- Updated `site/public/SEED.BANK.html` — enriched CSS for new card components
- Added health check handlers to all 4 existing Apps Script backends (Code.gs, TeamMemory.gs, PlantTypes.gs, KnowledgeBase.gs)
- Agnes deployed SeedBank.gs to fireflyagents.com Google Sheet
- Wired live endpoint into SEED.BANK.html, added `--seedbank-endpoint` arg to generate_site.py
- Added Farm Tools section to index page with Seed Bank link
- Analyzed Claire's purchase orders spreadsheet: 8 historical orders, ~$2,395, 3 main suppliers
- Designed purchase order page + harvest QR page architecture
- Updated CLAUDE.md: current state, repo structure, Phase SB, Phase KB status, session log
- Updated MEMORY.md: priorities, seed bank details, Apps Script endpoints

**Key learnings:**
- `import_plants.py` had a critical bug where `if "Syntropic Agriculture Data" in current_value` caused ALL existing taxonomy terms to be skipped on update, even when the description had changed. Fixed to compare full text.
- Claire's seed bank file merges plant_types.csv + seed_bank.csv into one 27-column sheet — the "source of truth" for seed inventory includes plant enrichment data inline
- Seed Bank Apps Script endpoint: `https://script.google.com/macros/s/AKfycbwm2YllQ0vi-vSz_aruKXGxVL3klbSE7F_85dS4qIlxoy3TP4DA0VkAPcI3izNgj7hMIg/exec`

### March 21, 2026 — Harvest Page + Home Button + Source Corrections + Apps Script Cleanup

**Session: Full sprint — 12 commits (`bc2ad6c` → `d5f8f0e`)**

Part 1 — Nursery + Harvest QR pages:
- Built nursery inline observations with farmOS data flow + transplant timing badges
- Built HARVEST.html + harvest.js — species dropdown, weight (kg/g), photo, notes, precise location (paddock→row→section)
- Built Harvest.gs — Apps Script backend bound to "Firefly Corner - Harvest Log" Sheet
- Drive folder: `1vI_JxVYnTAcclFOT5ziN7wBTz6ofuskA`
- Harvest endpoint: `https://script.google.com/macros/s/AKfycbwsNstKLN3o1r-ccvJn9wA2DZXx_3P7IbMK7Akl2AgUpOOxX1x7frMzyv_5d2lQxhZZsQ/exec`
- Added whole-paddock location options per James's request

Part 2 — Index page redesign:
- Collapsible sections: Seed Bank → Plant Nursery → Paddock 1 → Paddock 2 → Harvest Station
- `toggleLocation()` JS for expand/collapse
- Nursery sub-groups: Shelving I/II/III, Ground & Zones
- Paddock sub-groups: individual rows with section counts

Part 3 — Home button on all QR pages:
- Frog logo (`logo-sm.png`, 68x68, 12KB) as circular button top-right
- Applied to all 131 pages (53 paddock view, 53 observe, 18 nursery, SEED.BANK, HARVEST, index)
- Added to both generators (generate_site.py, generate_nursery_pages.py)
- Skip logic: generate_site.py won't overwrite hand-managed index.html or styles.css

Part 4 — Source corrections + seed_bank.csv:
- Applied 53 source/provenance corrections from Claire's seed bank review to plant_types.csv
- Preserved 2 blanked sources (Basil Perennial Greek, Fennel) and 8 species with blanked data
- Updated seed_bank.csv: 263 entries, new 11-column format with farmos_name as join key

Part 5 — Apps Script cleanup:
- Renamed Code.gs → Observations.gs (matches naming pattern)
- Converted Observations from standalone to bound-script (getActiveSpreadsheet)
- New observe endpoint: `AKfycbxwWorskdbg8ZFpkYAzpo4ILGUNRhTi7HtQbxtYI38ws9vKSIlASAZHvpGIPrbHVBVY`
- Updated all 53 observe pages + Railway + local .env with new endpoint
- Agnes deployed all 6 Apps Scripts with health handlers + UsageTracking.gs:
  - Observations.gs, TeamMemory.gs, KnowledgeBase.gs, PlantTypes.gs (redeployed March 21)
  - SeedBank.gs, Harvest.gs (already deployed)

Part 6 — James ops guide:
- Added transplant readiness check to daily routine
- New Section 6: nursery inline observations + farmOS data flow
- Updated nursery zone count, added collapsible index note

**Key learnings:**
- macOS `sips -z 68 68` for image resizing (95KB → 12KB)
- Skip logic pattern: check content markers ("home-btn", "toggleLocation") to detect hand-managed files
- All 6 Apps Scripts now use consistent bound-script pattern on fireflyagents.com
- Standalone Apps Script deployments persist as snapshots even when source is deleted, but eventually stop working

### March 29, 2026 — MCP Tool Improvements + Nursery Data Cleanup + Pagination Plan

**Session 1: Nursery watering task revealed 4 tool pain points**
- Agnes asked for nursery watering guidance and current inventory for James's daily tasks
- KB search "watering nursery" returned 0 results despite perfect SOP match (exact phrase matching bug)
- Nursery inventory required 16 separate `get_inventory` calls (no batch query)
- `list_knowledge` returned 64KB blob (no summary mode)
- First `query_sections` call got 401 auth expired (no retry in Python client)
- Nursery inventory in farmOS didn't match physical shelves — triggered data investigation

**4 MCP tool fixes implemented (225 tests green: 124 Python + 101 TypeScript):**

1. **Batch inventory** — Added `section_prefix` param to `get_inventory` in Python + TypeScript. `get_inventory(section_prefix="NURS")` returns all nursery zones in 1 call instead of 16. Works for any prefix (NURS, COMP, P2R3).

2. **KB search OR matching** — Rewrote `handleSearch` in KnowledgeBase.gs. Splits query into words, matches ANY word in ANY field (title, content, tags, topics, related_plants). Scores by match count for relevance ranking. Agnes redeployed Apps Script same session.

3. **KB summary mode** — Added `summary_only=true` param to `search_knowledge` and `list_knowledge` in Python + TypeScript. Returns only: entry_id, title, category, topics, tags, author, content_preview (first 100 chars).

4. **401 auto-retry** — Added `_retry_on_auth_error()` helper to Python farmos_client.py. On 401/403: reconnects with fresh OAuth2 token, retries once. All 6 HTTP methods covered. (TypeScript already had this pattern.)

**Nursery data investigation and cleanup:**
- Root cause: Two CSV imports ran — `CORRECTED_17Mar` (120 rows, `map_location()` mapped SHELVES+FLOOR columns incorrectly) and enriched March 20 CSV (86 rows, correct Location IDs). Both created plants because asset names include location (different location = different name = bypasses idempotency).
- Built `scripts/cleanup_nursery.py`: compares farmOS vs enriched CSV (source of truth)
- Phase 1: Archived 58 misplaced plant assets from old import (wrong zones)
- Phase 2: Created 30 correct plant assets in proper zones
- Phase 3: Cleaned duplicate assets caused by CONTAINS pagination missing entries during multi-pass cleanup
- Final state: farmOS nursery has 65 active plant assets matching the enriched CSV exactly
- Regenerated all 15 nursery QR pages from clean farmOS data

**Pagination investigation:**
- CONTAINS filter on "NURS." returned 85/90 assets — 5 missed due to `links.next` ceiling (~250 results)
- Duplicates from previous runs consumed pagination slots, causing valid assets to fall off the end
- Confirmed: direct `fetchByName` queries found all 5 "missing" assets — they existed but weren't returned by CONTAINS pagination
- Created comprehensive fix plan: `claude-docs/pagination-fix-plan.md`
- Core strategy: switch all CONTAINS methods from `links.next` to offset-based pagination (matching `fetchAllPaginated` pattern), add stable sort ordering, add `fetchByName` fallback for write safety
- Added architecture decisions #16 (pagination safety) and #17 (MCP tools as only write path)

**Key learnings:**
- farmOS JSON:API `links.next` disappears after ~250 results — NEVER rely on it for completeness
- Archived records consume pagination slots even with `filter[status]=active`
- Write tools that check "not found in list" before creating MUST use `fetchByName` (direct name query), not CONTAINS result sets
- Running MCP servers don't pick up code changes until restart (STDIO) / redeploy (Railway)
- KnowledgeBase.gs search was doing exact phrase matching (`indexOf(query)`) — word-level OR matching is the correct approach

**Commits:** `4d988cf` (main push with all fixes + nursery pages)

---

### April 2, 2026 — Camp Amenities QR Page
- Built `AMENITIES.html` — mobile-first, collapsible sections (Water Supply, Dry Toilet, Shower)
- Published illustrated camp facilities guide on GitHub Pages
- Generated AMENITIES QR code for mounting on amenities block

### April 4, 2026 — Farm Intelligence Layer + Transcript Processing + Repo Audit
- **Farm Intelligence Layer built and deployed** (five-layer architecture):
  - Ontology: `knowledge/farm_ontology.yaml` (18 entity types, relationships, constraints)
  - Semantics: `knowledge/farm_semantics.yaml` (metrics, thresholds, feedback loops)
  - Python: `mcp-server/semantics.py` (9 functions) + `farm_context` tool (29th tool)
  - TypeScript: `helpers/semantics.ts` + `tools/farm-context.ts` (31st tool)
  - Data integrity gate: cross-references team memory claims against actual farmOS logs
- **Maverick's P2R5 transcript processed**: 9 new plant assets, 2 count updates, 4 pending review tasks
- **Pagination fix**: Replaced links.next with offset-based pagination in both Python and TypeScript CONTAINS methods. Added stable sort ordering and maxPages safety cap. 184 Python tests + 124 TypeScript tests all green.
- **Repo audit**: Deleted misplaced .gs drafts from claude-docs/, migration artifacts from knowledge/, updated .gitignore, fixed 17+ stale items in CLAUDE.md

