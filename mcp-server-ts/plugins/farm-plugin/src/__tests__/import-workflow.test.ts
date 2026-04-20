/**
 * Layer 3c: Import observations composite workflow tests.
 * Mirrors Python test_import_workflow.py (12 tests).
 * Tests case routing (A/B/C), status validation, dry run, error resilience.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { makePlantAsset, makeObservation } from './fixtures.js';

// Populated plant_type taxonomy used by buildBotanicalLookupResilient.
// Description format matches parsePlantTypeMetadata's expected schema.
const MOCK_PLANT_TYPES = [
  {
    id: 'pt-uuid-pigeonpea',
    attributes: {
      name: 'Pigeon Pea',
      description: {
        value: 'Syntropic Agriculture Data\n**Botanical Name:** Cajanus cajan\n**Strata:** high',
      },
    },
  },
];

const mockClient = {
  fetchByName: vi.fn(),
  getPlantAssets: vi.fn(),
  getSectionUuid: vi.fn().mockResolvedValue('section-uuid-1'),
  getSectionType: vi.fn().mockResolvedValue('asset--land'),
  getPlantTypeUuid: vi.fn().mockResolvedValue('type-uuid-1'),
  getAllPlantTypesCached: vi.fn().mockResolvedValue(MOCK_PLANT_TYPES),
  plantAssetExists: vi.fn().mockResolvedValue(null),
  logExists: vi.fn().mockResolvedValue(null),
  createQuantity: vi.fn().mockResolvedValue('qty-id'),
  createObservationLog: vi.fn().mockResolvedValue('obs-log-id'),
  createActivityLog: vi.fn().mockResolvedValue('activity-log-id'),
  createPlantAsset: vi.fn().mockResolvedValue('new-plant-id'),
  updatePlantType: vi.fn().mockResolvedValue(true),
  archivePlant: vi.fn(),
  uploadFile: vi.fn().mockResolvedValue('file-uuid'),
  connect: vi.fn(),
  isConnected: true,
};

// Photo pipeline needs a non-empty PlantNet key to attempt verification
// (the mocked verifySpeciesPhoto will always approve). Without this the
// pipeline short-circuits at the "no_api_key" check and nothing gets
// promoted as species reference photo.
process.env.PLANTNET_API_KEY = process.env.PLANTNET_API_KEY || 'test-plantnet-key';

const mockObsClient = {
  listObservations: vi.fn(),
  updateStatus: vi.fn().mockResolvedValue({ success: true }),
  deleteImported: vi.fn().mockResolvedValue({ success: true }),
  getMedia: vi.fn(),
};

vi.mock('../clients/index.js', () => ({
  getFarmOSClient: () => mockClient,
  getObserveClient: () => mockObsClient,
  getMemoryClient: () => null,
  getPlantTypesClient: () => null,
  getKnowledgeClient: () => null,
}));

// Bypass PlantNet verification in tests — always approve photos.
vi.mock('../helpers/plantnet-verify.js', () => ({
  buildBotanicalLookupFromCsv: () => ({ forward: new Map(), reverse: new Map() }),
  verifySpeciesPhoto: async () => ({ verified: true, plantnetTop: '', confidence: 1.0, reason: 'test_bypass' }),
  getPlantnetCallCount: () => 0,
  resetPlantnetCallCount: () => {},
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

  it('empty submission is treated as already-imported (ADR 0007 Fix 2 idempotency)', async () => {
    mockObsClient.listObservations.mockResolvedValue({
      success: true, observations: [],
    });

    const result = parseResult(await importObservationsTool.handler({
      submission_id: 'sub-999', reviewer: 'Claude', dry_run: false,
    }));
    // Not an error — delete_imported may have cleaned up rows after a prior
    // successful import. Retries must be safe.
    expect(result.error).toBeUndefined();
    expect(result.status).toBe('already_imported_or_unknown');
    expect(result.actions).toBe(0);
  });

  it('all-imported submission is skipped gracefully (ADR 0007 Fix 2)', async () => {
    mockObsClient.listObservations.mockResolvedValue({
      success: true,
      observations: [
        makeObservation({ species: 'Pigeon Pea', status: 'imported' }),
      ],
    });

    const result = parseResult(await importObservationsTool.handler({
      submission_id: 'sub-already-done', reviewer: 'Claude', dry_run: false,
    }));
    expect(result.error).toBeUndefined();
    expect(result.status).toBe('already_imported');
    expect(result.actions).toBe(0);
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

// ── Photo pipeline ──────────────────────────────────────────
//
// Mirrors the Python TestPhotoPipeline class in test_import_workflow.py.
// Locks in Steps 1+2 of photo-pipeline-and-plant-id-design.md on the
// TypeScript side: photos fetched once per submission, attached to each
// log, species reference refresh, failure resilience.

const TINY_PNG_B64 =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';
// Distinct payloads are required for tests that attach multiple files
// to the same log — ADR 0008 I4 dedup (photo-pipeline.ts) now skips
// same-filesize attachments. Counters indexed by the filename's last
// char keep each fixture call distinct.
const TINY_PNG_VARIANTS = [
  TINY_PNG_B64,
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQg==',
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggkNDQ0NDQ0NDQw==',
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggkREREREREREREREREREREREQ==',
];
let mediaFileCounter = 0;
function mediaFile(filename = 'photo.jpg', b64?: string) {
  const data_base64 = b64 ?? TINY_PNG_VARIANTS[(mediaFileCounter++) % TINY_PNG_VARIANTS.length];
  return { filename, mime_type: 'image/jpeg', data_base64 };
}

describe('import_observations photo pipeline', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockClient.getSectionUuid.mockResolvedValue('section-uuid-1');
    mockClient.getPlantTypeUuid.mockResolvedValue('pt-uuid-pigeonpea');
    mockClient.plantAssetExists.mockResolvedValue(null);
    mockClient.logExists.mockResolvedValue(null);
    mockClient.createObservationLog.mockResolvedValue('obs-log-id');
    mockClient.createActivityLog.mockResolvedValue('activity-log-id');
    mockClient.createPlantAsset.mockResolvedValue('new-plant-id');
    mockClient.uploadFile.mockResolvedValue('file-uuid');
    mockObsClient.updateStatus.mockResolvedValue({ success: true });
    mockObsClient.deleteImported.mockResolvedValue({ success: true });
  });

  it('Case A: photos attached to activity log, no species refresh', async () => {
    mockObsClient.listObservations.mockResolvedValue({
      success: true,
      observations: [
        makeObservation({
          species: '',
          sectionNotes: 'Weeds growing',
          mediaFiles: 'first.jpg,second.jpg',
        }),
      ],
    });
    mockObsClient.getMedia.mockResolvedValue({
      success: true,
      files: [mediaFile('first.jpg'), mediaFile('second.jpg')],
    });

    const result = parseResult(
      await importObservationsTool.handler({
        submission_id: 'sub-photo-a',
        reviewer: 'Claude',
        dry_run: false,
      }),
    );

    expect(mockObsClient.getMedia).toHaveBeenCalledWith('sub-photo-a');
    expect(result.photos_uploaded).toBe(2);
    expect(result.submission_media_fetched).toBe(2);
    expect(result.species_reference_photos_updated).toBe(0);
    expect(result.actions[0].photos_uploaded).toBe(2);

    // Both files went to the activity log
    const calls = mockClient.uploadFile.mock.calls;
    expect(calls).toHaveLength(2);
    expect(calls[0][0]).toBe('log/activity');
    expect(calls[0][1]).toBe('activity-log-id');
    expect(calls[0][2]).toBe('image');
  });

  it('Case C: photos on observation log + species reference refresh', async () => {
    mockObsClient.listObservations.mockResolvedValue({
      success: true,
      observations: [
        makeObservation({
          species: 'Pigeon Pea',
          newCount: 4,
          previousCount: 3,
          // Tier-3 plant-specific filenames so ADR 0008 I5 gate allows
          // species-reference promotion.
          mediaFiles: 'abc12345_P2R3.15-21_plant_001.jpg,def67890_P2R3.15-21_plant_002.jpg',
        }),
      ],
    });
    mockObsClient.getMedia.mockResolvedValue({
      success: true,
      files: [
        mediaFile('abc12345_P2R3.15-21_plant_001.jpg'),
        mediaFile('def67890_P2R3.15-21_plant_002.jpg'),
      ],
    });
    mockClient.getPlantAssets.mockResolvedValue([
      makePlantAsset({ name: '25 APR 2025 - Pigeon Pea - P2R3.15-21' }),
    ]);

    const result = parseResult(
      await importObservationsTool.handler({
        submission_id: 'sub-photo-c',
        reviewer: 'Claude',
        dry_run: false,
      }),
    );

    expect(result.photos_uploaded).toBe(2);
    expect(result.species_reference_photos_updated).toBe(1);
    expect(result.photo_pipeline.verification.plantnet_key_present).toBe(true);
    expect(result.photo_pipeline.verification.botanical_lookup_size).toBeGreaterThan(0);
    expect(result.photo_pipeline.verification.photos_verified).toBeGreaterThanOrEqual(1);
    expect(result.photo_pipeline.upload_errors).toEqual([]);

    const calls = mockClient.uploadFile.mock.calls;
    const logCalls = calls.filter((c: any[]) => c[0] === 'log/observation');
    const taxoCalls = calls.filter((c: any[]) => c[0] === 'taxonomy_term/plant_type');
    expect(logCalls).toHaveLength(2);
    expect(logCalls[0][1]).toBe('obs-log-id');
    expect(taxoCalls).toHaveLength(1);
    expect(taxoCalls[0][1]).toBe('pt-uuid-pigeonpea');
  });

  it('no media_files → get_media is never called', async () => {
    mockObsClient.listObservations.mockResolvedValue({
      success: true,
      observations: [makeObservation({ species: '', sectionNotes: 'No photo' })],
    });

    const result = parseResult(
      await importObservationsTool.handler({
        submission_id: 'sub-no-media',
        reviewer: 'Claude',
        dry_run: false,
      }),
    );

    expect(mockObsClient.getMedia).not.toHaveBeenCalled();
    expect(result.photos_uploaded).toBe(0);
    expect(result.submission_media_fetched).toBe(0);
  });

  it('upload_file failure does not block import', async () => {
    mockObsClient.listObservations.mockResolvedValue({
      success: true,
      observations: [
        makeObservation({
          species: '',
          sectionNotes: 'Photo upload will fail',
          mediaFiles: 'photo.jpg',
        }),
      ],
    });
    mockObsClient.getMedia.mockResolvedValue({
      success: true,
      files: [mediaFile('photo.jpg')],
    });
    mockClient.uploadFile.mockRejectedValue(new Error('farmOS down'));

    const result = parseResult(
      await importObservationsTool.handler({
        submission_id: 'sub-photo-fail',
        reviewer: 'Claude',
        dry_run: false,
      }),
    );

    expect(result.total_actions).toBe(1);
    expect(result.actions[0].result).toBe('created');
    expect(result.photos_uploaded).toBe(0);
    // Photo failures don't surface as top-level errors but they DO
    // surface in photo_pipeline.upload_errors so the operator sees them.
    expect(result.errors).toBeNull();
    expect(result.photo_pipeline.upload_errors.length).toBeGreaterThan(0);
    expect(result.photo_pipeline.upload_errors[0]).toMatch(/upload_threw.*farmOS down/);
    expect(result.photo_pipeline.warnings).toBeTruthy();
  });

  it('verification degradation does NOT block photo upload (regression: Leah Apr 14 walk)', async () => {
    // This is the bug that silently broke Leah's field walk. Before the
    // April 15 redesign, a failing PlantNet gate meant photos never
    // reached the log. The new design uploads first, verifies after —
    // photos always make it to the log even when PlantNet is down.
    const originalKey = process.env.PLANTNET_API_KEY;
    process.env.PLANTNET_API_KEY = '';  // simulate missing key on Railway

    mockObsClient.listObservations.mockResolvedValue({
      success: true,
      observations: [
        makeObservation({
          species: 'Pigeon Pea',
          newCount: 4,
          previousCount: 3,
          mediaFiles: 'a.jpg,b.jpg,c.jpg',
        }),
      ],
    });
    mockObsClient.getMedia.mockResolvedValue({
      success: true,
      files: [mediaFile('a.jpg'), mediaFile('b.jpg'), mediaFile('c.jpg')],
    });
    mockClient.getPlantAssets.mockResolvedValue([
      makePlantAsset({ name: '25 APR 2025 - Pigeon Pea - P2R3.15-21' }),
    ]);

    const result = parseResult(
      await importObservationsTool.handler({
        submission_id: 'sub-verification-off',
        reviewer: 'Claude',
        dry_run: false,
      }),
    );

    // Photos attach unconditionally
    expect(result.photos_uploaded).toBe(3);
    expect(result.actions[0].photos_uploaded).toBe(3);
    // Verification was skipped (no key)
    expect(result.photo_pipeline.verification.plantnet_key_present).toBe(false);
    expect(result.photo_pipeline.verification.plantnet_api_calls).toBe(0);
    expect(result.photo_pipeline.verification.photos_verified).toBe(0);
    // Species reference photo is NOT promoted because verification couldn't run
    expect(result.species_reference_photos_updated).toBe(0);
    // Upload errors are empty because the uploads actually worked
    expect(result.photo_pipeline.upload_errors).toEqual([]);

    process.env.PLANTNET_API_KEY = originalKey;
  });

  it('undecodable base64 is skipped without crashing', async () => {
    mockObsClient.listObservations.mockResolvedValue({
      success: true,
      observations: [
        makeObservation({
          species: '',
          sectionNotes: 'Corrupt photo',
          mediaFiles: 'broken.jpg',
        }),
      ],
    });
    mockObsClient.getMedia.mockResolvedValue({
      success: true,
      files: [{ filename: 'broken.jpg', mime_type: 'image/jpeg', data_base64: '@@not-base64@@' }],
    });

    const result = parseResult(
      await importObservationsTool.handler({
        submission_id: 'sub-photo-corrupt',
        reviewer: 'Claude',
        dry_run: false,
      }),
    );

    // Buffer.from('@@not-base64@@', 'base64') returns a non-empty buffer
    // (it just ignores invalid chars), so we can't rely on decodeMediaFile
    // returning null here. What matters is the import still completes.
    expect(result.total_actions).toBe(1);
    expect(result.actions[0].result).toBe('created');
  });
});
