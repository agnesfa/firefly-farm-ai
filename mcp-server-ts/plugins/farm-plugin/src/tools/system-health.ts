import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getFarmOSClient, getMemoryClient, getKnowledgeClient, getObserveClient, getPlantTypesClient } from '../clients/index.js';
import { assessFarmMaturity, assessSystemMaturity, assessTeamMaturity, assessSectionHealth, formatPlantAsset, formatLog, parsePlantTypeMetadata } from '../helpers/index.js';
import { readFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { parse as parseYaml } from 'yaml';

function loadGrowthConfig(): any {
  // Try multiple paths to find farm_growth.yaml
  // In Docker with npm workspace: CWD = /app/apps/farm-server/, __dirname = /app/plugins/farm-plugin/dist/tools/
  const candidates = [
    resolve(process.cwd(), 'knowledge', 'farm_growth.yaml'),                                                        // CWD = /app/
    resolve(process.cwd(), '..', '..', 'knowledge', 'farm_growth.yaml'),                                             // CWD = /app/apps/farm-server/
    resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', '..', 'knowledge', 'farm_growth.yaml'),        // __dirname relative (4 levels up to /app/)
  ];
  for (const p of candidates) {
    try { return parseYaml(readFileSync(p, 'utf-8')); } catch { /* try next */ }
  }
  throw new Error('Cannot find knowledge/farm_growth.yaml');
}

export const systemHealthTool: Tool = {
  namespace: 'fc',
  name: 'system_health',
  title: 'System Health',
  description: `Assess farm maturity across three dimensions: Farm (biological), System (technical), and Team (human). Returns current growth stage per dimension, metric scores, and active scale triggers with recommended build actions.\n\nAll thresholds and interpretation rules are defined in knowledge/farm_growth.yaml (human-reviewable, not hardcoded).`,
  paramsSchema: z.object({}).shape,
  options: { readOnlyHint: true },

  handler: async (_params, extra) => {
    const config = loadGrowthConfig();
    const client = getFarmOSClient(extra);
    const result: any = { dimensions: {}, scale_triggers: [], assumptions: [] };

    // ── Farm dimension ──────────────────────────────────
    try {
      const allPlants = await client.fetchAllPaginated('asset/plant', { status: 'active' });
      const activePlantCount = allPlants.length;

      const allTypes = await client.getAllPlantTypesCached();
      const plantTypesDb: Record<string, any> = {};
      for (const t of allTypes) {
        const name = t.attributes?.name ?? '';
        const desc = t.attributes?.description;
        const descText = typeof desc === 'object' ? desc?.value ?? '' : String(desc ?? '');
        plantTypesDb[name] = parsePlantTypeMetadata(descText);
      }

      const sections = await client.getSectionAssets();
      const sectionScores: any[] = [];
      for (const sec of sections.slice(0, 20)) {
        const secName = sec.attributes?.name ?? '';
        const secPlantsRaw = await client.getPlantAssets(secName);
        const secPlants = secPlantsRaw.map(formatPlantAsset).map((p: any) => ({
          species: p.species ?? '',
          count: p.inventory_count ?? 0,
        }));
        const secLogsRaw = await client.getLogs(undefined, secName);
        const secLogs = secLogsRaw.map(formatLog) as any[];
        const health = assessSectionHealth(secPlants, secLogs, plantTypesDb, true);
        sectionScores.push({
          section: secName,
          strata_score: health.strata_coverage?.score ?? 0,
          survival_rate: null,
          status: health.overall_status ?? 'unknown',
        });
      }

      const farmResult = assessFarmMaturity({ active_plants: activePlantCount, section_health_scores: sectionScores }, config);
      farmResult.sampled_sections = sectionScores.length;
      farmResult.total_sections = sections.length;
      result.dimensions.farm = farmResult;
      result.scale_triggers.push(...(farmResult.scale_triggers ?? []));
    } catch (e: any) {
      result.dimensions.farm = { error: e.message };
    }

    // ── System dimension ────────────────────────────────
    try {
      const totalEntities = (result.dimensions.farm?.metrics?.active_plants?.value ?? 0) + 1200;
      let driftCount: number | null = null;
      try {
        const ptClient = getPlantTypesClient();
        if (ptClient) {
          const drift = await ptClient.getReconcileData();
          driftCount = drift?.mismatch_count ?? 0;
        }
      } catch { /* */ }

      let backlogCount: number | null = null;
      try {
        const obsClient = getObserveClient();
        if (obsClient) {
          const pending = await obsClient.listObservations({ status: 'pending' });
          backlogCount = Array.isArray(pending) ? pending.length : 0;
        }
      } catch { /* */ }

      const systemResult = assessSystemMaturity({ total_entities: totalEntities, plant_type_drift: driftCount, observation_backlog: backlogCount }, config);
      result.dimensions.system = systemResult;
      result.scale_triggers.push(...(systemResult.scale_triggers ?? []));
    } catch (e: any) {
      result.dimensions.system = { error: e.message };
    }

    // ── Team dimension ──────────────────────────────────
    try {
      const memClient = getMemoryClient();
      if (!memClient) throw new Error('Memory client not configured');
      const recent = await memClient.readActivity(7);
      const distinctUsers = new Set((Array.isArray(recent) ? recent : []).map((e: any) => e.user).filter(Boolean)).size;
      const velocity = Array.isArray(recent) ? recent.length : 0;

      let kbCount: number | null = null;
      try {
        const kbClient = getKnowledgeClient();
        if (kbClient) {
          const entries = await kbClient.listEntries();
          kbCount = Array.isArray(entries) ? entries.length : 0;
        }
      } catch { /* */ }

      const teamResult = assessTeamMaturity({ active_users_weekly: distinctUsers, team_memory_velocity: velocity, kb_entry_count: kbCount }, config);
      result.dimensions.team = teamResult;
      result.scale_triggers.push(...(teamResult.scale_triggers ?? []));
    } catch (e: any) {
      result.dimensions.team = { error: e.message };
    }

    // ── Summary ─────────────────────────────────────────
    const stages = ['farm', 'system', 'team']
      .map(d => result.dimensions[d]?.stage ? `${d.charAt(0).toUpperCase() + d.slice(1)}: ${result.dimensions[d].stage}` : null)
      .filter(Boolean);
    result.overall_maturity = stages.join(' | ') || 'Unable to assess';

    // Surface assumptions
    for (const [dimName, dimConfig] of Object.entries(config.dimensions ?? {})) {
      for (const stage of (dimConfig as any).stages ?? []) {
        if (stage.assumption) result.assumptions.push({ dimension: dimName, stage: stage.label, assumption: stage.assumption });
      }
      for (const [mn, mc] of Object.entries((dimConfig as any).metrics ?? {})) {
        if ((mc as any).assumption) result.assumptions.push({ dimension: dimName, metric: mn, assumption: (mc as any).assumption });
      }
    }

    return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
  },
};
