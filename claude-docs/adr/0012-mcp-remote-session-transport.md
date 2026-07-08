# 0012 — Fix intermittent "Connection closed" via mcp-remote transport pin + session-lifecycle hardening

- **Status:** proposed — 2026-07-07 (client fix in trial on the volunteer laptop; promote to accepted once validated)
- **Date:** 2026-07-07
- **Authors:** Agnes, Claude
- **Related:** ADR 0009 (farmOS v4 cutover), ADR 0010 (framework auth handler), `project_mcp_timeout_root_cause` memory note

## Context

Team members repeatedly hit `MCP error -32000: Connection closed` on farm
MCP tool calls — intermittently, and disproportionately on the Google
Apps Script-backed tools (`read_team_activity`, `search_team_memory`,
`write_session_summary`, `search_knowledge`, `list_observations`). It hit
James's and the volunteer's Claude Desktop laptops, and Agnes's Claude Code,
during the 2026-07-07 session. The volunteer laptop reached a fully-stuck
state ("can't access team memory at all").

A 2026-07-07 diagnostic established the root cause with evidence, and ruled
out the obvious suspects:

- **Not slow backends.** Raw HTTP against production holding one session:
  16/16 slow-tool calls succeeded in 2.5–7.2s, zero drops. Apps Script is
  not timing out today.
- **The failures are session invalidation.** Railway logs show a steady
  stream of `Invalid session ID` / `Missing session ID` from the
  streamable-HTTP handler — the *same* session IDs 404ing across 2.5 hours.
- **The server is spec-correct.** It returns HTTP 404 for an unknown
  session (verified on a logged-dead ID and a random one), which is what
  the MCP spec says should trigger the client to re-initialize.
- **Sessions die two ways.** (a) The session store is in-memory, so every
  redeploy wipes all sessions — and there was exactly one deploy today
  (06:18 UTC), which was Agnes's/Claude's credential change (adding the
  farmhand key via `railway variables --set CREDENTIALS_JSON`); every
  session error is after it. (b) A **1-hour session TTL** (`ttl: 3600`,
  hardcoded in `@fireflyagents/mcp-server-core` `default-server.js:53`,
  not configurable from the app) invalidates even active long-lived
  connections roughly hourly.
- **The client mishandles the 404.** `mcp-remote`'s default transport
  strategy is `http-first`, which *"falls back to SSE if HTTP fails with a
  404 error."* Our expired-session 404 is plausibly mis-read as "HTTP
  unsupported → fall back to SSE," so instead of a clean one-round-trip
  re-initialize, the client drops the in-flight call as `-32000` and can
  get wedged. `npx -y mcp-remote` also pulls **latest** on every launch
  (today: 0.1.38), so client behaviour is non-reproducible.

## Decision

Four parts, in priority order:

1. **Client transport pin (trial now).** Change every farm Claude config
   from `-y mcp-remote` to `-y mcp-remote@0.1.38` **and add
   `--transport http-only`**, forcing streamable HTTP and removing the
   SSE-fallback-on-404 path. Applies to the volunteer + James Claude
   Desktop configs and Agnes's `~/.claude.json`. Validate on the volunteer
   laptop (currently broken) before rolling out; if `http-only` doesn't
   hold, try `sse-only`.

2. **Stop redeploying to change credentials (ops).** Adding a user/key must
   not restart the server and wipe every active session. Move credentials
   to a Railway volume file + use the framework `POST /admin/reload`, or
   batch credential changes into low-usage windows. This removes the single
   biggest mass-invalidation trigger (which caused this very incident).

3. **Framework escalation (Foundry).** Raise the session TTL (1h → 8–24h,
   sliding on activity) and set explicit HTTP-server `keepAliveTimeout` /
   `headersTimeout` / `requestTimeout`. These live in
   `@fireflyagents/mcp-server-core` (packed-dep, not editable here), so
   file against the framework repo.

