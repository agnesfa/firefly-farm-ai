import type { ServerPlugin, PluginAccountConfig, Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { farmTools } from './tools/index.js';

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
    return {
      healthy: true,
      details: {
        plugin: 'farm-plugin',
        version: '0.1.0',
        timestamp: new Date().toISOString(),
      },
    };
  }
}

/**
 * Factory function to create the farm plugin instance.
 */
export async function createPlugin(): Promise<ServerPlugin> {
  return new FarmPlugin();
}

export default createPlugin;
