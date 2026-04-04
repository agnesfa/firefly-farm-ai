/**
 * Tests for the Farm Semantic Layer (Layer 3) — TypeScript port.
 *
 * Pure function tests — no I/O, no mocking needed.
 */

import { describe, it, expect } from 'vitest';
import {
  assessStrataCoverage,
  assessActivityRecency,
  assessSuccessionBalance,
  assessSectionHealth,
  findTransplantReady,
  detectKnowledgeGaps,
  detectDecisionGaps,
  detectLoggingGaps,
} from '../helpers/semantics.js';

const PLANT_TYPES_DB: Record<string, any> = {
  'Pigeon Pea': { strata: 'high', succession_stage: 'pioneer', transplant_days: 60 },
  'Macadamia': { strata: 'high', succession_stage: 'climax', transplant_days: 365 },
  'Ice Cream Bean': { strata: 'emergent', succession_stage: 'pioneer' },
  'Comfrey': { strata: 'low', succession_stage: 'secondary', transplant_days: 45 },
  'Tomato (Marmande)': { strata: 'medium', succession_stage: 'pioneer', transplant_days: 60 },
  'Forest Red Gum': { strata: 'emergent', succession_stage: 'climax' },
  'Sweet Potato': { strata: 'low', succession_stage: 'pioneer' },
  'Apple': { strata: 'high', succession_stage: 'secondary' },
};

const plant = (species: string, count: number, strata?: string) =>
  ({ species, count, ...(strata ? { strata } : {}) });

// ── Strata Coverage ─────────────────────────────────────────

describe('assessStrataCoverage', () => {
  it('full tree section = 1.0 good', () => {
    const plants = [
      plant('Ice Cream Bean', 2), plant('Pigeon Pea', 4),
      plant('Tomato (Marmande)', 3), plant('Comfrey', 5),
    ];
    const r = assessStrataCoverage(plants, PLANT_TYPES_DB, true);
    expect(r.score).toBe(1.0);
    expect(r.status).toBe('good');
    expect(r.filled_strata).toBe(4);
  });

  it('open section 2/2 = 1.0 good', () => {
    const plants = [plant('Tomato (Marmande)', 6), plant('Comfrey', 3)];
    const r = assessStrataCoverage(plants, PLANT_TYPES_DB, false);
    expect(r.score).toBe(1.0);
    expect(r.expected_strata).toBe(2);
  });

  it('3/4 strata = 0.75 good', () => {
    const plants = [plant('Pigeon Pea', 4), plant('Tomato (Marmande)', 3), plant('Sweet Potato', 2)];
    const r = assessStrataCoverage(plants, PLANT_TYPES_DB, true);
    expect(r.score).toBe(0.75);
    expect(r.status).toBe('good');
  });

  it('1/4 strata = 0.25 poor', () => {
    const r = assessStrataCoverage([plant('Pigeon Pea', 4)], PLANT_TYPES_DB, true);
    expect(r.score).toBe(0.25);
    expect(r.status).toBe('poor');
  });

  it('dead plants not counted', () => {
    const plants = [plant('Ice Cream Bean', 0), plant('Pigeon Pea', 4), plant('Comfrey', 2)];
    const r = assessStrataCoverage(plants, PLANT_TYPES_DB, true);
    expect(r.filled_strata).toBe(2);
  });

  it('unknown species uses plant strata field', () => {
    const r = assessStrataCoverage([plant('Unknown', 3, 'emergent')], PLANT_TYPES_DB, true);
    expect(r.emergent).toBe(3);
  });
});

// ── Activity Recency ─────────────────────────────────────────

describe('assessActivityRecency', () => {
  const now = new Date('2026-04-04T10:00:00+10:00');

  it('5 days ago = active', () => {
    const r = assessActivityRecency([{ timestamp: '2026-03-30T10:00:00+10:00' }], now);
    expect(r.days_since_last).toBe(5);
    expect(r.status).toBe('active');
  });

  it('20 days ago = needs_attention', () => {
    const r = assessActivityRecency([{ timestamp: '2026-03-15T10:00:00+10:00' }], now);
    expect(r.status).toBe('needs_attention');
  });

  it('no logs = neglected', () => {
    const r = assessActivityRecency([], now);
    expect(r.days_since_last).toBe(9999);
    expect(r.status).toBe('neglected');
  });

  it('uses most recent log', () => {
    const logs = [
      { timestamp: '2026-01-01T10:00:00+10:00' },
      { timestamp: '2026-04-01T10:00:00+10:00' },
      { timestamp: '2026-02-15T10:00:00+10:00' },
    ];
    const r = assessActivityRecency(logs, now);
    expect(r.days_since_last).toBe(3);
  });
});

