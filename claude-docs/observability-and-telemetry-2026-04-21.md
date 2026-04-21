# Observability & Telemetry — Design Note

- **Date:** 2026-04-21
- **Authors:** Agnes, Claude
- **Status:** draft — proposed alongside FASF ratification
- **Scope:** MCP server (Python + TypeScript); farmOS write paths; skill invocations
- **Pre-reading:** [ADR 0006 FASF](adr/0006-agent-skill-framework.md) (performance budget + Phase 0 prerequisites)

## Why

The team is reporting timeouts and tool-call latency issues. `system_health()` itself takes ~51s. We're about to ship FASF, which adds a behavioural layer on top of the existing tool surface. **We cannot ship more behaviour on a substrate we can't see.**

Two failure modes we want to catch *before* a user complains:
1. A tool's p95 latency has doubled since last week — nobody tripped a timeout yet, but it's heading there.
2. A skill is silently failing a step in 10% of invocations — the session still "succeeds" but a postcondition is quietly broken.

This doc proposes a minimum-viable observability layer. It is intentionally small — enough to answer "what is slow / failing / unused", not a full metrics platform. We can grow it when we have real data telling us what we're missing.

## What we measure

Two levels of telemetry — both cheap, both queryable.

### Level 1 — Per-call telemetry (every MCP tool call)

Every invocation of every `fc__*` MCP tool records:

```json
{
  "ts": "2026-04-21T14:23:09.481Z",
  "tool": "query_logs",
  "user": "Agnes",                     // from auth context or first param
  "client": "claude-code|claude-desktop|unknown",
  "duration_ms": 823,
  "status": "ok|error|timeout",
  "error_code": null,                  // present when status != ok
  "cached": false,                     // if served from TTL cache
  "result_size_bytes": 4812            // approximate, for payload trend detection
}
```

**Storage.** In-memory ring buffer in each MCP server process (last 1000 calls, ~200KB). Periodic flush — every 5 minutes OR when buffer is 80% full, whichever first — to a team memory entry with `topics="telemetry"`. Old entries garbage-collect after 7 days.

**Cost.** One record per call, zero outbound I/O per call (flush is async batched). Measured overhead target: < 0.5ms per call.

### Level 2 — Per-skill-invocation telemetry

Every run of a shared_behavioural skill records:

```json
{
  "ts": "2026-04-21T14:23:12.100Z",
  "skill": "record_fieldwork",
  "version": "0.1.0",
  "user": "Agnes",
  "trigger": "user_describes_fieldwork",
  "duration_ms": 2400,
  "steps_total": 4,
  "steps_completed": 4,
  "steps_failed": 0,
  "postconditions_asserted": true,
  "status": "ok|degraded|failed"
}
```

**Storage.** Same mechanism as Level 1 — ring buffer → periodic flush → team memory.

**What this tells us.** Which skills are actually firing (dead skills discovered), which skills are slow (budget violations), which skills have partial-step failures (silent bugs).

## How to query it

### New MCP tool: `get_usage_metrics`

```
get_usage_metrics(
  days=7,                              // rolling window
  group_by="tool|user|skill|client",
  percentile=[50, 95, 99]              // optional, default [50, 95]
) → {
  window: "7d",
  group_by: "tool",
  rows: [
    {
      key: "query_logs",
      call_count: 1240,
      p50_ms: 180,
      p95_ms: 820,
      p99_ms: 2400,
      error_rate: 0.008,
      timeout_rate: 0.001,
      cache_hit_rate: 0.31
    },
    ...
  ]
}
```

**Use cases:**
- Agnes: "show me slowest tools last 24h" → `get_usage_metrics(days=1, group_by="tool")` sorted by p95.
- Agnes: "is Claire's session slower than mine?" → `get_usage_metrics(days=7, group_by="user")`.
- Agnes: "which skills nobody invokes?" → `get_usage_metrics(days=30, group_by="skill")`, look for zero-count entries.

### Extended `system_health()`

Current `system_health()` returns overall status + subsystem flags. Add a `performance` section built from Level 1 telemetry of the last 24 hours:

```
system_health() → {
  overall: "ok|degraded|down",
  mcp: {...},                          // existing
  farmos: {...},                       // existing
  apps_script: {...},                  // existing
  performance: {                       // NEW
    window_hours: 24,
    tool_p95_latency_ms: {
      query_logs: 820,
      query_plants: 1240,
      open_session: 2100,
      system_health: 4800              // ← this itself, meta-measured
    },
    slowest_tools: [
      {tool: "import_observations", p95_ms: 8400},   // over budget
      {tool: "open_session", p95_ms: 2100}
    ],
    error_rate_by_tool: {
      add_knowledge: 0.012,
      ...
    },
    budget_violations: [                // tools currently over their budget
      {tool: "import_observations", metric: "p95", value: 8400, budget: 5000}
    ]
  }
}
```

`open_session` itself surfaces `system_health.performance.budget_violations` so Agnes sees regressions at the top of every session.

## Budgets and alerts

