# Retrospective: March 2026 — Architecture Learnings, Media Strategy & Updated Roadmap

*Written March 9, 2026 after completing Phase 0, Phase A, Phase H1, and Phase 1.*

---

## Part 1: MCP Experience Retrospective

### What Worked Well

**1. Raw HTTP over farmOS.py for the MCP server**
The decision to use raw HTTP requests (via Python `requests`) instead of the farmOS.py library for the MCP server was vindicated. The pydantic v1/v2 conflict would have been a showstopper. Raw HTTP gave us:
- Full control over pagination (CONTAINS filter, page[limit])
- No dependency conflicts (separate venv with just FastMCP + requests)
- Direct access to farmOS JSON:API features like computed inventory on assets
- Ability to handle edge cases (ISO vs Unix timestamps, relationship fields)

**2. Server-side CONTAINS filter**
The single most impactful pattern. With 400+ plants and 750+ logs, client-side pagination fails (caps at ~250). Pushing filtering server-side via `?filter[name][operator]=CONTAINS&filter[name][value]=P2R3.15-21` returns exactly what we need in 1-2 pages. This pattern is reusable across any farmOS query.

**3. STDIO transport for development**
Starting with STDIO (not HTTP) was right. Zero networking complexity, instant testing via Claude Code's MCP config. The tools were testable the same session they were built.

**4. 10 focused tools (not 50)**
The MCP server has exactly the tools needed for real farm operations:
- 6 read tools (query plants, sections, plant detail, logs, inventory, plant types)
- 4 write tools (create observation, activity, plant; update inventory)
This covers 95% of Agnes's daily needs. Resist the urge to add tools until there's a concrete use case.

### What Was Painful

**1. farmOS.py pagination bug**
`client.asset.iterate()` and `client.term.iterate()` silently return incomplete results with 200+ entities. This caused hours of debugging during the plant types migration. The fix (raw HTTP with `page[limit]=50` + follow `links.next`) is now a documented pattern, but the farmOS.py library should be considered unreliable for large datasets.

**2. Plant name parsing complexity**
The asset naming convention `{date} - {species} - {section}` breaks when species contain ` - ` (e.g., "Basil - Sweet (Classic)"). Every parser needs the first/last segment logic. This is a tax on every new script.

**3. Inventory system indirection**
Understanding that inventory is a *computed attribute* on assets (derived from Quantity entities on observation logs with `inventory_adjustment: "reset"`) required reading live API responses. The farmOS documentation doesn't make this clear. Once understood, it simplified everything — just read `asset.attributes.inventory` directly.

### Architecture Learnings for the MCP Layer

**The MCP server should be the ONLY interface to farmOS for all users.** Currently:
- Agnes uses MCP tools via Claude Code (Phase 1a, STDIO)
- Scripts (import_fieldsheets.py, import_historical.py) use farmOS.py directly
- export_farmos.py uses farmOS.py for auth + raw HTTP for queries

**Target architecture:**
```
Claire (Claude Desktop) ──→ MCP Server (HTTP) ──→ farmOS API
James  (Claude Desktop) ──→ MCP Server (HTTP) ──→ farmOS API
Agnes  (Claude Code)    ──→ MCP Server (STDIO) ──→ farmOS API
Scripts (Python)        ──→ MCP Server (HTTP)  ──→ farmOS API  (future: replace direct API)
Observe pages (JS)      ──→ Apps Script ──→ Google Sheet ──→ review ──→ MCP Server ──→ farmOS
```

The MCP server becomes the single gateway. Benefits:
- One place to handle pagination, CONTAINS filters, name parsing
- One place to enforce business rules (naming conventions, inventory logic)
- Claire and James get the same capabilities as Agnes
- Scripts can be simplified to just call MCP tools

**Phase 1b (HTTP transport) is critical** — it's what unlocks multi-user access.

### MCP Tool Gaps (for next iteration)

