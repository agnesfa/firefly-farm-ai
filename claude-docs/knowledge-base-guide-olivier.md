# Knowledge Base Guide — For Olivier

> This guide explains how to use the Knowledge Base with your Claude.
> Updated March 18, 2026.

---

## What Is the Knowledge Base?

The Knowledge Base is a shared library of farm knowledge — tutorials, guides, SOPs, references, and source materials. It lives in a Google Sheet and is accessible through Claude via MCP tools. Everything you save there is searchable by the whole team.

Your tutorials (Cuttings, Seedling Separation) are already in there!

---

## The Three Fields That Matter

When saving something to the Knowledge Base, there are 3 important metadata fields:

### 1. Category — WHAT TYPE of document is it?

Pick ONE from this list:

| Category | Use for | Example |
|----------|---------|---------|
| `tutorial` | Step-by-step learning | Tutorial 01 — Cuttings |
| `sop` | Standard operating procedure | Daily watering routine |
| `guide` | General how-to | WWOOFer waste management |
| `reference` | Lookup table, data reference | Nursery section IDs list |
| `recipe` | Cooking or compost recipes | Olivier's soup recipe |
| `observation` | Field notes, learnings | "Rats ate the chilli seedlings" |
| `source-material` | Raw files (audio, photos, transcriptions) | Cuttings workshop recordings |

**Important**: Category is the TYPE of document, NOT the topic. A tutorial about nursery work has `category: tutorial`, not `category: nursery`.

### 2. Tags — WHAT is it about?

Tags are keywords that help search. Include:

**Farm domains** (where on the farm):
`nursery`, `compost`, `irrigation`, `syntropic`, `seeds`, `harvest`, `paddock`, `equipment`, `cooking`, `infrastructure`, `camp`

**Plus specific keywords**: species names, techniques, tools, anything relevant.

Example for a cuttings tutorial:
```
tags: nursery, propagation, cuttings, banagrass, comfrey, tansy, root cutting, stem cutting
```

### 3. Related Plants & Sections — Cross-references

These connect your knowledge to farmOS data:
- `related_plants`: Species names exactly as they appear in farmOS (e.g., "Comfrey", "Banagrass")
- `related_sections`: farmOS section IDs (e.g., "NURS.SH1-2", "P2R3.15-21")

---

## How to Save Knowledge

### Saving a tutorial or guide

Tell Claude something like:

> "Save this as a tutorial in the Knowledge Base. Title: Tutorial 03 — Potting Mix. Category is tutorial. Tags: nursery, potting mix, soil preparation. Related plants: none. Author: Olivier."

Claude will use the `add_knowledge` tool to save it.

### Saving source materials (audio, photos, transcriptions)

When you have raw files in Google Drive that you want indexed:

> "Index these source materials in the Knowledge Base. Title: Source Materials — Cuttings Workshop March 2026. Category is source-material. Tags: audio, transcription, photos, nursery, propagation, cuttings. The Drive folder URL is [paste URL]. Related plants: Banagrass, Comfrey, Tansy."

This makes your raw recordings findable, so anyone can re-process them later.

### Drive folder convention

Put finished outputs in category folders, raw materials in `sources/` subfolders:

```
Knowledge Drive/
├── tutorials/
│   ├── 01-cuttings/
│   │   ├── FFC_Cuttings_Quicksheet.pdf          ← finished
│   │   └── sources/
│   │       ├── audio/                            ← your recordings
│   │       ├── transcriptions/                   ← Whisper output
│   │       └── photos/                           ← field photos
│   └── 02-seedling-separation/
│       └── ...
├── guides/
├── sops/
├── references/
└── source-library/                               ← unprocessed raw materials
    └── olivier-nursery-march2026/
```

---

## How to Find Knowledge

### Search

> "Search the knowledge base for cuttings"
> "Find anything about nursery propagation"
> "Is there a tutorial about potting mix?"

### Browse

> "List all tutorials in the knowledge base"
> "Show me everything in the knowledge base"

### Nursery sections (NEW)

You can now query nursery locations:

> "Show me all nursery sections" → uses `query_sections(row="NURS")`
> "What's planted on Shelf 1?" → uses `get_inventory(section_id="NURS.SH1-1")`

---

## Quick Reference Card

| I want to... | Tell Claude... |
|-------------|----------------|
| Save a tutorial | "Save this as a tutorial. Category: tutorial. Tags: nursery, [topics]" |
| Save a guide | "Save this guide. Category: guide. Tags: [topics]" |
| Save source files | "Index these as source-material. Category: source-material. Tags: audio, [topics]. Media link: [Drive URL]" |
| Find something | "Search the knowledge base for [topic]" |
| List tutorials | "List all tutorials" (uses `list_knowledge(category="tutorial")`) |
| Update an entry | "Update tutorial 01 — add rosemary to related plants" |
| Check nursery | "Show me nursery sections" or "What's on shelf 2?" |

---

## Common Mistakes to Avoid

| Wrong | Right | Why |
|-------|-------|-----|
| `category: nursery` | `category: tutorial` | "nursery" is a topic, not a document type |
| `category: compost` | `category: guide` | Same — compost is what it's about, guide is what it is |
| No tags | `tags: nursery, propagation, comfrey` | Tags make entries searchable |
| No related_plants | `related_plants: Comfrey, Banagrass` | Connects knowledge to farmOS data |

---

## Your Workflow (Tutorial Production)

1. **Record** audio + photos in the field
2. **Transcribe** with Whisper → .txt files
3. **Organise** files in Drive folder (tutorials/{number}-{topic}/sources/)
4. **Tell Claude** to read transcriptions + photos
5. **Claude produces** the tutorial content
6. **Save to KB**: `category: tutorial`, tags with domains + species, related_plants, related_sections
7. **Index sources**: `category: source-material`, Drive folder URL, same tags
8. **Write session summary** so the team knows what was created

---

*Last updated: March 18, 2026*
