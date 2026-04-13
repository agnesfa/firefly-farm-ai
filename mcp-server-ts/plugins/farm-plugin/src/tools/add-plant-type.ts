import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getFarmOSClient, getPlantTypesClient } from '../clients/index.js';
import { buildPlantTypeDescription, buildMcpStamp, appendStamp } from '../helpers/index.js';

export const addPlantTypeTool: Tool = {
  namespace: 'fc',
  name: 'add_plant_type',
  title: 'Add Plant Type',
  description: 'Add a new plant type to the farmOS taxonomy.\n\nCreates a plant_type taxonomy term with syntropic agriculture metadata\nembedded in the description.\n\nArgs:\n    farmos_name: The canonical name (e.g., "Tomato (Marmande)", "Pigeon Pea"). Must not already exist.\n    botanical_name: Scientific name (e.g., "Cajanus cajan").\n    strata: Height layer — emergent, high, medium, or low.\n    succession_stage: Temporal role — pioneer, secondary, or climax.\n    plant_functions: Comma-separated function tags (e.g., "nitrogen_fixer,edible_seed,biomass_producer").\n    crop_family: Botanical family (e.g., "Fabaceae").\n    origin: Geographic origin (e.g., "India/Africa").\n    description: Free-text description of the plant.\n    lifespan_years: How long the plant lives (e.g., "5-10", "20+").\n    lifecycle_years: Production/harvest cycle (e.g., "0.5", "3-5").\n    source: Where seeds/plants come from (e.g., "EDEN Seeds", "Daleys Fruit Nursery").\n    maturity_days: Days to maturity (numeric, optional).\n    transplant_days: Days from seed to transplant (numeric, optional).',
  paramsSchema: z.object({
    farmos_name: z.string().describe('The canonical name'),
    botanical_name: z.string().optional().describe('Scientific name'),
    strata: z.string().optional().describe('Height layer'),
    succession_stage: z.string().optional().describe('Temporal role'),
    plant_functions: z.string().optional().describe('Comma-separated function tags'),
    crop_family: z.string().optional().describe('Botanical family'),
    origin: z.string().optional().describe('Geographic origin'),
    description: z.string().optional().describe('Free-text description'),
    lifespan_years: z.string().optional().describe('How long the plant lives'),
    lifecycle_years: z.string().optional().describe('Production/harvest cycle'),
    source: z.string().optional().describe('Where seeds/plants come from'),
    maturity_days: z.number().optional().describe('Days to maturity'),
    transplant_days: z.number().optional().describe('Days from seed to transplant'),
  }).shape,
  options: { readOnlyHint: false },
  handler: async (params, extra) => {
    const client = getFarmOSClient(extra);
    const existing = await client.fetchByName('taxonomy_term/plant_type', params.farmos_name);
    if (existing.length > 0) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ error: `Plant type '${params.farmos_name}' already exists.`, existing_id: existing[0].id }) }] };
    }

    const stamp = buildMcpStamp('created', 'plant_type', { relatedEntities: [params.farmos_name] });

    const rawDescription = buildPlantTypeDescription({
      description: params.description ?? '', botanical_name: params.botanical_name,
      lifecycle_years: params.lifecycle_years, strata: params.strata,
      succession_stage: params.succession_stage, plant_functions: params.plant_functions,
      crop_family: params.crop_family, lifespan_years: params.lifespan_years, source: params.source,
    });
    const fullDescription = appendStamp(rawDescription, stamp);

    try {
      const uuid = await client.createPlantType(params.farmos_name, fullDescription, params.maturity_days, params.transplant_days);

      // Sync to Google Sheet
      let sheetStatus = 'not_configured';
      const ptClient = getPlantTypesClient();
      if (ptClient) {
        try {
          let commonName = params.farmos_name;
          let variety = '';
          if (params.farmos_name.includes(' (') && params.farmos_name.endsWith(')')) {
            const idx = params.farmos_name.lastIndexOf(' (');
            commonName = params.farmos_name.slice(0, idx);
            variety = params.farmos_name.slice(idx + 2, -1);
          }
          const result = await ptClient.add({
            common_name: commonName, variety, farmos_name: params.farmos_name,
            botanical_name: params.botanical_name ?? '', crop_family: params.crop_family ?? '',
            origin: params.origin ?? '', description: params.description ?? '',
            lifespan_years: params.lifespan_years ?? '', lifecycle_years: params.lifecycle_years ?? '',
            maturity_days: params.maturity_days ? String(params.maturity_days) : '',
            strata: params.strata ?? '', succession_stage: params.succession_stage ?? '',
            plant_functions: params.plant_functions ?? '',
            transplant_days: params.transplant_days ? String(params.transplant_days) : '',
            source: params.source ?? '',
          });
          sheetStatus = result.success ? 'synced' : (result.error ?? 'failed');
        } catch (e: any) { sheetStatus = `sync_error: ${e.message}`; }
      }

      return { content: [{ type: 'text' as const, text: JSON.stringify({
        status: 'created', id: uuid, name: params.farmos_name,
        strata: params.strata, succession_stage: params.succession_stage, sheet_sync: sheetStatus,
      }, null, 2) }] };
    } catch (e: any) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ error: `Failed to create plant type: ${e.message}` }) }] };
    }
  },
};
