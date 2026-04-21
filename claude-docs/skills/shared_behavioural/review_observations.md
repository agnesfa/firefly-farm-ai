---
name: review_observations
version: 0.2.0
status: draft
system: B
trigger: manager_reviews_pending_observations
last_reviewed: 2026-04-21
author: Agnes, Claude
supersedes: review_observations@0.1.0
related_adr: 0006, 0007, 0008
related_ontology_verbs: [observed, reviewed, approved, rejected, imported, archived]
---

# Skill: review_observations

## Purpose

When a manager (Agnes, Claire, James) reviews pending field observations submitted by WWOOFers or team members via QR code, every Claude agent must present the same rich context for every submission so the manager can make a reliable decision in one pass — without fishing for information across multiple tools.

This skill exists because reviewing observations is where data quality enters or leaves the farm's record. A superficial review (counts only, no photos, no history, no provenance) is how Claire's trust in the data eroded.

## Trigger

- Manager explicitly says "review pending observations" / "process Leah's walk" / "let's clean up the queue".
- `list_observations(status="pending")` returns non-zero AND current user is a manager.
- A batch of recent submissions lands within 24h and no review has occurred.

## Preconditions

- `open_session` has completed this session.
- MCP server reachable (`mcp__farmos__fc__*` available).
- `system_health()` returns no "observability degraded" state.
- Manager is identified (so the approval InteractionStamp attributes correctly).

## Procedure

For every submission in the review batch, the agent assembles and presents **all six blocks** *before* asking the manager for a verdict. Not one, not four. All six. In this order.

### Block 1 — Provenance

- Submission ID (short form)
- Observer (the field worker who submitted)
- Timestamp (absolute + relative: "3 h ago")
- Section ID
- Mode (`quick` / `inventory` / `new_plant` / `section_notes`)
- Submission source: QR page (which one), voice transcript, Apps Script, direct MCP
- Previous status history (pending → reviewed? rejected? re-submitted?)

*Why:* Reviewer must know who said what, when, and via which pathway. Silent re-submissions and corrections have bitten us before.

### Block 2 — Current farmOS state for the section

- Active plant assets (species, count, planted date, last observation date)
- Last 3 logs for the section (observation / activity / transplanting)
- Any pending logs attached to the section (including `"<USER> —"` review tasks)

*Why:* You cannot judge a count change ("Lemon 2 → 1") without knowing what the current count actually is and when it was last verified.

### Block 3 — Pattern check from prior logs

Look back at least 60 days of logs for this section and for this species in other sections:

- Has this species had repeated count changes in this section? (Noise signal — boundary ambiguity, mis-ID history.)
- Has this observer submitted similar edits before, and were they approved / rejected? (Observer-reliability signal.)
- Are there integrity-gate flags on this section (audit KB entries, review tasks, silent-failure notes)?
- Is this submission consistent with recent team-memory activity (did James log a transplant / chop-and-drop here recently)?

*Why:* One observation in isolation is weak evidence. Observation + pattern is strong.

### Block 4 — Photos attached + PlantNet verification

- List each attached photo (filename, size, thumbnail if possible).
- For each photo, run PlantNet verification against the claimed species:
  - Top-3 matches + scores
  - Same genus / family / clade flag if expected species is not top-1
  - Verdict: `confirmed` (top-1 exact) / `plausible` (genus or top-3) / `mismatch` (different species) / `unverifiable` (API failure, low score, multi-plant frame)
- **Show the photos to the reviewer, not just the verdict.** The reviewer has the final say. PlantNet assists; it does not decide.

