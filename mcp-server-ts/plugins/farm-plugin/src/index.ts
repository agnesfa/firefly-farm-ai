import type { ServerPlugin, PluginAccountConfig, Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { logger as baseLogger } from '@fireflyagents/mcp-shared-utils';
import { farmTools } from './tools/index.js';
import { getFarmOSClient } from './clients/index.js';

const logger = baseLogger.child({ context: 'farm-plugin' });

// Re-export tools for direct usage
export { farmTools } from './tools/index.js';

/**
 * Farm Plugin Implementation
 *
 * Provides FarmOS tools via the ServerPlugin interface.
 * Add new tools in src/tools/ (one file per tool), then register them
 * in src/tools/index.ts.
 */
class FarmPlugin implements ServerPlugin {
  getTools(): Tool[] {
    return farmTools;
  }

  getAccountConfig(): PluginAccountConfig {
    return {
      accountId: 'farm',
      features: ['farm-management'],
      metadata: {
        pluginType: 'farm-plugin',
        version: '0.1.0',
      },
    };
  }

  async healthCheck(): Promise<{ healthy: boolean; details?: Record<string, unknown> }> {
    try {
      const client = getFarmOSClient();
      await client.ensureConnected();
      const stats = client.getStats();
      return {
        healthy: true,
        details: {
          plugin: 'farm-plugin',
          version: '0.1.0',
          farmosConnected: true,
          ...stats,
          timestamp: new Date().toISOString(),
        },
      };
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      logger.warn('Health check: farmOS not connected', { error: msg });
      return {
        healthy: false,
        details: {
          plugin: 'farm-plugin',
          version: '0.1.0',
          farmosConnected: false,
          error: msg,
          timestamp: new Date().toISOString(),
        },
      };
    }
  }
}

/**
 * Factory function to create the farm plugin instance.
 */
export async function createPlugin(): Promise<ServerPlugin> {
  return new FarmPlugin();
}

export default createPlugin;
