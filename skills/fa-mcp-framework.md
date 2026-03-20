---
name: fa-mcp-framework
description: Reference guide for building MCP servers with the Firefly Agents MCP Framework (TypeScript). Covers tool development, auth gotchas, client patterns, testing, and Railway deployment.
---

# Firefly Agents MCP Framework — Reference Guide

> Comprehensive reference for building MCP servers using the FA MCP Framework.
> Based on lessons learned building the Firefly Corner farmOS MCP server (29 tools, 82 tests).

---

## 1. Framework Architecture

### Package Structure

The framework ships as four pre-built tgz packages in `packed-deps/`:

| Package | Purpose |
|---------|---------|
| `@fireflyagents/mcp-server-core` | App config, server creation, auth, transports (StreamableHTTP + SSE), health routes |
| `@fireflyagents/mcp-server-plugin-sdk` | `ServerPlugin` interface, `Tool` type, `z` (Zod re-export), plugin builder |
| `@fireflyagents/mcp-shared-utils` | Logger (pino), `AxiosHttpClient`, env config, `StructuredResponseBuilder` |
| `@fireflyagents/mcp-server-types` | Type definitions (temporary, will merge into plugin-sdk) |

### Project Layout

```
my-mcp-server/
├── packed-deps/                    # Framework tgz packages (DO NOT MODIFY)
├── apps/
│   └── my-server/                  # The MCP server application
│       └── src/
│           ├── index.ts            # Entry point: buildAppConfig + createServerApp
│           └── tools/index.ts      # App-level tools (usually empty)
├── plugins/
│   └── my-plugin/                  # Domain tools plugin
│       └── src/
│           ├── index.ts            # Plugin factory (implements ServerPlugin)
│           ├── clients/            # API clients
│           │   └── index.ts        # Client factory functions
│           ├── tools/              # One file per tool
│           │   ├── index.ts        # Barrel export (array of all tools)
│           │   ├── hello.ts
│           │   └── query-data.ts
│           ├── helpers/            # Pure functions (parsing, formatting)
│           └── __tests__/          # Vitest tests
├── Dockerfile                      # Multi-stage build for Railway
├── docker-entrypoint.sh            # Credentials injection from env var
├── package.json                    # Root workspace config
└── tsconfig.json
```

### App Entry Point

```typescript
// apps/my-server/src/index.ts
import { buildAppConfig, createServerApp } from '@fireflyagents/mcp-server-core';
import { env } from '@fireflyagents/mcp-shared-utils';
import { createPlugin as createMyPlugin } from '@my/my-plugin';

const myPlugin = await createMyPlugin();

const appConfig = await buildAppConfig(env, {
  capabilities: {
    plugins: [myPlugin],    // Plugins providing tools
    tools: [],              // App-level tools (usually empty)
  },
  // includeDefaults: false,  // Disable framework demo tools/prompts/resources
});

const app = createServerApp(appConfig);
await app.start();
```

### Plugin Factory

```typescript
// plugins/my-plugin/src/index.ts
import type { ServerPlugin, PluginAccountConfig, Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { myTools } from './tools/index.js';

class MyPlugin implements ServerPlugin {
  getTools(): Tool[] {
    return myTools;
  }

  getAccountConfig(): PluginAccountConfig {
    return {
      accountId: 'my-domain',
      features: ['my-feature'],
      metadata: { pluginType: 'my-plugin', version: '0.1.0' },
    };
  }

  async healthCheck(): Promise<{ healthy: boolean; details?: any }> {
    return { healthy: true, details: { plugin: 'my-plugin' } };
  }
}

export async function createPlugin(): Promise<ServerPlugin> {
  return new MyPlugin();
}
```

### Build Order

The plugin must build before the app:

```bash
npm run build    # Handles order automatically via workspace scripts
npm run dev      # Development with tsx (auto-restart)
npm run test     # Vitest
```

---

## 2. Tool Development Pattern

### Complete Tool Anatomy

