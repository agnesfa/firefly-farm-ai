# 0007 — Import Pipeline Reliability

- **Status:** proposed
- **Date:** 2026-04-18
- **Authors:** Agnes, Claude
- **Supersedes:** —
- **Related:** 0004 (batch observation tools), 0005 (submission-scoped media),
  0006 (agent skill framework)

## Context

The 2026-04-18 clean-slate pass exposed multiple stacked failure modes in
the observation import pipeline. Agnes approved 24 observations for
import ahead of a new WWOOFer cohort; the batch tool reported failure;
but audit against farmOS revealed that **all 24 had actually imported**
— just with data loss on the individual quick submissions and duplicate
activity logs. The MCP response was lying about what the backend
completed.

Specific symptoms observed:

1. **MCP 60 s timeout trips on any batch > ~6 submissions.** Each import
   takes 3–10 s (Apps Script fetch + farmOS writes + photo pipeline).
   Batch of 24 overflowed. Batch of 8 overflowed. Even batches of 5
   returned mid-flight errors despite partial success on the backend.

2. **Apps Script `listObservations` returns stale / inconsistent data.**
   Querying the same submission by `submission_id` right after a status
   update returns empty. Querying by `date` returns it. The handler
   loads the entire sheet via `getDataRange().getValues()` then filters
   client-side — subject to response-size truncation and consistency
   lag.

3. **Lost individual notes on quick submissions.** When an inventory
   submission and multiple single-species quick submissions target the
   same section on the same day, the inventory write creates
   per-species logs that *shadow* the quick submissions. The quick
   submissions then get their status flipped to `imported` and their
   rows deleted by `delete_imported` — but the individual notes
   ("Yellow leaves on Turmeric", "Leaves eaten on Thai White Guava")
   never made it into farmOS. The data is gone.

4. **Duplicate activity logs.** The same P2R3.50-62 chop-and-drop,
   seeding, and mulching activities exist twice in farmOS — written by
   session 82 and session 84 in James's memory. No duplicate-detection
   check in the write path.

5. **Retries compound the loss.** Because delete_imported runs after
   successful status transition, a retried import finds an empty result
   from `listObservations` ("No observations found") and reports
   failure, masking the fact that the first attempt landed.

6. **`approved → imported` is a one-way door.** No tool exists to revert
   a status (the backend rejects `pending` as a transition target). Once
   flipped to `approved`, the only path is forward, which compounds any
   mid-flight failures.

The cumulative effect is: Agnes cannot trust the import tool's reported
status. She must audit farmOS directly after every batch. That is not
sustainable with WWOOFers starting to submit 10–30 observations per day.

## Decision

Ship a prioritised stack of six fixes to the import pipeline, ordered by
impact:

**Fix 1 — Apps Script server-side filter.** Replace `sheet.getDataRange().getValues()`
in `Observations.gs handleListObservations` with a column-indexed scan
that matches submission_id or date without loading the whole sheet into
memory. Eliminates response-size truncation and stale read behaviour.

**Fix 2 — Import idempotency.** In `import-observations.ts` (and Python
mirror), treat `status = imported` as "already done — skip with
success verdict" instead of erroring. Treat `rejected` as "skip with
reject verdict". Only error on unknown or `pending` (needs approval).
Lets us retry any batch safely.

**Fix 3 — Async job queue for batch imports.** (Noted as a queue
pattern; full design below.) `import_observations_batch` kicks off a
backend job and returns a `job_id` immediately. MCP client polls
`get_job_status(job_id)` until complete. Removes the 60 s ceiling
entirely. Also enables progress reporting.

**Fix 4 — Post-write verification in the write path.** Every
`create_plant` / `create_observation` / `update_log_status` call in the
import flow must re-read the created / updated entity and confirm it
exists with expected fields before returning success. Replaces "tool
returned 200 → we're done" with "verified persisted". Implementation of
the `record_fieldwork` skill's postcondition from ADR 0006.

**Fix 5 — Duplicate-write detection.** Before creating a new
observation/activity log for a (section, species, date, mode) tuple,
check if one already exists. If yes, either skip with a "dup-detected"
verdict OR merge the new notes into the existing log. Eliminates the
duplicate chop-and-drop pattern.

**Fix 6 — Batch-size limit at the tool.** `import_observations_batch`
refuses batches larger than N (start with N=5) with a clear message
directing the caller to split or use async mode. Prevents the silent
partial-success trap entirely while Fix 3 is being built.

## Rationale

### Why this stack and not alternatives

- **Fix 1 attacks the root cause of stale reads.** Response truncation
  and sheet-scan inconsistency cannot be worked around at the client;
  they have to be fixed at the Apps Script tier. Once fixed, every
  downstream call (`import`, `update_status`, `get_media`) becomes
  deterministic.
