/**
 * No-op PlatformAuthHandler for the Farm MCP server.
 *
 * The framework's platform-auth-service crashes when authHandlers is empty
 * (type-cast bug: treats array as Map, crashes on undefined.authenticate()).
 * This no-op handler prevents that crash path.
 *
 * Our farmOS auth is handled inside the plugin (OAuth2 password grant
 * directly to farmOS), not through the framework's platform auth pipeline.
 * We only need this handler to satisfy the framework's assumption that
 * at least one handler exists when platformCredentials are present.
 *
 * Bug report: bug-report-platform-auth-service-null.md (2026-04-09)
 * Framework response: confirmed, fix pending (2026-04-13)
 * Remove this once the framework ships the fix.
 *
 * @see knowledge/farm_ontology.yaml — InteractionStamp reliability tracking
 */

import type { PlatformAuthHandler } from '@fireflyagents/mcp-server-types';
import { logger as baseLogger } from '@fireflyagents/mcp-shared-utils';

const logger = baseLogger.child({ context: 'noop-platform-auth' });

export class NoopPlatformAuthHandler implements PlatformAuthHandler {
  platform = 'farmos';

  async authenticate(): Promise<string> {
    logger.debug('No-op authenticate called — farmOS auth handled by plugin');
    return 'noop-token';
  }

  async refreshToken(): Promise<{ accessToken: string; expiresAt: Date }> {
    return { accessToken: 'noop-token', expiresAt: new Date(Date.now() + 86400000) };
  }

  async validateToken(): Promise<boolean> {
    return true;
  }

  async healthCheck(): Promise<{ healthy: boolean; details?: any }> {
    return { healthy: true, details: { note: 'No-op handler — farmOS auth in plugin' } };
  }
}