| Gap | Priority | Notes |
|-----|----------|-------|
| File/media upload | HIGH | Upload photos to farmOS logs/assets (binary POST) |
| Bulk operations | MEDIUM | Import multiple observations in one call |
| Search across entities | MEDIUM | Find all logs mentioning "frost" across sections |
| Archive/delete plant | LOW | Mark plants as archived when count reaches 0 |
| Seed management | LOW | Phase 3 — create/track seed assets |

---

## Part 2: Media Management Analysis & Proposal

### Current State

**Where photos live today:**
1. **Google Drive** — `Firefly Corner AI Observations` folder
   - Structure: `{root}/{YYYY-MM-DD}/{section_id}/`
   - Raw JSON archives alongside photos
   - Free storage (15GB shared with Gmail)
   - Accessible via Drive UI or Apps Script

2. **Observe.js client-side** — captures and compresses before upload
   - Max 1200px, JPEG quality 0.7 (~150-300KB per photo)
   - Base64 encoded in POST payload
   - Stripped from offline queue (too large for localStorage)

3. **Google Sheet** — column M lists filenames (comma-separated)
   - No direct link to Drive files
   - Used for review workflow tracking

**What farmOS supports:**
- `image` and `file` relationship fields on ALL assets and logs (base fields)
- Binary upload: `POST /api/log/{type}/{uuid}/image` with raw binary body
- Content-Disposition header for filename
- CORS enabled for Content-Disposition
- Auto-cleanup of orphaned files via Drupal cron

**What doesn't exist yet:**
- No farmOS ↔ media integration (photos stay in Drive)
- No audio/video capture in observe.js
- No media viewer in section pages
- No plant identification from photos
- No MCP tool for file upload

### Storage Options Analysis

| Option | Cost | Performance | Accessibility | Scalability |
|--------|------|-------------|---------------|-------------|
| **Google Drive** (current) | Free (15GB) | OK for upload, slow for serving | Drive UI, Apps Script API | Limited by Google account quota |
| **farmOS native** (Drupal files) | Server disk ($) | Fast for farmOS, slow for external | API only, needs auth | Limited by server disk + PHP memory |
| **Cloud storage** (S3/GCS/R2) | ~$0.02/GB/mo | CDN-fast for serving | Public URLs, API | Unlimited |
| **GitHub LFS** | Free tier (1GB) | Slow writes, fast reads via CDN | Public via GitHub Pages | Poor for frequent writes |

### Recommended Architecture: Tiered Media Storage

```
                    ┌─────────────────────────────────┐
                    │     OBSERVE PAGE (Phone)         │
                    │  📷 Photo  🎙 Audio  🎥 Video    │
                    └──────────────┬──────────────────┘
                                   │ compressed upload
                                   ▼
                    ┌─────────────────────────────────┐
                    │     GOOGLE DRIVE (Working)       │
                    │  Quick storage, review workflow  │
                    │  Free, accessible, Apps Script   │
                    │  Retention: 90 days after import │
                    └──────────────┬──────────────────┘
                                   │ approved + imported
                                   ▼
                    ┌─────────────────────────────────┐
                    │     farmOS (Permanent Record)    │
                    │  Photos on observation logs      │
                    │  Photos on plant assets          │
                    │  Linked via image/file fields    │
                    │  Binary upload via MCP server    │
                    └──────────────┬──────────────────┘
                                   │ export for pages
                                   ▼
                    ┌─────────────────────────────────┐
                    │   LANDING PAGES (Public View)    │
                    │  Compressed thumbnails on pages  │
                    │  Served from GitHub Pages or CDN │
                    └─────────────────────────────────┘
```

**Tier 1: Google Drive (Working Storage)**
- Keep current architecture for capture and review
- Photos arrive via observe.js → Apps Script → Drive
- Claire/James review with photos visible in context
- Add: audio recording (MediaRecorder API → webm → Drive)
- Add: short video clips (same pipeline)
- Retention: auto-archive/delete 90 days after import to farmOS

