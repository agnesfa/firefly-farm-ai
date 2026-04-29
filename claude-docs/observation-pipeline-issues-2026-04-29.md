# Observation pipeline — issues surfaced 2026-04-28/29

**Status:** post-mortem from a 39-submission backlog review session. Not blocking v4 cutover (scheduled 2026-04-30 ~08:00 by Mike). Material for the post-v4 architecture revision.

**Why this doc exists:** ADR 0007 (Apr 21) and ADR 0008 (Apr 21) hardened the pipeline against the silent-failure classes known at that time, and shipped the eleven invariants + write-time enforcement. This session surfaced **new** silent-failure modes that the existing harness does not catch, plus one fully unexplained data-loss event. Agnes's framing: *"This session shows again many unreliable paths in our observations + photos pipeline which is concerning as we have done multiple iterations of revisions and testing on it, yet seems to keep being elusive."*

The issues are catalogued here for the planned post-v4 architecture revision rather than fixed inline.

---

## Session context

- **Goal:** clear the 39-submission pending backlog accumulated since 2026-03-22.
- **Outcome:** 30 submissions imported successfully (188+ observation logs, 12 activity logs, 1 new plant asset, 3 invasive-species flag activity logs), 2 rejected as duplicates/superseded, 7 lost from the sheet during the session and recovered via direct API backfill, 1 manual sheet delete deferred to Agnes.
- **Net farmOS state:** all source observations are represented in farmOS one way or another. **No data lost from farmOS's perspective.** The losses were in the sheet/transit layer, recovered before commit.

---

## Issues catalogued

### Issue 1 — Truncated submission_id silent no-op (operator-reproducible)

**What:** Passing an 8-char prefix instead of the full UUID to `update_observation_status_batch` returns `status: "updated"` with `rows_updated: 0`. Same shape with `import_observations_batch` returns `succeeded: 5` with `total_actions: 0`. **No error, no warning** — looks like a successful no-op.

**Reproduction (verified twice in this session):**
1. `update_observation_status_batch(submission_ids=["a31a3dc8", ...], new_status="approved")` → `{"status": "updated", "rows_updated": 0}` with no indication that submission lookup failed.
2. `import_observations_batch(submission_ids=["a31a3dc8", ...], dry_run=true)` → `{"succeeded": 5, "total_actions": 0, "errors": null}`.

Strict equality (`===`) on submission_id in `Observations.gs:349` should fail to match — but the response doesn't surface "no rows matched" as a distinct outcome. Apps Script returns `success: true, updated: 0` and the MCP layer relays it.

**Why it bites:** identical response shape for "matched 0 rows because IDs are wrong" and "matched 0 rows because there's nothing to do." Operator can't tell the difference. I (Claude) made the mistake twice in one session because the tool's `description: "sub=..."` display field is 8 chars and I copied that into the call.

**Severity:** medium. The bug is in the SDK ergonomics + Apps Script error-shape, not in the data path. But it cascades: a silent zero-row return from `update_status` led to a separate import call that returned "no observations found", which I initially read as "already imported" — meaning the discrepancy between sheet state and farmOS state was nearly invisible.

**Fix shape (post-v4):**
- Apps Script: distinguish "0 rows because no match" (return error or warning) from "0 rows because already in target status" (return success). Add an `unmatched_ids: [...]` field to the response.
- MCP layer: validate UUID format before the round-trip; reject prefix-style IDs at the boundary. UUID v4 has a known shape (8-4-4-4-12 hex).
- Tool descriptions: stop emitting truncated IDs as the canonical-looking display; use `sub=…full uuid…` or omit prefix display entirely.

**Already saved:** `feedback_use_full_uuids.md` covers the operator-side discipline.

---

### Issue 2 — Sheet rows physically deleted with no traceable cause (UNEXPLAINED, root cause unknown)

**What:** 7 valid `pending` submissions submitted on 2026-04-28 vanished from the Observations sheet during this session. They were verifiable in the sheet at session start (initial `list_observations` returned them) and confirmed in Agnes's exported version-history snapshot (Sheet2 of `Observations sheet versions history 28-29 Apr 2026.xlsx`). By the post-session snapshot, they are absent from every status (`pending` / `reviewed` / `approved` / `imported` / `rejected`).

**The 7:**

