# 0009 — farmOS v4 cutover via runtime version flag

- **Status:** accepted — 2026-04-21 · **CODE SHIPPED 2026-04-27** (commits `7587ccc` TS + `8e4059f` Python + `fdee24f` docs); production running on `FARMOS_API_VERSION=3`, awaiting Mike's margregen upgrade for the `'4'` flip.
- **Date:** 2026-04-21 (proposed and ratified same day, forcing-function deadline 2026-04-27)
- **Authors:** Agnes, Claude
- **Related:** ADR 0010 (Framework auth handler migration), `claude-docs/plan-2026-04-22-v4-migration-bundle.md`

## Context

Michael Stenta (Farmier host) emailed 2026-04-04 announcing farmOS v4 is
available, and a follow-up confirmed he intends to upgrade
`margregen.farmos.net` on **2026-04-27**. The upgrade path is forced —
Farmier moves all hosted instances to v4; we don't get to stay on v3.

The blog (https://farmos.org/blog/2026/farmOS-v4-and-v3.5/) and the v4.0.0
changelog (https://github.com/farmOS/farmOS/blob/4.0.0/CHANGELOG.md) describe
two breaking changes that affect us:

1. **Asset `status` base field removed**, replaced by `archived` boolean
   (`#986`). Migration: assets with status="archived" → `archived: true`,
   else `archived: false`. The field disappears from JSON:API responses
   entirely; `filter[status]=...` returns 400.
2. **`is_castrated` → `is_sterile`** on Animal assets (`#960`). We don't
   use Animal assets — non-issue.

Other changes (Plan model rework, `farm_api` made optional + split into
`farm_api_oauth`, JSON:API Extras removal, Worker role tightening,
cross-farm log validation, PHP 8.4 / DB version bumps) either don't
affect us or are Mike's problem on the host side. The OAuth2 question is
parked in the reply to Mike (confirm `farm_api_oauth` enabled and the
existing `farm` OAuth client preserved).

Audit of our codebase against the asset-status removal: ~25 sites across
the Python MCP server, the TypeScript MCP server, the import scripts,
and a handful of doc/KB files. Concrete locations enumerated in
`claude-docs/plan-2026-04-22-v4-migration-bundle.md`.

The window between "we have the v4 code working" and "Mike actually
flips margregen to v4" needs a coordination strategy: deploying v4
client code while the server is still v3 will brick us; deploying
v3-only code while the server is on v4 will brick us equally.

## Decision

Introduce a runtime config flag `FARMOS_API_VERSION` (default `"3"`,
acceptable values `"3"` and `"4"`). Branch in a small set of
deliberately-narrow code sites:

1. **Asset list-filter builder** — when v3, emit `filter[status]=active`
   / `filter[status]=archived`; when v4, emit `filter[archived]=0` /
   `filter[archived]=1`.
2. **Archive-write payload builder** — when v3, PATCH
   `attributes.status = "archived"`; when v4, PATCH
   `attributes.archived = true`.
3. **Asset display-status reader** — when v3, read
   `attributes.status`; when v4, derive `"active" | "archived"` from
   `attributes.archived` boolean.
4. **Create-asset payload** — drop `status: "active"` from POST bodies
   entirely (it's redundant in v3 since active is the default, and the
   field doesn't exist in v4). Single-version code, no branch.

Every other site touching status (test fixtures, docs, KB YAMLs)
follows from these four pivot points.

The flag lives in environment config in both servers:
- **TypeScript:** read from `process.env.FARMOS_API_VERSION` at
  `FarmOSClient` construction, exposed via `client.apiVersion`.
- **Python:** read from `os.getenv("FARMOS_API_VERSION", "3")` in
  `farmos_client.FarmOSClient.__init__`, exposed as `self.api_version`.

Tests are parameterised over both versions. The flag stays in the
codebase for at least one release cycle past stable v4 operation; the
v3 branch gets removed in a follow-up PR (tracked as a deferred task,
not blocking).

## Rationale

The forcing function is Mike's upgrade window. We have ~6 days. The
strategy must satisfy:

1. **Pre-deployable** — code lands and is exercised in production with
   the flag at `"3"` well before Mike's window, so the v4 path isn't
   first tested under time pressure.
2. **Reversible mid-flight** — if Mike's upgrade slips or a regression
   appears, we flip the flag back without redeploying.
3. **Small surface area** — minimise the count of places where v3-vs-v4
   logic lives, so the eventual removal PR is one-shot.

A runtime flag wins on all three. It's also the same pattern we
already use for other config (`FARMOS_URL`, OAuth credentials), so it
sits in muscle memory.

### Alternatives considered

- **Single-commit cutover, no flag.** Deploy v4-only code at the moment
  Mike says "done". Rejected: zero rollback window; coordination has to
  be tight to the minute; if Mike's upgrade fails partway, we're worse
  off than before.

- **Dual-shape on every request** — always send both
  `filter[status]=active` AND `filter[archived]=0` so both versions
  accept the query. Rejected: roughly doubles the URL builder surface
  for a few days of benefit; v4 may reject unknown filter keys with
  400; doesn't help the write path at all (PATCHes can't be dual-shape).

- **Server-version detection via `/api/` capability probe** — auto-detect
  on first connect, cache, branch. Rejected: adds an HTTP call to
  startup; opaque; cache invalidation is another bug surface; we already
  know exactly when the cutover happens.

- **Pre-stage v4 code on a branch, merge at cutover.** Rejected: leaves
  the v4 path untested in production until the riskiest moment.

## Consequences

### Positive

- Code can land Apr 22-25, deploy Apr 26 with `flag=3`, soak for a day.
- Cutover reduces to "flip env var on Railway, redeploy".
- If anything goes sideways at cutover, flag reverts in <2 minutes.
- Same pattern we can reuse for any future forced upgrade.

### Negative

- ~6 days of dual-path code in the read filter, archive write, and
  status display sites. Test surface roughly doubles for those sites
  (parameterised tests over both versions).
- Cleanup PR required after stable v4 operation; if forgotten, the
  v3 dead branch lingers.
- The Python server gets the same flag plumbing even though it's
  Agnes's local fallback only. Reason: Agnes still runs Python for
  local dev / reconciliation work; the flag keeps her local environment
  consistent with the Railway TS server so tests and scripts don't
  diverge. Not "overhead" so much as "parity by design".

### Neutral

- `create_plant`-shape POSTs lose the redundant `status: "active"` line
  unconditionally. Behaviour identical in v3 (active is default) and
  v4 (field doesn't exist).
- **Parallel-safe work in the same window.** Three items are v3/v4-
  independent and can land alongside this ADR without version branching:
  (1) ADR 0007 Fix 6 batch-size cap at `import_observations_batch`
  (pure input validation); (2) ADR 0008 I12 `parse_date` future-
  timestamp guard (pure input validation); (3) the `record_fieldwork`
  shared_behavioural skill spec from ADR 0006 (consumes client helpers
  defined here so it's version-agnostic by construction). Listing them
  explicitly so the FASF / reliability threads don't accidentally
  hardcode v3-only shapes.
- **Observability tie-in.** The v3→v4 cutover is measurable if the
  observability substrate from
  [claude-docs/observability-and-telemetry-2026-04-21.md](../observability-and-telemetry-2026-04-21.md)
  is in place. Per-tool telemetry + extended `system_health.performance`
  gives objective evidence of whether v4 regresses any tool's p95
  latency. Worth bundling into the pre-flight Apr 26 check if the
  substrate ships first; otherwise manual baselines pre- and post-flip
  on the Sat/Sun timeline.

## Implementation

Files touched (Phase A — pre-cutover, both servers):

**Python (`mcp-server/`):**
- `farmos_client.py:46-90` — read `FARMOS_API_VERSION` in `__init__`.
- `farmos_client.py:570,650` — branch URL-string `filter[status]=` /
  `filter[archived]=` builder.
- `farmos_client.py:622-625,636-640` — `fetch_all_paginated` filters
  dict; helper `_status_filter(active=True)` returns the right
  key/value pair for the active version.
- `farmos_client.py:980-1012` (`archive_plant`) — branch PATCH
  payload (`status: "archived"` vs `archived: true`).
- `farmos_client.py:716-740` — formatters that read
  `attributes.status` → use helper `_asset_status_label(asset)` that
  branches on version.
- `farmos_client.py:421-425, 537-543` — drop `"status": "active"` from
  create payloads.
- `server.py:161, 340, 1379, 4073` — call sites use the helpers above.
- Test fixtures (`tests/conftest.py`, `tests/test_farmos_client.py`,
  `tests/test_tools_write.py`) — add `archived: false/true` alongside
  existing `status` fixtures; parameterise tests over both versions.

**TypeScript (`mcp-server-ts/plugins/farm-plugin/`):**
- `src/clients/farmos-client.ts:71-94` — read API version into
  `client.apiVersion` field.
- `src/clients/farmos-client.ts:504, 530-535, 565` — branch URL filter
  builder + `fetchAllPaginated` filter dict.
- `src/clients/farmos-client.ts:591, 601` — formatters read status via
  helper.
- `src/tools/archive-plant.ts` — relies on `client.archivePlant()`
  internals; no direct change needed.
- `src/tools/create-plant.ts`, `src/tools/create-seed.ts` — drop
  `status: "active"` from payloads.
- `src/tools/get-farm-overview.ts:18`,
  `src/tools/system-health.ts:46,220`,
  `src/tools/query-sections.ts:39` — pass through to helper.
- Test fixtures
  (`src/__tests__/fixtures.ts`,
  `src/__tests__/farmos-client.test.ts`,
  `src/__tests__/tools-write.test.ts`) — same dual-version
  parameterisation as Python.

**Scripts (single-version: when run, the operator picks the version):**
- `scripts/export_farmos.py`,
  `scripts/cleanup_nursery.py`,
  `scripts/generate_nursery_pages.py`,
  `scripts/import_p1.py`,
  `scripts/import_nursery.py`,
  `scripts/import_seed_bank.py`,
  `scripts/import_fieldsheets.py`,
  `scripts/cleanup/cleanup_i5_plant_type_references.py`
  — all read the same `FARMOS_API_VERSION` env var. Pre-cutover runs
  default to v3; post-cutover runs default to v4.

**Docs:**
- `CLAUDE.md:109` — note the version flag, update example.
- `docs/farmos/api-reference.md` — replace `filter[status]=active`
  examples with v4 syntax + a "v3 legacy" note.
- `knowledge/farm_growth.yaml`, `knowledge/farm_ontology.yaml` — mention
  archived semantics now derived from `archived: bool`.

**Railway / env:**
- Add `FARMOS_API_VERSION` env var on the Railway service — set to `"3"`
  pre-cutover, flipped to `"4"` after Mike confirms v4 is live.

Cutover sequence is defined in
`claude-docs/plan-2026-04-22-v4-migration-bundle.md`.

## Open questions

- **Cleanup PR timing.** ~~Agnes to decide~~ — **confirmed 2026-05-04**
  (one stable week post-cutover). Track as a follow-up issue: "Remove
  v3 dual-path code; FARMOS_API_VERSION flag retired."
- **Mike's confirmation on `farm_api_oauth`.** Reply sent 2026-04-21
  asking him to confirm both `farm_api` + `farm_api_oauth` modules will
  stay enabled and the existing `farm` OAuth client + keys will be
  preserved. Awaiting his response. If keys change, we re-issue OAuth
  credentials to all 4 users before the cutover; the flag doesn't help
  with that.
- **Taxonomy `filter[status]=1` in `scripts/export_farmos.py:387`** — that's
  the Drupal entity-published flag on taxonomy terms, NOT the asset
  status base field. Confirmed unaffected by `#986`. Leave as-is.
