# 0007 — Import Pipeline Reliability

- **Status:** accepted — 2026-04-21
- **Date:** 2026-04-18 (proposed) / 2026-04-21 (ratified)
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

7. **Silent year-typo via batch-import — P2R4 empty-page bug (2026-04-21).**
   A batch import on 2026-03-07 wrote 24 inventory logs with
   `timestamp=2026-12-18` (year typo for `2025-12-18`). farmOS accepted
   the writes — the logs exist with positive counts, relationships
   intact — but the computed `asset.inventory` field silently drops
   future-dated `reset` adjustments from its recompute. Result: three
   section QR pages (P2R4.52-62, .62-72, .72-77) rendered "0 plants"
   for weeks while farmOS held the correct counts, invisible until
   Agnes noticed a missing section. No tool error, no validation
   failure, no integrity flag — pure silent data loss. This symptom
   was added to the ADR on 2026-04-21 after the reconciliation and
   drives the Fix 4 / ADR 0008 I12 cross-referencing below.

The cumulative effect is: Agnes cannot trust the import tool's reported
status. She must audit farmOS directly after every batch. That is not
sustainable with WWOOFers starting to submit 10–30 observations per day
(now observed live: 2 WWOOFers plus Claire remote submitting on
2026-04-21, 75+ pending observations in the queue).

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
the `record_fieldwork` skill's postcondition from ADR 0006 — spec at
[claude-docs/skills/shared_behavioural/record_fieldwork.md](../skills/shared_behavioural/record_fieldwork.md).