| Sub | Section | Observer | Mode | Species | Count | Submitted |
|---|---|---|---|---|---|---|
| 943654a9 | NURS.BCK | James | quick | Comfrey | 14 (sink) | 2026-04-28 05:12 UTC |
| 749adb5b | P1R1.29-39 | James | new_plant | Comfrey | 1 | 2026-04-28 05:08 |
| 3987845e | P1R1.19-29 | James | new_plant | Comfrey | 3 | 2026-04-28 05:07 |
| 832357d9 | P1R1.9-19 | James | new_plant | Comfrey | 3 | 2026-04-28 05:06 |
| 313a5468 | P1R1.5-9 | James | new_plant | Comfrey | 3 | 2026-04-28 05:05 |
| 8fe36a5b | P1R3.13-23 | Kacper | new_plant | Capsicum | 1 | 2026-04-28 05:02 |
| 77b0f56f | P1R3.13-23 | Kacper | quick | Corn (Manning Pride) | 52 + photo | 2026-04-28 05:02 |

**Pattern:** 100% correlation with submission timestamp. **All Apr 28 submissions vanished. All Apr 24 + Apr 27 submissions survived.** No correlation with mode, observer, section, or operator action.

**What we ruled out via code review:**
- `Observations.gs` has exactly one row-deletion path: `handleDeleteImported` (line 607), gated on `submission_id ===` exact match AND `status === "imported"`. I never called import on these IDs.
- `handleUpdateStatus` (line 307) only writes to status/reviewer/notes columns — no deletion.
- No time-based, edit-based, or change-based triggers (`grep -E "Trigger|onEdit|onChange|installable" Observations.gs` → 0 hits).
- The MCP server's "no observations found" early-return path (`import-observations.ts:178-189`) is read-only.
- `import_observations_batch` with `dry_run=true` correctly guards status updates + delete via `if (!params.dry_run && ...)` at `import-observations.ts:715`.

**Hypotheses (none confirmed):**

1. **Bug we haven't found** — most likely. Some path I haven't traced calls `deleteRow` outside the strict `===` + `status="imported"` gate. Or `handleListObservations` returns rows from a state I don't see. Or a race condition in concurrent calls.
2. **Truncated-ID `update_observation_status_batch` calls (Issue 1) caused the deletion via partial-prefix matching server-side.** Code review didn't surface this — `===` on UUIDs would not partial-match. But the temporal correlation is strong: my truncated calls happened mid-session; the rows disappeared mid-session.
3. **A separate session/actor deleted the rows during this session's runtime.** Plausible only if the in-progress chat thread spans multiple Claude sessions and one of the earlier sessions ran imports we don't have memory of.

**To definitively answer:** Google Sheets revision history (UI, not export) shows actor + timestamp of every cell + row mutation. Agnes's export is a snapshot diff, not an action log. Reading the sheet's actual revision UI is the smoking-gun investigation step.

**Severity:** high. **This is silent data loss in the transit layer.** Source data was preserved in our cached JSON file (`/tmp/obs-audit/batch-b-and-d-source.json`) so we backfilled cleanly, but if it had happened on a session with no preserved snapshot, the data would be gone with no audit trail.

**Recovery action this session:** all 7 backfilled into farmOS via direct `create_plant`/`create_observation` calls. Each backfill log is tagged `Backfilled from missing sheet sub <id>` for traceability. **One photo lost** — the Corn (Manning Pride) self-germination photo on submission 77b0f56f.

**Already saved:** `project_observation_deletion_incident_2026-04-29.md` has the full timeline + reproduction steps for future investigation.

---

### Issue 3 — Silent species drop on multi-plant submission (no error, no flag)

**What:** Importing submission `f67d3b93-f020-4f8a-8aca-9b21680e12ce` (P1R3.0-3 inventory, 15 source plants) created **only 13 observation logs**. Two species — `Corn (Manning Pride)` (emergent) and `Basil - Perennial (Thai)` (medium) — were silently skipped. Response had `errors: null` and `total_actions: 14` (13 observations + 1 activity log). No indication 2 plants were dropped.

**Pattern observation:** the 2 dropped species were the first plant in their respective strata groups (alphabetically), but the same heuristic doesn't apply to other 15-plant submissions in the same batch. Most likely **transient API glitch with no error capture** in the per-plant loop.

**Why this is concerning:**
- Repeats the SDLC-with-AI lesson from Apr 22: tests don't catch this class of bug because the code path completes successfully — just one (or more) inner iteration silently fails to write.
- ADR 0007 Fix 7 (observability) was supposed to address this with stale-approval surfacing, but per-plant skip isn't currently visible in the import response.

