# Phase KB: Knowledge Base Taxonomy & Cross-Referencing

> Design document created March 18, 2026. Implementation ready — 6 items.
> Priority: implement BEFORE Phase 1b remote server, but can also enhance after remote server is live.

---

## Context & Problem Statement

The Knowledge Base (launched March 17) has 4 entries and is growing fast thanks to Olivier's tutorial production workflow. Two problems surfaced immediately:

1. **Category schema mismatch** (James, March 18): Olivier's Claude saved tutorials with `category="nursery"` (a topic) instead of `category="tutorial"` (a content type). James searched with `category="tutorial"` and got empty results. Root cause: the single `category` field conflates content type with subject matter.

2. **query_sections gap** (Olivier, March 18): The `query_sections` MCP tool only returns paddock sections (P1/P2), not nursery zones (NURS.*), compost bays (COMP.*), or other location types. This prevents cross-referencing KB entries with farmOS locations outside paddocks.

3. **No automatic cross-referencing**: farmOS and the Knowledge Base are separate silos. The AI has tools to query each independently, but nothing connects them. Cross-referencing depends on the AI remembering to check both systems, which is fragile and invisible.

4. **Raw materials not indexed**: Olivier wants to store source materials (audio, transcriptions, photos) in the Knowledge Drive and have them searchable, so future team members can re-process or verify original sources.

---

## Design: Three Orthogonal Metadata Dimensions

### Current (broken)
| Field | Intended use | Actual use |
|-------|-------------|------------|
| `category` | Content type | Mixed: "tutorial" AND "nursery" used interchangeably |
| `tags` | Free-form keywords | Everything — species, techniques, topics, all mixed |

### New design
| Dimension | Field | Cardinality | Values | Purpose |
|-----------|-------|-------------|--------|---------|
| **Content type** | `category` | Single | `tutorial`, `sop`, `guide`, `reference`, `recipe`, `observation`, `source-material` | *What kind of document is this?* |
| **Farm domains** | `topics` | Multi (comma-separated) | `nursery`, `compost`, `irrigation`, `syntropic`, `seeds`, `harvest`, `paddock`, `equipment`, `cooking`, `infrastructure`, `camp` | *What areas of the farm does it cover?* |
| **Keywords** | `tags` | Multi (free-form) | Species names, techniques, tool names, anything | *What specific things does it mention?* |

### Why 3 dimensions, not 2
- `category` answers: "Show me all tutorials" — content type filtering
- `topics` answers: "Show me everything about the nursery" — domain filtering
- `tags` answers: "Show me anything mentioning comfrey" — keyword search
- Combined: `category=tutorial + topic=nursery` → "nursery tutorials"

### Topic vocabulary (semi-controlled, extensible)
```
nursery      — NURS.* sections, propagation, seedlings, potting
compost      — COMP.* sections, Berkeley method, ingredients, turning
irrigation   — Water assets, dams, keyline, hoses, scheduling
syntropic    — Row design, strata, succession, consortiums, chop-and-drop
seeds        — NURS.FRDG, NURS.FRZR, seed saving, germination
harvest      — Picking, processing, storage, WhatsApp logs
paddock      — P1/P2 field sections, planting, renovation
equipment    — Tools, machinery, maintenance
cooking      — Recipes, preservation, kitchen
infrastructure — Dams, fencing, roads, buildings, power
camp         — WWOOFer accommodation, waste, visitor facilities
```

---

## Design: Cross-Referencing Architecture

### The Three Join Keys

| Join Key | Connects | Example |
|----------|----------|---------|
| **`farmos_name`** (species) | Plant assets ↔ Plant types ↔ KB entries (`related_plants`) | "Comfrey" links 6 farmOS assets + plant type metadata + Tutorial 01 |
| **Section ID** (location) | Land assets ↔ KB entries (`related_sections`) ↔ Observation logs | "NURS.SH1-2" links farmOS inventory + KB nursery reference |
| **Topic** (domain) | Farm domains ↔ KB entries (`topics`) ↔ farmOS entity groups | "nursery" maps to all NURS.* sections + all nursery KB entries |

### Topic-to-farmOS Mapping

A simple config dict in the MCP server that maps topics to farmOS query patterns:

```python
TOPIC_FARMOS_MAP = {
    "nursery": {"section_prefix": "NURS.", "asset_types": ["plant", "structure"]},
    "compost": {"section_prefix": "COMP.", "asset_types": ["compost"]},
    "paddock": {"section_prefix": "P", "asset_types": ["plant", "land"]},
    "seeds":   {"section_prefix": "NURS.FR", "asset_types": ["seed"]},
    "irrigation": {"section_prefix": None, "asset_types": ["water", "equipment"]},
    "equipment": {"section_prefix": None, "asset_types": ["equipment"]},
    "infrastructure": {"section_prefix": None, "asset_types": ["water", "land"]},
    "camp": {"section_prefix": None, "asset_types": ["structure"]},
}
```

