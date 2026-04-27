/**
 * FarmOSClient tests — pagination, entity creation, file upload.
 *
 * Auth + reactive refresh are owned by the framework HttpClient
 * (@fireflyagents/mcp-shared-utils createHttpClient with onUnauthorized).
 * These tests mock the HttpClient interface directly; auth handler tests
 * live in apps/farm-server/src/auth/.
 */

import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import type { HttpClient, HttpResponse } from '@fireflyagents/mcp-shared-utils';
import { HttpClientError } from '@fireflyagents/mcp-shared-utils';
import { FarmOSClient } from '../clients/farmos-client.js';
import { makeUuid } from './fixtures.js';

type MockedHttpClient = {
  [K in keyof HttpClient]: Mock;
};

function makeMockHttpClient(): MockedHttpClient {
  return {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    graphql: vi.fn(),
  };
}

function ok<T = any>(data: T, status = 200): HttpResponse<T> {
  return {
    data,
    status,
    statusText: status >= 200 && status < 300 ? 'OK' : 'Error',
    headers: {},
  };
}

function err(status: number, body?: any): HttpClientError {
  return new HttpClientError(`HTTP ${status}`, status, body);
}

const baseConfig = (httpClient: HttpClient) => ({
  farmUrl: 'https://test.farmos.net',
  httpClient,
});

