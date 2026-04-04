# Photo Pipeline + Plant Identification — Design Document

> Created: April 4, 2026
> Status: Designed, ready for implementation
> Priority: HIGH — directly improves WWOOFer data quality
> Dependencies: import_observations photo wiring, farmOS file upload, generate_site.py

---

## 1. The Problem

Maverick's P2R5 transcript (April 4, 2026) exposed a critical gap: he couldn't identify
native trees (Tallowood, Prickly-leaved Paperbark, Rough Barked Apple, possibly Banagrass)
and had no visual reference on the QR pages to help. Meanwhile, photos ARE being captured
via QR observe pages but stop at Google Drive — they never reach farmOS or the landing pages.

The plumbing exists at every stage. Nothing is wired.

## 2. Current State — Where Photos Get Lost

```
observe.js (compress to 1200px JPEG @ 0.7 quality)
    ↓
Apps Script Observations.gs (decode base64, save to Drive)
    ↓
Google Drive: /Firefly Corner AI Observations/{YYYY-MM-DD}/{section_id}/
    │
    ├── observe_client.get_media(submission_id)  ← EXISTS, never called
    ├── farmos_client.upload_file(log_id)         ← EXISTS, never called
    └── import_observations                       ← IGNORES media completely
```

**Files with unused photo methods:**
- `mcp-server/observe_client.py` → `get_media(submission_id)` — fetches from Drive via Apps Script
- `mcp-server/farmos_client.py` → `upload_file(entity_type, entity_id, field_name, filename, binary_data)` — uploads to farmOS
- `mcp-server-ts/.../observe-client.ts` → same pattern
- `mcp-server-ts/.../farmos-client.ts` → same pattern

**Apps Script endpoint:** `handleGetMedia()` in Observations.gs returns `{files: [{filename, mime_type, data_base64}]}`

**Existing photos in Drive:** At least 14 observations from March 9 field test (Claire + James) with photos. These need backfill.

## 3. Design — Three-Layer Photo Architecture

### Layer 1: Observation Photos → farmOS Logs

Every observation with photos should have those photos attached to the farmOS log.

**Wire into import_observations (both Python + TypeScript):**
```
After creating farmOS log (Case A/B/C):
  1. Check if observation has media files (Sheet column "Media Files")
  2. If yes: observe_client.get_media(submission_id)
  3. For each file: farmos_client.upload_file(log_type, log_id, 'image', filename, binary_data)
  4. Log: "Uploaded {n} photos to farmOS log {log_id}"
```

**Error handling:** Photo upload failure should NOT block the observation import. Log the failure, continue.

### Layer 2: Species Reference Photos (Latest Wins)

The most recent observation photo for a species becomes the reference photo for that species
in the plant_type taxonomy.

**Logic (runs after Layer 1):**
```
After uploading photo to observation log:
  1. Determine species from the observation
  2. Get plant_type taxonomy term UUID for that species
  3. Upload same photo to plant_type term: upload_file('taxonomy_term/plant_type', uuid, 'image', ...)
  4. This overwrites previous species photo (latest always wins)
```

**Why latest wins:** The farm changes. A Pigeon Pea in April looks different from January.
The most recent field photo is always the most useful reference for species identification.

### Layer 3: QR Landing Pages Show Farm Photos + PlantNet Fallback

**On section view pages (P2R3.15-21.html etc.):**
Each plant card shows the species reference photo (from farmOS plant_type taxonomy).

**Photo source priority:**
1. **Farm photo** from farmOS plant_type image field → inline thumbnail
2. **PlantNet reference** link → "Identify this plant" button pre-filled with botanical name
3. **No photo** → species name + strata color only (current state)

**On observe pages (identification UX):**
```
WWOOFer taps "What is this plant?"
→ Camera opens via <input type="file" accept="image/*" capture="environment">
→ Photo sent to PlantNet API (CORS-enabled, free 500/day)
   + if farm reference photo exists for candidate species, show it side-by-side
→ PlantNet returns top 3 matches with confidence scores
→ Each match shows: species name + farm photo (if available) + PlantNet photo
→ WWOOFer confirms match → pre-fills observation form with species
→ If no match → logs as "unknown species" with photo attached
```