### The `farm_context` Composite Tool

Single tool that cross-references all three data systems in one call:

```
farm_context(subject="Comfrey")
→ farmOS: 6 plant assets (locations, counts, latest logs)
→ KB: Tutorial 01 (cuttings technique), any observations
→ Plant type: botanical name, strata=low, succession=secondary, functions
→ Gaps: "No harvest guide. No chop-and-drop SOP."

farm_context(section="NURS.SH1-2")
→ farmOS: 8 plants on this shelf, species + counts
→ KB: nursery section reference, relevant tutorials for species present
→ Actionable: "3 plants ready to transplant"

farm_context(topic="nursery")
→ farmOS: all NURS.* inventory summary (86 plants, 16 locations)
→ KB: 3 entries (2 tutorials, 1 reference)
→ Coverage: "Tutorials exist for cuttings and seedling separation. Missing: potting mix, transplanting, seed saving, grafting."
```

**Why this matters:** Guarantees cross-referencing happens in code (not dependent on AI memory). Works for any AI — not Claude-specific. Surfaces gaps proactively. Is the embryo of the future Farm Intelligence Layer.

### Future: Farm Intelligence Layer

```
┌─────────────────────────────────────────────┐
│              Farm AI / Claude                │
│         (natural language interface)         │
└──────────────────┬──────────────────────────┘
                   │ asks
                   ▼
┌─────────────────────────────────────────────┐
│          Farm Context Engine                 │
│  ┌─────────┐ ┌──────────┐ ┌─────────────┐  │
│  │ farmOS  │ │ Knowledge│ │ Plant Types  │  │
│  │ Client  │ │ Base     │ │ + Seasons    │  │
│  └────┬────┘ └────┬─────┘ └──────┬──────┘  │
│       └───────────┼──────────────┘          │
│          Join / Rank / Enrich               │
│          ┌────────▼────────┐                │
│          │ Structured      │                │
│          │ Farm Context    │                │
│          └─────────────────┘                │
└─────────────────────────────────────────────┘
```

Capabilities to grow into:
- **Entity resolution**: "pigeon pea", "Pigeon Pea", "cajanus cajan" → same entity
- **Temporal awareness**: season, growth stage, last activity date
- **Gap detection**: surfaces missing knowledge proactively
- **Relevance ranking**: nursery KB entries rank above paddock data for nursery questions
- **Provenance tracking**: every answer traces back to source (Olivier's audio, Claire's spreadsheet, farmOS log)

---

## Design: Raw Materials & Drive Folder Convention

### Drive folder structure
```
Knowledge Drive/
├── tutorials/
│   ├── 01-cuttings/
│   │   ├── FFC_Cuttings_Quicksheet.pdf          ← finished output
│   │   └── sources/
│   │       ├── audio/
│   │       │   ├── cuttings-coupe-oblique.m4a
│   │       │   └── cuttings-banagrass.m4a
│   │       ├── transcriptions/
│   │       │   ├── cuttings-coupe-oblique.txt
│   │       │   └── cuttings-banagrass.txt
│   │       └── photos/
│   │           ├── banagrass-node.jpg
│   │           └── comfrey-root.jpg
│   ├── 02-seedling-separation/
│   │   └── ...
├── guides/
│   └── waste-management/
├── sops/
│   └── seed-bank-operations/
├── references/
│   └── nursery-section-ids/
└── source-library/                               ← unprocessed raw materials
    ├── olivier-nursery-march2026/
    │   ├── audio/
    │   ├── transcriptions/
    │   └── photos/
    └── claire-renovation-notes/
```

### Source material KB entries
Each source folder gets its own KB entry:
```
title: "Source Materials — Nursery Cuttings (Olivier, March 2026)"
category: source-material
topics: nursery, propagation
tags: audio, transcription, photos, banagrass, comfrey, tansy, ...
media_links: https://drive.google.com/drive/folders/XXX
content: "10 audio recordings (Whisper-transcribed), 53 field photos..."
related_plants: Banagrass, Comfrey, Tansy, Geranium, Mint, Lavender, Sweet Potato, Rosemary
```

Benefits:
- Searchable: "find all raw audio about nursery techniques"
- Reusable: same sources can feed multiple finished outputs
- Auditable: see what raw materials exist that haven't been turned into tutorials yet
- Provenance: when Claire and Olivier leave, future team can trace back any knowledge

