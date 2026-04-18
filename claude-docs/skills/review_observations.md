---
skill_name: review_observations
version: 0.1-draft
author: Agnes + Claude (2026-04-18 session)
status: draft — pending FASF ratification (ADR 0006)
trigger: manager_reviews_pending_observations
last_reviewed: 2026-04-18
---

# Skill: review_observations

## Purpose

When a manager (Agnes, Claire, James) sits down to review pending field
observations submitted by WWOOFers or team members via QR code, every
Claude agent must present the same rich context for every submission so
that the manager can make a reliable decision in one pass — without
having to go fishing for information across multiple tools.

This skill exists because reviewing observations is where data quality
enters or leaves the farm's record. A superficial review (counts only,
no photos, no history, no provenance) is how Claire's trust in the data
eroded.

## Trigger

One of:

- Manager explicitly says "review pending observations" / "process
  Leah's walk" / "let's clean up the queue".
- `list_observations(status="pending")` returns non-zero.
- A batch of recent submissions lands within 24 h and no review has
  occurred.

## Preconditions

- MCP server reachable (`mcp__farmos__fc__*` available).
- `system_health()` returns no "observability degraded" state.
- Manager is identified (so assessments can be attributed correctly).

## Procedure

For every submission in the review batch, the agent must assemble and
present the following six blocks **before** asking the manager for a
verdict. Not one, not four. All six. In this order.

### Block 1 — Provenance

- Submission ID (short form)
- Observer (the field worker who submitted)
- Timestamp (absolute + relative: "3 h ago")
- Section ID
- Mode (`quick` / `inventory` / `new_plant` / `section_notes`)
- Submission source: QR page (which one), voice transcript, Apps Script,
  direct MCP
- Previous status history (pending → reviewed? rejected? re-submitted?)

*Why:* The reviewer has to know who said what, when, and via which
pathway. Silent re-submissions and corrections have bitten us before.

### Block 2 — Current farmOS state for the section

- Active plant assets in the section (species, count, planted date,
  last observation date)
- Last 3 logs for the section (observation / activity / transplanting)
- Any pending logs attached to the section (including "JAMES — review"
  tasks)

*Why:* You cannot judge a count change ("Lemon 2 → 1") without knowing
what the current count actually is and when it was last verified.

### Block 3 — Pattern check from prior logs

Look back at least 60 days of logs for this section and for this
species in other sections:

- Has this species had repeated count changes in this section? (Noise
  signal — might indicate boundary ambiguity, mis-ID history.)
- Has this observer submitted similar edits before, and were they
  approved / rejected? (Observer-reliability signal.)
- Are there integrity-gate flags on this section (audit KB entries,
  review tasks, silent-failure notes)?
- Is this submission consistent with recent team-memory activity (did
  James log a transplant or chop-and-drop in this section recently)?

*Why:* One observation in isolation is weak evidence. Observation +
pattern is strong.

### Block 4 — Photos attached + PlantNet verification

- List each attached photo (filename, size, thumbnail if possible).
- For each photo, run PlantNet verification (`verify_species_photo` or
  equivalent) against the claimed species:
  - Top-3 matches + scores
  - Same genus / family / clade flag if expected species is not top-1
  - Verdict: `confirmed` (top-1 exact) / `plausible` (genus or top-3) /
    `mismatch` (different species) / `unverifiable` (API failure, low
    score, multi-plant frame)
- **Show the photos to the reviewer, not just the verdict.** The
  reviewer has the final say. PlantNet assists; it does not decide.

*Why:* PlantNet has known weaknesses (can't distinguish Thai from Sweet
basil; struggles with young plants under 30 cm; fails on multi-plant
frames). The reviewer must see what PlantNet saw. See
`feedback_plantnet_verification_policy.md`.

### Block 5 — Agent's assessment (with reasoning)

For each observation row in the submission, the agent presents its own
judgement synthesised from blocks 1–4:

- **Recommended verdict:** approve / approve-with-note / reject / flag-for-field-recheck
- **Reasoning:** 1–3 sentences citing specific evidence from the blocks.
- **Confidence:** high / medium / low
- **If the observation is actually an activity** (chop-and-drop,
  seeding, mulching, transplanting) rather than a count observation,
  flag it and propose converting it to the correct log type. The QR
  form often surfaces everything as an "observation" but the semantic
  meaning differs.

*Why:* The manager benefits from a concrete recommendation to respond
to, not a blank canvas. The reasoning keeps the agent accountable for
its recommendation.

### Block 6 — Metric / semantic-layer impact preview

Before the manager approves, the agent must surface:

- **Which farmOS entities will be written or modified** (plant counts
  adjusted, new assets created, logs inserted).
- **Which KB entries reference this species or section and may need
  update** (e.g. if you zero out Carob in P2R2.28-38, the P2R2 audit KB
  entry and the species KB entry should be re-referenced).
- **Which metrics the change propagates into** per `farm_semantics.yaml`
  and `farm_ontology.yaml`:
  - Section health score (count-dependent)
  - Strata coverage (if species is the sole representative of its stratum)
  - Diversity index (if species disappears from section)
  - Pending-tasks total (if an integrity flag is cleared)
  - Growth stage indicators (if scale triggers affected)
