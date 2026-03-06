# Firefly Corner Farm AI — Design, Plan & Roadmap

> Living document. Updated March 4, 2026.
> This captures architectural decisions, current status, and the implementation roadmap
> as refined through Claude Code sessions.

---

## 1. Current Status (March 4, 2026)

### What's Done

| Deliverable | Status | Notes |
|-------------|--------|-------|
| GitHub repo created | Done | agnesfa/firefly-farm-ai |
| GitHub Pages live | Done | https://agnesfa.github.io/firefly-farm-ai/ |
| 15 HTML pages (index + 14 sections) | Done | P2R2 (7) + P2R3 (7), from fieldsheets |
| 32 QR codes generated | Done | From live farmOS data, forest green branding |
| Fresh farmOS export | Done | March 4, 2026: 156 assets, 126 logs, 104 taxonomy |
| Foundation scripts migrated | Done | export_farmos.py, import_plants.py (credential cleanup) |
| Plant types CSV v6 | Done | 180 species, comprehensive syntropic metadata |
| CI/CD pipeline | Done | GitHub Actions auto-deploys site/public/ on push |

### What's In Progress

| Item | Status | Blocker |
|------|--------|---------|
| P2R2 section boundary alignment | Waiting | Agnes reviewing with Claire |
| Remaining fieldsheets (P2R1, P2R4, P2R5) | Waiting | Agnes preparing |
| Plant types import to farmOS | Ready to start | Name mismatches need resolution (see below) |

### Known Issues

1. **P2R2 section ID mismatch**: farmOS has (3-9, 9-16, 27-36, 36-45) but fieldsheets have (3-7, 7-16, 28-37, 37-46). Four QR codes will 404 until resolved.
2. **Plant type name mismatches**: 23 plants have different names between CSV and farmOS (see Section 5).
3. **import_plants.py bug**: Silently drops range values like "60-90" for harvest_days, maturity_days. Needs fix before running.
4. **P2R5.29-37 missing from farmOS**: Listed in Jan 5 doc but asset not found in March 4 export.

---

## 2. Architecture Overview

### Data Flow (Target State)

```
INPUTS                           SOURCE OF TRUTH                    OUTPUTS

Claire's spreadsheets (.xlsx) ─┐
Plant types CSV (v6) ──────────┤
Seed bank CSV ─────────────────┤       farmOS                     QR Landing Pages
Claire via Claude chat ────────┼──▶  margregen.farmos.net  ──▶   (GitHub Pages)
WWOOFer observations ──────────┤     (Drupal + JSON:API)
WhatsApp harvest logs ─────────┘           │                      Plant Database
                                           │                      Inventory Reports
                                           ▼                      Farm Analytics
                                    farmOS MCP Server
                                    (Python, Phase 1)
                                           │
                                           ▼
                                    Claude Agent
                                    (Single agent + sub-agents)
```

### Key Architectural Decisions

1. **farmOS is the source of truth** for all farm data
2. **Single Claude agent** with sub-agents for parallel work (not multi-agent orchestration)
3. **farmOS MCP server in Python** (farmOS.py client + Python MCP SDK)
4. **Claude IS the UI** for non-technical users (Claire, James)
5. **GitHub Pages** for visitor-facing content (QR code landing pages)
6. **Plant types CSV enriches** farmOS data until custom Drupal module (Phase 4)
7. **Idempotent scripts** — all pipeline scripts safe to re-run

### Sub-Agent Pattern (New — March 2026)

Within a single Claude Code session, we use sub-agents for parallel work:
- **Explore agents** for codebase discovery and file searches
- **General-purpose agents** for research, data audits, and validation
- **Bash agents** for running scripts and git operations

This is NOT multi-agent orchestration — it's a single architect delegating focused tasks.
Agent Teams (experimental) available for complex parallel development if needed in Phase 1.

---

## 3. Implementation Phases (Revised)

### Phase 0: Landcare Demo (by March 10, 2026)

**Goal:** Working QR code pages for P2 farm tour.

- [x] Parse P2R2 and P2R3 field sheets into sections.json
- [x] Generate 14 section HTML pages + index
- [x] Pipeline tested end-to-end
- [x] Push to GitHub, enable GitHub Pages
- [x] Fresh farmOS export (March 4, 2026)
- [x] Generate 32 QR codes from live farmOS data
- [ ] Resolve P2R2 section boundaries with Claire
- [ ] Upload and parse remaining P2 rows (R1, R4, R5)
- [ ] Regenerate all pages with aligned section IDs
- [ ] Print QR codes for poles (minimum 3cm x 3cm)
- [ ] Test visitor experience on phone

### Phase 0.5: Plant Types Foundation (NEW — March 2026)

**Goal:** Get the full plant types database into farmOS. This unblocks Phase 1.

**Why now:** The plant_type taxonomy is the join key across ALL systems. With only 80 of 180+ species in farmOS, the MCP server and import scripts can't work properly.

Tasks:
- [ ] Resolve 23 name mismatches between CSV and farmOS (Agnes deciding)
- [ ] Fix import_plants.py: parse range values (e.g., "60-90" → store as range or min)
- [ ] Fix import_plants.py: handle name collisions with existing farmOS entries
- [ ] Dry-run import of 103+ new plant types
- [ ] Production import
- [ ] Verify: farmOS plant_type taxonomy has 180+ entries
- [ ] Update plant_types.csv with any name changes (canonical names)
- [ ] Clean up farmOS-only entries: Cattail (keep?), Water plantains (remove?), Chilli (Big Jim) (add to CSV?)

**Dependencies:** None — can run now
**Unblocks:** Phase 1 (MCP server needs complete taxonomy), import_fieldsheets.py (needs plant_type UUIDs)

### Phase 1: farmOS MCP Server + Data Pipeline (Weeks 2–4)

