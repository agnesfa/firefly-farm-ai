# Pending decisions — 2026-04-22 autonomous import session

**Context:** Autonomous import run on 2026-04-22 cleared the full 124-submission backlog + the 35 stale pre-Apr-21 approvals. Surfaced 6 bug classes in the photo/import pipeline, all of which are now fixed + deployed. 17 plant_types had their reference photos manually re-patched after an audit discovered every "promotion" tonight was a silent lie.

## Resolution status

### F1 — NURS.GR junk row with empty submission_id
**RESOLVED 2026-04-22 by Agnes:** row deleted directly in Google Sheet.

### F2 — Coriander plant_type reference photo
**RESOLVED 2026-04-22:** plant_type image PATCHED manually via direct farmOS API to Kacper's `65520376_P2R5.22-29_plant_001.jpg` (71 KB, correct Coriander). Agnes confirmed the photo is a real coriander. QR pages regenerated + pushed in commit d10acc9; GitHub Pages picking up.

### F3 — Cuban Jute / invasive species handling
**RESOLVED:** Agnes confirmed identification is correct, Cuban Jute is an invasive in Australia. Kept as section observation on the P2R5.22-29 section log (no plant_type creation). Backlog item created: `memory/project_invasive_species_handling.md` — design question for how to represent weeds/invasives in farmOS (section-note-only vs first-class with invasive tag vs KB-entry approach). Deferred, to be discussed alongside Charter+Principles v2 review.

### F4 — 35 stale approved-but-never-imported submissions
**RESOLVED 2026-04-22:**
- **Rejected 20** (Maverick + Kerstin Apr 3 new_plant submissions for P2R5.x) — existing plant assets in farmOS already reflect those counts from an earlier bulk-import pathway; re-importing would have created duplicate assets.
- **Imported 15** (9 Daniel P1R3 chop-and-drop/weeding comments + 1 Olivier water-leak comment + 1 Agnes Mint "Found it!" + 4 Hadrien Mar 11 submissions incl. P2R2.23-26 inventory + Geranium/Jacaranda new_plants + Achiote reclassification note).
- **Root cause of stale accumulation:** photos on these old submissions use the PRE-ADR-0005 naming (no submission_id prefix) so the importer's photo fetcher couldn't cleanly match them → silent failures → sheet status never flipped to `imported`. Observability gap filed as **ADR 0007 Fix 7** (periodic stale-approval check).

### F5 — Pipeline observation notes
**RESOLVED 2026-04-22:** ADR 0007 updated with:
- Fix 5 minimal shipping context (commit 528a23b + 3ad2f27)
- Fix 7 (new): observability for stale approvals — daily check + skill preflight + import-run aggregate logging
- Silent-promotion bug context + test-usefulness lesson folded into the ADR narrative

### Additional issues found + resolved during the session

**F6 — Silent species-reference photo promotion (discovered mid-session, fixed)**
The import pipeline reported `species_reference_photos_updated: 1` for every species whose photo got uploaded, but the plant_type.image relationship was NOT actually updated — 8 of 8 audited plant_types still pointed at stock/pre-ADR-0005 photos. Root cause: `uploadFile` returned `data[0]` of a multi-entry farmOS response (the PRIOR file's id) instead of `data[-1]` (the newly uploaded). Downstream `patchRelationship` then overwrote the image with the prior file id, orphaning the newly uploaded file in farmOS storage.
- **Fixed:** commit 3ad2f27 (TS + Python both return `data[-1]`)
- **Recovered:** `scripts/fix_species_reference_photos_2026_04_22.py` swept 33 species with recent tier-2+ photos, patched 17 plant_types, skipped 17 already-correct
- **Tests added:** 5 Python + 1 TS covering multi-entry list case (previous fixtures only had single-entry lists, masking the bug)
- **Logged as SDLC gap:** `claude-docs/sdlc-with-ai-design-thinking-2026-04-22.md`

## Test plan for 2026-04-23 — end-to-end verification

The pipeline has been patched extensively tonight. Before declaring stability, Agnes wants a fresh end-to-end test. Suggested:

1. **Walk 2-3 sections** (any P2R5 row in Paddock 2 is well-covered and safe to use) and submit at least one observation per mode via QR:
   - `quick` submission with 1 photo (tests basic flow + photo attach + species-ref promotion if tier-3)
   - `new_plant` submission with 1 photo (tests plant asset creation + photo)
   - `inventory` submission with ≥ 3 species and a section_note (tests multi-species handling + section_notes dedup + section log creation)
   - `comment` submission with section_note only (tests activity log creation)

2. **Run `/review-observations` in a fresh Claude session**, check:
   - Preflight reports `plantnet_key_present: true` and spot-checks media_files
   - No claimed `species_reference_photos_updated: 1` where the plant_type.image is actually stale (use the recovery script logic as an audit after import)
   - `photo_pipeline.upload_errors` is empty on every import
   - `total_actions` matches what's in the submissions (no silent drop)
   - `same_name_prior_log` markers surface only on legitimate collisions

3. **Post-import audit** — hit one of the logs directly via the farmOS API (or by loading the section's QR page and visually inspecting the section-log block) to verify:
   - Photos attached correctly, not cross-contaminated between species
   - Count updated in plant asset inventory
   - Observer identity preserved in InteractionStamp (Sarah / Kacper / observer name, not Claude_user)
   - Notes deduped (no 4× Cuban Jute repeats)

4. **Section reference photo audit** — for the species you observed, confirm the QR section page shows the photo YOU took on this walk, not a stock/stale image.

If all 4 pass, the pipeline is verified stable. If any fails, we have a concrete data point to diagnose further — much better than waiting weeks to discover it like happened with the 35 stale approvals.

## Auto-handled rules used this session

- Duplicates within same minute → reject one (prefer the one with notes)
- Self-corrections ("discard previous") → reject older, keep newer
- Superseded counts within same hour same observer → reject older
- Dead / missing observations → import as-is
- Condition notes (yellow, eaten, brown, etc.) → import as-is
- Cowpea harvest section_notes → import as activity log per A2 (I13 deferred)
- James's NURS.GR empty junk → sheet-edit rejection by Agnes

## What remains NOT auto-handled (requires Agnes for future runs)

- New plant_type creation (e.g. Cuban Jute, other invasives TBD)
- Species reclassification ("not X, it's Y")
- Ambiguous PlantNet overrides
- New bug class discovery → halt + save state
- Stale approvals older than N days (once Fix 7 lands, this surfaces automatically)

## QR page enhancement backlog (2026-04-22)

**Section-level "Field observations" block takes too much real estate.**
The current render shows up to 5 recent section logs (line 700 in generate_site.py)
with full text + up to 6 thumbnails per log. Busy sections end up scrolling
past plants which is the actual primary content. Agnes's proposal:

- **Short-term:** cap visible section logs to 2-3 (most recent), add a "+N more"
  link that expands inline or opens a dialog.
- **Better long-term:** link to a dedicated section-log listing page (e.g.
  `{section_id}-observations.html`) with pagination + filter-by-observer/mode.
  Mirrors the log-detail page pattern: one-click from section view, full context
  on dedicated page.

Ties into the broader UX story: QR pages are mobile-first and visitor-facing.
Section logs are high-signal for farmhands+managers but low-signal for
visitors (Hipcamp guests etc). A collapsible/linked treatment serves both
audiences without mode-switching.

File this when UI/UX work restarts post-v4 migration.