**Tier 2: farmOS (Permanent Record)**
- After approval, upload photos to farmOS observation logs via MCP
- Each observation log gets its photos attached via `image` field
- Plant assets get "best photo" attached for identification
- Binary upload: `POST /api/log/observation/{uuid}/image`
- This becomes the source of truth for media-to-plant associations
- Storage: margregen.farmos.net server disk (hosted, included in plan)

**Tier 3: Landing Pages (Public Display)**
- During page generation, export_farmos.py fetches photo URLs from farmOS
- Compress to thumbnails (400px max) for fast mobile loading
- Serve from GitHub Pages (free) or CDN if needed
- Photo gallery in expanded plant card view

### Why NOT a dedicated cloud bucket (yet)

- Adding S3/GCS/R2 introduces: account setup, IAM, billing, CORS config, URL signing
- farmOS already has file storage included in the hosting plan
- Google Drive is free and already working
- When/if we hit limits (>5GB photos, >50ms latency), migrate to R2 (Cloudflare, no egress fees)
- Keep the architecture simple: 2 existing systems (Drive + farmOS) before adding a 3rd

### Audio & Video Strategy

**Audio (voice notes):**
- Capture: MediaRecorder API in observe.js → webm/opus format
- Compress: Keep under 500KB for ~30 second notes (opus is efficient)
- Storage: Same pipeline as photos (Drive → farmOS)
- Processing: Claude can transcribe audio to text for farmOS log notes
- UI: 🎙 Record button alongside 📷 Photo button in observe pages

**Video (short clips):**
- Capture: MediaRecorder API → webm/VP8 (or mp4 if Safari)
- Limit: 15 seconds max (field clips, not documentaries)
- Compress: 720p max, ~2-5MB per clip
- Storage: Drive only initially (too large for farmOS efficiently)
- Processing: Future — frame extraction for plant identification
- UI: 🎥 Record Video button (Phase B+)

**Transcription pipeline (future):**
```
Audio recording → Drive → Claude transcription → farmOS log notes
```
This eliminates the biggest friction in field logging: typing on a phone in the sun with dirty hands. Claire can just say "Three pigeon peas dead from frost in section 3.14-21, comfrey looking healthy, new volunteers planted this morning" and Claude converts it to structured observations.

### Plant Identification from Photos (Future)

**Near-term (Phase B2):**
- Reference photos per plant type (curated, stored in farmOS as plant_type taxonomy media)
- Shown on landing pages in expanded plant cards
- Sources: farm photos (best ones), Daleys Nursery (with attribution), own photography

**Medium-term (Phase 4+):**
- Claude vision API to identify plants from field photos
- Worker takes photo → "What plant is this?" → Claude identifies from reference database
- Confidence scoring against known species in section
- Auto-suggest species for Unknown Plant observations

**Long-term:**
- Training on farm-specific photos (Firefly Corner plants in their actual environment)
- Pest/disease detection from leaf photos
- Growth tracking from periodic photos of same plant

---

## Part 3: Updated Roadmap

### Immediate Priority: Stabilise Review Workflow (This Week)

**Goal:** Claire and James can independently review and approve observations using their own Claude instances.

**What's needed:**
1. Claire's Claude Desktop configured with shared project context (`claude-docs/claire-desktop-context.md`)
2. James's Claude Desktop configured similarly
3. The `/review-observations` skill works reliably for both
4. Approved observations flow to farmOS via Agnes's MCP (for now)

**Workflow:**
```
Observer (phone) → observe page → Google Sheet (pending)
Claire (Claude Desktop) → /review-observations → Sheet (reviewed/approved)
Agnes (Claude Code) → /review-observations → Sheet (approved) → farmOS (imported)
```

Phase 1b (HTTP MCP) will let Claire approve directly to farmOS, removing Agnes as bottleneck.

### Revised Phase Roadmap

