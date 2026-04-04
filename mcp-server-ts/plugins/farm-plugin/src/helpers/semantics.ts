/**
 * Farm Semantic Layer (Layer 3) — Computable metric functions.
 *
 * Mirrors knowledge/farm_semantics.yaml definitions as TypeScript constants
 * and pure functions. No I/O, no client calls.
 *
 * When updating thresholds here, also update farm_semantics.yaml to keep
 * the human-readable definitions in sync.
 */

// ── Semantic definitions (mirrors farm_semantics.yaml) ────────────

export const SECTION_HEALTH = {
  strata_coverage: {
    expected_strata: { tree_section: 4, open_section: 2 },
    thresholds: { good: 0.75, fair: 0.50, poor: 0.25 },
  },
  activity_recency: {
    thresholds: { active: 14, needs_attention: 30, neglected: 60 },
  },
} as const;

export const TOPIC_FARMOS_MAP: Record<string, { section_prefix: string | null; asset_types: string[] }> = {
  nursery:        { section_prefix: 'NURS.', asset_types: ['plant', 'structure'] },
  compost:        { section_prefix: 'COMP.', asset_types: ['compost'] },
  paddock:        { section_prefix: 'P', asset_types: ['plant', 'land'] },
  seeds:          { section_prefix: 'NURS.FR', asset_types: ['seed'] },
  irrigation:     { section_prefix: null, asset_types: ['water', 'equipment'] },
  equipment:      { section_prefix: null, asset_types: ['equipment'] },
  infrastructure: { section_prefix: null, asset_types: ['water', 'land'] },
  camp:           { section_prefix: null, asset_types: ['structure'] },
  harvest:        { section_prefix: null, asset_types: ['plant'] },
  cooking:        { section_prefix: null, asset_types: [] },
  syntropic:      { section_prefix: 'P', asset_types: ['plant', 'land'] },
};

// ── Helper types ──────────────────────────────────────────────────

interface PlantData {
  species: string;
  count: number;
  strata?: string;
}

interface LogData {
  timestamp?: string;
  status?: string;
  type?: string;
  name?: string;
  notes?: string;
}

interface PlantTypeInfo {
  strata?: string;
  succession_stage?: string;
  plant_functions?: string;
  transplant_days?: number;
  [key: string]: any;
}

type PlantTypesDb = Record<string, PlantTypeInfo>;

interface StrataCoverage {
  emergent: number;
  high: number;
  medium: number;
  low: number;
  filled_strata: number;
  expected_strata: number;
  score: number;
  status: string;
}

interface ActivityRecency {
  days_since_last: number;
  last_log_date: string | null;
  status: string;
}

interface SuccessionBalance {
  pioneer: number;
  secondary: number;
  climax: number;
  unknown: number;
  total: number;
  percentages: Record<string, number>;
  note: string;
}

interface SectionHealth {
  strata_coverage: StrataCoverage;
  activity_recency: ActivityRecency;
  succession_balance: SuccessionBalance;
  overall_status: string;
}

interface LoggingGap {
  type: string;
  session_id: string;
  user: string;
  session_timestamp: string;
  claimed_change: { type: string; id?: string | null; details: string };
  evidence: string;
}

// ── Classification helpers ────────────────────────────────────────

function classify(value: number, thresholds: Record<string, number>): string {
  for (const label of ['good', 'healthy', 'active']) {
    if (label in thresholds && value >= thresholds[label]) return label;
  }
  for (const label of ['fair', 'concerning', 'needs_attention']) {
    if (label in thresholds && value >= thresholds[label]) return label;
  }
  for (const label of ['poor', 'at_risk', 'neglected', 'stalled']) {
    if (label in thresholds) return label;
  }
  return 'unknown';
}

function classifyRecency(days: number, thresholds: { active: number; needs_attention: number; neglected?: number }): string {
  if (days <= thresholds.active) return 'active';
  if (days <= thresholds.needs_attention) return 'needs_attention';
  return 'neglected';
}

// ── Core metric functions ─────────────────────────────────────────