---

## Implementation Plan: 6 Items

### Item 1: Add `topics` field to KB schema
**Effort:** ~1 hour
**Changes:**
1. **Knowledge Sheet**: Add `Topics` column between `Category` and `Tags`
2. **Apps Script (Knowledge Code.gs)**: Read/write `topics` field in all handlers (doGet, doPost)
3. **MCP `knowledge_client.py`**: Include `topics` in payloads for add/update/list/search
4. **MCP `server.py`**: Add `topics` parameter to `add_knowledge`, `update_knowledge` tools; add `topic` filter to `list_knowledge`; include `topics` in `search_knowledge` text search
5. **Fix Tutorial 01 & 02**: Set `category="tutorial"`, add `topics="nursery, propagation"`
6. **Fix Nursery Section IDs reference**: Keep `category="reference"`, add `topics="nursery"`

**Testing:** Create test entry with topics, search by topic, list filtered by topic, verify existing entries still work.

### Item 2: Build `farm_context` composite MCP tool
**Effort:** 2-3 hours
**Changes:**
1. **MCP `server.py`**: New tool `farm_context(subject=None, section=None, topic=None)`
2. **Logic for `subject` (species name)**:
   - Query farmOS: `query_plants(species=subject)` → assets with locations, counts, latest logs
   - Query KB: `search_knowledge(query=subject)` → matching entries
   - Query plant types: `search_plant_types(query=subject)` → botanical info, strata, functions
   - Identify gaps: "No KB entries found for this species" or "No harvest guide exists"
3. **Logic for `section` (location ID)**:
   - Query farmOS: `get_inventory(section_id=section)` → plants at this location
   - Query KB: filter entries where `related_sections` contains the section ID
   - For each species present: pull plant type metadata
4. **Logic for `topic` (farm domain)**:
   - Use `TOPIC_FARMOS_MAP` to determine farmOS query pattern
   - Query farmOS: sections matching prefix, or assets matching types
   - Query KB: `list_knowledge(topic=topic)` → all entries for this domain
   - Coverage analysis: what topics have KB content vs gaps
5. **Response format**: Structured JSON with `farmos_data`, `knowledge_entries`, `plant_type_info`, `gaps` sections

**Dependencies:** Item 1 (topics field) should be done first so `farm_context` can filter by topic.

**Testing:** Test each query path (subject, section, topic) with mock data. Test gap detection. Test with real farmOS data (pigeon pea, NURS.SH1-2, nursery topic).