describe('FarmOSClient', () => {
  let mockHttp: MockedHttpClient;

  beforeEach(() => {
    mockHttp = makeMockHttpClient();
  });

  // ── Construction ──────────────────────────────────────────

  describe('construction', () => {
    it('throws when httpClient is missing', () => {
      expect(() => new FarmOSClient({ farmUrl: 'https://test.farmos.net' } as any)).toThrow(
        /httpClient is required/,
      );
    });

    it('isConnected returns true (back-compat shim)', () => {
      const client = new FarmOSClient(baseConfig(mockHttp));
      expect(client.isConnected).toBe(true);
    });
  });

  // ── Error handling (HttpClient throws HttpClientError) ────

  describe('error handling', () => {
    it('wraps HttpClientError on 500 GET into farmOS API error message', async () => {
      const client = new FarmOSClient(baseConfig(mockHttp));
      mockHttp.get.mockRejectedValueOnce(err(500));

      await expect(client.fetchByName('asset/plant', 'Test')).rejects.toThrow(/HTTP 500/);
    });

    it('wraps HttpClientError on 422 POST into farmOS POST error message', async () => {
      const client = new FarmOSClient(baseConfig(mockHttp));
      mockHttp.post.mockRejectedValueOnce(err(422, { errors: [{ detail: 'Unprocessable' }] }));

      await expect(client.createPlantType('Bad Type', 'desc')).rejects.toThrow(/422/);
    });

    it('propagates non-HTTP errors unchanged (timeout, network, etc.)', async () => {
      const client = new FarmOSClient(baseConfig(mockHttp));
      mockHttp.get.mockRejectedValueOnce(new Error('socket hang up'));

      await expect(client.fetchByName('asset/plant', 'Test')).rejects.toThrow('socket hang up');
    });
  });

  // ── Pagination ────────────────────────────────────────────

  describe('pagination', () => {
    it('fetches single page', async () => {
      const client = new FarmOSClient(baseConfig(mockHttp));
      const uuid1 = makeUuid();
      const uuid2 = makeUuid();
      mockHttp.get
        .mockResolvedValueOnce(ok({
          data: [{ id: uuid1, attributes: { name: 'A' } }, { id: uuid2, attributes: { name: 'B' } }],
        }))
        .mockResolvedValueOnce(ok({ data: [] }));

      const result = await client.fetchAllPaginated('asset/plant');
      expect(result).toHaveLength(2);
    });

    it('deduplicates across pages', async () => {
      const client = new FarmOSClient(baseConfig(mockHttp));
      const uuid1 = makeUuid();
      const uuid2 = makeUuid();
      const uuid3 = makeUuid();

      mockHttp.get
        .mockResolvedValueOnce(ok({
          data: [{ id: uuid1, attributes: { name: 'A' } }, { id: uuid2, attributes: { name: 'B' } }],
        }))
        .mockResolvedValueOnce(ok({
          data: [{ id: uuid2, attributes: { name: 'B' } }, { id: uuid3, attributes: { name: 'C' } }],
        }))
        .mockResolvedValueOnce(ok({ data: [] }));

      const result = await client.fetchAllPaginated('taxonomy_term/plant_type');
      expect(result).toHaveLength(3);
      expect(new Set(result.map((r: any) => r.id)).size).toBe(3);
    });

    it('constructs CONTAINS filter URL correctly', async () => {
      const client = new FarmOSClient(baseConfig(mockHttp));
      mockHttp.get.mockResolvedValueOnce(ok({ data: [] }));
      await client.getPlantAssets('P2R3.15-21');

      const callPath = mockHttp.get.mock.calls[0][0] as string;
      expect(callPath).toContain('filter[name][operator]=CONTAINS');
      expect(callPath).toContain('P2R3.15-21');
      expect(callPath).toContain('filter[status]=active');
    });

    it('uses exact species match to avoid partial matches (Strawberry bug)', async () => {
      const client = new FarmOSClient(baseConfig(mockHttp));
      mockHttp.get
        .mockResolvedValueOnce(ok({
          data: [
            { id: makeUuid(), type: 'asset--plant', attributes: { name: '25 APR 2025 - Strawberry - P2R3.15-21', status: 'active' } },
            { id: makeUuid(), type: 'asset--plant', attributes: { name: '25 APR 2025 - Guava (Strawberry) - P2R3.15-21', status: 'active' } },
          ],
        }))
        .mockResolvedValueOnce(ok({ data: [] }));

      const result = await client.getPlantAssets('P2R3.15-21', 'Strawberry');
      expect(result).toHaveLength(1);
      expect(result[0].attributes.name).toContain('- Strawberry -');
      expect(result[0].attributes.name).not.toContain('Guava');
    });

    it('fetchPlantsContains uses offset pagination, not links.next', async () => {
      const client = new FarmOSClient(baseConfig(mockHttp));
      mockHttp.get
        .mockResolvedValueOnce(ok({
          data: [
            { id: makeUuid(), type: 'asset--plant', attributes: { name: 'Plant A' } },
            { id: makeUuid(), type: 'asset--plant', attributes: { name: 'Plant B' } },
          ],
          links: { next: { href: 'https://test.farmos.net/api/asset/plant?page[offset]=50' } },
        }))
        .mockResolvedValueOnce(ok({
          data: [{ id: makeUuid(), type: 'asset--plant', attributes: { name: 'Plant C' } }],
          links: {},
        }))
        .mockResolvedValueOnce(ok({ data: [] }));

      const result = await client.getPlantAssets('P2R3');
      expect(result).toHaveLength(3);
    });

    it('fetchPlantsContains includes stable sort=name', async () => {
      const client = new FarmOSClient(baseConfig(mockHttp));
      mockHttp.get.mockResolvedValueOnce(ok({ data: [] }));
      await client.getPlantAssets('P2R3');

      const callPath = mockHttp.get.mock.calls[0][0] as string;
      expect(callPath).toContain('sort=name');
    });

    it('fetchPlantsContains respects maxPages safety cap', async () => {
      const client = new FarmOSClient(baseConfig(mockHttp));
      for (let i = 0; i < 25; i++) {
        mockHttp.get.mockResolvedValueOnce(ok({
          data: [{ id: makeUuid(), type: 'asset--plant', attributes: { name: `Plant ${i}` } }],
        }));
      }

      await (client as any).fetchPlantsContains('P2R3', 'active', 5);
      expect(mockHttp.get.mock.calls.length).toBe(5);
    });

    it('exact match handles species with dashes (Basil - Sweet)', async () => {
      const client = new FarmOSClient(baseConfig(mockHttp));
      mockHttp.get
        .mockResolvedValueOnce(ok({
          data: [
            { id: makeUuid(), type: 'asset--plant', attributes: { name: '25 APR 2025 - Basil - Sweet - P2R3.15-21', status: 'active' } },
            { id: makeUuid(), type: 'asset--plant', attributes: { name: '25 APR 2025 - Basil - Sweet (Classic) - P2R3.15-21', status: 'active' } },
          ],
        }))
        .mockResolvedValueOnce(ok({ data: [] }));

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
      const client = new FarmOSClient(baseConfig(mockHttp));
      mockHttp.post.mockResolvedValueOnce(ok({ data: { id: 'new-qty-id' } }));
      const result = await client.createQuantity('plant-id-1', 5, 'reset');

      expect(result).toBe('new-qty-id');
      const [path, body] = mockHttp.post.mock.calls[0];
      expect(path).toBe('/api/quantity/standard');
      expect(body.data.type).toBe('quantity--standard');
      expect(body.data.attributes.value.decimal).toBe('5');
      expect(body.data.attributes.measure).toBe('count');
      expect(body.data.attributes.inventory_adjustment).toBe('reset');
      expect(body.data.relationships.inventory_asset.data.id).toBe('plant-id-1');
    });

    it('creates observation log with movement', async () => {
      const client = new FarmOSClient(baseConfig(mockHttp));
      mockHttp.post.mockResolvedValueOnce(ok({ data: { id: 'obs-log-id' } }));
      await client.createObservationLog('plant-1', 'section-uuid', 'qty-1', 1714003200, 'Test Obs', 'notes');

      const [, body] = mockHttp.post.mock.calls[0];
      expect(body.data.type).toBe('log--observation');
      expect(body.data.attributes.is_movement).toBe(true);
      expect(body.data.attributes.status).toBe('done');
      expect(body.data.relationships.asset.data[0].id).toBe('plant-1');
      expect(body.data.relationships.location.data[0].id).toBe('section-uuid');
      expect(body.data.relationships.quantity.data[0].id).toBe('qty-1');
    });

    it('creates plant asset (no status field — ADR 0009)', async () => {
      const client = new FarmOSClient(baseConfig(mockHttp));
      mockHttp.post.mockResolvedValueOnce(ok({ data: { id: 'new-plant-id' } }));
      await client.createPlantAsset('Test Plant', 'type-uuid-1', 'test notes');

      const [, body] = mockHttp.post.mock.calls[0];
      expect(body.data.type).toBe('asset--plant');
      expect(body.data.attributes.name).toBe('Test Plant');
      expect(body.data.relationships.plant_type.data[0].id).toBe('type-uuid-1');
      // status field is intentionally omitted — redundant in v3 (active is
      // the default), removed in v4. Single-version code per ADR 0009.
      expect(body.data.attributes).not.toHaveProperty('status');
      expect(body.data.attributes).not.toHaveProperty('archived');
    });

    it('creates plant type taxonomy term', async () => {
      const client = new FarmOSClient(baseConfig(mockHttp));
      mockHttp.post.mockResolvedValueOnce(ok({ data: { id: 'new-type-id' } }));
      await client.createPlantType('Pigeon Pea', 'A pioneer legume', 120, 30);

      const [, body] = mockHttp.post.mock.calls[0];
      expect(body.data.type).toBe('taxonomy_term--plant_type');
      expect(body.data.attributes.name).toBe('Pigeon Pea');
      expect(body.data.attributes.maturity_days).toBe(120);
      expect(body.data.attributes.transplant_days).toBe(30);
    });
  });

  // ── Archive plant ─────────────────────────────────────────

  describe('archive plant', () => {
    it('archives by name (lookup then patch)', async () => {
      const client = new FarmOSClient(baseConfig(mockHttp));
      const uuid = makeUuid();
      mockHttp.get.mockResolvedValueOnce(ok({ data: [{ id: uuid }] }));
      mockHttp.patch.mockResolvedValueOnce(ok({ data: { id: uuid, attributes: { status: 'archived' } } }));

      const result = await client.archivePlant('25 APR 2025 - Pigeon Pea - P2R2.0-3');
      expect(result.id).toBe(uuid);
      expect(mockHttp.patch).toHaveBeenCalledOnce();
    });

    it('archives by UUID (skip lookup)', async () => {
      const client = new FarmOSClient(baseConfig(mockHttp));
      const uuid = '12345678-1234-1234-1234-123456789012';
      mockHttp.patch.mockResolvedValueOnce(
        ok({ data: { id: uuid, attributes: { status: 'archived' } } }),
      );

      const result = await client.archivePlant(uuid);
      expect(result.id).toBe(uuid);
      expect(mockHttp.get).not.toHaveBeenCalled();
      expect(mockHttp.patch).toHaveBeenCalledOnce();
    });

    it('throws when not found by name', async () => {
      const client = new FarmOSClient(baseConfig(mockHttp));
      mockHttp.get.mockResolvedValueOnce(ok({ data: [] }));
      await expect(client.archivePlant('Nonexistent Plant')).rejects.toThrow('not found');
    });
  });

  // ── File upload ──────────────────────────────────────────
  // Regression 2026-04-21: farmOS file upload responses can return
  // {data: {...}} (dict) or {data: [{...}]} (list) depending on cardinality.
  // 2026-04-22: multi-entry list returns LAST entry (newly-uploaded file).

  describe('file upload response shapes', () => {
    it('returns id from dict-form response {data: {id}}', async () => {
      const client = new FarmOSClient(baseConfig(mockHttp));
      mockHttp.post.mockResolvedValueOnce(ok({ data: { id: 'file-uuid-dict', type: 'file--file' } }));
      const id = await client.uploadFile(
        'log/observation', 'log-1', 'image', 'photo.jpg', new ArrayBuffer(4), 'image/jpeg',
      );
      expect(id).toBe('file-uuid-dict');
    });

    it('returns id from list-form response {data: [{id}]}', async () => {
      const client = new FarmOSClient(baseConfig(mockHttp));
      mockHttp.post.mockResolvedValueOnce(ok({ data: [{ id: 'file-uuid-list', type: 'file--file' }] }));
      const id = await client.uploadFile(
        'log/observation', 'log-1', 'image', 'photo.jpg', new ArrayBuffer(4), 'image/jpeg',
      );
      expect(id).toBe('file-uuid-list');
    });

    it('regression 2026-04-22: multi-entry list returns LAST entry (newly-uploaded file)', async () => {
      const client = new FarmOSClient(baseConfig(mockHttp));
      mockHttp.post.mockResolvedValueOnce(
        ok({
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
    });

    it('returns null on empty list response {data: []}', async () => {
      const client = new FarmOSClient(baseConfig(mockHttp));
      mockHttp.post.mockResolvedValueOnce(ok({ data: [] }));
      const id = await client.uploadFile(
        'log/observation', 'log-1', 'image', 'photo.jpg', new ArrayBuffer(4), 'image/jpeg',
      );
      expect(id).toBeNull();
    });

    it('returns null on empty dict response {data: {}}', async () => {
      const client = new FarmOSClient(baseConfig(mockHttp));
      mockHttp.post.mockResolvedValueOnce(ok({ data: {} }));
      const id = await client.uploadFile(
        'log/observation', 'log-1', 'image', 'photo.jpg', new ArrayBuffer(4), 'image/jpeg',
      );
      expect(id).toBeNull();
    });

    it('throws on HTTP error status (HttpClientError wrapped)', async () => {
      const client = new FarmOSClient(baseConfig(mockHttp));
      mockHttp.post.mockRejectedValueOnce(err(422, { errors: ['bad request'] }));
      await expect(
        client.uploadFile('log/observation', 'log-1', 'image', 'bad.json', new ArrayBuffer(4), 'application/json'),
      ).rejects.toThrow('HTTP 422');
    });

    it('passes binary body through with octet-stream Content-Type override', async () => {
      const client = new FarmOSClient(baseConfig(mockHttp));
      const binaryData = new ArrayBuffer(8);
      mockHttp.post.mockResolvedValueOnce(ok({ data: { id: 'file-1' } }));

      await client.uploadFile('log/observation', 'log-1', 'image', 'x.jpg', binaryData);

      const [path, body, config] = mockHttp.post.mock.calls[0];
      expect(path).toBe('/api/log/observation/log-1/image');
      expect(body).toBe(binaryData);
      expect(config.headers['Content-Type']).toBe('application/octet-stream');
      expect(config.headers['Content-Disposition']).toBe('file; filename="x.jpg"');
    });
  });

  // ── Cache ─────────────────────────────────────────────────

  describe('plant type cache', () => {
    it('caches results and avoids second fetch', async () => {
      const client = new FarmOSClient(baseConfig(mockHttp));
      const data = [{ id: makeUuid(), attributes: { name: 'Pigeon Pea' } }];
      mockHttp.get
        .mockResolvedValueOnce(ok({ data }))
        .mockResolvedValueOnce(ok({ data: [] }));

      const result1 = await client.getAllPlantTypesCached();
      const callCountAfterFirst = mockHttp.get.mock.calls.length;

      const result2 = await client.getAllPlantTypesCached();
      expect(result1).toEqual(result2);
      expect(mockHttp.get.mock.calls.length).toBe(callCountAfterFirst);
    });
  });

  // ── patchRelationship ─────────────────────────────────────

  describe('patchRelationship', () => {
    it('returns true on 2xx', async () => {
      const client = new FarmOSClient(baseConfig(mockHttp));
      mockHttp.patch.mockResolvedValueOnce(ok({ data: [] }, 204));
      const ok_ = await client.patchRelationship('asset/plant', 'plant-1', 'image', [
        { type: 'file--file', id: 'file-1' },
      ]);
      expect(ok_).toBe(true);
    });

    it('returns false on HttpClientError (graceful)', async () => {
      const client = new FarmOSClient(baseConfig(mockHttp));
      mockHttp.patch.mockRejectedValueOnce(err(404));
      const ok_ = await client.patchRelationship('asset/plant', 'plant-1', 'image', []);
      expect(ok_).toBe(false);
    });
  });

  // ── v4 mode (FARMOS_API_VERSION='4') ──────────────────────
  // Exercises the v3/v4 dual-path sites flipped via `apiVersion: '4'` on
  // FarmOSConfig. Default-version (v3) coverage lives in the describe blocks
  // above. ADR 0009.

  describe('v4 mode', () => {
    const v4Config = (httpClient: HttpClient) => ({
      farmUrl: 'https://test.farmos.net',
      httpClient,
      apiVersion: '4' as const,
    });

    it('exposes apiVersion=4', () => {
      const client = new FarmOSClient(v4Config(mockHttp));
      expect(client.apiVersion).toBe('4');
    });

    it('CONTAINS plant query uses filter[archived]=0 (not filter[status]=active)', async () => {
      const client = new FarmOSClient(v4Config(mockHttp));
      mockHttp.get.mockResolvedValueOnce(ok({ data: [] }));
      await client.getPlantAssets('P2R3.15-21');

      const callPath = mockHttp.get.mock.calls[0][0] as string;
      expect(callPath).toContain('filter[archived]=0');
      expect(callPath).not.toContain('filter[status]=');
    });

    it('paginated plant fetch uses filter[archived]=0 in dict form', async () => {
      const client = new FarmOSClient(v4Config(mockHttp));
      mockHttp.get
        .mockResolvedValueOnce(ok({ data: [] })); // empty page
      await client.getPlantAssets(); // no filters → falls into fetchAllPaginated path

      const callPath = mockHttp.get.mock.calls[0][0] as string;
      expect(callPath).toContain('filter[archived]=0');
      expect(callPath).not.toContain('filter[status]=');
    });

    it('archive PATCH sends {archived: true} (not {status: archived})', async () => {
      const client = new FarmOSClient(v4Config(mockHttp));
      const uuid = '12345678-1234-1234-1234-123456789012';
      mockHttp.patch.mockResolvedValueOnce(
        ok({ data: { id: uuid, attributes: { archived: true } } }),
      );

      await client.archivePlant(uuid);

      const [, body] = mockHttp.patch.mock.calls[0];
      expect(body.data.attributes).toEqual({ archived: true });
      expect(body.data.attributes).not.toHaveProperty('status');
    });

    it('client.assetStatusFilter("active") returns v4 dict shape', () => {
      const client = new FarmOSClient(v4Config(mockHttp));
      expect(client.assetStatusFilter('active')).toEqual({ archived: '0' });
      expect(client.assetStatusFilter('archived')).toEqual({ archived: '1' });
    });
  });
});
