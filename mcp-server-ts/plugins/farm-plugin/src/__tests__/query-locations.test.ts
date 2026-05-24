/**
 * query_locations tool + getLocations client method tests.
 *
 * Layer 3a (tool orchestration with mocked client) + Layer 2 (HTTP-mocked
 * client behaviour), mirroring the split in tools-read.test.ts /
 * farmos-client.test.ts.
 *
 * The motivating gap (2026-05-24): query_sections silently returns 0 for
 * row-level (P1R2) and paddock-level (P1) assets because its regex only
 * matches section-shaped names. query_locations exposes the full
 * land+structure surface so we can confirm assets exist before triggering a
 * create that would duplicate them.
 */

import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import type { HttpClient, HttpResponse } from '@fireflyagents/mcp-shared-utils';
import { FarmOSClient } from '../clients/farmos-client.js';

// ── Layer 2: client.getLocations against HTTP-mocked transport ─────────────

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

function landAsset(name: string, id: string, archived = false) {
  return {
    id,
    type: 'asset--land',
    attributes: { name, archived, land_type: 'paddock' },
    relationships: { parent: { data: [] } },
  };
}

function structureAsset(name: string, id: string, archived = false) {
  return {
    id,
    type: 'asset--structure',
    attributes: { name, archived, structure_type: 'shelf' },
    relationships: { parent: { data: [] } },
  };
}

describe('FarmOSClient.getLocations', () => {
  let mockHttp: MockedHttpClient;

  beforeEach(() => {
    mockHttp = makeMockHttpClient();
  });

  it('returns every land + structure asset classified by level', async () => {
    const client = new FarmOSClient({
      farmUrl: 'https://test.farmos.net',
      httpClient: mockHttp,
      apiVersion: '4',
    });

    // First call: asset/land — returns paddock, row, section, nursery, compost, other
    mockHttp.get
      .mockResolvedValueOnce(ok({
        data: [
          landAsset('P1', 'uuid-paddock-1'),
          landAsset('P2', 'uuid-paddock-2'),
          landAsset('P1R2', 'uuid-row-p1r2'),
          landAsset('P2R3', 'uuid-row-p2r3'),
          landAsset('P1R2.0-14', 'uuid-section-1'),
          landAsset('NURS.GR', 'uuid-nurs'),
          landAsset('COMP.BAY1', 'uuid-comp'),
          landAsset('Dam', 'uuid-other'),
        ],
      }))
      .mockResolvedValueOnce(ok({ data: [] }))
      // Second call: asset/structure
      .mockResolvedValueOnce(ok({
        data: [
          structureAsset('NURS.SH1-1', 'uuid-struct-1'),
        ],
      }))
      .mockResolvedValueOnce(ok({ data: [] }));

    const locations = await client.getLocations();

    expect(locations).toHaveLength(9);
    const byLevel = locations.reduce<Record<string, number>>((acc, l) => {
      acc[l.level] = (acc[l.level] ?? 0) + 1;
      return acc;
    }, {});
    expect(byLevel).toEqual({
      paddock: 2,
      row: 2,
      section: 1,
      nursery: 1,
      compost: 1,
      structure: 1,
      other: 1,
    });
  });

  it('hides archived assets by default but includes them when asked', async () => {
    const client = new FarmOSClient({
      farmUrl: 'https://test.farmos.net',
      httpClient: mockHttp,
      apiVersion: '4',
    });

    mockHttp.get
      .mockResolvedValueOnce(ok({
        data: [
          landAsset('P1R2', 'uuid-active'),
          landAsset('P1R9-old', 'uuid-archived', true),
        ],
      }))
      .mockResolvedValueOnce(ok({ data: [] }))
      .mockResolvedValueOnce(ok({ data: [] }));

    const active = await client.getLocations();
    expect(active.map((l) => l.uuid)).toEqual(['uuid-active']);

    // Reset mocks and rerun with includeArchived
    mockHttp.get.mockReset();
    mockHttp.get
      .mockResolvedValueOnce(ok({
        data: [
          landAsset('P1R2', 'uuid-active'),
          landAsset('P1R9-old', 'uuid-archived', true),
        ],
      }))
      .mockResolvedValueOnce(ok({ data: [] }))
      .mockResolvedValueOnce(ok({ data: [] }));

    const all = await client.getLocations({ includeArchived: true });
    expect(all.map((l) => l.uuid).sort()).toEqual(['uuid-active', 'uuid-archived']);
  });
});

// ── Layer 3a: query_locations tool with mocked client ──────────────────────

const mockClient = {
  getLocations: vi.fn(),
  fetchAllPaginated: vi.fn(),
  apiVersion: '4' as const,
  assetStatusFilter: vi.fn(() => ({ archived: '0' })),
};

vi.mock('../clients/index.js', () => ({
  getFarmOSClient: () => mockClient,
  getObserveClient: () => null,
  getMemoryClient: () => null,
  getPlantTypesClient: () => null,
  getKnowledgeClient: () => null,
}));

