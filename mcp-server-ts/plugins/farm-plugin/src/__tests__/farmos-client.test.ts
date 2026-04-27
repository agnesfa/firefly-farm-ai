/**
 * FarmOSClient tests — pagination, entity creation, file upload, refresh-on-401.
 *
 * Auth is now framework-managed (ADR 0010): the client takes an accessToken
 * directly and an optional refreshAuth callback for in-flight 401 recovery.
 * OAuth2 password grant logic now lives in FarmOSPlatformAuthHandler and is
 * tested separately in apps/farm-server/src/auth/.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { FarmOSClient } from '../clients/farmos-client.js';
import { makeUuid } from './fixtures.js';

function mockResponse(data: any, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'Error',
    json: () => Promise.resolve(data),
    text: () => Promise.resolve(JSON.stringify(data)),
    headers: new Headers(),
  } as Response;
}

const baseConfig = {
  farmUrl: 'https://test.farmos.net',
  accessToken: 'test-token-initial',
};

describe('FarmOSClient', () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // ── Construction ──────────────────────────────────────────

  describe('construction', () => {
    it('throws when accessToken is missing', () => {
      expect(() => new FarmOSClient({ farmUrl: 'https://test.farmos.net', accessToken: '' })).toThrow(
        /accessToken is required/,
      );
    });

    it('strips trailing slashes from farmUrl', () => {
      const client = new FarmOSClient({
        farmUrl: 'https://test.farmos.net///',
        accessToken: 'tok',
      });
      // Trigger a fetch and inspect the URL
      fetchSpy.mockResolvedValueOnce(mockResponse({ data: [] }));
      return client.fetchByName('asset/plant', 'X').then(() => {
        const callUrl = fetchSpy.mock.calls[0][0] as string;
        expect(callUrl.startsWith('https://test.farmos.net/')).toBe(true);
        expect(callUrl.startsWith('https://test.farmos.net///')).toBe(false);
      });
    });

    it('isConnected returns true when accessToken is present', () => {
      const client = new FarmOSClient(baseConfig);
      expect(client.isConnected).toBe(true);
    });

    it('sends Bearer token in Authorization header', async () => {
      const client = new FarmOSClient(baseConfig);
      fetchSpy.mockResolvedValueOnce(mockResponse({ data: [] }));
      await client.fetchByName('asset/plant', 'X');

      const init = fetchSpy.mock.calls[0][1];
      expect(init.headers.Authorization).toBe('Bearer test-token-initial');
    });
  });

  // ── Refresh-on-401 (replaces old reconnect-on-401) ────────

  describe('refresh-on-401', () => {
    it('throws immediately on 401 when no refreshAuth callback configured', async () => {
      const client = new FarmOSClient(baseConfig);
      fetchSpy.mockResolvedValueOnce(mockResponse({}, 401));

      await expect(client.fetchByName('asset/plant', 'Test')).rejects.toThrow(
        /authentication expired.*restart your Claude session/,
      );
    });

    it('calls refreshAuth on 401 and retries with new token', async () => {
      const refreshAuth = vi.fn().mockResolvedValueOnce({
        headers: { Authorization: 'Bearer new-token-after-refresh' },
      });
      const client = new FarmOSClient({ ...baseConfig, refreshAuth });

      fetchSpy
        .mockResolvedValueOnce(mockResponse({}, 401)) // initial 401
        .mockResolvedValueOnce(mockResponse({ data: [{ id: 'a', attributes: { name: 'X' } }] })); // retry succeeds

      const result = await client.fetchByName('asset/plant', 'X');
      expect(result).toEqual([{ id: 'a', attributes: { name: 'X' } }]);
      expect(refreshAuth).toHaveBeenCalledOnce();

      // Retry request used the new token
      const retryInit = fetchSpy.mock.calls[1][1];
      expect(retryInit.headers.Authorization).toBe('Bearer new-token-after-refresh');
    });

    it('updates internal accessToken so subsequent calls use the refreshed token', async () => {
      const refreshAuth = vi.fn().mockResolvedValueOnce({
        headers: { Authorization: 'Bearer new-token-after-refresh' },
      });
      const client = new FarmOSClient({ ...baseConfig, refreshAuth });

      fetchSpy
        .mockResolvedValueOnce(mockResponse({}, 401))
        .mockResolvedValueOnce(mockResponse({ data: [] })) // first call retry
        .mockResolvedValueOnce(mockResponse({ data: [] })); // second call (no 401)

      await client.fetchByName('asset/plant', 'X');
      await client.fetchByName('asset/plant', 'Y');

      // refreshAuth called only once — second call uses cached new token
      expect(refreshAuth).toHaveBeenCalledOnce();
      // Third fetch (second call) used the new token directly
      expect(fetchSpy.mock.calls[2][1].headers.Authorization).toBe('Bearer new-token-after-refresh');
    });

    it('throws when refreshAuth returns null', async () => {
      const refreshAuth = vi.fn().mockResolvedValueOnce(null);
      const client = new FarmOSClient({ ...baseConfig, refreshAuth });
      fetchSpy.mockResolvedValueOnce(mockResponse({}, 401));

      await expect(client.fetchByName('asset/plant', 'X')).rejects.toThrow(
        /authentication expired.*restart your Claude session/,
      );
      expect(refreshAuth).toHaveBeenCalledOnce();
    });

    it('throws when refreshAuth callback itself throws', async () => {
      const refreshAuth = vi.fn().mockRejectedValueOnce(new Error('framework refresh failed'));
      const client = new FarmOSClient({ ...baseConfig, refreshAuth });
      fetchSpy.mockResolvedValueOnce(mockResponse({}, 401));

      await expect(client.fetchByName('asset/plant', 'X')).rejects.toThrow(
        /auth refresh failed.*framework refresh failed/,
      );
    });

    it('throws when retry after refresh also returns 401', async () => {
      const refreshAuth = vi.fn().mockResolvedValueOnce({
        headers: { Authorization: 'Bearer fresh-but-still-rejected' },
      });
      const client = new FarmOSClient({ ...baseConfig, refreshAuth });
      fetchSpy
        .mockResolvedValueOnce(mockResponse({}, 401))
        .mockResolvedValueOnce(mockResponse({}, 401));

      await expect(client.fetchByName('asset/plant', 'X')).rejects.toThrow(
        /authentication failed after refresh.*HTTP 401/,
      );
    });

    it('refresh-on-401 also fires inside fetchAllPaginated', async () => {
      const refreshAuth = vi.fn().mockResolvedValueOnce({
        headers: { Authorization: 'Bearer refreshed' },
      });
      const client = new FarmOSClient({ ...baseConfig, refreshAuth });
      const uuid1 = makeUuid();

      fetchSpy
        .mockResolvedValueOnce(mockResponse({}, 401)) // first paginated GET 401
        .mockResolvedValueOnce(mockResponse({ data: [{ id: uuid1, attributes: { name: 'A' } }] })) // retry succeeds
        .mockResolvedValueOnce(mockResponse({ data: [] })); // empty next page

      const result = await client.fetchAllPaginated('asset/plant');
      expect(result).toHaveLength(1);
      expect(result[0].id).toBe(uuid1);
    });

    it('tracks refresh stats', async () => {
      const refreshAuth = vi.fn().mockResolvedValueOnce({
        headers: { Authorization: 'Bearer refreshed' },
      });
      const client = new FarmOSClient({ ...baseConfig, refreshAuth });
      fetchSpy
        .mockResolvedValueOnce(mockResponse({}, 401))
        .mockResolvedValueOnce(mockResponse({ data: [] }));

      await client.fetchByName('asset/plant', 'X');

      const stats = client.getStats();
      expect(stats.refreshCount).toBe(1);
      expect(stats.refreshSuccessCount).toBe(1);
      expect(stats.refreshFailCount).toBe(0);
      expect(stats.lastRefreshAt).toBeTruthy();
    });

    it('tracks failed refresh in refreshFailCount', async () => {
      const refreshAuth = vi.fn().mockResolvedValueOnce(null);
      const client = new FarmOSClient({ ...baseConfig, refreshAuth });
      fetchSpy.mockResolvedValueOnce(mockResponse({}, 401));

      await expect(client.fetchByName('asset/plant', 'X')).rejects.toThrow();

      const stats = client.getStats();
      expect(stats.refreshCount).toBe(1);
      expect(stats.refreshSuccessCount).toBe(0);
      expect(stats.refreshFailCount).toBe(1);
    });
  });

  // ── Error handling on non-auth failures ───────────────────

  describe('error handling', () => {
    it('throws on 500 response', async () => {
      const client = new FarmOSClient(baseConfig);
      fetchSpy.mockResolvedValueOnce(mockResponse({}, 500));
      await expect(client.fetchByName('asset/plant', 'Test')).rejects.toThrow('HTTP 500');
    });

    it('throws on 422 POST', async () => {
      const client = new FarmOSClient(baseConfig);
      fetchSpy.mockResolvedValueOnce(mockResponse({ errors: [{ detail: 'Unprocessable' }] }, 422));
      await expect(client.createPlantType('Bad Type', 'desc')).rejects.toThrow('422');
    });
  });

  // ── Pagination ────────────────────────────────────────────

  describe('pagination', () => {
    it('fetches single page', async () => {
      const client = new FarmOSClient(baseConfig);
      const uuid1 = makeUuid();
      const uuid2 = makeUuid();
      fetchSpy
        .mockResolvedValueOnce(mockResponse({
          data: [{ id: uuid1, attributes: { name: 'A' } }, { id: uuid2, attributes: { name: 'B' } }],
        }))
        .mockResolvedValueOnce(mockResponse({ data: [] }));

      const result = await client.fetchAllPaginated('asset/plant');
      expect(result).toHaveLength(2);
    });

    it('deduplicates across pages', async () => {
      const client = new FarmOSClient(baseConfig);
      const uuid1 = makeUuid();
      const uuid2 = makeUuid();
      const uuid3 = makeUuid();

      fetchSpy
        .mockResolvedValueOnce(mockResponse({
          data: [{ id: uuid1, attributes: { name: 'A' } }, { id: uuid2, attributes: { name: 'B' } }],
        }))
        .mockResolvedValueOnce(mockResponse({
          data: [{ id: uuid2, attributes: { name: 'B' } }, { id: uuid3, attributes: { name: 'C' } }],
        }))
        .mockResolvedValueOnce(mockResponse({ data: [] }));

      const result = await client.fetchAllPaginated('taxonomy_term/plant_type');
      expect(result).toHaveLength(3);
      expect(new Set(result.map((r: any) => r.id)).size).toBe(3);
    });

    it('constructs CONTAINS filter URL correctly', async () => {
      const client = new FarmOSClient(baseConfig);
      fetchSpy.mockResolvedValueOnce(mockResponse({ data: [] }));
      await client.getPlantAssets('P2R3.15-21');

      const callUrl = fetchSpy.mock.calls[0][0] as string;
      expect(callUrl).toContain('filter[name][operator]=CONTAINS');
      expect(callUrl).toContain('P2R3.15-21');
      expect(callUrl).toContain('filter[status]=active');
    });

    it('uses exact species match to avoid partial matches (Strawberry bug)', async () => {
      const client = new FarmOSClient(baseConfig);
      fetchSpy
        .mockResolvedValueOnce(mockResponse({
          data: [
            { id: makeUuid(), type: 'asset--plant', attributes: { name: '25 APR 2025 - Strawberry - P2R3.15-21', status: 'active' } },
            { id: makeUuid(), type: 'asset--plant', attributes: { name: '25 APR 2025 - Guava (Strawberry) - P2R3.15-21', status: 'active' } },
          ],
        }))
        .mockResolvedValueOnce(mockResponse({ data: [] }));

      const result = await client.getPlantAssets('P2R3.15-21', 'Strawberry');
      expect(result).toHaveLength(1);
      expect(result[0].attributes.name).toContain('- Strawberry -');
      expect(result[0].attributes.name).not.toContain('Guava');
    });

    it('fetchPlantsContains uses offset pagination, not links.next', async () => {
      const client = new FarmOSClient(baseConfig);
      fetchSpy
        .mockResolvedValueOnce(mockResponse({
          data: [
            { id: makeUuid(), type: 'asset--plant', attributes: { name: 'Plant A' } },
            { id: makeUuid(), type: 'asset--plant', attributes: { name: 'Plant B' } },
          ],
          links: { next: { href: 'https://test.farmos.net/api/asset/plant?page[offset]=50' } },
        }))
        .mockResolvedValueOnce(mockResponse({
          data: [{ id: makeUuid(), type: 'asset--plant', attributes: { name: 'Plant C' } }],
          links: {},
        }))
        .mockResolvedValueOnce(mockResponse({ data: [] }));

      const result = await client.getPlantAssets('P2R3');
      expect(result).toHaveLength(3);
    });

    it('fetchPlantsContains includes stable sort=name', async () => {
      const client = new FarmOSClient(baseConfig);
      fetchSpy.mockResolvedValueOnce(mockResponse({ data: [] }));
      await client.getPlantAssets('P2R3');

      const callUrl = fetchSpy.mock.calls[0][0] as string;
      expect(callUrl).toContain('sort=name');
    });

    it('fetchPlantsContains respects maxPages safety cap', async () => {
      const client = new FarmOSClient(baseConfig);
      for (let i = 0; i < 25; i++) {
        fetchSpy.mockResolvedValueOnce(mockResponse({
          data: [{ id: makeUuid(), type: 'asset--plant', attributes: { name: `Plant ${i}` } }],
        }));
      }

      await (client as any).fetchPlantsContains('P2R3', 'active', 5);
      const plantCalls = fetchSpy.mock.calls.filter((c: any[]) => (c[0] as string).includes('asset/plant'));
      expect(plantCalls.length).toBe(5);
    });

    it('exact match handles species with dashes (Basil - Sweet)', async () => {
      const client = new FarmOSClient(baseConfig);
      fetchSpy
        .mockResolvedValueOnce(mockResponse({
          data: [
            { id: makeUuid(), type: 'asset--plant', attributes: { name: '25 APR 2025 - Basil - Sweet - P2R3.15-21', status: 'active' } },
            { id: makeUuid(), type: 'asset--plant', attributes: { name: '25 APR 2025 - Basil - Sweet (Classic) - P2R3.15-21', status: 'active' } },
          ],
        }))
        .mockResolvedValueOnce(mockResponse({ data: [] }));

      const result = await client.getPlantAssets('P2R3.15-21', 'Basil - Sweet');
      expect(result).toHaveLength(1);
      expect(result[0].attributes.name).toBe('25 APR 2025 - Basil - Sweet - P2R3.15-21');
    });
  });

  // ── Quantity merging (pure function) ──────────────────────

  describe('quantity merging', () => {
    it('merges included quantities into items', () => {
      const qtyId = makeUuid();
      const data = {
        included: [{ id: qtyId, type: 'quantity--standard', attributes: { value: { decimal: '10' } } }],
      };
      const items: any[] = [{ relationships: { quantity: { data: [{ id: qtyId }] } } }];

      FarmOSClient.mergeIncludedQuantities(data, items);
      expect(items[0]._quantities).toHaveLength(1);
      expect(items[0]._quantities[0].id).toBe(qtyId);
    });

    it('leaves items unchanged when no included data', () => {
      const items = [{ relationships: { quantity: { data: [{ id: 'missing' }] } } }];
      FarmOSClient.mergeIncludedQuantities({ included: [] }, items);
      expect(items[0]).not.toHaveProperty('_quantities');
    });
  });

  // ── Entity creation payloads ──────────────────────────────

  describe('entity creation', () => {
    it('creates quantity with correct payload', async () => {
      const client = new FarmOSClient(baseConfig);
      fetchSpy.mockResolvedValueOnce(mockResponse({ data: { id: 'new-qty-id' } }));
      const result = await client.createQuantity('plant-id-1', 5, 'reset');

      expect(result).toBe('new-qty-id');
      const body = JSON.parse(fetchSpy.mock.calls[0][1].body);
      expect(body.data.type).toBe('quantity--standard');
      expect(body.data.attributes.value.decimal).toBe('5');
      expect(body.data.attributes.measure).toBe('count');
      expect(body.data.attributes.inventory_adjustment).toBe('reset');
      expect(body.data.relationships.inventory_asset.data.id).toBe('plant-id-1');
    });

    it('creates observation log with movement', async () => {
      const client = new FarmOSClient(baseConfig);
      fetchSpy.mockResolvedValueOnce(mockResponse({ data: { id: 'obs-log-id' } }));
      await client.createObservationLog('plant-1', 'section-uuid', 'qty-1', 1714003200, 'Test Obs', 'notes');

      const body = JSON.parse(fetchSpy.mock.calls[0][1].body);
      expect(body.data.type).toBe('log--observation');
      expect(body.data.attributes.is_movement).toBe(true);
      expect(body.data.attributes.status).toBe('done');
      expect(body.data.relationships.asset.data[0].id).toBe('plant-1');
      expect(body.data.relationships.location.data[0].id).toBe('section-uuid');
      expect(body.data.relationships.quantity.data[0].id).toBe('qty-1');
    });

    it('creates plant asset', async () => {
      const client = new FarmOSClient(baseConfig);
      fetchSpy.mockResolvedValueOnce(mockResponse({ data: { id: 'new-plant-id' } }));
      await client.createPlantAsset('Test Plant', 'type-uuid-1', 'test notes');

      const body = JSON.parse(fetchSpy.mock.calls[0][1].body);
      expect(body.data.type).toBe('asset--plant');
      expect(body.data.attributes.name).toBe('Test Plant');
      expect(body.data.attributes.status).toBe('active');
      expect(body.data.relationships.plant_type.data[0].id).toBe('type-uuid-1');
    });

    it('creates plant type taxonomy term', async () => {
      const client = new FarmOSClient(baseConfig);
      fetchSpy.mockResolvedValueOnce(mockResponse({ data: { id: 'new-type-id' } }));
      await client.createPlantType('Pigeon Pea', 'A pioneer legume', 120, 30);

      const body = JSON.parse(fetchSpy.mock.calls[0][1].body);
      expect(body.data.type).toBe('taxonomy_term--plant_type');
      expect(body.data.attributes.name).toBe('Pigeon Pea');
      expect(body.data.attributes.maturity_days).toBe(120);
      expect(body.data.attributes.transplant_days).toBe(30);
    });
  });

  // ── Archive plant ─────────────────────────────────────────

  describe('archive plant', () => {
    it('archives by name (lookup then patch)', async () => {
      const client = new FarmOSClient(baseConfig);
      const uuid = makeUuid();
      fetchSpy
        .mockResolvedValueOnce(mockResponse({ data: [{ id: uuid }] }))
        .mockResolvedValueOnce(mockResponse({ data: { id: uuid, attributes: { status: 'archived' } } }));

      const result = await client.archivePlant('25 APR 2025 - Pigeon Pea - P2R2.0-3');
      expect(result.id).toBe(uuid);
    });

    it('archives by UUID (skip lookup)', async () => {
      const client = new FarmOSClient(baseConfig);
      const uuid = '12345678-1234-1234-1234-123456789012';
      fetchSpy.mockResolvedValueOnce(
        mockResponse({ data: { id: uuid, attributes: { status: 'archived' } } }),
      );

      const result = await client.archivePlant(uuid);
      expect(result.id).toBe(uuid);
      expect(fetchSpy).toHaveBeenCalledTimes(1); // patch only, no lookup
    });

    it('throws when not found by name', async () => {
      const client = new FarmOSClient(baseConfig);
      fetchSpy.mockResolvedValueOnce(mockResponse({ data: [] }));
      await expect(client.archivePlant('Nonexistent Plant')).rejects.toThrow('not found');
    });
  });

  // ── File upload ──────────────────────────────────────────
  // Regression 2026-04-21: farmOS file upload responses can return
  // {data: {...}} (dict) or {data: [{...}]} (list) depending on cardinality.
  // 2026-04-22: multi-entry list returns LAST entry (newly-uploaded file).

  describe('file upload response shapes', () => {
    it('returns id from dict-form response {data: {id}}', async () => {
      const client = new FarmOSClient(baseConfig);
      fetchSpy.mockResolvedValueOnce(
        mockResponse({ data: { id: 'file-uuid-dict', type: 'file--file' } }),
      );
      const id = await client.uploadFile(
        'log/observation', 'log-1', 'image', 'photo.jpg', new ArrayBuffer(4), 'image/jpeg',
      );
      expect(id).toBe('file-uuid-dict');
    });

    it('returns id from list-form response {data: [{id}]}', async () => {
      const client = new FarmOSClient(baseConfig);
      fetchSpy.mockResolvedValueOnce(
        mockResponse({ data: [{ id: 'file-uuid-list', type: 'file--file' }] }),
      );
      const id = await client.uploadFile(
        'log/observation', 'log-1', 'image', 'photo.jpg', new ArrayBuffer(4), 'image/jpeg',
      );
      expect(id).toBe('file-uuid-list');
    });

    it('regression 2026-04-22: multi-entry list returns LAST entry (newly-uploaded file)', async () => {
      const client = new FarmOSClient(baseConfig);
      fetchSpy.mockResolvedValueOnce(
        mockResponse({
          data: [
            { id: 'prior-file-uuid-stale-reference', type: 'file--file' },
            { id: 'newly-uploaded-file-uuid', type: 'file--file' },
          ],
        }),
      );
      const id = await client.uploadFile(
        'taxonomy_term/plant_type', 'plant-type-uuid', 'image', 'photo.jpg', new ArrayBuffer(4), 'image/jpeg',
      );
      expect(id).toBe('newly-uploaded-file-uuid');
      expect(id).not.toBe('prior-file-uuid-stale-reference');
    });

    it('returns null on empty list response {data: []}', async () => {
      const client = new FarmOSClient(baseConfig);
      fetchSpy.mockResolvedValueOnce(mockResponse({ data: [] }));
      const id = await client.uploadFile(
        'log/observation', 'log-1', 'image', 'photo.jpg', new ArrayBuffer(4), 'image/jpeg',
      );
      expect(id).toBeNull();
    });

    it('returns null on empty dict response {data: {}}', async () => {
      const client = new FarmOSClient(baseConfig);
      fetchSpy.mockResolvedValueOnce(mockResponse({ data: {} }));
      const id = await client.uploadFile(
        'log/observation', 'log-1', 'image', 'photo.jpg', new ArrayBuffer(4), 'image/jpeg',
      );
      expect(id).toBeNull();
    });

    it('throws on HTTP error status', async () => {
      const client = new FarmOSClient(baseConfig);
      fetchSpy.mockResolvedValueOnce(mockResponse({ errors: ['bad request'] }, 422));
      await expect(
        client.uploadFile('log/observation', 'log-1', 'image', 'bad.json', new ArrayBuffer(4), 'application/json'),
      ).rejects.toThrow('HTTP 422');
    });
  });

  // ── Cache ─────────────────────────────────────────────────

  describe('plant type cache', () => {
    it('caches results and avoids second fetch', async () => {
      const client = new FarmOSClient(baseConfig);
      const data = [{ id: makeUuid(), attributes: { name: 'Pigeon Pea' } }];
      fetchSpy
        .mockResolvedValueOnce(mockResponse({ data }))
        .mockResolvedValueOnce(mockResponse({ data: [] }));

      const result1 = await client.getAllPlantTypesCached();
      const callCountAfterFirst = fetchSpy.mock.calls.length;

      const result2 = await client.getAllPlantTypesCached();
      expect(result1).toEqual(result2);
      expect(fetchSpy.mock.calls.length).toBe(callCountAfterFirst);
    });
  });
});
