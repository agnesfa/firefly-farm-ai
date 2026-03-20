# Phase 1b Plan: Remote MCP Server on FA Framework

> **Goal:** Replace 4 local STDIO Python MCP servers with 1 centrally deployed HTTP TypeScript server
> **Deadline:** Saturday March 21, 2026 (Claire & Olivier departure — laptops must be updated before they leave)
> **Framework:** Firefly Agents MCP Server Framework (v1.0.0-beta.0)
> **Deploy target:** Railway ($5/month Hobby plan)
>
> **Updated March 19, 2026 (evening):**
> - **TypeScript port COMPLETE**: All 29 tools built, 82 tests passing, build clean
> - Tool count: 22 → **29** (added get_all_plant_types, archive_plant, 4 knowledge tools, get_farm_overview, regenerate_pages, hello)
> - Clients: 5 total — FarmOSClient (native fetch, OAuth2) + 4 Apps Script clients (AxiosHttpClient via shared base)
> - **Client architecture validated**: AppsScriptClient base class uses framework's AxiosHttpClient; FarmOSClient uses native fetch (OAuth2 state + pagination dedup). Lesley confirmed pattern is correct.
> - Knowledge tools have `topics` parameter (multi-value farm domain field)
> - New env vars needed: `KNOWLEDGE_ENDPOINT`, `OBSERVE_ENDPOINT`, `MEMORY_ENDPOINT`, `PLANT_TYPES_ENDPOINT`
> - All 4 users confirmed: Agnes (macOS), James (macOS), Claire (Windows), Olivier (Windows)
> - **Remaining**: Railway deployment (Steps 11-13), client config updates

---

## 1. WHY FA FRAMEWORK (not raw FastMCP Python)

| Factor | FastMCP Python | FA Framework |
|--------|---------------|--------------|
| Transport | STDIO → need `mcp-remote` bridge for HTTP | Native HTTP (StreamableHTTP + SSE) |
| Auth | Manual `StaticTokenVerifier` setup | Built-in credentials.json per-tenant |
| Deployment | Manual Dockerfile | Production Dockerfile included |
| Health checks | Custom route needed | 3-tier built-in (/health, /live, /ready) |
| Session mgmt | Manual | Framework handles transport-per-session |
| Client machines | Python 3.13 + venv + 8 files each | Just Claude Desktop config (Node.js for mcp-remote OR native connector) |
| Dogfooding | Uses competitor framework | Uses OUR framework — proves it works |

**Strategic value:** Second real deployment after Fluent Commerce. Proves the framework handles diverse domains.

---

## 2. ARCHITECTURE

```
┌─────────────────────────────────────────────────────┐
│                    Railway                           │
│  ┌───────────────────────────────────────────────┐  │
│  │  FA MCP Server (Node.js 20)                   │  │
│  │                                               │  │
│  │  apps/farm-server/     ← Entry point          │  │
│  │  plugins/farm-plugin/  ← 22 tools             │  │
│  │    src/clients/        ← farmOS, Sheet clients │  │
│  │    src/tools/          ← One file per tool     │  │
│  │    src/helpers/        ← Shared utilities      │  │
│  │                                               │  │
│  │  /mcp      ← StreamableHTTP endpoint          │  │
│  │  /mcp/sse  ← SSE fallback endpoint            │  │
│  │  /health   ← Railway health checks            │  │
│  │                                               │  │
│  │  secrets/credentials.json ← Per-user API keys  │  │
│  └───────────────────────────────────────────────┘  │
│         │              │            │               │
│    OAuth2 to      HTTP to       HTTP to             │
│    farmOS         Apps Script   Apps Script          │
└─────────┼──────────────┼────────────┼───────────────┘
          ▼              ▼            ▼
   margregen.        Observation   Team Memory
   farmos.net        Sheet         Sheet
                     + Plant Types Sheet

┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│  Agnes   │  │  Claire  │  │  James   │  │ Olivier  │
│  macOS   │  │ Windows  │  │  macOS   │  │ Windows  │
│          │  │          │  │          │  │          │
│ Claude   │  │ Claude   │  │ Claude   │  │ Claude   │
│ Desktop  │  │ Desktop  │  │ Desktop  │  │ Desktop  │
│    ↓     │  │    ↓     │  │    ↓     │  │    ↓     │
│ mcp-     │  │ mcp-     │  │ mcp-     │  │ mcp-     │
│ remote   │  │ remote   │  │ remote   │  │ remote   │
│    ↓     │  │    ↓     │  │    ↓     │  │    ↓     │
│ Railway  │  │ Railway  │  │ Railway  │  │ Railway  │
│ endpoint │  │ endpoint │  │ endpoint │  │ endpoint │
└──────────┘  └──────────┘  └──────────┘  └──────────┘
```

