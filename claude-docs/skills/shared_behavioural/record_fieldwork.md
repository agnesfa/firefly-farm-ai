---
name: record_fieldwork
version: 0.1.0
status: draft
system: B
trigger: user_describes_completed_fieldwork
last_reviewed: 2026-04-21
author: Agnes, Claude
supersedes: none
related_adr: 0006, 0007, 0008
related_ontology_verbs: [planted, transplanted, seeded, harvested, chopped, mulched, watered, sprayed, inoculated, fertilised, composted, weeded, pruned]
---

# Skill: record_fieldwork

## Purpose

When a user describes completed field work — "I transplanted 5 lavender from NURS.SH1-2 to P2R4.22-29 yesterday" — the agent must write the corresponding farmOS entity and **verify the write landed before reporting success**. Without verification, silent API failures become missing data (see [James's 2026-03-24 lavender/geranium silent failure](../../cross-agent-consistency-2026-04-18.md) — claimed transplant, no farmOS log, caught weeks later by the `farm_context` integrity gate).

This skill is the write-path postcondition behind ADR 0007 Fix 4 and one of two complementary safeguards for ADR 0008 I12 (the other being the `parse_date` future-timestamp guard at write time). It's invoked by every System A tactical skill that creates farmOS records (`process-transcript`, `row-inventory`, future `seed-bank-withdrawal` etc.) and by every ad-hoc "log this for me" conversation.

## Trigger

- User describes completed field work in natural language.
- Another skill explicitly invokes `record_fieldwork` as part of its procedure (e.g. `process-transcript` after transcribing a field walk).
- User corrects or amends a previously-logged action ("actually that was 7 plants, not 5").

## Preconditions

- `open_session` has completed this session (or the user has explicitly acknowledged proceeding without it).
- MCP write tools available: `create_plant`, `create_observation`, `create_activity`, `update_inventory`, `archive_plant`, `create_seed` — at least one, depending on action.
- User identity known (for the InteractionStamp on the created log).

## Procedure

### Step 1 — Classify the action

Use the verb + context to determine the farmOS log type. Cross-reference [knowledge/farm_ontology.yaml](../../../knowledge/farm_ontology.yaml) verb mappings (the same classifier used by `classify_observation` / ADR 0008 I11):

- `seeded`, `sowed`, `germinated` → `log--seeding`
- `planted`, `transplanted`, `moved`, `relocated`, `replanted` → `log--transplanting`
- `harvested`, `picked`, `collected`, `yielded`, `gathered` → `log--harvest`
- `chopped`, `pruned`, `mulched`, `watered`, `sprayed`, `fertilised`, `composted`, `weeded`, `inoculated` → `log--activity`
- `observed`, `counted`, past-tense narrative of state → `log--observation`

On ambiguity: default to `log--observation, status=pending`, prepend `[FLAG classifier-ambiguous: <reason>]` to notes (per ADR 0008 I11 Q5).

### Step 2 — Validate inputs

- **Species exists in taxonomy.** `search_plant_types(species_name)` — if zero results, ask the user or offer `add_plant_type`. Do not proceed with an invented species.
- **Section / asset exists.** `get_section_uuid(section_id)` for location, `fetch_by_name("asset/plant", plant_name)` for asset attachment. If missing, surface the mismatch to the user.
- **Timestamp not in future** (ADR 0008 I12). If the user says "yesterday" or no date, resolve to today. If an explicit date resolves to > now + 24h, **refuse the write** and surface the year-typo possibility.
- **Count consistency.** If the action involves a count (transplant N plants), the count must be ≥ 1 and the nursery/source section must have ≥ N available, unless the user explicitly confirms the discrepancy.

### Step 3 — Build the InteractionStamp

```
[ontology:InteractionStamp]
initiator={user} | role={manager|farmhand|visitor}
channel=claude_session | executor=mcp_server
action={planted|transplanted|...} | target={plant|activity|...}
related_entities=[<species>, <section_id>, <source_section if applicable>]
ts={iso_timestamp}
```

Per ADR 0008 I6 (status + attribution), append to the log's notes only — never the asset's notes (I8).

### Step 4 — Write

Call the appropriate MCP write tool. Capture the returned ID(s) — **do not trust the tool's "success" return alone.**

### Step 5 — Post-write verify (THE critical step)

For each entity just created, issue a read-back:

| Created | Verify by | Expected |
|---|---|---|
| `log--transplanting` | `query_logs(id=..., include=asset,location,quantity)` | Exists; asset_ids match; location_ids match; quantity.inventory_adjustment ∈ {reset, increment, decrement}; quantity.inventory_asset set; quantity.units set |
| `log--observation` with inventory | same | Same + `asset.inventory` (after recompute) matches the count just written |
| `asset--plant` (via `create_plant`) | `query_plants(name=..., include=plant_type)` | Exists; plant_type matches; sanitised notes (I8); location attached |
| `log--activity` | `query_logs(id=...)` | Exists; notes contain InteractionStamp; category matches |
| `asset--seed` quantity update | `get_inventory(section_prefix=NURS.{sh})` | Updated count reflected |

**Verify budget: 3s per read-back.** If the verify times out or returns stale data, retry once (cache bust). On second failure, flag the write as **unverified** — do not report success.

### Step 6 — Record outcome

- **Verified success:** state the ID(s) and a one-line confirmation. Example: `Transplanted — log 7314a63f, asset afe29d10, P2R5.0-8 → Pigeon Pea count 7`. Do NOT say "successfully transplanted" without IDs.
- **Unverified (write returned OK but verify failed):** prepend `[UNVERIFIED]` to the output. Example: `[UNVERIFIED] create_plant returned id=abc123 but asset not found on verify read. Possible silent failure — check farmOS UI directly before the next session.` Record the anomaly in telemetry.
- **Write failed:** report the error text verbatim. Offer retry OR a fallback (e.g. "I can log this as a pending task for you to complete in the farmOS UI").

### Step 7 — Capture skill feedback (if any)

If during Steps 1–6 the user said "that's not quite how we do it" or "you should also check X" — the agent captures this for Agnes's skill-edit queue:
- Write a team memory entry with `topics` containing `skill_feedback:record_fieldwork`, summary describing what the user would change, reference to the specific step.
- Do NOT try to self-modify the skill. Feedback surfaces in Agnes's next `open_session`; Agnes decides.

### Step 8 — Telemetry

Record Level 2 telemetry per the [observability doc](../../observability-and-telemetry-2026-04-21.md):
`{skill: "record_fieldwork", version, user, duration_ms, steps_completed: 8, steps_failed: 0, status: "ok|degraded|failed"}`.

## Postconditions

Stated explicitly in the session summary:

- **Created entity ID(s):** listed, each paired with the verify read-back result.
- **Verify status:** `verified` OR `unverified (reason)` for each write.
- **Any refused writes:** listed with the reason (e.g. "I12 timestamp in future: 2026-12-18 resolved after now + 24h").
- **Any skill-feedback captured:** stated so the user knows their suggestion was logged.

Summary line the agent states:
> "record_fieldwork complete in Xms: N writes, N verified, K refused (reason), Y skill_feedback captured."

## Failure mode

- **Validation failure (species / section / future timestamp / count mismatch).** The skill refuses the write and surfaces the mismatch. Never write with invented or future-dated data.
- **Write tool returns error.** Report error. Offer retry. Do not silently treat as success.
- **Write returns OK but verify fails twice.** Mark as `[UNVERIFIED]`. Surface in session summary. Do NOT retry the write — that would create a duplicate. Agnes / user must resolve manually.
- **Read-back verify times out both attempts.** Same as above — do not assume success.
- **Classifier ambiguous (can't map verb to log type).** Per ADR 0008 I11 Q5: write as `observation, status=pending`, prepend FLAG marker, surface for human review.
- **Dependency on `open_session` missing.** If `open_session` wasn't run this session, warn once, then proceed. The write still has to verify; integrity-gate context is just degraded.

## Dependencies

- MCP write tools: `create_plant`, `create_observation`, `create_activity`, `update_inventory`, `archive_plant`, `create_seed`
- MCP read tools (for verify): `query_logs`, `query_plants`, `get_inventory`
- Ontology: [knowledge/farm_ontology.yaml](../../../knowledge/farm_ontology.yaml) verb mappings
- Other skills this invokes: `classify_observation` (Step 1), `ingest_knowledge` (if user also shares durable knowledge)
- Other skills that invoke this: `process-transcript`, `row-inventory`, `review_observations` (during import step), every future System A tactical skill that creates farmOS records

## Example

```
User: "I just transplanted 7 pigeon pea from NURS.SH1-3 to P2R5.0-8 this morning."

Step 1 — Classify: verb="transplanted" → log--transplanting.
Step 2 — Validate:
  ✓ Species "Pigeon Pea" found (farmos_name match)
  ✓ Source NURS.SH1-3 has 56 available (need 7, ok)
  ✓ Destination P2R5.0-8 exists
  ✓ Timestamp: "this morning" → 2026-04-21T09:00+11:00 — not in future
  ✓ Count 7 ≥ 1
Step 3 — Build InteractionStamp with initiator=Agnes, action=transplanted, related_entities=[Pigeon Pea, P2R5.0-8, NURS.SH1-3]
Step 4 — Write:
  - create_plant({name: "21 APR 2026 - Pigeon Pea - P2R5.0-8", plant_type: "Pigeon Pea", notes: sanitised}) → plant_id=afe29d10
  - create_observation_log({asset: afe29d10, location: P2R5.0-8, quantity: 7, inventory_adjustment: reset}) → log_id=7314a63f
  - update_inventory(NURS.SH1-3 Pigeon Pea, 56 → 49) → log_id=81b55383
Step 5 — Verify (parallel reads):
  ✓ query_plants(id=afe29d10) → exists, plant_type=Pigeon Pea, notes=1 line (I8 clean)
  ✓ query_logs(id=7314a63f) → exists, asset_ids=[afe29d10], quantity.inventory_asset=afe29d10, quantity.units=plant-unit-uuid
  ✓ get_inventory(NURS.SH1-3) → Pigeon Pea count = 49 ✓
Step 6 — Outcome: Verified. "Transplanted 7 Pigeon Pea to P2R5.0-8. Plant afe29d10, log 7314a63f, nursery 56→49."
Step 7 — No skill-feedback captured.
Step 8 — Telemetry recorded: 2400ms, 8/8 steps, status=ok.

record_fieldwork complete in 2400ms: 3 writes, 3 verified, 0 refused, 0 skill_feedback captured.
```

## Known gaps

- **Verify reads add latency.** Parallelise them server-side when possible; for now they're sequential client-side, which inflates `record_fieldwork` duration. Optimisation: batch them into a single `verify_writes(ids)` MCP tool.
- **`asset.inventory` recompute lag.** farmOS's computed field updates asynchronously after a qty reset. Verify step may race the recompute. Mitigation: `asset touch` (PATCH the asset with a no-op) forces recompute — add as Step 4.5 when verify would otherwise race.
- **Duplicate-detection not yet in write path (ADR 0007 Fix 5).** This skill will re-create a duplicate chop-and-drop if the user describes the same action twice. Until Fix 5 ships, the user must check themselves.
- **Skill-feedback trigger is heuristic.** "that's not quite right" is easy to catch; a subtler correction may be missed. Capture rules need tuning over time.

## Lineage

- Origin: [cross-agent-consistency-2026-04-18.md §6.4](../../cross-agent-consistency-2026-04-18.md) and James's 2026-03-24 silent lavender/geranium failure.
- ADRs: [0006](../../adr/0006-agent-skill-framework.md) (FASF framework), [0007](../../adr/0007-import-pipeline-reliability.md) Fix 4 (post-write verify at import layer), [0008](../../adr/0008-observation-record-invariant.md) I12 (future-timestamp guard — input-side complement).
- Feedback: [feedback_plantnet_verification_policy](../../../../../../.claude/projects/-Users-agnes-Repos-FireflyCorner/memory/feedback_plantnet_verification_policy.md), [reference_farmos_inventory_quirks](../../../../../../.claude/projects/-Users-agnes-Repos-FireflyCorner/memory/reference_farmos_inventory_quirks.md).
