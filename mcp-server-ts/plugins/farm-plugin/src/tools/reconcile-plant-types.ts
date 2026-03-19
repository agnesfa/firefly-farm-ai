import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getFarmOSClient, getPlantTypesClient } from '../clients/index.js';
import { parsePlantTypeMetadata } from '../helpers/index.js';

export const reconcilePlantTypesTool: Tool = {
  namespace: 'fc',
  name: 'reconcile_plant_types',
  title: 'Reconcile Plant Types',
  description: 'Compare plant types between the Google Sheet and farmOS taxonomy.\n\nDetects drift: strata mismatches, missing entries, metadata differences.\nReturns a report of discrepancies that need to be resolved.\n\nRequires PLANT_TYPES_ENDPOINT to be configured.',
  paramsSchema: z.object({}).shape,
  options: { readOnlyHint: true },
  handler: async (_params, extra) => {
    const ptClient = getPlantTypesClient();
    if (!ptClient) return { content: [{ type: 'text' as const, text: JSON.stringify({ error: 'PLANT_TYPES_ENDPOINT not configured' }) }] };
    const client = getFarmOSClient(extra);

    const sheetData = await ptClient.getReconcileData();
    if (!sheetData.success) return { content: [{ type: 'text' as const, text: JSON.stringify({ error: `Failed to fetch sheet data: ${sheetData.error}` }) }] };
    const sheetTypes: Record<string, any> = {};
    for (const pt of (sheetData.plant_types ?? [])) sheetTypes[pt.farmos_name] = pt;

    const farmosTypesRaw = await client.fetchAllPaginated('taxonomy_term/plant_type');
    const farmosTypes: Record<string, any> = {};
    for (const term of farmosTypesRaw) {
      const name = term.attributes?.name ?? '';
      if (name.startsWith('[ARCHIVED]')) continue;
      const descRaw = term.attributes?.description;
      const descText = typeof descRaw === 'object' ? (descRaw?.value ?? '') : String(descRaw ?? '');
      const meta = parsePlantTypeMetadata(descText);
      farmosTypes[name] = { farmos_name: name, strata: meta.strata ?? '', succession_stage: meta.succession_stage ?? '', botanical_name: meta.botanical_name ?? '', crop_family: meta.crop_family ?? '', plant_functions: meta.plant_functions ?? '' };
    }

    const mismatches: any[] = [];
    const inSheetNotFarmos: string[] = [];
    const inFarmosNotSheet: string[] = [];

    for (const [name, sheetEntry] of Object.entries(sheetTypes)) {
      if (!(name in farmosTypes)) { inSheetNotFarmos.push(name); continue; }
      const farmosEntry = farmosTypes[name];
      const diffs: any[] = [];
      for (const field of ['strata', 'succession_stage', 'botanical_name', 'crop_family']) {
        const sv = (sheetEntry[field] ?? '').trim().toLowerCase();
        const fv = (farmosEntry[field] ?? '').trim().toLowerCase();
        if (sv && fv && sv !== fv) diffs.push({ field, sheet: sheetEntry[field], farmos: farmosEntry[field] });
      }
      if (diffs.length > 0) mismatches.push({ farmos_name: name, differences: diffs });
    }
    for (const name of Object.keys(farmosTypes)) { if (!(name in sheetTypes)) inFarmosNotSheet.push(name); }

    return {
      content: [{ type: 'text' as const, text: JSON.stringify({
        sheet_count: Object.keys(sheetTypes).length, farmos_count: Object.keys(farmosTypes).length,
        mismatches, mismatch_count: mismatches.length,
        in_sheet_not_farmos: inSheetNotFarmos, in_farmos_not_sheet: inFarmosNotSheet,
        status: !mismatches.length && !inSheetNotFarmos.length && !inFarmosNotSheet.length ? 'clean' : 'drift_detected',
      }, null, 2) }],
    };
  },
};
