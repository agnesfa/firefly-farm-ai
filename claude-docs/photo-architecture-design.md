# Photo Architecture — Full Design Document

> Created: April 12, 2026
> Status: Designed, pending Agnes review
> Context: Retrospective from the April 11-12 photo pipeline hardening session
> Predecessor: claude-docs/photo-pipeline-and-plant-id-design.md (April 4)

---

## Part 1 — Session Retrospective: What We Learned About the Semantic Layer

### What happened

In one session we: pushed the photo pipeline, ran a backfill that attached
section-level landscape shots as species reference photos for ALL 35 species
in those sections, discovered every single one was wrong via PlantNet audit,
cleaned them all out, rewrote the backfill with verification, then manually
scanned Drive folders to find 4 genuinely usable photos across 30 candidates.

### Six semantic layer gaps this exposed

**1. No concept of EVIDENCE or MEDIA as a first-class entity**

The ontology defines Species, Plant, Section, Log — but not Photo, Media,
or Evidence. A photo is currently just a binary blob attached to a log or
taxonomy term. It has no provenance, no verification status, no relationship
chain. The ontology needs:
- `Media` entity type with source attribution
- `verified_by`, `verification_confidence`, `verification_method` attributes
- Relationships: Media → Log → Plant → Section → Row (full trace)

**2. No trust hierarchy across data sources**

The Okra discrepancy (transcript said 11, QR said 6) exposed that we have
no model for source precedence. Currently everything that lands in farmOS
is treated as equally trusted. The semantic layer should define:

| Source | Trust Level | Reconciliation Rule |
|--------|------------|---------------------|
| farmOS direct (Claire/Agnes) | highest | Always authoritative |
| QR observation (field worker, reviewed) | high | Supersedes transcript |
| Audio transcript (processed by Claude) | medium | Cross-reference, flag conflicts |
| PlantNet identification | supporting | Verification only, never authoritative |
| Backfill/import (automated) | low | Requires human review gate |

When sources conflict, the semantic layer should surface the conflict with
both values and the trust ranking, not silently pick one.

**3. No data quality dimension in the growth model**

`farm_growth.yaml` has Farm (biological), System (technical), Team (human)
dimensions but no **Data Quality** dimension. This session showed that bad
data propagates silently and compounds. Metrics needed:

- **Species photo coverage**: % of species with a verified reference photo
- **Observation completeness**: % of observations with structured species data
- **Verification rate**: % of photos that pass PlantNet verification
- **Provenance coverage**: % of data with traceable origin
- **Conflict rate**: count of unresolved source conflicts (like the Okra case)
- **Time-to-import**: lag between observation and farmOS entry

These should surface in `system_health` alongside the existing 3 dimensions.

**4. No external reference bridging model**

PlantNet uses different botanical names than our taxonomy (Bergera vs Murraya,
Typha latifolia vs Typha spp., Davidsonia pruriens vs jerseyana). We built
`plantnet_bridge.csv` as a quick fix, but the semantic layer should define
this as a general concept: **External Reference Mapping**.

Any external system (PlantNet, GBIF, Australian Plant Census, seed suppliers)
may use different nomenclature. The ontology should have:
- `ExternalReference` entity with system, external_id, local_id, match_type
- `bridge_coverage`: % of species with validated external reference mappings
- Automatic flagging of unmapped species when encountered

**5. No observation pipeline health metrics**

The 23 pending observations sat for 8 days (April 3→11). We have no metric
for pipeline throughput. Needed:
- **Pending observation age**: max/mean days in pending status
- **Import success rate**: % of observations that import cleanly
- **Duplicate detection rate**: % caught before creating duplicate assets
- **Rejection rate**: % rejected with reasons (helps identify training needs)

**6. Section-level vs species-level photo semantics are conflated**

The backfill disaster happened because we treated "a photo taken in section X"
as "a photo of species Y in section X". These are fundamentally different:
- **Section photo**: documents the overall state of the section at a point in time
- **Species photo**: close-up of a single identifiable plant, suitable as reference

The semantic layer should distinguish these and only allow species-level photos
to become reference photos. Section photos are valuable documentation but are
NOT species identification references.

---

## Part 2 — Photo Architecture Design

### Core Principle

**Every photo has provenance.** A photo without a traceable origin and
verification status is untrustworthy and should not be shown as a species
reference.

### Entity Model

