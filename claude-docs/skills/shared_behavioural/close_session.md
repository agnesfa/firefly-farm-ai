---
name: close_session
version: 0.1.0
status: draft
system: B
trigger: session_end
last_reviewed: 2026-04-21
author: Agnes, Claude
supersedes: none
related_adr: 0006
related_ontology_verbs: []
---

# Skill: close_session

## Purpose

`open_session` gives every session a consistent opening. `close_session` gives every session a consistent closing — a session summary that lists what was done, what failed (explicitly, never silently), what KB entries were created or touched, and any skill-feedback captured during the session. This is how work done today becomes reviewable context for tomorrow.

The motivating failure: James's 2026-03-24 transplant silently did not persist, but James's session summary claimed success. The gap between "what happened" and "what the summary says" was invisible until the `farm_context` integrity gate caught it weeks later. `close_session` closes that gap by forcing the summary to cite verified IDs, never hand-waved narrative.

## Trigger

- User explicitly ends the session ("thanks, done for now", "catch you later", "goodbye").
- User indicates a major context shift that should bookend the previous work (a fresh task that's clearly unrelated).
- Agent detects 30+ min of user inactivity after the last substantive exchange (heuristic; be conservative).
- Manual invocation: user says "wrap this up" or "write the session summary".

## Preconditions

- `open_session` ran earlier this session. If it didn't, warn the user that the summary will be partial (no team-delta context, no integrity state baseline).
- At least one substantive exchange occurred. Don't write a session summary for a three-message conversation that produced no writes or decisions.

## Procedure

### Step 1 — Collect session artefacts

Gather from this session's context:

- **Writes performed** — every `record_fieldwork` run, every `add_knowledge` / `update_knowledge`, every `archive_plant`, every `import_observations` call. Each with ID + verify status.
- **Skill invocations** — which skills ran, their telemetry status (ok / degraded / failed).
- **Decisions made** — any "we decided to X because Y" moments. These are the content of the `decisions` field.
- **Skill-feedback captured** — items written this session with `topics=skill_feedback:<name>`. Count + brief summaries.
- **Outstanding questions** — anything the user said "we'll revisit later" about. These become the `questions` field.
- **Unverified writes** — any `[UNVERIFIED]` results from `record_fieldwork`. These are the headline risk items.
- **Failures** — any tool error, any aborted skill run, any degraded state observed.

### Step 2 — Structure the summary

Use the `write_session_summary` schema:

```
{
  "user": "<current_user>",
  "topics": "<comma-separated, 5-15 topics>",
  "decisions": "<1-3 sentence narrative of what was decided>",
  "farmos_changes": [
    {"type": "transplant", "count": 7, "species": "Pigeon Pea", "section": "P2R5.0-8", "log_id": "7314a63f", "verify": "verified"},
    {"type": "observation", "count": 1, "species": "Coriander", "section": "P2R5.29-38", "log_id": "fc5f01ed", "verify": "verified"}
  ],
  "questions": "<anything unresolved, open, assigned to others, or flagged for next session>",
  "summary": "<1-2 paragraph narrative, human-readable>"
}
```

Rules:
- Every `farmos_changes` entry has a `verify` field: `verified | unverified | not_applicable`. Unverified entries MUST also appear in `questions` (they're outstanding risks).
- `decisions` is what was decided, not what was done. If the session was purely execution, this field can be empty — but usually the user or Claude made at least one judgement call worth naming.
- `questions` is the handoff to the next session. KB entry_ids created this session are cited here (`KB entry 1a4fce78 created for Passionfruit transplant protocol`).
- `summary` is the only narrative field. Keep it under 200 words. The reader is the next session's `open_session.team_activity_7d` feed — they want signal, not flavour.
- Append an InteractionStamp to `summary` per ADR 0008 I6.

### Step 3 — Cite skill-feedback

If the session captured any `skill_feedback:<name>` entries, list them in `questions` explicitly:

```
questions: "...; Skill feedback captured (2): review_observations — block 5 should include neighbour-section cross-check (Claire); record_fieldwork — nursery count validation should suggest alternatives not just refuse (Agnes)."
```

This surfaces them to Agnes's next `open_session.skills_feedback_queue`.

### Step 4 — Downstream generators

If the session modified farmOS data that flows to the QR site, trigger the regenerate:

- Any `create_plant` / `archive_plant` / `update_inventory` in this session → run `regenerate_pages`.
- On regenerate failure, record in `questions` as a TODO.

Skip this step if the session was read-only.

### Step 5 — Write the summary

Call `write_session_summary(payload)`. Capture the returned `summary_id`.

**Post-write verify** (same pattern as `record_fieldwork` Step 5): read back the just-written summary via `read_team_activity(days=1)` filter by `summary_id`. Confirm it exists with the expected structure. If verify fails, surface — a silent session-summary failure is exactly the failure mode this skill prevents elsewhere.

### Step 6 — Telemetry

Record Level 2 telemetry:
`{skill: "close_session", version, user, duration_ms, steps_completed, steps_failed, status}`.

Also flush any pending telemetry ring-buffer entries that haven't been flushed yet, so the session's per-call and per-skill records land in team memory.

### Step 7 — Acknowledge to user

One line back to the user: `Session summary written (id=N, verified). See you next time.` Or, if the user is in-conversation for an extended task, skip the acknowledgement — the summary is for them to read later, not an interruption now.

## Postconditions

Asserted explicitly — the summary itself is the postcondition record:

- **Summary written and verified.** `summary_id` cited, verify status confirmed.
- **All session writes cited.** Each farmOS change from this session appears in `farmos_changes`.
- **All unverified writes flagged.** Every `[UNVERIFIED]` from `record_fieldwork` appears in both `farmos_changes` (with `verify: unverified`) AND `questions` (as an outstanding risk).
- **Skill-feedback surfaced.** Every `skill_feedback:<name>` team memory entry created this session is referenced in `questions`.
- **Downstream generators triggered if applicable.** `regenerate_pages` status noted (success / failure / not applicable).
- **Telemetry flushed.** Session's telemetry ring-buffer is empty.

Summary line:
> "close_session complete in Xms: summary id=N verified, M writes cited, K unverified, Y skill_feedback surfaced, regenerate {ran|skipped|failed}."

## Failure mode

- **`write_session_summary` fails.** Retry once. On second failure, SAVE THE PAYLOAD LOCALLY (to `/tmp/session_summary_<ts>.json` or print it to stdout so the user can copy it). Do NOT silently lose the summary. The user should be able to hand-insert it into team memory later.
- **Verify fails after write.** Flag `[UNVERIFIED SUMMARY]` in the user-facing acknowledgement. This is a tier-1 alarm — we specifically wrote this skill to prevent unverified summaries.
- **`regenerate_pages` fails.** Record in `questions` of the summary. Do not block the close — the site can be regenerated manually next session.
- **`close_session` triggered without any writes this session.** Still write the summary — it captures context (topics discussed, decisions made) even when no farmOS state changed.
- **Session had a catastrophic error partway through** (MCP unreachable, user's internet dropped). Write a partial summary describing what WAS accomplished and explicitly naming the interruption point. Half a summary beats no summary.

## Dependencies

- MCP tool: `write_session_summary`
- MCP read tool (for verify): `read_team_activity`
- MCP tool: `regenerate_pages` (conditional)
- Ontology: none directly
- Other skills this invokes: none (it's a terminal skill)
- Other skills that feed into this: every skill that writes — `record_fieldwork`, `ingest_knowledge`, `review_observations`, plus all System A tactical skills

## Example

```
User: "Ok that's everything, catching up with James shortly."

[close_session triggers]

Step 1 — Collect:
  - 3 record_fieldwork runs (all verified): transplant Pigeon Pea x7, observation Coriander, archive Ginger
  - 1 ingest_knowledge: KB entry 8c3f2a19 created — "Winter seed-mix protocol from Claire Apr 21"
  - 0 skill_feedback captured
  - Decision: "Agreed to defer I12 backfill script to next session — 24 known logs already fixed manually"

Step 2 — Structure summary ...
Step 3 — No skill-feedback to cite.
Step 4 — Regenerate needed (plant created + archived): run regenerate_pages → ok, 149 pages rebuilt in 12s.
Step 5 — write_session_summary(payload) → summary_id=129 → verify: ✓
Step 6 — Telemetry flushed (42 per-call entries, 4 skill-invocation entries).
Step 7 — Ack: "Session summary 129 written and verified. Pages rebuilt. See you next time."

close_session complete in 3800ms: summary id=129 verified, 3 writes cited, 0 unverified, 0 skill_feedback surfaced, regenerate ran ok.
```

## Known gaps

- **Session boundaries are fuzzy in Claude Desktop.** Claude Code sessions end when the user closes the CLI; Desktop sessions blur with the conversation thread. Heuristics (inactivity timeout, explicit user goodbye, context shift) may miss or over-fire. Observe + tune.
- **Downstream generator trigger is all-or-nothing.** `regenerate_pages` rebuilds the full site. If only one section changed, a partial regenerate would be faster. Optimisation for Phase 2.
- **"Substantive exchange" threshold for whether to write a summary at all isn't defined.** A session that only answered "what's in P2R3?" shouldn't write a summary. A session that edited one plant should. Currently: if any `farmos_changes` OR any KB write OR any explicit `decisions` — write one. Refine as we see pattern.
- **Telemetry flush is best-effort.** If the session crashes before Step 6, some per-call records may be lost. Mitigation: flush is also triggered on any MCP server lifecycle event (request handler exit).

## Lineage

- Origin: [cross-agent-consistency-2026-04-18.md §3.2](../../cross-agent-consistency-2026-04-18.md) — silent write failures mask themselves in session summaries that claim success without verification. close_session closes that loop.
- ADRs: [0006](../../adr/0006-agent-skill-framework.md) (FASF framework), [0008](../../adr/0008-observation-record-invariant.md) I6 (InteractionStamp attribution on summary).
- Related: [open_session](open_session.md) (bookend partner), [record_fieldwork](record_fieldwork.md) (supplies the verified writes cited here).