export function assessStrataCoverage(
  plants: PlantData[],
  plantTypesDb: PlantTypesDb,
  hasTrees: boolean,
): StrataCoverage {
  const config = SECTION_HEALTH.strata_coverage;
  const expected = hasTrees ? config.expected_strata.tree_section : config.expected_strata.open_section;

  const strataCounts: Record<string, number> = { emergent: 0, high: 0, medium: 0, low: 0 };

  for (const plant of plants) {
    if (!plant.count || plant.count <= 0) continue;
    const pt = plantTypesDb[plant.species] ?? {};
    const strata = (pt.strata ?? plant.strata ?? '').toLowerCase();
    if (strata in strataCounts) {
      strataCounts[strata] += plant.count;
    }
  }

  const filled = Object.values(strataCounts).filter(v => v > 0).length;
  const score = expected > 0 ? Math.round((filled / expected) * 100) / 100 : 0;

  return {
    ...strataCounts as any,
    filled_strata: filled,
    expected_strata: expected,
    score,
    status: classify(score, config.thresholds as Record<string, number>),
  };
}

export function assessActivityRecency(
  logs: LogData[],
  now?: Date,
): ActivityRecency {
  const thresholds = SECTION_HEALTH.activity_recency.thresholds;
  const currentTime = now ?? new Date();

  if (!logs.length) {
    return { days_since_last: 9999, last_log_date: null, status: 'neglected' };
  }

  let latest: Date | null = null;
  for (const log of logs) {
    if (!log.timestamp) continue;
    try {
      let dt: Date;
      const ts = log.timestamp;
      if (/^\d+$/.test(ts)) {
        dt = new Date(parseInt(ts) * 1000);
      } else {
        dt = new Date(ts);
      }
      if (!isNaN(dt.getTime()) && (latest === null || dt > latest)) {
        latest = dt;
      }
    } catch { /* skip */ }
  }

  if (!latest) {
    return { days_since_last: 9999, last_log_date: null, status: 'neglected' };
  }

  const days = Math.floor((currentTime.getTime() - latest.getTime()) / (1000 * 60 * 60 * 24));

  return {
    days_since_last: days,
    last_log_date: latest.toISOString().slice(0, 10),
    status: classifyRecency(days, thresholds),
  };
}

export function assessSuccessionBalance(
  plants: PlantData[],
  plantTypesDb: PlantTypesDb,
): SuccessionBalance {
  const counts: Record<string, number> = { pioneer: 0, secondary: 0, climax: 0, unknown: 0 };

  for (const plant of plants) {
    if (!plant.count || plant.count <= 0) continue;
    const pt = plantTypesDb[plant.species] ?? {};
    const stage = (pt.succession_stage ?? '').toLowerCase();
    if (stage === 'pioneer' || stage === 'secondary' || stage === 'climax') {
      counts[stage] += plant.count;
    } else {
      counts.unknown += plant.count;
    }
  }

  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  const percentages: Record<string, number> = {};
  if (total > 0) {
    for (const [k, v] of Object.entries(counts)) {
      if (k !== 'unknown') percentages[k] = Math.round(100 * v / total);
    }
  }

  let note = '';
  if (total === 0) note = 'No plants with known succession stage';
  else if ((percentages.pioneer ?? 0) > 60) note = 'Pioneer-heavy — expected for young sections';
  else if ((percentages.climax ?? 0) > 40) note = 'Climax-dominant — mature succession';
  else if ((percentages.secondary ?? 0) > 40) note = 'Secondary-dominant — transitioning well';
  else note = 'Balanced mix across succession stages';

  return {
    pioneer: counts.pioneer,
    secondary: counts.secondary,
    climax: counts.climax,
    unknown: counts.unknown,
    total,
    percentages,
    note,
  };
}

export function assessSectionHealth(
  plants: PlantData[],
  logs: LogData[],
  plantTypesDb: PlantTypesDb,
  hasTrees: boolean,
  now?: Date,
): SectionHealth {
  const strata = assessStrataCoverage(plants, plantTypesDb, hasTrees);
  const recency = assessActivityRecency(logs, now);
  const succession = assessSuccessionBalance(plants, plantTypesDb);

  const statusOrder = ['good', 'healthy', 'active', 'fair', 'concerning',
    'needs_attention', 'poor', 'at_risk', 'neglected'];
  const rank = (s: string) => { const i = statusOrder.indexOf(s); return i >= 0 ? i : statusOrder.length; };

  const worst = rank(strata.status) >= rank(recency.status) ? strata.status : recency.status;

  return { strata_coverage: strata, activity_recency: recency, succession_balance: succession, overall_status: worst };
}

