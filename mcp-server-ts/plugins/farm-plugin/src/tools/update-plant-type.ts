import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getFarmOSClient, getPlantTypesClient } from '../clients/index.js';
import { buildPlantTypeDescription, parsePlantTypeMetadata } from '../helpers/index.js';

export const updatePlantTypeTool: Tool = {
  namespace: 'fc',
  name: 'update_plant_type',
  title: 'Update Plant Type',
  description: 'Update an existing plant type in the farmOS taxonomy.\n\nFetches the existing term, merges in the provided updates,\nrebuilds the description with syntropic metadata, and patches.\n\nArgs:\n    farmos_name: The exact name of the plant type to update. Must already exist.\n    botanical_name: New scientific name (optional).\n    strata: New height layer (optional).\n    succession_stage: New temporal role (optional).\n    plant_functions: New function tags, comma-separated (optional).\n    crop_family: New botanical family (optional).\n    origin: New geographic origin (optional).\n    description: New free-text description (optional).\n    lifespan_years: New lifespan (optional).\n    lifecycle_years: New lifecycle (optional).\n    source: New source (optional).\n    maturity_days: New days to maturity (optional).\n    transplant_days: New days to transplant (optional).',
  paramsSchema: z.object({
    farmos_name: z.string().describe('The exact name of the plant type'),
    botanical_name: z.string().optional(), strata: z.string().optional(),
    succession_stage: z.string().optional(), plant_functions: z.string().optional(),
    crop_family: z.string().optional(), origin: z.string().optional(),
    description: z.string().optional(), lifespan_years: z.string().optional(),
    lifecycle_years: z.string().optional(), source: z.string().optional(),
    maturity_days: z.number().optional(), transplant_days: z.number().optional(),
  }).shape,
  options: { readOnlyHint: false },
  handler: async (params, extra) => {
    const client = getFarmOSClient(extra);
    const existing = await client.fetchByName('taxonomy_term/plant_type', params.farmos_name);
    if (existing.length === 0) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ error: `Plant type '${params.farmos_name}' not found.` }) }] };
    }
    const term = existing[0];
    const uuid = term.id;
    const descRaw = term.attributes?.description;
    const existingText = typeof descRaw === 'object' ? (descRaw?.value ?? '') : String(descRaw ?? '');
    const currentMeta = parsePlantTypeMetadata(existingText);
    const plainDesc = existingText.includes('\n\n---\n') ? existingText.split('\n\n---\n')[0] : existingText;

    const fields = {
      description: params.description ?? plainDesc,
      botanical_name: params.botanical_name ?? currentMeta.botanical_name,
      lifecycle_years: params.lifecycle_years ?? currentMeta.lifecycle_years,
      strata: params.strata ?? currentMeta.strata,
      succession_stage: params.succession_stage ?? currentMeta.succession_stage,
      plant_functions: params.plant_functions ?? currentMeta.plant_functions,
      crop_family: params.crop_family ?? currentMeta.crop_family,
      lifespan_years: params.lifespan_years ?? currentMeta.lifespan_years,
      source: params.source ?? currentMeta.source,
    };
    const newDescription = buildPlantTypeDescription(fields);
    const patchAttrs: any = { description: { value: newDescription, format: 'default' } };
    if (params.maturity_days != null) patchAttrs.maturity_days = params.maturity_days;
    if (params.transplant_days != null) patchAttrs.transplant_days = params.transplant_days;

    try {
      await client.updatePlantType(uuid, patchAttrs);
      const updatedFields = Object.entries({
        botanical_name: params.botanical_name, strata: params.strata,
        succession_stage: params.succession_stage, plant_functions: params.plant_functions,
        crop_family: params.crop_family, description: params.description,
        lifespan_years: params.lifespan_years, lifecycle_years: params.lifecycle_years,
        source: params.source, maturity_days: params.maturity_days, transplant_days: params.transplant_days,
      }).filter(([, v]) => v != null).map(([k]) => k);

      let sheetStatus = 'not_configured';
      const ptClient = getPlantTypesClient();
      if (ptClient) {
        try {
          const sheetFields: Record<string, string> = {};
          if (params.botanical_name != null) sheetFields.botanical_name = params.botanical_name;
          if (params.strata != null) sheetFields.strata = params.strata;
          if (params.succession_stage != null) sheetFields.succession_stage = params.succession_stage;
          if (params.plant_functions != null) sheetFields.plant_functions = params.plant_functions;
          if (params.crop_family != null) sheetFields.crop_family = params.crop_family;
          if (params.origin != null) sheetFields.origin = params.origin;
          if (params.description != null) sheetFields.description = params.description;
          if (params.lifespan_years != null) sheetFields.lifespan_years = params.lifespan_years;
          if (params.lifecycle_years != null) sheetFields.lifecycle_years = params.lifecycle_years;
          if (params.source != null) sheetFields.source = params.source;
          if (params.maturity_days != null) sheetFields.maturity_days = String(params.maturity_days);
          if (params.transplant_days != null) sheetFields.transplant_days = String(params.transplant_days);
          if (Object.keys(sheetFields).length > 0) {
            const result = await ptClient.update(params.farmos_name, sheetFields);
            sheetStatus = result.success ? 'synced' : (result.error ?? 'failed');
          } else { sheetStatus = 'no_sheet_fields'; }
        } catch (e: any) { sheetStatus = `sync_error: ${e.message}`; }
      }

      return { content: [{ type: 'text' as const, text: JSON.stringify({
        status: 'updated', id: uuid, name: params.farmos_name, updated_fields: updatedFields, sheet_sync: sheetStatus,
      }, null, 2) }] };
    } catch (e: any) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ error: `Failed to update plant type: ${e.message}` }) }] };
    }
  },
};
