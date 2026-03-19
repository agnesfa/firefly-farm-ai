import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getFarmOSClient } from '../clients/index.js';
import { formatPlantAsset, formatLog } from '../helpers/index.js';

export const getPlantDetailTool: Tool = {
  namespace: 'fc',
  name: 'get_plant_detail',
  title: 'Get Plant Detail',
  description: 'Get full detail of a plant asset including all associated logs.\n\nArgs:\n    plant_name: The exact plant asset name (e.g., "25 APR 2025 - Pigeon Pea - P2R2.0-3").\n                Can also be a partial name for search.\n\nReturns:\n    Plant asset details and all associated logs.',
  paramsSchema: z.object({
    plant_name: z.string().describe('The exact plant asset name or partial name for search'),
  }).shape,
  options: { readOnlyHint: true },
  handler: async (params, extra) => {
    const client = getFarmOSClient(extra);
    let assets = await client.fetchByName('asset/plant', params.plant_name);
    if (assets.length === 0) {
      const allPlants = await client.getPlantAssets(undefined, params.plant_name);
      if (allPlants.length === 0) {
        return { content: [{ type: 'text' as const, text: JSON.stringify({ error: `Plant '${params.plant_name}' not found` }) }] };
      }
      assets = allPlants.slice(0, 5);
    }

    if (assets.length === 1) {
      const formatted = formatPlantAsset(assets[0]);
      const logs = await client.getLogs(undefined, formatted.section, formatted.species, 20);
      const formattedLogs = logs.map(formatLog);
      return {
        content: [{ type: 'text' as const, text: JSON.stringify({ plant: formatted, log_count: formattedLogs.length, logs: formattedLogs }, null, 2) }],
      };
    }

    const formatted = assets.map(formatPlantAsset);
    return {
      content: [{ type: 'text' as const, text: JSON.stringify({
        note: `Multiple matches found for '${params.plant_name}'. Showing first ${formatted.length}.`,
        matches: formatted,
      }, null, 2) }],
    };
  },
};
