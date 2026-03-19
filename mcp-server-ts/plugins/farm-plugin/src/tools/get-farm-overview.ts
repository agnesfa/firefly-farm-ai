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
    const sections = await client.getSectionAssets();
    const rows: Record<string, string[]> = {};
    for (const s of sections) {
      const name = s.attributes?.name ?? '';
      const prefix = name.split('.')[0];
      if (!rows[prefix]) rows[prefix] = [];
      rows[prefix].push(name);
    }
    const p1 = Object.fromEntries(Object.entries(rows).filter(([k]) => k.startsWith('P1')).map(([k, v]) => [k, v.sort()]));
    const p2 = Object.fromEntries(Object.entries(rows).filter(([k]) => k.startsWith('P2')).map(([k, v]) => [k, v.sort()]));

    return {
      content: [{ type: 'text' as const, text: JSON.stringify({
        farm: 'Firefly Corner Farm', location: 'Krambach, NSW, Australia',
        farmos_url: 'https://margregen.farmos.net',
        paddocks: 2, total_rows: Object.keys(rows).length, total_sections: sections.length,
        paddock_1: { sections: Object.values(p1).flat().length, rows: p1 },
        paddock_2: { sections: Object.values(p2).flat().length, rows: p2, note: 'P2 has plant assets and observation data imported' },
        plant_assets: '596+', plant_types: '223',
        note: 'Use query tools for exact current counts.',
      }, null, 2) }],
    };
  },
};