*Why:* PlantNet has known weaknesses (can't distinguish Thai from Sweet basil; struggles with young plants under 30cm; fails on multi-plant frames). The reviewer must see what PlantNet saw. See [feedback_plantnet_verification_policy](../../../../../../.claude/projects/-Users-agnes-Repos-FireflyCorner/memory/feedback_plantnet_verification_policy.md).

### Block 5 — Agent's assessment (with reasoning)

For each observation row in the submission, the agent presents its own judgement synthesised from blocks 1–4:

- **Recommended verdict:** approve / approve-with-note / reject / flag-for-field-recheck
- **Reasoning:** 1–3 sentences citing specific evidence from the blocks.
- **Confidence:** high / medium / low
- **Log-type classification (per ADR 0008 I11).** If this observation is actually an activity (chop-and-drop, seeding, mulching, transplanting) rather than a count observation, the classifier will flag it and propose converting to the correct log type. The QR form surfaces everything as an "observation" but semantic meaning differs.

*Why:* The manager benefits from a concrete recommendation to respond to, not a blank canvas. The reasoning keeps the agent accountable.

### Block 6 — Metric / semantic-layer impact preview

Before the manager approves, the agent surfaces:

- **Which farmOS entities will be written or modified** (plant counts adjusted, new assets created, logs inserted).
- **Which KB entries reference this species or section and may need update.**
- **Which metrics the change propagates into** per [farm_semantics.yaml](../../../knowledge/farm_semantics.yaml):
  - Section health score (count-dependent)
  - Strata coverage (if species is the sole representative of its stratum)
  - Diversity index (if species disappears from section)
  - Pending-tasks total (if an integrity flag is cleared)
  - Growth stage indicators (if scale triggers affected)
- **Downstream generators to re-run** after the write: `regenerate_pages`, site rebuild, any dashboard refresh.

*Why:* Every observation is a propagation event through the five-layer semantic stack. Surfacing the impact before the write keeps the manager from making invisible changes to derived state.

## Postconditions

After the manager makes a decision, the agent:

1. **Writes the verdict** via `update_observation_status` (one) or `update_observation_status_batch` (many).
2. **Imports approved observations** via `import_observations_batch` — invokes [record_fieldwork](record_fieldwork.md) for each write, so post-write verification is guaranteed, not trusted.
3. **Archives any ghost plants** identified during review (plants the inventory explicitly zeroed or the reviewer confirmed absent), with an archive reason citing the `submission_id`.
4. **Updates or creates KB entries** where the review surfaced durable findings (e.g. "section boundary shifted in Claire's field sheet vs farmOS") — via [ingest_knowledge](#) skill.
5. **Captures skill feedback** if the manager commented on the review format during this run (e.g. "block 5 should also cross-check neighbour sections") — writes team memory entry with `topics=skill_feedback:review_observations`.
6. **The session wrap-up** is handled by [close_session](close_session.md), not by this skill — close_session is the one that writes the summary with `farmos_changes`, cites KB entry_ids, and triggers `regenerate_pages`. review_observations does not duplicate that work; it produces the review outcomes that close_session cites.
7. **Re-runs the section's `farm_context`** after import to confirm integrity gate is clean.

Summary line stated at the end of the skill's run:
> "review_observations complete in Xms: N submissions reviewed, A approved, R rejected, F flagged for field re-check, K KB entries updated, Y skill_feedback captured."

## Failure mode

If any of the six presentation blocks cannot be assembled (tool failure, data missing, photo fetch failed), the agent:

- Presents the submission with the block explicitly marked as `UNAVAILABLE — <reason>`.
- Does not hide the gap. The reviewer sees what the agent could not see.
- Proposes the smallest decision the reviewer can make on partial data (often: "reviewed" — defer until the missing block is available).

If a write step fails (approval, import, archive, KB create):

- Record the failure explicitly for close_session to cite in the summary `questions` field.
- Never report success for a step that did not verify (deferred to `record_fieldwork` for actual writes).

If PlantNet CORS or API is broken (see [reference_plantnet_cors](../../../../../../.claude/projects/-Users-agnes-Repos-FireflyCorner/memory/reference_plantnet_cors.md)):

- Block 4 marked `UNAVAILABLE — PlantNet API failure`.
- Manager decides based on photo alone. Review proceeds; does not block.

## Dependencies

- MCP read tools: `list_observations`, `query_logs`, `query_plants`, `search_knowledge`, `farm_context`
- MCP write tools (invoked via record_fieldwork): `update_observation_status`, `update_observation_status_batch`, `import_observations_batch`, `archive_plant`, `add_knowledge`, `update_knowledge`
- External: PlantNet verification API
- Data: [knowledge/plant_types.csv](../../../knowledge/plant_types.csv), [knowledge/farm_ontology.yaml](../../../knowledge/farm_ontology.yaml), [knowledge/farm_semantics.yaml](../../../knowledge/farm_semantics.yaml), audit KB entries for P2R1–P2R5
- Other skills this invokes: `record_fieldwork` (per write), `ingest_knowledge` (for durable findings), `classify_observation` (Block 5)
- Other skills that follow this: `close_session` (consumes this skill's outcomes)

## Example — one submission through the skill

```
Submission a1e29d45 (P2R3.40-50 — Ice Cream Bean NEW)

── Block 1 — Provenance ──
Observer: Agnes (manager) | 2026-04-17 04:44 UTC (22h ago)
Source: QR page P2R3.40-50-observe.html | Mode: new_plant
Previous status: pending → approved 2026-04-18 14:30 UTC (this session)

── Block 2 — Current farmOS state, P2R3.40-50 ──
Active plants: Macadamia ×1, Tagasaste ×5 (recent), Malabar Chestnut ×1 (new)
Last 3 logs: Observation 2026-04-17 (Tagasaste), Activity 2026-04-12
  (chop-and-drop by James), Transplanting 2026-03-22 (Ice Cream Bean x2)
Pending logs: none open on this section

── Block 3 — Pattern check ──
Ice Cream Bean previously transplanted here 2026-03-22 (log 198198d5).
Audit KB entry be767896 flagged Ice Cream Bean "all lost" — Agnes's
note says "Planted by James approximately 20 March 2026". Consistent
with the Mar 22 transplant. This submission appears to be an
additional plant, or a re-registration.

── Block 4 — Photos + PlantNet ──
No photos attached. PlantNet: not applicable.

── Block 5 — Agent assessment ──
Recommended: approve-with-note. Likely the same plant James transplanted
Mar 22, being re-registered now that Agnes has located it. Timing
matches transplant log; field note cites James's planting; pattern
check shows species was flagged "lost" in audit.
Confidence: medium (no photo; relies on field note).
Log type: observation (count sighting), not activity. Classifier agrees.

── Block 6 — Semantic-layer impact ──
farmOS writes: new plant asset "17 APR 2026 - Ice Cream Bean -
  P2R3.40-50" with count 1. Potential duplicate of Mar 22 transplant
  asset — record_fieldwork will flag this in verify step.
KB updates: audit KB be767896 Ice Cream Bean "all lost" flag should
  be updated to "recovered, 1 confirmed".
Metrics affected: section health (+1), Emergent strata count (+1).
Downstream: regenerate_pages (via close_session).

Awaiting manager decision.
```

## Known gaps

- **Photo display.** Agents need a way to show photos to the reviewer inline. Today only Claude Code's Read tool renders images; Claude Desktop needs a different approach (links to log detail page, or a KB entry of recent photos).
- **Duplicate-detection (ADR 0007 Fix 5).** The Ice Cream Bean example hits the "did Mar 22 create an asset we might duplicate?" risk. Needs standardised dedup check before import writes; currently deferred to `record_fieldwork`'s Step 5 verify (which catches duplicates after the fact, not before).
- **Metric propagation is ad-hoc.** Block 6 is computed each time by `farm_context`. For consistency, we need a `preview_metric_impact(changes)` tool or a deterministic computation the agent runs — currently deferred to a future skill.
- **Audit KB entries are referenced but not re-mark-able.** The skill reads audit flags but has no standardised way to mark them "addressed" after a review pass. Pending structured Task entity in Phase 4.
- **Batch review UX.** Six blocks per submission × 20 submissions = information overload. Need a "triage mode" that surfaces only blocks 1, 5 for skim, with blocks 2/3/4/6 expandable on demand.

## Lineage

- Origin: Agnes's 2026-04-18 observation that the current review process was ad-hoc and inconsistent across agents.
- Sits alongside `open_session` and `ingest_knowledge` as the day-one FASF skill set.
- v0.1 drafted 2026-04-18 at `claude-docs/skills/review_observations.md` (old location); v0.2 migrated 2026-04-21 to `shared_behavioural/` with the new convention (server-side composite patterns, explicit skill-feedback + telemetry, integration with `close_session` + `record_fieldwork`).
- ADRs: [0006](../../adr/0006-agent-skill-framework.md) (FASF), [0007](../../adr/0007-import-pipeline-reliability.md) Fix 4/5 (verify + dedup depend on this skill's outputs), [0008](../../adr/0008-observation-record-invariant.md) (I1–I12 — every invariant is checked during the review).
- Related feedback: [feedback_plantnet_verification_policy](../../../../../../.claude/projects/-Users-agnes-Repos-FireflyCorner/memory/feedback_plantnet_verification_policy.md), [feedback_reference_photo_highest_quality](../../../../../../.claude/projects/-Users-agnes-Repos-FireflyCorner/memory/feedback_reference_photo_highest_quality.md).
- CC tactical counterpart: [.claude/skills/review-observations/SKILL.md](../../../.claude/skills/review-observations/SKILL.md) — dash-variant, System A, Agnes's CC workflow that invokes this behavioural skill.