- **Downstream generators to re-run** after the write: `regenerate_pages`,
  site rebuild, any dashboard refresh.

*Why:* Every observation is a propagation event through the five-layer
semantic stack. Surfacing the impact before the write keeps the manager
from making invisible changes to derived state.

## Postconditions

After the manager makes a decision, the agent must:

1. **Write the verdict** via `update_observation_status` (one per
   submission) or `update_observation_status_batch` (many).
2. **Import approved observations** via `import_observations_batch` and
   **verify the writes landed** (query_logs for the resulting logs, do
   not trust the return alone — see `record_fieldwork` skill).
3. **Archive any ghost plants** identified during review (plants the
   inventory explicitly zeroed out or the reviewer confirmed absent),
   with an archive reason citing the submission_id.
4. **Update or create KB entries** where the review surfaced durable
   findings (e.g. "this section boundary has shifted in Claire's field
   sheet vs farmOS"). Follow `ingest_knowledge` skill.
5. **Write session summary** via `write_session_summary` that:
   - Lists submissions processed (ID + verdict + reviewer)
   - Lists ghost plants archived (asset ID + reason)
   - Lists KB entries created/updated (entry_id + title)
   - Lists any writes that failed (explicit flags, never silent)
   - Lists downstream generators run (`regenerate_pages` result, etc.)
6. **Re-run the section's `farm_context`** after import to confirm
   integrity gate is clean.

## Failure mode

If any of the six presentation blocks cannot be assembled (tool
failure, data missing, photo fetch failed), the agent:

- Presents the submission with the block explicitly marked as
  `UNAVAILABLE — <reason>`.
- Does not hide the gap. The reviewer sees what the agent could not
  see.
- Proposes the smallest decision the reviewer can make on partial data
  (often: "reviewed" — defer until the missing block is available).

If a write step fails (approval, import, archive, KB create):

- Record the failure explicitly in the session summary with the error
  text.
- Never report success for a step that did not verify.

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
Audit KB entry be767896 (P2R3 reconciliation) flagged Ice Cream Bean
as "all lost" in this section — Agnes's note says "Planted by James
approximately 20 March 2026" — consistent with the Mar 22 transplant.
This submission appears to be an additional plant, or a re-registration.

── Block 4 — Photos + PlantNet ──
No photos attached to this submission.
PlantNet: not applicable (no photos).

── Block 5 — Agent assessment ──
Recommended: approve-with-note. This is likely the same plant James
transplanted Mar 22, being re-registered from the field now that
Agnes has located it. Reasoning: timing matches the transplant log;
field note cites James's planting; pattern check shows the species
was flagged as "lost" in the audit.
Confidence: medium (no photo to verify; relies on field note).
Is this an activity vs observation? This looks like an observation
(a count sighting), not a new planting action (planting already
logged Mar 22). No reclassification needed.

── Block 6 — Semantic-layer impact ──
farmOS writes: new plant asset "17 APR 2026 - Ice Cream Bean -
  P2R3.40-50" with count 1. Potential duplicate of existing asset
  from 2026-03-22 if the Mar 22 transplant created one at the same
  section. Needs dedup check before create.
KB updates: audit KB be767896 should have its Ice Cream Bean "all
  lost" flag re-visited (may now be "recovered, 1 confirmed").
Metrics affected: section health (+1 plant), Emergent strata count
  (+1), diversity index (no change — species already present).
Downstream: regenerate_pages after import.

Awaiting manager decision.
```

## Dependencies

- Tool: `mcp__farmos__fc__list_observations`, `query_logs`,
  `query_plants`, `search_knowledge`, `farm_context`,
  `verify_species_photo` (PlantNet), `update_observation_status[_batch]`,
  `import_observations_batch`, `archive_plant`, `add_knowledge`,
  `update_knowledge`, `write_session_summary`.
- Data: `knowledge/plant_types.csv`, `knowledge/farm_ontology.yaml`,
  `knowledge/farm_semantics.yaml`, audit KB entries for P2R1–P2R5.

## Known gaps (TODO before ratification)

- Photo display: agents need a way to show photos to the reviewer
  inline. Today only Claude Code's Read tool renders images; Claude
  Desktop needs a different approach (links to log detail page, or
  a KB entry of recent photos).
- Duplicate-detection in write path: the Ice Cream Bean example above
  hits the "did Mar 22 create an asset we might duplicate?" risk.
  Needs a standardised dedup check in `record_fieldwork`.
- Metric propagation logic is currently implicit in `farm_semantics.yaml`
  and computed ad-hoc by `farm_context`. For the skill to assert it in
  block 6, we need a `preview_metric_impact(changes)` tool or a
  deterministic computation the agent runs.
- Integration with audit KB entries: the skill references them but has
  no standardised way to mark an audit flag as "addressed" after a
  review pass.

## Lineage

- Triggered by Agnes's 2026-04-18 observation that the current review
  process was ad-hoc and inconsistent across agents.
- Sits alongside `session_open` and `ingest_knowledge` as the day-one
  FASF skill set (see ADR 0006).
- Reviewed at governance session (pending).
