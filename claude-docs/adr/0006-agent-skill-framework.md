# 0006 — Firefly Agent Skill Framework (FASF)

- **Status:** accepted — 2026-04-21
- **Date:** 2026-04-18 (proposed) / 2026-04-21 (ratified)
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
   expectation via a **minimal one-line pinned instruction** in their
   Claude Desktop config: _"At session start, call
   `list_active_skills()` and apply the returned skills."_ All actual
   behaviour ships via the MCP tool's response, not via per-user
   config content. This collapses the per-user drift problem: the
   pinned instruction never changes; skill updates land in the KB and
   propagate to every client on their next session. The
   `list_active_skills()` tool itself is introduced in Phase 2 (see
   Implementation); until it ships, the stopgap is a slightly
   longer pinned instruction, but the end-state is the one-liner.
4. **Day-one skills** seeded into the KB: `session_open`,
   `ingest_knowledge`, `review_assignment`, `record_fieldwork`,
   `per_row_review`. Specs in the companion analysis doc §6.4 and,
   for `review_observations`, in `claude-docs/skills/review_observations.md`.
   Skill specs are the authoritative source for each skill's trigger,
   procedure, postconditions; one file per skill in
   `claude-docs/skills/NAME.md`, mirrored to KB entries at ratification
   time.
5. **Enforcement** through CLAUDE.md (Claude Code) + the one-line
   pinned instruction (Claude Desktop) + skill postconditions that
   the agent asserts explicitly (observable in session memory).