**Fix 4 is the output-side complement to ADR 0008 I12.** The P2R4
year-typo bug (Context #7 above) is blocked at input by the I12
`parse_date` guard (refuse any inventory-adjusting log with
`timestamp > now + 24h`); Fix 4 catches semantic drift of any other
kind — count mismatch, missing relationships, recompute lag — by
reading the created entity's `asset.inventory` and confirming it
matches the count just written. Neither invariant is sufficient alone:
I12 blocks the specific failure we observed, Fix 4 catches the general
failure class. Ship together.

**Fix 5 — Duplicate-write detection (two-tier).** A single dedup
key cannot serve two purposes: a strict key that includes
`submission_id` never over-merges but misses batch retries (the
March 7 failure class); a loose key that omits `submission_id`
catches retries but over-merges legitimate re-observations. So the
check is two-tier with different actions per tier.

Before any log write, compute:

- `content_hash = hash(section, species, date, mode, action_type, count)`
- `submission_id` from the InteractionStamp (`submission=<uuid>`)

Then:

1. **Tier 1 — hard skip (retry detection).** Look for an existing
   log with the **same `submission_id` AND same `content_hash`**. If
   found → return the existing log_id with verdict
   `"already_imported"`. Do not write. Safe to auto-skip because
   same submission + same content = definite retry.
2. **Tier 2 — soft warn (possible duplicate).** Look for an
   existing log with the **same `content_hash` but a DIFFERENT
   `submission_id`**. If found → surface to the caller as
   `{verdict: "possible_duplicate", match_log_id, match_submission_id,
   options: [proceed|skip|merge]}`. The caller (skill or human) decides.
   The decision is recorded in telemetry
   (`skill_feedback:duplicate_handling`) so we observe how often each
   path gets chosen and can tune the rule.
3. **No match → proceed normally.**

This handles:

- Batch retries where same submissions re-run (Tier 1 catches each)
- Legitimate re-observation by a different observer (Tier 2 warns,
  operator approves)
- Accidental duplicate from two sessions (Tier 2 warns, operator
  skips)
- A March-7-style rerun with fresh submission_ids (Tier 2 warns on
  each — 24 warnings signal the scale of the accident)
- The original duplicate chop-and-drop pattern (Tier 2 warns,
  operator merges)

Implementation note: the Tier 2 read extends the post-write verify
(Fix 4) — same read-back mechanism, just with an extra
`content_hash` lookup before the write. The user-decision step is
exposed via a new `confirm_duplicate_decision(match_id, action)` MCP
tool when called from an agent, or as a natural-language response
the calling skill interprets.

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

Status updated 2026-04-21.

**Phase 1 (ship now):**
- ✅ **Fix 2 — idempotency.** Shipped in both servers:
  [import-observations.ts:181-186](../../mcp-server-ts/plugins/farm-plugin/src/tools/import-observations.ts:181),
  [server.py:1924-1928](../../mcp-server/server.py:1924). Confirmed live.
- ⏳ **Fix 6 — `max_batch_size` cap.** Tagged Phase 1 "ship now" in
  v1 of this ADR; not yet shipped as of 2026-04-21 ratification walk.
  Trivially shippable (20-min patch: size check + clear error
  message). Either ship before ratification flips the ADR to accepted
  OR escalate to Phase 2 with explicit acknowledgement that the
  partial-success trap remains open until Fix 3 lands. Agnes to
  decide at ratification.

**Phase 2 (governance session):**
- **Fix 1 — Apps Script server-side filter rewrite.** Requires
  Observations.gs redeploy + regression test against a populated
  sheet. Increasingly load-bearing: 75+ pending observations in the
  queue as of 2026-04-21; sheet-scan performance drives the "team
  reports timeouts" symptom.
- **Fix 4 — post-write verify in the import path.** Implements the
  `record_fieldwork` skill postcondition from ADR 0006. Complements
  ADR 0008 I12 (input-side guard). Ship together.
- **Fix 5 — two-tier dedup.** Tier 1 (hard skip) via
  `submission_id + content_hash`; Tier 2 (soft warn) via
  `content_hash` alone, caller decides. Integrates with Fix 4 via
  the same pre-write read-back.
  - 🟡 **Fix 5 minimal shipped 2026-04-22** (commit 528a23b) after a
    mid-import incident exposed silent data loss: Kacper's
    `2334a179` Okra 13→15 was dropped because the earlier
    `23603752` inventory had written a log with the same name at
    count 13, and the naive `logExists(name)` check short-circuited
    without comparing submission_ids. The minimal version covers
    the narrow retry-vs-distinct disambiguation:
    - Fetch existing log, scan notes for `submission=<current_id>`
    - Same id → skip idempotently (retry)
    - Different id → proceed with creation; action result carries
      `same_name_prior_log` so the operator sees the collision
    - No content_hash yet; no Tier 2 operator-confirm flow yet
  - **Full Fix 5 still in backlog:** the `content_hash` check and
    operator-confirm flow ship together post-v4. The minimal
    shipped version is upward-compatible — full Fix 5 can extend
    the same notes-search path without changing the signature.

**Phase 3 (post-governance):**
- **Fix 3 — async job queue.** Storage tier resolved (KB entries
  with `category=import_job`, split header + per-submission to stay
  under Google Sheets per-cell limit). Remaining design work:
  worker lifecycle, polling contract, retention cleanup script.
  Implementation is a proper architecture decision deserving its own
  ADR (0009 or later).

## Queue pattern (Fix 3) — design notes

Resolved 2026-04-21 with input from the sheet-limits volume check.

- **Job submission:** `import_observations_batch(submission_ids, ...) →
  { job_id, status: "queued", estimated_completion_s }`
- **Polling:** `get_job_status(job_id) → { status: "queued|running|done|failed|partial_success|timed_out",
  progress: {processed, total}, results?: [...] }`
- **Storage: KB entries with `category=import_job`.** Chosen over the
  earlier v1 proposal of "farmOS activity log with
  category=import_job" because:
    1. KB is the "system state" tier in our model; farmOS is the
       "farm state" tier. Import jobs are system state. Co-mingling
       would pollute activity logs that should describe actual field
       work.
    2. KB already has sufficient headroom: current 20 entries, adding
       ~2000 import_job entries/year leaves us at ~0.2% of the
       Google-Sheets 10M-cell limit.
    3. Agent tooling already knows how to read KB — no new
       observability wiring.
- **Storage shape — avoid per-cell limit.** Google Sheets cells cap
  at 50K characters. A batch import of 30 submissions with long notes
  could exceed this if serialised into a single cell. Split each job
  into:
    - **Job header** (1 KB entry): `{job_id, submitted_at, user,
      submission_ids[], total, status, started_at, ended_at,
      error_summary}`. Small, <5KB per cell.
    - **Per-submission results** (N KB entries per job):
      `{job_id, submission_id, status, farmos_writes[], error_text}`.
      Linked back to the header via `job_id`. Each stays <5KB.
   
   A `get_job_status(job_id)` call assembles header + per-submission
   rows. Keeps us safely under the cell-character limit regardless
   of job size.
- **Workers:** single-worker model initially (jobs processed
  sequentially by the MCP server). Later: worker pool if we hit
  throughput limits.
- **Failure handling:** per-submission failures recorded in the job
  result (one per-submission KB entry per failure); the job header
  reports `partial_success` if some landed and others failed.
- **Timeout:** jobs have a max runtime of 30 minutes. Exceeded →
  header marked `timed_out` with partial per-submission results
  preserved.
- **Retention:** import_job entries older than 30 days are archived
  to a separate KB category or deleted by a cleanup script. These are
  ephemeral queue records, not audit trail — the actual import
  outcomes live on the farmOS logs they created.

## Links

- [ADR 0004](0004-batch-observation-tools.md): batch observation tools
  (the tools this ADR makes reliable)
- [ADR 0006](0006-agent-skill-framework.md): agent skill framework —
  the `record_fieldwork` skill lives within this reliability work
- [ADR 0008 amendment I12](0008-observation-record-invariant.md#i12--inventory-log-timestamps-must-not-be-in-the-future):
  input-side complement to Fix 4 (future-timestamp guard at `parse_date`)
- [record_fieldwork skill spec](../skills/shared_behavioural/record_fieldwork.md):
  implements the Fix 4 postcondition as a shared_behavioural skill
- [observability-and-telemetry-2026-04-21.md](../observability-and-telemetry-2026-04-21.md):
  telemetry plan that this ADR's Fix 5 decision-tracking depends on
- Session diagnostic:
  [cross-agent-consistency-2026-04-18.md](../cross-agent-consistency-2026-04-18.md)
- Root-cause evidence gathered in 2026-04-18 session (see session
  summary) and 2026-04-21 P2R4 empty-page reconciliation (see commit
  `9e61f62`)