### Client Config (all 4 users)

```json
{
  "mcpServers": {
    "farmos": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote@latest",
        "https://farm-mcp.up.railway.app/mcp",
        "--header", "Authorization:Bearer ${MCP_API_KEY}"
      ],
      "env": {
        "MCP_API_KEY": "<user-specific-api-key>"
      }
    }
  }
}
```

**Prerequisites per machine:** Node.js 18+ (for npx). No Python, no venv, no file copying.

### Credentials File (on Railway)

```json
{
  "tenants": {
    "agnes": {
      "apiKey": "<generated-key>",
      "platform": "farmos",
      "metadata": {
        "farmUrl": "https://margregen.farmos.net",
        "userName": "Agnes",
        "role": "admin"
      },
      "credentials": {
        "username": "<farmos-user>",
        "password": "<farmos-pass>"
      }
    },
    "claire": {
      "apiKey": "<generated-key>",
      "platform": "farmos",
      "metadata": {
        "farmUrl": "https://margregen.farmos.net",
        "userName": "Claire",
        "role": "manager"
      },
      "credentials": {
        "username": "<farmos-user>",
        "password": "<farmos-pass>"
      }
    },
    "james": { "..." : "same pattern" },
    "olivier": { "..." : "same pattern" }
  }
}
```

**Key insight:** All users share the same farmOS credentials (single API account), but each has their own MCP API key. The `metadata.userName` identifies who's calling — tools can use this for session summaries and audit trails.

---

## 3. FILE STRUCTURE (Target)