6. **Codebase is the source of truth for every skill, but the
   repo is not the contribution interface.** All skill `.md`
   source files live in `claude-docs/skills/` under git. KB entries
   with `category=agent_skill` are a **deployed copy**, not the
   master — maintained by a sync tool
   (`scripts/sync_agent_skills.py` + TS mirror) that reads the repo
   specs and writes/updates KB entries. A reconcile tool detects
   drift (direct-to-KB edits become a surfaced discrepancy Agnes
   decides to push or pull). This matches the existing pattern for
   `knowledge/plant_types.csv`, `knowledge/farm_ontology.yaml`, and
   `knowledge/farm_semantics.yaml` — repo-as-truth, deployment
   adapters per target. Rationale: skills are code-adjacent (a
   `record_fieldwork` postcondition often requires a change in
   `import-observations.ts`; atomic commits keep them aligned);
   target-architecture design requires auditable, reviewable skill
   state (not hidden behind a KB query).

   **Critical constraint: no farm-system user except Agnes is
   technical.** Claire, James, Olivier, WWOOFers do not understand
   git, commits, or PRs — and must not need to. The repo-as-truth
   rule applies to Agnes's write path, not to the contribution path.
   Non-technical users contribute exactly as they do today: they
   tell their Claude, Claude writes a `skill_feedback:<skill_name>`
   topic into team memory, Agnes's next `open_session` surfaces the
   queue, Agnes discusses and edits in-session. The sync tool must
   be light enough that Agnes's promotion loop is fast — single
   command, in-session, no pipeline. See
   [claude-docs/skills/README.md](../skills/README.md#how-users-contribute-no-git-knowledge-required)
   for the flow diagram.
7. **Lifecycle** mirrors the ADR process for substantive changes;
   minor updates land as git commits (not inline KB edits) and
   propagate via the sync tool. Every skill has a **30-day review
   cadence**. Staleness is surfaced, not timed: `open_session` runs
   `list_knowledge(category="agent_skill", last_reviewed_before=30d)`
   and presents any overdue skills to the manager at the start of
   the session. Early-stage farm operations evolve fast — 30 days
   keeps the library honest; can be relaxed to 90 once the set
   stabilises.
8. **Naming convention.** Shared behavioural skills (System B,
   seeded to KB): verb-first snake_case — `open_session`,
   `record_fieldwork`, `ingest_knowledge`, `classify_observation`,
   `archive_ghost_plant`. Verbs align with
   `knowledge/farm_ontology.yaml` verb mappings. Tactical skills
   (System A, client-side): kebab-case — `process-transcript`,
   `row-inventory`. The convention split is a visual cue for which
   system the skill belongs to.
9. **Two-system reality.** System A (client-installed skills:
   `.claude/skills/NAME/SKILL.md` for Claude Code; account-level
   uploads for Claude Desktop) and System B (FASF, this ADR:
   KB-backed, shared, loaded by the agent at session start) coexist
   by design. System A = tactical task automation with bundled
   scripts, installed per-user on each client. System B =
   behavioural protocols the agent always follows. A System A skill
   that creates a farmOS record invokes the System B
   `record_fieldwork` contract. Both live in `claude-docs/skills/`
   as source; deployment paths differ (symlink / UI upload / KB
   sync).

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
- **Skill library can grow stale** if the 30-day review cadence is not
  enforced. Mitigation: `session_open` skill runs
  `list_knowledge(category="agent_skill", last_reviewed_before=30d)`
  and presents overdue skills inline at the top of every session.
  Staleness becomes a visible prompt, not an untriggered timer.
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

## Performance budget

FASF introduces behaviour — and every behaviour costs latency. The
team is already reporting timeouts and slow tool calls; shipping a
chatty skill framework on top of that degrades the system further,
not improves it. The framework must operate inside a strict budget:

| Metric | Target | Degraded | Alerted |
|---|---:|---:|---:|
| `open_session` p95 latency | ≤ 3s | ≤ 5s | > 5s |
| Individual skill invocation p95 | ≤ 3s | ≤ 5s | > 5s |
| `system_health` p95 | ≤ 2s | ≤ 5s | > 5s |
| Session startup (first agent output) | ≤ 5s | ≤ 10s | > 10s |

Any metric in the "Alerted" column trips `system_health()` to a
degraded state and surfaces in the next `open_session` run. If the
framework cannot meet the "Degraded" column consistently, implementation
must pause until the bottleneck is fixed — shipping more skills on a
slow substrate compounds the problem.

## Implementation

### Phase 0 — Prerequisites (before any skill seeds)

These must be in place before FASF is useful at scale.

1. **Fix `system_health()` performance.** Currently ~51s per
   [project_mcp_timeout_root_cause](../../.claude/projects/-Users-agnes-Repos-FireflyCorner/memory/project_mcp_timeout_root_cause.md).
   Root cause: stale session loop + uncached taxonomy fetch. Target
   <5s. Blocks FASF ratification.
2. **Observability substrate.** Per-call telemetry (tool, user,
   duration, status), accessible via a new `get_usage_metrics()` MCP
   tool, surfaced via an expanded `system_health()` performance
   section. Design doc:
   [claude-docs/observability-and-telemetry-2026-04-21.md](../observability-and-telemetry-2026-04-21.md).
3. **TTL caches for slow-moving data.** Skills list (TTL 15min),
   plant types (15min), `farm_ontology.yaml` (15min — it's a repo
   file, read once per session). Invalidated on any write that
   affects the cached data.

### Phase 1 — Framework shipped (server-side composite)

**The pre-ratification plan had Phase 1 = client-side pull (agent
calls `list_knowledge` + 5 other tools at session open) and Phase 2 =
server-side push. Performance constraints invalidate that sequence:
6 MCP roundtrips per session is unaffordable given current team-
reported latency. Phase 1 and Phase 2 are merged.** FASF ships
directly in the server-push model.

1. Finalise day-one skill specs in `claude-docs/skills/NAME.md`
   (one file per skill, per conventions in
   [claude-docs/skills/README.md](../skills/README.md)).
2. Build `open_session(user, verbosity)` as a single server-side
   composite MCP tool. Server parallelises 5–6 sub-fetches with a
   3s timeout each; any sub-fetch that times out returns
   `"unavailable"` but the tool still succeeds. One roundtrip per
   session start; graceful degradation built in.
3. Build `scripts/sync_agent_skills.py` + TS mirror (lightweight,
   runnable in-session) to push `claude-docs/skills/shared_behavioural/*.md`
   to KB entries.
4. Seed KB with day-one skills via the sync tool.
5. Add a section to `CLAUDE.md` mandating that every Claude Code
   session begins with `open_session` output loaded into context.
6. Draft the one-line pinned session-protocol instruction for
   Claude Desktop users: _"At session start, call `open_session()`
   and apply the returned skills and context."_ James onboards on
   this instruction as the first skill-framework test subject —
   his first live session under FASF doubles as the ratification
   smoke test.
7. Extend write tools with post-write verify wrappers per
   `record_fieldwork` skill (implements ADR 0007 Fix 4).

### Phase 2 — Operational maturity

1. Build the reconcile tool (repo ↔ KB drift detector).
2. Wire `skill_feedback:<name>` team memory topic surfacing into
   `open_session` output — non-technical users' feedback becomes
   Agnes's skill-edit queue automatically.
3. Usage-driven skill retirement: if `get_usage_metrics(days=30)`
   shows a skill was never invoked, flag it for review.
4. (Optional, deferred from Phase 1.) Backfill integrity gate across
   the last 30 days of James's sessions.

### Phase 3 — Ontology extension (with farm_syntropic module)

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