```typescript
// plugins/my-plugin/src/tools/query-data.ts
import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { logger as baseLogger } from '@fireflyagents/mcp-shared-utils';
import { getMyClient } from '../clients/index.js';

const logger = baseLogger.child({ context: 'my-plugin:tool:query-data' });

export const queryDataTool: Tool = {
  // Identity
  namespace: 'my',                // MCP tool name becomes my__query_data
  name: 'query_data',
  title: 'Query Data',
  description: 'What this does — LLMs read this to decide when to call the tool.',

  // Input schema — MUST pass .shape, not the Zod object itself
  paramsSchema: z.object({
    filter: z.string().optional().describe('Filter description for the LLM'),
    limit: z.number().optional().default(20).describe('Max results'),
  }).shape,

  // MCP hints
  options: {
    readOnlyHint: true,    // true = read-only, false = mutating
  },

  // Handler receives validated params + auth context
  handler: async (params, extra) => {
    const client = getMyClient(extra);
    const results = await client.query(params.filter);

    return {
      content: [{
        type: 'text' as const,
        text: JSON.stringify({ count: results.length, results }, null, 2),
      }],
    };
  },
};
```

### Registering Tools

Add to the barrel export (`tools/index.ts`):

```typescript
import { queryDataTool } from './query-data.js';
import { createItemTool } from './create-item.js';

export const myTools = [
  queryDataTool,
  createItemTool,
];

export { queryDataTool, createItemTool };
```

### Key Rules

1. **One tool per file** -- keeps things organized and testable.
2. **Import `z` from `@fireflyagents/mcp-server-plugin-sdk`** -- never `import { z } from 'zod'` directly. The framework bundles its own Zod version.
3. **Pass `.shape` to `paramsSchema`** -- the framework expects the Zod shape object, not the full schema.
4. **Use `as const` on content type** -- TypeScript needs `type: 'text' as const` for literal narrowing.
5. **Return `content` array** -- standard MCP response format, always `{ content: [{ type, text }] }`.
6. **Error responses** -- return `{ content: [...], isError: true }` for tool errors.

---

## 3. Authentication -- CRITICAL GOTCHAS

