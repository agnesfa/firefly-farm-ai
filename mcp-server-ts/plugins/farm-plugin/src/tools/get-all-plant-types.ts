import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getFarmOSClient } from '../clients/index.js';
import { formatPlantType } from '../helpers/index.js';

export const getAllPlantTypesTool: Tool = {
  namespace: 'fc',
  name: 'get_all_plant_types',
  title: 'Get All Plant Types',
  description: 'Get ALL plant types with full syntropic metadata in a single call.\n\nReturns the complete taxonomy (220+ species) with strata, succession stage,\nlifecycle, lifespan, botanical name, crop family, plant functions, and source.\n\nUSE THIS instead of calling search_plant_types multiple times when you need\ndata for many species (e.g., building inventory sheets, comparing strata across\na row). One call replaces 40+ individual lookups.\n\nResults are cached for 5 minutes — fast on repeated calls within a session.\n\nReturns:\n    All plant types with full metadata, sorted alphabetically.',
  paramsSchema: z.object({}).shape,
  options: { readOnlyHint: true },
  handler: async (_params, extra) => {
    const client = getFarmOSClient(extra);
    const allTypes = await client.getAllPlantTypesCached();
    const formatted = allTypes.map(formatPlantType).sort((a: any, b: any) => (a.name ?? '').toLowerCase().localeCompare((b.name ?? '').toLowerCase()));
    return {
      content: [{ type: 'text' as const, text: JSON.stringify({ count: formatted.length, plant_types: formatted }, null, 2) }],
    };
  },
};
