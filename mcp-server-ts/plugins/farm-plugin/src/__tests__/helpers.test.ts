/**
 * Layer 1: Pure function tests — dates, names, formatters, plant-type-metadata.
 * Mirrors Python test_helpers.py (29 tests). Zero network, zero mocks.
 */

import { describe, it, expect } from 'vitest';
import { parseDate, formatPlantedLabel, buildAssetName, formatTimestamp } from '../helpers/dates.js';
import { parseAssetName } from '../helpers/names.js';
import { formatPlantAsset, formatLog, formatPlantType } from '../helpers/formatters.js';
import { buildPlantTypeDescription, parsePlantTypeMetadata } from '../helpers/plant-type-metadata.js';
import {
  makePlantAsset, makeLog, makeQuantity, makePlantType,
  pigeon_pea_asset, basil_sweet_classic_asset,
} from './fixtures.js';

// ── parseDate ─────────────────────────────────────────────────

describe('parseDate', () => {
  it('parses ISO date', () => {
    const ts = parseDate('2025-10-09');
    const dt = new Date(ts * 1000);
    expect(dt.getUTCFullYear()).toBe(2025);
  });

  it('parses ISO with UTC Z suffix', () => {
    const ts = parseDate('2026-03-09T03:15:00.000Z');
    const dt = new Date(ts * 1000);
    expect(dt.getUTCFullYear()).toBe(2026);
    expect(dt.getUTCMonth()).toBe(2); // March = 2
    expect(dt.getUTCHours()).toBe(3);
    expect(dt.getUTCMinutes()).toBe(15);
  });

  it('parses text year-month-day format', () => {
    const ts = parseDate('2025-MARCH-20 to 24TH');
    const dt = new Date(ts * 1000);
    expect(dt.getUTCFullYear()).toBe(2025);
  });

  it('parses text year-month only', () => {
    const ts = parseDate('2025-MARCH');
    const dt = new Date(ts * 1000);
    expect(dt.getUTCFullYear()).toBe(2025);
  });

  it('returns approximately now for empty string', () => {
    const before = Math.floor(Date.now() / 1000);
    const ts = parseDate('');
    const after = Math.floor(Date.now() / 1000);
    expect(ts).toBeGreaterThanOrEqual(before);
    expect(ts).toBeLessThanOrEqual(after + 1);
  });

  it('returns approximately now for null', () => {
    const before = Math.floor(Date.now() / 1000);
    const ts = parseDate(null);
    const after = Math.floor(Date.now() / 1000);
    expect(ts).toBeGreaterThanOrEqual(before);
    expect(ts).toBeLessThanOrEqual(after + 1);
  });

  it('returns approximately now for garbage input', () => {
    const before = Math.floor(Date.now() / 1000);
    const ts = parseDate('not-a-date-at-all!!!');
    const after = Math.floor(Date.now() / 1000);
    expect(ts).toBeGreaterThanOrEqual(before);
    expect(ts).toBeLessThanOrEqual(after + 1);
  });

  // ── ADR 0008 I12 — future-timestamp guard ──────────────────────

  it('I12: rejects year-typo future date (2026-12-18)', () => {
    expect(() => parseDate('2026-12-18')).toThrow(/Refusing future-dated/);
  });

  it('I12: rejects arbitrary far-future date', () => {
    expect(() => parseDate('2030-01-01')).toThrow(/ADR 0008 I12/);
  });

  it('I12: accepts today', () => {
    const AEST_OFFSET = 10 * 60 * 60 * 1000;
    const today = new Date(Date.now() + AEST_OFFSET).toISOString().slice(0, 10);
    const ts = parseDate(today);
    expect(ts).toBeGreaterThan(0);
  });

  it('I12: accepts within 24h grace window', () => {
    // Pick a date 12h ahead — safely inside the AEST↔UTC grace
    const AEST_OFFSET = 10 * 60 * 60 * 1000;
    const twelveHoursAhead = new Date(Date.now() + 12 * 60 * 60 * 1000 + AEST_OFFSET)
      .toISOString().slice(0, 10);
    const ts = parseDate(twelveHoursAhead);
    expect(ts).toBeGreaterThan(0);
  });

  it('I12: rejects beyond 24h grace window', () => {
    const threeDaysAhead = new Date(Date.now() + 3 * 24 * 60 * 60 * 1000)
      .toISOString().slice(0, 10);
    expect(() => parseDate(threeDaysAhead)).toThrow(/Refusing future-dated/);
  });
});

