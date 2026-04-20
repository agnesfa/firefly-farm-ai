# 0005 — Submission-scoped media: scope photos by submission ID, not section folder

- **Status:** accepted
- **Date:** 2026-04-15
- **Authors:** Agnes, Claude
- **Supersedes:** the unrecorded "date+section folder" convention from the
  original Observations.gs Phase A implementation (March 7 2026)
- **Related:** ADR 0001 (photo pipeline redesign), ADR 0004 (batch tools)

## Context

Agnes reviewed Leah's April 14 field walk photos on the freshly
deployed log detail pages (commit `0a324c7`) and reported:

> "The same photos are attached to multiple plants and when I open
> the latest log there are lots of photos of many different plants in
> that section. Definitely not what was expected."

Investigation found a three-part bug chain in the observation media
pipeline:

### Bug 1 — Flat date+section Drive folder

`Observations.gs saveMediaToDrive` saves every submission's photos
into `{root}/{YYYY-MM-DD}/{section_id}/` — a flat folder shared by
all submissions that land on the same date and section. When Leah
made 8 separate single-plant observations in P2R5.0-8 on April 14,
all 8 submissions' photos ended up in one shared folder.

### Bug 2 — `handleGetMedia` returns the whole folder

When `import_observations(submission_id=X)` calls
`get_media(submission_id=X)`, the Apps Script:

1. Looks up X's date + section from the Sheet
2. Opens the Drive folder for that date + section
3. Returns **every file in the folder** (`sectionFolder.getFiles()`
   with no filtering)

So every import call for a submission in P2R5.0-8 got back the
combined pile of all 8 submissions' photos.

### Bug 3 — Filename collision

`observe.js collectMediaData` names files as
`{section}_plant_{counter}.jpg` with a counter that resets per
submission. Two submissions in the same section produce colliding
filenames. Even if the Apps Script tried to filter by filename,
it couldn't distinguish which photo belonged to which submission.

### Compounding factor — `resetForm` dataset leak

After a successful submission, `resetForm` cleared
`heroPreview.innerHTML` but did NOT clear `heroPreview.dataset.base64`.
If a worker submitted twice without taking a new hero photo, the old
photo leaked into the second submission via `collectMediaData`.

### Impact

11 Leah observation logs in P2R5 (8 in .0-8, 3 in .29-38) each
received the combined photo pile from their section folder — 12
photos each in .0-8, 6 each in .29-38. Total: 114 misattributed
file entities in farmOS. The photos were real field evidence but
attached to the wrong species. Log detail pages showed sunflower
photos on the basil card, pumpkin photos on the mulberry card, etc.
Detected by Agnes's visual review of the deployed log detail pages.

## Decision

**Make the submission the scope unit for media, not the section.**

Three-part fix:

1. **`observe.js` — submission-prefixed filenames.** `collectMediaData`
   now takes the `submissionId` and prefixes every filename with
   `{submission_id_first_8}_`. Example:
   `ae5a40f8_P2R5.0-8_plant_001.jpg`. This gives Observations.gs a
   reliable filter key without changing the Drive folder structure.

2. **`Observations.gs handleGetMedia` — prefix-filtered file listing.**
   After listing files in the section folder, only return files whose
   name matches `^{submission_id_first_8}_`. Old-format files (no UUID
   prefix) are returned unconditionally for backward compatibility
   with pre-fix submissions.

3. **`observe.js resetForm` — clear `heroPreview.dataset.base64`.**
   Previously only `innerHTML` was cleared; the base64 payload leaked
   into the next submission.

Additionally:

4. **Cleanup script `scripts/cleanup_leah_photos.py`** — walked
   Leah's 11 affected logs, detached all 114 image relationships via
   JSON:API PATCH (set `image.data: []`), then deleted all 114
   orphaned file entities via DELETE. Option B from the cleanup
   options discussed.

## Rationale

The fix is at the filename level rather than the folder structure
because:

- Changing the folder structure (e.g. `{date}/{section}/{submission}/`)
  would break the `get_media_by_path` backfill endpoint that uses
  `{date}/{section}` as its access pattern
- The existing Drive folder structure is visible to humans browsing
  the folder — adding per-submission subfolders would make the Drive
  folder impractical to navigate manually
- Filename prefixing achieves the same scoping without any structural
  change, and is backward compatible (old files without prefixes pass
  through the filter unchanged)

The `resetForm` fix is belt-and-braces — even if the base64 leaks
due to a future UI change, the filename prefix ensures it only
appears in its own submission's media set, not in every subsequent
one.

### Alternatives considered

- **Per-submission subfolders in Drive.** Cleaner from a filesystem
  perspective but breaks the backfill path and makes the Drive folder
  opaque to humans. Rejected.

- **Store submission_id as a Drive file property.** Google Drive
  supports custom properties on files. Querying by property requires
  Advanced Drive Service which is more complex than filename
  filtering. Rejected for now; revisit if filename-prefix has edge
  cases.

- **PlantNet-based photo routing.** Run each photo through PlantNet,
  match it to the observation of the identified species. Elegant in
  theory but fragile in practice (PlantNet can't identify every farm
  species, section overview shots don't match any species, and the
  PlantNet rate limit makes this expensive). Also doesn't fix the
  Drive-side contamination — only masks it at import time. Rejected.