```
Media (NEW entity type)
├── id: UUID
├── source_type: observation | plantnet_stock | manual_upload
├── source_id: observation log UUID | PlantNet query ID | upload session
├── photo_level: species_closeup | section_landscape | detail_macro
├── species_claim: farmos_name (what the submitter says it is)
├── verification_status: unverified | verified | rejected
├── verification_method: plantnet | human_review | none
├── verification_confidence: 0.0-1.0
├── verified_botanical: PlantNet's botanical match
├── captured_by: observer name
├── captured_at: ISO timestamp
├── section_id: where the photo was taken
├── file_paths:
│   ├── original: farmOS file URL (authenticated)
│   ├── thumbnail: photos/{slug}.jpg (112px, public)
│   └── lightbox: photos/{slug}-full.jpg (800px, public)
└── relationships:
    ├── log: farmOS log UUID (observation evidence)
    ├── plant_asset: farmOS plant UUID (if identifiable)
    ├── species: farmos_name → plant_type taxonomy
    └── section: section_id → land asset
```

### Two-Tier Display System

Each species on the farm has two possible photo sources, shown with
visual distinction:

**Tier 1 — Farm Observation Photo (preferred)**
- Source: a real photo taken by a worker on this farm
- Verified: passed PlantNet verification (≥30% confidence + botanical match)
- Visual: no badge needed — this IS the plant, on this farm
- Updates: latest observation photo always replaces previous (latest-wins)
- Shows: on plant cards in section view pages

**Tier 2 — PlantNet Stock Photo (fallback)**
- Source: PlantNet API returns a reference image with each identification
- Visual: small "🌐 PlantNet" or "📚 Reference" badge on the thumbnail
- Purpose: helps WWOOFers identify species they haven't seen yet
- Updates: fetched once per species at build time, cached
- Shows: only when no Tier 1 photo exists for that species

```
Display logic (generate_site.py):
  if species has farm observation photo → show Tier 1 (no badge)
  elif species has PlantNet stock photo → show Tier 2 (with badge)
  else → no photo (current behavior — species name + strata color only)
```

### PlantNet Stock Photo Population

At build time, `export_farmos.py` fetches a PlantNet reference image for
every species that has a botanical name but NO farm observation photo:

```python
for species in all_species:
    if species.has_farm_photo:
        continue  # Tier 1 exists, skip
    if not species.botanical_name:
        continue  # Can't query PlantNet without botanical name
    
    # Query PlantNet for a reference image
    result = plantnet_search(species.botanical_name)
    if result.images:
        download(result.images[0], f"photos/ref-{slug}.jpg")  # thumbnail
        download(result.images[0], f"photos/ref-{slug}-full.jpg")  # lightbox
        species.photo_url = f"photos/ref-{slug}.jpg"
        species.photo_source = "plantnet_stock"
```

PlantNet API: `GET /v2/species/{botanical_name}` returns reference images.
Free tier covers this (one-time batch at build, not per-request).

Rate limit: ~296 species × 1 call = 296 calls. Well within 500/day.
Cache: store results so rebuild doesn't re-fetch unchanged species.

### Photo Provenance Tracking

Every photo in the system carries metadata about where it came from:

```json
{
  "photo_url": "photos/papaya.jpg",
  "photo_full_url": "photos/papaya-full.jpg",
  "photo_source": "farm_observation",
  "photo_source_detail": {
    "observer": "James",
    "date": "2026-03-09",
    "section": "P2R5.44-53",
    "log_id": "uuid-of-observation-log",
    "verification": {
      "method": "plantnet",
      "confidence": 0.86,
      "botanical_match": "Carica papaya"
    }
  }
}
```

For PlantNet stock photos:
```json
{
  "photo_url": "photos/ref-macadamia.jpg",
  "photo_source": "plantnet_stock",
  "photo_source_detail": {
    "botanical_query": "Macadamia integrifolia",
    "fetched_at": "2026-04-12",
    "plantnet_image_url": "https://..."
  }
}
```

This metadata flows through `sections.json` and is available to
`generate_site.py` for rendering the badge and tooltip.

### Visual Indicators on QR Pages

**Tier 1 (farm photo):**
- Thumbnail with zoom-in cursor
- Lightbox on click (800px)
- No badge — it's the real plant from your farm

**Tier 2 (PlantNet stock):**
- Thumbnail with zoom-in cursor  
- Small `📚` badge in bottom-right corner of thumbnail
- Lightbox on click with banner: "Reference photo from PlantNet — not from this farm"
- Tooltip on hover: "Reference photo · Source: PlantNet · {botanical_name}"

### Latest-Wins Update Logic

When a new observation comes through `import_observations`:

```
1. Photo captured by worker → attached to farmOS log (always)
2. PlantNet verification gate:
   - PASS (≥30% + botanical match) → set as species reference photo
     - Overwrites previous Tier 1 photo (latest-wins)
     - If Tier 2 existed, Tier 1 now takes precedence
   - FAIL → photo stays on log as section documentation
     - NOT set as species reference
     - Does not affect Tier 1 or Tier 2 display
3. At next regenerate_pages:
   - export_farmos.py downloads the new reference photo
   - Creates both thumbnail + lightbox sizes
   - generate_site.py renders it on all section pages with that species
```

### Build Pipeline Changes

```
export_farmos.py
├── fetch_species_photo_urls()          # existing — farm observation photos
├── fetch_plantnet_stock_photos()       # NEW — fallback for species without farm photos
├── download both at two sizes:
│   ├── {slug}.jpg (112px thumbnail)
│   └── {slug}-full.jpg (800px lightbox)
├── For PlantNet stock: prefix with ref- to distinguish
│   ├── ref-{slug}.jpg
│   └── ref-{slug}-full.jpg
└── Write photo_source metadata into sections.json

generate_site.py
├── render_plant_card():
│   ├── if photo_source == "farm_observation" → thumbnail, no badge
│   ├── elif photo_source == "plantnet_stock" → thumbnail + 📚 badge
│   └── else → no photo
├── Lightbox JS:
│   ├── farm photos → clean lightbox
│   └── PlantNet stock → lightbox with "Reference photo" banner
```

### Data Model Changes

**farm_ontology.yaml** — add Media entity:
```yaml
Media:
  description: >
    A photo or document with traceable provenance. Every media item
    has a source, verification status, and relationship chain back
    to the farm entities it documents.
  attributes:
    - source_type    # observation | plantnet_stock | manual_upload
    - photo_level    # species_closeup | section_landscape
    - verification_status  # unverified | verified | rejected
    - verification_method  # plantnet | human_review
    - verification_confidence  # 0.0-1.0
```

**farm_semantics.yaml** — add data quality metrics:
```yaml
data_quality:
  species_photo_coverage:
    definition: "Fraction of active species with a verified reference photo"
    calculation: "species_with_farm_photo / total_active_species"
    interpretation:
      direction: higher_is_better
      thresholds:
        equipped: 0.50    # Half of species have photos
        growing: 0.25
        minimal: 0.10
        dormant: 0.0

  observation_pipeline_health:
    definition: "Max age in days of pending observations"
    interpretation:
      direction: lower_is_better
      thresholds:
        healthy: 3
        fair: 7
        concerning: 14

  external_reference_coverage:
    definition: "Fraction of species with validated PlantNet bridge mapping"
    calculation: "species_in_bridge / species_with_botanical_name"
```

**farm_growth.yaml** — add Data dimension (D1-D4):
```yaml
data:
  description: "Quality, completeness, and trustworthiness of farm data"
  stages:
    - name: raw
      label: "D1: Raw"
      trigger: "Data exists but unverified"
    - name: structured
      label: "D2: Structured"
      trigger: "Data in farmOS with ontology compliance"
    - name: verified
      label: "D3: Verified"
      trigger: "Cross-referenced with external sources, conflicts resolved"
    - name: governed
      label: "D4: Governed"
      trigger: "Provenance tracked, quality metrics meeting thresholds"
```

### Implementation Order

```
Phase 1: PlantNet stock photos (build-time batch)
  - Add fetch_plantnet_stock_photos() to export_farmos.py
  - Download reference images for species without farm photos
  - Add photo_source to sections.json
  - Render 📚 badge in generate_site.py
  → Immediate visual improvement: ~200 species get photos

Phase 2: Provenance metadata
  - Add photo_source_detail to sections.json
  - Lightbox shows source info
  - Tooltip on thumbnail hover
  → Transparency: users know where each photo came from

Phase 3: Semantic layer evolution
  - Add Media entity to ontology
  - Add data_quality metrics to semantics
  - Add Data dimension to growth model
  - Surface in system_health
  → Governance: quality metrics drive priorities

Phase 4: Trust hierarchy + conflict resolution
  - Define source precedence in semantics.yaml
  - farm_context surfaces conflicts with both values + trust ranking
  - Auto-flag unresolved conflicts as pending tasks
  → Intelligence: the system catches inconsistencies humans miss
```

### What This Does NOT Cover (Parked)

- **Video** — not needed yet, same architecture when it is
- **Drone/aerial photos** — separate tile system already exists
- **Photo editing/cropping** — manual step, not automated
- **Multi-photo per species** — latest-wins is sufficient for now
- **Photo-based health assessment** — ML feature, future roadmap

---

*This document supersedes the photo sections of
claude-docs/photo-pipeline-and-plant-id-design.md (April 4).
The pipeline implementation is done; this covers the architecture
that governs how photos flow through the system and what they mean.*
