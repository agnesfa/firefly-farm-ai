# Plan — farmOS v4 + framework + auth migration bundle

**Window:** 2026-04-22 → 2026-04-27
**Forcing function:** Mike Stenta upgrades `margregen.farmos.net` to farmOS v4 on **2026-04-27**.
**Authors:** Agnes, Claude
**Related:** ADR 0009 (v4 cutover), ADR 0010 (framework + auth migration), Mike's email 2026-04-04

---

## STATUS — 2026-04-27: ALL CODE SHIPPED

All three bundle items landed and deployed in a single session on 2026-04-27 (out of the planned 6-day window). Production Railway is running the v4-aware code with `FARMOS_API_VERSION=3` (byte-identical to pre-cutover behaviour, smoke-verified). When Mike's margregen v4 upgrade lands, flip the env var to `'4'` — two-line operation.

| Item | Commit(s) | State |
|---|---|---|
| Framework bump (PATCH support, 2nd refresh) | `5373d47` + later in-session refresh | Deployed |
| PlatformAuthHandler migration (ADR 0010) | `dc8bc7e` `02a88f2` `52bbcaa` `4f17f08` `fae3e55` | Deployed; smoke verified |
| v4 cutover code (ADR 0009) | `7587ccc` (TS) + `8e4059f` (Python) + `fdee24f` (docs) | Deployed; pre-flight passed on `=3` |

**Tests:** TS 317/317 + Python 352/352 = 669 across both servers.
**Cutover when Mike replies:** `echo "4" \| railway variable set FARMOS_API_VERSION --stdin` (auto-redeploy ~3min) → smoke → done. Rollback by flipping back to `"3"`.
**Cleanup PR scheduled ~2026-05-04** (one stable week post-cutover): drop dual-path code, retire flag.

---

## TL;DR

Three changes bundled into one window:

1. **farmOS v4 cutover** (ADR 0009) — runtime `FARMOS_API_VERSION` flag, dual-path code in ~6 narrow sites, ~25 sites updated downstream.
2. **MCP framework bump** (ADR 0010) — `1.0.0-beta.0` → Lesley's latest with small bug fix.
3. **PlatformAuthHandler migration** (ADR 0010) — move OAuth2 from plugin into framework session-level handler. Likely also fixes the 51s `system_health` timeout.

Python server gets only #1. TypeScript server gets all three. Mike does the actual farmOS upgrade — we coordinate around him.

## Day-by-day calendar

| Day | Work | Owner | Blocking on |
|---|---|---|---|
| **Tue 22 Apr** | Receive Lesley's framework tarballs. Drop in `mcp-server-ts/packed-deps/`, swap from `1.0.0-beta.0`. `npm install && npm run build`. Run all 252 TS tests. Fix any framework-drift breakage; document in ADR 0010 §Implementation Phase 1. | Claude | Lesley delivery (today) |
| **Wed 23 Apr** | Build `FarmOSPlatformAuthHandler`. Register in `buildAppConfig`. Refactor `FarmOSClient` to consume token from `extra.authInfo`. Retire `noop-platform-auth-handler.ts`. Adjust 31 tool files (factory absorbs most of the change). All TS tests green. | Claude | Phase 1 done |
| **Thu 24 Apr** | v4 cutover code in TS — `FARMOS_API_VERSION` env, helpers `assetStatusFilter()`, `assetArchivePayload()`, `assetStatusLabel()`. Branch the 4 pivot sites (read filter, archive PATCH, display reader, drop redundant create-status). Parameterise tests over both versions. | Claude | none |
| **Fri 25 Apr** | v4 cutover code in Python — same pattern, mirror sites. Update import scripts to read `FARMOS_API_VERSION`. Update docs (`CLAUDE.md:109`, `docs/farmos/api-reference.md`, KB YAMLs). All 309 Python tests green. | Claude | none |
| **Sat 26 Apr** | **Pre-flight.** Deploy TS to Railway with `FARMOS_API_VERSION=3`. Run `system_health()` (measure: should already be <20s if auth migration helped). Run `get_farm_overview()`. Run `python scripts/validate_observations.py --scope P2`. Manual smoke: `query_plants`, `archive_plant`, `create_plant`. Confirm zero regression vs v3. Send Mike final go-ahead. | Claude + Agnes | Mon-Fri code complete |
| **Sun 27 Apr** | **Cutover day.** Mike pings ~hours before he starts. He runs 3.5.1 → 4.0 in sequence. The moment he confirms v4 is live: flip `FARMOS_API_VERSION=4` on Railway, redeploy. Run `system_health` + `get_farm_overview` + `validate_observations.py` again. Smoke `archive_plant` + `create_plant`. Update [CLAUDE.md:109](CLAUDE.md:109) and [docs/farmos/api-reference.md](docs/farmos/api-reference.md) to drop the "v3 legacy" notes. Tag commit `farmos-v4-cutover`. | Mike + Claude + Agnes | Mike's window |

