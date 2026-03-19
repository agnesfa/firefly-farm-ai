# FarmOS MCP Server

TypeScript monorepo implementing a FarmOS MCP (Model Context Protocol) server, built on the Firefly Agents MCP Server Framework.

## Project Structure

```
fa-farm-mcp-server/
├── packed-deps/                     # Framework tgz packages (DO NOT MODIFY)
│   ├── fireflyagents-mcp-server-core-*.tgz
│   ├── fireflyagents-mcp-server-types-*.tgz   # Temporary — will be bundled into plugin-sdk in future
│   ├── fireflyagents-mcp-shared-utils-*.tgz
│   └── fireflyagents-mcp-server-plugin-sdk-*.tgz
├── apps/
│   └── farm-server/                 # The MCP server application
│       └── src/
│           ├── index.ts             # App entry point
│           └── tools/
│               └── index.ts         # App-level tools (prefer plugin instead)
├── plugins/
│   └── farm-plugin/                 # FarmOS tools plugin
│       └── src/
│           ├── index.ts             # Plugin factory
│           └── tools/
│               ├── index.ts         # Tool barrel export
│               └── hello.ts         # Example tool (one file per tool)
├── Dockerfile                       # Railway-ready multi-stage build
├── package.json                     # Root workspace config
└── tsconfig.json                    # Root TypeScript config
```

## Development Workflow

### Setup

```bash
npm install          # Install all dependencies
npm run build        # Build plugin first, then app
```

### Running

```bash
npm run dev          # Development mode with tsx (auto-restart)
npm start            # Production mode (requires build first)
```

### Testing

```bash
npm run test                     # Run all tests
npm run test:coverage            # With coverage report
npm run test -- --watch          # Watch mode
```

### Build Order

The plugin must build before the app:
1. `plugins/farm-plugin` (provides tools)
2. `apps/farm-server` (consumes the plugin)

`npm run build` handles this automatically.

## How to Add Tools

Tools go in `plugins/farm-plugin/src/tools/`. **One tool per file.**

### Step 1: Create the tool file

Create a new file like `plugins/farm-plugin/src/tools/list-assets.ts`:

```typescript
import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { logger as baseLogger } from '@fireflyagents/mcp-shared-utils';

const logger = baseLogger.child({ context: 'farm-plugin:tool:list-assets' });

const paramsSchema = z.object({
  type: z.string().optional().describe('Asset type to filter by (e.g. "animal", "plant", "equipment")'),
  limit: z.number().optional().describe('Maximum number of results to return'),
});

export const listAssetsTool: Tool = {
  namespace: 'farm',
  name: 'list_assets',
  title: 'List Farm Assets',
  description: 'List assets tracked in FarmOS, optionally filtered by type',
  paramsSchema: paramsSchema.shape,
  options: {
    readOnlyHint: true,
  },
  handler: async ({ type, limit = 20 }) => {
    logger.info('Listing assets', { type, limit });

    // TODO: Call FarmOS API here
    const assets = []; // Replace with actual API call

    return {
      content: [
        {
          type: 'text' as const,
          text: JSON.stringify({ assets, count: assets.length }, null, 2),
        },
      ],
    };
  },
};
```

### Step 2: Register in the barrel export

Add it to `plugins/farm-plugin/src/tools/index.ts`:

```typescript
import { helloTool } from './hello.js';
import { listAssetsTool } from './list-assets.js';

export const farmTools = [
  helloTool,
  listAssetsTool,
];

export { helloTool };
export { listAssetsTool };
```

### Step 3: Build and test

```bash
npm run build
npm run dev
```

That's it. The framework auto-registers all tools from the plugin.

## Tool Anatomy

Every tool follows this structure:

```typescript
import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';

export const myTool: Tool = {
  // Identity
  namespace: 'farm',              // Groups tools in MCP (farm__tool_name)
  name: 'my_tool',                // Unique name within namespace
  title: 'Human Readable Title',  // Display name
  description: 'What this tool does — be descriptive, LLMs read this',

  // Input schema - uses Zod, pass .shape (not the full object)
  paramsSchema: z.object({
    requiredParam: z.string().describe('Description for LLM'),
    optionalParam: z.number().optional().describe('Description for LLM'),
  }).shape,

  // Hints for MCP clients
  options: {
    readOnlyHint: true,    // true = read-only, false = mutating
  },

  // Handler receives validated params
  handler: async (params) => {
    // Your logic here

    return {
      content: [
        {
          type: 'text' as const,
          text: 'Response text or JSON.stringify(data, null, 2)',
        },
      ],
    };
  },
};
```

### Key Rules

- **One tool per file** — keeps things organized and testable
- **`z` import from `@fireflyagents/mcp-server-plugin-sdk`** — never import Zod directly
- **Pass `.shape` to `paramsSchema`** — the framework expects the shape object, not the Zod schema
- **Return `content` array** — standard MCP response format
- **Use `as const` on type** — TypeScript needs this for literal type narrowing

## Testing Tools

Test tool handlers directly — no need to spin up the server:

```typescript
import { describe, it, expect } from 'vitest';
import { listAssetsTool } from './list-assets.js';

describe('list-assets tool', () => {
  it('should have correct metadata', () => {
    expect(listAssetsTool.namespace).toBe('farm');
    expect(listAssetsTool.name).toBe('list_assets');
  });

  it('should return assets', async () => {
    const result = await listAssetsTool.handler({ limit: 5 });
    expect(result.content).toBeDefined();
    expect(result.content[0].type).toBe('text');
  });
});
```

## Plugin Interface

The farm plugin (`plugins/farm-plugin/src/index.ts`) implements `ServerPlugin`:

```typescript
interface ServerPlugin {
  getTools(): Tool[];
  getAccountConfig(): PluginAccountConfig;
  healthCheck(): Promise<{ healthy: boolean; details?: any }>;
}
```

To add a second plugin (e.g., for a different domain), create a new folder under `plugins/` and register it in the app's `index.ts`.

## App Entry Point

The app (`apps/farm-server/src/index.ts`) wires everything together:

```typescript
const farmPlugin = await createFarmPlugin();

const appConfig = await buildAppConfig(env, {
  capabilities: {
    tools: appTools,          // App-level tools (usually empty)
    plugins: [farmPlugin],    // Plugins providing tools
  },
});

const app = createServerApp(appConfig);
await app.start();
```

### Adding Multiple Plugins

```typescript
const farmPlugin = await createFarmPlugin();
const anotherPlugin = await createAnotherPlugin();

const appConfig = await buildAppConfig(env, {
  capabilities: {
    plugins: [farmPlugin, anotherPlugin],
  },
});
```

### Disabling Framework Defaults

By default, the framework includes demo tools/prompts/resources. To disable:

```typescript
const appConfig = await buildAppConfig(env, {
  includeDefaults: false,
  capabilities: {
    plugins: [farmPlugin],
  },
});
```

## Authentication

The framework provides file-based API key authentication out of the box.

### Development

A dev key (`dev-key-12345`) is automatically available. Pass it as a header:

```
x-api-key: dev-key-12345
```

### Production (Credentials File)

Create a `secrets/credentials.json`:

```json
{
  "tenants": {
    "my-tenant": {
      "apiKey": "your-api-key-here",
      "platform": "farmos",
      "metadata": {
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

Set `CREDENTIALS_PATH` env var to point to this file.

### Accessing Auth in Tool Handlers

Tools receive auth context via the second `extra` parameter:

```typescript
handler: async (params, extra) => {
  const authInfo = extra?.authInfo;
  if (!authInfo) {
    return {
      content: [{ type: 'text' as const, text: 'Authentication required' }],
      isError: true,
    };
  }

  // authInfo contains tenant data, metadata, credentials
  const farmUrl = authInfo.clientMetadata?.farmUrl;

  // Use credentials for API calls...
}
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `3000` | Server port |
| `LOG_LEVEL` | `info` | Logging level (debug, info, warn, error) |
| `CREDENTIALS_PATH` | `./secrets/credentials.json` | Path to credentials file |
| `NODE_ENV` | `development` | Environment mode |

