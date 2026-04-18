# 0006 — Firefly Agent Skill Framework (FASF)

- **Status:** proposed
- **Date:** 2026-04-18
- **Authors:** Agnes, Claude
- **Supersedes:** —
- **Related:** 0001 (photo pipeline), 0003 (reconciliation audit), 0004
  (batch observation tools)

## Context

On 2026-04-18 we uncovered three systemic consistency failures between
the Claude instances working the farm (Agnes's, James's, Claire's — any
future Claude that joins). See companion doc
`claude-docs/cross-agent-consistency-2026-04-18.md` for the full evidence
and gap analysis.

In summary:

1. **17 pending farmOS logs** (9 review tasks, 8 transplant signals) are
   surfaced by Agnes's Claude but **invisible to James's Claude** — because
   ownership is encoded as a `"JAMES —"` prefix in unstructured log notes,
   and James's Claude has no protocol to scan for it. farmOS has no
   assignee / owner field.
2. **James's day-debrief claims sometimes silently fail** to persist. The
   24 Mar Lavender / Geranium transplant was missed entirely until a later
   `farm_context` integrity run caught it. There is no post-write
   verification in the write path.
3. **James's chop-and-drop KB entry does not exist.** Either his Claude
   never recognised the shared content as KB-worthy, or the write silently
   failed. There is no enforced rule that "durable knowledge shared by the
   user must land in the KB, with session memory citing the KB entry_id".

The common underlying cause: the only layers currently shared across
Claude instances are **team memory, MCP tools, and KB content**. There is
**no shared layer for how to behave** — every Claude invents its own
session protocol, write discipline, and knowledge persistence rules.

This is the failure mode the governance + architecture review session
needs to solve for.

## Decision

Introduce the **Firefly Agent Skill Framework (FASF)** as the shared
behavioural layer. Specifically:

1. **Agent skills are KB entries** with `category = "agent_skill"`. Each
   has a structured body: trigger, preconditions, procedure, postconditions,
   failure mode, version, author, last_reviewed.
2. **CLAUDE.md mandates** that every session, regardless of user, begins
   by loading active skills via `list_knowledge(category="agent_skill")`
   and applying the ones whose `trigger` matches the session state.
3. **Claude Desktop users** (who have no repo) receive the same
   expectation via a pinned "session protocol" instruction in their
   Claude config that points them to the same KB category.
4. **Day-one skills** seeded into the KB: `session_open`,
   `ingest_knowledge`, `review_assignment`, `record_fieldwork`,
   `per_row_review`. Specs in the companion analysis doc §6.4.
5. **Enforcement** through CLAUDE.md + pinned Claude Desktop instruction
   + skill postconditions that the agent asserts explicitly (observable in
   session memory).
6. **Lifecycle** mirrors the ADR process for substantive changes; minor
   updates land via `update_knowledge`. Every skill has a 90-day review
   cadence.

## Rationale

### Why this and not the alternatives

- **Shared storage is the KB** because every Claude on the farm already
  has read access, every write path already exists (`add_knowledge`,
  `update_knowledge`), and it is version-controllable. No new storage
  tier, no new auth surface. Keeps the architecture honest: farmOS is
  source of truth for farm state; KB is source of truth for knowledge
  *including knowledge about how to behave*.
- **KB entries over hardcoded tool logic** because behaviour changes
  frequently in early-stage farm operations, and a tool redeploy to
  change "session_open must also check X" is friction. KB entries can be
  edited by anyone with write access; the agents pick up the new
  behaviour on the next session.
- **Pull (agent queries at session start) over push (orchestrator
  injects)** for phase 1 because it requires no changes to any server,
  only CLAUDE.md edits and the KB entries themselves. Push can be added
  later as an MCP tool when the pull pattern proves stable.
- **Postconditions over pre-validation** because pre-validation hides
  bugs (a failing assertion is silent); postcondition assertions in the
  session summary are explicit, inspectable, and trip the next reviewer.