```
fa-farm-mcp-server/
├── packed-deps/                          # Framework packages (unchanged)
├── apps/farm-server/
│   ├── src/
│   │   ├── index.ts                      # Entry point (unchanged from template)
│   │   └── tools/index.ts                # Empty (all tools in plugin)
│   ├── package.json
│   └── tsconfig.json
├── plugins/farm-plugin/
│   ├── src/
│   │   ├── index.ts                      # Plugin factory (unchanged from template)
│   │   ├── clients/                      # HTTP clients
│   │   │   ├── farmos-client.ts          # farmOS JSON:API + OAuth2 (port of farmos_client.py)
│   │   │   ├── observe-client.ts         # Observation Sheet (port of observe_client.py)
│   │   │   ├── memory-client.ts          # Team Memory Sheet (port of memory_client.py)
│   │   │   ├── plant-types-client.ts     # Plant Types Sheet (port of plant_types_client.py)
│   │   │   └── knowledge-client.ts      # Knowledge Base Sheet (port of knowledge_client.py)
│   │   ├── helpers/
│   │   │   ├── dates.ts                  # parse_date, format_planted_label, format_timestamp
│   │   │   ├── formatters.ts             # format_plant_asset, format_log, format_plant_type
│   │   │   ├── names.ts                  # build_asset_name, name parsing
│   │   │   ├── plant-type-metadata.ts    # build/parse plant type descriptions
│   │   │   └── index.ts                  # Barrel export
│   │   ├── tools/
│   │   │   ├── index.ts                  # Barrel: farmTools = [all 27 tools]
│   │   │   │
│   │   │   │── # READ TOOLS (7)
│   │   │   ├── query-plants.ts
│   │   │   ├── query-sections.ts
│   │   │   ├── get-plant-detail.ts
│   │   │   ├── query-logs.ts
│   │   │   ├── get-inventory.ts
│   │   │   ├── search-plant-types.ts
│   │   │   ├── get-all-plant-types.ts
│   │   │   │
│   │   │   │── # WRITE TOOLS (5)
│   │   │   ├── create-observation.ts
│   │   │   ├── create-activity.ts
│   │   │   ├── update-inventory.ts
│   │   │   ├── create-plant.ts
│   │   │   ├── archive-plant.ts
│   │   │   │
│   │   │   │── # OBSERVATION MANAGEMENT (3)
│   │   │   ├── list-observations.ts
│   │   │   ├── update-observation-status.ts
│   │   │   ├── import-observations.ts
│   │   │   │
│   │   │   │── # TEAM MEMORY (3)
│   │   │   ├── write-session-summary.ts
│   │   │   ├── read-team-activity.ts
│   │   │   ├── search-team-memory.ts
│   │   │   │
│   │   │   │── # PLANT TYPE MANAGEMENT (3)
│   │   │   ├── add-plant-type.ts
│   │   │   ├── update-plant-type.ts
│   │   │   ├── reconcile-plant-types.ts
│   │   │   │
│   │   │   │── # KNOWLEDGE BASE (4)
│   │   │   ├── search-knowledge.ts
│   │   │   ├── list-knowledge.ts
│   │   │   ├── add-knowledge.ts          # includes topics param
│   │   │   ├── update-knowledge.ts       # includes topics param
│   │   │   │
│   │   │   │── # OTHER (2)
│   │   │   ├── get-farm-overview.ts      # Replaces farm://overview resource
│   │   │   └── regenerate-pages.ts       # Deferred (server-only, needs git repo)
│   │   │
│   │   └── types/
│   │       ├── farmos.ts                 # farmOS JSON:API types
│   │       └── index.ts                  # Shared types
│   ├── package.json
│   └── tsconfig.json
├── secrets/
│   └── credentials.json                  # Local dev credentials (gitignored)
├── Dockerfile                            # Railway deployment (already exists)
├── package.json                          # Root workspace
└── tsconfig.json                         # Root TS config
```

---

## 4. PORTING GUIDE: PYTHON → TYPESCRIPT

### 4.1 Clients

#### FarmOSClient (farmos_client.py → clients/farmos-client.ts)

**Python OAuth2 pattern:**
```python
def connect(self):
    token_url = f"{self._hostname}/oauth/token"
    data = {"grant_type": "password", "username": ..., "password": ..., "client_id": "farm", "scope": "farm_manager"}
    response = self._session.post(token_url, data=data)
    self._session.headers["Authorization"] = f"Bearer {token}"
```

