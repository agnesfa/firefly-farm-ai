/**
 * Tests for seed bank tools: create_seed and sync_seed_transactions.
 * Follows the same mock-injection pattern as tools-write.test.ts.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

// ── Mock client ──────────────────────────────────────────────
const mockClient = {
  getPlantTypeUuid: vi.fn(),
  seedAssetExists: vi.fn(),
  createSeedAsset: vi.fn(),
  createSeedQuantity: vi.fn(),
  createSeedObservationLog: vi.fn(),
  fetchByName: vi.fn(),
  getSeedAssets: vi.fn(),
  logExists: vi.fn(),
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

// ── Imports (AFTER mock setup) ───────────────────────────────
import { createSeedTool } from '../tools/create-seed.js';
import { syncSeedTransactionsTool } from '../tools/sync-seed-transactions.js';

function parseResult(result: any): any {
  return JSON.parse(result.content[0].text);
}

// ═══════════════════════════════════════════════════════════════
// CREATE SEED TOOL
// ═══════════════════════════════════════════════════════════════

describe('create_seed', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('has correct metadata', () => {
    expect(createSeedTool.namespace).toBe('fc');
    expect(createSeedTool.name).toBe('create_seed');
    expect(createSeedTool.options?.readOnlyHint).toBe(false);
  });

  it('creates new seed asset with grams quantity', async () => {
    mockClient.getPlantTypeUuid.mockResolvedValue('pt-uuid-1');
    mockClient.seedAssetExists.mockResolvedValue(null);
    mockClient.createSeedAsset.mockResolvedValue('new-seed-id');
    mockClient.createSeedQuantity.mockResolvedValue('qty-id-1');
    mockClient.createSeedObservationLog.mockResolvedValue('log-id-1');

    const result = parseResult(await createSeedTool.handler({
      species: 'Pigeon Pea',
      quantity_grams: 500,
      source: 'Greenpatch',
      source_type: 'commercial',
      notes: 'Organic certified',
      date: '2026-03-13',
    }));

    expect(result.status).toBe('created');
    expect(result.seed.id).toBe('new-seed-id');
    expect(result.seed.name).toBe('Pigeon Pea Seeds');
    expect(result.inventory.quantity_grams).toBe(500);
    expect(result.inventory.adjustment).toBe('reset');
    expect(result.source_type).toBe('commercial');

    expect(mockClient.createSeedAsset).toHaveBeenCalledWith(
      'Pigeon Pea Seeds', 'pt-uuid-1', expect.stringContaining('Greenpatch'),
    );
    expect(mockClient.createSeedQuantity).toHaveBeenCalledWith('new-seed-id', 500, 'grams', 'reset');
    expect(mockClient.createSeedObservationLog).toHaveBeenCalledWith(
      'new-seed-id', 'qty-id-1', expect.any(Number),
      expect.stringContaining('Seedbank addition'), expect.any(String),
    );
  });

  it('restocks existing seed asset with increment', async () => {
    mockClient.getPlantTypeUuid.mockResolvedValue('pt-uuid-1');
    mockClient.seedAssetExists.mockResolvedValue('existing-seed-id');
    mockClient.createSeedQuantity.mockResolvedValue('qty-id-2');
    mockClient.createSeedObservationLog.mockResolvedValue('log-id-2');

    const result = parseResult(await createSeedTool.handler({
      species: 'Pigeon Pea',
      quantity_grams: 200,
      source: 'Farm harvest P2R3',
      source_type: 'harvest',
    }));

    expect(result.status).toBe('restocked');
    expect(result.seed.id).toBe('existing-seed-id');
    expect(result.inventory.adjustment).toBe('increment');
    expect(result.source_type).toBe('harvest');

    // Should NOT create a new seed asset
    expect(mockClient.createSeedAsset).not.toHaveBeenCalled();
    expect(mockClient.createSeedQuantity).toHaveBeenCalledWith('existing-seed-id', 200, 'grams', 'increment');
  });

  it('creates seed with stock_level for sachet seeds', async () => {
    mockClient.getPlantTypeUuid.mockResolvedValue('pt-uuid-2');
    mockClient.seedAssetExists.mockResolvedValue(null);
    mockClient.createSeedAsset.mockResolvedValue('sachet-seed-id');
    mockClient.createSeedQuantity.mockResolvedValue('qty-id-3');
    mockClient.createSeedObservationLog.mockResolvedValue('log-id-3');

    const result = parseResult(await createSeedTool.handler({
      species: 'Tomato (Marmande)',
      stock_level: 'full',
      source: 'EDEN Seeds',
    }));

    expect(result.status).toBe('created');
    expect(result.inventory.stock_level).toBe('full');
    expect(mockClient.createSeedQuantity).toHaveBeenCalledWith('sachet-seed-id', 1, 'stock_level', 'reset');
  });

  it('errors when plant type not found', async () => {
    mockClient.getPlantTypeUuid.mockResolvedValue(null);

    const result = parseResult(await createSeedTool.handler({
      species: 'Nonexistent Plant',
      quantity_grams: 100,
    }));

    expect(result.error).toContain('not found');
    expect(mockClient.createSeedAsset).not.toHaveBeenCalled();
  });

  it('errors when neither quantity_grams nor stock_level provided', async () => {
    mockClient.getPlantTypeUuid.mockResolvedValue('pt-uuid-1');

    const result = parseResult(await createSeedTool.handler({
      species: 'Pigeon Pea',
    }));

    expect(result.error).toContain('quantity_grams');
    expect(mockClient.createSeedAsset).not.toHaveBeenCalled();
  });

  it('defaults source_type to commercial', async () => {
    mockClient.getPlantTypeUuid.mockResolvedValue('pt-uuid-1');
    mockClient.seedAssetExists.mockResolvedValue(null);
    mockClient.createSeedAsset.mockResolvedValue('seed-id');
    mockClient.createSeedQuantity.mockResolvedValue('qty-id');
    mockClient.createSeedObservationLog.mockResolvedValue('log-id');

    const result = parseResult(await createSeedTool.handler({
      species: 'Comfrey',
      quantity_grams: 50,
    }));

    expect(result.source_type).toBe('commercial');
  });

  it('handles exchange source_type', async () => {
    mockClient.getPlantTypeUuid.mockResolvedValue('pt-uuid-1');
    mockClient.seedAssetExists.mockResolvedValue(null);
    mockClient.createSeedAsset.mockResolvedValue('seed-id');
    mockClient.createSeedQuantity.mockResolvedValue('qty-id');
    mockClient.createSeedObservationLog.mockResolvedValue('log-id');

    const result = parseResult(await createSeedTool.handler({
      species: 'Comfrey',
      quantity_grams: 50,
      source: 'Minimba Farm',
      source_type: 'exchange',
    }));

    expect(result.source_type).toBe('exchange');
    expect(result.source).toBe('Minimba Farm');
  });
});

// ═══════════════════════════════════════════════════════════════
// SYNC SEED TRANSACTIONS TOOL
// ═══════════════════════════════════════════════════════════════

describe('sync_seed_transactions', () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
    fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
  });

  const makeSheetResponse = (transactions: any[]) => ({
    ok: true,
    json: () => Promise.resolve({ success: true, transactions }),
  });

  const makeSeedAsset = (name: string, inventory = 1000) => ({
    id: `seed-${name.toLowerCase().replace(/\s/g, '-')}`,
    attributes: {
      name: `${name} Seeds`,
      inventory: [{ value: String(inventory), measure: 'weight' }],
    },
  });

  it('has correct metadata', () => {
    expect(syncSeedTransactionsTool.namespace).toBe('fc');
    expect(syncSeedTransactionsTool.name).toBe('sync_seed_transactions');
  });

  it('syncs a take transaction', async () => {
    const transactions = [{
      seed: 'Pigeon Pea', type: 'take', amount: '150',
      user: 'James', date: '2026-03-21 14:30', notes: 'For P2R3',
    }];
    fetchSpy.mockResolvedValueOnce(makeSheetResponse(transactions));

    const seedAsset = makeSeedAsset('Pigeon Pea');
    mockClient.fetchByName.mockResolvedValue([seedAsset]);
    mockClient.logExists.mockResolvedValue(null);
    mockClient.createSeedQuantity.mockResolvedValue('qty-1');
    mockClient.createSeedObservationLog.mockResolvedValue('log-1');

    const result = parseResult(await syncSeedTransactionsTool.handler({ days: 7, dry_run: false }));

    expect(result.synced).toBe(1);
    expect(result.failed).toBe(0);
    expect(result.details.synced[0].seed).toBe('Pigeon Pea');
    expect(result.details.synced[0].type).toBe('take');

    // Verify quantity was negative (take = decrement)
    expect(mockClient.createSeedQuantity).toHaveBeenCalledWith(
      seedAsset.id, -150, 'grams', 'increment',
    );
  });

  it('syncs an add transaction', async () => {
    const transactions = [{
      seed: 'Comfrey', type: 'add', amount: '200',
      user: 'Claire', date: '2026-04-01 10:00', notes: 'Harvest saved',
    }];
    fetchSpy.mockResolvedValueOnce(makeSheetResponse(transactions));

    const seedAsset = makeSeedAsset('Comfrey', 500);
    mockClient.fetchByName.mockResolvedValue([seedAsset]);
    mockClient.logExists.mockResolvedValue(null);
    mockClient.createSeedQuantity.mockResolvedValue('qty-2');
    mockClient.createSeedObservationLog.mockResolvedValue('log-2');

    const result = parseResult(await syncSeedTransactionsTool.handler({ days: 7 }));

    expect(result.synced).toBe(1);
    // Verify quantity was positive (add)
    expect(mockClient.createSeedQuantity).toHaveBeenCalledWith(
      seedAsset.id, 200, 'grams', 'increment',
    );
  });

  it('skips already-synced transactions (idempotency)', async () => {
    fetchSpy.mockResolvedValueOnce(makeSheetResponse([{
      seed: 'Pigeon Pea', type: 'take', amount: '100',
      user: 'James', date: '2026-03-20 09:00', notes: '',
    }]));

    mockClient.fetchByName.mockResolvedValue([makeSeedAsset('Pigeon Pea')]);
    mockClient.logExists.mockResolvedValue('existing-log-id'); // Already synced

    const result = parseResult(await syncSeedTransactionsTool.handler({ days: 7 }));

    expect(result.synced).toBe(0);
    expect(result.skipped).toBe(1);
    expect(result.details.skipped[0].reason).toBe('Already synced');
    expect(mockClient.createSeedQuantity).not.toHaveBeenCalled();
  });

  it('reports failed when seed asset not found', async () => {
    fetchSpy.mockResolvedValueOnce(makeSheetResponse([{
      seed: 'Unknown Seed', type: 'take', amount: '50',
      user: 'James', date: '2026-03-25 11:00', notes: '',
    }]));

    mockClient.fetchByName.mockResolvedValue([]);
    mockClient.getSeedAssets.mockResolvedValue([]);

    const result = parseResult(await syncSeedTransactionsTool.handler({ days: 7 }));

    expect(result.failed).toBe(1);
    expect(result.details.failed[0].reason).toContain('not found');
  });

  it('dry_run mode shows changes without creating', async () => {
    fetchSpy.mockResolvedValueOnce(makeSheetResponse([{
      seed: 'Pigeon Pea', type: 'take', amount: '300',
      user: 'James', date: '2026-03-31 12:00', notes: 'P2R5',
    }]));

    mockClient.fetchByName.mockResolvedValue([makeSeedAsset('Pigeon Pea', 5000)]);
    mockClient.logExists.mockResolvedValue(null);

    const result = parseResult(await syncSeedTransactionsTool.handler({ days: 7, dry_run: true }));

    expect(result.dry_run).toBe(true);
    expect(result.synced).toBe(1);
    expect(result.details.synced[0].dry_run).toBe(true);
    expect(result.details.synced[0].current_inventory).toBe(5000);
    expect(result.details.synced[0].new_inventory).toBe(4700);

    // Should NOT create anything
    expect(mockClient.createSeedQuantity).not.toHaveBeenCalled();
    expect(mockClient.createSeedObservationLog).not.toHaveBeenCalled();
  });

  it('handles empty transaction list', async () => {
    fetchSpy.mockResolvedValueOnce(makeSheetResponse([]));

    const result = parseResult(await syncSeedTransactionsTool.handler({ days: 7 }));

    expect(result.synced).toBe(0);
    expect(result.message).toContain('No transactions');
  });

  it('handles Sheet API error', async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ success: false, error: 'Sheet not found' }),
    });

    const result = parseResult(await syncSeedTransactionsTool.handler({ days: 7 }));

    expect(result.error).toContain('Sheet not found');
  });
});
