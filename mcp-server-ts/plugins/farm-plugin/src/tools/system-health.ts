import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getFarmOSClient, getMemoryClient, getKnowledgeClient, getObserveClient, getPlantTypesClient } from '../clients/index.js';
import { assessFarmMaturity, assessSystemMaturity, assessTeamMaturity, assessSectionHealth, formatPlantAsset, formatLog, parsePlantTypeMetadata } from '../helpers/index.js';
import { readFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { parse as parseYaml } from 'yaml';

function loadGrowthConfig(): any {
  // knowledge/farm_growth.yaml lives at the REPO ROOT — one level above
  // mcp-server-ts/. The Dockerfile (build context = repo root) copies it
  // into /app/knowledge/ for the production image. Locally it stays at
  // the repo root and is found via __dirname walks.
  const candidates = [
    resolve(process.cwd(), 'knowledge', 'farm_growth.yaml'),                                                              // Docker: CWD = /app/
    resolve(process.cwd(), '..', '..', 'knowledge', 'farm_growth.yaml'),                                                  // Docker: CWD = /app/apps/farm-server/
    resolve(process.cwd(), '..', 'knowledge', 'farm_growth.yaml'),                                                        // Local dev: CWD = mcp-server-ts/
    resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', '..', 'knowledge', 'farm_growth.yaml'),              // Docker: __dirname 4-up → /app/
    resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', '..', '..', 'knowledge', 'farm_growth.yaml'),         // Local dev: __dirname 5-up → repo root
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

    // Farm, System, and Team dimensions are independent — run in parallel.
    // Within Farm, the 20 section assessments are also independent and run in parallel.
    // This turns ~40 sequential farmOS roundtrips into a couple of parallel waves.

    const farmDimension = async () => {
      const [allPlants, allTypes, sections] = await Promise.all([
        client.fetchAllPaginated('asset/plant', { status: 'active' }),
        client.getAllPlantTypesCached(),
        client.getSectionAssets(),
      ]);
      const activePlantCount = allPlants.length;

      const plantTypesDb: Record<string, any> = {};
      for (const t of allTypes) {
        const name = t.attributes?.name ?? '';
        const desc = t.attributes?.description;
        const descText = typeof desc === 'object' ? desc?.value ?? '' : String(desc ?? '');
        plantTypesDb[name] = parsePlantTypeMetadata(descText);
      }

      const sampledSections = sections.slice(0, 20);
      const sectionScores = await Promise.all(
        sampledSections.map(async (sec) => {
          const secName = sec.attributes?.name ?? '';
          const [secPlantsRaw, secLogsRaw] = await Promise.all([
            client.getPlantAssets(secName),
            client.getLogs(undefined, secName),
          ]);
          const secPlants = secPlantsRaw.map(formatPlantAsset).map((p: any) => ({
            species: p.species ?? '',
            count: p.inventory_count ?? 0,
          }));
          const secLogs = secLogsRaw.map(formatLog) as any[];
          const health = assessSectionHealth(secPlants, secLogs, plantTypesDb, true);
          return {
            section: secName,
            strata_score: health.strata_coverage?.score ?? 0,
            survival_rate: null,
            status: health.overall_status ?? 'unknown',
          };
        })
      );

      const farmResult = assessFarmMaturity({ active_plants: activePlantCount, section_health_scores: sectionScores }, config);
      farmResult.sampled_sections = sectionScores.length;
      farmResult.total_sections = sections.length;
      return farmResult;
    };

    const systemDimension = async (activePlantCount: number) => {
      const totalEntities = activePlantCount + 1200;
      const [driftCount, backlogCount] = await Promise.all([
        (async () => {
          try {
            const ptClient = getPlantTypesClient();
            if (!ptClient) return null;
            const drift = await ptClient.getReconcileData();
            return drift?.mismatch_count ?? 0;
          } catch { return null; }
        })(),
        (async () => {
          try {
            const obsClient = getObserveClient();
            if (!obsClient) return null;
            const pending = await obsClient.listObservations({ status: 'pending' });
            return Array.isArray(pending) ? pending.length : 0;
          } catch { return null; }
        })(),
      ]);
      return assessSystemMaturity({ total_entities: totalEntities, plant_type_drift: driftCount, observation_backlog: backlogCount }, config);
    };

    const teamDimension = async () => {
      const memClient = getMemoryClient();
      if (!memClient) throw new Error('Memory client not configured');
      const [recent, kbCount] = await Promise.all([
        memClient.readActivity(7),
        (async () => {
          try {
            const kbClient = getKnowledgeClient();
            if (!kbClient) return null;
            const entries = await kbClient.listEntries();
            return Array.isArray(entries) ? entries.length : 0;
          } catch { return null; }
        })(),
      ]);
      const distinctUsers = new Set((Array.isArray(recent) ? recent : []).map((e: any) => e.user).filter(Boolean)).size;
      const velocity = Array.isArray(recent) ? recent.length : 0;
      return assessTeamMaturity({ active_users_weekly: distinctUsers, team_memory_velocity: velocity, kb_entry_count: kbCount }, config);
    };

    // Run Farm first (System depends on its activePlantCount), then System + Team in parallel.
    // Farm itself parallelizes its 20 section fetches internally.
    const [farmSettled] = await Promise.allSettled([farmDimension()]);
    if (farmSettled.status === 'fulfilled') {
      result.dimensions.farm = farmSettled.value;
      result.scale_triggers.push(...(farmSettled.value.scale_triggers ?? []));
    } else {
      result.dimensions.farm = { error: farmSettled.reason?.message ?? String(farmSettled.reason) };
    }

    const activePlantCount = result.dimensions.farm?.metrics?.active_plants?.value ?? 0;
    const [systemSettled, teamSettled] = await Promise.allSettled([
      systemDimension(activePlantCount),
      teamDimension(),
    ]);
    if (systemSettled.status === 'fulfilled') {
      result.dimensions.system = systemSettled.value;
      result.scale_triggers.push(...(systemSettled.value.scale_triggers ?? []));
    } else {
      result.dimensions.system = { error: systemSettled.reason?.message ?? String(systemSettled.reason) };
    }
    if (teamSettled.status === 'fulfilled') {
      result.dimensions.team = teamSettled.value;
      result.scale_triggers.push(...(teamSettled.value.scale_triggers ?? []));
    } else {
      result.dimensions.team = { error: teamSettled.reason?.message ?? String(teamSettled.reason) };
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
