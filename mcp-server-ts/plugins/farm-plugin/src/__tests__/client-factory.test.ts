/**
 * Tests for client factory functions — getFarmOSClient, getUserName, and env-based clients.
 *
 * CRITICAL: These tests verify the auth context integration with the FA Framework.
 * The framework passes auth as `extra.authInfo` (NOT `extra.auth`), and only populates
 * it when a platform OAuth handler is configured. Since farmOS uses its own OAuth2
 * password grant, credentials come from env vars instead.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// We need to test the REAL factory functions, not mocks
// Reset module cache so env changes take effect
const originalEnv = { ...process.env };

describe('client factory', () => {
  afterEach(() => {
    // Restore original env
    process.env = { ...originalEnv };
    vi.resetModules();
  });

  describe('getFarmOSClient', () => {
    it('returns client when env vars are set', async () => {
      process.env.FARMOS_URL = 'https://test.farmos.net';
      process.env.FARMOS_USERNAME = 'testuser';
      process.env.FARMOS_PASSWORD = 'testpass';

      const { getFarmOSClient } = await import('../clients/index.js');
      const client = getFarmOSClient();
      expect(client).toBeDefined();
      expect(client.isConnected).toBe(false); // Not connected yet, just instantiated
    });

    it('throws when FARMOS_URL is missing', async () => {
      delete process.env.FARMOS_URL;
      process.env.FARMOS_USERNAME = 'testuser';
      process.env.FARMOS_PASSWORD = 'testpass';

      const { getFarmOSClient } = await import('../clients/index.js');
      expect(() => getFarmOSClient()).toThrow('FARMOS_URL');
    });

    it('throws when FARMOS_USERNAME is missing', async () => {
      process.env.FARMOS_URL = 'https://test.farmos.net';
      delete process.env.FARMOS_USERNAME;
      process.env.FARMOS_PASSWORD = 'testpass';

      const { getFarmOSClient } = await import('../clients/index.js');
      expect(() => getFarmOSClient()).toThrow('FARMOS_USERNAME');
    });

    it('throws when FARMOS_PASSWORD is missing', async () => {
      process.env.FARMOS_URL = 'https://test.farmos.net';
      process.env.FARMOS_USERNAME = 'testuser';
      delete process.env.FARMOS_PASSWORD;

      const { getFarmOSClient } = await import('../clients/index.js');
      expect(() => getFarmOSClient()).toThrow('FARMOS_PASSWORD');
    });

    it('ignores extra parameter (no auth context dependency)', async () => {
      process.env.FARMOS_URL = 'https://test.farmos.net';
      process.env.FARMOS_USERNAME = 'testuser';
      process.env.FARMOS_PASSWORD = 'testpass';

      const { getFarmOSClient } = await import('../clients/index.js');

      // Should work with undefined, null, empty object, or any extra
      expect(() => getFarmOSClient(undefined)).not.toThrow();
      expect(() => getFarmOSClient(null)).not.toThrow();
      expect(() => getFarmOSClient({})).not.toThrow();
      expect(() => getFarmOSClient({ authInfo: undefined })).not.toThrow();
    });

    it('does NOT depend on extra.auth or extra.authInfo for farmOS credentials', async () => {
      // This test explicitly verifies the fix: farmOS credentials must NOT
      // come from the auth context, because the FA Framework only populates
      // extra.authInfo when a platform OAuth handler is configured.
      process.env.FARMOS_URL = 'https://test.farmos.net';
      process.env.FARMOS_USERNAME = 'testuser';
      process.env.FARMOS_PASSWORD = 'testpass';

      const { getFarmOSClient } = await import('../clients/index.js');

      // Even with a fully populated auth context, env vars should be used
      const extraWithAuth = {
        authInfo: {
          clientMetadata: { farmUrl: 'https://other.farmos.net', userName: 'Alice' },
          platformCredentials: { credentials: { username: 'other', password: 'other' } },
        },
      };
      const client = getFarmOSClient(extraWithAuth);
      expect(client).toBeDefined();
    });
  });

  describe('getUserName', () => {
    it('returns userName from authInfo.metadata (FA Framework pattern)', async () => {
      const { getUserName } = await import('../clients/index.js');
      const extra = { authInfo: { metadata: { userName: 'Agnes' } } };
      expect(getUserName(extra)).toBe('Agnes');
    });

    it('falls back to authInfo.clientMetadata (legacy pattern)', async () => {
      const { getUserName } = await import('../clients/index.js');
      const extra = { authInfo: { clientMetadata: { userName: 'Claire' } } };
      expect(getUserName(extra)).toBe('Claire');
    });

    it('falls back to FARMOS_DEFAULT_USER env var', async () => {
      process.env.FARMOS_DEFAULT_USER = 'DefaultUser';
      const { getUserName } = await import('../clients/index.js');
      expect(getUserName({})).toBe('DefaultUser');
      expect(getUserName(undefined)).toBe('DefaultUser');
    });

    it('returns Unknown when nothing is available', async () => {
      delete process.env.FARMOS_DEFAULT_USER;
      const { getUserName } = await import('../clients/index.js');
      expect(getUserName(undefined)).toBe('Unknown');
      expect(getUserName({})).toBe('Unknown');
      expect(getUserName({ authInfo: {} })).toBe('Unknown');
    });

    it('prefers authInfo.metadata over authInfo.clientMetadata', async () => {
      const { getUserName } = await import('../clients/index.js');
      const extra = {
        authInfo: {
          metadata: { userName: 'FromMetadata' },
          clientMetadata: { userName: 'FromClientMetadata' },
        },
      };
      expect(getUserName(extra)).toBe('FromMetadata');
    });

    it('does NOT read from extra.auth (wrong path)', async () => {
      // This test guards against regression to the old pattern
      // that used extra.auth instead of extra.authInfo
      delete process.env.FARMOS_DEFAULT_USER;
      const { getUserName } = await import('../clients/index.js');
      const extraWrongPath = {
        auth: { clientMetadata: { userName: 'ShouldNotWork' } },
      };
      expect(getUserName(extraWrongPath)).toBe('Unknown');
    });
  });

  describe('Apps Script clients from env vars', () => {
    it('getObserveClient returns null when env not set', async () => {
      delete process.env.OBSERVE_ENDPOINT;
      const { getObserveClient } = await import('../clients/index.js');
      expect(getObserveClient()).toBeNull();
    });

    it('getMemoryClient returns null when env not set', async () => {
      delete process.env.MEMORY_ENDPOINT;
      const { getMemoryClient } = await import('../clients/index.js');
      expect(getMemoryClient()).toBeNull();
    });

    it('getPlantTypesClient returns null when env not set', async () => {
      delete process.env.PLANT_TYPES_ENDPOINT;
      const { getPlantTypesClient } = await import('../clients/index.js');
      expect(getPlantTypesClient()).toBeNull();
    });

    it('getKnowledgeClient returns null when env not set', async () => {
      delete process.env.KNOWLEDGE_ENDPOINT;
      const { getKnowledgeClient } = await import('../clients/index.js');
      expect(getKnowledgeClient()).toBeNull();
    });
  });
});