**TypeScript equivalent:**
```typescript
class FarmOSClient {
  private baseUrl: string;
  private token: string | null = null;
  private headers: Record<string, string> = {};

  constructor(private config: { farmUrl: string; username: string; password: string }) {
    this.baseUrl = config.farmUrl;
  }

  async connect(): Promise<void> {
    const response = await fetch(`${this.baseUrl}/oauth/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        grant_type: 'password',
        username: this.config.username,
        password: this.config.password,
        client_id: 'farm',
        scope: 'farm_manager',
      }),
    });
    const data = await response.json();
    this.token = data.access_token;
    this.headers = {
      'Authorization': `Bearer ${this.token}`,
      'Content-Type': 'application/vnd.api+json',
      'Accept': 'application/vnd.api+json',
    };
  }
}
```

**Key difference:** In the Python version, each local process has its own client instance. In the TypeScript HTTP version, **the server is long-lived** — must handle token refresh. The Python client already detects 401/403 and reconnects, so port that pattern.

**Methods to port (35 total):**
- `connect()` — OAuth2 password grant
- `_get(path)`, `_post(path, payload)`, `_patch(path, payload)` — HTTP with auth retry
- `fetch_by_name(api_path, name)` — Per-name query
- `fetch_all_paginated(api_path, filters, sort, limit)` — Offset pagination + dedup
- `fetch_filtered(api_path, filters, sort, max_results, include)` — Single-page + includes
- `_fetch_plants_contains(name_contains, status)` — CONTAINS filter pagination
- `_fetch_logs_contains(log_type, name_contains, include_quantity)` — CONTAINS filter + quantity merge
- `_merge_included_quantities(data, items)` — Quantity relationship resolution
- `get_plant_type_uuid(name)` — Cached lookup
- `get_section_uuid(section_id)` — Cached lookup
- `plant_asset_exists(name)` — Existence check
- `log_exists(name, type)` — Existence check
- `create_quantity(plant_id, count, adjustment)` — Entity creation
- `create_observation_log(...)` — Log creation with movement
- `create_activity_log(...)` — Log creation
- `create_plant_asset(...)` — Asset creation
- `get_plant_assets(section_id, species, status)` — Composite query
- `get_section_assets(row_filter)` — Section enumeration
- `get_logs(type, section, species, max)` — Composite log query
- `get_plant_type_details(name)` — Type enumeration/lookup
- `get_recent_logs(count)` — Recent logs
- `create_plant_type(name, description, ...)` — Taxonomy creation
- `update_plant_type(uuid, attributes)` — Taxonomy update
- `archive_plant(name_or_uuid)` — Asset archival
- `upload_file(entity_type, entity_id, field, filename, data, mime)` — Binary upload

#### ObservationClient (observe_client.py → clients/observe-client.ts)

Simple HTTP client — 4 methods. Straightforward port.
- `list_observations(status?, section?, observer?, date?, submission_id?)`
- `update_status(updates[])`
- `delete_imported(submission_id)`
- `get_media(submission_id)`

**Key pattern:** POST uses `Content-Type: text/plain` (avoids CORS preflight with Apps Script).

#### MemoryClient (memory_client.py → clients/memory-client.ts)

Simple HTTP client — 3 methods.
- `write_summary(user, topics, decisions, ...)`
- `read_activity(days, user?, limit)`
- `search_memory(query, days)`

#### PlantTypesClient (plant_types_client.py → clients/plant-types-client.ts)

Simple HTTP client — 5 methods.
- `list_all()`
- `search(query)`
- `add(fields)`
- `update(farmos_name, fields)`
- `get_reconcile_data()`

### 4.2 Helpers

#### dates.ts
- `AEST` timezone constant (UTC+10)
- `parseDate(dateStr)` — Multi-format date parser → Unix timestamp
- `formatPlantedLabel(dateStr)` — "2025-04-25" → "25 APR 2025"
- `formatTimestamp(unixTs)` — Unix/ISO → "YYYY-MM-DD HH:MM" in AEST

#### formatters.ts
- `formatPlantAsset(asset)` — Parse name, extract inventory, format response
- `formatLog(log)` — Parse log with quantities
- `formatPlantType(term)` — Parse with syntropic metadata
- `formatSectionFromAssets(section, plants)` — Section summary

#### names.ts
- `buildAssetName(plantedDate, farmosName, sectionId)` — "{date} - {species} - {section}"
- Name parsing with rsplit logic for species containing " - "

#### plant-type-metadata.ts
- `buildPlantTypeDescription(fields)` — Description + metadata block
- `parsePlantTypeMetadata(description)` — Reverse parse

### 4.3 Tools

Each tool becomes one `.ts` file following the Tool interface pattern. The handler receives `(params, extra)` where `extra.auth` contains the tenant's credentials.

**Auth-aware client pattern:**
```typescript
// Each tool creates/gets a client from auth context
function getFarmOSClient(extra: any): FarmOSClient {
  const auth = extra?.auth;
  if (!auth?.clientMetadata?.farmUrl || !auth?.platformCredentials) {
    throw new Error('FarmOS credentials not found in auth context');
  }
  return FarmOSClient.getInstance({
    farmUrl: auth.clientMetadata.farmUrl,
    username: auth.platformCredentials.username,
    password: auth.platformCredentials.password,
  });
}
```

**Singleton pattern:** Since all users share the same farmOS account, we can use a singleton FarmOSClient keyed by `farmUrl`. Cache it on first connection.

### 4.4 Special Considerations

#### `regenerate_pages` tool
This tool shells out to Python scripts and does git operations. On Railway, there's no git repo.
**Decision:** DEFER this tool. Mark it as "local only" — Agnes runs page regeneration from her machine. The tool returns "Pages need regeneration — run locally" on the remote server.

Future: Trigger GitHub Actions workflow via API instead.

#### `import_observations` composite tool
This is the most complex tool (~230 lines). It orchestrates:
1. Fetch observations from Sheet
2. Validate and route to 3 cases (section comment, new plant, inventory update)
3. Create farmOS entities
4. Update Sheet status
5. Delete imported rows
6. (Optional) regenerate pages

Port carefully — test each case independently.

#### Resources and Prompts
The current Python server has 5 resources and 3 prompts via FastMCP decorators.
**Decision:** The FA Framework focuses on tools. Resources and prompts are NOT directly supported by the plugin interface.
**Options:**
1. Convert resources to read-only tools (simplest, works today)
2. Add resource support to the framework (future framework enhancement)

**Recommendation:** Convert the 5 resources to tools:
- `farm://overview` → `get_farm_overview` tool
- `farm://sections/{id}` → Already covered by `query_sections` + `get_plant_detail`
- `farm://plant-types` → Already covered by `search_plant_types`
- `farm://plant-types/{name}` → Already covered by `search_plant_types`
- `farm://recent-logs` → Already covered by `query_logs`

