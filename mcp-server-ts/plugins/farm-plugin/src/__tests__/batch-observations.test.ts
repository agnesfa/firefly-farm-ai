/**
 * Tests for the batch observation tools:
 *   - update_observation_status_batch
 *   - import_observations_batch
 *
 * The batch tools exist to collapse many tool calls into one for
 * multi-submission flows (the classic trigger being Leah's April 14
 * walk, where a ~15-submission import required ~45 tool calls through
 * the single-submission tools). See ADR (TBD, written in a follow-up).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

// ── Mocks ────────────────────────────────────────────────────

const mockObsClient = {
  listObservations: vi.fn(),
  updateStatus: vi.fn().mockResolvedValue({ success: true, updated: 0 }),
  deleteImported: vi.fn().mockResolvedValue({ success: true }),
  getMedia: vi.fn(),
};

const mockFarmOSClient = {
  getPlantAssets: vi.fn(),
  getSectionUuid: vi.fn().mockResolvedValue('section-uuid'),
  getPlantTypeUuid: vi.fn().mockResolvedValue('pt-uuid'),
  getAllPlantTypesCached: vi.fn().mockResolvedValue([]),
  plantAssetExists: vi.fn().mockResolvedValue(null),
  logExists: vi.fn().mockResolvedValue(null),
  createQuantity: vi.fn().mockResolvedValue('qty-id'),
  createObservationLog: vi.fn().mockResolvedValue('obs-log-id'),
  createActivityLog: vi.fn().mockResolvedValue('activity-log-id'),
  createPlantAsset: vi.fn().mockResolvedValue('plant-id'),
  updatePlantType: vi.fn().mockResolvedValue(true),
  uploadFile: vi.fn().mockResolvedValue('file-uuid'),
};

vi.mock('../clients/index.js', () => ({
  getFarmOSClient: () => mockFarmOSClient,
  getObserveClient: () => mockObsClient,
  getMemoryClient: () => null,
  getPlantTypesClient: () => null,
  getKnowledgeClient: () => null,
}));

vi.mock('../helpers/plantnet-verify.js', () => ({
  buildBotanicalLookupFromCsv: () => ({ forward: new Map(), reverse: new Map() }),
  verifySpeciesPhoto: async () => ({ verified: true, plantnetTop: '', confidence: 1.0, reason: 'test' }),
  getPlantnetCallCount: () => 0,
  resetPlantnetCallCount: () => {},
}));

import { updateObservationStatusBatchTool } from '../tools/update-observation-status-batch.js';
import { importObservationsBatchTool } from '../tools/import-observations-batch.js';

function parse(result: any): any {
  return JSON.parse(result.content[0].text);
}

function makeObservation(overrides: any = {}): any {
  return {
    submission_id: 'sub-1',
    species: 'Pigeon Pea',
    section_id: 'P2R3.15-21',
    mode: 'quick',
    status: 'approved',
    media_files: '',
    new_count: 3,
    previous_count: 3,
    condition: 'alive',
    plant_notes: '',
    section_notes: '',
    timestamp: '2026-04-15T10:00:00Z',
    observer: 'Leah',
    ...overrides,
  };
}

// ── update_observation_status_batch ───────────────────────────

describe('update_observation_status_batch', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockObsClient.updateStatus.mockResolvedValue({ success: true, updated: 3 });
  });

  it('sends one updateStatus call with N entries', async () => {
    const result = parse(
      await updateObservationStatusBatchTool.handler({
        submission_ids: ['sub-a', 'sub-b', 'sub-c'],
        new_status: 'approved',
        reviewer: 'Claude',
        notes: 'batch',
      } as any, undefined as any),
    );

    expect(mockObsClient.updateStatus).toHaveBeenCalledTimes(1);
    expect(mockObsClient.updateStatus.mock.calls[0][0]).toHaveLength(3);
    expect(mockObsClient.updateStatus.mock.calls[0][0][0]).toEqual({
      submission_id: 'sub-a',
      status: 'approved',
      reviewer: 'Claude',
      notes: 'batch',
    });
    expect(result.status).toBe('updated');
    expect(result.submission_count).toBe(3);
    expect(result.submission_ids).toEqual(['sub-a', 'sub-b', 'sub-c']);
  });

  it('deduplicates submission_ids', async () => {
    await updateObservationStatusBatchTool.handler({
      submission_ids: ['sub-a', 'sub-a', 'sub-b', 'sub-a'],
      new_status: 'approved',
      reviewer: 'Claude',
      notes: '',
    } as any, undefined as any);

    expect(mockObsClient.updateStatus.mock.calls[0][0]).toHaveLength(2);
  });

  it('rejects invalid status values', async () => {
    const result = parse(
      await updateObservationStatusBatchTool.handler({
        submission_ids: ['sub-a'],
        new_status: 'wibble',
        reviewer: 'Claude',
        notes: '',
      } as any, undefined as any),
    );
    expect(result.error).toMatch(/Invalid status/);
    expect(mockObsClient.updateStatus).not.toHaveBeenCalled();
  });

  it('surfaces update_status errors back to the caller', async () => {
    mockObsClient.updateStatus.mockResolvedValue({ success: false, error: 'sheet locked' });
    const result = parse(
      await updateObservationStatusBatchTool.handler({
        submission_ids: ['sub-a', 'sub-b'],
        new_status: 'approved',
        reviewer: 'Claude',
        notes: '',
      } as any, undefined as any),
    );
    expect(result.error).toContain('sheet locked');
    expect(result.submission_ids).toEqual(['sub-a', 'sub-b']);
  });
});

// ── import_observations_batch ─────────────────────────────────

describe('import_observations_batch', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFarmOSClient.getPlantAssets.mockResolvedValue([
      {
        id: 'plant-1',
        attributes: { name: '25 APR 2025 - Pigeon Pea - P2R3.15-21' },
        relationships: {},
      },
    ]);
    mockFarmOSClient.logExists.mockResolvedValue(null);
    mockObsClient.updateStatus.mockResolvedValue({ success: true, updated: 1 });
    mockObsClient.deleteImported.mockResolvedValue({ success: true });
  });

  it('processes each submission once and aggregates results', async () => {
    // Each submission returns a different section_id so we can tell them apart
    mockObsClient.listObservations.mockImplementation(async (params: any) => ({
      success: true,
      observations: [
        makeObservation({
          submission_id: params.submission_id,
          section_id: `P2R3.${params.submission_id}`,
        }),
      ],
    }));

    const result = parse(
      await importObservationsBatchTool.handler({
        submission_ids: ['sub-1', 'sub-2', 'sub-3'],
        reviewer: 'Claude',
        dry_run: false,
        continue_on_error: true,
      } as any, undefined as any),
    );

    expect(result.submitted).toBe(3);
    expect(result.processed).toBe(3);
    expect(result.succeeded).toBe(3);
    expect(result.submissions).toHaveLength(3);
    expect(mockObsClient.listObservations).toHaveBeenCalledTimes(3);
  });

  it('continues past a failed submission when continue_on_error=true', async () => {
    let call = 0;
    mockObsClient.listObservations.mockImplementation(async () => {
      call++;
      if (call === 2) return { success: false, error: 'not found' };
      return { success: true, observations: [makeObservation()] };
    });

    const result = parse(
      await importObservationsBatchTool.handler({
        submission_ids: ['sub-1', 'sub-2', 'sub-3'],
        reviewer: 'Claude',
        dry_run: false,
        continue_on_error: true,
      } as any, undefined as any),
    );

    expect(result.processed).toBe(3);
    expect(result.succeeded).toBe(2);
    expect(result.status).toBe('partial');
    expect(result.errors).toBeTruthy();
  });

  it('aggregates photo_pipeline metrics across submissions', async () => {
    mockObsClient.listObservations.mockImplementation(async (params: any) => ({
      success: true,
      observations: [makeObservation({ submission_id: params.submission_id })],
    }));

    const result = parse(
      await importObservationsBatchTool.handler({
        submission_ids: ['sub-1', 'sub-2'],
        reviewer: 'Claude',
        dry_run: true,  // skip photo/media fetching
        continue_on_error: true,
      } as any, undefined as any),
    );

    expect(result.photo_pipeline).toBeDefined();
    expect(result.photo_pipeline.verification).toBeDefined();
    expect(result.photo_pipeline.media_files_fetched).toBe(0);  // dry run
  });
});