// ── formatPlantedLabel ────────────────────────────────────────

describe('formatPlantedLabel', () => {
  it('formats ISO date', () => {
    expect(formatPlantedLabel('2025-04-25')).toBe('25 APR 2025');
  });

  it('formats text month year', () => {
    expect(formatPlantedLabel('April 2025')).toBe('APR 2025');
  });

  it('returns fallback for empty string', () => {
    expect(formatPlantedLabel('')).toBe('SPRING 2025');
  });

  it('uppercases unrecognised input', () => {
    expect(formatPlantedLabel('late winter')).toBe('LATE WINTER');
  });
});

// ── buildAssetName ────────────────────────────────────────────

describe('buildAssetName', () => {
  it('builds standard name', () => {
    expect(buildAssetName('2025-04-25', 'Pigeon Pea', 'P2R2.0-3'))
      .toBe('25 APR 2025 - Pigeon Pea - P2R2.0-3');
  });

  it('handles empty date', () => {
    expect(buildAssetName('', 'Comfrey', 'P2R1.3-9'))
      .toBe('SPRING 2025 - Comfrey - P2R1.3-9');
  });
});

// ── parseAssetName / formatPlantAsset name parsing ────────────

describe('asset name parsing', () => {
  it('parses three-part simple name', () => {
    const result = formatPlantAsset(pigeon_pea_asset);
    expect(result.species).toBe('Pigeon Pea');
    expect(result.section).toBe('P2R2.0-3');
    expect(result.planted_date).toBe('25 APR 2025');
  });

  it('parses species with dash', () => {
    const asset = makePlantAsset({ name: '25 APR 2025 - Basil - Sweet - P2R3.15-21' });
    const result = formatPlantAsset(asset);
    expect(result.species).toBe('Basil - Sweet');
    expect(result.section).toBe('P2R3.15-21');
  });

  it('parses species with dash and variety', () => {
    const result = formatPlantAsset(basil_sweet_classic_asset);
    expect(result.species).toBe('Basil - Sweet (Classic)');
    expect(result.section).toBe('P2R3.15-21');
  });

  it('handles two-part name (no section)', () => {
    const asset = makePlantAsset({ name: '25 APR 2025 - Pigeon Pea' });
    const result = formatPlantAsset(asset);
    expect(result.species).toBe('Pigeon Pea');
    expect(result.section).toBe('');
  });

  it('handles one-part name', () => {
    const asset = makePlantAsset({ name: 'Pigeon Pea' });
    const result = formatPlantAsset(asset);
    expect(result.species).toBe('Pigeon Pea');
    expect(result.planted_date).toBe('');
    expect(result.section).toBe('');
  });
});

// ── formatPlantAsset inventory ────────────────────────────────

describe('formatPlantAsset inventory', () => {
  it('extracts integer inventory count', () => {
    const result = formatPlantAsset(pigeon_pea_asset);
    expect(result.inventory_count).toBe(4);
  });

  it('truncates float inventory', () => {
    const asset = makePlantAsset({ name: 'Test Plant' });
    asset.attributes.inventory = [{ measure: 'count', value: '3.7', units: { name: 'Plants' } }];
    const result = formatPlantAsset(asset);
    expect(result.inventory_count).toBe(3);
  });

  it('omits inventory_count when not present', () => {
    const asset = makePlantAsset({ name: 'Test Plant', inventoryCount: null });
    const result = formatPlantAsset(asset);
    expect(result).not.toHaveProperty('inventory_count');
  });
});

// ── formatLog ─────────────────────────────────────────────────

describe('formatLog', () => {
  it('formats basic log', () => {
    const log = makeLog({ name: 'Observation P2R3.15-21', logType: 'observation', notes: 'Test notes' });
    const result = formatLog(log);
    expect(result.name).toBe('Observation P2R3.15-21');
    expect(result.type).toBe('observation');
    expect(result.notes).toBe('Test notes');
  });

  it('merges quantities', () => {
    const qty = makeQuantity({ value: 5, measure: 'count', adjustment: 'reset' });
    const log = makeLog({ quantities: [qty] });
    const result = formatLog(log);
    expect(result.quantity).toHaveLength(1);
    expect(result.quantity[0].value).toBe(5);
    expect(result.quantity[0].measure).toBe('count');
    expect(result.quantity[0].inventory_adjustment).toBe('reset');
  });

  it('omits quantity when none present', () => {
    const log = makeLog({});
    const result = formatLog(log);
    expect(result).not.toHaveProperty('quantity');
  });
});