This section documents hard-won lessons about how auth works (and doesn't work) in the FA Framework.

### The Auth Context Bug

The framework passes auth context to tool handlers as `extra.authInfo`. However, **`extra.authInfo` is ONLY populated when a platform OAuth handler is configured** in the framework's auth pipeline.

If your backend does its own OAuth (like farmOS with OAuth2 password grant), the framework has no platform handler for it. Result: **`extra.authInfo` will be UNDEFINED** in tool handlers, even though the user authenticated with a valid API key.

### The Solution: Separate Credentials from Identity

```
Shared backend credentials  -->  Environment variables (FARMOS_URL, FARMOS_USERNAME, etc.)
Per-user identity           -->  credentials.json metadata (via extra.authInfo when available)
```

```typescript
// Client factory — credentials from env vars, identity from auth context
export function getMyClient(_extra?: any): MyClient {
  const url = process.env.MY_API_URL;
  const username = process.env.MY_API_USERNAME;
  const password = process.env.MY_API_PASSWORD;
  if (!url || !username || !password) {
    throw new Error('API credentials not found. Set MY_API_URL, MY_API_USERNAME, MY_API_PASSWORD env vars.');
  }
  return MyClient.getInstance({ url, username, password });
}

// User identity — falls back gracefully
export function getUserName(extra?: any): string {
  return extra?.authInfo?.metadata?.userName
    ?? extra?.authInfo?.clientMetadata?.userName
    ?? process.env.DEFAULT_USER
    ?? 'Unknown';
}
```

### extra.authInfo vs extra.auth

The framework uses `extra.authInfo` (camelCase "Info"). **NOT** `extra.auth`. If you write `extra.auth.clientMetadata`, it will always be undefined. This was a painful debugging session.

### credentials.json Structure

```json
{
  "tenants": {
    "agnes": {
      "apiKey": "agnes-unique-api-key-here",
      "platform": "farmos",
      "metadata": {
        "userName": "Agnes",
        "farmUrl": "https://myfarm.farmos.net"
      },
      "credentials": {
        "username": "api-user",
        "password": "api-password"
      }
    }
  }
}
```

The framework's `file-api-key-store.ts` maps API keys to tenant configs, which become the `ExtendedAuthContext` available as `extra.authInfo`. But only if a platform handler picks it up -- otherwise, the API key validates but `authInfo` stays empty.

### Development Key

A dev key (`dev-key-12345`) is automatically available in development. Pass via header:

```
x-api-key: dev-key-12345
```

---

## 4. Client Architecture Patterns

### When to Use Which HTTP Client

| Pattern | Use When | Example |
|---------|----------|---------|
| **Native `fetch`** | Stateful connections (OAuth2, token refresh, connection pooling), complex pagination with dedup | farmOS JSON:API client |
| **Framework `AxiosHttpClient`** | Stateless endpoints, simple GET/POST, retries/timeouts wanted | Google Apps Script endpoints |

### Singleton Pattern for Stateful Clients

```typescript
export class FarmOSClient {
  private static instances = new Map<string, FarmOSClient>();

  private constructor(private config: FarmOSConfig) {}

  static getInstance(config: FarmOSConfig): FarmOSClient {
    const key = config.farmUrl;
    let instance = FarmOSClient.instances.get(key);
    if (!instance) {
      instance = new FarmOSClient(config);
      FarmOSClient.instances.set(key, instance);
    }
    return instance;
  }
}
```

The singleton is keyed by URL so one MCP server can (in theory) talk to multiple backends. The `connect()` method handles OAuth2 password grant, and `ensureConnected()` is called before every request. On 401/403, it reconnects once automatically.

### Apps Script Base Client Pattern

Google Apps Script endpoints share identical HTTP patterns, so use an abstract base class:

```typescript
import { AxiosHttpClient, type HttpClient } from '@fireflyagents/mcp-shared-utils';

export abstract class AppsScriptClient {
  protected http: HttpClient;
  protected endpoint: string;

  constructor(endpoint: string) {
    this.endpoint = endpoint.replace(/\/+$/, '');
    this.http = new AxiosHttpClient({ baseURL: this.endpoint, timeout: 30_000 });
  }

  protected async get(params: Record<string, string>): Promise<any> {
    const qs = new URLSearchParams(params).toString();
    const resp = await this.http.get(`?${qs}`);
    return resp.data;
  }

  // CRITICAL: Use Content-Type: text/plain to avoid CORS preflight
  protected async post(payload: Record<string, any>): Promise<any> {
    const resp = await this.http.post('', JSON.stringify(payload), {
      headers: { 'Content-Type': 'text/plain' },
    });
    return resp.data;
  }
}
```

Subclasses are tiny -- they just define domain methods:

```typescript
export class ObservationClient extends AppsScriptClient {
  async listObservations(params: { status?: string; section?: string } = {}): Promise<any> {
    return this.get({ action: 'list', ...params });
  }

  async updateStatus(updates: any[]): Promise<any> {
    return this.post({ action: 'update_status', updates });
  }
}
```

### Apps Script CORS Avoidance

Google Apps Script deployed as web app returns 403 for POST requests with `Content-Type: application/json` from anonymous callers. This triggers a CORS preflight (OPTIONS request) which Apps Script doesn't handle. The fix: **always POST with `Content-Type: text/plain`** and `JSON.stringify()` the payload as the body. Apps Script's `JSON.parse(e.postData.contents)` handles this fine.

---

## 5. Testing Patterns

### 3-Layer Test Architecture

| Layer | What | How | Coverage Focus |
|-------|------|-----|----------------|
| **1. Helpers** | Pure functions (parsing, formatting) | Direct import, no mocks | Edge cases, name parsing, date formats |
| **2. Client** | HTTP interactions | `vi.mock` or dynamic `import()` with env vars | Auth, pagination, error handling |
| **3. Tools** | Tool handler orchestration | `vi.mock('../clients/index.js')` with mock client | Happy path, not-found, idempotency |

### Mocking the Client Factory

For tool tests, mock the entire client factory module:

```typescript
const mockClient = {
  fetchByName: vi.fn(),
  getSectionUuid: vi.fn(),
  getPlantTypeUuid: vi.fn(),
  createQuantity: vi.fn(),
  createObservationLog: vi.fn(),
  // ... all methods your tools call
};

vi.mock('../clients/index.js', () => ({
  getFarmOSClient: () => mockClient,
  getObserveClient: () => null,
  getMemoryClient: () => null,
  getUserName: () => 'TestUser',
}));

// Import tools AFTER vi.mock (vitest hoists mocks automatically)
import { myTool } from '../tools/my-tool.js';
```

### Dynamic Import for Env Var Tests

When testing factory functions that read `process.env`, use `vi.resetModules()` + dynamic `import()`:

```typescript
const originalEnv = { ...process.env };

afterEach(() => {
  process.env = { ...originalEnv };
  vi.resetModules();
});

it('throws when env var missing', async () => {
  delete process.env.MY_API_URL;
  const { getMyClient } = await import('../clients/index.js');
  expect(() => getMyClient()).toThrow('MY_API_URL');
});
```

### Fixture Factories

Create reusable factories for mock data, mirroring your API's response shape:

```typescript
let uuidCounter = 0;

export function makeUuid(): string {
  uuidCounter++;
  const hex = uuidCounter.toString(16).padStart(8, '0');
  return `${hex}-0000-0000-0000-000000000000`;
}

export function makePlantAsset(opts: {
  name?: string;
  uuid?: string;
  inventoryCount?: number | null;
} = {}) {
  return {
    id: opts.uuid ?? makeUuid(),
    type: 'asset--plant',
    attributes: {
      name: opts.name ?? 'Default Plant',
      status: 'active',
      inventory: opts.inventoryCount != null
        ? [{ measure: 'count', value: String(opts.inventoryCount), units: { name: 'plant' } }]
        : [],
    },
    relationships: { /* ... */ },
  };
}
```

### Parsing Results in Tests

Tool handlers return `{ content: [{ type: 'text', text: jsonString }] }`. Parse them:

```typescript
function parseResult(result: any): any {
  return JSON.parse(result.content[0].text);
}

it('creates observation', async () => {
  // ... setup mocks ...
  const result = parseResult(await myTool.handler({ count: 3 }));
  expect(result.status).toBe('created');
});
```

### Test Goals

- Zero network calls (all mocked).
- Fast execution (82 tests in <1.1s).
- Cover: happy path, not-found errors, idempotency guards, auth failures.
- Build must succeed before tests run (`vitest` needs compiled `dist/` from plugin).

---

## 6. Railway Deployment

### Dockerfile (Multi-Stage Build)

```dockerfile
# Stage 1: Build
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
COPY apps/my-server/package*.json ./apps/my-server/
COPY plugins/my-plugin/package*.json ./plugins/my-plugin/
COPY packed-deps/ ./packed-deps/
RUN npm ci --include=dev
COPY . .
RUN npm run build

# Stage 2: Runtime
FROM node:20-alpine AS runtime
RUN addgroup -g 1001 -S nodejs && adduser -S appuser -u 1001
WORKDIR /app
COPY package*.json ./
COPY apps/my-server/package*.json ./apps/my-server/
COPY plugins/my-plugin/package*.json ./plugins/my-plugin/
COPY packed-deps/ ./packed-deps/
RUN npm ci --omit=dev && npm cache clean --force
COPY --from=builder --chown=appuser:nodejs /app/plugins/my-plugin/dist ./plugins/my-plugin/dist
COPY --from=builder --chown=appuser:nodejs /app/apps/my-server/dist ./apps/my-server/dist
COPY --chown=appuser:nodejs docker-entrypoint.sh ./
RUN chown -R appuser:nodejs /app && chmod +x /app/docker-entrypoint.sh
USER appuser
EXPOSE 3010
ENV NODE_ENV=production HOST=0.0.0.0 PORT=3010
ENV CREDENTIALS_PATH=/app/secrets/credentials.json

# NO Docker HEALTHCHECK — Railway handles it natively
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["npm", "run", "--workspace=@my/my-server", "start"]
```

### Credentials Injection (docker-entrypoint.sh)

Railway doesn't support persistent volumes well. Instead, inject credentials from an env var at container start:

```bash
#!/bin/sh
if [ -n "$CREDENTIALS_JSON" ]; then
  mkdir -p /app/secrets
  echo "$CREDENTIALS_JSON" > /app/secrets/credentials.json
  echo "Credentials written from CREDENTIALS_JSON env var"
fi
exec "$@"
```

Set `CREDENTIALS_JSON` as a Railway environment variable containing the full JSON content of your credentials file.

### Framework Health Routes

The framework automatically provides:

- `GET /health` -- basic health check
- `GET /health/live` -- liveness probe
- `GET /health/ready` -- readiness probe

### MCP Endpoints

- `POST /mcp` -- StreamableHTTP transport (primary)
- `GET /mcp/sse` -- SSE transport (fallback for older clients)

### Required Environment Variables

| Variable | Value | Notes |
|----------|-------|-------|
| `NODE_ENV` | `production` | |
| `HOST` | `0.0.0.0` | Bind all interfaces |
| `PORT` | `3010` (or Railway's `$PORT`) | |
| `CREDENTIALS_PATH` | `/app/secrets/credentials.json` | |
| `CREDENTIALS_JSON` | `{"tenants":{...}}` | Full JSON, injected by entrypoint |
| Custom env vars | Per your backend | e.g., `FARMOS_URL`, `OBSERVE_ENDPOINT` |

### NO Docker HEALTHCHECK

Do NOT add a Docker `HEALTHCHECK` instruction. Railway handles health checks natively via the `/health` path. A Docker `HEALTHCHECK` can block Railway deploys because the container reports "unhealthy" during startup before the server is ready to accept connections.

### Client Configuration (Claude Desktop)

```json
{
  "mcpServers": {
    "my-server": {
      "url": "https://my-server.railway.app/mcp",
      "headers": {
        "x-api-key": "user-api-key-here"
      }
    }
  }
}
```

For machines without Node.js, use `npx mcp-remote`:

```json
{
  "mcpServers": {
    "my-server": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://my-server.railway.app/mcp",
        "--header",
        "Authorization:Bearer user-api-key-here"
      ]
    }
  }
}
```

---

## 7. Common Pitfalls (Learned the Hard Way)

### Auth Context Undefined

**Symptom**: `extra.authInfo` is undefined even though the API key is valid.
**Cause**: The framework only populates `authInfo` when a platform OAuth handler is configured.
**Fix**: Use env vars for backend credentials. Only rely on `authInfo` for user identity metadata, and always provide fallbacks.

### extra.auth vs extra.authInfo

**Symptom**: Auth data is always undefined in tool handlers.
**Cause**: You wrote `extra.auth` instead of `extra.authInfo`.
**Fix**: The framework uses `authInfo` (with capital I). Always `extra?.authInfo?.metadata`.

### HEALTHCHECK Blocking Railway Deploys

**Symptom**: Railway deploy hangs or container restarts in a loop.
**Cause**: Docker `HEALTHCHECK` instruction reports unhealthy during startup.
**Fix**: Remove all `HEALTHCHECK` instructions from Dockerfile. Railway uses its own probe on `/health`.

### farmOS API Pagination Returns Duplicates

**Symptom**: Paginated queries return fewer or more results than expected.
**Cause**: farmOS JSON:API returns duplicate entries across pages.
**Fix**: Always deduplicate by UUID:

```typescript
async fetchAllPaginated(apiPath: string): Promise<any[]> {
  const seen = new Map<string, any>();  // Key by UUID, not name
  let offset = 0;
  while (true) {
    const data = await this._get(`/api/${apiPath}?page[limit]=50&page[offset]=${offset}`);
    const items = data.data ?? [];
    if (items.length === 0) break;
    for (const item of items) {
      seen.set(item.id, item);  // Dedup by UUID
    }
    offset += 50;
  }
  return Array.from(seen.values());
}
```

### Zod Version Conflicts

**Symptom**: Type errors or runtime failures with schema validation.
**Cause**: Importing `z` from `'zod'` directly instead of from the SDK.
**Fix**: Always `import { z } from '@fireflyagents/mcp-server-plugin-sdk'`. The framework bundles a specific Zod version.

### paramsSchema Must Be .shape

**Symptom**: Tool parameters are ignored or validation errors.
**Cause**: Passing the full `z.object({...})` instead of `z.object({...}).shape`.
**Fix**: Always append `.shape`:

```typescript
paramsSchema: z.object({
  name: z.string().describe('...'),
}).shape,   // <-- .shape is required
```

### Build Must Precede Tests

**Symptom**: `vitest` fails with "Cannot find module" or "Failed to resolve entry".
**Cause**: Tests import from the compiled plugin dist, which doesn't exist yet.
**Fix**: Run `npm run build` before `npm run test`.

### Apps Script CORS Preflight Failure

**Symptom**: POST to Apps Script returns 403.
**Cause**: `Content-Type: application/json` triggers CORS preflight (OPTIONS), which Apps Script doesn't handle for anonymous callers.
**Fix**: POST with `Content-Type: text/plain` and `JSON.stringify()` the body.

### Google Workspace Account Blocks Anonymous POST

**Symptom**: Apps Script returns 403 for all anonymous POST requests.
**Cause**: Google Workspace accounts restrict web app access.
**Fix**: Deploy Apps Script from a personal Google account (e.g., gmail.com), not a Workspace account.

---

## 8. Import Patterns Quick Reference

```typescript
// In the APP (server entry point):
import { buildAppConfig, createServerApp } from '@fireflyagents/mcp-server-core';
import { env, logger } from '@fireflyagents/mcp-shared-utils';

// In the PLUGIN (tools, clients):
import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { logger, AxiosHttpClient } from '@fireflyagents/mcp-shared-utils';

// Logger with context:
const logger = baseLogger.child({ context: 'my-plugin:tool:my-tool' });

// NEVER do this:
// import { z } from 'zod';           // Wrong Zod version
// import { Tool } from 'some/path';  // Always from plugin-sdk
```

---

## 9. Checklist: Adding a New Tool

1. Create `plugins/my-plugin/src/tools/my-tool.ts` with the tool definition.
2. Add import and entry to `plugins/my-plugin/src/tools/index.ts` (barrel export).
3. If the tool needs a client, add a factory function to `clients/index.ts`.
4. Write tests in `__tests__/` -- mock the client factory with `vi.mock`.
5. `npm run build && npm run test`.
6. Test with MCP Inspector: `cd plugins/my-plugin && npx fastmcp dev ../../apps/my-server/dist/index.js`.

## 10. Checklist: New Railway Deployment

1. Ensure `Dockerfile` and `docker-entrypoint.sh` are at the repo root (or subdirectory configured in Railway).
2. No `HEALTHCHECK` in Dockerfile.
3. Set Railway env vars: `NODE_ENV`, `HOST`, `PORT`, `CREDENTIALS_PATH`, `CREDENTIALS_JSON`, plus any custom vars.
4. Set Railway root directory if the MCP server is in a subdirectory.
5. Deploy. Verify `GET /health/ready` returns 200.
6. Generate API keys for each user, add to `CREDENTIALS_JSON`.
7. Distribute Claude Desktop configs with the Railway URL and per-user API keys.