export function findTransplantReady(
  nurseryPlants: Array<{ species: string; planted_date?: string; name?: string; count?: number; section?: string }>,
  plantTypesDb: PlantTypesDb,
  now?: Date,
): Array<{ name: string; species: string; section: string; count: number; days_since_planted: number; transplant_days: number; days_overdue: number }> {
  const currentTime = now ?? new Date();
  const ready: Array<{ name: string; species: string; section: string; count: number; days_since_planted: number; transplant_days: number; days_overdue: number }> = [];

  for (const plant of nurseryPlants) {
    const pt = plantTypesDb[plant.species] ?? {};
    const transplantDays = pt.transplant_days;
    if (transplantDays == null) continue;
    if (!plant.planted_date) continue;

    const plantedDt = new Date(plant.planted_date);
    if (isNaN(plantedDt.getTime())) continue;

    const daysSince = Math.floor((currentTime.getTime() - plantedDt.getTime()) / (1000 * 60 * 60 * 24));
    if (daysSince >= transplantDays) {
      ready.push({
        name: plant.name ?? '',
        species: plant.species,
        section: plant.section ?? '',
        count: plant.count ?? 0,
        days_since_planted: daysSince,
        transplant_days: transplantDays,
        days_overdue: daysSince - transplantDays,
      });
    }
  }

  ready.sort((a, b) => b.days_overdue - a.days_overdue);
  return ready;
}

export function detectKnowledgeGaps(
  speciesInField: string[],
  kbEntries: Array<{ related_plants?: string; [key: string]: any }>,
): { uncovered_species: string[]; covered_species: string[]; coverage_ratio: number; total_field_species: number; total_covered: number } {
  const covered = new Set<string>();
  for (const entry of kbEntries) {
    for (const sp of (entry.related_plants ?? '').split(',')) {
      const trimmed = sp.trim();
      if (trimmed) covered.add(trimmed);
    }
  }

  const fieldSet = new Set(speciesInField);
  const uncovered = [...fieldSet].filter(s => !covered.has(s)).sort();
  const coveredField = [...fieldSet].filter(s => covered.has(s)).sort();
  const total = fieldSet.size;
  const ratio = total > 0 ? Math.round((coveredField.length / total) * 100) / 100 : 0;

  return { uncovered_species: uncovered, covered_species: coveredField, coverage_ratio: ratio, total_field_species: total, total_covered: coveredField.length };
}

export function detectDecisionGaps(
  pendingTasks: LogData[],
  recentObservations: LogData[],
): string[] {
  const gaps: string[] = [];

  for (const task of pendingTasks) {
    if (task.status === 'pending' && task.timestamp) {
      try {
        const created = /^\d+$/.test(task.timestamp)
          ? new Date(parseInt(task.timestamp) * 1000)
          : new Date(task.timestamp);
        const days = Math.floor((Date.now() - created.getTime()) / (1000 * 60 * 60 * 24));
        if (days > 7) {
          gaps.push(`Task '${task.name ?? ''}' pending for ${days} days — needs attention`);
        }
      } catch { /* skip */ }
    }
  }

  if (recentObservations.length > 0 && pendingTasks.length === 0) {
    gaps.push('Recent observations exist but no pending tasks — observations may not be acted on');
  }

  return gaps;
}

