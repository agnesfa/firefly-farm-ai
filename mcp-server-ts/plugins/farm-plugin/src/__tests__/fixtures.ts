/**
 * Test fixtures and factory functions — mirrors Python conftest.py.
 * Used across all test files for consistent farmOS mock data.
 */

let uuidCounter = 0;

export function makeUuid(): string {
  uuidCounter++;
  const hex = uuidCounter.toString(16).padStart(8, '0');
  return `${hex}-0000-0000-0000-000000000000`;
}

export function makePlantAsset(opts: {
  name?: string;
  uuid?: string;
  status?: string;
  inventoryCount?: number | null;
  plantTypeUuid?: string;
  notes?: string;
} = {}) {
  const uuid = opts.uuid ?? makeUuid();
  const inventory = opts.inventoryCount != null
    ? [{ measure: 'count', value: String(opts.inventoryCount), units: { name: 'plant' } }]
    : [];
  return {
    id: uuid,
    type: 'asset--plant',
    attributes: {
      name: opts.name ?? '25 APR 2025 - Pigeon Pea - P2R2.0-3',
      status: opts.status ?? 'active',
      notes: opts.notes ? { value: opts.notes, format: 'default' } : {},
      inventory,
    },
    relationships: {
      plant_type: {
        data: [{ type: 'taxonomy_term--plant_type', id: opts.plantTypeUuid ?? makeUuid() }],
      },
      location: { data: [] },
    },
  };
}

export function makeLog(opts: {
  name?: string;
  logType?: string;
  uuid?: string;
  timestamp?: string;
  notes?: string;
  quantities?: any[];
  assetIds?: string[];
  locationIds?: string[];
  isMovement?: boolean;
} = {}) {
  const uuid = opts.uuid ?? makeUuid();
  return {
    id: uuid,
    type: `log--${opts.logType ?? 'observation'}`,
    attributes: {
      name: opts.name ?? 'Test Log',
      timestamp: opts.timestamp ?? '1714003200',
      status: 'done',
      is_movement: opts.isMovement ?? false,
      notes: opts.notes ? { value: opts.notes, format: 'default' } : {},
    },
    relationships: {
      asset: { data: (opts.assetIds ?? []).map((id) => ({ type: 'asset--plant', id })) },
      location: { data: (opts.locationIds ?? []).map((id) => ({ type: 'asset--land', id })) },
      quantity: { data: [] },
    },
    _quantities: opts.quantities ?? [],
  };
}

export function makeQuantity(opts: {
  value?: number;
  measure?: string;
  adjustment?: string;
  label?: string;
  uuid?: string;
} = {}) {
  return {
    id: opts.uuid ?? makeUuid(),
    type: 'quantity--standard',
    attributes: {
      value: { decimal: String(opts.value ?? 5) },
      measure: opts.measure ?? 'count',
      inventory_adjustment: opts.adjustment ?? 'reset',
      label: opts.label ?? 'plants',
    },
  };
}

export function makePlantType(opts: {
  name?: string;
  uuid?: string;
  description?: string;
  maturityDays?: number;
  transplantDays?: number;
} = {}) {
  return {
    id: opts.uuid ?? makeUuid(),
    type: 'taxonomy_term--plant_type',
    attributes: {
      name: opts.name ?? 'Pigeon Pea',
      description: opts.description
        ? { value: opts.description, format: 'default' }
        : {},
      maturity_days: opts.maturityDays ?? null,
      transplant_days: opts.transplantDays ?? null,
    },
  };
}

export function makeSectionAsset(opts: {
  name?: string;
  uuid?: string;
} = {}) {
  return {
    id: opts.uuid ?? makeUuid(),
    type: 'asset--land',
    attributes: {
      name: opts.name ?? 'P2R3.15-21',
      status: 'active',
    },
  };
}

export function makeObservation(opts: {
  species?: string;
  sectionId?: string;
  observer?: string;
  newCount?: number | null;
  previousCount?: number | null;
  mode?: string;
  status?: string;
  submissionId?: string;
  sectionNotes?: string;
  plantNotes?: string;
  condition?: string;
  timestamp?: string;
  mediaFiles?: string;
} = {}) {
  return {
    species: opts.species ?? '',
    section_id: opts.sectionId ?? 'P2R3.15-21',
    observer: opts.observer ?? 'Claire',
    new_count: opts.newCount ?? null,
    previous_count: opts.previousCount ?? null,
    mode: opts.mode ?? 'full_inventory',
    status: opts.status ?? 'approved',
    submission_id: opts.submissionId ?? 'sub-001',
    section_notes: opts.sectionNotes ?? '',
    plant_notes: opts.plantNotes ?? '',
    condition: opts.condition ?? '',
    timestamp: opts.timestamp ?? '2026-03-09T03:15:00.000Z',
    media_files: opts.mediaFiles ?? '',
  };
}

/** Pre-built fixtures matching Python conftest */
export const pigeon_pea_asset = makePlantAsset({
  name: '25 APR 2025 - Pigeon Pea - P2R2.0-3',
  inventoryCount: 4,
});

export const basil_sweet_classic_asset = makePlantAsset({
  name: '25 APR 2025 - Basil - Sweet (Classic) - P2R3.15-21',
  inventoryCount: 2,
});
