/**
 * Layer 3c: Import observations composite workflow tests.
 * Mirrors Python test_import_workflow.py (12 tests).
 * Tests case routing (A/B/C), status validation, dry run, error resilience.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { makePlantAsset, makeObservation } from './fixtures.js';

const mockClient = {
  fetchByName: vi.fn(),
  getPlantAssets: vi.fn(),
  getSectionUuid: vi.fn().mockResolvedValue('section-uuid-1'),
  getSectionType: vi.fn().mockResolvedValue('asset--land'),
  getPlantTypeUuid: vi.fn().mockResolvedValue('type-uuid-1'),
  plantAssetExists: vi.fn().mockResolvedValue(null),
  logExists: vi.fn().mockResolvedValue(null),
  createQuantity: vi.fn().mockResolvedValue('qty-id'),
  createObservationLog: vi.fn().mockResolvedValue('obs-log-id'),
  createActivityLog: vi.fn().mockResolvedValue('activity-log-id'),
  createPlantAsset: vi.fn().mockResolvedValue('new-plant-id'),
  archivePlant: vi.fn(),
  connect: vi.fn(),
  isConnected: true,
};

const mockObsClient = {
  listObservations: vi.fn(),
  updateStatus: vi.fn().mockResolvedValue({ success: true }),
  deleteImported: vi.fn().mockResolvedValue({ success: true }),
};

vi.mock('../clients/index.js', () => ({
  getFarmOSClient: () => mockClient,
  getObserveClient: () => mockObsClient,
  getMemoryClient: () => null,
  getPlantTypesClient: () => null,
  getKnowledgeClient: () => null,
}));

import { importObservationsTool } from '../tools/import-observations.js';

function parseResult(result: any): any {
  return JSON.parse(result.content[0].text);
}

describe('import_observations workflow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset defaults
    mockClient.getSectionUuid.mockResolvedValue('section-uuid-1');
    mockClient.getPlantTypeUuid.mockResolvedValue('type-uuid-1');
    mockClient.plantAssetExists.mockResolvedValue(null);
    mockClient.logExists.mockResolvedValue(null);
    mockClient.createQuantity.mockResolvedValue('qty-id');
    mockClient.createObservationLog.mockResolvedValue('obs-log-id');
    mockClient.createActivityLog.mockResolvedValue('activity-log-id');
    mockClient.createPlantAsset.mockResolvedValue('new-plant-id');
    mockObsClient.updateStatus.mockResolvedValue({ success: true });
    mockObsClient.deleteImported.mockResolvedValue({ success: true });
  });

  // ── Case routing ──────────────────────────────────────────

  it('Case A: section comment → creates activity', async () => {
    mockObsClient.listObservations.mockResolvedValue({
      success: true,
      observations: [makeObservation({ species: '', sectionNotes: 'Weeds growing' })],
    });

    const result = parseResult(await importObservationsTool.handler({
      submission_id: 'sub-001', reviewer: 'Claude', dry_run: false,
    }));
    expect(result.total_actions).toBe(1);
    expect(result.actions[0].type).toBe('activity');
    expect(result.actions[0].result).toBe('created');
    expect(mockClient.createActivityLog).toHaveBeenCalled();
  });

  it('Case B: new_plant mode → creates plant', async () => {
    mockObsClient.listObservations.mockResolvedValue({
      success: true,
      observations: [makeObservation({
        species: 'Macadamia', mode: 'new_plant', newCount: 2, previousCount: 0,
      })],
    });

    const result = parseResult(await importObservationsTool.handler({
      submission_id: 'sub-001', reviewer: 'Claude', dry_run: false,
    }));
    expect(result.total_actions).toBe(1);
    expect(result.actions[0].type).toBe('create_plant');
    expect(result.actions[0].result).toBe('created');
    expect(mockClient.createPlantAsset).toHaveBeenCalled();
  });

  it('Case B inferred: previous_count=0 + new_count>0 → creates plant', async () => {
    mockObsClient.listObservations.mockResolvedValue({
      success: true,
      observations: [makeObservation({
        species: 'Comfrey', mode: 'full_inventory', previousCount: 0, newCount: 3,
      })],
    });

    const result = parseResult(await importObservationsTool.handler({
      submission_id: 'sub-001', reviewer: 'Claude', dry_run: false,
    }));
    expect(result.actions[0].type).toBe('create_plant');
    expect(result.actions[0].result).toBe('created');
  });

  it('Case C: inventory update → creates observation', async () => {
    const plant = makePlantAsset({ name: '25 APR 2025 - Pigeon Pea - P2R3.15-21', inventoryCount: 5 });
    mockClient.getPlantAssets.mockResolvedValue([plant]);
    mockObsClient.listObservations.mockResolvedValue({
      success: true,
      observations: [makeObservation({
        species: 'Pigeon Pea', newCount: 3, previousCount: 5,
      })],
    });

    const result = parseResult(await importObservationsTool.handler({
      submission_id: 'sub-001', reviewer: 'Claude', dry_run: false,
    }));
    expect(result.total_actions).toBe(1);
    expect(result.actions[0].type).toBe('observation');
    expect(result.actions[0].previous_count).toBe(5);
    expect(result.actions[0].new_count).toBe(3);
  });

  // ── Status validation ────────────────────────────────────

  it('rejects pending status', async () => {
    mockObsClient.listObservations.mockResolvedValue({
      success: true,
      observations: [makeObservation({ species: 'Pigeon Pea', status: 'pending' })],
    });

    const result = parseResult(await importObservationsTool.handler({
      submission_id: 'sub-001', reviewer: 'Claude', dry_run: false,
    }));
    expect(result.error).toContain('unexpected statuses');
  });

  it('accepts approved status', async () => {
    mockObsClient.listObservations.mockResolvedValue({
      success: true,
      observations: [makeObservation({ species: '', sectionNotes: 'All good', status: 'approved' })],
    });

    const result = parseResult(await importObservationsTool.handler({
      submission_id: 'sub-001', reviewer: 'Claude', dry_run: false,
    }));
    expect(result).not.toHaveProperty('error');
    expect(result.total_actions).toBe(1);
  });

  // ── Sheet lifecycle ───────────────────────────────────────

  it('updates sheet status to imported after success', async () => {
    mockObsClient.listObservations.mockResolvedValue({
      success: true,
      observations: [makeObservation({ species: '', sectionNotes: 'Mulch needed' })],
    });

    await importObservationsTool.handler({
      submission_id: 'sub-001', reviewer: 'Claude', dry_run: false,
    });
    expect(mockObsClient.updateStatus).toHaveBeenCalled();
    const call = mockObsClient.updateStatus.mock.calls[0][0][0];
    expect(call.submission_id).toBe('sub-001');
    expect(call.status).toBe('imported');
  });

  it('handles sheet status update failure gracefully', async () => {
    mockObsClient.listObservations.mockResolvedValue({
      success: true,
      observations: [makeObservation({ species: '', sectionNotes: 'Test' })],
    });
    mockObsClient.updateStatus.mockRejectedValue(new Error('Sheet API down'));

    const result = parseResult(await importObservationsTool.handler({
      submission_id: 'sub-001', reviewer: 'Claude', dry_run: false,
    }));
    expect(result.sheet_status).toBe('partial');
    expect(result.errors).toEqual(expect.arrayContaining([expect.stringContaining('Sheet status')]));
  });

  // ── Dry run ───────────────────────────────────────────────

  it('dry run previews without creating', async () => {
    mockObsClient.listObservations.mockResolvedValue({
      success: true,
      observations: [
        makeObservation({ species: '', sectionNotes: 'Weeds' }),
        makeObservation({ species: 'Pigeon Pea', newCount: 3, previousCount: 5 }),
      ],
    });
    mockClient.getPlantAssets.mockResolvedValue([
      makePlantAsset({ name: '25 APR 2025 - Pigeon Pea - P2R3.15-21' }),
    ]);

    const result = parseResult(await importObservationsTool.handler({
      submission_id: 'sub-001', reviewer: 'Claude', dry_run: true,
    }));
    expect(result.dry_run).toBe(true);
    expect(result.total_actions).toBe(2);
    expect(result.actions.every((a: any) => a.result === 'dry_run')).toBe(true);
    expect(mockClient.createActivityLog).not.toHaveBeenCalled();
    expect(mockClient.createObservationLog).not.toHaveBeenCalled();
    expect(mockObsClient.updateStatus).not.toHaveBeenCalled();
  });

  // ── Error resilience ──────────────────────────────────────

  it('returns error for empty submission', async () => {
    mockObsClient.listObservations.mockResolvedValue({
      success: true, observations: [],
    });

    const result = parseResult(await importObservationsTool.handler({
      submission_id: 'sub-999', reviewer: 'Claude', dry_run: false,
    }));
    expect(result.error).toContain('No observations found');
  });

  it('continues when one action fails', async () => {
    mockObsClient.listObservations.mockResolvedValue({
      success: true,
      observations: [
        makeObservation({ species: '', sectionNotes: 'Activity note' }),
        makeObservation({ species: 'Macadamia', mode: 'new_plant', newCount: 2, previousCount: 0 }),
      ],
    });
    // Activity succeeds, plant creation fails
    mockClient.createActivityLog.mockResolvedValue('activity-id');
    mockClient.getPlantTypeUuid.mockResolvedValueOnce('type-uuid-1'); // first call for macadamia
    mockClient.createPlantAsset.mockRejectedValue(new Error('farmOS 500'));

    const result = parseResult(await importObservationsTool.handler({
      submission_id: 'sub-001', reviewer: 'Claude', dry_run: false,
    }));
    expect(result.total_actions).toBe(2);
    expect(result.actions[0].result).toBe('created');
    expect(result.actions[1].result).toBe('error');
    expect(result.errors).toHaveLength(1);
    expect(result.errors[0]).toContain('Macadamia');
  });
});
