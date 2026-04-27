import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ExtendedAuthContext } from '@fireflyagents/mcp-server-types';
import { FarmOSPlatformAuthHandler } from './farmos-platform-auth-handler.js';

const validContext: ExtendedAuthContext = {
  apiKey: 'test-key',
  tenantId: 'tenant-1',
  clientMetadata: { farmUrl: 'https://test.farmos.net' },
  platformCredentials: {
    credentials: { username: 'alice', password: 'hunter2' },
  },
};

function mockTokenResponse(body: unknown, init: ResponseInit = { status: 200 }) {
  return vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
    new Response(JSON.stringify(body), {
      ...init,
      headers: { 'content-type': 'application/json' },
    }),
  );
}

describe('FarmOSPlatformAuthHandler', () => {
  let handler: FarmOSPlatformAuthHandler;

  beforeEach(() => {
    handler = new FarmOSPlatformAuthHandler();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('platform identifier', () => {
    it('exposes platform=farmos', () => {
      expect(handler.platform).toBe('farmos');
    });
  });

  describe('authenticate — happy path', () => {
    it('issues OAuth2 password grant and returns access_token', async () => {
      const fetchSpy = mockTokenResponse({
        access_token: 'tok_abc123',
        expires_in: 3600,
        token_type: 'Bearer',
      });

      const token = await handler.authenticate(validContext);

      expect(token).toBe('tok_abc123');
      expect(fetchSpy).toHaveBeenCalledOnce();
      const [url, init] = fetchSpy.mock.calls[0];
      expect(url).toBe('https://test.farmos.net/oauth/token');
      expect(init?.method).toBe('POST');
      expect((init?.headers as Record<string, string>)['Content-Type']).toBe(
        'application/x-www-form-urlencoded',
      );

      const body = new URLSearchParams(init?.body as string);
      expect(body.get('grant_type')).toBe('password');
      expect(body.get('client_id')).toBe('farm');
      expect(body.get('scope')).toBe('farm_manager');
      expect(body.get('username')).toBe('alice');
      expect(body.get('password')).toBe('hunter2');
    });

    it('strips trailing slashes from farmUrl', async () => {
      const fetchSpy = mockTokenResponse({ access_token: 'tok' });

      const ctx: ExtendedAuthContext = {
        ...validContext,
        clientMetadata: { farmUrl: 'https://test.farmos.net///' },
      };
      await handler.authenticate(ctx);

      expect(fetchSpy.mock.calls[0][0]).toBe('https://test.farmos.net/oauth/token');
    });

    it('uses credentials.clientId and credentials.scope when provided', async () => {
      const fetchSpy = mockTokenResponse({ access_token: 'tok' });
      const ctx: ExtendedAuthContext = {
        ...validContext,
        platformCredentials: {
          credentials: {
            username: 'alice',
            password: 'hunter2',
            clientId: 'custom-client',
            scope: 'custom_scope',
          },
        },
      };

      await handler.authenticate(ctx);

      const body = new URLSearchParams(fetchSpy.mock.calls[0][1]?.body as string);
      expect(body.get('client_id')).toBe('custom-client');
      expect(body.get('scope')).toBe('custom_scope');
    });

    it('falls back to defaults when only clientId is set', async () => {
      const fetchSpy = mockTokenResponse({ access_token: 'tok' });
      const ctx: ExtendedAuthContext = {
        ...validContext,
        platformCredentials: {
          credentials: { username: 'alice', password: 'hunter2', clientId: 'custom-client' },
        },
      };

      await handler.authenticate(ctx);

      const body = new URLSearchParams(fetchSpy.mock.calls[0][1]?.body as string);
      expect(body.get('client_id')).toBe('custom-client');
      expect(body.get('scope')).toBe('farm_manager');
    });

    it('falls back to defaults when only scope is set', async () => {
      const fetchSpy = mockTokenResponse({ access_token: 'tok' });
      const ctx: ExtendedAuthContext = {
        ...validContext,
        platformCredentials: {
          credentials: { username: 'alice', password: 'hunter2', scope: 'custom_scope' },
        },
      };

      await handler.authenticate(ctx);

      const body = new URLSearchParams(fetchSpy.mock.calls[0][1]?.body as string);
      expect(body.get('client_id')).toBe('farm');
      expect(body.get('scope')).toBe('custom_scope');
    });
  });

  describe('authenticate — input validation', () => {
    it('throws when clientMetadata.farmUrl is missing', async () => {
      const ctx: ExtendedAuthContext = { ...validContext, clientMetadata: {} };
      await expect(handler.authenticate(ctx)).rejects.toThrow(/farmUrl missing/);
    });

    it('throws when platformCredentials missing entirely', async () => {
      const ctx: ExtendedAuthContext = {
        ...validContext,
        platformCredentials: undefined,
      };
      await expect(handler.authenticate(ctx)).rejects.toThrow(/username,password.*missing/);
    });

    it('throws when username missing', async () => {
      const ctx: ExtendedAuthContext = {
        ...validContext,
        platformCredentials: { credentials: { password: 'p' } },
      };
      await expect(handler.authenticate(ctx)).rejects.toThrow(/username,password.*missing/);
    });

    it('throws when password missing', async () => {
      const ctx: ExtendedAuthContext = {
        ...validContext,
        platformCredentials: { credentials: { username: 'u' } },
      };
      await expect(handler.authenticate(ctx)).rejects.toThrow(/username,password.*missing/);
    });
  });

  describe('authenticate — failure modes', () => {
    it('throws on HTTP 401 from /oauth/token (bad credentials)', async () => {
      mockTokenResponse({ error: 'invalid_grant' }, { status: 401 });

      await expect(handler.authenticate(validContext)).rejects.toThrow(/HTTP 401/);
    });

    it('throws on HTTP 500 from /oauth/token (server error)', async () => {
      mockTokenResponse({}, { status: 500 });

      await expect(handler.authenticate(validContext)).rejects.toThrow(/HTTP 500/);
    });

    it('throws when response is 200 but missing access_token field', async () => {
      mockTokenResponse({ token_type: 'Bearer', expires_in: 3600 });

      await expect(handler.authenticate(validContext)).rejects.toThrow(/missing access_token/);
    });
  });

  describe('refreshToken', () => {
    it('throws — password grant has no refresh tokens', async () => {
      await expect(handler.refreshToken('whatever')).rejects.toThrow(
        /does not support refresh tokens/,
      );
    });
  });

  describe('validateToken', () => {
    it('returns true unconditionally (framework detects 401 on real call)', async () => {
      await expect(handler.validateToken('any-token')).resolves.toBe(true);
      await expect(handler.validateToken('')).resolves.toBe(true);
    });
  });

  describe('healthCheck', () => {
    it('returns healthy', async () => {
      const result = await handler.healthCheck();
      expect(result.healthy).toBe(true);
      expect(result.details).toBeDefined();
    });
  });
});