Net: Only `get_farm_overview` needs to be added. The other 4 are redundant with existing tools.

Prompts can live in Claude Desktop project instructions instead.

---

## 5. IMPLEMENTATION STEPS (Ordered by Priority)

### Step 1: Set Up Project Structure ✅ DONE

Copied FA Framework template into `mcp-server-ts/`. Build verified.

### Step 2: Port Helpers ✅ DONE

All 4 helper modules ported with 34 unit tests:
- `helpers/dates.ts` — parseDate (7 formats), formatPlantedLabel, formatTimestamp
- `helpers/names.ts` — parseAssetName with rsplit logic for species containing " - "
- `helpers/formatters.ts` — formatPlantAsset, formatLog, formatPlantType
- `helpers/plant-type-metadata.ts` — build/parse roundtrip

### Step 3: Port FarmOS Client ✅ DONE

Native `fetch` with OAuth2, singleton pattern, pagination dedup. 18 client tests.

### Step 4: Port Apps Script Clients ✅ DONE

`AppsScriptClient` base class uses framework's `AxiosHttpClient`. 4 subclasses (~30 lines each).
Validated with Lesley — correct pattern: framework HTTP client for stateless, native fetch for stateful.

### Steps 5-9: Port All Tools ✅ DONE

29 tools across 7 categories. All build clean.

### Step 10: Test Suite ✅ DONE

**82 tests, all passing, <1.1 seconds, zero network calls.**

| Test File | Tests | Layer |
|-----------|-------|-------|
| helpers.test.ts | 34 | Pure functions (dates, names, formatters, metadata) |
| farmos-client.test.ts | 18 | HTTP client (OAuth2, pagination, entity creation) |
| tools-read.test.ts | 7 | Read tool orchestration (mock client) |
| tools-write.test.ts | 12 | Write tools + idempotency |
| import-workflow.test.ts | 11 | Composite workflow (case routing, dry run, resilience) |

### Step 11: Deploy to Railway (30 min) ⬜ NEXT

1. Create Railway project, connect GitHub repo
2. Set root directory to `mcp-server-ts/`
3. Railway auto-detects Dockerfile
4. Create Railway volume `secrets`, upload `credentials.json`
5. Set env vars: `NODE_ENV=production`, `CREDENTIALS_PATH=/app/secrets/credentials.json`
6. Deploy, verify health check

### Step 12: Generate API Keys + Update Client Configs (30 min)