// ── Succession Balance ───────────────────────────────────────

describe('assessSuccessionBalance', () => {
  it('pioneer heavy', () => {
    const plants = [plant('Pigeon Pea', 5), plant('Sweet Potato', 3), plant('Comfrey', 2)];
    const r = assessSuccessionBalance(plants, PLANT_TYPES_DB);
    expect(r.pioneer).toBe(8);
    expect(r.percentages.pioneer).toBe(80);
    expect(r.note.toLowerCase()).toContain('pioneer');
  });

  it('empty = appropriate note', () => {
    const r = assessSuccessionBalance([], PLANT_TYPES_DB);
    expect(r.total).toBe(0);
    expect(r.note).toContain('No plants');
  });
});

// ── Section Health ───────────────────────────────────────────

describe('assessSectionHealth', () => {
  const now = new Date('2026-04-04T10:00:00+10:00');

  it('healthy section', () => {
    const plants = [
      plant('Ice Cream Bean', 2), plant('Pigeon Pea', 4),
      plant('Tomato (Marmande)', 3), plant('Comfrey', 5),
    ];
    const logs = [{ timestamp: '2026-04-01T10:00:00+10:00' }];
    const r = assessSectionHealth(plants, logs, PLANT_TYPES_DB, true, now);
    expect(r.strata_coverage.status).toBe('good');
    expect(r.activity_recency.status).toBe('active');
    expect(['good', 'active']).toContain(r.overall_status);
  });

  it('neglected overrides good strata', () => {
    const plants = [
      plant('Ice Cream Bean', 2), plant('Pigeon Pea', 4),
      plant('Tomato (Marmande)', 3), plant('Comfrey', 5),
    ];
    const logs = [{ timestamp: '2025-12-01T10:00:00+10:00' }];
    const r = assessSectionHealth(plants, logs, PLANT_TYPES_DB, true, now);
    expect(r.strata_coverage.status).toBe('good');
    expect(r.activity_recency.status).toBe('neglected');
    expect(r.overall_status).toBe('neglected');
  });
});

// ── Knowledge Gaps ───────────────────────────────────────────

describe('detectKnowledgeGaps', () => {
  it('full coverage', () => {
    const r = detectKnowledgeGaps(['Pigeon Pea', 'Comfrey'], [{ related_plants: 'Pigeon Pea, Comfrey' }]);
    expect(r.coverage_ratio).toBe(1.0);
    expect(r.uncovered_species).toHaveLength(0);
  });

  it('partial coverage', () => {
    const r = detectKnowledgeGaps(['Pigeon Pea', 'Comfrey', 'Macadamia'], [{ related_plants: 'Pigeon Pea' }]);
    expect(r.uncovered_species).toContain('Comfrey');
    expect(r.coverage_ratio).toBeCloseTo(0.33, 1);
  });
});

// ── Logging Gaps ─────────────────────────────────────────────

describe('detectLoggingGaps', () => {
  it('detects missing farmOS log from team memory claim', () => {
    const sessions = [{
      summary_id: '89', user: 'James', timestamp: '2026-03-25T00:00:00Z',
      farmos_changes: JSON.stringify([
        { type: 'create_plant', species: 'Lavender', section: 'P2R4.6-14', count: 5 },
      ]),
    }];
    const gaps = detectLoggingGaps(sessions, [], 'P2R4.6-14');
    expect(gaps).toHaveLength(1);
    expect(gaps[0].user).toBe('James');
    expect(gaps[0].claimed_change.details).toContain('Lavender');
  });

  it('no gap when log ID matches', () => {
    const sessions = [{
      summary_id: '82', user: 'James', timestamp: '2026-03-21T00:00:00Z',
      farmos_changes: JSON.stringify([{ type: 'activity', id: '0ee1ea15', details: 'Seeding — P2R3.50-62' }]),
    }];
    const logs = [{ id: '0ee1ea15-a7e7-482c-8872-6745588a75be', name: 'Seeding — P2R3.50-62', type: 'activity' }];
    const gaps = detectLoggingGaps(sessions, logs);
    expect(gaps).toHaveLength(0);
  });

  it('skips empty farmos_changes', () => {
    const sessions = [{ summary_id: '90', user: 'James', timestamp: '2026-03-25T00:00:00Z', farmos_changes: '' }];
    expect(detectLoggingGaps(sessions, [])).toHaveLength(0);
  });

  it('skips plain text farmos_changes', () => {
    const sessions = [{ summary_id: '91', user: 'James', timestamp: '2026-03-25T00:00:00Z', farmos_changes: 'Updated some plants' }];
    expect(detectLoggingGaps(sessions, [])).toHaveLength(0);
  });
});
