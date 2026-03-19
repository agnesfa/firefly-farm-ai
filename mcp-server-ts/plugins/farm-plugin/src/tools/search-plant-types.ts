import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getFarmOSClient } from '../clients/index.js';
import { formatPlantType } from '../helpers/index.js';

export const searchPlantTypesTool: Tool = {
  namespace: 'fc',
  name: 'search_plant_types',
  title: 'Search Plant Types',
  description: 'Search plant types by name (partial match).\n\nArgs:\n    query: Search term (e.g., "Pigeon", "Tomato", "Macadamia").\n\nReturns:\n    Matching plant types with syntropic metadata.',
  paramsSchema: z.object({
    query: z.string().describe('Search term'),
  }).shape,
  options: { readOnlyHint: true },
  handler: async (params, extra) => {
    const client = getFarmOSClient(extra);
    const allTypes = await client.getPlantTypeDetails();
    const queryLower = params.query.toLowerCase();
    const matches = allTypes
      .filter((t: any) => (t.attributes?.name ?? '').toLowerCase().includes(queryLower))
      .map(formatPlantType);
    return {
      content: [{ type: 'text' as const, text: JSON.stringify({ query: params.query, count: matches.length, plant_types: matches }, null, 2) }],
    };
  },
};
