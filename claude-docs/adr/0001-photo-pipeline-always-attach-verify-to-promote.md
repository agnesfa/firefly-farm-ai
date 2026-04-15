# 0001 — Photo pipeline: always attach, verify to promote

- **Status:** accepted
- **Date:** 2026-04-15
- **Authors:** Agnes, Claude
- **Supersedes:** the unrecorded "verify-gate" design from the
  April 10–12 photo pipeline hardening session
- **Related:** `claude-docs/photo-architecture-design.md` (April 12
  retrospective — the first time we documented the semantic gaps
  around Media-as-first-class)

## Context

On 2026-04-14 WWOOFer Leah walked Paddock 2 Row 5 taking photos via
the QR observe pages. Fifteen observations reached the sheet
successfully. When Agnes imported them through the Railway-hosted
TypeScript MCP server the next morning, the response reported
`photos_uploaded: 0`, `photos_verified: 0`, `plantnet_api_calls: 0` —
apparently a total pipeline failure.

A direct JSON:API inspection of the resulting farmOS logs (performed
2026-04-15, this session) found that **all 15 logs actually had 12
photos attached each** (file IDs 877–966). The photos had been
uploaded successfully; the metrics were lying, and the design had
silently degraded in a way nobody noticed.

Root cause analysis uncovered three compounding problems in the
existing `import-observations.ts`:

1. **Verification as a hard gate.** The `verifyMediaForSpecies`
   function filtered the media list: photos that PlantNet didn't
   approve were thrown away before upload. Any PlantNet outage,
   auth failure, or classification miss meant photo loss.

2. **Silent short-circuit when lookup is empty.** When the
   `plant_types.csv` path didn't resolve on Railway (caused by the
   April 9 build-context refactor leaving the resolve path ambiguous
   between tools/ and helpers/ compilation paths), `botanicalLookup`
   was empty, verification was skipped entirely, and the gate
   reversed to "let everything through" — which is why Leah's
   photos actually landed. But this hid the fact that verification
   was completely disabled in production.

3. **Broken reporting.** `action.photos_uploaded` was only set when
   a per-action counter was non-zero. Some combination of empty
   verified-media lists, null upload returns, and the outer
   `totalPhotos` reduce resulted in a flat zero even though 180+
   files were uploaded. Operators had no way to see what actually
   happened without querying farmOS directly.

A parallel architectural concern: PlantNet's domain-based CORS auth
means the key had to be authorized for the Railway domain
(`firefly-farm-ai-production.up.railway.app`) for server-side calls
to succeed. That authorization happened today alongside this ADR.

The Leah walk exposed that the photo pipeline was a single point of
failure with no diagnostics — exactly the class of bug we'd already
identified as unacceptable in `claude-docs/photo-architecture-design.md`
(April 12) but hadn't yet redesigned around.

## Decision

Split photo attachment from PlantNet verification. Every photo is
attached to its farmOS log unconditionally. PlantNet verification is
used exclusively to decide whether to **promote** the photo as the
plant_type reference photo — it never gates attachment.

Concretely:

1. **Always attach.** For every log the importer creates, every
   fetched photo is uploaded via `uploadMediaToLog` with no
   verification prerequisite.

2. **Verify to promote.** After a log is created and its photos
   are attached, the importer runs each photo through PlantNet
   (one photo at a time, stopping at the first verified match)
   purely to decide whether to replace the plant_type reference
   photo via `updateSpeciesReferencePhoto`.

3. **Loud diagnostics.** Every import returns a `photo_pipeline`
   block with: `media_files_fetched`, `decode_failures`,
   `photos_uploaded`, `upload_errors[]`,
   `species_reference_photos_updated`, and a `verification`
   sub-block with `plantnet_key_present`, `botanical_lookup_size`,
   `plantnet_api_calls`, `photos_verified`, `photos_rejected`,
   `degraded`, and `degraded_reason`. A `warnings` field flags
   any state the operator should investigate.

4. **Fail loud, fail once.** If the first PlantNet call in an
   import comes back with an auth error (HTTP 401/403),
   verification is marked `degraded` for the rest of that import,
   photos continue to attach normally, and the failure is reported
   in the top-level warnings. No infinite-retry loops, no silent
   quota burn.

5. **Resilient botanical lookup.** `buildBotanicalLookupResilient`
   prefers farmOS's cached `plant_type` taxonomy (no filesystem
   dependency, always reflects live truth) and falls back to
   `knowledge/plant_types.csv` searching multiple candidate paths
   so refactors of the build layout don't silently break it again.

## Rationale

The old design coupled two concerns — preserving evidence and
maintaining data quality — into a single step, with quality winning
when the two conflicted. The new design inverts the priority:
evidence always wins, quality is a best-effort enrichment.

This matches the principle stated in the April 12 photo architecture
design doc ("Media is a first-class entity, with its own provenance")
but never implemented. Photos are the raw field-truth; a PlantNet
model running on a third-party server is not.

### Alternatives considered

- **Fix the verify gate's silent failure modes in place.** Keep
  the existing filter architecture, make sure it never drops
  photos unintentionally. Rejected because it doesn't eliminate
  the class of bug — any future misconfiguration of the gate
  still risks data loss. The root problem was the coupling, not
  the particular bug.

- **Always attach, never verify.** Drop PlantNet entirely.
  Rejected because species-reference-photo promotion is genuinely
  valuable (it's how the QR landing pages get a visual identity
  for species) and verification catches real misidentifications.

