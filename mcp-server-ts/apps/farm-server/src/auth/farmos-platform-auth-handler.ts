/**
 * farmOS PlatformAuthHandler — performs OAuth2 password grant against farmOS
 * at session creation and returns the access token to the framework. Token
 * lifecycle (caching, expiry, reactive refresh) is owned by the framework's
 * unified session store; this handler is stateless.
 *
 * Replaces NoopPlatformAuthHandler. See ADR 0010.
 *
 * Auth flow (handled by @fireflyagents/mcp-server-core):
 *   1. API key validates → ExtendedAuthContext built from credentials.json
 *      (clientMetadata.farmUrl, platformCredentials.credentials.{username,password}).
 *   2. PlatformAuthService.authenticateOnSessionCreation calls our authenticate(),
 *      stores the returned token in UnifiedSessionStore.
 *   3. Tools receive the token via extra.authInfo.token.
 *   4. On 401 mid-session, tools wired with createAuthRefreshCallback trigger
 *      PlatformAuthService.refreshSessionToken → calls our authenticate() again.
 */

import type { PlatformAuthHandler, ExtendedAuthContext } from '@fireflyagents/mcp-server-types';
import { logger as baseLogger } from '@fireflyagents/mcp-shared-utils';

const logger = baseLogger.child({ context: 'farmos-platform-auth' });

const CONNECT_TIMEOUT_MS = 10_000;

export class FarmOSPlatformAuthHandler implements PlatformAuthHandler {
  platform = 'farmos';

  async authenticate(authContext: ExtendedAuthContext): Promise<string> {
    const farmUrl = authContext.clientMetadata?.farmUrl as string | undefined;
    const credentials = authContext.platformCredentials?.credentials as
      | { username?: string; password?: string; clientId?: string; scope?: string }
      | undefined;

    if (!farmUrl) {
      throw new Error(
        'farmOS authenticate: clientMetadata.farmUrl missing from auth context. ' +
          'Add farmUrl to the credentials.json metadata block for this tenant.',
      );
    }
    if (!credentials?.username || !credentials?.password) {
      throw new Error(
        'farmOS authenticate: platformCredentials.credentials.{username,password} missing. ' +
          'Check the credentials.json entry for this tenant.',
      );
    }

    // OAuth client_id and scope come from credentials when set (lets per-tenant
    // farmOS instances configure their own OAuth client), with sensible
    // defaults that match a stock farmOS install.
    const clientId = credentials.clientId ?? 'farm';
    const scope = credentials.scope ?? 'farm_manager';

    const baseUrl = farmUrl.replace(/\/+$/, '');
    const tokenUrl = `${baseUrl}/oauth/token`;
    const body = new URLSearchParams({
      grant_type: 'password',
      username: credentials.username,
      password: credentials.password,
      client_id: clientId,
      scope,
    });

    const resp = await fetch(tokenUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString(),
      signal: AbortSignal.timeout(CONNECT_TIMEOUT_MS),
    });

    if (!resp.ok) {
      logger.error('farmOS authenticate failed', {
        status: resp.status,
        url: baseUrl,
        tenantId: authContext.tenantId,
      });
      throw new Error(`farmOS OAuth2 authentication failed: HTTP ${resp.status}`);
    }

    const data = (await resp.json()) as { access_token?: string; expires_in?: number };
    if (!data.access_token) {
      throw new Error('farmOS OAuth2 response missing access_token field');
    }

    logger.info('farmOS authenticate succeeded', {
      url: baseUrl,
      tenantId: authContext.tenantId,
      expiresIn: data.expires_in,
    });

    return data.access_token;
  }

  /**
   * farmOS uses OAuth2 password grant; we don't persist refresh tokens.
   * The framework's reactive refresh path calls authenticate() again, not this.
   * Implemented to satisfy the interface; never actually invoked by the framework.
   */
  async refreshToken(_refreshToken: string): Promise<{ accessToken: string; expiresAt: Date }> {
    throw new Error(
      'farmOS handler does not support refresh tokens (password grant only). ' +
        'The framework re-authenticates via authenticate() instead.',
    );
  }

  /**
   * Token validation requires the farmUrl, which the framework interface does not
   * provide here. Return true unconditionally; the framework will detect invalid
   * tokens via 401 on the next real API call and trigger a re-authenticate.
   */
  async validateToken(_token: string): Promise<boolean> {
    return true;
  }

  async healthCheck(): Promise<{ healthy: boolean; details?: any }> {
    return {
      healthy: true,
      details: { note: 'farmOS auth handler — health verified per-session at authenticate()' },
    };
  }
}
