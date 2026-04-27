/**
 * Client factory tests — getFarmOSClient now reads from extra.authInfo,
 * not env vars (ADR 0010). Apps Script clients still env-based.
 */

import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';

// Mock createAuthRefreshCallback so the factory doesn't need a live framework session.
vi.mock('@fireflyagents/mcp-server-core', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@fireflyagents/mcp-server-core')>();
  return {
    ...actual,
    createAuthRefreshCallback: vi.fn(() => async () => null),
  };
});

const originalEnv = { ...process.env };

const validExtra = {
  authInfo: {
    token: 'test-token-from-handler',
    clientMetadata: { farmUrl: 'https://test.farmos.net' },
  },
  sessionId: 'sess-1',
};

describe('client factory', () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    process.env = { ...originalEnv };
    vi.restoreAllMocks();
  });

  describe('getFarmOSClient', () => {
    it('returns a client when extra.authInfo has token + farmUrl', async () => {
      const { getFarmOSClient } = await import('../clients/index.js');
      const client = getFarmOSClient(validExtra);
      expect(client).toBeDefined();
      expect(client.isConnected).toBe(true);
    });

    it('throws clear error when extra is undefined', async () => {
      const { getFarmOSClient } = await import('../clients/index.js');
      expect(() => getFarmOSClient(undefined)).toThrow(/access token missing/);
    });

    it('throws clear error when authInfo is missing', async () => {
      const { getFarmOSClient } = await import('../clients/index.js');
      expect(() => getFarmOSClient({})).toThrow(/access token missing/);
    });

    it('throws clear error when token is missing', async () => {
      const { getFarmOSClient } = await import('../clients/index.js');
      const extra = { authInfo: { clientMetadata: { farmUrl: 'https://x.farmos.net' } } };
      expect(() => getFarmOSClient(extra)).toThrow(/access token missing/);
    });

    it('throws clear error when farmUrl is missing', async () => {
      const { getFarmOSClient } = await import('../clients/index.js');
      const extra = { authInfo: { token: 'tok', clientMetadata: {} } };
      expect(() => getFarmOSClient(extra)).toThrow(/farmUrl missing/);
    });

    it('throws clear error when clientMetadata is missing entirely', async () => {
      const { getFarmOSClient } = await import('../clients/index.js');
      const extra = { authInfo: { token: 'tok' } };
      expect(() => getFarmOSClient(extra)).toThrow(/farmUrl missing/);
    });

    it('does NOT use FARMOS_URL/USERNAME/PASSWORD env vars (no fallback)', async () => {
      // Even with all the legacy env vars set, factory throws because
      // extra.authInfo is empty. Confirms the env-var fallback is gone.
      process.env.FARMOS_URL = 'https://legacy.farmos.net';
      process.env.FARMOS_USERNAME = 'legacy';
      process.env.FARMOS_PASSWORD = 'legacy';

      const { getFarmOSClient } = await import('../clients/index.js');
      expect(() => getFarmOSClient({ authInfo: {} })).toThrow(/access token missing/);
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
      delete process.env.FARMOS_DEFAULT_USER;
      const { getUserName } = await import('../clients/index.js');
      const extraWrongPath = { auth: { clientMetadata: { userName: 'ShouldNotWork' } } };
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