```bash
# Generate 4 API keys
node -e "const c=require('crypto'); for(const u of ['Agnes','Claire','James','Olivier']) console.log(u+': '+c.randomBytes(32).toString('base64url'))"
```

Update `credentials.json` with keys, redeploy Railway.

Update Claude Desktop config on all 4 machines:
- Agnes: local (she's on the machine)
- Claire/James/Olivier: paste new config (only change is replacing entire mcpServers block)

### Step 13: Verify + Cut Over (30 min)

Test each user's connection:
1. Open Claude Desktop
2. Verify farmos tools appear
3. Run `query_sections` — should return all 37 sections
4. Run `write_session_summary` — verify user identity flows through

Once verified, the old Python `mcp-server/` on Claire/James/Olivier machines can be deleted.

---

## 6. CREDENTIAL & ENDPOINT FLOW

### Apps Script Endpoints

Currently stored as env vars on each machine. In the FA Framework, they go in the credentials file metadata:

```json
{
  "tenants": {
    "agnes": {
      "apiKey": "...",
      "platform": "farmos",
      "metadata": {
        "farmUrl": "https://margregen.farmos.net",
        "userName": "Agnes",
        "observeEndpoint": "https://script.google.com/macros/s/.../exec",
        "memoryEndpoint": "https://script.google.com/macros/s/.../exec",
        "plantTypesEndpoint": "https://script.google.com/macros/s/.../exec"
      },
      "credentials": {
        "username": "farmos-user",
        "password": "farmos-pass"
      }
    }
  }
}
```

Alternatively, since all users share the same endpoints, put them in server-level env vars on Railway (simpler):
```
OBSERVE_ENDPOINT=https://...
MEMORY_ENDPOINT=https://...
PLANT_TYPES_ENDPOINT=https://...
```

**Recommendation:** Server-level env vars for shared endpoints (simpler). Per-tenant metadata for user-specific values only (userName, role).

---

## 7. RISK ASSESSMENT

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| TypeScript port introduces bugs | Medium | Medium | Keep Python server as parallel fallback for 1 week |
| Railway cold starts (5-10s) | High | Low | Acceptable for farm usage pattern (few sessions/day) |
| farmOS OAuth token expires in long-lived server | Medium | Low | Already handled: 401 → reconnect pattern |
| `mcp-remote` npm bridge issues | Low | High | Falls back to Claude Desktop Connectors UI |
| Framework beta breaking changes | Low | Low | Pinned to 1.0.0-beta.0 tgz files (immutable) |
| Node.js install on Claire/Olivier Windows | Low | Medium | Node.js installer is simpler than Python 3.13 |

---

## 8. TIMELINE

**Total estimated effort: ~12 hours coding + testing**

| Day | Tasks | Hours |
|-----|-------|-------|
| Day 1 (today) | Steps 1-4: Project setup, helpers, all clients | 4h |
| Day 2 | Steps 5-8: All 22 tools | 5.5h |
| Day 3 | Steps 9-13: Testing, Railway deploy, client configs | 2.5h |

**Buffer:** 2 days before March 22 deadline.

---

## 9. WHAT STAYS IN PYTHON

- `mcp-server/` directory stays in repo as reference and Agnes's STDIO fallback
- All `scripts/` (export_farmos.py, generate_site.py, etc.) stay Python
- `regenerate_pages` triggered manually by Agnes from local machine
- Main project venv at root stays (for scripts)

---

## 10. POST-DEPLOYMENT

After March 22 deployment is confirmed:

1. **Delete local MCP installs** on Claire/James/Olivier machines (Python + venv + files)
2. **Update CLAUDE.md** with new architecture
3. **Update team context files** — remove "restart after file changes" instructions
4. **Monitor Railway logs** for errors, cold start times
5. **Consider:** GitHub Actions workflow for page regeneration (replace local `regenerate_pages`)
6. **Consider:** Moving `mcp-server-ts/` to its own repo or to `FA MCP Framework` org

---

## 11. DECISION LOG

| Decision | Rationale |
|----------|-----------|
| FA Framework over raw FastMCP | Strategic (dogfooding) + technical (built-in HTTP, auth, health) |
| `mcp-server-ts/` alongside `mcp-server/` | Parallel operation during transition, Agnes keeps STDIO option |
| Server-level env vars for shared endpoints | All users share same Apps Script endpoints — simpler than per-tenant |
| Per-tenant metadata for userName | Tools need to know who's calling (session summaries, audit) |
| Defer `regenerate_pages` | Needs git repo — Railway doesn't have one. Future: GitHub Actions |
| Convert resources to tools | FA Framework plugin interface doesn't support MCP resources directly |
| Native `fetch` for FarmOS, `AxiosHttpClient` for Apps Script | FarmOS needs OAuth2 state + pagination dedup (stateful); Apps Script clients are stateless → framework HTTP client fits perfectly |
| `AppsScriptClient` base class pattern | 4 clients (observe, memory, plant-types, knowledge) inherit shared GET/POST logic via framework's `AxiosHttpClient`. Zero duplication, ~30 lines per subclass |
| Keep Python mcp-server as fallback | Zero-risk transition — can revert any user to STDIO if HTTP fails |
| Stay on Farmier for farmOS hosting | $75/yr, zero ops. Self-host only when Phase 4 (farm_syntropic module) requires it |

---

## 12. FARMOS HOSTING: STAY ON FARMIER

### Decision: Do NOT self-host farmOS now

**Evaluated March 15, 2026** — Agnes asked whether to co-locate farmOS on Railway alongside the MCP server.

#### Why Stay on Farmier (margregen.farmos.net)

| Factor | Farmier | Self-hosted |
|--------|---------|-------------|
| **Cost** | $75/year (~$6.25/mo) | ~$10/mo (Railway) or ~€5/mo (Hetzner VPS) |
| **Ops burden** | Zero — automatic updates, backups, SSL | You manage everything |
| **MCP server works?** | ✅ Already working perfectly over API | ✅ Same API, different URL |
| **Custom Drupal modules** | ❌ Not supported (Farmier limitation) | ✅ Full control |
| **Database access** | ❌ No direct access | ✅ Full access |
| **File storage** | Included (extra for >5GB) | Depends on plan |

#### Why Railway is Wrong for farmOS

farmOS is a **stateful Drupal/PHP app** that needs:
- Persistent filesystem (uploaded photos, OAuth keys, config)
- Cron jobs (`drush cron` — Railway has no native cron)
- SSH access for Drupal updates (`drush updb`)
- Volume ownership quirks (Railway runs as root, Drupal expects www-data)

Railway is optimised for **stateless** Node/Python services. farmOS would fight the platform.

#### When to Self-Host (Phase 4+, Month 3+)

Self-hosting becomes necessary ONLY when we need the `farm_syntropic` Drupal module (custom fields for strata, succession, plant functions as structured data instead of description text).

**Recommended stack:** Hetzner CX22 (~€5/month, 2 vCPU, 4GB RAM, 40GB SSD) + Coolify (open-source PaaS) running farmOS Docker + PostgreSQL. Can also host the MCP server on the same box.

**Migration path:**
1. Provision Hetzner VPS, install Coolify
2. Deploy farmOS 3.x/4.x + PostgreSQL via Docker
3. Export all data from Farmier via API (extend `export_farmos.py`)
4. Import to self-hosted instance
5. Update MCP server env var to new URL
6. Install `farm_syntropic` custom module

#### Alternatives Evaluated

| Option | Verdict |
|--------|---------|
| Railway (farmOS + MCP + DB) | ❌ Poor fit — stateful PHP app, no cron, volume issues |
| DigitalOcean VPS | ✅ Works but pricier than Hetzner ($12/mo vs €5/mo) |
| Hetzner + Coolify | ✅ **Best option when time comes** — git-push deploys, auto SSL, native cron |
| Stay on Farmier | ✅ **Best option NOW** — cheapest, zero ops, good enough until Phase 4 |

### Bottom Line

**Phase 1b scope = deploy MCP server to Railway + keep farmOS on Farmier.** Revisit self-hosting when Phase 4 starts.