## Framework Packages

These are pre-built framework packages in `packed-deps/`. Do not modify them.

| Package | Purpose |
|---------|---------|
| `@fireflyagents/mcp-server-core` | MCP server framework — app config, server creation, auth, transports, health routes |
| `@fireflyagents/mcp-shared-utils` | Logger, HTTP client, env config, schema utilities |
| `@fireflyagents/mcp-server-plugin-sdk` | Plugin SDK — `ServerPlugin` interface, `Tool` type, `z` (Zod), plugin builder |
| `@fireflyagents/mcp-server-types` | Type definitions (temporary — will be bundled into plugin-sdk in a future version) |

### Import Patterns

```typescript
// In the app (farm-server):
import { buildAppConfig, createServerApp } from '@fireflyagents/mcp-server-core';
import { env, logger } from '@fireflyagents/mcp-shared-utils';

// In the plugin (farm-plugin):
import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { logger } from '@fireflyagents/mcp-shared-utils';

// IMPORTANT: Never import Zod directly — always get it from the SDK
// import { z } from 'zod';  <-- DO NOT DO THIS
```

## Available Utilities

From `@fireflyagents/mcp-shared-utils`:

```typescript
import {
  logger,                    // Structured logger (pino-based)
  env,                       // Environment config (HOST, PORT, etc.)
  AxiosHttpClient,           // HTTP client with retry, timeout, logging
  StructuredResponseBuilder, // Build consistent tool responses
} from '@fireflyagents/mcp-shared-utils';

// Logger with context
const log = logger.child({ context: 'my-module' });
log.info('Something happened', { key: 'value' });

// HTTP client
const client = new AxiosHttpClient({ baseURL: 'https://api.example.com' });
const response = await client.get('/endpoint');

// Structured responses (for complex tools)
const result = StructuredResponseBuilder.buildResponse(data, outputSchema);
const errorResult = StructuredResponseBuilder.buildErrorResponse(error);
```

## Railway Deployment

### Setup

1. Create a new Railway project and connect this GitHub repo
2. Set Builder to **Dockerfile** (it auto-detects `Dockerfile` at root)
3. Create a Volume named `secrets` mounted at `/app/secrets`
4. Upload your `credentials.json` to the volume
5. Set environment variables:
   ```
   NODE_ENV=production
   HOST=0.0.0.0
   PORT=3010
   CREDENTIALS_PATH=/app/secrets/credentials.json
   ```

### Local Docker Testing

```bash
# Build
docker build -t farm-mcp-server .

# Run with local secrets
docker run -p 3010:3010 \
  -v $(pwd)/secrets:/app/secrets \
  -e CREDENTIALS_PATH=/app/secrets/credentials.json \
  farm-mcp-server

# Test health
curl http://localhost:3010/health/ready
```

## MCP Client Configuration

### Claude Desktop

Add to your Claude Desktop config (`~/.claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "farm": {
      "url": "http://localhost:3000/mcp",
      "headers": {
        "x-api-key": "dev-key-12345"
      }
    }
  }
}
```

### Calling Tools

The server exposes tools via MCP protocol. Tool names are `{namespace}__{name}`, e.g., `farm__hello`.

## Common Issues

### Build fails with "Cannot find module"
Run `npm run build` — the plugin must be compiled before the app can resolve it.

### "Failed to resolve entry"
Same as above — vitest needs compiled `dist/` directories. Build first.

### Zod version conflicts
Never `import { z } from 'zod'`. Always use `import { z } from '@fireflyagents/mcp-server-plugin-sdk'`.

### Port already in use
Set `PORT` env var: `PORT=3001 npm run dev`