**Detection method that worked:** post-import audit by counting source plants vs farmOS observation logs filtered by `submission_id`. This caught it. **But the audit was something I added on a hunch after one suspicious response, not a guard the system runs by default.**

**Severity:** high. Equivalent to silent data loss — the operator doesn't know they need to backfill.

**Fix shape (post-v4):**
- `import_observations` should track `expected_observation_count` (from source) and report `created_observation_count` after the loop. If they don't match, populate `errors[]` with the missing plant identifiers.
- Add an `audit` field to the response: `{expected_plants: 15, created_observations: 13, missing_species: ["Corn (Manning Pride)", "Basil - Perennial (Thai)"]}`.
- Make this a hard invariant — refuse to call `delete_imported` if the count doesn't match (preserve sheet rows so operator can retry).

**Recovery this session:** 2 missing logs backfilled via direct `create_observation` calls.

---

### Issue 4 — MCP timeout on long imports (60s ceiling, server-side completes)

**What:** `import_observations` and `import_observations_batch` for submissions with many plants regularly trip the 60s MCP timeout. The server-side work continues and completes (verified by querying farmOS for the resulting logs), but the client-side response is lost. This forces the operator into post-hoc verification by querying farmOS.

**Observed in this session:**
- `import_observations_batch` with 5 P1R1 inventory submissions → timed out after ~55s; 3 of 5 had completed full cycle, 2 of 5 had observation logs created but no activity log + no sheet cleanup yet.
- `import_observations` on `80925e35` (18 plants) → timed out; activity log created, all 18 observation logs created, sheet rows cleaned. Response never came back.
- `import_observations` on `6b9b2914` (16 plants) → timed out; same story.

**Per the existing `import_observations_batch` documentation:** "The synchronous import path cannot reliably complete more than 5 submissions within the 60s MCP timeout (each submission takes 3-10s)." Reality is each per-plant write is ~2-3s (network + farmOS validation), so a 16-plant inventory + 1 activity log + 1 status flip + 1 delete_imported = ~40-55s, near the ceiling.

**Severity:** medium. Not data loss (work completes server-side), but **breaks the idempotent-retry assumption**: the operator doesn't know whether to retry or audit, and `import_observations` is intentionally idempotent so retry is safe in theory — except the post-flow `delete_imported` may have already cleaned the sheet rows, making the retry return "no observations found."

**Fix shape (post-v4):**
- Async job queue (ADR 0007 Fix 3) — already on the backlog. After v4: implement.
- In the meantime: split per-plant writes into background promises, return early with a `job_id` and let the operator poll.

---

### Issue 5 — Workflow hygiene: pending and rejected accumulate forever

**What:** The pipeline has zero auto-progression between states.
- `pending` rows stay `pending` indefinitely if nobody reviews them.
- `rejected` rows stay in the active sheet forever (no archival).
- Only `imported` rows get auto-deleted (via `handleDeleteImported`).

**Surfaced 2026-04-29 by Agnes:** *"what about all the pending observations, all the inventory observations are still pending, there are a lot of them. Even if not imported they should be changing status at the very least and potentially be deleted too?"*

