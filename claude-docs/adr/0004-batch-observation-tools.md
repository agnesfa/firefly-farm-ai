# 0004 — Batch observation tools and Python-server photo pipeline parity

- **Status:** accepted
- **Date:** 2026-04-15
- **Authors:** Agnes, Claude
- **Related:** ADR 0001 (photo pipeline redesign), April 14 Leah walk

## Context

Two observations came out of the April 14–15 work on Leah's walk
import:

1. **Tool-call explosion on multi-submission flows.** A sub-agent
   running on Claude asked me to import 15 submissions through
   `import_observations`. It took ~45 tool calls end-to-end:
   one `list_observations`, 15 `update_observation_status` calls to
   flip each from `pending` → `approved`, 15 `import_observations`
   calls, plus two corrective `update_inventory` calls and several
   incidental lookups. The underlying Apps Script `update_status`
   endpoint already accepts a list — the bottleneck was tool surface,
   not backend capability.

2. **Python-server photo pipeline drift.** ADR 0001 redesigned the
   TypeScript photo pipeline around "always attach, verify to
   promote", with rich diagnostics in `photo_pipeline`. The Python
   server (Agnes's STDIO fallback) was explicitly left on the old
   verify-gate design, flagged as an open question at the bottom of
   ADR 0001. That's a latent bug: the next time Python runs in
   production it reintroduces the same class of silent photo loss
   the TypeScript server just escaped.

Both items are mechanical once the design is settled, and both block
operator trust in the observation pipeline — which is the prerequisite
for everything else in the farm intelligence system. The principles
work Agnes flagged for a follow-up session is stuck behind a stack of
"fix the wobbly foundation" items, and these are two of them.

## Decision

### 1. Batch tools — `update_observation_status_batch` + `import_observations_batch`

Add two new MCP tools on both servers (Python and TypeScript), sitting
alongside the existing single-submission tools rather than replacing
them:

**`update_observation_status_batch`** takes `submission_ids: list[str]`,
`new_status`, `reviewer`, `notes`. Deduplicates the ids, builds one
entry per id, and calls `obs_client.update_status()` exactly once with
the full list. The Apps Script endpoint already supports this — it
was never a multi-call API, we just weren't using it.

**`import_observations_batch`** takes `submission_ids: list[str]`,
`reviewer`, `dry_run`, `continue_on_error`. Loops the existing
single-submission importer internally, collects per-submission results,
aggregates `photo_pipeline` metrics into a single roll-up, and returns
one response. The loop is **sequential** by design — parallel imports
would race on farmOS deduplication checks and the PlantNet rate limit,
and the Apps Script backend is single-threaded anyway.

Single-submission tools remain for the common case of "I'm doing one
thing right now." Batch tools are for "I need to process a whole
walker's observations."

### 2. Python-server photo pipeline parity

Port ADR 0001's redesign to `mcp-server/server.py`:

- Add `_new_photo_pipeline_report()` helper matching the TS
  `PhotoPipelineReport` interface.
- Refactor `_upload_media_to_log` to accept a `report` dict and record
  every failure mode (decode_failures, upload_errors with reasons)
  rather than swallowing silently.
- Rewrite `import_observations` to use the new `_attach_and_maybe_promote`
  helper: upload all photos unconditionally, then run PlantNet only to
  decide species-reference-photo promotion.
- Add `reset_call_count()` to `plantnet_verify.py` so per-import
  counters diff correctly instead of accumulating across STDIO sessions.
- Add an auth-degradation short-circuit: first `api_http_401/403`
  response marks verification degraded for the rest of the import and
  stops burning quota.
- Emit `photo_pipeline` in the response JSON matching the TS shape.

### 3. Keep the Apps Script call-out in KnowledgeBase.gs

No change to KnowledgeBase.gs — this ADR documents the observation tools
only. But it's worth noting that we considered a third batch tool
(`upload_file_batch`) and rejected it: the KB file upload action
(ADR 0002) is a low-volume admin operation, not a per-submission hot
path, and batching would complicate the per-file error reporting that
already works cleanly.

## Rationale

### Why a batch tool, not "make the single tool accept a list"

Backward compatibility. `update_observation_status` is called from
Claire's Claude, Olivier's Claude, James's desktop workflow, and
at least one Apps Script wrapper we don't fully own. Widening its
signature to accept list-or-string risks silent behavior changes in
one of those callers. A new tool leaves the old one untouched and
gives callers an explicit opt-in to batch semantics.

### Why sequential import, not parallel

Three reasons:

1. **farmOS deduplication races.** `logExists(logName, 'observation')`
   is a lookup-by-name check. Parallel imports for the same
   species/section/date would both miss the existing log and both
   attempt to create it.
2. **PlantNet rate limiting.** Free tier is 500 calls/day. Parallelism
   would burst the quota faster without any latency win on Agnes's
   STDIO server (which isn't network-bound on the Claude side).
3. **Apps Script is single-threaded.** Every observation import hits
   the same Apps Script endpoint which serializes internally anyway.
   Parallelism at the MCP layer doesn't buy anything except complexity.

Sequential-with-continue-on-error is the right default: it matches the
actual operational pattern ("do the walk, some observations might
fail, keep the good ones, don't lose the whole walk because one row
was malformed").

### Why port to Python

ADR 0001 left Python as an open question because the TS server is the
production path. But the Python server is Agnes's STDIO fallback and
will be used again — and the next session to use it will silently
regress through the same photo pipeline bug. The port is 200 lines of
mechanical refactoring against a test harness that already existed.
The alternative is a trap waiting to spring.

### Alternatives considered

- **One big batch tool that covers both approve + import** (flip
  pending→approved and import in one call). Rejected because the two
  operations have different safety profiles: `update_status` is
  reversible, `import_observations` creates farmOS records that have
  to be manually cleaned up. Separate tools force the caller to
  pause between them and decide whether the import is safe. Also, the
  "review" step in the workflow is genuinely separate — Claire
  reviews → approves → then Agnes imports. Merging them assumes a
  single-user flow we don't actually want.

- **Fat batch with media deduplication across submissions.** The
  current sequential loop re-fetches media per submission. For a
  walker with photos attached submission-by-submission, that's one
  get_media call per submission. Smarter batching could dedupe by
  date+section. Rejected: premature optimisation — the Apps Script
  get_media endpoint is fast, and the logic to dedupe safely across
  potentially-different date/section tuples is more code than savings.
  Worth revisiting if we hit per-import latency problems.

- **Skip the Python port.** Leave Python on the old design until
  someone complains. Rejected: exactly the "foundation drift" pattern
  the principles work is meant to eliminate.

## Consequences

### Positive

- **~90% reduction in tool calls for multi-submission flows.**
  Leah's 45-call sequence collapses to roughly 4 calls:
  list → status_batch → import_batch → optional cleanup.
- **Parity between Python and TS servers** eliminates the hidden
  regression path. Either server can run imports without reintroducing
  the Leah bug.
- **Aggregated photo_pipeline report** makes it obvious when a batch
  of imports had trouble somewhere — operator doesn't have to
  correlate N separate per-submission responses to find the one
  that silently lost photos.
- **New TS test pins the Leah regression in Python too.**
  `test_verification_degradation_does_not_block_photo_upload` in
  `tests/test_import_workflow.py` is the Python mirror of the TS
  regression test. Both servers now have a failing test if the
  photo pipeline silently drops photos when PlantNet is off.

### Negative

- **Tool count up from 35 to 37 on both servers.** More tool surface
  to maintain, to describe in prompts, to pick from when invoking.
  Marginal cost — batch tools have clearly-different descriptions
  from their single-submission counterparts, and we're still under
  the ~40-tool limit that makes tool-picker performance start to
  degrade.
- **Sequential import batch is slower than parallel would be.**
  Accepted. See rationale above.

### Neutral

- The Python and TS implementations intentionally match signature and
  behaviour as closely as the language constructs allow. Any future
  change to one must be mirrored in the other. This is a small
  toil tax but the alternative (each server drifts) is worse.

## Implementation

TypeScript files:

- `mcp-server-ts/plugins/farm-plugin/src/tools/update-observation-status-batch.ts` (new)
- `mcp-server-ts/plugins/farm-plugin/src/tools/import-observations-batch.ts` (new)
- `mcp-server-ts/plugins/farm-plugin/src/tools/index.ts` (register both)
- `mcp-server-ts/plugins/farm-plugin/src/__tests__/batch-observations.test.ts` (new — 8 tests)

Python files:

- `mcp-server/server.py`:
  - `import_observations` rewritten around `_attach_and_maybe_promote`
    helper and `_new_photo_pipeline_report()` — mirrors the TS redesign.
  - Adds `update_observation_status_batch` and `import_observations_batch`
    as new `@mcp.tool` functions.
- `mcp-server/plantnet_verify.py`:
  - Adds `reset_call_count()`.
- `mcp-server/tests/test_import_workflow.py`:
  - Updates `_setup_media` to populate botanical lookup + PLANTNET_API_KEY
    (matches the TS test fixture setup).
  - Adds `test_verification_degradation_does_not_block_photo_upload`
    as Python mirror of the TS Leah regression test.
- `mcp-server/tests/test_batch_observations.py` (new — 10 tests).
- `mcp-server/tests/test_knowledge_client.py`:
  - Fixes `test_connect_missing_env` that had a pre-existing environment
    pollution from adding `KNOWLEDGE_ENDPOINT` to `.env` earlier in the
    session (stubs out `load_dotenv` like `test_observe_client.py`).

Also polished `scripts/upload_kb_audit_files.py` to populate
`related_plants` with the 🔴 species list from each audit file. Follow-up
from the verification agent's nits on the April 15 KB upload.

Tests: 277 Python + 215 TypeScript = **492 tests passing** across both
servers. No regressions.

Commit SHA at time of writing: _filled in when committed_

## Open questions

- **Still unresolved from ADR 0001:** the Media-as-first-class-entity
  ontology extension. This ADR does not address it either — it just
  makes the existing blob model reliable on both servers. A dedicated
  ADR should propose the ontology extension when we pick it up.

- **Related plants population on existing KB entries.** The 5 audit
  entries already in the KB (from the earlier upload this session)
  have `related_plants` empty. The uploader polish only affects new
  uploads. We either (a) re-upload with overwrite to refresh them,
  or (b) add a one-off update-only mode. Deferred.

- **Batch tools in the CSR/COIP plugin.** The FA-Mall CSR plugin
  that Lesley's team released today has similar single-entity tools
  (`execute_order_action`, `set_escalation`, etc.). If the
  "batch observe tools" pattern works here, it might be worth
  proposing a batch version in that plugin too. Not in scope for
  this ADR — noted for the governance session.