**Goal:** farmOS becomes the live source of truth. Claude can query and write to farmOS.

#### MCP Server (mcp-server/)
Core tools:
1. `query_assets` — Search assets by type, status, location
2. `get_locations` — Return location hierarchy
3. `get_plant_types` — Search/list plant type taxonomy
4. `create_log` — Create activity/observation/seeding/transplanting/harvest logs
5. `query_logs` — Search logs by date, type, asset, location
6. `create_asset` — Create plant or seed assets
7. `get_inventory` — Query seed stock levels

Resources: `farm://overview`, `farm://plants`, `farm://locations`, `farm://recent`
Prompts: `log-field-activity`, `record-seeding`, `transplant-to-paddock`

#### Data Pipeline
- [ ] Build export_farmos.py sections.json output (currently exports raw JSON, needs sections.json format)
- [ ] Build import_fieldsheets.py (spreadsheets → farmOS logs + assets)
- [ ] Switch site generation from parse_fieldsheets.py → export_farmos.py
- [ ] End-to-end test: farmOS data → sections.json → HTML pages → GitHub Pages

### Phase 2: Claire's First Real Log (Weeks 4–5)

**Goal:** Claire uses Claude + MCP to log a field activity in natural language, and it lands in farmOS correctly.

- Claire says: "Planted 5 pigeon pea seedlings in P2R3.14-21 today"
- Claude creates: Transplanting Log with correct asset references, location, quantities
- farmOS reflects: Updated plant inventory for that section

### Phase 3: Nursery & Seed Bank (Months 2–3)

- Import seed_bank.csv (244 records) as Seed assets
- Create Plant assets for tracked plantings
- Nursery inventory workflow (seed → seedling → transplant)
- Seed → Plant lifecycle tracking via native farmOS workflow

### Phase 4: Custom farmOS Module (Month 3+)

`farm_syntropic` Drupal module:
- Proper fields: strata, succession_stage, plant_functions on plant_type taxonomy
- New taxonomies: strata, succession_stage, plant_function
- New asset types: Consortium
- New log types: Pruning, Biomass
- Data migration from description text to structured fields

### Phase 5: Multi-User & Advanced AI (Month 4+)

- Shared Claude Project for the team
- Voice input for field use
- Live site updates from farmOS data changes
- Knowledge base evolution (learning which consortiums work)
- WhatsApp harvest log parsing

---

## 4. Technical Environment

### Requirements

- **Python 3.13** (NOT 3.14 — farmOS library uses pydantic v1 which is incompatible with 3.14)
- **Virtual environment:** `venv/` at repo root
- **farmOS credentials:** `.env` file (never committed), see `.env.example`
- **farmOS Python client:** `farmOS>=1.0.0` (OAuth2 auth)

### Dependencies

```
# Data pipeline
openpyxl          # Excel parsing
pandas            # Data manipulation
jinja2            # HTML templating (future)

# farmOS API
farmOS>=1.0.0     # Python client library
requests>=2.31.0  # HTTP

# QR codes
qrcode[pil]>=7.4.0  # QR generation with PIL styling

# Environment
python-dotenv>=1.0.0  # .env file loading
```

### Related Repositories

| Repo | Purpose | URL |
|------|---------|-----|
| firefly-farm-ai | This repo — main project | github.com/agnesfa/firefly-farm-ai |
| farm-tiles | Drone orthophoto raster tiles for farmOS | github.com/agnesfa/farm-tiles |

---

## 5. Plant Types Database — Status & Plan

### Current State

| Metric | Count |
|--------|-------|
| Plant types in CSV (v6 master) | 180 |
| Plant types in farmOS | 80 |
| Exact match (in both) | 54 |
| Name mismatches (same plant, different name) | 23 |
| In CSV only (need importing) | 103 |
| In farmOS only (not in CSV) | 4 |

### Name Mismatch Resolution

> **STATUS: AWAITING AGNES'S DECISION** (case-by-case review)

General pattern: farmOS tends to have more specific cultivar names (from seed packets).
Recommendation: Align CSV to farmOS names where farmOS is more specific.

See full mismatch list in session notes (March 4, 2026).

### Import Script Fixes Needed

1. **Range value parsing** (MAJOR): Script drops "60-90" format for days fields. Need to parse as min value or range string.
2. **Name collision handling** (MODERATE): Script will create duplicates if CSV name differs from existing farmOS name.
3. **crop_family relationship** (MINOR, deferred): Not setting the farmOS crop_family taxonomy relationship — only embedding in description text. Acceptable until Phase 4.

---

## 6. QR Code Strategy

### URL Format

URLs are section-based: `https://agnesfa.github.io/firefly-farm-ai/{section_id}.html`
Example: `https://agnesfa.github.io/firefly-farm-ai/P2R3.14-21.html`

### Permanence Decision

**Decision: Accept reprinting** if section boundaries change. The simplicity of direct URLs outweighs the complexity of a redirect system. Section boundaries are expected to be stable once established.

### Current QR Codes (32 total, from farmOS)

Generated from live farmOS export data (March 4, 2026). Forest green on white, with section label and "Firefly Corner Farm" subtitle. Print at minimum 3cm x 3cm.

---

## 7. Open Questions

1. ~~Plant type naming: CSV or farmOS canonical?~~ → Reviewing case-by-case
2. P2R2 section boundaries: Awaiting Claire's confirmation
3. P2R5.29-37: Missing from farmOS — needs creating?
4. farmOS-only entries: Keep Cattail? Remove Water plantains? Add Chilli (Big Jim) to CSV?
5. Mulberry naming: CSV has `White Mulberry` (species level), farmOS has `Mulberry (White)` (cultivar format). Are these the same tree?

---

*Last updated: March 4, 2026*