### Item 3: Add `source-material` category + Drive folder convention
**Effort:** 30 minutes (convention + prompt update)
**Changes:**
1. Add `source-material` to the allowed category values in all system prompts
2. Document Drive folder convention in team briefing / system prompts
3. Update `media_links` field convention: can contain multiple comma-separated URLs (finished output + source folder)
4. Create example source-material KB entry (Olivier's cuttings source audio/photos)

**No code changes needed** — this is purely convention. The existing `add_knowledge` tool already supports any category string and multiple media_links.

### Item 4: Add topic-to-farmOS mapping config
**Effort:** ~1 hour
**Changes:**
1. **MCP `helpers.py` or new `config.py`**: Define `TOPIC_FARMOS_MAP` dict
2. **MCP `server.py`**: `farm_context` tool uses the map when called with `topic` parameter
3. Map initial topics to farmOS section prefixes:
   ```python
   TOPIC_FARMOS_MAP = {
       "nursery": {"section_prefix": "NURS.", "asset_types": ["plant", "structure"]},
       "compost": {"section_prefix": "COMP.", "asset_types": ["compost"]},
       "paddock": {"section_prefix": "P", "asset_types": ["plant", "land"]},
       "seeds":   {"section_prefix": "NURS.FR", "asset_types": ["seed"]},
       "irrigation": {"section_prefix": None, "asset_types": ["water", "equipment"]},
       "equipment": {"section_prefix": None, "asset_types": ["equipment"]},
       "infrastructure": {"section_prefix": None, "asset_types": ["water", "land"]},
       "camp": {"section_prefix": None, "asset_types": ["structure"]},
   }
   ```
4. Extensible: new topics just need a new dict entry

**Dependencies:** Item 2 (farm_context tool) — the map is consumed by that tool.

### Item 5: Enhance `query_sections` to return all location types
**Effort:** ~1 hour
**Changes:**
1. **MCP `farmos_client.py`**: New method or updated `fetch_sections()` that queries:
   - Land assets (paddock sections — existing)
   - Structure assets (nursery shelves, compost bays — new)
   - Grouped by type: `{"paddock": [...], "nursery": [...], "compost": [...], "other": [...]}`
2. **MCP `server.py`**: Update `query_sections` tool to include all location types
   - Optional `type` filter: `query_sections(type="nursery")` or `query_sections()` for all
   - Default: return all types, grouped
3. Nursery sections to include: NURS.SH1-1 through SH3-1, NURS.GR, NURS.GL, NURS.BCK, NURS.FRT, NURS.HILL, NURS.STRB, NURS.FRDG, NURS.FRZR (17 total)

**This directly addresses Olivier's March 18 request.**

**Testing:** Verify all 17 nursery sections appear. Verify paddock sections still work. Test type filter.

### Item 6: Update all 4 Claude system prompts
**Effort:** 30 minutes
**Changes:** Add to Agnes, Claire, James, and Olivier context files:

```
## Knowledge Base Schema

When creating or searching Knowledge Base entries:
- **category** is the CONTENT TYPE — what kind of document:
  tutorial, sop, guide, reference, recipe, observation, source-material
- **topics** are FARM DOMAINS — what areas of the farm it relates to (multi-value):
  nursery, compost, irrigation, syntropic, seeds, harvest, paddock, equipment, cooking, infrastructure, camp
- **tags** are FREE-FORM KEYWORDS for search — species names, techniques, specific tools

Example: A tutorial about taking comfrey cuttings in the nursery:
  category: tutorial
  topics: nursery, propagation
  tags: comfrey, root cutting, cuttings, potting

When saving source materials (audio, transcriptions, photos) to the Knowledge Base:
  category: source-material
  topics: (relevant domains)
  media_links: Google Drive folder URL containing the raw files
```

**Dependencies:** Do this LAST — after Items 1-5 are implemented and tested.

---

## Implementation Order

```
Item 1 (topics field)          ← foundation, do first
    │
    ├── Item 3 (source-material convention)   ← no code, just convention
    │
    ├── Item 5 (query_sections all locations)  ← independent, can parallel
    │
    └── Item 2 (farm_context tool)             ← needs topics field
            │
            └── Item 4 (topic-to-farmOS map)   ← consumed by farm_context
                    │
                    └── Item 6 (system prompts) ← do last, after testing
```

Items 1, 3, and 5 can be done in parallel.
Items 2 and 4 depend on Item 1.
Item 6 is last (after everything works).

**Total estimated effort:** 5-6 hours implementation + testing.

---

## Relationship to Phase 1b (Remote MCP Server)

These changes are to the Python MCP server. Two strategies:

**Strategy A: Implement in Python first, then port**
- Build all 6 items in Python MCP server (mcp-server/)
- Test with Agnes locally
- Port to TypeScript when doing Phase 1b
- Pro: Fast iteration, can test immediately
- Con: Work done twice

**Strategy B: Implement directly in TypeScript**
- Do Phase 1b first (remote server)
- Add these features in TypeScript from the start
- Pro: No double work
- Con: Slower to get cross-referencing working

**Recommended: Strategy A** — implement in Python now, especially Items 1, 3, 5, 6 which are small. The farm_context tool (Item 2) is the big one and can be ported cleanly since it's orchestration logic, not framework-specific.

The key insight from Agnes: "Can always enhance the MCP tools once the MCP server is remote — I won't need to update their laptops." This means: get the remote server running with current tools (Phase 1b), THEN add these enhancements server-side without touching any client machines.

**Pragmatic order:**
1. Items 1, 3, 5, 6 in Python (quick wins, fix the broken schema) — ~2 hours
2. Phase 1b: remote server with current 26 tools — critical path for March 22
3. Items 2, 4 (farm_context) — add to remote server, no laptop updates needed

---

## Open Questions

1. **Should `farm_context` be a single tool or three tools?** (`context_for_species`, `context_for_section`, `context_for_topic`). Single tool is simpler for the AI to discover; three tools are more explicit. Recommend: single tool with optional parameters.

2. **Should topics be validated against the vocabulary?** Strict validation prevents typos but blocks new topics. Recommend: warn on unknown topics but don't reject — log for review.

3. **Should the farm_context response include actionable suggestions?** e.g., "3 comfrey ready to transplant to P2R3 which has gaps". This adds significant logic but is very high value. Recommend: start with data assembly only, add suggestions in a later iteration.

4. **How should the Drive folder structure be enforced?** By convention (documented) or by code (Apps Script validates folder paths on upload). Recommend: convention only for now — the team is small and Olivier is disciplined.

---

*Document created: March 18, 2026*
*Author: Agnes + Claude Code session*
*Status: Design complete, implementation ready*