## Audit — what breaks under v4

Ground truth from grepping the codebase against the v4 changelog
(`#986` asset status removal):

### Read-path filters (will return 400 in v4)

- [mcp-server/farmos_client.py:570](mcp-server/farmos_client.py:570), `:650` — URL-string `filter[status]=`
- [mcp-server/farmos_client.py:622-625](mcp-server/farmos_client.py:622), `:636-640` — `fetch_all_paginated` filters dict
- [mcp-server/server.py:161](mcp-server/server.py:161), `:340`, `:4073` — plant-query call sites
- [mcp-server-ts/.../farmos-client.ts:504](mcp-server-ts/plugins/farm-plugin/src/clients/farmos-client.ts:504), `:530`, `:535`, `:565`
- [mcp-server-ts/.../get-farm-overview.ts:18](mcp-server-ts/plugins/farm-plugin/src/tools/get-farm-overview.ts:18)
- [mcp-server-ts/.../system-health.ts:46](mcp-server-ts/plugins/farm-plugin/src/tools/system-health.ts:46), `:220`
- [mcp-server-ts/.../query-sections.ts:39](mcp-server-ts/plugins/farm-plugin/src/tools/query-sections.ts:39)
- [scripts/export_farmos.py:187](scripts/export_farmos.py:187)
- [scripts/cleanup_nursery.py:111](scripts/cleanup_nursery.py:111)
- [scripts/generate_nursery_pages.py:230](scripts/generate_nursery_pages.py:230)

### Archive-write payload (will be rejected in v4)

- [mcp-server/farmos_client.py:1007](mcp-server/farmos_client.py:1007) (`archive_plant`)
- [mcp-server/server.py:1379](mcp-server/server.py:1379)
- [scripts/cleanup_nursery.py:140-146](scripts/cleanup_nursery.py:140)

### Create payloads with redundant `status: "active"` (drop unconditionally)

- [mcp-server/farmos_client.py:423](mcp-server/farmos_client.py:423), `:539`
- [scripts/import_p1.py:595](scripts/import_p1.py:595)
- [scripts/import_nursery.py:175](scripts/import_nursery.py:175)
- [scripts/import_seed_bank.py:128](scripts/import_seed_bank.py:128)
- [scripts/import_fieldsheets.py:148](scripts/import_fieldsheets.py:148)
- [scripts/cleanup/cleanup_i5_plant_type_references.py:128](scripts/cleanup/cleanup_i5_plant_type_references.py:128), `:217`

### Display readers (will read undefined in v4)

- [mcp-server/farmos_client.py:718](mcp-server/farmos_client.py:718), `:737`
- [mcp-server-ts/.../farmos-client.ts:591](mcp-server-ts/plugins/farm-plugin/src/clients/farmos-client.ts:591), `:601`

### Test fixtures (need dual-version)

- `mcp-server/tests/conftest.py`
- `mcp-server/tests/test_farmos_client.py`
- `mcp-server/tests/test_tools_write.py`
- `mcp-server-ts/.../fixtures.ts`
- `mcp-server-ts/.../farmos-client.test.ts`
- `mcp-server-ts/.../tools-write.test.ts`

