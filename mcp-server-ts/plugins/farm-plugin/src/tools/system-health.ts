import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getFarmOSClient, getMemoryClient, getKnowledgeClient, getObserveClient, getPlantTypesClient } from '../clients/index.js';
import { assessFarmMaturity, assessSystemMaturity, assessTeamMaturity, assessDataMaturity, assessSectionHealth, formatPlantAsset, formatLog, parsePlantTypeMetadata, extractMemorySummaries, countKbEntries, countStampsInLogs } from '../helpers/index.js';
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
  description: `Assess farm maturity across four dimensions: Farm (biological), System (technical), Team (human), and Data (quality). Returns current growth stage per dimension, metric scores, and active scale triggers with recommended build actions.\n\nAll thresholds and interpretation rules are defined in knowledge/farm_growth.yaml (human-reviewable, not hardcoded).`,
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
            // Apps Script wraps results: {success, entries: [...], count, total}
            return countKbEntries(await kbClient.listEntries(undefined, 200));
          } catch { return null; }
        })(),
      ]);
      // Apps Script wraps results: {success, summaries: [...], count}
      const summaries = extractMemorySummaries(recent);
      const distinctUsers = new Set(summaries.map((e: any) => e.user).filter(Boolean)).size;
      const velocity = summaries.length;
      return assessTeamMaturity({ active_users_weekly: distinctUsers, team_memory_velocity: velocity, kb_entry_count: kbCount }, config);
    };

    const dataDimension = async (allPlants: any[], allTypes: any[]) => {
      // species_photo_coverage: species with TIER 1 (farm-sourced) photo only.
      // Tier 2 stock photos (wikimedia_stock) don't count — they're display aids.
      // Photo source tracked in plant_type description metadata (photo_source field).
      const distinctSpecies = new Set(allPlants.map((p: any) => {
        const name = p.attributes?.name ?? '';
        const match = name.match(/^\d{1,2}\s+\w{3}\s+\d{4}\s*-\s*(.+?)\s*-\s*/);
        return match ? match[1].trim() : name;
      }).filter(Boolean));
      let farmSourcedPhotos = 0;
      for (const t of allTypes) {
        if (t.relationships?.image?.data == null) continue;
        const desc = t.attributes?.description;
        const descText = typeof desc === 'object' ? desc?.value ?? '' : String(desc ?? '');
        const meta = parsePlantTypeMetadata(descText);
        const src = meta.photo_source ?? '';
        // farm_observation = Tier 1. Empty = legacy (pre-batch, all were farm-sourced).
        if (src === 'farm_observation' || src === '') farmSourcedPhotos++;
      }
      const photoCoverage = distinctSpecies.size > 0 ? farmSourcedPhotos / distinctSpecies.size : 0;

      // observation_pipeline_age: max days any observation has been pending
      let pipelineAge = 0;
      try {
        const obsClient = getObserveClient();
        if (obsClient) {
          const pending = await obsClient.listObservations({ status: 'pending' });
          const submissions = Array.isArray(pending) ? pending : (pending?.submissions ?? []);
          const now = Date.now();
          for (const sub of submissions) {
            const obs = sub.observations ?? [sub];
            for (const o of (Array.isArray(obs) ? obs : [obs])) {
              const ts = o.timestamp ?? o.date ?? sub.timestamp ?? sub.date;
              if (!ts) continue;
              const dt = new Date(ts);
              if (!isNaN(dt.getTime())) {
                const days = Math.floor((now - dt.getTime()) / (1000 * 60 * 60 * 24));
                if (days > pipelineAge) pipelineAge = days;
              }
            }
          }
        }
      } catch { /* observation client unavailable */ }

      // provenance_coverage: fraction of recent logs with InteractionStamp
      let provenanceCoverage = 0;
      try {
        const recentLogs = await client.getRecentLogs(50);
        const { coverage } = countStampsInLogs(recentLogs);
        provenanceCoverage = coverage;
      } catch { /* fallback to 0 */ }

      // source_conflict_count: pending activity logs with conflict/discrepancy in notes
      let conflictCount = 0;
      try {
        const pendingLogs = await client.getLogs('activity', undefined, 'pending', 50);
        for (const log of pendingLogs) {
          const notes = typeof log.attributes?.notes === 'object'
            ? log.attributes?.notes?.value ?? ''
            : String(log.attributes?.notes ?? '');
          if (/discrepancy|conflict/i.test(notes)) conflictCount++;
        }
      } catch { /* fallback to 0 */ }

      return assessDataMaturity({
        species_photo_coverage: photoCoverage,
        observation_pipeline_age: pipelineAge,
        provenance_coverage: provenanceCoverage,
        source_conflict_count: conflictCount,
      }, config);
    };

    // Run Farm first (System depends on its activePlantCount), then System + Team + Data in parallel.
    // Farm itself parallelizes its 20 section fetches internally.
    const [farmSettled] = await Promise.allSettled([farmDimension()]);
    if (farmSettled.status === 'fulfilled') {
      result.dimensions.farm = farmSettled.value;
      result.scale_triggers.push(...(farmSettled.value.scale_triggers ?? []));
    } else {
      result.dimensions.farm = { error: farmSettled.reason?.message ?? String(farmSettled.reason) };
    }

    const activePlantCount = result.dimensions.farm?.metrics?.active_plants?.value ?? 0;

    // Fetch allPlants + allTypes for dataDimension (Farm already fetched them but we need the raw data)
    // Re-fetch is cheap because getAllPlantTypesCached is cached.
    const [allPlantsForData, allTypesForData] = await Promise.all([
      client.fetchAllPaginated('asset/plant', { status: 'active' }),
      client.getAllPlantTypesCached(),
    ]);

    const [systemSettled, teamSettled, dataSettled] = await Promise.allSettled([
      systemDimension(activePlantCount),
      teamDimension(),
      dataDimension(allPlantsForData, allTypesForData),
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
    if (dataSettled.status === 'fulfilled') {
      result.dimensions.data = dataSettled.value;
      result.scale_triggers.push(...(dataSettled.value.scale_triggers ?? []));
    } else {
      result.dimensions.data = { error: dataSettled.reason?.message ?? String(dataSettled.reason) };
    }

    // ── Summary ─────────────────────────────────────────
    const stages = ['farm', 'system', 'team', 'data']
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