| Phase | Name | Priority | Status | Target |
|-------|------|----------|--------|--------|
| **A.1** | Stabilise review workflow | P0 | NEXT | This week |
| **A.2** | Claire/James Claude Desktop setup | P0 | NEXT | This week |
| **1b** | MCP HTTP transport | P1 | PLANNED | Week 2 |
| **B.1** | Audio capture in observe.js | P1 | PLANNED | Week 2-3 |
| **B.2** | Reference photos per plant type | P2 | PLANNED | Week 3-4 |
| **C** | Observation → farmOS import pipeline | P1 | PLANNED | Week 2-3 |
| **M.1** | farmOS media upload (MCP tool) | P1 | PLANNED | Week 3 |
| **M.2** | Photo display on landing pages | P2 | PLANNED | Week 4 |
| **M.3** | Audio transcription pipeline | P2 | PLANNED | Month 2 |
| **M.4** | Video capture (15s clips) | P3 | PLANNED | Month 2 |
| **M.5** | Plant identification from photos | P3 | PLANNED | Month 3+ |
| **H2** | Dead plant asset creation | P3 | PLANNED | Month 2 |
| **2** | Claire's first real log via Claude | P1 | PLANNED | Week 3 |
| **3** | Nursery & Seed Bank | P2 | PLANNED | Month 2-3 |
| **4** | farm_syntropic Drupal module | P3 | PLANNED | Month 3+ |

### Phase A.1: Stabilise Review Workflow (Immediate)

**Tasks:**
1. Test `/review-observations` skill end-to-end with Claire's account
2. Ensure sheet column ordering matches skill expectations
3. Add batch approval (approve multiple observations at once)
4. Add summary view: "3 sections reviewed, 12 observations pending, 2 need photos"
5. Document the workflow for Claire and James

**Success criteria:** Claire reviews and approves 10+ observations without Agnes's help.

### Phase B.1: Audio Capture

**Tasks:**
1. Add MediaRecorder API to observe.js
2. Audio format: webm/opus, 30s max, ~500KB
3. UI: 🎙 Hold-to-record button in all modes
4. Upload same pipeline as photos (base64 in payload)
5. Code.gs: detect audio MIME type, save to Drive as .webm
6. Sheet: track audio files in Media Files column

**Note:** Audio transcription (converting voice to text) comes later in Phase M.3. For now, just capture and store.

### Phase C + M.1: Observation Import + Media Upload

**Tasks:**
1. Build `import_observations.py` script:
   - Fetch approved observations from Google Sheet
   - Download associated photos from Google Drive
   - Create farmOS observation logs with inventory quantities
   - Upload photos to observation logs via binary POST
   - Update Sheet status to "imported"
2. Add `upload_file` MCP tool:
   - Accept file path or binary data
   - Upload to farmOS entity (log or asset)
   - Attach via `image` or `file` relationship field
3. Add `attach_photo_to_plant` convenience tool:
   - Find plant asset by name
   - Upload photo and attach to asset's `image` field

### Phase M.2: Photo Display on Landing Pages

**Tasks:**
1. Export photo URLs from farmOS during sections.json generation
2. Generate compressed thumbnails (400px) during page build
3. Add photo to plant card (collapsed: small thumbnail, expanded: full gallery)
4. Mobile-optimized: lazy loading, progressive JPEG
5. Consider: plant type reference photos from curated sources

---

## Part 4: Key Decisions for Agnes

1. **Cloud storage**: Stick with Drive + farmOS for now? Or set up Cloudflare R2 early?
   - Recommendation: Drive + farmOS. Revisit if >5GB photos or latency issues.

2. **Audio format**: webm/opus (Chrome/Firefox native) vs mp4/AAC (Safari preferred)?
   - Recommendation: webm first (most workers use Android), Safari fallback later.

3. **Photo retention**: How long to keep in Drive after farmOS import?
   - Recommendation: 90 days, then auto-archive to a "completed" Drive folder.

4. **Plant identification**: Build custom or use Claude Vision API?
   - Recommendation: Claude Vision API (no training needed, already paid for, handles novel plants).

5. **Video**: Worth the storage/bandwidth cost?
   - Recommendation: Defer to Month 2. Audio covers 90% of the use case. Video is nice-to-have.

---

*This document captures the team's learnings after 6 days of intensive development (March 4-9, 2026). Review and update monthly.*