4. **In-repo defensive fetch hardening (deferred).** Add
   `signal: AbortSignal.timeout(90_000)` + light retry to the two raw
   `fetch()` calls in `plugins/farm-plugin/src/clients/apps-script-client.ts`.
   Not today's cause, but prevents the *future* variant: as the observation
   / KB sheets grow, Apps Script latency climbs (documented linear scaling)
   toward the point where an untimed fetch hangs into a Railway edge drop.

## Rationale

The server already does the correct thing (404 on expired session). The
user-visible failure lives in the **client bridge** — so the highest-leverage
fix is at the client (`--transport http-only`), not the server. Pinning the
version buys reproducibility so a future `mcp-remote` publish can't silently
regress every laptop.

The biggest *trigger* is orthogonal to the client: a redeploy wipes all
in-memory sessions at once, and credential changes shouldn't cause redeploys.
Fixing that (part 2) removes the mass events; fixing the TTL (part 3) removes
the slow drip. The defensive fetch timeout (part 4) closes the latent future
hole surfaced during the investigation.

### Alternatives considered

- **`--transport sse-only`.** The opposite corner — force SSE, no HTTP.
  Rejected as first choice because the server is primarily a streamable-HTTP
  server; kept as the fallback trial if `http-only` fails.
- **Persist the session store (Redis) so sessions survive restarts.**
  Rejected: `StreamableHTTPServerTransport` objects are per-process and
  can't be serialized/shared, so a restart inevitably invalidates sessions
  regardless of where session *metadata* is stored. The MCP model expects
  re-init on restart; the real fix is graceful client recovery, not session
  persistence.
- **Just keep retrying at the tool layer.** Rejected: treats the symptom,
  loses the in-flight call, and does nothing for the wedged-client state the
  volunteer hit.
- **Add a fetch timeout and call it the fix.** Rejected as the *headline*
  fix: evidence shows Apps Script is fast today, so this wouldn't stop the
  current drops. Kept as deferred hardening (part 4).

## Consequences

### Positive

- Removes (or sharply reduces) the `-32000` drops for the whole team.
- Reproducible client version — no more silent `mcp-remote` latest-version
  drift across four machines.
- Credential changes stop taking everyone's session down.
- Closes the latent slow-Apps-Script failure mode before it activates.

### Negative

- `--transport http-only` is a hypothesis with a clear mechanism, not a
  certainty — needs validation on the volunteer laptop before rollout.
- Parts 2 and 3 add ops/framework work outside this repo (volume + admin
  key; a Foundry framework change).
- Pinned version now needs manual bumps to pick up genuine `mcp-remote`
  improvements.

### Neutral

- No farmOS or farm-data change. Pure transport/session lifecycle.

## Implementation

Client config (all farm Claudes) — `~/.claude.json` (Agnes) and
`claude_desktop_config.json` (James, volunteer):

```json
"args": [
  "-y", "mcp-remote@0.1.38",
  "https://firefly-farm-ai-production.up.railway.app/mcp",
  "--transport", "http-only",
  "--header", "x-api-key: <THAT USER'S KEY>"
]
```

Per-laptop rollout: replace config → delete `~/.mcp-auth` (clears the wedged
session) → fully quit + reopen Claude Desktop.

- **Part 1 (client):** config-only, no code. Trial on volunteer laptop first.
- **Part 4 (deferred, in-repo):** `plugins/farm-plugin/src/clients/apps-script-client.ts`
  (fetch timeout + retry) — pattern already used at `apps/farm-server/src/index.ts:84`
  and `.../auth/farmos-platform-auth-handler.ts:68`.
- **Commit SHA when written:** (docs-only ADR; no code change in this commit).

## Open questions

- **Does `http-only` actually stop the drops?** — Agnes, validate on the
  volunteer laptop; promote this ADR to accepted or pivot to `sse-only`.
- **`/admin/reload` path for credential changes** — needs an admin key +
  credentials on a volume file rather than the `CREDENTIALS_JSON` env var.
  Who owns configuring that? — Agnes.
- **Framework TTL + server timeouts** — file against
  `fa-intelligence-foundry` / the mcp-server-core framework repo. — Agnes.
- **Should the team move off `mcp-remote` entirely** once MCP clients gain
  native remote-HTTP+OAuth support? — revisit when clients support it.
