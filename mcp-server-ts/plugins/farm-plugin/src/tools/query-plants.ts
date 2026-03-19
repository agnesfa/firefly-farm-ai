import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getFarmOSClient } from '../clients/index.js';
import { formatPlantAsset } from '../helpers/index.js';

export const queryPlantsTool: Tool = {
  namespace: 'fc',
  name: 'query_plants',
  title: 'Search Plant Assets',
  description: 'Search plant assets by section, species, or status.\n\nArgs:\n    section_id: Filter by section (e.g., "P2R3.15-21"). Optional.\n    species: Filter by species name (e.g., "Pigeon Pea"). Partial match. Optional.\n    status: Asset status filter. Default "active".\n\nReturns:\n    List of matching plant assets with name, species, section, and status.',
  paramsSchema: z.object({
    section_id: z.string().optional().describe('Filter by section (e.g., "P2R3.15-21")'),
    species: z.string().optional().describe('Filter by species name (e.g., "Pigeon Pea"). Partial match'),
    status: z.string().default('active').describe('Asset status filter'),
  }).shape,
  options: { readOnlyHint: true },
  handler: async (params, extra) => {
    const client = getFarmOSClient(extra);
    const plants = await client.getPlantAssets(params.section_id, params.species, params.status);
    const formatted = plants.map(formatPlantAsset);
    return {
      content: [{ type: 'text' as const, text: JSON.stringify({
        count: formatted.length,
        filters: { section_id: params.section_id, species: params.species, status: params.status },
        plants: formatted,
      }, null, 2) }],
    };
  },
};