### Alternatives considered

- **Option A — Hard-code session protocol into each MCP tool.**
  Rejected: every tool would need updates for every protocol change;
  friction blocks iteration; couples behavioural evolution to deploy
  schedule.
- **Option B — Use each user's CLAUDE.md / Claude Desktop config as the
  source of truth.** Rejected: duplicates content across users (diverges);
  James does not have a repo; updates require touching every user's
  config.
- **Option C — Build a separate skill server (new service).** Rejected:
  over-engineered. The KB already solves storage + retrieval + versioning.
- **Option D — Add a `Task` entity to farmOS via a custom Drupal module
  (farm_syntropic).** Deferred to Phase 4 per architectural decision #14.
  FASF can ship now without it; the `review_assignment` skill fills the
  gap by scanning note prefixes until we have structured assignments.

## Consequences

### Positive

- **Behavioural consistency across Claudes.** Every agent follows the
  same session_open, ingest_knowledge, and record_fieldwork protocols.
- **No silent failures for durable knowledge.** `ingest_knowledge`
  postcondition requires either the KB entry_id is cited in session
  memory, or the failure is explicitly flagged.
- **No silent failures for farmOS writes.** `record_fieldwork`
  postcondition requires post-write verification.
- **Pending work is always visible to the assignee.** `review_assignment`
  makes "JAMES — …" prefixes queryable.
- **Skills are governable.** The ADR process applies for substantive
  behaviour changes; inline edits land for minor refinements.
- **Cheap to iterate.** Skill edits are KB updates, not deploys.

### Negative

- **Token cost at session start.** Loading active skills into the agent's
  context adds tokens per session. Phase 2 push model (MCP tool returns
  only relevant skills for the current context) mitigates.
- **Skill library can grow stale** if the 90-day review cadence is not
  enforced. Mitigation: a KB query for skills past due for review,
  surfaced at session_open.
- **Users must adopt the pinned Claude Desktop instruction.** For James
  and Claire, this requires one-off setup; not enforced by the framework
  itself. Mitigation: onboarding doc + Agnes audits at governance session.
- **Behaviour consistency is not behaviour correctness.** Every Claude
  running the same wrong skill produces consistent wrongness. Mitigation:
  ADR process for skill changes; 90-day review cadence; test sessions
  before ratifying new skills.

### Neutral

- **Ontology extension is optional.** We can add a `Task` /
  `AgentSkill` entity to `knowledge/farm_ontology.yaml` later; the
  framework does not require it. Skills living as KB entries with a
  category filter is sufficient for phase 1.

## Implementation

Phase 1 (this or next session):
1. Add a section to `CLAUDE.md` mandating session_open skill application.
2. Create day-one skill entries in KB under `category = "agent_skill"`.
3. Draft the pinned session-protocol instruction for Claude Desktop users
   (see `claude-docs/james-claude-session-protocol.md`).
4. Run integrity gate across last 30 days of James's sessions to catch any
   remaining silent failures from Mar / Apr.

Phase 2 (post-governance ratification):
1. Introduce `list_active_skills(context)` MCP tool for push-style skill
   loading.
2. Add `last_reviewed` query and surface skills past 90 days.
3. Extend write tools with optional post-write verify wrappers.

Phase 3 (with `farm_syntropic` module, Phase 4 overall):
1. Add `Task` / `Assignment` entity to the ontology.
2. Migrate `review_assignment` skill off note-prefix scanning onto
   structured queries.

## Links

- Companion analysis: `claude-docs/cross-agent-consistency-2026-04-18.md`
- Session protocol for Claude Desktop:
  `claude-docs/james-claude-session-protocol.md`
- Related memories:
  - `feedback_reference_photo_highest_quality.md`
  - `feedback_plantnet_verification_policy.md`
  - `reference_plantnet_cors.md`
