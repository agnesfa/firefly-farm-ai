/**
 * Tests for the Farm Semantic Layer (Layer 3) — TypeScript port.
 *
 * Pure function tests — no I/O, no mocking needed.
 */

import { describe, it, expect } from 'vitest';
import { readFileSync, existsSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { parse as parseYaml } from 'yaml';
import {
  assessStrataCoverage,
  assessActivityRecency,
  assessSuccessionBalance,
  assessSectionHealth,
  findTransplantReady,
  detectKnowledgeGaps,
  detectDecisionGaps,
  detectLoggingGaps,
  classifyByDirection,
  assessFarmMaturity,
  assessSystemMaturity,
  assessTeamMaturity,
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

// ── Growth Model tests ───────────────────────────────────────

const GROWTH_CONFIG = {
  dimensions: {
    farm: {
      stages: [
        { name: 'planted', label: 'F1: Planted' },
        { name: 'surviving', label: 'F2: Surviving' },
      ],
      metrics: {
        active_plants: {
          interpretation: {
            direction: 'higher_is_better',
            thresholds: [
              { label: 'f2', value: 1000 }, { label: 'f1', value: 500 }, { label: 'starting', value: 0 },
            ],
          },
          scale_actions: { f2: 'Optimize query_sections' },
        },
        survival_rate: {
          interpretation: {
            direction: 'higher_is_better',
            thresholds: [
              { label: 'healthy', value: 0.70 }, { label: 'concerning', value: 0.50 }, { label: 'at_risk', value: 0.30 },
            ],
            pioneer_exception: true,
          },
        },
        strata_coverage: {
          interpretation: {
            direction: 'higher_is_better',
            thresholds: [
              { label: 'good', value: 0.75 }, { label: 'fair', value: 0.50 }, { label: 'poor', value: 0.25 },
            ],
          },
        },
      },
    },
    system: {
      stages: [{ name: 'i', label: 'S1' }, { name: 'o', label: 'S2' }, { name: 'i2', label: 'S3' }, { name: 'r', label: 'S4: Reliable' }],
      metrics: {
        total_entities: {
          interpretation: { direction: 'lower_is_better', thresholds: [{ label: 'safe', value: 1500 }, { label: 'warning', value: 3000 }] },
          scale_actions: { warning: 'Add Views' },
        },
        plant_type_drift: {
          interpretation: { direction: 'lower_is_better', thresholds: [{ label: 'healthy', value: 0 }, { label: 'drifting', value: 5 }, { label: 'broken', value: 20 }] },
          scale_actions: { drifting: 'Sync' },
        },
        observation_backlog: {
          interpretation: { direction: 'lower_is_better', thresholds: [{ label: 'healthy', value: 5 }, { label: 'backlog', value: 15 }] },
        },
      },
    },
    team: {
      stages: [{ name: 'e', label: 'T1' }, { name: 'u', label: 'T2: Using' }],
      metrics: {
        active_users_weekly: {
          interpretation: { direction: 'higher_is_better', thresholds: [{ label: 'healthy', value: 3 }, { label: 'low', value: 1 }, { label: 'dormant', value: 0 }] },
        },
        team_memory_velocity: {
          interpretation: { direction: 'higher_is_better', thresholds: [{ label: 'active', value: 5 }, { label: 'slow', value: 2 }, { label: 'dormant', value: 0 }] },
        },
        kb_entry_count: {
          interpretation: { direction: 'higher_is_better', thresholds: [{ label: 't4', value: 20 }, { label: 'growing', value: 10 }, { label: 'minimal', value: 3 }] },
        },
      },
    },
  },
};

describe('classifyByDirection', () => {
  it('higher_is_better classifies correctly', () => {
    const interp = { direction: 'higher_is_better' as const, thresholds: [{ label: 'good', value: 0.75 }, { label: 'fair', value: 0.50 }, { label: 'poor', value: 0.25 }] };
    expect(classifyByDirection(0.80, interp)).toBe('good');
    expect(classifyByDirection(0.60, interp)).toBe('fair');
    expect(classifyByDirection(0.10, interp)).toBe('poor');
  });

  it('lower_is_better classifies correctly', () => {
    const interp = { direction: 'lower_is_better' as const, thresholds: [{ label: 'healthy', value: 5 }, { label: 'backlog', value: 15 }, { label: 'blocked', value: 50 }] };
    expect(classifyByDirection(2, interp)).toBe('healthy');
    expect(classifyByDirection(10, interp)).toBe('backlog');
    expect(classifyByDirection(60, interp)).toBe('blocked');
  });

  it('null returns unknown', () => {
    expect(classifyByDirection(null, { direction: 'higher_is_better', thresholds: [{ label: 'good', value: 0.5 }] })).toBe('unknown');
  });
});

describe('assessFarmMaturity', () => {
  it('644 plants > 500 → passed F1', () => {
    const result = assessFarmMaturity({ active_plants: 644, section_health_scores: [{ strata_score: 0.75, survival_rate: 0.65 }] }, GROWTH_CONFIG);
    expect(result.stage).toBe('F2: Surviving');
    expect(result.metrics.active_plants.status).toBe('passed_f1');
  });

  it('survival rate surfaced with pioneer_exception', () => {
    const result = assessFarmMaturity({ active_plants: 644, section_health_scores: [{ strata_score: 0.75, survival_rate: 0.55 }] }, GROWTH_CONFIG);
    expect(result.metrics.survival_rate.status).toBe('concerning');
    expect(result.metrics.survival_rate.pioneer_exception).toBe(true);
  });
});

describe('assessSystemMaturity', () => {
  it('drift beyond threshold triggers scale action', () => {
    // 10 drift: > drifting(5), <= broken(20) → classified as "broken"
    const result = assessSystemMaturity({ total_entities: 1200, plant_type_drift: 10, observation_backlog: 0 }, GROWTH_CONFIG);
    expect(result.metrics.plant_type_drift.status).toBe('broken');
    const triggers = result.scale_triggers.filter((t: any) => t.metric === 'plant_type_drift');
    expect(triggers.length).toBeGreaterThan(0);
  });
});

describe('assessTeamMaturity', () => {
  it('active team classified correctly', () => {
    const result = assessTeamMaturity({ active_users_weekly: 3, team_memory_velocity: 6, kb_entry_count: 15 }, GROWTH_CONFIG);
    expect(result.metrics.active_users_weekly.status).toBe('healthy');
    expect(result.metrics.team_memory_velocity.status).toBe('active');
    expect(result.metrics.kb_entry_count.status).toBe('growing');
  });

  it('dormant team classified correctly', () => {
    const result = assessTeamMaturity({ active_users_weekly: 0, team_memory_velocity: 0, kb_entry_count: 2 }, GROWTH_CONFIG);
    expect(result.metrics.active_users_weekly.status).toBe('dormant');
    expect(result.metrics.kb_entry_count.status).toBe('minimal');
  });
});

// ────────────────────────────────────────────────────────────
// farm_growth.yaml hygiene
// ────────────────────────────────────────────────────────────
// system_health surfaces assumption: strings verbatim from knowledge/farm_growth.yaml.
// If a point-in-time count leaks in ("Currently 53 ..."), it silently goes stale because
// nothing regenerates the YAML. These tests reject that failure mode at build time.
describe('farm_growth.yaml hygiene', () => {
  // Mirrors the path-resolution logic in tools/system-health.ts:loadGrowthConfig.
  const loadRealGrowthConfig = (): any => {
    const here = dirname(fileURLToPath(import.meta.url));
    const candidates = [
      resolve(here, '..', '..', '..', '..', 'knowledge', 'farm_growth.yaml'),          // from src/__tests__ up to repo root
      resolve(here, '..', '..', '..', '..', '..', 'knowledge', 'farm_growth.yaml'),
      resolve(process.cwd(), 'knowledge', 'farm_growth.yaml'),
      resolve(process.cwd(), '..', '..', 'knowledge', 'farm_growth.yaml'),
    ];
    for (const p of candidates) {
      if (existsSync(p)) return parseYaml(readFileSync(p, 'utf-8'));
    }
    throw new Error(`Cannot find knowledge/farm_growth.yaml. Tried:\n  ${candidates.join('\n  ')}`);
  };

  it('loads the real farm_growth.yaml with expected structure', () => {
    const config = loadRealGrowthConfig();
    expect(config.dimensions).toBeDefined();
    expect(config.dimensions.farm).toBeDefined();
    expect(config.dimensions.system).toBeDefined();
    expect(config.dimensions.team).toBeDefined();
  });

  it('assumption text must not embed point-in-time counts', () => {
    // Narrow patterns: trigger on temporal framing ("Currently 53 ...") or
    // counts paired with state verbs ("53 pending", "4 users equipped").
    // Definitional phrasing like "counts as 1 user" should NOT trip these.
    const stalePatterns: RegExp[] = [
      /\bCurrently\s+\d+/i,
      /\b\d+\s+\w+\s+(?:equipped|pending|remaining|connected|installed|synced|active)\b/i,
      /\b\d+\s+(?:pending|remaining)\b/i,
      /\bpending\s+sync\b/i,
    ];

    const config = loadRealGrowthConfig();
    const violations: string[] = [];

    for (const [dimName, dim] of Object.entries<any>(config.dimensions ?? {})) {
      for (const stage of (dim.stages ?? []) as any[]) {
        const text: string = stage.assumption ?? '';
        if (stalePatterns.some((p) => p.test(text))) {
          violations.push(`${dimName}.stages[${stage.label}]: ${text.trim().slice(0, 120)}`);
        }
      }
      for (const [metricName, metric] of Object.entries<any>(dim.metrics ?? {})) {
        const text: string = metric?.assumption ?? '';
        if (stalePatterns.some((p) => p.test(text))) {
          violations.push(`${dimName}.metrics.${metricName}: ${text.trim().slice(0, 120)}`);
        }
      }
    }

    expect(violations, `farm_growth.yaml assumption text must not embed point-in-time counts (they leak into system_health output and go stale). Describe the metric's meaning instead. Violations:\n  - ${violations.join('\n  - ')}`).toEqual([]);
  });
});