- **Option A cleanup (detach only, keep files orphaned).** Simpler
  but leaves 114 orphaned files in farmOS. Agnes chose Option B
  (detach + delete) to keep farmOS clean.

## Consequences

### Positive

- **Photos are correctly scoped per-submission going forward.** Next
  walk Leah (or any worker) does will attach each photo to exactly
  the right log, regardless of how many observations they make in the
  same section on the same day.

- **No structural change to Drive.** Folder layout is unchanged.
  Humans browsing the Drive folder see the same `{date}/{section}/`
  layout as before. The only visible change is that new filenames
  start with `ae5a40f8_` instead of `P2R5.0-8_`.

- **Backward compatible.** Old-format files (no UUID prefix) pass
  through the filter unconditionally. Existing unimported submissions
  from before the fix still work.

- **Hero photo leak eliminated.** `resetForm` now deletes
  `heroPreview.dataset.base64` in addition to clearing innerHTML.

### Negative

- **114 deleted files in farmOS are unrecoverable.** The file entities
  are gone. The original photos still exist on Leah's phone and in
  the Drive folder (the Drive files were saved by `saveMediaToDrive`
  and not touched by the cleanup script — only the farmOS file
  entities were deleted). If we ever need them again, they can be
  re-imported from Drive using the backfill path.

- **Apps Script deploy required.** The `handleGetMedia` fix is in
  `scripts/google-apps-script/Observations.gs` and must be manually
  redeployed by Agnes. Until redeployed, the old unfiltered behavior
  remains active on the deployed endpoint. This is the same deploy
  friction pattern as ADR 0002 / KnowledgeBase.gs.

- **Leah's 11 logs are now photo-less.** The observation metadata
  (notes, counts, InteractionStamps) is intact, but the visual
  evidence from her walk is no longer attached to the logs. The
  photos still exist in Drive and can be re-imported when the
  pipeline fix is deployed and a re-import path is built.

### Neutral

- The `get_media_by_path` backfill endpoint is unchanged. It returns
  all files in a date+section folder regardless of prefix, which is
  the correct behavior for historical backfill (where submission IDs
  aren't available).

## Implementation

Files changed:

- `site/public/observe.js`:
  - `collectMediaData(submissionId)` now takes a submission_id arg
    and prefixes every filename with `{submission_id_first_8}_`.
  - `submitObservation` generates `subId` before calling `collectMediaData`.
  - `resetForm` now calls `delete heroPreview.dataset.base64`.

- `scripts/google-apps-script/Observations.gs`:
  - `handleGetMedia` filters files by `^{submission_id_first_8}_` prefix.
    Old-format files (no UUID prefix, detected by `/^[0-9a-f]{8}_/` regex)
    pass through for backward compatibility.
  - Returns `submission_prefix` in the response for diagnostic visibility.

- `scripts/cleanup_leah_photos.py` (new, one-off):
  - Walks P2R5 observation logs containing "initiator=Leah" or
    "Reporter: Leah" in notes
  - Detaches image relationships via PATCH (sets `image.data: []`)
  - Deletes each orphaned file entity via DELETE
  - Supports `--dry-run` for preview

Cleanup result: 11 logs processed, 114 files detached, 114 files
deleted. Zero errors.

Commit SHA at time of writing: _filled in when committed_

## Open questions

- **Re-import from Drive** — Leah's original photos still exist in
  the Drive folders (`2026-04-14/P2R5.0-8/`, `2026-04-14/P2R5.29-38/`).
  Once the Observations.gs fix is deployed, we could write a recovery
  script that uses PlantNet to identify each photo and attach it to
  the correct log. Low priority — Leah will do another walk, and the
  next one will work correctly from end to end.

- **Per-plant photo capture UI — CLOSED 2026-04-20.** The 2026-04-20
  pipeline review (`claude-docs/observation-photo-pipeline-review-2026-04-20.md`)
  established that per-plant photo capture is **out of scope by
  design**, not deferred. Rationale:
  - **Single-Plant modes** (`quick`, `new_plant`) submit exactly one
    observation per submission; all submission photos attach to that
    one log unambiguously. No per-plant tagging needed.
  - **Full-Section inventory mode** has no per-plant photo input by
    design; photos in that mode are section-level and the importer
    attaches them to a section-level observation log
    (`asset_ids=[]`, `location_ids=[section_uuid]`) per ADR 0008
    invariant I9.
  - Within-submission routing is therefore a function of the
    submission's mode, not of per-photo tagging. The filename scheme
    `{sub_id}_{section}_{target}_{counter}.jpg` is sufficient.
  - If a future UX ever adds per-plant photo input to inventory mode,
    the filename scheme would extend to include a species slug and
    I9 would revisit; until then this question is resolved.

- **Observations.gs deploy coordination** — we now have TWO pending
  Apps Script deploys in this session: KnowledgeBase.gs (ADR 0002,
  already deployed) and Observations.gs (this ADR). Agnes needs to
  update and redeploy Observations.gs before the next WWOOFer walk.
  Consider adding a "deploy checklist" entry to the team memory or
  session summary so it doesn't fall through the cracks.