export function detectLoggingGaps(
  teamMemorySessions: Array<{ summary_id?: string; user?: string; timestamp?: string; farmos_changes?: string }>,
  farmosLogs: Array<{ id?: string; name?: string; type?: string }>,
  sectionFilter?: string,
): LoggingGap[] {
  const gaps: LoggingGap[] = [];

  // Index farmOS logs by ID prefix and name
  const logIds = new Set<string>();
  const logNamesLower = new Set<string>();
  for (const log of farmosLogs) {
    if (log.id) {
      logIds.add(log.id);
      logIds.add(log.id.slice(0, 8));
    }
    if (log.name) logNamesLower.add(log.name.toLowerCase());
  }

  for (const session of teamMemorySessions) {
    const changesRaw = session.farmos_changes;
    if (!changesRaw?.trim()) continue;

    let claimedChanges: any[];
    try {
      const parsed = JSON.parse(changesRaw);
      claimedChanges = Array.isArray(parsed) ? parsed : [parsed];
    } catch {
      continue; // plain text — can't cross-reference
    }

    for (const change of claimedChanges) {
      if (typeof change !== 'object' || change === null) continue;

      const changeId: string = change.id ?? '';
      let details: string = change.details ?? change.description ?? '';

      // Build details from structured fields if not present
      if (!details) {
        const parts: string[] = [];
        if (change.species) parts.push(change.species);
        if (change.count) parts.push(`x${change.count}`);
        if (change.section) parts.push(`— ${change.section}`);
        if (change.notes) parts.push(`— ${String(change.notes).slice(0, 80)}`);
        if (parts.length) details = parts.join(' ');
      }

      // Apply section filter
      if (sectionFilter && !String(details).includes(sectionFilter)) continue;

      // Check if claimed change exists in farmOS
      let found = false;
      if (changeId && logIds.has(changeId)) found = true;

      if (!found && details) {
        const detailsLower = details.toLowerCase();
        for (const logName of logNamesLower) {
          const words = detailsLower.split(/\s+/).filter(w => w.length > 2).slice(0, 3);
          if (words.every(w => logName.includes(w))) { found = true; break; }
        }
      }

      if (!found) {
        gaps.push({
          type: 'claimed_not_found',
          session_id: session.summary_id ?? '',
          user: session.user ?? 'unknown',
          session_timestamp: session.timestamp ?? '',
          claimed_change: { type: change.type ?? '', id: changeId || null, details },
          evidence: 'No matching farmOS log found — possible silent API failure',
        });
      }
    }
  }

  return gaps;
}

// ── Growth Model — YAML-driven maturity assessment ───────────────

interface ThresholdEntry { label: string; value: number; meaning?: string; }
interface InterpretationBlock {
  direction?: 'higher_is_better' | 'lower_is_better';
  thresholds?: ThresholdEntry[] | Record<string, number>;
  pioneer_exception?: boolean;
}

/**
 * Classify a value using the YAML-declared interpretation rule.
 * Reads direction from the interpretation block — no hardcoded assumptions.
 */
export function classifyByDirection(value: number | null | undefined, interpretation: InterpretationBlock): string {
  if (value == null) return 'unknown';
  const direction = interpretation.direction ?? 'higher_is_better';
  const raw = interpretation.thresholds;
  let thresholds: [string, number][];
  if (Array.isArray(raw)) {
    thresholds = raw.map(t => [t.label, t.value]);
  } else if (raw && typeof raw === 'object') {
    thresholds = Object.entries(raw);
  } else return 'unknown';

  if (direction === 'lower_is_better') {
    const sorted = [...thresholds].sort((a, b) => a[1] - b[1]);
    for (const [label, threshold] of sorted) { if (value <= threshold) return label; }
    return sorted[sorted.length - 1]?.[0] ?? 'unknown';
  } else {
    const sorted = [...thresholds].sort((a, b) => b[1] - a[1]);
    for (const [label, threshold] of sorted) { if (value >= threshold) return label; }
    return sorted[sorted.length - 1]?.[0] ?? 'unknown';
  }
}

function getInterpThreshold(interpretation: InterpretationBlock, label: string, defaultVal: number): number {
  const raw = interpretation.thresholds;
  if (Array.isArray(raw)) { const f = raw.find(t => t.label === label); if (f) return f.value; }
  else if (raw && typeof raw === 'object') { const v = (raw as Record<string, number>)[label]; if (v !== undefined) return v; }
  return defaultVal;
}