// Import AFTER the mock
import { queryLocationsTool } from '../tools/query-locations.js';

function parseResult(result: any): any {
  return JSON.parse(result.content[0].text);
}

const FULL_LOCATIONS = [
  { name: 'COMP.BAY1', uuid: 'uuid-comp', level: 'compost', asset_type: 'land', archived: false, parent_uuids: [] },
  { name: 'Dam', uuid: 'uuid-other', level: 'other', asset_type: 'land', archived: false, parent_uuids: [] },
  { name: 'NURS.GR', uuid: 'uuid-nurs-1', level: 'nursery', asset_type: 'land', archived: false, parent_uuids: [] },
  { name: 'NURS.SH1-1', uuid: 'uuid-struct-1', level: 'structure', asset_type: 'structure', archived: false, parent_uuids: [] },
  { name: 'P1', uuid: 'uuid-paddock-1', level: 'paddock', asset_type: 'land', archived: false, parent_uuids: [] },
  { name: 'P1R2', uuid: 'uuid-row-p1r2', level: 'row', asset_type: 'land', archived: false, parent_uuids: ['uuid-paddock-1'] },
  { name: 'P1R2.0-14', uuid: 'uuid-section-1', level: 'section', asset_type: 'land', archived: false, parent_uuids: ['uuid-row-p1r2'] },
  { name: 'P2', uuid: 'uuid-paddock-2', level: 'paddock', asset_type: 'land', archived: false, parent_uuids: [] },
  { name: 'P2R3', uuid: 'uuid-row-p2r3', level: 'row', asset_type: 'land', archived: false, parent_uuids: ['uuid-paddock-2'] },
];

describe('query_locations tool', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockClient.getLocations.mockResolvedValue(FULL_LOCATIONS);
  });

  it('returns all locations when level=all (default)', async () => {
    const result = parseResult(await queryLocationsTool.handler({}));
    expect(result.count).toBe(FULL_LOCATIONS.length);
    expect(result.total).toBe(FULL_LOCATIONS.length);
    expect(result.by_level.paddock).toBe(2);
    expect(result.by_level.row).toBe(2);
    expect(result.by_level.section).toBe(1);
  });

  it('level=row returns only row-level assets', async () => {
    const result = parseResult(await queryLocationsTool.handler({ level: 'row' }));
    expect(result.count).toBe(2);
    expect(result.locations.map((l: any) => l.name).sort()).toEqual(['P1R2', 'P2R3']);
  });

  it('level=paddock returns only paddock-level assets', async () => {
    const result = parseResult(await queryLocationsTool.handler({ level: 'paddock' }));
    expect(result.count).toBe(2);
    expect(result.locations.map((l: any) => l.name).sort()).toEqual(['P1', 'P2']);
  });

  it('level=section returns only section-level assets (the old behaviour)', async () => {
    const result = parseResult(await queryLocationsTool.handler({ level: 'section' }));
    expect(result.count).toBe(1);
    expect(result.locations[0].name).toBe('P1R2.0-14');
  });

  it('level=structure returns structure assets', async () => {
    const result = parseResult(await queryLocationsTool.handler({ level: 'structure' }));
    expect(result.count).toBe(1);
    expect(result.locations[0].name).toBe('NURS.SH1-1');
  });

  it('level=nursery returns nursery assets only', async () => {
    const result = parseResult(await queryLocationsTool.handler({ level: 'nursery' }));
    expect(result.count).toBe(1);
    expect(result.locations[0].name).toBe('NURS.GR');
  });

  it('name="P1R2" resolves the row asset (the 2026-05-24 gap)', async () => {
    const result = parseResult(await queryLocationsTool.handler({ name: 'P1R2' }));
    expect(result.count).toBe(1);
    expect(result.locations[0].uuid).toBe('uuid-row-p1r2');
    expect(result.locations[0].level).toBe('row');
  });

  it('name_prefix="P1R" returns every P1 row', async () => {
    const result = parseResult(await queryLocationsTool.handler({ name_prefix: 'P1R' }));
    // P1R2 (row) + P1R2.0-14 (section) — both start with P1R
    expect(result.count).toBe(2);
    const names = result.locations.map((l: any) => l.name).sort();
    expect(names).toEqual(['P1R2', 'P1R2.0-14']);
  });

  it('name_prefix + level combine to narrow', async () => {
    const result = parseResult(await queryLocationsTool.handler({ name_prefix: 'P1R', level: 'row' }));
    expect(result.count).toBe(1);
    expect(result.locations[0].name).toBe('P1R2');
  });

  it('include_archived flag is forwarded to client', async () => {
    mockClient.getLocations.mockResolvedValueOnce(FULL_LOCATIONS);
    await queryLocationsTool.handler({ include_archived: true });
    expect(mockClient.getLocations).toHaveBeenCalledWith({ includeArchived: true });
  });
});
