/**
 * farm_context — Cross-reference farmOS, Knowledge Base, and plant types in one call.
 *
 * Returns interpreted farm intelligence with all five layers:
 * ontology, facts, interpretation, context (with integrity checks), and gaps.
 */

import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getFarmOSClient, getKnowledgeClient, getMemoryClient } from '../clients/index.js';
import { formatPlantAsset, formatLog, formatPlantType } from '../helpers/index.js';
import {
  TOPIC_FARMOS_MAP,
  assessSectionHealth,
  findTransplantReady,
  detectKnowledgeGaps,
  detectDecisionGaps,
  detectLoggingGaps,
} from '../helpers/semantics.js';

export const farmContextTool: Tool = {
  namespace: 'fc',
  name: 'farm_context',
  title: 'Farm Context (Intelligence Layer)',
  description:
    'Cross-reference farmOS, Knowledge Base, and plant types in one call.\n\n' +
    'Returns interpreted farm intelligence with all five layers:\n' +
    'ontology (what exists), facts (what\'s true), interpretation (what it means),\n' +
    'context (what we did about it, with integrity checks), and gaps (what\'s missing).\n\n' +
    'Provide exactly ONE of:\n' +
    '- subject: Species name (e.g., "Pigeon Pea") — distribution + KB + metadata\n' +
    '- section: Section ID (e.g., "P2R3.15-21") — health assessment + pending tasks\n' +
    '- topic: Farm domain (e.g., "nursery") — domain overview + transplant readiness',
  paramsSchema: z.object({
    subject: z.string().optional().describe('Species name (e.g., "Pigeon Pea")'),
    section: z.string().optional().describe('Section ID (e.g., "P2R3.15-21")'),
    topic: z.string().optional().describe('Farm domain (e.g., "nursery")'),
  }).shape,
  options: { readOnlyHint: true },
  handler: async (params, extra) => {
    if (!params.subject && !params.section && !params.topic) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ error: 'Provide one of: subject, section, or topic' }) }] };
    }

    const client = getFarmOSClient(extra);
    const kbClient = getKnowledgeClient();
    const memClient = getMemoryClient();
    const result: any = {};

    // ── Section mode ──────────────────────────────────────
    if (params.section) {
      const section = params.section;
      result.query = { type: 'section', id: section };

      const isNursery = section.startsWith('NURS.');
      const hasTrees = !isNursery;
      const entityType = isNursery ? 'nursery_zone' : 'paddock_section';

      result.ontology = {
        entity_type: entityType,
        constraints: [hasTrees
          ? 'expects 4 strata layers (emergent, high, medium, low)'
          : 'nursery zone — no strata expectation'],
      };

      // Layer 2: Facts
      const plantsRaw = await client.getPlantAssets(section);
      const plants = plantsRaw.map(formatPlantAsset);
      const logsRaw = await client.getLogs(undefined, section);
      const logs = logsRaw.map(formatLog);

      // Build plant_types_db
      const allTypes = await client.getAllPlantTypesCached();
      const plantTypesDb: Record<string, any> = {};
      for (const pt of allTypes) {
        const fmt = formatPlantType(pt);
        plantTypesDb[fmt.name] = fmt;
      }

      // KB entries
      let kbEntries: any[] = [];
      if (kbClient) {
        try {
          const kbResult = await kbClient.search(section);
          kbEntries = Array.isArray(kbResult) ? kbResult : (kbResult?.results ?? []);
        } catch { /* graceful */ }
      }

      result.facts = {
        total_plants: plants.length,
        total_species: new Set(plants.map((p: any) => p.species)).size,
        plants: plants.map((p: any) => ({ species: p.species, count: p.inventory_count, status: p.status })),
        recent_logs: logs.length,
        kb_entries: kbEntries.slice(0, 5).map((e: any) => ({ title: e.title ?? '', category: e.category ?? '' })),
      };

      // Layer 3: Interpretation
      const plantData = plants.map((p: any) => ({ species: p.species ?? '', count: p.inventory_count ?? 0, strata: p.strata ?? '' }));
      const logData = logs.map((l: any) => ({ timestamp: l.timestamp ?? '', status: l.status, type: l.type, name: l.name }));

      const health = assessSectionHealth(plantData, logData, plantTypesDb, hasTrees);
      result.interpretation = health;

      // Layer 4: Context + team memory cross-reference
      const pending = logs.filter((l: any) => l.status === 'pending');
      const recentObs = logs.filter((l: any) => l.type === 'observation').slice(0, 5);

      let loggingGaps: any[] = [];
      if (memClient) {
        try {
          const memResult = await memClient.searchMemory(section, 30);
          const sessions = memResult?.results ?? [];
          if (sessions.length) {
            loggingGaps = detectLoggingGaps(sessions, logs, section);
          }
        } catch { /* graceful */ }
      }

      result.context = {
        pending_tasks: pending.map((t: any) => ({ name: t.name ?? '', timestamp: t.timestamp ?? '' })),
        recent_observations: recentObs.map((o: any) => ({ name: o.name ?? '', timestamp: o.timestamp ?? '', notes: o.notes ?? '' })),
        logging_gaps: loggingGaps.map((g: any) => ({
          user: g.user, session: g.session_id,
          claimed: g.claimed_change.details, evidence: g.evidence,
        })),
      };

      // Gaps
      const speciesInSection = plants.map((p: any) => p.species).filter(Boolean);
      const kbGaps = detectKnowledgeGaps(speciesInSection, kbEntries);
      const decisionGaps = detectDecisionGaps(pending, recentObs);

      const gaps: string[] = [];
      if (kbGaps.uncovered_species.length) {
        gaps.push(`No KB entries for species: ${kbGaps.uncovered_species.slice(0, 5).join(', ')}`);
      }
      gaps.push(...decisionGaps);
      if (health.activity_recency.status === 'neglected') {
        gaps.push('Section has not been visited in over 60 days');
      }
      if (health.strata_coverage.status === 'poor') {
        gaps.push('Poor strata coverage — missing most canopy layers');
      }
      for (const g of loggingGaps) {
        gaps.push(`INTEGRITY: ${g.user} claimed '${g.claimed_change.details}' (session ${g.session_id}) but no matching farmOS log found`);
      }
      result.gaps = gaps;

      // Data integrity gate
      if (loggingGaps.length > 0) {
        result.data_integrity = {
          requires_confirmation: true,
          reason: 'Team memory records changes that are not reflected in farmOS. '
            + 'The facts shown above may be INCOMPLETE. '
            + 'Confirm with the human what actually happened before acting on this data.',
          discrepancies: loggingGaps.map((g: any) => ({
            who: g.user, session: g.session_id,
            claimed: g.claimed_change.details, type: g.claimed_change.type ?? 'unknown',
          })),
        };
      } else {
        result.data_integrity = { requires_confirmation: false };
      }
    }

    // ── Subject (species) mode ────────────────────────────
    else if (params.subject) {
      const subject = params.subject;
      result.query = { type: 'species', name: subject };
      result.ontology = { entity_type: 'Species', canonical_source: 'farmOS taxonomy_term/plant_type' };

      const plantsRaw = await client.getPlantAssets(undefined, subject);
      const plants = plantsRaw.map(formatPlantAsset);

      const allTypes = await client.getAllPlantTypesCached();
      let speciesMeta: any = null;
      for (const pt of allTypes) {
        const fmt = formatPlantType(pt);
        if (fmt.name.toLowerCase() === subject.toLowerCase()) { speciesMeta = fmt; break; }
      }

      let kbEntries: any[] = [];
      if (kbClient) {
        try {
          const kbResult = await kbClient.search(subject);
          kbEntries = Array.isArray(kbResult) ? kbResult : (kbResult?.results ?? []);
        } catch { /* graceful */ }
      }

      const sections: Record<string, { count: number; plants: string[] }> = {};
      for (const p of plants) {
        const sec = p.section ?? 'unknown';
        if (!sections[sec]) sections[sec] = { count: 0, plants: [] };
        sections[sec].count += p.inventory_count ?? 0;
        sections[sec].plants.push(p.name ?? '');
      }

      result.facts = {
        total_plants: plants.length,
        total_count: Object.values(sections).reduce((sum, s) => sum + s.count, 0),
        sections: Object.fromEntries(Object.entries(sections).map(([k, v]) => [k, v.count])),
        distribution: Object.keys(sections).length,
        species_metadata: speciesMeta,
        kb_entries: kbEntries.slice(0, 5).map((e: any) => ({ title: e.title ?? '', category: e.category ?? '' })),
      };

      result.interpretation = {
        strata: speciesMeta?.strata ?? 'unknown',
        succession: speciesMeta?.succession_stage ?? 'unknown',
        functions: speciesMeta?.plant_functions ?? '',
        distribution_sections: Object.keys(sections).length,
      };

      result.context = { kb_coverage: kbEntries.length > 0 };

      const gaps: string[] = [];
      if (!kbEntries.length) gaps.push(`No Knowledge Base entries for ${subject}`);
      if (!speciesMeta) gaps.push(`${subject} not found in plant type taxonomy`);
      result.gaps = gaps;
    }

    // ── Topic (domain) mode ───────────────────────────────
    else if (params.topic) {
      const topicLower = params.topic.toLowerCase();
      result.query = { type: 'topic', name: topicLower };

      const topicConfig = TOPIC_FARMOS_MAP[topicLower] ?? {};
      const prefix = topicConfig.section_prefix;
      result.ontology = { entity_type: 'farm_domain', topic: topicLower, section_prefix: prefix };

      let plants: any[] = [];
      const sectionsData: Record<string, { count: number; species: Set<string> }> = {};
      if (prefix) {
        const plantsRaw = await client.getPlantAssets(prefix);
        plants = plantsRaw.map(formatPlantAsset);
        for (const p of plants) {
          const sec = p.section ?? 'unknown';
          if (!sectionsData[sec]) sectionsData[sec] = { count: 0, species: new Set() };
          sectionsData[sec].count += p.inventory_count ?? 0;
          sectionsData[sec].species.add(p.species ?? '');
        }
      }

      let kbEntries: any[] = [];
      if (kbClient) {
        try {
          const kbResult = await kbClient.search(topicLower);
          kbEntries = Array.isArray(kbResult) ? kbResult : (kbResult?.results ?? []);
        } catch { /* graceful */ }
      }

      result.facts = {
        total_plants: plants.length,
        total_sections: Object.keys(sectionsData).length,
        sections_summary: Object.fromEntries(Object.entries(sectionsData).map(([k, v]) => [k, v.count])),
        total_species: new Set(plants.map((p: any) => p.species)).size,
        kb_entries: kbEntries.slice(0, 10).map((e: any) => ({ title: e.title ?? '', category: e.category ?? '' })),
      };

      // Transplant readiness for nursery topic
      if (topicLower === 'nursery') {
        const allTypes = await client.getAllPlantTypesCached();
        const plantTypesDb: Record<string, any> = {};
        for (const pt of allTypes) {
          const fmt = formatPlantType(pt);
          plantTypesDb[fmt.name] = fmt;
        }
        const nurseryPlants = plants.map((p: any) => ({
          species: p.species ?? '', planted_date: p.planted_date ?? '',
          name: p.name ?? '', count: p.inventory_count ?? 0, section: p.section ?? '',
        }));
        const ready = findTransplantReady(nurseryPlants, plantTypesDb);
        result.interpretation = {
          transplant_ready: ready.slice(0, 10).map(r => ({
            species: r.species, section: r.section, count: r.count, days_overdue: r.days_overdue,
          })),
          total_transplant_ready: ready.length,
        };
      } else {
        result.interpretation = {};
      }

      result.context = { kb_entry_count: kbEntries.length };
      const gaps: string[] = [];
      if (!kbEntries.length) gaps.push(`No Knowledge Base entries for topic '${topicLower}'`);
      result.gaps = gaps;
    }

    return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
  },
};