- **Fixes 2 + 6 are small, safe, high-impact.** Can ship today without
  architectural work. Make the current state usable.
- **Fix 3 is the proper long-term answer.** Batch processing with a 60 s
  synchronous timeout is inherently fragile when each unit of work
  varies from 3 s to 10 s. A job queue pattern (decouples request from
  execution) is the right architectural shape.
- **Fixes 4 + 5 are behavioural postconditions, not transport fixes.**
  They sit in the write path itself and prevent the worst data-loss
  modes. Fix 4 is already specified by ADR 0006's `record_fieldwork`
  skill; this ADR formalises its enforcement at the import layer.

### Alternatives considered

- **Make the MCP timeout longer than 60 s.** Rejected: the timeout
  protects against truly stuck requests; raising it hides rather than
  solves the problem.
- **Keep sequential import, don't batch.** Rejected: 10 × one-call
  imports take 30+ s of MCP overhead each and don't scale to WWOOFer
  volume.
- **Write observations directly from the QR page to farmOS, bypass
  Sheet.** Rejected for now: the Sheet is the manager review queue;
  bypassing it removes Agnes's approval gate. Possible future change.

## Consequences

### Positive

- **Import reports match reality.** Success means the write landed;
  failure means it did not. Agnes stops audit-every-batch.
- **Retries are safe.** Idempotent imports + post-write verify means
  network blips don't cause data loss.
- **No duplicates.** Same activity logged twice in two sessions
  produces one farmOS record with both notes merged.
- **Batches scale.** Async queue removes the timeout ceiling.
- **Photos land with observations.** Photo pipeline already works (ADR
  0001); reliability fixes ensure the observations they attach to
  actually exist.

### Negative

- **Fix 1 + Fix 3 require Apps Script + backend work.** Not small.
  Requires deploy coordination per the memory rule. Realistic scope is
  to ship Fixes 2 + 6 now, Fix 4 + 5 next, Fix 1 + 3 during the
  governance session.
- **Job queue introduces state to track.** Job history needs a storage
  tier (initially in farmOS logs with type `activity` + category
  `import_job`; or dedicated tier if volume grows).
- **Duplicate detection may occasionally over-merge.** If two genuinely
  distinct observations land in the same (section, species, date),
  merge is wrong. Mitigate by including submission_id in the dedup key
  so two explicit submissions by the same observer are preserved.

### Neutral

- **Apps Script side filtering (Fix 1) may reveal other latent bugs**
  in the sheet layer. Worth surfacing.

## Implementation phases

**Phase 1 (ship now):**
- Fix 2: idempotency patch in `import-observations.ts` and
  `import_observations.py`.
- Fix 6: enforce `max_batch_size = 5` in `import_observations_batch`
  with a clear error message.
- Tests: unit tests for both fixes.

**Phase 2 (governance session):**
- Fix 1: Apps Script server-side filter rewrite (requires
  Observations.gs redeploy + regression test against a populated sheet).
- Fix 4: post-write verify in import path. Implements the
  `record_fieldwork` skill postcondition from ADR 0006.
- Fix 5: duplicate detection using (section, species, date, mode,
  submission_id) composite key.

**Phase 3 (post-governance):**
- Fix 3: async job queue. Design spike first — storage tier, polling
  contract, job history, progress surface. Implementation is a proper
  architecture decision deserving its own ADR.

## Queue pattern (Fix 3) — design notes

Noted for the architecture review:

- **Job submission:** `import_observations_batch(submission_ids, ...) →
  { job_id, status: "queued", estimated_completion_s }`
- **Polling:** `get_job_status(job_id) → { status: "queued|running|done|failed",
  progress: {processed, total}, results?: [...] }`
- **Storage:** start with a farmOS log type `activity` with category
  `import_job`, notes carry the JSON job record. Move to a dedicated
  storage tier if volume exceeds ~100 jobs/day.
- **Workers:** single-worker model initially (jobs processed
  sequentially by the MCP server). Later: worker pool if we hit
  throughput limits.
- **Failure handling:** per-submission failures recorded in the job
  result; the job as a whole reports `partial_success` if some landed
  and others failed.
- **Timeout:** jobs have a max runtime (e.g. 30 minutes). Exceeded →
  job marked `timed_out` with the partial results preserved.

## Links

- ADR 0004: batch observation tools (the tools this ADR makes reliable)
- ADR 0006: agent skill framework (the `record_fieldwork` skill lives
  within this reliability work)
- Session diagnostic: `claude-docs/cross-agent-consistency-2026-04-18.md`
- Root-cause evidence gathered in 2026-04-18 session (see session summary)
