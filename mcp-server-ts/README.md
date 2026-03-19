# FarmOS MCP Server

An MCP (Model Context Protocol) server for FarmOS, built on the [Firefly Agents MCP Server Framework](https://github.com/fireflyagents/fa-mcp-server).

## Quick Start

```bash
# Install dependencies
npm install

# Build
npm run build

# Run in development mode
npm run dev

# The server starts at http://localhost:3000
# Use API key: dev-key-12345
```

## Project Structure

This is a TypeScript monorepo with two packages:

- **`apps/farm-server/`** — The MCP server application (entry point, config, startup)
- **`plugins/farm-plugin/`** — FarmOS tools (this is where you add new tools)

The framework is provided as pre-built packages in `packed-deps/`.

## Adding Tools

Create a new file in `plugins/farm-plugin/src/tools/` (one tool per file):

```typescript
import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';

export const myTool: Tool = {
  namespace: 'farm',
  name: 'my_tool',
  title: 'My Tool',
  description: 'What this tool does',
  paramsSchema: z.object({
    param: z.string().describe('A parameter'),
  }).shape,
  options: { readOnlyHint: true },
  handler: async ({ param }) => ({
    content: [{ type: 'text' as const, text: `Result: ${param}` }],
  }),
};
```

Then add it to `plugins/farm-plugin/src/tools/index.ts`:

```typescript
import { myTool } from './my-tool.js';
export const farmTools = [myTool, /* ...other tools */];
```

Build and run: `npm run build && npm run dev`

## Connecting to Claude Desktop

Add to `~/.claude/claude_desktop_config.json`:

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

## Deployment

A `Dockerfile` is included for Railway deployment. See `CLAUDE.md` for full deployment instructions.

## Development Guide

See **`CLAUDE.md`** for comprehensive documentation including:
- Tool patterns and anatomy
- Plugin architecture
- Authentication setup
- Testing patterns
- Framework package reference
- Railway deployment guide

## Commands

| Command | Description |
|---------|-------------|
| `npm install` | Install dependencies |
| `npm run build` | Build all packages |
| `npm run dev` | Development mode (tsx) |
| `npm start` | Production mode |
| `npm run test` | Run tests |
| `npm run test:coverage` | Tests with coverage |
| `npm run type-check` | TypeScript validation |
| `npm run clean` | Remove build artifacts |