**Reality at session start:** 41 pending observations across 6 submissions — 5 were Batch D + B5 (this session's queue) and 1 was the empty Mar 22 NURS.GR row (manual cleanup deferred). So the absolute backlog is small *right now*, but the **structural concern is real**: nothing prevents pending from piling up if a review session is missed for weeks.

**Severity:** low-medium. Operationally fine if review cadence is weekly. Architecturally weak — the active sheet grows unbounded.

**Fix shape (post-v4):**
- Stale-pending policy: auto-flag (visually marked, or surfaced via a `get_workflow_health` tool) for rows older than 14 days. **Don't auto-reject** — that's silent data loss.
- Rejected-row archival: move to a separate "archive" sheet/tab after 90 days. Preserves audit; keeps active sheet small.

**Already saved:** `project_observation_workflow_hygiene.md`.

---

### Issue 6 — PlantNet "configured but never called" warning fires on inventory mode (false alarm)

**What:** Some imports return `warnings: ["WARNING: PlantNet is configured but was never called. Verification may be silently short-circuiting. lookup_source=farmos_plant_types"]` even when the submission's plants don't have new photos to verify (e.g., inventory mode with 0 attached media).

**Severity:** noise-only. Not breaking anything; just spammy when correctly skipping verification.

**Fix shape (post-v4):**
- Suppress the warning when `media_files_fetched === 0` (nothing to verify).
- Or: only fire the warning when there ARE photos AND verification was bypassed AND PlantNet is configured.

---

### Issue 7 — Drive media fetch transient errors (no retry visibility)

**What:** Submission `97a0f0cc` returned `errors: ["Media fetch returned not-ok: Drive error: Service error: Drive"]`. The submission itself had no photos, so the error was a Drive-side transient hiccup — harmless. But the response surfaces it as a hard error in the `errors` array, which would be alarming if the submission DID have photos and the photos didn't make it.

**Severity:** low. Not data loss in this case, but the error shape doesn't distinguish "transient Drive hiccup with no photos to lose" from "transient Drive hiccup that lost photos."

**Fix shape (post-v4):**
- On Drive transient: retry with exponential backoff before reporting error.
- Distinguish in response: `media_status: "no_media" | "fetched_ok" | "transient_error_no_loss" | "transient_error_with_loss"`.
- If photos were attempted and failed, mark the submission for retry rather than letting the import proceed with the loss.

---

## Cross-cutting pattern

The **silent failure** is the connecting theme:

- Issue 1 — silent zero-row no-op (no distinction between "ID not found" and "already done")
- Issue 2 — silent row deletion (no actor, no log, no detectable trigger from the code)
- Issue 3 — silent per-plant skip (no error, no warning)
- Issue 4 — silent timeout-with-server-completion (the operator can't tell whether to retry)
- Issue 5 — silent state accumulation (no automatic surfacing of stale rows)
- Issue 6 — false-positive warning (operator learns to ignore warnings)
- Issue 7 — undifferentiated transient error (operator can't tell if photos were lost)

The pipeline needs a **structured response contract** where every endpoint returns:
- A categorical status (success / partial / failed / timeout / dry_run)
- An audit object listing intended actions, completed actions, and skipped actions with reasons
- A boolean `requires_followup` flag for the operator
- `errors[]` distinguishing fatal vs informational

ADR 0008's invariants address output-side correctness. We now need an **invariant on the response contract itself** so the operator can trust "success" actually means "all requested writes happened."

---

## Recommendations for the post-v4 architecture revision

1. **Response-contract invariant** — every write tool returns the audit triple (intended / completed / skipped) and refuses to report success if completed != intended. Could be enforced via a shared `MutationResponse` Zod schema on the SDK side.

2. **Sheet-side audit tab** — add a hidden "deleted_log" sheet that captures every row-deletion event with timestamp + actor + previous-status + submission_id. Solves the silent-deletion mystery class permanently.

3. **Pre-flight UUID validation** — reject malformed UUIDs at the MCP boundary, not at the Apps Script lookup. Distinguish "not-found" from "match-zero-rows."

4. **Async job queue for imports** (already ADR 0007 Fix 3) — break the 60s timeout assumption.

5. **Per-plant write idempotency receipts** — every observation log carries an idempotency key (`submission_id` + `species` + `section_id`); refuse to create duplicates AND refuse to claim success without the receipt.

6. **Operator-facing audit tool** — `get_pipeline_health(window_days=N)` returning stale-pending counts, mismatched-import counts, deletion events, retry-recommended IDs. Couples with Issue 5.

7. **Test harness rebuild** (ties to `project_sdlc_with_ai_thinking.md`) — scenario tests that drive the real Apps Script + MCP path with deliberately malformed inputs (truncated IDs, empty plants, oversized batches) and assert the response contract holds.

---

## What this session ALSO surfaced

Three more invasive-species instances (Periwinkle in P2R5.66-77 + P2R3.0-2; Fierce Thornapple in P1R1.5-9). 4 species in 7 days now. The invasives-handling design (deferred per `project_invasive_species_handling.md`) is now urgent — operator pattern of "flag in section_note, hope someone field-verifies" is not scaling.

---

## Filed memories

- `feedback_use_full_uuids.md` — operator discipline (Issue 1 mitigation)
- `project_observation_deletion_incident_2026-04-29.md` — full forensics (Issue 2)
- `project_observation_workflow_hygiene.md` — stale-pending + archival (Issue 5)
- `project_invasive_species_handling.md` — updated with Apr 25/28 instances

## Related prior docs

- `claude-docs/observation-photo-pipeline-review-2026-04-20.md` — the prior pipeline review that surfaced the eleven invariants
- `claude-docs/adr/0007-import-reliability.md` — ADR addressing photo-pipeline silent failures
- `claude-docs/adr/0008-observation-record-invariant.md` — eleven invariants
- `project_sdlc_with_ai_thinking.md` — the "tests don't catch the bugs we hit" thread that this session reinforces