**PlantNet integration details:**
- API: `POST https://my-api.plantnet.org/v2/identify/all?api-key=KEY&lang=en`
- Accepts 1-5 images per query (send user photo + farm reference photo together)
- Returns botanical names → match against plant_types.csv `botanical_name`
- CORS enabled — direct from browser, no backend proxy
- Free tier: 500/day (farm needs ~10/week)
- Photos NOT stored by PlantNet (volatile memory only, GDPR compliant)

## 4. Image Sizing for Low Connectivity

The farm is in a low connectivity area. Image optimization is critical.

**Capture (observe.js — already implemented):**
- Max dimension: 1200px
- JPEG quality: 0.7
- Typical size: 100-200KB per photo

**farmOS storage:**
- Full resolution (1200px) stored on farmOS server (Farmier hosting)
- farmOS generates thumbnails automatically for API responses

**QR landing pages (generate_site.py):**
- Thumbnails only: 200px wide, JPEG quality 0.6 (~15-30KB each)
- Lazy loading: `loading="lazy"` on all `<img>` tags
- Placeholder: strata-colored silhouette until image loads
- Total page size target: < 500KB for a 20-plant section (vs current ~50KB text-only)

**PlantNet identification:**
- Compress to 800px before sending (PlantNet recommends 600px minimum)
- Single image per query to minimize upload on slow connection
- Show loading spinner: "Identifying plant..."
- Cache PlantNet results in sessionStorage to avoid repeat queries

## 5. farmOS as the Source

farmOS is the source of truth for photos, not Google Drive.

**Data flow:**
```
Drive (raw capture) → farmOS log (observation evidence) → farmOS taxonomy (species reference)
                                                              ↓
                                                    generate_site.py
                                                              ↓
                                                    QR pages (thumbnails)
```

**export_farmos.py changes needed:**
- Include image URLs in sections.json export
- For each plant: fetch species reference photo URL from plant_type taxonomy
- Photo URL format: `{farmos_url}/sites/default/files/{path}` (farmOS file serving)

**generate_site.py changes needed:**
- Download species thumbnails at build time (not runtime)
- Save to `site/public/images/species/{farmos_name}.jpg`
- Embed in plant cards with lazy loading
- PlantNet button for species without farm photos

## 6. Backfill — Existing Drive Photos

At least 14 observations from March 9 (Claire + James) have photos in Drive that never
reached farmOS. These need to be:

1. Listed: query Apps Script for all observations with media files
2. Matched: find corresponding farmOS observation logs by submission_id/date/section
3. Uploaded: fetch from Drive, upload to farmOS logs
4. Species reference: extract species, update taxonomy term photos

**Script needed:** `scripts/backfill_photos.py` or add to existing import workflow.

## 7. Implementation Order

```
Step 1: Wire import_observations to fetch + upload photos (Python)
        - Add media fetch/upload loop after log creation
        - Test with a new observation submission with photo
        - Backfill existing Drive photos

Step 2: Add species reference photo logic
        - After observation photo upload, copy to plant_type taxonomy
        - Latest photo always wins

Step 3: Update export_farmos.py + generate_site.py
        - Include species photo URLs in sections.json
        - Download thumbnails at build time
        - Embed in plant cards with lazy loading

Step 4: Add PlantNet identification to observe pages
        - "What is this plant?" button
        - Camera capture → PlantNet API → match against taxonomy
        - Show farm photo + PlantNet result side-by-side
        - Confirm → pre-fill observation form

Step 5: Port photo handling to TypeScript MCP
        - Same logic as Python, for Railway deployment

Step 6: Regenerate all QR pages with photos
```

## 8. Files to Modify

| File | Changes |
|------|---------|
| `mcp-server/server.py` | Wire media fetch + upload into import_observations |
| `mcp-server/observe_client.py` | Already has `get_media()` — no changes needed |
| `mcp-server/farmos_client.py` | Already has `upload_file()` — may need species photo method |
| `scripts/export_farmos.py` | Include species photo URLs in sections.json |
| `scripts/generate_site.py` | Download thumbnails, embed in plant cards, PlantNet fallback |
| `site/public/observe.js` | Add "What is this plant?" PlantNet identification flow |
| `mcp-server-ts/.../import-observations.ts` | Same photo wiring as Python |

## 9. New Dependencies

- PlantNet API key (free tier, sign up at my.plantnet.org)
- No new npm/pip packages needed (fetch + base64 already available)

---

*This document covers the full photo pipeline from capture to display, with PlantNet as
the AI identification fallback. Implementation order prioritizes wiring existing plumbing
(Step 1-2) before new features (Step 3-4).*