- **Attach all photos, verify all, reject the promoted photo
  only.** A middle path — run verification on every photo,
  discard nothing, but use verification results to choose the
  single best photo for species-reference promotion. Rejected
  for cost reasons: verifying every photo burns PlantNet quota
  (500/day free tier) and adds latency per-log. The new design
  stops at the first verified photo per species per import,
  which is cheap and correct.

## Consequences

### Positive

- **Zero-path-for-photo-loss.** Attachment and verification are
  independent. PlantNet outages, auth failures, missing API keys,
  rate limits, and misclassifications no longer affect whether
  photos land on logs.

- **Observable pipeline.** Every failure mode now surfaces in the
  response with a reason string. Operators can debug photo issues
  from a single `import_observations` response without querying
  farmOS or reading server logs.

- **Quota efficiency.** Stopping verification after the first
  match per-species-per-submission reduces PlantNet calls from
  O(photos) to O(species × submissions). For Leah's walk this
  would be 11 calls instead of 180+.

- **Build-layout-resilient.** `buildBotanicalLookupResilient`
  tries farmOS first and has four fallback CSV paths. Moving
  files between `tools/` and `helpers/` no longer silently
  breaks verification.

### Negative

- **Unverified photos on logs.** If PlantNet is misconfigured or
  the CSV lookup fails, photos land on logs without species
  verification. This is by design (evidence > quality) but means
  the log history can temporarily include photos that don't match
  their claimed species. The `photo_pipeline.warnings` field
  makes this visible so we can clean up later; the alternative
  is losing the evidence entirely, which was the previous bug.

- **Two API paths to maintain.** Python (`mcp-server/server.py`)
  and TypeScript (`mcp-server-ts/plugins/farm-plugin/...`)
  implement the same logic. Only the TypeScript server is
  updated in this ADR — the Python server still runs the old
  verify-gate design and should be updated in a follow-up
  before it's used in production again. See "Open questions".

### Neutral

- **PlantNet key scope widened.** The key is now authorized for
  both `agnesfa.github.io` (observe-page in-browser calls) and
  `firefly-farm-ai-production.up.railway.app` (server-side
  import). This is a configuration change on my.plantnet.org
  recorded in `.env` under `PLANTNET_API_KEY`. Not a code
  change, but worth recording alongside the code change.

## Implementation

Files changed (TypeScript server):

- `mcp-server-ts/plugins/farm-plugin/src/helpers/photo-pipeline.ts` —
  introduces `PhotoPipelineReport`, extends `uploadMediaToLog` to
  record every outcome (success, decode failure, null return,
  thrown error) in the report instead of swallowing silently.

- `mcp-server-ts/plugins/farm-plugin/src/helpers/plantnet-verify.ts` —
  adds `resetPlantnetCallCount` so per-import counters diff
  correctly instead of accumulating across sessions on a
  long-running server.

- `mcp-server-ts/plugins/farm-plugin/src/tools/import-observations.ts` —
  rewrites the photo pipeline around the new `attachAndMaybePromote`
  function that uploads first and verifies to promote. Adds
  `buildBotanicalLookupResilient` with farmOS-first + four CSV
  fallback paths. Adds top-level warnings for
  "media fetched but zero uploaded" and "PlantNet silently
  short-circuiting". Drops the lying `totalPhotos` reducer in
  favour of `report.photos_uploaded` which is incremented per-upload.

- `mcp-server-ts/plugins/farm-plugin/src/__tests__/photo-pipeline.test.ts` —
  updated signatures; added tests for null-returning uploads and
  decode failures that prove they land in `report.upload_errors`.

- `mcp-server-ts/plugins/farm-plugin/src/__tests__/import-workflow.test.ts` —
  adds `MOCK_PLANT_TYPES` and `getAllPlantTypesCached` mock so the
  new farmOS-first lookup path is exercised. Sets
  `PLANTNET_API_KEY=test-plantnet-key` in the test environment.
  Adds a regression test called "verification degradation does
  NOT block photo upload (regression: Leah Apr 14 walk)" that
  sets `PLANTNET_API_KEY=''` and verifies 3 photos still upload.

Tests: 208 passing (one new test added for the Leah regression).

Commit SHA at time of writing: _filled in when committed_

Deferred:

- Port the new design to `mcp-server/server.py` + `mcp-server/plantnet_verify.py`
  (Python). The Python server still runs the old gate design.
- Add a dedicated `diagnose_photo_pipeline` MCP tool that runs the
  same diagnostics without creating any logs (for pre-flight checks).

## Open questions

- **Python server parity** (Agnes) — the Python server is Agnes's
  STDIO fallback. It should adopt the same design before we run
  any imports through it, or we'll reintroduce the same bug in a
  different codebase.

- **Media-as-first-class ontology** — `claude-docs/photo-architecture-design.md`
  identifies the lack of a `Media` entity type as a deeper issue
  (photos are blobs hanging off logs, with no provenance, no
  verification status, no relationship chain). This ADR does not
  fix that — it just makes the existing blob model work reliably.
  A future ADR should propose the ontology extension.

- **PlantNet API key rotation** — the key is currently a single
  secret shared between the browser (agnesfa.github.io), the
  Railway server, and any local dev environment. A compromise
  anywhere compromises everywhere. Consider per-environment keys
  in a future ADR.