// ── formatPlantType ───────────────────────────────────────────

describe('formatPlantType', () => {
  it('extracts syntropic metadata from description', () => {
    const desc = 'A nitrogen-fixing pioneer.\n\n---\n**Syntropic Agriculture Data:**\n**Botanical Name:** Cajanus cajan\n**Strata:** High\n**Succession Stage:** Pioneer\n**Functions:** Nitrogen Fixer, Biomass Producer\n**Family:** Fabaceae';
    const term = makePlantType({ name: 'Pigeon Pea', description: desc });
    const result = formatPlantType(term);
    expect(result.name).toBe('Pigeon Pea');
    expect(result.botanical_name).toBe('Cajanus cajan');
    expect(result.strata).toBe('High');
    expect(result.succession_stage).toBe('Pioneer');
    expect(result.functions).toBe('Nitrogen Fixer, Biomass Producer');
    expect(result.family).toBe('Fabaceae');
  });

  it('handles term without syntropic metadata', () => {
    const term = makePlantType({ name: 'Unknown Plant' });
    const result = formatPlantType(term);
    expect(result.name).toBe('Unknown Plant');
    expect(result).not.toHaveProperty('botanical_name');
  });
});

// ── plant type metadata roundtrip ─────────────────────────────

describe('plant type metadata roundtrip', () => {
  it('survives full build → parse roundtrip', () => {
    const fields = {
      description: 'A fast-growing pioneer.',
      botanical_name: 'Cajanus cajan',
      lifecycle_years: '3-5',
      strata: 'high',
      succession_stage: 'pioneer',
      plant_functions: 'nitrogen_fixer,biomass_producer,edible_seed',
      crop_family: 'Fabaceae',
      lifespan_years: '5-10',
      source: 'EDEN Seeds',
    };
    const built = buildPlantTypeDescription(fields);
    const parsed = parsePlantTypeMetadata(built);

    expect(parsed.botanical_name).toBe('Cajanus cajan');
    expect(parsed.strata).toBe('high');
    expect(parsed.succession_stage).toBe('pioneer');
    expect(parsed.crop_family).toBe('Fabaceae');
    expect(parsed.lifespan_years).toBe('5-10');
    expect(parsed.lifecycle_years).toBe('3-5');
    expect(parsed.source).toBe('EDEN Seeds');
  });

  it('preserves function tags with underscores', () => {
    const fields = { plant_functions: 'nitrogen_fixer,biomass_producer,edible_fruit' };
    const built = buildPlantTypeDescription(fields);
    const parsed = parsePlantTypeMetadata(built);
    expect(parsed.plant_functions).toBe('nitrogen_fixer,biomass_producer,edible_fruit');
  });

  it('returns empty dict for empty description', () => {
    const parsed = parsePlantTypeMetadata('');
    expect(Object.keys(parsed)).toHaveLength(0);
  });

  it('returns empty dict for null', () => {
    const parsed = parsePlantTypeMetadata(null);
    expect(Object.keys(parsed)).toHaveLength(0);
  });
});

// ── formatTimestamp ────────────────────────────────────────────

describe('formatTimestamp', () => {
  it('formats ISO string to AEST', () => {
    const result = formatTimestamp('2026-03-09T03:15:00Z');
    expect(result).toBe('2026-03-09 13:15');
  });

  it('returns "unknown" for falsy input', () => {
    expect(formatTimestamp(null)).toBe('unknown');
    expect(formatTimestamp('')).toBe('unknown');
    expect(formatTimestamp(undefined)).toBe('unknown');
  });
});

// ── parseAssetName (standalone) ───────────────────────────────

describe('parseAssetName', () => {
  it('parses standard three-part name', () => {
    const result = parseAssetName('25 APR 2025 - Pigeon Pea - P2R2.0-3');
    expect(result.plantedDate).toBe('25 APR 2025');
    expect(result.species).toBe('Pigeon Pea');
    expect(result.section).toBe('P2R2.0-3');
  });

  it('handles species with multiple dashes', () => {
    const result = parseAssetName('25 APR 2025 - Wattle - Cootamundra (Baileyana) - P2R1.0-3');
    expect(result.species).toBe('Wattle - Cootamundra (Baileyana)');
    expect(result.section).toBe('P2R1.0-3');
  });
});
