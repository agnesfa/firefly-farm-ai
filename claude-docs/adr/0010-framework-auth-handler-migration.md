# 0010 — Framework auth handler migration + framework version bump

- **Status:** accepted — 2026-04-21 (design ratified; implementation blocked on Lesley's package delivery, expected 2026-04-21)
- **Date:** 2026-04-21 (proposed and design-ratified same day; implementation starts once Lesley's tarballs land)
- **Authors:** Agnes, Claude (with Lesley input on framework)
- **Related:** ADR 0009 (farmOS v4 cutover), `project_farmos_auth_migration` memory note, `project_mcp_timeout_root_cause` memory note, `claude-docs/plan-2026-04-22-v4-migration-bundle.md`

## Context

Two pieces of deferred work are being bundled into the same window as
the farmOS v4 cutover (ADR 0009):

1. **Framework version bump.** The TypeScript MCP server depends on
   four `@fireflyagents/*` framework packages currently pinned at
   `1.0.0-beta.0` (built 2026-03-19, in `mcp-server-ts/packed-deps/`).
   Lesley has released a newer version with a small bug fix we flagged
   in a prior session. Exact version TBD — Agnes is waiting on the
   tarballs today.

2. **PlatformAuthHandler migration.** Lesley recommended (April
   timeframe — see `project_farmos_auth_migration.md`) moving the
   farmOS OAuth2 password-grant authentication out of our plugin's
   `FarmOSClient.connect()` and into a framework `PlatformAuthHandler`.
   Current state: the plugin authenticates per-request, retries on 401,
   and the framework runs a no-op auth handler
   (`apps/farm-server/src/auth/noop-platform-auth-handler.ts`).

The bundle exists because:

- All three changes touch the same TypeScript codebase.
- Doing the auth migration on the old framework would mean redoing it
  immediately after the framework bump.
- The auth migration is plausibly part of why `system_health` takes
  ~51s (per-request 1-2s OAuth round-trip × multiple parallel
  fetches) — see `project_mcp_timeout_root_cause.md`.
- The v4 cutover is the forcing function for a "we're touching
  everything anyway" window. Bundling avoids a second deploy
  coordination cycle later.

The Python server is not part of this ADR — it's Agnes's local fallback
only and doesn't ride the framework. It still gets the v4 cutover
(ADR 0009).

## Decision

Three sequential changes to the TypeScript server, gated on Lesley's
package landing:

1. **Bump framework packages** in `mcp-server-ts/packed-deps/` to
   Lesley's latest. Update `package.json` references. Resolve any
   API drift surfaced by `npm run build` and the existing 252 tests.

2. **Build `FarmOSPlatformAuthHandler`** implementing the framework's
   `PlatformAuthHandler` interface. It performs the OAuth2 password
   grant at session-init time using credentials from the tenant's
   `credentials.json` entry, and exposes the access token via
   `extra.authInfo.accessToken` to all tool handlers.

3. **Refactor `FarmOSClient`** to accept the access token from
   `extra.authInfo` rather than managing its own. Drop the
   `connect()` / `ensureConnected()` pattern. Remove the
   `noop-platform-auth-handler.ts` file. Register the new handler in
   `apps/farm-server/src/index.ts`'s `buildAppConfig` call.

Every TS tool handler that currently calls `getFarmOSClient(extra)`
gets adjusted to thread `extra.authInfo` into the client constructor or
factory. Mechanical change — the surface is wide (~31 tool files) but
the per-file diff is small.

Mirror to the Python server is **out of scope** for this ADR. Python is
local-only, doesn't ride the framework, and doesn't have the same
session-management benefits to gain.

## Rationale

Lesley's exact framing (memory note, paraphrased): use the framework as
a framework. Token lifecycle belongs at session level, not per-request.
Pre-tool hooks and metadata (InteractionStamp could eventually move
here too) belong at framework level. Auth cost is paid once at session
init, not on first tool call.

The system-health timeout investigation
(`project_mcp_timeout_root_cause.md`) named per-request OAuth as one of
two probable causes (the other being mcp-remote stale-session loops).
Moving auth to the framework directly addresses one of them.

The bundle decision is opportunistic, not architectural: the v4
cutover already requires deploying TypeScript changes and coordinating
with Mike. Adding two more deploys (framework bump, then auth refactor)
in the weeks after would be three coordination cycles instead of one.
The marginal cost of doing all three together is testing surface, not
deploy risk.

### Alternatives considered

- **Defer auth migration further.** Status quo. Rejected: every week
  it stays deferred, the duplicate auth code grows more entrenched and
  the system_health bug stays unsolved.

- **Auth migration without framework bump.** Use the current
  `1.0.0-beta.0` framework's PlatformAuthHandler interface. Rejected:
  Lesley's bug fix is in the new release; we'd refactor onto a
  known-buggy base and have to rework when we eventually upgrade.

- **Framework bump without auth migration.** Cleanest standalone
  change. Rejected: misses the bundle window. We'd touch the same
  codebase again 2-4 weeks later for the auth refactor.

- **Bundle Python migration too.** Rejected: Python doesn't ride the
  framework, has no PlatformAuthHandler equivalent, and is local-only.
  The benefit doesn't exist.

## Consequences

### Positive

- One coordination window instead of three.
- Eliminates duplicate auth code (currently maintained in plugin
  client + would-be framework handler).
- Likely contributes to fixing `system_health` 51s timeout.
- Token lifecycle managed at session level — better for any future
  multi-tool workflows that today re-auth needlessly.
- Framework bug fix lands in production.
- **Zero user-visible change expected** during the cutover. The
  `credentials.json` schema is unchanged — same `username` /
  `password` fields, just consumed at the session-init layer rather
  than per-request. James and Claire's sessions auto re-auth through
  the new handler on their next session start; they don't need to
  update creds, change pinned instructions, or re-login. The
  migration is observable only via `system_health().performance`
  latency improvement (and only if something breaks).

### Negative

- ~31 TS tool handler files touched. All mechanical, but the diff is
  wide and review takes time.
- Two refactors (framework bump + auth migration) interleave during
  the same week as the v4 cutover. If Lesley's package has unexpected
  drift, the schedule compresses.
- The Python server diverges further from the TS server in auth
  shape. Acceptable — Python is the local fallback, not the
  reference implementation.
- **Blast radius is total.** Every TS tool depends on the session
  handler. If `FarmOSPlatformAuthHandler` fails at session-init, every
  tool fails simultaneously for every user. Mitigation: rollback is a
  single `git revert` of the auth-handler commit + Railway redeploy,
  restoring the `noop-platform-auth-handler.ts` + plugin-level auth
  path. Expected recovery time <5 minutes. Pre-flight (Sat Apr 26)
  deliberately smokes a cross-section of tools to catch handler bugs
  before the v4 cutover window starts.

### Neutral

- `noop-platform-auth-handler.ts` retired, replaced by the real
  handler. Net file count unchanged.
- Tenant `credentials.json` schema unchanged — same `username` /
  `password` fields, just consumed at a different layer.

## Implementation

Phase 0 (blocking — waiting on Lesley):
- Receive framework tarballs.
- Place in `mcp-server-ts/packed-deps/`, replacing `1.0.0-beta.0`.
- Update `mcp-server-ts/package.json` package references if version
  string is in the dependency declaration.

Phase 1 — framework bump:
- `npm install && npm run build` from repo root.
- Run `npm run test` (252 tests). Fix any breakage from framework API
  drift. Document drift in this ADR if non-trivial.
- Manual smoke against margregen (still v3 at this point).

Phase 2 — auth handler:
- New file:
  `mcp-server-ts/apps/farm-server/src/auth/farmos-platform-auth-handler.ts`
  implementing the framework's `PlatformAuthHandler` interface. Logic
  copied from `FarmOSClient.connect()`:
  ```
  POST {farmUrl}/oauth/token
  grant_type=password
  client_id=farm
  username, password from authInfo.credentials
  → access_token cached in authInfo.accessToken
  ```
- `mcp-server-ts/apps/farm-server/src/index.ts` — replace
  `noopPlatformAuthHandler` with `FarmOSPlatformAuthHandler` in
  `buildAppConfig`.
- Delete
  `mcp-server-ts/apps/farm-server/src/auth/noop-platform-auth-handler.ts`.

Phase 3 — client refactor:
- `mcp-server-ts/plugins/farm-plugin/src/clients/farmos-client.ts` —
  remove `connect()`, `ensureConnected()`, internal token state.
  Constructor accepts `accessToken: string` directly. `_fetchWithRetry`
  no longer re-auths on 401 — surfaces the error (framework re-auths
  at session level per the token-expiry policy below).
- `mcp-server-ts/plugins/farm-plugin/src/clients/index.ts` —
  `getFarmOSClient(extra)` reads `extra.authInfo.accessToken` and
  `extra.authInfo.clientMetadata.farmUrl`.
- All ~31 tool files in `mcp-server-ts/plugins/farm-plugin/src/tools/`
  — verify each calls `getFarmOSClient(extra)` correctly. The factory
  signature absorbs the change; most files need no edit.

**Token-expiry policy (decided 2026-04-21):**
- The framework `PlatformAuthHandler` is responsible for re-authing
  on 401 at session level. On expiry, it re-runs the OAuth2 password
  grant, refreshes `authInfo.accessToken`, and retries the triggering
  tool call once transparently.
- The plugin client does NOT retry on 401. Double-issuing tokens at
  two layers is exactly the bug to avoid. A 401 surfacing to the
  plugin means the framework re-auth also failed; the tool errors
  with the explicit message `"farmOS session auth expired — please
  restart your Claude session to re-authenticate."` Non-technical
  users get a clear next step rather than a silent tool failure.
- Rationale: the framework already owns session lifecycle; token
  lifecycle is a session concern; plugin-level retry is architectural
  drift even if it happens to work. Making this explicit now rather
  than "decide during Phase 3" closes a surprise bug class ahead of
  first long-session use.

Phase 4 — tests + smoke:
- Unit tests for `FarmOSPlatformAuthHandler` in
  `apps/farm-server/src/auth/__tests__/`.
- Adjust `farmos-client.test.ts` to construct client with explicit
  token (no internal `connect()` to mock).
- `npm run test` green (target: 252+ tests).
- Deploy to Railway, run `system_health` — measure against the 51s
  baseline. If <20s, we've also closed out one of the Apr-15 carry-overs
  in `MEMORY.md` §7.

**Observability integration (if substrate has shipped):** the
[telemetry plan](../observability-and-telemetry-2026-04-21.md)
specifies per-call telemetry + `get_usage_metrics(days, group_by)`.
If these are in place pre-migration, Phase 4 validation becomes
objective: call `get_usage_metrics(days=1, group_by="tool")` before
and after redeploy; confirm p95 dropped. If the substrate hasn't
shipped yet, manual baseline on `system_health` duration is the
fallback. Either way, record the before/after number in the
session summary so we have a durable answer to "did the auth
migration fix the timeout?"

## Open questions

- **Lesley's package version — Agnes** (today). Until landed, this ADR
  stays `proposed`. Update version number in §Implementation Phase 0
  when received.
- **Does the new framework's PlatformAuthHandler signature differ from
  the `1.0.0-beta.0` interface?** Discover during Phase 1 build. Likely
  not, but documenting the assumption.
- **Should InteractionStamp move to framework metadata in this same
  pass?** Lesley mentioned it as a future possibility. Out of scope
  for this ADR — track separately if it becomes relevant. The
  InteractionStamp contract is defined by
  [ADR 0008 I6](0008-observation-record-invariant.md#i6--status--attribution);
  a future migration would move the *construction* of the stamp to
  a framework pre-tool hook while keeping the contract (fields, shape,
  write destination) owned by ADR 0008. Noted here so the cross-
  reference survives if anyone picks this up later.
- **Can `FarmOSClient` keep the retry-on-401 pattern as a
  belt-and-braces?** Probably not — if the framework re-auths at
  session level, plugin-level retry would double-issue tokens. Decide
  during Phase 3.
