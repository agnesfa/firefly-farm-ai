#!/usr/bin/env node
/**
 * FarmOS MCP Server Application
 *
 * Uses the Firefly Agents MCP Server framework with the farm-plugin.
 */
import { AppConfig, buildAppConfig, createServerApp } from '@fireflyagents/mcp-server-core';
import { env, logger as baseLogger } from '@fireflyagents/mcp-shared-utils';
import { createPlugin as createFarmPlugin } from '@farm/farm-plugin';
import { appTools } from './tools/index.js';
import { FarmOSPlatformAuthHandler } from './auth/farmos-platform-auth-handler.js';

const logger = baseLogger.child({ context: 'farm-server:main' });

async function main() {
  try {
    logger.info('Starting FarmOS MCP Server...');

    // Create plugins
    const farmPlugin = await createFarmPlugin();

    const appConfig = await buildAppConfig(env, {
      capabilities: {
        tools: appTools,
        plugins: [farmPlugin],
        authHandlers: [new FarmOSPlatformAuthHandler()],
      },
    });

    // Create and start server
    const app = createServerApp(appConfig);
    await app.start();

    printAppInfo(appConfig);

    // Keep-alive: ping own health endpoint every 4 minutes to prevent
    // Railway from sleeping the container. Without this, cold starts
    // take ~5-10s and exceed MCP client timeouts.
    startKeepAlive(appConfig.server.port);
  } catch (error) {
    logger.error('Failed to start server', {
      error: error instanceof Error ? error.message : error,
      stack: error instanceof Error ? error.stack : undefined,
    });
    console.error('Failed to start server:', error);
    process.exit(1);
  }
}

const printAppInfo = (appConfig: AppConfig) => {
  const { host, port } = appConfig.server;

  // Collect all tools: direct + plugin-provided
  const allTools = [...(appConfig.tools || [])];
  appConfig.plugins?.forEach((plugin) => {
    const pluginTools = plugin.getTools?.() || [];
    allTools.push(...pluginTools);
  });

  console.log('-----------------------------------------------------------------------');
  console.log(' FarmOS MCP Server running!');
  console.log(`   Server URL: http://${host}:${port}`);
  console.log(`   Health URL: http://${host}:${port}/health`);
  console.log(`   StreamableHTTP MCP Endpoint: http://${host}:${port}/mcp`);
  console.log(`   SSE MCP Endpoint: http://${host}:${port}/mcp/sse`);
  console.log('');
  console.log('   Authentication: Include header x-api-key: dev-key-12345');
  console.log('');
  console.log(` Tools: (${allTools.length} total)`);
  allTools.forEach((tool) => {
    console.log(`   * ${tool.namespace}__${tool.name} - ${tool.title}`);
  });
  console.log('');
  console.log(' Press Ctrl+C to stop');
  console.log('-----------------------------------------------------------------------');
};

function startKeepAlive(port: number) {
  const INTERVAL_MS = 4 * 60 * 1000; // 4 minutes
  const url = `http://localhost:${port}/health`;

  setInterval(async () => {
    try {
      await fetch(url, { signal: AbortSignal.timeout(5_000) });
      logger.debug('Keep-alive ping sent');
    } catch {
      // Server might be restarting or slow — ignore
    }
  }, INTERVAL_MS);

  logger.info('Keep-alive enabled', { intervalMinutes: 4 });
}

main();
