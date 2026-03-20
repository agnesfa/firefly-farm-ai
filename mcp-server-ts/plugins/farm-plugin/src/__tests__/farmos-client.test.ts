/**
 * Layer 2: FarmOS client tests — OAuth2, pagination, entity creation.
 * Mirrors Python test_farmos_client.py (15+ tests). Mocks native fetch.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { FarmOSClient } from '../clients/farmos-client.js';
import { makeUuid } from './fixtures.js';

// Helper to create a mock Response
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

// Reset singleton between tests
function resetSingletons() {
  (FarmOSClient as any).instances = new Map();
}

const config = {
  farmUrl: 'https://test.farmos.net',
  username: 'testuser',
  password: 'testpass',
};

describe('FarmOSClient', () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    resetSingletons();
    fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // ── OAuth2 ────────────────────────────────────────────────

  describe('OAuth2', () => {
    it('connects successfully with password grant', async () => {
      fetchSpy.mockResolvedValueOnce(mockResponse({ access_token: 'test-token-123' }));
      const client = FarmOSClient.getInstance(config);
      await client.connect();
      expect(client.isConnected).toBe(true);
      expect(fetchSpy).toHaveBeenCalledWith(
        'https://test.farmos.net/oauth/token',
        expect.objectContaining({ method: 'POST' }),
      );
    });

    it('throws on auth failure', async () => {
      fetchSpy.mockResolvedValueOnce(mockResponse({ error: 'invalid_grant' }, 401));
      const client = FarmOSClient.getInstance(config);
      await expect(client.connect()).rejects.toThrow('OAuth2 authentication failed');
    });
  });

  // ── Error handling ────────────────────────────────────────

  describe('error handling', () => {
    it('reconnects on 401 GET', async () => {
      // First connect
      fetchSpy.mockResolvedValueOnce(mockResponse({ access_token: 'token1' }));
      const client = FarmOSClient.getInstance(config);
      await client.connect();

      // GET returns 401, then reconnect succeeds, retry succeeds
      fetchSpy.mockResolvedValueOnce(mockResponse({}, 401)); // first GET fails
      fetchSpy.mockResolvedValueOnce(mockResponse({ access_token: 'token2' })); // reconnect
      fetchSpy.mockResolvedValueOnce(mockResponse({ data: [] })); // retry GET

      const result = await client.fetchByName('asset/plant', 'Test');
      expect(result).toEqual([]);
    });

    it('throws on 500 response', async () => {
      fetchSpy.mockResolvedValueOnce(mockResponse({ access_token: 'token1' }));
      const client = FarmOSClient.getInstance(config);
      await client.connect();

      fetchSpy.mockResolvedValueOnce(mockResponse({}, 500));
      await expect(client.fetchByName('asset/plant', 'Test')).rejects.toThrow('HTTP 500');
    });

    it('throws on 422 POST', async () => {
      fetchSpy.mockResolvedValueOnce(mockResponse({ access_token: 'token1' }));
      const client = FarmOSClient.getInstance(config);
      await client.connect();

      fetchSpy.mockResolvedValueOnce(mockResponse({ errors: [{ detail: 'Unprocessable' }] }, 422));
      await expect(
        client.createPlantType('Bad Type', 'desc'),
      ).rejects.toThrow('422');
    });
  });

  // ── Pagination ────────────────────────────────────────────

  describe('pagination', () => {
    it('fetches single page', async () => {
      fetchSpy.mockResolvedValueOnce(mockResponse({ access_token: 'token' }));
      const client = FarmOSClient.getInstance(config);
      await client.connect();

      const uuid1 = makeUuid();
      const uuid2 = makeUuid();
      fetchSpy.mockResolvedValueOnce(mockResponse({
        data: [{ id: uuid1, attributes: { name: 'A' } }, { id: uuid2, attributes: { name: 'B' } }],
      }));
      fetchSpy.mockResolvedValueOnce(mockResponse({ data: [] }));

      const result = await client.fetchAllPaginated('asset/plant');
      expect(result).toHaveLength(2);
    });

    it('deduplicates across pages', async () => {
      fetchSpy.mockResolvedValueOnce(mockResponse({ access_token: 'token' }));
      const client = FarmOSClient.getInstance(config);
      await client.connect();

      const uuid1 = makeUuid();
      const uuid2 = makeUuid();
      const uuid3 = makeUuid();

      // Page 1: uuid1, uuid2
      fetchSpy.mockResolvedValueOnce(mockResponse({
        data: [{ id: uuid1, attributes: { name: 'A' } }, { id: uuid2, attributes: { name: 'B' } }],
      }));
      // Page 2: uuid2 (dup), uuid3
      fetchSpy.mockResolvedValueOnce(mockResponse({
        data: [{ id: uuid2, attributes: { name: 'B' } }, { id: uuid3, attributes: { name: 'C' } }],
      }));
      // Page 3: empty
      fetchSpy.mockResolvedValueOnce(mockResponse({ data: [] }));

      const result = await client.fetchAllPaginated('taxonomy_term/plant_type');
      expect(result).toHaveLength(3);
      const ids = result.map((r: any) => r.id);
      expect(new Set(ids).size).toBe(3); // no duplicates
    });

    it('constructs CONTAINS filter URL correctly', async () => {
      fetchSpy.mockResolvedValueOnce(mockResponse({ access_token: 'token' }));
      const client = FarmOSClient.getInstance(config);
      await client.connect();

      fetchSpy.mockResolvedValueOnce(mockResponse({ data: [] }));
      await client.getPlantAssets('P2R3.15-21');

      const callUrl = fetchSpy.mock.calls[1][0] as string;
      expect(callUrl).toContain('filter[name][operator]=CONTAINS');
      expect(callUrl).toContain('P2R3.15-21');
      expect(callUrl).toContain('filter[status]=active');
    });

    it('uses exact species match to avoid partial matches (Strawberry bug)', async () => {
      fetchSpy.mockResolvedValueOnce(mockResponse({ access_token: 'token' }));
      const client = FarmOSClient.getInstance(config);
      await client.connect();

      // Server CONTAINS filter returns both Strawberry and Guava (Strawberry) for section
      fetchSpy.mockResolvedValueOnce(mockResponse({
        data: [
          { id: makeUuid(), type: 'asset--plant', attributes: { name: '25 APR 2025 - Strawberry - P2R3.15-21', status: 'active' } },
          { id: makeUuid(), type: 'asset--plant', attributes: { name: '25 APR 2025 - Guava (Strawberry) - P2R3.15-21', status: 'active' } },
        ],
      }));

      const result = await client.getPlantAssets('P2R3.15-21', 'Strawberry');
      expect(result).toHaveLength(1);
      expect(result[0].attributes.name).toContain('- Strawberry -');
      expect(result[0].attributes.name).not.toContain('Guava');
    });

    it('exact match handles species with dashes (Basil - Sweet)', async () => {
      fetchSpy.mockResolvedValueOnce(mockResponse({ access_token: 'token' }));
      const client = FarmOSClient.getInstance(config);
      await client.connect();

      fetchSpy.mockResolvedValueOnce(mockResponse({
        data: [
          { id: makeUuid(), type: 'asset--plant', attributes: { name: '25 APR 2025 - Basil - Sweet - P2R3.15-21', status: 'active' } },
          { id: makeUuid(), type: 'asset--plant', attributes: { name: '25 APR 2025 - Basil - Sweet (Classic) - P2R3.15-21', status: 'active' } },
        ],
      }));

      const result = await client.getPlantAssets('P2R3.15-21', 'Basil - Sweet');
      expect(result).toHaveLength(1);
      expect(result[0].attributes.name).toBe('25 APR 2025 - Basil - Sweet - P2R3.15-21');
    });
  });

  // ── Quantity merging ──────────────────────────────────────

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
    let client: FarmOSClient;

    beforeEach(async () => {
      fetchSpy.mockResolvedValueOnce(mockResponse({ access_token: 'token' }));
      client = FarmOSClient.getInstance(config);
      await client.connect();
    });

    it('creates quantity with correct payload', async () => {
      fetchSpy.mockResolvedValueOnce(mockResponse({ data: { id: 'new-qty-id' } }));
      const result = await client.createQuantity('plant-id-1', 5, 'reset');

      expect(result).toBe('new-qty-id');
      const body = JSON.parse(fetchSpy.mock.calls[1][1].body);
      expect(body.data.type).toBe('quantity--standard');
      expect(body.data.attributes.value.decimal).toBe('5');
      expect(body.data.attributes.measure).toBe('count');
      expect(body.data.attributes.inventory_adjustment).toBe('reset');
      expect(body.data.relationships.inventory_asset.data.id).toBe('plant-id-1');
    });

    it('creates observation log with movement', async () => {
      fetchSpy.mockResolvedValueOnce(mockResponse({ data: { id: 'obs-log-id' } }));
      await client.createObservationLog('plant-1', 'section-uuid', 'qty-1', 1714003200, 'Test Obs', 'notes');

      const body = JSON.parse(fetchSpy.mock.calls[1][1].body);
      expect(body.data.type).toBe('log--observation');
      expect(body.data.attributes.is_movement).toBe(true);
      expect(body.data.attributes.status).toBe('done');
      expect(body.data.relationships.asset.data[0].id).toBe('plant-1');
      expect(body.data.relationships.location.data[0].id).toBe('section-uuid');
      expect(body.data.relationships.quantity.data[0].id).toBe('qty-1');
    });

    it('creates plant asset', async () => {
      fetchSpy.mockResolvedValueOnce(mockResponse({ data: { id: 'new-plant-id' } }));
      await client.createPlantAsset('Test Plant', 'type-uuid-1', 'test notes');

      const body = JSON.parse(fetchSpy.mock.calls[1][1].body);
      expect(body.data.type).toBe('asset--plant');
      expect(body.data.attributes.name).toBe('Test Plant');
      expect(body.data.attributes.status).toBe('active');
      expect(body.data.relationships.plant_type.data[0].id).toBe('type-uuid-1');
    });

    it('creates plant type taxonomy term', async () => {
      fetchSpy.mockResolvedValueOnce(mockResponse({ data: { id: 'new-type-id' } }));
      await client.createPlantType('Pigeon Pea', 'A pioneer legume', 120, 30);

      const body = JSON.parse(fetchSpy.mock.calls[1][1].body);
      expect(body.data.type).toBe('taxonomy_term--plant_type');
      expect(body.data.attributes.name).toBe('Pigeon Pea');
      expect(body.data.attributes.maturity_days).toBe(120);
      expect(body.data.attributes.transplant_days).toBe(30);
    });
  });

  // ── Archive plant ─────────────────────────────────────────

  describe('archive plant', () => {
    let client: FarmOSClient;

    beforeEach(async () => {
      fetchSpy.mockResolvedValueOnce(mockResponse({ access_token: 'token' }));
      client = FarmOSClient.getInstance(config);
      await client.connect();
    });

    it('archives by name (lookup then patch)', async () => {
      const uuid = makeUuid();
      fetchSpy.mockResolvedValueOnce(mockResponse({ data: [{ id: uuid }] })); // fetch_by_name
      fetchSpy.mockResolvedValueOnce(mockResponse({ data: { id: uuid, attributes: { status: 'archived' } } })); // patch

      const result = await client.archivePlant('25 APR 2025 - Pigeon Pea - P2R2.0-3');
      expect(result.id).toBe(uuid);
    });

    it('archives by UUID (skip lookup)', async () => {
      const uuid = '12345678-1234-1234-1234-123456789012';
      fetchSpy.mockResolvedValueOnce(mockResponse({ data: { id: uuid, attributes: { status: 'archived' } } }));

      const result = await client.archivePlant(uuid);
      expect(result.id).toBe(uuid);
      // Only 2 calls: connect + patch (no lookup)
      expect(fetchSpy).toHaveBeenCalledTimes(2);
    });

    it('throws when not found by name', async () => {
      fetchSpy.mockResolvedValueOnce(mockResponse({ data: [] }));
      await expect(client.archivePlant('Nonexistent Plant')).rejects.toThrow('not found');
    });
  });

  // ── Cache ─────────────────────────────────────────────────

  describe('plant type cache', () => {
    it('caches results and avoids second fetch', async () => {
      fetchSpy.mockResolvedValueOnce(mockResponse({ access_token: 'token' }));
      const client = FarmOSClient.getInstance(config);
      await client.connect();

      const data = [{ id: makeUuid(), attributes: { name: 'Pigeon Pea' } }];
      fetchSpy.mockResolvedValueOnce(mockResponse({ data }));
      fetchSpy.mockResolvedValueOnce(mockResponse({ data: [] }));

      const result1 = await client.getAllPlantTypesCached();
      const callCountAfterFirst = fetchSpy.mock.calls.length;

      const result2 = await client.getAllPlantTypesCached();
      expect(result1).toEqual(result2);
      // No additional fetch calls for second call
      expect(fetchSpy.mock.calls.length).toBe(callCountAfterFirst);
    });
  });
});
