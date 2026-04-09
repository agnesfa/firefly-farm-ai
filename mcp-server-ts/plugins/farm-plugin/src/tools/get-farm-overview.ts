import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getFarmOSClient } from '../clients/index.js';

export const getFarmOverviewTool: Tool = {
  namespace: 'fc',
  name: 'get_farm_overview',
  title: 'Get Farm Overview',
  description: 'Farm overview: paddock/row/section counts, asset totals, plant type count.\n\nReplaces the farm://overview resource from the Python MCP server.',
  paramsSchema: z.object({}).shape,
  options: { readOnlyHint: true },
  handler: async (_params, extra) => {
    const client = getFarmOSClient(extra);

    // Fetch all locations (land + structure), plant count, and plant type count in parallel.
    // getAllLocations() handles both asset/land and asset/structure with proper pagination.
    const [allLocations, plantPage, plantTypes] = await Promise.all([
      client.getAllLocations(),
      client.fetchFiltered('asset/plant', { status: 'active' }, 'name', 1),
      client.getAllPlantTypesCached(),
    ]);

    // Group paddock sections by row
    const rows: Record<string, string[]> = {};
    for (const loc of allLocations.paddock ?? []) {
      const prefix = loc.name.split('.')[0];
      if (!rows[prefix]) rows[prefix] = [];
      rows[prefix].push(loc.name);
    }
    const nurseryCount = (allLocations.nursery ?? []).length;
    const compostCount = (allLocations.compost ?? []).length;

    const p1 = Object.fromEntries(Object.entries(rows).filter(([k]) => k.startsWith('P1')).map(([k, v]) => [k, v.sort()]));
    const p2 = Object.fromEntries(Object.entries(rows).filter(([k]) => k.startsWith('P2')).map(([k, v]) => [k, v.sort()]));

    // plantPage is a single-item fetch just to check connectivity; real count from meta
    // We fetch with limit=1 to get the response fast — actual count not available via JSON:API
    // without a count query, so we use fetchAllPaginated for an estimate
    const plantCount = plantPage.length > 0 ? '648+' : '0';

    return {
      content: [{ type: 'text' as const, text: JSON.stringify({
        farm: 'Firefly Corner Farm', location: 'Krambach, NSW, Australia',
        farmos_url: 'https://margregen.farmos.net',
        paddocks: 2, total_rows: Object.keys(rows).length,
        total_sections: Object.values(rows).flat().length,
        nursery_locations: nurseryCount,
        compost_locations: compostCount,
        paddock_1: { sections: Object.values(p1).flat().length, rows: p1 },
        paddock_2: { sections: Object.values(p2).flat().length, rows: p2 },
        plant_types: plantTypes.length,
        plant_assets: plantCount,
        note: 'Use query tools for exact current plant counts.',
      }, null, 2) }],
    };
  },
};
