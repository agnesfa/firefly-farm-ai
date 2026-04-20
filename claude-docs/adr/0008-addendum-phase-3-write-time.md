# 0008 Addendum — Phase 3 write-time enforcement (partial)

- **Status:** implementation in progress
- **Date:** 2026-04-20
- **Relates to:** ADR 0008 (Observation Record Invariant), ADR 0007
  (Import Pipeline Reliability Fix 4)

## Context

ADR 0008 §7 defined a four-phase implementation for the Observation
Record Invariant. Phase 2 (audit + cleanup) completed on 2026-04-20.
This addendum documents what Phase 3 looks like in shipped code, what
shipped today vs what is deferred, and what "done" looks like for the
deferred parts.

The driver for Phase 3 is prevention: the I4 duplicate photos and I5
section-level-photo-as-species-reference defects we cleaned up in
Phase 2 happened because the write path had no awareness of the
invariants. The cleanup has to keep happening until the write path
enforces the rules at commit time.

## What shipped today (Phase 3a + 3b)

### Phase 3a — dedup at photo upload (I4)

`uploadMediaToLog` (TS) and `_upload_media_to_log` (Python) now:

1. Before uploading, fetch the list of filesizes already attached to
   the target log (include=image) and build a `set[int]`.
2. Before each incoming upload, check `size ∈ existing ∪ added-this-call`.
   If hit, record an `already_attached` entry in the photo pipeline
   report and skip the upload.
3. After a successful upload, add its size to `sizes_added_this_call`
   so two identical incoming payloads collapse too.

Keyed on filesize as a cheap content-hash proxy. The silent-success-
retry pattern that produced 2026-04-18's 9 duplicate image refs is
impossible going forward for same-log attachments.

Defensive fallback: if the "fetch existing sizes" lookup fails or
returns non-dict-shaped data (as can happen with test mocks), the
function returns an empty set and dedup is skipped — the safe
fallback is a possible double-attach (caught by the validator audit),
never a dropped upload.

### Phase 3b — tier-aware species-reference promotion (I5)

`updateSpeciesReferencePhoto` (TS) and `_update_species_reference_photo`
(Python) now:

1. Classify each incoming file by filename tier
   (`fieldPhotoTier(filename)`):
   - tier 3: submission-id-prefixed OR submission-prefixed + `_plant_`
   - tier 2: section-prefixed + `_plant_`
   - tier 1: section-prefixed + `_section_` (multi-plant frame)
   - tier 0: stock / unrecognised
2. **Refuse to promote tier ≤ 1.** Section-level multi-plant frames
   never become species references — this is the exact bug that made
   Chilli Jalapeño, Comfrey, and Geranium all share the same photo
   before today's revert.
3. Inspect the plant_type's current image; skip promotion if the
   current reference is strictly higher tier than the incoming
   candidate.
4. On promote: upload + patch the `image` relationship to single-valued
   pointing at the new file (collapses the multi-valued drift that
   appeared in Phase 2 when the client simply appended).

Tests added:
- TS: 3 new tests in `photo-pipeline.test.ts` covering tier-3 promote,
  tier-1 refusal, tier-0 refusal. 222 total pass.
- Python: existing tests updated to use tier-3 filenames and distinct
  content fixtures. 278 total pass.

### Supporting plumbing

TS: `FarmOSClient` gained `getRaw(path)` and `patchRelationship(...)`
methods, both exposed as optional extensions of the `PhotoUploadClient`
interface so the photo pipeline falls back gracefully when they're
absent (e.g. in unit tests with a minimal mock).

## What is deferred (Phase 3c + 3d)

### Phase 3c — section vs plant log routing (I2 + I3)

Problem: inventory-mode submissions carrying a `section_notes` field
currently get fanned out — the importer creates one observation log
per species in the inventory, each carrying the same section_notes
text in its notes field. This is how "Confirming no gingers in this
section" ended up attached to the Pear (Williams) log.

Required fix:
1. On inventory submissions, detect the `section_notes` field.
2. Create ONE section-level observation log for the section_notes —
   `asset_ids=[]`, `location_ids=[section_uuid]`, notes = section_notes
   text.
3. For each species in the inventory, create a plant-attached
   observation log — `asset_ids=[plant_uuid]`,
   `location_ids=[section_uuid]`, notes contain ONLY the per-plant
   count / condition / plant_notes, **not** the section_notes text.

Plus generator changes (`generate_site.py`) to render section-level
observations in a dedicated block on the section QR page, since no
current template surfaces logs that aren't attached to a plant.

Why deferred: this is a data-model change, not a bug fix. It changes
the shape of what `import_observations` produces, which downstream
consumers (`farm_context`, `generate_site.py`, the observation
integrity gate) will need to handle. Worth its own focused pass.

### Phase 3d — post-write validator (ADR 0007 Fix 4 proper)

Problem: today the validator exists as a standalone audit
(`scripts/validate_observations.py`) that runs on demand. ADR 0008
§7 Phase 3 specifies it should run after every log-creating write in
the pipeline, with failures either corrected in-place or aborting
with a specific violation message.

Required fix:
1. Extract the invariant-check functions from
   `scripts/validate_observations.py` into a library
   (`mcp-server/observation_invariants.py`) usable by any caller.
2. Mirror to TS
   (`mcp-server-ts/plugins/farm-plugin/src/helpers/observation-invariants.ts`).
3. Integrate into `import_observations` / `create_plant` /
   `create_observation` / `create_activity` / `archive_plant`: after
   each write, re-read the entity and run the checker. On violation,
   either auto-correct (for deterministic fixes like "strip section
   notes" after a mistaken fanout) or flag the violation in the
   response with remediation text.

Why deferred: this is the integration work that only makes sense once
Phase 3c establishes the correct log shape. Doing it now would
encode the current (wrong) fanout pattern into the invariant gate.

## Implementation order

The recommended sequence for the next session:

1. Phase 3c — write a small ADR 0009 (or extend this addendum) with
   the section-log schema design. Update `import_observations` +
   `generate_site.py` in one atomic change. Ship with tests.
2. Phase 3d — extract validator to library, wire into write paths.
3. Enable a `--strict` flag on the audit tool that exits non-zero on
   any error-severity violation. Wire that into CI (when we have CI)
   as a pre-deploy gate.

Estimated scope: 3c = 1 session (half-day), 3d = 1 session.

## Success criteria

Phase 3 is "done" when:

- Running `scripts/validate_observations.py --scope P2` after any
  WWOOFer walk reports **zero errors** in I1–I6 for logs created by
  that walk.
- A deliberate attempt to import an I3-violating observation (or an I4
  duplicate photo, or an I5 tier-1 promote) is **rejected** with a
  specific error by the import pipeline.
- `generate_site.py` renders section-level observations visibly on
  the section page, so `farm_context` integrity gate and human review
  can both see them.