export function assessFarmMaturity(data: { active_plants: number; section_health_scores: any[] }, config: any): any {
  const farmConfig = config.dimensions.farm;
  const metricsConfig = farmConfig.metrics;
  const stages = farmConfig.stages;
  const metrics: Record<string, any> = {};
  const triggers: any[] = [];

  const active = data.active_plants ?? 0;
  const plantInterp = metricsConfig.active_plants?.interpretation ?? {};
  const f1 = getInterpThreshold(plantInterp, 'f1', 500);
  const f2 = getInterpThreshold(plantInterp, 'f2', 1000);
  const plantStatus = classifyByDirection(active, plantInterp);
  metrics.active_plants = { value: active, status: active >= f1 ? `passed_${plantStatus}` : 'below_f1' };
  if (active >= f2) triggers.push({ metric: 'active_plants', status: 'warning', value: active, threshold: f2, action: metricsConfig.active_plants?.scale_actions?.f2 ?? '' });

  const scores = data.section_health_scores ?? [];
  let avgSurvival: number | null = null;
  if (scores.length) {
    const rates = scores.map((s: any) => s.survival_rate).filter((r: any) => r != null) as number[];
    avgSurvival = rates.length ? rates.reduce((a, b) => a + b, 0) / rates.length : null;
  }
  const survivalInterp = metricsConfig.survival_rate?.interpretation ?? {};
  metrics.survival_rate = { value: avgSurvival, status: avgSurvival != null ? classifyByDirection(avgSurvival, survivalInterp) : 'unknown', pioneer_exception: survivalInterp.pioneer_exception ?? false };

  let pctGood: number | null = null;
  let strataStatus = 'unknown';
  if (scores.length) {
    const strataInterp = metricsConfig.strata_coverage?.interpretation ?? {};
    const goodT = getInterpThreshold(strataInterp, 'good', 0.75);
    const ss = scores.map((s: any) => s.strata_score ?? 0);
    pctGood = ss.filter((s: number) => s >= goodT).length / ss.length;
    strataStatus = classifyByDirection(pctGood, strataInterp);
  }
  metrics.strata_coverage = { value: pctGood, status: strataStatus };
  return { stage: active < f1 ? stages[0].label : stages[1].label, metrics, scale_triggers: triggers };
}

export function assessSystemMaturity(data: Record<string, any>, config: any): any {
  const sysConfig = config.dimensions.system;
  const mc = sysConfig.metrics;
  const metrics: Record<string, any> = {};
  const triggers: any[] = [];
  const best = new Set(['healthy', 'safe', 'fresh']);

  for (const mn of ['total_entities', 'plant_type_drift', 'observation_backlog']) {
    const v = data[mn]; if (v == null) { metrics[mn] = { value: null, status: 'unknown' }; continue; }
    const interp = mc[mn]?.interpretation ?? {};
    metrics[mn] = { value: v, status: classifyByDirection(v, interp) };
    const raw = interp.thresholds ?? [];
    const pairs: [string, number][] = Array.isArray(raw) ? raw.map((t: any) => [t.label, t.value]) : Object.entries(raw);
    const dir = interp.direction ?? 'higher_is_better';
    for (const [label, threshold] of pairs) {
      if (best.has(label)) continue;
      if ((dir === 'lower_is_better' && v > threshold) || (dir === 'higher_is_better' && v >= threshold))
        triggers.push({ metric: mn, status: label, value: v, threshold, action: mc[mn]?.scale_actions?.[label] ?? '' });
    }
  }
  return { stage: sysConfig.stages[3]?.label ?? 'S4: Reliable', metrics, scale_triggers: triggers };
}

export function assessTeamMaturity(data: Record<string, any>, config: any): any {
  const tc = config.dimensions.team;
  const mc = tc.metrics;
  const metrics: Record<string, any> = {};
  for (const mn of ['active_users_weekly', 'team_memory_velocity', 'kb_entry_count']) {
    const v = data[mn]; if (v == null) { metrics[mn] = { value: null, status: 'unknown' }; continue; }
    metrics[mn] = { value: v, status: classifyByDirection(v, mc[mn]?.interpretation ?? {}) };
  }
  return { stage: tc.stages[1]?.label ?? 'T2: Using', metrics, scale_triggers: [] };
}
