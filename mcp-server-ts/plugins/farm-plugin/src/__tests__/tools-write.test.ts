/**
 * Layer 3b: Write tool tests — create observation, activity, plant, archive.
 * Mirrors Python test_tools_write.py (10+ tests).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { makePlantAsset } from './fixtures.js';

const mockClient = {
  fetchByName: vi.fn(),
  getPlantAssets: vi.fn(),
  getSectionUuid: vi.fn(),
  getPlantTypeUuid: vi.fn(),
  plantAssetExists: vi.fn(),
  logExists: vi.fn(),
  createQuantity: vi.fn(),
  createObservationLog: vi.fn(),
  createActivityLog: vi.fn(),
  createPlantAsset: vi.fn(),
  archivePlant: vi.fn(),
  connect: vi.fn(),
  isConnected: true,
};

vi.mock('../clients/index.js', () => ({
  getFarmOSClient: () => mockClient,
  getObserveClient: () => null,
  getMemoryClient: () => null,
  getPlantTypesClient: () => null,
  getKnowledgeClient: () => null,
}));

import { createObservationTool } from '../tools/create-observation.js';
import { createActivityTool } from '../tools/create-activity.js';
import { updateInventoryTool } from '../tools/update-inventory.js';
import { createPlantTool } from '../tools/create-plant.js';
import { archivePlantTool } from '../tools/archive-plant.js';

function parseResult(result: any): any {
  return JSON.parse(result.content[0].text);
}

describe('write tools', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── create_observation ────────────────────────────────────

  describe('create_observation', () => {
    it('happy path — creates observation', async () => {
      const plant = makePlantAsset({ name: '25 APR 2025 - Pigeon Pea - P2R2.0-3', inventoryCount: 4 });
      mockClient.fetchByName.mockResolvedValue([plant]);
      mockClient.getSectionUuid.mockResolvedValue('section-uuid-1');
      mockClient.logExists.mockResolvedValue(null);
      mockClient.createQuantity.mockResolvedValue('qty-id-1');
      mockClient.createObservationLog.mockResolvedValue('log-id-1');

      const result = parseResult(await createObservationTool.handler({
        plant_name: '25 APR 2025 - Pigeon Pea - P2R2.0-3', count: 3, notes: '1 lost to frost', date: '2026-03-09',
      }));
      expect(result.status).toBe('created');
      expect(result.log_id).toBe('log-id-1');
      expect(result.count).toBe(3);
      expect(mockClient.createQuantity).toHaveBeenCalledWith(plant.id, 3, 'reset');
    });

    it('returns error when plant not found', async () => {
      mockClient.fetchByName.mockResolvedValue([]);
      const result = parseResult(await createObservationTool.handler({
        plant_name: 'Nonexistent', count: 3, notes: '',
      }));
      expect(result.error).toContain('not found');
      expect(mockClient.createQuantity).not.toHaveBeenCalled();
    });

    it('skips when log already exists (idempotency)', async () => {
      const plant = makePlantAsset({ name: '25 APR 2025 - Pigeon Pea - P2R2.0-3' });
      mockClient.fetchByName.mockResolvedValue([plant]);
      mockClient.getSectionUuid.mockResolvedValue('section-uuid');
      mockClient.logExists.mockResolvedValue('existing-log-id');

      const result = parseResult(await createObservationTool.handler({
        plant_name: '25 APR 2025 - Pigeon Pea - P2R2.0-3', count: 3, notes: '', date: '2026-03-09',
      }));
      expect(result.status).toBe('skipped');
      expect(result.existing_log_id).toBe('existing-log-id');
      expect(mockClient.createQuantity).not.toHaveBeenCalled();
    });
  });

  // ── create_activity ───────────────────────────────────────

  describe('create_activity', () => {
    it('happy path — creates activity log', async () => {
      mockClient.getSectionUuid.mockResolvedValue('section-uuid-1');
      mockClient.createActivityLog.mockResolvedValue('activity-log-id');

      const result = parseResult(await createActivityTool.handler({
        section_id: 'P2R3.15-21', activity_type: 'watering', notes: 'Drip irrigation', date: '2026-03-09',
      }));
      expect(result.status).toBe('created');
      expect(result.log_id).toBe('activity-log-id');
      expect(result.log_name).toBe('Watering — P2R3.15-21');
    });

    it('returns error when section not found', async () => {
      mockClient.getSectionUuid.mockResolvedValue(null);
      const result = parseResult(await createActivityTool.handler({
        section_id: 'P99R99.0-1', activity_type: 'watering', notes: 'Test',
      }));
      expect(result.error).toContain('not found');
      expect(mockClient.createActivityLog).not.toHaveBeenCalled();
    });
  });

  // ── create_plant ──────────────────────────────────────────

  describe('create_plant', () => {
    it('happy path — creates plant + observation', async () => {
      mockClient.getPlantTypeUuid.mockResolvedValue('type-uuid-1');
      mockClient.getSectionUuid.mockResolvedValue('section-uuid-1');
      mockClient.plantAssetExists.mockResolvedValue(null);
      mockClient.createPlantAsset.mockResolvedValue('new-plant-id');
      mockClient.createQuantity.mockResolvedValue('qty-id');
      mockClient.createObservationLog.mockResolvedValue('obs-log-id');

      const result = parseResult(await createPlantTool.handler({
        species: 'Pigeon Pea', section_id: 'P2R3.15-21', count: 5,
        planted_date: '2026-03-09', notes: 'New planting',
      }));
      expect(result.status).toBe('created');
      expect(result.plant.species).toBe('Pigeon Pea');
      expect(result.plant.section).toBe('P2R3.15-21');
      expect(result.plant.count).toBe(5);
      expect(result.observation_log.id).toBe('obs-log-id');
    });

    it('returns error when plant type not found', async () => {
      mockClient.getPlantTypeUuid.mockResolvedValue(null);
      const result = parseResult(await createPlantTool.handler({
        species: 'Nonexistent', section_id: 'P2R3.15-21', count: 1, notes: '',
      }));
      expect(result.error).toContain('not found');
      expect(mockClient.createPlantAsset).not.toHaveBeenCalled();
    });

    it('skips when plant already exists (idempotency)', async () => {
      mockClient.getPlantTypeUuid.mockResolvedValue('type-uuid');
      mockClient.getSectionUuid.mockResolvedValue('section-uuid');
      mockClient.plantAssetExists.mockResolvedValue('existing-plant-id');

      const result = parseResult(await createPlantTool.handler({
        species: 'Pigeon Pea', section_id: 'P2R3.15-21', count: 5, notes: '',
      }));
      expect(result.status).toBe('skipped');
      expect(result.existing_id).toBe('existing-plant-id');
      expect(mockClient.createPlantAsset).not.toHaveBeenCalled();
    });
  });

  // ── update_inventory ──────────────────────────────────────

  describe('update_inventory', () => {
    it('delegates to create_observation', async () => {
      const plant = makePlantAsset({ name: '25 APR 2025 - Pigeon Pea - P2R2.0-3' });
      mockClient.fetchByName.mockResolvedValue([plant]);
      mockClient.getSectionUuid.mockResolvedValue('section-uuid');
      mockClient.logExists.mockResolvedValue(null);
      mockClient.createQuantity.mockResolvedValue('qty-id');
      mockClient.createObservationLog.mockResolvedValue('log-id');

      const result = parseResult(await updateInventoryTool.handler({
        plant_name: '25 APR 2025 - Pigeon Pea - P2R2.0-3', new_count: 4, notes: 'snails ate two',
      }));
      expect(result.status).toBe('created');
      expect(mockClient.createQuantity).toHaveBeenCalled();
    });
  });

  // ── archive_plant ─────────────────────────────────────────

  describe('archive_plant', () => {
    it('happy path — archives without reason', async () => {
      const archived = {
        id: 'plant-uuid-1',
        type: 'asset--plant',
        attributes: { name: '25 APR 2025 - Pigeon Pea - P2R2.0-3', status: 'archived', notes: {}, inventory: [] },
        relationships: { plant_type: { data: [] } },
      };
      mockClient.archivePlant.mockResolvedValue(archived);

      const result = parseResult(await archivePlantTool.handler({
        plant_name: '25 APR 2025 - Pigeon Pea - P2R2.0-3', reason: '',
      }));
      expect(result.status).toBe('archived');
      expect(result.plant.species).toBe('Pigeon Pea');
      expect(mockClient.createActivityLog).not.toHaveBeenCalled();
    });

    it('returns error when not found', async () => {
      mockClient.archivePlant.mockRejectedValue(new Error('Plant not found'));
      const result = parseResult(await archivePlantTool.handler({
        plant_name: 'Nonexistent', reason: '',
      }));
      expect(result.error).toContain('not found');
    });

    it('creates activity log when reason provided', async () => {
      const archived = {
        id: 'plant-uuid-1',
        type: 'asset--plant',
        attributes: { name: '25 APR 2025 - Pigeon Pea - P2R2.0-3', status: 'archived', notes: {}, inventory: [] },
        relationships: { plant_type: { data: [] } },
      };
      mockClient.archivePlant.mockResolvedValue(archived);
      mockClient.getSectionUuid.mockResolvedValue('section-uuid');
      mockClient.createActivityLog.mockResolvedValue('activity-log-id');

      const result = parseResult(await archivePlantTool.handler({
        plant_name: '25 APR 2025 - Pigeon Pea - P2R2.0-3', reason: 'Died from frost damage',
      }));
      expect(result.status).toBe('archived');
      expect(result.activity_log.reason).toBe('Died from frost damage');
      expect(result.activity_log.id).toBe('activity-log-id');
      expect(mockClient.createActivityLog).toHaveBeenCalled();
    });
  });
});
