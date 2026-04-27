/**
 * Layer 3a: Read tool tests — verifies tool orchestration with mocked client.
 * Mirrors Python test_tools_read.py (8 tests).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { makePlantAsset, makePlantType, makeSectionAsset, makeLog } from './fixtures.js';

// Mock the client factory
const mockClient = {
  getPlantAssets: vi.fn(),
  fetchByName: vi.fn(),
  getLogs: vi.fn(),
  getSectionAssets: vi.fn(),
  getAllLocations: vi.fn(),
  fetchAllPaginated: vi.fn(),
  fetchFiltered: vi.fn(),
  getPlantTypeDetails: vi.fn(),
  getAllPlantTypesCached: vi.fn(),
  getSectionUuid: vi.fn(),
  getSectionType: vi.fn().mockResolvedValue('asset--land'),
  getPlantTypeUuid: vi.fn(),
  connect: vi.fn(),
  isConnected: true,
  apiVersion: '3' as const,
  // Default to v3 dict shape; tests can override per call.
  assetStatusFilter: vi.fn((status: 'active' | 'archived') => ({ status })),
};

vi.mock('../clients/index.js', () => ({
  getFarmOSClient: () => mockClient,
  getObserveClient: () => null,
  getMemoryClient: () => null,
  getPlantTypesClient: () => null,
  getKnowledgeClient: () => null,
}));

// Import AFTER mocks
import { queryPlantsTool } from '../tools/query-plants.js';
import { getPlantDetailTool } from '../tools/get-plant-detail.js';
import { getInventoryTool } from '../tools/get-inventory.js';
import { querySectionsTool } from '../tools/query-sections.js';
import { searchPlantTypesTool } from '../tools/search-plant-types.js';
import { getAllPlantTypesTool } from '../tools/get-all-plant-types.js';

function parseResult(result: any): any {
  return JSON.parse(result.content[0].text);
}

describe('read tools', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('query_plants returns formatted results', async () => {
    const plants = [
      makePlantAsset({ name: '25 APR 2025 - Pigeon Pea - P2R2.0-3', inventoryCount: 4 }),
      makePlantAsset({ name: '25 APR 2025 - Comfrey - P2R2.0-3', inventoryCount: 6 }),
    ];
    mockClient.getPlantAssets.mockResolvedValue(plants);

    const result = parseResult(await queryPlantsTool.handler({ section_id: 'P2R2.0-3', status: 'active' }));
    expect(result.count).toBe(2);
    expect(result.plants).toHaveLength(2);
    expect(result.filters.section_id).toBe('P2R2.0-3');
  });

  it('get_plant_detail returns plant with logs', async () => {
    const plant = makePlantAsset({ name: '25 APR 2025 - Pigeon Pea - P2R2.0-3', inventoryCount: 4 });
    mockClient.fetchByName.mockResolvedValue([plant]);
    mockClient.getLogs.mockResolvedValue([
      makeLog({ name: 'Obs 1', logType: 'observation' }),
      makeLog({ name: 'Obs 2', logType: 'transplanting' }),
    ]);

    const result = parseResult(await getPlantDetailTool.handler({ plant_name: '25 APR 2025 - Pigeon Pea - P2R2.0-3' }));
    expect(result.plant.species).toBe('Pigeon Pea');
    expect(result.plant.section).toBe('P2R2.0-3');
    expect(result.log_count).toBe(2);
  });

  it('get_plant_detail returns error when not found', async () => {
    mockClient.fetchByName.mockResolvedValue([]);
    mockClient.getPlantAssets.mockResolvedValue([]);

    const result = parseResult(await getPlantDetailTool.handler({ plant_name: 'Nonexistent' }));
    expect(result.error).toContain('not found');
  });

  it('get_inventory groups by section for species query', async () => {
    const plants = [
      makePlantAsset({ name: '25 APR 2025 - Pigeon Pea - P2R2.0-3', inventoryCount: 4 }),
      makePlantAsset({ name: '25 APR 2025 - Pigeon Pea - P2R3.15-21', inventoryCount: 3 }),
    ];
    mockClient.getPlantAssets.mockResolvedValue(plants);

    const result = parseResult(await getInventoryTool.handler({ species: 'Pigeon Pea' }));
    expect(result.summary.total_species_entries).toBe(2);
    expect(result.summary.total_plant_count).toBe(7);
    expect(result.by_section).toHaveLength(2);
  });

  it('query_sections groups by row (with row filter)', async () => {
    const sections = [
      makeSectionAsset({ name: 'P2R2.0-3' }),
      makeSectionAsset({ name: 'P2R2.3-7' }),
    ];
    mockClient.getSectionAssets.mockResolvedValue(sections);
    mockClient.fetchAllPaginated.mockResolvedValue([
      makePlantAsset({ name: '25 APR 2025 - Pigeon Pea - P2R2.0-3' }),
      makePlantAsset({ name: '25 APR 2025 - Comfrey - P2R2.0-3' }),
    ]);

    const result = parseResult(await querySectionsTool.handler({ row: 'P2R2' }));
    expect(result.total_sections).toBe(2);
    expect(result.rows.P2R2).toHaveLength(2);
    const p2r2_03 = result.rows.P2R2.find((s: any) => s.section_id === 'P2R2.0-3');
    expect(p2r2_03.plant_count).toBe(2);
  });

  it('query_sections returns all location types when no filter', async () => {
    mockClient.getAllLocations.mockResolvedValue({
      paddock: [
        { name: 'P2R2.0-3', uuid: 'uuid-1' },
        { name: 'P2R3.15-21', uuid: 'uuid-2' },
      ],
      nursery: [
        { name: 'NURS.SH1-1', uuid: 'uuid-3' },
      ],
      compost: [
        { name: 'COMP.BAY1', uuid: 'uuid-4' },
      ],
    });
    mockClient.fetchAllPaginated.mockResolvedValue([
      makePlantAsset({ name: '25 APR 2025 - Pigeon Pea - P2R2.0-3' }),
      makePlantAsset({ name: '25 APR 2025 - Comfrey - NURS.SH1-1' }),
    ]);

    const result = parseResult(await querySectionsTool.handler({}));
    expect(result.total_sections).toBe(4);
    expect(result.rows.P2R2).toHaveLength(1);
    expect(result.rows.P2R3).toHaveLength(1);
    expect(result.rows.NURS).toHaveLength(1);
    expect(result.rows.COMP).toHaveLength(1);
    expect(result.rows.NURS[0].plant_count).toBe(1);
  });

  it('search_plant_types is case-insensitive', async () => {
    const types = [
      makePlantType({ name: 'Pigeon Pea' }),
      makePlantType({ name: 'Peanut' }),
      makePlantType({ name: 'Sweet Potato' }),
    ];
    mockClient.getPlantTypeDetails.mockResolvedValue(types);

    const result = parseResult(await searchPlantTypesTool.handler({ query: 'pea' }));
    expect(result.count).toBe(2);
    const names = result.plant_types.map((pt: any) => pt.name);
    expect(names).toContain('Pigeon Pea');
    expect(names).toContain('Peanut');
    expect(names).not.toContain('Sweet Potato');
  });

  it('get_all_plant_types returns sorted', async () => {
    const types = [
      makePlantType({ name: 'Sweet Potato' }),
      makePlantType({ name: 'Comfrey' }),
      makePlantType({ name: 'Pigeon Pea' }),
    ];
    mockClient.getAllPlantTypesCached.mockResolvedValue(types);

    const result = parseResult(await getAllPlantTypesTool.handler({}));
    expect(result.count).toBe(3);
    expect(result.plant_types[0].name).toBe('Comfrey');
    expect(result.plant_types[1].name).toBe('Pigeon Pea');
    expect(result.plant_types[2].name).toBe('Sweet Potato');
  });
});