### Documentation + KB (cosmetic, do last)

- `CLAUDE.md:109` — JSON:API filter example
- `docs/farmos/api-reference.md:57,82,155,186` — params examples
- `knowledge/farm_growth.yaml:43,80` — `Plant (status=active)` semantics
- `knowledge/farm_ontology.yaml:417,560` — `status update`, `Section (status=active)`

### Known unaffected

- `scripts/export_farmos.py:387` — `filter[status]=1` on `taxonomy_term` is the
  Drupal entity-published flag, not the asset `status` base field. Confirmed
  unaffected by `#986`.
- `is_castrated → is_sterile` — we don't use Animal assets.
- Plan model changes — we don't use Plans.
- Worker role tightening — we authenticate as owner.
- Cross-farm log validation — single-farm install.

## Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Lesley's package has API drift breaking the 252 tests | Medium | Phase 1 dedicated to fixing drift before any other work starts |
| Mike's farmOS upgrade slips beyond Apr 27 | Medium | Flag-based approach means our code stays on `flag=3` indefinitely without harm |
| Mike's upgrade fails partway, margregen ends up in mixed state | Low | Flag flips back to `3` in <2min via Railway env var |
| `farm` OAuth client / keys regenerated during upgrade | Medium | **Open question to Mike** in the reply draft. If yes, we re-issue creds before flipping flag. |
| Auth refactor breaks unrelated tools we don't smoke-test | Low-Medium | All 252 tests must pass; manual smoke covers `query_plants`, `archive_plant`, `create_plant`, `system_health`, `get_farm_overview` |
| Cutover-day code regression we missed | Low | Pre-flight Apr 26 with `flag=3` catches v3 regressions; v4 path exercised in tests |
| The `farm_api_oauth` module isn't enabled post-upgrade | Low | Mike confirms in reply; if not, we ask him to enable before flipping flag |

## Rollback plans

**Auth migration goes wrong (Apr 23):** revert the auth-handler commit on the
TS server, redeploy with `1.0.0-beta.0` framework. v4 cutover code can land
on top of either framework — auth migration is independently reversible.

**Framework bump goes wrong (Apr 22):** revert `packed-deps/` to
`1.0.0-beta.0` tarballs (still in git history). All other work blocked
until Lesley delivers a fix.

**v4 cutover goes wrong (Apr 27):** flip `FARMOS_API_VERSION=3` on Railway,
redeploy. If Mike's farmOS is already on v4, this won't work — but in that
case Mike can roll back farmOS too (the blog says 3.5.1 is the prereq, so
3.5.1 is the rollback target). Coordinate with Mike on the day.

**Lesley's package never arrives (rolling forward):** ship ADR 0009 alone
on Apr 27 (v4 cutover only). ADR 0010 deferred to a later window. Plan
collapses to just Thu/Fri/Sat/Sun rows above.

## Reply to Mike

**Sent 2026-04-21.** Confirmed Apr 27, asked about `farm_api_oauth` + key
preservation across the upgrade, requested a few hours' notice before he
starts the 3.5.1 → 4.0 sequence. Awaiting his reply.

## Cross-session coordination

The MCP inventory-write audit spawned 2026-04-21 evening (running async)
needs visibility into this plan so it doesn't merge inventory-write
changes against assumptions that v4 will invalidate. Captured in team
memory via `write_session_summary` 2026-04-21 — search for
`farmos-v4-migration` topic.

## Open items needing Agnes decision

- [ ] **Lesley package version** (today, blocking ADR 0010 Phase 0)
- [x] ~~Send Mike reply~~ — sent as drafted 2026-04-21
- [x] ~~Cleanup PR timing post-cutover~~ — confirmed **2026-05-04** (one stable week post-cutover)
- [ ] **Mike reply on `farm_api_oauth` + OAuth key preservation** — pending
