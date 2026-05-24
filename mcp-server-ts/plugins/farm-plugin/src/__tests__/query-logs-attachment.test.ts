/**
 * query_logs section_id filter — attachment vs name-substring behaviour.
 *
 * The 2026-05-24 diagnostic: query_logs(section_id="P1R2") returned 0 even
 * though P1R2 has logs in farmOS. Root cause: the filter was matching on the
 * log NAME substring rather than the log's `location` relationship. This test
 * suite locks in the new behaviour:
 *
 *   - When section_id resolves to a known asset → filter[location.id]=UUID
 *   - When section_id does NOT resolve            → name-substring fallback
 *
 * Layer 2 (HTTP-mocked client) so we can verify the actual URL the client
 * builds + the surfaced filter_method on the tool response.
 */

import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import type { HttpClient, HttpResponse } from '@fireflyagents/mcp-shared-utils';
import { FarmOSClient } from '../clients/farmos-client.js';

type MockedHttpClient = { [K in keyof HttpClient]: Mock };

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
  return { data, status, statusText: 'OK', headers: {} };
}

describe('FarmOSClient.getLogs section_id filter', () => {
  let mockHttp: MockedHttpClient;
  let client: FarmOSClient;

  beforeEach(() => {
    mockHttp = makeMockHttpClient();
    client = new FarmOSClient({
      farmUrl: 'https://test.farmos.net',
      httpClient: mockHttp,
      apiVersion: '4',
    });
  });

  it('uses filter[location.id] when section_id resolves to a known asset', async () => {
    // 1st GET: getSectionUuid → /api/asset/land?filter[name]=P1R2 → returns the row asset
    // 2nd-onward GETs: per-log-type fetchLogsByLocationId → one per log type, each empty
    mockHttp.get
      .mockResolvedValueOnce(ok({ data: [{ id: 'uuid-row-p1r2', attributes: { name: 'P1R2' } }] }))
      // 5 log types, each one paginated call returning empty page
      .mockResolvedValue(ok({ data: [] }));

    const logs = await client.getLogs(undefined, 'P1R2', undefined, 20);

    // Verify at least one call used the attachment filter
    const paths = mockHttp.get.mock.calls.map((c) => c[0] as string);
    const attachmentCall = paths.find((p) => p.includes('filter[location.id]=uuid-row-p1r2'));
    expect(attachmentCall).toBeDefined();
    expect((logs as any)._filterMethod).toBe('location-id');
  });

  it('falls back to name-substring when section_id does not resolve', async () => {
    // 1st GET: land lookup → empty
    // 2nd GET: structure lookup → empty
    mockHttp.get
      .mockResolvedValueOnce(ok({ data: [] }))  // land
      .mockResolvedValueOnce(ok({ data: [] }))  // structure
      .mockResolvedValue(ok({ data: [] }));      // log fetches (5 types)

    const logs = await client.getLogs(undefined, 'BOGUS', undefined, 20);

    const paths = mockHttp.get.mock.calls.map((c) => c[0] as string);
    // Should NOT have hit filter[location.id]
    expect(paths.some((p) => p.includes('filter[location.id]'))).toBe(false);
    // SHOULD have hit the CONTAINS filter for the name
    const containsCall = paths.find((p) => p.includes('filter[name][operator]=CONTAINS'));
    expect(containsCall).toBeDefined();
    expect(containsCall).toContain('BOGUS');
    expect((logs as any)._filterMethod).toBe('name-substring (fallback)');
  });

  it('species-only query uses name-substring (no fallback flag)', async () => {
    mockHttp.get.mockResolvedValue(ok({ data: [] }));
    const logs = await client.getLogs(undefined, undefined, 'Pigeon Pea', 20);

    const paths = mockHttp.get.mock.calls.map((c) => c[0] as string);
    expect(paths.some((p) => p.includes('filter[name][operator]=CONTAINS'))).toBe(true);
    expect((logs as any)._filterMethod).toBe('name-substring');
  });

  it('no section_id and no species uses fetchFiltered, marked as filter_method=none', async () => {
    mockHttp.get.mockResolvedValue(ok({ data: [] }));
    const logs = await client.getLogs(undefined, undefined, undefined, 20);
    expect((logs as any)._filterMethod).toBe('none');
  });

  it('sectionId + species combined uses attachment filter and narrows by species', async () => {
    mockHttp.get
      // getSectionUuid resolves
      .mockResolvedValueOnce(ok({ data: [{ id: 'uuid-row-p1r2', attributes: { name: 'P1R2' } }] }))
      // log type 1 (observation): one matching, one not
      .mockResolvedValueOnce(ok({
        data: [
          { id: 'log-1', type: 'log--observation', attributes: { name: 'Some Pigeon Pea note', timestamp: '1' }, relationships: {} },
          { id: 'log-2', type: 'log--observation', attributes: { name: 'Some Comfrey note', timestamp: '2' }, relationships: {} },
        ],
      }))
      .mockResolvedValueOnce(ok({ data: [] }))  // observation page 2
      .mockResolvedValue(ok({ data: [] }));     // remaining log types

    const logs = await client.getLogs(undefined, 'P1R2', 'Pigeon Pea', 20);
    // Only the matching one survives the species narrow
    expect(logs.length).toBe(1);
    expect(logs[0].id).toBe('log-1');
    expect((logs as any)._filterMethod).toBe('location-id');
  });
});

// ── Tool-level test: surfaces filter_method in response ────────────────────

const mockClient = {
  getLogs: vi.fn(),
};

vi.mock('../clients/index.js', () => ({
  getFarmOSClient: () => mockClient,
  getObserveClient: () => null,
  getMemoryClient: () => null,
  getPlantTypesClient: () => null,
  getKnowledgeClient: () => null,
}));

import { queryLogsTool } from '../tools/query-logs.js';

function parseResult(result: any): any {
  return JSON.parse(result.content[0].text);
}

describe('query_logs tool surfaces filter_method', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('reports filter_method=location-id when client resolved the section UUID', async () => {
    const fakeLogs: any[] = [];
    Object.defineProperty(fakeLogs, '_filterMethod', { value: 'location-id', enumerable: false });
    mockClient.getLogs.mockResolvedValueOnce(fakeLogs);

    const result = parseResult(await queryLogsTool.handler({ section_id: 'P1R2' }));
    expect(result.filter_method).toBe('location-id');
  });

  it('reports filter_method=name-substring (fallback) when section_id did not resolve', async () => {
    const fakeLogs: any[] = [];
    Object.defineProperty(fakeLogs, '_filterMethod', { value: 'name-substring (fallback)', enumerable: false });
    mockClient.getLogs.mockResolvedValueOnce(fakeLogs);

    const result = parseResult(await queryLogsTool.handler({ section_id: 'BOGUS' }));
    expect(result.filter_method).toBe('name-substring (fallback)');
  });

  it('reports filter_method=none when no filters were passed', async () => {
    const fakeLogs: any[] = [];
    Object.defineProperty(fakeLogs, '_filterMethod', { value: 'none', enumerable: false });
    mockClient.getLogs.mockResolvedValueOnce(fakeLogs);

    const result = parseResult(await queryLogsTool.handler({}));
    expect(result.filter_method).toBe('none');
  });
});
