---
name: open_session
version: 0.2.0
status: draft
system: B
trigger: session_start
last_reviewed: 2026-04-21
author: Agnes, Claude
supersedes: open_session@0.1.0
related_adr: 0006
related_ontology_verbs: []
---

# Skill: open_session

## Purpose

Every Claude session at Firefly Corner must start from the same ground state: the agent knows what's pending for the user, what the team has been doing, what skills are active, and which parts of the data model are currently known-divergent. Without this, each session re-discovers reality from scratch — and over time sessions disagree with each other, silent failures accumulate, and the user cannot trust the agent's answers.

The April 18 cross-agent consistency investigation ([cross-agent-consistency-2026-04-18.md](../../cross-agent-consistency-2026-04-18.md)) found 17 pending logs visible to Agnes's Claude but invisible to James's — because James's Claude had no consistent session-open protocol. This skill is the fix.

## Performance-first design (v0.2)

**v0.1 specced this as 6 client-side MCP calls at session start.** The team was already reporting timeouts (`project_mcp_timeout_root_cause`) when v0.1 was written; shipping six calls per session would have compounded the problem. v0.2 **replaces the client-side pull with a single server-side composite MCP tool** (`open_session(user, verbosity)`) that parallelises all sub-fetches server-side with per-section timeouts. One MCP roundtrip per session. Graceful degradation — if any sub-fetch stalls, that section returns `"unavailable"` and the tool still succeeds.