Per [ADR 0006 performance budget](adr/0006-agent-skill-framework.md#performance-budget):

| Tool / Metric | Target p95 | Degraded | Alerted |
|---|---:|---:|---:|
| `open_session` | 3s | 5s | > 5s |
| `system_health` | 2s | 5s | > 5s |
| `query_logs` | 1s | 3s | > 5s |
| `query_plants` | 1s | 3s | > 5s |
| `import_observations` (per submission) | 5s | 10s | > 15s |
| Individual skill invocation | 3s | 5s | > 5s |
| Session startup (first agent output) | 5s | 10s | > 10s |

**How alerts fire.** No external alerting infrastructure (we're not paying for PagerDuty). Instead:
1. `system_health().performance.budget_violations` is non-empty.
2. `open_session` surfaces the violation count at the top of every session.
3. Agnes sees it, fixes the root cause or raises an issue for later.

**Alert fatigue is a risk.** If `import_observations` is routinely over budget during WWOOFer-cohort imports, that's expected and shouldn't fire every session. Mitigation: mark some violations as "known / tolerated until Phase 2" — stored as a KB entry with `category=budget_exception`. `system_health` subtracts these from the violation count.

## Privacy and security considerations

Small farm, small team, low stakes — but worth naming:

- **User identity in telemetry is a first-name string** (Agnes, Claire, James, Olivier, wwoofer-{instance_id}). Not email, not full name, not role metadata. WWOOFer sessions use a generic account identifier, not the individual volunteer's name.
- **Result sizes are stored but not result contents.** We record that a tool returned 4812 bytes, not what those bytes were. Telemetry entries never contain farmOS data.
- **Telemetry flushes to team memory entries with `topics=telemetry`.** Team memory is accessible to every Claude — this is a feature (observability is shared) but means we never put anything sensitive in there. Non-issue at the current scope; re-evaluate if we ever add customer-facing data.
- **Retention: 7 days of raw entries.** Aggregated stats (daily summaries) retained 90 days in a separate team memory category, so we can see month-over-month trends without keeping raw call logs forever.

## Implementation plan

### Phase 0A — Minimum viable observability (ship with FASF Phase 0)

1. Add telemetry hook to the MCP server request lifecycle (Python + TS). Records Level 1 entry on every tool call. In-memory ring buffer (1000 entries).
2. Async flush to team memory with `topics=telemetry` every 5 minutes.
3. Add `get_usage_metrics(days, group_by)` MCP tool reading from the flushed team memory entries + current buffer.
4. Extend `system_health()` with the `performance` section.
5. Wire `open_session` to surface budget violations.

Estimated scope: 1-2 sessions of focused work. Same Python + TS parity pattern as ADR 0008 shipments.

### Phase 0B — Skill-invocation telemetry (ship alongside first shared_behavioural skills)

1. Every `shared_behavioural/*.md` skill logs Level 2 telemetry at the end of its run.
2. `get_usage_metrics(group_by="skill")` returns skill stats.
3. `open_session` surfaces "skills never invoked in last 30 days" for deprecation review.

### Phase 1 — Cache invalidation integration

1. Writes that affect cached sections (skills, plant_types, ontology) tag the cache for invalidation.
2. Cache hit rate surfaces in telemetry.

### Phase 2 — Retention + aggregation

1. Daily aggregation job compresses raw entries into summary stats.
2. 90-day aggregated retention, 7-day raw retention.
3. Trend queries (`get_usage_metrics(days=30, compare_to_previous=true)`) surface week-over-week changes.

## Open questions for governance

- **Q1 — Storage tier.** Team memory is cheap but not purpose-built for time-series data. Is this good enough forever, or do we need a dedicated tier (SQLite in the repo, or a Drupal log type) once volume grows? Suggested answer: team memory is fine until we exceed ~500 calls/day (we're currently at ~100/day); re-evaluate then.
- **Q2 — Telemetry for non-MCP code paths.** QR-page JS → Apps Script → Sheet flow is opaque today. Adding telemetry there is doable but separate scope — Apps Script timing + Sheet update latency. Propose: defer until after FASF ships.
- **Q3 — Exposing metrics to non-Agnes users.** Claire and James might benefit from "my own session latency trend". Is this worth exposing via `get_usage_metrics(user=self)` or is it noise? Suggested: expose read-only to the user's own stats once FASF is live; admin-only for cross-user comparison.
- **Q4 — Privacy budget.** At WWOOFer generic account, multiple volunteers share one identity. Acceptable? Or do we want per-volunteer tagging (session_id + volunteer_name captured at sign-in)? Suggested: acceptable for now; revisit if we ever care about per-volunteer reliability.

## Links

- [ADR 0006 FASF](adr/0006-agent-skill-framework.md) — performance budget + Phase 0 prerequisites
- [project_mcp_timeout_root_cause](../../.claude/projects/-Users-agnes-Repos-FireflyCorner/memory/project_mcp_timeout_root_cause.md) — known slow `system_health` baseline
- [skills/shared_behavioural/open_session.md](skills/shared_behavioural/open_session.md) — consumer of the performance section