This is the Phase 1/Phase 2 merge specified in [ADR 0006 Implementation](../../adr/0006-agent-skill-framework.md#phase-1--framework-shipped-server-side-composite).

## Trigger

- Start of every Claude session, regardless of user or client.

## Preconditions

- MCP server reachable.
- User identity is known (so the tool can filter `pending_for_user` and `team_activity_7d`).

## Procedure

### Step 1 — Single MCP call

```
result = open_session(
  user=<current_user>,
  verbosity="full" | "minimal"     // minimal for Agnes's CC (less context needed);
                                    // full for Desktop / new users
)
```

The server runs the following **in parallel**, each with a 3s timeout. Any timeout returns `"unavailable"` for that section; the overall tool still succeeds.

| Section | Server-side source | Cache TTL |
|---|---|---|
| `skills_active` | KB entries `category=agent_skill AND status=active` | 15 min |
| `skills_overdue_review` | KB entries `last_reviewed < now-30d` | 15 min |
| `skills_feedback_queue` | team memory with `topic CONTAINS "skill_feedback:"` | 5 min |
| `system_health` | `system_health()` aggregate (uses its own cache) | 1 min |
| `pending_for_user` | `query_logs(status=pending)` filtered by `"<USER> —"` notes prefix | live |
| `pending_total` | `query_logs(status=pending)` count | 5 min |
| `team_activity_7d` | `read_team_activity(days=7, only_fresh_for=user)` | live |
| `integrity_flags` | `farm_context(topic=overview).data_integrity` | 1 min |

Return shape:

```json
{
  "user": "Agnes",
  "verbosity": "minimal",
  "skills_active": [{"name": "open_session", "version": "0.2.0"}, ...],
  "skills_overdue_review": [],
  "skills_feedback_queue": [
    {"skill": "review_observations", "from": "Claire", "summary_id": "128", "topic": "skill_feedback:review_observations — block 5 should include ..."}
  ],
  "system_health": {"overall": "ok", "mcp_latency_p95_ms": 650, "degraded_tools": []},
  "pending_for_user": [{"id": "a1b2", "note_excerpt": "AGNES — re-ID coriander ..."}],
  "pending_total": 59,
  "team_activity_7d": [{"user": "James", "summaries": 8, "topics": "transplants, winter prep"}],
  "integrity_flags": [],
  "per_section_latency_ms": {"skills_active": 120, "pending_for_user": 280, ...},
  "unavailable_sections": []
}
```

### Step 2 — Present to user

The agent summarises the result in a fixed order. Each section is a single line unless there's something to show. Agnes gets minimal; Desktop users get full.

```
open_session (verbosity=minimal, 2.4s):
• Skills: 8 active, 0 overdue, 1 feedback signal (see below)
• Health: ok (p95 latency 650ms)
• Your pending: 3 (a1b2, c3d4, e5f6)
• Team pending total: 59
• Team delta (7d): James 8 summaries (transplants, winter prep); Claire no new
• Integrity: clean
• Skill feedback: 1 — Claire Apr 20 "review_observations block 5 should include ..."
```

If `unavailable_sections` is non-empty, the agent states:
```
open_session (verbosity=minimal, 3.1s): 2 sections degraded
• skills_overdue_review: UNAVAILABLE (KB query timed out at 3s)
• team_activity_7d: UNAVAILABLE (read_team_activity returned error)
• {rest as normal}
```

### Step 3 — Ready for user request

The agent does NOT proactively start work. `open_session` ends with: "What would you like to work on?" or the equivalent in the user's preferred style.

## Postconditions

Asserted explicitly in the summary line at the end of the skill's run (also logged to telemetry per the [observability doc](../../observability-and-telemetry-2026-04-21.md)):

- **Skills loaded:** N active skills loaded; any overdue surfaced.
- **Feedback queue surfaced:** skill-feedback signals for Agnes presented (even if zero).
- **Pending reviewed:** user has M pending items; team has K; numbers stated.
- **Team delta reviewed:** session summary covered days=7; fresh summaries for the user surfaced.
- **Integrity state:** gate clean OR discrepancies surfaced.
- **Latency within budget:** total call ≤ 5s; if >5s, user sees "SLOW" tag on the output and `system_health` is auto-flagged.

The summary line the agent states is literally:
> "open_session complete in Xms: N skills, M pending, K total, team delta reviewed, integrity {clean|flagged}. Unavailable: [sections or none]."

## Failure mode

- **Entire `open_session` MCP call fails / times out beyond 10s.** Abort. Report to user: "Cannot open session — MCP unreachable or all sub-fetches timed out. Proceed offline for discussion only; no writes." Writes are blocked in a session where open_session did not complete. (The session CAN still continue for read-only conversation.)
- **Individual section returns `"unavailable"`.** Proceed, but flag the section explicitly in the summary so the user knows what the agent *doesn't* know this session. Example: if `integrity_flags` is unavailable, the agent warns before any write, "Integrity gate state unknown this session — proceed with caution."
- **Result looks stale / inconsistent** (e.g. `pending_for_user = 0` but the user knows there are pendings). The agent flags the discrepancy and suggests cache bust via `system_health(refresh=true)`. A pattern of these trips `system_health` degraded.
- **Skill-feedback queue returns >10 items.** Truncate to 5 most recent, state the remainder count, recommend Agnes schedule a skill-review session.

## Dependencies

- MCP tool: `open_session(user, verbosity)` — single composite, server-side (to be built)
- Underlying server-side fetches: `list_knowledge`, `system_health`, `query_logs`, `read_team_activity`, `farm_context`, team memory search
- Telemetry: records to in-memory ring buffer via the observability substrate
- Other skills invoked by this one: none (this is the root skill)
- Other skills that depend on this one running first: every write-flavoured shared_behavioural skill (`record_fieldwork`, `review_observations`, `ingest_knowledge`, etc.)

## Example

```
Agnes starts a new session on Claude Code.

[open_session(user="Agnes", verbosity="minimal") — 2.4s total, server-parallel]

open_session (2.4s, minimal):
• Skills: 8 active (open_session 0.2.0, record_fieldwork 0.1.0, close_session 0.1.0, review_observations 0.2.0, ingest_knowledge 0.1.0, review_assignment 0.1.0, per_row_review 0.1.0, classify_observation 0.1.0). 0 overdue.
• Health: ok (p95 tool latency 650ms, no degraded tools)
• Your pending: 3 (logs a1b2..., c3d4..., e5f6...)
• Team pending total: 59 (47 classifier-ambiguous I11, 12 field-review)
• Team delta (7d): James 8 summaries (transplants + winter prep Apr 20 AM); Claire no new; Olivier no new
• Integrity: clean
• Skill feedback (1): Claire 2026-04-20 summary_id=128 — "review_observations block 5 should include neighbour-section cross-check"

What would you like to work on?
```

## Known gaps

- **v0.2 depends on the `open_session` MCP tool being built** — it does not exist yet. Until it does, this skill cannot ship. Phase 0 prerequisite per ADR 0006.
- **No telemetry schema yet.** The `per_section_latency_ms` field assumes the observability substrate is in place. See [observability-and-telemetry-2026-04-21.md](../../observability-and-telemetry-2026-04-21.md).
- **Cache invalidation is coarse.** Writes that affect cached sections (e.g. `add_knowledge` with `category=agent_skill`) should invalidate the `skills_active` cache immediately. Implementation TBD.
- **`skills_feedback_queue` schema not finalised.** The convention is team memory summaries with `topics` containing `skill_feedback:<skill_name>` but the exact query + shape needs fixing before the tool builds.
- **Verbosity parameter is client-driven and trusts the client.** Agnes asking for "minimal" is obvious; a WWOOFer asking for "minimal" on their first session would hide context they need. Heuristic: default `full` for first 10 sessions per user, `minimal` after.

## Lineage

- Origin: [cross-agent-consistency-2026-04-18.md §6.4](../../cross-agent-consistency-2026-04-18.md) day-one skill specification (as `session_open`).
- Renamed `session_open` → `open_session` for verb-first convention (ADR 0006 point 8).
- v0.1 client-side pull was drafted 2026-04-21 AM; v0.2 server-side composite is the same-day revision after Agnes flagged the performance problem.
- ADRs: [0006](../../adr/0006-agent-skill-framework.md) (FASF framework + performance budget), [0008](../../adr/0008-observation-record-invariant.md) (I11 classifier skill upgrade loads via this skill).
- Related observability doc: [observability-and-telemetry-2026-04-21.md](../../observability-and-telemetry-2026-04-21.md).
